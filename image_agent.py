import json
import os
import re
import time
import requests
from datetime import datetime
from anthropic import Anthropic
from bs4 import BeautifulSoup

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
MIN_HERO_BYTES       = 50  * 1024   # Hero image minimum: 50KB
MIN_HERO_REJECTS     = 20  * 1024   # Hero hard reject below 20KB
MIN_SCREENSHOT_BYTES = 60  * 1024   # Catches Cloudflare/login walls
LOGIN_WALL_BYTES     = 15  * 1024   # Blank/login wall hard reject
MIN_PRESSKIT_BYTES   = 30  * 1024   # Press kit minimum
MIN_LOGO_BYTES       =  2  * 1024   # Logos are small by nature
MAX_UPLOAD_BYTES     = 500 * 1024   # Compress anything over 500KB

os.makedirs(LOGS_DIR, exist_ok=True)

# ── Tool screenshot URLs — HOMEPAGES ONLY ─────────────────────────────────────
# CRITICAL: Always use the public homepage or a public marketing page.
# NEVER use /app/, /dashboard/, or any URL that requires login.
# Login walls produce ~15KB screenshots that get rejected — waste of time.
# The homepage screenshot shows the product to the reader without requiring auth.
TOOL_URLS = {
    "canva":                    "https://www.canva.com",
    "descript":                 "https://www.descript.com",
    "elevenlabs":               "https://elevenlabs.io",
    "riverside":                "https://riverside.fm",
    "riverside.fm":             "https://riverside.fm",
    "convertkit":               "https://convertkit.com",
    "beehiiv":                  "https://www.beehiiv.com",
    "kajabi":                   "https://kajabi.com",
    "notion":                   "https://www.notion.so",
    "loom":                     "https://www.loom.com",
    "opus clip":                "https://www.opus.pro",
    "pictory":                  "https://pictory.ai",
    "buzzsprout":               "https://www.buzzsprout.com",
    "surfer seo":               "https://surferseo.com",
    "surfer":                   "https://surferseo.com",
    "podcastle":                "https://podcastle.ai",
    "synthesia":                "https://www.synthesia.io",
    "otter.ai":                 "https://otter.ai",
    "later":                    "https://later.com",
    "stan store":               "https://stan.store",
    "gumroad":                  "https://gumroad.com",
    "typeform":                 "https://www.typeform.com",
    "metricool":                "https://metricool.com",
    "teachable":                "https://teachable.com",
    "jasper ai":                "https://www.jasper.ai",
    "krisp":                    "https://krisp.ai",
    "krisp accent conversion":  "https://krisp.ai",
    "coursekit":                "https://coursekit.dev",
    "willow voice":             "https://willow.voice",
    "willow voice for teams":   "https://willow.voice",
    "spoke":                    "https://www.spoke.app",
    "trimmr":                   "https://trimmr.ai",
    "vois":                     "https://vois.ai",
    "luma agents":              "https://lumalabs.ai",
}

# ── Press kit / media page URLs ───────────────────────────────────────────────
PRESS_KIT_URLS = {
    "canva":        "https://www.canva.com/newsroom/",
    "notion":       "https://www.notion.so/about",
    "kajabi":       "https://kajabi.com/press",
    "beehiiv":      "https://www.beehiiv.com/press",
    "convertkit":   "https://convertkit.com/press",
    "loom":         "https://www.loom.com/press",
    "typeform":     "https://www.typeform.com/press/",
    "surfer seo":   "https://surferseo.com/press/",
    "surfer":       "https://surferseo.com/press/",
    "descript":     "https://www.descript.com/press",
    "synthesia":    "https://www.synthesia.io/press",
    "buzzsprout":   "https://www.buzzsprout.com/press",
    "later":        "https://later.com/press/",
    "teachable":    "https://teachable.com/press",
    "jasper ai":    "https://www.jasper.ai/press",
    "elevenlabs":   "https://elevenlabs.io/press",
    "trimmr":       "https://www.trimmr.ai/blog",
}

