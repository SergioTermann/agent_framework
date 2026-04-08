from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from agent_framework.tool.registry import ToolMiddleware


class ToolExecutionBlockedError(RuntimeError):
    """Raised when a tool hook blocks execution."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str = "",
        arguments: dict[str, Any] | None = None,
        decision: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.tool_name = tool_name
        self.arguments = dict(arguments or {})
        self.decision = decision
        self.metadata = dict(metadata or {})


_UNSET = object()


@dataclass
class ToolInvocation:
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class BeforeToolResult:
    allow: bool = True
    updated_arguments: dict[str, Any] | None = None
    override_result: Any = _UNSET
    reason: str = ""
    decision: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolErrorResult:
    handled: bool = False
    result: Any = None


class ToolHook(Protocol):
    def before_tool(self, invocation: ToolInvocation) -> BeforeToolResult | None:
        ...

    def after_tool(self, invocation: ToolInvocation, result: Any) -> Any:
        ...

    def on_tool_error(
        self,
        invocation: ToolInvocation,
        error: Exception,
    ) -> ToolErrorResult | None:
        ...


def create_tool_hook_middleware(hooks: Iterable[ToolHook]) -> ToolMiddleware:
    hook_list = [hook for hook in hooks if hook is not None]

    def middleware(name: str, arguments: dict[str, Any], next_fn):
        current_arguments = dict(arguments or {})
        invocation = ToolInvocation(tool_name=name, arguments=current_arguments)
        override_result = _UNSET

        for hook in hook_list:
            before_tool = getattr(hook, "before_tool", None)
            if not callable(before_tool):
                continue
            decision = before_tool(invocation)
            if decision is None:
                continue
            if not decision.allow:
                reason = decision.reason or f"Tool '{name}' was blocked by a hook"
                raise ToolExecutionBlockedError(
                    reason,
                    tool_name=name,
                    arguments=current_arguments,
                    decision=decision.decision,
                    metadata=decision.metadata,
                )
            if decision.updated_arguments is not None:
                current_arguments = dict(decision.updated_arguments)
                invocation.arguments = current_arguments
            if decision.override_result is not _UNSET:
                override_result = decision.override_result

        if override_result is _UNSET:
            try:
                result = next_fn(name, current_arguments)
            except Exception as exc:
                for hook in reversed(hook_list):
                    on_tool_error = getattr(hook, "on_tool_error", None)
                    if not callable(on_tool_error):
                        continue
                    handled = on_tool_error(invocation, exc)
                    if handled and handled.handled:
                        result = handled.result
                        break
                else:
                    raise
        else:
            result = override_result

        for hook in reversed(hook_list):
            after_tool = getattr(hook, "after_tool", None)
            if not callable(after_tool):
                continue
            updated = after_tool(invocation, result)
            if updated is not _UNSET:
                result = updated
        return result

    return middleware


def truncate_tool_result(result: Any, max_chars: int | None) -> tuple[str, bool, int]:
    text = "null" if result is None else str(result)
    original_length = len(text)
    limit = max(0, int(max_chars or 0))
    if limit <= 0 or original_length <= limit:
        return text, False, original_length

    suffix = f"\n...[truncated {original_length - limit} chars]"
    if len(suffix) >= limit:
        truncated = suffix[-limit:]
    else:
        truncated = text[: limit - len(suffix)] + suffix
    return truncated, True, original_length


def create_tool_result_limit_middleware(
    max_chars_provider,
) -> ToolMiddleware:
    def middleware(name: str, arguments: dict[str, Any], next_fn):
        result = next_fn(name, arguments)
        max_chars = max_chars_provider() if callable(max_chars_provider) else max_chars_provider
        truncated, _, _ = truncate_tool_result(result, max_chars)
        return truncated

    return middleware
