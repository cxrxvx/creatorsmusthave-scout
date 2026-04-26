# 🏛️ CXRXVX LLC — Master Architecture

The company bible. Upload this to every Claude project so any session understands the full empire.

**Company:** CXRXVX LLC
**Type:** AI-powered digital holding company
**Builder:** Alex — built between shifts, 100 metres above the North Sea
**One-liner:** "We build AI systems that make money while we sleep."
**Divisions:** 6 planned. 2 active. Launched sequentially — never in parallel.

---

## 🏢 Company Structure — 6 Divisions

```
CXRXVX LLC (holding company)
│
├── Division 1: CXRXVX Media          [ACTIVE — CMH live, pipeline running]
│   └── Owned content brands — affiliate commissions + display ads
│
├── Division 2: CXRXVX SEO            [BLUEPRINT COMPLETE — building next]
│   └── AI-powered local SEO — free audit tool + retainers + SaaS
│
├── Division 3: CXRXVX White-Label    [FUTURE — gate: 5+ agency clients]
│   └── AI SEO fulfillment for other agencies
│
├── Division 4: CXRXVX Newsletters    [FUTURE — gate: White-Label running]
│   └── AI-powered niche email publications
│
├── Division 5: CXRXVX Tools          [FUTURE — gate: Newsletters running]
│   └── Micro-SaaS standalone SEO tools
│
└── Division 6: CXRXVX Directories    [FUTURE — gate: Tools running]
    └── Local business listing sites — pay-per-lead + featured listings
```

---

## 🔑 Core Design Principle: Horizontal Scaling Through Config Files

**Both divisions scale the same way: by adding config files, not by rewriting code.**

CXRXVX Media adds a brand: copy `brands/_template.toml`, fill in details, create memory folder. 20 minutes.

CXRXVX SEO adds an industry: copy `industry_templates/_template.toml`, fill in GBP categories and keywords. 20 minutes.

CXRXVX SEO adds a client: copy from industry template, fill in business specifics. 20 minutes.

Every future division follows the same pattern. Config files define entities. Memory files store intelligence. Agents do the work. Telegram is the interface. This principle guides every technical decision.

---

## 🚦 Sequential Launch Order — One At A Time

**Rule: Never start the next division until the current one runs autonomously. No exceptions.**

### Division 1: CXRXVX Media — ACTIVE
**What:** AI-powered affiliate content brands (CMH, SSR, future brands)
**Status:** CMH live — 13 articles published, 33 pending, 13 agents, Phase 2.7J complete. April 24: 12-day downtime recovered, auto-renewal enabled. **April 26 morning: CTR optimization sprint complete on top 4 money pages. April 26 evening: affiliate_links.json expanded 4 → 13 active programs.**
**Revenue model:** Affiliate commissions + display ads
**Alex's time:** 5 min/week (Telegram approvals)
**Honest month 12:** $5,000-15,000/month
**Honest month 18-24:** $15,000-30,000/month
**Gate to start Division 2:** CMH Phase 3 CEO agent running. Pipeline autonomous.

### Division 2: CXRXVX SEO — BUILDING NEXT
**What:** Free audit tool → done-for-you retainers → self-service SaaS
**Status:** Blueprint complete. Build starts after CMH Phase 3.
**Revenue model:** Free audit (lead gen) → $1,500-5,000/mo retainers → $299-799/mo SaaS
**Alex's time:** 30 min/week (Telegram approvals)
**Honest month 12:** $15,000-30,000/month
**Honest month 18-24:** $25,000-50,000/month
**Gate to start Division 3:** 5+ paying agency clients. System 80% autonomous. Proven results.

### Division 3: CXRXVX White-Label — FUTURE
**What:** Other agencies pay you to run your AI SEO system under their brand. They sell, you fulfill.
**Why it's Division 3:** It reuses the exact same agents from Division 2. One config change: swap your branding for theirs on reports. Zero new code. Zero new infrastructure.
**Revenue model:** $500-800/month per client the partner agency brings
**Alex's time:** 10 min/week (Telegram approvals)
**Honest month 12 (from launch):** $8,000-20,000/month
**Honest month 18-24 (from launch):** $20,000-40,000/month
**Gate to start Division 4:** 5+ agency partners. Fulfillment running smoothly.

