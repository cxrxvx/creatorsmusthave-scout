import json
import os
import re
from datetime import datetime
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

KEYWORD_DATA_FILE = "memory/keyword_data.json"
HANDOFFS_FILE = "memory/handoffs.json"
TOPICS_USED_FILE = "memory/topics_used.json"

# Max articles per run — each costs ~$0.066
# Increase this once you're happy with quality
DAILY_CAP = 10

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

    # ── Step 1: exact match ───────────────────────────────────────────────────
    if key in TOOL_URLS:
        candidate = TOOL_URLS[key]
        if check_url_live(candidate):
            return candidate
        else:
            print(f"   ⚠️  Known URL for {tool_name} is unreachable ({candidate}) — trying alternatives")

    # ── Step 2: partial match ─────────────────────────────────────────────────
    for k, v in TOOL_URLS.items():
        if k in key or key in k:
            if check_url_live(v):
                return v

    # ── Step 3: guess common domains ─────────────────────────────────────────
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

    # ── Step 4: safe fallback ─────────────────────────────────────────────────
    print(f"   ⚠️  Could not verify a live URL for {tool_name} — using search fallback")
    return f"https://www.google.com/search?q={tool_name.replace(' ', '+')}+official+website"


# ─────────────────────────────────────────
# POST-PROCESSING — enforce rules Claude misses
# ─────────────────────────────────────────

def enforce_tool_url(html: str, tool_url: str, tool_name: str) -> str:
    """
    Aggressively replace ALL placeholder patterns with the real tool URL.
    Claude sometimes leaves [TOOL_URL], [AFFILIATE_LINK], or writes
    'https://example.com' as a dummy. This catches all of them.
    """
    replacements = [
        "[TOOL_URL]",
        "[AFFILIATE_LINK]",
        "[tool_url]",
        "[affiliate_link]",
        "https://example.com",
        "https://www.example.com",
        "http://example.com",
        "[INSERT_AFFILIATE_LINK]",
        "[INSERT_TOOL_URL]",
        "[URL]",
    ]
    for placeholder in replacements:
        if placeholder in html:
            html = html.replace(placeholder, tool_url)
            print(f"   🔧 Replaced placeholder '{placeholder}' with {tool_url}")

    # Also catch href="" (empty links) and fill them
    empty_href_count = html.count('href=""')
    if empty_href_count:
        html = html.replace('href=""', f'href="{tool_url}"')
        print(f"   🔧 Filled {empty_href_count} empty href(s) with {tool_url}")

    # Verify no placeholders remain
    remaining = [p for p in replacements if p in html]
    if remaining:
        print(f"   ⚠️  WARNING: {len(remaining)} placeholder(s) still in HTML after replacement")

    return html


def enforce_disclosure_position(html: str, article_type: str) -> str:
    """
    Ensure the affiliate disclosure appears AFTER the opening hook,
    not as the very first element in the article.

    The hook is the first <p> tag in the article (before any heading or div).
    We move the disclosure to sit directly after that first paragraph.

    authority_article type: no disclosure needed — remove if present.
    """
    disclosure_pattern = re.compile(
        r'<div class="affiliate-disclosure">.*?</div>',
        re.DOTALL | re.IGNORECASE
    )

    # For authority articles — remove any disclosure that crept in
    if article_type == "authority_article":
        if disclosure_pattern.search(html):
            html = disclosure_pattern.sub('', html)
            print(f"   🔧 Removed disclosure from authority_article")
        return html

    # Check if disclosure exists at all
    disclosure_match = disclosure_pattern.search(html)
    if not disclosure_match:
        # No disclosure — add one after the first paragraph
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

    # Find position of first <p> tag close (end of opening hook)
    first_p_end = html.find('</p>')
    disclosure_pos = disclosure_match.start()

    if first_p_end == -1:
        # No paragraph found — leave as is
        return html

    # If disclosure is BEFORE the first paragraph ends, it's in the wrong place
    if disclosure_pos < first_p_end:
        # Remove it from current position
        html = disclosure_pattern.sub('', html, count=1)
        # Re-find first paragraph end after removal
        first_p_end = html.find('</p>')
        if first_p_end != -1:
            html = html[:first_p_end + 4] + '\n' + disclosure_html + html[first_p_end + 4:]
            print(f"   🔧 Moved disclosure to after opening hook")

    return html


