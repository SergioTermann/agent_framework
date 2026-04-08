"""
韧性模块 —— 借鉴 Claude Code 的错误处理与降级策略

提供三大核心能力：
  1. RetryPolicy     ── 带指数退避的智能重试（错误分类 + 可重试判断）
  2. CircuitBreaker  ── 电路断路器保护外部服务
  3. ModelFallback   ── LLM 模型降级链（主模型失败自动切换备选）

设计参考：
  - Claude Code 的 withRetry() 包装
  - Claude Code 的分类错误处理（timeout/quota/auth/server）
  - Claude Code 的 token budget 回退与模型降级策略
"""

from __future__ import annotations

import logging
import time
import random
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar, Generic, Optional

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ─── 错误分类（借鉴 Claude Code 的 error categorization）─────────────────────

class ErrorCategory(Enum):
    """错误分类 —— 决定重试策略"""
    TRANSIENT = "transient"          # 瞬态错误，可立即重试（网络抖动、502）
    RATE_LIMITED = "rate_limited"    # 速率限制，需要退避后重试（429）
    SERVER_ERROR = "server_error"    # 服务端错误，可退避重试（500/503）
    AUTH_ERROR = "auth_error"        # 认证错误，不可重试
    INVALID_REQUEST = "invalid_request"  # 请求错误，不可重试（400）
    TIMEOUT = "timeout"             # 超时，可重试（加长超时）
    QUOTA_EXCEEDED = "quota_exceeded"    # 配额耗尽，不可重试
    CONTEXT_TOO_LONG = "context_too_long"  # 上下文过长，需压缩后重试
    UNKNOWN = "unknown"             # 未知错误


def classify_error(error: Exception) -> ErrorCategory:
    """
    对错误进行分类，决定重试策略。

    借鉴 Claude Code 的错误分类逻辑：
      - HTTP 429 → RATE_LIMITED
      - HTTP 500/502/503 → SERVER_ERROR
      - HTTP 401/403 → AUTH_ERROR
      - HTTP 400 → INVALID_REQUEST（检查是否上下文过长）
      - Timeout → TIMEOUT
      - 网络错误 → TRANSIENT
    """
    msg = str(error).lower()

    # HTTP 状态码检测
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return ErrorCategory.RATE_LIMITED
    if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg:
        return ErrorCategory.AUTH_ERROR
    if "quota" in msg or "billing" in msg or "insufficient" in msg:
        return ErrorCategory.QUOTA_EXCEEDED
    if "context" in msg and ("long" in msg or "length" in msg or "exceed" in msg):
        return ErrorCategory.CONTEXT_TOO_LONG
    if ("400" in msg) or ("invalid" in msg and "request" in msg):
        return ErrorCategory.INVALID_REQUEST
    if "500" in msg or "502" in msg or "503" in msg or "internal server" in msg:
        return ErrorCategory.SERVER_ERROR
    if "timeout" in msg or "timed out" in msg:
        return ErrorCategory.TIMEOUT
    if "connection" in msg or "network" in msg or "urlopen" in msg:
        return ErrorCategory.TRANSIENT

    return ErrorCategory.UNKNOWN


def is_retryable(category: ErrorCategory) -> bool:
    """判断错误类别是否可重试"""
    return category in {
        ErrorCategory.TRANSIENT,
        ErrorCategory.RATE_LIMITED,
        ErrorCategory.SERVER_ERROR,
        ErrorCategory.TIMEOUT,
        ErrorCategory.CONTEXT_TOO_LONG,
        ErrorCategory.UNKNOWN,  # 未知错误给一次重试机会
    }


# ─── RetryPolicy ── 智能重试策略 ───────────────────────────────────────────

