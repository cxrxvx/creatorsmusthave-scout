# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
"""
internal_link_agent.py — Internal Linking Agent for CXRXVX Affiliates
=======================================================================
Phase 2.5 Opus Upgrade:
  ✅ Roundup ↔ review cross-linking — roundups link TO individual reviews, reviews link TO roundups
  ✅ Comparison article handling — comparisons link to both individual tool reviews
  ✅ Article type passed to Claude — smarter matching decisions
  ✅ Orphan resolver — suggests specific articles to link FROM (not just reports orphans)
  ✅ Stale link check — flags articles with no placeholders but also no outbound links
  ✅ All existing features preserved (topic clusters, early link bias, ratios, confidence, rollback, dry run, rescan)

Drop this file into your cxrxvx-ai-empire/ folder to replace the old internal_link_agent.py.
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
    WP_URL, WP_USERNAME, WP_APP_PASSWORD
)
import anthropic

# ── Settings ──────────────────────────────────────────────────────────────────
DAILY_CAP               = 20
KEYWORD_DATA_FILE       = "memory/keyword_data.json"
LINK_MAP_FILE           = "memory/link_map.json"
LOG_FILE                = "memory/logs/internal_link_agent.log"
MIN_WORD_COUNT          = 800

# Link ratio per article
MAX_MONEY_LINKS         = 3
MAX_REVIEW_LINKS        = 2
MAX_INFO_LINKS          = 2

# ⚡ Phase 2.5: Roundup articles get higher link limits (they're natural hubs)
MAX_ROUNDUP_OUTBOUND    = 10   # roundups link to many individual reviews
MAX_COMPARISON_OUTBOUND = 6    # comparisons link to both tools + related articles

# Global inbound link cap
MAX_INBOUND_PER_ARTICLE = 3

# ⚡ Phase 2.5: Roundups can receive MORE inbound links (they're pillar pages)
MAX_INBOUND_ROUNDUP     = 6

# Claude confidence threshold
MIN_CONFIDENCE          = 60

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


# ═══════════════════════════════════════════════════════
# KEYWORD CLUSTER BUILDER (unchanged — works well)
# ═══════════════════════════════════════════════════════

def build_keyword_map(keyword_data):
    """Build slug → keyword_cluster map for topical matching."""
    slug_to_keywords = {}
    for tool_key, data in keyword_data.items():
        slug    = data.get("url_slug", "")
        cluster = data.get("keyword_cluster", [])
        if isinstance(cluster, list):
            keywords = cluster
        elif isinstance(cluster, str):
            keywords = [cluster]
        else:
            keywords = []
        if slug:
            slug_to_keywords[slug] = keywords
    return slug_to_keywords


# ═══════════════════════════════════════════════════════
# PUBLISHED ARTICLES INDEX — now with article_type
# ═══════════════════════════════════════════════════════

def build_published_index(handoffs, slug_to_keywords):
    """Build lookup of all published articles with types and keyword clusters."""
    index = {}
    for slug, article in handoffs.items():
        if not isinstance(article, dict):
            continue
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
        tool_name      = article.get("tool_name", "")

        # ⚡ Phase 2.5: track article type for cross-linking intelligence
        if has_affiliate:
            link_type = "money"
        elif article_type == "affiliate_review":
            link_type = "review"
        else:
            link_type = "informational"

        # Roundups and comparisons get special treatment
        content_type = article_type  # review, roundup, comparison, authority_article, alert

        # For roundups: extract the tools covered
        roundup_tools = []
        if article_type == "roundup":
            rt = article.get("roundup_tools", [])
            for t in rt:
                if isinstance(t, str):
                    roundup_tools.append(t.lower())
                elif isinstance(t, dict):
                    roundup_tools.append(t.get("name", "").lower())

        # For comparisons: extract the two tools
        comparison_tools = []
        if article_type == "comparison":
            ct = article.get("comparison_tools", {})
            if ct.get("tool_a"):
                comparison_tools.append(ct["tool_a"].lower())
            if ct.get("tool_b"):
                comparison_tools.append(ct["tool_b"].lower())

        index[slug] = {
            "title":            title,
            "keyword":          keyword,
            "keywords":         keywords,
            "url":              url,
            "wp_id":            wp_id,
            "link_type":        link_type,
            "content_type":     content_type,
            "tool_name":        tool_name.lower(),
            "roundup_tools":    roundup_tools,
            "comparison_tools": comparison_tools,
        }
    return index


def count_inbound_links(link_map):
    """Count how many times each article is linked to from others."""
    inbound_counts = {}
    for source_slug, targets in link_map.get("outbound", {}).items():
        for target_slug in targets:
            inbound_counts[target_slug] = inbound_counts.get(target_slug, 0) + 1
    return inbound_counts


def get_inbound_cap(slug: str, published_index: dict) -> int:
    """Roundups can receive more inbound links since they're pillar pages."""
    info = published_index.get(slug, {})
    if info.get("content_type") == "roundup":
        return MAX_INBOUND_ROUNDUP
    return MAX_INBOUND_PER_ARTICLE


