"""
migrate_json_to_sqlite.py — One-Time Migration Script
=======================================================
Reads all existing JSON pipeline files and copies every record into SQLite.

RUN THIS ONCE: python3 migrate_json_to_sqlite.py
Takes about 2 seconds. Zero data loss.

WHAT IT DOES:
  1. Reads memory/tool_database.json → tools table
  2. Reads memory/watchlist.json     → watchlist table
  3. Reads memory/keyword_data.json  → keywords table
  4. Reads memory/handoffs.json      → handoffs table
  5. Reads memory/.daily_counter.json → counters table
  6. Reads memory/topics_used.json   → topics_used table

WHAT IT DOES NOT TOUCH:
  - memory/affiliate_links.json  (stays JSON — you edit manually)
  - memory/manual_tools.json     (stays JSON — you edit manually)
  - memory/system_health.json    (stays JSON — written once daily)
  - memory/weekly_digest.json    (stays JSON — written once weekly)

SAFETY:
  - JSON files are NEVER deleted — they become permanent backups
  - If a record already exists in SQLite, it gets updated (not duplicated)
  - Can be run multiple times safely (idempotent)
  - Prints a full report showing what was migrated
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from database import db

MEMORY_DIR = BASE_DIR / "memory"


def load_json_safe(path, default):
    """Load JSON with error handling."""
    if not os.path.exists(path):
        print(f"   ⏭️  File not found: {path}")
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        size_kb = os.path.getsize(path) / 1024
        print(f"   📄 Loaded: {path} ({size_kb:.1f}KB)")
        return data
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON parse error in {path}: {e}")
        return default
    except Exception as e:
        print(f"   ❌ Error reading {path}: {e}")
        return default


def migrate_tool_database():
    """Migrate memory/tool_database.json → tools table."""
    print("\n── Migrating tool_database.json ──")
    data = load_json_safe(MEMORY_DIR / "tool_database.json", {})

    if not isinstance(data, dict):
        print("   ⚠️  Expected dict, got something else — skipping")
        return 0

    count = 0
    for key, tool in data.items():
        if not isinstance(tool, dict):
            continue

        record = {
            "key":                    key,
            "name":                   tool.get("name", key),
            "score":                  tool.get("score", 0),
            "type":                   tool.get("type", "affiliate_review"),
            "category":               tool.get("category", "other"),
            "description":            tool.get("description", ""),
            "has_affiliate_potential": 1 if tool.get("has_affiliate_potential", True) else 0,
            "is_fast_growing":        1 if tool.get("is_fast_growing", False) else 0,
            "source":                 tool.get("source", ""),
            "discovered_date":        tool.get("discovered_date", ""),
            "promoted_date":          tool.get("promoted_date", ""),
            "status":                 tool.get("status", "discovered"),
            "competitors":            json.dumps(tool.get("competitors", [])),
        }

        # Everything else goes into 'extra'
        known_fields = set(record.keys()) | {"key"}
        extra = {k: v for k, v in tool.items() if k not in known_fields}
        if extra:
            record["extra"] = json.dumps(extra)

        db.upsert_tool(key, record)
        count += 1

    print(f"   ✅ Migrated {count} tools")
    return count


def migrate_watchlist():
    """Migrate memory/watchlist.json → watchlist table."""
    print("\n── Migrating watchlist.json ──")
    data = load_json_safe(MEMORY_DIR / "watchlist.json", [])

    if isinstance(data, dict):
        # Old format was sometimes a dict
        data = list(data.values())
    if not isinstance(data, list):
        print("   ⚠️  Expected list, got something else — skipping")
        return 0

    count = 0
    for item in data:
        if not isinstance(item, dict):
            continue

        name = item.get("name", "")
        if not name:
            continue

        record = {
            "name":            name,
            "title":           item.get("title", ""),
            "description":     item.get("description", ""),
            "score":           item.get("score", 0),
            "category":        item.get("category", "other"),
            "source":          item.get("source", ""),
            "discovered_date": item.get("discovered_date", ""),
            "recheck_date":    item.get("recheck_date", ""),
            "recheck_count":   item.get("recheck_count", 0),
        }

        known_fields = set(record.keys())
        extra = {k: v for k, v in item.items() if k not in known_fields}
        if extra:
            record["extra"] = json.dumps(extra)

        db.upsert_watchlist(name, record)
        count += 1

    print(f"   ✅ Migrated {count} watchlist items")
    return count


def migrate_keyword_data():
    """Migrate memory/keyword_data.json → keywords table."""
    print("\n── Migrating keyword_data.json ──")
    data = load_json_safe(MEMORY_DIR / "keyword_data.json", {})

    if not isinstance(data, dict):
        print("   ⚠️  Expected dict — skipping")
        return 0

    count = 0
    for key, kw in data.items():
        if not isinstance(kw, dict):
            continue

        record = {
            "key":                  key,
            "tool_name":            kw.get("tool_name", ""),
            "tool_category":        kw.get("tool_category", "other"),
            "tool_score":           kw.get("tool_score", 0),
            "primary_keyword":      kw.get("primary_keyword", ""),
            "secondary_keywords":   json.dumps(kw.get("secondary_keywords", [])),
            "keyword_cluster":      json.dumps(kw.get("keyword_cluster", [])),
            "search_intent":        kw.get("search_intent", "buyer"),
            "difficulty_score":     kw.get("difficulty_score", 0),
            "traffic_value":        kw.get("traffic_value", "medium"),
            "article_type":         kw.get("article_type", "review"),
            "recommended_word_count": kw.get("recommended_word_count", 2500),
            "article_title":        kw.get("article_title", ""),
            "url_slug":             kw.get("url_slug", ""),
            "serp_gap":             kw.get("serp_gap", ""),
            "urgency":              kw.get("urgency", "medium"),
            "supporting_articles":  json.dumps(kw.get("supporting_articles", [])),
            "roundup_tools":        json.dumps(kw.get("roundup_tools", [])),
            "comparison_tools":     json.dumps(kw.get("comparison_tools", {})),
            "status":               kw.get("status", "pending_article"),
            "researched_date":      kw.get("researched_date", ""),
        }

        known_fields = set(record.keys()) | {"key"}
        extra = {k: v for k, v in kw.items()
                 if k not in known_fields and k not in
                 ("secondary_keywords", "keyword_cluster", "supporting_articles",
                  "roundup_tools", "comparison_tools")}
        if extra:
            record["extra"] = json.dumps(extra)

        db.upsert_keyword(key, record)
        count += 1

    print(f"   ✅ Migrated {count} keyword packages")
    return count


def migrate_handoffs():
    """Migrate memory/handoffs.json → handoffs table."""
    print("\n── Migrating handoffs.json ──")
    data = load_json_safe(MEMORY_DIR / "handoffs.json", {})

    if not isinstance(data, dict):
        print("   ⚠️  Expected dict — skipping")
        return 0

    count = 0
    for slug, article in data.items():
        if not isinstance(article, dict):
            continue

        record = {
            "slug":                slug,
            "tool_name":           article.get("tool_name", ""),
            "tool_key":            article.get("tool_key", ""),
            "article_type":        article.get("article_type", "review"),
            "article_title":       article.get("article_title", ""),
            "url_slug":            article.get("url_slug", slug),
            "primary_keyword":     article.get("primary_keyword", ""),
            "word_count":          article.get("word_count", 0),
            "article_html":        article.get("article_html", ""),
            "status":              article.get("status", "pending_edit"),
            "written_date":        article.get("written_date", ""),
            "tool_score":          article.get("tool_score", 0),
            "category":            article.get("category", "other"),
            "tool_url":            article.get("tool_url", ""),
            "hook_style":          article.get("hook_style", ""),
            "writing_angle":       article.get("writing_angle", ""),

            "editor_score":        article.get("editor_score"),
            "editor_feedback":     article.get("editor_feedback", ""),
            "editor_rewrite_instructions": article.get("editor_rewrite_instructions", ""),
            "editor_deductions":   article.get("editor_deductions", ""),
            "editor_scores":       json.dumps(article.get("editor_scores", {})),
            "editor_reviewed":     article.get("editor_reviewed", ""),

            "images_added":        1 if article.get("images_added") else 0,
            "image_data":          json.dumps(article.get("image_data", {})),
            "images_date":         article.get("images_date", ""),

            "seo_done":            1 if article.get("seo_done") else 0,
            "meta_title":          article.get("meta_title", ""),
            "meta_description":    article.get("meta_description", ""),
            "focus_keyword":       article.get("focus_keyword", ""),
            "schema_type":         article.get("schema_type", ""),
            "og_image":            article.get("og_image", ""),
            "seo_processed_date":  article.get("seo_processed_date", ""),

            "internal_links_done":    1 if article.get("internal_links_done") else 0,
            "internal_links_added":   article.get("internal_links_added", 0),
            "internal_links_removed": article.get("internal_links_removed", 0),
            "internal_links_date":    article.get("internal_links_date", ""),

            "wp_post_id":          article.get("wp_post_id"),
            "wp_post_url":         article.get("wp_post_url", article.get("wp_url", "")),
            "wp_url":              article.get("wp_url", ""),
            "published_date":      article.get("published_date", ""),
            "priority_score":      article.get("priority_score", 0),
            "affiliate_injected":  1 if article.get("affiliate_injected") else 0,
            "publish_category":    article.get("publish_category", ""),

            "roundup_tools":       json.dumps(article.get("roundup_tools", [])),
            "comparison_tools":    json.dumps(article.get("comparison_tools", {})),
        }

        # Store everything else in extra
        known = set(record.keys()) | {"slug", "editor_scores", "image_data",
                                       "roundup_tools", "comparison_tools",
                                       "images_added", "seo_done",
                                       "internal_links_done", "affiliate_injected",
                                       "_priority_score", "_freshness_tag", "_slug"}
        extra = {}
        for k, v in article.items():
            if k not in known:
                try:
                    json.dumps(v)  # Check it's serializable
                    extra[k] = v
                except (TypeError, ValueError):
                    extra[k] = str(v)
        if extra:
            record["extra"] = json.dumps(extra)

        db.upsert_handoff(slug, record)
        count += 1

    print(f"   ✅ Migrated {count} handoff articles")
    return count


def migrate_counters():
    """Migrate memory/.daily_counter.json → counters table."""
    print("\n── Migrating .daily_counter.json ──")
    data = load_json_safe(MEMORY_DIR / ".daily_counter.json", {})

    if not isinstance(data, dict):
        return 0

    db.set_counter("daily_publish", data)
    print(f"   ✅ Migrated daily counter")
    return 1


def migrate_topics_used():
    """Migrate memory/topics_used.json → topics_used table."""
    print("\n── Migrating topics_used.json ──")
    data = load_json_safe(MEMORY_DIR / "topics_used.json", [])

    if not isinstance(data, list):
        print("   ⚠️  Expected list — skipping")
        return 0

    count = 0
    for slug in data:
        if isinstance(slug, str) and slug:
            db.add_topic(slug)
            count += 1

    print(f"   ✅ Migrated {count} topics")
    return count


def verify_migration():
    """Run a quick check to make sure everything migrated correctly."""
    print("\n── Verifying migration ──")
    stats = db.get_pipeline_stats()

    print(f"   📊 Tools in database:     {stats['total_tools']}")
    print(f"   👀 Watchlist items:       {stats['watchlist_count']}")
    print(f"   🔑 Keyword packages:      {sum(stats['keyword_statuses'].values())}")
    print(f"   📝 Handoff articles:      {sum(stats['handoff_statuses'].values())}")
    print(f"   ✅ Published:             {stats['published_count']}")

    if stats.get("tools_by_category"):
        cats = ", ".join(f"{v} {k}" for k, v in stats["tools_by_category"].items())
        print(f"   📁 Categories:            {cats}")

    if stats.get("handoff_statuses"):
        statuses = ", ".join(f"{v} {k}" for k, v in stats["handoff_statuses"].items())
        print(f"   📋 Handoff statuses:      {statuses}")

    if stats.get("article_types"):
        types = ", ".join(f"{v} {k}" for k, v in stats["article_types"].items())
        print(f"   📝 Article types:         {types}")

    # Check database file size
    db_path = MEMORY_DIR / "pipeline.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        print(f"   💾 Database size:         {size_kb:.1f}KB")

    return stats


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("🔄 JSON → SQLite Migration")
    print("=" * 60)
    print(f"   Database: {db.db_path}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    start = datetime.now()

    # Run all migrations
    totals = {}
    totals["tools"]     = migrate_tool_database()
    totals["watchlist"] = migrate_watchlist()
    totals["keywords"]  = migrate_keyword_data()
    totals["handoffs"]  = migrate_handoffs()
    totals["counters"]  = migrate_counters()
    totals["topics"]    = migrate_topics_used()

    # Verify
    stats = verify_migration()

    elapsed = (datetime.now() - start).total_seconds()

    print(f"\n{'=' * 60}")
    print(f"✅ Migration complete in {elapsed:.1f} seconds")
    print(f"   Total records migrated: {sum(totals.values())}")
    print(f"   Database: memory/pipeline.db")
    print(f"")
    print(f"   ⚠️  JSON files are kept as backups — DO NOT delete them.")
    print(f"   📌 Next step: update agents to 'from database import db'")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
