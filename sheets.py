from dotenv import load_dotenv
load_dotenv()
import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime

# ===================================================
# Google Sheets 狀態管理
# spreadsheet 名稱：Finfo Bot 狀態追蹤
# 欄位：ID | 文章URL | 文章標題 | 回覆ID | 草稿 | 狀態 | 建立時間
# ===================================================

SHEET_NAME = "Finfo Bot 狀態追蹤"
HEADERS = ["ID", "文章URL", "文章標題", "回覆ID", "草稿", "狀態", "建立時間"]

# 狀態常數
STATUS_PENDING   = "待審核"
STATUS_APPROVED  = "已確認"
STATUS_REJECTED  = "已略過"
STATUS_EDITING   = "修改中"
STATUS_DONE      = "已送出"


SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def get_client():
    """建立 gspread 連線（service account）"""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("請設定環境變數 GOOGLE_CREDENTIALS_JSON")

    creds_dict = json.loads(creds_json)
    # Railway 環境變數會把真正的換行符變成字面 \n，強制還原後 JWT 才能正確簽名
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def get_sheet():
    """取得或建立工作表"""
    client = get_client()
    try:
        spreadsheet = client.open(SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(SHEET_NAME)
        # 分享給自己（service account 預設只有自己看得到）
        spreadsheet.share(None, perm_type='anyone', role='writer')
    
    sheet = spreadsheet.sheet1
    
    # 確認 header
    if sheet.row_count == 0 or sheet.cell(1, 1).value != "ID":
        sheet.insert_row(HEADERS, 1)
    
    return sheet


def add_task(post_url: str, post_title: str, comment_id: str, draft: str) -> str:
    """新增一筆待審核任務，回傳任務 ID"""
    sheet = get_sheet()
    
    # 產生任務 ID（用時間戳）
    task_id = datetime.now().strftime("%Y%m%d%H%M%S")
    
    row = [
        task_id,
        post_url,
        post_title,
        comment_id,
        draft,
        STATUS_PENDING,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ]
    sheet.append_row(row)
    return task_id


def get_task(task_id: str) -> dict | None:
    """用任務 ID 取得任務資料"""
    sheet = get_sheet()
    records = sheet.get_all_records()
    
    for i, record in enumerate(records):
        if str(record.get("ID")) == str(task_id):
            record["_row"] = i + 2  # +2 因為第1列是 header
            return record
    return None


def update_status(task_id: str, status: str):
    """更新任務狀態"""
    sheet = get_sheet()
    records = sheet.get_all_records()
    
    for i, record in enumerate(records):
        if str(record.get("ID")) == str(task_id):
            row_num = i + 2
            # 狀態在第6欄
            sheet.update_cell(row_num, 6, status)
            return True
    return False


def update_draft(task_id: str, new_draft: str):
    """更新草稿內容"""
    sheet = get_sheet()
    records = sheet.get_all_records()
    
    for i, record in enumerate(records):
        if str(record.get("ID")) == str(task_id):
            row_num = i + 2
            # 草稿在第5欄
            sheet.update_cell(row_num, 5, new_draft)
            return True
    return False


def get_pending_tasks() -> list:
    """取得所有待審核任務"""
    sheet = get_sheet()
    records = sheet.get_all_records()
    return [r for r in records if r.get("狀態") == STATUS_PENDING]
