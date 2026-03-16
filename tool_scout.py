"""
tool_scout.py — Tool Discovery Agent for CXRXVX Affiliates
=============================================================
Phase 2.5 Opus Upgrade:
  ✅ Fixed RSS source labels (BetaList feeds had wrong names)
  ✅ Category detection — tools enter pipeline with a category assigned
  ✅ Competitor flagging — detects when new tool competes with existing ones
  ✅ Discovery stats tracked in memory/discovery_stats.json
  ✅ Existing tool names passed to scoring prompt to prevent duplicate scores
  ✅ Removed dead r/AItools subreddit (HTTP 404)
  ✅ Proper promoted/archived counting in summary
  ✅ All existing features preserved (3-tier scoring, watchlist, manual tools, pre-filter)

Scans 13 RSS sources + 14 Reddit subreddits for creator tools.
Scores tools 0-100, routes to pipeline (55+), watchlist (35-54), or rejection.

Drop this file into your cxrxvx-ai-empire/ folder to replace the old tool_scout.py.
"""

import json
import os
import sys
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
import feedparser
import requests
from anthropic import Anthropic

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_DIR.mkdir(exist_ok=True)

TOOL_DB_FILE    = MEMORY_DIR / "tool_database.json"
WATCHLIST_FILE  = MEMORY_DIR / "watchlist.json"
MANUAL_FILE     = MEMORY_DIR / "manual_tools.json"
STATS_FILE      = MEMORY_DIR / "discovery_stats.json"

# ─── Config ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(BASE_DIR))
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── Thresholds ───────────────────────────────────────────────────────────────
FULL_REVIEW_THRESHOLD = 55   # score 55+ → article pipeline
WATCHLIST_THRESHOLD   = 35   # score 35-54 → watchlist

# ─── RSS Feeds — 13 sources (labels fixed in Phase 2.5) ──────────────────────
RSS_FEEDS = [
    {"url": "https://www.producthunt.com/feed?category=artificial-intelligence", "source": "Product Hunt - AI"},
    {"url": "https://www.producthunt.com/feed?category=productivity",            "source": "Product Hunt - Productivity"},
    {"url": "https://www.producthunt.com/feed",                                  "source": "Product Hunt - General"},
    {"url": "https://hnrss.org/newest?q=AI+tool",                                "source": "Hacker News - AI Tools"},
    {"url": "https://hnrss.org/launches",                                        "source": "Hacker News - Launches"},
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/",     "source": "TechCrunch AI"},
    {"url": "https://venturebeat.com/category/ai/feed/",                         "source": "VentureBeat AI"},
    # ⚡ Phase 2.5: fixed labels — these are all BetaList topic feeds
    {"url": "https://betalist.com/topics/ai-tools.atom",           "source": "BetaList - AI Tools"},
    {"url": "https://betalist.com/topics/content-creators.atom",   "source": "BetaList - Content Creators"},
    {"url": "https://betalist.com/topics/video.atom",              "source": "BetaList - Video"},
    {"url": "https://betalist.com/topics/social-media.atom",       "source": "BetaList - Social Media"},
    {"url": "https://www.theverge.com/rss/index.xml",              "source": "The Verge"},
    {"url": "https://www.marktechpost.com/feed/",                  "source": "MarkTechPost"},
]

# ─── Reddit — 14 subreddits (removed dead r/AItools) ─────────────────────────
REDDIT_SUBREDDITS = [
    "artificial", "ChatGPT", "MachineLearning", "singularity",
    "ContentCreators", "Blogging", "YoutubeCreators", "podcasting", "VideoEditing",
    "SideProject", "indiehackers", "Entrepreneur", "passive_income", "SEO",
]

REDDIT_HEADERS = {
    "User-Agent": "CreatorsMustHave-ToolScout/1.0 (tool discovery bot)"
}

# ─── Signal / Reject word lists ───────────────────────────────────────────────
SIGNAL_WORDS = [
    "ai", "gpt", "llm", "generate", "automate", "creator", "video", "audio",
    "voice", "write", "content", "podcast", "youtube", "blog", "seo", "image",
    "affiliate", "saas", "tool", "app", "platform", "launch", "new",
]

REJECT_WORDS = [
    "hardware", "physical", "device", "sensor", "drone", "robot",
    "crypto", "nft", "blockchain", "adult", "gambling", "betting",
    "medical", "healthcare", "hospital", "pharmaceutical",
    "government", "military", "defence", "defense",
]