@dataclass
class RetryPolicy:
    """
    带指数退避的智能重试策略。

    特性（借鉴 Claude Code withRetry()）：
      - 错误分类决定是否重试
      - 指数退避 + 随机 jitter 防止惊群
      - 不同错误类别使用不同退避基数
      - 回调通知每次重试（用于日志/监控）

    用法：
        policy = RetryPolicy(max_retries=3, base_delay=1.0)
        result = policy.execute(lambda: call_llm(messages))
    """

    max_retries: int = 3
    """最大重试次数"""

    base_delay: float = 1.0
    """基础退避延迟（秒）"""

    max_delay: float = 60.0
    """最大退避延迟（秒）"""

    jitter: bool = True
    """是否添加随机 jitter"""

    on_retry: Optional[Callable[[int, Exception, ErrorCategory, float], None]] = None
    """重试回调: (attempt, error, category, wait_seconds) -> None"""

    def execute(self, fn: Callable[[], T], **kwargs) -> T:
        """
        执行函数，失败时按策略重试。

        :param fn: 要执行的函数
        :returns: 函数返回值
        :raises: 最后一次失败的异常（不可重试或超过重试次数时）
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return fn()
            except Exception as e:
                last_error = e
                category = classify_error(e)

                # 不可重试的错误直接抛出
                if not is_retryable(category):
                    logger.warning(
                        f"不可重试的错误 [{category.value}]: {e}"
                    )
                    raise

                # 已达最大重试次数
                if attempt >= self.max_retries:
                    logger.error(
                        f"重试 {self.max_retries} 次后仍失败 [{category.value}]: {e}"
                    )
                    raise

                # 计算退避时间
                wait = self._calculate_delay(attempt, category)

                logger.info(
                    f"第 {attempt + 1}/{self.max_retries} 次重试, "
                    f"类别={category.value}, 等待 {wait:.1f}s"
                )

                # 触发回调
                if self.on_retry:
                    try:
                        self.on_retry(attempt + 1, e, category, wait)
                    except Exception:
                        pass  # 回调错误不影响重试逻辑

                time.sleep(wait)

        # 理论上不会到这里
        raise last_error or RuntimeError("RetryPolicy: 未知错误")

    def _calculate_delay(self, attempt: int, category: ErrorCategory) -> float:
        """计算退避延迟 —— 不同错误类别使用不同策略"""
        # 速率限制使用更长的退避基数
        if category == ErrorCategory.RATE_LIMITED:
            base = self.base_delay * 3
        elif category == ErrorCategory.TIMEOUT:
            base = self.base_delay * 2
        else:
            base = self.base_delay

        # 指数退避
        delay = base * (2 ** attempt)

        # 加 jitter
        if self.jitter:
            delay *= (0.5 + random.random())

        return min(delay, self.max_delay)


# ─── CircuitBreaker ── 电路断路器 ─────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"       # 正常工作
    OPEN = "open"           # 断路，拒绝所有请求
    HALF_OPEN = "half_open" # 探测状态，允许少量请求试探


@dataclass
class CircuitBreaker:
    """
    电路断路器 —— 保护外部服务，防止级联故障。

    状态机：
      CLOSED  ──(连续失败达阈值)──→ OPEN
      OPEN    ──(冷却时间到)──→ HALF_OPEN
      HALF_OPEN ──(探测成功)──→ CLOSED
      HALF_OPEN ──(探测失败)──→ OPEN

    用法：
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        result = breaker.call(lambda: external_api_call())
    """

    failure_threshold: int = 5
    """连续失败次数阈值，超过后断路"""

    recovery_timeout: float = 30.0
    """断路后的冷却时间（秒），到期后进入半开状态"""

    half_open_max_calls: int = 1
    """半开状态允许通过的最大探测请求数"""

    name: str = "default"
    """断路器名称（用于日志区分）"""

    # 内部状态
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # 检查是否到了冷却时间，自动转为半开
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(f"断路器 [{self.name}]: OPEN → HALF_OPEN")
            return self._state

    def call(self, fn: Callable[[], T]) -> T:
        """
        通过断路器执行函数调用。

        :raises CircuitBreakerOpenError: 断路器处于 OPEN 状态时
        """
        current_state = self.state  # 触发状态检查

        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"断路器 [{self.name}] 处于 OPEN 状态，"
                f"将在 {self._remaining_cooldown():.0f}s 后尝试恢复"
            )

        if current_state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"断路器 [{self.name}] 半开探测中，请稍后重试"
                    )
                self._half_open_calls += 1

        try:
            result = fn()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """调用成功：重置计数器，关闭断路器"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"断路器 [{self.name}]: HALF_OPEN → CLOSED (探测成功)")
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def _on_failure(self) -> None:
        """调用失败：累加计数器，达到阈值后断路"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"断路器 [{self.name}]: HALF_OPEN → OPEN (探测失败)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"断路器 [{self.name}]: CLOSED → OPEN "
                    f"(连续失败 {self._failure_count} 次)"
                )

    def _remaining_cooldown(self) -> float:
        """剩余冷却时间"""
        elapsed = time.time() - self._last_failure_time
        return max(0, self.recovery_timeout - elapsed)

    def reset(self) -> None:
        """手动重置断路器"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            logger.info(f"断路器 [{self.name}] 已手动重置")


