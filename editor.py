import time
import html as _html_mod
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def _to_clipboard_text(text: str) -> str:
    # Convert template text to plain text for clipboard paste.
    # \xa0-only lines (blank markers) become empty lines so trix paste
    # produces <br><br> (one blank line) inside ONE <div> — same as PLACEHOLDER.
    lines = []
    for line in text.split('\n'):
        if not line.strip('\xa0').strip():
            lines.append('')
        else:
            lines.append(line)
    return '\n'.join(lines)


def edit_comment(driver, post_url: str, comment_id: str, new_content: str) -> bool:
    try:
        driver.get(post_url)
        time.sleep(3)

        triggered = driver.execute_script(
            "var btn = document.querySelector('a.comment-editor-trigger');"
            "if (btn) { btn.click(); return true; } return false;"
        )
        if not triggered:
            raise Exception("找不到 a.comment-editor-trigger，頁面上可能沒有自己的回覆")
        time.sleep(5)

        trix = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "trix-editor.bg-white"))
        )
        trix.click()
        time.sleep(0.8)

        paste_text = _to_clipboard_text(new_content)
        print(f"🔍 paste_text preview: {paste_text[:150]}")
        pyperclip.copy(paste_text)

        actions = ActionChains(driver)
        # 全選現有內容刪除，再貼上新內容（同 post_placeholder 的方式）
        actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
        time.sleep(0.3)
        actions.send_keys(Keys.DELETE).perform()
        time.sleep(0.5)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        time.sleep(1.5)

        stored = driver.execute_script("""
            var el = document.querySelector('trix-editor.bg-white');
            var inputId = el ? el.getAttribute('input') : null;
            var hidden = inputId ? document.getElementById(inputId) : null;
            return hidden ? hidden.value.substring(0, 200) : 'not found';
        """)
        print(f"🔍 after paste, hidden: {stored}")

        # 提交（TAB×3 + ENTER）
        trix.click()
        time.sleep(0.5)
        ActionChains(driver).send_keys(Keys.TAB).send_keys(Keys.TAB).send_keys(Keys.TAB).perform()
        time.sleep(0.5)
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        time.sleep(3)

        print(f"✅ 編輯成功：comment_id={comment_id}")
        return True

    except Exception as e:
        print(f"❌ 編輯失敗：{e}")
        return False
