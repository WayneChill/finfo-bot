from dotenv import load_dotenv
load_dotenv()
import os
import json
import threading
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, PostbackAction,
    PostbackEvent, QuickReply, QuickReplyButton, MessageAction
)

import sheets
import claude_helper

# ===================================================
# LINE Bot Webhook
# 整合到現有 Flask app，或獨立跑
# ===================================================

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_USER_ID = os.environ.get("LINE_USER_ID")  # 你自己的 LINE user ID

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

# 暫存「修改中」的 task_id（per user session）
pending_edit = {}


# ===================================================
# 推播函式（給 finfo.py 呼叫）
# ===================================================

def push_review(task_id: str, post_title: str, post_url: str, draft: str):
    """推播草稿給你審核"""
    message = f"""📌 新文章待審核
━━━━━━━━━━━━━━
🆔 任務ID：{task_id}
📄 標題：{post_title}
🔗 {post_url}
━━━━━━━━━━━━━━
💬 草稿內容：

{draft}
━━━━━━━━━━━━━━
回覆以下指令：
✅ 確認{task_id}
✏️ 修改{task_id} [你的修改意見]
⏭️ 略過{task_id}"""

    line_bot_api.push_message(
        LINE_USER_ID,
        TextSendMessage(text=message)
    )


def push_text(text: str):
    """推播純文字"""
    line_bot_api.push_message(
        LINE_USER_ID,
        TextSendMessage(text=text)
    )


# ===================================================
# Webhook 處理
# ===================================================

@app.route("/line/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    
    # ✅ 確認{task_id}
    if text.startswith("確認"):
        task_id = text.replace("確認", "").strip()
        handle_approve(task_id)

    # ✏️ 修改{task_id} {修改意見}
    elif text.startswith("修改"):
        parts = text.replace("修改", "").strip().split(" ", 1)
        task_id = parts[0]
        instruction = parts[1] if len(parts) > 1 else ""
        handle_edit_request(task_id, instruction)

    # ⏭️ 略過{task_id}
    elif text.startswith("略過"):
        task_id = text.replace("略過", "").strip()
        handle_skip(task_id)

    # 處理修改中的對話
    elif task_id := pending_edit.get(LINE_USER_ID):
        handle_edit_reply(task_id, text)

    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="指令格式：\n確認{ID}\n修改{ID} {意見}\n略過{ID}")
        )


def handle_approve(task_id: str):
    """確認送出"""
    task = sheets.get_task(task_id)
    if not task:
        push_text(f"❌ 找不到任務 {task_id}")
        return
    
    sheets.update_status(task_id, sheets.STATUS_APPROVED)
    push_text(f"✅ 任務 {task_id} 已確認，Bot 即將編輯回覆...")
    
    # 通知 finfo.py 執行編輯（用 flag 或 queue）
    trigger_edit(task_id)


def handle_edit_request(task_id: str, instruction: str):
    """修改草稿"""
    task = sheets.get_task(task_id)
    if not task:
        push_text(f"❌ 找不到任務 {task_id}")
        return
    
    sheets.update_status(task_id, sheets.STATUS_EDITING)
    pending_edit[LINE_USER_ID] = task_id
    
    if instruction:
        # 有修改意見，直接重新生成
        push_text(f"✏️ 正在根據你的意見修改草稿...")
        new_draft = claude_helper.revise_draft(
            original_draft=task["草稿"],
            instruction=instruction,
            post_title=task["文章標題"]
        )
        sheets.update_draft(task_id, new_draft)
        sheets.update_status(task_id, sheets.STATUS_PENDING)
        pending_edit.pop(LINE_USER_ID, None)
        
        push_text(f"""✏️ 修改後草稿：
━━━━━━━━━━━━━━
{new_draft}
━━━━━━━━━━━━━━
確認{task_id} ／ 修改{task_id} [繼續修改]""")
    else:
        push_text(f"請說明要怎麼修改（任務 {task_id}）：")


def handle_edit_reply(task_id: str, instruction: str):
    """修改中的對話回覆"""
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
    
    push_text(f"""✏️ 修改後草稿：
━━━━━━━━━━━━━━
{new_draft}
━━━━━━━━━━━━━━
確認{task_id} ／ 修改{task_id} [繼續修改]""")


def handle_skip(task_id: str):
    """略過（佔位保留）"""
    sheets.update_status(task_id, sheets.STATUS_REJECTED)
    push_text(f"⏭️ 任務 {task_id} 已略過，佔位文字保留在 Finfo。")


# ===================================================
# 編輯 trigger（放到 queue 讓 finfo.py 主迴圈處理）
# ===================================================

edit_queue = []

def trigger_edit(task_id: str):
    """把任務丟進編輯 queue"""
    edit_queue.append(task_id)


def get_edit_queue():
    return edit_queue


def clear_edit_task(task_id: str):
    if task_id in edit_queue:
        edit_queue.remove(task_id)


if __name__ == "__main__":
    app.run(port=5001, debug=False)