class CircuitBreakerOpenError(Exception):
    """断路器处于 OPEN 状态的异常"""
    pass


# ─── ModelFallback ── LLM 模型降级链 ──────────────────────────────────────

@dataclass
class FallbackModel:
    """降级链中的一个模型"""
    model: str
    base_url: str | None = None  # None 表示使用与主模型相同的 base_url
    api_key: str | None = None   # None 表示使用与主模型相同的 key
    max_tokens: int | None = None  # 可选：降级模型可能需要较小的 token 限制


@dataclass
class ModelFallbackChain:
    """
    LLM 模型降级链 —— 主模型失败时自动切换备选。

    借鉴 Claude Code 的模型降级策略：
      - 主模型超时/限流 → 切换到更快的小模型
      - 上下文过长 → 切换到更大上下文窗口的模型
      - 连续失败 → 逐级降级

    用法：
        chain = ModelFallbackChain(
            fallbacks=[
                FallbackModel(model="gpt-4o-mini"),
                FallbackModel(model="gpt-3.5-turbo"),
            ]
        )

        for model_cfg in chain.iterate_models(primary_model="gpt-4o"):
            try:
                result = llm.chat(messages, model=model_cfg.model)
                chain.record_success(model_cfg.model)
                break
            except Exception as e:
                chain.record_failure(model_cfg.model, e)
    """

    fallbacks: list[FallbackModel] = field(default_factory=list)
    """降级模型列表（按优先级从高到低）"""

    on_fallback: Optional[Callable[[str, str, Exception], None]] = None
    """降级回调: (from_model, to_model, error) -> None"""

    # 内部状态
    _failure_counts: dict[str, int] = field(default_factory=dict, init=False)

    def iterate_models(
        self,
        primary_model: str,
        primary_base_url: str | None = None,
        primary_api_key: str | None = None,
    ):
        """
        生成器：依次返回主模型和降级模型配置。

        先返回主模型，若主模型失败则返回降级链中的下一个模型。
        调用方通过 record_failure/record_success 通知结果。
        """
        # 主模型
        yield FallbackModel(
            model=primary_model,
            base_url=primary_base_url,
            api_key=primary_api_key,
        )

        # 降级模型
        for fb in self.fallbacks:
            yield FallbackModel(
                model=fb.model,
                base_url=fb.base_url or primary_base_url,
                api_key=fb.api_key or primary_api_key,
                max_tokens=fb.max_tokens,
            )

    def record_success(self, model: str) -> None:
        """记录成功，重置该模型的失败计数"""
        self._failure_counts[model] = 0

    def record_failure(self, model: str, error: Exception) -> None:
        """记录失败"""
        self._failure_counts[model] = self._failure_counts.get(model, 0) + 1
        logger.warning(f"模型 {model} 失败 (累计 {self._failure_counts[model]} 次): {error}")

    def get_failure_count(self, model: str) -> int:
        return self._failure_counts.get(model, 0)