### Division 4: CXRXVX Newsletters — FUTURE
**What:** AI-curated niche newsletters.
**Revenue model:** Sponsorships + paid subscribers
**Alex's time:** 30 min/week
**Honest month 12 (from launch):** $1,000-5,000/month
**Honest month 18-24 (from launch):** $5,000-15,000/month
**Gate to start Division 5:** 1 newsletter at 3,000+ subscribers.

### Division 5: CXRXVX Tools — FUTURE
**What:** 3-5 tiny standalone SaaS tools.
**Revenue model:** $19-49/month per user × 3-5 tools
**Alex's time:** 0 min/week after launch.
**Honest month 12 (from launch):** $2,000-7,000/month
**Honest month 18-24 (from launch):** $7,000-15,000/month
**Gate to start Division 6:** 2+ tools live with 50+ total paying users.

### Division 6: CXRXVX Directories — FUTURE
**What:** Curated local business directories.
**Revenue model:** $99-199/month per featured listing OR $25-50 per lead
**Alex's time:** 0 min/week after setup.
**Honest month 12 (from launch):** $3,000-10,000/month
**Honest month 18-24 (from launch):** $10,000-30,000/month

---

## 📊 Honest Revenue Timeline — Sequential Stacking

| Timeline | Div 1 Media | Div 2 SEO | Div 3 White-Label | Div 4 Newsletters | Div 5 Tools | Div 6 Directories | TOTAL |
|---|---|---|---|---|---|---|---|
| Month 6 | $1,500-3,000 | $7,500-12,500 | not started | not started | not started | not started | $9,000-15,500 |
| Month 12 | $5,000-15,000 | $15,000-30,000 | $2,000-5,000 | not started | not started | not started | $22,000-50,000 |
| Month 18 | $10,000-20,000 | $20,000-35,000 | $8,000-20,000 | $1,000-3,000 | not started | not started | $39,000-78,000 |
| Month 24 | $15,000-30,000 | $25,000-50,000 | $15,000-30,000 | $3,000-10,000 | $2,000-7,000 | $3,000-10,000 | $63,000-137,000 |

**Conservative month 12:** $22,000-50,000/month. Retirement territory.
**Conservative month 24:** $63,000-137,000/month. Empire built.

---

## 🧠 Shared Intelligence Layer

### Shared directly (same file):
- memory/anti_ai_filter.md — all content avoids AI slop
- memory/debug_playbook.md — 5-step diagnosis
- Security patterns (.env, .gitignore)

### Same architecture, separate instances:
- TOML config system (brands, industries, clients, newsletter topics, tools, directories)
- Memory folder per entity
- Lessons log (Gotchas format)
- Runtime prompt loading from markdown
- Brand/client voice files loaded at runtime
- Pre-publish verification gates
- Activity log (cost tracking)
- CEO plan approval ("Here's what I'd do. Reply YES.")
- Telegram approval flow
- Shared DB module with auto-migrations
- Scheduler with entity-specific caps
- Health monitor
- Feedback loops (performance → prompts)
- Learnings table with temporal decay
- Screenshot Guidance System (Phase 3 NEW — per-entity variations)
- Decline Feedback Loop (Phase 3-4 NEW — per-entity feedback injected into rewrites)
- **CTR Framework (Phase 3 NEW April 26 — applies to ALL content-producing divisions)**

### Division-specific (not shared):
Each division has its own agents purpose-built for its specific work. Media agents write affiliate articles. SEO agents audit GBP listings. Newsletter agents curate and format. Tools run standalone. Directories manage listings.

---

## 🎯 The CTR Framework — Cross-Division Shared Pattern (Added April 26, 2026)

**Discovered in:** Division 1 (Media) — CMH brand
**Applies to:** All divisions that produce text-based content for Google search visibility
**Origin:** April 26, 2026 — Alex spent 90 minutes rewriting meta descriptions on top 4 CMH articles after diagnosing 0.1% CTR (50-150x below industry standard)

### Why this matters for ALL divisions

Every division that publishes content for Google traffic faces the same bottleneck:
- **Division 1 Media:** Affiliate review articles
- **Division 2 SEO Agency:** Industry blog posts that capture local SEO leads
- **Division 4 Newsletters:** Public newsletter landing pages and archived issues
- **Division 5 Tools:** Tool landing pages and how-to articles
- **Division 6 Directories:** Business listing pages

