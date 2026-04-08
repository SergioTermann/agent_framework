"""
12-Factor Agent Framework
=========================

基于 12-Factor Agents 原则的原生 Python Agent 框架，零第三方依赖。

因子对照表：
  Factor 1  自然语言 → 工具调用        llm.py
  Factor 2  掌控你的 Prompt             prompts.py
  Factor 3  掌控上下文窗口              context.py
  Factor 4  工具只是结构化输出          tools.py
  Factor 5  统一执行状态与业务状态      thread.py
  Factor 6  启动 / 暂停 / 恢复          runner.py + store.py
  Factor 7  用工具联系人类              tools.py + runner.py
  Factor 8  掌控控制流                  runner.py
  Factor 9  将错误压缩进上下文窗口      runner.py + context.py
  Factor 10 小而专注的 Agent            AgentBuilder.with_max_rounds()
  Factor 11 随处触发                    server.py
  Factor 12 无状态 Reducer              thread.py + runner.py
  Factor 13 预取上下文                  runner.launch(prefetch_context=...)

快速开始：
    from agent_framework.agent import AgentBuilder

    builder = AgentBuilder().with_openai(api_key="sk-...")

    @builder.tool(description="获取当前天气")
    def get_weather(city: str) -> str:
        return f"{city}: 晴天 22°C"

    runner = builder.build()
    thread = runner.launch("北京今天天气怎么样？")
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

# 核心模块（全部原生实现）
from agent_framework.agent.context import build_context_messages          # noqa: F401  Factor 3
from agent_framework.agent.llm import (  # noqa: F401  Factor 1
    LLMProvider,
    OpenAICompatibleProvider,
    is_local_openai_compatible_url,
)
from agent_framework.agent.prompts import (                               # noqa: F401  Factor 2
    DEFAULT_SYSTEM_PROMPT,
    FOCUSED_AGENT_PROMPT,
    CODE_AGENT_PROMPT,
    PromptTemplate,
)
from agent_framework.agent.openai_agents import OpenAIAgentsThreadRunner, agents_sdk_is_available
from agent_framework.agent.runner import AgentRunner, RunConfig           # noqa: F401  Factor 6/8/9
from agent_framework.agent.store import FileSystemStore, SQLiteStore, ThreadStore  # noqa: F401  Factor 6
from agent_framework.agent.thread import Thread                           # noqa: F401  Factor 5/12
from agent_framework.tool.registry import (                          # noqa: F401  Factor 4/7
    BUILTIN_TOOLS,
    ToolRegistry,
    ToolSpec,
)
from agent_framework.tool.middleware import (
    ToolHook,
    create_tool_hook_middleware,
    create_tool_result_limit_middleware,
)
from agent_framework.tool.permissions import ToolPermissionHook, resolve_tool_permission_rules
from agent_framework.agent.callbacks import CallbackManager, PerformanceMonitor, TokenCounter  # noqa: F401


# ─── AgentBuilder：链式 API（Factor 10：每个 Agent 职责清晰）──────────────────

class AgentBuilder:
    """
    链式构建器 —— 快速组装一个符合 12-Factor 的 Agent。

    设计原则（Factor 10）：
      每个 AgentBuilder 实例对应"一件事"的 Agent。
      通过 with_max_rounds() 限制 Agent 能力边界，避免失控的单体 Agent。

    用法：
        runner = (
            AgentBuilder()
            .with_openai(api_key="sk-...")
            .with_name("WeatherBot")
            .with_role("查询天气信息")
            .with_max_rounds(10)
            .build()
        )
    """

    def __init__(self):
        self._llm: Optional[LLMProvider] = None
        self._tools = ToolRegistry()
        self._store: Optional[ThreadStore] = None
        self._config = RunConfig()
        self._on_human_request: Optional[Callable[[Thread, dict], None]] = None
        self._agent_backend: str = "auto"
        self._tools.use(
            create_tool_result_limit_middleware(
                lambda: self._config.max_tool_result_chars
            )
        )

    # ── LLM 配置 ──────────────────────────────────────────────────────────────

    def with_openai(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 120,
    ) -> "AgentBuilder":
        """配置 OpenAI 或兼容接口（DeepSeek / Azure / Ollama 等）"""
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key and not is_local_openai_compatible_url(base_url):
            raise ValueError("缺少 API Key，请传入 api_key、设置 OPENAI_API_KEY，或改用本地 vLLM/Ollama 端点")
        self._llm = OpenAICompatibleProvider(
            api_key=resolved_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
        )
        return self

    def with_vllm(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
    ) -> "AgentBuilder":
        """配置本地/远程 vLLM OpenAI 兼容端点。"""
        resolved_base_url = (
            base_url
            or os.environ.get("VLLM_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or "http://localhost:8000/v1"
        )
        resolved_key = (
            api_key
            if api_key is not None
            else os.environ.get("VLLM_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or ""
        )
        self._llm = OpenAICompatibleProvider(
            api_key=resolved_key,
            model=model,
            base_url=resolved_base_url,
            timeout=timeout,
        )
        return self

    def with_xinference(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
    ) -> "AgentBuilder":
        """配置 Xinference OpenAI 兼容端点。"""
        resolved_base_url = (
            base_url
            or os.environ.get("XINFERENCE_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or "http://localhost:9997/v1"
        )
        resolved_key = (
            api_key
            if api_key is not None
            else os.environ.get("XINFERENCE_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or ""
        )
        self._llm = OpenAICompatibleProvider(
            api_key=resolved_key,
            model=model,
            base_url=resolved_base_url,
            timeout=timeout,
        )
        return self

    def with_llm(self, llm: LLMProvider) -> "AgentBuilder":
        """注入自定义 LLM 提供商（实现 LLMProvider 接口即可）"""
        self._llm = llm
        return self

    def with_agent_backend(self, backend: str) -> "AgentBuilder":
        """设置 Agent 执行后端：auto / openai_agents / legacy。"""
        normalized = str(backend or "").strip().lower()
        if normalized not in {"auto", "openai_agents", "legacy"}:
            raise ValueError("backend must be one of: auto, openai_agents, legacy")
        self._agent_backend = normalized
        return self

    def with_legacy_runner(self) -> "AgentBuilder":
        """强制使用 legacy runner。"""
        return self.with_agent_backend("legacy")

    # ── 工具注册（Factor 4）──────────────────────────────────────────────────

    def tool(
        self,
        name: str | None = None,
        description: str = "",
        parameters: dict | None = None,
    ):
        """
        装饰器：注册工具函数。

        用法：
            @builder.tool(description="计算两数之和")
            def add(a: int, b: int) -> int:
                return a + b
        """
        return self._tools.register(
            name=name,
            description=description,
            parameters=parameters,
        )

    def with_tool_spec(self, spec: ToolSpec) -> "AgentBuilder":
        """注入预定义的 ToolSpec（适用于动态工具生成）"""
        self._tools.add(spec)
        return self

    def with_middleware(self, middleware) -> "AgentBuilder":
        """Add a tool middleware to the dispatch chain."""
        self._tools.use(middleware)
        return self

    def with_tool_hook(self, hook: ToolHook) -> "AgentBuilder":
        """Add a structured tool hook to the dispatch chain."""
        self._tools.use(create_tool_hook_middleware([hook]))
        return self

    def with_tool_permission_rules(
        self,
        rules: Any,
    ) -> "AgentBuilder":
        """Attach ordered allow/deny/ask tool permission rules."""
        parsed = resolve_tool_permission_rules(rules)
        if not parsed:
            return self
        self._tools.use(create_tool_hook_middleware([ToolPermissionHook(parsed)]))
        return self

    # ── Agent 配置（Factor 2 / 10）────────────────────────────────────────────

    def with_name(self, name: str) -> "AgentBuilder":
        """设置 Agent 名称（注入 Prompt）"""
        self._config.agent_name = name
        return self

    def with_role(self, role: str) -> "AgentBuilder":
        """设置 Agent 职责描述（注入 Prompt）"""
        self._config.agent_role = role
        return self

    def with_prompt(self, template: PromptTemplate) -> "AgentBuilder":
        """
        Factor 2: 替换系统 Prompt。
        Prompt 作为代码：版本化、可测试、完全透明。
        """
        self._config.system_prompt_template = template
        return self

    def with_max_rounds(self, n: int) -> "AgentBuilder":
        """
        Factor 10: 限制最大 LLM 调用轮次。
        小而专注的 Agent 通常 3-20 轮即可完成任务。
        """
        self._config.max_rounds = n
        return self

    def with_error_threshold(self, n: int) -> "AgentBuilder":
        """Factor 9: 设置连续错误升级阈值（默认 3）"""
        self._config.max_consecutive_errors = n
        return self

    def with_store(self, store: ThreadStore) -> "AgentBuilder":
        """Factor 6: 自定义状态持久化后端"""
        self._store = store
        return self

    def on_human_request(
        self, handler: Callable[[Thread, dict], None]
    ) -> "AgentBuilder":
        """
        Factor 7: 注册人类请求回调。
        当 Agent 需要人类审批/输入时触发，可用于发送 Slack/Email 通知。

        handler 签名：(thread: Thread, request: dict) -> None
        """
        self._on_human_request = handler
        return self

    def with_verbose(self) -> "AgentBuilder":
        """开启详细日志输出"""
        self._config.verbose = True
        logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
        return self

    def with_compaction(
        self,
        enabled: bool = True,
        threshold: float = 0.85,
        context_window: int = 128_000,
        microcompact_threshold: int = 3000,
    ) -> "AgentBuilder":
        """
        配置智能上下文压缩（借鉴 Claude Code compaction）。

        :param enabled: 是否启用
        :param threshold: token 使用率触发阈值 (0.0-1.0)
        :param context_window: 模型上下文窗口大小
        :param microcompact_threshold: 微压缩 token 阈值
        """
        self._config.enable_compaction = enabled
        self._config.compaction_threshold = threshold
        self._config.context_window_tokens = context_window
        self._config.microcompact_threshold = microcompact_threshold
        return self

    # ── LLM 生成参数配置 ──────────────────────────────────────────────────────

    def with_temperature(self, temperature: float) -> "AgentBuilder":
        """设置采样温度 (0.0-2.0)，越高越随机"""
        self._config.temperature = temperature
        return self

    def with_max_tokens(self, max_tokens: int) -> "AgentBuilder":
        """设置最大生成 token 数"""
        self._config.max_tokens = max_tokens
        return self

    def with_top_p(self, top_p: float) -> "AgentBuilder":
        """设置核采样参数 (0.0-1.0)"""
        self._config.top_p = top_p
        return self

    def with_frequency_penalty(self, penalty: float) -> "AgentBuilder":
        """设置频率惩罚 (-2.0-2.0)，降低重复内容"""
        self._config.frequency_penalty = penalty
        return self

    def with_presence_penalty(self, penalty: float) -> "AgentBuilder":
        """设置存在惩罚 (-2.0-2.0)，鼓励谈论新话题"""
        self._config.presence_penalty = penalty
        return self

    def with_stream(self, enabled: bool = True, on_chunk: Callable[[str], None] | None = None) -> "AgentBuilder":
        """
        启用流式输出。

        :param enabled: 是否启用流式输出
        :param on_chunk: 流式输出回调函数，接收每个文本块

        用法：
            # 启用流式输出并打印到控制台
            builder.with_stream(True, lambda chunk: print(chunk, end="", flush=True))

            # 只启用流式输出
            builder.with_stream(True)
        """
        self._config.stream = enabled
        if on_chunk:
            self._config.on_stream_chunk = on_chunk
        return self

    def with_tool_result_limit(self, max_chars: int) -> "AgentBuilder":
        """Cap a single tool result before it is fed back into the model."""
        self._config.max_tool_result_chars = max(0, int(max_chars))
        return self

    def with_callbacks(self, callbacks: CallbackManager) -> "AgentBuilder":
        """
        设置回调管理器。

        用法：
            from agent_framework.agent.callbacks import CallbackManager, PerformanceMonitor

            callbacks = CallbackManager()
            monitor = PerformanceMonitor()

            callbacks.on("llm_start", monitor.on_llm_start)
            callbacks.on("llm_end", monitor.on_llm_end)

            builder.with_callbacks(callbacks)
        """
        self._config.callbacks = callbacks
        return self

    def with_performance_monitor(self) -> "AgentBuilder":
        """
        启用性能监控（快捷方法）。

        用法：
            builder.with_performance_monitor()
        """
        if not self._config.callbacks:
            self._config.callbacks = CallbackManager()

        monitor = PerformanceMonitor()
        self._config.callbacks.on("llm_start", monitor.on_llm_start)
        self._config.callbacks.on("llm_end", monitor.on_llm_end)
        self._config.callbacks.on("tool_call_start", monitor.on_tool_call_start)
        self._config.callbacks.on("tool_call_end", monitor.on_tool_call_end)
        self._config.callbacks.on("round_end", monitor.on_round_end)

        # 保存 monitor 引用以便后续获取报告
        self._performance_monitor = monitor
        return self

    def with_token_counter(self) -> "AgentBuilder":
        """
        启用 Token 统计（快捷方法）。

        用法：
            builder.with_token_counter()
        """
        if not self._config.callbacks:
            self._config.callbacks = CallbackManager()

        counter = TokenCounter()
        self._config.callbacks.on("llm_end", counter.on_llm_end)

        # 保存 counter 引用以便后续获取报告
        self._token_counter = counter
        return self

    def with_generation_config(
        self,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        stream: bool | None = None,
    ) -> "AgentBuilder":
        """
        批量设置 LLM 生成参数。

        用法：
            builder.with_generation_config(
                temperature=0.9,
                max_tokens=2048,
                top_p=0.95,
                frequency_penalty=0.5,
                presence_penalty=0.5,
                stream=True,
            )
        """
        if temperature is not None:
            self._config.temperature = temperature
        if max_tokens is not None:
            self._config.max_tokens = max_tokens
        if top_p is not None:
            self._config.top_p = top_p
        if frequency_penalty is not None:
            self._config.frequency_penalty = frequency_penalty
        if presence_penalty is not None:
            self._config.presence_penalty = presence_penalty
        if stream is not None:
            self._config.stream = stream
        return self

    # ── 构建 ─────────────────────────────────────────────────────────────────

    def build(self) -> AgentRunner:
        """构建并返回 AgentRunner"""
        if self._llm is None:
            raise ValueError(
                "未指定 LLM，请先调用 .with_openai() 或 .with_llm()"
            )
        if self._should_use_openai_agents():
            assert isinstance(self._llm, OpenAICompatibleProvider)
            return OpenAIAgentsThreadRunner(
                api_key=self._llm.api_key,
                model=self._llm.model_name,
                base_url=self._llm.base_url,
                timeout=self._llm.timeout,
                tools=self._tools,
                store=self._store or FileSystemStore(),
                config=self._config,
                on_human_request=self._on_human_request,
            )
        return AgentRunner(
            llm=self._llm,
            tools=self._tools,
            store=self._store or FileSystemStore(),
            config=self._config,
            on_human_request=self._on_human_request,
        )

    def _should_use_openai_agents(self) -> bool:
        if self._agent_backend == "legacy":
            return False
        if not isinstance(self._llm, OpenAICompatibleProvider):
            return False
        if not agents_sdk_is_available():
            return False
        return self._agent_backend in {"auto", "openai_agents"}


# ─── 便捷函数 ─────────────────────────────────────────────────────────────────

def quick_agent(
    user_input: str,
    tools: dict[str, Callable[..., Any]],
    api_key: str | None = None,
    model: str = "gpt-4o",
    verbose: bool = False,
) -> Thread:
    """
    快速运行一次性 Agent（适合脚本集成）。

    :param user_input: 用户指令
    :param tools:      工具字典 {name: handler_function}
    :param api_key:    OpenAI API key（可选，默认读环境变量）
    :param model:      LLM 模型名称
    :param verbose:    是否输出详细日志

    用法：
        thread = quick_agent(
            "计算 100 的平方根",
            tools={"sqrt": lambda x: x**0.5},
        )
    """
    builder = AgentBuilder().with_openai(api_key=api_key, model=model)
    if verbose:
        builder.with_verbose()

    for name, fn in tools.items():
        builder.tool(name=name, description=fn.__doc__ or "")(fn)

    runner = builder.build()
    return runner.launch(user_input)


# ─── 公开接口 ─────────────────────────────────────────────────────────────────

__all__ = [
    # 高级 API
    "AgentBuilder",
    "quick_agent",
    # 核心类
    "AgentRunner",
    "RunConfig",
    "Thread",
    # 工具系统
    "ToolRegistry",
    "ToolSpec",
    "BUILTIN_TOOLS",
    # LLM
    "LLMProvider",
    "OpenAICompatibleProvider",
    # Prompt
    "PromptTemplate",
    "DEFAULT_SYSTEM_PROMPT",
    "FOCUSED_AGENT_PROMPT",
    "CODE_AGENT_PROMPT",
    # 存储
    "ThreadStore",
    "FileSystemStore",
    "SQLiteStore",
    # 上下文
    "build_context_messages",
]
