import json
import os
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
    Check if a URL is reachable and returns a real page (not a DNS error or
    Cloudflare block). Returns True if the URL is usable, False if broken.

    Uses HEAD first (fast), falls back to GET if HEAD is rejected.
    Accepts any 2xx or 3xx response — redirects are fine (tool may redirect
    to /app or /home). Only rejects connection errors and DNS failures.
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
        # HEAD returned 5xx — try GET
        r = _requests.get(url, headers=headers, timeout=timeout,
                          allow_redirects=True, stream=True)
        r.close()
        return r.status_code < 500
    except Exception:
        # DNS failure, connection refused, timeout — URL is broken
        return False


def get_tool_url(tool_name: str) -> str:
    """
    Get the homepage URL for a tool.

    Priority:
      1. Known URL from TOOL_URLS dict — verified live before use
      2. Partial name match in TOOL_URLS — verified live before use
      3. Common domain guesses (tool_name.com / .ai / .io) — each checked live
      4. Google search fallback — always works, affiliate_manager replaces later

    The live check prevents dead links ending up in published articles.
    Adds ~2-5 seconds per article but saves embarrassing broken links.
    """
    import re as _re

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
    slug = _re.sub(r"[^a-z0-9]", "", key)   # strip spaces/special chars
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

    # ── Step 4: safe fallback — Google search ─────────────────────────────────
    # Article still publishes. affiliate_manager.py will add real link later.
    print(f"   ⚠️  Could not verify a live URL for {tool_name} — using search fallback")
    return f"https://www.google.com/search?q={tool_name.replace(' ', '+')}+official+website"


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
   Example opening style: "Editing a 30-minute podcast used to mean 2 hours of work.
   Krisp's new accent conversion feature changes that for non-native English speakers
   who want to sound more natural on air."

3. AFFILIATE DISCLOSURE
   Place this AFTER the opening hook — not before it.
   <div class="affiliate-disclosure">
   <p><strong>Disclosure:</strong> This article contains affiliate links.
   If you purchase through our links, we may earn a commission at no extra
   cost to you. We only recommend tools we've genuinely evaluated.</p>
   </div>

4. KEY TAKEAWAYS BOX
   HTML format:
   <div class="key-takeaways">
   <h3>Key Takeaways</h3>
   <ul>
   <li><strong>Best for:</strong> [specific creator type]</li>
   <li><strong>Pricing:</strong> [starting price or free tier]</li>
   <li><strong>Standout feature:</strong> [one thing it does better than alternatives]</li>
   <li><strong>Verdict:</strong> [one sentence — buy it or skip it and why]</li>
   <li><strong>Try it:</strong> <a href="[TOOL_URL]">Visit [Tool Name] →</a></li>
   </ul>
   </div>

5. IS IT RIGHT FOR YOU? (quick decision table)
   HTML table with two columns: "Choose [Tool] if..." and "Skip [Tool] if..."
   3 rows each. Specific, honest, not generic.
   <table class="decision-table">
   <thead><tr><th>✅ Choose [Tool] if...</th><th>❌ Skip [Tool] if...</th></tr></thead>
   <tbody>
   <tr><td>[specific reason to buy]</td><td>[specific reason to skip]</td></tr>
   </tbody>
   </table>

6. TABLE OF CONTENTS
   HTML anchor links to each H2 section in the article.
   <nav class="toc"><h3>In This Review</h3><ul>
   <li><a href="#what-is">What Is [Tool]?</a></li>
   ... etc
   </ul></nav>

7. WHAT IS [TOOL NAME]? (H2, id="what-is")
   2 paragraphs. What it does, who built it, what problem it was designed to solve.
   Mention the primary keyword naturally here.

8. KEY FEATURES (3-5 H2 sections, each with id attribute)
   One H2 per major feature. Each section: 2-3 paragraphs of real detail.
   Use H3 for any sub-points within a feature.
   Be specific — name the actual feature, explain how it works, give a real use case.
   No marketing language. Write like you tested it.

