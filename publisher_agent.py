import json
import os
import requests
from datetime import datetime
from requests.auth import HTTPBasicAuth
from config import (
    WP_URL, WP_USERNAME, WP_APP_PASSWORD,
    PUBLISH_MODE, SITE_NAME
)

HANDOFFS_FILE = "memory/handoffs.json"
KEYWORD_DATA_FILE = "memory/keyword_data.json"

# WordPress category ID for AI Tools
# You can find this in WordPress → Posts → Categories
# Default to 1 (Uncategorized) until you create proper categories
DEFAULT_CATEGORY_ID = 1

# Map our internal categories to WordPress category IDs
# Add more as you create categories in WordPress
CATEGORY_MAP = {
    "ai-tools": 1,
    "other": 1,
}


# ─────────────────────────────────────────
# FILE HELPERS
# ─────────────────────────────────────────

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


# ─────────────────────────────────────────
# WORDPRESS API
# ─────────────────────────────────────────

def get_auth():
    return HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)


def test_connection():
    """Verify WordPress API is reachable before trying to publish."""
    try:
        response = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts?per_page=1",
            auth=get_auth(),
            timeout=10
        )
        if response.status_code == 200:
            return True
        else:
            print(f"   ❌ WordPress API error: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ WordPress connection failed: {e}")
        return False


def get_or_create_tag(tag_name):
    """Get existing tag ID or create a new one. Returns tag ID."""
    # Check if tag exists
    response = requests.get(
        f"{WP_URL}/wp-json/wp/v2/tags",
        params={"search": tag_name},
        auth=get_auth(),
        timeout=10
    )
    if response.status_code == 200:
        tags = response.json()
        for tag in tags:
            if tag["name"].lower() == tag_name.lower():
                return tag["id"]

    # Create new tag
    response = requests.post(
        f"{WP_URL}/wp-json/wp/v2/tags",
        json={"name": tag_name},
        auth=get_auth(),
        timeout=10
    )
    if response.status_code == 201:
        return response.json()["id"]

    return None


def publish_to_wordpress(article):
    """
    Send article to WordPress.
    PUBLISH_MODE = "draft"   → saves as draft, not visible to public
    PUBLISH_MODE = "publish" → goes live immediately
    """

    tool_name = article.get("tool_name", "Unknown Tool")
    title = article.get("article_title", tool_name)
    content = article.get("article_html", "")
    slug = article.get("url_slug", "")
    category = article.get("category", "other")

    # WordPress inserts the post title as H1 automatically.
    # Strip the H1 from article HTML to prevent a duplicate title showing on the page.
    import re
    content = re.sub(r'<h1[^>]*>.*?</h1>', '', content, count=1, flags=re.DOTALL).strip()

    # Get WordPress category ID
    category_id = CATEGORY_MAP.get(category, DEFAULT_CATEGORY_ID)

    # Build tags from keyword cluster if available
    tag_ids = []
    primary_keyword = article.get("primary_keyword", "")
    if primary_keyword:
        tag_id = get_or_create_tag(primary_keyword)
        if tag_id:
            tag_ids.append(tag_id)

    # Build the WordPress post payload
    post_data = {
        "title": title,
        "content": content,
        "slug": slug,
        "status": PUBLISH_MODE,          # "draft" or "publish"
        "categories": [category_id],
        "tags": tag_ids,
        "comment_status": "open",
        "ping_status": "closed",
        "format": "standard",
    }

    response = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=post_data,
        auth=get_auth(),
        timeout=30
    )

    if response.status_code == 201:
        post = response.json()
        post_id = post["id"]
        post_url = post.get("link", "")
        preview_url = f"{WP_URL}/?p={post_id}&preview=true"
        return {
            "success": True,
            "post_id": post_id,
            "post_url": post_url,
            "preview_url": preview_url
        }
    else:
        error_msg = response.json().get("message", response.text[:200])
        return {
            "success": False,
            "error": f"HTTP {response.status_code}: {error_msg}"
        }


# ─────────────────────────────────────────
# MAIN RUN
# ─────────────────────────────────────────

