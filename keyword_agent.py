import json
import os
from datetime import datetime
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SITE_NAME

client = Anthropic(api_key=ANTHROPIC_API_KEY)

TOOL_DATABASE = "memory/tool_database.json"
KEYWORD_DATA = "memory/keyword_data.json"
TOPICS_USED = "memory/topics_used.json"
LOGS_DIR = "memory/logs/keyword_agent"

# Only research keywords for tools we are confident about
MIN_SCORE_THRESHOLD = 60

# Process max this many tools per run to control API spend
DAILY_CAP = 8

# Hard signals — if these appear in the NAME, it's definitely physical
PHYSICAL_NAME_SIGNALS = [
    "macbook", "iphone", "ipad", "pixel phone", "galaxy phone",
    "airpods", "homepod", "apple watch", "gaming console"
]

# Soft signals — only flag as physical if these appear AND no software signals present
PHYSICAL_DESC_SIGNALS = [
    "physical device", "hardware device", "buy now ships",
    "ships in", "order online", "add to cart", "in the box",
    "unboxing", "plug in", "usb device", "hdmi", "bluetooth speaker"
]

# If description contains these, it's software regardless of anything else
SOFTWARE_OVERRIDE_SIGNALS = [
    "app", "software", "subscription", "saas", "platform", "tool",
    "dashboard", "browser", "extension", "api", "plugin", "web-based",
    "cloud", "download", "install", "free trial", "pricing plan"
]

# Article types the Tool Scout can assign — Keyword Agent respects these
VALID_ARTICLE_TYPES = [
    "affiliate_review", "full_review", "authority_article",
    "new_tool_alert", "comparison", "listicle", "tutorial"
]

# Map Scout article types to Keyword Agent article types
ARTICLE_TYPE_MAP = {
    "affiliate_review":  "review",
    "full_review":       "review",
    "authority_article": "review",
    "new_tool_alert":    "alert",
    "comparison":        "comparison",
    "listicle":          "listicle",
    "tutorial":          "tutorial"
}

# Category-specific audience context for better keyword targeting
CATEGORY_AUDIENCE = {
    "video":        "YouTubers, TikTok creators, Instagram Reels creators, video editors",
    "audio":        "podcasters, voiceover artists, musicians, audio creators",
    "writing":      "bloggers, copywriters, content writers, email marketers",
    "image":        "graphic designers, social media managers, visual content creators",
    "productivity": "freelancers, solopreneurs, remote workers, content creators",
    "coding":       "developer-creators, technical bloggers, no-code builders",
    "seo":          "bloggers, affiliate marketers, SEO specialists, content strategists",
    "other":        "content creators, online entrepreneurs, digital marketers"
}

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
    log_path = f"{LOGS_DIR}/{today}.md"
    with open(log_path, "a") as f:
        f.write(entry + "\n")

def is_physical_product(tool):
    """
    Detect physical hardware that slipped past the Scout filter.
    Uses three-layer check to avoid false positives on software tools.
    """
    name_lower = tool["name"].lower()
    desc_lower = tool["description"].lower()

    # Layer 1 — hard name signals: always physical regardless of description
    for signal in PHYSICAL_NAME_SIGNALS:
        if signal in name_lower:
            return True

    # Layer 2 — if description has software signals, it's definitely not physical
    for signal in SOFTWARE_OVERRIDE_SIGNALS:
        if signal in desc_lower:
            return False

    # Layer 3 — soft description signals: only flag if no software context found
    for signal in PHYSICAL_DESC_SIGNALS:
        if signal in desc_lower:
            return True

    return False

def is_duplicate_slug(slug, existing_keyword_data):
    """Check if this slug already exists in keyword data."""
    for key, data in existing_keyword_data.items():
        if data.get("url_slug") == slug:
            return data.get("tool_name", key)
    return None

def build_slug_index(keyword_data):
    """
    Build a secondary index: slug → tool_key.
    Lets the Article Writer find tools by slug as well as by name key.
    Saved alongside keyword_data.json as keyword_slug_index.json.
    """
    index = {}
    for tool_key, data in keyword_data.items():
        slug = data.get("url_slug")
        if slug:
            index[slug] = tool_key
    return index

