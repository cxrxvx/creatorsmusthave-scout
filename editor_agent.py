# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
"""
editor_agent.py — Strict Quality Editor for CXRXVX Affiliates
================================================================
Phase 2.5 Opus Upgrade:
  ✅ PASS_SCORE 78 — strict but fair (was 82, caused 14% approval)
  ✅ Scoring prompt finds real problems without over-penalizing
  ✅ Article type awareness — roundups/comparisons scored on their own criteria
  ✅ Structured feedback saved for article_agent self-learning loop
  ✅ Pattern tracking — detects recurring mistakes across articles
  ✅ Specific rewrite instructions when an article fails
  ✅ Score calibration notes — tells Claude what 90+ actually means
  ✅ Balanced deductions — no single issue tanks the whole score

Expected results:
  - Target: ~70-80% approval, avg 80-86, meaningful quality gate
  - Below 50% approval = prompt too harsh, above 90% = too lenient
"""

import json
import os
import re
from datetime import datetime
from anthropic import Anthropic
import db_helpers

# ── Config ──────────────────────────────────────────────────────────────────
try:
    from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
except ImportError:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

client = Anthropic(api_key=ANTHROPIC_API_KEY)

MEMORY_DIR           = "memory"
LOGS_DIR             = os.path.join(MEMORY_DIR, "logs", "editor_agent")
EDITOR_CRITERIA_FILE = os.path.join(MEMORY_DIR, "prompts", "editor_criteria.md")

# ⚡ Phase 2.5 tuned: 82 was too harsh (14% approval), 75 was rubber stamp
# 78 targets 70-80% approval — strict enough to catch real problems,
# fair enough to let decent articles through the pipeline
PASS_SCORE   = 78
DAILY_CAP    = 15

