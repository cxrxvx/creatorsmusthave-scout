# Pipeline Debug Playbook

5-step diagnosis for any pipeline bug. Work through these in order — do not skip steps.

---

## STEP 1 — Find the exact error line in the logs

```bash
# Find today's log for the failing agent
ls memory/logs/<agent_name>/
cat memory/logs/<agent_name>/YYYY-MM-DD.log

# Scan for errors quickly
grep -n "ERROR\|❌\|Failed\|Traceback\|Exception" memory/logs/<agent_name>/YYYY-MM-DD.log
```

**What to look for:**
- The exact exception class and message (e.g. `KeyError: 'tool_name'`, `AttributeError: 'NoneType'`)
- The line number in the Python file (from the traceback)
- The slug or tool_name that was being processed when it failed

**Do not guess the cause from the symptom.** Read the actual error line first.

---

## STEP 2 — Check tool_name vs JSON/dict key (case sensitivity)

Most lookup bugs are case mismatches.

```python
# Check what the dict key looks like
import json
aff = json.load(open("memory/affiliate_links.json"))
print(list(aff.keys()))          # e.g. ["ElevenLabs", "Beehiiv"]

# Check what tool_name is coming in as
# Look in the log for the line that prints tool_name before the failure
```

**Common patterns:**
- Dict key is `"ElevenLabs"` but lookup uses `"elevenlabs"` — always use `_resolve_affiliate_entry()`, never direct dict access
- SQLite `WHERE name = ?` is case-sensitive — use `WHERE LOWER(name) = ?` and `.lower()` on the lookup value
- JSON field is `tool_name` but code reads `name` (or vice versa)
- `roundup_tools` is a list of strings in one place and a list of dicts in another

**Fix pattern:** `value.lower().strip()` on both sides of any comparison.

---

## STEP 3 — Check None-safe patterns

The second most common crash cause. Any value from SQLite can be None.

```python
# WRONG — crashes if existing is None
images_data = existing.copy()

# RIGHT — safe in all cases
images_data = existing.copy() if existing is not None else {}
# or shorter:
images_data = (existing or {}).copy()
```

**Checklist:**
- Any `dict.get()` call on a value loaded from SQLite — wrap with `or {}`
- Any `list.append()` or iteration on a SQLite value — wrap with `or []`
- Any string method on a field that might be None — wrap with `or ""`
- Comparison like `if value > 80` — guard with `if value and value > 80`

**Quick scan for risky patterns:**
```bash
grep -n "\.copy()\|\.get(\|\.append(" <agent_file>.py | head -30
```

---

## STEP 4 — Check the SQLite path

Wrong path = empty database = silent failures, not crashes.

```bash
# Correct path — always this one
ls -lh memory/pipeline.db

# Wrong paths that have caused bugs:
# ./pipeline.db      — root of project, not memory/
# pipeline.db        — relative, resolves based on cwd
# ~/cxrxvx-ai-empire/pipeline.db  — absolute but wrong location
```

**Quick test:**
```python
import sqlite3
c = sqlite3.connect("memory/pipeline.db")
print(c.execute("SELECT COUNT(*) FROM handoffs").fetchone())
# Should return (N,) where N > 0
# If it returns (0,) — you are reading the wrong file
```

**Also check:** if agents write to different paths, they will not see each other's data. All agents must use `memory/pipeline.db`. db_helpers.py handles this — use db_helpers, not raw sqlite3 calls, wherever possible.

---

## STEP 5 — Check venv is activated

If you get `ModuleNotFoundError` for any package — this is the cause 90% of the time.

```bash
# Check if venv is active
which python3
# Should return something like: /Users/alex/cxrxvx-ai-empire/venv/bin/python3
# If it returns /usr/bin/python3 — venv is NOT active

# Activate it
source venv/bin/activate

# Then run again
python3 scheduler.py --now
```

**Packages that require venv:**
- `beautifulsoup4` (bs4) — image_agent uses this
- `anthropic` — all AI agents use this
- `feedparser` — tool_scout uses this
- `requests` — all agents that call APIs

**If a new package keeps going missing:**
```bash
pip freeze > requirements.txt   # update requirements
pip install -r requirements.txt # reinstall after venv rebuild
```

---

## Quick Reference — Common Bugs and Their Fix

| Symptom | Most Likely Cause | First Check |
|---|---|---|
| `AttributeError: 'NoneType'` | Missing `or {}` on SQLite value | Step 3 |
| `KeyError: 'tool_name'` | Field name mismatch | Step 2 |
| Affiliate link not injecting | Case mismatch or broken JSON | Step 2 |
| Score 0 or empty results | Wrong pipeline.db path | Step 4 |
| `ModuleNotFoundError` | Venv not activated | Step 5 |
| Agent silently skips articles | Check status filter + cap counter | Step 1 |
| Telegram buttons not working | scheduler.py not running | Step 1 + check logs |
| Pipeline lock stuck | `rm memory/.pipeline_lock` | N/A |
| Daily cap seems wrong | Check `get_daily_publish_cap()` | Step 1 |
| SEO fields not in WordPress | SEO ran before publisher | Step 1 + check pipeline order |

---

## Manual Recovery Commands

```bash
# Reset daily publish cap
python3 -c "
import sqlite3
c = sqlite3.connect('memory/pipeline.db')
c.execute(\"UPDATE counters SET value=0 WHERE key='articles_published_today'\")
c.commit()
print('Cap reset')
"

# Reset a stuck article
python3 -c "
import db_helpers
db_helpers.update_handoff('your-slug-here', {
    'status': 'needs_rewrite',
    'wp_post_id': None,
    'seo_done': 0,
    'internal_links_done': 0,
    'images_added': 0,
})
print('Reset done')
"

# Check what is in the queue right now
python3 -c "
import db_helpers
for status in ['needs_rewrite', 'pending_edit', 'pending_publish', 'pending_approval']:
    slugs = db_helpers.get_pending_by_status(status)
    print(f'{status}: {len(slugs)}')
"

# Force a specific article to publish next
python3 -c "
import sqlite3
c = sqlite3.connect('memory/pipeline.db')
c.execute(\"UPDATE handoffs SET priority_score=200 WHERE slug='your-slug-here'\")
c.commit()
print('Priority set')
"
```
