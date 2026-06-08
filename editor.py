import time
import html as _html_mod
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def _to_trix_html(text: str) -> str:
    parts = []
    for line in text.split('\n'):
        if not line.strip('\xa0').strip():
            parts.append('<p>&nbsp;</p>')
        else:
            parts.append(f'<p>{_html_mod.escape(line, quote=False)}</p>')
    return ''.join(parts)


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

        # 先 click 確保 trix .editor 物件初始化完成
        trix.click()
        time.sleep(0.8)

        trix_html = _to_trix_html(new_content)
        result = driver.execute_script("""
            var el = document.querySelector('trix-editor.bg-white');
            if (!el || !el.editor) return 'error: editor not ready';
            el.editor.loadHTML(arguments[0]);

            // 強制同步 hidden input（Rails form 讀的是這裡）
            var inputId = el.getAttribute('input');
            var hidden = inputId ? document.getElementById(inputId) : null;
            if (hidden) {
                hidden.value = el.value;
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
            }
            el.dispatchEvent(new Event('trix-change', { bubbles: true }));

            return 'ok:input=' + (inputId || 'not-found');
        """, trix_html)
        print(f"🔍 loadHTML: {result}")
        time.sleep(0.8)

        preview = driver.execute_script(
            "var el = document.querySelector('trix-editor.bg-white');"
            "return el ? el.innerText.substring(0, 60) : 'not found';"
        )
        print(f"🔍 trix 內容預覽: {preview}")

        # loadHTML 後重新 click 恢復 focus
        trix.click()
        time.sleep(0.5)

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