In every case, the gap between "Google shows you" and "user clicks you" is meta title + description quality.

### The 7 Rules (universal across divisions)

1. **Always read the actual content first** — verify every claim in meta exists in body (Atlassian-rule)
2. **Lead with a specific number in first 8 words** — prices, counts, durations
3. **Name a real test angle or specific signal** — proves first-hand authority
4. **Reference competitors when honest comparisons exist** — captures comparison searches
5. **End with a curiosity hook — often an HONEST weakness** — counterintuitive but clicks proven
6. **Match search intent in description** — review vs comparison vs pricing vs best-of
7. **Stay under pixel limits** — title ≤60 chars, description ≤920px

### Banned phrases (universal anti_ai_filter additions)

These tank CTR in every context:
- "Comprehensive guide"
- "Ultimate review"
- "Everything you need to know"
- "In-depth analysis"
- "Is It Worth It?" (overused as title)
- "Detailed breakdown"
- Generic adjectives: "powerful", "amazing", "incredible", "fantastic"

### Per-division application

**Division 1 Media:**
- Embedded in seo_agent.py (Phase 3)
- Pre-publish gate: anti-Atlassian verification (every numeric claim in description appears in article body)
- Loaded from memory/prompts/seo_prompt.md at runtime

**Division 2 SEO Agency:**
- Same 7 rules apply to client blog post meta descriptions
- Pre-publish gate verifies before pushing to client WordPress
- Loaded from memory/prompts/seo_prompt.md (shared between divisions)

**Future divisions:**
- Inherit memory/prompts/seo_prompt.md on day one
- Pre-publish gate is part of the standard pipeline scaffold
- New entities (brands, clients, newsletters) ship with framework already active

### Hard Limit reinforced

The CTR framework PROPOSES meta. Alex confirms via Telegram before any meta is published.

When the framework's anti-Atlassian gate flags a violation (claim in meta not in body), the agent SUGGESTS a rewrite — never auto-edits. Alex sees the flag in the Telegram approval message and can:
- Accept the auto-rewrite
- Manually adjust
- Decline (kicks back to article_agent for content rewrite)

**The framework is a quality multiplier, not an auto-publisher.**

---

## 🧠 Four-Layer Memory Architecture (Phase 3 — applies to all divisions)

Every division that runs autonomous agents uses the same four-layer memory split.

```
memory/
├── working/       # volatile, per-run state — cleared nightly
├── episodic/      # what happened in prior runs — activity_log with pain/importance/recurrence
├── semantic/      # abstractions that outlive any run — lessons.md, decisions.md, brand_voice.md
└── personal/      # stable preferences per entity (brand, client, newsletter, tool)
```

**Why the split matters for multi-brand/multi-entity:**
- `semantic/` transfers to new entities on day one — proven rules, not defaults
- `personal/` gets a new file per entity — never merged across entities
- `episodic/` and `working/` are entity-specific, never shared
- Shared files (`anti_ai_filter.md`, `debug_playbook.md`, `prompts/seo_prompt.md`) live at the root and apply universally

**Salience retrieval** — every agent that queries episodic memory uses a weighted formula:
```
salience = (10 - age_days × 0.3) × (pain / 10) × (importance / 10) × min(recurrence, 3)
```

**Nightly dream cycle** — runs at 03:00 via cron per division:
1. Find recurring patterns in episodic log
2. Propose promotion to semantic via Telegram (never auto-write)
3. Archive entries with salience < 2 older than 90 days
4. Git commit `memory/` with message `"dream cycle: promoted N, archived M, kept K"`

`git log memory/` becomes the division's autobiography.

**Hard Limit reinforced:** Dream cycle PROPOSES changes. Alex confirms via Telegram before any memory file is modified. No silent auto-edits, ever.

---

## 🏗️ Infrastructure (Shared Across All Divisions)

```
Hetzner VPS (~€4.50/month)
├── All division backends
├── All SQLite databases
├── Telegram bot (CEO agents for all divisions)
└── Backups (Backblaze B2)

Vercel (free tier)
├── Agency audit tool frontend
├── Micro-SaaS tool frontends
└── Directory site frontends (or WordPress)

Telegram (one channel)
└── Alex approves everything from one phone

Anthropic API (one account)
└── Haiku + Sonnet for all divisions

UptimeRobot (free tier — MANDATORY since April 24, 2026)
├── Every division's main domain monitored every 5 minutes
├── Email + Telegram alerts within 10 minutes of any downtime
└── Applies to: creatorsmusthave.com, agency audit tool, all future brand domains

Total infrastructure: ~$70-100/month for the ENTIRE empire
Each new division adds ~$15-40/month in API costs, zero infrastructure cost
```

