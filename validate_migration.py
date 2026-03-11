#!/usr/bin/env python3
"""
validate_migration.py — Verify SQLite-only migration is complete.

Checks:
  1. db_helpers.py imports OK
  2. load_all_handoffs() returns records
  3. get_handoffs_by_status() works for key statuses
  4. get_counter() works
  5. No remaining open(handoffs.json, 'w') or json.dump to handoffs in agent files
"""

import os
import re
import sys
import importlib

AGENTS = [
    "article_agent.py",
    "editor_agent.py",
    "image_agent.py",
    "publisher_agent.py",
    "seo_agent.py",
    "internal_link_agent.py",
    "keyword_agent.py",
    "scheduler.py",
    "health_monitor.py",
    "watchdog.py",
    "approval_bot.py",
]

WRITE_PATTERNS = [
    r'open\s*\(\s*["\'].*handoffs.*["\'],\s*["\']w["\']',     # open("handoffs.json", "w")
    r'json\.dump\s*\(.*handoffs',                               # json.dump(handoffs, ...)
    r'save_json\s*\(.*HANDOFFS',                                # save_json(HANDOFFS_FILE, ...)
    r'HANDOFFS.*\.write_text',                                  # HANDOFFS_FILE.write_text(...)
    r'save_handoffs\s*\(',                                      # save_handoffs(...)
]

PASS = "✅"
FAIL = "❌"

errors = []

print("=" * 60)
print("CXRXVX SQLite Migration Validator")
print("=" * 60)

# ── 1. db_helpers import ──────────────────────────────────────
print("\n[1] Importing db_helpers...")
try:
    import db_helpers
    print(f"  {PASS} db_helpers imported")
except Exception as e:
    print(f"  {FAIL} db_helpers import failed: {e}")
    errors.append(f"db_helpers import: {e}")

# ── 2. load_all_handoffs ──────────────────────────────────────
print("\n[2] load_all_handoffs()...")
try:
    handoffs = db_helpers.load_all_handoffs()
    n = len(handoffs)
    if n > 0:
        print(f"  {PASS} {n} records loaded from SQLite")
    else:
        print(f"  ⚠️  0 records — pipeline.db may be empty")
        errors.append("load_all_handoffs returned 0 records")
except Exception as e:
    print(f"  {FAIL} load_all_handoffs failed: {e}")
    errors.append(f"load_all_handoffs: {e}")

# ── 3. get_handoffs_by_status ─────────────────────────────────
print("\n[3] get_handoffs_by_status()...")
statuses_to_check = ["pending_edit", "pending_publish", "published", "draft_live"]
for s in statuses_to_check:
    try:
        results = db_helpers.get_handoffs_by_status(s)
        print(f"  {PASS} {s}: {len(results)} articles")
    except Exception as e:
        print(f"  {FAIL} {s}: {e}")
        errors.append(f"get_handoffs_by_status({s}): {e}")

# ── 4. get_counter ────────────────────────────────────────────
print("\n[4] get_counter()...")
try:
    val = db_helpers.get_counter("daily_publish")
    print(f"  {PASS} daily_publish counter = {val}")
except Exception as e:
    print(f"  {FAIL} get_counter failed: {e}")
    errors.append(f"get_counter: {e}")

# ── 5. Scan agent files for write patterns ────────────────────
print("\n[5] Scanning agent files for remaining handoffs.json writes...")
for fname in AGENTS:
    if not os.path.exists(fname):
        print(f"  ⚠️  {fname}: file not found — skipping")
        continue
    with open(fname, "r") as f:
        content = f.read()
    found = []
    for pat in WRITE_PATTERNS:
        matches = re.findall(pat, content, re.IGNORECASE)
        if matches:
            found.extend(matches[:2])  # show up to 2 matches per pattern
    if found:
        print(f"  {FAIL} {fname}: still has write patterns:")
        for m in found:
            print(f"       → {m[:80]}")
        errors.append(f"{fname}: remaining write patterns")
    else:
        print(f"  {PASS} {fname}: no write patterns found")

# ── 6. Check NOTE comments present ───────────────────────────
print("\n[6] Checking # NOTE comments in all agent files...")
for fname in AGENTS:
    if not os.path.exists(fname):
        continue
    with open(fname, "r") as f:
        first = f.read(300)
    if "# NOTE: handoffs.json is now READ-ONLY" in first:
        print(f"  {PASS} {fname}: NOTE comment present")
    else:
        print(f"  ⚠️  {fname}: NOTE comment missing (non-critical)")

# ── 7. Check handoffs.json archive exists ────────────────────
print("\n[7] Checking handoffs.json archive...")
if os.path.exists("memory/handoffs.json"):
    size = os.path.getsize("memory/handoffs.json")
    print(f"  {PASS} memory/handoffs.json exists ({size//1024}KB)")
else:
    print(f"  {FAIL} memory/handoffs.json missing")
    errors.append("memory/handoffs.json not found")

if os.path.exists("memory/HANDOFFS_ARCHIVED.txt"):
    print(f"  {PASS} memory/HANDOFFS_ARCHIVED.txt exists")
else:
    print(f"  {FAIL} memory/HANDOFFS_ARCHIVED.txt missing")
    errors.append("memory/HANDOFFS_ARCHIVED.txt not found")

# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"{FAIL} MIGRATION INCOMPLETE — {len(errors)} issue(s):")
    for e in errors:
        print(f"   • {e}")
    sys.exit(1)
else:
    print(f"{PASS} MIGRATION VALID — all checks passed")
    print("   SQLite is the sole source of truth for pipeline handoffs.")
print("=" * 60)
