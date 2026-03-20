# Lessons Log — Gotchas Format

Each entry follows: SYMPTOM → ROOT CAUSE → FIX APPLIED → PREVENTION RULE

---

## GOTCHA: Affiliate links not injecting

**SYMPTOM:** Articles published with `[AFFILIATE_LINK]` placeholder in the HTML, or the tool URL used instead of the affiliate URL.

**ROOT CAUSE:** Missing comma in affiliate_links.json caused a silent JSON parse failure. The whole dict loaded as empty `{}`. Also: case mismatch between the dict key ("ElevenLabs") and the tool_name lookup ("elevenlabs") caused misses even when JSON was valid.

**FIX APPLIED (2026-03-11):** Added JSON validation on load. Added `_resolve_affiliate_entry()` with case-insensitive lookup. Both `inject_affiliate_links()` and `inject_roundup_affiliate_links()` now use this function.

**PREVENTION RULE:** Always use `_resolve_affiliate_entry()` for any affiliate link lookup — never direct dict access. Validate affiliate_links.json on startup. Check `affiliate_injected` field in db_helpers after publish run.

---

## GOTCHA: Telegram Accept button not working

**SYMPTOM:** Alex taps Accept in Telegram — nothing happens. Post stays as draft.

**ROOT CAUSE:** `sys.exit()` inside publisher_agent was killing the whole process, including the bot thread running inside scheduler.py.

**FIX APPLIED (2026-03-11):** Replaced `sys.exit()` calls with `return`. Scheduler holds the process alive with a `while True: time.sleep(60)` loop after agents run, so the bot thread stays alive.

**PREVENTION RULE:** Never call `sys.exit()` inside any agent. Agents should return, not exit. The bot thread must be the thing that keeps the process alive — do not terminate early.

---

## GOTCHA: SEO agent scoring 21/100

**SYMPTOM:** SEO agent runs and saves a very low score. RankMath fields empty in WordPress.

**ROOT CAUSE:** SEO agent was running before publisher_agent, so no `wp_post_id` existed yet. The agent tried to push meta to a post that did not exist.

**FIX APPLIED (2026-03-11):** Pipeline order fixed in scheduler.py — SEO always runs after publisher. Pipeline order is: Write → Edit → Image → Internal Links → Publisher → Telegram → SEO.

**PREVENTION RULE:** Pipeline order in scheduler.py is load-bearing. Always check scheduler.py when an agent reports "post not found" or "no wp_post_id". SEO must always come after publisher. Internal links must always come before publisher.

---

## GOTCHA: Year hardcoded as 2025 in article titles

**SYMPTOM:** Articles published in 2026 with "2025" in the title and body. Looks outdated immediately.

**ROOT CAUSE:** Year was a hardcoded string literal in the prompt template instead of a dynamic value.

**FIX APPLIED (2026-03-11):** Added `CURRENT_YEAR = datetime.now().year` at top of article_agent.py. All prompt templates now use `{CURRENT_YEAR}`.

**PREVENTION RULE:** Never hardcode a year in any template or prompt. Always use `datetime.now().year`. Add "CURRENT YEAR IS {CURRENT_YEAR}" as a rule in every article prompt.

---

## GOTCHA: image_agent crash on None images_data

**SYMPTOM:** `image_agent.py` crashes with `AttributeError: 'NoneType' object has no attribute 'copy'` or similar. Pipeline stops mid-run.

**ROOT CAUSE:** `images_data = existing` where `existing` was `None` from a SQLite row that had NULL in the images_data field. Calling `.copy()` or any dict method on `None` crashes.

**FIX APPLIED (2026-03-17):** Applied `or {}` pattern everywhere images_data is loaded from SQLite. Pattern: `images_data = existing.copy() if existing is not None else {}`. Applied to `process_roundup_images()`, `process_tool_images()`, and `run()`.

**PREVENTION RULE:** Any field loaded from SQLite that is expected to be a dict must use `or {}`. Never trust that a row value is not None — treat all nullable SQLite columns as potentially None. Pattern: `value = row["field"] or {}`.

---

## GOTCHA: Daily publish cap stuck at 1/day

**SYMPTOM:** Pipeline only publishes 1 article per day despite the cap appearing to be set higher. Queue drains extremely slowly.

**ROOT CAUSE:** `get_daily_publish_cap()` in scheduler.py had the week 1-4 cap returning 1 instead of 3. The cap logic was correct in principle but the return value was wrong.

**FIX APPLIED (2026-03-17):** Raised weeks 1-4 cap from 1 to 3 in `get_daily_publish_cap()`. Write-ahead check migrated to SQLite via db_helpers so it reads from pipeline.db not handoffs.json.

