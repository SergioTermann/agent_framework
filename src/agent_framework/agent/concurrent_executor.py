"""
并发工具执行器 —— 借鉴 Claude Code 的 StreamingToolExecutor

核心思想：
  工具声明 `concurrency_safe` 属性，安全的工具并行执行，不安全的排队。

设计参考：
  - Claude Code 的 StreamingToolExecutor
  - 工具声明 isConcurrencySafe() 决定并发行为
  - 状态追踪: queued → executing → completed → yielded
  - 子 abort controller 防止工具级联失败

实现：
  - 使用 concurrent.futures.ThreadPoolExecutor 管理并发
  - 支持超时控制和取消
  - 提供进度回调，实时反馈工具执行状态
"""

from __future__ import annotations

import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future, as_completed, TimeoutError
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from agent_framework.tool.middleware import ToolExecutionBlockedError

logger = logging.getLogger(__name__)


# ─── 级联取消控制器（借鉴 Claude Code 的 sibling abort controller）──────────

class SiblingAbortController:
    """
    Bash 工具失败时级联取消同批次其他工具。

    当一个 Bash 类工具执行失败时，继续执行同批次其他工具通常没有意义
    （例如：第一步编译失败，后续的运行/测试步骤应被取消）。

    用法：
        controller = SiblingAbortController()

        # 在每个并行任务中
        controller.check_or_raise()  # 未取消则通过
        result = execute_tool(...)
        if result.failed:
            controller.abort("bash", "compilation failed")
    """

    def __init__(self):
        self._abort_event = threading.Event()
        self._error_source: str | None = None
        self._error_message: str | None = None
        self._lock = threading.Lock()

    def abort(self, source_tool: str, error: str) -> None:
        """
        触发取消信号。

        :param source_tool: 触发取消的工具名称
        :param error: 错误描述
        """
        with self._lock:
            if not self._abort_event.is_set():
                self._error_source = source_tool
                self._error_message = error
                self._abort_event.set()
                logger.info(
                    f"级联取消触发: {source_tool} 失败 → 取消同批次其他工具"
                )

    def is_aborted(self) -> bool:
        """检查是否已取消"""
        return self._abort_event.is_set()

    def check_or_raise(self) -> None:
        """未取消则通过，已取消则抛异常"""
        if self._abort_event.is_set():
            raise SiblingAbortError(
                f"Cancelled due to sibling tool failure: "
                f"{self._error_source}: {self._error_message}"
            )

    @property
    def error_source(self) -> str | None:
        return self._error_source

    @property
    def error_message(self) -> str | None:
        return self._error_message


class SiblingAbortError(Exception):
    """级联取消异常"""
    pass


# ─── 工具执行状态（借鉴 Claude Code: queued → executing → completed → yielded）─

class ToolExecStatus(Enum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class ToolExecResult:
    """单个工具执行结果"""
    call_id: str
    name: str
    arguments: dict[str, Any]
    status: ToolExecStatus
    result: Any = None
    error: str | None = None
    error_type: str | None = None
    error_details: dict[str, Any] | None = None
    elapsed_ms: float = 0.0
    concurrency_safe: bool = True


@dataclass
class ConcurrentExecReport:
    """并发执行报告"""
    results: list[ToolExecResult]
    total_elapsed_ms: float
    parallel_count: int      # 并行执行的工具数
    sequential_count: int    # 串行执行的工具数

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.status == ToolExecStatus.COMPLETED)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if r.status in {
            ToolExecStatus.FAILED, ToolExecStatus.TIMED_OUT
        })

    @property
    def cancelled_count(self) -> int:
        return sum(1 for r in self.results if r.status == ToolExecStatus.CANCELLED)


# ─── ConcurrentToolExecutor ─────────────────────────────────────────────

