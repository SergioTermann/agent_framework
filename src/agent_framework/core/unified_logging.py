"""
统一日志系统
提供日志收集、查询、分析和可视化功能
"""

import logging
import agent_framework.core.fast_json as json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from agent_framework.core.database import DatabaseManager, open_sqlite_connection


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: float
    level: str
    logger: str
    message: str
    module: str = ""
    function: str = ""
    line_number: int = 0
    thread_id: int = 0
    process_id: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'timestamp': datetime.fromtimestamp(self.timestamp).isoformat(),
            'level': self.level,
            'logger': self.logger,
            'message': self.message,
            'module': self.module,
            'function': self.function,
            'line_number': self.line_number,
            'thread_id': self.thread_id,
            'process_id': self.process_id,
            'extra': self.extra
        }


class LogStorage:
    """日志存储"""

    def __init__(self, db_path: str = "data/logs.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    level TEXT NOT NULL,
                    logger TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module TEXT,
                    function TEXT,
                    line_number INTEGER,
                    thread_id INTEGER,
                    process_id INTEGER,
                    extra TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON logs(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_level ON logs(level)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_logger ON logs(logger)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON logs(created_at)")

    def write(self, entry: LogEntry):
        """写入日志"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs (timestamp, level, logger, message, module, function,
                                line_number, thread_id, process_id, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.timestamp,
                entry.level,
                entry.logger,
                entry.message,
                entry.module,
                entry.function,
                entry.line_number,
                entry.thread_id,
                entry.process_id,
                json.dumps(entry.extra)
            ))

    def query(
        self,
        level: Optional[str] = None,
        logger: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[LogEntry]:
        """查询日志"""
        conn = open_sqlite_connection(self.db_path)
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM logs WHERE 1=1"
            params = []

            if level:
                query += " AND level = ?"
                params.append(level)

            if logger:
                query += " AND logger = ?"
                params.append(logger)

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            if keyword:
                query += " AND message LIKE ?"
                params.append(f"%{keyword}%")

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        entries = []
        for row in rows:
            entry = LogEntry(
                timestamp=row['timestamp'],
                level=row['level'],
                logger=row['logger'],
                message=row['message'],
                module=row['module'] or "",
                function=row['function'] or "",
                line_number=row['line_number'] or 0,
                thread_id=row['thread_id'] or 0,
                process_id=row['process_id'] or 0,
                extra=json.loads(row['extra']) if row['extra'] else {}
            )
            entries.append(entry)

        return entries

    def count(
        self,
        level: Optional[str] = None,
        logger: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> int:
        """统计日志数量"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT COUNT(*) FROM logs WHERE 1=1"
            params = []

            if level:
                query += " AND level = ?"
                params.append(level)

            if logger:
                query += " AND logger = ?"
                params.append(logger)

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            cursor.execute(query, params)
            count = cursor.fetchone()[0]

        return count

    def get_statistics(self, hours: int = 24) -> dict:
        """获取统计信息"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            start_time = time.time() - (hours * 3600)

            # 按级别统计
            cursor.execute("""
                SELECT level, COUNT(*) as count
                FROM logs
                WHERE timestamp >= ?
                GROUP BY level
            """, (start_time,))

            level_stats = {row[0]: row[1] for row in cursor.fetchall()}

            # 按日志器统计
            cursor.execute("""
                SELECT logger, COUNT(*) as count
                FROM logs
                WHERE timestamp >= ?
                GROUP BY logger
                ORDER BY count DESC
                LIMIT 10
            """, (start_time,))

            logger_stats = {row[0]: row[1] for row in cursor.fetchall()}

            # 按小时统计
            cursor.execute("""
                SELECT
                    strftime('%Y-%m-%d %H:00:00', datetime(timestamp, 'unixepoch')) as hour,
                    COUNT(*) as count
                FROM logs
                WHERE timestamp >= ?
                GROUP BY hour
                ORDER BY hour
            """, (start_time,))

            hourly_stats = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            'by_level': level_stats,
            'by_logger': logger_stats,
            'by_hour': hourly_stats,
            'total': sum(level_stats.values())
        }

    def cleanup(self, days: int = 30):
        """清理旧日志"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cutoff_time = time.time() - (days * 86400)
            cursor.execute("DELETE FROM logs WHERE timestamp < ?", (cutoff_time,))
            deleted = cursor.rowcount

        return deleted


class UnifiedLogHandler(logging.Handler):
    """统一日志处理器"""

    def __init__(self, storage: LogStorage):
        super().__init__()
        self.storage = storage
        self.buffer = deque(maxlen=1000)
        self.lock = threading.Lock()

        # 启动后台写入线程
        self.running = True
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()

    def emit(self, record: logging.LogRecord):
        """处理日志记录"""
        try:
            entry = LogEntry(
                timestamp=record.created,
                level=record.levelname,
                logger=record.name,
                message=self.format(record),
                module=record.module,
                function=record.funcName,
                line_number=record.lineno,
                thread_id=record.thread,
                process_id=record.process,
                extra=getattr(record, 'extra', {})
            )

            with self.lock:
                self.buffer.append(entry)

        except Exception:
            self.handleError(record)

    def _writer_loop(self):
        """后台写入循环"""
        while self.running:
            try:
                entries_to_write = []

                with self.lock:
                    while self.buffer:
                        entries_to_write.append(self.buffer.popleft())

                for entry in entries_to_write:
                    self.storage.write(entry)

                time.sleep(1)

            except Exception as e:
                print(f"日志写入错误: {e}")

    def close(self):
        """关闭处理器"""
        self.running = False
        self.writer_thread.join(timeout=5)
        super().close()


class UnifiedLogger:
    """统一日志系统"""

    def __init__(self, db_path: str = "data/logs.db"):
        self.storage = LogStorage(db_path)
        self.handler = UnifiedLogHandler(self.storage)

        # 配置格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.handler.setFormatter(formatter)

        # 添加到根日志器
        root_logger = logging.getLogger()
        root_logger.addHandler(self.handler)
        root_logger.setLevel(logging.INFO)

    def get_logger(self, name: str) -> logging.Logger:
        """获取日志器"""
        return logging.getLogger(name)

    def query(self, **kwargs) -> List[LogEntry]:
        """查询日志"""
        return self.storage.query(**kwargs)

    def count(self, **kwargs) -> int:
        """统计日志"""
        return self.storage.count(**kwargs)

    def get_statistics(self, hours: int = 24) -> dict:
        """获取统计信息"""
        return self.storage.get_statistics(hours)

    def cleanup(self, days: int = 30) -> int:
        """清理旧日志"""
        return self.storage.cleanup(days)

    def close(self):
        """关闭日志系统"""
        self.handler.close()


# 全局单例
_unified_logger: Optional[UnifiedLogger] = None


def get_unified_logger() -> UnifiedLogger:
    """获取统一日志系统"""
    global _unified_logger

    if _unified_logger is None:
        _unified_logger = UnifiedLogger()

    return _unified_logger


def get_logger(name: str) -> logging.Logger:
    """获取日志器（便捷函数）"""
    unified_logger = get_unified_logger()
    return unified_logger.get_logger(name)
