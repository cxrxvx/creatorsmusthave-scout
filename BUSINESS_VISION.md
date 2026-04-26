# 🚀 Creators Must Have — Vision & Roadmap

A fully autonomous affiliate website that discovers the best creator tools, writes SEO content, publishes articles, earns recurring commissions, and gets smarter every day — without human intervention.

**Parent company:** CXRXVX Affiliates
**Company site:** cxrxvx.com
**Brand:** Creators Must Have — creatorsmusthave.com
**Tagline:** "The best tools for creators. Honestly reviewed."
**Builder:** Alex — offshore wind turbine technician building his retirement
**Business model:** Passive income from affiliate commissions + display ads across multiple autonomous niche sites
**GitHub:** https://github.com/cxrxvx/creatorsmusthave-scout

---

## 🎯 The Vision

A self-running, self-learning, self-healing, self-improving affiliate empire:
- A CEO Agent is the central nervous system — the ONLY interface between Alex and the entire operation
- Alex checks Telegram once a day, sends natural language messages or approves/denies recommendations, and goes back to work
- The system discovers products, writes articles, publishes them, earns commissions, detects problems, fixes them, learns what works, and does more of it — all autonomously
- New brands launch by adding one config file — CEO manages all brands from one dashboard
- Revenue compounds because the system literally gets smarter every cycle

**The milestone that matters:** 2-5 brands producing $14,000-40,000/month combined passive income with Alex approving strategic decisions from his phone.

---

## 🏢 Architecture — CEO as Central Nervous System

```
👤 ALEX (on a wind turbine — Telegram only)
  │
  ↕ Telegram (only communication channel)
  │
🤵 CEO AGENT (ceo_agent.py) — the brain
  │
  ├── 📊 INTELLIGENCE DIVISION
  │     Tool Scout          ✅ → 13 RSS + 14 Reddit, 120+ tools
  │     Keyword Agent       ✅ → 134 keyword packages, cannibalization guard
  │     Research Agent      ⬜ Phase 4 → fetches live pricing, G2 reviews, Reddit before writing
  │     Competitor Analyst  ⬜ Phase 4
  │
  ├── ✍️ CONTENT DIVISION
  │     Article Writer      ✅ → brand_voice + anti_ai_filter + research-based framework
  │     Editor Agent        ✅ → runtime editor_criteria.md
  │     SEO Agent           ✅ → runs POST-publisher (rewrite Phase 3 with CTR framework)
  │     Image Agent         ✅ → None crash fixed + screenshot verification
  │     Screenshot Guide    ⬜ Phase 3 NEW → Telegram walkthrough of screenshots to take
  │
  ├── 📤 PUBLISHING DIVISION
  │     Publisher Agent     ✅ → verify gate + affiliate tracking + tool_url resolution
  │     Internal Link Agent ✅ → leftover placeholder cleanup
  │     Approval Bot        ✅ → Accept/Decline, flips draft to live
  │     Decline Feedback    ⬜ Phase 3-4 NEW → bot asks "why" on reject, feeds back to writer
  │     CTR Framework Gate  ⬜ Phase 3 NEW → verifies meta uses 7-rule CTR framework before publish
  │
  ├── 💰 REVENUE DIVISION
  │     Affiliate Links      ✅ → 13 active programs (was 4 morning of April 26)
  │     Affiliate Swap Agent ✅ → auto-updates published articles (NEEDS RUN next session)
  │     Affiliate Digest     ✅ → daily Telegram list of tools without links
  │     Email List (Beehiiv) ✅ → Popup LIVE 30s delay
  │     Display Ads          🔄 → AdSense applied, under review
  │
  ├── 🗄️ DATA LAYER
  │     db_helpers.py         ✅ → shared SQLite module + affiliate_pending column
  │     pipeline.db           ✅ → single source of truth
  │     Memory files          ✅ → brand_voice, anti_ai_filter, lessons, prompts/, debug_playbook
  │     Learnings DB          ⬜ Phase 3 → structured compound knowledge base
  │     Vector DB             ⬜ Phase 4
  │
  └── 📈 MONITORING DIVISION
        Health Monitor      ✅ → 10 checks + freshness
        Watchdog            ✅ → real error diagnosis
        Scheduler           ✅ → 3/day cap + affiliate digest + swap agent
        CEO Compound Step   ⬜ Phase 3 → extracts learnings after every pipeline run
        Security Hooks      ⬜ Phase 3
        Observability       ⬜ Phase 3
        UptimeRobot         ⬜ Next session → free tier, 5-min checks
```