os.makedirs(LOGS_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_editor_criteria() -> str:
    """
    Load scoring dimensions + usefulness test from memory/prompts/editor_criteria.md.
    Returns the extracted sections as a string for injection into the scoring prompt.
    Falls back to empty string if file is missing — prompt section will be empty.
    """
    try:
        with open(EDITOR_CRITERIA_FILE, "r") as f:
            content = f.read()
        # Extract "Scoring Dimensions" section (stops before Article-Type-Specific Checks)
        dims_match = re.search(
            r'## Scoring Dimensions.*?(?=\n## Article-Type-Specific)',
            content, re.DOTALL
        )
        # Extract "Usefulness Test" section
        useful_match = re.search(
            r'## Usefulness Test.*?(?=\n## Response Format|\n---|\Z)',
            content, re.DOTALL
        )
        parts = []
        if dims_match:
            parts.append(dims_match.group(0).strip())
        if useful_match:
            parts.append(useful_match.group(0).strip())
        return "\n\n".join(parts) if parts else ""
    except Exception:
        return ""


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[editor_agent] {timestamp} — {msg}")
    log_file = os.path.join(LOGS_DIR, datetime.now().strftime("%Y-%m-%d") + ".log")
    with open(log_file, "a") as f:
        f.write(f"{timestamp} — {msg}\n")


def strip_html_tags(html):
    return re.sub(r"<[^>]+>", " ", html or "")


EDITOR_FEEDBACK_FILE = os.path.join(MEMORY_DIR, "editor_feedback.json")


def _save_editor_feedback(deductions_list: list, total_reviewed: int, approved: int):
    """
    Parse deduction strings from this run, find the top 3 most common reasons,
    and save to memory/editor_feedback.json for article_agent to consume.
    """
    if not deductions_list:
        return

    # Split each deduction string on commas/semicolons, strip, lowercase, dedupe
    from collections import Counter
    phrase_counter: Counter = Counter()
    for deduction_str in deductions_list:
        # Split on comma or semicolon, clean up each phrase
        parts = re.split(r"[,;]", deduction_str)
        for part in parts:
            phrase = part.strip().lower()
            # Remove trailing score like " -5" or " -3"
            phrase = re.sub(r"\s*[-−]\d+\s*$", "", phrase).strip()
            if phrase and len(phrase) > 4:
                phrase_counter[phrase] += 1

    top_3 = [phrase for phrase, _ in phrase_counter.most_common(3)]
    if not top_3:
        return

    approval_rate = round(approved / total_reviewed, 2) if total_reviewed else 0.0
    feedback = {
        "run_date":              datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "top_deductions":        top_3,
        "total_articles_reviewed": total_reviewed,
        "approval_rate":         approval_rate,
    }
    try:
        save_json(EDITOR_FEEDBACK_FILE, feedback)
        log(f"  📝 Editor feedback saved → top issues: {', '.join(top_3)}")
    except Exception as e:
        log(f"  ⚠️  Could not save editor feedback: {e}")


# ═══════════════════════════════════════════════════════
# PATTERN TRACKING — detect recurring mistakes
# ═══════════════════════════════════════════════════════

def get_recent_patterns(handoffs: dict) -> str:
    """
    Look at the last 10 edited articles and find recurring issues.
    Returns a string to inject into the scoring prompt so the editor
    knows what patterns to watch for.
    """
    scored = []
    for slug, data in handoffs.items():
        if data.get("editor_scores") and data.get("editor_reviewed"):
            scored.append({
                "slug": slug,
                "scores": data["editor_scores"],
                "date": data.get("editor_reviewed", ""),
            })

    if not scored:
        return ""

    # Sort by date, take last 10
    scored.sort(key=lambda x: x["date"], reverse=True)
    recent = scored[:10]

    # Collect all notes
    seo_issues = []
    readability_issues = []
    completeness_issues = []

    for item in recent:
        s = item["scores"]
        seo_note = s.get("seo_notes", "")
        if seo_note and seo_note.lower() != "passed":
            seo_issues.append(seo_note)
        read_note = s.get("readability_notes", "")
        if read_note and read_note.lower() != "passed":
            readability_issues.append(read_note)
        comp_note = s.get("completeness_notes", "")
        if comp_note and comp_note.lower() != "passed":
            completeness_issues.append(comp_note)

    if not seo_issues and not readability_issues and not completeness_issues:
        return ""

    lines = ["RECURRING PATTERNS FROM RECENT ARTICLES (watch for these):"]
    if seo_issues:
        lines.append(f"  SEO issues seen: {'; '.join(seo_issues[:3])}")
    if readability_issues:
        lines.append(f"  Readability issues seen: {'; '.join(readability_issues[:3])}")
    if completeness_issues:
        lines.append(f"  Completeness issues seen: {'; '.join(completeness_issues[:3])}")
    lines.append("  → Note these patterns but score each article on its own merits.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# ARTICLE TYPE-SPECIFIC SCORING CRITERIA
# ═══════════════════════════════════════════════════════

def get_type_criteria(article_type: str) -> str:
    """Return extra scoring criteria based on article type."""

    if article_type == "roundup":
        return """
ROUNDUP-SPECIFIC CHECKS:
- Does it cover at least 5 tools? (-5 if fewer)
- Does each tool have its own mini-review (not just a name and link)? (-5 if shallow)
- Is there a Quick Picks / comparison table at the top? (-3 if missing)
- Does each tool section include pricing? (-3 if missing)
- Is there a clear #1 pick with reasoning? (-3 if missing)
- Does the comparison table at the end cover at least 4 feature rows? (-3 if missing)"""

    elif article_type == "comparison":
        return """
COMPARISON-SPECIFIC CHECKS:
- Does it clearly state a winner upfront? (-5 if wishy-washy)
- Are there at least 3 feature-by-feature comparison sections? (-5 if fewer)
- Does each comparison section declare a winner? (-3 if not)
- Is the pricing comparison side-by-side? (-3 if not)
- Are there separate "Who should choose X/Y" sections? (-3 if missing)
- Is the final verdict clear and decisive? (-5 if "it depends" cop-out)"""

    elif article_type == "authority_article":
        return """
AUTHORITY ARTICLE CHECKS:
- There should be NO affiliate disclosure (-10 if present)
- There should be NO CTA buttons (-10 if present)
- Content should be purely informational
- Should include at least 4 H2 sections of substantive content (-5 if fewer)"""

    else:
        # review or alert
        return """
REVIEW-SPECIFIC CHECKS:
- Is there a Key Takeaways box near the top? (-3 if missing)
- Is there a "Choose if / Skip if" decision table? (-3 if missing)
- Does the pricing section have plan names and dollar amounts? (-5 if vague)
- Are there at least 3 specific cons (not generic)? (-5 if generic)
- Is there a "Who it's NOT for" section? (-3 if missing)
- Does the verdict clearly state who should buy and who should skip? (-3 if vague)"""


# ═══════════════════════════════════════════════════════
# HARD-FAIL CHECKS — run before any scoring
# ═══════════════════════════════════════════════════════

# Emoji unicode ranges for heading checks
_EMOJI_RE = re.compile(
    r"[\U00010000-\U0010ffff"
    r"\U0001F300-\U0001F9FF"
    r"\U00002600-\U000027BF"
    r"\U0001FA00-\U0001FAFF"
    r"\U0001F600-\U0001F64F"
    r"🏆💰🆓✅❌⭐🔥⚡✨📚]",
    re.UNICODE,
)


def check_hard_fails(article: dict) -> list:
    """
    Check for conditions that auto-reject an article (score 0) before Claude runs.
    Returns a list of failure reason strings. Empty list = no hard fails.
    """
    html       = article.get("article_html", "")
    word_count = article.get("word_count", 0)
    fails      = []

    # 1. Placeholder URLs
    if "[AFFILIATE_LINK]" in html:
        fails.append("placeholder URL [AFFILIATE_LINK] found in article body")
    if "REPLACE_WITH_TOOL_URL" in html:
        fails.append("placeholder REPLACE_WITH_TOOL_URL found in article body")
    # Any href containing square-bracket placeholder like href="[TOOL_URL]"
    if re.search(r'href="[^"]*\[[^\]]+\][^"]*"', html):
        fails.append("href attribute contains a square-bracket placeholder (e.g. [TOOL_URL])")

    # 2. Emoji in H1, H2, or H3 headings
    headings = re.findall(r"<h[123][^>]*>(.*?)</h[123]>", html, re.IGNORECASE | re.DOTALL)
    for heading in headings:
        plain = re.sub(r"<[^>]+>", "", heading)
        if _EMOJI_RE.search(plain):
            fails.append(f"emoji found in H1/H2/H3 heading: \"{plain[:60].strip()}\"")
            break  # one example is enough

    # 3. Empty or too short
    if not html or word_count < 500:
        fails.append(f"article body too short: {word_count} words (minimum 500)")

    return fails


# ═══════════════════════════════════════════════════════
# HTML STRUCTURE CHECKS — things we can verify in code
# ═══════════════════════════════════════════════════════

def run_html_checks(html: str, article_type: str) -> dict:
    """
    Automated HTML checks that don't need Claude.
    Returns dict of issues found — injected into the scoring prompt
    so Claude can factor them in.
    """
    issues = []
    bonuses = []

    # Check for disclosure
    has_disclosure = 'class="affiliate-disclosure"' in html
    if article_type in ("review", "alert", "roundup", "comparison"):
        if not has_disclosure:
            issues.append("MISSING affiliate disclosure div")
    elif article_type == "authority_article":
        if has_disclosure:
            issues.append("Authority article has affiliate disclosure — should not")

    # Check for CTA buttons
    cta_count = html.count('class="cta-button"')
    if article_type == "authority_article" and cta_count > 0:
        issues.append(f"Authority article has {cta_count} CTA button(s) — should have zero")
    elif article_type in ("review", "alert") and cta_count > 3:
        issues.append(f"Too many CTAs: {cta_count} (max 3 for reviews)")
    elif article_type in ("review", "alert") and cta_count == 0:
        issues.append("No CTA buttons found — needs at least 1")

    # Check for pricing table
    has_pricing_table = 'class="pricing-table"' in html or '<th>Price</th>' in html or '<th>Pricing</th>' in html
    if article_type in ("review", "roundup", "comparison") and not has_pricing_table:
        issues.append("No pricing table found — pricing should be in a table")

    # Check for pros/cons
    has_pros = 'class="pros"' in html
    has_cons = 'class="cons"' in html
    if article_type == "review":
        if not has_pros:
            issues.append("Missing pros section")
        if not has_cons:
            issues.append("Missing cons section")

    # Check for FAQ
    has_faq = 'id="faq"' in html
    if not has_faq:
        issues.append("Missing FAQ section (no id='faq' found)")

    # Check for placeholder URLs that slipped through
    placeholders = ["[TOOL_URL]", "[AFFILIATE_LINK]", "https://example.com",
                     "href=\"\"", "[INSERT_", "[URL]"]
    for p in placeholders:
        if p in html:
            issues.append(f"PLACEHOLDER URL FOUND: {p} — must be real URL")

    # Check H2 count
    h2_count = len(re.findall(r'<h2[^>]*>', html))
    if article_type == "review" and h2_count < 5:
        issues.append(f"Only {h2_count} H2 sections — reviews need at least 5-6")
    elif article_type == "roundup" and h2_count < 7:
        issues.append(f"Only {h2_count} H2 sections — roundups need at least 7-8")

    # Check for emoji in h3 tags (inside pros/cons)
    emoji_h3 = re.findall(r'<h3>[^<]*[\U00010000-\U0010ffff🏆💰🆓✅❌⭐🔥⚡✨📚][^<]*</h3>', html)
    if emoji_h3:
        issues.append(f"Emoji found in h3 tags: {emoji_h3[:2]} — should be plain text")

    # Check for banned phrases
    plain = strip_html_tags(html).lower()
    banned = ["game-changer", "revolutionary", "cutting-edge", "state-of-the-art",
              "powerful tool", "robust features", "seamless integration",
              "in today's digital world", "in the fast-paced world"]
    found_banned = [b for b in banned if b in plain]
    if found_banned:
        issues.append(f"Banned phrases found: {', '.join(found_banned)}")

    # Bonuses
    if 'class="key-takeaways"' in html:
        bonuses.append("Has Key Takeaways box")
    if 'class="decision-table"' in html:
        bonuses.append("Has decision table")
    if 'class="quick-verdict"' in html:
        bonuses.append("Has quick verdict box")
    if '[INTERNAL_LINK:' in html:
        bonuses.append("Has internal link placeholders")

    return {
        "issues": issues,
        "bonuses": bonuses,
        "cta_count": cta_count,
        "h2_count": h2_count,
    }


# ═══════════════════════════════════════════════════════
# CORE SCORING — the Claude prompt
# ═══════════════════════════════════════════════════════

def score_article(article: dict, pattern_context: str = "") -> dict:
    """Score an article using Claude with a strict but fair prompt."""
    tool_name    = article.get("tool_name", "Unknown")
    title        = article.get("article_title", "")
    keyword      = article.get("primary_keyword", "")
    html         = article.get("article_html", "")
    article_type = article.get("article_type", "review")
    word_count   = article.get("word_count", 0)

    # Run automated HTML checks first
    html_checks = run_html_checks(html, article_type)

    # Build the automated issues context
    auto_issues = ""
    if html_checks["issues"]:
        issue_list = "\n".join(f"  ⚠️ {i}" for i in html_checks["issues"])
        auto_issues = f"""
AUTOMATED CHECKS FOUND THESE ISSUES (factor into your scoring):
{issue_list}
Each issue above should cost 2-4 points from the relevant dimension.
"""
    if html_checks["bonuses"]:
        bonus_list = ", ".join(html_checks["bonuses"])
        auto_issues += f"\nStructural elements present: {bonus_list}"

    # Get type-specific criteria
    type_criteria = get_type_criteria(article_type)

    # Load scoring criteria from memory/prompts/editor_criteria.md
    scoring_criteria = load_editor_criteria()

    plain_text = strip_html_tags(html)
    plain_text = plain_text[:30000]

    prompt = f"""You are a senior editor scoring affiliate content for quality.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HARD-FAIL CHECKS — do these FIRST before scoring anything
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Check for these conditions BEFORE you score anything. If ANY are true, stop
and return a hard-fail response (score 0, approved false).

1. PLACEHOLDER URLS: Does the article contain [AFFILIATE_LINK], REPLACE_WITH_TOOL_URL,
   or any href attribute with square brackets like href="[TOOL_URL]"?
2. EMOJI IN HEADINGS: Are there any emoji characters inside H1, H2, or H3 tags?
3. TOO SHORT: Is the article body empty or under 500 words?

If ANY hard-fail condition is true, return ONLY this JSON:
{{
  "seo_score": 0,
  "readability_score": 0,
  "completeness_score": 0,
  "overall_score": 0,
  "approved": false,
  "seo_notes": "HARD FAIL: <reason>",
  "readability_notes": "HARD FAIL: <reason>",
  "completeness_notes": "HARD FAIL: <reason>",
  "deductions_applied": "Hard fail — auto-rejected before scoring",
  "editor_summary": "HARD FAIL: <reason>. Article must be fixed before re-review.",
  "rewrite_instructions": "<specific fix required>",
  "usefulness_q1": "N/A — hard fail",
  "usefulness_q2": "N/A — hard fail"
}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your goal: catch articles with REAL problems (broken structure, fake info, unreadable
writing) while letting solid articles through. You are not looking for perfection —
you are looking for articles good enough to publish and rank.

SCORE CALIBRATION:
  90-100: Exceptional. Better than page 1 of Google right now. Rare — maybe 1 in 10.
  82-89:  Strong. Clear, useful, well-structured. Publish with confidence.
  78-81:  Solid. Minor issues but nothing that hurts the reader. Good to publish.
  70-77:  Needs work. Noticeable problems that could hurt ranking or trust.
  Below 70: Significant problems. Should not publish without major revision.

Most AI-generated affiliate articles should land in the 78-86 range. If you are
scoring most articles below 75, you are being too harsh. If most are above 88,
you are being too lenient.

ARTICLE DETAILS:
- Tool: {tool_name}
- Title: {title}
- Primary keyword: "{keyword}"
- Article type: {article_type}
- Word count: {word_count}
- H2 sections: {html_checks['h2_count']}
- CTA buttons: {html_checks['cta_count']}
{auto_issues}
{pattern_context}

ARTICLE CONTENT (plain text, first 30,000 chars):
{plain_text}

---

{scoring_criteria}
{type_criteria}

---

RESPOND IN THIS EXACT JSON FORMAT — nothing else:

{{
  "seo_score": <number 0-100>,
  "readability_score": <number 0-100>,
  "completeness_score": <number 0-100>,
  "overall_score": <number — weighted: SEO 35% + readability 30% + completeness 35%>,
  "approved": <true if overall_score >= {PASS_SCORE}, false otherwise>,
  "seo_notes": "<the single biggest SEO problem, or 'Passed' if genuinely no issues>",
  "readability_notes": "<the single biggest readability problem, or 'Passed'>",
  "completeness_notes": "<the single biggest completeness problem, or 'Passed'>",
  "deductions_applied": "<list the specific deductions you made, e.g. 'no keyword in intro -5, vague pricing -3'>",
  "editor_summary": "<2-3 sentences: overall quality assessment and the #1 thing to fix. Always include usefulness answers here>",
  "rewrite_instructions": "<if not approved: specific bullet points of what the writer must fix. if approved: 'N/A'>",
  "usefulness_q1": "<Yes or No — would this article be useful without search engines?>",
  "usefulness_q2": "<Yes or No — would this article still provide value in 6 months?>"
}}"""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)

        # Sanity check: if Claude still rubber-stamps (all 95+), flag it
        if (result.get("seo_score", 0) >= 95
                and result.get("readability_score", 0) >= 95
                and result.get("completeness_score", 0) >= 95):
            log(f"  ⚠️  Suspiciously high scores (all 95+) — Claude may be too lenient")

        # Enforce pass score check in case Claude got it wrong
        overall = result.get("overall_score", 0)
        result["approved"] = overall >= PASS_SCORE

        return result

    except json.JSONDecodeError as e:
        log(f"JSON parse error for {tool_name}: {e}")
        try:
            log(f"Raw response was: {raw[:500]}")
        except Exception:
            pass
        return None
    except Exception as e:
        log(f"Claude API error for {tool_name}: {e}")
        return None


# ═══════════════════════════════════════════════════════
# MAIN RUN
# ═══════════════════════════════════════════════════════

def run():
    log("Editor Agent starting")
    handoffs = db_helpers.load_all_handoffs()

    # Get pattern context from recent edits
    pattern_context = get_recent_patterns(handoffs)

    # Find articles pending edit
    pending_slugs = [slug for slug, article in handoffs.items()
                     if article.get("status") == "pending_edit"]

    # Also re-check articles that were rejected — they get a second chance
    rewrite_slugs = [slug for slug, article in handoffs.items()
                     if article.get("status") == "needs_rewrite"]

    all_slugs = pending_slugs + rewrite_slugs
    log(f"Found {len(pending_slugs)} articles pending edit + {len(rewrite_slugs)} needing re-review")

    if not all_slugs:
        log("Nothing to edit — exiting")
        return

    to_edit = all_slugs[:DAILY_CAP]
    if len(all_slugs) > DAILY_CAP:
        log(f"Cap applied — editing {DAILY_CAP} of {len(all_slugs)} today")

    approved_count = 0
    rejected_count = 0
    scores_this_run = []
    deductions_this_run = []  # collects deduction strings for feedback loop

    for slug in to_edit:
        article   = handoffs[slug]
        tool_name = article.get("tool_name", slug)
        article_type = article.get("article_type", "review")
        log(f"Editing: {tool_name} ({slug}) — type: {article_type}")

        # ── Hard-fail check (before any Claude call) ──────────────────────
        hard_fails = check_hard_fails(article)
        if hard_fails:
            reason = hard_fails[0]
            log(f"  [editor_agent] HARD FAIL: {reason} in {slug}")
            rejected_count += 1
            scores_this_run.append(0)
            db_helpers.update_handoff(slug, {
                "editor_scores":               {"overall_score": 0, "approved": False,
                                                "seo_score": 0, "readability_score": 0,
                                                "completeness_score": 0,
                                                "deductions_applied": f"HARD FAIL: {reason}",
                                                "editor_summary": f"HARD FAIL: {reason}"},
                "editor_reviewed":             datetime.now().strftime("%Y-%m-%d"),
                "editor_score":                0,
                "editor_feedback":             f"HARD FAIL: {reason}",
                "editor_rewrite_instructions": "; ".join(hard_fails),
                "editor_deductions":           f"HARD FAIL: {reason}",
                "status":                      "needs_rewrite",
            })
            continue

        scores = score_article(article, pattern_context)

        if scores is None:
            log(f"  ⚠️  Scoring failed — leaving as pending_edit")
            continue

        overall  = scores.get("overall_score", 0)
        approved = scores.get("approved", False)
        scores_this_run.append(overall)

        # Collect deduction phrases for feedback loop
        deductions_str = scores.get("deductions_applied", "")
        if deductions_str and deductions_str.lower() not in ("none", "n/a", "none listed"):
            deductions_this_run.append(deductions_str)

        log(f"  SEO: {scores.get('seo_score')} | Read: {scores.get('readability_score')} | Comp: {scores.get('completeness_score')} | Overall: {overall}")
        log(f"  Deductions: {scores.get('deductions_applied', 'none listed')}")

        new_status = "pending_publish" if approved else "needs_rewrite"

        if approved:
            approved_count += 1
            log(f"  ✅ APPROVED ({overall}/100) → pending_publish")
        else:
            rejected_count += 1
            log(f"  ❌ REJECTED ({overall}/100) → needs_rewrite")
            log(f"  Rewrite: {scores.get('rewrite_instructions', 'no instructions')[:200]}")

        db_helpers.update_handoff(slug, {
            "editor_scores":               scores,
            "editor_reviewed":             datetime.now().strftime("%Y-%m-%d"),
            "editor_score":                overall,
            "editor_feedback":             scores.get("editor_summary", ""),
            "editor_rewrite_instructions": scores.get("rewrite_instructions", ""),
            "editor_deductions":           scores.get("deductions_applied", ""),
            "status":                      new_status,
        })

    # ── Run summary with statistics ──
    total_edited = approved_count + rejected_count
    if total_edited > 0:
        avg_score = sum(scores_this_run) / len(scores_this_run) if scores_this_run else 0
        approval_rate = (approved_count / total_edited) * 100

        log(f"Editor run complete:")
        log(f"  Approved: {approved_count} | Rejected: {rejected_count}")
        log(f"  Approval rate: {approval_rate:.0f}%")
        log(f"  Average score: {avg_score:.1f}/100")
        log(f"  Score range: {min(scores_this_run)}-{max(scores_this_run)}")

        # Health check: if approval rate is too high or too low, flag it
        if approval_rate > 90 and total_edited >= 5:
            log(f"  ⚠️  Approval rate {approval_rate:.0f}% is suspiciously high — editor may be too lenient")
        elif approval_rate < 50 and total_edited >= 5:
            log(f"  ⚠️  Approval rate {approval_rate:.0f}% is very low — check if scoring prompt is too harsh")

        # ── Save editor feedback for article_agent self-learning ──────────
        _save_editor_feedback(deductions_this_run, total_edited, approved_count)

        print(f"\n✅ Editor done — {approved_count} approved, {rejected_count} rejected")
        print(f"   Avg score: {avg_score:.1f} | Approval rate: {approval_rate:.0f}%\n")
    else:
        log("No articles were successfully scored this run")
        print("\n⚠️  Editor done — no articles scored (check API connection)\n")


# ═══════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    run()