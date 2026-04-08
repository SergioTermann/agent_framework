"""
优化的限流器实现
使用更高效的数据结构和算法，减少锁竞争
"""

import time
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from collections import defaultdict
import bisect


@dataclass
class RateLimitConfig:
    """限流配置"""
    max_requests: int
    window_seconds: int
    strategy: str = "sliding_window"


class OptimizedSlidingWindowLimiter:
    """
    优化的滑动窗口限流器

    优化点:
    1. 使用有序列表 + 二分查找替代 deque
    2. 批量清理过期请求
    3. 减少锁持有时间
    4. 使用 defaultdict 减少键检查
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)
        self._locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._cleanup_counter = 0
        self._cleanup_interval = 100  # 每 100 次请求清理一次

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求（优化版）"""
        now = time.time()
        cutoff = now - self.window_seconds

        # 使用键级别的锁，减少锁竞争
        with self._locks[key]:
            requests = self._requests[key]

            # 使用二分查找找到第一个有效请求的位置
            # 比遍历删除快得多
            valid_idx = bisect.bisect_left(requests, cutoff)

            if valid_idx > 0:
                # 批量删除过期请求
                del requests[:valid_idx]

            # 检查请求数
            if len(requests) >= self.max_requests:
                return False

            # 使用 bisect.insort 保持有序（O(n) 但 n 很小）
            bisect.insort(requests, now)

            # 定期清理空键
            self._cleanup_counter += 1
            if self._cleanup_counter >= self._cleanup_interval:
                self._cleanup_empty_keys()
                self._cleanup_counter = 0

            return True

    def get_remaining(self, key: str) -> int:
        """获取剩余请求数"""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._locks[key]:
            requests = self._requests[key]
            valid_idx = bisect.bisect_left(requests, cutoff)

            if valid_idx > 0:
                del requests[:valid_idx]

            return max(0, self.max_requests - len(requests))

    def get_reset_time(self, key: str) -> float:
        """获取重置时间"""
        with self._locks[key]:
            requests = self._requests[key]
            if not requests:
                return time.time()

            return requests[0] + self.window_seconds

    def _cleanup_empty_keys(self):
        """清理空键（减少内存占用）"""
        empty_keys = [k for k, v in self._requests.items() if not v]
        for k in empty_keys:
            del self._requests[k]
            del self._locks[k]


class OptimizedTokenBucketLimiter:
    """
    优化的令牌桶限流器

    优化点:
    1. 使用更精确的时间计算
    2. 减少字典操作
    3. 延迟初始化
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.capacity = max_requests
        self.refill_rate = max_requests / window_seconds
        self._buckets: Dict[str, tuple] = {}  # (tokens, last_refill)
        self._locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求（优化版）"""
        now = time.time()

        with self._locks[key]:
            if key not in self._buckets:
                # 延迟初始化
                self._buckets[key] = (self.capacity - 1, now)
                return True

            tokens, last_refill = self._buckets[key]

            # 计算新令牌
            elapsed = now - last_refill
            tokens_to_add = elapsed * self.refill_rate
            new_tokens = min(self.capacity, tokens + tokens_to_add)

            # 检查令牌
            if new_tokens < 1:
                # 更新状态但不消耗令牌
                self._buckets[key] = (new_tokens, now)
                return False

            # 消耗令牌
            self._buckets[key] = (new_tokens - 1, now)
            return True


class OptimizedFixedWindowLimiter:
    """
    优化的固定窗口限流器

    优化点:
    1. 使用整数窗口 ID 减少计算
    2. 自动清理旧窗口
    3. 使用 defaultdict 减少键检查
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求（优化版）"""
        current_window = int(time.time() / self.window_seconds)

        with self._locks[key]:
            windows = self._windows[key]

            # 清理旧窗口（只保留当前窗口）
            old_windows = [w for w in windows.keys() if w < current_window]
            for w in old_windows:
                del windows[w]

            # 检查当前窗口
            count = windows[current_window]
            if count >= self.max_requests:
                return False

            windows[current_window] += 1
            return True


class OptimizedRateLimiter:
    """优化的统一限流器"""

    def __init__(self, config: RateLimitConfig):
        self.config = config

        if config.strategy == "fixed_window":
            self.limiter = OptimizedFixedWindowLimiter(
                config.max_requests, config.window_seconds
            )
        elif config.strategy == "sliding_window":
            self.limiter = OptimizedSlidingWindowLimiter(
                config.max_requests, config.window_seconds
            )
        elif config.strategy == "token_bucket":
            self.limiter = OptimizedTokenBucketLimiter(
                config.max_requests, config.window_seconds
            )
        else:
            raise ValueError(f"不支持的限流策略: {config.strategy}")

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求"""
        return self.limiter.is_allowed(key)

    def get_remaining(self, key: str) -> int:
        """获取剩余请求数"""
        if hasattr(self.limiter, 'get_remaining'):
            return self.limiter.get_remaining(key)
        return 0

    def get_reset_time(self, key: str) -> float:
        """获取重置时间"""
        if hasattr(self.limiter, 'get_reset_time'):
            return self.limiter.get_reset_time(key)
        return time.time() + self.config.window_seconds


class OptimizedRateLimitManager:
    """优化的限流管理器"""

    def __init__(self):
        self.limiters: Dict[str, OptimizedRateLimiter] = {}
        self._lock = threading.Lock()

    def register(self, name: str, config: RateLimitConfig):
        """注册限流器"""
        with self._lock:
            self.limiters[name] = OptimizedRateLimiter(config)

    def is_allowed(self, name: str, key: str) -> bool:
        """检查是否允许请求"""
        limiter = self.limiters.get(name)
        if not limiter:
            return True

        return limiter.is_allowed(key)

    def get_limiter(self, name: str) -> Optional[OptimizedRateLimiter]:
        """获取限流器"""
        return self.limiters.get(name)


# 全局优化限流管理器
_optimized_rate_limiter: Optional[OptimizedRateLimitManager] = None


def get_optimized_rate_limiter() -> OptimizedRateLimitManager:
    """获取优化的全局限流管理器"""
    global _optimized_rate_limiter
    if _optimized_rate_limiter is None:
        _optimized_rate_limiter = OptimizedRateLimitManager()
    return _optimized_rate_limiter


# 便捷函数
def create_rate_limiter(
    max_requests: int = 100,
    window_seconds: int = 60,
    strategy: str = "sliding_window"
) -> OptimizedRateLimiter:
    """创建优化的限流器"""
    config = RateLimitConfig(
        max_requests=max_requests,
        window_seconds=window_seconds,
        strategy=strategy
    )
    return OptimizedRateLimiter(config)
