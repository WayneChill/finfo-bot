import time
import html as _html_mod
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def _to_trix_html(text: str) -> str:
    # ONE <div>, all lines joined with <br>.
    # Blank lines (empty / \xa0) → empty string → <br><br> when joined.
    # Consecutive blank lines are collapsed to one to avoid triple-<br> from double _B in template.
    parts = []
    prev_empty = False
    for line in text.split('\n'):
        if line.strip('\xa0').strip():
            parts.append(_html_mod.escape(line, quote=False))
            prev_empty = False
        else:
            if not prev_empty:
                parts.append('')
            prev_empty = True
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
        print(f"🔍 trix_html preview: {trix_html[:150]}")

        # Load into trix's internal document so trix itself serializes the correct format on submit
        load_result = driver.execute_script("""
            var el = document.querySelector('trix-editor.bg-white');
            if (!el) return 'error: no trix';
            el.editor.loadHTML(arguments[0]);
            return 'ok:loadHTML';
        """, trix_html)
        print(f"🔍 loadHTML: {load_result}")
        time.sleep(0.5)

        # Verify what trix stored after loadHTML
        stored = driver.execute_script("""
            var el = document.querySelector('trix-editor.bg-white');
            var inputId = el ? el.getAttribute('input') : null;
            var hidden = inputId ? document.getElementById(inputId) : null;
            return hidden ? hidden.value.substring(0, 200) : 'not found';
        """)
        print(f"🔍 after loadHTML, hidden: {stored}")
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
