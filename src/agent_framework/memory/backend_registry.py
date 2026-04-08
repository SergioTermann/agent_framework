from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import socket
from typing import Any, Mapping
from urllib.parse import urlparse

from agent_framework.memory.config import load_config
from agent_framework.memory.reme_memory import probe_reme_backend
from agent_framework.memory.viking_memory import probe_viking_backend


SUPPORTED_MEMORY_BACKENDS = {"local", "reme", "viking"}


@dataclass
class MemoryBackendResolution:
    requested: str
    active: str
    fallback: bool
    reason: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _is_local_service_url(value: str | None) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}


def _probe_local_service_url(value: str | None, timeout: float = 0.5) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return True
    parsed = urlparse(raw)
    host = parsed.hostname
    if not host:
        return True
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _validate_reme_sidecar_dependencies(sidecar_config: Mapping[str, Any]) -> str | None:
    if str(sidecar_config.get("llm_provider") or "").strip().lower() == "vllm" and not str(sidecar_config.get("embedding_base_url") or "").strip():
        return "embedding_base_url_missing_for_vllm"
    checks = (
        ("embedding_base_url", sidecar_config.get("embedding_base_url")),
        ("llm_base_url", sidecar_config.get("llm_base_url")),
    )
    for label, value in checks:
        if _is_local_service_url(str(value or "")) and not _probe_local_service_url(value):
            return f"{label}_unreachable"
    return None


def resolve_memory_backend(config: Mapping[str, Any] | None = None) -> MemoryBackendResolution:
    config = dict(config or load_config())
    backend_config = dict(config.get("backend") or {})
    requested = str(backend_config.get("provider") or "local").strip().lower() or "local"
    if requested not in SUPPORTED_MEMORY_BACKENDS:
        requested = "local"

    if requested == "local":
        return MemoryBackendResolution(
            requested="local",
            active="local",
            fallback=False,
            reason="configured_local",
        )

    allow_fallback = bool(backend_config.get("fallback_to_local", True))
    if requested == "reme":
        reme_config = dict(backend_config.get("reme") or {})
        sidecar_config = dict(reme_config.get("sidecar") or {})
        if sidecar_config.get("enabled", True):
            venv_dir = Path(str(sidecar_config.get("venv_dir") or ".venv_reme_memory"))
            if not venv_dir.is_absolute():
                venv_dir = _repo_root() / venv_dir
            python_path = venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
            if python_path.exists():
                dependency_error = _validate_reme_sidecar_dependencies(sidecar_config)
                if dependency_error:
                    if allow_fallback:
                        return MemoryBackendResolution(
                            requested="reme",
                            active="local",
                            fallback=True,
                            reason=f"reme_sidecar_dependency_unreachable:{dependency_error}",
                        )
                    return MemoryBackendResolution(
                        requested="reme",
                        active="reme",
                        fallback=False,
                        reason=f"reme_sidecar_dependency_unreachable:{dependency_error}",
                    )
                return MemoryBackendResolution(
                    requested="reme",
                    active="reme",
                    fallback=False,
                    reason="reme_sidecar_ready",
                )
            probe = probe_reme_backend()
        else:
            probe = probe_reme_backend()
    else:
        probe = probe_viking_backend(backend_config.get("viking"))

    if probe.available:
        return MemoryBackendResolution(
            requested=requested,
            active=requested,
            fallback=False,
            reason="backend_ready",
        )

    if allow_fallback:
        return MemoryBackendResolution(
            requested=requested,
            active="local",
            fallback=True,
            reason=f"{requested}_unavailable:{probe.reason}",
        )

    return MemoryBackendResolution(
        requested=requested,
        active=requested,
        fallback=False,
        reason=f"{requested}_unavailable:{probe.reason}",
    )
