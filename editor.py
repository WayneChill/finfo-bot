import time
import html as _html_mod
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def _to_trix_html(text: str) -> str:
    # ONE <div>, all lines joined with <br>.
    # \xa0-only lines (blank markers) become '' → <br><br> (one blank line).
    # Consecutive blank lines collapsed to one.
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

        trix_html = _to_trix_html(new_content)
        print(f"🔍 trix_html preview: {trix_html[:200]}")

        # Replace the hidden input DOM element with a new one containing our HTML.
        # Trix's internally cached reference to the OLD element becomes detached
        # (still in JS memory but removed from DOM). Trix's serialize-on-submit
        # writes to the detached element (no-op). Our NEW element with the
        # correct ONE-div+br value is what actually gets submitted.
        result = driver.execute_script("""
            var el = document.querySelector('trix-editor.bg-white');
            if (!el) return 'error: no trix';
            var inputId = el.getAttribute('input');
            var hidden = document.getElementById(inputId);
            if (!hidden) return 'error: no hidden';
            var name = hidden.getAttribute('name');
            if (!name) return 'error: no name attr';
            var parent = hidden.parentNode;
            if (!parent) return 'error: no parent';

            el.removeAttribute('input');

            var newHidden = document.createElement('input');
            newHidden.type = 'hidden';
            newHidden.name = name;
            newHidden.value = arguments[0];
            parent.replaceChild(newHidden, hidden);

            return 'ok:name=' + name + ':len=' + arguments[0].length;
        """, trix_html)
        print(f"🔍 replace hidden: {result}")
        time.sleep(0.3)

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
