"""
向后兼容垫片 —— 所有内容已迁移至 tool_registry.py
"""
from agent_framework.tool.registry import (
    ToolSpec,
    ToolRegistry,
    ToolMiddleware,
    BUILTIN_TOOLS,
    HUMAN_APPROVAL_TOOL,
    REQUEST_INFO_TOOL,
    DONE_TOOL,
    PAUSE_TOOL_NAMES,
)
from agent_framework.tool.middleware import (
    BeforeToolResult,
    ToolErrorResult,
    ToolExecutionBlockedError,
    ToolHook,
    ToolInvocation,
    create_tool_hook_middleware,
    create_tool_result_limit_middleware,
    truncate_tool_result,
)
from agent_framework.tool.permissions import (
    ToolPermissionHook,
    ToolPermissionRule,
    parse_tool_permission_rules,
    resolve_tool_permission_rules,
)

__all__ = [
    "ToolSpec",
    "ToolRegistry",
    "ToolMiddleware",
    "BUILTIN_TOOLS",
    "HUMAN_APPROVAL_TOOL",
    "REQUEST_INFO_TOOL",
    "DONE_TOOL",
    "PAUSE_TOOL_NAMES",
    "ToolExecutionBlockedError",
    "ToolInvocation",
    "BeforeToolResult",
    "ToolErrorResult",
    "ToolHook",
    "create_tool_hook_middleware",
    "create_tool_result_limit_middleware",
    "truncate_tool_result",
    "ToolPermissionRule",
    "ToolPermissionHook",
    "parse_tool_permission_rules",
    "resolve_tool_permission_rules",
]
