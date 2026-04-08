"""
Factor 6  ── 启动 / 暂停 / 恢复
Factor 8  ── 掌控控制流
Factor 9  ── 将错误压缩进上下文窗口
Factor 10 ── 小而专注的 Agent
Factor 12 ── 无状态 Reducer

AgentRunner 是 Agent 的控制流引擎：
  - 自己写 while 循环，不交给框架决定何时继续或中断
  - Runner 自身无状态，全部状态在 Thread 中（Factor 12）
  - 每个 Runner 实例对应一个"小而专注"的 Agent（Factor 10）
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field, replace as dc_replace
from typing import Any, Callable, Optional

from agent_framework.agent.context import build_context_messages, should_flush_memories
from agent_framework.agent.compaction import CompactionService, CompactionConfig, CompactionResult
from agent_framework.agent.llm import LLMProvider, LLMResponse
from agent_framework.agent.prompts import PromptTemplate, DEFAULT_SYSTEM_PROMPT, ERROR_NOTICE_TEMPLATE
from agent_framework.agent.store import FileSystemStore, ThreadStore
from agent_framework.agent.thread import Thread
from agent_framework.agent.concurrent_executor import ConcurrentToolExecutor, ToolExecStatus, ToolExecResult
from agent_framework.agent.resilience import (
    ResilientLLMWrapper,
    RetryPolicy,
    CircuitBreaker,
    ModelFallbackChain,
    FallbackModel,
    classify_error,
    is_retryable,
    ErrorCategory,
    RecoveryAction,
    ContextAwareRecovery,
)
from agent_framework.tool.registry import (
    BUILTIN_TOOLS,
    DONE_TOOL,
    PAUSE_TOOL_NAMES,
    ToolRegistry,
)
from agent_framework.agent.callbacks import CallbackManager
from agent_framework.memory.system import get_memory_manager, get_file_memory_layer
from agent_framework.memory.config import MEMORY_CONFIG

logger = logging.getLogger(__name__)


# ─── 控制信号 ──────────────────────────────────────────────────────────────────

class Signal:
    """Runner 内部控制信号（Factor 8：掌控控制流）"""
    CONTINUE  = "continue"    # 继续下一轮 LLM 调用
    PAUSE     = "pause"       # 暂停，等待人类输入
    DONE      = "done"        # 任务完成，退出循环
    ESCALATE  = "escalate"    # 错误升级，强制停止


# ─── 运行配置 ──────────────────────────────────────────────────────────────────

@dataclass
class RunConfig:
    """AgentRunner 行为配置（Factor 10：约束 Agent 规模）"""

    max_rounds: int = 20
    """最大 LLM 调用轮次，防止失控循环（Factor 10）"""

    max_consecutive_errors: int = 3
    """连续工具错误阈值，超过后上升到人工处理（Factor 9）"""

    agent_name: str = "Agent"
    agent_role: str = "一个通用 AI 助手，使用工具帮助用户完成任务"

    system_prompt_template: PromptTemplate = field(
        default_factory=lambda: DEFAULT_SYSTEM_PROMPT
    )

    verbose: bool = False
    """是否输出详细日志"""

    prefetch_context: str | None = None
    """
    Factor 13: 预取上下文字符串（在 Prompt 构建阶段直接注入）。
    适用于"几乎必然会查询"的信息（如配置文件、当前用户信息）。
    """

    # LLM 生成参数
    temperature: float = 0.7
    """采样温度 (0.0-2.0)，越高越随机"""

    max_tokens: int | None = None
    """最大生成 token 数，None 表示使用模型默认值"""

    top_p: float = 1.0
    """核采样参数 (0.0-1.0)"""

    frequency_penalty: float = 0.0
    """频率惩罚 (-2.0-2.0)，降低重复内容"""

    presence_penalty: float = 0.0
    """存在惩罚 (-2.0-2.0)，鼓励谈论新话题"""

    stream: bool = False
    """是否启用流式输出"""

    on_stream_chunk: Optional[Callable[[str], None]] = None
    """流式输出回调函数，接收每个文本块"""

    callbacks: Optional[CallbackManager] = None
    """回调管理器"""

    # ── 并发工具执行配置（借鉴 Claude Code StreamingToolExecutor）──────────
    concurrent_tools: bool = True
    """是否启用工具并发执行"""

    max_tool_workers: int = 4
    """工具并发执行的最大工作线程数"""

    tool_timeout: float = 60.0
    """单个工具执行的超时时间（秒）"""

    on_tool_progress: Optional[Callable[[str, str, str], None]] = None
    max_tool_result_chars: int = 4000
    """工具执行进度回调: (call_id, tool_name, status)"""

    # ── 韧性配置（借鉴 Claude Code 的 withRetry + 模型降级）─────────────────
    enable_resilience: bool = True
    """是否启用韧性包装（重试 + 断路器）"""

    retry_max_attempts: int = 3
    """LLM 调用最大重试次数"""

    retry_base_delay: float = 1.0
    """重试基础退避延迟（秒）"""

    fallback_models: list[str] = field(default_factory=list)
    """降级模型列表（如 ["gpt-4o-mini", "gpt-3.5-turbo"]）"""

    circuit_breaker_threshold: int = 5
    """断路器连续失败阈值"""

    circuit_breaker_timeout: float = 30.0
    """断路器冷却时间（秒）"""

    # ── 上下文压缩配置（借鉴 Claude Code compaction）─────────────────────────
    enable_compaction: bool = True
    """是否启用智能上下文压缩"""

    compaction_threshold: float = 0.85
    """token 使用率超过此值时触发自动压缩"""

    context_window_tokens: int = 128_000
    """模型上下文窗口大小（token）"""

    microcompact_threshold: int = 3000
    """单个工具结果超此 token 数触发微压缩"""


# ─── 记忆钩子（三层架构自动行为）──────────────────────────────────────────────

class MemoryHooks:
    """
    封装三层记忆架构的自动行为：
    - build_memory_context: 加载 MEMORY.md + 每日笔记
    - auto_recall: 语义搜索相关记忆
    - auto_capture: 每轮结束后提取关键信息写入每日笔记
    - auto_flush: 上下文压缩前持久化重要信息
    """

    def __init__(self):
        self.config = MEMORY_CONFIG
        self.file_memory = get_file_memory_layer()
        self.memory_manager = get_memory_manager()

    def build_memory_context(self) -> str | None:
        """加载 MEMORY.md + 最近每日笔记，返回注入字符串"""
        if not self.config.get('file_memory', {}).get('enabled', True):
            return None

        parts = []

        # 加载 MEMORY.md
        memory_md = self.file_memory.load_memory_md()
        if memory_md.strip():
            parts.append(f"[MEMORY.md]\n{memory_md}")

        # 加载最近每日笔记
        days = self.config.get('file_memory', {}).get('daily_notes_load_days', 2)
        daily_notes = self.file_memory.load_daily_notes(days=days)
        if daily_notes.strip():
            parts.append(f"[最近每日笔记]\n{daily_notes}")

        return "\n\n".join(parts) if parts else None

    def auto_recall(self, query: str) -> str | None:
        """SQLite 语义搜索相关记忆，格式化返回注入字符串"""
        recall_config = self.config.get('auto_recall', {})
        if not recall_config.get('enabled', True):
            return None

        if not query or len(query.strip()) < 5:
            return None

        try:
            max_memories = recall_config.get('max_injected_memories', 3)
            results = self.memory_manager.recall_relevant_memories(
                query=query,
                context={"metadata": {"assistant_profile": "general"}},
                limit=max_memories,
            )

            if not results:
                return None

            lines = []
            for memory in results:
                lines.append(f"- [{memory.memory_type}] (重要度:{memory.importance:.2f}) {memory.content}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"自动回忆失败: {e}")
            return None

    def auto_capture(self, thread: Thread) -> None:
        """提取最近事件中的用户消息/助手回复，写入每日笔记"""
        capture_config = self.config.get('auto_capture', {})
        if not capture_config.get('enabled', True):
            return

        min_length = capture_config.get('min_content_length', 20)

        # 取最近的事件（最后几条）
        recent = thread.events[-5:] if len(thread.events) > 5 else thread.events

        for event in recent:
            content = ""
            if event.type == "user_message":
                content = event.data.get("content", "")
                prefix = "用户"
            elif event.type == "assistant_message":
                content = event.data.get("content", "")
                prefix = "助手"
            else:
                continue

            if len(content) < min_length:
                continue

            # 截取摘要
            summary = content[:200] + "..." if len(content) > 200 else content

            # 写入每日笔记
            if capture_config.get('save_to_daily_notes', True):
                try:
                    self.file_memory.append_daily_note(f"{prefix}: {summary}")
                except Exception as e:
                    logger.warning(f"自动捕获写入每日笔记失败: {e}")

    def auto_flush(self, thread: Thread) -> None:
        """从最近事件中提取关键信息，写入每日笔记 + MEMORY.md"""
        flush_config = self.config.get('auto_flush', {})
        if not flush_config.get('enabled', True):
            return

        # 收集本次会话中的关键交互摘要
        summaries = []
        for event in thread.events:
            if event.type == "user_message":
                content = event.data.get("content", "")
                if len(content) > 30:
                    summaries.append(f"Q: {content[:150]}")
            elif event.type == "assistant_message":
                content = event.data.get("content", "")
                if len(content) > 50:
                    summaries.append(f"A: {content[:150]}")

        if not summaries:
            return

        # 写入每日笔记
        flush_note = "[自动刷写] 会话摘要:\n" + "\n".join(summaries[:10])
        try:
            self.file_memory.append_daily_note(flush_note)
        except Exception as e:
            logger.warning(f"自动刷写到每日笔记失败: {e}")


# ─── Runner ────────────────────────────────────────────────────────────────────

class AgentRunner:
    """
    Agent 控制流引擎。

    核心思想（Factor 8）：
        while True:
            llm 决策 → 分发工具 → 结果写入 Thread → 决定控制信号
        信号 CONTINUE → 继续
        信号 PAUSE    → 保存 Thread，等待外部 resume()
        信号 DONE     → 正常结束
        信号 ESCALATE → 错误超阈值，强制停止，等待人工介入

    Runner 本身无状态（Factor 12），所有状态在 Thread 中。
    """

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        store: Optional[ThreadStore] = None,
        config: Optional[RunConfig] = None,
        on_human_request: Optional[Callable[[Thread, dict], None]] = None,
    ):
        self.llm = llm
        self.tools = tools
        self.store = store or FileSystemStore()
        self.config = config or RunConfig()
        # Factor 7: 人类请求触发的外部回调（可替换为 Slack/Email/钉钉推送）
        self._on_human_request = on_human_request

        if config and config.verbose:
            logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

        # ── 初始化并发工具执行器 ────────────────────────────────────────────
        self._concurrent_executor: Optional[ConcurrentToolExecutor] = None
        if self.config.concurrent_tools:
            progress_cb = None
            if self.config.on_tool_progress:
                user_cb = self.config.on_tool_progress
                progress_cb = lambda cid, name, status: user_cb(cid, name, status.value)
            self._concurrent_executor = ConcurrentToolExecutor(
                registry=self.tools,
                max_workers=self.config.max_tool_workers,
                tool_timeout=self.config.tool_timeout,
                on_progress=progress_cb,
            )

        # ── 初始化韧性包装 ──────────────────────────────────────────────────
        self._resilient_llm: Optional[ResilientLLMWrapper] = None
        if self.config.enable_resilience:
            retry_policy = RetryPolicy(
                max_retries=self.config.retry_max_attempts,
                base_delay=self.config.retry_base_delay,
            )
            circuit_breaker = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_threshold,
                recovery_timeout=self.config.circuit_breaker_timeout,
                name="llm",
            ) if self.config.circuit_breaker_threshold > 0 else None

            fallback_chain = None
            if self.config.fallback_models:
                fallback_chain = ModelFallbackChain(
                    fallbacks=[FallbackModel(model=m) for m in self.config.fallback_models],
                )

            self._resilient_llm = ResilientLLMWrapper(
                llm=self.llm,
                retry_policy=retry_policy,
                circuit_breaker=circuit_breaker,
                fallback_chain=fallback_chain,
            )

        # ── 初始化上下文压缩服务 ──────────────────────────────────────────
        self._compaction: Optional[CompactionService] = None
        if self.config.enable_compaction:
            self._compaction = CompactionService(CompactionConfig(
                auto_compact_threshold=self.config.compaction_threshold,
                context_window_tokens=self.config.context_window_tokens,
                microcompact_threshold=self.config.microcompact_threshold,
            ))

        # ── 初始化上下文感知错误恢复 ──────────────────────────────────────
        self._recovery = ContextAwareRecovery()

    # ── 公开 API（Factor 6：启动 / 暂停 / 恢复）──────────────────────────────

    def launch(
        self,
        user_input: str,
        thread_id: str | None = None,
        prefetch_context: str | None = None,
    ) -> Thread:
        """
        启动一个新的 Agent 任务。
        返回运行结束后的 Thread（可能是 DONE / PAUSE 状态）。
        """
        thread = Thread()
        if thread_id:
            thread.thread_id = thread_id

        thread.push("system", {"event": "launched"})
        thread.push("user_message", {"content": user_input})
        self.store.save(thread)

        cfg = self.config
        if prefetch_context:
            cfg = dc_replace(cfg, prefetch_context=prefetch_context)

        return self._run_loop(thread, cfg)

    def resume(
        self,
        thread_id: str,
        human_response: str | None = None,
    ) -> Thread:
        """
        恢复暂停中的 Agent。
        human_response: 人类对上次 human_input_request 的回答。
        """
        thread = self.store.load(thread_id)
        if thread is None:
            raise ValueError(f"Thread 不存在: {thread_id}")
        if not thread.is_paused():
            raise ValueError(f"Thread {thread_id} 未处于暂停状态")

        if human_response is not None:
            last_req = thread.last_of_type("human_input_request")
            thread.push("human_input_response", {
                "response": human_response,
                "responding_to": last_req.event_id if last_req else "",
            })

        thread.push("system", {"event": "resumed"})
        self.store.save(thread)
        return self._run_loop(thread, self.config)

    def status(self, thread_id: str) -> dict:
        """查询 Thread 状态摘要"""
        thread = self.store.load(thread_id)
        if thread is None:
            return {"thread_id": thread_id, "status": "not_found"}

        last = thread.events[-1] if thread.events else None
        return {
            "thread_id": thread_id,
            "status": "paused" if thread.is_paused() else
                      ("done" if thread.is_done() else "active"),
            "event_count": len(thread.events),
            "last_event_type": last.type if last else None,
            "created_at": thread.created_at,
        }

    # ── 核心循环（Factor 8：掌控控制流）──────────────────────────────────────

    def _run_loop(self, thread: Thread, config: RunConfig) -> Thread:
        """
        自己写 while 循环，而非交给框架决定。

        不同工具有不同的控制策略（Factor 8）：
          - 普通工具   → CONTINUE（同步执行，立即继续）
          - done 工具  → DONE（正常完成）
          - 人类交互   → PAUSE（异步等待，保存 Thread）
          - 错误超阈值 → ESCALATE（升级处理）

        三层记忆架构集成：
          - 循环开始前：加载 MEMORY.md + 每日笔记
          - 每轮循环：检查 flush → 自动回忆 → 注入上下文 → LLM → 自动捕获
        """
        # 局部可变拷贝，防止 INCREASE_TOKENS 等恢复动作永久修改共享 config
        config = dc_replace(config)

        # 构建工具 schema（用户工具 + 内置工具）
        tools_schema = [
            *self.tools.to_llm_format(),
            *[t.to_llm_format() for t in BUILTIN_TOOLS],
        ]

        # 初始化记忆钩子
        memory_hooks = MemoryHooks()
        memory_context = memory_hooks.build_memory_context()
        flushed = False

        for round_num in range(config.max_rounds):
            self._log(config, f"Round {round_num + 1} | Thread {thread.thread_id[:8]}")

            # 触发轮次开始回调
            if config.callbacks:
                config.callbacks.trigger("round_start", {
                    "round": round_num + 1,
                    "max_rounds": config.max_rounds,
                }, thread.thread_id)

            # 三层记忆：检查是否需要在压缩前刷写
            flush_threshold = MEMORY_CONFIG.get('auto_flush', {}).get('event_threshold', 30)
            if not flushed and should_flush_memories(thread, threshold=flush_threshold):
                memory_hooks.auto_flush(thread)
                flushed = True

            # Factor 9: 检查连续错误，超阈值则升级
            errs = thread.consecutive_errors()
            if errs >= config.max_consecutive_errors:
                last_err = thread.last_of_type("error")
                err_notice = ERROR_NOTICE_TEMPLATE.render(
                    error_count=errs,
                    threshold=config.max_consecutive_errors,
                    last_error=last_err.data.get("message", "") if last_err else "",
                )
                # 将升级提示注入上下文，给 LLM 一次最终自救机会
                thread.push("user_message", {"content": err_notice})
                thread.push("system", {
                    "event": "error_escalated",
                    "consecutive_errors": errs,
                })
                self.store.save(thread)
                self._log(config, f"连续错误 {errs} 次，已升级停止")
                return thread

            # ── 自动上下文压缩检查（借鉴 Claude Code compaction）─────────
            if self._compaction and self._compaction.should_auto_compact(thread, config):
                # 先做微压缩（截断超大工具结果）
                self._compaction.microcompact_tool_results(thread)
                # 如果微压缩后仍然超阈值，做 LLM 摘要压缩
                if self._compaction.should_auto_compact(thread, config):
                    llm_for_compact = self._resilient_llm or self.llm
                    compact_result = self._compaction.compact(
                        thread, llm_for_compact,
                    )
                    if compact_result.success:
                        self._log(
                            config,
                            f"上下文压缩: {compact_result.events_before} → "
                            f"{compact_result.events_after} 事件, "
                            f"节省 ~{compact_result.tokens_saved} tokens"
                        )

            # 构建上下文（Factor 3）
            system_prompt = config.system_prompt_template.render(
                agent_name=config.agent_name,
                agent_role=config.agent_role,
                tools_description=self.tools.describe(),
            )

            # 三层记忆：自动回忆（从最近用户消息中提取查询）
            recalled_memories = None
            last_user_msg = thread.last_of_type("user_message")
            if last_user_msg:
                user_query = last_user_msg.data.get("content", "")
                recalled_memories = memory_hooks.auto_recall(user_query)

            messages = build_context_messages(
                thread=thread,
                system_prompt=system_prompt,
                tools_schema=tools_schema,
                prefetch_context=config.prefetch_context,
                memory_context=memory_context,
                recalled_memories=recalled_memories,
            )

            # 调用 LLM（Factor 1）—— 使用韧性包装（重试 + 断路器 + 模型降级）
            try:
                # 触发 LLM 开始回调
                if config.callbacks:
                    config.callbacks.trigger("llm_start", {
                        "messages_count": len(messages),
                        "temperature": config.temperature,
                    }, thread.thread_id)

                # 准备流式回调
                def stream_callback(chunk_content: str):
                    if config.on_stream_chunk:
                        config.on_stream_chunk(chunk_content)

                # 选择 LLM 实例：优先使用韧性包装
                llm_instance = self._resilient_llm or self.llm

                response = llm_instance.chat(
                    messages,
                    tools=tools_schema,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    top_p=config.top_p,
                    frequency_penalty=config.frequency_penalty,
                    presence_penalty=config.presence_penalty,
                    stream=config.stream,
                    on_chunk=lambda chunk: stream_callback(chunk.content) if chunk.content else None,
                )

                # 触发 LLM 结束回调
                if config.callbacks:
                    config.callbacks.trigger("llm_end", {
                        "content": response.content,
                        "tool_calls_count": len(response.tool_calls),
                        "usage": response.usage,
                    }, thread.thread_id)

            except Exception as e:
                # 触发 LLM 错误回调
                if config.callbacks:
                    config.callbacks.trigger("llm_error", {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }, thread.thread_id)

                # 上下文感知错误恢复
                recovery = self._recovery.classify_and_plan(
                    e, attempt=round_num, config=config,
                )

                if recovery == RecoveryAction.COMPACT_AND_RETRY and self._compaction:
                    self._log(config, f"LLM 调用失败 (context_too_long), 尝试压缩后重试")
                    compact_result = self._compaction.reactive_compact(
                        thread, self._resilient_llm or self.llm, e,
                    )
                    if compact_result.success:
                        continue  # 压缩成功，重试本轮

                elif recovery == RecoveryAction.INCREASE_TOKENS:
                    adjusted = self._recovery.adjust_for_max_output(
                        {"max_tokens": config.max_tokens}, attempt=round_num,
                    )
                    config.max_tokens = adjusted["max_tokens"]
                    self._log(config, f"LLM 调用失败 (max_tokens), 增加到 {config.max_tokens}")
                    continue

                elif recovery == RecoveryAction.GIVE_UP:
                    thread.push("error", {
                        "message": str(e),
                        "type": type(e).__name__,
                        "recovery": "give_up",
                    })
                    self.store.save(thread)
                    self._log(config, f"LLM 调用失败 (不可恢复): {e}")
                    return thread

                # RETRY 或其他情况：记录错误并继续
                thread.push("error", {"message": str(e), "type": type(e).__name__})
                self.store.save(thread)
                self._log(config, f"LLM 调用失败: {e}")
                continue

            # LLM 调用成功后重置恢复计数器
            if self._compaction:
                self._compaction.reset_ptl_counter()
            self._recovery.reset()

            # 处理响应，获取控制信号
            signal = self._handle_response(thread, response)
            self.store.save(thread)

            if signal == Signal.DONE:
                return thread

            if signal == Signal.PAUSE:
                # Factor 7: 触发外部通知（Slack / Email 等）
                if self._on_human_request:
                    req = thread.last_of_type("human_input_request")
                    if req:
                        self._on_human_request(thread, req.data)
                return thread

            if signal == Signal.ESCALATE:
                return thread

            # 三层记忆：每轮结束后自动捕获
            memory_hooks.auto_capture(thread)

            # Signal.CONTINUE → 继续下一轮

        # 超过最大轮次
        thread.push("system", {
            "event": "max_rounds_reached",
            "rounds": config.max_rounds,
        })
        self.store.save(thread)
        return thread

    # ── 响应分发（Factor 4：工具调度 = 字典查表 + 并发执行）───────────────────

    def _handle_response(self, thread: Thread, response: LLMResponse) -> str:
        """
        分发 LLM 响应，返回控制信号。

        设计原则（Factor 8 + 并发执行）：
          - 每种工具可以有独立的控制策略
          - 内置工具（pause/done）立即处理，不进入并发池
          - 普通工具通过 ConcurrentToolExecutor 并行执行
          - 不依赖框架的魔法，显式控制流

        借鉴 Claude Code 的 StreamingToolExecutor：
          - 工具声明 concurrency_safe 决定并行/串行
          - 并行工具用线程池执行，串行工具用独占锁
          - 结果按原始调用顺序写入 Thread
        """
        if not response.has_tool_calls:
            # 纯文本回复 → 视为任务完成
            thread.push("assistant_message", {"content": response.content or ""})
            return Signal.DONE

        # 将本轮所有工具调用记录为一个 llm_response 事件（保持 call_id 配对）
        thread.push("llm_response", {
            "content": response.content,
            "tool_calls": [
                {
                    "call_id": tc.call_id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
                for tc in response.tool_calls
            ],
        })

        # 第一阶段：处理内置工具（pause/done），这些不进并发池
        builtin_calls = []
        normal_calls = []

        for tc in response.tool_calls:
            if tc.name in PAUSE_TOOL_NAMES or tc.name == DONE_TOOL.name:
                builtin_calls.append(tc)
            else:
                normal_calls.append(tc)

        # 内置工具优先处理（它们会改变控制流）
        for tc in builtin_calls:
            call_id = tc.call_id
            name = tc.name
            args = tc.arguments

            self._log(self.config, f"内置工具: {name}({args})")

            if name in PAUSE_TOOL_NAMES:
                question = args.get("action") or args.get("question", "需要您的输入")
                thread.push("human_input_request", {
                    "call_id": call_id,
                    "tool": name,
                    "question": question,
                    "details": args,
                })
                return Signal.PAUSE

            if name == DONE_TOOL.name:
                thread.push("tool_result", {
                    "call_id": call_id,
                    "name": name,
                    "result": args.get("result", "任务完成"),
                })
                thread.push("system", {
                    "event": "done",
                    "success": args.get("success", True),
                    "result": args.get("result", ""),
                })

                if self.config.callbacks:
                    self.config.callbacks.trigger("tool_call_end", {
                        "tool_name": name,
                        "result": args.get("result", "任务完成"),
                        "call_id": call_id,
                    }, thread.thread_id)

                return Signal.DONE

        # 第二阶段：普通工具 —— 使用并发执行器（多工具并行）
        if not normal_calls:
            return Signal.CONTINUE

        # 触发所有工具的开始回调
        for tc in normal_calls:
            self._log(self.config, f"工具调用: {tc.name}({tc.arguments})")
            if self.config.callbacks:
                self.config.callbacks.trigger("tool_call_start", {
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                    "call_id": tc.call_id,
                }, thread.thread_id)

        # 决定使用并发还是串行执行
        if self._concurrent_executor and len(normal_calls) > 1:
            # 并发执行：多个工具同时运行
            batch = [
                {"call_id": tc.call_id, "name": tc.name, "arguments": tc.arguments}
                for tc in normal_calls
            ]
            exec_results = self._concurrent_executor.execute_batch(batch)
            self._apply_exec_results(thread, exec_results)
        else:
            # 串行执行（单工具或未启用并发）
            for tc in normal_calls:
                self._execute_tool_serial(thread, tc.call_id, tc.name, tc.arguments)

        return Signal.CONTINUE

    def _apply_exec_results(
        self, thread: Thread, exec_results: list[ToolExecResult]
    ) -> None:
        """将并发执行器的结果写入 Thread"""
        for r in exec_results:
            if r.status == ToolExecStatus.COMPLETED:
                thread.push("tool_result", {
                    "call_id": r.call_id,
                    "name": r.name,
                    "result": r.result,
                })
                self._log(self.config, f"工具结果: {r.name} → {str(r.result)[:100]} ({r.elapsed_ms:.0f}ms)")

                if self.config.callbacks:
                    self.config.callbacks.trigger("tool_call_end", {
                        "tool_name": r.name,
                        "result": r.result,
                        "call_id": r.call_id,
                        "elapsed_ms": r.elapsed_ms,
                    }, thread.thread_id)
            else:
                # FAILED / TIMED_OUT / CANCELLED
                thread.push("error", {
                    "call_id": r.call_id,
                    "name": r.name,
                    "message": r.error or f"工具执行失败 ({r.status.value})",
                    "type": r.error_type or r.status.value,
                })
                self._log(self.config, f"工具错误: {r.name} → {r.error} ({r.elapsed_ms:.0f}ms)")

                if self.config.callbacks:
                    self.config.callbacks.trigger("tool_call_error", {
                        "tool_name": r.name,
                        "error": r.error,
                        "error_type": r.error_type or r.status.value,
                        "call_id": r.call_id,
                    }, thread.thread_id)

    def _execute_tool_serial(
        self, thread: Thread, call_id: str, name: str, args: dict
    ) -> None:
        """串行执行单个工具（兼容旧路径）"""
        if name not in self.tools:
            thread.push("error", {
                "call_id": call_id,
                "name": name,
                "message": f"工具 '{name}' 未注册",
                "type": "ToolNotFoundError",
            })
            return

        try:
            result = self.tools.dispatch(name, args)
            thread.push("tool_result", {
                "call_id": call_id,
                "name": name,
                "result": str(result) if result is not None else "null",
            })
            self._log(self.config, f"工具结果: {name} → {str(result)[:100]}")

            if self.config.callbacks:
                self.config.callbacks.trigger("tool_call_end", {
                    "tool_name": name,
                    "result": str(result) if result is not None else "null",
                    "call_id": call_id,
                }, thread.thread_id)

        except Exception as e:
            thread.push("error", {
                "call_id": call_id,
                "name": name,
                "message": str(e),
                "type": type(e).__name__,
            })
            self._log(self.config, f"工具错误: {name} → {e}")

            if self.config.callbacks:
                self.config.callbacks.trigger("tool_call_error", {
                    "tool_name": name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "call_id": call_id,
                }, thread.thread_id)

    @staticmethod
    def _log(config: RunConfig, msg: str) -> None:
        if config.verbose:
            logger.info(msg)