def run():
    print(f"\n📤 Publisher Agent starting...")
    print(f"   Mode: {PUBLISH_MODE.upper()}\n")
    write_log(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Publisher Agent run ({PUBLISH_MODE})")

    # Test connection first
    print("   🔌 Testing WordPress connection...")
    if not test_connection():
        print("   ❌ Cannot reach WordPress. Check your credentials in config.py.")
        write_log("FAILED: WordPress connection error")
        return

    print("   ✅ WordPress connected\n")

    handoffs = load_json(HANDOFFS_FILE, {})
    keyword_data = load_json(KEYWORD_DATA_FILE, {})

    # Find articles ready to publish
    # In Phase 1: pending_edit articles go straight to WordPress as drafts
    # In Phase 2+: editor_agent sets status to "ready_to_publish"
    all_ready = {
        slug: article for slug, article in handoffs.items()
        if article.get("status") in ("pending_edit", "ready_to_publish")
        and not article.get("wp_post_id")  # skip already published
    }

    if not all_ready:
        print("   ℹ️  No articles ready to publish.")
        write_log("No articles ready.")
        return

    # Apply publishing cap — only publish up to the daily limit
    # Articles over the cap stay as drafts and publish on the next run
    ready = dict(list(all_ready.items())[:DAILY_PUBLISH_CAP])
    held_back = len(all_ready) - len(ready)
    if held_back > 0:
        print(f"   📋 {held_back} article(s) held in draft — will publish tomorrow")
        write_log(f"Held {held_back} articles — daily publish cap ({DAILY_PUBLISH_CAP}) reached")

    print(f"📋 Found {len(ready)} article(s) to publish as {PUBLISH_MODE}s\n")
    write_log(f"Found {len(ready)} articles. Mode: {PUBLISH_MODE}")

    published = 0
    failed = 0

    for slug, article in ready.items():
        tool_name = article.get("tool_name", slug)
        word_count = article.get("word_count", "?")

        print(f"📝 Publishing: {tool_name}")
        print(f"   Slug: {slug} | Words: {word_count}")

        result = publish_to_wordpress(article)

        if result["success"]:
            post_id = result["post_id"]
            preview_url = result["preview_url"]

            print(f"   ✅ {PUBLISH_MODE.capitalize()}ed → Post ID: {post_id}")
            print(f"   🔗 Preview: {preview_url}\n")

            # Update handoffs with WordPress post ID
            handoffs[slug]["wp_post_id"] = post_id
            handoffs[slug]["wp_post_url"] = result["post_url"]
            handoffs[slug]["wp_preview_url"] = preview_url
            handoffs[slug]["published_date"] = datetime.now().strftime("%Y-%m-%d")
            handoffs[slug]["status"] = "published" if PUBLISH_MODE == "publish" else "draft_live"

            # Update keyword_data status
            tool_key = article.get("tool_key", "")
            if tool_key and tool_key in keyword_data:
                keyword_data[tool_key]["status"] = "published" if PUBLISH_MODE == "publish" else "draft_live"
                keyword_data[tool_key]["wp_post_id"] = post_id

            write_log(f"✅ {tool_name} → Post ID {post_id} | {preview_url}")
            published += 1

        else:
            print(f"   ❌ Failed: {result['error']}\n")
            write_log(f"❌ {tool_name} → FAILED: {result['error']}")
            failed += 1

    # Save updated files
    save_json(HANDOFFS_FILE, handoffs)
    save_json(KEYWORD_DATA_FILE, keyword_data)

    # Summary
    print(f"{'─' * 45}")
    print(f"✅ Publisher Agent done.")
    print(f"   Published: {published} | Failed: {failed}")

    if PUBLISH_MODE == "draft":
        print(f"\n📋 DRAFT REVIEW INSTRUCTIONS:")
        print(f"   Go to: {WP_URL}/wp-admin/edit.php")
        print(f"   Click any draft to preview and review")
        print(f"   When happy: change status to 'Published' manually")
        print(f"   Or: set PUBLISH_MODE = 'publish' in config.py to auto-publish")

    write_log(f"Done. Published: {published} | Failed: {failed}")


if __name__ == "__main__":
    run()