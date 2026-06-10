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

import requests as http
import claude_helper
import editor
import app

RAILWAY_API = "https://finfo-bot-production.up.railway.app"

# ===================================================
# 【設定區】
# ===================================================

KEYWORDS = [
    '問', '保險', '單', '業務', '缺口', '推薦', '建議',
    '新生兒', '規劃', '健檢', '補強', '檢視', '醫療',
    '實支', '癌症', '重大傷病', '壽險', '失能', '理賠'
]

PLACEHOLDER = """📌 保險一二三⚡規劃好簡單 — 夫妻雙業務・全台服務

━━━━━━━━━━━━━━━━━━
👫 為什麼選擇我們?
━━━━━━━━━━━━━━━━━━

✦ 雙業務制度｜夫妻聯手服務,溝通效率翻倍,不怕找不到人
✦ 十年實戰經驗｜累積服務 900+ 客戶,經手上千件規劃案
✦ 客觀不推銷｜佛系成交,讓保險回歸需求本質
✦ 全台線上服務｜以網路平台為主,不受地域限制
✦ 完整服務流程｜健檢→規劃→送件→理賠協助,一條龍服務

━━━━━━━━━━━━━━━━━━
❓編輯回答中，請耐心等候喔
━━━━━━━━━━━━━━━━━━

如果比較急的話，也可以點頭像來詢問喔"""

PATROL_INTERVAL_MIN = 15
PATROL_INTERVAL_MAX = 25
MAX_PROCESSED_CACHE = 500

# ===================================================


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

        placeholder_text = PLACEHOLDER
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
    """從頁面找到最新回覆的 data-comment-id"""
    try:
        elements = driver.find_elements(
            By.CSS_SELECTOR,
            "div.comment-content[data-comment-id]"
        )
        if elements:
            comment_id = elements[-1].get_attribute("data-comment-id")
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
    """向 Railway 取得已確認任務並執行編輯"""
    try:
        resp = http.get(f"{RAILWAY_API}/tasks/approved", timeout=10)
        resp.raise_for_status()
        tasks = resp.json()
    except Exception as e:
        print(f"⚠️ 無法取得已確認任務：{e}")
        return

    for task in tasks:
        task_id = task["ID"]
        print(f"✏️ 執行編輯任務：{task_id}")
        success = editor.edit_comment(
            driver=driver,
            post_url=task["文章URL"],
            comment_id=task["回覆ID"],
            new_content=task["草稿"]
        )

        if success:
            http.post(f"{RAILWAY_API}/tasks/{task_id}/done", timeout=10)
            app.push_text(f"✅ 任務 {task_id} 編輯完成！")
        else:
            http.post(f"{RAILWAY_API}/tasks/{task_id}/fail", timeout=10)
            app.push_text(f"❌ 任務 {task_id} 編輯失敗，請手動處理。\n{task['文章URL']}")