# ─── Category detection keywords ─────────────────────────────────────────────
# Maps keywords found in tool name/description to categories
# Used to assign a category before the tool reaches keyword_agent
CATEGORY_KEYWORDS = {
    "video": ["video", "youtube", "tiktok", "reels", "shorts", "clip", "editing", "footage",
              "animation", "render", "screen record", "webcam", "stream", "caption", "subtitle"],
    "audio": ["audio", "podcast", "voice", "speech", "music", "sound", "transcri", "dictation",
              "narration", "voiceover", "recording", "microphone", "noise cancell"],
    "writing": ["write", "copy", "blog", "content writ", "article", "grammar", "proofread",
                "paraphrase", "rewrite", "essay", "text generat", "ai writ"],
    "image": ["image", "photo", "graphic", "design", "illustration", "art generat",
              "logo", "banner", "thumbnail", "visual", "midjourney", "dall-e", "stable diffusion"],
    "seo": ["seo", "keyword", "backlink", "serp", "rank", "search engine", "domain authority",
            "organic traffic", "meta tag", "sitemap"],
    "email": ["email", "newsletter", "subscriber", "mailing list", "drip campaign",
              "email market", "broadcast", "inbox"],
    "courses": ["course", "coaching", "lms", "online teach", "student", "curriculum",
                "membership", "lesson", "training platform"],
    "productivity": ["productivity", "project manage", "task", "notion", "organize",
                     "workflow", "automat", "schedule", "calendar", "collaborat"],
}


def detect_category(name: str, description: str) -> str:
    """
    Detect the most likely category for a tool based on name + description.
    Returns the best matching category, or "other" if none match.
    """
    text = (name + " " + description).lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score

    if not scores:
        return "other"
    return max(scores, key=scores.get)


# ─── Competitor detection ─────────────────────────────────────────────────────
# Known tool categories for competitor matching
def find_competitors(tool_name: str, category: str, tool_db: dict) -> list:
    """
    Find existing tools in our database that compete with this new tool.
    Used to flag comparison article opportunities.
    """
    competitors = []
    name_lower = tool_name.lower()

    for key, existing in tool_db.items():
        if not isinstance(existing, dict):
            continue
        existing_cat = existing.get("category", "other")
        existing_name = existing.get("name", "").lower()

        # Same category = potential competitor
        if existing_cat == category and existing_name != name_lower:
            competitors.append(existing.get("name", key))

    # Return top 3 competitors by relevance (same category)
    return competitors[:3]


# ─── Scoring prompt — now with category detection + existing tools context ────

