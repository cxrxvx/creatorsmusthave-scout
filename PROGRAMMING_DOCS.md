# 🛠️ Creators Must Have — Programming Documentation

**Project folder:** ~/cxrxvx-ai-empire
**GitHub:** https://github.com/cxrxvx/creatorsmusthave-scout
**Current phase:** Phase 2.7J ✅ COMPLETE — Phase 2.6 🔄 IN PROGRESS — Phase 3 ⬜ NEXT
**Goal:** Self-running passive affiliate empire. CEO Agent manages everything. Alex approves from Telegram.

---

## ✅ Environment Status (April 26, 2026 — End Of Day)

| Item | Status |
|---|---|
| creatorsmusthave.com | ✅ Live (SiteGround, GeneratePress) |
| SiteGround auto-renewal | ✅ ENABLED April 24 |
| UptimeRobot monitoring | ⬜ Install next session (free tier, 5-minute checks) |
| WordPress | ✅ Live (RankMath, Pretty Links, UpdraftPlus, Code Snippets, Popup Maker, Ads.txt Manager) |
| Python 3.14.3 + venv | ✅ Ready — activate with `source venv/bin/activate` |
| SQLite (pipeline.db) | ✅ at `memory/pipeline.db` — 120+ tools, 134 keywords, 13 live, 33 pending |
| handoffs.json | ✅ Archived read-only |
| db_helpers.py | ✅ Shared SQLite module |
| 13 agents | ✅ All built, tested, Phase 2.7J hardened |
| Telegram approval gate | ✅ Draft-first flow, Accept/Decline, WP preview, affiliate status |
| Site CSS design | ✅ COMPLETE |
| Persona | ✅ Alex Builds — About page + How We Test page live |
| **`memory/affiliate_links.json`** | ✅ **13 entries (April 26 evening — was 4)** ← UPDATED |
| **`memory/affiliate_links.json.backup`** | ✅ **Created April 26 evening (4-entry backup before expansion)** ← NEW |
| **Riverside affiliate** | ✅ LIVE April 26 — Impact.com |
| **Descript affiliate** | ✅ APPROVED — added to JSON April 26 evening |
| **Kit affiliate** | ✅ APPROVED — added to JSON April 26 evening (50% recurring — highest commission) |
| **Gamma affiliate** | ✅ APPROVED — added to JSON April 26 evening |
| **KoalaWriter affiliate** | ✅ APPROVED — added to JSON April 26 evening |
| **ContentDrips affiliate** | ✅ APPROVED — added to JSON April 26 evening |
| **Predis AI affiliate** | ✅ APPROVED — added to JSON April 26 evening |
| **Citaable affiliate** | ✅ APPROVED — added to JSON April 26 evening |
| **Munch AI affiliate** | ✅ APPROVED — added to JSON April 26 evening |
| Chronicle affiliate | ❌ CANCELLED by them April 26 (was approved March 11, never had URL active) |
| affiliate_swap_agent.py run with new entries | ⬜ DEFERRED to next session for safe execution |
| affiliate_swap_agent.py | ✅ Phase 2.7J — auto-updates published articles |
| Daily affiliate digest | ✅ Phase 2.7J — 08:00 Telegram digest |
| Google Analytics | ✅ Internal IP filtered, bot filter on |
| Google Search Console | ✅ Sitemap "Success" (24 URLs) |
| Google AdSense | ✅ Applied, ads.txt authorized |
| Beehiiv popup | ✅ LIVE 30s delay |
| beautifulsoup4 | ✅ Installed in venv |
| requirements.txt | ✅ Created March 16 |
| memory/lessons.md | ✅ Gotchas format — through GOTCHA-005 (added April 26) |
| memory/editor_feedback.json | ✅ Auto-generated after each editor run |
| memory/brand_voice.md | ✅ Voice Rules + Product Facts + ICA Profile |
| memory/anti_ai_filter.md | ✅ 60+ banned words and phrases |
| memory/prompts/article_prompt.md | ✅ Loaded at runtime |
| memory/prompts/editor_criteria.md | ✅ Loaded at runtime |
| **memory/prompts/seo_prompt.md** | ⬜ NEW — to be created Phase 3 with CTR framework |
| memory/debug_playbook.md | ✅ 5-step diagnosis pattern |
| Pre-publish verification gate | ✅ Blocks bad articles |
| WRITE_AHEAD_CAP | 21 — 33 articles queued, drains at 3/day |
| Daily publish cap | ✅ 3/day |
| GitHub | ✅ Phase 2.7J merged to main |
| Pretty Links redirects | ✅ 1 active (April 24) |
| **Top 4 money pages CTR-optimized** | ✅ April 26 morning |
| **Re-index requested for 4 pages** | ✅ April 26 morning |

