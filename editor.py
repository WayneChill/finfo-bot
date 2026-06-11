import time
import html as _html_mod
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def _to_trix_html(text: str) -> str:
    # ONE <div>, all lines joined with <br>.
    # Blank lines (empty / \xa0) → empty string → produces <br><br> when joined.
    # This matches Finfo.tw's native clipboard-paste storage format.
    parts = []
    for line in text.split('\n'):
        if line.strip('\xa0').strip():
            parts.append(_html_mod.escape(line, quote=False))
        else:
            parts.append('')
    return '<div>' + '<br>'.join(parts) + '</div>'


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

        # 先讀現有 HTML（診斷用）
        existing = driver.execute_script("""
            var el = document.querySelector('trix-editor.bg-white');
            var inputId = el ? el.getAttribute('input') : null;
            var hidden = inputId ? document.getElementById(inputId) : null;
            return hidden ? hidden.value.substring(0, 200) : 'not found';
        """)
        print(f"🔍 existing HTML: {existing}")

        trix_html = _to_trix_html(new_content)
        result = driver.execute_script("""
            var el = document.querySelector('trix-editor.bg-white');
            if (!el) return 'error: no trix';
            var inputId = el.getAttribute('input');
            var hidden = inputId ? document.getElementById(inputId) : null;
            if (!hidden) return 'error: no hidden input';
            // Detach trix from hidden input so trix cannot overwrite our value on form submit
            el.removeAttribute('input');
            hidden.value = arguments[0];
            return 'ok:input=' + inputId + ':len=' + arguments[0].length;
        """, trix_html)
        print(f"🔍 direct set: {result}")
        print(f"🔍 trix_html preview: {trix_html[:120]}")
        time.sleep(0.5)

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
