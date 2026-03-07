import json
import os
import re
import requests
from datetime import datetime
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    WP_URL, WP_USERNAME, WP_APP_PASSWORD,
    PUBLISH_MODE, SITE_NAME
)

# =============================================================================
# PUBLISHER AGENT
# Reads handoffs.json, sorts by affiliate priority, applies daily cap,
# strips H1 + emojis, posts to WordPress via REST API.
#
# PUBLISH ORDER (most money first):
#   Tier 1: Has affiliate link + score 75+ → HOT + MONETISED → publish first
#   Tier 2: Has affiliate link + score 60+ → MONETISED → publish next
#   Tier 3: No affiliate link + score 75+  → HOT → publish after monetised
#   Tier 4: Everything else                → FIFO (oldest written date first)
#
# HANDLES TWO CASES:
#   New articles    — no wp_post_id → creates new WordPress post
#   Existing drafts — has wp_post_id but WP status is "draft" → updates to publish
#
# The goal: every slot in the daily publish cap earns money if possible.
# =============================================================================

HANDOFFS_FILE     = "memory/handoffs.json"
KEYWORD_DATA_FILE = "memory/keyword_data.json"
AFFILIATE_FILE    = "memory/affiliate_links.json"
LOG_FILE          = "memory/logs/publisher_agent.log"

DAILY_PUBLISH_CAP      = 3
URGENT_SCORE_THRESHOLD = 75


# =============================================================================
# LOGGING
# =============================================================================

def write_log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


# =============================================================================
# FILE HELPERS
# =============================================================================