def build_scoring_prompt(existing_tool_names: list) -> str:
    """Build the scoring prompt with context about tools we already cover."""
    existing_context = ""
    if existing_tool_names:
        names_str = ", ".join(existing_tool_names[:30])
        existing_context = f"""
TOOLS WE ALREADY COVER (do NOT score duplicates of these — reject if same product):
{names_str}

If this tool is clearly the same product as one listed above (just a different name
or version), set type = "rejected" and reason = "duplicate of [existing tool name]".
"""

    return f"""You are a tool scout for "Creators Must Have" — a review site for YouTubers, bloggers, podcasters, and online business owners.

Score this tool 0-100 for whether we should write an affiliate review article about it.
{existing_context}
TARGET AUDIENCE: Content creators — YouTubers, bloggers, podcasters, newsletter writers, course creators, social media managers.

SCORING PHILOSOPHY:
We are a NEW site. Our competitive advantage is SPEED — writing about tools BEFORE
established sites do. A fresh tool with zero competing articles is more valuable to
us than an established tool with 500 existing reviews. Score accordingly.

SCORING SYSTEM:

POSITIVE SIGNALS (add these):
+20  Just launched or very new — first-mover SEO advantage, zero competition
+15  Directly helps creators produce content faster or better
+12  Has visible /affiliates or /partners program page
+10  Clear monthly/annual subscription pricing on website
+8   Solves one very specific creator problem extremely well
+7   Fast-growing category: AI video, voice, writing, avatar, agents
+5   Has a free trial or freemium tier
+5   Has paying users, press coverage, or Product Hunt upvotes
+5   SaaS subscription model (likely to add affiliate program later)

NEGATIVE SIGNALS (subtract these):
-15  Pure ChatGPT wrapper with no unique value — just an API skin
-10  Category extremely saturated AND tool has zero differentiation
-8   Enterprise-only, no self-serve signup for individuals
-5   No pricing visible and no clear monetization path at all
-5   Very early vaporware — landing page only, no actual working product

IMPORTANT — do NOT penalize tools for:
- Being new (that's an ADVANTAGE for us — first-mover keywords)
- Not having an affiliate program YET (most SaaS tools add one within 6 months)
- Having a small user base (irrelevant — we care about SEO opportunity)
- Being in a competitive category IF the tool has genuine differentiation

SCORE GUIDE:
  75-100: Strong candidate — write immediately
  55-74:  Worth writing about — good SEO opportunity
  35-54:  Borderline — watchlist and recheck later
  0-34:   Not relevant to our audience — reject

AUTOMATIC REJECTION (score 0):
- Physical hardware / devices
- Open-source library with no paid product
- Not a creator tool (medical, government, legal, financial, developer-only)
- A news article, blog post, or newsletter — must be ACTUAL SOFTWARE
- Adult / gambling / crypto
- Browser extension only (no standalone web product)
- Academic research paper or university project

MAJOR PLATFORM RULE: OpenAI, Anthropic, Google, Meta, Microsoft → score max 70, type = "authority_article", has_affiliate_potential = false.

CATEGORY — assign the most fitting:
video | audio | writing | image | seo | email | courses | productivity | other

Output ONLY valid JSON — no explanation, no notes, nothing after the closing brace:
{{
  "name": "clean tool name",
  "score": 72,
  "type": "affiliate_review",
  "category": "video",
  "reason": "one sentence why",
  "description": "one sentence what it does for creators",
  "has_affiliate_potential": true,
  "is_fast_growing": true
}}

type must be: "affiliate_review" | "authority_article" | "rejected" | "too_weak"
category must be: video | audio | writing | image | seo | email | courses | productivity | other"""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def already_known(name: str, tool_db: dict, watchlist: list) -> bool:
    name_lower = name.lower().strip()
    for key in tool_db:
        if key.lower() == name_lower:
            return True
        # Also check the "name" field inside the tool dict
        if isinstance(tool_db[key], dict) and tool_db[key].get("name", "").lower() == name_lower:
            return True
    for item in watchlist:
        if isinstance(item, dict) and item.get("name", "").lower() == name_lower:
            return True
    return False


def quick_reject(title: str, description: str) -> bool:
    text = (title + " " + description).lower()
    for word in REJECT_WORDS:
        if word in text:
            return True
    return False


def get_existing_tool_names(tool_db: dict) -> list:
    """Get list of tool names we already cover — passed to scoring prompt."""
    names = []
    for key, data in tool_db.items():
        if isinstance(data, dict):
            names.append(data.get("name", key))
        else:
            names.append(key)
    return names


def extract_json(raw: str) -> dict | None:
    """
    Extract a JSON object from Claude's response, ignoring any trailing text.
    
    Claude often outputs valid JSON followed by an explanation:
      {"name": "Tool", "score": 72, ...}
      Note: this tool has strong potential because...
    
    json.loads() chokes on the trailing text. This function finds just the
    JSON object by matching braces.
    """
    # Strip markdown fences
    raw = re.sub(r"^```json\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    # Method 1: Try parsing as-is (works when Claude only outputs JSON)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Method 2: Find the JSON object by matching braces
    start = raw.find("{")
    if start == -1:
        return None

    depth = 0
    end = start
    in_string = False
    escape_next = False

    for i in range(start, len(raw)):
        c = raw[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if depth != 0:
        return None

    json_str = raw[start:end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def score_tool(title: str, description: str, existing_names: list = None) -> dict | None:
    """Ask Claude to score a tool. Returns parsed dict or None on failure."""
    prompt = build_scoring_prompt(existing_names or [])
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": f"{prompt}\n\nTool title: {title}\nDescription: {description or 'No description provided'}"
            }]
        )
        raw = response.content[0].text.strip()
        result = extract_json(raw)
        if result is None:
            print(f"   ⚠️  Could not extract JSON for '{title}'")
            print(f"   Raw: {raw[:200]}")
        return result
    except Exception as e:
        print(f"   ⚠️  Scoring failed for '{title}': {e}")
        return None