---

## 🔄 Article Pipeline Flow (Phase 2.7J+ — with Phase 3 additions)

```
tool_scout → keyword_agent
→ research_agent (Phase 4: fetches live pricing, G2 reviews, Reddit mentions)
→ article_agent (brand_voice + anti_ai_filter + research brief + editor feedback for rewrites)
→ editor_agent (editor_criteria.md → hard-fail rules → usefulness test)
→ image_agent (hero + screenshot + logo — verified before injection)
→ internal_link_agent (placeholders replaced or cleaned up)
→ seo_agent (Phase 3: CTR framework — title + description with 7 rules)
→ ctr_framework_gate (Phase 3 NEW: verify every claim in meta exists in article body)
→ publisher_agent (verify: affiliate + word count + no placeholders + no href="#" → WP draft)
→ screenshot_guide_agent (Phase 3 NEW: Telegram sends screenshot walkthrough)
→ Telegram notification (shows affiliate status)
→ Alex reads draft → Accept / Decline
→ decline_feedback_loop (Phase 3-4 NEW: if Decline, bot asks "why", feeds back)
→ affiliate_swap_agent (daily — updates homepage URLs when affiliate links become available)
→ CEO compound_step (Phase 3: extracts learnings, updates learnings_db)
```

**Status flow:** `needs_rewrite` → `pending_edit` → `pending_publish` → `pending_approval` → `published` / `rejected` / `abandoned`

---

## 🧠 Self-Learning Layers (44 total — 1 new April 26)

| Layer | Description | Status |
|---|---|---|
| 1 | Brand identity (brand_config.py) | Phase 3 |
| 2 | Shared Brain (SQLite pipeline.db) | ✅ Phase 2.7F |
| 3 | Editor → Writer feedback loop | ✅ Phase 2.7G |
| 4 | Established tool fallback | ✅ Built |
| 5 | Field normalizer | ✅ Built |
| 6 | Daily agent logs (activity_log) | Phase 3 |
| 7 | Brand voice file (brand_voice.md) | ✅ Phase 2.7I |
| 8 | Cannibalization guard | ✅ Phase 2.7A |
| 9 | Keyword density rules | ✅ Phase 2.7E |
| 10 | Lessons log — Gotchas format | ✅ Phase 2.7I |
| 11 | Editor feedback loop (editor_feedback.json) | ✅ Phase 2.7G |
| 12 | Prompt version tracking | ✅ Phase 2.7G |
| 13 | Usefulness test | ✅ Phase 2.7G |
| 14 | Anti-AI writing filter (anti_ai_filter.md) | ✅ Phase 2.7I |
| 15 | Runtime prompt files (memory/prompts/) | ✅ Phase 2.7I |
| 16 | Pre-publish verification gate | ✅ Phase 2.7I, hardened Phase 2.7J |
| 17 | Editor feedback injected into rewrites | ✅ Phase 2.7J |
| 18 | Style rotation forced for rewrites | ✅ Phase 2.7J |
| 19 | Affiliate pending tracking | ✅ Phase 2.7J |
| 20 | Daily affiliate digest | ✅ Phase 2.7J |
| 21 | Automatic affiliate link swapping | ✅ Phase 2.7J |
| 22 | Research-based review framework (honest attribution) | ✅ Phase 2.7J |
| 23 | Anti-keyword-stuffing rules | ✅ Phase 2.7J |
| 24 | Article variation rules (structure + voice diversity) | ✅ Phase 2.7J |
| 25 | Tool maturity matching (new vs established depth) | ✅ Phase 2.7J |
| 26 | Duplicate disclosure detection + removal | ✅ Phase 2.7J |
| 27 | CEO operational memory | Phase 3 |
| 28 | Idle study sessions | Phase 3 |
| 29 | Weekly rhythm + task routing | Phase 3 |
| 30 | Observability — actual cost per run | Phase 3 |
| 31 | Reddit monitoring agent | Phase 3 |
| 32 | Self-improvement loop (generate→evaluate→regenerate) | Phase 4 |
| 33 | Content refresh loop — top 20% pages | Phase 4 |
| 34 | Vector DB (semantic search + duplicate angles) | Phase 4 |
| 35 | CEO decision memory + revenue learning | Phase 6-7 |
| 36 | Four-layer memory architecture | Phase 3 |
| 37 | Salience-scored activity log | Phase 3 |
| 38 | Nightly dream cycle — episodic → semantic | Phase 3-4 |
| 39 | CEO constraint-first diagnosis + Type 1/Type 2 framing | Phase 3 |
| 40 | Inversion check in health monitor | Phase 3 |
| 41 | "Destinations and fences" prompts | Phase 4 |
| 42 | Screenshot Guidance System — CEO sends walkthrough per article | Phase 3 NEW |
| 43 | Decline Feedback Loop — bot asks "why", feeds back | Phase 3-4 NEW |
| **44** | **CTR Framework — 7 rules embedded in seo_agent + anti-Atlassian gate** | **Phase 3 NEW (April 26)** |

