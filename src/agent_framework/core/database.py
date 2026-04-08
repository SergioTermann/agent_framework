"""
统一数据库管理层
提供连接池、事务管理、错误处理
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator


SQLITE_BUSY_TIMEOUT_MS = 5000


class DatabaseManager:
    """数据库管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._connections = {}
            self._lock = threading.Lock()
            self._initialized = True

    def connect(
        self,
        db_path: str | Path,
        *,
        row_factory: Any = sqlite3.Row,
        check_same_thread: bool = False,
        timeout: float = 30.0,
    ) -> sqlite3.Connection:
        """创建并统一配置 SQLite 连接。"""
        db_path = str(db_path)
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            db_path,
            check_same_thread=check_same_thread,
            timeout=timeout,
        )
        if row_factory is not None:
            conn.row_factory = row_factory

        self._apply_sqlite_pragmas(conn)
        return conn

    def _apply_sqlite_pragmas(self, conn: sqlite3.Connection) -> None:
        """统一应用 SQLite 优化配置。"""
        pragmas = (
            "PRAGMA foreign_keys = ON",
            f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}",
            "PRAGMA journal_mode = WAL",
            "PRAGMA synchronous = NORMAL",
            "PRAGMA temp_store = MEMORY",
            "PRAGMA cache_size = -20000",
        )
        for pragma in pragmas:
            try:
                conn.execute(pragma)
            except sqlite3.DatabaseError:
                continue

    @contextmanager
    def get_connection(self, db_path: str | Path) -> Generator[sqlite3.Connection, None, None]:
        """
        获取数据库连接（上下文管理器）

        用法:
            with db_manager.get_connection("data/users.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users")
        """
        conn = self.connect(db_path)

        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def execute(
        self,
        db_path: str | Path,
        query: str,
        params: tuple | dict = ()
    ) -> list[sqlite3.Row]:
        """
        执行查询并返回结果

        Args:
            db_path: 数据库路径
            query: SQL 查询
            params: 参数（tuple 或 dict）

        Returns:
            查询结果列表
        """
        with self.get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def execute_one(
        self,
        db_path: str | Path,
        query: str,
        params: tuple | dict = ()
    ) -> sqlite3.Row | None:
        """执行查询并返回单条结果"""
        with self.get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

    def execute_many(
        self,
        db_path: str | Path,
        query: str,
        params_list: list[tuple | dict]
    ) -> int:
        """批量执行（插入/更新）"""
        with self.get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            return cursor.rowcount

    def init_table(self, db_path: str | Path, schema: str):
        """初始化表结构"""
        with self.get_connection(db_path) as conn:
            conn.executescript(schema)


# 全局单例
db_manager = DatabaseManager()


# 便捷函数
def get_db_connection(db_path: str | Path):
    """获取数据库连接（上下文管理器）"""
    return db_manager.get_connection(db_path)


def open_sqlite_connection(
    db_path: str | Path,
    *,
    row_factory: Any = sqlite3.Row,
    check_same_thread: bool = False,
    timeout: float = 30.0,
):
    """获取统一配置后的 SQLite 原始连接。"""
    return db_manager.connect(
        db_path,
        row_factory=row_factory,
        check_same_thread=check_same_thread,
        timeout=timeout,
    )


def execute_query(db_path: str | Path, query: str, params: tuple | dict = ()):
    """执行查询"""
    return db_manager.execute(db_path, query, params)


def execute_one(db_path: str | Path, query: str, params: tuple | dict = ()):
    """执行查询并返回单条结果"""
    return db_manager.execute_one(db_path, query, params)


def execute_many(db_path: str | Path, query: str, params_list: list):
    """批量执行"""
    return db_manager.execute_many(db_path, query, params_list)


def init_table(db_path: str | Path, schema: str):
    """初始化表"""
    db_manager.init_table(db_path, schema)
