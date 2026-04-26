# 🌐 Creators Must Have — Automated SEO Affiliate Content Pipeline

A self-running, self-learning, self-healing AI affiliate business. A CEO Agent manages all operations — Alex approves strategic decisions from Telegram.

**Parent company:** CXRXVX Affiliates
**Brand:** Creators Must Have — creatorsmusthave.com
**Tagline:** "The best tools for creators. Honestly reviewed."
**Builder:** Alex — offshore wind turbine technician building his retirement
**Business model:** Passive income from affiliate commissions + display ads across multiple autonomous niche sites
**Database:** SQLite only (pipeline.db) — dual-write ENDED Phase 2.7F ✅
**Stats:** 120+ tools, 134 keyword packages, 13 articles live, 33 pending publish, 0 needs_rewrite, 7 abandoned
**CEO Agent:** Central nervous system — monitors, heals, learns, recommends. Alex's only interface.
**GitHub:** https://github.com/cxrxvx/creatorsmusthave-scout

---

## ✅ Current Progress

### Phase 1 ✅ + Phase 2 ✅ + Phase 2.5 ✅ + Phase 2.7A–I ✅ + Phase 2.7J ✅ COMPLETE
13 agents built. 120+ tools scored. 134 keyword packages. 13 articles live. 33 pending publish. 0 needs_rewrite. 7 abandoned.

### 🎨 Site Design ✅ COMPLETE (March 10, 2026)
Full brand CSS installed site-wide via WordPress Customizer → Additional CSS.

### 👤 Persona ✅ COMPLETE (March 10, 2026)
- **Fictional reviewer:** Alex Builds
- **About page + How We Test page:** Live
- **Brand voice:** Negative Review Protection policy

---

# PART 1 — PASSIVE AFFILIATE EMPIRE

### Phase 2.6 — Revenue Activation 🔄 IN PROGRESS

**Affiliate programs:**
- [x] ElevenLabs — 22% recurring (PartnerStack) ✅ LIVE
- [x] Beehiiv — 50% recurring 12mo (Direct) ✅ LIVE
- [x] Mintly — 20% recurring (Direct) ✅ LIVE
- [x] Murf AI — 30% per sale (PartnerStack) ✅ LIVE
- [x] **Riverside.fm — Impact.com ✅ LIVE (April 26)** ← Added morning April 26
- [x] **Descript — $25 per sale (PartnerStack) ✅ APPROVED — added to JSON evening April 26**
- [x] **Kit (formerly ConvertKit) — 50% recurring (PartnerStack) ✅ APPROVED — added to JSON evening April 26**
- [x] **Gamma AI — 30% recurring (PartnerStack) ✅ APPROVED — added to JSON evening April 26**
- [x] **KoalaWriter — 30% recurring (Direct) ✅ APPROVED — added to JSON evening April 26**
- [x] **ContentDrips — 20% per sale (Direct) ✅ APPROVED — added to JSON evening April 26**
- [x] **Predis AI — recurring (FirstPromoter) ✅ APPROVED — added to JSON evening April 26**
- [x] **Citaable — 20% recurring (Direct) ✅ APPROVED — added to JSON evening April 26**
- [x] **Munch AI — recurring (Impact.com) ✅ APPROVED — added to JSON evening April 26**
- [ ] Krisp AI — Apply Now status (needs application)
- [ ] Stan Store — Pending since March 27 (needs follow-up)
- [ ] AIStudio Deepbrain, Citaable, Impact, Leonardo AI, Synthesia, Partnerstack T4 — Applied (waiting)
- [ ] FishAudio, Knowlify — Pending
- [x] ~~Loom — NO AFFILIATE PROGRAM AVAILABLE~~
- [x] ~~Canva — NO PUBLIC AFFILIATE PROGRAM AVAILABLE~~
- [x] **Chronicle — CANCELLED by them (April 26)** — was previously Approved

**Site setup:**
- [x] About page, How We Test page, author profile ✅ DONE
- [x] Google Search Console — sitemap submitted ✅ March 17
- [x] Google AdSense — applied, under review ✅
- [x] Beehiiv popup — LIVE ✅ March 21
- [x] www 301 redirect, /category/uncategorized noindex ✅ March 17
- [x] Entity SEO trinity — LinkedIn + Product Hunt + Crunchbase ✅ March 21
- [x] RankMath noindex fix ✅ March 27
- [x] **April 24: Downtime recovery complete ✅**
- [x] **April 26 morning: Top 4 money pages CTR-optimized ✅**
- [x] **April 26 evening: affiliate_links.json expanded 4 → 13 entries ✅**

