"""
approval_bot.py — Telegram approval bot for CXRXVX publisher pipeline
=======================================================================
Polls Telegram for Accept/Decline callbacks sent by publisher_agent.py.

Run with:  python3 approval_bot.py

Callback data format (set by publisher_agent.py):
  approve|{wp_post_id}   → publishes the WordPress draft
  decline|{wp_post_id}   → leaves as draft, status set to "declined"
"""

import json
import time
import threading
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR      = Path(__file__).parent
MEMORY_DIR    = BASE_DIR / "memory"
HANDOFFS_FILE = MEMORY_DIR / "handoffs.json"
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
    try:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
            json={"status": "publish"},
            auth=WP_AUTH,
            timeout=30,
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        log(f"WordPress publish failed for post {wp_post_id}: {e}")
        return False


# ── Handoffs lookup ────────────────────────────────────────────────────────

def find_slug_by_wp_post_id(handoffs: dict, wp_post_id: int) -> str | None:
    for slug, article in handoffs.items():
        if isinstance(article, dict) and article.get("wp_post_id") == wp_post_id:
            return slug
    return None


# ── Callback handler ───────────────────────────────────────────────────────

def handle_callback(callback_query: dict):
    callback_id = callback_query["id"]
    data        = callback_query.get("data", "")
    message     = callback_query.get("message", {})
    message_id  = message.get("message_id")
    chat_id     = message.get("chat", {}).get("id")

    if "|" not in data:
        answer_callback(callback_id, "Unknown action")
        return

    action, wp_post_id_str = data.split("|", 1)
    try:
        wp_post_id = int(wp_post_id_str)
    except ValueError:
        answer_callback(callback_id, "Invalid post ID")
        return

    handoffs = load_json(HANDOFFS_FILE, {})
    slug     = find_slug_by_wp_post_id(handoffs, wp_post_id)
    if not slug:
        answer_callback(callback_id, "Article not found in handoffs")
        log(f"No slug found for wp_post_id={wp_post_id}")
        return

    title = handoffs[slug].get("article_title", slug)

    if action == "approve":
        ok = wp_publish(wp_post_id)
        if ok:
            handoffs[slug]["status"]         = "published"
            handoffs[slug]["published_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Update keyword_data status
            keyword_data = load_json(KEYWORD_FILE, {})
            if slug in keyword_data:
                keyword_data[slug]["status"] = "published"
                save_json(KEYWORD_FILE, keyword_data)

            save_json(HANDOFFS_FILE, handoffs)
            answer_callback(callback_id, "Published!")
            edit_message_text(chat_id, message_id, f"✅ PUBLISHED: {title}")
            log(f"Approved and published: {slug} (post {wp_post_id})")
        else:
            answer_callback(callback_id, "WordPress publish failed — check logs")
            log(f"Failed to publish post {wp_post_id} for slug: {slug}")

    elif action == "decline":
        handoffs[slug]["status"]       = "declined"
        handoffs[slug]["declined_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_json(HANDOFFS_FILE, handoffs)
        answer_callback(callback_id, "Declined — article stays as draft")
        edit_message_text(chat_id, message_id, f"❌ DECLINED: {title}")
        log(f"Declined: {slug} (post {wp_post_id}) — stays as WordPress draft")

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