# ── Page labels for screenshot captions ──────────────────────────────────────
TOOL_PAGE_LABELS = {
    "canva":                    "homepage",
    "descript":                 "homepage",
    "elevenlabs":               "homepage",
    "riverside":                "homepage",
    "riverside.fm":             "homepage",
    "convertkit":               "homepage",
    "beehiiv":                  "homepage",
    "kajabi":                   "homepage",
    "notion":                   "homepage",
    "loom":                     "homepage",
    "opus clip":                "homepage",
    "pictory":                  "homepage",
    "buzzsprout":               "homepage",
    "surfer seo":               "homepage",
    "surfer":                   "homepage",
    "podcastle":                "homepage",
    "synthesia":                "homepage",
    "otter.ai":                 "homepage",
    "later":                    "homepage",
    "stan store":               "homepage",
    "gumroad":                  "homepage",
    "typeform":                 "homepage",
    "metricool":                "homepage",
    "teachable":                "homepage",
    "jasper ai":                "homepage",
    "krisp":                    "homepage",
    "krisp accent conversion":  "homepage",
    "coursekit":                "homepage",
    "willow voice":             "homepage",
    "willow voice for teams":   "homepage",
    "spoke":                    "homepage",
    "trimmr":                   "homepage",
    "vois":                     "homepage",
    "luma agents":              "homepage",
}

