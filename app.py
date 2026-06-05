from dotenv import load_dotenv
load_dotenv()
import os
import threading
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FlexSendMessage, PostbackEvent
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

import sheets
import claude_helper

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

pending_edit = {}


# ===================================================
# 工具：推播純文字
# ===================================================

def push_text(text: str):
    line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=text))


# ===================================================
# Flex 卡片組裝
# ===================================================

def _extract_qa(full_reply: str) -> str:
    """從完整回覆模板中抽出 Q&A 區塊內容（用於舊資料 fallback）。"""
    sep = "━━━━━━━━━━━━━━━━━━"
    marker = "❓問與答 Q&A"
    try:
        idx = full_reply.index(marker)
        after = full_reply[idx + len(marker):]
        i1 = after.index(sep)
        body = after[i1 + len(sep):].lstrip("\n")
        i2 = body.index(sep)
        return body[:i2].strip()
    except ValueError:
        return full_reply


def make_task_bubble(task: dict) -> dict:
    task_id = task["ID"]
    title = task.get("文章標題", "")
    post_url = task.get("文章URL", "")
    qa_raw = task.get("qa_content") or _extract_qa(task.get("草稿", ""))
    title_short = title[:40] + ("…" if len(title) > 40 else "")
    draft_preview = qa_raw[:300] + ("…" if len(qa_raw) > 300 else "")

    return {
        "type": "bubble",
        "size": "giga",
        "styles": {
            "header": {"backgroundColor": "#EBF5FB"},
            "body":   {"backgroundColor": "#FDFEFE"},
            "footer": {"backgroundColor": "#F4F6F7"}
        },
        "header": {
            "type": "box", "layout": "vertical",
            "contents": [
                {"type": "text", "text": "📌 待審核任務",
                 "size": "xs", "color": "#2E86C1", "weight": "bold"},
                {"type": "text", "text": f"任務 #{task_id}",
                 "size": "xl", "weight": "bold", "color": "#1A252F"},
                {"type": "text", "text": title_short,
                 "size": "sm", "wrap": True, "color": "#555555", "margin": "sm"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "link", "height": "sm",
                 "action": {"type": "uri", "label": "🔗 查看原文章", "uri": post_url}},
                {"type": "separator"},
                {"type": "text", "text": "💬 AI 草稿：",
                 "size": "xs", "color": "#2E86C1", "weight": "bold", "margin": "md"},
                {"type": "text", "text": draft_preview,
                 "size": "sm", "wrap": True, "color": "#2C3E50", "margin": "sm"}
            ]
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "color": "#27AE60",
                 "action": {"type": "postback", "label": "✅  確認送出",
                            "data": f"confirm_{task_id}", "displayText": f"確認{task_id}"}},
                {"type": "button", "style": "primary", "color": "#2E86C1",
                 "action": {"type": "postback", "label": "✏️  修改草稿",
                            "data": f"edit_{task_id}", "displayText": f"修改{task_id}"}},
                {"type": "button", "style": "secondary",
                 "action": {"type": "postback", "label": "⏭️  略過此篇",
                            "data": f"skip_{task_id}", "displayText": f"略過{task_id}"}}
            ]
        }
    }


def make_task_list_bubble(tasks: list) -> dict:
    rows = []
    for i, task in enumerate(tasks):
        if i > 0:
            rows.append({"type": "separator"})
        task_id = task["ID"]
        title = task.get("文章標題", "")
        title_short = title[:22] + ("…" if len(title) > 22 else "")
        rows.append({
            "type": "box", "layout": "horizontal", "alignItems": "center",
            "contents": [
                {"type": "text", "text": f"• #{task_id}　{title_short}",
                 "flex": 5, "wrap": True, "size": "sm", "color": "#2C3E50"},
                {"type": "button", "style": "link", "height": "sm", "flex": 1,
                 "action": {"type": "postback", "label": "查看",
                            "data": f"view_{task_id}", "displayText": f"查看{task_id}"}}
            ]
        })
    return {
        "type": "bubble",
        "size": "giga",
        "styles": {
            "header": {"backgroundColor": "#EBF5FB"},
            "body":   {"backgroundColor": "#FDFEFE"}
        },
        "header": {
            "type": "box", "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"📋 待審核任務（共 {len(tasks)} 筆）",
                 "weight": "bold", "size": "md", "color": "#1A252F"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": rows
        }
    }


