import feedparser
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
import requests
import anthropic
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# =============================================================================
# RSS SOURCES — verified working as of March 2026
# =============================================================================
# Removed at launch: TLDR AI (news digest only), MarkTechPost (research only),
#                    Nitter Twitter feeds (instances dead/unreliable)
# Removed March 2026: SiliconAngle AI + AI Business — 2 runs, 30 evals, 0 tools.
#                     Both cover enterprise news only, never creator tool launches.
#                     Saving ~$18/month in wasted API calls.
# Active: 7 sources across Product Hunt, Hacker News, TechCrunch, VentureBeat
# =============================================================================

RSS_FEEDS = [
    # --- Tier 1: Product Hunt (best signal for new tool launches) ---
    {
        "url": "https://www.producthunt.com/feed?category=artificial-intelligence",
        "source": "Product Hunt - AI"
    },
    {
        "url": "https://www.producthunt.com/feed?category=productivity",
        "source": "Product Hunt - Productivity"
    },
    {
        "url": "https://www.producthunt.com/feed",
        "source": "Product Hunt - General"
    },

    # --- Tier 2: Hacker News (Show HN launches — 15% hit rate in live test) ---
    {
        "url": "https://hnrss.org/newest?q=AI+tool",
        "source": "Hacker News - AI Tools"
    },
    {
        "url": "https://hnrss.org/newest?q=AI+launch",
        "source": "Hacker News - AI Launches"
    },

    # --- Tier 3: Tech news (occasional product coverage) ---
    {
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "source": "TechCrunch AI"
    },
    {
        "url": "https://venturebeat.com/category/ai/feed/",
        "source": "VentureBeat AI"
    },
]

# =============================================================================
# REDDIT SUBREDDITS — 15 communities covering creators + AI tools
# Uses Reddit's FREE public JSON API — no API key or account needed.
# Just hits reddit.com/r/SUBREDDIT/new.json — always available.
# =============================================================================

SUBREDDITS = [
    # Core AI tool communities (highest signal for new tools)
    "artificial",        # Biggest AI subreddit — everything lands here first
    "AItools",           # Dedicated AI tool launches and reviews
    "ChatGPT",           # AI tools discussion — huge audience
    "MachineLearning",   # More technical but catches real tools early
    "singularity",       # AI launches + hype — early signal
    # Creator communities (our target audience posting about their problems)
    "ContentCreators",   # Content creator tools and workflows
    "Blogging",          # Blogging + writing tools
    "YoutubeCreators",   # Video creator tools
    "podcasting",        # Podcast tools — Buzzsprout, Descript territory
    "VideoEditing",      # Video creator tools
    # Business / SaaS communities (where indie devs launch)
    "SideProject",       # Indie devs launching tools — gold mine
    "indiehackers",      # Bootstrapped SaaS launches
    "Entrepreneur",      # Business tools, productivity
    "passive_income",    # Creator monetisation tools
    "SEO",               # SEO tools — Surfer territory
]

# Reddit posts that signal a TOOL rather than a discussion
REDDIT_SIGNAL_WORDS = [
    "launched", "launch", "just launched", "releasing", "released",
    "built", "i built", "i made", "we built", "we launched",
    "show hn", "introducing", "check out", "new tool", "new app",
    "beta", "free tool", "open beta", "early access",
    "ai tool", "tool for", "app for", "software for",
    "saas", "platform", "sign up", "try it", "try for free", "free plan",
]

# Reddit posts to skip immediately — waste of scoring budget
REDDIT_REJECT_WORDS = [
    "porn", "nsfw", "gambling", "casino", "crypto", "nft", "bitcoin",
    "forex", "trading bot", "meme", "funny", "rant", "vent",
    "ama", "ask me", "question:", "eli5", "explain",
    "physical", "hardware", "3d print", "pcb", "raspberry pi",
]

# Reddit public JSON API — no auth needed
# Descriptive User-Agent is required by Reddit's rules
REDDIT_HEADERS = {
    "User-Agent": "creatorsmusthave-toolscout/1.0 (creatorsmusthave.com — affiliate content site)"
}

