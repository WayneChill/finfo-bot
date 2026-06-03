import time
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


def edit_comment(driver, post_url: str, comment_id: str, new_content: str) -> bool:
    try:
        # 1. 進文章頁
        driver.get(post_url)
        time.sleep(3)

        # 2. 直接用 JS click 觸發編輯按鈕（跳過 hover / 選單）
        triggered = driver.execute_script(
            "var btn = document.querySelector(\"a.comment-editor-trigger[data-target='#comment-"
            + comment_id +
            "-editor']\"); if (btn) { btn.click(); return true; } return false;"
        )
        if not triggered:
            raise Exception(f"找不到編輯觸發按鈕 #comment-{comment_id}-editor")
        time.sleep(1.5)

        # 3. 找編輯框（textarea 或 contenteditable）
        editor_sel = f"#comment-{comment_id}-editor textarea, #comment-{comment_id}-editor [contenteditable]"
        editors = driver.find_elements(By.CSS_SELECTOR, editor_sel)
        if not editors:
            raise Exception(f"找不到編輯框 {editor_sel}")
        editor_box = editors[0]

        # 4. 清空並貼上新內容
        editor_box.click()
        time.sleep(0.3)
        editor_box.send_keys(Keys.CONTROL + 'a')
        time.sleep(0.2)
        pyperclip.copy(new_content)
        editor_box.send_keys(Keys.CONTROL + 'v')
        time.sleep(1)

        # 5. 送出
        submit = driver.find_element(By.CSS_SELECTOR, "input[type='submit'][name='commit']")
        driver.execute_script("arguments[0].click();", submit)
        time.sleep(2)

        print(f"✅ 編輯成功：comment_id={comment_id}")
        return True

    except Exception as e:
        print(f"❌ 編輯失敗：{e}")
        return False
