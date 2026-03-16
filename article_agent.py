# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
import json
import os
import re
import random
from datetime import datetime
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
import db_helpers
import sqlite3

KEYWORD_DATA_FILE = "memory/keyword_data.json"
TOPICS_USED_FILE = "memory/topics_used.json"
LEARNINGS_FILE = "memory/learnings.json"
STYLE_TRACKER_FILE = "memory/.style_tracker.json"
AFFILIATE_LINKS_FILE = "memory/affiliate_links.json"

# Max articles per run — each costs ~$0.066
# Write-ahead cap in run() prevents overproduction
DAILY_CAP = 10

# Write-ahead cap — skip writing if this many drafts are queued
WRITE_AHEAD_LIMIT = 21

CURRENT_YEAR = datetime.now().year

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ─────────────────────────────────────────
# TOOL URLs — plain homepage links
# Used until affiliate links are approved
# affiliate_manager.py will replace these automatically
# ─────────────────────────────────────────

TOOL_URLS = {
    # Seeded tools
    "canva": "https://www.canva.com",
    "descript": "https://www.descript.com",
    "elevenlabs": "https://elevenlabs.io",
    "riverside": "https://riverside.fm",
    "riverside.fm": "https://riverside.fm",
    "convertkit": "https://convertkit.com",
    "beehiiv": "https://www.beehiiv.com",
    "kajabi": "https://kajabi.com",
    "notion": "https://www.notion.so",
    "loom": "https://www.loom.com",
    "opus clip": "https://www.opus.pro",
    "opus_clip": "https://www.opus.pro",
    "pictory": "https://pictory.ai",
    "surfer seo": "https://surferseo.com",
    "surfer_seo": "https://surferseo.com",
    "buzzsprout": "https://www.buzzsprout.com",
    "podcastle": "https://podcastle.ai",
    "synthesia": "https://www.synthesia.io",
    "otter.ai": "https://otter.ai",
    "stan store": "https://stan.store",
    "stan_store": "https://stan.store",
    "gumroad": "https://gumroad.com",
    "later": "https://later.com",
    "teachable": "https://teachable.com",
    "typeform": "https://www.typeform.com",
    "metricool": "https://metricool.com",
    "jasper ai": "https://www.jasper.ai",
    "jasper_ai": "https://www.jasper.ai",
    "jasper": "https://www.jasper.ai",
    # Overnight discoveries
    "coursekit": "https://coursekit.dev",
    "krisp": "https://krisp.ai",
    "krisp accent conversion": "https://krisp.ai",
    "willow voice": "https://willow.voice",
    "willow voice for teams": "https://willow.voice",
    "spoke": "https://www.spoke.app",
    "substack": "https://substack.com",
    "writesonic": "https://writesonic.com",
    "trimmr": "https://trimmr.ai",
    "trimmr.ai": "https://trimmr.ai",
    "vois": "https://vois.ai",
    "luma agents": "https://lumalabs.ai",
    "luma": "https://lumalabs.ai",
}

def check_url_live(url: str, timeout: int = 8) -> bool:
    """
    Check if a URL is reachable and returns a real page.
    Returns True if the URL is usable, False if broken.
    """
    import requests as _requests
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = _requests.head(url, headers=headers, timeout=timeout,
                           allow_redirects=True)
        if r.status_code < 500:
            return True
        r = _requests.get(url, headers=headers, timeout=timeout,
                          allow_redirects=True, stream=True)
        r.close()
        return r.status_code < 500
    except Exception:
        return False


def get_tool_url(tool_name: str) -> str:
    """
    Get the homepage URL for a tool.
    Priority:
      1. Known URL from TOOL_URLS dict — verified live
      2. Partial name match in TOOL_URLS — verified live
      3. Common domain guesses — each checked live
      4. Google search fallback
    """
    key = tool_name.lower().strip()

    # ── Step 1: exact match
    if key in TOOL_URLS:
        candidate = TOOL_URLS[key]
        if check_url_live(candidate):
            return candidate
        else:
            print(f"   ⚠️  Known URL for {tool_name} is unreachable ({candidate}) — trying alternatives")

    # ── Step 2: partial match
    for k, v in TOOL_URLS.items():
        if k in key or key in k:
            if check_url_live(v):
                return v

    # ── Step 3: guess common domains
    slug = re.sub(r"[^a-z0-9]", "", key)
    guesses = [
        f"https://www.{slug}.com",
        f"https://{slug}.ai",
        f"https://{slug}.io",
        f"https://app.{slug}.com",
        f"https://www.{slug}.co",
    ]
    for url in guesses:
        if check_url_live(url):
            print(f"   ✅ Verified URL for {tool_name}: {url}")
            return url

    # ── Step 4: safe fallback
    print(f"   ⚠️  Could not verify a live URL for {tool_name} — using search fallback")
    return f"https://www.google.com/search?q={tool_name.replace(' ', '+')}+official+website"


# ─────────────────────────────────────────
# POST-PROCESSING — enforce rules Claude misses
# ─────────────────────────────────────────

def enforce_tool_url(html: str, tool_url: str, tool_name: str) -> str:
    """
    Aggressively replace ALL placeholder patterns with the real tool URL.
    """
    replacements = [
        "[TOOL_URL]", "[AFFILIATE_LINK]", "[tool_url]", "[affiliate_link]",
        "https://example.com", "https://www.example.com", "http://example.com",
        "[INSERT_AFFILIATE_LINK]", "[INSERT_TOOL_URL]", "[URL]",
        "REPLACE_WITH_TOOL_URL",
    ]
    for placeholder in replacements:
        if placeholder in html:
            html = html.replace(placeholder, tool_url)
            print(f"   🔧 Replaced placeholder '{placeholder}' with {tool_url}")

    empty_href_count = html.count('href=""')
    if empty_href_count:
        html = html.replace('href=""', f'href="{tool_url}"')
        print(f"   🔧 Filled {empty_href_count} empty href(s) with {tool_url}")

    remaining = [p for p in replacements if p in html]
    if remaining:
        print(f"   ⚠️  WARNING: {len(remaining)} placeholder(s) still in HTML after replacement")

    return html


def enforce_disclosure_position(html: str, article_type: str) -> str:
    """
    Ensure the affiliate disclosure appears AFTER the opening hook.
    authority_article type: no disclosure needed — remove if present.
    """
    disclosure_pattern = re.compile(
        r'<div class="affiliate-disclosure">.*?</div>',
        re.DOTALL | re.IGNORECASE
    )

    if article_type == "authority_article":
        if disclosure_pattern.search(html):
            html = disclosure_pattern.sub('', html)
            print(f"   🔧 Removed disclosure from authority_article")
        return html

    disclosure_match = disclosure_pattern.search(html)
    if not disclosure_match:
        disclosure_html = (
            '\n<div class="affiliate-disclosure">\n'
            '<p><strong>Disclosure:</strong> This article contains affiliate links. '
            'If you purchase through our links, we may earn a commission at no extra '
            'cost to you. We only recommend tools we\'ve genuinely evaluated.</p>\n'
            '</div>\n'
        )
        first_p = html.find('</p>')
        if first_p != -1:
            html = html[:first_p + 4] + disclosure_html + html[first_p + 4:]
            print(f"   🔧 Added missing disclosure after first paragraph")
        return html

    disclosure_html = disclosure_match.group(0)
    first_p_end = html.find('</p>')
    disclosure_pos = disclosure_match.start()

    if first_p_end == -1:
        return html

    if disclosure_pos < first_p_end:
        html = disclosure_pattern.sub('', html, count=1)
        first_p_end = html.find('</p>')
        if first_p_end != -1:
            html = html[:first_p_end + 4] + '\n' + disclosure_html + html[first_p_end + 4:]
            print(f"   🔧 Moved disclosure to after opening hook")

    return html


