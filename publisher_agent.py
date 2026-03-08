"""
publisher_agent.py — Publishing Agent for CXRXVX Affiliates
==============================================================
Phase 2.5 Opus Upgrade:
  ✅ Dynamic category from article data (not hardcoded "AI Tools")
  ✅ Roundup/comparison priority boost — roundups score higher (more affiliate links)
  ✅ Fixed field name mismatches (article_title, tool_score, tool_url)
  ✅ --cap CLI argument support (scheduler passes --cap N)
  ✅ Saves wp_post_url field — internal_link_agent needs this
  ✅ File logging to memory/logs/publisher_agent/
  ✅ Broader affiliate link injection — uses tool_url from article data
  ✅ All existing features preserved (priority scoring, freshness, queue preview, emoji strip)

Drop this file into your cxrxvx-ai-empire/ folder to replace the old publisher_agent.py.
"""

import json
import re
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
MEMORY_DIR = BASE_DIR / "memory"

HANDOFFS_FILE    = MEMORY_DIR / "handoffs.json"
KEYWORD_FILE     = MEMORY_DIR / "keyword_data.json"
AFFILIATE_FILE   = MEMORY_DIR / "affiliate_links.json"
TOOL_DB_FILE     = MEMORY_DIR / "tool_database.json"
COUNTER_FILE     = MEMORY_DIR / ".daily_counter.json"
LOGS_DIR         = MEMORY_DIR / "logs" / "publisher_agent"

# ── Config ─────────────────────────────────────────────────────────────────
sys.path.insert(0, str(BASE_DIR))
from config import (WP_URL, WP_USERNAME, WP_APP_PASSWORD,
                    PUBLISH_MODE, SITE_NAME)

WP_AUTH = (WP_USERNAME, WP_APP_PASSWORD)

# ⚡ Phase 2.5: --cap CLI argument support (scheduler passes --cap N)
DEFAULT_CAP = 3
DAILY_PUBLISH_CAP = DEFAULT_CAP

for i, arg in enumerate(sys.argv):
    if arg == "--cap" and i + 1 < len(sys.argv):
        try:
            DAILY_PUBLISH_CAP = int(sys.argv[i + 1])
        except ValueError:
            pass

# Also check environment variable as fallback
if DAILY_PUBLISH_CAP == DEFAULT_CAP:
    env_cap = os.environ.get("DAILY_PUBLISH_CAP")
    if env_cap:
        try:
            DAILY_PUBLISH_CAP = int(env_cap)
        except ValueError:
            pass

URGENT_SCORE_THRESHOLD = 75

# Saturated categories — penalised if no affiliate link
SATURATED_CATEGORIES = ["AI Writing", "AI Copywriting", "AI SEO Writing"]

# ── Emoji strip pattern ────────────────────────────────────────────────────
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"
    "]+",
    flags=re.UNICODE
)

# ── Category mapping for WordPress ────────────────────────────────────────
# Maps tool_scout categories to WordPress-friendly display names
CATEGORY_DISPLAY_NAMES = {
    "video":        "Video Tools",
    "audio":        "Audio & Podcast Tools",
    "writing":      "Writing & AI Copy Tools",
    "image":        "Image & Design Tools",
    "seo":          "SEO Tools",
    "email":        "Email & Newsletter Tools",
    "courses":      "Course & Coaching Tools",
    "productivity": "Productivity Tools",
    "other":        "Creator Tools",
}