9. PRICING (H2, id="pricing")
   Always include. HTML table format:
   <table class="pricing-table">
   <thead><tr><th>Plan</th><th>Price</th><th>Best For</th></tr></thead>
   <tbody>...</tbody>
   </table>
   Use EXACT plan names and prices from the tool's website (e.g. "Creator — $29/month").
   Never write vague ranges like "starts at around $X" — use real numbers.
   If exact pricing is unavailable: "Pricing starts at approximately $X/month —
   verify current pricing at [TOOL_URL] as plans may have changed."
   Always mention if there is a free trial or free tier.
   Always note if annual billing gives a significant discount.

10. PROS AND CONS (H2, id="pros-cons")
    Two HTML lists:
    <div class="pros"><h3>✅ Pros</h3><ul>...</ul></div>
    <div class="cons"><h3>❌ Cons</h3><ul>...</ul></div>
    Be honest. At least 3 pros and 3 real cons.
    Cons must be specific and documented — not vague:
    BAD: "Learning curve for new users"
    GOOD: "No native mobile app — desktop only"
    BAD: "Can be expensive"
    GOOD: "Free plan limited to 3 projects — most creators need the $29/month tier"
    BAD: "Some features missing"
    GOOD: "Cannot export to .mp4 on the basic plan — requires Pro tier"
    Each con must reflect a real, verifiable limitation of the tool.

11. WHO IS [TOOL] FOR? (H2, id="who-is-it-for")
    Concrete creator types. Not "content creators" — name them specifically:
    "YouTubers who upload 2+ times per week", "podcast editors working with
    non-native English speakers", "solo course creators on a budget".

    Structure this section as TWO clear parts:
    Part 1 — WHO IT IS FOR: 3-4 specific creator types with specific reasons
    Part 2 — WHO IT IS NOT FOR: 2-3 specific creator types with specific reasons
    Example of good "NOT for":
    - Creators on a tight budget who only need basic trimming (free tools do this)
    - Teams needing real-time collaboration (no multi-user editing)
    - Creators who primarily work on mobile (desktop-only workflow)
    This honesty builds trust and actually improves conversions — readers who
    stay are the right buyers.

12. HOW IT COMPARES (H2, id="alternatives")
    1-2 paragraphs. Compare to 1-2 real alternatives by name.
    Do not write a full comparison table — keep it brief.
    Add internal link placeholder: [INTERNAL_LINK: full comparison article topic]

13. THE VERDICT (H2, id="verdict")
    Must answer all three of these explicitly:
    — Who should buy it? (specific)
    — Who should skip it? (specific)
    — What is the one reason to choose it over alternatives?
    End with CTA: <a href="[TOOL_URL]" class="cta-button">Try [Tool Name] →</a>

14. FAQ (H2, id="faq")
    4-5 questions people actually search for about this tool.
    Format each answer as 40-60 words in a single paragraph directly below the H3.
    This format helps Google pull featured snippets.
    <h3>Is [Tool] worth it?</h3>
    <p>[40-60 word direct answer]</p>
""",

        "alert": """
ARTICLE STRUCTURE — follow this exactly, in this order:

1. H1 TITLE
   Use the exact article title provided. Do not change it.

2. OPENING HOOK (no heading)
   2-3 sentences. What just launched and why creators should pay attention.
   Create urgency without hype. Facts only.

3. AFFILIATE DISCLOSURE
   Place this AFTER the opening hook — not before it.
   <div class="affiliate-disclosure">
   <p><strong>Disclosure:</strong> This article contains affiliate links.
   If you purchase through our links, we may earn a commission at no extra
   cost to you. We only recommend tools we've genuinely evaluated.</p>
   </div>

4. KEY TAKEAWAYS BOX
   <div class="key-takeaways">
   <h3>Quick Summary</h3>
   <ul>
   <li><strong>What launched:</strong> [one sentence]</li>
   <li><strong>Best for:</strong> [specific creator type]</li>
   <li><strong>Pricing:</strong> [starting price or free tier]</li>
   <li><strong>Why it matters:</strong> [one sentence]</li>
   <li><strong>Try it:</strong> <a href="[TOOL_URL]">Visit [Tool Name] →</a></li>
   </ul>
   </div>

5. TABLE OF CONTENTS
   HTML anchor links to each H2 section.

