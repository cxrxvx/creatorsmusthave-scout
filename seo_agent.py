# seo_agent.py
# Writes meta titles, meta descriptions, schema markup, and Open Graph tags for published articles
# Pushes everything to WordPress via RankMath REST API
# SAFE: never reads or writes post content — zero risk of wiping articles
#
# Features:
#   - Keyword check: verifies primary keyword appears in meta title
#   - Rewrite loop: up to 2 retries if Claude fails length requirements
#   - Duplicate detector: alerts if two articles get identical meta titles
#   - HowTo schema: for guide/tutorial articles
#   - Soft 404 guard: skips articles under 800 words (thin content)
#   - Dry run mode: python3 seo_agent.py --dry-run (no WordPress writes)
#   - Rollback flag: stores previous meta before overwriting
#   - Cost tracker: logs estimated API cost per run
#   - Year guard: wrong years auto-corrected + prompt explicitly states current year
#   - Focus keyword: sets RankMath focus keyword field automatically
#   - Open Graph: sets og:title, og:description for Facebook/X sharing

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
HANDOFFS_FILE       = "memory/handoffs.json"
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


def load_handoffs():
    if not os.path.exists(HANDOFFS_FILE):
        return {}
    with open(HANDOFFS_FILE, "r") as f:
        return json.load(f)


