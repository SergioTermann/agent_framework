from __future__ import annotations

import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flask import Flask

from agent_framework.core.config import get_config
from agent_framework.gateway.control_plane import gateway_control_plane_mode, gateway_control_plane_url
from agent_framework.memory.system import get_memory_backend_info
from agent_framework.platform.extension_system import get_extension_system


_DEFAULT_SECRET = "agent-framework-secret-key-change-in-production"


def build_liveness_report() -> dict[str, Any]:
    return {
        "status": "alive",
        "service": "agent-framework",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def build_readiness_report(app: Flask) -> dict[str, Any]:
    cfg = get_config()
    checks = [
        _check_required_routes(app),
        _check_data_directory(cfg.data.data_dir),
        _check_gateway_storage_path(cfg.gateway.db_path),
        _check_memory_backend(),
        _check_llm_configuration(cfg.llm.base_url, cfg.llm.model, cfg.llm.api_key),
        _check_auth_secret(cfg.server.secret_key),
        _check_gateway_control_plane(),
        _check_plugins(),
    ]

    summary = {
        "pass": sum(1 for check in checks if check["status"] == "pass"),
        "warn": sum(1 for check in checks if check["status"] == "warn"),
        "fail": sum(1 for check in checks if check["status"] == "fail"),
        "total": len(checks),
    }
    ready = summary["fail"] == 0
    if not ready:
        status = "not_ready"
    elif summary["warn"] > 0:
        status = "degraded"
    else:
        status = "ready"

    return {
        "status": status,
        "ready": ready,
        "service": "agent-framework",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "checks": checks,
    }


def readiness_http_status(report: dict[str, Any]) -> int:
    return 200 if report.get("ready") else 503


def _check_required_routes(app: Flask) -> dict[str, Any]:
    required = {
        "/api/openapi.json",
        "/api/docs",
        "/api/system/status",
        "/system-status",
    }
    present = {rule.rule for rule in app.url_map.iter_rules()}
    missing = sorted(required - present)
    if missing:
        return _check(
            "required_routes",
            "fail",
            "Required harness endpoints are missing.",
            {"missing": missing},
        )
    return _check(
        "required_routes",
        "pass",
        "Required harness endpoints are registered.",
        {"count": len(required)},
    )


def _check_data_directory(data_dir: str) -> dict[str, Any]:
    path = Path(data_dir)
    if path.exists() and path.is_dir():
        writable = os.access(path, os.W_OK)
        status = "pass" if writable else "fail"
        summary = "Primary data directory is available." if writable else "Primary data directory is not writable."
        return _check("data_directory", status, summary, {"path": str(path)})

    parent = path.parent if path.parent != Path("") else Path(".")
    if parent.exists() and os.access(parent, os.W_OK):
        return _check(
            "data_directory",
            "warn",
            "Primary data directory does not exist yet but can be created.",
            {"path": str(path), "parent": str(parent)},
        )
    return _check(
        "data_directory",
        "fail",
        "Primary data directory cannot be created.",
        {"path": str(path), "parent": str(parent)},
    )


def _check_gateway_storage_path(db_path: str) -> dict[str, Any]:
    path = Path(db_path)
    parent = path.parent if path.parent != Path("") else Path(".")
    if parent.exists() and os.access(parent, os.W_OK):
        return _check(
            "gateway_storage",
            "pass",
            "Gateway storage path is writable.",
            {"path": str(path)},
        )
    return _check(
        "gateway_storage",
        "fail",
        "Gateway storage path is not writable.",
        {"path": str(path)},
    )


def _check_memory_backend() -> dict[str, Any]:
    info = get_memory_backend_info()
    if not info.get("active"):
        return _check("memory_backend", "fail", "No active memory backend.", info)
    if info.get("fallback"):
        return _check("memory_backend", "warn", "Memory backend is running with fallback mode.", info)
    return _check("memory_backend", "pass", "Memory backend is active.", info)


def _check_llm_configuration(base_url: str, model: str, api_key: str) -> dict[str, Any]:
    if not base_url or not model:
        return _check(
            "llm_configuration",
            "fail",
            "LLM base URL or model is missing.",
            {"base_url": base_url, "model": model},
        )

    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip().lower()
    is_local = host in {"", "127.0.0.1", "localhost", "0.0.0.0", "::1"}
    if api_key:
        return _check(
            "llm_configuration",
            "pass",
            "LLM provider configuration looks complete.",
            {"base_url": base_url, "model": model, "api_key_configured": True},
        )
    if is_local:
        return _check(
            "llm_configuration",
            "warn",
            "LLM endpoint is local and no API key is configured.",
            {"base_url": base_url, "model": model, "api_key_configured": False},
        )
    return _check(
        "llm_configuration",
        "fail",
        "Remote LLM endpoint is configured without an API key.",
        {"base_url": base_url, "model": model, "api_key_configured": False},
    )


def _check_auth_secret(secret_key: str) -> dict[str, Any]:
    if not secret_key or secret_key == _DEFAULT_SECRET or len(secret_key) < 16:
        return _check(
            "auth_secret",
            "warn",
            "Auth secret is weak or still using the default value.",
            {"configured": bool(secret_key), "length": len(secret_key or "")},
        )
    return _check(
        "auth_secret",
        "pass",
        "Auth secret length looks acceptable.",
        {"length": len(secret_key)},
    )


def _check_gateway_control_plane() -> dict[str, Any]:
    mode = gateway_control_plane_mode()
    url = gateway_control_plane_url()
    if mode != "go":
        return _check(
            "gateway_control_plane",
            "pass",
            "Python gateway control plane mode is active.",
            {"mode": mode, "configured_url": url},
        )

    try:
        payload = _probe_json(f"{url}/health")
    except Exception as exc:
        return _check(
            "gateway_control_plane",
            "fail",
            "Go gateway control plane is enabled but unreachable.",
            {"mode": mode, "configured_url": url, "error": str(exc)},
        )
    return _check(
        "gateway_control_plane",
        "pass",
        "Go gateway control plane is reachable.",
        {"mode": mode, "configured_url": url, "response": payload},
    )


def _check_plugins() -> dict[str, Any]:
    system = get_extension_system()
    plugins = system.plugin_manager.list_plugins()
    error_plugins = [plugin["name"] for plugin in plugins if plugin.get("status") == "error"]
    if error_plugins:
        return _check(
            "plugins",
            "warn",
            "One or more plugins failed to load.",
            {"error_plugins": error_plugins, "loaded_count": len(plugins)},
        )
    return _check(
        "plugins",
        "pass",
        "Plugin subsystem is available.",
        {"loaded_count": len(plugins)},
    )


def _probe_json(url: str) -> dict[str, Any]:
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

    import json

    try:
        parsed = json.loads(payload or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("probe returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("probe returned invalid payload")
    return parsed


def _check(name: str, status: str, summary: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "details": details,
    }
