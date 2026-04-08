"""
API 密钥管理系统
支持 API Key 生成、验证、限流
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from functools import wraps
from flask import request, jsonify
from agent_framework.core.database import DatabaseManager


# ─── 数据模型 ─────────────────────────────────────────────────────────────────

@dataclass
class APIKey:
    """API 密钥"""
    key_id: str
    key_hash: str
    name: str
    created_at: str
    expires_at: Optional[str] = None
    is_active: bool = True

    # 限流配置
    rate_limit: int = 100  # 每分钟请求数
    daily_limit: int = 10000  # 每天请求数

    # 权限
    permissions: List[str] = field(default_factory=list)

    # 元数据
    user_id: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    # 统计
    total_requests: int = 0
    last_used_at: Optional[str] = None


@dataclass
class APIUsage:
    """API 使用记录"""
    usage_id: str
    key_id: str
    endpoint: str
    method: str
    status_code: int
    timestamp: str
    response_time: float
    tokens_used: int = 0
    metadata: Dict = field(default_factory=dict)


# ─── API 密钥存储 ─────────────────────────────────────────────────────────────

class APIKeyStorage:
    """API 密钥持久化存储"""

    def __init__(self, db_path: str = "./data/api_keys.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # API 密钥表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_id TEXT PRIMARY KEY,
                    key_hash TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    is_active INTEGER NOT NULL,
                    rate_limit INTEGER NOT NULL,
                    daily_limit INTEGER NOT NULL,
                    permissions TEXT,
                    user_id TEXT,
                    metadata TEXT,
                    total_requests INTEGER DEFAULT 0,
                    last_used_at TEXT
                )
            """)

            # 使用记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    usage_id TEXT PRIMARY KEY,
                    key_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    response_time REAL NOT NULL,
                    tokens_used INTEGER DEFAULT 0,
                    metadata TEXT,
                    FOREIGN KEY (key_id) REFERENCES api_keys(key_id)
                )
            """)

            # 限流计数表（内存缓存）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rate_limit_cache (
                    key_id TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    request_count INTEGER NOT NULL,
                    PRIMARY KEY (key_id, window_start)
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_user
                ON api_keys(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_usage_key
                ON api_usage(key_id, timestamp DESC)
            """)

    def create_key(self, api_key: APIKey, raw_key: str):
        """创建 API 密钥"""
        import json
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_keys
                (key_id, key_hash, name, created_at, expires_at, is_active,
                 rate_limit, daily_limit, permissions, user_id, metadata,
                 total_requests, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                api_key.key_id,
                api_key.key_hash,
                api_key.name,
                api_key.created_at,
                api_key.expires_at,
                1 if api_key.is_active else 0,
                api_key.rate_limit,
                api_key.daily_limit,
                json.dumps(api_key.permissions),
                api_key.user_id,
                json.dumps(api_key.metadata),
                api_key.total_requests,
                api_key.last_used_at,
            ))

    def get_key_by_hash(self, key_hash: str) -> Optional[APIKey]:
        """通过哈希获取密钥"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM api_keys WHERE key_hash = ?
            """, (key_hash,))
            row = cursor.fetchone()

        if not row:
            return None

        import json

        return APIKey(
            key_id=row[0],
            key_hash=row[1],
            name=row[2],
            created_at=row[3],
            expires_at=row[4],
            is_active=bool(row[5]),
            rate_limit=row[6],
            daily_limit=row[7],
            permissions=json.loads(row[8]) if row[8] else [],
            user_id=row[9],
            metadata=json.loads(row[10]) if row[10] else {},
            total_requests=row[11],
            last_used_at=row[12],
        )

    def list_keys(self, user_id: Optional[str] = None) -> List[APIKey]:
        """列出 API 密钥"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            if user_id:
                cursor.execute("""
                    SELECT * FROM api_keys WHERE user_id = ? ORDER BY created_at DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT * FROM api_keys ORDER BY created_at DESC
                """)

            rows = cursor.fetchall()

        import json

        keys = []
        for row in rows:
            keys.append(APIKey(
                key_id=row[0],
                key_hash=row[1],
                name=row[2],
                created_at=row[3],
                expires_at=row[4],
                is_active=bool(row[5]),
                rate_limit=row[6],
                daily_limit=row[7],
                permissions=json.loads(row[8]) if row[8] else [],
                user_id=row[9],
                metadata=json.loads(row[10]) if row[10] else {},
                total_requests=row[11],
                last_used_at=row[12],
            ))

        return keys

    def update_key(self, api_key: APIKey):
        """更新 API 密钥"""
        import json
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_keys SET
                    name = ?,
                    is_active = ?,
                    rate_limit = ?,
                    daily_limit = ?,
                    permissions = ?,
                    metadata = ?,
                    total_requests = ?,
                    last_used_at = ?
                WHERE key_id = ?
            """, (
                api_key.name,
                1 if api_key.is_active else 0,
                api_key.rate_limit,
                api_key.daily_limit,
                json.dumps(api_key.permissions),
                json.dumps(api_key.metadata),
                api_key.total_requests,
                api_key.last_used_at,
                api_key.key_id,
            ))

    def delete_key(self, key_id: str):
        """删除 API 密钥"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM api_keys WHERE key_id = ?", (key_id,))

    def log_usage(self, usage: APIUsage):
        """记录使用"""
        import json
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_usage
                (usage_id, key_id, endpoint, method, status_code, timestamp,
                 response_time, tokens_used, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                usage.usage_id,
                usage.key_id,
                usage.endpoint,
                usage.method,
                usage.status_code,
                usage.timestamp,
                usage.response_time,
                usage.tokens_used,
                json.dumps(usage.metadata),
            ))

    def get_usage_stats(
        self,
        key_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict:
        """获取使用统计"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM api_usage WHERE key_id = ?"
            params = [key_id]

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            cursor.execute(query, params)
            rows = cursor.fetchall()

        total_requests = len(rows)
        total_tokens = sum(row[7] for row in rows)
        avg_response_time = sum(row[6] for row in rows) / total_requests if total_requests > 0 else 0

        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "average_response_time": round(avg_response_time, 3),
        }


