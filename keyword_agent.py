# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
"""
keyword_agent.py — SEO Keyword Research Agent for CXRXVX Affiliates
=====================================================================
Phase 2.5 Opus Upgrade:
  ✅ Content types aligned with article_agent: review, roundup, comparison, alert, authority_article
  ✅ Roundup generation — detects when 5+ tools exist in same category, generates "Best X for Y"
  ✅ Comparison pairing — finds competing tools and generates "X vs Y" keyword packages
  ✅ Outputs roundup_tools and comparison_tools fields for article_agent
  ✅ Tracks existing roundups/comparisons to prevent duplicates
  ✅ Ratio enforcement: ~1 roundup per 5 reviews, ~1 comparison per 3-4 tools with competitors
  ✅ All existing features preserved (clusters, audiences, slug dedup, physical detection)

Drop this file into your cxrxvx-ai-empire/ folder to replace the old keyword_agent.py.
"""

import json
import os
import re
from datetime import datetime
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SITE_NAME

client = Anthropic(api_key=ANTHROPIC_API_KEY)

CURRENT_YEAR = datetime.now().year

TOOL_DATABASE = "memory/tool_database.json"
KEYWORD_DATA = "memory/keyword_data.json"
TOPICS_USED = "memory/topics_used.json"
LOGS_DIR = "memory/logs/keyword_agent"

MIN_SCORE_THRESHOLD = 60
DAILY_CAP = 8

# ── Roundup/comparison generation ratios ──
# Generate 1 roundup when this many single reviews exist in a category
ROUNDUP_TRIGGER_COUNT = 5
# Generate 1 comparison when a tool has a direct competitor also in our database
MIN_TOOLS_FOR_COMPARISON = 2

# ═══════════════════════════════════════════════════════
# PHYSICAL PRODUCT DETECTION (unchanged — works well)
# ═══════════════════════════════════════════════════════

PHYSICAL_NAME_SIGNALS = [
    "macbook", "iphone", "ipad", "pixel phone", "galaxy phone",
    "airpods", "homepod", "apple watch", "gaming console"
]
PHYSICAL_DESC_SIGNALS = [
    "physical device", "hardware device", "buy now ships",
    "ships in", "order online", "add to cart", "in the box",
    "unboxing", "plug in", "usb device", "hdmi", "bluetooth speaker"
]
SOFTWARE_OVERRIDE_SIGNALS = [
    "app", "software", "subscription", "saas", "platform", "tool",
    "dashboard", "browser", "extension", "api", "plugin", "web-based",
    "cloud", "download", "install", "free trial", "pricing plan"
]

def is_physical_product(tool):
    name_lower = tool.get("name", "").lower()
    desc_lower = tool.get("description", "").lower()
    for signal in PHYSICAL_NAME_SIGNALS:
        if signal in name_lower:
            return True
    for signal in SOFTWARE_OVERRIDE_SIGNALS:
        if signal in desc_lower:
            return False
    for signal in PHYSICAL_DESC_SIGNALS:
        if signal in desc_lower:
            return True
    return False


# ═══════════════════════════════════════════════════════
# ARTICLE TYPE MAPPING — aligned with article_agent.py
# ═══════════════════════════════════════════════════════

# Scout article types → keyword agent article types
ARTICLE_TYPE_MAP = {
    "affiliate_review":  "review",
    "full_review":       "review",
    "authority_article": "authority_article",
    "new_tool_alert":    "alert",
    "comparison":        "comparison",
    "listicle":          "roundup",
    "tutorial":          "review",
}

# ── Title templates per article type (aligned with article_agent) ──

