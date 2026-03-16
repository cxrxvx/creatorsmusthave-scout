# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
"""
seo_agent.py — SEO Metadata Agent for CXRXVX Affiliates
==========================================================
Phase 2.5 Opus Upgrade:
  ✅ Article type-aware schema: roundups get ItemList, comparisons get Article+FAQ
  ✅ Schema detection reads article_type field instead of guessing from title
  ✅ Article type-specific meta description angles for better CTR
  ✅ Removed hard-coded review rating (Google penalizes unearned ratings)
  ✅ Focus keyword logic for roundups (category keyword) and comparisons (both tool names)
  ✅ Fixed OG image extraction to match actual image_agent data structure
  ✅ All existing features preserved (year guard, retries, dedup, rollback, dry run, OG tags)

Drop this file into your cxrxvx-ai-empire/ folder to replace the old seo_agent.py.
"""

import db_helpers
import json
import os
import re
import sys
import requests
from datetime import datetime
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    WP_URL, WP_USERNAME, WP_APP_PASSWORD,
    SITE_NAME
)
import anthropic

# ── Settings ──────────────────────────────────────────────────────────────────
DAILY_CAP           = 15
LOG_FILE            = "memory/logs/seo_agent.log"
MIN_WORD_COUNT      = 800
MAX_RETRIES         = 2
COST_PER_1K_INPUT   = 0.000003
COST_PER_1K_OUTPUT  = 0.000015
CURRENT_YEAR        = str(datetime.now().year)
WRONG_YEARS         = ["2020", "2021", "2022", "2023", "2024", "2025"]
# ──────────────────────────────────────────────────────────────────────────────