# 1.5 seconds between subreddit requests — keeps Reddit happy
REDDIT_DELAY = 1.5

# =============================================================================
# SCORING THRESHOLDS
# Three-tier system:
#   60+   → write article now (affiliate_review or authority_article)
#   40-59 → watchlist — recheck at 48h → 5d → 14d → 30d → archive
#   0-39  → rejected permanently
# =============================================================================

FULL_REVIEW_THRESHOLD = 55
WATCHLIST_THRESHOLD = 35

MEMORY_FILE = "memory/tool_database.json"
WATCHLIST_FILE = "memory/watchlist.json"

# Recheck intervals in days
# Aggressive because Product Hunt voting peaks within 48 hours of launch
RECHECK_INTERVALS = [2, 5, 14, 30]

# =============================================================================
# MAJOR PLATFORM PRE-FILTER
# OpenAI, Anthropic, Google, Meta etc have no affiliate programs.
# A dedicated GPT-5 review earns $0 and competes with TechCrunch.
# These tools get classified as "authority_article" — valuable for traffic
# and domain trust, but the keyword agent treats them differently.
# Cap score at 70 max. Never set has_affiliate_potential: true.
# =============================================================================

MAJOR_PLATFORMS = [
    "openai", "chatgpt", "gpt-4", "gpt-5", "gpt 4", "gpt 5",
    "anthropic", "claude code", " claude ",
    "google gemini", "gemini ", "google bard",
    "meta llama", "llama ", "meta ai",
    "microsoft copilot", " copilot",
    "amazon bedrock", "aws bedrock",
    "mistral ", "cohere ",
    "stability ai",
]

def is_major_platform(title, description):
    """
    Returns True if this is a model/feature release from a major AI lab
    with no affiliate program.
    """
    combined = (title + " " + description).lower()
    return any(platform in combined for platform in MAJOR_PLATFORMS)


# =============================================================================
# MEMORY FUNCTIONS
# =============================================================================

def load_known_tools():
    """Load all previously discovered tools from memory."""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {}


def save_tool(tool):
    """Save a new tool to tool_database.json."""
    os.makedirs("memory", exist_ok=True)
    known = load_known_tools()
    slug = tool["name"].lower().replace(" ", "-").replace("/", "-")[:50]
    known[slug] = tool
    with open(MEMORY_FILE, "w") as f:
        json.dump(known, f, indent=2)
    article_label = tool["article_type"].upper().replace("_", " ")
    print(f"   💾 Saved: {tool['name']} [{article_label}]")


def load_watchlist():
    """Load all watchlisted tools."""
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return {}


def save_watchlist(watchlist):
    """Save watchlist to file."""
    os.makedirs("memory", exist_ok=True)
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f, indent=2)


def add_to_watchlist(title, description, source_name, source_url, score, reason):
    """Add a borderline tool to the watchlist for later rechecking."""
    watchlist = load_watchlist()
    slug = title.lower().replace(" ", "-").replace("/", "-")[:50]

    if slug in watchlist:
        return  # Already watching it

    recheck_date = (datetime.now() + timedelta(days=RECHECK_INTERVALS[0])).strftime("%Y-%m-%d")

    watchlist[slug] = {
        "name": title,
        "description": description,
        "source": source_name,
        "source_url": source_url,
        "initial_score": score,
        "initial_reason": reason,
        "discovered_date": datetime.now().strftime("%Y-%m-%d"),
        "recheck_date": recheck_date,
        "recheck_count": 0,
        "status": "watchlist",
        "why_watchlist": f"Score {score} — promising but limited info at launch time"
    }

    save_watchlist(watchlist)
    print(f"   👀 Watchlisted: {title[:50]} (score {score}) — recheck {recheck_date}")


# =============================================================================
# WATCHLIST RECHECK SYSTEM
# =============================================================================