---

## 📊 SEO & Content Strategy

- Long-tail keywords — difficulty max 30 for first 6 months
- E-E-A-T signals — Alex Builds persona, About page, How We Test ✅
- Entity SEO trinity — LinkedIn + Product Hunt + Crunchbase ✅
- AEO content formatting ✅
- Negative Review Protection ✅
- Five article types — reviews, roundups, comparisons, alerts, authority
- Google-safe ramp — 3/day → 5/day → uncapped
- Write-ahead cap — skip writing if 21+ drafts queued
- Draft-first publishing ✅
- Anti-AI writing filter ✅
- Brand voice file ✅
- Research-based review framework ✅ (Phase 2.7J)
- Anti-keyword-stuffing rules ✅ (Phase 2.7J)
- Article variation rules ✅ (Phase 2.7J)
- Affiliate tracking + auto-swap ✅ (Phase 2.7J)
- **CTR Framework — 7 rules for meta descriptions ✅ (April 26 — applied manually to top 4)** ← NEW
- Content refresh loop — top 20% pages weekly ⬜ (Phase 4)
- Strike zone keywords — positions 5-20 promoted ⬜ (Phase 4)
- Real product screenshots via Screenshot Guidance System ⬜ (Phase 3 NEW)

### 📈 Live SEO Performance (April 26, 2026 — Day 52, post-CTR-optimization)

**3-month GSC snapshot:**
- **5,000+ impressions** (was 2,730 March 27 — +83% growth despite 12-day downtime)
- **3 clicks** | **0.1% CTR** ← OPTIMIZATION DEPLOYED APRIL 26, watching 28-day window
- **Average position 9.2** — bottom of page 1
- **Top country:** USA 54% — correct money market

**Top pages (3-month view, all 4 META OPTIMIZED April 26):**
| Page | Impressions | Position | Status |
|---|---|---|---|
| Riverside FM review | **1,981** | 9.6 | ✅ Meta optimized + Affiliate LIVE (April 26) |
| ElevenLabs review | 958 | 8.9 | ✅ Meta optimized + Affiliate LIVE (PartnerStack) |
| Loom review | 829 | **#2 page 1** 🏆 | ✅ Meta optimized + No affiliate (Loom doesn't offer) |
| Canva review | 610 | **#1 page 2** 🏆 | ✅ Meta optimized + No affiliate (Canva doesn't offer) |
| `/?p=11` → Krisp | 428 | 8.3 | Ghost URL — auto-redirects |
| ElevenLabs vs Murf | 111 | 27.3 | Page 3 — needs work |
| Krisp Accent | 87 | 15.1 | Page 2 |

**Confirmed wins (April 26):**
- Riverside grew from 1,909 → 1,981 impressions in 2 days (Google still actively showing)
- Loom holding position #2 on page 1
- Canva holding position #1 on page 2
- 4 articles all re-indexed successfully after meta updates
- Brand voice + anti-AI filter producing content that Google ranks above human-written competitors

**Entity SEO trinity complete** ✅ March 21
**Sitemap resubmitted** ✅ April 24 — status "Success", 24 URLs discovered
**Downtime recovery** ✅ April 24 — auto-renewal enabled, 10 of 13 pages retained indexing
**CTR optimization sprint** ✅ April 26 — top 4 money pages, framework documented for future articles

### 🧠 The CTR Framework (Self-Learning Layer 44 — Established April 26)

**Why this matters for the vision:**

This is the missing piece between "ranking on page 1" and "earning revenue." Pre-April 26, articles ranked but didn't get clicked. Post-April 26, the system has explicit rules that turn rankings into clicks.

**The 7 rules:**