def next_recheck_date(attempt: int) -> str:
    days = [2, 5, 14, 30]
    delta = days[min(attempt, len(days) - 1)]
    return (datetime.now() + timedelta(days=delta)).strftime("%Y-%m-%d")


def tool_key(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower().strip()).strip("_")


# ─── Discovery stats tracking ────────────────────────────────────────────────

def update_discovery_stats(rss_aff, rss_auth, red_aff, red_auth, promoted_count, archived_count):
    """Track discovery trends over time."""
    stats = load_json(STATS_FILE, {"daily": {}})
    today = datetime.now().strftime("%Y-%m-%d")

    stats["daily"][today] = {
        "rss_affiliate": len(rss_aff),
        "rss_authority": len(rss_auth),
        "reddit_affiliate": len(red_aff),
        "reddit_authority": len(red_auth),
        "total_discovered": len(rss_aff) + len(rss_auth) + len(red_aff) + len(red_auth),
        "promoted_from_watchlist": promoted_count,
        "archived_from_watchlist": archived_count,
        "timestamp": datetime.now().isoformat(),
    }

    # Keep only last 90 days
    if len(stats["daily"]) > 90:
        sorted_dates = sorted(stats["daily"].keys())
        for old_date in sorted_dates[:-90]:
            del stats["daily"][old_date]

    # Running totals
    stats["total_ever_discovered"] = sum(
        d.get("total_discovered", 0) for d in stats["daily"].values()
    )

    save_json(STATS_FILE, stats)


# ─── Watchlist processing ─────────────────────────────────────────────────────

def process_watchlist():
    tool_db   = load_json(TOOL_DB_FILE, {})
    watchlist = load_json(WATCHLIST_FILE, [])

    # Safety: ensure watchlist is a list
    if not isinstance(watchlist, list):
        watchlist = []

    today     = datetime.now().strftime("%Y-%m-%d")
    due       = [t for t in watchlist if isinstance(t, dict) and t.get("recheck_date", "9999") <= today]

    promoted_count = 0
    archived_count = 0

    if not due:
        return tool_db, watchlist, promoted_count, archived_count

    print(f"   {len(due)} tools due for recheck...")
    existing_names = get_existing_tool_names(tool_db)

    remaining = []
    for item in watchlist:
        if not isinstance(item, dict):
            continue
        if item not in due:
            remaining.append(item)
            continue

        name    = item.get("name", "")
        title   = item.get("title", name)
        desc    = item.get("description", "")
        attempt = item.get("recheck_count", 0)

        print(f"\n   📋 Rechecking: {title} (was score {item.get('score', '?')}, recheck #{attempt + 1})")

        result = score_tool(title, desc, existing_names)
        if not result:
            remaining.append(item)
            continue

        score = result.get("score", 0)
        rtype = result.get("type", "rejected")

        if rtype in ("rejected", "too_weak") or score < FULL_REVIEW_THRESHOLD:
            if attempt >= 3:
                print(f"   📦 Archived after 4 rechecks: {title} (final score {score})")
                archived_count += 1
            else:
                item["score"]         = score
                item["recheck_count"] = attempt + 1
                item["recheck_date"]  = next_recheck_date(attempt + 1)
                remaining.append(item)
        else:
            category = result.get("category") or detect_category(name, desc)
            key = tool_key(result.get("name", name))
            tool_db[key] = {
                "name":                   result.get("name", name),
                "score":                  score,
                "type":                   rtype,
                "category":               category,
                "description":            result.get("description", desc),
                "has_affiliate_potential": result.get("has_affiliate_potential", True),
                "is_fast_growing":        result.get("is_fast_growing", False),
                "source":                 item.get("source", "watchlist"),
                "discovered_date":        item.get("discovered_date", today),
                "promoted_date":          today,
                "status":                 "discovered",
            }
            label = "AFFILIATE REVIEW" if rtype == "affiliate_review" else "AUTHORITY ARTICLE"
            print(f"   🎉 PROMOTED: {title} — score {score} → {label}")
            promoted_count += 1

    save_json(WATCHLIST_FILE, remaining)
    save_json(TOOL_DB_FILE, tool_db)
    return tool_db, remaining, promoted_count, archived_count


# ─── RSS scanning ─────────────────────────────────────────────────────────────

