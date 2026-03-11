# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
"""
db_helpers.py — Shared SQLite database functions for CXRXVX pipeline
======================================================================
All agents import from this module instead of reading/writing handoffs.json.
SQLite with WAL mode is safe for concurrent agent execution.

DB path: memory/pipeline.db
Table:   handoffs
"""

import json
import sqlite3
from datetime import datetime

DB_PATH = "memory/pipeline.db"

# Columns that store JSON strings — auto-parsed when loading rows
_JSON_COLUMNS = {"editor_scores", "image_data", "roundup_tools", "comparison_tools", "extra"}

# Columns that store booleans as integers (0/1)
_BOOL_COLUMNS = {"images_added", "seo_done", "internal_links_done", "affiliate_injected"}


# ══════════════════════════════════════════════════════════════════════════
#  CONNECTION
# ══════════════════════════════════════════════════════════════════════════

def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Return a WAL-mode connection with row_factory set."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


# ══════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _parse_row(row: sqlite3.Row) -> dict:
    """Convert a Row to dict, parsing JSON string columns back to Python objects."""
    d = dict(row)
    for col in _JSON_COLUMNS:
        val = d.get(col)
        if val and isinstance(val, str):
            try:
                d[col] = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                pass  # Leave as string if parse fails
    return d


def _serialize_value(key: str, value) -> object:
    """Serialize a value for SQLite storage (bool→int, dict/list→JSON)."""
    if key in _BOOL_COLUMNS:
        if isinstance(value, bool):
            return 1 if value else 0
        if value is None:
            return 0
        return value
    if key in _JSON_COLUMNS:
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value
    return value


# ══════════════════════════════════════════════════════════════════════════
#  READ FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def load_all_handoffs(db_path: str = DB_PATH) -> dict:
    """Load all handoffs as a dict keyed by slug."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM handoffs").fetchall()
        return {row["slug"]: _parse_row(row) for row in rows}
    finally:
        conn.close()


def get_handoff(slug: str, db_path: str = DB_PATH) -> dict | None:
    """Load a single handoff by slug. Returns None if not found."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM handoffs WHERE slug = ?", (slug,)).fetchone()
        return _parse_row(row) if row else None
    finally:
        conn.close()


def get_handoff_by_wp_post_id(wp_post_id: int, db_path: str = DB_PATH) -> dict | None:
    """Find a handoff by WordPress post ID. Returns None if not found."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM handoffs WHERE wp_post_id = ?", (wp_post_id,)
        ).fetchone()
        return _parse_row(row) if row else None
    finally:
        conn.close()


def get_handoffs_by_status(status: str, db_path: str = DB_PATH) -> list:
    """Return list of handoff dicts with the given status."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM handoffs WHERE status = ?", (status,)
        ).fetchall()
        return [_parse_row(row) for row in rows]
    finally:
        conn.close()


def get_pending_edit(db_path: str = DB_PATH) -> list:
    """Return articles with status='pending_edit'."""
    return get_handoffs_by_status("pending_edit", db_path)


def get_pending_rewrites(db_path: str = DB_PATH) -> list:
    """Return articles with status='needs_rewrite'."""
    return get_handoffs_by_status("needs_rewrite", db_path)


def get_published(db_path: str = DB_PATH) -> list:
    """Return all published articles."""
    return get_handoffs_by_status("published", db_path)


