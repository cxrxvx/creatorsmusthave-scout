import json
import os
import re
import time
import requests
from datetime import datetime
from anthropic import Anthropic

# ── Config ────────────────────────────────────────────────────────────────────
try:
    from config import (ANTHROPIC_API_KEY, CLAUDE_MODEL, WP_URL,
                        WP_USERNAME, WP_APP_PASSWORD,
                        PEXELS_API_KEY, PIXABAY_API_KEY)
except ImportError:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL      = "claude-sonnet-4-5-20250929"
    WP_URL            = os.environ.get("WP_URL", "")
    WP_USERNAME       = os.environ.get("WP_USERNAME", "")
    WP_APP_PASSWORD   = os.environ.get("WP_APP_PASSWORD", "")
    PEXELS_API_KEY    = os.environ.get("PEXELS_API_KEY", "")
    PIXABAY_API_KEY   = os.environ.get("PIXABAY_API_KEY", "")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

MEMORY_DIR  = "memory"
HANDOFFS    = os.path.join(MEMORY_DIR, "handoffs.json")
LOGS_DIR    = os.path.join(MEMORY_DIR, "logs", "image_agent")
DAILY_CAP   = 15

# ── Quality thresholds ────────────────────────────────────────────────────────
MIN_HERO_BYTES       = 50 * 1024
MIN_HERO_REJECTS     = 20 * 1024
MIN_SCREENSHOT_BYTES = 25 * 1024
LOGIN_WALL_BYTES     = 15 * 1024

os.makedirs(LOGS_DIR, exist_ok=True)

# ── Tool URL map ──────────────────────────────────────────────────────────────
TOOL_URLS = {
    "canva":                    "https://www.canva.com/design/",
    "descript":                 "https://web.descript.com",
    "elevenlabs":               "https://elevenlabs.io/app/speech-synthesis",
    "riverside":                "https://riverside.fm",
    "riverside.fm":             "https://riverside.fm",
    "convertkit":               "https://app.convertkit.com",
    "beehiiv":                  "https://app.beehiiv.com",
    "kajabi":                   "https://app.kajabi.com",
    "notion":                   "https://www.notion.so/templates",
    "loom":                     "https://www.loom.com/looms/videos",
    "opus clip":                "https://www.opus.pro",
    "pictory":                  "https://app.pictory.ai",
    "buzzsprout":               "https://www.buzzsprout.com",
    "surfer seo":               "https://app.surferseo.com",
    "surfer":                   "https://app.surferseo.com",
    "podcastle":                "https://podcastle.ai",
    "synthesia":                "https://www.synthesia.io/features/avatars",
    "otter.ai":                 "https://otter.ai/home",
    "later":                    "https://app.later.com",
    "stan store":               "https://stanwith.me",
    "gumroad":                  "https://app.gumroad.com",
    "typeform":                 "https://www.typeform.com/templates/",
    "metricool":                "https://app.metricool.com",
    "teachable":                "https://teachable.com/examples",
    "jasper ai":                "https://app.jasper.ai",
    "krisp":                    "https://krisp.ai",
    "krisp accent conversion":  "https://krisp.ai",
    "coursekit":                "https://coursekit.io",
    "willow":                   "https://willow.app",
    "willow voice for teams":   "https://willow.app",
    "spoke":                    "https://www.spoke.app",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[image_agent] {timestamp} — {msg}")
    log_file = os.path.join(LOGS_DIR, datetime.now().strftime("%Y-%m-%d") + ".log")
    with open(log_file, "a") as f:
        f.write(f"{timestamp} — {msg}\n")

def wp_auth():
    return (WP_USERNAME, WP_APP_PASSWORD)

# ── Quality checks ────────────────────────────────────────────────────────────
def check_hero_quality(image_bytes: bytes, source: str) -> tuple[bool, str]:
    size = len(image_bytes)
    if size < MIN_HERO_REJECTS:
        return False, f"too small ({size // 1024}KB) — likely broken"
    if size < MIN_HERO_BYTES:
        return False, f"low quality ({size // 1024}KB) — below 50KB threshold"
    return True, f"passed ({size // 1024}KB from {source})"

def check_screenshot_quality(image_bytes: bytes) -> tuple[bool, str]:
    size = len(image_bytes)
    if size < LOGIN_WALL_BYTES:
        return False, f"likely login wall or blank page ({size // 1024}KB)"
    if size < MIN_SCREENSHOT_BYTES:
        return False, f"low quality screenshot ({size // 1024}KB)"
    return True, f"passed ({size // 1024}KB)"

# ── Screenshot HTML injection ─────────────────────────────────────────────────
def build_screenshot_html(image_url: str, alt_text: str, tool_name: str) -> str:
    """Build a styled screenshot block to inject after the first paragraph."""
    return f"""
<figure style="margin: 2em 0; text-align: center;">
  <img
    src="{image_url}"
    alt="{alt_text}"
    style="width: 100%; max-width: 900px; border-radius: 8px; border: 1px solid #e0e0e0; box-shadow: 0 2px 12px rgba(0,0,0,0.10);"
    loading="lazy"
  />
  <figcaption style="margin-top: 0.6em; font-size: 0.92em; color: #666; font-style: italic;">
    {tool_name} — what you see when you log in
  </figcaption>
</figure>"""

def inject_screenshot_into_article(article_html: str, screenshot_html: str) -> str:
    """
    Inject screenshot block after the first closing </p> tag.
    This puts it right after the intro paragraph — the ideal position.
    Falls back to prepending if no </p> found.
    """
    first_p_end = article_html.find("</p>")
    if first_p_end == -1:
        log("  Could not find </p> — prepending screenshot")
        return screenshot_html + article_html

    insert_pos = first_p_end + len("</p>")
    return article_html[:insert_pos] + "\n" + screenshot_html + article_html[insert_pos:]

def update_wp_post_content(wp_post_id: int, new_html: str) -> bool:
    """Update the post content in WordPress with the injected screenshot."""
    try:
        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
            json={"content": new_html},
            auth=wp_auth(),
            timeout=15
        )
        return response.status_code in (200, 201)
    except Exception as e:
        log(f"  WordPress content update failed: {e}")
        return False

