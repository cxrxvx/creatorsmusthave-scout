# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
import json
import os
import re
import base64
import requests
from datetime import datetime, timedelta
from anthropic import Anthropic
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    WP_URL, WP_USERNAME, WP_APP_PASSWORD
)

MEMORY_DIR = "memory"
LOGS_DIR = "memory/logs"
SYSTEM_HEALTH_FILE = "memory/system_health.json"
WEEKLY_DIGEST_FILE = "memory/weekly_digest.json"

# Expected log folders — Health Monitor creates them if missing
EXPECTED_LOG_FOLDERS = [
    "memory/logs/tool_scout",
    "memory/logs/keyword_agent",
    "memory/logs/article_writer",
    "memory/logs/editor_agent",
    "memory/logs/publisher_agent",
    "memory/logs/health_monitor"
]

# Memory files to monitor for size
MEMORY_FILES_TO_WATCH = [
    "memory/tool_database.json",
    "memory/watchlist.json",
    "memory/keyword_data.json",
    "memory/keyword_slug_index.json",
    "memory/learnings.json",
    "memory/article_performance.json",
    "memory/affiliate_links.json",
    "memory/weekly_digest.json"
]

# Required config keys — if any are missing agents will crash
REQUIRED_CONFIG_KEYS = [
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "WP_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
    "PUBLISH_MODE",
    "SITE_NAME",
    "SITE_LAUNCH_DATE"
]

# Alert thresholds
STALE_PIPELINE_DAYS = 3       # Flag pending articles older than this
SIZE_WARNING_KB = 500         # Warn if memory file exceeds this
SIZE_CRITICAL_KB = 1000       # Critical warning — add ChromaDB soon
DUPLICATE_SIMILARITY = 0.8    # Name similarity threshold for duplicate detection


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_log(entry):
    log_dir = "memory/logs/health_monitor"
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    with open(f"{log_dir}/{today}.md", "a") as f:
        f.write(entry + "\n")


# ─────────────────────────────────────────
# CHECK 1 — API CONNECTIONS
# ─────────────────────────────────────────

