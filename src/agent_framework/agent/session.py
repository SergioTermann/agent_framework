"""
共享 AgentSession —— 统一 web_ui.py 和 app_platform.py 的会话管理

整合：工具自动发现 + 插件工具 + 统一配置
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from agent_framework.agent import AgentBuilder
from agent_framework.agent.callbacks import CallbackManager, PerformanceMonitor, TokenCounter
from agent_framework.agent.thread import latest_assistant_message
from agent_framework.core.config import get_config
from agent_framework.tool.file_cache import FileStateCache, create_file_cache_middleware
from agent_framework.tools import register_selected_tools

logger = logging.getLogger(__name__)


class AgentSession:
    """
    Agent 会话管理（共享实现）

    :param session_id: 会话唯一标识
    :param config: 前端传入的运行时配置覆盖
    :param user_id: 可选用户 ID
    :param emit_fn: WebSocket emit 函数（由调用方注入）
    """

    def __init__(
        self,
        session_id: str,
        config: dict,
        user_id: str | None = None,
        emit_fn: Callable[..., Any] | None = None,
    ):
        self.session_id = session_id
        self.config = config
        self.user_id = user_id
        self.thread = None
        self._emit = emit_fn or (lambda *a, **kw: None)

        # 回调 & 监控
        self.callbacks = CallbackManager()
        self.perf_monitor = PerformanceMonitor()
        self.token_counter = TokenCounter()
        self.file_cache = FileStateCache()

        self._setup_callbacks()

    # ── 回调注册 ──────────────────────────────────────────────────────────────

    def _setup_callbacks(self):
        self.callbacks.on("llm_start", self._on_llm_start)
        self.callbacks.on("llm_end", self._on_llm_end)
        self.callbacks.on("tool_call_start", self._on_tool_call_start)
        self.callbacks.on("tool_call_end", self._on_tool_call_end)
        self.callbacks.on("round_start", self._on_round_start)

        # 性能监控
        self.callbacks.on("llm_start", self.perf_monitor.on_llm_start)
        self.callbacks.on("llm_end", self.perf_monitor.on_llm_end)
        self.callbacks.on("tool_call_start", self.perf_monitor.on_tool_call_start)
        self.callbacks.on("tool_call_end", self.perf_monitor.on_tool_call_end)
        self.callbacks.on("round_end", self.perf_monitor.on_round_end)

        # Token 统计
        self.callbacks.on("llm_end", self.token_counter.on_llm_end)

    def _on_llm_start(self, event):
        self._emit("llm_start", {"session_id": self.session_id, "data": event.data})

    def _on_llm_end(self, event):
        self._emit("llm_end", {"session_id": self.session_id, "data": event.data})

    def _on_tool_call_start(self, event):
        self._emit("tool_call_start", {
            "session_id": self.session_id,
            "tool_name": event.data.get("tool_name"),
            "arguments": event.data.get("arguments"),
            "status": "running",
        })

    def _on_tool_call_end(self, event):
        result = event.data.get("result")
        self._emit("tool_call_end", {
            "session_id": self.session_id,
            "tool_name": event.data.get("tool_name"),
            "result": result,
            "result_preview": str(result)[:160] if result is not None else "",
            "status": "completed",
        })

    def _on_round_start(self, event):
        self._emit("round_start", {
            "session_id": self.session_id,
            "round": event.data.get("round"),
            "label": f"第 {event.data.get('round')} 轮",
        })

    # ── Agent 构建 ────────────────────────────────────────────────────────────

    def create_agent(self):
        """创建 Agent，自动注册 tools/ 目录下的工具 + 插件工具"""
        cfg = get_config()

        def stream_callback(chunk: str):
            self._emit("stream_chunk", {"session_id": self.session_id, "chunk": chunk})

        builder = (
            AgentBuilder()
            .with_openai(
                api_key=cfg.llm.api_key,
                model=self.config.get("model", cfg.llm.model),
                base_url=cfg.llm.base_url,
            )
            .with_agent_backend(self.config.get("agent_backend", "auto"))
            .with_temperature(self.config.get("temperature", cfg.agent.temperature))
            .with_max_tokens(self.config.get("max_tokens", cfg.agent.max_tokens))
            .with_top_p(self.config.get("top_p", cfg.agent.top_p))
            .with_frequency_penalty(self.config.get("frequency_penalty", cfg.agent.frequency_penalty))
            .with_presence_penalty(self.config.get("presence_penalty", cfg.agent.presence_penalty))
            .with_stream(self.config.get("stream", cfg.agent.stream), on_chunk=stream_callback)
            .with_callbacks(self.callbacks)
            .with_max_rounds(self.config.get("max_rounds", cfg.agent.max_rounds))
            .with_tool_permission_rules(self.config.get("tool_permission_rules"))
            .with_tool_result_limit(int(self.config.get("max_tool_result_chars", 4000) or 4000))
            .with_middleware(create_file_cache_middleware(self.file_cache))
        )

        register_selected_tools(
            builder,
            allowed_tools=self.config.get("allowed_tools"),
            blocked_tools=self.config.get("blocked_tools"),
            toolsets=self.config.get("toolsets") or self.config.get("toolset"),
            include_plugin_tools=bool(self.config.get("include_plugin_tools", True)),
        )

        return builder.build()

    # ── 运行 ──────────────────────────────────────────────────────────────────

    def run(self, user_input: str):
        """运行 Agent"""
        try:
            self._emit("workflow_started", {
                "session_id": self.session_id,
                "task": user_input,
                "status": "running",
            })

            runner = self.create_agent()
            self.thread = runner.launch(user_input)

            final_result = latest_assistant_message(self.thread)

            self._emit("agent_complete", {
                "session_id": self.session_id,
                "thread_id": self.thread.thread_id,
                "final_result": final_result,
                "stats": {
                    "performance": self.perf_monitor.get_report(),
                    "tokens": self.token_counter.get_report(),
                    "cost": self.token_counter.estimate_cost(),
                },
            })
        except Exception as e:
            self._emit("agent_error", {
                "session_id": self.session_id,
                "error": str(e),
            })