---

## 🚨 Infrastructure Hard Rules (Added April 24, 2026)

**These are non-negotiable across ALL divisions.**

### Rule A: Auto-Renewal On Every Payment
Every recurring service that powers the empire must have auto-renewal enabled.

### Rule B: UptimeRobot On Every Production Domain Before Launch
No division goes live without uptime monitoring already configured.

### Rule C: Backup Before Any Destructive Operation

### Rule D: RankMath Global Settings Check After Every Plugin Update

### Rule E: CTR Framework Before Any Public Content (Added April 26, 2026)
No content-producing division publishes a page to a domain that earns Google impressions without:
1. The 7-rule CTR framework loaded in the SEO agent (memory/prompts/seo_prompt.md)
2. Anti-Atlassian gate active (every claim in meta verified against body)
3. Banned phrases list active in anti_ai_filter.md

**Why this is a Hard Rule:** CMH spent 7 weeks producing content with AI-default meta descriptions, achieving 0.1% CTR vs industry standard 5-15%. That's 50-150x revenue left on the table. Every division must inherit the CTR framework on day one — never bolt it on after.

---

## ⚠️ Threats & Defences

### Threat 1: Competitors copy your tools (12-18 months)
**Defence:** DATA MOAT.

### Threat 2: Google builds it into GBP (2-4 years)
**Defence:** DIVERSIFICATION across 6 divisions.

### Threat 3: AI search replaces Google Maps (3-5 years)
**Defence:** Local intent searches are the LAST category to shift.

### Threat 4: Clients DIY with AI assistants (2-3 years)
**Defence:** CONVENIENCE.

### Threat 5: AI content gets commoditised (12-24 months)
**Defence:** STRATEGY OVER EXECUTION + HONESTY-FIRST CTR FRAMEWORK.

The April 26 sprint discovered that **honest meta descriptions** ("where it falls flat", "what happens when X breaks") outperform AI-generated marketing-flavored descriptions. As AI content commoditises, this becomes the moat: AI tends toward generic positivity. Our framework deliberately embeds honest weaknesses in the meta. Skeptical buyers click the honest signal.

### Threat 6: Infrastructure single-point failures (mitigated)
**Status:** Actively mitigated via Rules A-E.

### Master Defence Strategy:
1. **Speed** — be established before competitors catch up.
2. **Data moat** — learnings table + benchmarking database.
3. **Relationships** — retainer clients who see monthly results don't leave.
4. **Diversification** — 6 divisions means no single disruption kills you.
5. **Move up the value chain** — from execution to intelligence.
6. **Own the client relationship** — done-for-you before SaaS.
7. **Infrastructure hygiene** — Rules A-E applied before any division goes live.
8. **Honesty-first content** — CTR framework embeds honest signals that AI default content can't replicate.

---

## ⚙️ Rules That Apply Across ALL Divisions

1. **Sequential launch only.**
2. **Alex approves everything from Telegram.**
3. **Config files, not code changes.**
4. **Memory compounds.**
5. **Per-entity isolation.**
6. **Cost tracking on everything.**
7. **Security first.**
8. **Honest metrics only.**
9. **One VPS, one Telegram, one phone.**
10. **Be cautious and steady.**
11. **Own your memory.**
12. **Own your harness.**
13. **Infrastructure hygiene is non-negotiable** (Rules A-D).
14. **CTR framework is non-negotiable for content divisions** (Rule E — added April 26).

---

## 🔒 Security Permissions Pattern (Phase 3 — applies to all divisions)

```
deny:  Bash(rm -rf *), Bash(*--force*), Edit(.env*), Edit(*.pem)
ask:   Bash(git push *), destructive DB operations
allow: Bash(python3 *), Bash(git commit *), Read(**)
```

**Priority order: deny > ask > allow.**

Implemented as a wrapper around all subprocess/shell calls. Never optional.

---

## 🤵 CEO Agent Design Principles (Phase 3 — applies to all divisions)

### 1. Constraint-First Diagnosis
"What is the ONE thing limiting progress right now?"

