from __future__ import annotations

import json
import platform
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask

from agent_framework.gateway.control_plane import gateway_control_plane_mode, gateway_control_plane_url
from agent_framework.core.harness_health import build_readiness_report
from agent_framework.memory.system import get_memory_backend_info
from agent_framework.platform.extension_system import get_extension_system
from agent_framework.tools import TOOLSET_PRESETS, discover_tools


_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXCLUDED_ENDPOINTS = {"static"}


def collect_system_status(app: Flask) -> dict[str, Any]:
    cfg = _safe_get_config()
    route_counts = _route_counts(app)
    builtin_tools = _safe_discover_tools()
    extension_system = get_extension_system()
    loaded_plugins = sorted(extension_system.plugin_manager.plugins.keys())
    control_plane_mode = gateway_control_plane_mode()
    readiness = build_readiness_report(app)

    return {
        "status": "ok",
        "service": "agent-framework",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "readiness": {
            "status": readiness["status"],
            "ready": readiness["ready"],
            "summary": readiness["summary"],
        },
        "runtime": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "host": cfg.server.host,
            "port": cfg.server.port,
            "debug": bool(cfg.server.debug),
        },
        "routes": route_counts,
        "gateway": {
            "namespace": cfg.gateway.namespace,
            "mode": control_plane_mode,
            "storage": "noop" if control_plane_mode == "go" else "sqlite",
            "control_plane": _control_plane_status(control_plane_mode),
        },
        "llm": {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "base_url": cfg.llm.base_url,
            "api_key_configured": bool(cfg.llm.api_key),
        },
        "memory": get_memory_backend_info(),
        "tools": {
            "builtin_count": len(builtin_tools),
            "plugin_tool_count": len(extension_system.plugin_manager.get_tool_specs()),
            "preset_count": len(TOOLSET_PRESETS),
        },
        "plugins": {
            "loaded_count": len(loaded_plugins),
            "loaded_names": loaded_plugins,
        },
        "services": {
            "python_web": {
                "status": "active",
                "source_of_truth": True,
            },
            "gateway_go": {
                "status": "sidecar-ready",
                "enabled": control_plane_mode == "go",
                "repo_present": (_REPO_ROOT / "services" / "gateway-go").exists(),
            },
            "app_go": {
                "status": "bootstrap",
                "repo_present": (_REPO_ROOT / "services" / "app-go").exists(),
                "notes": [
                    "control-plane service skeleton is active",
                    "legacy Python APIs are not migrated yet",
                ],
            },
        },
        "migration": {
            "status": "hybrid",
            "source_of_truth": "legacy src/ tree remains primary while services/ is the target layout",
        },
    }


def _safe_get_config():
    from agent_framework.core.config import get_config

    return get_config()


def _route_counts(app: Flask) -> dict[str, int]:
    total = 0
    api = 0
    ui = 0
    websocket_related = 0

    for rule in app.url_map.iter_rules():
        if rule.endpoint in _EXCLUDED_ENDPOINTS:
            continue
        total += 1
        if rule.rule.startswith("/api/"):
            api += 1
        else:
            ui += 1
        if "gateway" in rule.rule or "socket" in rule.endpoint:
            websocket_related += 1

    return {
        "total": total,
        "api": api,
        "ui": ui,
        "websocket_related": websocket_related,
    }


def _safe_discover_tools():
    try:
        return discover_tools()
    except Exception:
        return []


def _control_plane_status(mode: str) -> dict[str, Any]:
    url = gateway_control_plane_url()
    if mode != "go":
        return {
            "configured_url": url,
            "reachable": False,
            "status": "disabled",
        }

    health_url = f"{url}/health"
    try:
        payload = _probe_json_url(health_url)
        return {
            "configured_url": url,
            "reachable": True,
            "status": payload.get("status", "ok"),
            "service": payload.get("service"),
        }
    except Exception as exc:
        return {
            "configured_url": url,
            "reachable": False,
            "status": "unreachable",
            "error": str(exc),
        }


def _probe_json_url(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.URLError as exc:  # pragma: no cover
        raise RuntimeError(f"probe failed: {exc.reason}") from exc

    try:
        parsed = json.loads(payload or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("probe returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("probe returned invalid payload")
    return parsed
