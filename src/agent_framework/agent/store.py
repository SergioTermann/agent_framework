"""
Factor 6 ── 启动 / 暂停 / 恢复

Thread 持久化存储，让 Agent 能够随时中断、随时恢复。
提供两种实现：
  - FileSystemStore：每个 Thread 存为独立 JSON 文件，调试友好
  - SQLiteStore    ：SQLite 单文件数据库，生产环境推荐
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from agent_framework.core.database import open_sqlite_connection
from agent_framework.agent.thread import Thread


class ThreadStore(ABC):
    """Thread 存储抽象接口"""

    @abstractmethod
    def save(self, thread: Thread) -> None: ...

    @abstractmethod
    def load(self, thread_id: str) -> Optional[Thread]: ...

    @abstractmethod
    def list_ids(self) -> list[str]: ...

    @abstractmethod
    def delete(self, thread_id: str) -> None: ...

    def exists(self, thread_id: str) -> bool:
        return self.load(thread_id) is not None


class FileSystemStore(ThreadStore):
    """
    文件系统存储 —— 每个 Thread 存为一个 JSON 文件。
    优点：透明可见、便于手动调试和版本控制。
    """

    def __init__(self, base_dir: str = ".agent_threads"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _path(self, thread_id: str) -> str:
        return os.path.join(self.base_dir, f"{thread_id}.json")

    def save(self, thread: Thread) -> None:
        with open(self._path(thread.thread_id), "w", encoding="utf-8") as f:
            json.dump(thread.to_dict(), f, ensure_ascii=False, indent=2)

    def load(self, thread_id: str) -> Optional[Thread]:
        path = self._path(thread_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return Thread.from_dict(json.load(f))

    def list_ids(self) -> list[str]:
        return [
            f[:-5]
            for f in os.listdir(self.base_dir)
            if f.endswith(".json")
        ]

    def delete(self, thread_id: str) -> None:
        path = self._path(thread_id)
        if os.path.exists(path):
            os.remove(path)

    def __repr__(self) -> str:
        return f"<FileSystemStore dir={self.base_dir!r}>"


class SQLiteStore(ThreadStore):
    """
    SQLite 存储 —— 单文件数据库，适合生产环境。
    支持并发查询（WAL 模式），可随时替换为 PostgreSQL（只需修改此类）。
    """

    def __init__(self, db_path: str = ".agent_threads/threads.db"):
        dir_part = os.path.dirname(db_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return open_sqlite_connection(self.db_path, check_same_thread=False)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id  TEXT PRIMARY KEY,
                    data       TEXT    NOT NULL,
                    updated_at TEXT    NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_updated_at ON threads(updated_at)
            """)

    def save(self, thread: Thread) -> None:
        data = json.dumps(thread.to_dict(), ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO threads (thread_id, data, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    data       = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (thread.thread_id, data, now),
            )

    def load(self, thread_id: str) -> Optional[Thread]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return Thread.from_dict(json.loads(row["data"]))

    def list_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT thread_id FROM threads ORDER BY updated_at DESC"
            ).fetchall()
        return [row["thread_id"] for row in rows]

    def delete(self, thread_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM threads WHERE thread_id = ?",
                (thread_id,),
            )

    def list_with_status(self) -> list[dict]:
        """列出所有 Thread 及其最后更新时间（用于管理界面）"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT thread_id, updated_at FROM threads ORDER BY updated_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            t = self.load(row["thread_id"])
            result.append({
                "thread_id": row["thread_id"],
                "updated_at": row["updated_at"],
                "event_count": len(t.events) if t else 0,
                "paused": t.is_paused() if t else False,
            })
        return result

    def __repr__(self) -> str:
        return f"<SQLiteStore db={self.db_path!r}>"
