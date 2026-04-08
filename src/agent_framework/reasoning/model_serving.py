"""
Local model serving manager.

Manages vLLM / Xinference processes and external OpenAI-compatible endpoints.
Persists endpoint metadata to data/model_endpoints.json.
"""

from __future__ import annotations

import json
import importlib.util
import os
import shlex
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from shutil import which
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests


ENDPOINTS_FILE = os.path.join("data", "model_endpoints.json")
MODEL_CACHE_DIR = os.path.join("data", "model_cache")
PORT_RANGE_START = 8001
PORT_RANGE_END = 8099
XINFERENCE_DEFAULT_PORT = 9997
ENDPOINT_TYPES = {"chat", "embedding", "rerank"}


@dataclass
class ModelEndpoint:
    endpoint_id: str
    model_path: str
    finetune_task_id: str
    base_url: str
    backend: str
    status: str
    port: int
    process_id: Optional[int] = None
    model_name: str = ""
    host: str = "127.0.0.1"
    tensor_parallel_size: int = 1
    gpu_memory_utilization: float = 0.9
    max_model_len: int = 0
    dtype: str = "auto"
    api_key: str = ""
    model_uid: str = ""
    endpoint_type: str = "chat"
    created_at: float = field(default_factory=time.time)
    error_msg: str = ""


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _find_free_port(start: int = PORT_RANGE_START, end: int = PORT_RANGE_END) -> int:
    for port in range(start, end + 1):
        if not _is_port_in_use(port):
            return port
    raise RuntimeError(f"No free port in range {start}-{end}")


def _find_xinference_port(port: int = 0) -> int:
    if port:
        if _is_port_in_use(port):
            raise RuntimeError(f"Port {port} is already in use")
        return port
    if not _is_port_in_use(XINFERENCE_DEFAULT_PORT):
        return XINFERENCE_DEFAULT_PORT
    return _find_free_port()


