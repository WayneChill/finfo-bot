import time
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


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

        # 1. 用正確的 HTML 結構定位回覆區塊
        comment_block = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, f"div.comment-content[data-comment-id='{comment_id}']")
        ))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", comment_block)
        time.sleep(0.5)

        # 2. Hover 到留言區塊讓選單按鈕出現，再等它進 DOM 後點擊
        actions = ActionChains(driver)
        actions.move_to_element(comment_block).perform()
        time.sleep(0.5)

        menu_btn = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#operation-menu-link")
        ))
        driver.execute_script("arguments[0].click();", menu_btn)
        time.sleep(1.5)  # 等 dropdown 動畫完成

        # 3. 點「編輯回應」（用 presence 找到後直接 JS click，不等 clickable 狀態）
        edit_btn = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR,
            f"a.comment-editor-trigger[data-target='#comment-{comment_id}-editor']"
        )))
        driver.execute_script("arguments[0].click();", edit_btn)
        time.sleep(2)

        # 4. 找編輯框
        editor_box = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR,
            f"#comment-{comment_id}-editor textarea, "
            f"#comment-{comment_id}-editor [contenteditable='true']"
        )))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor_box)
        time.sleep(0.5)
        editor_box.click()
        time.sleep(0.3)

        # 5. 全選清空，貼上新內容
        actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
        time.sleep(0.3)
        actions.send_keys(Keys.DELETE).perform()
        time.sleep(0.3)

        pyperclip.copy(new_content)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        time.sleep(1)

        # 6. 送出
        submit_selector = (
            f"#comment-{comment_id}-editor button[type='submit'], "
            f"#comment-{comment_id}-editor input[type='submit']"
        )
        try:
            submit_btn = driver.find_element(By.CSS_SELECTOR, submit_selector)
            driver.execute_script("arguments[0].click();", submit_btn)
        except Exception:
            actions.send_keys(Keys.TAB).send_keys(Keys.TAB).send_keys(Keys.ENTER).perform()

        time.sleep(2)
        print(f"✅ 編輯成功：comment_id={comment_id}")
        return True

    except Exception as e:
        print(f"❌ 編輯失敗：{e}")
        return False