def enforce_cta_limit(html: str, tool_url: str, tool_name: str) -> str:
    """
    Ensure no more than 3 CTAs in the article.
    If more than 3 cta-button links exist, remove the extras (keep first 3).
    """
    cta_pattern = re.compile(
        r'<a[^>]+class="cta-button"[^>]*>.*?</a>',
        re.DOTALL | re.IGNORECASE
    )
    ctas = cta_pattern.findall(html)
    if len(ctas) > 3:
        # Remove CTAs beyond the first 3
        count = 0
        def replace_extra(m):
            nonlocal count
            count += 1
            if count <= 3:
                return m.group(0)
            return f'<a href="{tool_url}">{tool_name} →</a>'  # plain link, no button class
        html = cta_pattern.sub(replace_extra, html)
        print(f"   🔧 Reduced CTAs from {len(ctas)} to 3")
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
# ARTICLE STRUCTURES BY TYPE
# ─────────────────────────────────────────

def get_structure(article_type):
    structures = {
        "review": """
ARTICLE STRUCTURE — follow this exactly, in this order:

1. H1 TITLE
   Use the exact article title provided. Do not change it.

2. OPENING HOOK (no heading)
   2-3 sentences maximum. Open with the specific pain point this tool solves.
   Do NOT start with "In today's world" or "Are you looking for".
   Start with the problem or a surprising fact.
   Example: "Editing a 30-minute podcast used to mean 2 hours of work.
   Descript cuts that to 20 minutes by letting you edit audio like a Word doc."

3. AFFILIATE DISCLOSURE — MUST come immediately after the opening hook paragraphs
   Place this HERE, after the hook, before the Key Takeaways box.
   <div class="affiliate-disclosure">
   <p><strong>Disclosure:</strong> This article contains affiliate links.
   If you purchase through our links, we may earn a commission at no extra
   cost to you. We only recommend tools we've genuinely evaluated.</p>
   </div>

4. KEY TAKEAWAYS BOX
   <div class="key-takeaways">
   <h3>Key Takeaways</h3>
   <ul>
   <li><strong>Best for:</strong> [specific creator type]</li>
   <li><strong>Pricing:</strong> [starting price or free tier]</li>
   <li><strong>Standout feature:</strong> [one thing it does better than alternatives]</li>
   <li><strong>Verdict:</strong> [one sentence — buy it or skip it and why]</li>
   <li><strong>Try it:</strong> <a href="REPLACE_WITH_TOOL_URL">Visit [Tool Name] →</a></li>
   </ul>
   </div>

5. IS IT RIGHT FOR YOU? (quick decision table)
   <table class="decision-table">
   <thead><tr><th>✅ Choose [Tool] if...</th><th>❌ Skip [Tool] if...</th></tr></thead>
   <tbody>
   <tr><td>[specific reason]</td><td>[specific reason]</td></tr>
   </tbody>
   </table>

6. TABLE OF CONTENTS
   <nav class="toc"><h3>In This Review</h3><ul>
   <li><a href="#what-is">What Is [Tool]?</a></li>
   </ul></nav>

7. WHAT IS [TOOL NAME]? (H2, id="what-is")
   2 paragraphs. What it does, who built it, what problem it solves.
   Mention primary keyword naturally here.

8. KEY FEATURES (3-5 H2 sections, each with id attribute)
   One H2 per major feature. 2-3 paragraphs of real detail per section.
   Be specific — name the actual feature, explain how it works, give a real use case.
   No marketing language. Write like you tested it.

9. PRICING (H2, id="pricing")
   <table class="pricing-table">
   <thead><tr><th>Plan</th><th>Price</th><th>Best For</th></tr></thead>
   <tbody>...</tbody>
   </table>
   Use EXACT plan names and prices. Never vague ranges.
   If pricing unavailable: "verify current pricing at [tool URL]"
   Always mention free trial or free tier if available.

10. PROS AND CONS (H2, id="pros-cons")
    <div class="pros"><h3>Pros</h3><ul>...</ul></div>
    <div class="cons"><h3>Cons</h3><ul>...</ul></div>
    IMPORTANT: The h3 tags inside pros/cons divs must use plain text — no emojis.
    At least 3 pros and 3 specific cons.
    BAD con: "Learning curve" | GOOD con: "No mobile app — desktop only"
    BAD con: "Can be expensive" | GOOD con: "Free plan limited to 3 projects"

11. WHO IS [TOOL] FOR? (H2, id="who-is-it-for")
    TWO clear parts:
    Part 1 — WHO IT IS FOR: 3-4 specific creator types with reasons
    Part 2 — WHO IT IS NOT FOR: 2-3 specific creator types with reasons

12. HOW IT COMPARES (H2, id="alternatives")
    1-2 paragraphs comparing to 1-2 real alternatives.
    Add ONE internal link placeholder — ONLY if it fits naturally in the text flow.
    The internal link must make sense in context. If it feels forced, skip it.
    Format: [INTERNAL_LINK: descriptive topic]

13. THE VERDICT (H2, id="verdict")
    Answer all three:
    — Who should buy it?
    — Who should skip it?
    — One reason to choose it over alternatives?
    End with: <a href="REPLACE_WITH_TOOL_URL" class="cta-button">Try [Tool Name] →</a>

14. FAQ (H2, id="faq")
    4-5 questions people actually search. Each answer: 40-60 words below H3.
    One FAQ CTA is allowed if it fits naturally — not forced.
""",

        "alert": """
ARTICLE STRUCTURE — follow this exactly:

1. H1 TITLE (exact title provided)
2. OPENING HOOK (2-3 sentences, no heading)
3. AFFILIATE DISCLOSURE (immediately after hook)
   <div class="affiliate-disclosure">
   <p><strong>Disclosure:</strong> This article contains affiliate links.
   If you purchase through our links, we may earn a commission at no extra
   cost to you. We only recommend tools we've genuinely evaluated.</p>
   </div>
4. KEY TAKEAWAYS BOX
5. TABLE OF CONTENTS
6. WHAT JUST LAUNCHED (H2, id="what-launched")
7. KEY FEATURES (3-4 H2 sections)
8. PRICING (H2, id="pricing")
9. WHO IS IT FOR? (H2, id="who-is-it-for")
10. EARLY VERDICT (H2, id="verdict")
    CTA: <a href="REPLACE_WITH_TOOL_URL" class="cta-button">Try [Tool Name] →</a>
11. FAQ (3-4 questions, 40-60 word answers)
""",

        "authority_article": """
ARTICLE STRUCTURE — follow this exactly:

NO affiliate disclosure — this is informational content, not a review.
NO CTA buttons.

1. H1 TITLE (exact title provided)
2. OPENING HOOK (2-3 sentences, no heading)
3. KEY TAKEAWAYS BOX
4. TABLE OF CONTENTS
5. MAIN BODY (4-6 H2 sections with id attributes)
6. WHO THIS IS FOR (H2, id="who-this-is-for") — 1 paragraph
7. SUMMARY (H2, id="verdict") — concrete takeaway, 1-2 internal links
8. FAQ (4-5 questions, 40-60 word answers)
"""
    }
    return structures.get(article_type, structures["review"])


