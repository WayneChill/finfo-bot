import time
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def edit_comment(driver, post_url: str, comment_id: str, new_content: str) -> bool:
    try:
        # 1. 進文章頁
        driver.get(post_url)
        time.sleep(3)

        # 2. JS click 觸發編輯按鈕
        triggered = driver.execute_script(
            "var btn = document.querySelector('a.comment-editor-trigger');"
            "if (btn) { btn.click(); return true; } return false;"
        )
        if not triggered:
            raise Exception("找不到 a.comment-editor-trigger，頁面上可能沒有自己的回覆")
        time.sleep(5)

        # 3. 等 trix-editor 進入編輯模式
        trix = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "trix-editor.bg-white"))
        )

        # 4. click → Ctrl+A 全選 → Delete 清空
        trix.click()
        time.sleep(0.5)
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
        time.sleep(0.3)
        actions = ActionChains(driver)
        actions.send_keys(Keys.DELETE).perform()
        time.sleep(0.3)

        # 5. pyperclip 複製 → Ctrl+V 貼上
        # trix-editor 貼入時會壓縮一層換行，\n\n → \n\n\n 補回空行效果
        pyperclip.copy(new_content.replace('\n\n', '\n\n\n'))
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        time.sleep(1.2)

        # 6. TAB×3 → ENTER 送出
        actions = ActionChains(driver)
        actions.send_keys(Keys.TAB).send_keys(Keys.TAB).send_keys(Keys.TAB).perform()
        time.sleep(0.5)
        actions = ActionChains(driver)
        actions.send_keys(Keys.ENTER).perform()
        time.sleep(3)

        print(f"✅ 編輯成功：comment_id={comment_id}")
        return True

    except Exception as e:
        print(f"❌ 編輯失敗：{e}")
        return False