---

## ⚠️ Critical Workflow Notes

### Always activate venv before running pipeline:
```bash
cd ~/cxrxvx-ai-empire
source venv/bin/activate
python3 scheduler.py --now
```

Running without venv = beautifulsoup4 not found = image agent crashes.

### File location reminders (NEW — added April 26 after a near-miss):

These files are NOT in the project root — they're in `memory/`:
- `memory/affiliate_links.json` ← affiliate URL mapping
- `memory/pipeline.db` ← SQLite database
- `memory/lessons.md` ← gotchas log
- `memory/brand_voice.md`
- `memory/anti_ai_filter.md`
- `memory/debug_playbook.md`
- `memory/editor_feedback.json`
- `memory/prompts/*.md` ← runtime-loaded agent prompts

**If a script fails with "file not found" — check if you're missing the `memory/` prefix.**

There are also Claude session backup files at `.claude/worktrees/*/memory/` — these are session caches and should NEVER be edited directly. They're cosmetic snapshots, not production files.

---

## 📄 Agent Reference (13 built)

| Agent | Model | Status |
|---|---|---|
| tool_scout.py | Haiku | ✅ 13 RSS + 14 Reddit — 120+ tools |
| keyword_agent.py | Haiku | ✅ 134 packages — cannibalization guard |
| article_agent.py | Sonnet | ✅ brand_voice + anti_ai_filter + editor feedback in rewrites |
| editor_agent.py | Sonnet | ✅ runtime editor_criteria.md |
| image_agent.py | Haiku | ✅ None crash fixed + screenshot verification |
| seo_agent.py | Haiku | ✅ runs POST-publisher — REWRITE NEEDED Phase 3 to embed CTR framework |
| publisher_agent.py | Python | ✅ verify gate + affiliate tracking + tool_url resolution |
| internal_link_agent.py | Sonnet | ✅ leftover placeholder cleanup |
| affiliate_swap_agent.py | Python | ✅ auto-updates published articles — **needs run with new 13-entry JSON next session** |
| health_monitor.py | Python | ✅ 10 checks + freshness |
| watchdog.py | Python | ✅ real error diagnosis |
| scheduler.py | Python | ✅ 3/day cap + affiliate digest + swap agent |
| db_helpers.py | Python | ✅ shared SQLite module + auto-migrations |

---

## 📱 Pipeline Order (Phase 2.7J+)

```
Write → Edit → Image → Internal Links → Verify → Publisher (WP Draft) → Telegram → SEO → Accept/Decline
```

**Daily scheduled jobs:**
- 08:00: Health monitor + Affiliate digest (Telegram)
- 08:30: Affiliate swap agent

**Status flow:**
`needs_rewrite` → `pending_edit` → `pending_publish` → `pending_approval` → `published` / `rejected` / `abandoned`

---

