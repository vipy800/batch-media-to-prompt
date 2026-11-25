"""SQLite 任务与结果存储"""
import json
import os
import sqlite3
import threading
import time
from collections import Counter

_lock = threading.RLock()
_local = threading.local()
_db_path = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    created_at REAL, finished_at REAL,
    name TEXT, source TEXT, media_type TEXT,
    model TEXT, preset_id TEXT, preset_name TEXT,
    status TEXT, total INTEGER, done INTEGER, failed INTEGER, skipped INTEGER,
    params TEXT
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT, idx INTEGER,
    filename TEXT, src_path TEXT, out_path TEXT,
    media_type TEXT, status TEXT, text TEXT, error TEXT,
    thumb TEXT, chars INTEGER, duration REAL,
    started_at REAL, finished_at REAL, retry INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_items_job ON items(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
"""


def init(db_path: str):
    global _db_path
    _db_path = db_path
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with _conn() as c:
        c.executescript(SCHEMA)
        c.commit()


def _conn():
    if _db_path is None:
        raise RuntimeError("store not initialised")
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(_db_path, timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return _ContextConn(conn)


class _ContextConn:
    """轻量包装，支持 with 而不关闭底层连接"""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------- jobs
def create_job(job: dict) -> None:
    with _lock, _conn() as c:
        c.execute(
            """INSERT INTO jobs(id,created_at,name,source,media_type,model,preset_id,preset_name,
                                status,total,done,failed,skipped,params)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job["id"], job.get("created_at", time.time()), job.get("name", ""),
                job.get("source", "upload"), job.get("media_type", "image"),
                job.get("model", ""), job.get("preset_id", ""), job.get("preset_name", ""),
                job.get("status", "pending"), job.get("total", 0), 0, 0, 0,
                json.dumps(job.get("params", {}), ensure_ascii=False),
            ),
        )
        c.commit()


def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE jobs SET {keys} WHERE id=?", (*fields.values(), job_id))
        c.commit()


def get_job(job_id: str):
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 50, offset: int = 0, q: str = "", status: str = ""):
    sql = "SELECT * FROM jobs WHERE 1=1"
    args = []
    if q:
        sql += " AND (name LIKE ? OR preset_name LIKE ? OR model LIKE ?)"
        args += [f"%{q}%"] * 3
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM items WHERE job_id=?", (job_id,))
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        c.commit()


def clear_history() -> int:
    with _lock, _conn() as c:
        n = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        c.execute("DELETE FROM items")
        c.execute("DELETE FROM jobs")
        c.commit()
    return n


# ---------------------------------------------------------------- items
def add_items(job_id: str, items: list) -> None:
    with _lock, _conn() as c:
        c.executemany(
            """INSERT INTO items(job_id,idx,filename,src_path,media_type,status,retry)
               VALUES(?,?,?,?,?,?,0)""",
            [
                (job_id, i, it["filename"], it["src_path"], it.get("media_type", "image"), "pending")
                for i, it in enumerate(items)
            ],
        )
        c.commit()


def update_item(item_id: int, **fields) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE items SET {keys} WHERE id=?", (*fields.values(), item_id))
        c.commit()


def get_item(item_id: int):
    with _conn() as c:
        row = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def job_items(job_id: str):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM items WHERE job_id=? ORDER BY idx", (job_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def cancel_pending(job_id: str) -> int:
    with _lock, _conn() as c:
        n = c.execute(
            "UPDATE items SET status='cancelled', finished_at=? WHERE job_id=? AND status='pending'",
            (time.time(), job_id),
        ).rowcount
        c.commit()
    return n


def reset_failed_items(job_id: str):
    """把失败项重置为待处理，返回重置后的条目列表"""
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT id, idx, filename, src_path, media_type FROM items WHERE job_id=? AND status='failed'",
            (job_id,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        for r in rows:
            c.execute(
                "UPDATE items SET status='pending', error=NULL, finished_at=NULL, retry=retry+1 WHERE id=?",
                (r["id"],),
            )
        c.commit()
    return [dict(r) for r in rows]


def recover_interrupted() -> int:
    """程序重启后，把上次残留的进行中任务标记为中断，避免一直卡在进行中"""
    with _lock, _conn() as c:
        n = c.execute(
            "SELECT COUNT(*) FROM items WHERE status IN ('running','pending')"
        ).fetchone()[0]
        if n:
            job_ids = [r["job_id"] for r in c.execute(
                "SELECT DISTINCT job_id FROM items WHERE status IN ('running','pending')"
            ).fetchall()]
            c.execute(
                "UPDATE items SET status='failed', error='任务中断（程序重启或崩溃）' "
                "WHERE status IN ('running','pending')"
            )
            for jid in job_ids:
                counts = Counter(
                    r["status"] for r in c.execute("SELECT status FROM items WHERE job_id=?", (jid,)).fetchall()
                )
                c.execute(
                    "UPDATE jobs SET status='error', done=?, failed=?, skipped=? WHERE id=?",
                    (counts["done"], counts["failed"], counts["skipped"], jid),
                )
        c.execute("UPDATE jobs SET status='error' WHERE status IN ('running','paused')")
        c.commit()
    return n


def stats():
    with _conn() as c:
        jobs = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        done = c.execute("SELECT COUNT(*) FROM items WHERE status='done'").fetchone()[0]
        failed = c.execute("SELECT COUNT(*) FROM items WHERE status='failed'").fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM items WHERE status IN ('pending','running')").fetchone()[0]
        chars = c.execute("SELECT COALESCE(SUM(chars),0) FROM items").fetchone()[0]
    return {"jobs": jobs, "done": done, "failed": failed, "pending": pending, "chars": chars}
