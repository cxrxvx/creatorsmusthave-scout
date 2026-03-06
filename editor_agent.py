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
PASS_SCORE   = 75
DAILY_CAP    = 15

os.makedirs(LOGS_DIR, exist_ok=True)

# ── Helpers ──────────────────────────────────────────────────────────────────
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

# ── Core editor logic ─────────────────────────────────────────────────────────
def score_article(article: dict) -> dict:
    tool_name    = article.get("tool_name", "Unknown")
    title        = article.get("article_title", "")
    keyword      = article.get("primary_keyword", "")
    html         = article.get("article_html", "")
    article_type = article.get("article_type", "review")
    word_count   = article.get("word_count", 0)

    plain_text = strip_html_tags(html)
    plain_text = plain_text[:30000]

    prompt = f"""You are a senior SEO content editor reviewing affiliate articles before they go live on a creator tools review site.

ARTICLE DETAILS:
- Tool: {tool_name}
- Title: {title}
- Primary keyword: {keyword}
- Article type: {article_type}
- Word count: {word_count}

ARTICLE CONTENT (plain text):
{plain_text}

---

Score this article on THREE dimensions. Be honest and strict — vague AI fluff should cost points.

## 1. SEO SCORE (0-100)
Check:
- Does the primary keyword "{keyword}" appear in the first 100 words?
- Does it appear in at least one H2 heading?
- Are there 8+ related keywords/phrases used naturally?
- Does it have a proper FAQ section with 4+ questions?
- Is the title compelling and under 65 characters?
- Are there clear H2 and H3 subheadings throughout?
Deduct heavily for: keyword stuffing, missing keyword in intro, no FAQ section.

## 2. READABILITY SCORE (0-100)
Check:
- Are paragraphs short (3-4 sentences max)?
- Is there a clear intro that hooks the reader in the first 2 sentences?
- Does it avoid walls of text?
- Is the language plain and direct (not corporate/AI fluff)?
- Are there bullet points or lists to break up information?
- Does it flow naturally from section to section?
Deduct heavily for: long unbroken paragraphs, generic opener ("In today's digital world..."), banned phrases like "game-changer" or "revolutionary" or "seamless".

## 3. COMPLETENESS SCORE (0-100)
Check (these are MANDATORY for every review):
- Does it include EXACT pricing with real plan names and prices?
- Does it include SPECIFIC cons (not just "can be expensive" — actual limitations)?
- Does it have a "Who it's NOT for" section with at least 2 specific groups?
- Does it have an affiliate disclosure near the top?
- Does it have a clear recommendation / verdict section?
- Does it avoid fake social proof or invented statistics?
Deduct heavily for: missing any of the above mandatory items.

---

RESPOND IN THIS EXACT JSON FORMAT — nothing else, no explanation outside the JSON:

{{
  "seo_score": <number 0-100>,
  "readability_score": <number 0-100>,
  "completeness_score": <number 0-100>,
  "overall_score": <number — weighted average: SEO 35% + readability 30% + completeness 35%>,
  "approved": <true if overall_score >= 75, false otherwise>,
  "seo_notes": "<one sentence on the biggest SEO issue or 'Passed' if fine>",
  "readability_notes": "<one sentence on the biggest readability issue or 'Passed' if fine>",
  "completeness_notes": "<one sentence on the biggest completeness issue or 'Passed' if fine>",
  "editor_summary": "<2-3 sentences summarising overall quality and the single most important fix if not approved>"
}}"""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
        return result

    except json.JSONDecodeError as e:
        log(f"JSON parse error for {tool_name}: {e}")
        log(f"Raw response was: {raw[:300]}")
        return None
    except Exception as e:
        log(f"Claude API error for {tool_name}: {e}")
        return None

# ── Main run ──────────────────────────────────────────────────────────────────
def run():
    log("Editor Agent starting")
    handoffs = load_json(HANDOFFS, {})

    # handoffs.json is a dict keyed by slug
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

    for slug in to_edit:
        article   = handoffs[slug]
        tool_name = article.get("tool_name", slug)
        log(f"Editing: {tool_name} ({slug})")

        scores = score_article(article)

        if scores is None:
            log(f"  ⚠️  Scoring failed — leaving as pending_edit")
            continue

        article["editor_scores"]   = scores
        article["editor_reviewed"] = datetime.now().strftime("%Y-%m-%d")

        overall  = scores.get("overall_score", 0)
        approved = scores.get("approved", False)

        log(f"  SEO: {scores.get('seo_score')} | Readability: {scores.get('readability_score')} | Completeness: {scores.get('completeness_score')} | Overall: {overall}")
        log(f"  Summary: {scores.get('editor_summary', '')}")

        if approved:
            article["status"] = "pending_publish"
            approved_count += 1
            log(f"  ✅ APPROVED ({overall}/100) → pending_publish")
        else:
            article["status"] = "needs_rewrite"
            rejected_count += 1
            log(f"  ❌ REJECTED ({overall}/100) → needs_rewrite")
            log(f"  Fix needed: {scores.get('completeness_notes', '')} | {scores.get('readability_notes', '')}")

    save_json(HANDOFFS, handoffs)

    log(f"Editor run complete — Approved: {approved_count} | Rejected: {rejected_count}")
    print(f"\n✅ Editor done — {approved_count} approved, {rejected_count} flagged for rewrite\n")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run()