def recover_lost_tasks(driver):
    """掃描 processed_posts.txt，對有佔位留言但 DB 無任務的文章補建任務。"""
    PROCESSED_FILE = "processed_posts.txt"
    try:
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            all_urls = [line.strip() for line in f if line.strip() and "/posts/" in line]
    except FileNotFoundError:
        print("⚠️ processed_posts.txt 不存在")
        return

    print(f"🔍 掃描 {len(all_urls)} 筆記錄，尋找遺失任務...")
    recovered = 0

    for post_url in all_urls:
        task_id = post_url.rstrip("/").split("/")[-1]

        # 確認 Railway DB 是否已有此任務
        try:
            r = http.get(f"{RAILWAY_API}/tasks/{task_id}", timeout=5)
            if r.status_code == 200:
                continue  # 已存在，跳過
        except Exception:
            pass

        # DB 無此任務 → 檢查頁面上是否有自己的留言
        try:
            driver.get(post_url)
            time.sleep(3)

            # 用 JS 找 comment-editor-trigger，再往上找 data-comment-id
            comment_id = driver.execute_script("""
                var trigger = document.querySelector('a.comment-editor-trigger');
                if (!trigger) return null;
                var el = trigger;
                while (el && el !== document.body) {
                    if (el.getAttribute('data-comment-id')) return el.getAttribute('data-comment-id');
                    el = el.parentElement;
                }
                var parent = trigger.parentElement;
                while (parent && parent !== document.body) {
                    var found = parent.querySelector('[data-comment-id]');
                    if (found) return found.getAttribute('data-comment-id');
                    parent = parent.parentElement;
                }
                return null;
            """)

            if not comment_id:
                print(f"⚠️ 找不到 comment_id：{task_id}（頁面有 trigger 但找不到 ID）")
                continue

            # 取文章標題
            try:
                title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
            except Exception:
                title = f"文章 {task_id}"

            # 生成草稿
            print(f"🤖 補建任務：{task_id}  {title[:30]}")
            qa_content, full_reply = claude_helper.generate_draft(title, "")

            resp = http.post(f"{RAILWAY_API}/tasks", json={
                "post_url": post_url,
                "post_title": title,
                "comment_id": comment_id,
                "draft": full_reply,
                "qa_content": qa_content,
                "full_reply": full_reply,
            }, timeout=15)
            resp.raise_for_status()
            print(f"✅ 恢復：#{task_id} comment={comment_id}")
            recovered += 1
            time.sleep(2)

        except Exception as e:
            print(f"⚠️ 處理 {task_id} 失敗：{e}")

    print(f"\n🎉 恢復完成，共補建 {recovered} 筆任務")


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

    PROCESSED_FILE = "processed_posts.txt"

    def load_processed():
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            return []

    def save_processed(posts):
        with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(posts))

    processed_posts = load_processed()
    print(f"📂 已讀取 {len(processed_posts)} 筆處理記錄")

    # 補建遺失任務（一次性，不影響正常流程）
    recover_lost_tasks(driver)

    while True:
        try:
            # ① 先處理編輯 queue
            process_edit_queue(driver)

            print(f"\n--- 🕒 巡邏開始：{time.strftime('%H:%M:%S')} ---")
            driver.get("https://finfo.tw/posts?sort=created_at")
            time.sleep(3)

            all_links = driver.find_elements(By.TAG_NAME, "a")
            print(f"🔗 找到連結數：{len(all_links)}")

            seen_hrefs = set()
            candidate_posts = []
            for link_el in all_links:
                href = link_el.get_attribute('href') or ""
                text = link_el.text.strip()
                if "/posts/" in href and any(c.isdigit() for c in href) and len(text) > 2:
                    clean_href = href.split('#')[0]
                    if clean_href not in seen_hrefs:
                        seen_hrefs.add(clean_href)
                        candidate_posts.append((text, clean_href))

            print(f"📄 找到 {len(candidate_posts)} 篇候選文章")

            for title, link in candidate_posts:
                if link in processed_posts:
                    print(f"⏭️ 已處理過，略過：{title}")
                    continue

                if not any(kw in title for kw in KEYWORDS):
                    processed_posts.append(link)
                    save_processed(processed_posts)
                    print(f"😐 無關鍵字，略過：{title}")
                    continue

                # 有關鍵字，進行完整處理流程，每篇獨立 try/except
                try:
                    print(f"🎯 鎖定：{title}，準備佔位！")

                    # ② 送出佔位（佔位前先記錄，避免重複卡位）
                    processed_posts.append(link)
                    save_processed(processed_posts)

                    comment_id = post_placeholder(driver, link)

                    if not comment_id:
                        print("⚠️ 未取得回覆 ID，跳過此篇")
                        continue

                    # ③ 取得文章內容（給 Claude）
                    post_content = get_post_content(driver, link)

                    # ④ Claude 生成草稿
                    print("🤖 Claude 生成草稿中...")
                    qa_content, full_reply = claude_helper.generate_draft(title, post_content)
                    print(f"📝 草稿：{qa_content[:80]}...")

                    # ⑤ 透過 Railway API 新增任務
                    resp = http.post(f"{RAILWAY_API}/tasks", json={
                        "post_url": link,
                        "post_title": title,
                        "comment_id": comment_id,
                        "draft": full_reply,
                        "qa_content": qa_content,
                        "full_reply": full_reply,
                    }, timeout=15)
                    resp.raise_for_status()
                    task_id = resp.json()["task_id"]
                    print(f"📊 任務已存入 Railway DB：{task_id}")
                    print(f"📱 任務已靜默存入，等待早報推播")

                except Exception as post_err:
                    print(f"⚠️ 處理文章失敗 [{title[:30]}]：{post_err}，繼續下一篇")

            if len(processed_posts) > MAX_PROCESSED_CACHE:
                processed_posts = processed_posts[-MAX_PROCESSED_CACHE:]
                save_processed(processed_posts)

            wait_time = random.randint(PATROL_INTERVAL_MIN, PATROL_INTERVAL_MAX)
            print(f"😴 休息 {wait_time} 秒...")
            time.sleep(wait_time)

        except Exception as e:
            print(f"⚠️ 主迴圈異常：{e}，等待 10 秒重試...")
            time.sleep(10)


if __name__ == "__main__":
    run_finfo_bot()
    input()
