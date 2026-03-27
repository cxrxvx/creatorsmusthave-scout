"""
affiliate_swap_agent.py — Swap homepage URLs with affiliate links in published articles
========================================================================================
Phase 2.7J: Runs on demand or daily via scheduler.

What it does:
  1. Loads affiliate_links.json
  2. Finds published articles where affiliate_pending = 1
  3. For each article, checks if an affiliate link now exists for that tool
  4. Fetches the LIVE WordPress post content (not DB — Alex may have edited it)
  5. Uses BeautifulSoup to find <a> tags with homepage URLs → replaces with affiliate URLs
  6. PUTs updated content back to WordPress
  7. Updates database: affiliate_pending = 0, affiliate_injected = 1
  8. Sends Telegram confirmation

Usage:
    cd ~/cxrxvx-ai-empire
    source venv/bin/activate
    python3 affiliate_swap_agent.py

Can also be called from scheduler.py or triggered via Telegram /swap command.
"""

import db_helpers
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
MEMORY_DIR   = BASE_DIR / "memory"
AFFILIATE_FILE = MEMORY_DIR / "affiliate_links.json"
LOGS_DIR     = MEMORY_DIR / "logs" / "affiliate_swap_agent"

# ── Config ─────────────────────────────────────────────────────────────────
sys.path.insert(0, str(BASE_DIR))
from config import (WP_URL, WP_USERNAME, WP_APP_PASSWORD)

WP_AUTH = (WP_USERNAME, WP_APP_PASSWORD)

# Telegram config
try:
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
except ImportError:
    TELEGRAM_BOT_TOKEN = ""
    TELEGRAM_CHAT_ID   = ""
    TELEGRAM_ENABLED   = False

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""

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


