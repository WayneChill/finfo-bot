import time
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===================================================
# Finfo 回覆編輯功能
# 依賴：已登入的 selenium driver（從 finfo.py 傳入）
# ===================================================


def edit_comment(driver, post_url: str, comment_id: str, new_content: str) -> bool:
    """
    找到指定回覆並編輯成新內容
    
    Args:
        driver: 已登入的 selenium webdriver
        post_url: 文章網址
        comment_id: 回覆 ID（例如 "263133"）
        new_content: 新的回覆內容
    
    Returns:
        True = 成功，False = 失敗
    """
    try:
        # 前往文章頁
        driver.get(post_url)
        time.sleep(3)

        wait = WebDriverWait(driver, 10)

        # 1. 找到那篇回覆的操作選單按鈕（⋯）
        menu_btn_selector = f"div[data-comment-id='{comment_id}'] #operation-menu-link"
        
        # 備用：直接找 dropdown 區塊
        try:
            menu_btn = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, menu_btn_selector)
            ))
        except:
            # 如果找不到，嘗試用 comment anchor 往上找
            anchor = driver.find_element(By.CSS_SELECTOR, f"a[id='comment-{comment_id}']")
            # 找相鄰的 operation-menu-link
            parent = anchor.find_element(By.XPATH, "following-sibling::div//div[@class[contains(.,'operation-dropdown')]]//a[@id='operation-menu-link']")
            menu_btn = parent

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", menu_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", menu_btn)
        time.sleep(0.8)

        # 2. 點「編輯回應」
        edit_btn_selector = f"a.comment-editor-trigger[data-target='#comment-{comment_id}-editor']"
        edit_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, edit_btn_selector)
        ))
        driver.execute_script("arguments[0].click();", edit_btn)
        time.sleep(1.5)

        # 3. 找到編輯框（textarea 或 contenteditable）
        editor_selector = f"#comment-{comment_id}-editor textarea, #comment-{comment_id}-editor [contenteditable='true']"
        editor_box = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, editor_selector)
        ))

        # 4. 清空並貼上新內容
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor_box)
        time.sleep(0.5)
        editor_box.click()
        time.sleep(0.3)

        # 全選清空
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
        time.sleep(0.3)
        actions.send_keys(Keys.DELETE).perform()
        time.sleep(0.3)

        # 貼上新內容
        pyperclip.copy(new_content)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        time.sleep(1)

        # 5. 找送出按鈕
        # 嘗試找 editor 區塊內的送出按鈕
        submit_selector = f"#comment-{comment_id}-editor button[type='submit'], #comment-{comment_id}-editor input[type='submit']"
        try:
            submit_btn = driver.find_element(By.CSS_SELECTOR, submit_selector)
            driver.execute_script("arguments[0].click();", submit_btn)
        except:
            # 找不到 submit 按鈕就用 TAB + ENTER
            actions.send_keys(Keys.TAB).send_keys(Keys.TAB).send_keys(Keys.ENTER).perform()

        time.sleep(2)
        print(f"✅ 編輯成功：comment_id={comment_id}")
        return True

    except Exception as e:
        print(f"❌ 編輯失敗：{e}")
        return False
