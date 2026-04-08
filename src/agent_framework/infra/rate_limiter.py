"""
API 限流系统
支持多种限流策略：固定窗口、滑动窗口、令牌桶
"""

from __future__ import annotations

import time
import threading
from typing import Optional, Dict
from dataclasses import dataclass
from collections import deque
from functools import wraps


@dataclass
class RateLimitConfig:
    """限流配置"""
    max_requests: int  # 最大请求数
    window_seconds: int  # 时间窗口（秒）
    strategy: str = "sliding_window"  # fixed_window, sliding_window, token_bucket


class FixedWindowLimiter:
    """固定窗口限流器"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[int, int] = {}
        self._lock = threading.RLock()

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求"""
        with self._lock:
            current_window = int(time.time() / self.window_seconds)

            # 清理旧窗口
            old_windows = [w for w in self._requests.keys() if w < current_window]
            for w in old_windows:
                del self._requests[w]

            # 检查当前窗口
            count = self._requests.get(current_window, 0)
            if count >= self.max_requests:
                return False

            self._requests[current_window] = count + 1
            return True


class SlidingWindowLimiter:
    """滑动窗口限流器"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, deque] = {}
        self._lock = threading.RLock()

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求"""
        with self._lock:
            now = time.time()

            if key not in self._requests:
                self._requests[key] = deque()

            requests = self._requests[key]

            # 移除过期请求
            while requests and requests[0] < now - self.window_seconds:
                requests.popleft()

            # 检查请求数
            if len(requests) >= self.max_requests:
                return False

            requests.append(now)
            return True

    def get_remaining(self, key: str) -> int:
        """获取剩余请求数"""
        with self._lock:
            now = time.time()

            if key not in self._requests:
                return self.max_requests

            requests = self._requests[key]

            # 移除过期请求
            while requests and requests[0] < now - self.window_seconds:
                requests.popleft()

            return max(0, self.max_requests - len(requests))

    def get_reset_time(self, key: str) -> float:
        """获取重置时间"""
        with self._lock:
            if key not in self._requests or not self._requests[key]:
                return time.time()

            oldest_request = self._requests[key][0]
            return oldest_request + self.window_seconds


class TokenBucketLimiter:
    """令牌桶限流器"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.capacity = max_requests
        self.refill_rate = max_requests / window_seconds  # 每秒补充的令牌数
        self._buckets: Dict[str, Dict] = {}
        self._lock = threading.RLock()

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求"""
        with self._lock:
            now = time.time()

            if key not in self._buckets:
                self._buckets[key] = {
                    'tokens': self.capacity,
                    'last_refill': now
                }

            bucket = self._buckets[key]

            # 补充令牌
            elapsed = now - bucket['last_refill']
            tokens_to_add = elapsed * self.refill_rate
            bucket['tokens'] = min(self.capacity, bucket['tokens'] + tokens_to_add)
            bucket['last_refill'] = now

            # 检查令牌
            if bucket['tokens'] < 1:
                return False

            bucket['tokens'] -= 1
            return True


class RateLimiter:
    """统一限流器"""

    def __init__(self, config: RateLimitConfig):
        self.config = config

        if config.strategy == "fixed_window":
            self.limiter = FixedWindowLimiter(config.max_requests, config.window_seconds)
        elif config.strategy == "sliding_window":
            self.limiter = SlidingWindowLimiter(config.max_requests, config.window_seconds)
        elif config.strategy == "token_bucket":
            self.limiter = TokenBucketLimiter(config.max_requests, config.window_seconds)
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


class RateLimitManager:
    """限流管理器"""

    def __init__(self):
        self.limiters: Dict[str, RateLimiter] = {}

    def register(self, name: str, config: RateLimitConfig):
        """注册限流器"""
        self.limiters[name] = RateLimiter(config)

    def is_allowed(self, name: str, key: str) -> bool:
        """检查是否允许请求"""
        limiter = self.limiters.get(name)
        if not limiter:
            return True  # 没有配置限流，默认允许

        return limiter.is_allowed(key)

    def get_limiter(self, name: str) -> Optional[RateLimiter]:
        """获取限流器"""
        return self.limiters.get(name)