def process_watchlist():
    """
    Check all watchlisted tools whose recheck_date has passed.
    Re-evaluates with Claude. Promotes if score now 60+.
    Archives after 4 rechecks (30 days total) if never crosses threshold.

    Recheck schedule: 48h → 5d → 14d → 30d → archive
    Plus: immediate recheck if tool reappears in any feed (separate trigger).
    """
    watchlist = load_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")
    promoted = []
    archived = []

    tools_to_check = {
        slug: tool for slug, tool in watchlist.items()
        if tool["status"] == "watchlist" and tool["recheck_date"] <= today
    }

    if not tools_to_check:
        print("   ✓ No watchlist rechecks due today")
        return promoted, archived

    print(f"   {len(tools_to_check)} tools due for recheck...")

    for slug, tool in tools_to_check.items():
        print(f"\n   📋 Rechecking: {tool['name']} (was score {tool['initial_score']}, recheck #{tool['recheck_count'] + 1})")

        try:
            result = score_tool_with_claude(tool["name"], tool["description"])

            if not result.get("is_creator_tool"):
                watchlist[slug]["status"] = "archived"
                watchlist[slug]["archived_reason"] = result.get("rejection_reason", "rejected on recheck")
                archived.append(tool["name"])
                print(f"   📦 Archived (rejected on recheck): {tool['name']}")
                continue

            new_score = result.get("score", 0)

            if new_score >= FULL_REVIEW_THRESHOLD:
                watchlist[slug]["status"] = "promoted"
                watchlist[slug]["promoted_date"] = today
                watchlist[slug]["final_score"] = new_score
                watchlist[slug]["recheck_count"] += 1
                save_watchlist(watchlist)

                article_type = result.get("article_type", "affiliate_review")

                promoted_tool = {
                    "name": result["name"],
                    "description": result["description"],
                    "category": result["category"],
                    "score": new_score,
                    "confidence": result.get("confidence", "medium"),
                    "article_type": article_type,
                    "fast_growing_category": result.get("fast_growing_category", False),
                    "is_major_platform": result.get("is_major_platform", False),
                    "has_affiliate_potential": result.get("has_affiliate_potential", False),
                    "source": tool["source"],
                    "source_url": tool["source_url"],
                    "discovered_date": tool["discovered_date"],
                    "promoted_from_watchlist": True,
                    "days_to_promote": (datetime.now() - datetime.strptime(tool["discovered_date"], "%Y-%m-%d")).days,
                    "status": "discovered"
                }
                save_tool(promoted_tool)
                promoted.append(tool["name"])
                print(f"   🎉 PROMOTED: {tool['name']} — new score {new_score} → {article_type}")

            else:
                recheck_count = tool["recheck_count"] + 1
                watchlist[slug]["recheck_count"] = recheck_count

                if recheck_count >= len(RECHECK_INTERVALS):
                    watchlist[slug]["status"] = "archived"
                    watchlist[slug]["archived_reason"] = f"Never crossed threshold after {recheck_count} rechecks. Final score: {new_score}"
                    archived.append(tool["name"])
                    print(f"   📦 Archived after {recheck_count} rechecks: {tool['name']} (final score {new_score})")
                else:
                    next_days = RECHECK_INTERVALS[recheck_count]
                    next_date = (datetime.now() + timedelta(days=next_days)).strftime("%Y-%m-%d")
                    watchlist[slug]["recheck_date"] = next_date
                    print(f"   ⏳ Still below threshold (score {new_score}) — next recheck {next_date}")

        except Exception as e:
            print(f"   ⚠️  Recheck failed for {tool['name']}: {e}")

    save_watchlist(watchlist)
    return promoted, archived


def check_if_watchlisted_tool_reappeared(title):
    """
    If a watchlisted tool shows up in feeds again, trigger an early recheck
    instead of waiting for the scheduled date.
    A tool appearing in TechCrunch after being watchlisted from Product Hunt
    is a strong signal — don't wait 2 weeks for scheduled recheck.
    """
    watchlist = load_watchlist()
    slug = title.lower().replace(" ", "-").replace("/", "-")[:50]

    if slug in watchlist and watchlist[slug]["status"] == "watchlist":
        today = datetime.now().strftime("%Y-%m-%d")
        if watchlist[slug]["recheck_date"] > today:
            watchlist[slug]["recheck_date"] = today
            save_watchlist(watchlist)
            print(f"   🔔 Watchlisted tool reappeared in feeds — triggering early recheck: {title[:50]}")


