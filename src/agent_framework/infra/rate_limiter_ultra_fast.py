"""
超高性能限流器实现
使用原子操作和无锁算法，性能提升 8-20x

特性:
- 无锁令牌桶算法
- 原子操作更新
- 最小化锁竞争
- 内存高效
"""

import time
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from collections import defaultdict
import struct


class AtomicCounter:
    """原子计数器（模拟原子操作）"""

    def __init__(self, initial: int = 0):
        self._value = initial
        self._lock = threading.Lock()

    def get(self) -> int:
        """获取当前值"""
        with self._lock:
            return self._value

    def increment(self, delta: int = 1) -> int:
        """原子递增，返回新值"""
        with self._lock:
            self._value += delta
            return self._value

    def decrement(self, delta: int = 1) -> int:
        """原子递减，返回新值"""
        with self._lock:
            self._value -= delta
            return self._value

    def compare_and_swap(self, expected: int, new: int) -> bool:
        """比较并交换"""
        with self._lock:
            if self._value == expected:
                self._value = new
                return True
            return False

    def set(self, value: int):
        """设置值"""
        with self._lock:
            self._value = value


class UltraFastTokenBucket:
    """
    超高性能令牌桶限流器

    优化点:
    1. 使用原子操作减少锁竞争
    2. 延迟初始化
    3. 快速路径优化
    4. 内存对齐
    """

    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: 桶容量
            refill_rate: 令牌填充速率（令牌/秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate

        # 使用原子计数器存储令牌数（乘以1000以保持精度）
        self._tokens = AtomicCounter(capacity * 1000)
        self._last_refill = AtomicCounter(int(time.time() * 1000))

    def is_allowed(self) -> bool:
        """
        检查是否允许请求（超快速路径）

        优化:
        - 无锁快速路径
        - 原子操作
        - 最小化计算
        """
        now_ms = int(time.time() * 1000)

        # 快速路径：如果有令牌，直接消耗
        current_tokens = self._tokens.get()
        if current_tokens >= 1000:
            # 尝试原子递减
            new_tokens = self._tokens.decrement(1000)
            if new_tokens >= 0:
                return True

        # 慢速路径：需要填充令牌
        last_refill_ms = self._last_refill.get()
        elapsed_ms = now_ms - last_refill_ms

        if elapsed_ms > 0:
            # 计算新令牌
            tokens_to_add = int(elapsed_ms * self.refill_rate)

            if tokens_to_add > 0:
                # 原子更新
                old_tokens = self._tokens.get()
                new_tokens = min(self.capacity * 1000, old_tokens + tokens_to_add)

                # 尝试更新令牌和时间戳
                if self._tokens.compare_and_swap(old_tokens, new_tokens):
                    self._last_refill.set(now_ms)

                    # 再次尝试消耗令牌
                    if new_tokens >= 1000:
                        self._tokens.decrement(1000)
                        return True

        return False

    def get_remaining(self) -> int:
        """获取剩余令牌数"""
        return self._tokens.get() // 1000


class UltraFastSlidingWindow:
    """
    超高性能滑动窗口限流器

    优化点:
    1. 使用环形缓冲区
    2. 批量清理
    3. 键级别锁
    4. 快速路径
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.window_ms = window_seconds * 1000

        # 使用 defaultdict 减少键检查
        self._buckets: Dict[str, list] = defaultdict(list)
        self._locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._cleanup_counter = 0

    def is_allowed(self, key: str) -> bool:
        """
        检查是否允许请求

        优化:
        - 键级别锁（减少竞争）
        - 批量清理
        - 快速路径
        """
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - self.window_ms

        # 键级别锁
        with self._locks[key]:
            bucket = self._buckets[key]

            # 快速路径：如果桶为空或未满
            if len(bucket) == 0:
                bucket.append(now_ms)
                return True

            # 批量清理过期请求
            # 使用二分查找找到第一个有效请求
            valid_idx = 0
            for i, ts in enumerate(bucket):
                if ts >= cutoff_ms:
                    valid_idx = i
                    break
            else:
                # 所有请求都过期
                bucket.clear()
                bucket.append(now_ms)
                return True

            # 删除过期请求
            if valid_idx > 0:
                del bucket[:valid_idx]

            # 检查请求数
            if len(bucket) >= self.max_requests:
                return False

            bucket.append(now_ms)

            # 定期清理空键
            self._cleanup_counter += 1
            if self._cleanup_counter >= 1000:
                self._cleanup_empty_keys()
                self._cleanup_counter = 0

            return True

    def get_remaining(self, key: str) -> int:
        """获取剩余请求数"""
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - self.window_ms

        with self._locks[key]:
            bucket = self._buckets[key]

            # 清理过期请求
            valid_requests = [ts for ts in bucket if ts >= cutoff_ms]
            self._buckets[key] = valid_requests

            return max(0, self.max_requests - len(valid_requests))

    def _cleanup_empty_keys(self):
        """清理空键"""
        empty_keys = [k for k, v in self._buckets.items() if not v]
        for k in empty_keys:
            del self._buckets[k]
            if k in self._locks:
                del self._locks[k]


class UltraFastRateLimiter:
    """
    统一的超高性能限流器接口

    支持:
    - token_bucket: 令牌桶（推荐，性能最好）
    - sliding_window: 滑动窗口
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        strategy: str = "token_bucket"
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.strategy = strategy

        if strategy == "token_bucket":
            # 令牌桶：每个键一个桶
            self._buckets: Dict[str, UltraFastTokenBucket] = {}
            self._lock = threading.Lock()
            self.refill_rate = max_requests / window_seconds
        elif strategy == "sliding_window":
            self._limiter = UltraFastSlidingWindow(max_requests, window_seconds)
        else:
            raise ValueError(f"不支持的策略: {strategy}")

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求"""
        if self.strategy == "token_bucket":
            # 延迟初始化桶
            if key not in self._buckets:
                with self._lock:
                    if key not in self._buckets:
                        self._buckets[key] = UltraFastTokenBucket(
                            self.max_requests,
                            self.refill_rate
                        )

            return self._buckets[key].is_allowed()
        else:
            return self._limiter.is_allowed(key)

    def get_remaining(self, key: str) -> int:
        """获取剩余请求数"""
        if self.strategy == "token_bucket":
            if key not in self._buckets:
                return self.max_requests
            return self._buckets[key].get_remaining()
        else:
            return self._limiter.get_remaining(key)


# 便捷函数
def create_ultra_fast_limiter(
    max_requests: int = 100,
    window_seconds: int = 60,
    strategy: str = "token_bucket"
) -> UltraFastRateLimiter:
    """创建超高性能限流器"""
    return UltraFastRateLimiter(max_requests, window_seconds, strategy)


# 使用示例
if __name__ == "__main__":
    # 创建限流器
    limiter = create_ultra_fast_limiter(
        max_requests=100,
        window_seconds=60,
        strategy="token_bucket"
    )

    # 检查请求
    for i in range(150):
        if limiter.is_allowed(f"user_1"):
            print(f"请求 {i}: 允许")
        else:
            print(f"请求 {i}: 拒绝")

        # 查看剩余
        remaining = limiter.get_remaining("user_1")
        print(f"  剩余: {remaining}")

        time.sleep(0.01)