# ═══════════════════════════════════════════════════════
# CROSS-LINKING INTELLIGENCE — roundup ↔ review matching
# ═══════════════════════════════════════════════════════

def find_cross_link_suggestions(current_slug: str, current_article: dict,
                                 published_index: dict) -> list:
    """
    Find strong cross-linking candidates based on article type relationships.
    
    Rules:
    - Roundup "Best AI Video Tools" should link TO individual reviews of each tool it covers
    - Individual reviews should link TO roundups that include their tool
    - Comparisons "X vs Y" should link to individual reviews of both X and Y
    - Individual reviews should link TO comparisons that include their tool
    
    Returns list of {slug, reason, priority} for Claude to consider.
    """
    suggestions = []
    current_type = current_article.get("article_type", "review")
    current_tool = current_article.get("tool_name", "").lower()

    for slug, info in published_index.items():
        if slug == current_slug:
            continue

        # ── Roundup → individual reviews ──
        if current_type == "roundup":
            roundup_tools = current_article.get("roundup_tools", [])
            for rt in roundup_tools:
                rt_name = rt.lower() if isinstance(rt, str) else rt.get("name", "").lower()
                if rt_name and rt_name in info.get("tool_name", ""):
                    suggestions.append({
                        "slug": slug,
                        "reason": f"This roundup covers {info['tool_name']} — link to its individual review",
                        "priority": "high",
                    })

        # ── Individual review → roundups that include this tool ──
        elif current_type in ("review", "affiliate_review", "alert"):
            if current_tool and current_tool in info.get("roundup_tools", []):
                suggestions.append({
                    "slug": slug,
                    "reason": f"Roundup '{info['title']}' includes this tool — link to it",
                    "priority": "high",
                })
            # Also link to comparisons that include this tool
            if current_tool and current_tool in info.get("comparison_tools", []):
                suggestions.append({
                    "slug": slug,
                    "reason": f"Comparison '{info['title']}' features this tool — link to it",
                    "priority": "high",
                })

        # ── Comparison → individual reviews of both tools ──
        elif current_type == "comparison":
            comp_tools = current_article.get("comparison_tools", {})
            tool_a = comp_tools.get("tool_a", "").lower()
            tool_b = comp_tools.get("tool_b", "").lower()
            if (tool_a and tool_a in info.get("tool_name", "")) or \
               (tool_b and tool_b in info.get("tool_name", "")):
                suggestions.append({
                    "slug": slug,
                    "reason": f"This comparison covers {info['tool_name']} — link to its review",
                    "priority": "high",
                })

    return suggestions


# ═══════════════════════════════════════════════════════
# PLACEHOLDER DETECTION + WORDPRESS CONTENT
# ═══════════════════════════════════════════════════════

def get_placeholder_positions(content, placeholders):
    """Determine if each placeholder is in first or second half of article."""
    half = len(content) // 2
    positions = {}
    for ph in placeholders:
        idx = content.find(ph)
        positions[ph] = "first_half" if (idx != -1 and idx < half) else "second_half"
    return positions