# ── Tool-specific Pexels search queries ───────────────────────────────────────
# Prevents generic/duplicate images across similar tools.
# Each query is unique so Pexels returns different photos.
TOOL_PEXELS_QUERIES = {
    "canva":                    "graphic designer creating social media post",
    "descript":                 "video editor working timeline editing",
    "elevenlabs":               "voice over artist recording microphone studio",
    "riverside":                "podcast interview remote recording setup",
    "riverside.fm":             "podcast interview remote recording setup",
    "convertkit":               "email marketer writing newsletter laptop",
    "beehiiv":                  "newsletter writer typing coffee morning",
    "kajabi":                   "online course instructor filming camera",
    "notion":                   "productivity workspace notes organisation",
    "loom":                     "screen recorder video message laptop",
    "opus clip":                "short form video creator editing clips",
    "pictory":                  "video content creator editing footage",
    "buzzsprout":               "podcast host microphone recording desk",
    "surfer seo":               "seo writer content strategy laptop",
    "krisp":                    "remote worker video call headset home office",
    "krisp accent conversion":  "remote worker video call headset home office",
    "coursekit":                "online course creator teaching students",
    "willow voice":             "voice dictation professional working",
    "willow voice for teams":   "remote team collaboration meeting",
    "spoke":                    "professional dictating voice notes phone",
    "trimmr":                   "youtube creator editing video shorts",
    "jasper ai":                "copywriter writing marketing content",
    "convertkit":               "email campaign creator laptop coffee",
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

def get_screenshot_caption(tool_name: str) -> str:
    tool_key   = tool_name.lower()
    page_label = TOOL_PAGE_LABELS.get(tool_key, "homepage")
    return f"{tool_name} — {page_label}"

# ── Image compression ─────────────────────────────────────────────────────────
def compress_image(image_bytes: bytes, max_kb: int = 500) -> bytes:
    if len(image_bytes) <= max_kb * 1024:
        return image_bytes
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img.thumbnail((1600, 1000), Image.LANCZOS)
        buf = io.BytesIO()
        quality = 85
        while quality >= 40:
            buf.seek(0)
            buf.truncate()
            img.save(buf, format="JPEG", quality=quality)
            if len(buf.getvalue()) <= max_kb * 1024:
                break
            quality -= 10
        compressed = buf.getvalue()
        log(f"  Compressed: {len(image_bytes) // 1024}KB → {len(compressed) // 1024}KB")
        return compressed
    except ImportError:
        log("  Pillow not installed — skipping compression")
        return image_bytes
    except Exception as e:
        log(f"  Compression failed: {e} — using original")
        return image_bytes

# ── Logo fetcher (Clearbit) ───────────────────────────────────────────────────
TOOL_DOMAINS = {
    "canva":                    "canva.com",
    "descript":                 "descript.com",
    "elevenlabs":               "elevenlabs.io",
    "riverside":                "riverside.fm",
    "riverside.fm":             "riverside.fm",
    "convertkit":               "convertkit.com",
    "beehiiv":                  "beehiiv.com",
    "kajabi":                   "kajabi.com",
    "notion":                   "notion.so",
    "loom":                     "loom.com",
    "opus clip":                "opus.pro",
    "pictory":                  "pictory.ai",
    "buzzsprout":               "buzzsprout.com",
    "surfer seo":               "surferseo.com",
    "surfer":                   "surferseo.com",
    "podcastle":                "podcastle.ai",
    "synthesia":                "synthesia.io",
    "otter.ai":                 "otter.ai",
    "later":                    "later.com",
    "stan store":               "stanwith.me",
    "gumroad":                  "gumroad.com",
    "typeform":                 "typeform.com",
    "metricool":                "metricool.com",
    "teachable":                "teachable.com",
    "jasper ai":                "jasper.ai",
    "krisp":                    "krisp.ai",
    "krisp accent conversion":  "krisp.ai",
    "coursekit":                "coursekit.dev",
    "willow voice":             "willow.voice",
    "willow voice for teams":   "willow.voice",
    "spoke":                    "spoke.app",
    "trimmr":                   "trimmr.ai",
    "vois":                     "vois.ai",
    "luma agents":              "lumalabs.ai",
}

def fetch_logo(tool_name: str) -> bytes | None:
    tool_key = tool_name.lower()
    domain   = TOOL_DOMAINS.get(tool_key)
    if not domain:
        slug   = re.sub(r"[^a-z0-9]", "", tool_key)
        domain = f"{slug}.com"
    url = f"https://logo.clearbit.com/{domain}"
    log(f"  Fetching logo: {url}")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            size = len(response.content)
            if size >= MIN_LOGO_BYTES:
                log(f"  ✅ Logo fetched ({size // 1024}KB)")
                return response.content
            else:
                log(f"  ❌ Logo too small ({size}B)")
                return None
        else:
            log(f"  ❌ Clearbit returned {response.status_code} for {domain}")
            return None
    except Exception as e:
        log(f"  Logo fetch failed: {e}")
        return None

def build_logo_html(image_url: str, tool_name: str) -> str:
    return f"""
<div style="text-align: center; margin: 1em 0 2em 0;">
  <img
    src="{image_url}"
    alt="{tool_name} logo"
    style="height: 48px; width: auto; object-fit: contain;"
    loading="lazy"
  />
</div>"""

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
        return False, f"likely login wall or blank ({size // 1024}KB)"
    if size < MIN_SCREENSHOT_BYTES:
        return False, f"too small — likely bot challenge ({size // 1024}KB)"
    return True, f"passed ({size // 1024}KB)"

def check_presskit_quality(image_bytes: bytes) -> tuple[bool, str]:
    size = len(image_bytes)
    if size < MIN_PRESSKIT_BYTES:
        return False, f"too small ({size // 1024}KB)"
    return True, f"passed ({size // 1024}KB)"

# ── Screenshot HTML ───────────────────────────────────────────────────────────
def build_screenshot_html(image_url: str, alt_text: str, tool_name: str) -> str:
    caption = get_screenshot_caption(tool_name)
    return f"""
<figure style="margin: 2em 0; text-align: center;">
  <img
    src="{image_url}"
    alt="{alt_text}"
    style="width: 100%; max-width: 900px; border-radius: 8px; border: 1px solid #e0e0e0; box-shadow: 0 2px 12px rgba(0,0,0,0.10);"
    loading="lazy"
  />
  <figcaption style="margin-top: 0.6em; font-size: 0.92em; color: #666; font-style: italic;">
    {caption}
  </figcaption>
</figure>"""

def inject_screenshot_into_article(article_html: str, screenshot_html: str) -> str:
    first_p_end = article_html.find("</p>")
    if first_p_end == -1:
        return screenshot_html + article_html
    insert_pos = first_p_end + len("</p>")
    return article_html[:insert_pos] + "\n" + screenshot_html + article_html[insert_pos:]

def update_wp_post_content(wp_post_id: int, new_html: str) -> bool:
    try:
        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
            json={"content": new_html},
            auth=wp_auth(),
            timeout=30
        )
        return response.status_code in (200, 201)
    except Exception as e:
        log(f"  WordPress content update failed: {e}")
        return False

