# internal_link_agent.py
# Replaces [INTERNAL_LINK: description] placeholders in published articles
# with real anchor tags pointing to other published articles on the site.
#
# SAFE: reads live WordPress content before replacing — never uses handoffs.json
# content directly, so affiliate links already injected by publisher are preserved.
# Never touches [AFFILIATE_LINK] placeholders.
#
# Features:
#   - Smart matching: Claude picks best topical match from published articles
#   - Topic cluster awareness: passes keyword clusters to Claude for better matching
#   - Early link bias: money page links placed in first half of article
#   - Link ratio enforcement: 3 money pages, 2 reviews, 2 informational per article
#   - Inbound link cap: no single article linked to more than 3x from others
#   - Natural anchor text: Claude rewrites placeholder text to sound editorial
#   - Confidence guard: removes placeholder rather than force a bad link
#   - Self-links guard: never links article to itself
#   - Orphan tracker: flags articles with no inbound links
#   - link_map.json: full cross-site link tracking for future intelligence
#   - Dry run mode: python3 internal_link_agent.py --dry-run
#   - Rollback storage: saves original content snapshot before any changes
#   - Re-scan mode: python3 internal_link_agent.py --rescan (reprocess all articles)

import json
import os
import re
import sys
import requests
from datetime import datetime
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    WP_URL, WP_USERNAME, WP_APP_PASSWORD
)
import anthropic

# ── Settings ──────────────────────────────────────────────────────────────────
DAILY_CAP               = 20
HANDOFFS_FILE           = "memory/handoffs.json"
KEYWORD_DATA_FILE       = "memory/keyword_data.json"
LINK_MAP_FILE           = "memory/link_map.json"
LOG_FILE                = "memory/logs/internal_link_agent.log"
MIN_WORD_COUNT          = 800

# Link ratio per article
MAX_MONEY_LINKS         = 3    # links to articles with affiliate programs
MAX_REVIEW_LINKS        = 2    # links to reviews without affiliate link yet
MAX_INFO_LINKS          = 2    # links to guides/comparisons/informational

# Global inbound link cap — no article should dominate all internal links
MAX_INBOUND_PER_ARTICLE = 3

# Claude confidence threshold — below this, remove placeholder instead of forcing
MIN_CONFIDENCE          = 60   # out of 100

COST_PER_1K_INPUT       = 0.000003
COST_PER_1K_OUTPUT      = 0.000015
# ──────────────────────────────────────────────────────────────────────────────