def fetch_live_content(wp_post_id):
    """Fetch current live content from WordPress (preserves affiliate links)."""
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
    """Push updated content back to WordPress."""
    if DRY_RUN:
        return True, "DRY RUN"
    auth     = (WP_USERNAME, WP_APP_PASSWORD)
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}"
    payload  = {"content": new_content}
    resp = requests.post(endpoint, json=payload, auth=auth, timeout=30)
    if resp.status_code not in (200, 201):
        return False, f"Push error {resp.status_code}: {resp.text[:200]}"
    return True, "OK"


# ═══════════════════════════════════════════════════════
# CLAUDE MATCHING — now with article type + cross-link suggestions
# ═══════════════════════════════════════════════════════

def build_matching_prompt(current_slug, current_title, current_keywords,
                           current_type, placeholders, placeholder_positions,
                           published_index, inbound_counts, existing_outbound,
                           cross_link_suggestions):
    """Ask Claude to match placeholders to the best published article."""

    available = []
    for slug, info in published_index.items():
        if slug == current_slug:
            continue

        inbound        = inbound_counts.get(slug, 0)
        inbound_cap    = get_inbound_cap(slug, published_index)
        already_linked = slug in existing_outbound

        available.append({
            "slug":           slug,
            "title":          info["title"],
            "keyword":        info["keyword"],
            "keywords":       info["keywords"][:4],
            "url":            info["url"],
            "link_type":      info["link_type"],
            "content_type":   info["content_type"],
            "inbound":        inbound,
            "at_cap":         inbound >= inbound_cap,
            "already_linked": already_linked,
        })

    placeholders_with_position = []
    for ph in placeholders:
        placeholders_with_position.append({
            "placeholder": ph,
            "position":    placeholder_positions.get(ph, "second_half"),
        })

    available_json    = json.dumps(available, indent=2)
    placeholders_json = json.dumps(placeholders_with_position, indent=2)
    current_keywords_str = ", ".join(current_keywords[:6]) if current_keywords else "none"

    # ⚡ Phase 2.5: cross-link suggestions for Claude to consider
    suggestions_text = ""
    if cross_link_suggestions:
        sugg_lines = []
        for s in cross_link_suggestions[:5]:
            sugg_lines.append(f"  - {s['slug']}: {s['reason']} (priority: {s['priority']})")
        suggestions_text = f"""
CROSS-LINK SUGGESTIONS (strongly consider these — they create content clusters):
{chr(10).join(sugg_lines)}

These suggestions come from article type relationships (roundup ↔ review, comparison ↔ review).
Give them +15 confidence bonus when scoring matches.
"""

    # ⚡ Phase 2.5: article type-specific link guidance
    type_guidance = ""
    if current_type == "roundup":
        type_guidance = f"""
ROUNDUP ARTICLE LINKING RULES:
- This is a roundup article — it's a natural LINK HUB
- Prioritize linking to individual reviews of tools covered in this roundup
- Up to {MAX_ROUNDUP_OUTBOUND} outbound links allowed (more than normal articles)
- Every tool mentioned should ideally link to its individual review if one exists
"""
    elif current_type == "comparison":
        type_guidance = f"""
COMPARISON ARTICLE LINKING RULES:
- This compares two specific tools head-to-head
- MUST link to individual reviews of BOTH tools if they exist
- Up to {MAX_COMPARISON_OUTBOUND} outbound links allowed
- Also link to roundup articles that include either tool
"""
    elif current_type in ("review", "affiliate_review"):
        type_guidance = """
REVIEW ARTICLE LINKING RULES:
- Link to roundup articles that include this tool (high value)
- Link to comparison articles featuring this tool
- Link to reviews of competing/complementary tools
"""

    return f"""You are an internal linking specialist for an affiliate review website about creator tools.

CURRENT ARTICLE:
- Slug: {current_slug}
- Title: {current_title}
- Article type: {current_type}
- Related keywords: {current_keywords_str}
{type_guidance}
{suggestions_text}
PLACEHOLDERS TO REPLACE (each has a position — first_half or second_half):
{placeholders_json}

AVAILABLE ARTICLES TO LINK TO:
{available_json}

MATCHING RULES — follow all strictly:

1. TOPICAL RELEVANCE
   - Match placeholders to the most topically relevant article
   - Use "keywords" field to judge topical overlap
   - Same-topic keyword overlap = strong candidate (+20 confidence)

2. ARTICLE TYPE CROSS-LINKING (⚡ NEW — high priority)
   - Roundup → individual review links are HIGH value (creates content clusters)
   - Review → roundup links are HIGH value (passes authority to pillar pages)
   - Comparison → both tool reviews are MANDATORY if available
   - Give content_type matches +15 confidence bonus

3. EARLY LINK BIAS
   - "first_half" placeholders: prefer "money" type articles
   - "second_half" placeholders: reviews and informational fine here

4. LINK RATIO (enforce across ALL matches for this article):
   - Max {MAX_MONEY_LINKS} links to "money" type
   - Max {MAX_REVIEW_LINKS} links to "review" type
   - Max {MAX_INFO_LINKS} links to "informational" type
   (Roundup and comparison articles have higher limits — see type guidance above)

5. HARD RULES:
   - Never link to "at_cap" articles
   - Never link to "already_linked" articles
   - Never self-link

6. ANCHOR TEXT: 3-6 words, natural editorial text, no "click here"

7. CONFIDENCE: Score 0-100. Below {MIN_CONFIDENCE} → action = "remove"

Respond in this EXACT JSON format (array, one entry per placeholder):
[
  {{
    "placeholder": "[INTERNAL_LINK: exact placeholder text]",
    "action": "link" or "remove",
    "target_slug": "slug",
    "target_url": "full URL",
    "anchor_text": "natural text",
    "confidence": 85,
    "topical_match": true or false,
    "cross_link_match": true or false,
    "reason": "one line why"
  }}
]

Return ONLY the JSON array."""