def get_tools_needing_keywords():
    """
    Find tools ready for keyword research.
    - Only processes tools scoring 60 or above
    - Skips tools with no affiliate potential
    - Skips physical products
    - Skips already processed tools
    - Sorts by score descending (best tools first)
    """
    tools_raw = load_json(TOOL_DATABASE, {})
    done = load_json(KEYWORD_DATA, {})
    topics = load_json(TOPICS_USED, [])

    tools = list(tools_raw.values())

    skipped_low_score = 0
    skipped_no_affiliate = 0
    skipped_physical = 0
    skipped_done = 0
    pending = []

    for tool in tools:
        tool_key = tool["name"].lower().replace(" ", "-")
        already_done = tool_key in done
        already_written = tool["name"].lower() in [t.lower() for t in topics]
        is_ready = tool.get("status") in ["discovered", "promoted"]

        if already_done or already_written:
            skipped_done += 1
            continue

        if not is_ready:
            continue

        # Skip tools below confidence threshold
        score = tool.get("score", 0)
        if score < MIN_SCORE_THRESHOLD:
            skipped_low_score += 1
            write_log(f"⏭️  Skipped (score {score} below {MIN_SCORE_THRESHOLD}): {tool['name']}")
            continue

        # Skip tools with no affiliate potential
        if not tool.get("has_affiliate_potential", True):
            skipped_no_affiliate += 1
            write_log(f"⏭️  Skipped (no affiliate): {tool['name']}")
            continue

        # Skip physical products
        if is_physical_product(tool):
            skipped_physical += 1
            write_log(f"⏭️  Skipped (physical product): {tool['name']}")
            print(f"   ⏭️  Skipping physical product: {tool['name']}")
            continue

        pending.append(tool)

    # Sort by score descending — highest value tools get written first
    pending.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Print skip summary
    if skipped_low_score > 0:
        print(f"   ℹ️  Skipped {skipped_low_score} tool(s) with score below {MIN_SCORE_THRESHOLD}")
    if skipped_no_affiliate > 0:
        print(f"   ℹ️  Skipped {skipped_no_affiliate} tool(s) with no affiliate potential")
    if skipped_physical > 0:
        print(f"   ℹ️  Skipped {skipped_physical} physical product(s)")

    return pending

def get_locked_article_type(tool):
    """
    Respect the article type the Tool Scout assigned.
    Only override if Scout didn't assign one.
    Maps Scout types to Keyword Agent types.
    """
    scout_type = tool.get("article_type", "")
    if scout_type in ARTICLE_TYPE_MAP:
        return ARTICLE_TYPE_MAP[scout_type]
    # Fallback based on score
    score = tool.get("score", 0)
    if score >= 70:
        return "review"
    elif score >= 60:
        return "alert"
    else:
        return "alert"