# Ensure log directory exists
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def log(msg):
    """Print and write to log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{today}.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")


def strip_emojis(text: str) -> str:
    return EMOJI_PATTERN.sub("", text).strip()


def strip_h1(html: str) -> str:
    """Remove the first H1 tag — WordPress uses the post title instead."""
    return re.sub(r"<h1[^>]*>.*?</h1>", "", html, count=1,
                  flags=re.IGNORECASE | re.DOTALL).strip()


def get_daily_count() -> int:
    counter = load_json(COUNTER_FILE, {})
    today   = datetime.now().strftime("%Y-%m-%d")
    if counter.get("date") != today:
        return 0
    return counter.get("count", 0)


def increment_daily_count():
    counter = load_json(COUNTER_FILE, {})
    today   = datetime.now().strftime("%Y-%m-%d")
    if counter.get("date") != today:
        counter = {"date": today, "count": 0}
    counter["count"] = counter.get("count", 0) + 1
    save_json(COUNTER_FILE, counter)


def days_since(date_str: str) -> int:
    if not date_str:
        return 9999
    try:
        discovered = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (datetime.now() - discovered).days
    except Exception:
        return 9999


# ══════════════════════════════════════════════════════════════════════════
#  SMART PRIORITY SCORING — updated for roundups/comparisons
# ══════════════════════════════════════════════════════════════════════════

def calculate_priority(article: dict, affiliate_links: dict,
                       tool_db: dict) -> int:
    """
    Calculate publish priority score for an article.
    Higher score = publishes first.
    
    Phase 2.5 additions:
    - Roundup articles get +15 bonus (5-8 affiliate links per article)
    - Comparison articles get +10 bonus (rank for both tool names)
    """
    tool_name    = article.get("tool_name", "").lower().strip()
    base_score   = article.get("tool_score", article.get("score", 60))
    article_type = article.get("article_type", "review")
    priority     = base_score

    # ── Affiliate bonus ──────────────────────────────────────────────────
    has_link = tool_name in affiliate_links and \
               affiliate_links[tool_name].get("status") == "active"

    if has_link:
        priority += 30
    else:
        tool_key = re.sub(r"[^a-z0-9_]", "_", tool_name).strip("_")
        tool_data = tool_db.get(tool_key, {})
        if isinstance(tool_data, dict) and tool_data.get("has_affiliate_potential", True):
            priority += 10

    # ── Article type bonus (Phase 2.5) ───────────────────────────────────
    if article_type == "roundup":
        priority += 15   # 5-8 affiliate links per article = highest conversion
    elif article_type == "comparison":
        priority += 10   # Ranks for both tool names = double traffic

    # ── Freshness bonus ──────────────────────────────────────────────────
    tool_key  = re.sub(r"[^a-z0-9_]", "_", tool_name).strip("_")
    tool_data = tool_db.get(tool_key, {})
    if not isinstance(tool_data, dict):
        tool_data = {}
    date_str  = (tool_data.get("discovered_date") or
                 article.get("written_date", ""))
    age_days  = days_since(date_str)

    if age_days <= 7:
        priority += 35
        article["_freshness_tag"] = "🔥 FRESH (≤7d)"
    elif age_days <= 14:
        priority += 25
        article["_freshness_tag"] = "⚡ NEW (≤14d)"
    elif age_days <= 30:
        priority += 15
        article["_freshness_tag"] = "✨ RECENT (≤30d)"
    elif age_days <= 90:
        priority += 5
        article["_freshness_tag"] = "📅 Recent (≤90d)"
    else:
        article["_freshness_tag"] = "📚 Established"

    # ── Saturation penalty ───────────────────────────────────────────────
    category = tool_data.get("category", article.get("category", ""))
    if category in SATURATED_CATEGORIES and not has_link:
        priority -= 20
        article["_freshness_tag"] += " ⚠️ saturated"

    # ── Urgency override ─────────────────────────────────────────────────
    if base_score >= URGENT_SCORE_THRESHOLD:
        priority += 10

    return priority


def sort_articles(articles: list, affiliate_links: dict,
                  tool_db: dict) -> list:
    for a in articles:
        a["_priority_score"] = calculate_priority(a, affiliate_links, tool_db)
    return sorted(articles, key=lambda x: -x["_priority_score"])


# ══════════════════════════════════════════════════════════════════════════
#  AFFILIATE LINK INJECTION — broader matching
# ══════════════════════════════════════════════════════════════════════════

def inject_affiliate_links(html: str, tool_name: str, tool_url: str,
                            affiliate_links: dict) -> tuple[str, bool]:
    """
    Replace plain tool URLs with affiliate links in CTAs.
    Returns (updated_html, was_injected).
    
    Phase 2.5: Uses tool_url from article data for broader matching.
    """
    key = tool_name.lower().strip()
    if key not in affiliate_links:
        return html, False
    entry = affiliate_links[key]
    if entry.get("status") != "active":
        return html, False

    affiliate_url = entry["url"]
    injected = False

    # Method 1: Replace the exact tool_url from article data
    if tool_url and tool_url in html:
        html = html.replace(tool_url, affiliate_url)
        injected = True

    # Method 2: Regex match common domain patterns
    domain_pattern = re.compile(
        r'href="https?://(?:www\.)?'
        + re.escape(key.replace(" ", "").replace("_", ""))
        + r'(?:\.com|\.ai|\.io|\.co|\.fm|\.so|\.pro)?(?:/[^"]*)??"',
        re.IGNORECASE
    )
    if domain_pattern.search(html):
        html = domain_pattern.sub(f'href="{affiliate_url}"', html)
        injected = True

    return html, injected


def inject_roundup_affiliate_links(html: str, roundup_tools: list,
                                    affiliate_links: dict) -> tuple[str, int]:
    """
    For roundup articles: inject affiliate links for each tool mentioned.
    Returns (updated_html, count_of_injections).
    """
    injections = 0
    for tool_info in roundup_tools:
        t_name = tool_info if isinstance(tool_info, str) else tool_info.get("name", "")
        if not t_name:
            continue
        t_key = t_name.lower().strip()
        if t_key not in affiliate_links:
            continue
        entry = affiliate_links[t_key]
        if entry.get("status") != "active":
            continue

        aff_url = entry["url"]
        # Try to find and replace this tool's URLs in the HTML
        domain_slug = re.sub(r"[^a-z0-9]", "", t_key)
        pattern = re.compile(
            r'href="https?://(?:www\.)?' + re.escape(domain_slug)
            + r'(?:\.com|\.ai|\.io|\.co|\.fm)?(?:/[^"]*)??"',
            re.IGNORECASE
        )
        if pattern.search(html):
            html = pattern.sub(f'href="{aff_url}"', html)
            injections += 1

    return html, injections


# ══════════════════════════════════════════════════════════════════════════
#  WORDPRESS PUBLISHING
# ══════════════════════════════════════════════════════════════════════════

def get_or_create_category(category_name: str) -> int | None:
    """Get WordPress category ID, create if it doesn't exist."""
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/categories",
            params={"search": category_name},
            auth=WP_AUTH, timeout=15
        )
        if resp.status_code == 200:
            cats = resp.json()
            if cats:
                return cats[0]["id"]
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/categories",
            json={"name": category_name},
            auth=WP_AUTH, timeout=15
        )
        if resp.status_code == 201:
            return resp.json()["id"]
    except Exception as e:
        log(f"   ⚠️  Category error: {e}")
    return None


