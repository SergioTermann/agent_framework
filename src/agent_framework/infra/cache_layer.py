"""
缓存层优化
使用 LRU 缓存减少数据库查询
"""

from functools import lru_cache
from typing import Optional, Dict, Any, List
import time
import threading
from collections import OrderedDict


class LRUCache:
    """
    线程安全的 LRU 缓存

    特性:
    - 自动过期
    - 线程安全
    - LRU 淘汰策略
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            # 检查是否存在
            if key not in self._cache:
                self._misses += 1
                return None

            # 检查是否过期
            if time.time() - self._timestamps[key] > self.ttl_seconds:
                del self._cache[key]
                del self._timestamps[key]
                self._misses += 1
                return None

            # 移到末尾（最近使用）
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]

    def set(self, key: str, value: Any):
        """设置缓存值"""
        with self._lock:
            # 如果已存在，更新并移到末尾
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                # 如果缓存满了，删除最旧的
                if len(self._cache) >= self.max_size:
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                    del self._timestamps[oldest_key]

            self._cache[key] = value
            self._timestamps[key] = time.time()

    def delete(self, key: str):
        """删除缓存值"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                del self._timestamps[key]

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "ttl_seconds": self.ttl_seconds,
            }


class CacheManager:
    """
    缓存管理器

    管理多个命名缓存实例
    """

    def __init__(self):
        self._caches: Dict[str, LRUCache] = {}
        self._lock = threading.Lock()

    def get_cache(
        self,
        name: str,
        max_size: int = 1000,
        ttl_seconds: int = 300
    ) -> LRUCache:
        """获取或创建缓存"""
        with self._lock:
            if name not in self._caches:
                self._caches[name] = LRUCache(max_size, ttl_seconds)
            return self._caches[name]

    def clear_all(self):
        """清空所有缓存"""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有缓存统计"""
        with self._lock:
            return {
                name: cache.get_stats()
                for name, cache in self._caches.items()
            }


# 全局缓存管理器
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


# 便捷函数
def get_cache(name: str, max_size: int = 1000, ttl_seconds: int = 300) -> LRUCache:
    """获取命名缓存"""
    return get_cache_manager().get_cache(name, max_size, ttl_seconds)


# 使用示例
if __name__ == "__main__":
    # 创建缓存
    cache = get_cache("test", max_size=100, ttl_seconds=60)

    # 设置值
    cache.set("key1", "value1")
    cache.set("key2", {"data": "value2"})

    # 获取值
    print(f"key1: {cache.get('key1')}")
    print(f"key2: {cache.get('key2')}")
    print(f"key3: {cache.get('key3')}")  # None

    # 统计
    stats = cache.get_stats()
    print(f"\n缓存统计: {stats}")
    print(f"命中率: {stats['hit_rate']:.2%}")
