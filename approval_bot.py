# NOTE: handoffs.json is now READ-ONLY archive. All reads/writes use pipeline.db via db_helpers.py
"""
approval_bot.py — Telegram approval bot for CXRXVX publisher pipeline
=======================================================================
Polls Telegram for Accept/Decline callbacks sent by publisher_agent.py.

Run with:  python3 approval_bot.py

Callback data format (set by publisher_agent.py):
  approve|{wp_post_id}   → publishes the WordPress draft
  decline|{wp_post_id}   → leaves as draft, status set to "declined"
"""

import db_helpers
import json
import time
import threading
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR      = Path(__file__).parent
MEMORY_DIR    = BASE_DIR / "memory"
KEYWORD_FILE  = MEMORY_DIR / "keyword_data.json"
LOGS_DIR      = MEMORY_DIR / "logs" / "approval_bot"

LOGS_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(BASE_DIR))
from config import (
    WP_URL, WP_USERNAME, WP_APP_PASSWORD,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)

WP_AUTH      = (WP_USERNAME, WP_APP_PASSWORD)
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ── Helpers ────────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    today = datetime.now().strftime("%Y-%m-%d")
    with open(LOGS_DIR / f"{today}.log", "a") as f:
        f.write(line + "\n")


# ── Telegram API calls ─────────────────────────────────────────────────────

def answer_callback(callback_id: str, text: str):
    try:
        requests.post(
            f"{TELEGRAM_API}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text, "show_alert": False},
            timeout=10,
        )
    except Exception as e:
        log(f"answerCallbackQuery failed: {e}")


def edit_message_text(chat_id, message_id: int, text: str):
    try:
        requests.post(
            f"{TELEGRAM_API}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        log(f"editMessageText failed: {e}")


# ── WordPress calls ────────────────────────────────────────────────────────

def wp_publish(wp_post_id: int) -> bool:
    """Set WordPress post status to publish."""
    log(f"  WP publish → POST {WP_URL}/wp-json/wp/v2/posts/{wp_post_id}")
    try:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
            json={"status": "publish"},
            auth=WP_AUTH,
            timeout=30,
        )
        log(f"  WP response: HTTP {resp.status_code} | {resp.text[:300]}")
        return resp.status_code in (200, 201)
    except Exception as e:
        log(f"  WP publish EXCEPTION for post {wp_post_id}: {e}")
        return False


# ── Callback handler ───────────────────────────────────────────────────────

def handle_callback(callback_query: dict):
    callback_id = callback_query["id"]
    data        = callback_query.get("data", "")
    message     = callback_query.get("message", {})
    message_id  = message.get("message_id")
    chat_id     = message.get("chat", {}).get("id")

    log(f"CALLBACK received: data='{data}' chat_id={chat_id} msg_id={message_id}")

    if "|" not in data:
        log(f"CALLBACK parse error: no '|' in data='{data}'")
        answer_callback(callback_id, "Unknown action")
        return

    action, wp_post_id_str = data.split("|", 1)
    log(f"CALLBACK action='{action}' wp_post_id_str='{wp_post_id_str}'")
    try:
        wp_post_id = int(wp_post_id_str)
    except ValueError:
        log(f"CALLBACK invalid post ID: '{wp_post_id_str}'")
        answer_callback(callback_id, "Invalid post ID")
        return

    article = db_helpers.get_handoff_by_wp_post_id(wp_post_id)
    if not article:
        answer_callback(callback_id, "Article not found in handoffs")
        log(f"CALLBACK no slug for wp_post_id={wp_post_id}")
        return

    slug  = article["slug"]
    title = article.get("article_title", slug)
    log(f"CALLBACK matched slug='{slug}' title='{title[:60]}'  current status='{article.get('status')}'")

    if action == "approve":
        ok = wp_publish(wp_post_id)
        if ok:
            db_helpers.update_handoff(slug, {
                "status":         "published",
                "published_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })

            # Update keyword_data status
            keyword_data = load_json(KEYWORD_FILE, {})
            if slug in keyword_data:
                keyword_data[slug]["status"] = "published"
                save_json(KEYWORD_FILE, keyword_data)

            answer_callback(callback_id, "Published!")
            edit_message_text(chat_id, message_id, f"✅ PUBLISHED: {title}")
            log(f"Approved and published: {slug} (post {wp_post_id})")
        else:
            answer_callback(callback_id, "WordPress publish failed — check logs")
            log(f"Failed to publish post {wp_post_id} for slug: {slug}")

    elif action == "decline":
        db_helpers.update_handoff(slug, {
            "status":        "rejected",
            "declined_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        answer_callback(callback_id, "Declined — article stays as draft")
        edit_message_text(chat_id, message_id, f"❌ DECLINED: {title}")
        log(f"Rejected: {slug} (post {wp_post_id}) — stays as WordPress draft")

    else:
        answer_callback(callback_id, "Unknown action")
        log(f"Unknown callback action: {action}")


# ── Main polling loop ──────────────────────────────────────────────────────

def run():
    log("Approval bot starting — polling Telegram for callbacks...")
    offset = 0

    while True:
        try:
            resp = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params={
                    "offset":           offset,
                    "timeout":          30,
                    "allowed_updates":  ["callback_query"],
                },
                timeout=40,
            )
            if resp.status_code == 200:
                updates = resp.json().get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    if "callback_query" in update:
                        handle_callback(update["callback_query"])
            else:
                log(f"getUpdates error {resp.status_code}: {resp.text[:100]}")
                time.sleep(5)

        except requests.exceptions.Timeout:
            pass  # Long-poll timeout is normal — loop again immediately
        except Exception as e:
            log(f"Polling error: {e}")
            time.sleep(5)


def start_bot_thread() -> threading.Thread | None:
    """
    Start the approval bot polling loop in a background daemon thread.
    Call this from scheduler.py at startup.
    Returns the thread, or None if Telegram credentials are missing.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[approval_bot] Telegram not configured — bot thread not started")
        return None
    t = threading.Thread(target=run, name="approval-bot", daemon=True)
    t.start()
    print("[approval_bot] Bot thread started — polling for callbacks")
    return t


if __name__ == "__main__":
    run()