# ─────────────────────────────────────────
# BUILD THE FULL WRITING PROMPT
# ─────────────────────────────────────────

def build_prompt(tool_data, published_slugs=None):
    article_type = tool_data.get("article_type", "review")
    structure = get_structure(article_type)
    keyword_cluster = ", ".join(tool_data.get("keyword_cluster", []))
    secondary = ", ".join(tool_data.get("secondary_keywords", []))
    tool_url = get_tool_url(tool_data.get("tool_name", ""))

    # Build internal link context
    if published_slugs:
        slug_list = "\n".join(f"  - {s}" for s in published_slugs[:20])
        internal_link_context = f"""
EXISTING ARTICLES ON THIS SITE (use for internal link placeholders):
{slug_list}

INTERNAL LINK RULES — read carefully:
→ Add 2-3 [INTERNAL_LINK: description] placeholders ONLY where they flow naturally
→ A link is natural when: you mention a related tool by name, or directly
   compare this tool to another, or reference a related topic the reader
   would genuinely want to read next
→ A link is FORCED when: you insert it at the end of a sentence that has
   nothing to do with the linked topic, or tack it on as an afterthought
→ GOOD example: "...similar to what Krisp does for real-time calls.
   [INTERNAL_LINK: krisp-accent-conversion-review-podcasters]"
→ BAD example: "Dragon NaturallySpeaking has a steeper learning curve.
   [INTERNAL_LINK: best-voice-to-text-tools]" ← forced, doesn't flow
→ If you can't find a genuinely natural place for a link — skip it
→ Never add a link placeholder as the last sentence of a paragraph
   unless that sentence is genuinely about the linked topic
"""
    else:
        internal_link_context = "→ Use 2-3 descriptive topic placeholders where they flow naturally: [INTERNAL_LINK: best AI podcast tools comparison]\n→ Only add them where the link would genuinely help the reader\n"

    return f"""You are a world-class SEO article writer specialising in affiliate content for creator tools.

You write in the style of the best SEO content producers — Brian Dean's depth and structure,
Ann Handley's human voice, Gael Breton's affiliate conversion focus, and Ryan Law's
research-backed specificity. Your articles rank on page 1 and convert readers into buyers.

You are writing for Creators Must Have (creatorsmusthave.com) — an affiliate review site
for content creators: YouTubers, podcasters, bloggers, course creators, video editors,
and freelancers who build online. Brand positioning: "If it's on Creators Must Have,
it's worth buying." Every recommendation must feel earned, not paid for.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool name:      {tool_data['tool_name']}
Tool URL:       {tool_url}
Category:       {tool_data.get('tool_category', 'AI tool')}
Article type:   {article_type}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SEO REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Article title (use exactly):  {tool_data['article_title']}
URL slug (do not change):      {tool_data['url_slug']}
Primary keyword:   "{tool_data['primary_keyword']}"
Secondary keywords: {secondary}
Keyword cluster:    {keyword_cluster}
Target word count:  {tool_data['recommended_word_count']} words
Search intent:      {tool_data.get('search_intent', 'buyer')}

SERP GAP — your content advantage:
"{tool_data.get('serp_gap', '')}"
→ Build an entire section around this — it's why our article outranks the competition

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  CRITICAL: TOOL URL — READ THIS CAREFULLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The real URL for {tool_data['tool_name']} is: {tool_url}

You MUST use this exact URL everywhere in the article:
- In the Key Takeaways "Try it" link
- In the Verdict CTA button
- In any FAQ CTA
- In the pricing section reference

FORBIDDEN — never use these in the HTML you return:
✗ [TOOL_URL]
✗ [AFFILIATE_LINK]
✗ https://example.com
✗ href=""
✗ Any placeholder text instead of the real URL

If you are unsure of the URL — use exactly this: {tool_url}
This is a plain homepage link. Affiliate tracking is added later automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AFFILIATE DISCLOSURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{"NO disclosure needed — authority_article type. Do NOT include any disclosure." if article_type == "authority_article" else f"""REQUIRED for this article type. Place it AFTER the opening hook paragraphs.
NOT before the H1. NOT as the very first element. AFTER the hook.

