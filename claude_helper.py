from dotenv import load_dotenv
load_dotenv()
import os
import requests
import sheets

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """你是「保險一二三⚡規劃好簡單」的業務助理，專門針對 Finfo 討論區的提問撰寫「問與答 Q&A」區塊的內容。

注意：你只需要生成問與答的回答內容，不要生成整個回覆框架，框架由程式負責組合。

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
- 只輸出問與答內容本身，不要加框架、分隔線、標題

回覆風格要求：
- 像真人業務在說話，不要像 AI 寫的文章
- 不要用過多 ** 粗體標記
- 不要條列太多層，保持自然口語
- 不要用「首先」「其次」「總結」等公式化開頭
- 語氣要像在跟朋友解釋，直接、實在、有溫度
- 可以用台灣人日常說話的方式，不需要太正式
- 避免過度使用專業術語堆砌，用白話解釋"""

REPLY_TEMPLATE = """📌 保險一二三⚡規劃好簡單 — 夫妻雙業務・全台服務


━━━━━━━━━━━━━━━━━━


👫 為什麼選擇我們?


━━━━━━━━━━━━━━━━━━


✦ 雙業務制度｜夫妻聯手服務,溝通效率翻倍,不怕找不到人

✦ 十年實戰經驗｜累積服務 900+ 客戶,經手上千件規劃案

✦ 客觀不推銷｜佛系成交,讓保險回歸需求本質

✦ 全台線上服務｜以網路平台為主,不受地域限制

✦ 完整服務流程｜健檢→規劃→送件→理賠協助,一條龍服務


━━━━━━━━━━━━━━━━━━


❓問與答 Q&A


━━━━━━━━━━━━━━━━━━


{qa_content}


━━━━━━━━━━━━━━━━━━


🔍 規劃核心理念


━━━━━━━━━━━━━━━━━━


「用最低預算,換取最大保障」


根據 900+ 客戶的規劃經驗,我們歸納出 5 大必備保障:


【保障金字塔結構】


🏥 第一層:醫療基礎(必備)

✦ 實支實付 + 住院日額

  ├─ 實支實付:解決健保不給付的高額自費

  │  • 達文西手術、標靶藥物、鈦合金醫材

  │  • 依收據限額理賠,補足健保缺口

  └─ 住院日額:彈性補貼

     • 薪資中斷、看護費、交通往返、院外藥材


🎯 第二層:重大風險一次金(高 CP 值)

✦ 重大傷病一次金(涵蓋 300+ 項疾病)

  • 取得「重大傷病卡」即理賠,不一定要住院

  • 理賠範圍廣,爭議少,金額彈性運用


💊 第三層:癌症專屬保障

✦ 癌症一次金

  • 確診即給付,無需蒐集單據

  • 因應標靶、免疫療法等高額自費趨勢

  • 一筆金自由運用,讓治療選擇更靈活


🚑 第四層:日常防護

✦ 意外醫療(最高 CP 值)

  • 骨折、縫合、門診手術都理賠

  • 補足非住院型治療開銷

  • 彌補健保與實支實付的不足


👨‍👩‍👧‍👦 第五層:家庭責任(經濟支柱必備)

✦ 壽險/失能長照

  • 保障家庭日常開支,避免經濟斷鏈

  • 萬一發生事故或需長期照護,家人生活無虞

  • 留愛不留債


━━━━━━━━━━━━━━━━━━


🩺 投保前健康狀況確認


━━━━━━━━━━━━━━━━━━


為提升核保效率、減少補件往返,請協助確認:

1️⃣ 目前身體狀況:有無不適或正在治療?

2️⃣ 五年就醫紀錄:有無慢性病或住院紀錄?

3️⃣ 近期就醫情形:兩個月內是否有看診/領藥?

4️⃣ 身心科紀錄:有無精神科/身心科用藥?

5️⃣ BMI 檢視:是否在 18.5~24 正常範圍?


💡 若不確定,可直接提供身高/體重,我來協助評估


━━━━━━━━━━━━━━━━━━


🛠️ 我們的服務優勢


━━━━━━━━━━━━━━━━━━


✓ 深度保單健檢｜像幫保單照 X 光,揪出條款陷阱與重複浪費

✓ 專屬管理系統｜免費提供線上帳號,一眼看懂所有保單

✓ 核保實戰經驗｜月處理百件案件,最懂核保眉角與送件策略

✓ 理賠協助服務｜不只規劃,更陪您走完理賠流程

✓ 歡迎同業交流｜資源共享,對接合作


━━━━━━━━━━━━━━━━━━


💬 開始規劃三步驟


━━━━━━━━━━━━━━━━━━


Step 1｜提供基本資料:年齡 + 性別 + 預算

Step 2｜舊保單免費健檢(可選)

Step 3｜收到專屬規劃建議書


📩 立即點擊我的頭像聯絡


━━━━━━━━━━━━━━━━━━


保險一二三⚡規劃好簡單

👫 夫妻雙業務 | 🏅 10 年資歷 | 🤝 900+ 客戶見證


━━━━━━━━━━━━━━━━━━"""


def generate_draft(post_title: str, post_content: str = "") -> tuple[str, str]:
    user_prompt = f"請針對以下 Finfo 討論區的提問，撰寫問與答 Q&A 區塊的回答內容：\n\n標題：{post_title}"
    if post_content:
        user_prompt += f"\n\n內容：{post_content[:500]}"

    examples = sheets.find_similar_examples(post_title)
    if examples:
        user_prompt += "\n\n以下是類似問題的過去回覆範例，請參考語氣與格式，但不要照抄內容：\n"
        for i, ex in enumerate(examples, 1):
            user_prompt += (
                f"\n【範例{i}】類型：{ex['category']}\n"
                f"問題：{ex['question_summary']}\n"
                f"回覆：\n{ex['qa_content']}\n"
            )

    qa_content = _call_api(user_prompt)
    full_reply = REPLY_TEMPLATE.format(qa_content=qa_content)
    return qa_content, full_reply


def revise_draft(original_draft: str, instruction: str, post_title: str) -> str:
    user_prompt = f"""原文章標題：{post_title}

原始草稿：
{original_draft}

修改意見：{instruction}

請根據修改意見重新撰寫回覆，保留原本的良好部分，針對意見做調整。"""

    return _call_api(user_prompt)


def _call_api(user_prompt: str) -> str:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-haiku-4-5-20251001",
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
        return "（草稿生成失敗，請手動編輯）"