def get_media_url(media_id: int) -> str | None:
    """Get the full URL of an uploaded media item."""
    try:
        response = requests.get(
            f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
            auth=wp_auth(),
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("source_url")
        return None
    except Exception as e:
        log(f"  Could not get media URL: {e}")
        return None

# ── Step 1: Claude generates smart search queries ─────────────────────────────
def get_image_search_query(tool_name: str, article_title: str, keyword: str) -> dict:
    prompt = f"""You are helping find the perfect hero image for an affiliate review article.

Tool: {tool_name}
Article title: {article_title}
Primary keyword: {keyword}

Generate:
1. The best photo search query (3-5 words) — should show a PERSON using technology or creating content. Think: "podcaster recording microphone", "content creator laptop editing", "newsletter writer coffee desk"
2. A second fallback query — different angle, still a person + technology
3. A third last-resort query — very generic but always returns results e.g. "person working laptop"
4. SEO alt text for the hero image (under 125 characters, naturally includes the keyword)
5. SEO alt text for the screenshot image (under 125 characters)

RESPOND IN THIS EXACT JSON FORMAT only — no explanation outside the JSON:
{{
  "primary_query": "<3-5 word search query>",
  "fallback_query": "<3-5 word fallback query>",
  "last_resort_query": "<very generic fallback that always works>",
  "hero_alt_text": "<alt text for hero image>",
  "screenshot_alt_text": "<alt text for tool screenshot>"
}}"""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        log(f"  Claude query generation failed: {e}")
        return {
            "primary_query": f"{tool_name} creator tool",
            "fallback_query": "content creator laptop working",
            "last_resort_query": "person working laptop desk",
            "hero_alt_text": f"{tool_name} review for creators",
            "screenshot_alt_text": f"{tool_name} dashboard interface"
        }

# ── Step 2: Fetch hero image ──────────────────────────────────────────────────
def fetch_pexels_image(query: str) -> bytes | None:
    try:
        headers  = {"Authorization": PEXELS_API_KEY}
        params   = {"query": query, "per_page": 5,
                    "orientation": "landscape", "size": "large"}
        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers, params=params, timeout=15
        )
        if response.status_code != 200:
            log(f"  Pexels API error: {response.status_code}")
            return None
        photos = response.json().get("photos", [])
        if not photos:
            log(f"  Pexels: no results for '{query}'")
            return None
        img = requests.get(photos[0]["src"]["large2x"], timeout=15)
        if img.status_code == 200:
            log(f"  Pexels: got image ({len(img.content) // 1024}KB) for '{query}'")
            return img.content
        return None
    except Exception as e:
        log(f"  Pexels fetch failed: {e}")
        return None

