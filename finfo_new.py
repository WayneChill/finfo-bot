from dotenv import load_dotenv
load_dotenv()
import time
import random
import threading
import pyperclip
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import sheets
import claude_helper
import editor
import app

# ===================================================
# 【設定區】
# ===================================================

KEYWORDS = [
    '問', '保險', '單', '業務', '缺口', '推薦', '建議',
    '新生兒', '規劃', '健檢', '補強', '檢視', '醫療',
    '實支', '癌症', '重大傷病', '壽險', '失能', '理賠'
]

# 佔位文字（搶位用，之後會被替換）
PLACEHOLDER_OPTIONS = [
    "這個問題我來回答，整理一下～",
    "有遇過類似狀況，稍後分享一下",
    "好問題，我來說說我的看法",
    "這塊我比較熟，稍後補充",
]

PATROL_INTERVAL_MIN = 15
PATROL_INTERVAL_MAX = 25
MAX_PROCESSED_CACHE = 500

# ===================================================


def get_placeholder():
    """隨機取一個佔位文字"""
    import random
    return random.choice(PLACEHOLDER_OPTIONS)


def post_placeholder(driver, post_url: str) -> str | None:
    """
    在文章頁送出佔位文字，回傳回覆 ID
    Returns: comment_id (str) 或 None（失敗）
    """
    try:
        driver.get(post_url)
        time.sleep(3.5)

        wait = WebDriverWait(driver, 6)
        trigger = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(), '回應...')]")
        ))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", trigger)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", trigger)

        actions = ActionChains(driver)
        time.sleep(1)

        placeholder_text = get_placeholder()
        pyperclip.copy(placeholder_text)
        actions.send_keys(Keys.TAB).perform()
        time.sleep(0.3)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

        time.sleep(1.2)
        actions.send_keys(Keys.TAB).send_keys(Keys.TAB).send_keys(Keys.TAB).perform()
        time.sleep(0.5)
        actions.send_keys(Keys.ENTER).perform()
        
        print(f"✅ 佔位送出：{placeholder_text}")
        time.sleep(2.5)  # 等頁面更新

        # 抓剛送出的回覆 ID
        comment_id = get_latest_own_comment_id(driver)
        return comment_id

    except Exception as e:
        print(f"❌ 佔位送出失敗：{e}")
        return None


def get_latest_own_comment_id(driver) -> str | None:
    """
    從頁面找到最新的自己的回覆 ID
    找 data-comment-id 中有 operation-menu-link 的區塊（代表是自己的回覆）
    """
    try:
        # 找所有有 operation-dropdown 的 comment 區塊（只有自己的回覆才有編輯選單）
        elements = driver.find_elements(
            By.CSS_SELECTOR,
            "div[data-comment-id] .operation-dropdown"
        )
        if elements:
            # 最後一個通常是最新的
            last = elements[-1]
            parent = last.find_element(
                By.XPATH,
                "ancestor::div[@data-comment-id]"
            )
            comment_id = parent.get_attribute("data-comment-id")
            print(f"🆔 取得回覆 ID：{comment_id}")
            return comment_id
    except Exception as e:
        print(f"⚠️ 無法取得回覆 ID：{e}")
    return None


def get_post_content(driver, post_url: str) -> str:
    """嘗試取得文章內文（給 Claude 更多上下文）"""
    try:
        # driver 已在文章頁，直接取
        content_el = driver.find_element(By.CSS_SELECTOR, ".post-content, .question-content, h1")
        return content_el.text[:500]
    except:
        return ""


def process_edit_queue(driver):
    """處理 LINE 確認後的編輯 queue"""
    queue = app.get_edit_queue()
    if not queue:
        return
    
    for task_id in list(queue):
        task = sheets.get_task(task_id)
        if not task:
            app.clear_edit_task(task_id)
            continue
        
        print(f"✏️ 執行編輯任務：{task_id}")
        success = editor.edit_comment(
            driver=driver,
            post_url=task["文章URL"],
            comment_id=task["回覆ID"],
            new_content=task["草稿"]
        )
        
        if success:
            sheets.update_status(task_id, sheets.STATUS_DONE)
            app.push_text(f"✅ 任務 {task_id} 編輯完成！")
        else:
            app.push_text(f"❌ 任務 {task_id} 編輯失敗，請手動處理。\n{task['文章URL']}")
        
        app.clear_edit_task(task_id)


def start_line_webhook():
    """在背景執行 LINE webhook server"""
    from app import app as flask_app
    flask_app.run(port=5001, debug=False, use_reloader=False)


def run_finfo_bot():
    print("⚡ 啟動『保險一二三』智慧版（佔位 + LINE 審核）...")
    
    # 背景啟動 LINE webhook
    webhook_thread = threading.Thread(target=start_line_webhook, daemon=True)
    webhook_thread.start()
    print("📱 LINE Webhook 已在背景啟動（port 5001）")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.maximize_window()

    driver.get("https://finfo.tw/users/sign_in")
    print("⚠️ 請完成登入，確認留在列表頁後按 Enter 繼續...")
    input()

    processed_posts = []

    while True:
        try:
            # ① 先處理編輯 queue
            process_edit_queue(driver)

            print(f"\n--- 🕒 巡邏開始：{time.strftime('%H:%M:%S')} ---")
            driver.get("https://finfo.tw/posts?sort=created_at")
            time.sleep(3)

            all_links = driver.find_elements(By.TAG_NAME, "a")
            print(f"🔗 找到連結數：{len(all_links)}")

            latest_post = None
            for link_el in all_links:
                href = link_el.get_attribute('href') or ""
                text = link_el.text.strip()
                if "/posts/" in href and any(c.isdigit() for c in href) and len(text) > 2:
                    clean_href = href.split('#')[0]
                    latest_post = (text, clean_href)
                    break

            print(f"📄 最新文章：{latest_post}")

            if latest_post:
                title, link = latest_post

                if link in processed_posts:
                    print(f"⏭️ 已處理過，略過：{title}")
                else:
                    processed_posts.append(link)

                    if any(kw in title for kw in KEYWORDS):
                        print(f"🎯 鎖定：{title}，準備佔位！")

                        # ② 送出佔位
                        comment_id = post_placeholder(driver, link)

                        if comment_id:
                            # ③ 取得文章內容（給 Claude）
                            post_content = get_post_content(driver, link)

                            # ④ Claude 生成草稿
                            print("🤖 Claude 生成草稿中...")
                            draft = claude_helper.generate_draft(title, post_content)
                            print(f"📝 草稿：{draft[:80]}...")

                            # ⑤ 存到 Sheets
                            task_id = sheets.add_task(
                                post_url=link,
                                post_title=title,
                                comment_id=comment_id,
                                draft=draft
                            )
                            print(f"📊 任務已存入 Sheets：{task_id}")

                            # ⑥ LINE 推播審核
                            app.push_review(task_id, title, link, draft)
                            print(f"📱 LINE 推播完成")

                        else:
                            print("⚠️ 未取得回覆 ID，跳過此篇")
                    else:
                        print(f"😐 無關鍵字，略過：{title}")

            if len(processed_posts) > MAX_PROCESSED_CACHE:
                processed_posts = processed_posts[-MAX_PROCESSED_CACHE:]

            wait_time = random.randint(PATROL_INTERVAL_MIN, PATROL_INTERVAL_MAX)
            print(f"😴 休息 {wait_time} 秒...")
            time.sleep(wait_time)

        except Exception as e:
            print(f"⚠️ 主迴圈異常：{e}，等待 10 秒重試...")
            time.sleep(10)


if __name__ == "__main__":
    run_finfo_bot()
    input()
