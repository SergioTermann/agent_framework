"""
Agent Framework SDK —— 对外统一入口

提供开发者友好的 API，用于：
  - 构建 Agent
  - 注册自定义工具
  - 开发插件
  - 添加中间件
  - 管理配置

快速开始：
    from agent_framework.agent.sdk import AgentPlatform

    platform = AgentPlatform()

    @platform.tool(description="获取天气")
    def get_weather(city: str) -> str:
        return f"{city}: 晴天"

    platform.register_tools_from("tools")
    runner = platform.build()
    thread = runner.launch("北京天气如何？")
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from agent_framework.agent import AgentBuilder
from agent_framework.core.config import PlatformConfig, get_config, load_config
from agent_framework.platform.extension_system import BasePlugin, EventBus, PluginManager
from agent_framework.tool.registry import ToolMiddleware, ToolRegistry, ToolSpec
from agent_framework.tool.middleware import ToolHook, create_tool_hook_middleware
from agent_framework.tool.permissions import resolve_tool_permission_rules
from agent_framework.tools import discover_tools, register_selected_tools

logger = logging.getLogger(__name__)

# ─── 重新导出核心类型，方便 from sdk import ... ─────────────────────────────────

__all__ = [
    "AgentPlatform",
    "AgentBuilder",
    "ToolSpec",
    "ToolRegistry",
    "ToolMiddleware",
    "BasePlugin",
    "PlatformConfig",
    "get_config",
]


class AgentPlatform:
    """
    SDK 统一入口 —— 一站式构建可扩展 Agent 平台

    用法：
        platform = AgentPlatform()

        # 注册工具
        @platform.tool(description="计算")
        def calculate(expr: str) -> str: ...

        # 添加中间件
        platform.with_middleware(my_logging_middleware)

        # 加载 tools/ 目录
        platform.register_tools_from("tools")

        # 加载插件
        platform.register_plugin("my_plugin", config={...})

        # 构建 Agent
        runner = platform.build()
    """

    def __init__(self, config: PlatformConfig | None = None):
        self._config = config or get_config()
        self._builder = AgentBuilder()
        self._registry = self._builder._tools
        self._plugin_manager = PluginManager()
        self._event_bus = EventBus()
        self._configured_llm = False

    # ── LLM 配置 ──────────────────────────────────────────────────────────────

    def with_llm(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> "AgentPlatform":
        """配置 LLM（默认从 PlatformConfig 读取）"""
        cfg = self._config.llm
        self._builder.with_openai(
            api_key=api_key or cfg.api_key,
            model=model or cfg.model,
            base_url=base_url or cfg.base_url,
        )
        self._configured_llm = True
        return self

    def with_vllm(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> "AgentPlatform":
        """快捷接入 vLLM OpenAI 兼容端点。"""
        cfg = self._config.llm
        self._builder.with_vllm(
            model=model or cfg.model,
            base_url=base_url or cfg.base_url,
            api_key=api_key if api_key is not None else cfg.api_key,
        )
        self._configured_llm = True
        return self

    def with_xinference(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> "AgentPlatform":
        """???? Xinference OpenAI ?????"""
        cfg = self._config.llm
        self._builder.with_xinference(
            model=model or cfg.model,
            base_url=base_url or cfg.base_url,
            api_key=api_key if api_key is not None else cfg.api_key,
        )
        self._configured_llm = True
        return self

    def with_agent_backend(self, backend: str) -> "AgentPlatform":
        """璁剧疆 Agent 鎵ц鍚庣锛歛uto / openai_agents / legacy銆?"""
        self._builder.with_agent_backend(backend)
        return self

    def with_legacy_runner(self) -> "AgentPlatform":
        """寮哄埗浣跨敤 legacy runner銆?"""
        self._builder.with_legacy_runner()
        return self

    # ── 工具注册 ──────────────────────────────────────────────────────────────

    def tool(
        self,
        name: str | None = None,
        description: str = "",
        parameters: dict | None = None,
    ):
        """装饰器：注册工具函数（与 AgentBuilder.tool 完全兼容）"""
        return self._builder.tool(name=name, description=description, parameters=parameters)

    def add_tool(self, spec: ToolSpec) -> "AgentPlatform":
        """直接注册 ToolSpec"""
        self._builder.with_tool_spec(spec)
        return self

    def register_tools_from(self, package_path: str = "tools") -> "AgentPlatform":
        """
        从指定包路径自动发现并注册工具。
        默认扫描 tools/ 目录。
        """
        if package_path == "tools":
            register_selected_tools(self._builder)
        else:
            # 支持自定义包路径
            try:
                mod = importlib.import_module(package_path)
                discover_fn = getattr(mod, "discover_tools", None)
                if discover_fn:
                    for spec in discover_fn():
                        self._builder.with_tool_spec(spec)
            except ImportError as e:
                logger.warning("无法导入工具包 %s: %s", package_path, e)
        return self

    def register_selected_tools(
        self,
        *,
        allowed_tools: list[str] | None = None,
        blocked_tools: list[str] | None = None,
        toolsets: list[str] | str | None = None,
        include_plugin_tools: bool = True,
    ) -> "AgentPlatform":
        """按白名单/黑名单/工具集注册工具"""
        register_selected_tools(
            self._builder,
            allowed_tools=allowed_tools,
            blocked_tools=blocked_tools,
            toolsets=[toolsets] if isinstance(toolsets, str) else toolsets,
            include_plugin_tools=include_plugin_tools,
        )
        return self

    # ── 中间件 ────────────────────────────────────────────────────────────────

    def with_middleware(self, middleware: ToolMiddleware) -> "AgentPlatform":
        """
        添加工具中间件。

        中间件签名：(name, arguments, next_fn) -> Any

        用法：
            def timer_mw(name, args, next_fn):
                import time
                start = time.time()
                result = next_fn(name, args)
                print(f"{name} 耗时 {time.time()-start:.3f}s")
                return result

            platform.with_middleware(timer_mw)
        """
        self._registry.use(middleware)
        return self

    def with_tool_hook(self, hook: ToolHook) -> "AgentPlatform":
        """Add a structured tool hook to the dispatch chain."""
        self._registry.use(create_tool_hook_middleware([hook]))
        return self

    def with_tool_result_limit(self, max_chars: int) -> "AgentPlatform":
        """Cap a single tool result before it is fed back into the model."""
        self._builder.with_tool_result_limit(max_chars)
        return self

    def with_tool_permission_rules(
        self,
        rules: Any,
    ) -> "AgentPlatform":
        """Attach ordered allow/deny/ask tool permission rules."""
        parsed = resolve_tool_permission_rules(rules)
        if parsed:
            self._builder.with_tool_permission_rules(rules)
        return self

    # ── 插件 ──────────────────────────────────────────────────────────────────

    def register_plugin(self, plugin_name: str, config: dict | None = None) -> "AgentPlatform":
        """
        加载并注册插件，插件工具自动注入 ToolRegistry。

        用法：
            platform.register_plugin("data_processor", config={"max_records": 5000})
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._plugin_manager.load_plugin(plugin_name, config))
            else:
                loop.run_until_complete(self._plugin_manager.load_plugin(plugin_name, config))
        except RuntimeError:
            asyncio.run(self._plugin_manager.load_plugin(plugin_name, config))

        # 将插件工具注入 registry
        for spec in self._plugin_manager.get_tool_specs():
            if spec.name not in self._registry:
                self._registry.add(spec)
        return self

    # ── 事件 ──────────────────────────────────────────────────────────────────

    def on_event(self, event_name: str, callback: Callable) -> "AgentPlatform":
        """订阅平台事件"""
        self._event_bus.subscribe(event_name, callback)
        return self

    # ── 构建 ──────────────────────────────────────────────────────────────────

    def build(self):
        """构建并返回 AgentRunner"""
        if not self._configured_llm:
            self.with_llm()

        cfg = self._config.agent
        self._builder.with_temperature(cfg.temperature)
        self._builder.with_max_tokens(cfg.max_tokens)
        self._builder.with_top_p(cfg.top_p)
        self._builder.with_max_rounds(cfg.max_rounds)

        return self._builder.build()

    # ── 便捷属性 ──────────────────────────────────────────────────────────────

    @property
    def config(self) -> PlatformConfig:
        return self._config

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def plugin_manager(self) -> PluginManager:
        return self._plugin_manager

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus
