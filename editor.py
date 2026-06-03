import time
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def _find_editor_box(driver, comment_id: str):
    """找到編輯框（contenteditable.bg-white）"""
    try:
        el = WebDriverWait(driver, 6).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[contenteditable].bg-white")
            )
        )
        print("  ✔ 找到編輯框：[contenteditable].bg-white")
        return el
    except Exception:
        return None


def _find_submit_btn(driver, comment_id: str):
    """找送出按鈕"""
    selectors = [
        "button[type='submit'].bg-primary",
        "button[type='submit']",
        "input[type='submit']",
        "button[name='commit']",
    ]
    for sel in selectors:
        try:
            return driver.find_element(By.CSS_SELECTOR, sel)
        except Exception:
            continue
    return None


def edit_comment(driver, post_url: str, comment_id: str, new_content: str) -> bool:
    """
    找到指定回覆並編輯成新內容

    Args:
        driver: 已登入的 selenium webdriver
        post_url: 文章網址
        comment_id: 回覆 ID（例如 "263233"）
        new_content: 新的回覆內容

    Returns:
        True = 成功，False = 失敗
    """
    try:
        driver.get(post_url)
        time.sleep(3)

        wait = WebDriverWait(driver, 10)

        # 1. 定位回覆區塊
        comment_block = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, f"div.comment-content[data-comment-id='{comment_id}']")
        ))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", comment_block)
        time.sleep(0.5)

        # 2. Hover 讓選單按鈕出現
        ActionChains(driver).move_to_element(comment_block).perform()
        time.sleep(0.5)

        menu_btn = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#operation-menu-link")
        ))
        driver.execute_script("arguments[0].click();", menu_btn)
        time.sleep(1.5)

        # 3. 點「編輯回應」
        edit_btn = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(text(), '編輯回應')]")
        ))
        driver.execute_script("arguments[0].click();", edit_btn)
        time.sleep(2)

        # 4. 找編輯框（多種 selector 嘗試）
        editor_box = _find_editor_box(driver, comment_id)
        if not editor_box:
            # Debug：印出頁面上所有 textarea / contenteditable 的屬性
            print("=== DEBUG：頁面上所有 textarea ===")
            for el in driver.find_elements(By.TAG_NAME, "textarea"):
                print(f"  id={el.get_attribute('id')!r}  "
                      f"name={el.get_attribute('name')!r}  "
                      f"class={el.get_attribute('class')!r}")
            print("=== DEBUG：所有 contenteditable ===")
            for el in driver.find_elements(By.CSS_SELECTOR, "[contenteditable]"):
                print(f"  id={el.get_attribute('id')!r}  "
                      f"class={el.get_attribute('class')!r}  "
                      f"contenteditable={el.get_attribute('contenteditable')!r}")
            raise Exception("找不到編輯框，請看上面 DEBUG 輸出確認正確 selector")

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor_box)
        time.sleep(0.3)

        # 5. 用 JS 直接寫入內容（contenteditable 用 textContent）
        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            el.focus();
            el.textContent = val;
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.dispatchEvent(new Event('keyup',  {bubbles: true}));
        """, editor_box, new_content)
        time.sleep(0.8)

        # 6. 送出
        submit_btn = _find_submit_btn(driver, comment_id)
        if submit_btn:
            driver.execute_script("arguments[0].click();", submit_btn)
        else:
            editor_box.send_keys(Keys.TAB, Keys.ENTER)

        time.sleep(2)
        print(f"✅ 編輯成功：comment_id={comment_id}")
        return True

    except Exception as e:
        print(f"❌ 編輯失敗：{e}")
        return False
