"""
editor_agent.py — Strict Quality Editor for CXRXVX Affiliates
================================================================
Phase 2.5 Opus Upgrade:
  ✅ PASS_SCORE raised from 75 to 82
  ✅ Scoring prompt is genuinely harsh — finds problems, doesn't confirm quality
  ✅ Article type awareness — roundups/comparisons scored on their own criteria
  ✅ Structured feedback saved for article_agent self-learning loop
  ✅ Pattern tracking — detects recurring mistakes across articles
  ✅ Specific rewrite instructions when an article fails
  ✅ Score calibration notes — tells Claude what 90+ actually means

Expected results after upgrade:
  - Old: 16/16 approved, avg 92/100, zero rejections (rubber stamp)
  - New: ~70-80% approval, avg 84-88, meaningful quality gate

Drop this file into your cxrxvx-ai-empire/ folder to replace the old editor_agent.py.
"""

import json
import os
import re
from datetime import datetime
from anthropic import Anthropic

# ── Config ──────────────────────────────────────────────────────────────────
try:
    from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
except ImportError:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

client = Anthropic(api_key=ANTHROPIC_API_KEY)

MEMORY_DIR   = "memory"
HANDOFFS     = os.path.join(MEMORY_DIR, "handoffs.json")
LOGS_DIR     = os.path.join(MEMORY_DIR, "logs", "editor_agent")

# ⚡ Phase 2.5: raised from 75 to 82
# A real editor rejects 20-30% of drafts. 75 was a rubber stamp.
PASS_SCORE   = 82
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


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[editor_agent] {timestamp} — {msg}")
    log_file = os.path.join(LOGS_DIR, datetime.now().strftime("%Y-%m-%d") + ".log")
    with open(log_file, "a") as f:
        f.write(f"{timestamp} — {msg}\n")


def strip_html_tags(html):
    return re.sub(r"<[^>]+>", " ", html or "")


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
    lines.append("  → If this article has the same problems, deduct points aggressively.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# ARTICLE TYPE-SPECIFIC SCORING CRITERIA
# ═══════════════════════════════════════════════════════

def get_type_criteria(article_type: str) -> str:
    """Return extra scoring criteria based on article type."""

    if article_type == "roundup":
        return """
ROUNDUP-SPECIFIC CHECKS (score harshly if missing):
- Does it cover at least 5 tools?
- Does each tool have its own mini-review (not just a name and link)?
- Is there a Quick Picks / comparison table at the top?
- Does each tool section include pricing?
- Does each tool have specific pros AND cons (not just pros)?
- Is there a "How We Chose" methodology section?
- Is there a clear #1 pick with reasoning?
- Does the comparison table at the end cover at least 4 feature rows?
Deduct 5 points per missing element above. Roundups that just list tools
without genuine mini-reviews should score below 70."""

    elif article_type == "comparison":
        return """
COMPARISON-SPECIFIC CHECKS (score harshly if missing):
- Does it clearly state a winner upfront (Quick Verdict box)?
- Are there at least 3 feature-by-feature comparison sections?
- Does each comparison section declare a winner?
- Is the pricing comparison side-by-side with equivalent tiers?
- Are there separate "Who should choose X" and "Who should choose Y" sections?
- Is the final verdict clear and decisive (not wishy-washy "it depends")?
- Does it rank for BOTH tool names in the content?
Deduct 5 points per missing element. Comparisons that refuse to pick
a winner should score below 75."""

    elif article_type == "authority_article":
        return """
AUTHORITY ARTICLE CHECKS:
- There should be NO affiliate disclosure (remove if present)
- There should be NO CTA buttons
- Content should be purely informational and educational
- Should include at least 4 H2 sections of substantive content
Deduct 10 points if any affiliate elements are present."""

    else:
        # review or alert
        return """
REVIEW-SPECIFIC CHECKS (score harshly if missing):
- Is there a Key Takeaways box near the top?
- Is there a "Choose if / Skip if" decision table?
- Does the pricing section have EXACT plan names and dollar amounts?
- Are there at least 3 specific cons (not generic)?
- Is there a clear "Who it's NOT for" section with 2+ creator types?
- Does the verdict answer: who should buy, who should skip, and why?
Deduct 5 points per missing element."""


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
    """Score an article using Claude with a strict, problem-finding prompt."""
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
Each issue above should cost 3-5 points from the relevant dimension.
"""
    if html_checks["bonuses"]:
        bonus_list = ", ".join(html_checks["bonuses"])
        auto_issues += f"\nStructural elements present: {bonus_list}"

    # Get type-specific criteria
    type_criteria = get_type_criteria(article_type)

    plain_text = strip_html_tags(html)
    plain_text = plain_text[:30000]

    prompt = f"""You are a STRICT senior editor. Your job is to FIND PROBLEMS — not confirm quality.

You have been too lenient in the past. You approved 16 out of 16 articles with an average
score of 92/100 and zero rejections. That is not editing — that is rubber-stamping.
A good editor rejects 20-30% of articles. Most decent articles score 80-88. A score of
90+ should be RARE — reserved for genuinely exceptional work that makes you think
"this is better than what I'd find on page 1 of Google right now."

SCORE CALIBRATION — read this carefully:
  95-100: Exceptional. Could compete with Wirecutter or NerdWallet. Rare.
  88-94:  Very good. Publishable with confidence. Maybe 1 in 5 articles.
  82-87:  Good enough. Minor issues but nothing that hurts the reader.
  75-81:  Mediocre. Publishable but won't rank. Needs improvement.
  60-74:  Weak. Significant problems. Should not publish.
  Below 60: Fundamentally broken. Rewrite from scratch.

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

Score on THREE dimensions. ACTIVELY LOOK FOR PROBLEMS. Deduct points aggressively.

## 1. SEO SCORE (0-100, weight: 35%)
Check:
- Does "{keyword}" appear in the first 100 words? (-10 if not)
- Does it appear in at least one H2? (-5 if not)
- Are there 8+ related keywords used naturally? (-5 if fewer)
- Is there a proper FAQ with 4+ questions? (-8 if missing)
- Is the title under 65 characters? (-3 if over)
- Do H2 headings use keyword variations, not generic labels? (-5 if generic)
- Is the content genuinely more useful than what's currently on page 1? (-10 if it's just average)