Use this exact HTML:
<div class="affiliate-disclosure">
<p><strong>Disclosure:</strong> This article contains affiliate links.
If you purchase through our links, we may earn a commission at no extra
cost to you. We only recommend tools we've genuinely evaluated.</p>
</div>"""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WRITING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOICE: Write like a knowledgeable friend who tested this tool, not a marketer.
Direct, honest, specific. Grade 7 readability. Short sentences. Max 3 per paragraph.
Use "you" and "your". Conversational but authoritative.

BANNED PHRASES — never use:
"game-changer", "revolutionary", "cutting-edge", "state-of-the-art",
"powerful tool", "robust features", "seamless integration",
"in today's digital world", "in the fast-paced world of",
"in conclusion", "to summarize", "leverage", "utilize", "synergy"

FACTUAL ACCURACY:
- Never present unverified statistics as fact
- Unverified claims: "according to their website" or "based on launch information"
- Unknown pricing: "verify at {tool_url} as this may have changed"
- Never invent testimonials, case studies, or usage statistics

NO FAKE SOCIAL PROOF:
- Never write "thousands of creators use this"
- Never write "users report X% improvement" without a verified source
- Never invent reviews or word-of-mouth claims

EVERGREEN LANGUAGE:
- Never write "just launched", "this morning", "last week"
- Use: "as of [month year]" or "at launch" or "verify current pricing"

META-COMMENTARY BAN:
- Never reference your SEO strategy inside the article
- Never explain why you chose this topic
- Write as if you're a journalist who tested the tool

CTA RULES:
- Maximum 3 CTAs in the entire article
- One in Key Takeaways, one in Verdict, one in FAQ only if natural
- All CTAs must use the real URL: {tool_url}
- CTA text must be specific: "Try [Tool Name] →" or "Start free with [Tool Name] →"
- NEVER use generic text like "Check availability here" or "Click here"

PROS/CONS HEADING RULE:
- Inside <div class="pros"> use: <h3>Pros</h3>
- Inside <div class="cons"> use: <h3>Cons</h3>
- Plain text only in h3 — no emojis, no checkmarks

INTERNAL LINKS:
{internal_link_context}

SCANNING STRUCTURE: Every H2 needs at least one visual break (list, table, or bold callout).

FAQ FORMAT: Questions start with Is/Can/Does/How/What/Why. Answers: 40-60 words, single paragraph below H3.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HTML FORMATTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Return clean HTML only — no markdown, no code fences, no preamble
- Every H2 needs an id attribute
- Use: <h1>, <h2>, <h3>, <p>, <ul>, <ol>, <table>, <strong>, <em>
- Tables must have <thead> and <tbody>
- CTAs: <a href="{tool_url}" class="cta-button">text →</a>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARTICLE STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{structure}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SELF-CHECK BEFORE SUBMITTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ ALL links use the real URL: {tool_url} — zero placeholders remain
✓ Disclosure placed AFTER opening hook (review/alert only)
✓ Primary keyword in first 100 words
✓ Target word count: {tool_data['recommended_word_count']} words
✓ Pricing table with exact plan names and prices
✓ No banned phrases
✓ No fake social proof or invented statistics
✓ FAQ answers are 40-60 words each
✓ Maximum 3 CTAs total
✓ Verdict answers: who should buy, who should skip, one reason to choose it
✓ At least 3 specific cons — not generic
✓ "Who it is NOT for" section with 2-3 specific creator types
✓ Internal links flow naturally — not tacked on at sentence ends
✓ No h3 headings with emoji characters inside pros/cons divs
✓ CTA text is specific — never "Check availability here" or "Click here"

Write the complete article now.
Return ONLY the HTML — no explanation, no preamble, no markdown fences.
"""