---

## 🚀 APRIL 26, 2026 — TWO-PART SPRINT (CTR + AFFILIATE ACTIVATION)

### Part 1 — Morning: Meta Optimization Sprint (CTR Fix)

**Why:** Pre-session CTR was 0.1% (3 clicks on 5,000 impressions). Industry average for our positions: 5-15%. Bottleneck identified: AI-generated meta descriptions used generic patterns.

**Articles optimized (4):**
1. **Loom Review** — "Loom Review 2026: 1080p Tutorials at $14.99/Month" + new description
2. **Riverside FM Review** — "Riverside FM Review 2026: Tested vs Squadcast at $19/mo" + new description
3. **ElevenLabs Review** — "ElevenLabs Review 2026: 29 Languages Tested, From $5/mo" + new description
4. **Canva Review** — "Canva Pro Review 2026: Magic Resize Tested at $14.99/mo" + new description

All 4 saved in WordPress + re-indexing requested in GSC. Expected CTR climb to 0.5-1.5% within 28 days.

### Part 2 — Evening: Affiliate Activation Discovery + Setup

**Discovery:** Spreadsheet showed 12+ affiliate programs as "Approved" with affiliate URLs ready, but `affiliate_links.json` only had 4. Massive activation gap identified.

**Actions completed (evening April 26):**
- [x] Identified 8 ready-to-activate affiliate programs from spreadsheet (URLs already grabbed)
- [x] Riverside.fm affiliate URL added (Impact.com)
- [x] Discovered Munch AI URL (newly added to spreadsheet)
- [x] Discovered Chronicle was cancelled by them (no URL change needed — they had no URL anyway)
- [x] Backed up `memory/affiliate_links.json` → `memory/affiliate_links.json.backup`
- [x] Updated `memory/affiliate_links.json` from 4 entries to 13 entries via terminal
- [x] Verified JSON validity (13 entries confirmed)
- [x] Cleaned up an accidentally-created duplicate file at project root
- [x] Documented PartnerStack click data investigation (73 clicks were mostly self-testing during article development, not real visitors — confirmed by checking timestamps and patterns)

**NOT done tonight (deferred to next session):**
- [ ] Run `python3 affiliate_swap_agent.py` — auto-update existing 13 published articles with new affiliate URLs
- [ ] Verify articles updated correctly via spot-check
- [ ] Update spreadsheet statuses (Approved → Active for the 8 newly added)
- [ ] Apply to Krisp AI (Apply Now status)

**Decision rationale for deferring swap agent:** Late-night fatigue + production-touching script = poor verification quality. Better to run with fresh eyes in the morning when we can spot-check changes properly. Backup exists at `memory/affiliate_links.json.backup` for safety.

---

## 🧠 THE NEW CTR FRAMEWORK (Apply To All Future Articles)

This framework was built and tested April 26 morning. **Apply to every new article AND every queued draft before publishing.**

### The 7-Step Meta Writing Rules

**Rule 1: Always read the actual article first**
Never write meta from imagination or article title alone. Verify every claim in meta exists in article body. Atlassian-style mistakes (claims not in article) cause bounce → ranking penalty.

**Rule 2: Lead with a specific number in first 8 words**
Numbers stop the eye. Dollar signs especially.

**Rule 3: Name a real test angle**
Proves first-hand testing, separates from AI slop.

**Rule 4: Reference competitors when honest comparisons exist**
Captures comparison searches with high buyer intent.

**Rule 5: End with a curiosity hook — often an HONEST weakness**
Counterintuitive but proven: skeptical buyers click honest reviews.

**Rule 6: Match search intent in description**
- Review → "Tested for X. Where it wins, where it fails."
- Comparison → "Tested both. Winner depends on..."
- Best-of → "Tested 11. Only 3 work."

**Rule 7: Stay under pixel limits**
- Title: ≤60 chars (RankMath green at ≤580px)
- Description: ≤160 chars (RankMath green at ≤920px)

### Banned Phrases In Meta Descriptions

These phrases signal "AI-generated" and tank CTR:
- "Comprehensive guide"
- "Ultimate review"
- "Everything you need to know"
- "In-depth analysis"
- "Is It Worth It?" (overused)
- "Detailed breakdown"
- Generic adjectives: "powerful", "amazing", "incredible", "fantastic"

### Honest Weakness Hooks That Drive Clicks