def push_task_card(task: dict):
    bubble = make_task_bubble(task)
    line_bot_api.push_message(
        LINE_USER_ID,
        FlexSendMessage(alt_text=f"任務 #{task['ID']} 請審核", contents=bubble)
    )


# ===================================================
# 保留舊介面（finfo_new.py 呼叫，改為靜默不推播）
# ===================================================

def push_review(task_id: str, post_title: str, post_url: str, draft: str):
    pass


# ===================================================
# 早報 & 查詢
# ===================================================

def send_morning_report():
    pending = sheets.get_pending_tasks()
    if not pending:
        push_text("☀️ 早安！目前沒有待審核任務。")
        return

    push_text(f"☀️ 早安！目前共有 {len(pending)} 筆待審核任務：")
    for task in pending:
        push_task_card(task)


def send_progress():
    pending = sheets.get_pending_tasks()
    if not pending:
        push_text("目前沒有待審核任務 🎉")
        return
    bubble = make_task_list_bubble(pending)
    line_bot_api.push_message(
        LINE_USER_ID,
        FlexSendMessage(alt_text=f"📋 待審核任務（共 {len(pending)} 筆）", contents=bubble)
    )


def send_history():
    done_tasks = sheets.get_recent_done_tasks(days=7)
    if not done_tasks:
        push_text("近 7 天沒有已處理的任務。")
        return
    lines = [f"📊 近 7 天已處理（共 {len(done_tasks)} 筆）：\n"]
    for t in done_tasks:
        icon = "✅" if t["狀態"] == sheets.STATUS_DONE else "⏭️"
        title_short = t.get("文章標題", "")[:20]
        lines.append(f"{icon} #{t['ID']}  {title_short}  — {t['狀態']}")
    push_text("\n".join(lines))


# ===================================================
# APScheduler：每天 08:00 發早報
# ===================================================

_tz = pytz.timezone("Asia/Taipei")
scheduler = BackgroundScheduler(timezone=_tz)
scheduler.add_job(send_morning_report, CronTrigger(hour=8, minute=0, timezone=_tz))
scheduler.start()


# ===================================================
# Flask 路由
# ===================================================

@app.route("/tasks", methods=["POST"])
def create_task():
    data = request.get_json()
    try:
        task_id = sheets.add_task(
            post_url=data["post_url"],
            post_title=data["post_title"],
            comment_id=data["comment_id"],
            draft=data["draft"],
            qa_content=data.get("qa_content", ""),
            full_reply=data.get("full_reply", ""),
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"task_id": task_id}), 201


@app.route("/tasks/approved", methods=["GET"])
def get_approved_tasks():
    return jsonify(sheets.get_approved_tasks())


@app.route("/tasks/all", methods=["GET"])
def get_all_tasks():
    with sheets._get_conn() as conn:
        rows = conn.execute(
            "SELECT ID, 文章URL, 回覆ID, 狀態, 建立時間 FROM tasks ORDER BY 建立時間 DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/tasks/<task_id>/done", methods=["POST"])
def mark_task_done(task_id):
    sheets.update_status(task_id, sheets.STATUS_DONE)
    return jsonify({"ok": True})


@app.route("/tasks/<task_id>/fail", methods=["POST"])
def mark_task_fail(task_id):
    sheets.update_status(task_id, sheets.STATUS_FAILED)
    return jsonify({"ok": True})


@app.route("/tasks/<task_id>/reset", methods=["POST"])
def reset_task(task_id):
    sheets.update_status(task_id, sheets.STATUS_APPROVED)
    return jsonify({"ok": True, "task_id": task_id, "status": sheets.STATUS_APPROVED})


@app.route("/tasks/<task_id>/update_comment_id", methods=["POST"])
def update_comment_id(task_id):
    data = request.get_json()
    new_comment_id = data.get("comment_id")
    if not new_comment_id:
        return jsonify({"error": "comment_id required"}), 400
    with sheets._get_conn() as conn:
        conn.execute("UPDATE tasks SET 回覆ID = ? WHERE ID = ?", (new_comment_id, task_id))
    return jsonify({"ok": True, "task_id": task_id, "comment_id": new_comment_id})