TITLE_TEMPLATES = {
    "review": [
        f"[Tool] Review: Is It Worth It for [Audience]? ({CURRENT_YEAR})",
        "I Tested [Tool] for 30 Days — Here's What [Audience] Need to Know",
        f"The Honest [Tool] Review for [Audience] (Tested {CURRENT_YEAR})",
        "Is [Tool] Worth It for [Audience]? I Found Out",
        "[Tool] Review: What [Audience] Actually Get for Their Money",
        "[Number] Things [Audience] Should Know Before Buying [Tool]",
        "[Tool] Pricing Explained: What [Audience] Actually Pay",
        "[Tool] for [Audience]: [Specific Outcome] Without [Pain Point]",
    ],
    "roundup": [
        f"Best [Category] Tools for [Audience] in {CURRENT_YEAR} (Tested & Ranked)",
        "[Number] Best [Category] Tools for [Audience] — Honest Picks",
        f"Best Free [Category] Tools for [Audience] ({CURRENT_YEAR})",
        "Best [Category] Tools Under $[Price] for [Audience]",
    ],
    "comparison": [
        f"[Tool A] vs [Tool B]: Which Is Better for [Audience]? ({CURRENT_YEAR})",
        "[Tool A] vs [Tool B] — Honest Comparison for [Audience]",
        "[Tool A] or [Tool B]? The Real Difference for [Audience]",
    ],
    "alert": [
        f"[Tool] Just Launched — First Look for [Audience] ({CURRENT_YEAR})",
        "[Tool] Review: Is This New Tool Worth It for [Audience]?",
    ],
    "authority_article": [
        f"The Complete Guide to [Topic] for [Audience] ({CURRENT_YEAR})",
        "[Topic] for Beginners: Everything [Audience] Need to Know",
        "How [Topic] Works: A Plain-English Guide for [Audience]",
    ],
}

# Category-specific audience context
CATEGORY_AUDIENCE = {
    "video":        "YouTubers, TikTok creators, Instagram Reels creators, video editors",
    "audio":        "podcasters, voiceover artists, musicians, audio creators",
    "writing":      "bloggers, copywriters, content writers, email marketers",
    "image":        "graphic designers, social media managers, visual content creators",
    "productivity": "freelancers, solopreneurs, remote workers, content creators",
    "coding":       "developer-creators, technical bloggers, no-code builders",
    "seo":          "bloggers, affiliate marketers, SEO specialists, content strategists",
    "email":        "newsletter creators, email marketers, community builders",
    "courses":      "course creators, coaches, online educators",
    "other":        "content creators, online entrepreneurs, digital marketers",
}

# ── Known competitor pairs for comparison articles ──
# Add pairs as you discover them. Format: (tool_a, tool_b)
KNOWN_COMPETITORS = [
    ("jasper ai", "copy.ai"),
    ("jasper ai", "writesonic"),
    ("descript", "riverside"),
    ("descript", "opus clip"),
    ("elevenlabs", "murf ai"),
    ("elevenlabs", "speechify"),
    ("canva", "midjourney"),
    ("convertkit", "beehiiv"),
    ("convertkit", "substack"),
    ("beehiiv", "substack"),
    ("kajabi", "teachable"),
    ("surfer seo", "jasper ai"),
    ("pictory", "opus clip"),
    ("loom", "synthesia"),
    ("heygen", "synthesia"),
    ("later", "metricool"),
]