def check_claude_api():
    """Check if Claude API is reachable."""
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}]
        )
        return {"status": "ok", "message": "Claude API reachable"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_wordpress():
    """Check if WordPress is reachable and API password works."""
    try:
        credentials = base64.b64encode(
            f"{WP_USERNAME}:{WP_APP_PASSWORD}".encode()
        ).decode()
        headers = {"Authorization": f"Basic {credentials}"}
        response = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts?per_page=1",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            return {"status": "ok", "message": "WordPress reachable and authenticated"}
        else:
            return {"status": "error", "message": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────
# CHECK 2 — STALE PIPELINE DETECTION
# ─────────────────────────────────────────

def check_stale_pipeline():
    """
    Flag tools that have been waiting for an article longer than
    STALE_PIPELINE_DAYS. Something is stuck if this happens.
    """
    keyword_data = load_json("memory/keyword_data.json", {})
    stale = []
    today = datetime.now()

    for tool_key, data in keyword_data.items():
        if data.get("status") != "pending_article":
            continue

        researched = data.get("researched_date", "")
        if not researched:
            continue

        try:
            researched_dt = datetime.strptime(researched, "%Y-%m-%d")
            days_waiting = (today - researched_dt).days
            if days_waiting >= STALE_PIPELINE_DAYS:
                stale.append({
                    "tool": data.get("tool_name", tool_key),
                    "days_waiting": days_waiting,
                    "researched_date": researched,
                    "article_type": data.get("article_type", "unknown")
                })
        except ValueError:
            continue

    return sorted(stale, key=lambda x: x["days_waiting"], reverse=True)


# ─────────────────────────────────────────
# CHECK 3 — DUPLICATE TOOL DETECTION
# ─────────────────────────────────────────

def name_similarity(a, b):
    """
    Simple similarity check between two tool names.
    Strips common words and checks for overlap.
    """
    stop_words = {"ai", "the", "for", "and", "app", "tool", "pro", "plus"}
    a_words = set(a.lower().split()) - stop_words
    b_words = set(b.lower().split()) - stop_words

    if not a_words or not b_words:
        return 0.0

    overlap = len(a_words & b_words)
    total = len(a_words | b_words)
    return overlap / total if total > 0 else 0.0


def check_duplicates():
    """
    Scan tool_database.json for tools that look like duplicates.
    Checks both name similarity and source URL domain.
    """
    tool_db = load_json("memory/tool_database.json", {})
    tools = list(tool_db.values())
    duplicates = []
    checked = set()

    for i, tool_a in enumerate(tools):
        for j, tool_b in enumerate(tools):
            if i >= j:
                continue

            pair_key = f"{i}-{j}"
            if pair_key in checked:
                continue
            checked.add(pair_key)

            name_a = tool_a.get("name", "")
            name_b = tool_b.get("name", "")

            # Check name similarity
            similarity = name_similarity(name_a, name_b)
            if similarity >= DUPLICATE_SIMILARITY:
                duplicates.append({
                    "tool_a": name_a,
                    "tool_b": name_b,
                    "reason": f"Similar names (similarity: {similarity:.0%})"
                })
                continue

            # Check same source domain
            url_a = tool_a.get("source_url", "")
            url_b = tool_b.get("source_url", "")
            if url_a and url_b:
                domain_a = url_a.split("/")[2] if len(url_a.split("/")) > 2 else ""
                domain_b = url_b.split("/")[2] if len(url_b.split("/")) > 2 else ""
                if domain_a and domain_a == domain_b and domain_a not in [
                    "www.producthunt.com", "techcrunch.com",
                    "venturebeat.com", "hnrss.org"
                ]:
                    duplicates.append({
                        "tool_a": name_a,
                        "tool_b": name_b,
                        "reason": f"Same source domain: {domain_a}"
                    })

    return duplicates


# ─────────────────────────────────────────
# CHECK 4 — MEMORY FILE SIZE
# ─────────────────────────────────────────

def check_memory_file_sizes():
    """
    Check size of all memory files.
    Warns at 500KB, critical at 1MB — time to add ChromaDB.
    Does NOT delete anything. Data is preserved always.
    """
    results = []

    for filepath in MEMORY_FILES_TO_WATCH:
        if not os.path.exists(filepath):
            continue

        size_bytes = os.path.getsize(filepath)
        size_kb = size_bytes / 1024

        if size_kb >= SIZE_CRITICAL_KB:
            status = "critical"
            message = f"⛔ {size_kb:.0f}KB — add ChromaDB now (Phase 4)"
        elif size_kb >= SIZE_WARNING_KB:
            status = "warning"
            message = f"⚠️  {size_kb:.0f}KB — plan ChromaDB upgrade soon"
        else:
            status = "ok"
            message = f"✅ {size_kb:.1f}KB"

        results.append({
            "file": filepath,
            "size_kb": round(size_kb, 1),
            "status": status,
            "message": message
        })

    return sorted(results, key=lambda x: x["size_kb"], reverse=True)


# ─────────────────────────────────────────
# CHECK 5 — CONFIG VALIDATION
# ─────────────────────────────────────────

def check_config():
    """
    Verify all required keys exist in config.py and have real values.
    Catches missing or empty credentials before agents crash.
    """
    issues = []

    try:
        import config
        for key in REQUIRED_CONFIG_KEYS:
            value = getattr(config, key, None)
            if value is None:
                issues.append(f"Missing: {key}")
            elif value in ["", "pending", "...", "your-wp-username"]:
                issues.append(f"Placeholder value: {key} = '{value}'")
    except ImportError:
        issues.append("config.py not found")

    return issues


# ─────────────────────────────────────────
# BONUS — LOG FOLDERS + DATABASE STATS
# ─────────────────────────────────────────

def ensure_log_folders():
    """Create any missing log folders so agents don't crash."""
    created = []
    for folder in EXPECTED_LOG_FOLDERS:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            created.append(folder)
    return created


def get_database_stats():
    """Count tools in each memory file."""
    tool_db = load_json("memory/tool_database.json", {})
    watchlist = load_json("memory/watchlist.json", {})
    keyword_data = load_json("memory/keyword_data.json", {})

    pending_articles = sum(
        1 for v in keyword_data.values()
        if v.get("status") == "pending_article"
    )
    articles_written = sum(
        1 for v in keyword_data.values()
        if v.get("status") == "article_written"
    )

    return {
        "tools_in_database": len(tool_db),
        "tools_on_watchlist": len(watchlist),
        "tools_with_keywords": len(keyword_data),
        "pending_articles": pending_articles,
        "articles_written": articles_written
    }


def get_todays_errors():
    """Scan today's agent logs for any ERROR lines."""
    today = datetime.now().strftime("%Y-%m-%d")
    errors = []

    if not os.path.exists(LOGS_DIR):
        return errors

    for agent_folder in os.listdir(LOGS_DIR):
        log_path = f"{LOGS_DIR}/{agent_folder}/{today}.md"
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                for line in f:
                    if "ERROR" in line or "❌" in line:
                        errors.append({
                            "agent": agent_folder,
                            "error": line.strip()
                        })
    return errors


def get_agent_activity_today():
    """Check which agents ran today."""
    today = datetime.now().strftime("%Y-%m-%d")
    activity = {}

    if not os.path.exists(LOGS_DIR):
        return activity

    for agent_folder in os.listdir(LOGS_DIR):
        log_path = f"{LOGS_DIR}/{agent_folder}/{today}.md"
        activity[agent_folder] = {
            "ran_today": os.path.exists(log_path),
            "log_size_bytes": os.path.getsize(log_path) if os.path.exists(log_path) else 0
        }

    return activity


def estimate_todays_cost():
    """Rough API cost estimate based on agent log activity."""
    today = datetime.now().strftime("%Y-%m-%d")
    cost = 0.0

    kw_log = f"{LOGS_DIR}/keyword_agent/{today}.md"
    if os.path.exists(kw_log):
        with open(kw_log, "r") as f:
            content = f.read()
        tool_count = content.count("\n### ")
        cost += tool_count * 0.0072

    scout_log = f"{LOGS_DIR}/tool_scout/{today}.md"
    if os.path.exists(scout_log):
        with open(scout_log, "r") as f:
            content = f.read()
        eval_count = content.count("Score:")
        cost += eval_count * 0.0033

    return round(cost, 4)


# ─────────────────────────────────────────
# WEEKLY DIGEST
# ─────────────────────────────────────────

def get_week_range():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return {
        "start": monday.strftime("%Y-%m-%d"),
        "end": sunday.strftime("%Y-%m-%d"),
        "label": f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"
    }


def update_weekly_digest(health_data):
    """
    Write Health Monitor section into weekly_digest.json.
    Preserves all other agent sections.
    """
    digest = load_json(WEEKLY_DIGEST_FILE, {})
    week = get_week_range()

    if digest.get("week", {}).get("start") != week["start"]:
        digest = {
            "generated": datetime.now().isoformat(),
            "week": week,
            "system_health": {},
            "scout_summary": {},
            "content": {},
            "revenue": {}
        }

    digest["generated"] = datetime.now().isoformat()
    digest["week"] = week

    today = datetime.now().strftime("%Y-%m-%d")

    if "daily_checks" not in digest.get("system_health", {}):
        digest["system_health"] = {
            "daily_checks": {},
            "total_errors_this_week": 0,
            "apis_down_this_week": [],
            "estimated_cost_this_week": 0.0,
            "stale_tools_flagged": [],
            "duplicates_detected": [],
            "config_issues": []
        }

    digest["system_health"]["daily_checks"][today] = {
        "claude_api": health_data["api_checks"]["claude"]["status"],
        "wordpress": health_data["api_checks"]["wordpress"]["status"],
        "errors_today": len(health_data["errors_today"]),
        "estimated_cost_today": health_data["estimated_cost_today"],
        "tools_in_database": health_data["database_stats"]["tools_in_database"],
        "pending_articles": health_data["database_stats"]["pending_articles"],
        "stale_tools": len(health_data["stale_pipeline"]),
        "duplicates_found": len(health_data["duplicates"]),
        "config_issues": len(health_data["config_issues"])
    }

    # Running totals
    digest["system_health"]["estimated_cost_this_week"] = round(
        sum(
            d.get("estimated_cost_today", 0)
            for d in digest["system_health"]["daily_checks"].values()
        ), 4
    )
    digest["system_health"]["total_errors_this_week"] = sum(
        d.get("errors_today", 0)
        for d in digest["system_health"]["daily_checks"].values()
    )

    # Track stale tools (keep unique list)
    for stale in health_data["stale_pipeline"]:
        entry = f"{stale['tool']} ({stale['days_waiting']}d waiting)"
        if entry not in digest["system_health"]["stale_tools_flagged"]:
            digest["system_health"]["stale_tools_flagged"].append(entry)

    # Track duplicates
    for dup in health_data["duplicates"]:
        entry = f"{dup['tool_a']} / {dup['tool_b']}"
        if entry not in digest["system_health"]["duplicates_detected"]:
            digest["system_health"]["duplicates_detected"].append(entry)

    # Track config issues
    for issue in health_data["config_issues"]:
        if issue not in digest["system_health"]["config_issues"]:
            digest["system_health"]["config_issues"].append(issue)

    # API downtime
    if health_data["api_checks"]["claude"]["status"] == "error":
        if "Claude API" not in digest["system_health"]["apis_down_this_week"]:
            digest["system_health"]["apis_down_this_week"].append("Claude API")
    if health_data["api_checks"]["wordpress"]["status"] == "error":
        if "WordPress" not in digest["system_health"]["apis_down_this_week"]:
            digest["system_health"]["apis_down_this_week"].append("WordPress")

    save_json(WEEKLY_DIGEST_FILE, digest)
    return digest


# ─────────────────────────────────────────
# MAIN RUN
# ─────────────────────────────────────────

def run():
    print("\n🏥 Health Monitor starting...\n")
    write_log(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Health Monitor run")

    # Ensure all log folders exist
    created_folders = ensure_log_folders()
    if created_folders:
        print(f"📁 Created missing log folders:")
        for f in created_folders:
            print(f"   + {f}")
        write_log(f"Created folders: {', '.join(created_folders)}")

    # ── CHECK 1: API connections
    print("🔌 Checking API connections...")
    claude_status = check_claude_api()
    wp_status = check_wordpress()
    claude_icon = "✅" if claude_status["status"] == "ok" else "❌"
    wp_icon = "✅" if wp_status["status"] == "ok" else "❌"
    print(f"   {claude_icon} Claude API:  {claude_status['message']}")
    print(f"   {wp_icon} WordPress:   {wp_status['message']}")
    write_log(f"Claude API: {claude_status['status']} | WordPress: {wp_status['status']}")

    # ── CHECK 2: Stale pipeline
    print("\n⏳ Checking for stale pipeline tools...")
    stale = check_stale_pipeline()
    if stale:
        print(f"   ⚠️  {len(stale)} tool(s) stuck in pipeline:")
        for s in stale:
            print(f"      → {s['tool']} — waiting {s['days_waiting']} days (type: {s['article_type']})")
        write_log(f"Stale tools: {[s['tool'] for s in stale]}")
    else:
        print("   ✅ No stale tools — pipeline is flowing")
        write_log("No stale tools found")

    # ── CHECK 3: Duplicate tools
    print("\n🔍 Checking for duplicate tools...")
    duplicates = check_duplicates()
    if duplicates:
        print(f"   ⚠️  {len(duplicates)} potential duplicate(s) found:")
        for d in duplicates:
            print(f"      → {d['tool_a']} / {d['tool_b']} ({d['reason']})")
        write_log(f"Duplicates: {duplicates}")
    else:
        print("   ✅ No duplicates detected")
        write_log("No duplicates found")

    # ── CHECK 4: Memory file sizes
    print("\n📦 Checking memory file sizes...")
    file_sizes = check_memory_file_sizes()
    has_size_issues = False
    for f in file_sizes:
        print(f"   {f['message']}  ← {f['file'].replace('memory/', '')}")
        if f["status"] in ["warning", "critical"]:
            has_size_issues = True
            write_log(f"Size issue: {f['file']} = {f['size_kb']}KB ({f['status']})")
    if not file_sizes:
        print("   ℹ️  No memory files exist yet")
    if not has_size_issues:
        write_log("All memory files within normal size")

    # ── CHECK 5: Config validation
    print("\n⚙️  Validating config.py...")
    config_issues = check_config()
    if config_issues:
        print(f"   ⚠️  {len(config_issues)} config issue(s):")
        for issue in config_issues:
            print(f"      → {issue}")
        write_log(f"Config issues: {config_issues}")
    else:
        print("   ✅ All required config keys present")
        write_log("Config validated OK")

    # ── Database stats
    print("\n📊 Memory file stats:")
    db_stats = get_database_stats()
    print(f"   🔧 Tools in database:    {db_stats['tools_in_database']}")
    print(f"   👀 Tools on watchlist:   {db_stats['tools_on_watchlist']}")
    print(f"   🔑 Tools with keywords:  {db_stats['tools_with_keywords']}")
    print(f"   ✍️  Pending articles:     {db_stats['pending_articles']}")
    print(f"   📝 Articles written:     {db_stats['articles_written']}")

    # ── Agent activity + errors
    print("\n📋 Agent activity today:")
    activity = get_agent_activity_today()
    if activity:
        for agent, info in activity.items():
            icon = "✅" if info["ran_today"] else "⬜"
            print(f"   {icon} {agent}")
    else:
        print("   ℹ️  No agent logs found yet today")

    errors = get_todays_errors()
    if errors:
        print(f"\n⚠️  Errors found today ({len(errors)}):")
        for e in errors:
            print(f"   ❌ [{e['agent']}] {e['error']}")
    else:
        print("\n   ✅ No errors in today's logs")

    # ── Cost estimate
    cost = estimate_todays_cost()
    print(f"\n💸 Estimated API cost today: ${cost}")

    # ── Build full health data package
    health_data = {
        "timestamp": datetime.now().isoformat(),
        "api_checks": {
            "claude": claude_status,
            "wordpress": wp_status
        },
        "database_stats": db_stats,
        "stale_pipeline": stale,
        "duplicates": duplicates,
        "config_issues": config_issues,
        "file_sizes": file_sizes,
        "agent_activity": activity,
        "errors_today": errors,
        "estimated_cost_today": cost
    }

    # ── Save system_health.json
    save_json(SYSTEM_HEALTH_FILE, health_data)
    print(f"\n💾 system_health.json updated")

    # ── Update weekly digest
    digest = update_weekly_digest(health_data)
    week_label = digest["week"]["label"]
    week_cost = digest["system_health"]["estimated_cost_this_week"]
    week_errors = digest["system_health"]["total_errors_this_week"]

    print(f"📓 weekly_digest.json updated")
    print(f"\n📅 Week so far ({week_label}):")
    print(f"   💸 Estimated cost this week: ${week_cost}")
    print(f"   ⚠️  Total errors this week:  {week_errors}")
    if digest["system_health"]["stale_tools_flagged"]:
        print(f"   ⏳ Stale tools flagged:      {len(digest['system_health']['stale_tools_flagged'])}")
    if digest["system_health"]["duplicates_detected"]:
        print(f"   🔍 Duplicates detected:      {len(digest['system_health']['duplicates_detected'])}")

    # ── Overall status
    all_ok = (
        claude_status["status"] == "ok" and
        wp_status["status"] == "ok" and
        len(errors) == 0 and
        len(config_issues) == 0 and
        not has_size_issues
    )

    print(f"\n{'✅ All systems healthy' if all_ok else '⚠️  Issues detected — check above'}")
    write_log(f"Run complete. Status: {'OK' if all_ok else 'ISSUES DETECTED'}")
    print("\n🏥 Health Monitor done.\n")


if __name__ == "__main__":
    run()