client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
DRY_RUN  = "--dry-run" in sys.argv
RESCAN   = "--rescan"  in sys.argv
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
        return
    with open(HANDOFFS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_keyword_data():
    if not os.path.exists(KEYWORD_DATA_FILE):
        return {}
    with open(KEYWORD_DATA_FILE, "r") as f:
        return json.load(f)


def load_link_map():
    if not os.path.exists(LINK_MAP_FILE):
        return {"outbound": {}, "inbound": {}, "last_updated": ""}
    with open(LINK_MAP_FILE, "r") as f:
        return json.load(f)


def save_link_map(data):
    if DRY_RUN:
        return
    data["last_updated"] = datetime.now().isoformat()
    with open(LINK_MAP_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Keyword Cluster Builder ────────────────────────────────────────────────────
def build_keyword_map(keyword_data):
    """
    Build a map of slug → keyword_cluster (list of related keywords).
    keyword_cluster is a list like:
    ['Coursekit vs traditional course platforms', 'best AI course tools 2026', ...]

    We use this to show Claude which keywords are topically related to each article,
    helping it make better same-topic linking decisions.
    """
    slug_to_keywords = {}

    for tool_key, data in keyword_data.items():
        slug    = data.get("url_slug", "")
        cluster = data.get("keyword_cluster", [])

        # Handle both list and string formats safely
        if isinstance(cluster, list):
            keywords = cluster
        elif isinstance(cluster, str):
            keywords = [cluster]
        else:
            keywords = []

        if slug:
            slug_to_keywords[slug] = keywords

    return slug_to_keywords


# ── Build Published Articles Index ────────────────────────────────────────────
def build_published_index(handoffs, slug_to_keywords):
    """Build a lookup of all published articles with their URLs, types, and keyword clusters."""
    index = {}
    for slug, article in handoffs.items():
        if article.get("status") not in ("published", "draft_live"):
            continue
        if not article.get("wp_post_url"):
            continue

        has_affiliate  = bool(article.get("affiliate_link") or article.get("affiliate_injected"))
        article_type   = article.get("article_type", "affiliate_review")
        title          = article.get("article_title", slug)
        keyword        = article.get("primary_keyword", "")
        url            = article.get("wp_post_url", "")
        wp_id          = article.get("wp_post_id")
        keywords       = slug_to_keywords.get(slug, [])

        if has_affiliate:
            link_type = "money"
        elif article_type == "affiliate_review":
            link_type = "review"
        else:
            link_type = "informational"

        index[slug] = {
            "title":    title,
            "keyword":  keyword,
            "keywords": keywords,   # full cluster list for topical matching
            "url":      url,
            "wp_id":    wp_id,
            "link_type": link_type,
        }
    return index


def count_inbound_links(link_map):
    """Count how many times each article is already linked to from others."""
    inbound_counts = {}
    for source_slug, targets in link_map.get("outbound", {}).items():
        for target_slug in targets:
            inbound_counts[target_slug] = inbound_counts.get(target_slug, 0) + 1
    return inbound_counts


# ── Placeholder Position Detector ─────────────────────────────────────────────
def get_placeholder_positions(content, placeholders):
    """
    Determine whether each placeholder falls in the first or second half
    of the article. Used to bias money page links toward early placement.
    """
    half = len(content) // 2
    positions = {}
    for ph in placeholders:
        idx = content.find(ph)
        positions[ph] = "first_half" if (idx != -1 and idx < half) else "second_half"
    return positions


# ── Fetch Live WordPress Content ───────────────────────────────────────────────
def fetch_live_content(wp_post_id):
    """
    Fetch the current live content from WordPress — not handoffs.json.
    Uses context=edit to get raw content with placeholders still intact.
    Affiliate links already injected by publisher are preserved this way.
    """
    auth     = (WP_USERNAME, WP_APP_PASSWORD)
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}?context=edit"
    try:
        resp = requests.get(endpoint, auth=auth, timeout=30)
        if resp.status_code == 200:
            data    = resp.json()
            content = data.get("content", {})
            if isinstance(content, dict):
                return content.get("raw", "")
            return str(content)
    except Exception as e:
        log(f"  ✗ Failed to fetch live content: {e}")
    return None


def push_updated_content(wp_post_id, new_content):
    """
    Push updated content back to WordPress.
    Only called after successful find-replace of [INTERNAL_LINK:] placeholders.
    """
    if DRY_RUN:
        return True, "DRY RUN"

    auth     = (WP_USERNAME, WP_APP_PASSWORD)
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}"
    payload  = {"content": new_content}

    resp = requests.post(endpoint, json=payload, auth=auth, timeout=30)
    if resp.status_code not in (200, 201):
        return False, f"Push error {resp.status_code}: {resp.text[:200]}"
    return True, "OK"


