"""
backfill_tool_urls.py — One-time script to populate empty tool_url fields
==========================================================================
Run this ONCE after updating db_helpers.py.
It looks up the homepage URL for every article with an empty tool_url
and saves it to the database. Safe to run multiple times — only updates
rows where tool_url is empty.

Usage:
    cd ~/cxrxvx-ai-empire
    source venv/bin/activate
    python3 backfill_tool_urls.py
"""

import db_helpers
from article_agent import get_tool_url

def run():
    print("🔧 Backfilling empty tool_url fields...\n")

    handoffs = db_helpers.load_all_handoffs()
    updated = 0
    failed = 0

    for slug, article in handoffs.items():
        tool_url = article.get("tool_url") or ""
        if tool_url:
            continue  # Already has a URL — skip

        tool_name = article.get("tool_name", "")
        if not tool_name:
            print(f"  ⚠️  {slug} — no tool_name, skipping")
            failed += 1
            continue

        resolved_url = get_tool_url(tool_name)
        if not resolved_url or resolved_url.startswith("https://www.google.com/search"):
            print(f"  ⚠️  {slug} — could not resolve URL for '{tool_name}', got: {resolved_url}")
            # Still save it — Google search fallback is better than empty
            # Publisher will flag it in verification

        db_helpers.update_handoff(slug, {"tool_url": resolved_url})
        print(f"  ✅ {slug} → {resolved_url}")
        updated += 1

    print(f"\n🏁 Done. Updated {updated} articles. Failed: {failed}.")
    print(f"   Total articles: {len(handoffs)}")

    # Verify
    print("\n🔍 Verification — any still empty?")
    handoffs_after = db_helpers.load_all_handoffs()
    still_empty = [s for s, a in handoffs_after.items() if not (a.get("tool_url") or "")]
    if still_empty:
        print(f"  ⚠️  {len(still_empty)} still empty: {still_empty}")
    else:
        print(f"  ✅ All articles have tool_url populated.")


if __name__ == "__main__":
    run()