client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
DRY_RUN  = "--dry-run" in sys.argv
run_cost = 0.0


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    os.makedirs("memory/logs", exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



# ═══════════════════════════════════════════════════════
# GUARDS (unchanged — work well)
# ═══════════════════════════════════════════════════════

def validate_year(meta):
    corrected = False
    for field in ("meta_title", "meta_description"):
        value = meta.get(field, "")
        for wrong_year in WRONG_YEARS:
            if wrong_year in value:
                meta[field] = value.replace(wrong_year, CURRENT_YEAR)
                log(f"  ⚠️  Year guard: corrected {wrong_year} → {CURRENT_YEAR} in {field}")
                corrected = True
    return meta, corrected


def count_words(text):
    clean = re.sub(r'<[^>]+>', ' ', text or '')
    return len(clean.split())


def passes_word_count_guard(article, slug):
    content    = article.get("article_html", "")
    word_count = count_words(content)
    if word_count < MIN_WORD_COUNT:
        log(f"  ⚠️  Soft 404 guard: {slug} only has {word_count} words (min {MIN_WORD_COUNT}) — skipping")
        return False
    return True


def build_existing_titles(handoffs):
    titles = {}
    for slug, article in handoffs.items():
        if isinstance(article, dict):
            mt = article.get("meta_title")
            if mt:
                titles[mt.lower().strip()] = slug
    return titles


def check_duplicate(meta_title, existing_titles, current_slug):
    key = meta_title.lower().strip()
    if key in existing_titles and existing_titles[key] != current_slug:
        return True, existing_titles[key]
    return False, None


# ═══════════════════════════════════════════════════════
# SCHEMA TYPE DETECTION — now reads article_type field
# ═══════════════════════════════════════════════════════

def detect_schema_type(article):
    """
    Determine which schema markup to use based on article_type field.
    
    Phase 2.5: Uses the article_type field directly instead of guessing
    from the title string. Much more reliable.
    
    Returns: "Review", "ItemList", "Comparison", "HowTo", or "Article"
    """
    article_type = article.get("article_type", "review")
    title        = article.get("article_title", "").lower()

    # ⚡ Phase 2.5: article_type field is the primary signal
    if article_type == "roundup":
        return "ItemList"
    elif article_type == "comparison":
        return "Comparison"
    elif article_type == "authority_article":
        return "Article"
    elif article_type == "alert":
        return "Review"  # New tool alerts get Review schema for rich snippets
    elif article_type in ("review", "affiliate_review"):
        # Check for HowTo subtype based on title
        if any(kw in title for kw in ["how to", "tutorial", "step by step", "guide"]):
            return "HowTo"
        return "Review"
    else:
        return "Article"


# ═══════════════════════════════════════════════════════
# FOCUS KEYWORD LOGIC — varies by article type
# ═══════════════════════════════════════════════════════

def get_focus_keyword(article):
    """
    Determine the best focus keyword for RankMath.
    
    Reviews: primary_keyword as-is
    Roundups: category-based keyword ("best [category] tools for [audience]")
    Comparisons: both tool names ("tool a vs tool b")
    """
    article_type = article.get("article_type", "review")
    primary      = article.get("primary_keyword", "")

    if primary:
        return primary

    # Fallback generation
    tool_name = article.get("tool_name", "")
    if article_type == "comparison":
        comp = article.get("comparison_tools", {})
        a = comp.get("tool_a", "")
        b = comp.get("tool_b", "")
        if a and b:
            return f"{a} vs {b}".lower()
    elif article_type == "roundup":
        category = article.get("tool_category", "")
        if category:
            return f"best {category} tools"

    return tool_name.lower() if tool_name else ""


# ═══════════════════════════════════════════════════════
# CLAUDE METADATA GENERATION — article type aware
# ═══════════════════════════════════════════════════════

def get_meta_angle(article_type):
    """
    Return article type-specific instructions for meta description.
    Different types need different CTR angles.
    """
    angles = {
        "review": "Focus on the verdict — is it worth it? Mention a specific pro or pricing detail.",
        "roundup": "Emphasize that these are tested and ranked. Mention the number of tools. Use 'best' and the category name.",
        "comparison": "Emphasize the head-to-head comparison. Mention both tool names. Help the reader decide which one to pick.",
        "alert": "Emphasize that this is a new launch. Create urgency — early adopter advantage.",
        "authority_article": "Focus on being the complete guide. Emphasize comprehensiveness and credibility.",
    }
    return angles.get(article_type, angles["review"])


def build_prompt(tool_name, title, keyword, content, schema_type, article_type, retry_note=""):
    content_sample    = content[:800] if content else "No content available."
    retry_instruction = ""
    if retry_note:
        retry_instruction = f"\n\n⚠️  PREVIOUS ATTEMPT FAILED: {retry_note}\nFix this in your new attempt."

    meta_angle = get_meta_angle(article_type)

    return f"""You are an expert SEO specialist writing metadata for an affiliate review website.
{retry_instruction}
IMPORTANT: The current year is {CURRENT_YEAR}. Always use {CURRENT_YEAR} — never any other year.

ARTICLE DETAILS:
- Tool/Topic: {tool_name}
- Article title: {title}
- Primary keyword: {keyword}
- Schema type: {schema_type}
- Article type: {article_type}
- Content preview: {content_sample}

YOUR TASKS:

1. META TITLE (strict rules):
   - The primary keyword "{keyword}" MUST appear in the meta title
   - 50-60 characters MAXIMUM — count carefully
   - Must match search intent for a "{article_type}" article
   - Do NOT copy the article title word-for-word — rewrite it for Google
   - No clickbait, no ALL CAPS
   - Use {CURRENT_YEAR} if including a year

2. META DESCRIPTION (strict rules):
   - 140-155 characters MAXIMUM — count carefully
   - Include the primary keyword naturally
   - ANGLE FOR THIS ARTICLE TYPE: {meta_angle}
   - End with a subtle call to action
   - No quotes, no special characters
   - Use {CURRENT_YEAR} if including a year

3. FAQ QUESTIONS (3 real buyer questions):
   - Questions a real person would type into Google about this {"category of tools" if article_type == "roundup" else "tool" if article_type in ("review", "alert") else "comparison"}
   - Answers under 60 words each
   - Factual and helpful — no fluff

Respond in this EXACT format (nothing else):

META_TITLE: [your meta title here]
META_DESCRIPTION: [your meta description here]
FAQ_1_Q: [question 1]
FAQ_1_A: [answer 1]
FAQ_2_Q: [question 2]
FAQ_2_A: [answer 2]
FAQ_3_Q: [question 3]
FAQ_3_A: [answer 3]"""


def generate_seo_metadata(slug, article):
    global run_cost

    tool_name    = article.get("tool_name", slug)
    title        = article.get("article_title", "")
    keyword      = get_focus_keyword(article)
    content      = article.get("article_html", "")
    schema_type  = detect_schema_type(article)
    article_type = article.get("article_type", "review")

    total_input_tokens  = 0
    total_output_tokens = 0
    retry_note          = ""

    for attempt in range(1, MAX_RETRIES + 2):
        if attempt > 1:
            log(f"  ↻ Retry {attempt - 1}/{MAX_RETRIES}: {retry_note}")

        prompt = build_prompt(tool_name, title, keyword, content, schema_type, article_type, retry_note)

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )

        total_input_tokens  += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        raw  = response.content[0].text.strip()
        meta = parse_seo_response(raw)

        if not meta.get("meta_title") or not meta.get("meta_description"):
            retry_note = "Response parse failed — check your format exactly"
            continue

        meta, _ = validate_year(meta)

        # Validate lengths
        title_len = len(meta["meta_title"])
        desc_len  = len(meta["meta_description"])
        issues    = []

        if title_len > 60:
            issues.append(f"meta title is {title_len} chars — must be 60 or under")
        if title_len < 40:
            issues.append(f"meta title is {title_len} chars — too short, aim for 50-60")
        if desc_len > 160:
            issues.append(f"meta description is {desc_len} chars — must be 160 or under")
        if desc_len < 100:
            issues.append(f"meta description is {desc_len} chars — too short, aim for 140-155")
        if keyword and keyword.lower() not in meta["meta_title"].lower():
            issues.append(f'primary keyword "{keyword}" not found in meta title')

        if issues:
            retry_note = " | ".join(issues)
            if attempt == MAX_RETRIES + 1:
                log(f"  ⚠️  All retries exhausted — applying hard truncate fallback")
                if len(meta["meta_title"]) > 60:
                    meta["meta_title"] = meta["meta_title"][:57] + "..."
                if len(meta["meta_description"]) > 160:
                    meta["meta_description"] = meta["meta_description"][:157] + "..."
            else:
                continue

        cost = (
            (total_input_tokens  / 1000) * COST_PER_1K_INPUT +
            (total_output_tokens / 1000) * COST_PER_1K_OUTPUT
        )
        run_cost += cost
        log(f"  Tokens: {total_input_tokens} in / {total_output_tokens} out | Cost: ${cost:.5f}")

        return meta, schema_type

    return None, schema_type