## 🐛 Debugging Guide

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'bs4'` | Activate venv: `source venv/bin/activate` |
| Daily cap hit | `UPDATE counters SET value=0 WHERE key='articles_published_today'` |
| Article stuck pending_approval | `db_helpers.update_handoff('slug', {'status': 'pending_edit', 'wp_post_id': None, ...})` |
| Want specific article first | `UPDATE handoffs SET priority_score=200 WHERE slug='your-slug'` |
| Affiliate links not injecting | Check `memory/affiliate_links.json` key matches tool_name exactly (case-insensitive resolver) |
| pipeline.db empty | Wrong path — use `memory/pipeline.db` not `./pipeline.db` |
| **affiliate_links.json not found** | **It's at `memory/affiliate_links.json`, not project root. NEW reminder April 26.** |
| Pipeline lock stuck | Delete `memory/.pipeline_lock` |
| Telegram buttons not working | Run scheduler.py — never publisher_agent.py standalone |
| New affiliate link not appearing | Run `python3 affiliate_swap_agent.py` |
| Site down — check first | SiteGround dashboard → Billing status, domain expiry, Resource Usage |
| GSC says noindex but page source clean | Click Validate Fix + wait 3-14 days |
| GSC says 5xx during known downtime | Will self-heal once site is back |
| GSC 404 on deleted article with impressions | Set up Pretty Links 301 redirect |
| **Meta description pixel meter red** | **Tighten by removing "the", "and", redundant nouns. Use "/mo" not "/month"** |
| **RankMath score crashes after meta rewrite** | **Ignore — focus keyword no longer in title/desc. Score is cosmetic, not Google's judgment** |
| **Article gets traffic but 0 clicks** | **CTR problem — apply 7-step CTR framework (Spec 8)** |
| **PartnerStack shows clicks but GSC doesn't** | **Likely your own testing during article development. Verify by checking timestamps + 7-day no-self-click test** |

---

## 🚀 PHASE 2.6.5 — TWO-PART SPRINT (April 26, 2026)

### Part 1: CTR Optimization (Morning)

**Why:** Pre-April 26 CTR was 0.1% (3 clicks on 5,000 impressions).

**Articles optimized (4):**

#### Loom Review (`/loom-review-content-creators-2026/`)
- New title: `Loom Review 2026: 1080p Tutorials at $14.99/Month`
- New description: `Loom at $12.50/mo for unlimited recordings — worth it for tutorials? Tested 1080p quality, instant sharing, and the 25-video free cap. Honest verdict.`

#### Riverside FM Review (`/riverside-fm-review-podcasters-2026/`)
- New title: `Riverside FM Review 2026: Tested vs Squadcast at $19/mo`
- New description: `Riverside FM at $19/mo: 4K video, uncompressed WAV audio. Tested vs Squadcast — local recording, quality, and what happens if internet drops.`

#### ElevenLabs Review (`/elevenlabs-review-podcast-voiceovers/`)
- New title: `ElevenLabs Review 2026: 29 Languages Tested, From $5/mo`
- New description: `ElevenLabs from $5/mo: tested voice cloning, 29 languages, 5 podcast genres. Where it beats Descript and Murf — and where comedy falls flat.`

#### Canva Review (`/canva-review-social-media-managers-2026/`)
- New title: `Canva Pro Review 2026: Magic Resize Tested at $14.99/mo`
- New description: `Canva Pro at $14.99/mo: tested Magic Resize, Brand Kit, and AI tools for social posts. Where it beats Adobe — and where video editing falls short.`

**All 4 saved + re-indexed via GSC.**

### Part 2: Affiliate Activation (Evening)

**What was done:**
- Discovered 8 ready-to-activate affiliate URLs in spreadsheet
- Backed up `memory/affiliate_links.json` to `memory/affiliate_links.json.backup`
- Updated `memory/affiliate_links.json` from 4 → 13 entries via `cat > memory/affiliate_links.json << EOF`
- JSON validated via Python (13 entries confirmed)
- Removed an accidentally-created duplicate at project root

**The new `memory/affiliate_links.json` (current state):**
```json
{
  "ElevenLabs": "https://try.elevenlabs.io/creatorsmusthave",
  "Beehiiv": "https://www.beehiiv.com?via=creatorsmusthave",
  "Mintly": "https://usemintly.com/?ref=creatorsmusthave",
  "Murf AI": "https://get.murf.ai/hgfneu0as3m3",
  "Riverside": "https://riverside.sjv.io/JkLXyQ",
  "Descript": "https://get.descript.com/creatorsmusthave",
  "Kit": "https://partners.kit.com/creatorsmusthave",
  "Gamma": "https://try.gamma.app/n4s20jaz7jj9",
  "KoalaWriter": "https://koala.sh/?via=creatorsmusthave",
  "ContentDrips": "https://contentdrips.tolt.io/",
  "Predis AI": "https://predis.ai?ref=creatorsmusthave",
  "Citaable": "https://getcitable.com/ref/PK7VWBTV",
  "Munch AI": "https://goto.munchstudio.com/B5zaDL"
}
```

**What was DEFERRED to next session:**
- Run `python3 affiliate_swap_agent.py` to update all 13 published articles with new affiliate URLs
- Spot-check 3 articles after swap to confirm correct injection
- Update affiliate spreadsheet statuses (Approved → Active for 8 newly added)
- Apply to Krisp AI (Apply Now status)

**Why deferred:** Late-night fatigue + production-touching script = poor verification quality. Morning session with fresh eyes is the safer call. Backup exists for safety.

### NEW GOTCHA-006 (added April 26 evening)

```
GOTCHA-006: affiliate_links.json lives in memory/, not project root