## 2. READABILITY SCORE (0-100, weight: 30%)
Check:
- Does the intro hook the reader in 2 sentences? (-8 if generic opener)
- Are paragraphs 3 sentences or fewer? (-5 per wall-of-text section)
- Is the language direct and specific, not AI fluff? (-10 if corporate-speak)
- Does it avoid ALL banned phrases? (-3 per banned phrase found)
- Do sections flow naturally? (-5 if transitions feel robotic)
- Would a real person enjoy reading this? (-10 if it reads like a template)
- Is every section at least 100 words of substance? (-5 per thin section)

## 3. COMPLETENESS SCORE (0-100, weight: 35%)
Check:
- EXACT pricing with real plan names and dollar amounts? (-15 if vague or missing)
- At least 3 SPECIFIC cons? "Learning curve" doesn't count. (-10 if generic)
- "Who it's NOT for" with 2+ specific creator types? (-10 if missing)
- Affiliate disclosure present and after the hook? (-5 if missing or misplaced)
- Verdict that answers: who should buy, who should skip, why? (-8 if vague)
- Does it avoid fake social proof and invented stats? (-15 if found)
- Are CTAs specific ("Start editing faster with Descript →") not generic? (-5 if generic)
{type_criteria}

---

IMPORTANT: Actually count deductions. Start at 100 for each dimension and subtract
for each problem found. Don't just eyeball a number. Show your work mentally.

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
  "deductions_applied": "<list the specific deductions you made, e.g. 'no keyword in intro -10, vague pricing -15'>",
  "editor_summary": "<2-3 sentences: overall quality assessment and the #1 thing to fix>",
  "rewrite_instructions": "<if not approved: specific bullet points of what the writer must fix. if approved: 'N/A'>"
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
    handoffs = load_json(HANDOFFS, {})

    # Get pattern context from recent edits
    pattern_context = get_recent_patterns(handoffs)

    # Find articles pending edit
    pending_slugs = [slug for slug, article in handoffs.items()
                     if article.get("status") == "pending_edit"]
    log(f"Found {len(pending_slugs)} articles pending edit")

    if not pending_slugs:
        log("Nothing to edit — exiting")
        return

    to_edit = pending_slugs[:DAILY_CAP]
    if len(pending_slugs) > DAILY_CAP:
        log(f"Cap applied — editing {DAILY_CAP} of {len(pending_slugs)} today")

    approved_count = 0
    rejected_count = 0
    scores_this_run = []

    for slug in to_edit:
        article   = handoffs[slug]
        tool_name = article.get("tool_name", slug)
        article_type = article.get("article_type", "review")
        log(f"Editing: {tool_name} ({slug}) — type: {article_type}")

        scores = score_article(article, pattern_context)

        if scores is None:
            log(f"  ⚠️  Scoring failed — leaving as pending_edit")
            continue

        # ── Save scores in TWO formats: ──
        # 1. Full scores object (for debugging and display)
        article["editor_scores"] = scores
        article["editor_reviewed"] = datetime.now().strftime("%Y-%m-%d")

        # 2. Flat fields that article_agent can easily read for self-learning
        article["editor_score"] = scores.get("overall_score", 0)
        article["editor_feedback"] = scores.get("editor_summary", "")
        article["editor_rewrite_instructions"] = scores.get("rewrite_instructions", "")
        article["editor_deductions"] = scores.get("deductions_applied", "")

        overall  = scores.get("overall_score", 0)
        approved = scores.get("approved", False)
        scores_this_run.append(overall)

        log(f"  SEO: {scores.get('seo_score')} | Read: {scores.get('readability_score')} | Comp: {scores.get('completeness_score')} | Overall: {overall}")
        log(f"  Deductions: {scores.get('deductions_applied', 'none listed')}")

        if approved:
            article["status"] = "pending_publish"
            approved_count += 1
            log(f"  ✅ APPROVED ({overall}/100) → pending_publish")
        else:
            article["status"] = "needs_rewrite"
            rejected_count += 1
            log(f"  ❌ REJECTED ({overall}/100) → needs_rewrite")
            log(f"  Rewrite: {scores.get('rewrite_instructions', 'no instructions')[:200]}")

    save_json(HANDOFFS, handoffs)

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