Clickable BECAUSE they signal trust:
- "where [feature] falls flat"
- "where [feature] falls short"
- "the [N] limits nobody mentions"
- "what happens when [edge case]"
- "where it lags vs [competitor]"

---

## 🎯 IMMEDIATE PLAN TO CLEAR PHASE 3 GATE

**Phase 3 gate:** 30 articles live + $50+/mo revenue signal + Phase 2.6 complete.
**Current position:** 13 live, 33 pending, $0 revenue, 4 top pages CTR-optimized, 13 affiliate programs in JSON ready for swap.

### Order of operations:

#### NEXT SESSION (estimated 30-45 min):

1. **Install UptimeRobot** — free tier, 5-min interval, email + Telegram alerts (~5 min) — STILL PENDING from April 24
2. **Run `python3 affiliate_swap_agent.py`** — auto-update 13 published articles with new affiliate URLs (~5 min + verification)
3. **Spot-check 3 articles after swap** — confirm new affiliate URLs injected correctly (~10 min)
4. **Update spreadsheet statuses** — Approved → Active for the 8 newly added programs (~5 min)
5. **Apply to Krisp AI** — currently in "Apply Now" status (~5 min)
6. **Check April 26 meta updates in GSC** — confirm "Indexing requested" → "Indexed" within 7 days (~3 min)
7. **Add Riverside, Descript, Kit, Gamma to article writing prompts** — so future articles auto-include affiliate context

#### MONITOR — CTR data from optimized 4 pages (passive, ~5 min/week)

- Check GSC weekly for next 4 weeks
- Target: CTR climbs from 0.1% → 0.5-1.5% within 28 days
- If yes → apply CTR framework to remaining 9 articles
- If no → diagnose what else is wrong

#### Daily routine until queue drains:
- [ ] Accept/decline Telegram drafts daily
- [ ] **Apply CTR framework to each article BEFORE accepting** — rewrite meta if it uses banned phrases
- [ ] Run `python3 publisher_agent.py --cap 3` daily to publish 3 articles
- [ ] **Don't click own affiliate links for 7 days** to verify real visitor traffic vs self-tests
- [ ] Check AdSense approval status
- [ ] Monitor GSC for Validate Fix results from April 24 (expect 3-14 days)

#### Apply CTR framework to remaining 9 live articles (~2 hours, spread over 3-4 sessions)
- Notion, Stan Store, AI Video Repurposing roundup, Murf vs ElevenLabs, Krisp Accent, Opus Clip, etc.
- Same workflow: read article → draft → save → request indexing
- Spread across sessions to avoid GSC rate limits

#### Take real screenshots for top 5 articles (~2.5 hours, 1/day)
- Sign up free tier, screenshot interface, add to WordPress
- See "Screenshot Guidance System" in Phase 3 plan below

---

### Phase 2.7A — Content Quality ✅ COMPLETE
### Phase 2.7B — Infrastructure Hardening ✅ COMPLETE
### Phase 2.7C — Pipeline Flow Redesign ✅ COMPLETE (March 10)
### Phase 2.7D — Bug Fixes ✅ COMPLETE (March 11)
### Phase 2.7E — Content Quality Fix ✅ COMPLETE (March 11)
### Phase 2.7F — SQLite Migration ✅ COMPLETE (March 11)
### Phase 2.7G — Pipeline Hardening ✅ COMPLETE (March 16)
### Phase 2.7H — Bug Fixes & SEO Audit ✅ COMPLETE (March 17)
### Phase 2.7I — Content Quality & Pipeline Hardening ✅ COMPLETE (March 21)
### Phase 2.7J — Bug Fixes & Affiliate Pipeline ✅ COMPLETE (March 27)

---

### Phase 3 — Cloud + CEO Layer 1 ⬜
**Gate: 30 articles live + $50+/mo revenue signal + Phase 2.6 complete**

**Cloud:**
- [ ] Hetzner VPS (~€4.50/month)
- [ ] Retry & error recovery (exponential backoff decorator)
- [ ] Automated backups (Backblaze B2)
- [ ] Image optimization (WebP + <100KB)
- [ ] **UptimeRobot monitoring** ⬅️ Install next session
- [ ] Multi-brand config (brand_config.py)
- [ ] Modular codebase split (utils.py, prompts.py, constants.py)
- [ ] Security hooks (output-secrets-scanner, dangerous-actions-blocker)