def research_keywords(tool, existing_keyword_data):
    """Ask Claude to research the best keyword strategy for this tool."""

    category = tool.get("category", "other")
    audience = CATEGORY_AUDIENCE.get(category, CATEGORY_AUDIENCE["other"])
    locked_article_type = get_locked_article_type(tool)

    days_since_launch = (datetime.now() - datetime.strptime(
        tool.get("discovered_date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d"
    )).days
    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are an SEO keyword research specialist for "{SITE_NAME}" — an affiliate website reviewing the best tools for content creators.

We are a BRAND NEW domain (launched March 2026) with zero domain authority.
This means we must ONLY target low-competition, long-tail keywords for the first 6 months.
Never recommend a keyword with difficulty above 30. We cannot rank for competitive terms yet.

Today's date: {today}
Tool discovered: {days_since_launch} days ago
{"⚡ URGENT: This tool just launched — competition window is open RIGHT NOW. Prioritize first-mover keywords." if days_since_launch <= 3 else ""}
{"⏰ Tool is " + str(days_since_launch) + " days old — act before competition increases." if 4 <= days_since_launch <= 14 else ""}

TOOL DETAILS:
Name: {tool['name']}
Description: {tool['description']}
Category: {category}
Score: {tool.get('score', 0)}/100
Article type LOCKED: {locked_article_type}
IMPORTANT: The article type is already decided. Do NOT change it.
Your job is only to find the best keywords for this article type.

TARGET AUDIENCE for this category: {audience}
Write keywords that THIS specific audience would search for.

YOUR TASK — think like a professional SEO strategist:

STEP 1 — SEARCH INTENT
Match the exact content type already ranking on page 1.
The article type is locked to: {locked_article_type}
Find keywords where THIS content type ranks on page 1.

STEP 2 — LONG-TAIL KEYWORD FIRST
Never target the short obvious keyword. Find the specific long-tail version.
Example: not "AI video editor" but "best AI video editor for YouTube shorts under $20"
Long-tail = lower competition + clearer intent + higher conversion rate.

STEP 3 — KEYWORD CLUSTER
Find 8-12 related keywords the same article can naturally rank for.
Include: brand keywords, feature keywords, comparison keywords, problem keywords.

STEP 4 — TRAFFIC VALUE OVER VOLUME
Prioritize buyer intent and problem urgency over raw search volume.
200 searches with high buyer intent beats 2000 searches with low intent.

STEP 5 — REALISTIC DIFFICULTY
Be honest about competition. Rules:
- Tool with 1M+ users = difficulty never below 40
- Brand new tool (under 30 days old) = difficulty likely under 15
- Established SaaS with many reviews = difficulty 20-35
- Never recommend difficulty above 30 for our new domain

STEP 6 — SERP GAP
What is missing from articles currently ranking?
Outdated info? No pricing table? No creator workflow? No free trial info?
This is our content advantage.

STEP 7 — TOPIC CLUSTER (supporting articles)
For every main review or alert article, identify 3 supporting articles that:
- Target related long-tail keywords the main article cannot rank for alone
- Answer specific questions people search AFTER discovering the main tool
- Build topical authority so Google sees us as the expert on this tool/category
Examples for a Descript review:
  → "descript vs adobe audition for podcasters" (comparison)
  → "how to remove filler words automatically in descript" (tutorial)
  → "descript free plan limitations 2026" (problem/question)
These supporting articles link back to the main review — building a content cluster
that ranks the whole group faster than isolated articles.

Respond ONLY with a valid JSON object, nothing else:
{{
  "primary_keyword": "specific long-tail keyword to target",
  "secondary_keywords": ["keyword 2", "keyword 3", "keyword 4"],
  "keyword_cluster": [
    "related keyword 1",
    "related keyword 2",
    "related keyword 3",
    "related keyword 4",
    "related keyword 5",
    "related keyword 6",
    "related keyword 7",
    "related keyword 8"
  ],
  "search_intent": "buyer|comparison|informational",
  "estimated_difficulty": "easy|medium|hard",
  "difficulty_score": 15,
  "traffic_value": "high|medium|low",
  "article_type": "{locked_article_type}",
  "recommended_word_count": 2000,
  "article_title": "A compelling SEO title under 60 characters",
  "url_slug": "keyword-friendly-url-slug",
  "serp_gap": "What is missing from current page 1 results that we can do better",
  "reasoning": "One sentence explaining why this keyword was chosen",
  "urgency": "high|medium|low",
  "supporting_articles": [
    {{
      "title": "Supporting article title 1",
      "slug": "url-slug-1",
      "angle": "Why this supports the main article and builds topical authority"
    }},
    {{
      "title": "Supporting article title 2",
      "slug": "url-slug-2",
      "angle": "Why this supports the main article and builds topical authority"
    }},
    {{
      "title": "Supporting article title 3",
      "slug": "url-slug-3",
      "angle": "Why this supports the main article and builds topical authority"
    }}
  ]
}}"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    # Clean up if Claude wrapped it in markdown code blocks
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)

    # Always enforce the locked article type — never let Claude override it
    result["article_type"] = locked_article_type

    # Duplicate slug check
    duplicate_of = is_duplicate_slug(result["url_slug"], existing_keyword_data)
    if duplicate_of:
        print(f"   ⚠️  Slug '{result['url_slug']}' already used by '{duplicate_of}' — appending tool name")
        write_log(f"⚠️  Duplicate slug detected: {result['url_slug']} — already used by {duplicate_of}")
        tool_suffix = tool["name"].lower().replace(" ", "-")[:20]
        result["url_slug"] = f"{result['url_slug']}-{tool_suffix}"

    result["tool_name"] = tool["name"]
    result["tool_category"] = tool["category"]
    result["tool_score"] = tool.get("score", 0)
    result["researched_date"] = datetime.now().strftime("%Y-%m-%d")
    result["days_since_launch"] = days_since_launch
    result["status"] = "pending_article"

    # Log supporting articles if generated
    if result.get("supporting_articles"):
        for sa in result["supporting_articles"]:
            print(f"   📎 Cluster: {sa.get('title', '')}")

    return result

