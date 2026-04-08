from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from agent_framework.tool.middleware import BeforeToolResult, ToolHook, ToolInvocation


PermissionDecision = Literal["allow", "deny", "ask"]


@dataclass
class ToolPermissionRule:
    tool_name: str = "*"
    decision: PermissionDecision = "allow"
    constraints: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def parse_tool_permission_rules(raw_rules: Iterable[dict[str, Any]] | None) -> list[ToolPermissionRule]:
    rules: list[ToolPermissionRule] = []
    for raw in raw_rules or []:
        if not isinstance(raw, dict):
            continue
        tool_name = str(raw.get("tool_name") or raw.get("tool") or "*").strip() or "*"
        decision = str(raw.get("decision") or "allow").strip().lower()
        if decision not in {"allow", "deny", "ask"}:
            continue
        constraints = raw.get("constraints") or raw.get("arguments") or {}
        if not isinstance(constraints, dict):
            constraints = {}
        rules.append(
            ToolPermissionRule(
                tool_name=tool_name,
                decision=decision,
                constraints=constraints,
                reason=str(raw.get("reason") or "").strip(),
            )
        )
    return rules


def resolve_tool_permission_rules(raw_rules: Any) -> list[ToolPermissionRule]:
    if isinstance(raw_rules, list):
        return parse_tool_permission_rules(raw_rules)
    if not isinstance(raw_rules, dict):
        return []

    ordered_keys = [
        "default_tool_permission_rules",
        "managed_tool_permission_rules",
        "user_tool_permission_rules",
        "project_tool_permission_rules",
        "session_tool_permission_rules",
        "tool_permission_rules",
    ]
    merged: list[dict[str, Any]] = []
    for key in ordered_keys:
        value = raw_rules.get(key)
        if isinstance(value, list):
            merged.extend(value)
    return parse_tool_permission_rules(merged)


class ToolPermissionHook(ToolHook):
    def __init__(self, rules: Iterable[ToolPermissionRule]):
        self.rules = [rule for rule in rules]

    @classmethod
    def from_raw(cls, raw_rules: Iterable[dict[str, Any]] | None) -> "ToolPermissionHook | None":
        rules = resolve_tool_permission_rules(raw_rules)
        if not rules:
            return None
        return cls(rules)

    def before_tool(self, invocation: ToolInvocation) -> BeforeToolResult | None:
        matched_rule: ToolPermissionRule | None = None
        for rule in self.rules:
            if _matches_rule(rule, invocation):
                matched_rule = rule
        if matched_rule is None:
            return None
        if matched_rule.decision == "allow":
            return None
        return BeforeToolResult(
            allow=False,
            reason=_build_permission_message(invocation, matched_rule),
            decision=matched_rule.decision,
            metadata={
                "tool_name": invocation.tool_name,
                "arguments": dict(invocation.arguments),
                "reason": matched_rule.reason,
                "rule": {
                    "tool_name": matched_rule.tool_name,
                    "decision": matched_rule.decision,
                    "constraints": matched_rule.constraints,
                },
            },
        )


def _build_permission_message(invocation: ToolInvocation, rule: ToolPermissionRule) -> str:
    base_reason = rule.reason or f"Permission rule requires '{rule.decision}' for tool '{invocation.tool_name}'"
    if rule.decision == "ask":
        return (
            f"{base_reason}. Ask the user for approval via request_human_approval before retrying "
            f"tool '{invocation.tool_name}'."
        )
    return base_reason


def _matches_rule(rule: ToolPermissionRule, invocation: ToolInvocation) -> bool:
    if rule.tool_name not in {"*", invocation.tool_name}:
        return False
    for path, expected in rule.constraints.items():
        actual = _get_nested_value(invocation.arguments, path)
        if not _match_expected(actual, expected):
            return False
    return True


def _get_nested_value(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in str(path or "").split("."):
        if not part:
            continue
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _match_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if "exists" in expected:
            return bool(actual is not None) is bool(expected["exists"])
        if actual is None:
            return False
        if "eq" in expected and actual != expected["eq"]:
            return False
        if "contains" in expected and str(expected["contains"]) not in str(actual):
            return False
        if "startswith" in expected and not str(actual).startswith(str(expected["startswith"])):
            return False
        if "endswith" in expected and not str(actual).endswith(str(expected["endswith"])):
            return False
        if "regex" in expected and re.search(str(expected["regex"]), str(actual)) is None:
            return False
        if "in" in expected and actual not in list(expected["in"] or []):
            return False
        return True
    return actual == expected