def load_json(path: str, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# =============================================================================
# AFFILIATE LINK LOOKUP
# =============================================================================

def load_affiliate_links() -> dict:
    """
    Load approved affiliate links from memory/affiliate_links.json.
    Returns empty dict safely if file doesn't exist yet.

    Expected file format:
    {
        "beehiiv": {
            "url": "https://www.beehiiv.com?via=YOUR_CODE",
            "commission": "50% for 12 months",
            "network": "direct",
            "approved_date": "2026-03-01",
            "status": "active"
        }
    }
    """
    return load_json(AFFILIATE_FILE, {})


def get_affiliate_url(tool_name: str, tool_key: str, affiliate_links: dict) -> str | None:
    """
    Look up the affiliate URL for a tool.
    Returns the affiliate URL string if found and active, or None if not.
    """
    if not affiliate_links:
        return None

    candidates = set()
    for raw in (tool_name, tool_key):
        if not raw:
            continue
        clean = raw.lower().strip()
        candidates.add(clean)
        candidates.add(clean.replace(" ", "_"))
        candidates.add(clean.replace("_", " "))
        candidates.add(clean.replace(".", "").replace(" ", ""))
        candidates.add(re.sub(r"[^a-z0-9]", "", clean))

    for key in candidates:
        if key in affiliate_links:
            entry = affiliate_links[key]
            if entry.get("status", "active") == "active":
                return entry.get("url")

    return None


# =============================================================================
# AFFILIATE PRIORITY SORT
# =============================================================================

def get_publish_priority(article: dict, affiliate_links: dict) -> tuple:
    """
    Calculate the sort key for a single article.
    Lower tuple value = publishes sooner.

    Returns: (tier, -score, written_date)
    """
    tool_name = article.get("tool_name", "")
    tool_key  = article.get("tool_key", "")
    score     = article.get("tool_score", 0) or 0
    written   = article.get("written_date", "2026-01-01")

    aff_url  = get_affiliate_url(tool_name, tool_key, affiliate_links)
    has_link = aff_url is not None

    if has_link and score >= URGENT_SCORE_THRESHOLD:
        tier = 1
    elif has_link and score >= 60:
        tier = 2
    elif score >= URGENT_SCORE_THRESHOLD:
        tier = 3
    else:
        tier = 4

    return (tier, -score, written)


def sort_for_publishing(pending: list, affiliate_links: dict) -> list:
    """
    Sort pending articles into publish order using affiliate priority.
    """
    tier_labels = {
        1: "T1 HOT+💰",
        2: "T2 AFF   ",
        3: "T3 HOT   ",
        4: "T4 QUEUE ",
    }

    sorted_articles = sorted(
        pending,
        key=lambda a: get_publish_priority(a, affiliate_links)
    )

    print(f"\n   📋 Publish queue ({len(sorted_articles)} articles ready):")
    for i, article in enumerate(sorted_articles, 1):
        tool     = article.get("tool_name", "?")
        score    = article.get("tool_score", 0) or 0
        tier     = get_publish_priority(article, affiliate_links)[0]
        badge    = tier_labels[tier]
        aff      = get_affiliate_url(
            article.get("tool_name", ""),
            article.get("tool_key", ""),
            affiliate_links
        )
        existing = " [existing draft]" if article.get("wp_post_id") else ""
        aff_note = f" → {aff[:45]}..." if aff else ""
        print(f"      {i:2}. [{badge}] score={score:3} — {tool}{existing}{aff_note}")

    return sorted_articles


# =============================================================================
# ARTICLE HTML PROCESSING
# =============================================================================

def strip_h1(html: str) -> str:
    """Remove H1 from article HTML — WordPress adds its own title."""
    return re.sub(r'<h1[^>]*>.*?</h1>', '', html, flags=re.IGNORECASE | re.DOTALL)


def strip_emojis(html: str) -> str:
    """Remove emoji characters from article HTML."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', html)


def inject_affiliate_links(html: str, tool_name: str, tool_key: str,
                            affiliate_links: dict, tool_url: str) -> tuple[str, bool]:
    """
    Replace plain tool URLs with affiliate tracking URLs in article HTML.
    Returns: (modified_html, did_inject)
    """
    aff_url = get_affiliate_url(tool_name, tool_key, affiliate_links)
    if not aff_url:
        return html, False

    if not tool_url or tool_url == aff_url:
        return html, False

    plain_variants = [
        tool_url.rstrip("/"),
        tool_url.rstrip("/") + "/",
    ]

    modified = html
    injected = False
    for variant in plain_variants:
        if variant in modified:
            modified = modified.replace(variant, aff_url)
            injected = True

    return modified, injected


# =============================================================================
# WORDPRESS REST API
# =============================================================================

def check_wp_post_status(post_id: int) -> str | None:
    """
    Check the actual WordPress status of an existing post.
    Returns 'publish', 'draft', 'private', etc. or None if not found.
    """
    auth     = (WP_USERNAME, WP_APP_PASSWORD)
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}"
    try:
        resp = requests.get(endpoint, auth=auth, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("status")
    except Exception:
        pass
    return None


def publish_existing_draft(post_id: int, html_content: str) -> bool:
    """
    Update an existing WordPress draft to published status.
    Also updates the content with latest version (affiliate links injected).
    Returns True on success.
    """
    auth     = (WP_USERNAME, WP_APP_PASSWORD)
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}"

    payload = {
        "status":  PUBLISH_MODE,
        "content": html_content,
    }

    try:
        resp = requests.post(endpoint, auth=auth, json=payload, timeout=60)
        resp.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        body   = e.response.text[:200] if e.response else ""
        print(f"   ❌ WordPress update HTTP {status}: {body}")
        return False
    except Exception as e:
        print(f"   ❌ WordPress update failed: {e}")
        return False


def create_new_post(article: dict, html_content: str) -> int | None:
    """
    Create a brand new WordPress post.
    Returns the WordPress post ID on success, or None on failure.
    """
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts"
    auth     = (WP_USERNAME, WP_APP_PASSWORD)

    CATEGORY_MAP = {
        "writing":      None,
        "video":        None,
        "image":        None,
        "audio":        None,
        "coding":       None,
        "productivity": None,
        "seo":          None,
        "other":        None,
    }

    category_name = article.get("category", "other")
    wp_category   = CATEGORY_MAP.get(category_name)
    categories    = [wp_category] if wp_category else []

    payload = {
        "title":      article.get("article_title", ""),
        "content":    html_content,
        "slug":       article.get("url_slug", ""),
        "status":     PUBLISH_MODE,
        "categories": categories,
    }

    try:
        response = requests.post(endpoint, auth=auth, json=payload, timeout=60)
        response.raise_for_status()
        return response.json().get("id")

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        body   = e.response.text[:200] if e.response else ""
        if status == 401:
            print(f"   ❌ WordPress auth failed (401) — regenerate App Password in WP admin")
        elif status == 403:
            print(f"   ❌ WordPress permission denied (403) — check user role")
        else:
            print(f"   ❌ WordPress HTTP {status}: {body}")
        return None

    except requests.exceptions.Timeout:
        print(f"   ❌ WordPress request timed out — try again")
        return None

    except Exception as e:
        print(f"   ❌ WordPress post failed: {e}")
        return None


# =============================================================================
# MAIN RUN
# =============================================================================

def run(daily_cap: int = DAILY_PUBLISH_CAP):
    """
    Main publisher run — called by scheduler.py or standalone.

    Handles two cases:
    1. New articles (no wp_post_id) → creates new WordPress post
    2. Existing drafts (has wp_post_id, WP status = draft) → updates to publish
    """
    print(f"\n📤 Publisher Agent starting...")
    print(f"   Mode: {PUBLISH_MODE.upper()} | Daily cap: {daily_cap}")
    write_log(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Publisher run (cap={daily_cap}, mode={PUBLISH_MODE})")

    handoffs     = load_json(HANDOFFS_FILE, {})
    keyword_data = load_json(KEYWORD_DATA_FILE, {})
    aff_links    = load_affiliate_links()

    if aff_links:
        print(f"   💰 {len(aff_links)} affiliate link(s) loaded — monetised articles get priority")
    else:
        print(f"   ℹ️  No affiliate_links.json yet — score-only sorting")

    # ── Find articles ready to publish ───────────────────────────────────────
    # Eligible:
    #   status = "pending_publish" AND no wp_post_id  → brand new article
    #   status = "pending_publish" AND has wp_post_id → existing draft to publish
    #
    # NOT eligible:
    #   status = "draft_live" or "published" → already live, skip

    pending = []
    for article in handoffs.values():
        if article.get("status") != "pending_publish":
            continue

        existing_id = article.get("wp_post_id")

        if existing_id:
            # Has a wp_post_id — check if it's actually still a draft in WordPress
            wp_status = check_wp_post_status(existing_id)
            if wp_status == "publish":
                # Already live — just fix our status and skip
                slug = article.get("url_slug", "")
                if slug in handoffs:
                    handoffs[slug]["status"] = "draft_live"
                continue
            elif wp_status == "draft":
                # Existing draft — eligible to publish
                pending.append(article)
            else:
                # Unknown status or post not found — treat as new
                article["wp_post_id"] = None
                pending.append(article)
        else:
            # Brand new article — eligible
            pending.append(article)

    if not pending:
        print(f"\n   ℹ️  No articles ready to publish.")
        write_log("No pending articles found.")
        return

    print(f"\n   Found {len(pending)} article(s) ready to publish")

    # ── Sort by affiliate priority ────────────────────────────────────────────
    sorted_queue = sort_for_publishing(pending, aff_links)
    to_publish   = sorted_queue[:daily_cap]
    held_over    = sorted_queue[daily_cap:]

    if held_over:
        print(f"\n   ⏸️  Cap of {daily_cap}/day reached — {len(held_over)} article(s) held for tomorrow")

    # ── Publish each article ──────────────────────────────────────────────────
    published_count  = 0
    affiliate_count  = 0
    plain_link_count = 0

    for article in to_publish:
        tool_name = article.get("tool_name", "?")
        tool_key  = article.get("tool_key", "")
        url_slug  = article.get("url_slug", "")
        tool_url  = article.get("tool_url", "")
        score     = article.get("tool_score", 0) or 0
        html      = article.get("article_html", "")
        existing_id = article.get("wp_post_id")

        print(f"\n   🔧 Processing: {tool_name} (score {score})")
        if existing_id:
            print(f"   📝 Existing draft — post ID {existing_id} — updating to {PUBLISH_MODE.upper()}")

        if not html:
            print(f"   ⚠️  No article HTML — skipping {tool_name}")
            write_log(f"SKIP {tool_name}: no HTML")
            continue

        # ── Step 1: inject affiliate link if available ────────────────────
        html, did_inject = inject_affiliate_links(
            html, tool_name, tool_key, aff_links, tool_url
        )
        if did_inject:
            aff_url = get_affiliate_url(tool_name, tool_key, aff_links)
            print(f"   💰 Affiliate link injected → {aff_url[:50]}")
            affiliate_count += 1
        else:
            print(f"   🔗 No affiliate link yet — using plain homepage URL")
            plain_link_count += 1

        # ── Step 2: strip H1 ─────────────────────────────────────────────
        html = strip_h1(html)

        # ── Step 3: strip emojis ─────────────────────────────────────────
        html = strip_emojis(html)

        # ── Step 4: post or update WordPress ─────────────────────────────
        print(f"   📤 Posting to WordPress as {PUBLISH_MODE.upper()}...")

        if existing_id:
            # Update existing draft → publish
            ok = publish_existing_draft(existing_id, html)
            post_id = existing_id if ok else None
        else:
            # Create brand new post
            post_id = create_new_post(article, html)

        if not post_id:
            print(f"   ❌ Failed to publish {tool_name} — skipping")
            write_log(f"FAIL {tool_name}: WordPress failed")
            continue

        # ── Step 5: update handoffs.json ──────────────────────────────────
        slug = article.get("url_slug", "")
        if slug in handoffs:
            handoffs[slug]["status"]             = "draft_live"
            handoffs[slug]["wp_post_id"]         = post_id
            handoffs[slug]["published_at"]       = datetime.now().isoformat()
            handoffs[slug]["publish_mode"]       = PUBLISH_MODE
            handoffs[slug]["affiliate_injected"] = did_inject

        # ── Step 6: update keyword_data.json ─────────────────────────────
        tool_key_lower = tool_key.lower() if tool_key else tool_name.lower()
        for kd_key in keyword_data:
            if (keyword_data[kd_key].get("url_slug") == slug or
                    kd_key.lower() == tool_key_lower):
                keyword_data[kd_key]["status"]       = PUBLISH_MODE
                keyword_data[kd_key]["wp_post_id"]   = post_id
                keyword_data[kd_key]["published_at"] = datetime.now().isoformat()
                break

        published_count += 1
        mode_label = "🟢 LIVE" if PUBLISH_MODE == "publish" else "📝 DRAFT"
        wp_link    = f"{WP_URL}/?p={post_id}"
        print(f"   ✅ {mode_label} — {tool_name} → Post ID {post_id}")
        print(f"      {wp_link}")
        write_log(f"OK {tool_name}: post_id={post_id}, affiliate={did_inject}")

    # ── Save updated files ────────────────────────────────────────────────────
    save_json(HANDOFFS_FILE, handoffs)
    save_json(KEYWORD_DATA_FILE, keyword_data)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"✅ Publisher done.")
    print(f"   {'🟢 Published live' if PUBLISH_MODE == 'publish' else '📝 Saved as drafts'}: {published_count}")
    print(f"   💰 With affiliate links:  {affiliate_count}")
    print(f"   🔗 Plain homepage links:  {plain_link_count}")
    if held_over:
        print(f"   ⏸️  Held for tomorrow:    {len(held_over)}")
    print(f"{'='*55}")

    write_log(f"Done. Published={published_count}, affiliate={affiliate_count}, held={len(held_over)}")

    if plain_link_count > 0:
        print(f"\n   💡 Tip: Add affiliate links to memory/affiliate_links.json")
        print(f"      to start earning commissions on those {plain_link_count} article(s).")


# =============================================================================
# STANDALONE + SCHEDULER ENTRY POINTS
# =============================================================================

if __name__ == "__main__":
    run()