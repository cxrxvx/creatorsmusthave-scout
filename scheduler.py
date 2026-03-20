# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
"""
scheduler.py — Decoupled pipeline scheduler for Creators Must Have
===================================================================
Phase 2.5 Opus Upgrade:
  ✅ Google-safe publishing ramp: 1/day → 2/day → 3/day → 5/day → uncapped
  ✅ Write-ahead cap: skip article writing if 21+ unpublished drafts queued
  ✅ Watchdog integration: runs after every --now pipeline and catches errors
  ✅ Pipeline summary with article type breakdown
  ✅ All existing features preserved (decoupled agents, per-agent locks, cost breaker)

Agents run on their own independent timers. Work gets processed as fast as it arrives.

Schedule:
  Tool Scout:         06:00 09:00 12:00 15:00 18:00 21:00  (6x/day)
  Keyword Agent:      06:00 09:00 12:00 15:00 18:00 21:00  (6x/day)
  Article Writer:     06:00 09:00 12:00 15:00 18:00 21:00  (6x/day — write-ahead capped)
  Editor Agent:       06:30 09:30 12:30 15:30 18:30 21:30  (6x/day — 30min after writers)
  Image Agent:        07:00 10:00 13:00 16:00 19:00 22:00  (6x/day)
  SEO Agent:          07:00 10:00 13:00 16:00 19:00 22:00  (6x/day)
  Internal Links:     23:00                                  (1x/day)
  Publisher:          10:00 17:00 21:00                     (3x/day — strategic US times)
  Health Monitor:     08:00                                  (1x/day)

Why these publisher times?
  10:00 Latvia (08:00 UTC) — Google morning crawl window
  17:00 Latvia (15:00 UTC) — US East Coast peak browsing
  21:00 Latvia (19:00 UTC) — US West Coast afternoon + overnight indexing

Drop this file into your cxrxvx-ai-empire/ folder to replace the old scheduler.py.
"""

import db_helpers
import subprocess
import sys
import os
import json
import schedule
import time
import threading
from datetime import datetime, date
from pathlib import Path

# ── Approval bot (Telegram callbacks) ─────────────────────────────────────────
try:
    from approval_bot import start_bot_thread as _start_bot_thread
except Exception as _e:
    _start_bot_thread = None
    print(f"[scheduler] approval_bot import failed ({_e}) — Telegram bot disabled")


_bot_thread = None   # set by start_approval_bot(); checked in --now mode


def start_approval_bot():
    global _bot_thread
    if _start_bot_thread:
        _bot_thread = _start_bot_thread()
    else:
        log("⚠️  Approval bot unavailable — Telegram callbacks will not be processed")

# ── paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
MEMORY_DIR = BASE_DIR / "memory"
LOCK_FILE  = MEMORY_DIR / ".pipeline_lock"
COST_FILE  = MEMORY_DIR / ".daily_cost.json"

# ── cost circuit breaker ───────────────────────────────────────────────────────
MAX_DAILY_COST = 20.00   # hard stop if API spend exceeds this today

# ── write-ahead cap ───────────────────────────────────────────────────────────
# Skip article writing if this many unpublished drafts are queued.
# At 1/day (month 1) = 3 weeks buffer. At 3/day (month 4+) = 1 week buffer.
WRITE_AHEAD_CAP = 21

# ── Google-safe publish ramp ──────────────────────────────────────────────────
SITE_LAUNCH_DATE = date(2026, 3, 5)


def get_daily_publish_cap() -> int:
    """
    Google-safe publishing ramp for new domains.
    
    Pattern Google likes: launch batch → steady drip → gradual ramp.
    The 15-article launch batch on day 1 is fine — Google expects new sites
    to launch with content. This ramp controls ONGOING daily publishing.
    
    Old (risky):  3/day from day 1
    New (safe):   1/day → 2/day → 3/day → 5/day → uncapped
    """
    days_active = (date.today() - SITE_LAUNCH_DATE).days

    if days_active <= 28:     return 3    # Weeks 1-4: 3/day
    elif days_active <= 90:   return 2    # Months 2-3: building trust
    elif days_active <= 150:  return 3    # Months 4-5: ramping up
    elif days_active <= 180:  return 5    # Month 6: Google trusts domain
    else:                     return 99   # Month 7+: uncapped


# ── write-ahead cap check ────────────────────────────────────────────────────

def should_write_articles() -> bool:
    """
    Check if we need more articles or if the draft queue is full enough.
    
    If 21+ articles are sitting at pending_edit or pending_publish,
    skip article writing to save API budget. Those articles won't
    publish for weeks — no point writing more.
    
    Returns True if writing should proceed, False to skip.
    """
    try:
        pending_edit    = db_helpers.get_handoffs_by_status("pending_edit")
        pending_publish = db_helpers.get_handoffs_by_status("pending_publish")
        unpublished = len(pending_edit) + len(pending_publish)

        if unpublished >= WRITE_AHEAD_CAP:
            log(f"⏸️  Write-ahead cap: {unpublished} drafts queued (max {WRITE_AHEAD_CAP}) — skipping article writing")
            return False

        log(f"📝 Write-ahead: {unpublished}/{WRITE_AHEAD_CAP} drafts queued — writing allowed")
        return True

    except Exception as e:
        log(f"⚠️  Write-ahead check failed ({e}) — allowing writes as safety fallback")
        return True


def get_pipeline_summary() -> str:
    """Get a quick summary of pipeline state for logging."""
    try:
        handoffs = db_helpers.load_all_handoffs()
        status_counts = {}
        type_counts = {}
        for slug, data in handoffs.items():
            status = data.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            atype = data.get("article_type", "review")
            type_counts[atype] = type_counts.get(atype, 0) + 1

        parts = []
        for s in ["pending_edit", "pending_publish", "published", "needs_rewrite"]:
            if status_counts.get(s, 0) > 0:
                parts.append(f"{status_counts[s]} {s}")

        status_str = " | ".join(parts) if parts else "empty"

        type_parts = [f"{v} {k}" for k, v in type_counts.items()]
        type_str = ", ".join(type_parts) if type_parts else ""

        summary = f"Pipeline: {status_str}"
        if type_str:
            summary += f" | Types: {type_str}"
        return summary

    except Exception:
        return "Could not read pipeline state"


# ── helpers ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_agent(script: str, extra_args: list[str] | None = None) -> bool:
    """Run a single agent script. Returns True on success."""
    cmd = [sys.executable, str(BASE_DIR / script)]
    if extra_args:
        cmd.extend(extra_args)
    log(f"▶  Starting {script}")
    try:
        result = subprocess.run(cmd, cwd=str(BASE_DIR), timeout=1800)
        if result.returncode == 0:
            log(f"✅ {script} finished")
            return True
        else:
            log(f"⚠️  {script} exited with code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        log(f"⏰ {script} timed out after 30 minutes — killed")
        return False
    except Exception as e:
        log(f"❌ {script} crashed: {e}")
        return False


def get_daily_cost() -> float:
    """Read today's accumulated API cost from the cost tracker file."""
    try:
        if not COST_FILE.exists():
            return 0.0
        data = json.loads(COST_FILE.read_text())
        if data.get("date") != str(date.today()):
            return 0.0
        return float(data.get("cost", 0.0))
    except Exception:
        return 0.0


def cost_ok() -> bool:
    """Returns True if we're still under the daily cost limit."""
    cost = get_daily_cost()
    if cost >= MAX_DAILY_COST:
        log(f"🛑 COST CIRCUIT BREAKER — ${cost:.2f} spent today (limit ${MAX_DAILY_COST:.2f}). Skipping run.")
        return False
    return True


def acquire_agent_lock(agent: str) -> bool:
    """
    Per-agent lock so two instances of the same agent never run in parallel.
    Lock file: memory/.lock_<agentname>
    Stale after 45 minutes.
    """
    lock = MEMORY_DIR / f".lock_{agent}"
    if lock.exists():
        try:
            data = json.loads(lock.read_text())
            started = datetime.fromisoformat(data["started"])
            age_mins = (datetime.now() - started).total_seconds() / 60
            if age_mins < 45:
                log(f"⏳ {agent} already running (started {age_mins:.0f}m ago) — skipping")
                return False
            else:
                log(f"🔓 Stale lock for {agent} ({age_mins:.0f}m old) — clearing")
                lock.unlink()
        except Exception:
            lock.unlink()
    lock.write_text(json.dumps({"agent": agent, "started": datetime.now().isoformat()}))
    return True


def release_agent_lock(agent: str):
    lock = MEMORY_DIR / f".lock_{agent}"
    try:
        lock.unlink(missing_ok=True)
    except Exception:
        pass


def run_with_lock(agent_name: str, script: str, extra_args: list[str] | None = None):
    """Acquire lock → cost check → run agent → release lock. Safe for concurrent schedule."""
    if not cost_ok():
        return
    if not acquire_agent_lock(agent_name):
        return
    try:
        run_agent(script, extra_args)
    finally:
        release_agent_lock(agent_name)


# ── watchdog integration ──────────────────────────────────────────────────────

def run_watchdog():
    """
    Run the watchdog after pipeline runs to catch errors immediately.
    If watchdog.py doesn't exist yet, skip gracefully.
    """
    watchdog_path = BASE_DIR / "watchdog.py"
    if not watchdog_path.exists():
        return  # Watchdog not deployed yet — skip silently

    try:
        # Import and run inline to avoid subprocess overhead
        sys.path.insert(0, str(BASE_DIR))
        from watchdog import check_pipeline_run
        alert = check_pipeline_run()

        if alert.get("has_critical"):
            log(f"🚨 WATCHDOG: {alert['critical_count']} critical issue(s) detected!")
            for issue in alert.get("critical_issues", [])[:3]:
                diagnosis = issue.get("diagnosis", issue.get("message", "Unknown"))
                log(f"   🔴 {diagnosis}")
        elif alert.get("has_warnings"):
            log(f"⚠️  WATCHDOG: {alert['warning_count']} warning(s)")
        else:
            log("🐕 Watchdog: all clear")

    except ImportError:
        # watchdog.py exists but has import errors — not critical
        log("⚠️  Watchdog import failed — check watchdog.py for errors")
    except Exception as e:
        # Watchdog itself crashed — don't let it break the scheduler
        log(f"⚠️  Watchdog error: {e}")


# ── individual agent jobs ──────────────────────────────────────────────────────
# Each runs in its own thread so slow agents don't block the scheduler clock.

def job_scout():
    threading.Thread(target=run_with_lock, args=("scout", "tool_scout.py"), daemon=True).start()

def job_keyword():
    threading.Thread(target=run_with_lock, args=("keyword", "keyword_agent.py"), daemon=True).start()

def job_article():
    """Article writer with write-ahead cap check."""
    if not should_write_articles():
        return  # Queue full — skip this run to save API budget
    threading.Thread(target=run_with_lock, args=("article", "article_agent.py"), daemon=True).start()

def job_editor():
    threading.Thread(target=run_with_lock, args=("editor", "editor_agent.py"), daemon=True).start()

def job_image():
    threading.Thread(target=run_with_lock, args=("image", "image_agent.py"), daemon=True).start()

def job_seo():
    threading.Thread(target=run_with_lock, args=("seo", "seo_agent.py"), daemon=True).start()

def job_internal_links():
    threading.Thread(target=run_with_lock, args=("links", "internal_link_agent.py"), daemon=True).start()

def job_health():
    threading.Thread(target=run_with_lock, args=("health", "health_monitor.py"), daemon=True).start()

def job_publisher():
    cap = get_daily_publish_cap()
    days = (date.today() - SITE_LAUNCH_DATE).days
    log(f"📤 Publisher firing — daily cap: {cap}/day (day {days})")
    threading.Thread(
        target=run_with_lock,
        args=("publisher", "publisher_agent.py", ["--cap", str(cap)]),
        daemon=True
    ).start()


# ── schedule setup ─────────────────────────────────────────────────────────────

def setup_schedule():
    log("📅 Setting up decoupled agent schedule...")

    # Tool Scout — 6x/day
    for t in ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]:
        schedule.every().day.at(t).do(job_scout)

    # Keyword Agent — 6x/day
    for t in ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]:
        schedule.every().day.at(t).do(job_keyword)

    # Article Writer — 6x/day (write-ahead cap checked in job_article)
    for t in ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]:
        schedule.every().day.at(t).do(job_article)

    # Editor Agent — 6x/day (30 min offset so articles exist to edit)
    for t in ["06:30", "09:30", "12:30", "15:30", "18:30", "21:30"]:
        schedule.every().day.at(t).do(job_editor)

    # Image Agent — 6x/day (1hr offset, approved articles ready by now)
    for t in ["07:00", "10:00", "13:00", "16:00", "19:00", "22:00"]:
        schedule.every().day.at(t).do(job_image)

    # SEO Agent — 6x/day (alongside image agent)
    for t in ["07:00", "10:00", "13:00", "16:00", "19:00", "22:00"]:
        schedule.every().day.at(t).do(job_seo)

    # Publisher — 3x/day at strategic US-audience times
    for t in ["10:00", "17:00", "21:00"]:
        schedule.every().day.at(t).do(job_publisher)

    # Internal Links — 1x/day after all publishing done
    schedule.every().day.at("23:00").do(job_internal_links)

    # Health Monitor — 1x/day morning check
    schedule.every().day.at("08:00").do(job_health)

    cap = get_daily_publish_cap()
    days = (date.today() - SITE_LAUNCH_DATE).days

    log("✅ Schedule configured:")
    log("   Scout + Keyword + Article:  06:00 09:00 12:00 15:00 18:00 21:00")
    log("   Editor:                     06:30 09:30 12:30 15:30 18:30 21:30")
    log("   Image + SEO:                07:00 10:00 13:00 16:00 19:00 22:00")
    log("   Publisher:                  10:00 17:00 21:00")
    log("   Internal Links:             23:00")
    log("   Health Monitor:             08:00")
    log(f"   Daily publish cap:          {cap}/day (day {days} since launch)")
    log(f"   Write-ahead cap:            {WRITE_AHEAD_CAP} max unpublished drafts")
    log(f"   Cost circuit breaker:       ${MAX_DAILY_COST:.2f}/day")


# ── run-once mode (python3 scheduler.py --now) ─────────────────────────────────

def run_pipeline_once():
    """
    Runs the full pipeline once in sequence — useful for testing.
    Includes write-ahead cap check and watchdog at the end.
    """
    log("🔁 Running full pipeline once (--now mode)...")
    cap = get_daily_publish_cap()
    days = (date.today() - SITE_LAUNCH_DATE).days
    log(f"   Publish cap: {cap}/day (day {days}) | Write-ahead cap: {WRITE_AHEAD_CAP}")
    log(f"   {get_pipeline_summary()}")

    steps = [
        ("scout",     "tool_scout.py",         None,             True),
        ("keyword",   "keyword_agent.py",       None,             True),
        ("article",   "article_agent.py",       None,             "write_ahead"),  # special check
        ("editor",    "editor_agent.py",        None,             True),
        ("image",     "image_agent.py",         None,             True),
        ("links",     "internal_link_agent.py", None,             True),
        ("publisher", "publisher_agent.py",     ["--cap", str(cap)], True),
        # SEO runs AFTER publisher so it can process newly pending_approval articles
        ("seo",       "seo_agent.py",           None,             True),
    ]

    results = []
    for name, script, args, should_run in steps:
        if not cost_ok():
            log("🛑 Cost limit hit — stopping pipeline")
            break

        # Write-ahead cap check for article writer
        if should_run == "write_ahead":
            if not should_write_articles():
                results.append((name, "skipped (write-ahead cap)"))
                continue

        success = run_agent(script, args)
        results.append((name, "✅" if success else "❌"))

    # Print run summary
    log("")
    log("📋 Pipeline run summary:")
    for name, status in results:
        log(f"   {status}  {name}")

    log(f"\n   {get_pipeline_summary()}")

    # Run watchdog to catch any errors
    log("")
    run_watchdog()

    log("✅ --now run complete")


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log("=" * 60)
    log("🚀 Creators Must Have — Decoupled Pipeline Scheduler")
    log(f"   Phase 2.5 — Google-safe ramp + write-ahead cap")
    log("=" * 60)

    start_approval_bot()

    if "--now" in sys.argv:
        run_pipeline_once()
        # If the Telegram bot thread is alive, keep the process running so
        # Alex can tap Accept/Decline on the notification that was just sent.
        # sys.exit() would kill the daemon thread immediately.
        if _bot_thread and _bot_thread.is_alive():
            log("")
            log("📱 Bot running — waiting for Telegram callbacks (Ctrl+C to exit)")
            try:
                while True:
                    time.sleep(10)
            except KeyboardInterrupt:
                log("👋 Exiting")
        sys.exit(0)

    setup_schedule()
    log("⏰ Scheduler running — press Ctrl+C to stop")
    log("")

    # Keep the scheduler alive
    while True:
        schedule.run_pending()
        time.sleep(30)   # check every 30 seconds