# ─────────────────────────────────────────
# WRITE THE ARTICLE
# ─────────────────────────────────────────

def write_article(tool_data, published_slugs=None):
    """Send to Claude and get back a full HTML article."""
    prompt = build_prompt(tool_data, published_slugs)
    tool_url = get_tool_url(tool_data.get("tool_name", ""))
    article_type = tool_data.get("article_type", "review")

    print(f"   ✍️  Sending to Claude... (target: {tool_data['recommended_word_count']} words)")

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    article_html = response.content[0].text.strip()

    # Strip markdown fences if Claude added them
    if article_html.startswith("```"):
        lines = article_html.split("\n")
        article_html = "\n".join(lines[1:-1]).strip()

    # ── Post-processing: enforce rules Python-side ────────────────────────────
    tool_name = tool_data.get("tool_name", "")

    # 1. Replace all URL placeholders with the real tool URL
    article_html = enforce_tool_url(article_html, tool_url, tool_name)

    # 2. Fix disclosure position (after hook, not before it)
    article_html = enforce_disclosure_position(article_html, article_type)

    # 3. Enforce max 3 CTAs
    article_html = enforce_cta_limit(article_html, tool_url, tool_name)

    word_count = len(article_html.split())

    if word_count < 500:
        raise ValueError(f"Article too short ({word_count} words) — something went wrong")

    return article_html, word_count