def scan_rss_feeds(tool_db: dict, watchlist: list):
    today = datetime.now().strftime("%Y-%m-%d")
    new_affiliate = []
    new_authority = []
    existing_names = get_existing_tool_names(tool_db)

    print("\n📰 Starting RSS scan...")

    for feed_cfg in RSS_FEEDS:
        url    = feed_cfg["url"]
        source = feed_cfg["source"]
        print(f"\n📡 Scanning: {source}")

        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                print(f"   ⚠️  No entries — feed may be down")
                continue
        except Exception as e:
            print(f"   ⚠️  Feed error: {e}")
            continue

        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            desc  = entry.get("summary", entry.get("description", "")).strip()
            desc  = re.sub(r"<[^>]+>", " ", desc).strip()

            if not title:
                continue
            if quick_reject(title, desc):
                continue
            if already_known(title, tool_db, watchlist):
                continue

            print(f"   🔍 Evaluating: {title[:60]}")

            result = score_tool(title, desc, existing_names)
            if not result:
                continue

            score = result.get("score", 0)
            rtype = result.get("type", "rejected")
            name  = result.get("name", title)

            if rtype == "rejected":
                print(f"   🚫 Rejected: {result.get('reason', '')}")
                continue
            if rtype == "too_weak" or score < WATCHLIST_THRESHOLD:
                continue

            # Detect category (Claude assigns it, fallback to keyword detection)
            category = result.get("category") or detect_category(name, desc)

            if score < FULL_REVIEW_THRESHOLD:
                watchlist.append({
                    "name":            name,
                    "title":           title,
                    "description":     result.get("description", desc),
                    "score":           score,
                    "category":        category,
                    "source":          source,
                    "discovered_date": today,
                    "recheck_date":    next_recheck_date(0),
                    "recheck_count":   0,
                })
                print(f"   👀 Watchlisted: {name} (score {score}, {category})")
                continue

            key = tool_key(name)
            if key in tool_db:
                continue

            # Check for competitors
            competitors = find_competitors(name, category, tool_db)

            tool_db[key] = {
                "name":                   name,
                "score":                  score,
                "type":                   rtype,
                "category":               category,
                "description":            result.get("description", desc),
                "has_affiliate_potential": result.get("has_affiliate_potential", True),
                "is_fast_growing":        result.get("is_fast_growing", False),
                "source":                 source,
                "source_url":             entry.get("link") or entry.get("url") or entry.get("source_url", ""),
                "discovered_date":        today,
                "status":                 "discovered",
                "competitors":            competitors,
            }

            label = "AFFILIATE REVIEW" if rtype == "affiliate_review" else "AUTHORITY ARTICLE"
            fast  = "🔥" if result.get("is_fast_growing") else ""
            print(f"   ✅ {label}! Score: {score} {fast} ({category}) — {result.get('reason', '')}")
            if competitors:
                print(f"   ⚖️  Competitors: {', '.join(competitors)}")

            if rtype == "affiliate_review":
                new_affiliate.append((name, score, result.get("description", "")))
            else:
                new_authority.append((name, score, result.get("description", "")))

    save_json(TOOL_DB_FILE, tool_db)
    save_json(WATCHLIST_FILE, watchlist)
    return tool_db, watchlist, new_affiliate, new_authority


# ─── Reddit scanning ──────────────────────────────────────────────────────────

