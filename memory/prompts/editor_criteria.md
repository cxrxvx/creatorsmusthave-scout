# Editor Scoring Criteria

Loaded at runtime by editor_agent.py — edit this file to change scoring rules.

Pass score: 78. Target approval rate: 70-80%. Below 50% = too harsh. Above 90% = too lenient.

---

## Hard-Fail Checks (run BEFORE scoring — any one of these = score 0, auto-reject)

1. **PLACEHOLDER URLS** — Does the article contain `[AFFILIATE_LINK]`, `REPLACE_WITH_TOOL_URL`, or any `href` attribute with square brackets like `href="[TOOL_URL]"`?
2. **EMOJI IN HEADINGS** — Are there any emoji characters inside H1, H2, or H3 tags?
3. **TOO SHORT** — Is the article body empty or under 500 words?

If ANY hard-fail condition is true, return score 0, `approved: false`, with the specific failure reason in `editor_summary`.

---

## Score Calibration

```
90-100: Exceptional. Better than page 1 of Google right now. Rare — maybe 1 in 10.
82-89:  Strong. Clear, useful, well-structured. Publish with confidence.
78-81:  Solid. Minor issues but nothing that hurts the reader. Good to publish.
70-77:  Needs work. Noticeable problems that could hurt ranking or trust.
Below 70: Significant problems. Should not publish without major revision.
```

Most AI-generated affiliate articles should land in the 78-86 range. If you are scoring most articles below 75, you are being too harsh. If most are above 88, you are being too lenient.

---

## Scoring Dimensions

Start at 100 for each dimension and subtract for problems found. Do not penalize the same issue twice across dimensions.

### 1. SEO Score (weight: 35%)

- Does the primary keyword appear in the first 150 words? (-5 if not)
- Does a keyword variation appear in at least one H2? (-3 if not)
- Are there 6+ related keywords used naturally? (-3 if fewer)
- Is there a proper FAQ with 4+ questions? (-5 if missing entirely)
- Do H2 headings use keyword variations, not just generic labels? (-3 if all generic)
- Is the content useful and informative for the target reader? (-8 if thin/superficial)

### 2. Readability Score (weight: 30%)

- Does the intro hook the reader in the first 2-3 sentences? (-5 if generic opener)
- Are paragraphs generally 3 sentences or fewer? (-3 per obvious wall-of-text)
- Is the language direct and specific? (-5 if heavy corporate-speak throughout)
- Does it avoid banned phrases from anti_ai_filter.md? (-3 per banned phrase found)
- Would a real person find this useful to read? (-5 if it reads like a template)

**Banned phrases (auto-deduct on first occurrence):**
`game-changer`, `revolutionary`, `cutting-edge`, `state-of-the-art`, `powerful tool`, `robust features`, `seamless integration`, `in today's digital world`, `in the fast-paced world`

### 3. Completeness Score (weight: 35%)

- Does it include pricing information? (-8 if no pricing at all, -3 if approximate)
- At least 3 SPECIFIC cons? "Learning curve" alone does not count. (-5 if generic)
- Is there a "Who it's for / not for" section? (-5 if completely missing)
- Affiliate disclosure present? (-3 if missing)
- Clear verdict with recommendation? (-5 if wishy-washy)
- Are CTAs present and specific? (-3 if generic "Click here" style)

---

## Article-Type-Specific Checks

### Review / Alert

- Is there a Key Takeaways box near the top? (-3 if missing)
- Is there a "Choose if / Skip if" decision table? (-3 if missing)
- Does the pricing section have plan names and dollar amounts? (-5 if vague)
- Are there at least 3 specific cons (not generic)? (-5 if generic)
- Is there a "Who it's NOT for" section? (-3 if missing)
- Does the verdict clearly state who should buy and who should skip? (-3 if vague)

### Roundup

- Does it cover at least 5 tools? (-5 if fewer)
- Does each tool have its own mini-review (not just a name and link)? (-5 if shallow)
- Is there a Quick Picks / comparison table at the top? (-3 if missing)
- Does each tool section include pricing? (-3 if missing)
- Is there a clear #1 pick with reasoning? (-3 if missing)
- Does the comparison table at the end cover at least 4 feature rows? (-3 if missing)

### Comparison

- Does it clearly state a winner upfront? (-5 if wishy-washy)
- Are there at least 3 feature-by-feature comparison sections? (-5 if fewer)
- Does each comparison section declare a winner? (-3 if not)
- Is the pricing comparison side-by-side? (-3 if not)
- Are there separate "Who should choose X/Y" sections? (-3 if missing)
- Is the final verdict clear and decisive? (-5 if "it depends" cop-out)

### Authority Article

- There should be NO affiliate disclosure (-10 if present)
- There should be NO CTA buttons (-10 if present)
- Content should be purely informational
- Should include at least 4 H2 sections of substantive content (-5 if fewer)

---

## Automated HTML Checks (run in code before Claude sees the article)

These are factored into the scoring prompt automatically:

- **Affiliate disclosure:** missing from review/roundup/comparison = flagged
- **Authority article disclosure:** present when it should not be = flagged
- **CTA count:** zero in a review = flagged; more than 3 in a review = flagged; any in authority_article = flagged
- **Pricing table:** `class="pricing-table"` or `<th>Price</th>` expected in reviews, roundups, comparisons
- **Pros/cons:** `class="pros"` and `class="cons"` expected in reviews
- **FAQ:** `id="faq"` expected in all article types
- **Placeholder URLs:** `[TOOL_URL]`, `[AFFILIATE_LINK]`, `https://example.com`, `href=""` = flagged
- **H2 count:** reviews need 5+, roundups need 7+
- **Emoji in h3 tags:** flagged if found in pros/cons section

**Bonuses (not deductions):**
- Has `class="key-takeaways"` box
- Has `class="decision-table"`
- Has `class="quick-verdict"` box
- Has `[INTERNAL_LINK:` placeholders

---

## Usefulness Test

Answer both questions for every article:

1. Would this article still be useful if search engines didn't exist?
2. If someone bookmarked this page and came back in 6 months, would it still provide value?

If the answer to EITHER question is No, reduce the overall_score by 10 points. Include both answers in `editor_summary` — always, even when the article passes.

---

## Response Format

Return ONLY this JSON:

```json
{
  "seo_score": <number 0-100>,
  "readability_score": <number 0-100>,
  "completeness_score": <number 0-100>,
  "overall_score": <number — weighted: SEO 35% + readability 30% + completeness 35%>,
  "approved": <true if overall_score >= 78, false otherwise>,
  "seo_notes": "<the single biggest SEO problem, or 'Passed' if genuinely no issues>",
  "readability_notes": "<the single biggest readability problem, or 'Passed'>",
  "completeness_notes": "<the single biggest completeness problem, or 'Passed'>",
  "deductions_applied": "<list the specific deductions you made>",
  "editor_summary": "<2-3 sentences: overall quality + #1 thing to fix. Always include usefulness answers.>",
  "rewrite_instructions": "<if not approved: specific bullet points of what to fix. if approved: 'N/A'>",
  "usefulness_q1": "<Yes or No — would this article be useful without search engines?>",
  "usefulness_q2": "<Yes or No — would this article still provide value in 6 months?>"
}
```