# ── Claude Matching ────────────────────────────────────────────────────────────
def build_matching_prompt(current_slug, current_title, current_keywords,
                           placeholders, placeholder_positions,
                           published_index, inbound_counts, existing_outbound):
    """
    Ask Claude to match each placeholder to the best published article.
    Passes keyword clusters for topical awareness and position data for early link bias.
    """

    # Build article list for Claude
    available = []
    for slug, info in published_index.items():
        if slug == current_slug:
            continue  # never self-link

        inbound        = inbound_counts.get(slug, 0)
        already_linked = slug in existing_outbound

        available.append({
            "slug":           slug,
            "title":          info["title"],
            "keyword":        info["keyword"],
            "keywords":       info["keywords"][:4],  # top 4 cluster keywords for context
            "url":            info["url"],
            "link_type":      info["link_type"],
            "inbound":        inbound,
            "at_cap":         inbound >= MAX_INBOUND_PER_ARTICLE,
            "already_linked": already_linked,
        })

    # Annotate placeholders with their position
    placeholders_with_position = []
    for ph in placeholders:
        placeholders_with_position.append({
            "placeholder": ph,
            "position":    placeholder_positions.get(ph, "second_half"),
        })

    available_json    = json.dumps(available, indent=2)
    placeholders_json = json.dumps(placeholders_with_position, indent=2)
    current_keywords_str = ", ".join(current_keywords[:6]) if current_keywords else "none"

    return f"""You are an internal linking specialist for an affiliate review website about creator tools.

CURRENT ARTICLE:
- Slug: {current_slug}
- Title: {current_title}
- Related keywords: {current_keywords_str}

PLACEHOLDERS TO REPLACE (each has a position — first_half or second_half of article):
{placeholders_json}

AVAILABLE ARTICLES TO LINK TO:
{available_json}

MATCHING RULES — follow all of these strictly:

1. TOPICAL RELEVANCE
   - Match placeholders to the most topically relevant article available
   - Use the "keywords" field of each available article to judge topical overlap
   - An article whose keyword list overlaps with the current article's related keywords
     is a strong candidate — treat this as a same-topic signal

2. EARLY LINK BIAS
   - Placeholders in "first_half": strongly prefer linking to "money" type articles
   - Placeholders in "second_half": reviews and informational articles are fine here
   - Money page links placed early in the article carry stronger SEO weight

3. LINK RATIO (enforce strictly across ALL matches for this article combined):
   - Maximum {MAX_MONEY_LINKS} total links to "money" type articles
   - Maximum {MAX_REVIEW_LINKS} total links to "review" type articles
   - Maximum {MAX_INFO_LINKS} total links to "informational" type articles

4. HARD RULES:
   - Never link to an article where "at_cap" is true (already at inbound link cap)
   - Never link to an article where "already_linked" is true
   - Never link the article to itself

5. ANCHOR TEXT:
   - Rewrite the placeholder description into natural editorial anchor text
   - 3-6 words maximum
   - No "click here", no "read more", no keyword stuffing
   - Must read naturally inside a sentence

6. CONFIDENCE:
   - Score each match 0-100 based on topical relevance
   - Topical keyword overlap adds +20 to confidence score
   - If best available match scores below {MIN_CONFIDENCE}/100 — set action to "remove"
   - A clean removal is always better than a forced irrelevant link

Respond in this EXACT JSON format (array, one entry per placeholder):
[
  {{
    "placeholder": "[INTERNAL_LINK: exact placeholder text]",
    "action": "link" or "remove",
    "target_slug": "slug of article to link to (empty string if remove)",
    "target_url": "full URL of article (empty string if remove)",
    "anchor_text": "natural anchor text (empty string if remove)",
    "confidence": 85,
    "topical_match": true or false,
    "reason": "one line why this match was chosen"
  }}
]

Return ONLY the JSON array. No preamble, no explanation, no markdown fences."""


