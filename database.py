"""
database.py — SQLite Database Module for CXRXVX Affiliates
============================================================
Replaces JSON files with SQLite for safe concurrent access.

WHY: JSON has no locking. If two agents write at the same time, data
corrupts. SQLite handles concurrent reads, has transactions, and is
built into Python — zero setup.

WHAT MOVES TO SQLITE:
  memory/handoffs.json      → handoffs table
  memory/tool_database.json → tools table
  memory/keyword_data.json  → keywords table
  memory/watchlist.json     → watchlist table
  memory/.daily_counter.json → counters table
  memory/topics_used.json   → topics_used table

WHAT STAYS AS JSON (rarely written, human-editable):
  memory/affiliate_links.json   — you edit manually
  memory/manual_tools.json      — you edit manually
  memory/system_health.json     — written once daily
  memory/weekly_digest.json     — written once weekly

USAGE IN YOUR AGENTS:
  from database import db

  # Reading (was: json.load(open('memory/handoffs.json')))
  article = db.get_handoff('descript-review-podcasters')
  all_pending = db.get_handoffs_by_status('pending_edit')

  # Writing (was: json.dump(data, open('memory/handoffs.json', 'w')))
  db.upsert_handoff('descript-review-podcasters', {
      'status': 'pending_publish',
      'editor_score': 87,
  })

  # The old JSON way still works during migration — agents can switch one at a time.

DATABASE LOCATION: memory/pipeline.db
"""

import sqlite3
import json
import os
from datetime import datetime, date
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(__file__), "memory", "pipeline.db")