# ══════════════════════════════════════════════════════════════════════════
#  WRITE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def _get_column_names(db_path: str = DB_PATH) -> set:
    """Return the set of column names for the handoffs table."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(handoffs)").fetchall()
        return {row["name"] for row in rows}
    finally:
        conn.close()


def update_handoff(slug: str, updates: dict, db_path: str = DB_PATH):
    """
    Update fields for a handoff.
    updates = {'status': 'published', 'wp_post_id': 123, ...}
    Automatically handles bool→int and dict/list→JSON serialization.
    Silently ignores keys that don't exist as columns in the table.
    """
    if not updates:
        return
    updates = dict(updates)  # don't mutate caller's dict
    updates["updated_at"] = datetime.now().isoformat()
    valid_cols = _get_column_names(db_path)
    updates = {k: v for k, v in updates.items() if k in valid_cols}
    if not updates:
        return
    serialized = {k: _serialize_value(k, v) for k, v in updates.items()}
    set_clause = ", ".join(f"{k} = ?" for k in serialized.keys())
    values = list(serialized.values()) + [slug]
    conn = get_db_connection(db_path)
    try:
        conn.execute(f"UPDATE handoffs SET {set_clause} WHERE slug = ?", values)
        conn.commit()
    finally:
        conn.close()


def insert_handoff(article: dict, db_path: str = DB_PATH):
    """
    Insert a new article into handoffs. Ignores if slug already exists.
    Handles both JSON field names (tools_covered, tool_a, tool_b)
    and SQLite field names (roundup_tools, comparison_tools).
    """
    now = datetime.now().isoformat()

    slug = article.get("slug") or article.get("url_slug")

    # Normalize roundup_tools — article_agent uses "tools_covered"
    roundup_tools = article.get("roundup_tools") or article.get("tools_covered", [])

    # Normalize comparison_tools — article_agent stores flat tool_a/tool_b
    comparison_tools = article.get("comparison_tools") or {}
    if not comparison_tools and (article.get("tool_a") or article.get("tool_b")):
        comparison_tools = {
            "tool_a": article.get("tool_a", ""),
            "tool_b": article.get("tool_b", ""),
        }

    # Normalize hook_style — article_agent uses "hook_type"
    hook_style = article.get("hook_style") or article.get("hook_type", "")

    # Normalize writing_angle — article_agent uses "writing_style"
    writing_angle = article.get("writing_angle") or article.get("writing_style", "")

    conn = get_db_connection(db_path)
    try:
        conn.execute("""
            INSERT OR IGNORE INTO handoffs
            (slug, tool_name, tool_key, article_type, article_title, url_slug,
             primary_keyword, word_count, article_html, status, written_date,
             tool_score, category, tool_url, hook_style, writing_angle,
             editor_score, editor_feedback, editor_rewrite_instructions, editor_deductions,
             editor_scores, editor_reviewed, images_added, image_data, images_date,
             seo_done, internal_links_done, wp_post_id, priority_score,
             affiliate_injected, roundup_tools, comparison_tools, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            slug,
            article.get("tool_name"),
            article.get("tool_key"),
            article.get("article_type"),
            article.get("article_title"),
            article.get("url_slug", slug),
            article.get("primary_keyword"),
            article.get("word_count", 0),
            article.get("article_html", ""),
            article.get("status", "pending_edit"),
            article.get("written_date"),
            article.get("tool_score", 0),
            article.get("category"),
            article.get("tool_url"),
            hook_style,
            writing_angle,
            article.get("editor_score", 0),
            article.get("editor_feedback"),
            article.get("editor_rewrite_instructions"),
            article.get("editor_deductions"),
            json.dumps(article["editor_scores"]) if article.get("editor_scores") else None,
            article.get("editor_reviewed"),
            1 if article.get("images_added") else 0,
            json.dumps(article["image_data"]) if article.get("image_data") else None,
            article.get("images_date"),
            1 if article.get("seo_done") else 0,
            1 if article.get("internal_links_done") else 0,
            article.get("wp_post_id"),
            article.get("priority_score", 0),
            1 if article.get("affiliate_injected") else 0,
            json.dumps(roundup_tools),
            json.dumps(comparison_tools),
            now,
            now,
        ))
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
#  COUNTER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def get_counter(key: str, db_path: str = DB_PATH) -> int:
    """Get current integer value of a named counter. Returns 0 if not found."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("SELECT value FROM counters WHERE key = ?", (key,)).fetchone()
        if not row:
            return 0
        val = row["value"]
        # Handle both plain int-string and JSON dict formats
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, int):
                    return parsed
                if isinstance(parsed, dict):
                    # Legacy format: {"date": ..., "articles_published": N}
                    return parsed.get("articles_published", 0)
            except (json.JSONDecodeError, ValueError):
                try:
                    return int(val)
                except ValueError:
                    return 0
        return int(val) if val is not None else 0
    finally:
        conn.close()


def increment_counter(key: str, db_path: str = DB_PATH):
    """Increment a named counter by 1, creating it at 1 if it doesn't exist."""
    now = datetime.now().isoformat()
    conn = get_db_connection(db_path)
    try:
        # Fetch current value first to handle non-integer legacy values
        row = conn.execute("SELECT value FROM counters WHERE key = ?", (key,)).fetchone()
        if row:
            current = get_counter(key, db_path)
            conn.execute(
                "UPDATE counters SET value = ?, updated_at = ? WHERE key = ?",
                (str(current + 1), now, key)
            )
        else:
            conn.execute(
                "INSERT INTO counters (key, value, updated_at) VALUES (?, '1', ?)",
                (key, now)
            )
        conn.commit()
    finally:
        conn.close()


def reset_counter(key: str, db_path: str = DB_PATH):
    """Reset a named counter to 0."""
    now = datetime.now().isoformat()
    conn = get_db_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO counters (key, value, updated_at) VALUES (?, '0', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = '0', updated_at = ?",
            (key, now, now)
        )
        conn.commit()
    finally:
        conn.close()