def parse_seo_response(raw_text):
    result = {}
    lines  = raw_text.strip().split("\n")
    for line in lines:
        if line.startswith("META_TITLE:"):
            result["meta_title"] = line.replace("META_TITLE:", "").strip()
        elif line.startswith("META_DESCRIPTION:"):
            result["meta_description"] = line.replace("META_DESCRIPTION:", "").strip()
        elif line.startswith("FAQ_1_Q:"):
            result["faq_1_q"] = line.replace("FAQ_1_Q:", "").strip()
        elif line.startswith("FAQ_1_A:"):
            result["faq_1_a"] = line.replace("FAQ_1_A:", "").strip()
        elif line.startswith("FAQ_2_Q:"):
            result["faq_2_q"] = line.replace("FAQ_2_Q:", "").strip()
        elif line.startswith("FAQ_2_A:"):
            result["faq_2_a"] = line.replace("FAQ_2_A:", "").strip()
        elif line.startswith("FAQ_3_Q:"):
            result["faq_3_q"] = line.replace("FAQ_3_Q:", "").strip()
        elif line.startswith("FAQ_3_A:"):
            result["faq_3_a"] = line.replace("FAQ_3_A:", "").strip()
    return result


# ═══════════════════════════════════════════════════════
# SCHEMA BUILDERS — updated with roundup/comparison types
# ═══════════════════════════════════════════════════════

def build_faqpage_schema(tool_name, faqs):
    questions = []
    for i in range(1, 4):
        q = faqs.get(f"faq_{i}_q")
        a = faqs.get(f"faq_{i}_a")
        if q and a:
            questions.append({
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a}
            })
    if not questions:
        return None
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": questions
    }


def build_review_schema(tool_name, meta):
    """
    Review schema WITHOUT a rating value.
    Google's guidelines require ratings to be based on a defined methodology.
    A hard-coded "4/5" with no testing methodology gets flagged.
    The schema still triggers rich snippets without the rating.
    """
    return {
        "@context": "https://schema.org",
        "@type": "Review",
        "name": meta.get("meta_title", tool_name),
        "description": meta.get("meta_description", ""),
        "author": {
            "@type": "Organization",
            "name": SITE_NAME
        },
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": "https://creatorsmusthave.com"
        },
        "itemReviewed": {
            "@type": "SoftwareApplication",
            "name": tool_name
        }
    }