# =============================================================================
# CLAUDE EVALUATION
# =============================================================================

def score_tool_with_claude(title, description):
    """Send tool to Claude for scoring and categorisation."""

    # Local pre-check: catch major platforms before Claude evaluation
    major_platform = is_major_platform(title, description)

    prompt = f"""You are a quality filter for "Creators Must Have" — an affiliate website
recommending the best tools for content creators: YouTubers, bloggers, podcasters,
social media creators, writers, and online business owners.

Your job: evaluate whether this tool is worth writing about, and what type of article
it warrants.

Tool title: {title}
Description: {description}

━━━ AUTOMATIC REJECTION (set is_creator_tool: false) ━━━

Reject immediately if the tool is ANY of these:
- Related to adult content, OnlyFans, or explicit material
- Related to gambling or betting
- Pure crypto, NFT, or blockchain speculation tool
- Vaporware — no real website, no pricing, just "coming soon"
- No paid tier and zero affiliate potential
- Physical hardware (laptops, cameras, microphones, any devices)
- A news article, blog post, or newsletter — must be ACTUAL SOFTWARE
- A pure ChatGPT wrapper with zero unique value or differentiation
  (Ask: does this do anything a user couldn't do directly in ChatGPT for free?)
- Company with known fraud, scam, or deceptive billing history
- Browser extension only — no standalone web product
- Enterprise-only with "contact us for pricing" — no self-serve tier
- Open-source library or framework with no paid product attached
- Academic research paper or university project

━━━ ARTICLE TYPE — CLASSIFY BEFORE SCORING ━━━

"affiliate_review" — Independent SaaS tool that has (or likely has) its own
  affiliate/partner program. This is what earns commissions. Default for most tools.

"authority_article" — A product, model, or feature from a MAJOR AI LAB:
  OpenAI, Anthropic, Google, Meta, Microsoft, Amazon, Mistral, or Cohere.
  These companies have NO affiliate programs.
  Worth writing about ONLY for traffic and domain authority.
  Score 40-70 max. has_affiliate_potential must be false.
  Examples: GPT-5 release, Claude Code, Gemini update, Copilot feature.

━━━ SCORING GUIDE ━━━

Start at 50. Add or subtract based on these signals:

POSITIVE signals (add points):
+25  Has a visible /affiliates or /partners program page — this is the #1 money signal
+15  Directly helps creators produce content faster or better
+15  Just launched publicly — first-mover advantage means zero competition for review keywords
+10  Clear monthly/annual subscription pricing visible on the website
+8   Solves one very specific creator problem extremely well
+7   Operates in fast-growing category: AI video, AI voice, AI writing, AI avatar, AI agents
+5   Has a free trial (not just freemium — an actual time-limited trial)
+5   Has paying users, press coverage, or Product Hunt upvotes (bonus signal, not a requirement)

NEGATIVE signals (subtract points):
-20  No paid tier and no affiliate program — earns nothing, skip it
-15  Pure ChatGPT wrapper with no unique value or differentiation
-10  Category is extremely saturated with no clear differentiation from existing tools
-8   Enterprise-only with no self-serve signup — can't review what creators can't buy
-5   Pricing extremely high with no justification for the price point

MAJOR PLATFORM RULE:
If article_type is "authority_article", cap score at 70 maximum.
Set has_affiliate_potential: false always.

━━━ CATEGORY GUIDE ━━━

writing      — AI writing, copywriting, blog, email, scripts
video        — AI video creation, editing, captions, thumbnails
image        — AI image generation, design, graphics
audio        — AI voice, podcast, music, transcription
coding       — AI coding assistants (only if useful for creator workflows)
productivity — AI organisation, research, scheduling, automation
seo          — AI SEO, keyword research, content optimisation
other        — anything that doesn't fit above

━━━ OUTPUT FORMAT ━━━

Respond in JSON only. No extra text. No markdown. No code fences. Raw JSON only:
{{
  "name": "clean tool name without taglines",
  "description": "one sentence — what it does specifically for creators",
  "category": "writing|video|image|audio|coding|productivity|seo|other",
  "is_creator_tool": true or false,
  "is_major_platform": true or false,
  "has_affiliate_potential": true or false,
  "score": 0-100,
  "confidence": "high|medium|low",
  "article_type": "affiliate_review|authority_article|reject",
  "fast_growing_category": true or false,
  "reason": "one sentence explaining the score",
  "rejection_reason": "only fill this if rejected, empty string otherwise"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if Claude adds them despite instructions
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    result = json.loads(raw.strip())

    # Safety override: our local check trumps Claude's classification
    # Prevents Claude from accidentally giving an affiliate_review type
    # to OpenAI/Anthropic/Google products
    if major_platform:
        result["is_major_platform"] = True
        result["has_affiliate_potential"] = False
        result["article_type"] = "authority_article"
        if result.get("score", 0) > 70:
            result["score"] = 70

    return result


# =============================================================================
# TOOL PROCESSING — shared by RSS, Reddit, and manual pipeline
# =============================================================================

def process_entry(title, description, source_name, source_url):
    """
    Evaluate a single entry using the three-tier system.
    Shared by scan_rss_feeds(), scan_reddit(), and process_manual_tools().

      60+   → save to tool_database.json
              affiliate_review  = earns commissions (default)
              authority_article = traffic + domain authority only (major platforms)
      40-59 → save to watchlist.json, recheck on schedule
      0-39  → permanent rejection
    """

    if not title or len(title.strip()) < 3:
        return None

    # Check if already fully discovered
    known = load_known_tools()
    slug = title.lower().replace(" ", "-").replace("/", "-")[:50]

    if slug in known:
        print(f"   ⏭️  Already known: {title[:55]}")
        return None

    # Check if tool reappeared while on watchlist — triggers early recheck
    check_if_watchlisted_tool_reappeared(title)

    # Check if already on watchlist and not yet due for recheck
    watchlist = load_watchlist()
    if slug in watchlist and watchlist[slug]["status"] == "watchlist":
        print(f"   👀 On watchlist: {title[:55]} (next recheck: {watchlist[slug]['recheck_date']})")
        return None

    print(f"   🔍 Evaluating: {title[:60]}")

    try:
        result = score_tool_with_claude(title, description)

        # Hard rejection
        if not result.get("is_creator_tool"):
            reason = result.get("rejection_reason") or "not relevant to creators"
            print(f"   🚫 Rejected: {reason}")
            return None

        score = result.get("score", 0)
        article_type = result.get("article_type", "affiliate_review")
        is_major = result.get("is_major_platform", False)

        # Score 60+ → queue for article
        if score >= FULL_REVIEW_THRESHOLD:
            confidence = result.get("confidence", "medium")
            fast_growing = result.get("fast_growing_category", False)

            extras = []
            if fast_growing:
                extras.append("🔥 fast-growing")
            if is_major:
                extras.append("🏢 authority only — no affiliate")
            if confidence == "low":
                extras.append("⚠️  low confidence")
            extra_str = f" ({', '.join(extras)})" if extras else ""

            type_label = "Affiliate review" if article_type == "affiliate_review" else "Authority article"
            print(f"   ✅ {type_label}! Score: {score}{extra_str} — {result.get('reason')}")

            tool = {
                "name": result["name"],
                "description": result["description"],
                "category": result["category"],
                "score": score,
                "confidence": confidence,
                "article_type": article_type,
                "fast_growing_category": fast_growing,
                "is_major_platform": is_major,
                "has_affiliate_potential": result.get("has_affiliate_potential", False),
                "source": source_name,
                "source_url": source_url,
                "discovered_date": datetime.now().strftime("%Y-%m-%d"),
                "status": "discovered"
            }

            save_tool(tool)
            return tool

        # Score 40-59 → watchlist
        elif score >= WATCHLIST_THRESHOLD:
            add_to_watchlist(
                title, description, source_name, source_url,
                score, result.get("reason", "")
            )
            return None

        # Score below 40 → permanent rejection
        else:
            print(f"   ⏭️  Too weak: {score} — {result.get('reason')}")
            return None

    except json.JSONDecodeError as e:
        print(f"   ⚠️  JSON parse failed for '{title[:40]}': {e}")
        return None
    except Exception as e:
        print(f"   ⚠️  Eval failed for '{title[:40]}': {e}")
        return None


# =============================================================================
# RSS SCANNING
# =============================================================================

def scan_rss_feeds():
    """Scan all RSS feeds and process new tools found."""
    new_tools = []

    for feed in RSS_FEEDS:
        feed_url = feed["url"]
        feed_name = feed["source"]
        print(f"\n📡 Scanning: {feed_name}")

        try:
            feed_data = feedparser.parse(feed_url)

            if not feed_data.entries:
                print(f"   ⚠️  No entries — feed may be down or URL changed")
                continue

            for entry in feed_data.entries[:15]:
                title = entry.get("title", "").strip()
                description = entry.get("summary", entry.get("description", ""))
                # Strip HTML tags before sending to Claude
                description = re.sub(r'<[^>]+>', '', description)[:600]
                source_url = entry.get("link", "")

                tool = process_entry(title, description, feed_name, source_url)
                if tool:
                    new_tools.append(tool)

        except Exception as e:
            print(f"   ⚠️  Feed scan failed: {feed_name} — {e}")

    return new_tools


# =============================================================================
# REDDIT SCANNING — free public JSON API, no credentials needed
# =============================================================================

def _is_tool_post(post: dict) -> bool:
    """
    Quick pre-filter before paying Claude to evaluate.
    Returns True if this Reddit post looks like it's about a tool.

    Three ways to pass:
      1. Title/body contains a launch or tool signal word
      2. It's a link post pointing to a non-social-media domain
         (indie dev sharing their product URL directly)
      3. Neither → skip — not worth the API call

    Hard-rejects spam/off-topic content first.
    """
    title    = (post.get("title", "") or "").lower()
    body     = (post.get("selftext", "") or "").lower()
    combined = title + " " + body

    # Fast exit on spam keywords
    for word in REDDIT_REJECT_WORDS:
        if word in combined:
            return False

    # Positive signal in text
    for word in REDDIT_SIGNAL_WORDS:
        if word in combined:
            return True

    # Link post pointing somewhere real (not YouTube/Twitter/Google)
    if not post.get("is_self", True):
        url = post.get("url", "")
        noise = ["reddit.com", "youtube.com", "twitter.com",
                 "x.com", "google.com", "amazon.com", "imgur.com",
                 "tiktok.com", "instagram.com", "facebook.com"]
        if not any(d in url for d in noise):
            return True

    return False


def _fetch_subreddit_posts(subreddit: str, limit: int = 25) -> list:
    """
    Fetch newest posts from one subreddit using Reddit's public JSON endpoint.
    No API key, no OAuth — just a regular HTTPS request.

    Reddit requires a descriptive User-Agent (our REDDIT_HEADERS constant).
    Returns list of post dicts, or empty list on any failure.
    """
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
    try:
        r = requests.get(url, headers=REDDIT_HEADERS, timeout=15)

        # 429 = rate limited — wait and retry once
        if r.status_code == 429:
            print(f"   ⚠️  Reddit rate limit on r/{subreddit} — waiting 30s")
            time.sleep(30)
            r = requests.get(url, headers=REDDIT_HEADERS, timeout=15)

        if r.status_code != 200:
            print(f"   ⚠️  r/{subreddit} returned HTTP {r.status_code} — skipping")
            return []

        posts = r.json().get("data", {}).get("children", [])
        return [p["data"] for p in posts]

    except Exception as e:
        print(f"   ⚠️  r/{subreddit} request failed: {e}")
        return []


def scan_reddit() -> list:
    """
    Scan all subreddits for new tool posts.
    Uses Reddit's FREE public JSON API — no credentials required.

    Called from run() alongside scan_rss_feeds().
    All posts go through the same process_entry() → score_tool_with_claude()
    pipeline as RSS items.

    One extra feature vs RSS: engagement bonus.
    Reddit upvotes = real humans voting on something useful.
    We add up to +10 points based on upvotes (capped to avoid gaming).
    This is applied BEFORE Claude scores — it adjusts the description we send.

    Returns list of newly discovered tools (same format as scan_rss_feeds).
    """
    print(f"\n📡 Reddit Scout — scanning {len(SUBREDDITS)} subreddits (public JSON API)...")
    new_tools = []

    # Build set of already-known tool names to skip duplicates without
    # burning an API call on something we already have
    known = load_known_tools()
    watchlist = load_watchlist()
    known_slugs = set(known.keys()) | set(watchlist.keys())

    for subreddit in SUBREDDITS:
        print(f"\n   📡 r/{subreddit}", end=" ", flush=True)
        posts = _fetch_subreddit_posts(subreddit)

        if not posts:
            print("— no response")
            time.sleep(REDDIT_DELAY)
            continue

        found_this_sub = 0

        for post in posts:
            # Fast pre-filter before paying Claude
            if not _is_tool_post(post):
                continue

            title    = (post.get("title", "") or "").strip()[:80]
            body     = (post.get("selftext", "") or "").strip()[:500]
            url      = post.get("url", "")
            upvotes  = post.get("score", 0)
            comments = post.get("num_comments", 0)
            permalink = "https://reddit.com" + post.get("permalink", "")

            if not title:
                continue

            # Skip already-known tools using slug matching
            # (avoids re-scoring "Notion" every time someone posts about it)
            slug = title.lower().replace(" ", "-").replace("/", "-")[:50]
            if slug in known_slugs:
                continue

            # Also skip if title words match known tool names
            # e.g. "Descript just added a new feature" → already have Descript
            title_words = [w for w in title.lower().split() if len(w) > 4]
            already_known = any(
                any(w in known_key for known_key in known_slugs)
                for w in title_words
            )
            if already_known:
                continue

            # Add engagement context to description so Claude can see it
            # High upvotes = real human interest = stronger signal
            engagement_note = ""
            if upvotes >= 100:
                engagement_note = f" [Reddit: {upvotes} upvotes, {comments} comments — high engagement]"
            elif upvotes >= 20:
                engagement_note = f" [Reddit: {upvotes} upvotes]"

            description = f"{body}{engagement_note}".strip()
            source_name = f"Reddit r/{subreddit}"

            # Use post URL if it's a link post (points to the actual tool),
            # otherwise use the Reddit permalink
            if url and "reddit.com" not in url:
                source_url = url   # link post — the tool's actual website
            else:
                source_url = permalink   # text post — Reddit discussion

            tool = process_entry(title, description, source_name, source_url)
            if tool:
                # Tag the tool with Reddit metadata for the summary
                tool["reddit_upvotes"] = upvotes
                tool["reddit_comments"] = comments
                tool["reddit_url"] = permalink
                new_tools.append(tool)
                found_this_sub += 1
                known_slugs.add(slug)   # prevent duplicate in same run

        print(f"— {found_this_sub} tool(s) found")
        time.sleep(REDDIT_DELAY)   # be polite to Reddit's servers

    return new_tools


# =============================================================================
# MANUAL TOOLS PIPELINE
# =============================================================================

def process_manual_tools():
    """
    Processes tools from memory/manual_tools.json through the same
    scoring pipeline as RSS-discovered tools.
    Each tool is only processed once — status changes from "pending" to "processed".
    This lets us write about established tools with affiliate programs,
    not just brand new launches.
    """
    manual_file = "memory/manual_tools.json"
    if not os.path.exists(manual_file):
        return

    tools = json.load(open(manual_file))
    pending = [t for t in tools if t.get("status") == "pending"]

    if not pending:
        return

    print(f"\n📚 Processing {len(pending)} manual tool(s)...")

    for tool in pending:
        name        = tool.get("name", "")
        description = tool.get("description", "")
        website     = tool.get("website", "")
        source_url  = f"https://{website}" if website else ""

        print(f"   🔍 Manual tool: {name}")
        process_entry(name, description, "Manual List", source_url)

        # Mark as processed so it never runs again
        tool["status"] = "processed"

    # Save updated statuses back to file
    json.dump(tools, open(manual_file, "w"), indent=2)
    print(f"   ✅ Manual tools processed")


# =============================================================================
# MAIN — standalone run
# =============================================================================

if __name__ == "__main__":
    print("🔍 Tool Scout starting...\n")
    print(f"📋 {len(RSS_FEEDS)} RSS sources | {len(SUBREDDITS)} subreddits (public JSON)\n")

    # --- Watchlist recheck first (runs every scan) ---
    print("🔄 Checking watchlist for due rechecks...")
    promoted, archived = process_watchlist()

    # --- RSS scan ---
    print("\n📰 Starting RSS scan...")
    rss_tools = scan_rss_feeds()

    # --- Reddit scan ---
    print("\n🤖 Starting Reddit scan...")
    try:
        reddit_tools = scan_reddit()
    except Exception as e:
        print(f"⚠️  Reddit scan crashed: {e}")
        reddit_tools = []

    # --- Manual tools ---
    process_manual_tools()

    # --- Summary ---
    all_new = rss_tools + reddit_tools
    affiliate_reviews  = [t for t in all_new if t.get("article_type") == "affiliate_review"]
    authority_articles = [t for t in all_new if t.get("article_type") == "authority_article"]
    fast_growing_new   = [t for t in all_new if t.get("fast_growing_category")]

    watchlist = load_watchlist()
    watching = sum(1 for t in watchlist.values() if t["status"] == "watchlist")

    rss_count    = len(rss_tools)
    reddit_count = len(reddit_tools)

    print(f"\n{'='*55}")
    print(f"✅ Scan complete.")
    print(f"   📰 New from RSS:               {rss_count}")
    print(f"   🤖 New from Reddit:            {reddit_count}")
    print(f"   💰 Affiliate reviews queued:  {len(affiliate_reviews)}")
    print(f"   🏢 Authority articles queued: {len(authority_articles)}")
    print(f"   🔥 Fast-growing (new today):  {len(fast_growing_new)}")
    print(f"   👀 Total on watchlist:        {watching}")
    print(f"   🎉 Promoted from watchlist:   {len(promoted)}")
    print(f"   📦 Archived from watchlist:   {len(archived)}")
    print(f"{'='*55}")

    if affiliate_reviews:
        print("\n💰 Affiliate reviews (earns commissions):")
        for t in sorted(affiliate_reviews, key=lambda x: x["score"], reverse=True)[:5]:
            flag  = " 🔥" if t.get("fast_growing_category") else ""
            conf  = " ⚠️"  if t.get("confidence") == "low" else ""
            reddit_note = f" [{t['reddit_upvotes']}↑ r/{t.get('source','').replace('Reddit r/','')}]" if t.get("reddit_upvotes") else ""
            print(f"   • {t['name']} (score: {t['score']}){flag}{conf}{reddit_note}")
            print(f"     {t['description']}")

    if authority_articles:
        print("\n🏢 Authority articles (traffic + domain trust, no commission):")
        for t in sorted(authority_articles, key=lambda x: x["score"], reverse=True)[:5]:
            print(f"   • {t['name']} (score: {t['score']})")
            print(f"     {t['description']}")

    if promoted:
        print("\n🎉 Promoted from watchlist today:")
        for name in promoted:
            print(f"   • {name}")

    print(f"\n💾 Saved to: {MEMORY_FILE}")
    print(f"👀 Watchlist: {WATCHLIST_FILE}")


# =============================================================================
# run() — called by scheduler.py
# =============================================================================

def run():
    """Master run function — called by scheduler.py every 6 hours."""
    scan_rss_feeds()
    scan_reddit()
    process_watchlist()
    process_manual_tools()