### 2. Type 1 / Type 2 Decision Framing
- **Type 2 (reversible):** "this is reversible — I can undo it."
- **Type 1 (irreversible):** "THIS IS IRREVERSIBLE." Requires deliberate YES.

### 3. Inversion Check in Health Monitor
Health monitor runs inversion checks: "What would guarantee failure?"

**Post-April 24, add to inversion checklist for every division:**
- Is any recurring bill due within 14 days with no auto-renewal? → alert
- Has any UptimeRobot check failed in last 24 hours without recovery? → alert
- Has RankMath (or equivalent) been updated in last 7 days without settings re-verification? → alert

**Post-April 26, add to inversion checklist:**
- Has any new article published with banned meta phrases (memory/anti_ai_filter.md)? → alert
- Has any meta description claim failed the anti-Atlassian gate (claim not in article body)? → alert
- Is any article with 100+ impressions still showing 0% CTR after 14 days? → flag for meta rewrite

**What NOT to implement in CEO agents:** Persona stacking. Clear logic, not personality theatre.

---

## 🧠 Self-Improvement Loop Design (Phase 3-4 — applies to all divisions)

### Foundation: Compound Learning System (Phase 3)

Every pipeline run produces reusable operational knowledge via `compound_step()`.

**Structured learnings database (`memory/learnings_db/`):**
JSON docs with: `problem_type`, `symptoms`, `root_cause`, `solution`, `prevention_steps`, `confidence_score`, `times_validated`, `created_date`, `source_brand`.

### Research Agent — Real Data Before Writing (Phase 4)

`research_agent.py` runs BETWEEN keyword_agent and article_agent.

### Two-Layer Improvement Architecture (Phase 4)

**Layer 1 — Article agent improves articles.**
**Layer 2 — Meta agent improves the evaluation criteria itself.**

### Cross-Brand Transfer

When Brand 2 (or any new entity) launches, it inherits:
- `editor_criteria.md` — proven scoring rules
- `brand_voice.md` structure
- `lessons.md` format
- `prompts/seo_prompt.md` — CTR framework (NEW April 26)
- Learnings table with cross-brand learnings flagged `source_brand = "universal"`

**One meta-improvement loop feeds all brands and all divisions.**

### Hard Limit — No Self-Modifying Code

Agents NEVER rewrite their own Python files. Memory files (`.md`, `.json`) can be updated by agents after Alex confirms via Telegram. Python code changes always require a human (Alex + Claude session).

---

## 📐 Context Management — Active Document Discipline

**200-line guideline per document.** When a document exceeds this, ask: is this active context or historical? Archive historical sections.

**Each division project has 4 active documents maximum.** CXRXVX_ARCHITECTURE.md is exempt — it's the company bible.

---

## 📄 Document Map

### CMH Claude Project (4 files):
1. README.md — CMH overview + progress + phases
2. PROGRAMMING_DOCS.md — CMH technical reference
3. BUSINESS_VISION.md — CMH strategy + revenue
4. **CXRXVX_ARCHITECTURE.md — THIS FILE**

### Agency Claude Project (4 files):
1. AGENCY_README.md — Agency overview + industries + expansion
2. AGENCY_PROGRAMMING_DOCS.md — Agency technical reference + CMH patterns
3. AGENCY_BUSINESS_VISION.md — Agency strategy + marketing
4. **CXRXVX_ARCHITECTURE.md — THIS FILE (same copy)**

### Reference Files (Alex's computer):
- CXRXVX_SEO_AGENCY_BLUEPRINT_v2.docx — Formatted blueprint
- cxrxvx_seo_audit_tool.jsx — Audit tool UI prototype
- CXRXVX_SITE_COPY_DECK.md — Website rewrite copy

---

*CXRXVX LLC — One person. AI agents. Infinite scale.*
*Built between shifts, 100 metres above the North Sea.*
*Be cautious. Be steady. Build one thing. Make it run. Start the next.*
*Created: March 25, 2026*
*Last updated: April 26, 2026 evening — added Rule E (CTR framework non-negotiable for content divisions), expanded Threat 5 defence with honesty-first CTR insight, added CEO inversion checks for meta quality, added shared seo_prompt.md as cross-division asset, expanded Cross-Brand Transfer to include CTR framework inheritance, noted CMH affiliate activation (4 → 13 programs).*