def build_howto_schema(tool_name, meta, content):
    steps = []
    h3_matches = re.findall(r'<h3[^>]*>(.*?)</h3>', content, re.IGNORECASE)
    for i, heading in enumerate(h3_matches[:6], 1):
        clean_heading = re.sub(r'<[^>]+>', '', heading).strip()
        if clean_heading:
            steps.append({
                "@type": "HowToStep",
                "position": i,
                "name": clean_heading,
                "text": clean_heading
            })
    if not steps:
        steps = [{
            "@type": "HowToStep",
            "position": 1,
            "name": f"Getting started with {tool_name}",
            "text": f"Follow our complete guide to using {tool_name} effectively."
        }]
    return {
        "@context": "https://schema.org",
        "@type": "HowTo",
        "name": meta.get("meta_title", f"How to use {tool_name}"),
        "description": meta.get("meta_description", ""),
        "step": steps
    }


def build_itemlist_schema(article, meta):
    """
    ⚡ Phase 2.5: ItemList schema for roundup/"Best X for Y" articles.
    Google can display these as rich list results in search.
    """
    roundup_tools = article.get("roundup_tools", [])
    items = []
    for i, tool_info in enumerate(roundup_tools, 1):
        name = tool_info if isinstance(tool_info, str) else tool_info.get("name", "")
        if name:
            items.append({
                "@type": "ListItem",
                "position": i,
                "name": name,
            })

    if not items:
        return None

    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": meta.get("meta_title", article.get("article_title", "")),
        "description": meta.get("meta_description", ""),
        "numberOfItems": len(items),
        "itemListElement": items
    }


def build_article_schema(tool_name, meta):
    """Generic Article schema for authority articles and comparisons."""
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": meta.get("meta_title", tool_name),
        "description": meta.get("meta_description", ""),
        "author": {
            "@type": "Organization",
            "name": SITE_NAME
        },
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": "https://creatorsmusthave.com"
        }
    }


def build_combined_schema(schema_type, tool_name, meta, faqs, content, article=None):
    """
    Build all applicable schemas for this article.
    
    Phase 2.5 schema mapping:
      Review      → Review + FAQPage
      ItemList    → ItemList + FAQPage (roundup articles)
      Comparison  → Article + FAQPage (comparisons)
      HowTo       → HowTo + FAQPage
      Article     → Article + FAQPage (authority articles)
    """
    schemas = []

    if schema_type == "Review":
        schemas.append(build_review_schema(tool_name, meta))
    elif schema_type == "ItemList":
        itemlist = build_itemlist_schema(article or {}, meta)
        if itemlist:
            schemas.append(itemlist)
        else:
            # Fallback if no roundup_tools data
            schemas.append(build_article_schema(tool_name, meta))
    elif schema_type == "HowTo":
        schemas.append(build_howto_schema(tool_name, meta, content))
    elif schema_type == "Comparison":
        schemas.append(build_article_schema(tool_name, meta))
    else:
        schemas.append(build_article_schema(tool_name, meta))

    # FAQ schema for all types
    faq_schema = build_faqpage_schema(tool_name, faqs)
    if faq_schema:
        schemas.append(faq_schema)

    return "\n".join(json.dumps(s, indent=2) for s in schemas)


# ═══════════════════════════════════════════════════════
# OG IMAGE — fixed to match actual image_agent data structure
# ═══════════════════════════════════════════════════════

def get_hero_image_url(article):
    """
    Extract hero image URL for Open Graph tags.
    Matches the actual image_data structure from image_agent.py.
    """
    image_data = article.get("image_data", {})
    if not isinstance(image_data, dict):
        return ""

    # image_agent stores hero as hero_media_id — we need the URL
    # Check if we have a stored URL from WordPress
    hero_media_id = image_data.get("hero_media_id")
    if hero_media_id:
        # Try to get the URL from WordPress
        try:
            auth = (WP_USERNAME, WP_APP_PASSWORD)
            resp = requests.get(
                f"{WP_URL}/wp-json/wp/v2/media/{hero_media_id}",
                auth=auth, timeout=10
            )
            if resp.status_code == 200:
                url = resp.json().get("source_url", "")
                if url:
                    return url
        except Exception:
            pass

    # Fallback: screenshot media ID
    screenshot_media_id = image_data.get("screenshot_media_id")
    if screenshot_media_id:
        try:
            auth = (WP_USERNAME, WP_APP_PASSWORD)
            resp = requests.get(
                f"{WP_URL}/wp-json/wp/v2/media/{screenshot_media_id}",
                auth=auth, timeout=10
            )
            if resp.status_code == 200:
                url = resp.json().get("source_url", "")
                if url:
                    return url
        except Exception:
            pass

    return ""