def scan_reddit(tool_db: dict, watchlist: list):
    today         = datetime.now().strftime("%Y-%m-%d")
    new_affiliate = []
    new_authority = []
    existing_names = get_existing_tool_names(tool_db)

    print("\n🤖 Starting Reddit scan...")
    print(f"   📡 Scanning {len(REDDIT_SUBREDDITS)} subreddits (public JSON API)...")

    for subreddit in REDDIT_SUBREDDITS:
        print(f"\n   📡 r/{subreddit}", end="   ")
        url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=10"

        try:
            resp = requests.get(url, headers=REDDIT_HEADERS, timeout=15)
            if resp.status_code == 404:
                print(f"⚠️  HTTP 404 — subreddit may be dead, skipping")
                continue
            if resp.status_code == 429:
                print(f"⚠️  Rate limited — waiting 30s")
                time.sleep(30)
                resp = requests.get(url, headers=REDDIT_HEADERS, timeout=15)
                if resp.status_code != 200:
                    print(f"⚠️  Still failing — skipping")
                    continue
            if resp.status_code != 200:
                print(f"⚠️  HTTP {resp.status_code} — skipping")
                continue
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
        except Exception as e:
            print(f"⚠️  Error: {e}")
            continue

        found = 0
        for post in posts:
            p     = post.get("data", {})
            title = p.get("title", "").strip()
            desc  = p.get("selftext", "").strip()[:500]

            if not title:
                continue
            if quick_reject(title, desc):
                continue

            text_lower = (title + " " + desc).lower()
            if not any(w in text_lower for w in SIGNAL_WORDS):
                continue

            if already_known(title, tool_db, watchlist):
                continue

            print(f"\n   🔍 Evaluating: {title[:60]}")

            result = score_tool(title, desc, existing_names)
            if not result:
                continue

            score = result.get("score", 0)
            rtype = result.get("type", "rejected")
            name  = result.get("name", title)

            if rtype == "rejected":
                print(f"   🚫 Rejected: {result.get('reason', '')}")
                continue
            if rtype == "too_weak" or score < WATCHLIST_THRESHOLD:
                continue

            category = result.get("category") or detect_category(name, desc)

            if score < FULL_REVIEW_THRESHOLD:
                watchlist.append({
                    "name":            name,
                    "title":           title,
                    "description":     result.get("description", desc),
                    "score":           score,
                    "category":        category,
                    "source":          f"r/{subreddit}",
                    "discovered_date": today,
                    "recheck_date":    next_recheck_date(0),
                    "recheck_count":   0,
                })
                print(f"   👀 Watchlisted: {name} (score {score}, {category})")
                found += 1
                continue

            key = tool_key(name)
            if key in tool_db:
                continue

            competitors = find_competitors(name, category, tool_db)

            tool_db[key] = {
                "name":                   name,
                "score":                  score,
                "type":                   rtype,
                "category":               category,
                "description":            result.get("description", desc),
                "has_affiliate_potential": result.get("has_affiliate_potential", True),
                "is_fast_growing":        result.get("is_fast_growing", False),
                "source":                 f"r/{subreddit}",
                "source_url":             p.get("url") or p.get("link") or p.get("source_url", ""),
                "discovered_date":        today,
                "status":                 "discovered",
                "competitors":            competitors,
            }

            label = "AFFILIATE REVIEW" if rtype == "affiliate_review" else "AUTHORITY ARTICLE"
            fast  = "🔥" if result.get("is_fast_growing") else ""
            print(f"   ✅ {label}! Score: {score} {fast} ({category})")
            if competitors:
                print(f"   ⚖️  Competitors: {', '.join(competitors)}")

            if rtype == "affiliate_review":
                new_affiliate.append((name, score, result.get("description", "")))
            else:
                new_authority.append((name, score, result.get("description", "")))
            found += 1

        if found == 0:
            print(f"— 0 found")

        time.sleep(1.5)

    save_json(TOOL_DB_FILE, tool_db)
    save_json(WATCHLIST_FILE, watchlist)
    return tool_db, watchlist, new_affiliate, new_authority


# ─── Manual tools pipeline ────────────────────────────────────────────────────

def process_manual_tools(tool_db: dict, watchlist: list):
    today    = datetime.now().strftime("%Y-%m-%d")
    manual   = load_json(MANUAL_FILE, [])

    if not isinstance(manual, list):
        return tool_db, watchlist

    pending  = [t for t in manual if isinstance(t, dict) and t.get("status") == "pending"]

    if not pending:
        return tool_db, watchlist

    print(f"\n📚 Processing {len(pending)} manual tool(s)...")
    existing_names = get_existing_tool_names(tool_db)

    for item in manual:
        if not isinstance(item, dict) or item.get("status") != "pending":
            continue

        name = item.get("name", "")
        desc = item.get("description", "")

        if already_known(name, tool_db, watchlist):
            print(f"   ⏭️  Already known: {name}")
            item["status"] = "processed"
            continue

        print(f"   🔍 Evaluating: {name}")
        result = score_tool(name, desc, existing_names)

        if not result:
            continue

        score      = result.get("score", 0)
        rtype      = result.get("type", "rejected")
        clean_name = result.get("name", name)
        category   = result.get("category") or detect_category(name, desc)

        item["status"] = "processed"

        if rtype == "rejected":
            print(f"   🚫 Rejected: {result.get('reason', '')}")
            continue
        if score < WATCHLIST_THRESHOLD:
            continue

        if score < FULL_REVIEW_THRESHOLD:
            watchlist.append({
                "name":            clean_name,
                "title":           name,
                "description":     result.get("description", desc),
                "score":           score,
                "category":        category,
                "source":          "manual",
                "discovered_date": today,
                "recheck_date":    next_recheck_date(0),
                "recheck_count":   0,
            })
            print(f"   👀 Watchlisted: {clean_name} (score {score}, {category})")
            continue

        key = tool_key(clean_name)
        competitors = find_competitors(clean_name, category, tool_db)

        tool_db[key] = {
            "name":                   clean_name,
            "score":                  score,
            "type":                   rtype,
            "category":               category,
            "description":            result.get("description", desc),
            "has_affiliate_potential": result.get("has_affiliate_potential", True),
            "is_fast_growing":        result.get("is_fast_growing", False),
            "source":                 "manual",
            "discovered_date":        today,
            "status":                 "discovered",
            "competitors":            competitors,
        }

        label = "AFFILIATE REVIEW" if rtype == "affiliate_review" else "AUTHORITY ARTICLE"
        print(f"   ✅ {label}! Score: {score} ({category})")
        if competitors:
            print(f"   ⚖️  Competitors: {', '.join(competitors)}")

    save_json(MANUAL_FILE, manual)
    save_json(TOOL_DB_FILE, tool_db)
    save_json(WATCHLIST_FILE, watchlist)
    return tool_db, watchlist


# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(rss_aff, rss_auth, red_aff, red_auth, watchlist,
                  promoted_count, archived_count, tool_db):
    all_affiliate = rss_aff + red_aff
    all_authority = rss_auth + red_auth

    # Category breakdown of database
    cat_counts = {}
    for key, data in tool_db.items():
        if isinstance(data, dict):
            cat = data.get("category", "other")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    print("\n" + "=" * 55)
    print("✅ Scan complete.")
    print(f"   📰 New from RSS:              {len(rss_aff) + len(rss_auth)}")
    print(f"   🤖 New from Reddit:           {len(red_aff) + len(red_auth)}")
    print(f"   💰 Affiliate reviews queued:  {len(all_affiliate)}")
    print(f"   🏢 Authority articles queued: {len(all_authority)}")
    print(f"   👀 Total on watchlist:        {len(watchlist)}")
    print(f"   🎉 Promoted from watchlist:   {promoted_count}")
    print(f"   📦 Archived from watchlist:   {archived_count}")
    print(f"   📊 Total tools in database:   {len(tool_db)}")

    if cat_counts:
        cat_str = ", ".join(f"{v} {k}" for k, v in sorted(cat_counts.items(), key=lambda x: -x[1]))
        print(f"   📁 Categories:               {cat_str}")

    print("=" * 55)

    if all_affiliate:
        print("\n💰 Affiliate reviews (earns commissions):")
        for name, score, desc in sorted(all_affiliate, key=lambda x: -x[1]):
            print(f"   • {name} (score: {score})")

    if all_authority:
        print("\n🏢 Authority articles (traffic + trust):")
        for name, score, desc in sorted(all_authority, key=lambda x: -x[1]):
            print(f"   • {name} (score: {score})")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    print("🔍 Tool Scout starting...")
    print(f"   📋 {len(RSS_FEEDS)} RSS sources | {len(REDDIT_SUBREDDITS)} subreddits (public JSON)")

    # Step 1 — watchlist rechecks
    print("\n🔄 Checking watchlist for due rechecks...")
    tool_db, watchlist, promoted_count, archived_count = process_watchlist()

    # Step 2 — RSS scan
    tool_db, watchlist, rss_aff, rss_auth = scan_rss_feeds(tool_db, watchlist)

    # Step 3 — Reddit scan
    tool_db, watchlist, red_aff, red_auth = scan_reddit(tool_db, watchlist)

    # Step 4 — Manual tools
    tool_db, watchlist = process_manual_tools(tool_db, watchlist)

    # Step 5 — Summary
    print_summary(rss_aff, rss_auth, red_aff, red_auth, watchlist,
                  promoted_count, archived_count, tool_db)

    # Step 6 — Discovery stats
    update_discovery_stats(rss_aff, rss_auth, red_aff, red_auth,
                          promoted_count, archived_count)

    print(f"\n💾 Saved to: {TOOL_DB_FILE}")
    print(f"📊 Stats: {STATS_FILE}")


if __name__ == "__main__":
    run()