**CEO Layer 1 — Operations:**
- [ ] ceo_agent.py — central brain
- [ ] activity_log table
- [ ] Telegram morning brief + evening summary + daily digest
- [ ] Natural language Telegram interpretation with plan approval
- [ ] CEO "stop and think" — shows plan before executing
- [ ] Auto-healing, atomic budget, link rot detection
- [ ] Observability — actual cost per agent run tracked
- [ ] Reddit monitoring agent

**CTR Framework Integration (added April 26 morning):**
- [ ] **seo_agent.py rewrite** — embed 7-rule CTR framework
- [ ] **memory/prompts/seo_prompt.md** — runtime-loaded CTR rules
- [ ] **Pre-publish gate** — verify meta description doesn't contain banned phrases
- [ ] **Article-meta consistency check** — verify every claim in meta exists in article body

---

### 📸 Phase 3 — Screenshot Guidance System ⬜ NEW (planned April 24)

**Problem:** Real product screenshots dramatically improve trust and CTR but require Alex's manual effort each time.

**Solution:** New agent `screenshot_guide_agent.py` sends Telegram instructions after article publish:
1. Tool to sign up for (free tier)
2. Screen-by-screen walkthrough (3-6 screenshots per article)
3. Specific UI elements to highlight
4. Caption text for each screenshot
5. Exact WordPress paragraph position

**Estimated build time:** 4-6 hours across Phase 3

---

### 💬 Phase 3 — Decline Feedback Loop ⬜ NEW (planned April 24)

**Problem:** When Alex declines an article, no structured feedback captured.

**Solution:** Bot asks "what's wrong?" on Decline. Alex replies with bullet points. Article goes back to article_agent with structured feedback.

**Why deferred:** Alex stated "next 50 articles I will do it on my own" (April 24).

**Estimated build time:** 2-3 hours

---

### Phase 4 — Intelligence + CEO Layer 2 ⬜
**Gate: Phase 3 stable + $200+/mo**

- [ ] `research_agent.py` — fetches live pricing, G2 reviews, Reddit BEFORE article_agent writes
- [ ] Prompt slimming — under 1500 words
- [ ] Personality anchor — 1 deep character profile
- [ ] Generate→evaluate→regenerate self-improvement loop
- [ ] Meta agent — monthly GSC/GA4 analysis
- [ ] Content refresh loop — top 20% pages refreshed weekly
- [ ] Strike zone keywords — GSC positions 5-20 auto-promoted
- [ ] Vector DB — semantic search + duplicate angle detection

### Phase 5 — Brand #2: StaySelfReliant.com ⬜
**Gate: CMH at $1K/mo × 2 months**

### Phase 6 — Revenue Optimization + Brand #3 + CEO Layer 3 ⬜
### Phase 7 — Compound & Scale ⬜

### 🏆 MILESTONE: 2-5 brands, $14,000-40,000/month, CEO manages everything

---

## 💸 Running Costs

| Stage | Daily | Monthly |
|---|---|---|
| Current (mixed Haiku/Sonnet) | ~$1.97 | ~$60 |
| + CEO Agent (Phase 3) | ~$2.30 | ~$70 |
| + Idle study sessions (Phase 3) | ~$0.10 | ~$3 |
| + UptimeRobot (free tier) | $0 | $0 |
| Per additional brand | ~$1.50-2.00 | ~$50-65 |

---

## 🔒 Security
- Phase 2.7B ✅: secrets in `.env`, startup validation, `.gitignore`
- Phase 2.7G ✅: bot token was visible in logs — regenerate via BotFather if not done
- Phase 3: automated backups to Backblaze B2
- Phase 3: output-secrets-scanner hook before every WordPress publish
- Phase 3: dangerous-actions-blocker on destructive DB operations

## 📬 Telegram Approval Gate ✅ REDESIGNED (March 10)
- Full pipeline → WordPress draft → Telegram → Alex reads → Accept/Decline
- Accept → publisher flips draft to live via REST API
- Decline → stays as draft, flagged for review
- **Phase 2.7J:** Telegram shows affiliate status (injected / homepage URL / N/A)
- **Phase 2.7J:** Daily affiliate digest at 08:00 — lists tools without links
- **Phase 3 (planned):** Screenshot guidance message after writing complete
- **Phase 3-4 (planned):** Decline feedback loop — bot asks "why" on rejection

