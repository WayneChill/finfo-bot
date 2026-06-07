from dotenv import load_dotenv
load_dotenv()
import os
import threading
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
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
# 工具：推播 / 回覆
# ===================================================

def push_text(text: str):
    """主動推播純文字（消耗額度）—— 只用於早報、巡邏通知等無 reply token 的場合。"""
    try:
        line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=text))
    except LineBotApiError as e:
        if e.status_code == 429:
            print(f"⚠️ LINE 推播月配額已用完，跳過通知：{text[:40]}…")
        else:
            raise


def _send(reply_token, messages):
    """有 reply_token 時用 reply_message（免費），否則 fallback 到 push_message。"""
    if not isinstance(messages, list):
        messages = [messages]
    msg = messages if len(messages) > 1 else messages[0]
    if reply_token:
        line_bot_api.reply_message(reply_token, msg)
    else:
        try:
            line_bot_api.push_message(LINE_USER_ID, msg)
        except LineBotApiError as e:
            if e.status_code == 429:
                print("⚠️ LINE 推播月配額已用完，跳過 fallback 通知")
            else:
                raise


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


FLEX_TEXT_LIMIT = 2000


def make_task_bubble(task: dict) -> dict:
    task_id = task["ID"]
    title = task.get("文章標題", "")
    post_url = task.get("文章URL", "")
    qa_raw = task.get("qa_content") or _extract_qa(task.get("草稿", ""))
    title_short = title[:40] + ("…" if len(title) > 40 else "")
    draft_preview = qa_raw[:FLEX_TEXT_LIMIT]

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
    pending_n = sum(1 for t in tasks if t.get("狀態") == sheets.STATUS_PENDING)
    failed_n  = sum(1 for t in tasks if t.get("狀態") == sheets.STATUS_FAILED)
    parts = []
    if pending_n:
        parts.append(f"待審核 {pending_n}")
    if failed_n:
        parts.append(f"失敗 {failed_n}")
    header_text = f"📋 任務總覽（{'、'.join(parts)}）"

    rows = []
    for i, task in enumerate(tasks):
        if i > 0:
            rows.append({"type": "separator"})
        task_id = task["ID"]
        title = task.get("文章標題", "")
        title_short = title[:20] + ("…" if len(title) > 20 else "")
        badge = "⚠️ " if task.get("狀態") == sheets.STATUS_FAILED else ""
        rows.append({
            "type": "box", "layout": "horizontal", "alignItems": "center",
            "contents": [
                {"type": "text", "text": f"{badge}#{task_id}　{title_short}",
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
                {"type": "text", "text": header_text,
                 "weight": "bold", "size": "md", "color": "#1A252F"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": rows
        }
    }


def push_task_card(task: dict, reply_token=None):
    qa_raw = task.get("qa_content") or _extract_qa(task.get("草稿", ""))
    bubble = make_task_bubble(task)
    messages = [FlexSendMessage(alt_text=f"任務 #{task['ID']} 請審核", contents=bubble)]
    if len(qa_raw) > FLEX_TEXT_LIMIT:
        messages.append(TextSendMessage(
            text=f"📄 完整草稿 #{task['ID']}：\n\n{qa_raw}"
        ))
    _send(reply_token, messages)


# ===================================================
# 保留舊介面（finfo_new.py 呼叫，改為靜默不推播）
# ===================================================

def push_review(task_id: str, post_title: str, post_url: str, draft: str):
    pass


# ===================================================
# 早報 & 查詢（早報用 push_message，查詢用 reply_message）
# ===================================================

def send_morning_report():
    """早報：系統主動推播，消耗額度（無 reply token）。"""
    pending = sheets.get_pending_tasks()
    if not pending:
        push_text("☀️ 早安！目前沒有待審核任務。")
        return
    push_text(f"☀️ 早安！目前有 {len(pending)} 筆待審核任務，輸入「進度」查看。")


def send_progress(reply_token=None):
    pending = sheets.get_pending_tasks()
    if not pending:
        _send(reply_token, TextSendMessage(text="目前沒有待審核任務 🎉"))
        return
    bubble = make_task_list_bubble(pending)
    _send(reply_token, FlexSendMessage(
        alt_text=f"📋 任務總覽（共 {len(pending)} 筆）", contents=bubble
    ))


def send_history(reply_token=None):
    done_tasks = sheets.get_recent_done_tasks(days=7)
    if not done_tasks:
        _send(reply_token, TextSendMessage(text="近 7 天沒有已處理的任務。"))
        return
    lines = [f"📊 近 7 天已處理（共 {len(done_tasks)} 筆）：\n"]
    for t in done_tasks:
        icon = "✅" if t["狀態"] == sheets.STATUS_DONE else "⏭️"
        title_short = t.get("文章標題", "")[:20]
        lines.append(f"{icon} #{t['ID']}  {title_short}  — {t['狀態']}")
    _send(reply_token, TextSendMessage(text="\n".join(lines)))


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


@app.route("/examples", methods=["POST"])
def create_example():
    data = request.get_json()
    missing = [f for f in ("category", "question_summary", "qa_content") if not data.get(f)]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400
    example_id = sheets.add_example(
        category=data["category"],
        question_summary=data["question_summary"],
        qa_content=data["qa_content"],
    )
    return jsonify({"example_id": example_id}), 201


@app.route("/examples", methods=["GET"])
def list_examples():
    return jsonify(sheets.get_examples())


@app.route("/line/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        import traceback
        print(f"❌ Webhook 處理錯誤：{e}")
        print(traceback.format_exc())
    return 'OK'


# ===================================================
# LINE 訊息處理
# ===================================================

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    rt = event.reply_token  # reply_token，免費使用

    if text == "進度":
        send_progress(rt)
    elif text == "歷史":
        send_history(rt)
    elif text.startswith("查看"):
        task_id = text.replace("查看", "").strip()
        task = sheets.get_task(task_id)
        if task:
            push_task_card(task, rt)
        else:
            _send(rt, TextSendMessage(text=f"❌ 找不到任務 {task_id}"))
    elif text.startswith("確認"):
        handle_approve(text.replace("確認", "").strip(), rt)
    elif text.startswith("修改"):
        parts = text.replace("修改", "").strip().split(" ", 1)
        handle_edit_request(parts[0], parts[1] if len(parts) > 1 else "", rt)
    elif text.startswith("略過"):
        handle_skip(text.replace("略過", "").strip(), rt)
    elif task_id := pending_edit.get(LINE_USER_ID):
        handle_edit_reply(task_id, text, rt)
    else:
        _send(rt, TextSendMessage(
            text="指令：\n進度 — 查看待審核任務\n歷史 — 近7天已完成\n確認{ID} / 修改{ID} {意見} / 略過{ID}"
        ))


@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    rt = event.reply_token  # reply_token，免費使用

    if data.startswith("confirm_"):
        handle_approve(data[8:], rt)
    elif data.startswith("edit_"):
        handle_edit_request(data[5:], "", rt)
    elif data.startswith("skip_"):
        handle_skip(data[5:], rt)
    elif data.startswith("view_"):
        task_id = data[5:]
        task = sheets.get_task(task_id)
        if task:
            push_task_card(task, rt)
        else:
            _send(rt, TextSendMessage(text=f"❌ 找不到任務 {task_id}"))


# ===================================================
# 任務動作
# ===================================================

def handle_approve(task_id: str, reply_token=None):
    task = sheets.get_task(task_id)
    if not task:
        _send(reply_token, TextSendMessage(text=f"❌ 找不到任務 {task_id}"))
        return
    sheets.update_status(task_id, sheets.STATUS_APPROVED)
    _send(reply_token, TextSendMessage(text=f"✅ 任務 {task_id} 已確認，Bot 即將編輯回覆..."))
    trigger_edit(task_id)


def handle_edit_request(task_id: str, instruction: str, reply_token=None):
    task = sheets.get_task(task_id)
    if not task:
        _send(reply_token, TextSendMessage(text=f"❌ 找不到任務 {task_id}"))
        return
    sheets.update_status(task_id, sheets.STATUS_EDITING)
    pending_edit[LINE_USER_ID] = task_id
    if instruction:
        # 先 reply 告知修改中（免費），結果再 push（消耗 1 則，因 reply token 已用完）
        _send(reply_token, TextSendMessage(text="✏️ 正在根據你的意見修改草稿..."))
        new_qa = claude_helper.revise_draft(
            original_draft=task["草稿"],
            instruction=instruction,
            post_title=task["文章標題"]
        )
        new_full = claude_helper.REPLY_TEMPLATE.format(qa_content=new_qa)
        sheets.update_draft(task_id, new_full)
        sheets.update_status(task_id, sheets.STATUS_PENDING)
        pending_edit.pop(LINE_USER_ID, None)
        push_text(f"✏️ 修改後草稿：\n━━━━━━━━━━━━━━\n{new_qa}\n━━━━━━━━━━━━━━\n確認{task_id} ／ 修改{task_id} [繼續修改]")
    else:
        _send(reply_token, TextSendMessage(text=f"請說明要怎麼修改（任務 {task_id}）："))


def handle_edit_reply(task_id: str, instruction: str, reply_token=None):
    task = sheets.get_task(task_id)
    if not task:
        pending_edit.pop(LINE_USER_ID, None)
        return
    # 先 reply 告知修改中（免費），結果再 push（消耗 1 則）
    _send(reply_token, TextSendMessage(text="✏️ 修改中..."))
    new_qa = claude_helper.revise_draft(
        original_draft=task["草稿"],
        instruction=instruction,
        post_title=task["文章標題"]
    )
    new_full = claude_helper.REPLY_TEMPLATE.format(qa_content=new_qa)
    sheets.update_draft(task_id, new_full)
    sheets.update_status(task_id, sheets.STATUS_PENDING)
    pending_edit.pop(LINE_USER_ID, None)
    push_text(f"✏️ 修改後草稿：\n━━━━━━━━━━━━━━\n{new_qa}\n━━━━━━━━━━━━━━\n確認{task_id} ／ 修改{task_id} [繼續修改]")


def handle_skip(task_id: str, reply_token=None):
    sheets.update_status(task_id, sheets.STATUS_REJECTED)
    _send(reply_token, TextSendMessage(text=f"⏭️ 任務 {task_id} 已略過。"))


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