@app.route("/line/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


# ===================================================
# LINE 訊息處理
# ===================================================

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()

    if text == "進度":
        send_progress()
    elif text == "歷史":
        send_history()
    elif text.startswith("查看"):
        task_id = text.replace("查看", "").strip()
        task = sheets.get_task(task_id)
        if task:
            push_task_card(task)
        else:
            push_text(f"❌ 找不到任務 {task_id}")
    elif text.startswith("確認"):
        handle_approve(text.replace("確認", "").strip())
    elif text.startswith("修改"):
        parts = text.replace("修改", "").strip().split(" ", 1)
        handle_edit_request(parts[0], parts[1] if len(parts) > 1 else "")
    elif text.startswith("略過"):
        handle_skip(text.replace("略過", "").strip())
    elif task_id := pending_edit.get(LINE_USER_ID):
        handle_edit_reply(task_id, text)
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="指令：\n進度 — 查看待審核任務\n歷史 — 近7天已完成\n確認{ID} / 修改{ID} {意見} / 略過{ID}")
        )


@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    if data.startswith("confirm_"):
        handle_approve(data[8:])
    elif data.startswith("edit_"):
        handle_edit_request(data[5:], "")
    elif data.startswith("skip_"):
        handle_skip(data[5:])
    elif data.startswith("view_"):
        task_id = data[5:]
        task = sheets.get_task(task_id)
        if task:
            push_task_card(task)
        else:
            push_text(f"❌ 找不到任務 {task_id}")


# ===================================================
# 任務動作
# ===================================================

def handle_approve(task_id: str):
    task = sheets.get_task(task_id)
    if not task:
        push_text(f"❌ 找不到任務 {task_id}")
        return
    sheets.update_status(task_id, sheets.STATUS_APPROVED)
    push_text(f"✅ 任務 {task_id} 已確認，Bot 即將編輯回覆...")
    trigger_edit(task_id)


def handle_edit_request(task_id: str, instruction: str):
    task = sheets.get_task(task_id)
    if not task:
        push_text(f"❌ 找不到任務 {task_id}")
        return
    sheets.update_status(task_id, sheets.STATUS_EDITING)
    pending_edit[LINE_USER_ID] = task_id
    if instruction:
        push_text("✏️ 正在根據你的意見修改草稿...")
        new_draft = claude_helper.revise_draft(
            original_draft=task["草稿"],
            instruction=instruction,
            post_title=task["文章標題"]
        )
        sheets.update_draft(task_id, new_draft)
        sheets.update_status(task_id, sheets.STATUS_PENDING)
        pending_edit.pop(LINE_USER_ID, None)
        push_text(f"✏️ 修改後草稿：\n━━━━━━━━━━━━━━\n{new_draft}\n━━━━━━━━━━━━━━\n確認{task_id} ／ 修改{task_id} [繼續修改]")
    else:
        push_text(f"請說明要怎麼修改（任務 {task_id}）：")


def handle_edit_reply(task_id: str, instruction: str):
    task = sheets.get_task(task_id)
    if not task:
        pending_edit.pop(LINE_USER_ID, None)
        return
    push_text("✏️ 修改中...")
    new_draft = claude_helper.revise_draft(
        original_draft=task["草稿"],
        instruction=instruction,
        post_title=task["文章標題"]
    )
    sheets.update_draft(task_id, new_draft)
    sheets.update_status(task_id, sheets.STATUS_PENDING)
    pending_edit.pop(LINE_USER_ID, None)
    push_text(f"✏️ 修改後草稿：\n━━━━━━━━━━━━━━\n{new_draft}\n━━━━━━━━━━━━━━\n確認{task_id} ／ 修改{task_id} [繼續修改]")


def handle_skip(task_id: str):
    sheets.update_status(task_id, sheets.STATUS_REJECTED)
    push_text(f"⏭️ 任務 {task_id} 已略過。")


# ===================================================
# 編輯 queue（finfo_new.py 輪詢用）
# ===================================================

edit_queue = []

def trigger_edit(task_id: str):
    edit_queue.append(task_id)

def get_edit_queue():
    return edit_queue

def clear_edit_task(task_id: str):
    if task_id in edit_queue:
        edit_queue.remove(task_id)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