# ─── ResilientLLM ── 集成韧性能力的 LLM 包装器 ──────────────────────────────

class ResilientLLMWrapper:
    """
    在现有 LLMProvider 上叠加韧性能力：
      - RetryPolicy: 智能重试
      - CircuitBreaker: 断路保护
      - ModelFallbackChain: 模型降级

    这是一个组合包装器，不修改原始 LLMProvider 接口。

    用法：
        from agent_framework.agent.llm import OpenAICompatibleProvider
        from agent_framework.agent.resilience import ResilientLLMWrapper, RetryPolicy

        llm = OpenAICompatibleProvider(api_key="sk-...", model="gpt-4o")
        resilient = ResilientLLMWrapper(
            llm=llm,
            retry_policy=RetryPolicy(max_retries=3),
            fallback_chain=ModelFallbackChain(
                fallbacks=[FallbackModel(model="gpt-4o-mini")]
            ),
        )
        # 使用 resilient.chat() 代替 llm.chat()
    """

    def __init__(
        self,
        llm,   # LLMProvider 实例
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        fallback_chain: ModelFallbackChain | None = None,
        on_fallback: Optional[Callable[[str, str, Exception], None]] = None,
    ):
        self.llm = llm
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker
        self.fallback_chain = fallback_chain
        self._on_fallback = on_fallback

    @property
    def model_name(self) -> str:
        return self.llm.model_name

    @property
    def api_key(self) -> str:
        return getattr(self.llm, "api_key", "")

    @property
    def base_url(self) -> str:
        return getattr(self.llm, "base_url", "")

    @property
    def timeout(self) -> int:
        return getattr(self.llm, "timeout", 120)

    def chat(self, messages: list[dict], **kwargs):
        """
        带韧性的 chat 调用。

        执行顺序：
          1. 尝试主模型（带重试 + 断路器）
          2. 主模型失败 → 尝试降级链中的下一个模型
          3. 所有模型都失败 → 抛出最后一个错误
        """
        if not self.fallback_chain or not self.fallback_chain.fallbacks:
            # 无降级链，直接用重试 + 断路器
            return self._call_with_resilience(messages, **kwargs)

        last_error: Exception | None = None
        primary_model = kwargs.get("model") or self.llm.model_name

        for model_cfg in self.fallback_chain.iterate_models(
            primary_model=primary_model,
            primary_base_url=getattr(self.llm, "base_url", None),
            primary_api_key=getattr(self.llm, "api_key", None),
        ):
            try:
                # 使用该模型尝试调用
                call_kwargs = dict(kwargs)
                call_kwargs["model"] = model_cfg.model
                if model_cfg.max_tokens:
                    call_kwargs["max_tokens"] = model_cfg.max_tokens

                result = self._call_with_resilience(messages, **call_kwargs)
                self.fallback_chain.record_success(model_cfg.model)
                return result

            except Exception as e:
                last_error = e
                self.fallback_chain.record_failure(model_cfg.model, e)

                # 不可重试的错误（如认证失败）不降级
                category = classify_error(e)
                if category in {ErrorCategory.AUTH_ERROR, ErrorCategory.INVALID_REQUEST}:
                    raise

                # 通知降级
                if self._on_fallback and model_cfg.model != primary_model:
                    try:
                        self._on_fallback(primary_model, model_cfg.model, e)
                    except Exception:
                        pass

                logger.info(f"模型 {model_cfg.model} 失败，尝试下一个降级模型")

        raise last_error or RuntimeError("所有模型均失败")

    def _call_with_resilience(self, messages: list[dict], **kwargs):
        """单模型调用：重试 + 断路器"""
        def do_call():
            return self.llm.chat(messages, **kwargs)

        # 断路器包装
        if self.circuit_breaker:
            def guarded_call():
                return self.circuit_breaker.call(do_call)
            return self.retry_policy.execute(guarded_call)

        return self.retry_policy.execute(do_call)