6. WHAT JUST LAUNCHED (H2, id="what-launched")
   2 paragraphs. What is this tool, what does it do, who built it.
   Mention primary keyword naturally.

7. KEY FEATURES (3-4 H2 sections)
   The most important capabilities. Real detail, not a feature list.
   Each feature: what it does + why a creator would care.

8. PRICING (H2, id="pricing")
   HTML pricing table. Note if early-bird pricing or launch discount applies.

9. WHO IS IT FOR? (H2, id="who-is-it-for")
   Specific creator types. Also note who should wait for a full review.

10. EARLY VERDICT (H2, id="verdict")
    Honest assessment based on launch information.
    Be clear this is an early look, not a full tested review.
    Answer: is it worth trying now or waiting?
    CTA: <a href="[TOOL_URL]" class="cta-button">Try [Tool Name] →</a>

11. FAQ (H2, id="faq")
    3-4 questions early adopters would actually ask.
    Each answer: 40-60 words directly below the H3.
""",

        "authority_article": """
ARTICLE STRUCTURE — follow this exactly, in this order:

NO affiliate disclosure in this article type — this is an informational
authority piece, not a product review with affiliate links.

1. H1 TITLE
   Use the exact article title provided. Do not change it.

2. OPENING HOOK (no heading)
   2-3 sentences. State the problem or knowledge gap this article solves.
   Do NOT start with "In today's world" or "Are you looking for".
   Start with a surprising fact, a common misconception, or the exact
   question the reader typed into Google.

3. KEY TAKEAWAYS BOX
   <div class="key-takeaways">
   <h3>Key Takeaways</h3>
   <ul>
   <li><strong>Bottom line:</strong> [one sentence summary of the answer]</li>
   <li>[Key point 1]</li>
   <li>[Key point 2]</li>
   <li>[Key point 3]</li>
   </ul>
   </div>

4. TABLE OF CONTENTS
   HTML anchor links to each H2 section.

5. MAIN BODY (4-6 H2 sections, each with id attribute)
   Each section covers one key sub-topic. Be comprehensive and specific.
   Use H3 for sub-points. Include at least one table, list, or visual
   break per H2 section.

6. WHO THIS IS FOR (H2, id="who-this-is-for")
   Specific creator types who would benefit from this information.
   Keep this brief — 1 paragraph maximum.

7. THE VERDICT / SUMMARY (H2, id="verdict")
   Concrete takeaway. What should the reader do with this information?
   No CTA button — this is not a product review.
   Add 1-2 relevant internal links here.

8. FAQ (H2, id="faq")
   4-5 questions people actually search for on this topic.
   Each answer: 40-60 words in a single paragraph directly below the H3.
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

    # Build internal link context from already-published articles
    if published_slugs:
        slug_list = "\n".join(f"  - {s}" for s in published_slugs[:20])
        internal_link_context = f"""
EXISTING ARTICLES ON THIS SITE (use for internal link placeholders):
{slug_list}
→ Where relevant, reference these real slugs in [INTERNAL_LINK: slug] placeholders
→ Example: [INTERNAL_LINK: krisp-accent-conversion-review-podcasters]
→ If none are relevant, use descriptive topic placeholders as normal
"""
    else:
        internal_link_context = "→ Use descriptive topic placeholders: [INTERNAL_LINK: best AI podcast tools comparison]\n"

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
SEO REQUIREMENTS — NON-NEGOTIABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Article title (use exactly):  {tool_data['article_title']}
URL slug (do not change):      {tool_data['url_slug']}

Primary keyword:   "{tool_data['primary_keyword']}"
→ Must appear in the first 100 words
→ Use naturally 3-4 times total — never stuffed
→ Use in at least one H2 heading

Secondary keywords (use each at least once):
{secondary}

Keyword cluster (weave throughout naturally):
{keyword_cluster}

Target word count:   {tool_data['recommended_word_count']} words
Search intent:       {tool_data.get('search_intent', 'buyer')}

SERP GAP — your content advantage:
"{tool_data.get('serp_gap', '')}"
→ This is what NO other article on page 1 covers
→ Build an entire section or subsection around this
→ This is why our article will outrank the competition

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPORTANT: LINKS IN THIS ARTICLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The tool URL for ALL CTAs and links in this article is:
{tool_url}