**PREVENTION RULE:** When queue seems stuck, check `get_daily_publish_cap()` in scheduler.py first. Reset the counter manually if needed: `UPDATE counters SET value=0 WHERE key='articles_published_today'`. Also check write-ahead cap — if 21+ articles are queued, article_agent skips writing.

---

## GOTCHA: Internal links not added to new articles

**SYMPTOM:** Articles publish without internal links. Internal link agent runs but produces no updates.

**ROOT CAUSE:** Internal link agent was running AFTER publisher_agent in the pipeline order. By the time internal links ran, the article was already a WordPress post. The agent was updating the handoff record, but those changes never made it to WordPress.

**FIX APPLIED (2026-03-17):** Pipeline order fixed in scheduler.py — internal_link_agent now runs BEFORE publisher_agent. Internal links are injected into `article_html` before the post is created.

**PREVENTION RULE:** Pipeline order: Internal Links → Publisher → Telegram → SEO. Never put internal_link_agent after publisher. The correct order is in PROGRAMMING_DOCS.md.

---

## GOTCHA: beautifulsoup4 not found — image agent crashes

**SYMPTOM:** `ModuleNotFoundError: No module named 'bs4'`. Image agent crashes. All downstream agents that depend on images then fail.

**ROOT CAUSE:** venv was rebuilt or the pipeline was run without activating the venv. `bs4` (beautifulsoup4) is installed inside the venv, not globally.

**FIX APPLIED (2026-03-12):** Added `beautifulsoup4` to requirements.txt. Added clear warning to PROGRAMMING_DOCS.md: always activate venv before running.

**PREVENTION RULE:** Always run `source venv/bin/activate` before running anything. If you get `ModuleNotFoundError` for any package, the first thing to check is whether the venv is activated — not whether the package is installed.

---

## GOTCHA: Editor approving everything (100% approval rate)

**SYMPTOM:** Every article passes the editor with high scores. Articles with placeholder URLs or emoji headings get published.

**ROOT CAUSE:** No hard-fail rules existed. Editor scored content quality but never blocked obvious structural problems like `[AFFILIATE_LINK]` in the HTML or emoji in H2 headings.

**FIX APPLIED (2026-03-12):** Added `check_hard_fails()` function in editor_agent.py. Hard-fail conditions: placeholder URLs in HTML, emoji in H1/H2/H3 headings, article body under 500 words. Any hard fail returns score 0, `approved: false`.

**PREVENTION RULE:** Hard-fail checks must run BEFORE Claude scores anything — they are structural checks, not quality judgments. If approval rate is above 90%, the hard-fail rules or scoring criteria are too lenient.

---

## GOTCHA: Article agent writing new articles instead of rewrites first

**SYMPTOM:** Articles stuck in `needs_rewrite` status for days while new articles keep being written. High-priority rewrites (ElevenLabs, Riverside) never get processed.

**ROOT CAUSE:** `run()` in article_agent.py only looked at `keyword_data` for new articles. There was no logic to fetch `needs_rewrite` articles from the database first.

**FIX APPLIED (2026-03-16):** Replaced `run()` with rewrites-first logic. Fetches `needs_rewrite` handoffs from db_helpers, scores and sorts by `calculate_rewrite_priority()`, rewrites them first. Only processes new articles if daily cap is not reached after rewrites.

**PREVENTION RULE:** The pipeline processes rewrites before new articles. If the queue seems to be ignoring rewrites, check `get_handoffs_by_status("needs_rewrite")` returns results and that `calculate_rewrite_priority()` is scoring them above zero.

---

## GOTCHA: Article agent fabricating tool URLs

**SYMPTOM:** Articles published with made-up URLs like `www.sometool.com` that redirect nowhere, or produce 404 errors. Affiliate links break.

**ROOT CAUSE:** No verified source URL was stored when tool_scout discovered a tool. Article agent had to guess the URL or rely on a hardcoded TOOL_URLS dict that was incomplete.

**FIX APPLIED (2026-03-16):** Added `source_url` column to tools table. tool_scout now saves the URL from the RSS entry (`entry.get("link")`) or Reddit post (`p.get("url")`) as `source_url`. Article agent calls `get_tool_source_url()` which queries this field and injects the verified URL — or a warning to use `[TOOL_WEBSITE]` placeholder — into the prompt.

**PREVENTION RULE:** If an article contains a broken tool URL, check the `source_url` field in the tools table for that tool. If empty, tool_scout needs to re-run and save it. Never trust a guessed URL — the prompt warning will cause the editor to reject articles with placeholder text.
