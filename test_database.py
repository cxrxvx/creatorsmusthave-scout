"""
test_database.py — Quick test to verify SQLite database works
================================================================
Run this BEFORE the migration to make sure database.py is healthy.

Usage: python3 test_database.py
"""

import os
import sys
import json
from pathlib import Path

# Use a TEST database — not the real one
TEST_DB = "memory/test_pipeline.db"

# Clean up any previous test
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

# Import database with test path
from database import PipelineDatabase
test_db = PipelineDatabase(db_path=TEST_DB)

print("🧪 Testing database.py...\n")
passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        print(f"   ✅ {name}")
        passed += 1
    else:
        print(f"   ❌ {name}")
        failed += 1


# ── Test 1: Insert and read a tool ──
print("── Tools ──")
test_db.upsert_tool("descript", {
    "name": "Descript",
    "score": 85,
    "category": "video",
    "description": "AI video editor for podcasters",
    "has_affiliate_potential": True,
    "competitors": ["Riverside", "Opus Clip"],
})

tool = test_db.get_tool("descript")
test("Insert + read tool", tool is not None and tool["name"] == "Descript")
test("Score preserved", tool["score"] == 85)
test("Category preserved", tool["category"] == "video")
test("Competitors deserialized", isinstance(tool["competitors"], list) and "Riverside" in tool["competitors"])
test("Boolean conversion", tool["has_affiliate_potential"] == True)

# Update the tool
test_db.upsert_tool("descript", {"score": 90})
tool = test_db.get_tool("descript")
test("Update preserves existing fields", tool["name"] == "Descript" and tool["score"] == 90)

# Get all tools
all_tools = test_db.get_all_tools()
test("Get all tools returns dict", isinstance(all_tools, dict) and "descript" in all_tools)

# Get by category
video_tools = test_db.get_tools_by_category("video")
test("Get by category", len(video_tools) == 1 and video_tools[0]["name"] == "Descript")


# ── Test 2: Watchlist ──
print("\n── Watchlist ──")
test_db.upsert_watchlist("NewTool", {
    "title": "New Tool",
    "score": 45,
    "recheck_date": "2020-01-01",
    "recheck_count": 0,
})

wl = test_db.get_watchlist()
test("Insert watchlist item", len(wl) == 1 and wl[0]["name"] == "NewTool")

due = test_db.get_watchlist_due()
test("Watchlist due (date in past)", len(due) == 1)  # 2026-03-15 is in the past relative to test

test_db.delete_from_watchlist("NewTool")
wl = test_db.get_watchlist()
test("Delete from watchlist", len(wl) == 0)


# ── Test 3: Keywords ──
print("\n── Keywords ──")
test_db.upsert_keyword("descript-review", {
    "tool_name": "Descript",
    "primary_keyword": "descript review for podcasters",
    "article_type": "review",
    "keyword_cluster": ["descript pricing", "descript vs riverside", "descript free plan"],
    "status": "pending_article",
})

kw = test_db.get_keyword("descript-review")
test("Insert + read keyword", kw is not None and kw["tool_name"] == "Descript")
test("Cluster deserialized", isinstance(kw["keyword_cluster"], list) and len(kw["keyword_cluster"]) == 3)

pending = test_db.get_keywords_by_status("pending_article")
test("Get by status", len(pending) == 1)


# ── Test 4: Handoffs ──
print("\n── Handoffs ──")
test_db.upsert_handoff("descript-review-podcasters", {
    "tool_name": "Descript",
    "article_type": "review",
    "article_title": "Descript Review for Podcasters",
    "article_html": "<h2>Test</h2><p>Content here</p>",
    "status": "pending_edit",
    "tool_score": 85,
    "images_added": True,
    "image_data": {"hero_media_id": 123, "screenshot_media_id": 456},
})

h = test_db.get_handoff("descript-review-podcasters")
test("Insert + read handoff", h is not None and h["tool_name"] == "Descript")
test("Boolean stored correctly", h["images_added"] == True)
test("Image data deserialized", isinstance(h["image_data"], dict) and h["image_data"]["hero_media_id"] == 123)

# Count by status
count = test_db.count_handoffs_by_status("pending_edit", "pending_publish")
test("Count by status", count == 1)

# Update status
test_db.upsert_handoff("descript-review-podcasters", {"status": "pending_publish", "editor_score": 87})
h = test_db.get_handoff("descript-review-podcasters")
test("Update handoff status", h["status"] == "pending_publish")
test("Editor score preserved", h["editor_score"] == 87)
test("Original fields preserved", h["tool_name"] == "Descript")

# Get all handoffs as dict
all_h = test_db.get_all_handoffs()
test("Get all handoffs returns dict", isinstance(all_h, dict) and "descript-review-podcasters" in all_h)


# ── Test 5: Counters ──
print("\n── Counters ──")
test_db.set_counter("daily_publish", {"date": "2026-03-08", "count": 3})
c = test_db.get_counter("daily_publish")
test("Counter set + get", c["date"] == "2026-03-08" and c["count"] == 3)


# ── Test 6: Topics used ──
print("\n── Topics Used ──")
test_db.add_topic("descript-review-podcasters")
test_db.add_topic("jasper-ai-review")
topics = test_db.get_topics_used()
test("Topics added", len(topics) == 2)
test("Topic exists check", test_db.is_topic_used("descript-review-podcasters"))
test("Topic not exists check", not test_db.is_topic_used("nonexistent-slug"))


# ── Test 7: Pipeline stats ──
print("\n── Pipeline Stats ──")
stats = test_db.get_pipeline_stats()
test("Stats returns dict", isinstance(stats, dict))
test("Stats has total_tools", stats["total_tools"] == 1)
test("Stats has published_count", "published_count" in stats)
test("Stats has tools_by_category", "video" in stats.get("tools_by_category", {}))


# ── Cleanup ──
print(f"\n{'=' * 40}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("✅ All tests passed — database.py is ready!")
else:
    print("❌ Some tests failed — check above")

# Remove test database
os.remove(TEST_DB)
print(f"🧹 Test database removed")
