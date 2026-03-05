import feedparser
import json
import os
import re
from datetime import datetime, timezone, timedelta
import anthropic
from config import ANTHROPIC_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

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

# REMOVED FEEDS (kept for reference):
# SiliconAngle AI  — removed March 2026 after 2 runs, 30 evals, 0 tools found
#                    100% news articles and enterprise content, never creator tools
# AI Business      — removed March 2026 after 2 runs, 30 evals, 0 useful tools
#                    same pattern — enterprise/news only, duplicates TechCrunch catches

# =============================================================================
# REDDIT SUBREDDITS — 15 communities covering creators + AI tools
# Active when Reddit API credentials are set in config.py
# =============================================================================

SUBREDDITS = [
    # Core AI tool communities
    "artificial", "AItools", "MachineLearning", "ChatGPT", "OpenAI",
    # Specific tool communities
    "midjourney", "StableDiffusion",
    # Creator communities
    "ContentCreators", "Blogging", "YoutubeCreators", "podcasting",
    # Business / SaaS
    "SaaS", "Entrepreneur", "passive_income", "SEO",
]

# =============================================================================
# SCORING THRESHOLDS
# Three-tier system:
#   60+   → write article now (affiliate_review or authority_article)
#   40-59 → watchlist — recheck at 48h → 5d → 14d → 30d → archive
#   0-39  → rejected permanently
# =============================================================================

FULL_REVIEW_THRESHOLD = 60
WATCHLIST_THRESHOLD = 40

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
+20  Established SaaS with clear monthly/annual subscription pricing
+15  Directly helps creators produce content faster or better
+10  Has a visible /affiliates or /partners program page
+10  Has launched publicly with real paying users
+8   Has 1000+ users, Product Hunt upvotes, or App Store reviews
+7   Operates in fast-growing category: AI video, AI voice, AI agents, AI avatar
+5   Has a free trial (not just freemium — an actual time-limited trial)
+5   Has positive reviews or press coverage from credible sources
+5   Solves one very specific creator problem extremely well

NEGATIVE signals (subtract points):
-15  Is a ChatGPT wrapper but specific enough use case to not auto-reject
-10  Just launched — very limited information available to verify claims
-10  Free tier only with no clear path to paid upgrade
-8   Category is extremely saturated (basic AI writing assistants, chatbots)
-5   No social proof — no reviews, no users mentioned, no press
-5   Pricing seems very high with no clear justification

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
# TOOL PROCESSING
# =============================================================================

def process_entry(title, description, source_name, source_url):
    """
    Evaluate a single feed entry using the three-tier system:
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
# REDDIT SCANNING
# =============================================================================

def scan_reddit():
    """Scan Reddit subreddits for new tool launches."""
    import requests as req
    new_tools = []

    # Skip gracefully if credentials not set yet
    if not REDDIT_CLIENT_ID or REDDIT_CLIENT_ID in ("pending", "", None):
        print("⚠️  Reddit credentials not set — skipping Reddit scan")
        return []

    auth = req.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
    data = {"grant_type": "client_credentials"}
    headers = {"User-Agent": REDDIT_USER_AGENT}

    try:
        token_response = req.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth, data=data, headers=headers, timeout=10
        )
        token = token_response.json().get("access_token")

        if not token:
            print("⚠️  Reddit auth failed — check REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
            return []

        headers["Authorization"] = f"bearer {token}"
        print("✅ Reddit authenticated")

        for subreddit in SUBREDDITS:
            print(f"\n📡 Scanning: r/{subreddit}")
            try:
                response = req.get(
                    f"https://oauth.reddit.com/r/{subreddit}/new",
                    headers=headers,
                    params={"limit": 10},
                    timeout=10
                )
                posts = response.json().get("data", {}).get("children", [])

                for post in posts:
                    post_data = post.get("data", {})
                    title = post_data.get("title", "").strip()
                    description = post_data.get("selftext", "")[:500]
                    source_url = f"https://reddit.com{post_data.get('permalink', '')}"

                    tool = process_entry(title, description, f"Reddit r/{subreddit}", source_url)
                    if tool:
                        new_tools.append(tool)

            except Exception as e:
                print(f"   ⚠️  r/{subreddit} failed: {e}")

    except Exception as e:
        print(f"⚠️  Reddit scan failed: {e}")

    return new_tools


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("🔍 Tool Scout starting...\n")
    print(f"📋 {len(RSS_FEEDS)} RSS sources | {len(SUBREDDITS)} subreddits\n")

    # --- Watchlist recheck first (runs every scan) ---
    print("🔄 Checking watchlist for due rechecks...")
    promoted, archived = process_watchlist()

    # --- RSS scan ---
    rss_tools = scan_rss_feeds()

    # --- Reddit scan ---
    print("\n🤖 Starting Reddit scan...")
    try:
        reddit_tools = scan_reddit()
    except Exception as e:
        print(f"⚠️  Reddit scan crashed: {e}")
        reddit_tools = []

    # --- Summary ---
    all_new = rss_tools + reddit_tools
    affiliate_reviews = [t for t in all_new if t["article_type"] == "affiliate_review"]
    authority_articles = [t for t in all_new if t["article_type"] == "authority_article"]
    fast_growing_new = [t for t in all_new if t.get("fast_growing_category")]

    watchlist = load_watchlist()
    watching = sum(1 for t in watchlist.values() if t["status"] == "watchlist")

    print(f"\n{'='*55}")
    print(f"✅ Scan complete.")
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
            flag = " 🔥" if t.get("fast_growing_category") else ""
            conf = " ⚠️" if t.get("confidence") == "low" else ""
            print(f"   • {t['name']} (score: {t['score']}){flag}{conf}")
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

    import json as _json
    tools = _json.load(open(manual_file))
    pending = [t for t in tools if t.get("status") == "pending"]

    if not pending:
        return

    print(f"\n📚 Processing {len(pending)} manual tool(s)...")

    for tool in pending:
        name = tool.get("name", "")
        description = tool.get("description", "")
        website = tool.get("website", "")
        source_url = f"https://{website}" if website else ""

        print(f"   🔍 Manual tool: {name}")
        process_entry(name, description, "Manual List", source_url)

        # Mark as processed so it never runs again
        tool["status"] = "processed"

    # Save updated statuses back to file
    _json.dump(tools, open(manual_file, "w"), indent=2)
    print(f"   ✅ Manual tools processed")

def run():
    """Master run function — called by scheduler.py"""
    scan_rss_feeds()
    process_watchlist()
    process_manual_tools()
