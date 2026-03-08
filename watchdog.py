"""
watchdog.py — Pipeline Error Watchdog for CXRXVX Affiliates
=============================================================
Runs after EVERY scheduler pipeline (not just daily like health_monitor).
Catches errors immediately, diagnoses them, writes fix instructions.

Zero Claude API calls. Zero cost. Pure Python pattern matching.

HOW TO USE:
  Called automatically by scheduler.py after each pipeline run:
      from watchdog import check_pipeline_run

      # After pipeline completes:
      issues = check_pipeline_run()
      if issues["critical"]:
          print("🚨 CRITICAL ISSUES — check memory/watchdog_alerts.json")

  Or run standalone to check current state:
      python3 watchdog.py

WHAT IT CHECKS:
  1. Agent crash detection — did any agent throw an unhandled exception?
  2. API failures — Claude or WordPress down?
  3. Pipeline stuck — articles not moving between stages?
  4. Cost spike — spending way more than expected?
  5. Publishing overcap — publishing more than Google-safe ramp allows?
  6. Lock file stuck — pipeline lock older than 2 hours?
  7. Disk space — memory files growing dangerously?
  8. Empty outputs — agents ran but produced nothing?

OUTPUT:
  memory/watchdog_alerts.json — latest alert state
  memory/logs/watchdog/YYYY-MM-DD.log — full history

FUTURE (Phase 5):
  CEO agent reads watchdog_alerts.json → sends Telegram alert → you respond.
  Until then, check this file manually or after seeing errors in scheduler output.
"""

import json
import os
from datetime import datetime, timedelta

# ── Config ──────────────────────────────────────────────────────────────────
MEMORY_DIR = "memory"
LOGS_DIR = "memory/logs"
WATCHDOG_ALERTS_FILE = "memory/watchdog_alerts.json"
WATCHDOG_LOG_DIR = "memory/logs/watchdog"
HANDOFFS_FILE = "memory/handoffs.json"
LOCK_FILE = "memory/.pipeline_lock"
DAILY_COUNTER_FILE = "memory/.daily_counter.json"

try:
    from config import SITE_LAUNCH_DATE
except ImportError:
    SITE_LAUNCH_DATE = "2026-03-05"

# Cost alert threshold (per day)
COST_ALERT_THRESHOLD = 15.0  # Warn before hitting the $20 circuit breaker
LOCK_STALE_HOURS = 2

os.makedirs(WATCHDOG_LOG_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def wlog(msg):
    """Write to watchdog log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"{timestamp} — {msg}"
    print(f"[watchdog] {log_line}")
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(WATCHDOG_LOG_DIR, f"{today}.log")
    with open(log_path, "a") as f:
        f.write(log_line + "\n")


# ═══════════════════════════════════════════════════════
# ERROR DIAGNOSIS DATABASE
# Each known error pattern → diagnosis + fix instructions
# ═══════════════════════════════════════════════════════

# Pattern: (string to search for in error) → diagnosis dict
ERROR_PATTERNS = [
    # ── API errors ──
    {
        "pattern": "401",
        "agent_hint": "publisher",
        "diagnosis": "WordPress authentication failed (HTTP 401)",
        "fix": "Regenerate Application Password in WordPress admin → Users → Your Profile → Application Passwords. Update WP_APP_PASSWORD in config.py.",
        "severity": "critical",
        "location": "config.py → WP_APP_PASSWORD",
    },
    {
        "pattern": "403",
        "agent_hint": "publisher",
        "diagnosis": "WordPress permission denied (HTTP 403)",
        "fix": "Check your WordPress user has Administrator role. Go to Users → Your Profile and verify.",
        "severity": "critical",
        "location": "WordPress admin → Users",
    },
    {
        "pattern": "authentication_error",
        "agent_hint": "any",
        "diagnosis": "Claude API authentication failed",
        "fix": "Check ANTHROPIC_API_KEY in config.py. Verify at console.anthropic.com that the key is active and has credits.",
        "severity": "critical",
        "location": "config.py → ANTHROPIC_API_KEY",
    },
    {
        "pattern": "rate_limit",
        "agent_hint": "any",
        "diagnosis": "Claude API rate limit hit",
        "fix": "Too many requests. Wait 60 seconds and retry. If persistent, check your API tier at console.anthropic.com.",
        "severity": "warning",
        "location": "console.anthropic.com → rate limits",
    },
    {
        "pattern": "insufficient_quota",
        "agent_hint": "any",
        "diagnosis": "Claude API credits exhausted",
        "fix": "Top up credits at console.anthropic.com → Billing. Recommended: add $30.",
        "severity": "critical",
        "location": "console.anthropic.com → Billing",
    },
    {
        "pattern": "overloaded_error",
        "agent_hint": "any",
        "diagnosis": "Claude API is overloaded",
        "fix": "Temporary issue on Anthropic's side. Will resolve automatically. Next scheduler run should work.",
        "severity": "warning",
        "location": "No action needed — retry automatically",
    },
    # ── File errors ──
    {
        "pattern": "JSONDecodeError",
        "agent_hint": "any",
        "diagnosis": "Corrupted JSON file — data was partially written",
        "fix": "Check which JSON file is corrupted. If handoffs.json: restore from most recent git commit with 'git checkout -- memory/handoffs.json'. This is why we need SQLite (Phase 3).",
        "severity": "critical",
        "location": "memory/*.json — check git log for last good version",
    },
    {
        "pattern": "FileNotFoundError",
        "agent_hint": "any",
        "diagnosis": "Expected file is missing",
        "fix": "Check memory/ folder. Run health_monitor.py to recreate missing files. Common cause: accidentally deleted or moved a file.",
        "severity": "critical",
        "location": "memory/ folder",
    },
    {
        "pattern": "PermissionError",
        "agent_hint": "any",
        "diagnosis": "Cannot write to file — permission denied",
        "fix": "Run: chmod -R 755 memory/ to fix permissions. On VPS: check the user running the scheduler owns the memory/ folder.",
        "severity": "critical",
        "location": "memory/ folder permissions",
    },
    # ── Network errors ──
    {
        "pattern": "ConnectionError",
        "agent_hint": "any",
        "diagnosis": "Network connection failed",
        "fix": "Check internet connection. On VPS: verify DNS is working with 'ping google.com'. If only WordPress fails, SiteGround might be down — check status.siteground.com.",
        "severity": "critical",
        "location": "Network / internet connection",
    },
    {
        "pattern": "Timeout",
        "agent_hint": "any",
        "diagnosis": "Request timed out",
        "fix": "Slow connection or server overloaded. Usually temporary. If WordPress timeouts persist, check SiteGround dashboard for server issues.",
        "severity": "warning",
        "location": "Network or SiteGround server",
    },
    # ── Article writer errors ──
    {
        "pattern": "Article too short",
        "agent_hint": "article_writer",
        "diagnosis": "Claude returned a truncated or empty article",
        "fix": "Usually caused by max_tokens being too low or Claude hitting a safety filter. Check the article topic — if it's about a sensitive category, Claude may refuse. Try running article_agent.py again.",
        "severity": "warning",
        "location": "article_agent.py — check the specific tool that failed",
    },
    # ── Image agent errors ──
    {
        "pattern": "Playwright",
        "agent_hint": "image_agent",
        "diagnosis": "Screenshot tool (Playwright) failed",
        "fix": "Run: playwright install chromium. If already installed, the target website may block screenshots. Check TOOL_URLS dict in image_agent.py.",
        "severity": "warning",
        "location": "image_agent.py → TOOL_URLS or Playwright installation",
    },
    {
        "pattern": "Pexels",
        "agent_hint": "image_agent",
        "diagnosis": "Pexels image API failed",
        "fix": "Check PEXELS_API_KEY in config.py. Verify at pexels.com/api that your key is active.",
        "severity": "warning",
        "location": "config.py → PEXELS_API_KEY",
    },
    # ── Editor errors ──
    {
        "pattern": "Scoring failed",
        "agent_hint": "editor_agent",
        "diagnosis": "Editor could not score an article",
        "fix": "Usually a Claude API issue. Check API credits and try running editor_agent.py again.",
        "severity": "warning",
        "location": "editor_agent.py — retry",
    },
    # ── SEO agent errors ──
    {
        "pattern": "rank_math",
        "agent_hint": "seo_agent",
        "diagnosis": "RankMath meta fields not saving to WordPress",
        "fix": "Check Code Snippets plugin is active in WordPress admin. The PHP snippet that registers RankMath REST API fields may be deactivated.",
        "severity": "warning",
        "location": "WordPress admin → Code Snippets plugin",
    },
]


def diagnose_error(error_text: str, agent_name: str = "") -> dict:
    """
    Match an error string against known patterns.
    Returns diagnosis with fix instructions, or a generic fallback.
    """
    error_lower = error_text.lower()

    for pattern in ERROR_PATTERNS:
        if pattern["pattern"].lower() in error_lower:
            # Check agent hint if provided
            if pattern["agent_hint"] != "any" and agent_name:
                if pattern["agent_hint"] not in agent_name.lower():
                    continue  # Skip if agent doesn't match
            return {
                "matched_pattern": pattern["pattern"],
                "diagnosis": pattern["diagnosis"],
                "fix": pattern["fix"],
                "severity": pattern["severity"],
                "location": pattern["location"],
            }

    # Generic fallback
    return {
        "matched_pattern": None,
        "diagnosis": f"Unknown error in {agent_name or 'unknown agent'}",
        "fix": f"Check the full error in the agent's log file at memory/logs/{agent_name}/. Share the error with Opus for diagnosis.",
        "severity": "warning",
        "location": f"memory/logs/{agent_name}/",
    }


# ═══════════════════════════════════════════════════════
# WATCHDOG CHECKS
# ═══════════════════════════════════════════════════════

def check_recent_errors() -> list:
    """Scan today's logs for errors and diagnose each one."""
    today = datetime.now().strftime("%Y-%m-%d")
    diagnosed_errors = []

    if not os.path.exists(LOGS_DIR):
        return diagnosed_errors

    for agent_folder in os.listdir(LOGS_DIR):
        agent_path = os.path.join(LOGS_DIR, agent_folder)
        if not os.path.isdir(agent_path):
            continue

        for ext in [".md", ".log"]:
            log_path = os.path.join(agent_path, today + ext)
            if not os.path.exists(log_path):
                continue

            with open(log_path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    if "ERROR" in line or "❌" in line or "Failed" in line:
                        error_text = line.strip()
                        diagnosis = diagnose_error(error_text, agent_folder)
                        diagnosed_errors.append({
                            "agent": agent_folder,
                            "error": error_text[:300],
                            "log_file": log_path,
                            "line": line_num,
                            **diagnosis,
                        })

    return diagnosed_errors


def check_lock_file() -> dict:
    """Check if pipeline lock is stuck (older than LOCK_STALE_HOURS)."""
    if not os.path.exists(LOCK_FILE):
        return {"status": "ok", "message": "No lock file"}

    lock_age_seconds = datetime.now().timestamp() - os.path.getmtime(LOCK_FILE)
    lock_age_hours = lock_age_seconds / 3600

    if lock_age_hours > LOCK_STALE_HOURS:
        return {
            "status": "critical",
            "message": f"Pipeline lock stuck for {lock_age_hours:.1f} hours",
            "fix": f"Delete the lock file: rm {LOCK_FILE}",
            "age_hours": round(lock_age_hours, 1),
        }
    else:
        return {
            "status": "ok",
            "message": f"Lock active ({lock_age_hours:.1f}h) — pipeline running",
            "age_hours": round(lock_age_hours, 1),
        }


def check_cost_today() -> dict:
    """Check if today's spending is approaching the circuit breaker."""
    counter = load_json(DAILY_COUNTER_FILE, {})
    today = datetime.now().strftime("%Y-%m-%d")
    today_data = counter.get(today, {})
    cost = today_data.get("estimated_cost", 0)

    if cost >= COST_ALERT_THRESHOLD:
        return {
            "status": "warning",
            "message": f"API cost today: ${cost:.2f} — approaching $20 circuit breaker",
            "cost": cost,
        }
    else:
        return {
            "status": "ok",
            "message": f"API cost today: ${cost:.2f}",
            "cost": cost,
        }


def check_publishing_overcap() -> dict:
    """Check if today's publishing exceeded the Google-safe ramp."""
    counter = load_json(DAILY_COUNTER_FILE, {})
    today = datetime.now().strftime("%Y-%m-%d")
    today_data = counter.get(today, {})
    published_today = today_data.get("articles_published", 0)

    try:
        launch = datetime.strptime(SITE_LAUNCH_DATE, "%Y-%m-%d")
        days_active = (datetime.now() - launch).days
    except (ValueError, TypeError):
        days_active = 0

    if days_active <= 28:
        cap = 1
    elif days_active <= 90:
        cap = 2
    elif days_active <= 150:
        cap = 3
    elif days_active <= 180:
        cap = 5
    else:
        cap = 99

    if published_today > cap:
        return {
            "status": "warning",
            "message": f"Published {published_today} today but cap is {cap}/day (day {days_active})",
            "published": published_today,
            "cap": cap,
        }
    else:
        return {
            "status": "ok",
            "message": f"Published {published_today}/{cap} today",
            "published": published_today,
            "cap": cap,
        }


def check_pipeline_stuck() -> dict:
    """Check if articles are stuck at any stage (nothing moved in 24h)."""
    handoffs = load_json(HANDOFFS_FILE, {})
    now = datetime.now()
    stuck = []

    for slug, data in handoffs.items():
        if not isinstance(data, dict):
            continue
        status = data.get("status", "")
        if status not in ("pending_edit", "pending_publish"):
            continue

        # Check when this article was last updated
        written_date = data.get("written_date", "")
        editor_date = data.get("editor_reviewed", "")
        last_date = editor_date or written_date
        if not last_date:
            continue

        try:
            last_dt = datetime.strptime(last_date[:10], "%Y-%m-%d")
            days_stuck = (now - last_dt).days
            if days_stuck >= 3:
                stuck.append({
                    "slug": slug,
                    "tool": data.get("tool_name", slug),
                    "status": status,
                    "days_stuck": days_stuck,
                })
        except ValueError:
            continue

    if stuck:
        return {
            "status": "warning",
            "message": f"{len(stuck)} article(s) stuck for 3+ days",
            "stuck_articles": stuck[:5],
        }
    else:
        return {
            "status": "ok",
            "message": "Pipeline is flowing normally",
        }


def check_empty_outputs() -> dict:
    """Check if agents ran today but produced nothing — sign of silent failure."""
    today = datetime.now().strftime("%Y-%m-%d")
    warnings = []

    # Check article writer — if it ran but wrote 0 articles
    writer_log = os.path.join(LOGS_DIR, "article_writer", f"{today}.md")
    if os.path.exists(writer_log):
        with open(writer_log, "r") as f:
            content = f.read()
        if "Article Agent starting" in content and "Written:" not in content:
            if "Write-ahead cap" not in content and "No pending tools" not in content:
                warnings.append("Article writer ran but wrote 0 articles (not cap or empty queue)")

    # Check publisher — if it ran but published 0
    pub_log = os.path.join(LOGS_DIR, "publisher_agent", f"{today}.md")
    if not os.path.exists(pub_log):
        pub_log = os.path.join(LOGS_DIR, "publisher_agent", f"{today}.log")
    if os.path.exists(pub_log):
        with open(pub_log, "r") as f:
            content = f.read()
        if "Publisher" in content and "Published:" not in content and "published" not in content.lower():
            if "Nothing to publish" not in content and "cap reached" not in content.lower():
                warnings.append("Publisher ran but published 0 articles (not empty queue or cap)")

    if warnings:
        return {
            "status": "warning",
            "message": "; ".join(warnings),
            "details": warnings,
        }
    else:
        return {"status": "ok", "message": "All agents produced expected output"}


# ═══════════════════════════════════════════════════════
# MAIN CHECK — called by scheduler after each run
# ═══════════════════════════════════════════════════════

def check_pipeline_run() -> dict:
    """
    Run all watchdog checks. Returns alert summary.
    Called by scheduler.py after every pipeline run.
    Also saves to memory/watchdog_alerts.json for future CEO agent.
    """
    wlog("Watchdog check starting")

    # Run all checks
    errors = check_recent_errors()
    lock = check_lock_file()
    cost = check_cost_today()
    overcap = check_publishing_overcap()
    stuck = check_pipeline_stuck()
    empty = check_empty_outputs()

    # Categorize
    critical_issues = []
    warnings = []

    # Diagnosed errors
    for err in errors:
        if err.get("severity") == "critical":
            critical_issues.append(err)
        else:
            warnings.append(err)

    # Other checks
    for check_result in [lock, cost, overcap, stuck, empty]:
        if check_result["status"] == "critical":
            critical_issues.append(check_result)
        elif check_result["status"] == "warning":
            warnings.append(check_result)

    # Build alert package
    alert = {
        "timestamp": datetime.now().isoformat(),
        "has_critical": len(critical_issues) > 0,
        "has_warnings": len(warnings) > 0,
        "critical_count": len(critical_issues),
        "warning_count": len(warnings),
        "critical_issues": critical_issues,
        "warnings": warnings,
        "checks": {
            "errors_found": len(errors),
            "lock_status": lock["status"],
            "cost_status": cost["status"],
            "publishing_status": overcap["status"],
            "pipeline_status": stuck["status"],
            "output_status": empty["status"],
        },
    }

    # Save alert state
    save_json(WATCHDOG_ALERTS_FILE, alert)

    # Log summary
    if critical_issues:
        wlog(f"🚨 {len(critical_issues)} CRITICAL issue(s) found:")
        for issue in critical_issues:
            diagnosis = issue.get("diagnosis", issue.get("message", "Unknown"))
            fix = issue.get("fix", "Check logs")
            wlog(f"   🔴 {diagnosis}")
            wlog(f"      Fix: {fix}")
    elif warnings:
        wlog(f"⚠️  {len(warnings)} warning(s) found:")
        for warn in warnings[:5]:
            msg = warn.get("diagnosis", warn.get("message", "Unknown"))
            wlog(f"   🟡 {msg}")
    else:
        wlog("✅ All checks passed — system healthy")

    return alert


# ═══════════════════════════════════════════════════════
# STANDALONE RUN — check current state manually
# ═══════════════════════════════════════════════════════

def run():
    """Run watchdog as a standalone script."""
    print("\n🐕 Watchdog checking system state...\n")

    alert = check_pipeline_run()

    # Pretty print results
    if alert["has_critical"]:
        print(f"\n🚨 CRITICAL ISSUES ({alert['critical_count']}):")
        print("=" * 60)
        for issue in alert["critical_issues"]:
            diagnosis = issue.get("diagnosis", issue.get("message", "Unknown"))
            fix = issue.get("fix", "Check logs")
            location = issue.get("location", "")
            agent = issue.get("agent", "")
            print(f"\n  🔴 {diagnosis}")
            if agent:
                print(f"     Agent: {agent}")
            if location:
                print(f"     Where: {location}")
            print(f"     Fix:   {fix}")

    if alert["has_warnings"]:
        print(f"\n⚠️  WARNINGS ({alert['warning_count']}):")
        print("-" * 60)
        for warn in alert["warnings"]:
            msg = warn.get("diagnosis", warn.get("message", "Unknown"))
            fix = warn.get("fix", "")
            print(f"\n  🟡 {msg}")
            if fix:
                print(f"     Fix: {fix}")

    if not alert["has_critical"] and not alert["has_warnings"]:
        print("✅ All systems healthy — no issues detected\n")

    # Show check summary
    print(f"\n📋 Check summary:")
    checks = alert["checks"]
    for check_name, status in checks.items():
        icon = "✅" if status == "ok" else ("🔴" if status == "critical" else "🟡")
        print(f"   {icon} {check_name.replace('_', ' ').title()}: {status}")

    print(f"\n💾 Saved to {WATCHDOG_ALERTS_FILE}")
    print("🐕 Watchdog done.\n")


if __name__ == "__main__":
    run()