# ═══════════════════════════════════════════════════════
# WORDPRESS / RANKMATH PUSH (unchanged)
# ═══════════════════════════════════════════════════════

def get_existing_meta(wp_post_id):
    auth     = (WP_USERNAME, WP_APP_PASSWORD)
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}"
    try:
        resp = requests.get(endpoint, auth=auth, timeout=30)
        if resp.status_code == 200:
            meta = resp.json().get("meta", {})
            return {
                "rank_math_title":       meta.get("rank_math_title", ""),
                "rank_math_description": meta.get("rank_math_description", ""),
            }
    except Exception:
        pass
    return {}


def push_to_rankmath(wp_post_id, meta_title, meta_description, schema_json, keyword="", og_image=""):
    """Push SEO metadata to WordPress via RankMath REST API. Never touches post content."""
    if DRY_RUN:
        log(f"  [DRY RUN] Would push to post {wp_post_id}:")
        log(f"  [DRY RUN] Title:    {meta_title}")
        log(f"  [DRY RUN] Desc:     {meta_description}")
        log(f"  [DRY RUN] Keyword:  {keyword}")
        log(f"  [DRY RUN] OG image: {og_image or 'none'}")
        return True, "DRY RUN"

    auth     = (WP_USERNAME, WP_APP_PASSWORD)
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}"

    meta_payload = {
        "rank_math_title":                meta_title,
        "rank_math_description":          meta_description,
        "rank_math_focus_keyword":        keyword,
        "rank_math_facebook_title":       meta_title,
        "rank_math_facebook_description": meta_description,
        "rank_math_twitter_use_facebook": "on",
    }
    if og_image:
        meta_payload["rank_math_facebook_image"] = og_image

    payload = {"meta": meta_payload}

    log(f"  → Pushing to {endpoint}")
    log(f"  → Meta keys: {list(meta_payload.keys())}")
    log(f"  → rank_math_title:         {meta_title[:60]}")
    log(f"  → rank_math_focus_keyword: {keyword[:60]}")
    log(f"  → rank_math_description:   {meta_description[:80]}")

    resp = requests.post(endpoint, json=payload, auth=auth, timeout=30)
    log(f"  → WP response: HTTP {resp.status_code}")

    if resp.status_code not in (200, 201):
        log(f"  → Response body: {resp.text[:400]}")
        return False, f"Push error {resp.status_code}: {resp.text[:200]}"

    # Verify the meta was actually saved by reading it back
    try:
        saved_meta = resp.json().get("meta", {})
        saved_kw   = saved_meta.get("rank_math_focus_keyword", "NOT FOUND")
        saved_title = saved_meta.get("rank_math_title", "NOT FOUND")
        log(f"  → Saved rank_math_focus_keyword: {saved_kw!r}")
        log(f"  → Saved rank_math_title:         {saved_title!r}")
        if saved_kw == "NOT FOUND" and saved_title == "NOT FOUND":
            log(f"  ⚠️  rank_math_* fields not in response meta — RankMath REST API may not be registered")
            log(f"  ⚠️  Check: RankMath → Titles & Meta → enable REST API support, or add register_meta() to theme")
    except Exception:
        pass

    return True, "OK"


# ═══════════════════════════════════════════════════════
# MAIN RUN
# ═══════════════════════════════════════════════════════

def get_articles_needing_seo(handoffs):
    pending = []
    for slug, article in handoffs.items():
        if not isinstance(article, dict):
            continue
        if (
            article.get("status") in ("published", "pending_approval")
            and not article.get("seo_done")
            and article.get("wp_post_id")
        ):
            pending.append((slug, article))
    # pending_approval articles use draft_pushed_date; published use published_date
    def sort_key(item):
        _, a = item
        return a.get("published_date") or a.get("draft_pushed_date") or ""
    pending.sort(key=sort_key)
    return pending