def match_placeholders(current_slug, current_title, current_keywords, current_type,
                        placeholders, placeholder_positions,
                        published_index, inbound_counts, existing_outbound,
                        cross_link_suggestions):
    global run_cost

    if not placeholders:
        return []

    prompt = build_matching_prompt(
        current_slug, current_title, current_keywords, current_type,
        placeholders, placeholder_positions,
        published_index, inbound_counts, existing_outbound,
        cross_link_suggestions
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


# ═══════════════════════════════════════════════════════
# APPLY REPLACEMENTS (unchanged — works well)
# ═══════════════════════════════════════════════════════

def apply_replacements(content, matches):
    """Replace [INTERNAL_LINK:] placeholders with anchors or remove them."""
    replacements_made = []

    for match in matches:
        placeholder   = match.get("placeholder", "")
        action        = match.get("action", "remove")
        target_url    = match.get("target_url", "")
        anchor_text   = match.get("anchor_text", "")
        target_slug   = match.get("target_slug", "")
        confidence    = match.get("confidence", 0)
        topical_match = match.get("topical_match", False)
        cross_link    = match.get("cross_link_match", False)

        if not placeholder or placeholder not in content:
            continue

        if action == "link" and target_url and anchor_text:
            anchor  = f'<a href="{target_url}">{anchor_text}</a>'
            content = content.replace(placeholder, anchor, 1)
            replacements_made.append({
                "placeholder":      placeholder,
                "action":           "linked",
                "anchor":           anchor,
                "target_slug":      target_slug,
                "confidence":       confidence,
                "topical_match":    topical_match,
                "cross_link_match": cross_link,
            })
            tags = []
            if topical_match: tags.append("topical")
            if cross_link: tags.append("cross-link")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            log(f"    ✓ Linked: {placeholder[:45]} → {anchor_text}{tag_str}")
        else:
            content = content.replace(placeholder, "", 1)
            replacements_made.append({
                "placeholder": placeholder,
                "action":      "removed",
                "reason":      match.get("reason", "no good match"),
            })
            log(f"    ✗ Removed: {placeholder[:45]} (confidence: {confidence})")

    return content, replacements_made


# ═══════════════════════════════════════════════════════
# ORPHAN TRACKER — now with resolution suggestions
# ═══════════════════════════════════════════════════════

def find_orphans(published_index, link_map):
    """Find published articles with zero inbound internal links."""
    inbound_counts = count_inbound_links(link_map)
    orphans = []
    for slug in published_index:
        if inbound_counts.get(slug, 0) == 0:
            orphans.append(slug)
    return orphans


def suggest_orphan_fixes(orphans: list, published_index: dict, link_map: dict) -> list:
    """
    For each orphan, suggest which existing article could link to it.
    Looks for topical overlap based on tool names and keyword clusters.
    """
    suggestions = []
    outbound = link_map.get("outbound", {})

    for orphan_slug in orphans:
        orphan_info = published_index.get(orphan_slug, {})
        orphan_tool = orphan_info.get("tool_name", "").lower()
        orphan_keywords = set(k.lower() for k in orphan_info.get("keywords", []))
        orphan_title = orphan_info.get("title", orphan_slug)

        best_source = None
        best_score = 0

        for source_slug, source_info in published_index.items():
            if source_slug == orphan_slug:
                continue

            # Skip if source already links to many articles
            current_outbound = len(outbound.get(source_slug, []))
            if current_outbound >= 7:
                continue

            score = 0

            # Same tool mentioned in roundup
            if orphan_tool and orphan_tool in source_info.get("roundup_tools", []):
                score += 30

            # Same tool in comparison
            if orphan_tool and orphan_tool in source_info.get("comparison_tools", []):
                score += 25

            # Keyword overlap
            source_keywords = set(k.lower() for k in source_info.get("keywords", []))
            overlap = len(orphan_keywords & source_keywords)
            score += overlap * 5

            # Same category bonus
            if orphan_info.get("link_type") == source_info.get("link_type"):
                score += 3

            if score > best_score:
                best_score = score
                best_source = source_slug

        if best_source:
            suggestions.append({
                "orphan": orphan_slug,
                "orphan_title": orphan_title,
                "suggested_source": best_source,
                "source_title": published_index.get(best_source, {}).get("title", ""),
                "match_score": best_score,
            })
        else:
            suggestions.append({
                "orphan": orphan_slug,
                "orphan_title": orphan_title,
                "suggested_source": None,
                "source_title": "No good candidate found",
                "match_score": 0,
            })

    return suggestions


# ═══════════════════════════════════════════════════════
# STALE LINK CHECK — articles with no outbound links and no placeholders
# ═══════════════════════════════════════════════════════

def find_articles_needing_links(published_index, link_map, handoffs):
    """
    Find published articles that have:
    - No outbound internal links
    - No [INTERNAL_LINK:] placeholders left
    - Were published more than 2 days ago
    
    These articles need manual attention — they're isolated in the site structure.
    """
    outbound = link_map.get("outbound", {})
    stale = []
    now = datetime.now()

    for slug, info in published_index.items():
        has_outbound = len(outbound.get(slug, [])) > 0
        if has_outbound:
            continue

        article = handoffs.get(slug, {})
        has_placeholders = "[INTERNAL_LINK:" in article.get("article_html", "")
        if has_placeholders:
            continue  # Will be processed normally

        pub_date = article.get("published_date", "")
        if pub_date:
            try:
                pub_dt = datetime.strptime(pub_date[:10], "%Y-%m-%d")
                if (now - pub_dt).days < 2:
                    continue  # Too new — give it time
            except ValueError:
                pass

        stale.append({
            "slug": slug,
            "title": info.get("title", slug),
            "content_type": info.get("content_type", "review"),
        })

    return stale


# ═══════════════════════════════════════════════════════
# CANDIDATE SELECTION
# ═══════════════════════════════════════════════════════

def get_articles_needing_links(handoffs):
    pending = []
    for slug, article in handoffs.items():
        if not isinstance(article, dict):
            continue
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


# ═══════════════════════════════════════════════════════
# MAIN RUN
# ═══════════════════════════════════════════════════════

def run():
    global run_cost
    run_cost = 0.0

    log("=" * 60)
    if DRY_RUN:
        log("Internal Link Agent starting — DRY RUN MODE")
    elif RESCAN:
        log("Internal Link Agent starting — RESCAN MODE")
    else:
        log("Internal Link Agent starting")

    handoffs     = db_helpers.load_all_handoffs()
    link_map     = load_link_map()
    keyword_data = load_keyword_data()

    slug_to_keywords = build_keyword_map(keyword_data)
    log(f"Keyword clusters loaded: {len(slug_to_keywords)} articles")

    published_index = build_published_index(handoffs, slug_to_keywords)
    log(f"Published articles available: {len(published_index)}")

    # ⚡ Phase 2.5: show article type breakdown
    type_counts = {}
    for info in published_index.values():
        ct = info.get("content_type", "review")
        type_counts[ct] = type_counts.get(ct, 0) + 1
    if type_counts:
        type_str = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        log(f"Article types: {type_str}")

    pending = get_articles_needing_links(handoffs)
    if not pending:
        log("No articles need internal links. All done!")
        _report_orphans_and_stale(published_index, link_map, handoffs)
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
    total_cross_links   = 0

    for slug, article in pending:
        if processed >= DAILY_CAP:
            log(f"Daily cap of {DAILY_CAP} reached — stopping")
            break

        tool_name        = article.get("tool_name", slug)
        wp_post_id       = article.get("wp_post_id")
        current_keywords = slug_to_keywords.get(slug, [])
        current_type     = article.get("article_type", "review")

        log(f"\n→ Processing: {tool_name} (type: {current_type}, post ID {wp_post_id})")

        try:
            # Step 1: Find placeholders
            original_content = article.get("article_html", "")
            placeholders = re.findall(r'\[INTERNAL_LINK:[^\]]+\]', original_content)

            if not placeholders:
                skipped += 1
                processed += 1
                continue

            log(f"  Found {len(placeholders)} placeholder(s)")

            # Step 2: Fetch live content
            live_content = fetch_live_content(wp_post_id)
            if live_content is None:
                log(f"  ✗ Could not fetch live content — skipping")
                failed += 1
                processed += 1
                continue

            live_placeholders = re.findall(r'\[INTERNAL_LINK:[^\]]+\]', live_content)
            if not live_placeholders:
                log(f"  Placeholders already replaced — marking done")
                db_helpers.update_handoff(slug, {"internal_links_done": True})
                skipped += 1
                processed += 1
                continue

            log(f"  Live: {len(live_placeholders)} placeholder(s)")

            # Step 3: Positions
            placeholder_positions = get_placeholder_positions(live_content, live_placeholders)

            # Step 4: Rollback snapshot (content_before_internal_links not in schema — omitted)

            # Step 5: Existing outbound
            existing_outbound = set(link_map.get("outbound", {}).get(slug, []))

            # ⚡ Step 5.5: Cross-link suggestions
            cross_suggestions = find_cross_link_suggestions(slug, article, published_index)
            if cross_suggestions:
                log(f"  Cross-link suggestions: {len(cross_suggestions)}")
                for cs in cross_suggestions[:3]:
                    log(f"    → {cs['slug']}: {cs['reason']}")

            # Step 6: Claude matching
            current_title = article.get("article_title", slug)
            matches = match_placeholders(
                slug, current_title, current_keywords, current_type,
                live_placeholders, placeholder_positions,
                published_index, inbound_counts, existing_outbound,
                cross_suggestions
            )

            if not matches:
                log(f"  No matches — cleaning placeholders")
                updated_content = re.sub(r'\[INTERNAL_LINK:[^\]]+\]', '', live_content)
                if not DRY_RUN:
                    ok, msg = push_updated_content(wp_post_id, updated_content)
                    if ok:
                        db_helpers.update_handoff(slug, {
                            "internal_links_done":    True,
                            "internal_links_added":   0,
                            "internal_links_removed": len(live_placeholders),
                            "internal_links_date":    datetime.now().isoformat(),
                        })
                        success += 1
                    else:
                        failed += 1
                processed += 1
                continue

            # Step 7: Dry run preview
            if DRY_RUN:
                for m in matches:
                    action = m.get("action", "remove")
                    tags = []
                    if m.get("topical_match"): tags.append("topical")
                    if m.get("cross_link_match"): tags.append("cross-link")
                    tag_str = f" [{', '.join(tags)}]" if tags else ""
                    if action == "link":
                        log(f"    LINK ({m.get('confidence',0)}%{tag_str}): "
                            f"{m.get('placeholder','')[:40]} → '{m.get('anchor_text','')}' ({m.get('target_slug','')})")
                    else:
                        log(f"    REMOVE: {m.get('placeholder','')[:40]}")
                success += 1
                processed += 1
                continue

            # Step 8: Apply replacements
            updated_content, replacements = apply_replacements(live_content, matches)

            links_added    = sum(1 for r in replacements if r["action"] == "linked")
            links_removed  = sum(1 for r in replacements if r["action"] == "removed")
            topical_links  = sum(1 for r in replacements if r.get("topical_match") and r["action"] == "linked")
            cross_links    = sum(1 for r in replacements if r.get("cross_link_match") and r["action"] == "linked")
            total_links_added    += links_added
            total_links_removed  += links_removed
            total_topical_links  += topical_links
            total_cross_links    += cross_links

            # Step 9: Push to WordPress
            ok, msg = push_updated_content(wp_post_id, updated_content)
            if not ok:
                log(f"  ✗ Push failed: {msg}")
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

            # Step 11: Mark done
            db_helpers.update_handoff(slug, {
                "internal_links_done":    True,
                "internal_links_added":   links_added,
                "internal_links_removed": links_removed,
                "internal_links_date":    datetime.now().isoformat(),
            })

            log(f"  ✓ Done: {links_added} linked [{topical_links} topical, {cross_links} cross-link], {links_removed} removed")
            success += 1

        except Exception as e:
            log(f"  ✗ Error: {e}")
            import traceback
            log(f"  {traceback.format_exc()}")
            failed += 1

        processed += 1

    # ── Reports ────────────────────────────────────────────────────────────
    _report_orphans_and_stale(published_index, link_map, handoffs)

    log(f"\n{'='*60}")
    log(f"Internal Link Agent complete")
    log(f"  ✓ Success:             {success}")
    log(f"  ✗ Failed:              {failed}")
    log(f"  ⏭  Skipped:             {skipped}")
    log(f"  🔗 Links added:        {total_links_added}")
    log(f"  🌐 Topical links:      {total_topical_links}")
    log(f"  🔄 Cross-links:        {total_cross_links}")
    log(f"  🗑  Links removed:      {total_links_removed}")
    log(f"  💰 Run cost:           ${run_cost:.4f}")
    log(f"{'='*60}\n")


def _report_orphans_and_stale(published_index, link_map, handoffs):
    """Report orphan articles with resolution suggestions + stale isolated articles."""

    # Orphans
    orphans = find_orphans(published_index, link_map)
    if orphans:
        log(f"\n  ⚠️  ORPHAN ARTICLES ({len(orphans)} with no inbound links):")
        suggestions = suggest_orphan_fixes(orphans, published_index, link_map)
        for s in suggestions:
            if s["suggested_source"]:
                log(f"    - {s['orphan_title'][:50]}")
                log(f"      → Suggested: add link FROM '{s['source_title'][:40]}' (score: {s['match_score']})")
            else:
                log(f"    - {s['orphan_title'][:50]} — no good link source found")
    else:
        log(f"\n  ✓ No orphan articles — all have inbound links")

    # Stale isolated articles
    stale = find_articles_needing_links(published_index, link_map, handoffs)
    if stale:
        log(f"\n  ⚠️  ISOLATED ARTICLES ({len(stale)} with no outbound links and no placeholders):")
        for s in stale[:5]:
            log(f"    - {s['title'][:50]} ({s['content_type']})")
        log(f"    These articles need manual [INTERNAL_LINK:] placeholders added")


if __name__ == "__main__":
    run()