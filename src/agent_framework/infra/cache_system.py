"""
统一缓存系统
支持内存缓存和 Redis 缓存
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import time
import threading
from typing import Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    expire_at: Optional[float] = None
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expire_at is None:
            return False
        return time.time() > self.expire_at


class MemoryCache:
    """内存缓存"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

        # 启动清理线程
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存"""
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return default

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return default

            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存"""
        with self._lock:
            # 如果缓存已满，删除最旧的条目
            if len(self._cache) >= self.max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
                del self._cache[oldest_key]

            ttl = ttl if ttl is not None else self.default_ttl
            expire_at = time.time() + ttl if ttl > 0 else None

            self._cache[key] = CacheEntry(
                key=key,
                value=value,
                expire_at=expire_at
            )

    def delete(self, key: str):
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            return True

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0

            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'total_requests': total
            }

    def _cleanup_loop(self):
        """清理过期条目"""
        while True:
            time.sleep(60)  # 每分钟清理一次
            self._cleanup_expired()

    def _cleanup_expired(self):
        """清理过期条目"""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]


class RedisCache:
    """Redis 缓存"""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0,
                 password: Optional[str] = None, default_ttl: int = 3600):
        try:
            import redis
        except ImportError:
            raise ImportError("Redis backend requires 'redis' package. Install with: pip install redis")

        self.default_ttl = default_ttl
        self._client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True
        )
        self._hits = 0
        self._misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存"""
        try:
            value = self._client.get(key)
            if value is None:
                self._misses += 1
                return default

            self._hits += 1
            return json.loads(value)
        except Exception:
            self._misses += 1
            return default

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存"""
        try:
            ttl = ttl if ttl is not None else self.default_ttl
            serialized = json.dumps(value)

            if ttl > 0:
                self._client.setex(key, ttl, serialized)
            else:
                self._client.set(key, serialized)
        except Exception:
            pass

    def delete(self, key: str):
        """删除缓存"""
        try:
            self._client.delete(key)
        except Exception:
            pass

    def clear(self):
        """清空缓存"""
        try:
            self._client.flushdb()
            self._hits = 0
            self._misses = 0
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            return bool(self._client.exists(key))
        except Exception:
            return False

    def get_stats(self) -> dict:
        """获取统计信息"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0

        try:
            info = self._client.info('stats')
            return {
                'backend': 'redis',
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'total_requests': total,
                'redis_keys': self._client.dbsize(),
                'redis_memory': info.get('used_memory_human', 'N/A')
            }
        except Exception:
            return {
                'backend': 'redis',
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'total_requests': total
            }


class CacheManager:
    """缓存管理器"""

    def __init__(self, backend: str = "memory", **kwargs):
        """
        初始化缓存管理器

        Args:
            backend: 缓存后端 ('memory' 或 'redis')
            **kwargs: 后端特定参数
        """
        self.backend = backend

        if backend == "memory":
            self.cache = MemoryCache(
                max_size=kwargs.get('max_size', 1000),
                default_ttl=kwargs.get('default_ttl', 3600)
            )
        elif backend == "redis":
            self.cache = RedisCache(
                host=kwargs.get('host', 'localhost'),
                port=kwargs.get('port', 6379),
                db=kwargs.get('db', 0),
                password=kwargs.get('password'),
                default_ttl=kwargs.get('default_ttl', 3600)
            )
        else:
            raise ValueError(f"不支持的缓存后端: {backend}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存"""
        return self.cache.get(key, default)

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存"""
        self.cache.set(key, value, ttl)

    def delete(self, key: str):
        """删除缓存"""
        self.cache.delete(key)

    def clear(self):
        """清空缓存"""
        self.cache.clear()

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return self.cache.exists(key)

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """获取缓存，如果不存在则调用工厂函数生成"""
        value = self.get(key)
        if value is None:
            value = factory()
            self.set(key, value, ttl)
        return value

    def cached(self, ttl: Optional[int] = None, key_prefix: str = ""):
        """缓存装饰器"""
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                # 生成缓存键
                cache_key = f"{key_prefix}{func.__name__}:{args}:{kwargs}"

                # 尝试从缓存获取
                result = self.get(cache_key)
                if result is not None:
                    return result

                # 调用函数
                result = func(*args, **kwargs)

                # 存入缓存
                self.set(cache_key, result, ttl)

                return result

            return wrapper
        return decorator

    def get_stats(self) -> dict:
        """获取统计信息"""
        return self.cache.get_stats()


# 全局缓存实例
_global_cache: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    """获取全局缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager(backend="memory")
    return _global_cache


def init_cache(backend: str = "memory", **kwargs):
    """初始化全局缓存"""
    global _global_cache
    _global_cache = CacheManager(backend=backend, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# 缓存策略
# ═══════════════════════════════════════════════════════════════════════════════

class CacheStrategy:
    """缓存策略"""

    @staticmethod
    def user_cache_key(user_id: str) -> str:
        """用户缓存键"""
        return f"user:{user_id}"

    @staticmethod
    def conversation_cache_key(conversation_id: str) -> str:
        """对话缓存键"""
        return f"conversation:{conversation_id}"

    @staticmethod
    def workflow_cache_key(workflow_id: str) -> str:
        """工作流缓存键"""
        return f"workflow:{workflow_id}"

    @staticmethod
    def llm_response_cache_key(prompt: str, model: str) -> str:
        """LLM 响应缓存键"""
        import hashlib
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        return f"llm:{model}:{prompt_hash}"

    @staticmethod
    def api_response_cache_key(url: str, params: dict) -> str:
        """API 响应缓存键"""
        import hashlib
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()
        return f"api:{url}:{params_hash}"


# ═══════════════════════════════════════════════════════════════════════════════
# 使用示例
# ═══════════════════════════════════════════════════════════════════════════════

"""
# 基本使用
cache = get_cache()

# 设置缓存
cache.set("user:123", {"name": "Alice"}, ttl=3600)

# 获取缓存
user = cache.get("user:123")

# 获取或设置
user = cache.get_or_set(
    "user:123",
    lambda: fetch_user_from_db(123),
    ttl=3600
)

# 使用装饰器
@cache.cached(ttl=300, key_prefix="api:")
def expensive_api_call(param):
    # 耗时的 API 调用
    return result

# 查看统计
stats = cache.get_stats()
print(f"缓存命中率: {stats['hit_rate']:.2%}")
"""