class PipelineDatabase:
    """
    Central SQLite database for the entire pipeline.
    Thread-safe with WAL mode. Transaction-safe. Corruption-proof.
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._create_tables()

    @contextmanager
    def _connect(self):
        """
        Safe database connection.
        Commits on success, rolls back on error, always closes.
        """
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row  # Access columns by name
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_tables(self):
        """Create all tables if they don't exist."""
        with self._connect() as conn:

            # ── TOOLS TABLE (replaces tool_database.json) ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tools (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    score INTEGER DEFAULT 0,
                    type TEXT DEFAULT 'affiliate_review',
                    category TEXT DEFAULT 'other',
                    description TEXT DEFAULT '',
                    has_affiliate_potential INTEGER DEFAULT 1,
                    is_fast_growing INTEGER DEFAULT 0,
                    source TEXT DEFAULT '',
                    discovered_date TEXT DEFAULT '',
                    promoted_date TEXT DEFAULT '',
                    status TEXT DEFAULT 'discovered',
                    competitors TEXT DEFAULT '[]',
                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── WATCHLIST TABLE (replaces watchlist.json) ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    name TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    score INTEGER DEFAULT 0,
                    category TEXT DEFAULT 'other',
                    source TEXT DEFAULT '',
                    discovered_date TEXT DEFAULT '',
                    recheck_date TEXT DEFAULT '',
                    recheck_count INTEGER DEFAULT 0,
                    extra TEXT DEFAULT '{}'
                )
            """)

            # ── KEYWORDS TABLE (replaces keyword_data.json) ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS keywords (
                    key TEXT PRIMARY KEY,
                    tool_name TEXT DEFAULT '',
                    tool_category TEXT DEFAULT 'other',
                    tool_score INTEGER DEFAULT 0,
                    primary_keyword TEXT DEFAULT '',
                    secondary_keywords TEXT DEFAULT '[]',
                    keyword_cluster TEXT DEFAULT '[]',
                    search_intent TEXT DEFAULT 'buyer',
                    difficulty_score INTEGER DEFAULT 0,
                    traffic_value TEXT DEFAULT 'medium',
                    article_type TEXT DEFAULT 'review',
                    recommended_word_count INTEGER DEFAULT 2500,
                    article_title TEXT DEFAULT '',
                    url_slug TEXT DEFAULT '',
                    serp_gap TEXT DEFAULT '',
                    urgency TEXT DEFAULT 'medium',
                    supporting_articles TEXT DEFAULT '[]',
                    roundup_tools TEXT DEFAULT '[]',
                    comparison_tools TEXT DEFAULT '{}',
                    status TEXT DEFAULT 'pending_article',
                    researched_date TEXT DEFAULT '',
                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── HANDOFFS TABLE (replaces handoffs.json) ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS handoffs (
                    slug TEXT PRIMARY KEY,
                    tool_name TEXT DEFAULT '',
                    tool_key TEXT DEFAULT '',
                    article_type TEXT DEFAULT 'review',
                    article_title TEXT DEFAULT '',
                    url_slug TEXT DEFAULT '',
                    primary_keyword TEXT DEFAULT '',
                    word_count INTEGER DEFAULT 0,
                    article_html TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending_edit',
                    written_date TEXT DEFAULT '',
                    tool_score INTEGER DEFAULT 0,
                    category TEXT DEFAULT 'other',
                    tool_url TEXT DEFAULT '',
                    hook_style TEXT DEFAULT '',
                    writing_angle TEXT DEFAULT '',

                    editor_score INTEGER,
                    editor_feedback TEXT DEFAULT '',
                    editor_rewrite_instructions TEXT DEFAULT '',
                    editor_deductions TEXT DEFAULT '',
                    editor_scores TEXT DEFAULT '{}',
                    editor_reviewed TEXT DEFAULT '',

                    images_added INTEGER DEFAULT 0,
                    image_data TEXT DEFAULT '{}',
                    images_date TEXT DEFAULT '',

                    seo_done INTEGER DEFAULT 0,
                    meta_title TEXT DEFAULT '',
                    meta_description TEXT DEFAULT '',
                    focus_keyword TEXT DEFAULT '',
                    schema_type TEXT DEFAULT '',
                    og_image TEXT DEFAULT '',
                    seo_processed_date TEXT DEFAULT '',

                    internal_links_done INTEGER DEFAULT 0,
                    internal_links_added INTEGER DEFAULT 0,
                    internal_links_removed INTEGER DEFAULT 0,
                    internal_links_date TEXT DEFAULT '',

                    wp_post_id INTEGER,
                    wp_post_url TEXT DEFAULT '',
                    wp_url TEXT DEFAULT '',
                    published_date TEXT DEFAULT '',
                    priority_score INTEGER DEFAULT 0,
                    affiliate_injected INTEGER DEFAULT 0,
                    publish_category TEXT DEFAULT '',

                    roundup_tools TEXT DEFAULT '[]',
                    comparison_tools TEXT DEFAULT '{}',

                    extra TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── COUNTERS TABLE (replaces .daily_counter.json) ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS counters (
                    key TEXT PRIMARY KEY,
                    value TEXT DEFAULT '{}',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── TOPICS USED TABLE (replaces topics_used.json) ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS topics_used (
                    slug TEXT PRIMARY KEY,
                    added_date TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── Indexes for common queries ──
            conn.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_status ON handoffs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_keywords_status ON keywords(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tools_score ON tools(score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tools_category ON tools(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_article_type ON handoffs(article_type)")

    # ═══════════════════════════════════════════════════════
    # TOOLS — replaces tool_database.json
    # ═══════════════════════════════════════════════════════

    def get_tool(self, key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tools WHERE key = ?", (key,)).fetchone()
            return self._row_to_dict(row) if row else None

    def get_all_tools(self, min_score: int = 0) -> dict:
        """Returns dict keyed by tool key, same format as tool_database.json."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tools WHERE score >= ? ORDER BY score DESC",
                (min_score,)).fetchall()
            return {row["key"]: self._row_to_dict(row) for row in rows}

    def get_tools_by_category(self, category: str) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tools WHERE category = ? ORDER BY score DESC",
                (category,)).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def upsert_tool(self, key: str, data: dict):
        """Insert or update a tool. Pass any subset of fields."""
        data["key"] = key
        data["updated_at"] = datetime.now().isoformat()
        # Serialize list/dict fields
        for field in ("competitors", "extra"):
            if field in data and not isinstance(data[field], str):
                data[field] = json.dumps(data[field])
        self._upsert("tools", "key", data)

    def delete_tool(self, key: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM tools WHERE key = ?", (key,))

    # ═══════════════════════════════════════════════════════
    # WATCHLIST — replaces watchlist.json
    # ═══════════════════════════════════════════════════════

    def get_watchlist(self) -> list:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM watchlist ORDER BY score DESC").fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_watchlist_due(self) -> list:
        today = date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist WHERE recheck_date <= ? ORDER BY score DESC",
                (today,)).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def upsert_watchlist(self, name: str, data: dict):
        data["name"] = name
        for field in ("extra",):
            if field in data and not isinstance(data[field], str):
                data[field] = json.dumps(data[field])
        self._upsert("watchlist", "name", data)

    def delete_from_watchlist(self, name: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM watchlist WHERE name = ?", (name,))

    # ═══════════════════════════════════════════════════════
    # KEYWORDS — replaces keyword_data.json
    # ═══════════════════════════════════════════════════════

    def get_keyword(self, key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM keywords WHERE key = ?", (key,)).fetchone()
            return self._row_to_dict(row) if row else None

    def get_all_keywords(self) -> dict:
        """Returns dict keyed by keyword key, same format as keyword_data.json."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM keywords").fetchall()
            return {row["key"]: self._row_to_dict(row) for row in rows}

    def get_keywords_by_status(self, status: str) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM keywords WHERE status = ?", (status,)).fetchall()
            return {row["key"]: self._row_to_dict(row) for row in rows}

    def upsert_keyword(self, key: str, data: dict):
        data["key"] = key
        data["updated_at"] = datetime.now().isoformat()
        for field in ("secondary_keywords", "keyword_cluster", "supporting_articles",
                       "roundup_tools", "comparison_tools", "extra"):
            if field in data and not isinstance(data[field], str):
                data[field] = json.dumps(data[field])
        self._upsert("keywords", "key", data)

    # ═══════════════════════════════════════════════════════
    # HANDOFFS — replaces handoffs.json
    # ═══════════════════════════════════════════════════════

    def get_handoff(self, slug: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM handoffs WHERE slug = ?", (slug,)).fetchone()
            return self._row_to_dict(row) if row else None

    def get_all_handoffs(self) -> dict:
        """Returns dict keyed by slug, same format as handoffs.json."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM handoffs").fetchall()
            return {row["slug"]: self._row_to_dict(row) for row in rows}

    def get_handoffs_by_status(self, status: str) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM handoffs WHERE status = ? ORDER BY tool_score DESC",
                (status,)).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def count_handoffs_by_status(self, *statuses) -> int:
        """Count articles at given statuses. Used by write-ahead cap."""
        with self._connect() as conn:
            placeholders = ",".join("?" * len(statuses))
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM handoffs WHERE status IN ({placeholders})",
                statuses).fetchone()
            return row["cnt"] if row else 0

    def upsert_handoff(self, slug: str, data: dict):
        data["slug"] = slug
        data["updated_at"] = datetime.now().isoformat()
        for field in ("editor_scores", "image_data", "roundup_tools",
                       "comparison_tools", "extra"):
            if field in data and not isinstance(data[field], str):
                data[field] = json.dumps(data[field])
        # Convert boolean to int for SQLite
        for bool_field in ("images_added", "seo_done", "internal_links_done", "affiliate_injected"):
            if bool_field in data:
                data[bool_field] = 1 if data[bool_field] else 0
        self._upsert("handoffs", "slug", data)

    def get_published_articles(self) -> list:
        """Get all published articles — used by internal_link_agent."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM handoffs WHERE status IN ('published', 'draft_live') ORDER BY published_date DESC"
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    # ═══════════════════════════════════════════════════════
    # COUNTERS — replaces .daily_counter.json
    # ═══════════════════════════════════════════════════════

    def get_counter(self, key: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM counters WHERE key = ?", (key,)).fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    return {}
            return {}

    def set_counter(self, key: str, value: dict):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO counters (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), datetime.now().isoformat()))

    # ═══════════════════════════════════════════════════════
    # TOPICS USED — replaces topics_used.json
    # ═══════════════════════════════════════════════════════

    def get_topics_used(self) -> list:
        with self._connect() as conn:
            rows = conn.execute("SELECT slug FROM topics_used").fetchall()
            return [row["slug"] for row in rows]

    def add_topic(self, slug: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO topics_used (slug, added_date) VALUES (?, ?)",
                (slug, datetime.now().isoformat()))

    def is_topic_used(self, slug: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM topics_used WHERE slug = ?", (slug,)).fetchone()
            return row is not None

    # ═══════════════════════════════════════════════════════
    # STATS & QUERIES — useful for health_monitor and watchdog
    # ═══════════════════════════════════════════════════════

    def get_pipeline_stats(self) -> dict:
        """Quick overview of the entire pipeline state."""
        with self._connect() as conn:
            stats = {}

            # Tool counts
            row = conn.execute("SELECT COUNT(*) as cnt FROM tools").fetchone()
            stats["total_tools"] = row["cnt"]

            # Tools by category
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM tools GROUP BY category ORDER BY cnt DESC"
            ).fetchall()
            stats["tools_by_category"] = {r["category"]: r["cnt"] for r in rows}

            # Watchlist
            row = conn.execute("SELECT COUNT(*) as cnt FROM watchlist").fetchone()
            stats["watchlist_count"] = row["cnt"]

            # Keyword statuses
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM keywords GROUP BY status"
            ).fetchall()
            stats["keyword_statuses"] = {r["status"]: r["cnt"] for r in rows}

            # Handoff statuses
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM handoffs GROUP BY status"
            ).fetchall()
            stats["handoff_statuses"] = {r["status"]: r["cnt"] for r in rows}

            # Article types
            rows = conn.execute(
                "SELECT article_type, COUNT(*) as cnt FROM handoffs GROUP BY article_type"
            ).fetchall()
            stats["article_types"] = {r["article_type"]: r["cnt"] for r in rows}

            # Published count
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM handoffs WHERE status = 'published'"
            ).fetchone()
            stats["published_count"] = row["cnt"]

            return stats

    # ═══════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════

    def _row_to_dict(self, row) -> dict:
        """Convert sqlite3.Row to a plain dict, deserializing JSON fields."""
        if row is None:
            return {}
        d = dict(row)
        # Deserialize known JSON fields
        for field in ("competitors", "extra", "secondary_keywords", "keyword_cluster",
                       "supporting_articles", "roundup_tools", "comparison_tools",
                       "editor_scores", "image_data"):
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        # Convert int booleans back
        for field in ("images_added", "seo_done", "internal_links_done",
                       "affiliate_injected", "has_affiliate_potential", "is_fast_growing"):
            if field in d and isinstance(d[field], int):
                d[field] = bool(d[field])
        return d

    def _upsert(self, table: str, pk_field: str, data: dict):
        """Generic upsert — insert or update on conflict."""
        with self._connect() as conn:
            # Get existing columns for this table
            cursor = conn.execute(f"PRAGMA table_info({table})")
            valid_columns = {row[1] for row in cursor.fetchall()}

            # Filter data to only valid columns
            filtered = {k: v for k, v in data.items() if k in valid_columns}

            if not filtered or pk_field not in filtered:
                return

            pk_value = filtered[pk_field]

            # Check if record already exists
            existing = conn.execute(
                f"SELECT 1 FROM {table} WHERE {pk_field} = ?", (pk_value,)
            ).fetchone()

            if existing:
                # UPDATE — only update the fields provided
                update_fields = {k: v for k, v in filtered.items() if k != pk_field}
                if not update_fields:
                    return
                set_clause = ", ".join(f"{c} = ?" for c in update_fields.keys())
                sql = f"UPDATE {table} SET {set_clause} WHERE {pk_field} = ?"
                conn.execute(sql, list(update_fields.values()) + [pk_value])
            else:
                # INSERT — full record
                columns = list(filtered.keys())
                placeholders = ", ".join("?" for _ in columns)
                col_names = ", ".join(columns)
                sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
                conn.execute(sql, list(filtered.values()))


# ═══════════════════════════════════════════════════════
# GLOBAL INSTANCE — import this in your agents
# ═══════════════════════════════════════════════════════

db = PipelineDatabase()
