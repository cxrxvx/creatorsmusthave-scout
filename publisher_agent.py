import json
import os
import re
import requests
from datetime import datetime, date
from requests.auth import HTTPBasicAuth
from config import (
    WP_URL, WP_USERNAME, WP_APP_PASSWORD,
    PUBLISH_MODE, SITE_NAME
)

HANDOFFS_FILE = "memory/handoffs.json"
KEYWORD_DATA_FILE = "memory/keyword_data.json"

DAILY_PUBLISH_CAP = 3
URGENT_SCORE_THRESHOLD = 75

DEFAULT_CATEGORY_ID = 1
CATEGORY_MAP = {
    "ai-tools": 1,
    "other": 1,
}

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def write_log(entry):
    log_dir = "memory/logs/publisher_agent"
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    with open(f"{log_dir}/{today}.md", "a") as f:
        f.write(entry + "\n")

def sort_by_urgency(articles):
    urgent = []
    normal = []
    for slug, article in articles.items():
        score = article.get("tool_score", 0)
        if score >= URGENT_SCORE_THRESHOLD:
            urgent.append((slug, article))
        else:
            normal.append((slug, article))
    urgent.sort(key=lambda x: x[1].get("tool_score", 0), reverse=True)
    normal.sort(key=lambda x: x[1].get("written_date", "9999-99-99"))
    sorted_articles = dict(urgent + normal)
    if urgent:
        print(f"   🔥 Urgent (score {URGENT_SCORE_THRESHOLD}+): {', '.join(a.get('tool_name', s) for s, a in urgent)}")
    if normal:
        print(f"   📋 Normal queue: {', '.join(a.get('tool_name', s) for s, a in normal)}")
    return sorted_articles

def get_auth():
    return HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)

def test_connection():
    try:
        r = requests.get(f"{WP_URL}/wp-json/wp/v2/posts?per_page=1", auth=get_auth(), timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"   Connection failed: {e}")
        return False

def get_or_create_tag(tag_name):
    r = requests.get(f"{WP_URL}/wp-json/wp/v2/tags", params={"search": tag_name}, auth=get_auth(), timeout=10)
    if r.status_code == 200:
        for tag in r.json():
            if tag["name"].lower() == tag_name.lower():
                return tag["id"]
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/tags", json={"name": tag_name}, auth=get_auth(), timeout=10)
    if r.status_code == 201:
        return r.json()["id"]
    return None

def publish_to_wordpress(article):
    title = article.get("article_title", article.get("tool_name", ""))
    content = article.get("article_html", "")
    content = re.sub(r'<h1[^>]*>.*?</h1>', '', content, count=1, flags=re.DOTALL).strip()

    # Strip emojis from headings — keep articles clean and professional
    import unicodedata
    content = ''.join(c for c in content if not unicodedata.category(c).startswith('So'))
    category_id = CATEGORY_MAP.get(article.get("category", "other"), DEFAULT_CATEGORY_ID)
    tag_ids = []
    pk = article.get("primary_keyword", "")
    if pk:
        tid = get_or_create_tag(pk)
        if tid:
            tag_ids.append(tid)
    post_data = {
        "title": title,
        "content": content,
        "slug": article.get("url_slug", ""),
        "status": PUBLISH_MODE,
        "categories": [category_id],
        "tags": tag_ids,
        "comment_status": "open",
        "ping_status": "closed",
        "format": "standard",
    }
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/posts", json=post_data, auth=get_auth(), timeout=30)
    if r.status_code == 201:
        post = r.json()
        post_id = post["id"]
        return {"success": True, "post_id": post_id, "post_url": post.get("link", ""), "preview_url": f"{WP_URL}/?p={post_id}&preview=true"}
    else:
        return {"success": False, "error": f"HTTP {r.status_code}: {r.json().get('message', r.text[:200])}"}

def run():
    print(f"\n📤 Publisher Agent starting...")
    print(f"   Mode: {PUBLISH_MODE.upper()} | Daily cap: {DAILY_PUBLISH_CAP}\n")
    write_log(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Publisher run ({PUBLISH_MODE})")
    print("   🔌 Testing WordPress connection...")
    if not test_connection():
        print("   WordPress connection failed.")
        write_log("FAILED: WordPress connection error")
        return
    print("   ✅ WordPress connected\n")
    handoffs = load_json(HANDOFFS_FILE, {})
    keyword_data = load_json(KEYWORD_DATA_FILE, {})
    all_ready = {
        slug: article for slug, article in handoffs.items()
        if article.get("status") in ("pending_edit", "ready_to_publish")
        and not article.get("wp_post_id")
    }
    if not all_ready:
        print("   No articles ready to publish.")
        write_log("No articles ready.")
        return
    print(f"📋 {len(all_ready)} article(s) ready — cap is {DAILY_PUBLISH_CAP}/day\n")
    sorted_articles = sort_by_urgency(all_ready)
    to_publish = dict(list(sorted_articles.items())[:DAILY_PUBLISH_CAP])
    held_back = len(all_ready) - len(to_publish)
    print(f"\n   Publishing {len(to_publish)} now", end="")
    if held_back > 0:
        print(f" | {held_back} held for tomorrow")
        write_log(f"Held {held_back} articles — cap {DAILY_PUBLISH_CAP}/day")
    else:
        print()
    print()
    published = 0
    failed = 0
    for slug, article in to_publish.items():
        tool_name = article.get("tool_name", slug)
        score = article.get("tool_score", "?")
        word_count = article.get("word_count", "?")
        is_urgent = isinstance(score, int) and score >= URGENT_SCORE_THRESHOLD
        print(f"📝 Publishing: {tool_name} {'🔥' if is_urgent else ''}")
        print(f"   Slug: {slug} | Score: {score} | Words: {word_count}")
        result = publish_to_wordpress(article)
        if result["success"]:
            post_id = result["post_id"]
            preview_url = result["preview_url"]
            print(f"   ✅ {PUBLISH_MODE.capitalize()}ed → Post ID: {post_id}")
            print(f"   🔗 Preview: {preview_url}\n")
            handoffs[slug]["wp_post_id"] = post_id
            handoffs[slug]["wp_post_url"] = result["post_url"]
            handoffs[slug]["wp_preview_url"] = preview_url
            handoffs[slug]["published_date"] = datetime.now().strftime("%Y-%m-%d")
            handoffs[slug]["status"] = "published" if PUBLISH_MODE == "publish" else "draft_live"
            tool_key = article.get("tool_key", "")
            if tool_key and tool_key in keyword_data:
                keyword_data[tool_key]["status"] = "published" if PUBLISH_MODE == "publish" else "draft_live"
                keyword_data[tool_key]["wp_post_id"] = post_id
            write_log(f"✅ {tool_name} (score {score}) → Post ID {post_id}")
            published += 1
        else:
            print(f"   Failed: {result['error']}\n")
            write_log(f"FAILED {tool_name}: {result['error']}")
            failed += 1
    save_json(HANDOFFS_FILE, handoffs)
    save_json(KEYWORD_DATA_FILE, keyword_data)
    print(f"{'─' * 45}")
    print(f"✅ Publisher done. Published: {published} | Failed: {failed}")
    if held_back > 0:
        print(f"   {held_back} article(s) queued for tomorrow")
    if PUBLISH_MODE == "draft":
        print(f"\n📋 Review drafts: {WP_URL}/wp-admin/edit.php")
    write_log(f"Done. Published: {published} | Failed: {failed} | Held: {held_back}")

if __name__ == "__main__":
    run()
