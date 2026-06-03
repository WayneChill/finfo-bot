import sqlite3
import os
from datetime import datetime

DB_PATH = "/app/data.db"

STATUS_PENDING  = "待審核"
STATUS_APPROVED = "已確認"
STATUS_REJECTED = "已略過"
STATUS_EDITING  = "修改中"
STATUS_DONE     = "已送出"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                ID       TEXT PRIMARY KEY,
                文章URL  TEXT,
                文章標題 TEXT,
                回覆ID   TEXT,
                草稿     TEXT,
                狀態     TEXT,
                建立時間 TEXT
            )
        """)


_init_db()


def add_task(post_url: str, post_title: str, comment_id: str, draft: str) -> str:
    task_id = datetime.now().strftime("%Y%m%d%H%M%S")
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, post_url, post_title, comment_id, draft, STATUS_PENDING,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
    return task_id


def get_task(task_id: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE ID = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def update_status(task_id: str, status: str):
    with _get_conn() as conn:
        conn.execute("UPDATE tasks SET 狀態 = ? WHERE ID = ?", (status, task_id))


def update_draft(task_id: str, new_draft: str):
    with _get_conn() as conn:
        conn.execute("UPDATE tasks SET 草稿 = ? WHERE ID = ?", (new_draft, task_id))


def get_pending_tasks() -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE 狀態 = ?", (STATUS_PENDING,)
        ).fetchall()
    return [dict(r) for r in rows]