Replace every instance of [TOOL_URL] with: {tool_url}

This is a direct homepage link — not an affiliate link yet.
Affiliate tracking will be added later by our affiliate manager.
Every CTA button must link to this URL — never leave [TOOL_URL] as a placeholder.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AFFILIATE DISCLOSURE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{"NO disclosure needed — this is an authority_article (informational content, no affiliate links). Do NOT include any affiliate disclosure anywhere in this article." if article_type == "authority_article" else """This article needs an affiliate disclosure. Follow the ARTICLE STRUCTURE section exactly for placement — the disclosure goes AFTER the opening hook, not before the H1 title.

Use this exact wording — do not modify it:

<div class="affiliate-disclosure">
<p><strong>Disclosure:</strong> This article contains affiliate links.
If you purchase through our links, we may earn a commission at no extra
cost to you. We only recommend tools we've genuinely evaluated.</p>
</div>

This is a legal requirement."""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WRITING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOICE & TONE:
- Write like a knowledgeable friend who tested this tool, not a marketer
- Direct, honest, specific — if something is limited, say so
- Conversational but authoritative — Grade 7 readability target
- Short sentences. Maximum 3 sentences per paragraph.
- Use "you" and "your" — write directly to the reader

BANNED PHRASES — never use these under any circumstances:
- "game-changer", "revolutionary", "cutting-edge", "state-of-the-art"
- "powerful tool", "robust features", "seamless integration"
- "in today's digital world", "in the fast-paced world of"
- "in conclusion", "to summarize", "it goes without saying"
- "leverage", "utilize", "synergy"
- Any phrase that sounds like it came from a press release

FACTUAL ACCURACY RULES — critical:
- Never present unverified statistics as fact
- If a claim is unverified use: "according to their website" or
  "based on launch information" — never invent numbers
- If pricing is unknown: "Pricing starts at approximately $X/month —
  verify at {tool_url} as this may have changed since publishing"
- Never invent user testimonials, case studies, or usage statistics
- If you are uncertain about a feature, say "according to [tool name]'s
  website" — never state uncertain things as confirmed facts

NO FAKE SOCIAL PROOF — strictly forbidden:
- Never write "thousands of creators use this"
- Never write "users report X% improvement" unless you have a verified source
- Never write "early users say..." for a brand new tool with no users yet
- Never write "creators report saving X hours" without a real attributed source
- Never invent reviews, testimonials, or word-of-mouth claims
- In the Pros section: if you include a performance claim, it MUST be attributed
- If there are no real user reports yet — say the tool is new and
  real-world results aren't available yet. That's honest and builds trust.

EVERGREEN LANGUAGE RULES:
- Never write "this tool just launched last week"
- Never write "as of this morning" or "just announced"
- For time references use: "as of [month year]" or "at launch" or
  "verify current pricing" — articles stay live for years
- Never reference current events that will date the article

META-COMMENTARY BAN — never break the fourth wall:
- Never write "since no reviews exist yet, we..."
- Never write "we're the first to cover this tool"
- Never write "since this is one of the first comprehensive reviews..."
- Never reference your SEO strategy inside the article
- Never explain why you chose this topic
- Just write the article as if you're a journalist who tested the tool

BRAND VOICE — Creators Must Have:
Good: "Coursekit cuts student support time in half for course creators who've scaled past 50 students."
Bad: "Coursekit is a powerful, revolutionary tool that leverages AI to seamlessly transform the way course creators interact with students."

CTA PLACEMENT RULES:
- One CTA in the Key Takeaways box
- One CTA at the end of the Verdict section
- One CTA in the FAQ if it fits naturally — not forced
- No more than 3 CTAs total in the entire article
- Never add CTAs mid-article after every section
- All CTAs must use the real tool URL: {tool_url}

CONVERSION RULES:
- Put the decision-making tools (Key Takeaways, Is It Right For You table) EARLY
- The verdict must be specific — not "it depends"
- Pros must be specific benefits, not feature names
- Cons must be real and honest — vague cons destroy trust

FEATURED SNIPPET RULES:
- FAQ answers must be 40-60 words in a single paragraph below the H3
- Write FAQ answers as direct, complete responses

INTERNAL LINKS:
- Add 2-3 [INTERNAL_LINK: ...] placeholders where related articles fit naturally
{internal_link_context}

SCANNING STRUCTURE RULE:
- Every H2 section must contain at least one visual break
- Visual breaks are: bullet list, numbered list, table, or a <strong> callout sentence
- Pure paragraph walls are not acceptable — readers scan on mobile before they read

PEOPLE ALSO ASK — FAQ TARGETING:
- FAQ questions must mirror how people actually type into Google
- Good: "Is Coursekit worth it for small course creators?"
- Bad: "What are the benefits of using Coursekit?"
- Every FAQ question should start with: Is, Can, Does, How, What, Why, or How much

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HTML FORMATTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Return clean HTML only — no markdown, no code fences, no preamble
- Every H2 needs an id attribute for the table of contents
- Use: <h1>, <h2>, <h3>, <p>, <ul>, <ol>, <table>, <strong>, <em>
- Tables must have <thead> and <tbody>
- CTAs: <a href="{tool_url}" class="cta-button">text →</a>
- Key Takeaways: <div class="key-takeaways">
- Decision table: <table class="decision-table">
- Pricing table: <table class="pricing-table">
- Pros: <div class="pros"> | Cons: <div class="cons">
- Disclosure: <div class="affiliate-disclosure"> (after opening hook, review/alert only)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARTICLE STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{structure}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SELF-CHECK BEFORE SUBMITTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before returning the article, silently verify:
✓ Affiliate disclosure placed AFTER the opening hook (review/alert only — not in authority articles)
✓ Primary keyword appears in the first 100 words
✓ Target word count reached: {tool_data['recommended_word_count']} words
✓ Pricing table is included
✓ No banned phrases used anywhere
✓ No fake social proof or invented statistics
✓ No meta-commentary about SEO or article strategy
✓ No time-sensitive language that will date the article
✓ FAQ answers are 40-60 words each
✓ Maximum 3 CTAs in the entire article
✓ All CTAs link to: {tool_url} — NO [TOOL_URL] placeholders left in the HTML
✓ 2-3 internal link placeholders included
✓ Verdict answers: who should buy, who should skip, one reason to choose it
✓ Pricing table has EXACT plan names and prices — not vague ranges
✓ At least 3 cons — each one specific and verifiable, not generic
✓ "Who it is NOT for" section has at least 2 specific creator types with reasons
✓ No section sounds like a brochure — every claim is grounded in specifics

If any check fails, fix it before returning.

Write the complete article now.
Return ONLY the HTML — no explanation, no preamble, no markdown fences.
"""


# ─────────────────────────────────────────
# WRITE THE ARTICLE
# ─────────────────────────────────────────

def write_article(tool_data, published_slugs=None):
    """Send to Claude and get back a full HTML article."""
    prompt = build_prompt(tool_data, published_slugs)

    print(f"   ✍️  Sending to Claude... (target: {tool_data['recommended_word_count']} words)")

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    article_html = response.content[0].text.strip()

    # Strip markdown fences if Claude added them anyway
    if article_html.startswith("```"):
        lines = article_html.split("\n")
        article_html = "\n".join(lines[1:-1]).strip()

    # Safety net — replace any leftover [TOOL_URL] placeholders
    tool_url = get_tool_url(tool_data.get("tool_name", ""))
    article_html = article_html.replace("[TOOL_URL]", tool_url)
    article_html = article_html.replace("[AFFILIATE_LINK]", tool_url)

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
            print(f"\n⏸️  Daily cap of {DAILY_CAP} reached. Remaining tools queued for next run.")
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

            # Save to handoffs for Editor Agent / Publisher Agent
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

            # Track topic so we never repeat it
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
        print(f"\n📬 Next step: run publisher_agent.py to save as WordPress drafts.")
        if remaining > 0:
            print(f"   {remaining} tool(s) still queued — run again tomorrow or increase DAILY_CAP.")


if __name__ == "__main__":
    run()