def log(msg):
    """Print and write to log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{today}.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")


def send_telegram(text: str):
    """Send a Telegram message."""
    if not TELEGRAM_ENABLED:
        return
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=15,
        )
    except Exception as e:
        log(f"   ⚠️  Telegram error: {e}")


def resolve_affiliate_url(affiliate_links: dict, tool_name: str) -> str:
    """
    Case-insensitive lookup into affiliate_links.
    Handles both plain string URLs and {url, status} dict format.
    Returns the affiliate URL string, or "" if not found / not active.
    """
    needle = tool_name.lower().strip()
    matched_value = None
    for k, v in affiliate_links.items():
        if k.lower().strip() == needle:
            matched_value = v
            break
    if matched_value is None:
        return ""
    if isinstance(matched_value, str):
        return matched_value
    if isinstance(matched_value, dict):
        if matched_value.get("status", "active") != "active":
            return ""
        return matched_value.get("url", "")
    return ""


def normalize_url(url: str) -> str:
    """
    Normalize a URL for comparison.
    Strips trailing slash, lowercases, removes www prefix.
    """
    url = url.strip().rstrip("/").lower()
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    # Rebuild without www, without trailing slash
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{host}{path}"


def url_matches_tool(href: str, tool_url: str) -> bool:
    """
    Check if an <a> tag's href points to the same domain as the tool's homepage.
    Matches: exact URL, URL with path, www vs non-www, trailing slash differences.
    Does NOT match: completely different domains.
    """
    if not href or not tool_url:
        return False

    try:
        href_parsed = urlparse(href.lower().strip())
        tool_parsed = urlparse(tool_url.lower().strip())

        href_host = (href_parsed.hostname or "").lstrip("www.")
        tool_host = (tool_parsed.hostname or "").lstrip("www.")

        if not href_host or not tool_host:
            return False

        return href_host == tool_host
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
#  WORDPRESS FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def fetch_wp_post_content(wp_post_id: int) -> str | None:
    """Fetch the current content of a WordPress post. Returns HTML or None."""
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
            auth=WP_AUTH,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("content", {}).get("rendered", "")
        else:
            log(f"   ❌ WP fetch error {resp.status_code} for post {wp_post_id}")
            return None
    except Exception as e:
        log(f"   ❌ WP fetch failed for post {wp_post_id}: {e}")
        return None


def update_wp_post_content(wp_post_id: int, new_content: str) -> bool:
    """Update a WordPress post's content via REST API. Returns True on success."""
    try:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
            json={"content": new_content},
            auth=WP_AUTH,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return True
        else:
            log(f"   ❌ WP update error {resp.status_code} for post {wp_post_id}: {resp.text[:200]}")
            return False
    except Exception as e:
        log(f"   ❌ WP update failed for post {wp_post_id}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════
#  SWAP LOGIC
# ══════════════════════════════════════════════════════════════════════════

def swap_links_in_html(html: str, tool_url: str, affiliate_url: str) -> tuple[str, int]:
    """
    Find all <a> tags whose href matches the tool's homepage domain
    and replace them with the affiliate URL.

    Uses BeautifulSoup for safe HTML parsing — never regex on href replacement.
    Returns (updated_html, count_of_swaps).
    """
    if not html or not tool_url or not affiliate_url:
        return html, 0

    soup = BeautifulSoup(html, "html.parser")
    swap_count = 0

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        # Skip if already pointing to affiliate URL
        if affiliate_url.lower().rstrip("/") in href.lower():
            continue

        # Skip anchor links, mailto, tel
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        if url_matches_tool(href, tool_url):
            a_tag["href"] = affiliate_url
            swap_count += 1

    if swap_count > 0:
        return str(soup), swap_count
    return html, 0


def process_single_tool_article(article: dict, affiliate_links: dict) -> dict | None:
    """
    Process a single-tool article (review, alert).
    Returns a result dict or None if no swap needed/possible.
    """
    tool_name = article.get("tool_name", "")
    tool_url = article.get("tool_url", "")
    wp_post_id = article.get("wp_post_id")
    slug = article.get("slug", "")

    if not tool_name or not wp_post_id:
        return None

    affiliate_url = resolve_affiliate_url(affiliate_links, tool_name)
    if not affiliate_url:
        return None  # No affiliate link available yet

    # Fetch live content from WordPress
    live_html = fetch_wp_post_content(wp_post_id)
    if live_html is None:
        return None

    # Check if affiliate URL is already in the content
    if affiliate_url.lower().rstrip("/") in live_html.lower():
        log(f"   ℹ️  {slug}: affiliate link already present — skipping")
        return {"slug": slug, "action": "already_done"}

    # Swap homepage URLs with affiliate URL
    updated_html, swap_count = swap_links_in_html(live_html, tool_url, affiliate_url)

    if swap_count == 0:
        log(f"   ℹ️  {slug}: no matching homepage URLs found in live content")
        return None

    # Push updated content to WordPress
    if update_wp_post_content(wp_post_id, updated_html):
        return {
            "slug": slug,
            "tool_name": tool_name,
            "swap_count": swap_count,
            "affiliate_url": affiliate_url,
            "action": "swapped",
        }
    return None


def process_roundup_article(article: dict, affiliate_links: dict) -> dict | None:
    """
    Process a roundup article — check each tool mentioned.
    Returns a result dict or None if no swaps made.
    """
    wp_post_id = article.get("wp_post_id")
    slug = article.get("slug", "")
    roundup_tools = article.get("roundup_tools", [])

    if not wp_post_id or not roundup_tools:
        return None

    # Build a list of (tool_name, tool_url, affiliate_url) for tools that have links
    swap_targets = []
    for tool_info in roundup_tools:
        t_name = tool_info if isinstance(tool_info, str) else tool_info.get("name", "")
        if not t_name:
            continue
        aff_url = resolve_affiliate_url(affiliate_links, t_name)
        if not aff_url:
            continue
        # Get the homepage URL for this tool
        from article_agent import get_tool_url
        t_url = get_tool_url(t_name)
        swap_targets.append((t_name, t_url, aff_url))

    if not swap_targets:
        return None

    # Fetch live content
    live_html = fetch_wp_post_content(wp_post_id)
    if live_html is None:
        return None

    total_swaps = 0
    swapped_tools = []
    current_html = live_html

    for t_name, t_url, aff_url in swap_targets:
        # Skip if already present
        if aff_url.lower().rstrip("/") in current_html.lower():
            continue
        current_html, count = swap_links_in_html(current_html, t_url, aff_url)
        if count > 0:
            total_swaps += count
            swapped_tools.append(t_name)

    if total_swaps == 0:
        return None

    if update_wp_post_content(wp_post_id, current_html):
        return {
            "slug": slug,
            "tool_name": ", ".join(swapped_tools),
            "swap_count": total_swaps,
            "action": "swapped",
        }
    return None


def process_comparison_article(article: dict, affiliate_links: dict) -> dict | None:
    """
    Process a comparison article — check both tools.
    Returns a result dict or None if no swaps made.
    """
    wp_post_id = article.get("wp_post_id")
    slug = article.get("slug", "")
    comparison_tools = article.get("comparison_tools", {}) or {}

    tool_a = comparison_tools.get("tool_a", "") if isinstance(comparison_tools, dict) else ""
    tool_b = comparison_tools.get("tool_b", "") if isinstance(comparison_tools, dict) else ""

    if not wp_post_id or not (tool_a or tool_b):
        return None

    swap_targets = []
    for t_name in [tool_a, tool_b]:
        if not t_name:
            continue
        aff_url = resolve_affiliate_url(affiliate_links, t_name)
        if not aff_url:
            continue
        from article_agent import get_tool_url
        t_url = get_tool_url(t_name)
        swap_targets.append((t_name, t_url, aff_url))

    if not swap_targets:
        return None

    live_html = fetch_wp_post_content(wp_post_id)
    if live_html is None:
        return None

    total_swaps = 0
    swapped_tools = []
    current_html = live_html

    for t_name, t_url, aff_url in swap_targets:
        if aff_url.lower().rstrip("/") in current_html.lower():
            continue
        current_html, count = swap_links_in_html(current_html, t_url, aff_url)
        if count > 0:
            total_swaps += count
            swapped_tools.append(t_name)

    if total_swaps == 0:
        return None

    if update_wp_post_content(wp_post_id, current_html):
        return {
            "slug": slug,
            "tool_name": ", ".join(swapped_tools),
            "swap_count": total_swaps,
            "action": "swapped",
        }
    return None


# ══════════════════════════════════════════════════════════════════════════
#  MAIN RUN
# ══════════════════════════════════════════════════════════════════════════

def run():
    log("🔄 Affiliate Swap Agent starting...")

    affiliate_links = load_json(AFFILIATE_FILE, {})
    if not affiliate_links:
        log("   ℹ️  No affiliate links configured. Nothing to swap.")
        return

    log(f"   📋 Affiliate links available: {', '.join(affiliate_links.keys())}")

    # Find all published or pending_approval articles that might need swaps
    # Check affiliate_pending = 1, but also scan ALL published articles
    # in case affiliate_pending wasn't set (articles from before Phase 2.7J)
    all_handoffs = db_helpers.load_all_handoffs()

    candidates = []
    for slug, article in all_handoffs.items():
        status = article.get("status", "")
        if status not in ("published", "pending_approval"):
            continue
        wp_post_id = article.get("wp_post_id")
        if not wp_post_id:
            continue
        candidates.append(article)

    if not candidates:
        log("   📭 No published articles to check.")
        return

    log(f"   🔍 Checking {len(candidates)} published article(s) for swappable links...")

    results = []
    already_done = 0

    for article in candidates:
        slug = article.get("slug", "")
        article_type = article.get("article_type", "review")

        if article_type == "roundup":
            result = process_roundup_article(article, affiliate_links)
        elif article_type == "comparison":
            result = process_comparison_article(article, affiliate_links)
        else:
            result = process_single_tool_article(article, affiliate_links)

        if result:
            if result.get("action") == "already_done":
                already_done += 1
                # Mark as no longer pending since affiliate link is present
                db_helpers.update_handoff(slug, {
                    "affiliate_pending": 0,
                    "affiliate_injected": 1,
                })
            elif result.get("action") == "swapped":
                results.append(result)
                db_helpers.update_handoff(slug, {
                    "affiliate_pending": 0,
                    "affiliate_injected": 1,
                })
                log(f"   ✅ {slug}: swapped {result['swap_count']} URL(s) → affiliate link")

    # ── Summary ────────────────────────────────────────────────────────
    log(f"\n   🏁 Swap Agent done.")
    log(f"   Checked: {len(candidates)} articles")
    log(f"   Swapped: {len(results)} articles")
    log(f"   Already had affiliate links: {already_done}")

    # ── Telegram summary ───────────────────────────────────────────────
    if results:
        lines = ["🔄 AFFILIATE LINKS SWAPPED:\n"]
        for r in results:
            lines.append(f"• {r['tool_name']}: {r['swap_count']} URL(s) updated in {r['slug']}")
        send_telegram("\n".join(lines))
    elif already_done > 0:
        log(f"   ℹ️  All affiliate links already in place. Nothing to swap.")


if __name__ == "__main__":
    run()