def run():
    print("\n🔑 Keyword Agent starting...\n")
    write_log(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Keyword Agent run started")

    pending = get_tools_needing_keywords()

    if not pending:
        print("✅ No tools waiting for keyword research right now.")
        write_log("No tools pending keyword research.")
        return

    # Apply daily cap
    if len(pending) > DAILY_CAP:
        print(f"📋 Found {len(pending)} tools — processing top {DAILY_CAP} by score (daily cap)\n")
        pending = pending[:DAILY_CAP]
    else:
        print(f"📋 Found {len(pending)} tool(s) waiting for keyword research\n")

    keyword_data = load_json(KEYWORD_DATA, {})
    processed = 0

    for tool in pending:
        tool_key = tool["name"].lower().replace(" ", "-")
        urgency_flag = "⚡" if tool.get("score", 0) >= 75 else "🔍"
        print(f"{urgency_flag} Researching keywords for: {tool['name']} (score: {tool.get('score', 0)})")

        try:
            result = research_keywords(tool, keyword_data)
            keyword_data[tool_key] = result

            urgency_emoji = {"high": "🔥", "medium": "⏰", "low": "📅"}.get(
                result.get("urgency", "low"), "📅"
            )

            print(f"   ✅ Primary keyword: \"{result['primary_keyword']}\"")
            print(f"   📊 Difficulty: {result['estimated_difficulty']} ({result['difficulty_score']}/100)")
            print(f"   🎯 Intent: {result['search_intent']}")
            print(f"   💰 Traffic value: {result['traffic_value']}")
            print(f"   📝 Article type: {result['article_type']} ({result['recommended_word_count']} words)")
            print(f"   🏆 Title: {result['article_title']}")
            print(f"   🔗 Slug: {result['url_slug']}")
            print(f"   🕳️  SERP gap: {result['serp_gap']}")
            print(f"   {urgency_emoji} Urgency: {result.get('urgency', 'unknown')}")
            print(f"   💡 {result['reasoning']}\n")

            log_entry = f"""
### {tool['name']} (score: {tool.get('score', 0)})
- Primary keyword: {result['primary_keyword']}
- Keyword cluster: {', '.join(result['keyword_cluster'])}
- Difficulty: {result['estimated_difficulty']} ({result['difficulty_score']}/100)
- Intent: {result['search_intent']}
- Traffic value: {result['traffic_value']}
- Urgency: {result.get('urgency', 'unknown')}
- Article type: {result['article_type']} ({result['recommended_word_count']} words)
- Title: {result['article_title']}
- Slug: {result['url_slug']}
- SERP gap: {result['serp_gap']}
- Reasoning: {result['reasoning']}"""
            write_log(log_entry)

            processed += 1

        except Exception as e:
            print(f"   ❌ Error processing {tool['name']}: {e}\n")
            write_log(f"### ERROR — {tool['name']}: {e}")

    # Save keyword data
    save_json(KEYWORD_DATA, keyword_data)

    # Save slug index for Article Writer
    slug_index = build_slug_index(keyword_data)
    save_json("memory/keyword_slug_index.json", slug_index)

    print(f"💾 Saved keyword data for {processed} tool(s) to {KEYWORD_DATA}")
    print(f"🗂️  Slug index saved to memory/keyword_slug_index.json")
    write_log(f"\nRun complete. Processed {processed} tools.")
    print("\n✅ Keyword Agent done.\n")

if __name__ == "__main__":
    run()