def enforce_cta_limit(html: str, tool_url: str, tool_name: str) -> str:
    """
    Ensure no more than 3 CTAs in the article (single-tool articles only).
    """
    cta_pattern = re.compile(
        r'<a[^>]+class="cta-button"[^>]*>.*?</a>',
        re.DOTALL | re.IGNORECASE
    )
    ctas = cta_pattern.findall(html)
    if len(ctas) > 3:
        count = 0
        def replace_extra(m):
            nonlocal count
            count += 1
            if count <= 3:
                return m.group(0)
            return f'<a href="{tool_url}">{tool_name} →</a>'
        html = cta_pattern.sub(replace_extra, html)
        print(f"   🔧 Reduced CTAs from {len(ctas)} to 3")
    return html


def enforce_roundup_urls(html: str, tools_data: list) -> str:
    """
    For roundup articles: replace each tool's placeholder with its real URL.
    tools_data is a list of dicts with 'name' and 'url' keys.
    """
    for tool in tools_data:
        name = tool.get("name", "")
        url = tool.get("url", "")
        if not name or not url:
            continue
        placeholder = f"[URL_{name.upper().replace(' ', '_')}]"
        if placeholder in html:
            html = html.replace(placeholder, url)
            print(f"   🔧 Replaced {placeholder} with {url}")
    return html


# ─────────────────────────────────────────
# FILE HELPERS
# ─────────────────────────────────────────

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
    log_dir = "memory/logs/article_writer"
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    with open(f"{log_dir}/{today}.md", "a") as f:
        f.write(entry + "\n")


# ─────────────────────────────────────────
# FIELD NORMALIZER — bridges keyword_agent → article_agent
# Fixed March 8, 2026 — Phase 2.5 bug fix
# ─────────────────────────────────────────

def normalize_tool_data(tool_data: dict) -> dict:
    """
    Map keyword_agent field names to article_agent field names.
    
    keyword_agent saves:
      - roundup_tools: list of {name, slug} for roundup articles
      - comparison_tools: {tool_a, tool_b} for comparison articles
    
    article_agent reads:
      - tools_to_cover: list of tools for roundup articles
      - tool_a / tool_b: top-level fields for comparison articles
    
    This bridges the gap so both naming conventions work.
    Runs once per article before any processing starts.
    """

    # Roundup: keyword_agent saves "roundup_tools", article_agent reads "tools_to_cover"
    if not tool_data.get("tools_to_cover") and tool_data.get("roundup_tools"):
        tool_data["tools_to_cover"] = tool_data["roundup_tools"]

    # Comparison: keyword_agent saves nested "comparison_tools" dict,
    # article_agent reads top-level "tool_a" and "tool_b"
    comp = tool_data.get("comparison_tools", {})
    if comp:
        if not tool_data.get("tool_a") and comp.get("tool_a"):
            tool_data["tool_a"] = comp["tool_a"]
        if not tool_data.get("tool_b") and comp.get("tool_b"):
            tool_data["tool_b"] = comp["tool_b"]

    return tool_data


# ─────────────────────────────────────────
# SELF-LEARNING — reads past performance data
# ─────────────────────────────────────────

EDITOR_FEEDBACK_FILE = "memory/editor_feedback.json"