# 全局限流管理器
_global_rate_limiter: Optional[RateLimitManager] = None


def get_rate_limiter() -> RateLimitManager:
    """获取全局限流管理器"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimitManager()
    return _global_rate_limiter


def rate_limit(
    name: str,
    key_func=None,
    max_requests: int = 100,
    window_seconds: int = 60,
    strategy: str = "sliding_window"
):
    """限流装饰器"""
    manager = get_rate_limiter()

    # 注册限流器
    if name not in manager.limiters:
        manager.register(name, RateLimitConfig(
            max_requests=max_requests,
            window_seconds=window_seconds,
            strategy=strategy
        ))

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取限流键
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # 默认使用第一个参数作为键
                key = str(args[0]) if args else "default"

            # 检查限流
            if not manager.is_allowed(name, key):
                from flask import jsonify
                limiter = manager.get_limiter(name)
                reset_time = limiter.get_reset_time(key) if limiter else time.time()

                return jsonify({
                    'error': '请求过于频繁，请稍后再试',
                    'rate_limit': {
                        'limit': max_requests,
                        'window': window_seconds,
                        'reset_at': reset_time
                    }
                }), 429

            return func(*args, **kwargs)

        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
# Flask 集成
# ═══════════════════════════════════════════════════════════════════════════════

def init_rate_limiting(app):
    """初始化 Flask 应用的限流"""
    from flask import request, g

    # 注册全局限流
    manager = get_rate_limiter()

    # API 限流配置
    manager.register("api", RateLimitConfig(
        max_requests=100,
        window_seconds=60,
        strategy="sliding_window"
    ))

    # 用户限流配置
    manager.register("user", RateLimitConfig(
        max_requests=1000,
        window_seconds=3600,
        strategy="sliding_window"
    ))

    @app.before_request
    def check_rate_limit():
        """请求前检查限流"""
        # 获取用户标识
        user_id = request.headers.get('X-User-ID') or request.remote_addr

        # 检查 API 限流
        if not manager.is_allowed("api", user_id):
            limiter = manager.get_limiter("api")
            return {
                'error': '请求过于频繁',
                'rate_limit': {
                    'remaining': limiter.get_remaining(user_id),
                    'reset_at': limiter.get_reset_time(user_id)
                }
            }, 429

        # 保存限流信息到 g
        g.rate_limit_key = user_id
        g.rate_limiter = manager.get_limiter("api")

    @app.after_request
    def add_rate_limit_headers(response):
        """添加限流响应头"""
        if hasattr(g, 'rate_limiter') and hasattr(g, 'rate_limit_key'):
            limiter = g.rate_limiter
            key = g.rate_limit_key

            response.headers['X-RateLimit-Limit'] = str(limiter.config.max_requests)
            response.headers['X-RateLimit-Remaining'] = str(limiter.get_remaining(key))
            response.headers['X-RateLimit-Reset'] = str(int(limiter.get_reset_time(key)))

        return response


# ═══════════════════════════════════════════════════════════════════════════════
# 使用示例
# ═══════════════════════════════════════════════════════════════════════════════

"""
# 1. 使用装饰器
@rate_limit(
    name="api_call",
    max_requests=10,
    window_seconds=60,
    strategy="sliding_window"
)
def api_endpoint(user_id):
    return {"message": "success"}

# 2. 手动检查
manager = get_rate_limiter()
manager.register("custom", RateLimitConfig(
    max_requests=5,
    window_seconds=10,
    strategy="token_bucket"
))

if manager.is_allowed("custom", "user_123"):
    # 处理请求
    pass
else:
    # 返回限流错误
    pass

# 3. Flask 集成
from flask import Flask
app = Flask(__name__)
init_rate_limiting(app)

@app.route('/api/data')
def get_data():
    return {"data": "..."}
"""