## 📊 SEO Health (April 26, 2026 — End Of Day)
- **Impressions:** 5,000+ total (3-month view)
- **Clicks:** 3 (pre-CTR-optimization baseline)
- **CTR:** 0.1% — OPTIMIZATION DEPLOYED APRIL 26 MORNING, watching 28-day window
- **Average position:** 9.2
- **Top country:** USA (54%) — correct money market ✅
- **Top pages:**
  - Riverside FM: 1,981 impressions, position 9.6 — META OPTIMIZED + AFFILIATE LIVE
  - ElevenLabs: 958 impressions, position 8.9 — META OPTIMIZED + AFFILIATE LIVE
  - Loom: 829 impressions, **position #2 page 1** 🏆 — META OPTIMIZED
  - Canva: 610 impressions, **position #1 page 2** 🏆 — META OPTIMIZED
  - `/?p=11` (Krisp): 428 impressions, position 8.3
  - ElevenLabs vs Murf AI: 111 impressions, position 27.3
  - Krisp Accent: 87 impressions, position 15.1

**Indexed pages:** 10 of 13
**Sitemap status:** ✅ Success (24 URLs)
**Re-index requests April 26:** 4 (top money pages, all successful)
**affiliate_links.json:** 13 entries (was 4 morning of April 26)

## ⚠️ Known Issues
- **CTR pre-April 26: 0.1%** — fixed via meta rewrites April 26 morning, results pending 28-day window
- **Loom + Canva have no affiliate programs** — confirmed. Page-1 rankings still valuable for AdSense + email + cluster traffic + topical authority
- **Chronicle affiliate cancelled by them April 26** — was approved, now cancelled. No URL impact (never had one)
- **April 12-24 downtime** — FIXED with auto-renewal enabled April 24
- **33 queued articles use old prompt rules + old meta style** — apply CTR framework before accepting each from Telegram queue
- **affiliate_swap_agent.py NOT YET RUN** with new 13-entry JSON — queued for next morning session
- **Worktree backup files at `.claude/worktrees/`** — cosmetic, ignore (Claude session caches, not production)
- **PartnerStack 73 clicks** were mostly self-testing during article development, not real visitors — verified via timestamps + lack of corresponding GSC clicks
- **RankMath updates can reset global settings** — verified clean April 24
- **Bot token exposed in logs (March 16)** — regenerate via BotFather if not done
- **publisher_agent.py --slug not supported** — use `UPDATE handoffs SET priority_score=200` workaround
- **Write-ahead cap at 21** — 33 articles queued. Will drain at 3/day.
- **AdSense under review.**

---

## 📊 Pipeline Run Log

### April 26 — Two-Part Sprint (CTR + Affiliate)

**Morning — CTR Optimization:**
- Rewrote meta on 4 top money pages: Loom, Riverside FM, ElevenLabs, Canva
- Established 7-rule CTR framework
- All 4 saved + re-indexing requested in GSC
- Expected: CTR climbs 0.1% → 0.5-1.5% within 28 days

**Evening — Affiliate Activation:**
- Discovered 8 affiliate URLs ready in spreadsheet but missing from `memory/affiliate_links.json`
- Found path discrepancy: file is at `memory/affiliate_links.json` (not project root)
- Backed up production file before modification
- Updated `memory/affiliate_links.json` from 4 → 13 entries via terminal
- JSON validated (13 entries confirmed via Python)
- Cleaned up duplicate at wrong path
- Documented PartnerStack click investigation (73 clicks = self-testing, not real visitors)
- Identified Chronicle cancellation
- Identified Munch AI new approval
- Backup file safe at `memory/affiliate_links.json.backup`

**Deferred to next session (responsible call given fatigue):**
- Run swap agent on 13 live articles
- Spot-check article changes
- Update spreadsheet statuses

### April 24 — Downtime Recovery Session
- Diagnosed 12-day downtime — cause: missed SiteGround annual payment
- Site back up, auto-renewal enabled
- Sitemap resubmitted ("Success", 24 URLs)
- 4 GSC error categories diagnosed and fixed
- Confirmed rankings: Loom #2, Canva #1 page 2
- Identified CTR as next bottleneck

### March 27 — Phase 2.7J full session
(unchanged — see git history)

---

*A self-running, self-learning, self-improving passive income machine.*
*Builder: Alex — offshore wind turbine technician building his retirement*
*Last updated: April 26, 2026 evening — affiliate_links.json expanded 4 → 13 entries, CTR framework deployed on top 4 articles, swap agent deferred to next morning session for safe execution with fresh eyes*
*Status: Phase 2.7J ✅ COMPLETE — Phase 2.6 🔄 IN PROGRESS — Phase 3 ⬜ NEXT*
