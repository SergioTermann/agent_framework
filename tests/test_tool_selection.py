from __future__ import annotations

from agent_framework.tools import resolve_tool_specs


def _names(specs):
    return [spec.name for spec in specs]


def test_tool_selection_defaults_to_all_tools():
    names = _names(resolve_tool_specs())
    assert "calculate" in names
    assert "web_search" in names
    assert "root_cause_analyze" in names


def test_tool_selection_supports_toolsets_and_blocklist():
    names = _names(
        resolve_tool_specs(
            toolsets=["causal", "research"],
            blocked_tools=["fetch_url"],
        )
    )
    assert "root_cause_analyze" in names
    assert "web_search" in names
    assert "fetch_url" not in names
    assert "calculate" not in names


def test_tool_selection_allows_precise_overrides():
    names = _names(
        resolve_tool_specs(
            toolsets=["none"],
            allowed_tools=["get_datetime", "calculate"],
            blocked_tools=["calculate"],
        )
    )
    assert names == ["get_datetime"]
