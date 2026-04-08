"""
tools 包 —— 自动发现并注册工具模块

约定：
  每个工具文件需导出：
    TOOL_META: dict  —— 包含 name / description / parameters（可选）
    与 TOOL_META["name"] 同名的函数作为 handler

用法：
    from agent_framework.tools import discover_tools, register_all

    # 获取所有 ToolSpec
    specs = discover_tools()

    # 一键注册到 AgentBuilder
    register_all(builder)
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from agent_framework.tool.registry import ToolSpec, _infer_schema

if TYPE_CHECKING:
    from agent_framework.agent import AgentBuilder

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).parent

TOOLSET_PRESETS: dict[str, set[str] | None] = {
    "none": set(),
    "all": None,
    "basic": {"calculate", "get_datetime", "sum_numbers", "score_grade", "create_todo_list"},
    "text": {"to_uppercase", "to_lowercase", "analyze_text", "split_text"},
    "research": {"web_search", "fetch_url"},
    "causal": {
        "analyze_causal_chain",
        "counterfactual_reason",
        "predict_effects",
        "root_cause_analyze",
        "intervention_evaluate",
    },
    "travel": {"travel_tip", "get_weather"},
    "wind_maintenance": {
        "calculate",
        "get_datetime",
        "web_search",
        "fetch_url",
        "analyze_causal_chain",
        "counterfactual_reason",
        "predict_effects",
        "root_cause_analyze",
        "intervention_evaluate",
        "get_weather",
    },
}


def discover_tools() -> list[ToolSpec]:
    """扫描 tools/ 目录，返回所有符合约定的 ToolSpec 列表"""
    specs: list[ToolSpec] = []

    # 读取统一工具开关
    try:
        from agent_framework.core.config import get_config
        _te = get_config().tools_enabled
    except Exception:
        _te = None

    def _is_enabled(tool_name: str) -> bool:
        """检查工具是否在 tools_enabled 配置中启用"""
        if _te is None:
            return True
        return getattr(_te, tool_name, True)

    for finder, module_name, is_pkg in pkgutil.iter_modules([str(_PACKAGE_DIR)]):
        if module_name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{module_name}")
        except Exception as e:
            logger.warning("加载工具模块 tools.%s 失败: %s", module_name, e)
            continue

        meta = getattr(mod, "TOOL_META", None)
        if not isinstance(meta, dict) or "name" not in meta:
            continue

        tool_name = meta["name"]

        # 统一开关检查
        if not _is_enabled(tool_name):
            logger.debug("工具 %s 已在 tools_enabled 中禁用，跳过", tool_name)
            continue

        handler = getattr(mod, tool_name, None)
        if handler is None or not callable(handler):
            logger.warning("工具模块 tools.%s 缺少同名函数 %s", module_name, tool_name)
            continue

        spec = ToolSpec(
            name=tool_name,
            description=meta.get("description", ""),
            parameters=meta.get("parameters") or _infer_schema(handler),
            handler=handler,
        )
        specs.append(spec)
        logger.debug("发现工具: %s (from tools.%s)", tool_name, module_name)

        # 支持 EXTRA_TOOLS：同一模块导出多个工具
        extra = getattr(mod, "EXTRA_TOOLS", None)
        if isinstance(extra, list):
            for item in extra:
                ename = item.get("name")
                ehandler = item.get("handler") or getattr(mod, ename, None)
                if ename and ehandler and callable(ehandler):
                    espec = ToolSpec(
                        name=ename,
                        description=item.get("description", ""),
                        parameters=item.get("parameters") or _infer_schema(ehandler),
                        handler=ehandler,
                    )
                    specs.append(espec)
                    logger.debug("发现额外工具: %s (from tools.%s)", ename, module_name)

    return specs


def discover_plugin_tools() -> list[ToolSpec]:
    """发现插件工具；扩展系统不可用时返回空列表"""
    try:
        from agent_framework.platform.extension_system import get_extension_system

        ext = get_extension_system()
        return list(ext.plugin_manager.get_tool_specs())
    except Exception:
        return []


def _normalize_names(values: Iterable[str] | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        name = str(value or "").strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def _collect_tool_pool(include_plugin_tools: bool = True, user_id: str = "") -> dict[str, ToolSpec]:
    pool: dict[str, ToolSpec] = {}
    for spec in discover_tools():
        pool.setdefault(spec.name, spec)
    if include_plugin_tools:
        for spec in discover_plugin_tools():
            pool[spec.name] = spec
    # 用户自定义工具
    if user_id is not None:
        try:
            from agent_framework.tool.user_tools import get_user_tool_storage, get_user_tool_executor
            storage = get_user_tool_storage()
            executor = get_user_tool_executor()
            for tool_def in storage.list_tools(user_id=user_id):
                try:
                    spec = tool_def.to_tool_spec(executor)
                    pool[spec.name] = spec
                except Exception as e:
                    logger.warning("加载用户工具 %s 失败: %s", tool_def.name, e)
        except Exception as e:
            logger.debug("用户工具系统不可用: %s", e)
    return pool


def resolve_tool_specs(
    *,
    allowed_tools: Iterable[str] | None = None,
    blocked_tools: Iterable[str] | None = None,
    toolsets: Iterable[str] | None = None,
    include_plugin_tools: bool = True,
    user_id: str = "",
) -> list[ToolSpec]:
    """根据工具白名单/黑名单/工具集解析最终注册列表"""
    pool = _collect_tool_pool(include_plugin_tools=include_plugin_tools, user_id=user_id)
    pool_names = list(pool.keys())
    requested_names: list[str] = []
    selectors_specified = False

    for toolset in _normalize_names(toolsets):
        selectors_specified = True
        preset = TOOLSET_PRESETS.get(toolset)
        if toolset in pool and toolset not in TOOLSET_PRESETS:
            requested_names.append(toolset)
            continue
        if preset is None:
            requested_names.extend(pool_names)
            continue
        requested_names.extend(name for name in preset if name in pool)

    normalized_allowed = _normalize_names(allowed_tools)
    if normalized_allowed:
        selectors_specified = True
        requested_names.extend(name for name in normalized_allowed if name in pool)

    if not selectors_specified:
        requested_names = list(pool_names)

    blocked = set(_normalize_names(blocked_tools))
    resolved: list[ToolSpec] = []
    seen: set[str] = set()
    for name in requested_names:
        if name in seen or name in blocked:
            continue
        spec = pool.get(name)
        if spec is None:
            continue
        resolved.append(spec)
        seen.add(name)
    return resolved


def register_selected_tools(
    builder: "AgentBuilder",
    *,
    allowed_tools: Iterable[str] | None = None,
    blocked_tools: Iterable[str] | None = None,
    toolsets: Iterable[str] | None = None,
    include_plugin_tools: bool = True,
    user_id: str = "",
) -> "AgentBuilder":
    """按选择器把工具注册到 AgentBuilder"""
    for spec in resolve_tool_specs(
        allowed_tools=allowed_tools,
        blocked_tools=blocked_tools,
        toolsets=toolsets,
        include_plugin_tools=include_plugin_tools,
        user_id=user_id,
    ):
        builder.with_tool_spec(spec)
    return builder


def register_all(builder: "AgentBuilder") -> "AgentBuilder":
    """将 tools/ 下所有工具注册到 AgentBuilder"""
    return register_selected_tools(builder)
