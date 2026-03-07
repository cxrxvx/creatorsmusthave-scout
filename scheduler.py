import schedule, time, sys, os, json
from datetime import datetime, date
import tool_scout, keyword_agent, article_agent, publisher_agent, health_monitor, seo_agent

SITE_LAUNCH = datetime(2026, 3, 5)
SCAN_TIMES = ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
HEALTH_CHECK_TIME = "08:00"
DAILY_COST_LIMIT_USD = 20.00
QUIET_HOURS_START = 23
QUIET_HOURS_END = 5
LOCK_FILE = "memory/.pipeline_lock"
DAILY_COUNTER_FILE = "memory/.daily_counter.json"

def get_daily_cap():
    months_active = (datetime.now() - SITE_LAUNCH).days / 30
    if months_active < 2:   return 2
    elif months_active < 4: return 3
    elif months_active < 6: return 5
    else:                   return 99

def get_articles_written_today():
    today = str(date.today())
    if not os.path.exists(DAILY_COUNTER_FILE): return 0
    try:
        data = json.load(open(DAILY_COUNTER_FILE))
        return 0 if data.get("date") != today else data.get("articles_published", 0)
    except: return 0

def increment_daily_counter(count):
    today = str(date.today())
    current = get_articles_written_today()
    os.makedirs("memory", exist_ok=True)
    json.dump({"date": today, "articles_published": current + count}, open(DAILY_COUNTER_FILE, "w"))

def get_estimated_cost_today():
    try: return float(json.load(open("memory/system_health.json")).get("estimated_cost_today", 0.0))
    except: return 0.0

def cost_limit_exceeded():
    cost = get_estimated_cost_today()
    if cost >= DAILY_COST_LIMIT_USD:
        print(f"\n  COST CIRCUIT BREAKER: ${cost:.2f} spent — limit ${DAILY_COST_LIMIT_USD:.2f}")
        write_scheduler_log(f"COST BREAKER: ${cost:.2f}")
        return True
    return False

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        lock_age = time.time() - os.path.getmtime(LOCK_FILE)
        if lock_age > 7200:
            os.remove(LOCK_FILE)
            write_scheduler_log("Stale lock removed")
        else:
            print(f"  Pipeline already running ({lock_age/60:.0f}min) — skipping")
            write_scheduler_log("Skipped — already running")
            return False
    os.makedirs("memory", exist_ok=True)
    open(LOCK_FILE, "w").write(datetime.now().isoformat())
    return True

def release_lock():
    if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)

def has_pending_articles():
    try:
        data = json.load(open("memory/keyword_data.json"))
        return any(v.get("status") == "pending_article" for v in data.values())
    except: return True

def in_quiet_hours():
    # Quiet hours disabled — running 24/7 to catch tool launches in any timezone
    return False

def write_scheduler_log(entry):
    log_dir = "memory/logs/scheduler"
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    with open(f"{log_dir}/{today}.md", "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M')}] {entry}\n")

def banner(text):
    print(f"\n{'=' * 50}\n  {text}\n{'=' * 50}\n")

def _run_step(name, fn):
    print(f"\n{'-' * 50}\n  {name}\n{'-' * 50}")
    try:
        fn()
        write_scheduler_log(f"OK {name}")
    except Exception as e:
        print(f"\n  FAILED {name}: {e}")
        write_scheduler_log(f"FAILED {name}: {e}")

def run_pipeline():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if in_quiet_hours(): return
    if not acquire_lock(): return
    try:
        cap = get_daily_cap()
        already = get_articles_written_today()
        remaining = cap - already
        if remaining <= 0:
            banner(f"Cap reached — scouting only — {now}")
            write_scheduler_log(f"Cap reached ({already}/{cap})")
            _run_step("Tool Scout", tool_scout.run)
            _run_step("Keyword Agent", keyword_agent.run)
            return
        banner(f"Pipeline starting — {now}")
        print(f"  Cap: {cap} | Published: {already} | Remaining: {remaining}")
        write_scheduler_log(f"Pipeline started. Remaining: {remaining}/{cap}")
        if cost_limit_exceeded(): return
        _run_step("Tool Scout", tool_scout.run)
        _run_step("Keyword Agent", keyword_agent.run)
        if has_pending_articles():
            # Writer has no daily cap — build up draft library freely
            # Publisher respects the cap — controls what actually goes live
            article_agent.DAILY_CAP = 10
            publisher_agent.DAILY_PUBLISH_CAP = remaining
            _run_step("Article Writer", article_agent.run)
            _run_step("Publisher", publisher_agent.run)
            _run_step("SEO Agent", seo_agent.run)
            try:
                data = json.load(open("memory/keyword_data.json"))
                now_pub = sum(1 for v in data.values() if v.get("status") in ("draft_live","published") and v.get("wp_post_id"))
                increment_daily_counter(max(0, now_pub - already))
            except: pass
        else:
            print("\n  No tools queued — skipping Article Writer")
            write_scheduler_log("Skipped Article Writer — nothing pending")
        banner(f"Pipeline complete — {datetime.now().strftime('%H:%M')}")
        write_scheduler_log("Pipeline complete")
    finally:
        release_lock()

def run_health_check():
    banner(f"Health Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    write_scheduler_log("Health check started")
    try:
        health_monitor.run()
        write_scheduler_log("Health check complete")
    except Exception as e:
        print(f"  Failed: {e}")
        write_scheduler_log(f"FAILED Health Monitor: {e}")

def setup_schedule():
    for t in SCAN_TIMES:
        schedule.every().day.at(t).do(run_pipeline)
        print(f"  Pipeline: {t} EET")
    schedule.every().day.at(HEALTH_CHECK_TIME).do(run_health_check)
    print(f"  Health:   {HEALTH_CHECK_TIME} EET")

def main():
    if "--now" in sys.argv:
        print("\n--now flag — running pipeline once\n")
        run_pipeline()
        return
    banner("Creators Must Have — Scheduler Starting")
    print(f"  Daily cap:    {get_daily_cap()} articles/day")
    print(f"  Cost limit:   ${DAILY_COST_LIMIT_USD:.2f}/day")
    print(f"  Quiet hours:  {QUIET_HOURS_START}:00 - {QUIET_HOURS_END}:00")
    print(f"\n  Setting up schedule...\n")
    setup_schedule()
    print(f"\n  Next runs:")
    for job in schedule.jobs:
        print(f"    {job.next_run.strftime('%H:%M')} — {job.job_func.__name__}")
    print(f"\n{'=' * 50}\n  Scheduler running. Ctrl+C to stop.\n{'=' * 50}\n")
    write_scheduler_log("Scheduler started")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n  Stopped.")
        write_scheduler_log("Stopped by user")
        release_lock()

if __name__ == "__main__":
    main()