def _vllm_available() -> bool:
    try:
        result = subprocess.run(
            ["python", "-m", "vllm.entrypoints.openai.api_server", "--help"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _wsl_vllm_command(inner_args: List[str]) -> List[str]:
    distro = _first_env("VLLM_WSL_DISTRO", default="").strip()
    python_path = _first_env("VLLM_WSL_PYTHON", default="").strip()
    if not distro or not python_path:
        return []
    env_assignments: List[str] = []
    hf_endpoint = _first_env("VLLM_HF_ENDPOINT", "HF_ENDPOINT", default="").strip()
    if hf_endpoint:
        env_assignments.append(f"HF_ENDPOINT={shlex.quote(hf_endpoint)}")
    command_parts = [*env_assignments, shlex.quote(python_path), *[shlex.quote(part) for part in inner_args]]
    command = " ".join(command_parts)
    return ["wsl", "-d", distro, "--", "bash", "-lc", command]


def _wsl_vllm_available() -> bool:
    cmd = _wsl_vllm_command(["-m", "vllm.entrypoints.openai.api_server", "--help"])
    if not cmd:
        return False
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _rerank_runtime_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def _is_windows() -> bool:
    return os.name == "nt"


def _normalize_openai_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return normalized
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def _is_local_base_url(base_url: str) -> bool:
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        return False
    return host in {"127.0.0.1", "0.0.0.0", "localhost", "::1"}


def _first_env(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key)
        if value not in (None, ""):
            return value
    return default


def _looks_like_model_reference(model_path: str) -> bool:
    value = (model_path or "").strip()
    if not value:
        return False
    if os.path.exists(value):
        return False
    if "://" in value or value.startswith(".") or value.startswith("/") or value.startswith("\\"):
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    parts = [part for part in value.split("/") if part]
    return len(parts) >= 2 and " " not in value


def _model_cache_dir_for_ref(model_ref: str) -> str:
    safe_name = (
        model_ref.strip()
        .replace("\\", "--")
        .replace("/", "--")
        .replace(":", "_")
        .replace(" ", "_")
    )
    return os.path.join(MODEL_CACHE_DIR, safe_name)


def _ensure_model_path(model_path: str) -> str:
    value = (model_path or "").strip()
    if not value:
        raise FileNotFoundError("model_path is required")
    if os.path.isdir(value):
        return value
    if _looks_like_model_reference(value):
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "模型不存在于本地，且缺少 huggingface_hub，无法自动下载。"
            ) from exc
        local_dir = _model_cache_dir_for_ref(value)
        Path(MODEL_CACHE_DIR).mkdir(parents=True, exist_ok=True)
        snapshot_download(repo_id=value, local_dir=local_dir)
        return local_dir
    raise FileNotFoundError(f"Model path does not exist: {value}")


def _windows_to_wsl_path(path: str) -> str:
    normalized = os.path.abspath(path).replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[0].lower()
        remainder = normalized[2:].lstrip("/")
        return f"/mnt/{drive}/{remainder}"
    return normalized


def _resolve_vllm_model_target(model_path: str, *, use_wsl: bool) -> str:
    value = (model_path or "").strip()
    if not value:
        raise FileNotFoundError("model_path is required")
    if not use_wsl:
        return _ensure_model_path(value)
    if os.path.exists(value):
        return _windows_to_wsl_path(value)
    if _looks_like_model_reference(value):
        return value
    raise FileNotFoundError(f"Model path does not exist: {value}")


def _resolve_local_or_model_ref(model_path: str) -> str:
    value = (model_path or "").strip()
    if not value:
        raise FileNotFoundError("model_path is required")
    if os.path.exists(value):
        return os.path.abspath(value)
    if _looks_like_model_reference(value):
        return value
    raise FileNotFoundError(f"Model path does not exist: {value}")


def _default_model_name(requested_model: str, resolved_model: str) -> str:
    requested = (requested_model or "").strip()
    if _looks_like_model_reference(requested):
        return requested
    return os.path.basename((resolved_model or requested).rstrip("/\\")) or requested


def _normalize_endpoint_type(endpoint_type: str, model_name: str = "", model_uid: str = "") -> str:
    value = (endpoint_type or "").strip().lower()
    if value in ENDPOINT_TYPES:
        return value
    sample = f"{value} {model_name} {model_uid}".lower()
    if any(token in sample for token in ("rerank", "reranker", "bge-reranker")):
        return "rerank"
    if any(token in sample for token in ("embed", "embedding", "bge", "e5", "gte")):
        return "embedding"
    return "chat"


def _build_headers(api_key: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if (api_key or "").strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def _extract_port(base_url: str) -> int:
    try:
        return urlparse(base_url).port or 0
    except Exception:
        return 0


def _parse_model_item(item: object) -> Dict[str, object]:
    payload = item if isinstance(item, dict) else {"id": str(item or "")}
    model_id = str(
        payload.get("id")
        or payload.get("model_name")
        or payload.get("name")
        or payload.get("model_uid")
        or payload.get("uid")
        or ""
    )
    model_uid = str(payload.get("model_uid") or payload.get("uid") or payload.get("name") or "")

    hint_parts: List[str] = [model_id, model_uid]
    for key in ("model_type", "task", "type"):
        if payload.get(key):
            hint_parts.append(str(payload.get(key)))
    ability = payload.get("ability") or payload.get("abilities") or payload.get("tasks")
    if isinstance(ability, list):
        hint_parts.extend(str(v) for v in ability if v)
    elif ability:
        hint_parts.append(str(ability))

    endpoint_type = _normalize_endpoint_type(" ".join(hint_parts), model_id, model_uid)

    details = {}
    for key in ("model_type", "task", "type", "ability", "abilities", "tasks", "owned_by"):
        if key in payload and payload.get(key) not in (None, ""):
            details[key] = payload.get(key)

    return {
        "id": model_id,
        "model_name": model_id,
        "model_uid": model_uid,
        "object": payload.get("object", "model"),
        "owned_by": payload.get("owned_by", ""),
        "endpoint_type": endpoint_type,
        "details": details,
    }


class ModelServingManager:
    """Manages local and remote model endpoints."""

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self._endpoints: Dict[str, ModelEndpoint] = {}
        self._processes: Dict[str, subprocess.Popen] = {}
        self._load()
        self._sync_configured_llm_endpoint()

    def _load(self):
        if os.path.exists(ENDPOINTS_FILE):
            try:
                with open(ENDPOINTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    if "endpoint_type" not in item:
                        item["endpoint_type"] = _normalize_endpoint_type(
                            item.get("endpoint_type", ""),
                            item.get("model_name", ""),
                            item.get("model_uid", ""),
                        )
                    endpoint = ModelEndpoint(**item)
                    if endpoint.process_id and endpoint.status in {"starting", "running"}:
                        endpoint.status = "stopped"
                        endpoint.process_id = None
                    self._endpoints[endpoint.endpoint_id] = endpoint
            except (json.JSONDecodeError, TypeError, ValueError):
                self._endpoints = {}
        self._save()

    def _save(self):
        with open(ENDPOINTS_FILE, "w", encoding="utf-8") as f:
            json.dump([asdict(ep) for ep in self._endpoints.values()], f, ensure_ascii=False, indent=2)

    def _sync_configured_llm_endpoint(self):
        provider = _first_env("LLM_PROVIDER", default="").strip().lower()
        base_url = _first_env("LLM_BASE_URL", "VLLM_BASE_URL", "XINFERENCE_BASE_URL", default="").strip()
        model_name = _first_env("LLM_MODEL", "VLLM_MODEL", "XINFERENCE_MODEL", default="").strip()
        api_key = _first_env("LLM_API_KEY", "VLLM_API_KEY", "XINFERENCE_API_KEY", default="").strip()

        if not base_url or not model_name:
            return

        normalized_url = _normalize_openai_base_url(base_url)
        backend = provider or ("vllm" if _is_local_base_url(normalized_url) else "manual")
        if backend not in {"vllm", "xinference", "manual", "openai-compatible"}:
            backend = "manual"
        if backend == "openai-compatible":
            backend = "manual"

        try:
            models = self.discover_models(base_url=normalized_url, api_key=api_key)
        except Exception:
            return

        target = next(
            (
                item for item in models
                if str(item.get("id") or item.get("model_name") or "").strip() == model_name
            ),
            None,
        ) or (models[0] if models else None)

        if target is None:
            return

        endpoint_type = _normalize_endpoint_type(
            str(target.get("endpoint_type") or "chat"),
            str(target.get("model_name") or model_name),
            str(target.get("model_uid") or ""),
        )
        resolved_name = str(target.get("model_name") or target.get("id") or model_name).strip() or model_name
        resolved_uid = str(target.get("model_uid") or "").strip()

        existing = next(
            (
                ep for ep in self._endpoints.values()
                if ep.base_url == normalized_url
                and ep.model_name == resolved_name
                and ep.endpoint_type == endpoint_type
            ),
            None,
        )
        if existing:
            existing.status = "running"
            existing.backend = backend
            existing.api_key = api_key
            existing.model_uid = resolved_uid
            existing.error_msg = ""
            self._save()
            return

        self.register_manual(
            base_url=normalized_url,
            model_name=resolved_name,
            api_key=api_key,
            backend=backend,
            model_uid=resolved_uid,
            endpoint_type=endpoint_type,
        )

    def _wait_until_ready(
        self,
        endpoint_id: str,
        proc: subprocess.Popen,
        failure_message: str,
        timeout_seconds: int = 60,
    ):
        endpoint = self._endpoints.get(endpoint_id)
        if not endpoint:
            return

        for _ in range(timeout_seconds):
            time.sleep(1)
            if self.health_check(endpoint_id):
                endpoint.status = "running"
                endpoint.error_msg = ""
                self._save()
                return
            if proc.poll() is not None:
                endpoint.status = "error"
                try:
                    _, stderr = proc.communicate(timeout=1)
                    stderr_text = stderr.decode("utf-8", errors="ignore").strip()
                except Exception:
                    stderr_text = ""
                endpoint.error_msg = failure_message if not stderr_text else f"{failure_message}: {stderr_text[-300:]}"
                self._save()
                return

        endpoint.status = "error"
        endpoint.error_msg = "Startup timed out"
        self._save()

    def start_serving(
        self,
        model_path: str,
        port: int = 0,
        finetune_task_id: str = "",
        model_name: str = "",
        host: str = "127.0.0.1",
        tensor_parallel_size: int = 1,
        gpu_memory_utilization: float = 0.9,
        max_model_len: int = 0,
        dtype: str = "auto",
        api_key: str = "",
        endpoint_type: str = "chat",
    ) -> ModelEndpoint:
        normalized_endpoint_type = _normalize_endpoint_type(endpoint_type, model_name, "")
        if normalized_endpoint_type == "rerank":
            if not _rerank_runtime_available():
                raise RuntimeError(
                    "sentence-transformers is not installed. Install it or register an external rerank endpoint."
                )

            resolved_model_path = _resolve_local_or_model_ref(model_path)

            if port == 0:
                port = _find_free_port()
            elif _is_port_in_use(port):
                raise RuntimeError(f"Port {port} is already in use")

            endpoint_id = uuid.uuid4().hex[:12]
            connect_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
            endpoint = ModelEndpoint(
                endpoint_id=endpoint_id,
                model_path=resolved_model_path,
                finetune_task_id=finetune_task_id,
                base_url=f"http://{connect_host}:{port}/v1",
                backend="rerank",
                status="starting",
                port=port,
                model_name=model_name or _default_model_name(model_path, resolved_model_path),
                host=host,
                api_key=(api_key or "").strip(),
                endpoint_type="rerank",
            )

            script_path = str(Path(__file__).with_name("rerank_server.py"))
            cmd = [
                sys.executable,
                script_path,
                "--model",
                resolved_model_path,
                "--host",
                endpoint.host,
                "--port",
                str(port),
                "--served-model-name",
                endpoint.model_name,
            ]
            if endpoint.api_key:
                cmd.extend(["--api-key", endpoint.api_key])

            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                endpoint.process_id = proc.pid
                self._processes[endpoint_id] = proc
                self._endpoints[endpoint_id] = endpoint
                self._save()
                threading.Thread(
                    target=self._wait_until_ready,
                    args=(endpoint_id, proc, "Rerank process failed to start", 180),
                    daemon=True,
                ).start()
            except Exception as exc:
                endpoint.status = "error"
                endpoint.error_msg = str(exc)
                self._endpoints[endpoint_id] = endpoint
                self._save()
            return endpoint

        use_wsl_vllm = False
        if _vllm_available():
            use_wsl_vllm = False
        elif _wsl_vllm_available():
            use_wsl_vllm = True
        else:
            if _is_windows():
                raise RuntimeError(
                    "当前环境未检测到可用的 vLLM。Windows 下请优先配置 "
                    "VLLM_WSL_DISTRO 和 VLLM_WSL_PYTHON 指向你的 WSL vLLM 环境，"
                    "或注册一个已运行的 OpenAI-compatible / vLLM 端点。"
                )
            raise RuntimeError("vLLM is not installed. Run `pip install vllm` or register an external endpoint.")

        resolved_model_path = _resolve_vllm_model_target(model_path, use_wsl=use_wsl_vllm)

        if port == 0:
            port = _find_free_port()
        elif _is_port_in_use(port):
            raise RuntimeError(f"Port {port} is already in use")

        endpoint_id = uuid.uuid4().hex[:12]
        connect_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        endpoint = ModelEndpoint(
            endpoint_id=endpoint_id,
            model_path=resolved_model_path,
            finetune_task_id=finetune_task_id,
            base_url=f"http://{connect_host}:{port}/v1",
            backend="vllm",
            status="starting",
            port=port,
            model_name=model_name or _default_model_name(model_path, resolved_model_path),
            host=host,
            tensor_parallel_size=max(1, int(tensor_parallel_size or 1)),
            gpu_memory_utilization=float(gpu_memory_utilization or 0.9),
            max_model_len=int(max_model_len or 0),
            dtype=(dtype or "auto").strip() or "auto",
            api_key=(api_key or "").strip(),
            endpoint_type=_normalize_endpoint_type(
                endpoint_type,
                model_name or _default_model_name(model_path, resolved_model_path),
                "",
            ),
        )

        inner_cmd = [
            "-m", "vllm.entrypoints.openai.api_server",
            "--model", resolved_model_path,
            "--host", endpoint.host,
            "--port", str(port),
            "--served-model-name", endpoint.model_name,
            "--tensor-parallel-size", str(endpoint.tensor_parallel_size),
            "--gpu-memory-utilization", str(endpoint.gpu_memory_utilization),
            "--dtype", endpoint.dtype,
        ]
        if endpoint.max_model_len > 0:
            inner_cmd.extend(["--max-model-len", str(endpoint.max_model_len)])
        if endpoint.api_key:
            inner_cmd.extend(["--api-key", endpoint.api_key])

        cmd = _wsl_vllm_command(inner_cmd) if use_wsl_vllm else ["python", *inner_cmd]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            endpoint.process_id = proc.pid
            self._processes[endpoint_id] = proc
            self._endpoints[endpoint_id] = endpoint
            self._save()
            threading.Thread(
                target=self._wait_until_ready,
                args=(endpoint_id, proc, "vLLM process failed to start", 120),
                daemon=True,
            ).start()
        except Exception as exc:
            endpoint.status = "error"
            endpoint.error_msg = str(exc)
            self._endpoints[endpoint_id] = endpoint
            self._save()
        return endpoint

    def _xinference_launch_candidates(self, host: str, port: int) -> List[List[str]]:
        candidates: List[List[str]] = []
        cli = which("xinference-local") or which("xinference-local.exe")
        if cli:
            candidates.extend([
                [cli, "--host", host, "--port", str(port)],
                [cli, "-H", host, "-p", str(port)],
            ])
        candidates.extend([
            ["python", "-m", "xinference.deploy.local", "--host", host, "--port", str(port)],
            ["python", "-m", "xinference.deploy.local", "-H", host, "-p", str(port)],
        ])
        return candidates

    def _launch_xinference_process(self, host: str, port: int) -> subprocess.Popen:
        errors: List[str] = []
        for cmd in self._xinference_launch_candidates(host, port):
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except FileNotFoundError as exc:
                errors.append(f"{' '.join(cmd)} -> {exc}")
                continue
            except OSError as exc:
                errors.append(f"{' '.join(cmd)} -> {exc}")
                continue

            time.sleep(2)
            if proc.poll() is None:
                return proc

            try:
                _, stderr = proc.communicate(timeout=2)
                stderr_text = stderr.decode("utf-8", errors="ignore").strip()
            except Exception:
                stderr_text = ""
            errors.append(f"{' '.join(cmd)} -> exit={proc.returncode} {stderr_text[-200:]}")

        suffix = f" Last error: {errors[-1]}" if errors else ""
        raise RuntimeError(
            "Unable to start Xinference. Ensure `xinference-local` or `python -m xinference.deploy.local` is available."
            + suffix
        )

    def start_xinference(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        model_name: str = "",
        model_uid: str = "",
        finetune_task_id: str = "",
        api_key: str = "",
        endpoint_type: str = "chat",
    ) -> ModelEndpoint:
        port = _find_xinference_port(port)
        connect_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        endpoint_id = uuid.uuid4().hex[:12]
        endpoint = ModelEndpoint(
            endpoint_id=endpoint_id,
            model_path="",
            finetune_task_id=finetune_task_id,
            base_url=f"http://{connect_host}:{port}/v1",
            backend="xinference",
            status="starting",
            port=port,
            model_name=(model_name or "xinference-service").strip(),
            host=host,
            api_key=(api_key or "").strip(),
            model_uid=(model_uid or "").strip(),
            endpoint_type=_normalize_endpoint_type(endpoint_type, model_name, model_uid),
        )

        try:
            proc = self._launch_xinference_process(host, port)
            endpoint.process_id = proc.pid
            self._processes[endpoint_id] = proc
            self._endpoints[endpoint_id] = endpoint
            self._save()
            threading.Thread(
                target=self._wait_until_ready,
                args=(endpoint_id, proc, "Xinference service failed to start"),
                daemon=True,
            ).start()
        except Exception as exc:
            endpoint.status = "error"
            endpoint.error_msg = str(exc)
            self._endpoints[endpoint_id] = endpoint
            self._save()
        return endpoint

    def stop_serving(self, endpoint_id: str) -> bool:
        endpoint = self._endpoints.get(endpoint_id)
        if not endpoint:
            return False

        proc = self._processes.pop(endpoint_id, None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

        endpoint.status = "stopped"
        endpoint.process_id = None
        self._save()
        return True

    def remove_endpoint(self, endpoint_id: str) -> bool:
        self.stop_serving(endpoint_id)
        if endpoint_id in self._endpoints:
            del self._endpoints[endpoint_id]
            self._save()
            return True
        return False

    def register_manual(
        self,
        base_url: str,
        model_name: str,
        finetune_task_id: str = "",
        api_key: str = "",
        backend: str = "manual",
        model_uid: str = "",
        endpoint_type: str = "chat",
    ) -> ModelEndpoint:
        endpoint_id = uuid.uuid4().hex[:12]
        normalized_url = _normalize_openai_base_url(base_url)
        endpoint = ModelEndpoint(
            endpoint_id=endpoint_id,
            model_path="",
            finetune_task_id=finetune_task_id,
            base_url=normalized_url,
            backend=(backend or "manual").strip().lower() or "manual",
            status="running",
            port=_extract_port(normalized_url),
            model_name=(model_name or "").strip(),
            api_key=(api_key or "").strip(),
            model_uid=(model_uid or "").strip(),
            endpoint_type=_normalize_endpoint_type(endpoint_type, model_name, model_uid),
        )
        self._endpoints[endpoint_id] = endpoint
        self._save()
        return endpoint

    def register_xinference(
        self,
        base_url: str,
        model_name: str,
        *,
        model_uid: str = "",
        finetune_task_id: str = "",
        api_key: str = "",
        endpoint_type: str = "chat",
    ) -> ModelEndpoint:
        return self.register_manual(
            base_url=base_url,
            model_name=model_name,
            finetune_task_id=finetune_task_id,
            api_key=api_key,
            backend="xinference",
            model_uid=model_uid,
            endpoint_type=endpoint_type,
        )

    def discover_models(
        self,
        *,
        endpoint_id: str = "",
        base_url: str = "",
        api_key: str = "",
    ) -> List[Dict[str, object]]:
        resolved_base_url = base_url
        resolved_api_key = api_key
        if endpoint_id:
            endpoint = self._endpoints.get(endpoint_id)
            if not endpoint:
                raise KeyError(f"endpoint not found: {endpoint_id}")
            resolved_base_url = endpoint.base_url
            resolved_api_key = endpoint.api_key

        normalized_url = _normalize_openai_base_url(resolved_base_url)
        if not normalized_url:
            raise ValueError("base_url is required")

        response = requests.get(
            f"{normalized_url}/models",
            headers=_build_headers(resolved_api_key),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            items = payload.get("data") or payload.get("models") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        if not isinstance(items, list):
            items = []
        return [_parse_model_item(item) for item in items]

    def health_check(self, endpoint_id: str) -> bool:
        if endpoint_id not in self._endpoints:
            return False
        try:
            self.discover_models(endpoint_id=endpoint_id)
            return True
        except Exception:
            return False

    def list_endpoints(self, *, endpoint_type: str = "", status: str = "") -> List[ModelEndpoint]:
        items = list(self._endpoints.values())
        if endpoint_type:
            normalized = _normalize_endpoint_type(endpoint_type)
            items = [ep for ep in items if ep.endpoint_type == normalized]
        if status:
            items = [ep for ep in items if ep.status == status]
        return sorted(items, key=lambda ep: ep.created_at, reverse=True)

    def get_endpoint(self, endpoint_id: str) -> Optional[ModelEndpoint]:
        return self._endpoints.get(endpoint_id)

    def get_best_endpoint(self, endpoint_type: str = "chat") -> Optional[ModelEndpoint]:
        normalized_type = _normalize_endpoint_type(endpoint_type)
        running = [
            ep for ep in self._endpoints.values()
            if ep.status == "running" and ep.endpoint_type == normalized_type
        ]
        backend_priority = {"vllm": 0, "xinference": 1, "manual": 2}
        running.sort(
            key=lambda ep: (
                0 if ep.finetune_task_id else 1,
                backend_priority.get(ep.backend, 9),
                -ep.created_at,
            )
        )
        return running[0] if running else None


_manager: Optional[ModelServingManager] = None


def get_model_serving_manager() -> ModelServingManager:
    global _manager
    if _manager is None:
        _manager = ModelServingManager()
    return _manager