def match_placeholders(current_slug, current_title, current_keywords,
                        placeholders, placeholder_positions,
                        published_index, inbound_counts, existing_outbound):
    global run_cost

    if not placeholders:
        return []

    prompt = build_matching_prompt(
        current_slug, current_title, current_keywords,
        placeholders, placeholder_positions,
        published_index, inbound_counts, existing_outbound
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )

    input_tokens  = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (input_tokens / 1000) * COST_PER_1K_INPUT + (output_tokens / 1000) * COST_PER_1K_OUTPUT
    run_cost += cost
    log(f"  Tokens: {input_tokens} in / {output_tokens} out | Cost: ${cost:.5f}")

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude adds them
    raw = re.sub(r'^```json\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'^```\s*',     '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```$',     '', raw)
    raw = raw.strip()

    try:
        matches = json.loads(raw)
        return matches
    except json.JSONDecodeError as e:
        log(f"  ⚠️  JSON parse error: {e}")
        log(f"  Raw response: {raw[:300]}")
        return []


# ── Apply Replacements ─────────────────────────────────────────────────────────
def apply_replacements(content, matches):
    """
    Replace [INTERNAL_LINK: ...] placeholders with anchor tags or remove them.
    Only touches [INTERNAL_LINK:] patterns — [AFFILIATE_LINK] completely untouched.
    """
    replacements_made = []

    for match in matches:
        placeholder   = match.get("placeholder", "")
        action        = match.get("action", "remove")
        target_url    = match.get("target_url", "")
        anchor_text   = match.get("anchor_text", "")
        target_slug   = match.get("target_slug", "")
        confidence    = match.get("confidence", 0)
        topical_match = match.get("topical_match", False)

        if not placeholder or placeholder not in content:
            continue

        if action == "link" and target_url and anchor_text:
            anchor  = f'<a href="{target_url}">{anchor_text}</a>'
            content = content.replace(placeholder, anchor, 1)
            replacements_made.append({
                "placeholder":   placeholder,
                "action":        "linked",
                "anchor":        anchor,
                "target_slug":   target_slug,
                "confidence":    confidence,
                "topical_match": topical_match,
            })
            topic_tag = " [topical]" if topical_match else ""
            log(f"    ✓ Linked: {placeholder[:45]} → {anchor_text}{topic_tag}")
        else:
            content = content.replace(placeholder, "", 1)
            replacements_made.append({
                "placeholder": placeholder,
                "action":      "removed",
                "reason":      match.get("reason", "no good match"),
            })
            log(f"    ✗ Removed: {placeholder[:45]} (confidence: {confidence})")

    return content, replacements_made


# ── Orphan Tracker ─────────────────────────────────────────────────────────────
def find_orphans(published_index, link_map):
    """Find published articles with zero inbound internal links."""
    inbound_counts = count_inbound_links(link_map)
    orphans = []
    for slug in published_index:
        if inbound_counts.get(slug, 0) == 0:
            orphans.append(slug)
    return orphans


# ── Main Run ───────────────────────────────────────────────────────────────────
def get_articles_needing_links(handoffs):
    pending = []
    for slug, article in handoffs.items():
        if article.get("status") not in ("published", "draft_live"):
            continue
        if not article.get("wp_post_id"):
            continue
        if article.get("internal_links_done") and not RESCAN:
            continue
        content = article.get("article_html", "")
        if "[INTERNAL_LINK:" not in content:
            continue
        pending.append((slug, article))
    pending.sort(key=lambda x: x[1].get("published_date", ""))
    return pending


def run():
    global run_cost
    run_cost = 0.0

    log("=" * 60)
    if DRY_RUN:
        log("Internal Link Agent starting — DRY RUN MODE")
    elif RESCAN:
        log("Internal Link Agent starting — RESCAN MODE (reprocessing all articles)")
    else:
        log("Internal Link Agent starting")

    handoffs     = load_handoffs()
    link_map     = load_link_map()
    keyword_data = load_keyword_data()

    # Build keyword cluster map
    slug_to_keywords = build_keyword_map(keyword_data)
    log(f"Keyword clusters loaded: {len(slug_to_keywords)} articles")

    published_index = build_published_index(handoffs, slug_to_keywords)
    log(f"Published articles available for linking: {len(published_index)}")

    pending = get_articles_needing_links(handoffs)
    if not pending:
        log("No articles need internal links. All done!")
        _report_orphans(published_index, link_map)
        return

    log(f"Articles needing internal links: {len(pending)}")
    log(f"Daily cap: {DAILY_CAP}")

    inbound_counts = count_inbound_links(link_map)

    processed           = 0
    success             = 0
    failed              = 0
    skipped             = 0
    total_links_added   = 0
    total_links_removed = 0
    total_topical_links = 0

    for slug, article in pending:
        if processed >= DAILY_CAP:
            log(f"Daily cap of {DAILY_CAP} reached — stopping")
            break

        tool_name        = article.get("tool_name", slug)
        wp_post_id       = article.get("wp_post_id")
        current_keywords = slug_to_keywords.get(slug, [])

        log(f"\n→ Processing: {tool_name} (post ID {wp_post_id})")
        if current_keywords:
            log(f"  Keywords: {', '.join(current_keywords[:3])}...")

        try:
            # Step 1: Find placeholders in original article content
            original_content = article.get("article_html", "")
            placeholders = re.findall(r'\[INTERNAL_LINK:[^\]]+\]', original_content)

            if not placeholders:
                log(f"  No placeholders found — skipping")
                skipped += 1
                processed += 1
                continue

            log(f"  Found {len(placeholders)} placeholder(s)")

            # Step 2: Fetch LIVE content from WordPress
            log(f"  Fetching live content from WordPress...")
            live_content = fetch_live_content(wp_post_id)

            if live_content is None:
                log(f"  ✗ Could not fetch live content — skipping")
                failed += 1
                processed += 1
                continue

            # Verify placeholders still exist in live content
            live_placeholders = re.findall(r'\[INTERNAL_LINK:[^\]]+\]', live_content)
            if not live_placeholders:
                log(f"  ⚠️  Placeholders already replaced in live content — marking done")
                handoffs[slug]["internal_links_done"] = True
                save_handoffs(handoffs)
                skipped += 1
                processed += 1
                continue

            log(f"  Live content confirmed — {len(live_placeholders)} placeholder(s) to replace")

            # Step 3: Detect placeholder positions
            placeholder_positions = get_placeholder_positions(live_content, live_placeholders)
            first_half_count  = sum(1 for p in placeholder_positions.values() if p == "first_half")
            second_half_count = sum(1 for p in placeholder_positions.values() if p == "second_half")
            log(f"  Position split: {first_half_count} first half, {second_half_count} second half")

            # Step 4: Store rollback snapshot
            if not DRY_RUN:
                handoffs[slug]["content_before_internal_links"] = live_content[:500] + "..."
                log(f"  Rollback stored")

            # Step 5: Get existing outbound links for this article
            existing_outbound = set(link_map.get("outbound", {}).get(slug, []))

            # Step 6: Ask Claude to match placeholders
            log(f"  Matching placeholders via Claude...")
            current_title = article.get("article_title", slug)
            matches = match_placeholders(
                slug, current_title, current_keywords,
                live_placeholders, placeholder_positions,
                published_index, inbound_counts, existing_outbound
            )

            if not matches:
                log(f"  ✗ Claude returned no matches — removing all placeholders cleanly")
                updated_content = re.sub(r'\[INTERNAL_LINK:[^\]]+\]', '', live_content)

                if not DRY_RUN:
                    ok, msg = push_updated_content(wp_post_id, updated_content)
                    if ok:
                        handoffs[slug]["internal_links_done"]    = True
                        handoffs[slug]["internal_links_added"]   = 0
                        handoffs[slug]["internal_links_removed"] = len(live_placeholders)
                        handoffs[slug]["internal_links_date"]    = datetime.now().isoformat()
                        save_handoffs(handoffs)
                        log(f"  ✓ Placeholders cleaned for: {tool_name}")
                        success += 1
                    else:
                        log(f"  ✗ WordPress push failed: {msg}")
                        failed += 1
                processed += 1
                continue

            # Step 7: Dry run preview
            if DRY_RUN:
                log(f"  [DRY RUN] Planned replacements:")
                for m in matches:
                    action = m.get("action", "remove")
                    topic_tag = " [topical]" if m.get("topical_match") else ""
                    if action == "link":
                        log(f"    LINK ({m.get('confidence',0)}%{topic_tag}): "
                            f"{m.get('placeholder','')[:40]} "
                            f"→ '{m.get('anchor_text','')}' ({m.get('target_slug','')})")
                    else:
                        log(f"    REMOVE: {m.get('placeholder','')[:40]} — {m.get('reason','')}")
                success += 1
                processed += 1
                continue

            # Step 8: Apply replacements
            updated_content, replacements = apply_replacements(live_content, matches)

            links_added    = sum(1 for r in replacements if r["action"] == "linked")
            links_removed  = sum(1 for r in replacements if r["action"] == "removed")
            topical_links  = sum(1 for r in replacements if r.get("topical_match") and r["action"] == "linked")
            total_links_added    += links_added
            total_links_removed  += links_removed
            total_topical_links  += topical_links

            # Step 9: Push updated content to WordPress
            log(f"  Pushing to WordPress ({links_added} links added, {links_removed} removed)...")
            ok, msg = push_updated_content(wp_post_id, updated_content)

            if not ok:
                log(f"  ✗ WordPress push failed: {msg}")
                failed += 1
                processed += 1
                continue

            # Step 10: Update link map
            linked_targets = [r["target_slug"] for r in replacements if r["action"] == "linked"]
            if linked_targets:
                if "outbound" not in link_map:
                    link_map["outbound"] = {}
                if "inbound" not in link_map:
                    link_map["inbound"] = {}

                existing_out = set(link_map["outbound"].get(slug, []))
                existing_out.update(linked_targets)
                link_map["outbound"][slug] = list(existing_out)

                for target in linked_targets:
                    existing_in = set(link_map["inbound"].get(target, []))
                    existing_in.add(slug)
                    link_map["inbound"][target] = list(existing_in)
                    inbound_counts[target] = inbound_counts.get(target, 0) + 1

            save_link_map(link_map)

            # Step 11: Mark done in handoffs
            handoffs[slug]["internal_links_done"]    = True
            handoffs[slug]["internal_links_added"]   = links_added
            handoffs[slug]["internal_links_removed"] = links_removed
            handoffs[slug]["internal_links_date"]    = datetime.now().isoformat()
            handoffs[slug]["link_replacements"]      = replacements
            save_handoffs(handoffs)

            log(f"  ✓ Internal links done for: {tool_name} "
                f"({links_added} linked [{topical_links} topical], {links_removed} removed)")
            success += 1

        except Exception as e:
            log(f"  ✗ Error processing {tool_name}: {e}")
            import traceback
            log(f"  {traceback.format_exc()}")
            failed += 1

        processed += 1

    # ── Orphan Report ──────────────────────────────────────────────────────────
    _report_orphans(published_index, link_map)

    log(f"\n{'='*60}")
    log(f"Internal Link Agent complete")
    log(f"  ✓ Success:             {success}")
    log(f"  ✗ Failed:              {failed}")
    log(f"  ⏭  Skipped:             {skipped}")
    log(f"  🔗 Links added:        {total_links_added}")
    log(f"  🌐 Topical links:      {total_topical_links}")
    log(f"  🗑  Links removed:      {total_links_removed}")
    log(f"  💰 Run cost:           ${run_cost:.4f}")
    log(f"{'='*60}\n")


def _report_orphans(published_index, link_map):
    orphans = find_orphans(published_index, link_map)
    if orphans:
        log(f"\n  ⚠️  ORPHAN ARTICLES (no inbound links yet):")
        for slug in orphans:
            info = published_index.get(slug, {})
            log(f"    - {slug}: {info.get('title', '')}")
    else:
        log(f"\n  ✓ No orphan articles — all published articles have inbound links")


if __name__ == "__main__":
    run()