# ─────────────────────────────────────────
# MAIN RUN
# ─────────────────────────────────────────

def run():
    print("\n✍️  Article Agent starting...\n")
    write_log(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Article Agent run")

    keyword_data = load_json(KEYWORD_DATA_FILE, {})
    handoffs = load_json(HANDOFFS_FILE, {})
    topics_used = load_json(TOPICS_USED_FILE, [])

    # Collect already-published slugs for smart internal linking
    published_slugs = [
        data.get("url_slug", key)
        for key, data in keyword_data.items()
        if data.get("status") in ("article_written", "published")
           and data.get("url_slug")
    ]

    # Find pending tools
    pending = [
        (key, data) for key, data in keyword_data.items()
        if data.get("status") == "pending_article"
    ]

    if not pending:
        print("   ℹ️  No tools waiting for articles.")
        write_log("No pending tools found.")
        return

    # Highest score first
    pending.sort(key=lambda x: x[1].get("tool_score", 0), reverse=True)

    print(f"📋 Found {len(pending)} tool(s) waiting for articles")
    print(f"📝 Writing up to {DAILY_CAP} articles this run\n")
    write_log(f"Found {len(pending)} pending. Cap: {DAILY_CAP}")

    written = 0

    for tool_key, tool_data in pending:
        if written >= DAILY_CAP:
            print(f"\n⏸️  Daily cap of {DAILY_CAP} reached.")
            write_log(f"Daily cap reached after {written} articles.")
            break

        tool_name = tool_data.get("tool_name", tool_key)
        article_type = tool_data.get("article_type", "review")
        score = tool_data.get("tool_score", "?")
        tool_url = get_tool_url(tool_name)

        print(f"🔧 Writing: {tool_name}")
        print(f"   Type: {article_type} | Score: {score} | URL: {tool_url}")
        write_log(f"\n### {tool_name} ({article_type}) — {tool_url}")

        try:
            article_html, word_count = write_article(tool_data, published_slugs)

            print(f"   ✅ Done — {word_count} words")
            write_log(f"Written: {word_count} words")

            # Save to handoffs
            handoff_key = tool_data.get("url_slug", tool_key)
            handoffs[handoff_key] = {
                "tool_name": tool_name,
                "tool_key": tool_key,
                "article_type": article_type,
                "article_title": tool_data.get("article_title", ""),
                "url_slug": tool_data.get("url_slug", ""),
                "primary_keyword": tool_data.get("primary_keyword", ""),
                "word_count": word_count,
                "article_html": article_html,
                "status": "pending_edit",
                "written_date": datetime.now().strftime("%Y-%m-%d"),
                "tool_score": score,
                "category": tool_data.get("tool_category", "ai-tools"),
                "tool_url": tool_url
            }

            # Mark as written in keyword_data
            keyword_data[tool_key]["status"] = "article_written"
            keyword_data[tool_key]["article_written_date"] = datetime.now().strftime("%Y-%m-%d")

            # Track topic
            slug = tool_data.get("url_slug", "")
            if slug and slug not in topics_used:
                topics_used.append(slug)

            written += 1
            if tool_data.get("url_slug") and tool_data["url_slug"] not in published_slugs:
                published_slugs.append(tool_data["url_slug"])
            print(f"   💾 Saved to handoffs.json\n")

        except Exception as e:
            print(f"   ❌ Failed: {e}")
            write_log(f"ERROR: {e}")
            continue

    # Save all files
    save_json(KEYWORD_DATA_FILE, keyword_data)
    save_json(HANDOFFS_FILE, handoffs)
    save_json(TOPICS_USED_FILE, topics_used)

    print(f"✅ Article Agent done. Wrote {written} article(s) this run.")
    write_log(f"Run complete. Articles written: {written}")

    if written > 0:
        remaining = len(pending) - written
        print(f"\n📬 Next step: run editor_agent.py → image_agent.py → publisher_agent.py")
        if remaining > 0:
            print(f"   {remaining} tool(s) still queued — run again tomorrow or increase DAILY_CAP.")


if __name__ == "__main__":
    run()