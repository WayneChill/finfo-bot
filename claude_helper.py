from dotenv import load_dotenv
load_dotenv()
import os
import requests

# ===================================================
# Claude API 呼叫
# ===================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """你是「保險一二三⚡規劃好簡單」的業務助理，協助撰寫 Finfo 討論區的回覆。

回覆原則：
1. 親切、專業、不過度推銷
2. 先回應提問者的具體問題或情況
3. 提供有價值的保險知識或方向
4. 結尾自然帶出可以進一步諮詢
5. 字數控制在 150-300 字
6. 不使用「保單健檢」「投資建議」「理財規劃」「報酬率」「保證獲利」等禁用詞
7. 不直接推薦特定商品名稱
8. 語氣真實自然，像人在回答，不像機器人

格式：
- 不要用過多 emoji
- 可以條列但不要太多層
- 結尾可以邀請私訊或點頭像聯繫"""


def generate_draft(post_title: str, post_content: str = "") -> str:
    """
    根據文章標題（和內容）生成回覆草稿
    
    Args:
        post_title: 文章標題
        post_content: 文章內容（可選）
    
    Returns:
        草稿文字
    """
    user_prompt = f"請針對以下 Finfo 討論區的提問，撰寫一篇回覆草稿：\n\n標題：{post_title}"
    if post_content:
        user_prompt += f"\n\n內容：{post_content[:500]}"  # 最多 500 字
    
    return _call_api(user_prompt)


def revise_draft(original_draft: str, instruction: str, post_title: str) -> str:
    """
    根據修改意見重新生成草稿
    
    Args:
        original_draft: 原始草稿
        instruction: 修改意見
        post_title: 原文章標題
    
    Returns:
        修改後的草稿
    """
    user_prompt = f"""原文章標題：{post_title}

原始草稿：
{original_draft}

修改意見：{instruction}

請根據修改意見重新撰寫回覆，保留原本的良好部分，針對意見做調整。"""
    
    return _call_api(user_prompt)


def _call_api(user_prompt: str) -> str:
    """呼叫 Claude API"""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": user_prompt}
        ]
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"❌ Claude API 呼叫失敗：{e}")
        return f"（草稿生成失敗，請手動編輯）"