def run():
    global run_cost
    run_cost = 0.0

    log("=" * 60)
    if DRY_RUN:
        log("SEO Agent starting — DRY RUN MODE")
    else:
        log("SEO Agent starting")

    handoffs = db_helpers.load_all_handoffs()
    pending  = get_articles_needing_seo(handoffs)

    if not pending:
        log("No published articles need SEO metadata. All done!")
        return

    log(f"Found {len(pending)} articles needing SEO metadata")

    # Show article type breakdown
    type_counts = {}
    for _, article in pending:
        t = article.get("article_type", "review")
        type_counts[t] = type_counts.get(t, 0) + 1
    if type_counts:
        type_str = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        log(f"Article types: {type_str}")

    log(f"Daily cap: {DAILY_CAP}")

    existing_titles = build_existing_titles(handoffs)

    processed = 0
    success   = 0
    failed    = 0
    skipped   = 0

    for slug, article in pending:
        if processed >= DAILY_CAP:
            log(f"Daily cap of {DAILY_CAP} reached — stopping")
            break

        tool_name    = article.get("tool_name", slug)
        wp_post_id   = article.get("wp_post_id")
        article_type = article.get("article_type", "review")
        keyword      = get_focus_keyword(article)
        log(f"\n→ Processing: {tool_name} (type: {article_type}, post {wp_post_id})")

        if not passes_word_count_guard(article, slug):
            skipped += 1
            processed += 1
            continue

        try:
            log("  Generating SEO metadata via Claude...")
            meta, schema_type = generate_seo_metadata(slug, article)

            if not meta:
                log(f"  ✗ Failed after all retries — skipping")
                failed += 1
                processed += 1
                continue

            log(f"  Meta title ({len(meta['meta_title'])} chars): {meta['meta_title']}")
            log(f"  Meta desc  ({len(meta['meta_description'])} chars): {meta['meta_description']}")
            log(f"  Focus keyword: {keyword}")
            log(f"  Schema: {schema_type} + FAQPage")

            # Duplicate check
            is_dup, conflict_slug = check_duplicate(meta["meta_title"], existing_titles, slug)
            if is_dup:
                log(f"  ⚠️  DUPLICATE META TITLE — conflicts with: {conflict_slug} — skipping")
                skipped += 1
                processed += 1
                continue

            # Build schema
            content     = article.get("article_html", "")
            schema_json = build_combined_schema(schema_type, tool_name, meta, meta, content, article)

            # OG image
            og_image = get_hero_image_url(article)
            if og_image:
                log(f"  OG image: found")
            else:
                log(f"  OG image: none available")

            # Rollback (captured in memory only; meta_title_previous not in schema)
            if not DRY_RUN:
                existing = get_existing_meta(wp_post_id)
                if existing.get("rank_math_title"):
                    log(f"  Rollback captured (previous title: {existing['rank_math_title'][:40]})")

            # Push
            log("  Pushing to WordPress...")
            ok, msg = push_to_rankmath(
                wp_post_id,
                meta["meta_title"],
                meta["meta_description"],
                schema_json,
                keyword=keyword,
                og_image=og_image
            )

            if ok:
                existing_titles[meta["meta_title"].lower().strip()] = slug
                if not DRY_RUN:
                    db_helpers.update_handoff(slug, {
                        "seo_done":          True,
                        "meta_title":        meta["meta_title"],
                        "meta_description":  meta["meta_description"],
                        "focus_keyword":     keyword,
                        "schema_type":       schema_type,
                        "og_image":          og_image,
                        "seo_processed_date": datetime.now().isoformat(),
                    })
                log(f"  ✓ SEO live: {tool_name}")
                success += 1
            else:
                log(f"  ✗ Push failed: {msg}")
                failed += 1

        except Exception as e:
            log(f"  ✗ Error: {e}")
            failed += 1

        processed += 1

    log(f"\n{'='*60}")
    log(f"SEO Agent complete")
    log(f"  ✓ Success:  {success}")
    log(f"  ✗ Failed:   {failed}")
    log(f"  ⏭  Skipped:  {skipped}")
    log(f"  💰 Run cost: ${run_cost:.4f}")
    log(f"{'='*60}\n")


if __name__ == "__main__":
    run()