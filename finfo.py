import time
import random
import pyperclip
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===================================================
# 【保險一二三⚡ 專用設定區 — 改這裡就好】
# ===================================================

KEYWORDS = [
    '問', '保險', '單', '業務', '缺口', '推薦', '建議',
    '新生兒', '規劃', '健檢', '補強', '檢視', '醫療',
    '實支', '癌症', '重大傷病', '壽險', '失能', '理賠'
]

# ▼▼▼ 留言內容 — 只改這裡 ▼▼▼
MY_INTRO = """📌 保險一二三⚡規劃好簡單 — 夫妻雙業務・全台服務

回覆中請稍等，如果急的話也可以點我頭像聯繫

👫 為什麼選擇我們?

✦ 雙業務制度｜夫妻聯手服務，溝通效率翻倍，不怕找不到人
✦ 十年實戰經驗｜累積服務 900+ 客戶，經手上千件規劃案
✦ 客觀不推銷｜佛系成交，讓保險回歸需求本質
✦ 全台線上服務｜以網路平台為主，不受地域限制
✦ 完整服務流程｜健檢→規劃→送件→理賠協助，一條龍服務

🔍 規劃核心理念

「用最低預算，換取最大保障」
根據 900+ 客戶的規劃經驗，我們歸納出 5 大必備保障：

🏥 第一層：醫療基礎（必備）
✦ 實支實付：解決健保不給付的高額自費（達文西、標靶藥物、鈦合金醫材）
✦ 住院日額：薪資中斷、看護費、交通往返等彈性補貼

🎯 第二層：重大風險一次金（高 CP 值）
✦ 重大傷病一次金（涵蓋 300+ 項疾病）
✦ 取得重大傷病卡即理賠，不一定要住院，爭議少

💊 第三層：癌症專屬保障
✦ 癌症一次金，確診即給付，無需蒐集單據
✦ 因應標靶、免疫療法等高額自費趨勢

🚑 第四層：日常防護
✦ 意外醫療（最高 CP 值）
✦ 骨折、縫合、門診手術都理賠，彌補健保與實支的不足

👨‍👩‍👧‍👦 第五層：家庭責任（經濟支柱必備）
✦ 壽險／失能長照，保障家庭日常開支，留愛不留債

🩺 投保前健康狀況確認

為提升核保效率，請協助確認：
1️⃣ 目前身體狀況：有無不適或正在治療？
2️⃣ 五年就醫紀錄：有無慢性病或住院紀錄？
3️⃣ 近期就醫情形：兩個月內是否有看診／領藥？
4️⃣ 身心科紀錄：有無精神科／身心科用藥？
5️⃣ BMI 檢視：是否在 18.5~24 正常範圍？
💡 若不確定，可直接提供身高／體重，我來協助評估

🛠️ 我們的服務優勢

✓ 深度保單健檢｜揪出條款陷阱與重複浪費
✓ 專屬管理系統｜免費提供線上帳號，一眼看懂所有保單
✓ 核保實戰經驗｜月處理百件案件，最懂核保眉角與送件策略
✓ 理賠協助服務｜不只規劃，更陪您走完理賠流程
✓ 歡迎同業交流｜資源共享，對接合作

💬 開始規劃三步驟

Step 1｜提供基本資料：年齡 + 性別 + 預算
Step 2｜舊保單免費健檢（可選）
Step 3｜收到專屬規劃建議書

📩 立即點擊我的頭像聯絡

保險一二三⚡規劃好簡單
👫 夫妻雙業務 | 🏅 10 年資歷 | 🤝 900+ 客戶見證"""
# ▲▲▲ 留言內容結束 ▲▲▲

PATROL_INTERVAL_MIN = 15
PATROL_INTERVAL_MAX = 25
MAX_PROCESSED_CACHE = 500

# ===================================================


def run_finfo_bot():
    print("⚡ 啟動『保險一二三』搶頭香競爭版...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.maximize_window()

    driver.get("https://finfo.tw/users/sign_in")
    print("⚠️ 請完成登入，確認留在列表頁後按 Enter 繼續...")
    input()

    processed_posts = []

    while True:
        try:
            print(f"\n--- 🕒 巡邏開始：{time.strftime('%H:%M:%S')} ---")
            driver.get("https://finfo.tw/posts?sort=created_at")
            time.sleep(3)

            all_links = driver.find_elements(By.TAG_NAME, "a")
            print(f"🔗 找到連結數：{len(all_links)}")

            # 只抓列表最新第一篇
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
                    print(f"⏭️ 最新文章已處理過，略過：{title}")
                else:
                    processed_posts.append(link)

                    if any(kw in title for kw in KEYWORDS):
                        print(f"🎯 鎖定新目標：{title}，準備卡位！")
                        driver.get(link)
                        time.sleep(3.5)

                        try:
                            driver.switch_to.window(driver.window_handles[0])
                            wait = WebDriverWait(driver, 6)
                            trigger = wait.until(EC.presence_of_element_located(
                                (By.XPATH, "//*[contains(text(), '回應...')]")
                            ))
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", trigger)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", trigger)

                            actions = ActionChains(driver)
                            time.sleep(1)

                            # ★ 改用剪貼簿貼上，避免特殊字元被拆解
                            pyperclip.copy(MY_INTRO)
                            actions.send_keys(Keys.TAB).perform()
                            time.sleep(0.3)
                            actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

                            time.sleep(1.2)
                            actions.send_keys(Keys.TAB).send_keys(Keys.TAB).send_keys(Keys.TAB).perform()
                            time.sleep(0.5)
                            actions.send_keys(Keys.ENTER).perform()
                            print(f"✅ 卡位指令已發送：{time.strftime('%H:%M:%S')}")

                        except Exception as e:
                            print(f"❌ 內頁操作異常：{e}")
                    else:
                        print(f"😐 最新文章無關鍵字，略過：{title}")

            # 快取超量清最舊
            if len(processed_posts) > MAX_PROCESSED_CACHE:
                processed_posts = processed_posts[-MAX_PROCESSED_CACHE:]

            wait_time = random.randint(PATROL_INTERVAL_MIN, PATROL_INTERVAL_MAX)
            print(f"😴 休息 {wait_time} 秒後進行下一次突襲...")
            time.sleep(wait_time)

        except Exception as e:
            print(f"⚠️ 主迴圈異常：{e}，等待 10 秒重試...")
            time.sleep(10)


if __name__ == "__main__":
    run_finfo_bot()
    input()  # 