class ConcurrentToolExecutor:
    """
    并发工具执行器。

    借鉴 Claude Code 的 StreamingToolExecutor 模式：
      - 工具声明是否可并发（concurrency_safe）
      - 可并发的工具用线程池并行执行
      - 不可并发的工具串行执行（独占锁）
      - 所有结果按原始调用顺序返回

    用法：
        executor = ConcurrentToolExecutor(registry, max_workers=4)
        results = executor.execute_batch(tool_calls)

        for result in results:
            if result.status == ToolExecStatus.COMPLETED:
                print(f"{result.name}: {result.result}")
            else:
                print(f"{result.name}: 失败 - {result.error}")
    """

    def __init__(
        self,
        registry,    # ToolRegistry 实例
        max_workers: int = 4,
        tool_timeout: float = 60.0,
        on_progress: Optional[Callable[[str, str, ToolExecStatus], None]] = None,
    ):
        """
        :param registry: 工具注册表
        :param max_workers: 最大并发工作线程数
        :param tool_timeout: 单个工具的执行超时时间（秒）
        :param on_progress: 进度回调 (call_id, tool_name, status)
        """
        self.registry = registry
        self.max_workers = max_workers
        self.tool_timeout = tool_timeout
        self._on_progress = on_progress
        self._sequential_lock = threading.Lock()

    def execute_batch(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[ToolExecResult]:
        """
        批量执行工具调用，自动决定并行/串行。

        :param tool_calls: 工具调用列表，每个元素包含:
            - call_id: str
            - name: str
            - arguments: dict

        :returns: 按原始顺序返回的执行结果列表
        """
        if not tool_calls:
            return []

        # 单个工具直接执行，无需线程池
        if len(tool_calls) == 1:
            return [self._execute_single(tool_calls[0])]

        # 分组：并发安全 vs 需串行
        safe_calls = []
        sequential_calls = []

        for tc in tool_calls:
            name = tc.get("name", "")
            spec = self.registry.get(name) if name in self.registry else None
            is_safe = getattr(spec, "concurrency_safe", True) if spec else True

            if is_safe:
                safe_calls.append(tc)
            else:
                sequential_calls.append(tc)

        start_time = time.monotonic()

        # 用字典存储结果，最后按原始顺序返回
        results_map: dict[str, ToolExecResult] = {}

        # 阶段 1：并发执行安全工具
        if safe_calls:
            parallel_results = self._execute_parallel(safe_calls)
            for r in parallel_results:
                results_map[r.call_id] = r

        # 阶段 2：串行执行不安全工具
        for tc in sequential_calls:
            result = self._execute_single(tc, require_lock=True)
            results_map[result.call_id] = result

        # 按原始顺序排列
        ordered_results = []
        for tc in tool_calls:
            call_id = tc.get("call_id", "")
            if call_id in results_map:
                ordered_results.append(results_map[call_id])

        total_elapsed = (time.monotonic() - start_time) * 1000

        logger.info(
            f"并发执行完成: {len(safe_calls)} 并行 + "
            f"{len(sequential_calls)} 串行, "
            f"总耗时 {total_elapsed:.0f}ms"
        )

        return ordered_results

    # Bash 类工具名称集合（失败时触发级联取消）
    _BASH_TOOLS = {"bash", "execute_command", "shell", "run_command"}

    def _execute_parallel(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[ToolExecResult]:
        """并行执行多个工具（支持级联取消）"""
        results: list[ToolExecResult] = []
        abort_controller = SiblingAbortController()

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(tool_calls))) as pool:
            future_to_call: dict[Future, dict] = {}

            for tc in tool_calls:
                self._emit_progress(tc.get("call_id", ""), tc.get("name", ""), ToolExecStatus.QUEUED)
                future = pool.submit(self._execute_tool, tc, abort_controller=abort_controller)
                future_to_call[future] = tc

            for future in as_completed(future_to_call):
                tc = future_to_call[future]
                try:
                    result = future.result(timeout=self.tool_timeout)
                    results.append(result)

                    # Bash 类工具失败时触发级联取消
                    if (
                        result.status == ToolExecStatus.FAILED
                        and result.name in self._BASH_TOOLS
                    ):
                        abort_controller.abort(
                            result.name,
                            result.error or "unknown error",
                        )

                except TimeoutError:
                    results.append(ToolExecResult(
                        call_id=tc.get("call_id", ""),
                        name=tc.get("name", ""),
                        arguments=tc.get("arguments", {}),
                        status=ToolExecStatus.TIMED_OUT,
                        error=f"工具执行超时 ({self.tool_timeout}s)",
                        error_type="TimeoutError",
                    ))
                    self._emit_progress(
                        tc.get("call_id", ""), tc.get("name", ""),
                        ToolExecStatus.TIMED_OUT,
                    )
                except Exception as e:
                    results.append(ToolExecResult(
                        call_id=tc.get("call_id", ""),
                        name=tc.get("name", ""),
                        arguments=tc.get("arguments", {}),
                        status=ToolExecStatus.FAILED,
                        error=str(e),
                        error_type=type(e).__name__,
                    ))
                    self._emit_progress(
                        tc.get("call_id", ""), tc.get("name", ""),
                        ToolExecStatus.FAILED,
                    )

        return results

    def _execute_single(
        self,
        tc: dict[str, Any],
        require_lock: bool = False,
    ) -> ToolExecResult:
        """执行单个工具（可选串行锁）"""
        if require_lock:
            with self._sequential_lock:
                return self._execute_tool(tc)
        return self._execute_tool(tc)

    def _execute_tool(self, tc: dict[str, Any], abort_controller: SiblingAbortController | None = None) -> ToolExecResult:
        """实际执行单个工具调用（支持级联取消检查）"""
        call_id = tc.get("call_id", "")
        name = tc.get("name", "")
        args = tc.get("arguments", {})

        # 执行前检查是否已被级联取消
        if abort_controller and abort_controller.is_aborted():
            self._emit_progress(call_id, name, ToolExecStatus.CANCELLED)
            return ToolExecResult(
                call_id=call_id,
                name=name,
                arguments=args,
                status=ToolExecStatus.CANCELLED,
                error=f"Cancelled: sibling tool '{abort_controller.error_source}' failed",
                error_type="SiblingAbortError",
            )

        self._emit_progress(call_id, name, ToolExecStatus.EXECUTING)
        start_time = time.monotonic()

        try:
            if name not in self.registry:
                return ToolExecResult(
                    call_id=call_id,
                    name=name,
                    arguments=args,
                    status=ToolExecStatus.FAILED,
                    error=f"工具 '{name}' 未注册",
                    error_type="ToolNotFoundError",
                )

            result = self.registry.dispatch(name, args)
            elapsed = (time.monotonic() - start_time) * 1000

            self._emit_progress(call_id, name, ToolExecStatus.COMPLETED)

            return ToolExecResult(
                call_id=call_id,
                name=name,
                arguments=args,
                status=ToolExecStatus.COMPLETED,
                result=str(result) if result is not None else "null",
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000

            self._emit_progress(call_id, name, ToolExecStatus.FAILED)

            error_details = None
            if isinstance(e, ToolExecutionBlockedError):
                error_details = {
                    "decision": e.decision,
                    "metadata": e.metadata,
                    "arguments": e.arguments,
                    "tool_name": e.tool_name,
                }

            return ToolExecResult(
                call_id=call_id,
                name=name,
                arguments=args,
                status=ToolExecStatus.FAILED,
                error=str(e),
                error_type=type(e).__name__,
                error_details=error_details,
                elapsed_ms=elapsed,
            )

    def _emit_progress(
        self,
        call_id: str,
        name: str,
        status: ToolExecStatus,
    ) -> None:
        """发送进度通知"""
        if self._on_progress:
            try:
                self._on_progress(call_id, name, status)
            except Exception:
                pass  # 进度回调错误不影响执行