def get_media_url(media_id: int) -> str | None:
    try:
        response = requests.get(
            f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
            auth=wp_auth(), timeout=10
        )
        if response.status_code == 200:
            return response.json().get("source_url")
        return None
    except Exception as e:
        log(f"  Could not get media URL: {e}")
        return None

# ── Step 1: Claude generates search queries ───────────────────────────────────
def get_image_search_query(tool_name: str, article_title: str, keyword: str) -> dict:
    tool_key = tool_name.lower()

    # Use tool-specific query if available — prevents duplicate images
    specific_query = TOOL_PEXELS_QUERIES.get(tool_key)

    prompt = f"""You are helping find the perfect stock photo for an affiliate review article.

Tool: {tool_name}
Article title: {article_title}
Primary keyword: {keyword}
{"Suggested primary query: " + specific_query if specific_query else ""}

Generate unique photo search queries. Each query must be DIFFERENT from the others
and specific enough to return different photos than other tool reviews.

Think about what type of creator uses this specific tool and show them in action.
NOT generic desk/laptop photos — show the specific use case.

Examples of GOOD queries:
- "podcast host recording microphone soundproofed room" (for audio tools)
- "video editor color grading monitor" (for video tools)
- "newsletter writer coffee morning laptop" (for email tools)

RESPOND IN THIS EXACT JSON FORMAT only:
{{
  "primary_query": "<specific 4-6 word query unique to this tool>",
  "fallback_query": "<different angle, still specific>",
  "last_resort_query": "person working laptop desk",
  "hero_alt_text": "<alt text under 125 chars with keyword>",
  "screenshot_alt_text": "<alt text under 125 chars for homepage screenshot>"
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
        result = json.loads(raw)
        # Override primary query with tool-specific one if available
        if specific_query:
            result["primary_query"] = specific_query
        return result
    except Exception as e:
        log(f"  Claude query generation failed: {e}")
        fallback = specific_query or f"{tool_name} creator tool"
        return {
            "primary_query":      fallback,
            "fallback_query":     "content creator laptop working",
            "last_resort_query":  "person working laptop desk",
            "hero_alt_text":      f"{tool_name} review for creators",
            "screenshot_alt_text": f"{tool_name} homepage"
        }

# ── Step 2: Screenshot tool homepage ─────────────────────────────────────────
# Screenshot is now the PRIMARY image for articles — shown as hero and in body.
# Pexels/Pixabay stock photos are fallback only.
# Using homepage URLs only — never login/dashboard URLs.
def screenshot_tool_homepage(tool_name: str) -> bytes | None:
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
        log(f"  No URL for {tool_name} — trying {url}")

    log(f"  Screenshotting homepage: {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page    = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)

            # Dismiss cookie banners
            for selector in [
                "[id*='cookie'] button", "[class*='cookie'] button",
                "button:has-text('Accept')", "button:has-text('Got it')",
                "button:has-text('Accept all')", "button:has-text('Allow')",
                "button:has-text('I agree')", "button:has-text('Agree')",
            ]:
                try:
                    page.click(selector, timeout=1500)
                    time.sleep(0.5)
                    break
                except Exception:
                    pass

            screenshot_bytes = page.screenshot(type="jpeg", quality=85)
            browser.close()

            passed, reason = check_screenshot_quality(screenshot_bytes)
            if not passed:
                log(f"  ❌ Homepage screenshot quality failed: {reason}")
                return None
            log(f"  ✅ Homepage screenshot: {reason}")
            return screenshot_bytes
    except Exception as e:
        log(f"  Homepage screenshot failed for {tool_name}: {e}")
        return None

# ── Step 3: Press kit fallback ────────────────────────────────────────────────
def fetch_presskit_image(tool_name: str) -> bytes | None:
    tool_key     = tool_name.lower()
    presskit_url = PRESS_KIT_URLS.get(tool_key)

    if not presskit_url:
        log(f"  No press kit URL for {tool_name}")
        return None

    log(f"  Trying press kit: {presskit_url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        page_response = requests.get(presskit_url, headers=headers, timeout=15)
        if page_response.status_code != 200:
            log(f"  Press kit returned {page_response.status_code}")
            return None

        soup           = BeautifulSoup(page_response.text, "html.parser")
        candidate_urls = []

        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                if src.startswith("//"):   src = "https:" + src
                elif src.startswith("/"): 
                    from urllib.parse import urlparse
                    base = urlparse(presskit_url)
                    src  = f"{base.scheme}://{base.netloc}{src}"
                candidate_urls.append(src)

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(ext in href.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                if href.startswith("//"): href = "https:" + href
                candidate_urls.append(href)

        log(f"  Found {len(candidate_urls)} candidate images on press kit page")

        for img_url in candidate_urls[:15]:
            try:
                img_response = requests.get(img_url, headers=headers, timeout=10)
                if img_response.status_code == 200:
                    image_bytes = img_response.content
                    passed, reason = check_presskit_quality(image_bytes)
                    if passed:
                        log(f"  ✅ Press kit image: {reason}")
                        return image_bytes
            except Exception:
                continue

        log(f"  ❌ No usable images on press kit page")
        return None
    except Exception as e:
        log(f"  Press kit failed for {tool_name}: {e}")
        return None

# ── Step 4: Stock photo fallback ─────────────────────────────────────────────
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
            log(f"  Pexels error: {response.status_code}")
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
        log(f"  Pexels failed: {e}")
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
        response = requests.get("https://pixabay.com/api/", params=params, timeout=15)
        if response.status_code != 200:
            log(f"  Pixabay error: {response.status_code}")
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
        log(f"  Pixabay failed: {e}")
        return None

def get_stock_hero(queries: dict) -> tuple[bytes | None, str]:
    """Stock photo fallback when screenshot fails."""
    attempts = [
        ("Pexels",  fetch_pexels_image,  queries["primary_query"]),
        ("Pexels",  fetch_pexels_image,  queries["fallback_query"]),
        ("Pixabay", fetch_pixabay_image, queries["primary_query"]),
        ("Pixabay", fetch_pixabay_image, queries["fallback_query"]),
        ("Pexels",  fetch_pexels_image,  queries["last_resort_query"]),
        ("Pixabay", fetch_pixabay_image, queries["last_resort_query"]),
    ]
    for source, fetcher, query in attempts:
        log(f"  Trying {source} stock: '{query}'")
        image_bytes = fetcher(query)
        if image_bytes:
            passed, reason = check_hero_quality(image_bytes, source)
            if passed:
                log(f"  ✅ Stock hero quality: {reason}")
                return image_bytes, f"{source} — '{query}'"
            else:
                log(f"  ❌ Stock hero rejected: {reason}")
    return None, "all stock sources exhausted"

# ── Step 5: Upload to WordPress ───────────────────────────────────────────────
def upload_to_wordpress(
    image_bytes: bytes, filename: str, alt_text: str, caption: str = ""
) -> int | None:
    image_bytes = compress_image(image_bytes, max_kb=500)
    endpoint    = f"{WP_URL}/wp-json/wp/v2/media"
    headers     = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type":        "image/jpeg",
    }
    try:
        response = requests.post(
            endpoint, headers=headers, data=image_bytes,
            auth=wp_auth(), timeout=60
        )
        if response.status_code in (200, 201):
            media_id = response.json().get("id")
            requests.post(
                f"{endpoint}/{media_id}",
                json={"alt_text": alt_text, "caption": caption},
                auth=wp_auth(), timeout=10
            )
            log(f"  Uploaded → media ID: {media_id}")
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

    candidates = {}
    for slug, article in handoffs.items():
        status = article.get("status")
        if status not in ("pending_publish", "draft_live", "published"):
            continue

        images_added     = article.get("images_added")
        image_data       = article.get("image_data", {})
        wp_post_id       = article.get("wp_post_id")

        if images_added != True:
            candidates[slug] = article
            continue

        has_screenshot   = bool(image_data.get("screenshot_media_id"))
        already_injected = bool(image_data.get("screenshot_injected"))
        has_live_post    = bool(wp_post_id)

        if has_screenshot and not already_injected and has_live_post:
            log(f"  🔁 Queuing {article.get('tool_name', slug)} — screenshot needs injection")
            candidates[slug] = article

    log(f"Found {len(candidates)} articles needing images")

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

        existing         = article.get("image_data", {})
        has_hero         = bool(existing.get("hero_media_id"))
        has_shot         = bool(existing.get("screenshot_media_id"))
        has_logo         = bool(existing.get("logo_media_id"))
        already_injected = bool(existing.get("screenshot_injected"))

        log(f"Processing: {tool_name} | hero: {'✅' if has_hero else '❌'} | screenshot: {'✅' if has_shot else '❌'} | logo: {'✅' if has_logo else '❌'}")

        queries     = get_image_search_query(tool_name, title, keyword)
        images_data = existing.copy()

        # ── PRIMARY: Screenshot the tool homepage ─────────────────────────────
        # Screenshot goes first — it's the most relevant image for the article.
        # Shows the actual tool. Much better than a generic stock photo.
        if not has_shot:
            shot_bytes = screenshot_tool_homepage(tool_name)

            if not shot_bytes:
                log(f"  Homepage screenshot failed — trying press kit for {tool_name}")
                shot_bytes = fetch_presskit_image(tool_name)
                shot_source = "press_kit"
            else:
                shot_source = "homepage_screenshot"

            if shot_bytes:
                shot_id = upload_to_wordpress(
                    shot_bytes, f"{slug}-screenshot.jpg",
                    queries["screenshot_alt_text"],
                    caption=f"{tool_name} — homepage"
                )
                if shot_id:
                    images_data["screenshot_media_id"] = shot_id
                    images_data["screenshot_alt_text"]  = queries["screenshot_alt_text"]
                    images_data["screenshot_source"]    = shot_source
                    has_shot = True
                    log(f"  ✅ Tool image uploaded ({shot_source}) — media ID: {shot_id}")

                    # Use homepage screenshot as featured image too
                    if wp_post_id and not has_hero:
                        if set_featured_image(wp_post_id, shot_id):
                            images_data["hero_media_id"] = shot_id
                            images_data["hero_source"]   = shot_source
                            has_hero = True
                            log(f"  ✅ Homepage screenshot set as featured image")
            else:
                log(f"  ❌ Screenshot + press kit both failed — falling back to stock photo")

        # ── FALLBACK: Stock photo if screenshot failed ────────────────────────
        if not has_hero:
            log(f"  Falling back to stock photo for hero image")
            hero_bytes, source = get_stock_hero(queries)
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
                    has_hero = True
                    if wp_post_id:
                        if set_featured_image(wp_post_id, hero_id):
                            log(f"  ✅ Stock photo set as featured image")
            else:
                log(f"  ❌ All hero sources exhausted for {tool_name}")

        # ── Logo (Clearbit) ───────────────────────────────────────────────────
        if not has_logo:
            logo_bytes = fetch_logo(tool_name)
            if logo_bytes:
                logo_id = upload_to_wordpress(
                    logo_bytes, f"{slug}-logo.png",
                    f"{tool_name} logo",
                    caption=f"{tool_name} logo"
                )
                if logo_id:
                    images_data["logo_media_id"] = logo_id
                    log(f"  ✅ Logo uploaded — media ID: {logo_id}")

                    if wp_post_id:
                        logo_url = get_media_url(logo_id)
                        if logo_url:
                            post_response = requests.get(
                                f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
                                auth=wp_auth(), timeout=10
                            )
                            if post_response.status_code == 200:
                                current_html = post_response.json().get("content", {}).get("raw", "")
                                if not current_html:
                                    current_html = post_response.json().get("content", {}).get("rendered", "")
                                if current_html:
                                    logo_block   = build_logo_html(logo_url, tool_name)
                                    updated_html = logo_block + current_html
                                    if update_wp_post_content(wp_post_id, updated_html):
                                        log(f"  ✅ Logo injected at top of article")
                                        images_data["logo_injected"] = True
            else:
                log(f"  ⚠️  Logo not found for {tool_name}")

        # ── Inject screenshot into article body ───────────────────────────────
        if has_shot and not already_injected and wp_post_id:
            shot_id = images_data.get("screenshot_media_id")
            if shot_id:
                media_url = get_media_url(shot_id)
                if media_url:
                    post_response = requests.get(
                        f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
                        auth=wp_auth(), timeout=10
                    )
                    if post_response.status_code == 200:
                        current_html = post_response.json().get("content", {}).get("raw", "")
                        if not current_html:
                            current_html = post_response.json().get("content", {}).get("rendered", "")
                        if current_html:
                            screenshot_block = build_screenshot_html(
                                media_url,
                                images_data.get("screenshot_alt_text", f"{tool_name} homepage"),
                                tool_name
                            )
                            updated_html = inject_screenshot_into_article(
                                current_html, screenshot_block
                            )
                            if update_wp_post_content(wp_post_id, updated_html):
                                log(f"  ✅ Screenshot injected into article body")
                                images_data["screenshot_injected"] = True
        elif has_shot and not already_injected and not wp_post_id:
            log(f"  ℹ️  No wp_post_id yet — injection queued for publish time")

        # ── Final status ──────────────────────────────────────────────────────
        now_has_hero = bool(images_data.get("hero_media_id"))
        now_has_shot = bool(images_data.get("screenshot_media_id"))
        now_has_logo = bool(images_data.get("logo_media_id"))

        article["image_data"]  = images_data
        article["images_date"] = datetime.now().strftime("%Y-%m-%d")

        if now_has_hero and now_has_shot:
            article["images_added"] = True
            success_count += 1
            logo_note = " + logo" if now_has_logo else ""
            log(f"  ✅ COMPLETE — hero + screenshot{logo_note}")
        elif now_has_hero or now_has_shot:
            article["images_added"] = True
            success_count += 1
            log(f"  ✅ COMPLETE — {'hero' if now_has_hero else 'screenshot'} ready")
        else:
            article["images_added"] = False
            fail_count += 1
            log(f"  ❌ FAILED — no images added — retrying next run")

    save_json(HANDOFFS, handoffs)

    log(f"Image Agent complete — Complete: {success_count} | Partial: {partial_count} | Failed: {fail_count}")
    print(f"\n✅ Image Agent done — {success_count} complete, {partial_count} partial, {fail_count} failed\n")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run()