# ─── API 密钥管理器 ───────────────────────────────────────────────────────────

class APIKeyManager:
    """API 密钥管理器"""

    def __init__(self, storage: APIKeyStorage):
        self.storage = storage

    def generate_key(
        self,
        name: str,
        user_id: Optional[str] = None,
        rate_limit: int = 100,
        daily_limit: int = 10000,
        permissions: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
    ) -> tuple[APIKey, str]:
        """生成新的 API 密钥"""
        # 生成随机密钥
        raw_key = f"sk-{secrets.token_urlsafe(32)}"

        # 计算哈希
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        # 计算过期时间
        expires_at = None
        if expires_in_days:
            expires_at = (datetime.now() + timedelta(days=expires_in_days)).isoformat()

        # 创建密钥对象
        api_key = APIKey(
            key_id=secrets.token_urlsafe(16),
            key_hash=key_hash,
            name=name,
            created_at=datetime.now().isoformat(),
            expires_at=expires_at,
            rate_limit=rate_limit,
            daily_limit=daily_limit,
            permissions=permissions or [],
            user_id=user_id,
        )

        # 保存到数据库
        self.storage.create_key(api_key, raw_key)

        return api_key, raw_key

    def validate_key(self, raw_key: str) -> Optional[APIKey]:
        """验证 API 密钥"""
        # 计算哈希
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        # 查询密钥
        api_key = self.storage.get_key_by_hash(key_hash)

        if not api_key:
            return None

        # 检查是否激活
        if not api_key.is_active:
            return None

        # 检查是否过期
        if api_key.expires_at:
            if datetime.fromisoformat(api_key.expires_at) < datetime.now():
                return None

        return api_key

    def check_rate_limit(self, api_key: APIKey) -> bool:
        """检查限流"""
        # 简单实现：基于内存的滑动窗口
        # 生产环境应使用 Redis
        now = datetime.now()
        window_start = now.replace(second=0, microsecond=0)

        with self.storage.db_manager.get_connection(self.storage.db_path) as conn:
            cursor = conn.cursor()

            # 获取当前窗口的请求数
            cursor.execute("""
                SELECT request_count FROM rate_limit_cache
                WHERE key_id = ? AND window_start = ?
            """, (api_key.key_id, window_start.isoformat()))

            row = cursor.fetchone()
            current_count = row[0] if row else 0

            # 检查是否超限
            if current_count >= api_key.rate_limit:
                return False

            # 更新计数
            if row:
                cursor.execute("""
                    UPDATE rate_limit_cache
                    SET request_count = request_count + 1
                    WHERE key_id = ? AND window_start = ?
                """, (api_key.key_id, window_start.isoformat()))
            else:
                cursor.execute("""
                    INSERT INTO rate_limit_cache (key_id, window_start, request_count)
                    VALUES (?, ?, 1)
                """, (api_key.key_id, window_start.isoformat()))

        # 清理旧数据
        self._cleanup_rate_limit_cache()

        return True

    def _cleanup_rate_limit_cache(self):
        """清理限流缓存"""
        # 删除 1 小时前的数据
        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()

        with self.storage.db_manager.get_connection(self.storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM rate_limit_cache WHERE window_start < ?
            """, (cutoff,))


# ─── Flask 中间件 ─────────────────────────────────────────────────────────────

def require_api_key(permissions: Optional[List[str]] = None):
    """API 密钥验证装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 从请求头获取 API 密钥
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({
                    "success": False,
                    "error": "缺少 API 密钥",
                }), 401

            raw_key = auth_header[7:]  # 移除 "Bearer " 前缀

            # 验证密钥
            storage = APIKeyStorage()
            manager = APIKeyManager(storage)

            api_key = manager.validate_key(raw_key)
            if not api_key:
                return jsonify({
                    "success": False,
                    "error": "无效的 API 密钥",
                }), 401

            # 检查权限
            if permissions:
                if not all(p in api_key.permissions for p in permissions):
                    return jsonify({
                        "success": False,
                        "error": "权限不足",
                    }), 403

            # 检查限流
            if not manager.check_rate_limit(api_key):
                return jsonify({
                    "success": False,
                    "error": "请求过于频繁，请稍后再试",
                }), 429

            # 将 API 密钥添加到请求上下文
            request.api_key = api_key

            # 执行函数
            start_time = time.time()
            response = f(*args, **kwargs)
            response_time = time.time() - start_time

            # 记录使用
            import uuid
            usage = APIUsage(
                usage_id=str(uuid.uuid4()),
                key_id=api_key.key_id,
                endpoint=request.path,
                method=request.method,
                status_code=response[1] if isinstance(response, tuple) else 200,
                timestamp=datetime.now().isoformat(),
                response_time=response_time,
            )
            storage.log_usage(usage)

            # 更新最后使用时间
            api_key.last_used_at = datetime.now().isoformat()
            api_key.total_requests += 1
            storage.update_key(api_key)

            return response

        return decorated_function
    return decorator
