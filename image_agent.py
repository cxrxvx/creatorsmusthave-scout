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
MIN_HERO_BYTES       = 50 * 1024   # Hero image minimum: 50KB
MIN_HERO_REJECTS     = 20 * 1024   # Hero hard reject below 20KB
MIN_SCREENSHOT_BYTES = 60 * 1024   # Raised from 25KB — catches Cloudflare/login walls
LOGIN_WALL_BYTES     = 15 * 1024   # Blank/login wall hard reject below 15KB
MIN_PRESSKIT_BYTES   = 30 * 1024   # Press kit images can be smaller but still real
MIN_LOGO_BYTES       =  2 * 1024   # Logos are small by nature — just reject blank/broken
MAX_UPLOAD_BYTES     = 500 * 1024  # Compress anything over 500KB before uploading

os.makedirs(LOGS_DIR, exist_ok=True)

# ── Tool URL map ──────────────────────────────────────────────────────────────
TOOL_URLS = {
    "canva":                    "https://www.canva.com/templates/",
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
    "trimmr":                   "https://app.trimmr.ai",
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

# ── Human-readable page labels for screenshot captions ───────────────────────
TOOL_PAGE_LABELS = {
    "canva":                    "template gallery",
    "descript":                 "editor dashboard",
    "elevenlabs":               "speech synthesis studio",
    "riverside":                "recording studio",
    "riverside.fm":             "recording studio",
    "convertkit":               "creator dashboard",
    "beehiiv":                  "newsletter dashboard",
    "kajabi":                   "course builder",
    "notion":                   "template gallery",
    "loom":                     "video library",
    "opus clip":                "AI clip creator",
    "pictory":                  "video editor",
    "buzzsprout":               "podcast dashboard",
    "surfer seo":               "content editor",
    "surfer":                   "content editor",
    "podcastle":                "recording studio",
    "synthesia":                "AI avatar creator",
    "otter.ai":                 "transcription dashboard",
    "later":                    "social media scheduler",
    "stan store":               "creator storefront",
    "gumroad":                  "creator dashboard",
    "typeform":                 "form template gallery",
    "metricool":                "analytics dashboard",
    "teachable":                "course examples",
    "jasper ai":                "AI writing dashboard",
    "krisp":                    "noise cancellation settings",
    "krisp accent conversion":  "accent conversion settings",
    "coursekit":                "course platform",
    "willow":                   "voice assistant dashboard",
    "willow voice for teams":   "team dashboard",
    "spoke":                    "meeting intelligence dashboard",
    "trimmr":                   "AI video trimmer",
    "vois":                     "AI voice generator",
    "luma agents":              "AI creative agents",
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
    tool_key = tool_name.lower()
    page_label = TOOL_PAGE_LABELS.get(tool_key, "interface")
    return f"{tool_name} — {page_label}"

# ── Image compression ─────────────────────────────────────────────────────────
def compress_image(image_bytes: bytes, max_kb: int = 500) -> bytes:
    """
    Compress image to under max_kb using Pillow.
    Prevents WordPress upload timeouts from oversized press kit images.
    Falls back to original if Pillow not installed or compression fails.
    """
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
        log(f"  Compressed image: {len(image_bytes) // 1024}KB → {len(compressed) // 1024}KB")
        return compressed
    except ImportError:
        log("  Pillow not installed — skipping compression (run: pip install Pillow --break-system-packages)")
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
    "coursekit":                "coursekit.io",
    "willow":                   "willow.app",
    "willow voice for teams":   "willow.app",
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
        log(f"  No domain mapping for {tool_name} — guessing {domain}")

    url = f"https://logo.clearbit.com/{domain}"
    log(f"  Fetching logo: {url}")

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            size = len(response.content)
            if size >= MIN_LOGO_BYTES:
                log(f"  ✅ Logo fetched ({size // 1024}KB) for {tool_name}")
                return response.content
            else:
                log(f"  ❌ Logo too small ({size}B) — likely placeholder")
                return None
        else:
            log(f"  ❌ Clearbit returned {response.status_code} for {domain}")
            return None
    except Exception as e:
        log(f"  Logo fetch failed for {tool_name}: {e}")
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
        return False, f"likely login wall or blank page ({size // 1024}KB)"
    if size < MIN_SCREENSHOT_BYTES:
        return False, f"too small — likely bot challenge page ({size // 1024}KB) — minimum is 60KB"
    return True, f"passed ({size // 1024}KB)"

def check_presskit_quality(image_bytes: bytes) -> tuple[bool, str]:
    size = len(image_bytes)
    if size < MIN_PRESSKIT_BYTES:
        return False, f"too small for press kit image ({size // 1024}KB)"
    return True, f"passed ({size // 1024}KB)"

# ── Screenshot HTML injection ─────────────────────────────────────────────────
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
        log("  Could not find </p> — prepending screenshot")
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

# ── Step 3a: Screenshot tool website ─────────────────────────────────────────
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

# ── Step 3b: Press kit fallback ───────────────────────────────────────────────
def fetch_presskit_image(tool_name: str) -> bytes | None:
    tool_key     = tool_name.lower()
    presskit_url = PRESS_KIT_URLS.get(tool_key)

    if not presskit_url:
        log(f"  No press kit URL for {tool_name} — skipping press kit fallback")
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
            log(f"  Press kit page returned {page_response.status_code}")
            return None

        soup = BeautifulSoup(page_response.text, "html.parser")
        candidate_urls = []

        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    from urllib.parse import urlparse
                    base = urlparse(presskit_url)
                    src = f"{base.scheme}://{base.netloc}{src}"
                candidate_urls.append(src)

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(ext in href.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                if href.startswith("//"):
                    href = "https:" + href
                candidate_urls.append(href)

        log(f"  Found {len(candidate_urls)} candidate image URLs on press kit page")

        for img_url in candidate_urls[:15]:
            try:
                img_response = requests.get(img_url, headers=headers, timeout=10)
                if img_response.status_code == 200:
                    image_bytes = img_response.content
                    passed, reason = check_presskit_quality(image_bytes)
                    if passed:
                        log(f"  ✅ Press kit image found: {reason} — {img_url[:60]}...")
                        return image_bytes
                    else:
                        log(f"  ↩️  Skipping small image: {reason}")
            except Exception:
                continue

        log(f"  ❌ No usable images found on press kit page")
        return None

    except Exception as e:
        log(f"  Press kit fetch failed for {tool_name}: {e}")
        return None

# ── Step 3: Get best available tool image ─────────────────────────────────────
def get_tool_image(tool_name: str) -> tuple[bytes | None, str]:
    shot_bytes = screenshot_tool(tool_name)
    if shot_bytes:
        return shot_bytes, "screenshot"

    log(f"  Screenshot failed — trying press kit fallback for {tool_name}")
    presskit_bytes = fetch_presskit_image(tool_name)
    if presskit_bytes:
        return presskit_bytes, "press_kit"

    return None, "all sources failed"

# ── Step 4: Upload to WordPress ───────────────────────────────────────────────
def upload_to_wordpress(
    image_bytes: bytes, filename: str, alt_text: str, caption: str = ""
) -> int | None:
    # Compress large images before upload to prevent timeouts
    image_bytes = compress_image(image_bytes, max_kb=500)

    endpoint = f"{WP_URL}/wp-json/wp/v2/media"
    headers  = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type":        "image/jpeg",
    }
    try:
        response = requests.post(
            endpoint, headers=headers, data=image_bytes,
            auth=wp_auth(), timeout=60  # increased from 30 to 60
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

    # ── Candidate selection ───────────────────────────────────────────────────
    # Three cases get processed:
    #
    # Case 1 — Needs images: images_added is not True (False, "partial", missing)
    #          Catches pending_publish, draft_live, AND published articles
    #          so nothing with missing images ever gets permanently skipped.
    #
    # Case 2 — Injection catch-up: images_added=True, screenshot was uploaded
    #          but never injected into WordPress because article wasn't live yet.
    #          Now has wp_post_id so we inject retroactively.
    # ─────────────────────────────────────────────────────────────────────────
    candidates = {}
    for slug, article in handoffs.items():
        status = article.get("status")

        # Skip articles that haven't entered the pipeline yet
        if status not in ("pending_publish", "draft_live", "published"):
            continue

        images_added     = article.get("images_added")
        image_data       = article.get("image_data", {})
        wp_post_id       = article.get("wp_post_id")

        # Case 1: needs images — includes published articles with missing images
        if images_added != True:
            candidates[slug] = article
            continue

        # Case 2: screenshot uploaded but never injected into a live post
        has_screenshot   = bool(image_data.get("screenshot_media_id"))
        already_injected = bool(image_data.get("screenshot_injected"))
        has_live_post    = bool(wp_post_id)

        if has_screenshot and not already_injected and has_live_post:
            log(f"  🔁 Queuing {article.get('tool_name', slug)} — screenshot needs injection into post {wp_post_id}")
            candidates[slug] = article

    log(f"Found {len(candidates)} articles needing images (including partials and pending injections)")

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

        log(f"Processing: {tool_name} | hero: {'✅' if has_hero else '❌'} | screenshot: {'✅' if has_shot else '❌'} | logo: {'✅' if has_logo else '❌'} | injected: {'✅' if already_injected else '❌'}")

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

        # ── Logo (Clearbit) ──
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
                log(f"  ⚠️  Logo not found for {tool_name} — article still fine without it")

        # ── Tool screenshot: fetch if not yet uploaded ──
        if not has_shot:
            shot_bytes, shot_source = get_tool_image(tool_name)
            if shot_bytes:
                shot_id = upload_to_wordpress(
                    shot_bytes, f"{slug}-screenshot.jpg",
                    queries["screenshot_alt_text"],
                    caption=f"{tool_name} interface screenshot"
                )
                if shot_id:
                    images_data["screenshot_media_id"] = shot_id
                    images_data["screenshot_alt_text"]  = queries["screenshot_alt_text"]
                    images_data["screenshot_source"]    = shot_source
                    log(f"  ✅ Tool image uploaded ({shot_source}) — media ID: {shot_id}")
                    has_shot = True  # mark so injection block below runs
            else:
                log(f"  ❌ Screenshot + press kit both failed for {tool_name} — retrying next run")

        # ── Inject screenshot into article body ──
        # Runs if: screenshot exists AND not yet injected AND post is live
        # Handles both fresh articles and catch-up injection for already-published ones
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
                                images_data.get("screenshot_alt_text", f"{tool_name} interface"),
                                tool_name
                            )
                            updated_html = inject_screenshot_into_article(
                                current_html, screenshot_block
                            )
                            if update_wp_post_content(wp_post_id, updated_html):
                                log(f"  ✅ Image injected into article body (post {wp_post_id})")
                                images_data["screenshot_injected"] = True
                            else:
                                log(f"  ⚠️  Could not inject image into article")
                        else:
                            log(f"  ⚠️  Could not retrieve article content for injection")
                    else:
                        log(f"  ⚠️  Could not fetch post {wp_post_id} from WordPress")
                else:
                    log(f"  ⚠️  Could not get media URL for injection")
        elif has_shot and not already_injected and not wp_post_id:
            log(f"  ℹ️  No wp_post_id yet — injection queued for publish time")

        # ── Determine final status ──
        now_has_hero = bool(images_data.get("hero_media_id"))
        now_has_shot = bool(images_data.get("screenshot_media_id"))
        now_has_logo = bool(images_data.get("logo_media_id"))

        article["image_data"]  = images_data
        article["images_date"] = datetime.now().strftime("%Y-%m-%d")

        if now_has_hero and now_has_shot:
            article["images_added"] = True
            success_count += 1
            logo_note = " + logo" if now_has_logo else " (no logo)"
            log(f"  ✅ COMPLETE — hero + tool image{logo_note}")
        elif now_has_hero:
            article["images_added"] = True   # hero alone = complete, screenshot is bonus
            success_count += 1
            log(f"  ✅ COMPLETE — hero image ready (screenshot optional)")
        elif now_has_shot:
            article["images_added"] = "partial"
            partial_count += 1
            log(f"  ⚠️  PARTIAL — screenshot only, no hero — retrying next run")
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