# ═══════════════════════════════════════════════════════
# FILE HELPERS
# ═══════════════════════════════════════════════════════

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
    os.makedirs(LOGS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    with open(f"{LOGS_DIR}/{today}.md", "a") as f:
        f.write(entry + "\n")

def is_duplicate_slug(slug, existing_keyword_data):
    for key, data in existing_keyword_data.items():
        if data.get("url_slug") == slug:
            return data.get("tool_name", key)
    return None

def build_slug_index(keyword_data):
    index = {}
    for tool_key, data in keyword_data.items():
        slug = data.get("url_slug")
        if slug:
            index[slug] = tool_key
    return index


def is_duplicate_primary_keyword(keyword, existing_keyword_data):
    """
    Phase 2.7A — Cannibalization guard.

    Check if a primary keyword is already targeted (exactly or near-exactly)
    by an existing keyword package. Returns the conflicting tool name/key, or
    None if the keyword is safe to use.

    Checks:
    1. Exact match after normalisation (lowercase, stripped)
    2. Substring match — one keyword fully contains the other
       e.g. "best AI podcast tools" vs "best AI podcast tools for beginners"
       catches the highest-risk cannibalization cases without false positives
       from unrelated short words.
    """
    keyword_norm = keyword.lower().strip()
    for key, data in existing_keyword_data.items():
        if not isinstance(data, dict):
            continue
        existing_kw = data.get("primary_keyword", "").lower().strip()
        if not existing_kw:
            continue
        if keyword_norm == existing_kw:
            return data.get("tool_name", key)
        # Only flag substring match when the shorter string is at least 4 words
        # (avoids false positives from very short generic phrases)
        shorter = keyword_norm if len(keyword_norm) <= len(existing_kw) else existing_kw
        if len(shorter.split()) >= 4:
            if keyword_norm in existing_kw or existing_kw in keyword_norm:
                return data.get("tool_name", key)
    return None


# ═══════════════════════════════════════════════════════
# ROUNDUP DETECTION — when to generate "Best X for Y" articles
# ═══════════════════════════════════════════════════════

def find_roundup_opportunities(keyword_data, tool_database):
    """
    Detect categories with enough reviewed tools to generate a roundup.
    
    Rules:
    - Need 5+ tools in the same category with keyword packages
    - No roundup already exists for that category
    - Returns list of {category, tools, audience}
    """
    # Count tools per category that have keyword packages
    category_tools = {}
    for key, data in keyword_data.items():
        if not isinstance(data, dict):
            continue
        category = data.get("tool_category", "other")
        tool_name = data.get("tool_name", "")
        if tool_name and data.get("status") in ("pending_article", "article_written", "published"):
            if category not in category_tools:
                category_tools[category] = []
            category_tools[category].append({
                "name": tool_name,
                "score": data.get("tool_score", 0),
                "slug": data.get("url_slug", ""),
            })

    # Also check tool_database for tools not yet keyworded
    for key, tool in tool_database.items():
        if not isinstance(tool, dict):
            continue
        category = tool.get("category", "other")
        tool_name = tool.get("name", "")
        score = tool.get("score", 0)
        if score >= MIN_SCORE_THRESHOLD and tool_name:
            existing_names = [t["name"].lower() for t in category_tools.get(category, [])]
            if tool_name.lower() not in existing_names:
                if category not in category_tools:
                    category_tools[category] = []
                category_tools[category].append({
                    "name": tool_name,
                    "score": score,
                    "slug": "",
                })

    # Check which categories already have roundups
    existing_roundup_categories = set()
    for key, data in keyword_data.items():
        if isinstance(data, dict) and data.get("article_type") == "roundup":
            cat = data.get("tool_category", "")
            if cat:
                existing_roundup_categories.add(cat)

    # Find categories ready for a roundup
    opportunities = []
    for category, tools in category_tools.items():
        if len(tools) >= ROUNDUP_TRIGGER_COUNT and category not in existing_roundup_categories:
            # Sort by score, take top 8
            tools.sort(key=lambda x: x.get("score", 0), reverse=True)
            top_tools = tools[:8]
            audience = CATEGORY_AUDIENCE.get(category, CATEGORY_AUDIENCE["other"])
            opportunities.append({
                "category": category,
                "tools": top_tools,
                "tool_count": len(tools),
                "audience": audience,
            })

    return opportunities


# ═══════════════════════════════════════════════════════
# COMPARISON DETECTION — find competing tool pairs
# ═══════════════════════════════════════════════════════

def find_comparison_opportunities(keyword_data, tool_database):
    """
    Find tool pairs that should have comparison articles.
    
    Sources:
    1. KNOWN_COMPETITORS list (manually curated)
    2. Tools in the same category with similar scores (auto-detected)
    
    Rules:
    - Both tools must be in our database (score 60+)
    - No comparison article already exists for this pair
    - Returns list of {tool_a, tool_b, category, reason}
    """
    # Get all known tools
    all_tools = {}
    for key, tool in tool_database.items():
        if not isinstance(tool, dict):
            continue
        name = tool.get("name", "").lower()
        if name and tool.get("score", 0) >= MIN_SCORE_THRESHOLD:
            all_tools[name] = {
                "name": tool.get("name", ""),
                "category": tool.get("category", "other"),
                "score": tool.get("score", 0),
            }

    # Check which comparisons already exist
    existing_comparisons = set()
    for key, data in keyword_data.items():
        if isinstance(data, dict) and data.get("article_type") == "comparison":
            comp = data.get("comparison_tools", {})
            a = comp.get("tool_a", "").lower()
            b = comp.get("tool_b", "").lower()
            if a and b:
                existing_comparisons.add(frozenset([a, b]))

    opportunities = []

    # Source 1: Known competitor pairs
    for tool_a_name, tool_b_name in KNOWN_COMPETITORS:
        pair = frozenset([tool_a_name, tool_b_name])
        if pair in existing_comparisons:
            continue
        # Both must be in our database
        if tool_a_name in all_tools and tool_b_name in all_tools:
            opportunities.append({
                "tool_a": all_tools[tool_a_name]["name"],
                "tool_b": all_tools[tool_b_name]["name"],
                "category": all_tools[tool_a_name]["category"],
                "reason": "known competitors",
            })

    # Source 2: Same category, similar scores (auto-detected)
    by_category = {}
    for name, info in all_tools.items():
        cat = info["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(info)

    for cat, tools in by_category.items():
        if len(tools) < 2:
            continue
        tools.sort(key=lambda x: x["score"], reverse=True)
        # Pair top tool with #2, #2 with #3 (natural competitors)
        for i in range(min(len(tools) - 1, 3)):
            a = tools[i]
            b = tools[i + 1]
            pair = frozenset([a["name"].lower(), b["name"].lower()])
            if pair in existing_comparisons:
                continue
            # Skip if already in opportunities from known competitors
            if any(frozenset([o["tool_a"].lower(), o["tool_b"].lower()]) == pair for o in opportunities):
                continue
            # Only pair tools with similar enough scores (within 20 points)
            if abs(a["score"] - b["score"]) <= 20:
                opportunities.append({
                    "tool_a": a["name"],
                    "tool_b": b["name"],
                    "category": cat,
                    "reason": "same category, similar scores",
                })

    return opportunities


# ═══════════════════════════════════════════════════════
# KEYWORD RESEARCH — single tool reviews
# ═══════════════════════════════════════════════════════

def get_locked_article_type(tool):
    """Respect the article type the Tool Scout assigned."""
    scout_type = tool.get("article_type", "")
    if scout_type in ARTICLE_TYPE_MAP:
        return ARTICLE_TYPE_MAP[scout_type]
    score = tool.get("score", 0)
    if score >= 70:
        return "review"
    else:
        return "alert"

def research_keywords_single(tool, existing_keyword_data):
    """Research keywords for a single-tool review or alert."""
    category = tool.get("category", "other")
    audience = CATEGORY_AUDIENCE.get(category, CATEGORY_AUDIENCE["other"])
    locked_type = get_locked_article_type(tool)

    templates = TITLE_TEMPLATES.get(locked_type, TITLE_TEMPLATES["review"])
    templates_formatted = "\n".join(f"  - {t}" for t in templates)

    days_since_launch = 0
    try:
        days_since_launch = (datetime.now() - datetime.strptime(
            tool.get("discovered_date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d"
        )).days
    except (ValueError, TypeError):
        pass

    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are an SEO keyword research specialist for "{SITE_NAME}" — an affiliate website reviewing creator tools.

We are a NEW domain (launched March 2026) with zero domain authority.
Only target low-competition, long-tail keywords. Max difficulty: 30.

Today: {today}
{"⚡ URGENT: Tool just launched — first-mover window open." if days_since_launch <= 3 else ""}

TOOL: {tool['name']}
Description: {tool.get('description', '')}
Category: {category}
Score: {tool.get('score', 0)}/100
Article type (LOCKED — do not change): {locked_type}
Target audience: {audience}

TITLE TEMPLATES (pick one and adapt):
{templates_formatted}

YOUR TASK:
1. Find the best long-tail primary keyword (not the obvious short one)
2. Build a cluster of 8-12 related keywords
3. Identify the SERP gap (what page 1 is missing)
4. Create a title under 60 characters using a template above
5. Generate 3 supporting article ideas for the topic cluster

Respond ONLY with valid JSON:
{{
  "primary_keyword": "specific long-tail keyword",
  "secondary_keywords": ["kw2", "kw3", "kw4"],
  "keyword_cluster": ["related1", "related2", "related3", "related4", "related5", "related6", "related7", "related8"],
  "search_intent": "buyer|comparison|informational",
  "difficulty_score": 15,
  "traffic_value": "high|medium|low",
  "article_type": "{locked_type}",
  "recommended_word_count": 2500,
  "article_title": "Title under 60 characters",
  "url_slug": "keyword-friendly-slug",
  "serp_gap": "What page 1 is missing",
  "urgency": "high|medium|low",
  "supporting_articles": [
    {{"title": "Title 1", "slug": "slug-1", "content_type": "comparison", "angle": "Why this helps"}},
    {{"title": "Title 2", "slug": "slug-2", "content_type": "question", "angle": "Why this helps"}},
    {{"title": "Title 3", "slug": "slug-3", "content_type": "roundup", "angle": "Why this helps"}}
  ]
}}"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)
    result["article_type"] = locked_type  # enforce
    result["tool_name"] = tool["name"]
    result["tool_category"] = tool.get("category", "other")
    result["tool_score"] = tool.get("score", 0)
    result["researched_date"] = datetime.now().strftime("%Y-%m-%d")
    result["status"] = "pending_article"

    # Duplicate slug check
    dup = is_duplicate_slug(result["url_slug"], existing_keyword_data)
    if dup:
        suffix = tool["name"].lower().replace(" ", "-")[:20]
        result["url_slug"] = f"{result['url_slug']}-{suffix}"
        print(f"   ⚠️  Slug already used by '{dup}' — appended suffix")

    return result


# ═══════════════════════════════════════════════════════
# KEYWORD RESEARCH — roundup articles ("Best X for Y")
# ═══════════════════════════════════════════════════════

def research_keywords_roundup(opportunity, existing_keyword_data):
    """Research keywords for a roundup article covering multiple tools."""
    category = opportunity["category"]
    audience = opportunity["audience"]
    tools = opportunity["tools"]
    tool_names = [t["name"] for t in tools]

    templates = TITLE_TEMPLATES["roundup"]
    templates_formatted = "\n".join(f"  - {t}" for t in templates)

    prompt = f"""You are an SEO keyword research specialist for "{SITE_NAME}" — an affiliate website reviewing creator tools.

New domain, zero authority. Max keyword difficulty: 30.

ROUNDUP ARTICLE — "Best X for Y" format covering multiple tools.
Category: {category}
Target audience: {audience}
Tools to cover: {', '.join(tool_names)}

TITLE TEMPLATES (pick one and adapt):
{templates_formatted}

This is the HIGHEST CONVERTING article type in affiliate marketing.
Searchers looking for "best [category] tools" are ready to buy.

Respond ONLY with valid JSON:
{{
  "primary_keyword": "best [category] tools for [audience]",
  "secondary_keywords": ["kw2", "kw3", "kw4"],
  "keyword_cluster": ["related1", "related2", "related3", "related4", "related5", "related6"],
  "search_intent": "buyer",
  "difficulty_score": 20,
  "traffic_value": "high",
  "article_type": "roundup",
  "recommended_word_count": 4000,
  "article_title": "Title under 60 characters using a template above",
  "url_slug": "best-category-tools-for-audience",
  "serp_gap": "What existing roundups on page 1 are missing",
  "urgency": "high"
}}"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)
    result["article_type"] = "roundup"  # enforce
    result["tool_name"] = f"Best {category.title()} Tools"
    result["tool_category"] = category
    result["tool_score"] = max(t.get("score", 0) for t in tools)
    result["researched_date"] = datetime.now().strftime("%Y-%m-%d")
    result["status"] = "pending_article"
    # ⚡ This field tells article_agent which tools to include
    result["roundup_tools"] = [{"name": t["name"], "slug": t.get("slug", "")} for t in tools]

    dup = is_duplicate_slug(result["url_slug"], existing_keyword_data)
    if dup:
        result["url_slug"] = f"{result['url_slug']}-{category}"

    return result


# ═══════════════════════════════════════════════════════
# KEYWORD RESEARCH — comparison articles ("X vs Y")
# ═══════════════════════════════════════════════════════

def research_keywords_comparison(comp_opportunity, existing_keyword_data):
    """Research keywords for a head-to-head comparison article."""
    tool_a = comp_opportunity["tool_a"]
    tool_b = comp_opportunity["tool_b"]
    category = comp_opportunity["category"]
    audience = CATEGORY_AUDIENCE.get(category, CATEGORY_AUDIENCE["other"])

    templates = TITLE_TEMPLATES["comparison"]
    templates_formatted = "\n".join(f"  - {t}" for t in templates)

    prompt = f"""You are an SEO keyword research specialist for "{SITE_NAME}" — an affiliate website reviewing creator tools.

New domain, zero authority. Max keyword difficulty: 30.

COMPARISON ARTICLE — "{tool_a} vs {tool_b}" head-to-head.
Category: {category}
Target audience: {audience}

This article ranks for BOTH tool names — double the traffic opportunity.
Searchers comparing two tools are very close to buying.

TITLE TEMPLATES (pick one and adapt):
{templates_formatted}

Respond ONLY with valid JSON:
{{
  "primary_keyword": "{tool_a.lower()} vs {tool_b.lower()}",
  "secondary_keywords": ["kw2", "kw3", "kw4"],
  "keyword_cluster": ["related1", "related2", "related3", "related4", "related5", "related6"],
  "search_intent": "comparison",
  "difficulty_score": 15,
  "traffic_value": "high",
  "article_type": "comparison",
  "recommended_word_count": 3000,
  "article_title": "Title under 60 characters using a template above",
  "url_slug": "{tool_a.lower().replace(' ', '-')}-vs-{tool_b.lower().replace(' ', '-')}",
  "serp_gap": "What existing comparisons are missing",
  "urgency": "high"
}}"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)
    result["article_type"] = "comparison"  # enforce
    result["tool_name"] = f"{tool_a} vs {tool_b}"
    result["tool_category"] = category
    result["tool_score"] = 80  # comparisons are always high value
    result["researched_date"] = datetime.now().strftime("%Y-%m-%d")
    result["status"] = "pending_article"
    # ⚡ This field tells article_agent which tools to compare
    result["comparison_tools"] = {"tool_a": tool_a, "tool_b": tool_b}

    dup = is_duplicate_slug(result["url_slug"], existing_keyword_data)
    if dup:
        result["url_slug"] = f"{result['url_slug']}-comparison"

    return result


# ═══════════════════════════════════════════════════════
# GET TOOLS NEEDING KEYWORDS (updated — same core logic)
# ═══════════════════════════════════════════════════════

def get_tools_needing_keywords():
    """Find tools ready for single-review keyword research."""
    tools_raw = load_json(TOOL_DATABASE, {})
    done = load_json(KEYWORD_DATA, {})
    topics = load_json(TOPICS_USED, [])

    tools = list(tools_raw.values()) if isinstance(tools_raw, dict) else tools_raw

    skipped_low = 0
    skipped_no_aff = 0
    skipped_physical = 0
    pending = []

    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_key = tool.get("name", "").lower().replace(" ", "-")
        if not tool_key:
            continue

        if tool_key in done:
            continue
        if tool.get("name", "").lower() in [t.lower() for t in topics]:
            continue
        if tool.get("status") not in ["discovered", "promoted", "pending"]:
            continue

        score = tool.get("score", 0)
        if score < MIN_SCORE_THRESHOLD:
            skipped_low += 1
            continue
        if not tool.get("has_affiliate_potential", True):
            skipped_no_aff += 1
            continue
        if is_physical_product(tool):
            skipped_physical += 1
            continue

        pending.append(tool)

    pending.sort(key=lambda x: x.get("score", 0), reverse=True)

    if skipped_low > 0:
        print(f"   ℹ️  Skipped {skipped_low} tool(s) below score {MIN_SCORE_THRESHOLD}")
    if skipped_no_aff > 0:
        print(f"   ℹ️  Skipped {skipped_no_aff} tool(s) with no affiliate potential")
    if skipped_physical > 0:
        print(f"   ℹ️  Skipped {skipped_physical} physical product(s)")

    return pending


# ═══════════════════════════════════════════════════════
# MAIN RUN
# ═══════════════════════════════════════════════════════

def run():
    print("\n🔑 Keyword Agent starting...\n")
    write_log(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Keyword Agent run started")

    keyword_data = load_json(KEYWORD_DATA, {})
    tool_database = load_json(TOOL_DATABASE, {})
    processed = 0

    # ── Phase 1: Single-tool reviews ──────────────────────────────────────
    pending = get_tools_needing_keywords()

    if pending:
        review_cap = max(DAILY_CAP - 2, 4)  # Reserve 2 slots for roundups/comparisons
        to_process = pending[:review_cap]
        print(f"📋 Single reviews: {len(pending)} tools waiting, processing {len(to_process)}")

        for tool in to_process:
            if processed >= DAILY_CAP:
                break
            tool_key = tool["name"].lower().replace(" ", "-")
            score = tool.get("score", 0)
            print(f"\n{'⚡' if score >= 75 else '🔍'} Researching: {tool['name']} (score: {score})")

            try:
                result = research_keywords_single(tool, keyword_data)

                # ── Cannibalization check (Phase 2.7A) ──────────────────────
                dup_kw = is_duplicate_primary_keyword(result["primary_keyword"], keyword_data)
                if dup_kw:
                    print(f"   ⚠️  Cannibalization: \"{result['primary_keyword']}\" conflicts with \"{dup_kw}\" — skipping")
                    write_log(f"### SKIP (cannibalization): {tool['name']} — keyword conflicts with {dup_kw}")
                    continue
                # ─────────────────────────────────────────────────────────────

                keyword_data[tool_key] = result

                print(f"   ✅ Keyword: \"{result['primary_keyword']}\"")
                print(f"   📝 Type: {result['article_type']} | {result['recommended_word_count']} words")
                print(f"   🏆 Title: {result['article_title']}")
                print(f"   🔗 Slug: {result['url_slug']}")
                print(f"   📊 Difficulty: {result['difficulty_score']}/100")

                if result.get("supporting_articles"):
                    for sa in result["supporting_articles"]:
                        print(f"   📎 Cluster [{sa.get('content_type', '')}]: {sa.get('title', '')}")

                write_log(f"### {tool['name']} → \"{result['primary_keyword']}\" | {result['article_type']} | diff {result['difficulty_score']}")
                processed += 1

            except Exception as e:
                print(f"   ❌ Error: {e}")
                write_log(f"### ERROR — {tool['name']}: {e}")
    else:
        print("   ℹ️  No single-review tools pending")

    # ── Phase 2: Roundup articles ─────────────────────────────────────────
    if processed < DAILY_CAP:
        roundup_opps = find_roundup_opportunities(keyword_data, tool_database)
        if roundup_opps:
            print(f"\n📦 Roundup opportunities: {len(roundup_opps)} categories ready")
            for opp in roundup_opps[:1]:  # Max 1 roundup per run
                if processed >= DAILY_CAP:
                    break
                tool_names = [t["name"] for t in opp["tools"]]
                print(f"\n🏆 Generating roundup: Best {opp['category'].title()} Tools")
                print(f"   Tools: {', '.join(tool_names[:5])}{'...' if len(tool_names) > 5 else ''}")

                try:
                    result = research_keywords_roundup(opp, keyword_data)

                    # ── Cannibalization check (Phase 2.7A) ──────────────────
                    dup_kw = is_duplicate_primary_keyword(result["primary_keyword"], keyword_data)
                    if dup_kw:
                        print(f"   ⚠️  Cannibalization: \"{result['primary_keyword']}\" conflicts with \"{dup_kw}\" — skipping")
                        write_log(f"### SKIP (cannibalization): Roundup {opp['category']} — keyword conflicts with {dup_kw}")
                    else:
                        roundup_key = f"roundup-{opp['category']}"
                        keyword_data[roundup_key] = result

                        print(f"   ✅ Keyword: \"{result['primary_keyword']}\"")
                        print(f"   📝 Type: roundup | {result['recommended_word_count']} words")
                        print(f"   🏆 Title: {result['article_title']}")
                        print(f"   🔗 Slug: {result['url_slug']}")
                        print(f"   🔧 Tools included: {len(result.get('roundup_tools', []))}")

                        write_log(f"### ROUNDUP: {result['article_title']} → \"{result['primary_keyword']}\" | {len(result.get('roundup_tools', []))} tools")
                        processed += 1

                except Exception as e:
                    print(f"   ❌ Roundup error: {e}")
                    write_log(f"### ERROR — Roundup {opp['category']}: {e}")
        else:
            print(f"\n   ℹ️  No roundup opportunities yet (need {ROUNDUP_TRIGGER_COUNT}+ tools per category)")

    # ── Phase 3: Comparison articles ──────────────────────────────────────
    if processed < DAILY_CAP:
        comp_opps = find_comparison_opportunities(keyword_data, tool_database)
        if comp_opps:
            print(f"\n⚖️  Comparison opportunities: {len(comp_opps)} pairs found")
            for opp in comp_opps[:1]:  # Max 1 comparison per run
                if processed >= DAILY_CAP:
                    break
                print(f"\n⚖️  Generating comparison: {opp['tool_a']} vs {opp['tool_b']}")
                print(f"   Reason: {opp['reason']}")

                try:
                    result = research_keywords_comparison(opp, keyword_data)

                    # ── Cannibalization check (Phase 2.7A) ──────────────────
                    dup_kw = is_duplicate_primary_keyword(result["primary_keyword"], keyword_data)
                    if dup_kw:
                        print(f"   ⚠️  Cannibalization: \"{result['primary_keyword']}\" conflicts with \"{dup_kw}\" — skipping")
                        write_log(f"### SKIP (cannibalization): {opp['tool_a']} vs {opp['tool_b']} — keyword conflicts with {dup_kw}")
                    else:
                        comp_key = f"comparison-{opp['tool_a'].lower().replace(' ', '-')}-vs-{opp['tool_b'].lower().replace(' ', '-')}"
                        keyword_data[comp_key] = result

                        print(f"   ✅ Keyword: \"{result['primary_keyword']}\"")
                        print(f"   📝 Type: comparison | {result['recommended_word_count']} words")
                        print(f"   🏆 Title: {result['article_title']}")
                        print(f"   🔗 Slug: {result['url_slug']}")

                        write_log(f"### COMPARISON: {result['article_title']} → \"{result['primary_keyword']}\"")
                        processed += 1

                except Exception as e:
                    print(f"   ❌ Comparison error: {e}")
                    write_log(f"### ERROR — Comparison {opp['tool_a']} vs {opp['tool_b']}: {e}")
        else:
            print(f"\n   ℹ️  No comparison opportunities yet")

    # ── Save everything ───────────────────────────────────────────────────
    save_json(KEYWORD_DATA, keyword_data)
    slug_index = build_slug_index(keyword_data)
    save_json("memory/keyword_slug_index.json", slug_index)

    # ── Summary ───────────────────────────────────────────────────────────
    type_counts = {}
    for data in keyword_data.values():
        if isinstance(data, dict):
            t = data.get("article_type", "review")
            type_counts[t] = type_counts.get(t, 0) + 1
    type_str = ", ".join(f"{v} {k}" for k, v in type_counts.items())

    print(f"\n💾 Saved {processed} keyword package(s)")
    print(f"📊 Total in keyword_data: {len(keyword_data)} ({type_str})")
    write_log(f"\nRun complete. Processed: {processed}. Total: {len(keyword_data)}")
    print("\n✅ Keyword Agent done.\n")


if __name__ == "__main__":
    run()