# ─── ContextAwareRecovery ── 上下文感知错误恢复 ───────────────────────────────

class RecoveryAction(Enum):
    """恢复动作 —— 决定 LLM 调用失败后如何处理"""
    RETRY = "retry"                     # 简单重试（由 ResilientLLMWrapper 处理）
    COMPACT_AND_RETRY = "compact_retry" # 压缩上下文后重试
    INCREASE_TOKENS = "increase_tokens" # 增加 max_tokens 后重试
    FALLBACK = "fallback"               # 切换降级模型
    GIVE_UP = "give_up"                 # 放弃


class ContextAwareRecovery:
    """
    上下文感知的错误恢复策略。

    借鉴 Claude Code 的分层恢复逻辑：
      - context_too_long → 压缩上下文后重试
      - max_tokens 不足 → 递增 max_tokens 后重试
      - 瞬态/服务器错误 → 简单重试（委托给 ResilientLLMWrapper）
      - 认证/配额错误 → 放弃
    """

    MAX_OUTPUT_TOKEN_RETRIES = 3

    def __init__(self):
        self._output_token_attempts = 0

    def classify_and_plan(
        self,
        error: Exception,
        attempt: int = 0,
        config: Any = None,
    ) -> RecoveryAction:
        """
        根据错误类型和当前状态，决定恢复动作。

        :param error: 异常实例
        :param attempt: 当前轮次编号
        :param config: RunConfig（可选）
        :returns: 建议的恢复动作
        """
        category = classify_error(error)
        msg = str(error).lower()

        # 上下文过长 → 压缩后重试
        if category == ErrorCategory.CONTEXT_TOO_LONG:
            return RecoveryAction.COMPACT_AND_RETRY

        # max_tokens / output 相关错误 → 增加 max_tokens
        if "max_tokens" in msg or "maximum.*output" in msg or "max_output" in msg:
            if self._output_token_attempts < self.MAX_OUTPUT_TOKEN_RETRIES:
                self._output_token_attempts += 1
                return RecoveryAction.INCREASE_TOKENS

        # 不可重试的错误 → 放弃
        if category in {
            ErrorCategory.AUTH_ERROR,
            ErrorCategory.INVALID_REQUEST,
            ErrorCategory.QUOTA_EXCEEDED,
        }:
            return RecoveryAction.GIVE_UP

        # 可重试的错误 → 委托给 ResilientLLMWrapper 的 RetryPolicy
        if is_retryable(category):
            return RecoveryAction.RETRY

        return RecoveryAction.GIVE_UP

    def adjust_for_max_output(
        self,
        kwargs: dict[str, Any],
        attempt: int = 0,
    ) -> dict[str, Any]:
        """
        递增 max_tokens 参数。

        策略：每次增加 50%，最大不超过 16384。

        :param kwargs: 当前 LLM 调用参数
        :param attempt: 当前输出 token 重试次数
        :returns: 更新后的参数字典
        """
        current = kwargs.get("max_tokens") or 4096
        # 每次增加 50%
        new_value = min(int(current * 1.5), 16384)
        result = dict(kwargs)
        result["max_tokens"] = new_value
        logger.info(f"调整 max_tokens: {current} → {new_value}")
        return result

    def extract_token_gap(self, error: Exception) -> int | None:
        """从错误消息解析 token 差额"""
        import re
        msg = str(error)

        # 格式: "requested X tokens ... maximum Y"
        m = re.search(r"requested\s+(\d+).*?maximum.*?(\d+)", msg, re.I)
        if m:
            return int(m.group(1)) - int(m.group(2))

        # 格式: "X tokens > Y"
        m = re.search(r"(\d+)\s+tokens?\s*>\s*(\d+)", msg, re.I)
        if m:
            return int(m.group(1)) - int(m.group(2))

        return None

    def reset(self) -> None:
        """重置内部计数器（成功调用后调用）"""
        self._output_token_attempts = 0