Symptom: cp affiliate_links.json affiliate_links.json.backup → "No such file or directory"

Cause: Initial assumption that affiliate_links.json was at project root was wrong. 
The file actually lives at memory/affiliate_links.json (consistent with other memory files: 
memory/pipeline.db, memory/lessons.md, etc.). Always check `memory/` first when handling 
project state files.

Impact: If we'd run cat > affiliate_links.json << EOF without checking, we'd have created 
a duplicate file at project root with no production impact (agents read from memory/), but 
also wasted time troubleshooting "why aren't my new affiliate links working".

Fix: When working with project state files, always verify location with:
find ~ -name "FILENAME" -type f 2>/dev/null
First. The `memory/` subdirectory is the standard for all CMH state files.

First seen: April 26, 2026 evening — affiliate_links.json expansion 4 → 13 entries.
```

---

## 🧠 NEW SPEC 8 — CTR FRAMEWORK (added April 26 morning)

**Will be embedded in seo_agent.py during Phase 3.**

### The 7 Rules

1. **Read article first** — verify every claim in meta exists in article body
2. **Lead with specific number in first 8 words**
3. **Name a real test angle**
4. **Reference competitors when honest comparisons exist**
5. **End with curiosity hook — often an HONEST weakness**
6. **Match search intent**
7. **Stay under pixel limits** (Title ≤60 chars / ≤580px, Description ≤160 chars / ≤920px)

### Banned Phrases (add to anti_ai_filter.md)

- "Comprehensive guide"
- "Ultimate review"
- "Everything you need to know"
- "In-depth analysis"
- "Is It Worth It?" (overused as title)
- "Detailed breakdown"
- Generic adjectives: "powerful", "amazing", "incredible", "fantastic"

### Honest Weakness Hooks That Work

- "where [feature] falls flat"
- "where [feature] falls short"
- "the [N] limits nobody mentions"
- "what happens when [edge case]"
- "where it lags vs [competitor]"

### Implementation (Phase 3)

```python
def generate_seo_meta(article_html, tool_name, focus_keyword):
    ctr_rules = load_seo_prompt()  # from memory/prompts/seo_prompt.md
    real_facts = extract_facts_from_article(article_html)
    # Generate title + description using rules + verified facts
    # Pre-publish check: every numeric/product claim in description must appear in article body
    return {
        "title": optimized_title,
        "description": optimized_description,
        "verified_claims": list_of_facts_used
    }
```

### NEW GOTCHA-005 (added April 26 morning)

```
GOTCHA-005: Meta descriptions written by AI without reading article create false claims

Symptom: Meta description references something not in article (e.g. "Atlassian price hike" 
when article never mentions Atlassian).

Cause: AI agent (or human) drafts meta from title + memory, doesn't verify against article.

Impact: Reader clicks expecting X, article delivers Y, bounce rate → ranking penalty.

Fix: Always read article body BEFORE drafting meta. Every numeric claim, product name, 
and specific feature in meta must appear in the article. Implemented as pre-publish 
verification gate Phase 3.