def fetch_pixabay_image(query: str) -> bytes | None:
    try:
        params = {
            "key":         PIXABAY_API_KEY,
            "q":           query,
            "image_type":  "photo",
            "orientation": "horizontal",
            "category":    "people,technology,business",
            "min_width":   1200,
            "per_page":    5,
            "safesearch":  "true"
        }
        response = requests.get(
            "https://pixabay.com/api/",
            params=params, timeout=15
        )
        if response.status_code != 200:
            log(f"  Pixabay API error: {response.status_code}")
            return None
        hits = response.json().get("hits", [])
        if not hits:
            log(f"  Pixabay: no results for '{query}'")
            return None
        img = requests.get(hits[0]["largeImageURL"], timeout=15)
        if img.status_code == 200:
            log(f"  Pixabay: got image ({len(img.content) // 1024}KB) for '{query}'")
            return img.content
        return None
    except Exception as e:
        log(f"  Pixabay fetch failed: {e}")
        return None

def get_hero_image(queries: dict) -> tuple[bytes | None, str]:
    attempts = [
        ("Pexels",  fetch_pexels_image,  queries["primary_query"]),
        ("Pexels",  fetch_pexels_image,  queries["fallback_query"]),
        ("Pixabay", fetch_pixabay_image, queries["primary_query"]),
        ("Pixabay", fetch_pixabay_image, queries["fallback_query"]),
        ("Pexels",  fetch_pexels_image,  queries["last_resort_query"]),
        ("Pixabay", fetch_pixabay_image, queries["last_resort_query"]),
    ]
    for source, fetcher, query in attempts:
        log(f"  Trying {source}: '{query}'")
        image_bytes = fetcher(query)
        if image_bytes:
            passed, reason = check_hero_quality(image_bytes, source)
            if passed:
                log(f"  ✅ Hero quality check: {reason}")
                return image_bytes, f"{source} — '{query}'"
            else:
                log(f"  ❌ Hero rejected: {reason} — trying next")
    return None, "all sources exhausted"

# ── Step 3: Screenshot tool website ──────────────────────────────────────────
def screenshot_tool(tool_name: str) -> bytes | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("  Playwright not installed — skipping screenshot")
        return None

    tool_key = tool_name.lower()
    url      = TOOL_URLS.get(tool_key)
    if not url:
        slug = re.sub(r"[^a-z0-9]", "", tool_key)
        url  = f"https://www.{slug}.com"
        log(f"  No specific URL for {tool_name} — trying {url}")

    log(f"  Screenshotting: {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page    = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            for selector in [
                "[id*='cookie'] button", "[class*='cookie'] button",
                "button:has-text('Accept')", "button:has-text('Got it')",
                "button:has-text('Accept all')", "button:has-text('Allow')"
            ]:
                try:
                    page.click(selector, timeout=2000)
                    break
                except Exception:
                    pass
            screenshot_bytes = page.screenshot(type="jpeg", quality=85)
            browser.close()
            passed, reason = check_screenshot_quality(screenshot_bytes)
            if not passed:
                log(f"  ❌ Screenshot quality failed: {reason}")
                return None
            log(f"  ✅ Screenshot quality: {reason}")
            return screenshot_bytes
    except Exception as e:
        log(f"  Screenshot failed for {tool_name}: {e}")
        return None

# ── Step 4: Upload to WordPress ───────────────────────────────────────────────
def upload_to_wordpress(
    image_bytes: bytes, filename: str, alt_text: str, caption: str = ""
) -> int | None:
    endpoint = f"{WP_URL}/wp-json/wp/v2/media"
    headers  = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type":        "image/jpeg",
    }
    try:
        response = requests.post(
            endpoint, headers=headers, data=image_bytes,
            auth=wp_auth(), timeout=30
        )
        if response.status_code in (200, 201):
            media_id = response.json().get("id")
            requests.post(
                f"{endpoint}/{media_id}",
                json={"alt_text": alt_text, "caption": caption},
                auth=wp_auth(), timeout=10
            )
            log(f"  Uploaded → WordPress media ID: {media_id}")
            return media_id
        else:
            log(f"  WordPress upload failed: {response.status_code}")
            return None
    except Exception as e:
        log(f"  WordPress upload error: {e}")
        return None

def set_featured_image(wp_post_id: int, media_id: int) -> bool:
    try:
        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
            json={"featured_media": media_id},
            auth=wp_auth(), timeout=10
        )
        return response.status_code in (200, 201)
    except Exception as e:
        log(f"  Set featured image failed: {e}")
        return False

# ── Main run ──────────────────────────────────────────────────────────────────
def run():
    log("Image Agent starting")
    handoffs = load_json(HANDOFFS, {})

    candidates = {
        slug: article for slug, article in handoffs.items()
        if article.get("status") in ("pending_publish", "draft_live")
        and article.get("images_added") != True
    }

    log(f"Found {len(candidates)} articles needing images (including partials)")

    if not candidates:
        log("Nothing to process — exiting")
        return

    to_process    = list(candidates.items())[:DAILY_CAP]
    success_count = 0
    partial_count = 0
    fail_count    = 0

    for slug, article in to_process:
        tool_name  = article.get("tool_name", slug)
        title      = article.get("article_title", "")
        keyword    = article.get("primary_keyword", "")
        wp_post_id = article.get("wp_post_id")

        existing = article.get("image_data", {})
        has_hero = bool(existing.get("hero_media_id"))
        has_shot = bool(existing.get("screenshot_media_id"))

        log(f"Processing: {tool_name} | hero: {'✅' if has_hero else '❌'} | screenshot: {'✅' if has_shot else '❌'}")

        queries     = get_image_search_query(tool_name, title, keyword)
        images_data = existing.copy()

        # ── Hero image ──
        if not has_hero:
            hero_bytes, source = get_hero_image(queries)
            if hero_bytes:
                hero_id = upload_to_wordpress(
                    hero_bytes, f"{slug}-hero.jpg",
                    queries["hero_alt_text"],
                    caption=f"Hero image for {tool_name} review"
                )
                if hero_id:
                    images_data["hero_media_id"] = hero_id
                    images_data["hero_alt_text"]  = queries["hero_alt_text"]
                    images_data["hero_source"]    = source
                    if wp_post_id:
                        if set_featured_image(wp_post_id, hero_id):
                            log(f"  ✅ Featured image set on post {wp_post_id}")
                        else:
                            log(f"  ⚠️  Could not set featured image on post {wp_post_id}")
                    else:
                        log(f"  ℹ️  No wp_post_id yet — will set at publish time")
            else:
                log(f"  ❌ All hero sources exhausted for {tool_name}")

        # ── Screenshot ──
        if not has_shot:
            shot_bytes = screenshot_tool(tool_name)
            if shot_bytes:
                shot_id = upload_to_wordpress(
                    shot_bytes, f"{slug}-screenshot.jpg",
                    queries["screenshot_alt_text"],
                    caption=f"{tool_name} interface screenshot"
                )
                if shot_id:
                    images_data["screenshot_media_id"] = shot_id
                    images_data["screenshot_alt_text"]  = queries["screenshot_alt_text"]
                    log(f"  ✅ Screenshot uploaded — media ID: {shot_id}")

                    # ── Inject screenshot into article body ──
                    if wp_post_id:
                        media_url = get_media_url(shot_id)
                        if media_url:
                            # Get current post content
                            post_response = requests.get(
                                f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
                                auth=wp_auth(), timeout=10
                            )
                            if post_response.status_code == 200:
                                current_html = post_response.json().get("content", {}).get("raw", "")
                                if not current_html:
                                    # Try rendered if raw is empty
                                    current_html = post_response.json().get("content", {}).get("rendered", "")

                                if current_html:
                                    screenshot_block = build_screenshot_html(
                                        media_url,
                                        queries["screenshot_alt_text"],
                                        tool_name
                                    )
                                    updated_html = inject_screenshot_into_article(
                                        current_html, screenshot_block
                                    )
                                    if update_wp_post_content(wp_post_id, updated_html):
                                        log(f"  ✅ Screenshot injected into article body")
                                        images_data["screenshot_injected"] = True
                                    else:
                                        log(f"  ⚠️  Could not inject screenshot into article")
                                else:
                                    log(f"  ⚠️  Could not retrieve article content for injection")
                        else:
                            log(f"  ⚠️  Could not get media URL for injection")
                    else:
                        log(f"  ℹ️  No wp_post_id yet — screenshot injection queued for publish time")
            else:
                log(f"  ❌ Screenshot failed — will retry next run")

        # ── Determine final status ──
        now_has_hero = bool(images_data.get("hero_media_id"))
        now_has_shot = bool(images_data.get("screenshot_media_id"))

        article["image_data"]  = images_data
        article["images_date"] = datetime.now().strftime("%Y-%m-%d")

        if now_has_hero and now_has_shot:
            article["images_added"] = True
            success_count += 1
            log(f"  ✅ COMPLETE — hero + screenshot ready")
        elif now_has_hero or now_has_shot:
            article["images_added"] = "partial"
            partial_count += 1
            log(f"  ⚠️  PARTIAL — {'hero only' if now_has_hero else 'screenshot only'} — retrying next run")
        else:
            article["images_added"] = False
            fail_count += 1
            log(f"  ❌ FAILED — no images added — retrying next run")

    save_json(HANDOFFS, handoffs)

    log(f"Image Agent complete — Complete: {success_count} | Partial: {partial_count} | Failed: {fail_count}")
    print(f"\n✅ Image Agent done — {success_count} complete, {partial_count} partial, {fail_count} failed\n")
    print("Partial and failed articles retry automatically next run.\n")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run()