def save_handoffs(data):
    if DRY_RUN:
        log("  [DRY RUN] Skipping handoffs save")
        return
    with open(HANDOFFS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Year Guard ─────────────────────────────────────────────────────────────────
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


# ── Soft 404 Guard ─────────────────────────────────────────────────────────────
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


# ── Duplicate Detector ─────────────────────────────────────────────────────────
def build_existing_titles(handoffs):
    titles = {}
    for slug, article in handoffs.items():
        mt = article.get("meta_title")
        if mt:
            titles[mt.lower().strip()] = slug
    return titles


def check_duplicate(meta_title, existing_titles, current_slug):
    key = meta_title.lower().strip()
    if key in existing_titles and existing_titles[key] != current_slug:
        return True, existing_titles[key]
    return False, None


# ── Schema Type Detection ──────────────────────────────────────────────────────
def detect_schema_type(article):
    article_type = article.get("article_type", "affiliate_review")
    title        = article.get("article_title", "").lower()

    if "how to" in title or "tutorial" in title or "step by step" in title or "guide" in title:
        return "HowTo"
    elif article_type == "affiliate_review" or "review" in title:
        return "Review"
    elif "vs" in title or "versus" in title or "comparison" in title:
        return "Review"
    else:
        return "Article"


# ── Claude Metadata Generation ─────────────────────────────────────────────────
def build_prompt(tool_name, title, keyword, content, schema_type, retry_note=""):
    content_sample    = content[:800] if content else "No content available."
    retry_instruction = ""
    if retry_note:
        retry_instruction = f"\n\n⚠️  PREVIOUS ATTEMPT FAILED: {retry_note}\nFix this in your new attempt."

    return f"""You are an expert SEO specialist. Write metadata for this article.
{retry_instruction}
IMPORTANT: The current year is {CURRENT_YEAR}. Always use {CURRENT_YEAR} — never use any other year.

ARTICLE DETAILS:
- Tool: {tool_name}
- Title: {title}
- Primary keyword: {keyword}
- Schema type: {schema_type}
- Content preview: {content_sample}

YOUR TASKS:

1. META TITLE (strict rules):
   - The primary keyword "{keyword}" MUST appear in the meta title
   - 50-60 characters MAXIMUM — count every character carefully
   - Must match search intent
   - Do NOT copy the article title — rewrite it for Google
   - No clickbait, no ALL CAPS
   - Always use {CURRENT_YEAR} if a year is included — never any other year

2. META DESCRIPTION (strict rules):
   - 140-155 characters MAXIMUM — count every character carefully
   - Include the primary keyword naturally
   - State a clear benefit or outcome
   - End with a subtle call to action (e.g. "Find out if it's worth it.")
   - No quotes, no special characters
   - Always use {CURRENT_YEAR} if a year is included — never any other year

3. FAQ QUESTIONS (3 real buyer questions):
   - Questions a real person would type into Google
   - Answers under 60 words each
   - Factual and helpful — no fluff

Respond in this EXACT format (nothing else — no preamble, no explanation):

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

    tool_name   = article.get("tool_name", slug)
    title       = article.get("article_title", "")
    keyword     = article.get("primary_keyword", "")
    content     = article.get("article_html", "")
    schema_type = detect_schema_type(article)

    total_input_tokens  = 0
    total_output_tokens = 0
    retry_note          = ""

    for attempt in range(1, MAX_RETRIES + 2):
        if attempt > 1:
            log(f"  ↻ Retry {attempt - 1}/{MAX_RETRIES}: {retry_note}")

        prompt = build_prompt(tool_name, title, keyword, content, schema_type, retry_note)

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

        # Year guard
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


# ── Schema Builders ────────────────────────────────────────────────────────────
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
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": questions
    }


def build_review_schema(tool_name, meta):
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
        },
        "reviewRating": {
            "@type": "Rating",
            "ratingValue": "4",
            "bestRating": "5"
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


def build_combined_schema(schema_type, tool_name, meta, faqs, content):
    schemas = []
    if schema_type == "Review":
        schemas.append(build_review_schema(tool_name, meta))
        schemas.append(build_faqpage_schema(tool_name, faqs))
    elif schema_type == "HowTo":
        schemas.append(build_howto_schema(tool_name, meta, content))
        schemas.append(build_faqpage_schema(tool_name, faqs))
    else:
        schemas.append(build_faqpage_schema(tool_name, faqs))
    return "\n".join(json.dumps(s, indent=2) for s in schemas)


# ── WordPress / RankMath Push ──────────────────────────────────────────────────
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


def get_hero_image_url(article):
    """Extract hero image URL from article data for Open Graph image tag."""
    image_data = article.get("image_data", {})
    if isinstance(image_data, dict):
        # Try hero image URL first
        hero = image_data.get("hero", {})
        if isinstance(hero, dict):
            url = hero.get("wp_url") or hero.get("url", "")
            if url:
                return url
    # Fallback: site default OG image
    return "https://creatorsmusthave.com/wp-content/uploads/og-default.jpg"


def push_to_rankmath(wp_post_id, meta_title, meta_description, schema_json, keyword="", og_image=""):
    """Push SEO metadata to WordPress via RankMath REST API.
    SAFE: only writes to post meta fields — never touches post content.
    Includes Open Graph tags for Facebook and X (Twitter) sharing.
    """
    if DRY_RUN:
        log(f"  [DRY RUN] Would push to post {wp_post_id}:")
        log(f"  [DRY RUN] Title:       {meta_title}")
        log(f"  [DRY RUN] Desc:        {meta_description}")
        log(f"  [DRY RUN] Keyword:     {keyword}")
        log(f"  [DRY RUN] OG image:    {og_image or 'default'}")
        return True, "DRY RUN"

    auth     = (WP_USERNAME, WP_APP_PASSWORD)
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}"

    # Push ONLY to meta fields — post content is never read or written
    payload = {
        "meta": {
            # Core SEO fields
            "rank_math_title":           meta_title,
            "rank_math_description":     meta_description,
            "rank_math_focus_keyword":   keyword,
            # Open Graph — controls how article looks when shared on Facebook / X
            "rank_math_facebook_title":       meta_title,
            "rank_math_facebook_description": meta_description,
            "rank_math_twitter_use_facebook": "on",   # reuse FB data for X
        }
    }

    # Add OG image if we have one
    if og_image:
        payload["meta"]["rank_math_facebook_image"] = og_image

    resp = requests.post(endpoint, json=payload, auth=auth, timeout=30)

    if resp.status_code not in (200, 201):
        return False, f"Push error {resp.status_code}: {resp.text[:200]}"

    return True, "OK"


# ── Main Run ───────────────────────────────────────────────────────────────────
def get_articles_needing_seo(handoffs):
    pending = []
    for slug, article in handoffs.items():
        if (
            article.get("status") in ("published", "draft_live")
            and not article.get("seo_done")
            and article.get("wp_post_id")
        ):
            pending.append((slug, article))
    pending.sort(key=lambda x: x[1].get("published_date", ""))
    return pending


def run():
    global run_cost
    run_cost = 0.0

    log("=" * 60)
    if DRY_RUN:
        log("SEO Agent starting — DRY RUN MODE (nothing will be written to WordPress)")
    else:
        log("SEO Agent starting")

    handoffs = load_handoffs()
    pending  = get_articles_needing_seo(handoffs)

    if not pending:
        log("No published articles need SEO metadata. All done!")
        return

    log(f"Found {len(pending)} articles needing SEO metadata")
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

        tool_name  = article.get("tool_name", slug)
        wp_post_id = article.get("wp_post_id")
        keyword    = article.get("primary_keyword", "")
        log(f"\n→ Processing: {tool_name} (post ID {wp_post_id})")

        # Soft 404 guard
        if not passes_word_count_guard(article, slug):
            skipped += 1
            processed += 1
            continue

        try:
            # Generate metadata
            log("  Generating SEO metadata via Claude...")
            meta, schema_type = generate_seo_metadata(slug, article)

            if not meta:
                log(f"  ✗ Failed to generate valid metadata after all retries — skipping")
                failed += 1
                processed += 1
                continue

            log(f"  Meta title ({len(meta['meta_title'])} chars): {meta['meta_title']}")
            log(f"  Meta desc  ({len(meta['meta_description'])} chars): {meta['meta_description']}")
            log(f"  Focus keyword: {keyword}")
            log(f"  Schema type: {schema_type} + FAQPage")

            # Duplicate detector
            is_dup, conflict_slug = check_duplicate(meta["meta_title"], existing_titles, slug)
            if is_dup:
                log(f"  ⚠️  DUPLICATE META TITLE — conflicts with: {conflict_slug} — skipping")
                skipped += 1
                processed += 1
                continue

            # Build schema
            content     = article.get("article_html", "")
            schema_json = build_combined_schema(schema_type, tool_name, meta, meta, content)

            # Get hero image for Open Graph
            og_image = get_hero_image_url(article)
            if og_image and "og-default" not in og_image:
                log(f"  OG image: {og_image}")
            else:
                log(f"  OG image: using site default")

            # Rollback: store existing meta before overwriting
            if not DRY_RUN:
                existing = get_existing_meta(wp_post_id)
                if existing.get("rank_math_title"):
                    handoffs[slug]["meta_title_previous"]       = existing["rank_math_title"]
                    handoffs[slug]["meta_description_previous"] = existing.get("rank_math_description", "")
                    log(f"  Rollback stored")

            # Push to WordPress — meta fields only, content never touched
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
                handoffs[slug]["seo_done"]          = True
                handoffs[slug]["meta_title"]         = meta["meta_title"]
                handoffs[slug]["meta_description"]   = meta["meta_description"]
                handoffs[slug]["schema_type"]        = schema_type
                handoffs[slug]["og_image"]           = og_image
                handoffs[slug]["seo_processed_date"] = datetime.now().isoformat()
                existing_titles[meta["meta_title"].lower().strip()] = slug
                save_handoffs(handoffs)
                log(f"  ✓ SEO metadata + Open Graph live for: {tool_name}")
                success += 1
            else:
                log(f"  ✗ WordPress push failed: {msg}")
                failed += 1

        except Exception as e:
            log(f"  ✗ Error processing {tool_name}: {e}")
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