def get_category_for_article(article: dict) -> str:
    """
    Get the WordPress category name for this article.
    Uses the article's category field, maps to display name.
    Falls back to "Creator Tools" if unknown.
    """
    raw_category = article.get("category", article.get("tool_category", "other"))
    return CATEGORY_DISPLAY_NAMES.get(raw_category, "Creator Tools")


def publish_to_wordpress(article: dict) -> dict | None:
    """Post article to WordPress. Returns WP response dict or None."""
    html    = article.get("article_html", "")
    title   = strip_emojis(article.get("article_title", article.get("title", "Untitled")))
    slug    = article.get("url_slug", article.get("slug", ""))
    tool    = article.get("tool_name", "")

    # Clean up content
    html = strip_h1(html)
    html = strip_emojis(html)

    # ⚡ Phase 2.5: Dynamic category based on article data
    category_name = get_category_for_article(article)
    cat_id = get_or_create_category(category_name)

    payload = {
        "title":   title,
        "content": html,
        "status":  PUBLISH_MODE,
        "slug":    slug,
    }
    if cat_id:
        payload["categories"] = [cat_id]

    # Featured image
    featured_id = article.get("featured_image_id")
    if not featured_id:
        # Check image_data for hero
        image_data = article.get("image_data", {})
        if isinstance(image_data, dict):
            featured_id = image_data.get("hero_media_id") or image_data.get("screenshot_media_id")
    if featured_id:
        payload["featured_media"] = featured_id

    # RankMath SEO fields (if seo_agent has run)
    meta_title = article.get("meta_title", "")
    if meta_title:
        payload["meta"] = {
            "rank_math_title":         meta_title,
            "rank_math_description":   article.get("meta_description", ""),
            "rank_math_focus_keyword": article.get("focus_keyword", article.get("primary_keyword", "")),
        }

    try:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            json=payload,
            auth=WP_AUTH,
            timeout=60
        )
        if resp.status_code in (200, 201):
            return resp.json()
        else:
            log(f"   ❌ WordPress error {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        log(f"   ❌ Request failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════
#  MAIN RUN
# ══════════════════════════════════════════════════════════════════════════

def run():
    log("📤 Publisher Agent starting...")
    log(f"   Mode: {PUBLISH_MODE.upper()} | Cap: {DAILY_PUBLISH_CAP}/day")

    # ── Load data ──────────────────────────────────────────────────────
    handoffs        = load_json(HANDOFFS_FILE, {})
    affiliate_links = load_json(AFFILIATE_FILE, {})
    keyword_data    = load_json(KEYWORD_FILE, {})
    tool_db         = load_json(TOOL_DB_FILE, {})

    # ── Check daily cap ────────────────────────────────────────────────
    published_today = get_daily_count()
    remaining_slots = DAILY_PUBLISH_CAP - published_today

    if remaining_slots <= 0:
        log(f"   📊 Daily cap reached ({DAILY_PUBLISH_CAP}/day). Done.")
        return

    log(f"   📊 Published today: {published_today} | Slots remaining: {remaining_slots}")

    # ── Find articles ready to publish ────────────────────────────────
    ready = []
    for slug, article in handoffs.items():
        if not isinstance(article, dict):
            continue
        if article.get("status") != "pending_publish":
            continue
        if not article.get("article_html"):
            continue
        # Images check — roundups may not have all individual screenshots
        if not article.get("images_added", False):
            # Allow roundups/comparisons without full image set if they have a hero
            image_data = article.get("image_data", {})
            if isinstance(image_data, dict) and image_data.get("hero_media_id"):
                pass  # Has at least a hero — good enough
            else:
                continue

        article["_slug"] = slug
        ready.append(article)

    if not ready:
        log("   📭 No articles ready to publish.")
        return

    log(f"   📬 {len(ready)} articles ready — sorting by priority...")

    # Show article type breakdown
    type_counts = {}
    for a in ready:
        t = a.get("article_type", "review")
        type_counts[t] = type_counts.get(t, 0) + 1
    if type_counts:
        type_str = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        log(f"   📝 Types in queue: {type_str}")

    # ── Smart priority sort ────────────────────────────────────────────
    sorted_articles = sort_articles(ready, affiliate_links, tool_db)

    # ── Print queue preview ────────────────────────────────────────────
    log("\n   📋 Publish queue (top 10):")
    for i, a in enumerate(sorted_articles[:10], 1):
        tool      = a.get("tool_name", "?")
        score     = a.get("tool_score", a.get("score", "?"))
        priority  = a.get("_priority_score", "?")
        freshness = a.get("_freshness_tag", "")
        atype     = a.get("article_type", "review")
        has_link  = tool.lower() in affiliate_links
        link_icon = "💰" if has_link else "  "
        type_tag  = f"[{atype}]" if atype != "review" else ""
        log(f"   {i:2}. {link_icon} {tool:<25} "
            f"score:{str(score):<4} priority:{str(priority):<4} "
            f"{type_tag} {freshness}")

    log("")

    # ── Publish top N articles ─────────────────────────────────────────
    published = 0
    for article in sorted_articles:
        if published >= remaining_slots:
            break

        tool_name    = article.get("tool_name", "unknown")
        slug         = article.get("_slug", "")
        article_type = article.get("article_type", "review")
        priority     = article.get("_priority_score", 0)
        freshness    = article.get("_freshness_tag", "")
        tool_url     = article.get("tool_url", "")

        log(f"   🚀 Publishing: {tool_name} ({article_type}) "
            f"priority:{priority} {freshness}")

        # ── Inject affiliate links ────────────────────────────────────
        html = article.get("article_html", "")
        affiliate_injected = False

        if article_type == "roundup":
            # Roundups: inject for each tool mentioned
            roundup_tools = article.get("roundup_tools", [])
            html, injection_count = inject_roundup_affiliate_links(
                html, roundup_tools, affiliate_links
            )
            if injection_count > 0:
                affiliate_injected = True
                log(f"   💰 Injected {injection_count} affiliate link(s) in roundup")
        else:
            # Single tool: inject for the primary tool
            html, affiliate_injected = inject_affiliate_links(
                html, tool_name, tool_url, affiliate_links
            )
            if affiliate_injected:
                log(f"   💰 Affiliate link injected for {tool_name}")

        article["article_html"] = html

        # ── Publish to WordPress ──────────────────────────────────────
        wp_result = publish_to_wordpress(article)

        if wp_result:
            wp_id  = wp_result.get("id")
            wp_url = wp_result.get("link", "")
            log(f"   ✅ Published! Post ID: {wp_id}")
            log(f"      🔗 {wp_url}")

            # ⚡ Phase 2.5: Save all fields downstream agents need
            handoffs[slug]["status"]              = "published"
            handoffs[slug]["wp_post_id"]          = wp_id
            handoffs[slug]["wp_post_url"]         = wp_url  # internal_link_agent needs this
            handoffs[slug]["wp_url"]              = wp_url  # backward compat
            handoffs[slug]["published_date"]      = datetime.now().strftime("%Y-%m-%d %H:%M")
            handoffs[slug]["priority_score"]      = priority
            handoffs[slug]["affiliate_injected"]  = affiliate_injected
            handoffs[slug]["publish_category"]    = get_category_for_article(article)

            # Update keyword_data status
            if slug in keyword_data:
                keyword_data[slug]["status"] = "published"

            increment_daily_count()
            published += 1
        else:
            log(f"   ❌ Failed to publish: {tool_name}")

    # ── Save updated files ─────────────────────────────────────────────
    save_json(HANDOFFS_FILE, handoffs)
    save_json(KEYWORD_FILE, keyword_data)

    # ── Summary ────────────────────────────────────────────────────────
    total_today = get_daily_count()
    log(f"\n   ✅ Published {published} article(s) this run.")
    log(f"   📊 Total published today: {total_today}/{DAILY_PUBLISH_CAP}")

    remaining = [a for a in sorted_articles
                 if handoffs.get(a.get("_slug", ""), {}).get("status") != "published"]
    if remaining:
        log(f"   📬 {len(remaining)} articles still queued for next run.")


if __name__ == "__main__":
    run()