def get_editor_feedback() -> str:
    """
    Load memory/editor_feedback.json (written by editor_agent after each run)
    and return a warning block to inject into article prompts.
    Returns empty string if file doesn't exist or is invalid.
    """
    try:
        feedback = load_json(EDITOR_FEEDBACK_FILE, None)
        if not feedback or not isinstance(feedback, dict):
            return ""
        top_deductions = feedback.get("top_deductions", [])
        if not top_deductions:
            return ""
        issues = ", ".join(top_deductions)
        return (
            "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "AVOID THESE MISTAKES (editor flagged these last run)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{issues}.\n"
            "The editor will auto-reject articles with placeholder URLs or emoji in headings.\n"
            "→ Review the list above and make sure none of these appear in your article.\n"
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return ""
    except Exception:
        return ""


# ─────────────────────────────────────────
# REWRITE HELPERS (Phase 2.7G)
# ─────────────────────────────────────────

def _handoff_to_tool_data(handoff: dict) -> dict:
    """Convert a handoff record back to tool_data format for re-writing."""
    comparison_tools = handoff.get("comparison_tools") or {}
    return {
        "tool_name":             handoff.get("tool_name", ""),
        "tool_key":              handoff.get("tool_key", handoff.get("slug", "")),
        "article_type":          handoff.get("article_type", "review"),
        "article_title":         handoff.get("article_title", ""),
        "url_slug":              handoff.get("url_slug", handoff.get("slug", "")),
        "primary_keyword":       handoff.get("primary_keyword", ""),
        "tool_category":         handoff.get("category", "AI tool"),
        "tool_score":            handoff.get("tool_score", 0),
        "tool_url":              handoff.get("tool_url", ""),
        "recommended_word_count": 2500,
        "search_intent":         "buyer",
        "serp_gap":              "",
        "keyword_cluster":       [],
        "secondary_keywords":    [],
        "tools_to_cover":        handoff.get("roundup_tools", []),
        "tool_a":                comparison_tools.get("tool_a", "") if isinstance(comparison_tools, dict) else "",
        "tool_b":                comparison_tools.get("tool_b", "") if isinstance(comparison_tools, dict) else "",
    }


def calculate_rewrite_priority(slug: str, handoff: dict) -> int:
    """
    Score a needs_rewrite article to decide processing order.
    Higher score = process first.
      +50  affiliate link exists for this tool
      +30  previous editor_score below 85 (most room to improve)
      +20  tool score above 80 in tools table (important tool)
    """
    score = 0
    tool_name = (handoff.get("tool_name") or slug).lower().strip()

    # +50 — affiliate link exists (case-insensitive match)
    try:
        affiliate_links = load_json(AFFILIATE_LINKS_FILE, {})
        if any(k.lower() == tool_name for k in affiliate_links):
            score += 50
    except Exception:
        pass

    # +30 — previous editor_score below 85
    editor_score = handoff.get("editor_score", 0) or 0
    if 0 < editor_score < 85:
        score += 30

    # +20 — tool score above 80 from tools table
    try:
        conn = sqlite3.connect("memory/pipeline.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT score FROM tools WHERE LOWER(name) = ?", (tool_name,)
        ).fetchone()
        conn.close()
        if row and (row["score"] or 0) > 80:
            score += 20
    except Exception:
        pass

    return score


def get_tool_source_url(tool_name: str) -> str:
    """
    Look up a tool's source_url (and website fallback) from the tools table.
    Returns an injection string for the writing prompt, or empty string.
    """
    try:
        conn = sqlite3.connect("memory/pipeline.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT source_url FROM tools WHERE LOWER(name) = ?",
            (tool_name.lower().strip(),)
        ).fetchone()
        conn.close()
        if row:
            real_url = row["source_url"] if row["source_url"] else None
            if real_url:
                return (
                    f"The tool's real URL is: {real_url} — "
                    "use this exact URL, do not guess or fabricate a URL."
                )
    except Exception:
        pass
    return (
        "WARNING: No verified URL found for this tool. "
        "Do not fabricate a URL like www.[toolname].com — "
        "instead write [TOOL_WEBSITE] as a placeholder which the editor will catch and reject."
    )


def get_learnings() -> str:
    """
    Read learnings.json if it exists and return formatted insights
    for the writing prompt. This is how the system gets smarter over time.
    
    Phase 4 will auto-populate this from Google Analytics + Search Console.
    For now, Alex can add learnings manually or weekly_digest can seed it.
    
    Expected format:
    {
        "seo_insights": ["longer articles rank better in AI tools niche"],
        "avoid_patterns": ["long intros lose readers"],
        "winning_hooks": ["problem-first openings get lowest bounce rate"],
        "audience_preferences": ["podcasters engage most with tool comparisons"]
    }
    """
    learnings = load_json(LEARNINGS_FILE, {})
    if not learnings:
        return ""
    
    parts = []
    
    if learnings.get("seo_insights"):
        insights = "\n".join(f"  - {i}" for i in learnings["seo_insights"][:5])
        parts.append(f"SEO INSIGHTS FROM PAST PERFORMANCE:\n{insights}")
    
    if learnings.get("avoid_patterns"):
        avoids = "\n".join(f"  - {a}" for a in learnings["avoid_patterns"][:5])
        parts.append(f"PATTERNS TO AVOID (underperformed):\n{avoids}")
    
    if learnings.get("winning_hooks"):
        hooks = "\n".join(f"  - {h}" for h in learnings["winning_hooks"][:3])
        parts.append(f"HOOK STYLES THAT PERFORMED WELL:\n{hooks}")
    
    if learnings.get("audience_preferences"):
        prefs = "\n".join(f"  - {p}" for p in learnings["audience_preferences"][:3])
        parts.append(f"AUDIENCE PREFERENCES:\n{prefs}")
    
    if not parts:
        return ""
    
    return ("\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "LEARNINGS FROM PAST PERFORMANCE\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n\n".join(parts) + 
            "\n→ Incorporate these insights naturally. Do not mention them in the article.\n")


# ─────────────────────────────────────────
# STYLE ROTATION — no two articles feel the same
# ─────────────────────────────────────────

WRITING_STYLES = {
    "tester": {
        "name": "The Hands-On Tester",
        "voice": (
            "Write as someone who personally tested this tool and is reporting back. "
            "Use phrases like 'when I tried', 'the first thing I noticed', 'after a week of use'. "
            "Be specific about what surprised you (good and bad). Share small details that "
            "only someone who actually used the tool would know — menu locations, loading times, "
            "the exact moment the tool clicked or frustrated. Tone: honest, slightly informal, "
            "like a friend telling you about something they found."
        ),
        "opening_style": (
            "Open with a specific moment during testing. What were you trying to do? "
            "What happened? One concrete scene, 2 sentences max."
        ),
    },
    "analyst": {
        "name": "The Data-Driven Analyst",
        "voice": (
            "Write with analytical precision. Compare features methodically. "
            "Use structured breakdowns, numbered criteria, clear scoring logic. "
            "Tone: authoritative but accessible — like a Consumer Reports reviewer "
            "who explains the methodology. Reference specific metrics: "
            "response times, export quality, number of templates, API limits."
        ),
        "opening_style": (
            "Open with a specific problem statement and a quantified claim. "
            "Example structure: '[Task] takes the average creator [X hours]. "
            "We tested [N] tools to find which actually cuts that time.'"
        ),
    },
    "advisor": {
        "name": "The Trusted Advisor",
        "voice": (
            "Write like a mentor helping a creator make the right choice. "
            "Lead with the reader's situation, not the tool's features. "
            "Frame every feature in terms of what it means for the reader's "
            "workflow, income, or time savings. Tone: warm, knowledgeable, "
            "slightly protective — you want to save them from a bad purchase."
        ),
        "opening_style": (
            "Open by describing the reader's exact situation. "
            "Paint the scene in 2 sentences, then name the solution."
        ),
    },
    "strategist": {
        "name": "The Business Strategist",
        "voice": (
            "Write from a business growth perspective. Frame every tool "
            "as a business decision — what is the ROI? How does it fit into a "
            "creator's stack? What does it replace? What is the cost of NOT using it? "
            "Tone: confident and direct, like a consultant. "
            "Use concrete money/time numbers wherever possible."
        ),
        "opening_style": (
            "Open with a business reality check. Frame the problem in "
            "dollars or hours lost, then offer the solution."
        ),
    },
    "storyteller": {
        "name": "The Storyteller",
        "voice": (
            "Write through the lens of a specific creator persona. "
            "Introduce a character (a podcaster, course creator, YouTuber) "
            "and weave their journey with the tool throughout. "
            "Not a fictional testimonial — a representative scenario built from "
            "real use cases. Tone: narrative and engaging, with concrete details."
        ),
        "opening_style": (
            "Open with a mini-scenario. Quick character, quick result, "
            "then reveal the tool. 2-3 sentences."
        ),
    },
}

OPENING_HOOKS = [
    "problem_first",
    "statistic_led",
    "scenario",
    "contrarian",
    "result_first",
    "question",
]


def get_next_style(article_type: str) -> dict:
    """
    Pick the next writing style from rotation.
    Ensures no two consecutive articles use the same style.
    """
    tracker = load_json(STYLE_TRACKER_FILE, {"last_styles": [], "last_hooks": []})
    recent_styles = tracker.get("last_styles", [])[-4:]
    recent_hooks = tracker.get("last_hooks", [])[-4:]
    
    style_preferences = {
        "roundup": ["analyst", "advisor", "strategist"],
        "comparison": ["analyst", "tester", "strategist"],
        "review": list(WRITING_STYLES.keys()),
        "affiliate_review": list(WRITING_STYLES.keys()),
        "alert": ["tester", "analyst", "strategist"],
        "authority_article": ["analyst", "strategist", "advisor"],
    }
    
    available_styles = style_preferences.get(article_type, list(WRITING_STYLES.keys()))
    
    if recent_styles:
        last_style = recent_styles[-1]
        preferred = [s for s in available_styles if s != last_style]
        if preferred:
            available_styles = preferred
    
    chosen_style_key = random.choice(available_styles)
    chosen_style = WRITING_STYLES[chosen_style_key].copy()
    
    available_hooks = OPENING_HOOKS.copy()
    if recent_hooks:
        last_hook = recent_hooks[-1]
        preferred_hooks = [h for h in available_hooks if h != last_hook]
        if preferred_hooks:
            available_hooks = preferred_hooks
    
    chosen_hook = random.choice(available_hooks)
    
    recent_styles.append(chosen_style_key)
    recent_hooks.append(chosen_hook)
    tracker["last_styles"] = recent_styles[-10:]
    tracker["last_hooks"] = recent_hooks[-10:]
    save_json(STYLE_TRACKER_FILE, tracker)
    
    chosen_style["key"] = chosen_style_key
    chosen_style["hook_type"] = chosen_hook
    
    return chosen_style


def get_hook_instruction(hook_type: str, tool_name: str, category: str) -> str:
    """Return specific opening hook instructions based on the chosen type."""
    hooks = {
        "problem_first": (
            f"OPENING HOOK: Problem-First\n"
            f"Start with the exact frustration or time-waste that {tool_name} solves. "
            f"Be specific — name the task, the time it takes, the friction. "
            f"2 sentences max. Then name {tool_name} as the solution."
        ),
        "statistic_led": (
            f"OPENING HOOK: Statistic-Led\n"
            f"Open with a surprising number related to {category} or the problem {tool_name} solves. "
            f"Use 'according to' or 'based on' if the stat is not universally known. "
            f"Follow with how {tool_name} addresses that reality. 2-3 sentences."
        ),
        "scenario": (
            f"OPENING HOOK: Scenario\n"
            f"Paint a 2-sentence scene of a creator in the middle of the exact workflow "
            f"where {tool_name} helps. Be vivid — mention the specific task, the moment "
            f"of frustration or need. Then pivot to the solution."
        ),
        "contrarian": (
            f"OPENING HOOK: Contrarian\n"
            f"Challenge a common belief about {category} tools. "
            f"Pattern: 'Most people think X. They are wrong because Y.' "
            f"Then introduce how {tool_name} proves the alternative. 2-3 sentences."
        ),
        "result_first": (
            f"OPENING HOOK: Result-First\n"
            f"Start with a concrete result from using {tool_name}. "
            f"Time saved, money earned, quality improved — pick one, be specific. "
            f"Then explain HOW the tool delivers that result. 2-3 sentences."
        ),
        "question": (
            f"OPENING HOOK: Question\n"
            f"Open with a question matching what the searcher is thinking. "
            f"Follow immediately with a direct answer mentioning {tool_name}. "
            f"Do NOT use 'Are you looking for' — that is banned."
        ),
    }
    return hooks.get(hook_type, hooks["problem_first"])


# ─────────────────────────────────────────
# ARTICLE STRUCTURES BY TYPE
# ─────────────────────────────────────────

def get_review_structure():
    return """
ARTICLE STRUCTURE — follow this exactly:

1. H1 TITLE (exact title provided)

2. OPENING HOOK (no heading) — follow hook strategy above

3. AFFILIATE DISCLOSURE — after the hook
   <div class="affiliate-disclosure">
   <p><strong>Disclosure:</strong> This article contains affiliate links.
   If you purchase through our links, we may earn a commission at no extra
   cost to you. We only recommend tools we've genuinely evaluated.</p>
   </div>

4. KEY TAKEAWAYS BOX
   <div class="key-takeaways"><h3>Key Takeaways</h3><ul>
   <li><strong>Best for:</strong> [specific creator type]</li>
   <li><strong>Pricing:</strong> [starting price or free tier]</li>
   <li><strong>Standout feature:</strong> [one differentiator]</li>
   <li><strong>Verdict:</strong> [one sentence]</li>
   <li><strong>Try it:</strong> <a href="REPLACE_WITH_TOOL_URL">Visit [Tool] →</a></li>
   </ul></div>

5. IS IT RIGHT FOR YOU? (quick decision table)
   <table class="decision-table">
   <thead><tr><th>Choose [Tool] if...</th><th>Skip [Tool] if...</th></tr></thead>
   <tbody><tr><td>[reason]</td><td>[reason]</td></tr></tbody>
   </table>

6. TABLE OF CONTENTS

7. WHAT IS [TOOL]? (H2, id="what-is") — 2 paragraphs

8. KEY FEATURES (3-5 H2 sections with id) — real detail, real use cases

9. PRICING (H2, id="pricing") — exact plan names and prices in a table

10. PROS AND CONS (H2, id="pros-cons")
    <div class="pros"><h3>Pros</h3><ul>...</ul></div>
    <div class="cons"><h3>Cons</h3><ul>...</ul></div>
    At least 3 specific cons. No generic "learning curve" or "can be expensive".

11. WHO IS [TOOL] FOR? (H2, id="who-is-it-for")
    WHO IT IS FOR: 3-4 specific creator types
    WHO IT IS NOT FOR: 2-3 specific creator types with reasons

12. HOW IT COMPARES (H2, id="alternatives") — 1-2 real alternatives

13. THE VERDICT (H2, id="verdict")
    Who should buy, who should skip, one reason to choose it.
    CTA: <a href="REPLACE_WITH_TOOL_URL" class="cta-button">Try [Tool] →</a>

14. FAQ (H2, id="faq") — 4-5 questions, 40-60 word answers below H3
"""


def get_roundup_structure():
    return """
ARTICLE STRUCTURE — ROUNDUP FORMAT ("Best X for Y")

1. H1 TITLE (exact title provided)

2. OPENING HOOK — name the #1 pick immediately (featured snippet capture)

3. AFFILIATE DISCLOSURE (after hook)

4. QUICK PICKS TABLE — featured snippet target
   <div class="quick-picks">
   <h2 id="quick-picks">Quick Picks</h2>
   <table class="comparison-table">
   <thead><tr><th>Tool</th><th>Best For</th><th>Starting Price</th><th>Link</th></tr></thead>
   <tbody>[one row per tool, 5-8 tools]</tbody>
   </table></div>

5. HOW WE CHOSE THESE TOOLS (H2, id="methodology") — 1-2 paragraphs, builds E-E-A-T

6. INDIVIDUAL TOOL SECTIONS — one H2 per tool:
   - H2: "[Tool] — Best for [Use Case]" (with id)
   - 2-3 paragraphs: what it does, key strength, ideal user
   - Quick pros/cons (2-3 each, inline)
   - Pricing mention
   - CTA: <a href="[TOOL_URL]" class="cta-button">Try [Tool] →</a>
   
   CRITICAL: Vary each section. Do NOT repeat the same template.
   Tool 1: lead with standout feature
   Tool 2: lead with pricing value
   Tool 3: lead with ideal user profile
   Tool 4: lead with a use case scenario
   Tool 5: lead with what makes it unique

7. COMPARISON TABLE (H2, id="comparison")
   Rows: Free Plan, Starting Price, Best Feature, Learning Curve, Mobile App

8. HOW TO CHOOSE (H2, id="how-to-choose")
   Decision tree: "If you need X → choose Tool A"

9. FAQ (H2, id="faq") — 5-6 questions including comparison questions
"""


def get_comparison_structure():
    return """
ARTICLE STRUCTURE — COMPARISON FORMAT ("X vs Y")

1. H1 TITLE (exact title provided)

2. OPENING HOOK — declare the winner upfront (featured snippet capture)
   "[Tool A] wins for X. [Tool B] wins for Y. Here is the breakdown."

3. AFFILIATE DISCLOSURE (after hook)

4. QUICK VERDICT TABLE
   <table class="verdict-table">
   <thead><tr><th>Category</th><th>[Tool A]</th><th>[Tool B]</th><th>Winner</th></tr></thead>
   <tbody>[5-6 comparison rows + overall winner row]</tbody>
   </table>

5. [TOOL A] OVERVIEW (H2) — what it is, core value. 2 paragraphs.

6. [TOOL B] OVERVIEW (H2) — what it is, core value. 2 paragraphs.

7. HEAD-TO-HEAD SECTIONS — 4-6 H2 sections comparing one dimension each:
   Ease of Use, Features, Pricing, Output Quality, Integrations, Learning Curve
   Each section: both tools discussed, clear winner declared.
   ALTERNATE which tool you discuss first in each section.

8. PRICING COMPARISON (H2, id="pricing") — side-by-side tables

9. WHO SHOULD CHOOSE [TOOL A] (H2) — 3-4 creator profiles + CTA

10. WHO SHOULD CHOOSE [TOOL B] (H2) — 3-4 creator profiles + CTA

11. FINAL VERDICT (H2, id="verdict") — overall winner + when the other wins

12. FAQ (H2, id="faq") — 5-6 questions including "Is [A] better than [B]?"
"""


def get_authority_structure():
    return """
ARTICLE STRUCTURE — NO disclosure, NO CTA buttons.

1. H1 TITLE
2. OPENING HOOK (2-3 sentences)
3. KEY TAKEAWAYS BOX
4. TABLE OF CONTENTS
5. MAIN BODY (4-6 H2 sections with id)
6. WHO THIS IS FOR (H2) — 1 paragraph
7. SUMMARY (H2, id="verdict") — concrete takeaway
8. FAQ (4-5 questions, 40-60 word answers)
"""


def get_alert_structure():
    return """
ARTICLE STRUCTURE:

1. H1 TITLE
2. OPENING HOOK (2-3 sentences)
3. AFFILIATE DISCLOSURE (after hook)
4. KEY TAKEAWAYS BOX
5. TABLE OF CONTENTS
6. WHAT JUST LAUNCHED (H2, id="what-launched")
7. KEY FEATURES (3-4 H2 sections)
8. PRICING (H2, id="pricing")
9. WHO IS IT FOR? (H2, id="who-is-it-for")
10. EARLY VERDICT (H2, id="verdict") + CTA
11. FAQ (3-4 questions)
"""


def get_structure(article_type: str) -> str:
    structures = {
        "review": get_review_structure(),
        "affiliate_review": get_review_structure(),
        "roundup": get_roundup_structure(),
        "comparison": get_comparison_structure(),
        "authority_article": get_authority_structure(),
        "alert": get_alert_structure(),
    }
    return structures.get(article_type, get_review_structure())


# ─────────────────────────────────────────
# E-E-A-T + AEO BLOCK — injected into every prompt
# Phase 2.7A — improves every article going forward
# ─────────────────────────────────────────

def get_eeat_aeo_block() -> str:
    """
    Returns the E-E-A-T and AEO instruction block injected into all prompts.
    E-E-A-T = Experience, Expertise, Authoritativeness, Trustworthiness.
    AEO = Answer Engine Optimization (structured for AI assistants + featured snippets).
    """
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
E-E-A-T SIGNALS — required in every article
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXPERIENCE (most critical for affiliate sites):
→ Use first-person testing language: "In our testing," "We found," "When we evaluated"
→ Name specific moments: "The export took 4 minutes — faster than we expected"
→ Acknowledge what you couldn't access: "We couldn't test enterprise pricing — verify at [URL]"
→ Mention what surprised you (good or bad) — only real testers get surprised
→ One credibility signal in the opening: who evaluated this and by what standard

EXPERTISE:
→ Frame comparisons with criteria: "We evaluated on ease of use, output quality, and pricing"
→ Name the specific feature or plan you tested when relevant
→ Use category context: "Compared to other tools in this space..."

AUTHORITATIVENESS:
→ Comparison tables must declare a winner per row — never leave the winner column blank
→ "Who this is NOT for" section is mandatory in reviews — it signals honest evaluation
→ Roundups: "How We Chose These Tools" section (already in structure — make it substantive)

TRUSTWORTHINESS:
→ Affiliate disclosure always present and prominent (except authority_article)
→ 3+ specific, non-generic cons — "Limited export formats on the free plan" not "learning curve"
→ Always include exact pricing or flag: "verify current pricing at [URL]"
→ No CTAs with fake urgency. No "limited time offer," "act now," "don't miss out."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AEO FORMATTING — structured for AI assistants + featured snippets
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANSWER FIRST, EXPLAIN SECOND (core rule):
→ Every H2 section opens with a direct answer in the first sentence
→ WRONG: "When it comes to pricing, there are several factors to consider..."
→ RIGHT: "[Tool] starts at $29/month with a free tier that includes [X]."

FEATURED SNIPPET TARGETS:
→ Key Takeaways box: items under 15 words each — structured for list snippets
→ FAQ answers: exactly 40-60 words, first sentence = the answer, rest = context
→ Quick Picks / Quick Verdict tables: one winner declared per row, no "it depends" rows
→ Decision tree in roundups: "If you need X → choose Tool A" (entity-extraction ready)

STATISTICS:
→ Use specific numbers with attribution: "according to [source]" or "based on our testing"
→ Never invent a statistic. No data = "we couldn't find published data on this"
→ Exact numbers beat round estimates: "3.4 seconds" over "about 3 seconds"

QUESTION-PATTERN H2s (use where natural — matches People Also Ask and AI queries):
→ "Is [Tool] worth it for [audience]?"
→ "How much does [Tool] cost?"
→ "Is [Tool] free?"
→ "Is [Tool A] better than [Tool B]?"
→ "What is [Tool] used for?"
"""


# ─────────────────────────────────────────
# BUILD PROMPTS — one per article type
# ─────────────────────────────────────────

def build_prompt(tool_data, published_slugs=None):
    article_type = tool_data.get("article_type", "review")
    if article_type == "roundup":
        return build_roundup_prompt(tool_data, published_slugs)
    elif article_type == "comparison":
        return build_comparison_prompt(tool_data, published_slugs)
    return build_single_tool_prompt(tool_data, published_slugs)


def _build_internal_link_context(published_slugs):
    if published_slugs:
        slug_list = "\n".join(f"  - {s}" for s in published_slugs[:20])
        return f"""EXISTING ARTICLES (for internal links):
{slug_list}
→ Add 2-3 [INTERNAL_LINK: slug] placeholders ONLY where natural
→ Never force a link as an afterthought at a paragraph end
"""
    return "→ Use 2-3 descriptive placeholders: [INTERNAL_LINK: best AI podcast tools]\n"


def build_single_tool_prompt(tool_data, published_slugs=None):
    article_type = tool_data.get("article_type", "review")
    structure = get_structure(article_type)
    keyword_cluster = ", ".join(tool_data.get("keyword_cluster", []))
    secondary = ", ".join(tool_data.get("secondary_keywords", []))
    tool_url = get_tool_url(tool_data.get("tool_name", ""))
    tool_name = tool_data.get("tool_name", "")
    category = tool_data.get("tool_category", "AI tool")

    style = get_next_style(article_type)
    hook_instruction = get_hook_instruction(style["hook_type"], tool_name, category)
    learnings_context = get_learnings()
    editor_feedback_context = get_editor_feedback()
    internal_link_context = _build_internal_link_context(published_slugs)
    source_url_context = get_tool_source_url(tool_name)

    return f"""You are a world-class SEO article writer for affiliate content about creator tools.

Best-in-class references: Brian Dean's structure, Ann Handley's voice,
Gael Breton's conversion focus, Ryan Law's research depth.

Site: Creators Must Have (creatorsmusthave.com) — affiliate reviews for
YouTubers, podcasters, bloggers, course creators, video editors, freelancers.
Brand: "If it's on Creators Must Have, it's worth buying."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR WRITING PERSONA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Style: {style["name"]}
{style["voice"]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPENING HOOK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{hook_instruction}

{get_eeat_aeo_block()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool: {tool_name}  |  URL: {tool_url}  |  Category: {category}  |  Type: {article_type}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SEO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title (exact):     {tool_data['article_title']}
Slug (exact):      {tool_data['url_slug']}
Primary keyword:   "{tool_data['primary_keyword']}"
Secondary:         {secondary}
Cluster:           {keyword_cluster}
Word count:        {tool_data['recommended_word_count']}
Intent:            {tool_data.get('search_intent', 'buyer')}
SERP gap:          "{tool_data.get('serp_gap', '')}"
→ Build a section around this gap — it is your ranking advantage

FEATURED SNIPPET TIPS:
→ Key Takeaways box and decision table are structured for snippet capture
→ FAQ answers: exactly 40-60 words — ideal for Google FAQ snippets
→ Start each FAQ answer with a direct answer in the first sentence

PEOPLE ALSO ASK TARGETING:
→ Use patterns: "Is [tool] worth it?", "How much does [tool] cost?",
  "Is [tool] free?", "Is [tool] better than [competitor]?"
{learnings_context}{editor_feedback_context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL URL — use this everywhere
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{tool_url}
{source_url_context}
FORBIDDEN: [TOOL_URL], [AFFILIATE_LINK], https://example.com, href=""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DISCLOSURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{"NO disclosure — authority article." if article_type == "authority_article" else "REQUIRED — place AFTER opening hook, not before H1."}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- CURRENT YEAR IS {CURRENT_YEAR}. Use {CURRENT_YEAR} whenever a year appears in text. NEVER write any other year.
- Stay in your persona: {style["name"]}. Grade 7 readability. Short sentences.
- Max 3 sentences per paragraph. Use "you" and "your".
- BANNED: "game-changer", "revolutionary", "cutting-edge", "state-of-the-art",
  "powerful tool", "robust features", "seamless integration", "in today's digital world",
  "in conclusion", "leverage", "utilize", "synergy", "dive in", "look no further",
  "it's worth noting", "without further ado", "buckle up"
- No fake statistics or invented testimonials
- Unknown pricing: "verify at {tool_url}"
- Max 3 CTAs. Specific text only: "Try [Tool] →" — never "Click here"
- Pros/cons h3 tags: plain text only, no emojis

INTERNAL LINKS:
{internal_link_context}

HTML: Clean HTML only. No markdown. Every H2 needs id. Tables need thead/tbody.
CTAs: <a href="{tool_url}" class="cta-button">text →</a>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{structure}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SELF-CHECK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ All links use {tool_url} — zero placeholders
✓ Persona: {style["name"]} | Hook: {style["hook_type"]}
✓ Primary keyword in first 100 words
✓ Word count target: {tool_data['recommended_word_count']}
✓ Exact pricing in table | 3+ specific cons | "Not for" section
✓ FAQ answers 40-60 words | Max 3 CTAs | No banned phrases
✓ E-E-A-T: first-person testing language used ("In our testing," "We found")
✓ AEO: every H2 opens with a direct answer in the first sentence
✓ AEO: FAQ answers are answer-first, 40-60 words, no hedging

Write the complete article now. Return ONLY HTML.
"""


def build_roundup_prompt(tool_data, published_slugs=None):
    structure = get_structure("roundup")
    keyword_cluster = ", ".join(tool_data.get("keyword_cluster", []))
    secondary = ", ".join(tool_data.get("secondary_keywords", []))
    category = tool_data.get("tool_category", "AI tool")
    
    tools_to_cover = tool_data.get("tools_to_cover", [])
    tool_lines = []
    for i, tool in enumerate(tools_to_cover, 1):
        if isinstance(tool, str):
            t_name, t_url = tool, get_tool_url(tool)
        else:
            t_name = tool.get("name", f"Tool {i}")
            t_url = tool.get("url") or get_tool_url(t_name)
        tool_lines.append(f"  {i}. {t_name} — {t_url}")
    tools_block = "\n".join(tool_lines) if tool_lines else "  (Use your knowledge of the best tools in this category — cover 5-8)"
    
    style = get_next_style("roundup")
    hook_instruction = get_hook_instruction(style["hook_type"], "these tools", category)
    learnings_context = get_learnings()
    editor_feedback_context = get_editor_feedback()
    internal_link_context = _build_internal_link_context(published_slugs)

    return f"""You are a world-class SEO writer creating a "Best X for Y" roundup — the highest-converting affiliate format. Each tool gets its own CTA = 5-8 affiliate links per article.

Site: Creators Must Have (creatorsmusthave.com). Brand: "If it's on Creators Must Have, it's worth buying."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERSONA: {style["name"]}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{style["voice"]}

HOOK: {hook_instruction}
CRITICAL: Name your #1 pick in the opening — captures featured snippets.

{get_eeat_aeo_block()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARTICLE DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title (exact):   {tool_data['article_title']}
Slug (exact):    {tool_data['url_slug']}
Keyword:         "{tool_data['primary_keyword']}"
Secondary:       {secondary}
Cluster:         {keyword_cluster}
Word count:      {tool_data.get('recommended_word_count', 3500)}
Category:        {category}
SERP gap:        "{tool_data.get('serp_gap', '')}"

TOOLS TO COVER (use each tool's actual URL):
{tools_block}
{learnings_context}{editor_feedback_context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROUNDUP RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0. CURRENT YEAR IS {CURRENT_YEAR}. Use {CURRENT_YEAR} whenever a year appears. NEVER write any other year.
1. 5-8 tools. Each gets H2 + CTA with its own URL.
2. VARY each section — different lead: feature, pricing, user profile, scenario, uniqueness.
3. Quick Picks table at top — featured snippet target.
4. Decision tree at bottom: "If you need X → choose Y"
5. Declare a #1 overall pick. Readers want a clear recommendation.
6. 150-250 words per tool. Comparison table with 5-6 feature rows.
7. BANNED: "game-changer", "revolutionary", "cutting-edge", "seamless", etc.
8. No fake stats. Specific pricing.

HTML: Clean HTML. H2s need id. Tables need thead/tbody.
CTAs: <a href="[TOOL_URL]" class="cta-button">Try [Tool] →</a>
INTERNAL LINKS:
{internal_link_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{structure}

Write the complete article. Return ONLY HTML.
"""


def build_comparison_prompt(tool_data, published_slugs=None):
    structure = get_structure("comparison")
    keyword_cluster = ", ".join(tool_data.get("keyword_cluster", []))
    secondary = ", ".join(tool_data.get("secondary_keywords", []))
    category = tool_data.get("tool_category", "AI tool")
    
    tool_a = tool_data.get("tool_a", tool_data.get("tool_name", "Tool A"))
    tool_b = tool_data.get("tool_b", "")
    tool_a_url = get_tool_url(tool_a)
    tool_b_url = get_tool_url(tool_b) if tool_b else ""

    style = get_next_style("comparison")
    hook_instruction = get_hook_instruction(style["hook_type"], f"{tool_a} vs {tool_b}", category)
    learnings_context = get_learnings()
    editor_feedback_context = get_editor_feedback()
    internal_link_context = _build_internal_link_context(published_slugs)
    source_url_a = get_tool_source_url(tool_a)
    source_url_b = get_tool_source_url(tool_b) if tool_b else ""

    return f"""You are a world-class SEO writer creating an "X vs Y" comparison — ranks for BOTH tool names, doubling traffic.

Site: Creators Must Have (creatorsmusthave.com). Brand: "If it's on Creators Must Have, it's worth buying."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERSONA: {style["name"]}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{style["voice"]}

HOOK: {hook_instruction}
CRITICAL: Declare the winner upfront — captures featured snippets.

{get_eeat_aeo_block()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPARISON DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title (exact):   {tool_data['article_title']}
Slug (exact):    {tool_data['url_slug']}
Keyword:         "{tool_data['primary_keyword']}"
Secondary:       {secondary}
Cluster:         {keyword_cluster}
Word count:      {tool_data.get('recommended_word_count', 3000)}
Category:        {category}
SERP gap:        "{tool_data.get('serp_gap', '')}"

Tool A: {tool_a} — {tool_a_url}
{source_url_a}
Tool B: {tool_b} — {tool_b_url}
{source_url_b}
{learnings_context}{editor_feedback_context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPARISON RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0. CURRENT YEAR IS {CURRENT_YEAR}. Use {CURRENT_YEAR} whenever a year appears. NEVER write any other year.
1. Quick Verdict table at top — featured snippet target.
2. 4-6 head-to-head dimension sections (each H2).
3. ALTERNATE which tool is discussed first in each section.
4. Each tool gets "Who should choose" section with CTA.
5. Declare overall winner but acknowledge when the other wins.
6. Side-by-side pricing.
7. FAQ must include "{tool_a} vs {tool_b}" questions.
8. FAIRNESS: Equal word count and depth for both tools.
9. BANNED phrases: "game-changer", "revolutionary", etc.
10. {tool_a} links → {tool_a_url} | {tool_b} links → {tool_b_url}

HTML: Clean HTML. H2s need id. Tables need thead/tbody.
INTERNAL LINKS:
{internal_link_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{structure}

Write the complete article. Return ONLY HTML.
"""


# ─────────────────────────────────────────
# WRITE THE ARTICLE
# ─────────────────────────────────────────

def write_article(tool_data, published_slugs=None):
    """Send to Claude and get back a full HTML article."""
    prompt = build_prompt(tool_data, published_slugs)
    tool_name = tool_data.get("tool_name", "")
    tool_url = get_tool_url(tool_name)
    article_type = tool_data.get("article_type", "review")

    print(f"   ✍️  Sending to Claude... (target: {tool_data.get('recommended_word_count', 2500)} words)")

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    article_html = response.content[0].text.strip()

    if article_html.startswith("```"):
        lines = article_html.split("\n")
        article_html = "\n".join(lines[1:-1]).strip()

    # ── Post-processing ──────────────────────────────────────────────────────

    article_html = enforce_tool_url(article_html, tool_url, tool_name)

    if article_type == "roundup":
        tools_to_cover = tool_data.get("tools_to_cover", [])
        tools_data = []
        for tool in tools_to_cover:
            if isinstance(tool, str):
                tools_data.append({"name": tool, "url": get_tool_url(tool)})
            else:
                tools_data.append({
                    "name": tool.get("name", ""),
                    "url": tool.get("url") or get_tool_url(tool.get("name", ""))
                })
        article_html = enforce_roundup_urls(article_html, tools_data)

    if article_type == "comparison":
        tool_a = tool_data.get("tool_a", "")
        tool_b = tool_data.get("tool_b", "")
        if tool_a:
            article_html = enforce_tool_url(article_html, get_tool_url(tool_a), tool_a)
        if tool_b:
            article_html = enforce_tool_url(article_html, get_tool_url(tool_b), tool_b)

    article_html = enforce_disclosure_position(article_html, article_type)

    if article_type not in ("roundup",):
        article_html = enforce_cta_limit(article_html, tool_url, tool_name)

    word_count = len(article_html.split())

    if word_count < 500:
        raise ValueError(f"Article too short ({word_count} words) — something went wrong")

    return article_html, word_count


# ─────────────────────────────────────────
# WRITE-AHEAD CAP
# ─────────────────────────────────────────

def should_write_articles() -> bool:
    """
    Skip writing if 21+ unpublished drafts are waiting.
    Saves API budget — no point writing articles that sit for weeks.
    """
    pending_edit = db_helpers.get_handoffs_by_status("pending_edit")
    pending_pub  = db_helpers.get_handoffs_by_status("pending_publish")
    count = len(pending_edit) + len(pending_pub)
    
    if count >= WRITE_AHEAD_LIMIT:
        print(f"   📦 Write-ahead cap: {count} drafts queued (limit: {WRITE_AHEAD_LIMIT})")
        print(f"   ⏸️  Skipping article writing — queue is full enough")
        write_log(f"Write-ahead cap: {count} drafts, skipping")
        return False
    
    remaining = WRITE_AHEAD_LIMIT - count
    print(f"   📊 Queue: {count} drafts waiting | Room for {remaining} more")
    return True


# ─────────────────────────────────────────
# MAIN RUN
# ─────────────────────────────────────────

def run():
    print("\n✍️  Article Agent starting...\n")
    write_log(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Article Agent run")

    if not should_write_articles():
        return

    keyword_data = load_json(KEYWORD_DATA_FILE, {})
    topics_used = load_json(TOPICS_USED_FILE, [])

    published_slugs = [
        data.get("url_slug", key)
        for key, data in keyword_data.items()
        if data.get("status") in ("article_written", "published")
           and data.get("url_slug")
    ]

    # ── Phase 2.7G: Rewrites-first ──────────────────────────────────────────
    rewrites = db_helpers.get_handoffs_by_status("needs_rewrite")

    pending = [
        (key, data) for key, data in keyword_data.items()
        if data.get("status") == "pending_article"
    ]

    if not rewrites and not pending:
        print("   ℹ️  No tools waiting for articles.")
        write_log("No pending tools found.")
        return

    written = 0

    # ── Process rewrites first ───────────────────────────────────────────────
    if rewrites:
        # Sort by priority score (Task 2)
        scored = []
        for h in rewrites:
            slug = h.get("slug", "")
            pri = calculate_rewrite_priority(slug, h)
            print(f"[article_agent] Rewrite priority: {slug} = {pri}")
            write_log(f"[article_agent] Rewrite priority: {slug} = {pri}")
            scored.append((pri, h))
        scored.sort(key=lambda x: -x[0])

        print(f"📋 Found {len(rewrites)} rewrite(s) — processing before new articles")
        write_log(f"Found {len(rewrites)} rewrites. Processing first.")

        for _, handoff in scored:
            if written >= DAILY_CAP:
                print(f"\n⏸️  Daily cap of {DAILY_CAP} reached during rewrites.")
                write_log(f"Cap reached after {written} rewrites.")
                break

            slug      = handoff.get("slug", "")
            tool_name = handoff.get("tool_name", slug)
            print(f"[article_agent] REWRITE: processing {slug} (was needs_rewrite)")
            write_log(f"[article_agent] REWRITE: {slug}")

            # Reset pipeline fields before rewriting
            db_helpers.update_handoff(slug, {
                "status":               "pending_edit",
                "seo_done":             0,
                "internal_links_done":  0,
                "images_added":         0,
                "wp_post_id":           None,
            })

            tool_data = _handoff_to_tool_data(handoff)
            tool_data["tool_url"] = get_tool_url(tool_name)

            try:
                article_html, word_count = write_article(tool_data, published_slugs)

                style_tracker = load_json(STYLE_TRACKER_FILE, {"last_styles": [], "last_hooks": []})
                last_style = (style_tracker.get("last_styles") or ["unknown"])[-1]
                last_hook  = (style_tracker.get("last_hooks")  or ["unknown"])[-1]

                db_helpers.update_handoff(slug, {
                    "article_html":  article_html,
                    "word_count":    word_count,
                    "status":        "pending_edit",
                    "written_date":  datetime.now().strftime("%Y-%m-%d"),
                    "tool_url":      tool_data["tool_url"],
                    "prompt_version": "v2",
                })
                print(f"   ✅ Rewrite done — {word_count} words")
                write_log(f"Rewrite complete: {slug} | {word_count} words")
                written += 1
                if slug not in published_slugs:
                    published_slugs.append(slug)

            except Exception as e:
                print(f"   ❌ Rewrite failed for {slug}: {e}")
                write_log(f"ERROR (rewrite {slug}): {e}")
                continue

    # ── Process new articles (if cap not reached) ────────────────────────────
    if written < DAILY_CAP and pending:
        # Sort: roundups first (most revenue), then comparisons, then by score
        def sort_priority(item):
            key, data = item
            article_type = data.get("article_type", "review")
            score = data.get("tool_score", 0)
            type_bonus = {"roundup": 300, "comparison": 200}.get(article_type, 0)
            return type_bonus + score

        pending.sort(key=sort_priority, reverse=True)

        slots = DAILY_CAP - written
        print(f"📋 Found {len(pending)} new tool(s) waiting for articles")
        print(f"📝 Writing up to {slots} new article(s) this run")

        type_counts = {}
        for _, data in pending:
            t = data.get("article_type", "review")
            type_counts[t] = type_counts.get(t, 0) + 1
        type_summary = " | ".join(f"{t}: {c}" for t, c in type_counts.items())
        print(f"📊 Queue: {type_summary}\n")
        write_log(f"Found {len(pending)} new. Slots remaining: {slots}. Types: {type_summary}")

        for tool_key, tool_data in pending:
            if written >= DAILY_CAP:
                print(f"\n⏸️  Daily cap of {DAILY_CAP} reached.")
                write_log(f"Cap reached after {written} articles total.")
                break

            # ── Normalize field names from keyword_agent → article_agent ──
            tool_data = normalize_tool_data(tool_data)

            tool_name    = tool_data.get("tool_name", tool_key)
            article_type = tool_data.get("article_type", "review")
            score        = tool_data.get("tool_score", "?")
            tool_url     = get_tool_url(tool_name)
            url_slug     = tool_data.get("url_slug", tool_key)

            style_tracker = load_json(STYLE_TRACKER_FILE, {"last_styles": [], "last_hooks": []})

            print(f"[article_agent] NEW: writing {url_slug}")
            print(f"🔧 Writing: {tool_name}")
            print(f"   Type: {article_type} | Score: {score} | URL: {tool_url}")

            if article_type == "roundup":
                tools_list = tool_data.get("tools_to_cover", [])
                print(f"   Roundup: {len(tools_list)} tools")
            elif article_type == "comparison":
                print(f"   Comparing: {tool_data.get('tool_a', '?')} vs {tool_data.get('tool_b', '?')}")

            write_log(f"\n### {tool_name} ({article_type}) — {tool_url}")

            try:
                article_html, word_count = write_article(tool_data, published_slugs)

                style_tracker = load_json(STYLE_TRACKER_FILE, {"last_styles": [], "last_hooks": []})
                last_style = (style_tracker.get("last_styles") or ["unknown"])[-1]
                last_hook  = (style_tracker.get("last_hooks")  or ["unknown"])[-1]

                print(f"   🎨 Style: {last_style} | Hook: {last_hook}")
                print(f"   ✅ Done — {word_count} words")
                write_log(f"Written: {word_count} words | Style: {last_style} | Hook: {last_hook}")

                handoff_key = tool_data.get("url_slug", tool_key)
                db_helpers.insert_handoff({
                    "slug":            handoff_key,
                    "tool_name":       tool_name,
                    "tool_key":        tool_key,
                    "article_type":    article_type,
                    "article_title":   tool_data.get("article_title", ""),
                    "url_slug":        tool_data.get("url_slug", handoff_key),
                    "primary_keyword": tool_data.get("primary_keyword", ""),
                    "word_count":      word_count,
                    "article_html":    article_html,
                    "status":          "pending_edit",
                    "written_date":    datetime.now().strftime("%Y-%m-%d"),
                    "tool_score":      score,
                    "category":        tool_data.get("tool_category", "ai-tools"),
                    "tool_url":        tool_url,
                    "writing_style":   last_style,
                    "hook_type":       last_hook,
                    "tools_covered":   tool_data.get("tools_to_cover", []),
                    "tool_a":          tool_data.get("tool_a", ""),
                    "tool_b":          tool_data.get("tool_b", ""),
                    "prompt_version":  "v2",
                })

                keyword_data[tool_key]["status"] = "article_written"
                keyword_data[tool_key]["article_written_date"] = datetime.now().strftime("%Y-%m-%d")

                slug = tool_data.get("url_slug", "")
                if slug and slug not in topics_used:
                    topics_used.append(slug)

                written += 1
                if tool_data.get("url_slug") and tool_data["url_slug"] not in published_slugs:
                    published_slugs.append(tool_data["url_slug"])
                print(f"   💾 Saved to pipeline.db\n")

            except Exception as e:
                print(f"   ❌ Failed: {e}")
                write_log(f"ERROR: {e}")
                continue

    save_json(KEYWORD_DATA_FILE, keyword_data)
    save_json(TOPICS_USED_FILE, topics_used)

    print(f"✅ Article Agent done. Wrote {written} article(s) this run.")
    write_log(f"Complete. Written: {written}")

    if written > 0:
        remaining_new = max(0, len(pending) - max(0, written - len(rewrites)))
        print(f"\n📬 Next: editor_agent.py → image_agent.py → publisher_agent.py")
        if remaining_new > 0:
            print(f"   {remaining_new} new tool(s) still queued.")


if __name__ == "__main__":
    run()