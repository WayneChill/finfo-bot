import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "data.db")

STATUS_PENDING  = "待審核"
STATUS_APPROVED = "已確認"
STATUS_REJECTED = "已略過"
STATUS_EDITING  = "修改中"
STATUS_DONE     = "已送出"
STATUS_FAILED   = "編輯失敗"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                ID       TEXT PRIMARY KEY,
                文章URL  TEXT,
                文章標題 TEXT,
                回覆ID   TEXT,
                草稿     TEXT,
                狀態     TEXT,
                建立時間 TEXT,
                qa_content TEXT,
                full_reply TEXT
            )
        """)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        for col in ("qa_content", "full_reply"):
            if col not in existing:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS examples (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                category         TEXT,
                question_summary TEXT,
                qa_content       TEXT,
                created_at       TEXT
            )
        """)


_init_db()


def add_task(post_url: str, post_title: str, comment_id: str, draft: str,
             qa_content: str = "", full_reply: str = "") -> str:
    task_id = post_url.rstrip("/").split("/")[-1]
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO tasks
               (ID, 文章URL, 文章標題, 回覆ID, 草稿, 狀態, 建立時間, qa_content, full_reply)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, post_url, post_title, comment_id, draft, STATUS_PENDING,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), qa_content, full_reply)
        )
    return task_id


def get_task(task_id: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE ID = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def update_status(task_id: str, status: str):
    with _get_conn() as conn:
        conn.execute("UPDATE tasks SET 狀態 = ? WHERE ID = ?", (status, task_id))


def update_draft(task_id: str, new_draft: str, qa_content: str = None):
    with _get_conn() as conn:
        if qa_content is not None:
            conn.execute(
                "UPDATE tasks SET 草稿 = ?, qa_content = ?, full_reply = ? WHERE ID = ?",
                (new_draft, qa_content, new_draft, task_id)
            )
        else:
            conn.execute("UPDATE tasks SET 草稿 = ? WHERE ID = ?", (new_draft, task_id))


def get_pending_tasks() -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE 狀態 IN (?, ?)",
            (STATUS_PENDING, STATUS_FAILED)
        ).fetchall()
    return [dict(r) for r in rows]


def get_approved_tasks() -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE 狀態 = ?", (STATUS_APPROVED,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_example(category: str, question_summary: str, qa_content: str) -> int:
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO examples (category, question_summary, qa_content, created_at) VALUES (?, ?, ?, ?)",
            (category, question_summary, qa_content,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        return cur.lastrowid


def get_examples() -> list:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM examples ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def find_similar_examples(title: str, limit: int = 3) -> list:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM examples ORDER BY id DESC").fetchall()
    examples = [dict(r) for r in rows]
    if not examples:
        return []

    def score(ex):
        haystack = (ex.get("category") or "") + (ex.get("question_summary") or "")
        return sum(1 for i in range(len(title) - 1) if title[i:i+2] in haystack)

    scored = sorted(((score(ex), ex) for ex in examples), key=lambda x: x[0], reverse=True)
    if scored[0][0] == 0:
        return []
    return [ex for s, ex in scored[:limit] if s > 0]


def get_recent_done_tasks(days: int = 7) -> list:
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE 狀態 IN (?, ?) AND 建立時間 >= ? ORDER BY 建立時間 DESC",
            (STATUS_DONE, STATUS_REJECTED, cutoff)
        ).fetchall()
    return [dict(r) for r in rows]