First seen: April 25, 2026 — Loom meta drafted with "Atlassian price hike" reference, 
caught by Alex before publish.
```

### Cost & timing

- **Implementation cost:** ~$0.005 extra per article
- **Implementation time:** 2-3 hours during Phase 3
- **Expected CTR lift:** 0.1% → 0.5-1.5%
- **Revenue impact:** At 100 articles, this is the difference between ~$80/mo and ~$1,000/mo

---

## 💰 affiliate_links.json — Current State (April 26 evening)

**Location:** `memory/affiliate_links.json` (NOT project root)
**Backup:** `memory/affiliate_links.json.backup` (4-entry pre-expansion state)
**Total entries:** 13 (was 4 morning of April 26)

```json
{
  "ElevenLabs": "https://try.elevenlabs.io/creatorsmusthave",
  "Beehiiv": "https://www.beehiiv.com?via=creatorsmusthave",
  "Mintly": "https://usemintly.com/?ref=creatorsmusthave",
  "Murf AI": "https://get.murf.ai/hgfneu0as3m3",
  "Riverside": "https://riverside.sjv.io/JkLXyQ",
  "Descript": "https://get.descript.com/creatorsmusthave",
  "Kit": "https://partners.kit.com/creatorsmusthave",
  "Gamma": "https://try.gamma.app/n4s20jaz7jj9",
  "KoalaWriter": "https://koala.sh/?via=creatorsmusthave",
  "ContentDrips": "https://contentdrips.tolt.io/",
  "Predis AI": "https://predis.ai?ref=creatorsmusthave",
  "Citaable": "https://getcitable.com/ref/PK7VWBTV",
  "Munch AI": "https://goto.munchstudio.com/B5zaDL"
}
```

Keys must match `tool_name` in handoffs (case-insensitive via `_resolve_affiliate_entry()`).
**Run `python3 affiliate_swap_agent.py` next session to apply these to existing articles.**

**Confirmed unavailable affiliate programs:**
- Loom (no public program)
- Canva (no public program)
- Chronicle (cancelled by them April 26 — was approved March 11)

---

## 📋 Task List

### IMMEDIATE — Next session (~30-45 min):

- [ ] **Install UptimeRobot** (~5 min) — STILL PENDING from April 24
- [ ] **Activate venv:** `source venv/bin/activate` (~5 sec)
- [ ] **Run swap agent:** `python3 affiliate_swap_agent.py` (~5 min)
- [ ] **Spot-check 3 articles** to verify affiliate URLs swapped correctly (~10 min)
  - Verify on creatorsmusthave.com directly via incognito
  - Look at: any article mentioning Descript, Kit, or Gamma — should now have affiliate URL
- [ ] **Update spreadsheet statuses** Approved → Active for the 8 newly-added programs (~5 min)
- [ ] **Apply to Krisp AI** — Apply Now status (~5 min)
- [ ] **Check April 26 meta updates in GSC** — confirm "Indexing requested" → "Indexed" (~3 min)

### IMMEDIATE — Daily routine until queue drains:
- [ ] Accept/decline Telegram drafts daily
- [ ] **Apply CTR framework to each article BEFORE accepting from Telegram queue**
- [ ] Run `python3 publisher_agent.py --cap 3` daily
- [ ] **DO NOT click own affiliate links for 7 days** (verify real visitor traffic vs self-tests)
- [ ] Apply to remaining affiliate programs (Krisp, Stan Store follow-up, etc.)
- [ ] Check AdSense approval status
- [ ] Check RankMath Titles & Meta after any plugin update
- [ ] Monitor GSC for Validate Fix results from April 24

### IMMEDIATE — Manual WordPress fixes:
- [ ] Fix keyword stuffing in Riverside review BODY content (meta done, body next)
- [ ] Fix duplicate disclosure in AI Video Repurposing roundup
- [ ] Fix keyword stuffing in Stan Store review if present
- [ ] **Apply CTR framework to remaining 9 live articles** (~2 hours, 3-4 sessions)
- [ ] Take real screenshots for top 5 articles (~2.5 hours, 1/day)

### Phase 2.6 (in progress):
- [ ] Reddit presence — 14 subreddits (authentic community member, not spam)
- [ ] Stan Store follow-up email (pending since March 27)
- [ ] Drain article queue — publish 3/day until 30 articles live
- [ ] Check AdSense approval status

### Phase 3:
- [ ] Hetzner VPS, backups, monitoring
- [ ] Security hooks (output-secrets-scanner, dangerous-actions-blocker)
- [ ] ceo_agent.py + activity_log + Telegram digest
- [ ] CEO compound learning system
- [ ] Observability — actual cost per agent run
- [ ] Reddit monitoring agent
- [ ] **Screenshot Guidance System (Spec 6)**
- [ ] **Decline Feedback Loop (Spec 7)**
- [ ] **CTR Framework integrated into seo_agent.py (Spec 8)**
- [ ] **memory/prompts/seo_prompt.md created with CTR framework**
- [ ] **Pre-publish CTR verification gate**

### Phase 4:
- [ ] `research_agent.py` — fetches live pricing, G2 reviews, Reddit
- [ ] Prompt slimming — under 1500 words
- [ ] Personality anchor — 1 deep character profile
- [ ] Generate→evaluate→regenerate self-improvement loop
- [ ] Meta agent — monthly GSC/GA4 analysis
- [ ] Content refresh loop
- [ ] Vector DB

### Phase 5:
- [ ] TOML team templates per brand
- [ ] Per-brand memory folder structure
- [ ] brand_config.py

---

## 🔮 Phase 3 Prep — Design Specs

### Spec 1: `activity_log` table schema (Phase 3)
### Spec 2: Four-Layer Memory Reorganization (Phase 3)
### Spec 3: Nightly Dream Cycle (Phase 3-4)
### Spec 4: CEO Agent Design Principles (Phase 3)
### Spec 5: "Destinations and Fences" Prompt Rewrite (Phase 4)
### Spec 6: Screenshot Guidance System (Phase 3)
### Spec 7: Decline Feedback Loop (Phase 3-4)
### Spec 8: CTR Framework In seo_agent.py (Phase 3) ← see full spec above

(Full specs preserved in earlier doc revisions — see git log)

---

## 📊 Pipeline Run Log

### April 26 — Two-Part Sprint (CTR + Affiliate Activation)

**Morning — CTR Optimization:**
- Rewrote SEO title + description for top 4 money pages
- Established 7-rule CTR framework
- All 4 re-indexed in GSC (successful)
- **No code changes** — pure WordPress + GSC operations
- Identified GOTCHA-005 (anti-Atlassian rule)
- Banned phrases identified for anti_ai_filter.md additions

**Evening — Affiliate Activation:**
- Discovered 8 ready-to-activate affiliate URLs in spreadsheet
- Identified Chronicle cancellation (no impact — never had URL)
- Discovered Munch AI new approval
- File location near-miss: confirmed `memory/affiliate_links.json` is the production file (NOT project root)
- Backed up `memory/affiliate_links.json` → `memory/affiliate_links.json.backup`
- Updated `memory/affiliate_links.json` from 4 → 13 entries via terminal `cat > ... << EOF`
- Validated JSON (13 entries confirmed via `python3 -c "import json..."`)
- Cleaned up duplicate at wrong path
- Identified GOTCHA-006 (memory/ prefix reminder)
- PartnerStack click investigation: 73 clicks were mostly self-testing during article development, not real visitors

**Deferred (responsible call given fatigue):**
- Run `python3 affiliate_swap_agent.py` on 13 live articles
- Spot-check article changes
- Update spreadsheet statuses
- Apply to Krisp AI

### April 24 — Downtime Recovery Session
(unchanged — see git log)

### March 27 — Phase 2.7J full session
(unchanged — see git log)

---

*Last updated: April 26, 2026 evening — affiliate_links.json expanded 4 → 13 entries via terminal, swap agent deferred to next session for safe execution, 2 new gotchas identified (GOTCHA-005 anti-Atlassian, GOTCHA-006 memory/ path)*
*Status: Phase 2.7J ✅ COMPLETE — Phase 2.6 🔄 IN PROGRESS — Phase 3 ⬜ NEXT*
*Builder: Alex — offshore wind turbine technician building his retirement*