1. **Read article first** — verify every claim in meta exists in article body (anti-Atlassian rule)
2. **Lead with specific number** — "$X/mo:" or "tested 14 [things]"
3. **Name a real test angle** — proves first-hand testing
4. **Reference competitors** when honest — captures comparison searches
5. **End with curiosity hook** — often an HONEST weakness ("where comedy falls flat")
6. **Match search intent** — review vs comparison vs pricing vs best-of
7. **Stay under pixel limits** — 60 chars title, 920px description

**Applied to:** Top 4 money pages April 26 (Loom, Riverside, ElevenLabs, Canva)
**Will be applied to:** Remaining 9 live articles + all 33 queued drafts + every new article going forward
**Phase 3 plan:** Embed these rules in seo_agent.py with anti-Atlassian verification gate

**Counterintuitive insight discovered April 26:** Skeptical buyers click HONEST reviews. Admitting weaknesses in the meta description gets MORE clicks, not fewer. "Where it lags" beats "Best tool ever!" every time.

---

## 💰 Revenue Projections

| Timeline | Articles | Traffic | Affiliate | Display Ads | Total |
|---|---|---|---|---|---|
| Month 1 | 15-30 | ~500 | $0-50 | $0 | $0-50 |
| Month 3 | 60-80 | ~3,000 | $200-500 | $0 | $200-500 |
| Month 6 | 150-200 | ~15,000 | $1,500-4,000 | $150-300 | $1,650-4,300 |
| Month 12 | 350-400 | ~50,000 | $5,000-15,000 | $750-1,250 | $5,750-16,250 |

**Current status (end of month 2):** 13 articles live, ~5,000 impressions (3-mo view), $0 revenue, 4 articles at competitive ranking positions, all 4 META OPTIMIZED April 26. **CTR optimization is the bridge from "impressions" to "revenue" — first real test in next 28 days.**

### Honest revenue scenarios at 500 articles (added April 26)

**Pessimistic (no CTR improvement):** ~$30-80/mo total
**Realistic (CTR climbs to 1.5%, industry standard):** ~$5,200/mo
**Optimistic (CTR 2.5%, some champion articles):** ~$17,000/mo + AdSense $1,500-3,000/mo

**The deciding factor between "$80/mo" and "$5,200/mo" at 500 articles is whether the CTR framework works.** April 26's experiment is the test.

---

## 🗺️ Roadmap

### ✅ COMPLETE
- Phase 1 — Foundation
- Phase 2 — Quality & Volume
- Phase 2.5 — Opus Optimization Sprint (March 8, 2026)
- Phase 2.7A through 2.7J — all complete (March 27, 2026)
- **April 24 — Downtime recovery operations complete**
- **April 26 — CTR optimization sprint complete (top 4 money pages)**

### 🔄 IN PROGRESS
- Phase 2.6 — Revenue Activation
- **Phase 2.6.5 — CTR Framework Application** (informal: applying framework to remaining 9 live articles + 33 queued drafts)

### ⬜ Phase 3 — Cloud + CEO Layer 1
Gate: 30 articles live + $50+/mo + Phase 2.6 complete
**New features added April 24:** Screenshot Guidance System, Decline Feedback Loop
**New features added April 26:** CTR Framework integrated into seo_agent.py (Spec 8)

### ⬜ Phase 4 — Intelligence + CEO Layer 2
Gate: Phase 3 stable + $200+/mo

### ⬜ Phase 5 — Brand #2: StaySelfReliant.com
Gate: CMH at $1K/mo × 2 months

### ⬜ Phase 6-7 — Revenue Optimization + Scale

### 🏆 END GOAL
```
2-5 brands running autonomously
CEO Agent manages everything — Alex approves from Telegram
$14,000-40,000/month combined passive income
```

---

*A self-running, self-learning, self-improving passive income machine.*
*Parent: CXRXVX Affiliates*
*Builder: Alex — offshore wind turbine technician building his retirement*
*Last updated: April 26, 2026 evening — affiliate_links.json expanded 4 → 13 entries (Riverside, Descript, Kit, Gamma, KoalaWriter, ContentDrips, Predis AI, Citaable, Munch AI added), CTR framework deployed on top 4 articles morning of same day, swap agent run deferred to next morning session*
*Status: Phase 2.7J ✅ COMPLETE — Phase 2.6 🔄 IN PROGRESS — Phase 3 ⬜ NEXT*
