from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
import socket
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


_dotenv_loaded = False


def ensure_dotenv_loaded() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    if load_dotenv is not None:
        load_dotenv()
    _dotenv_loaded = True


def first_env(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return default


def llm_provider() -> str:
    return first_env("LLM_PROVIDER").strip().lower()


def is_local_service_url(value: str | None) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}


def probe_local_service_url(value: str | None, timeout: float = 0.5) -> bool:
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


def build_runtime_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(repo_root / "src")
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def wait_until_ready(url: str, process: subprocess.Popen[bytes], timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(1)
    return False


def main() -> int:
    ensure_dotenv_loaded()
    parser = argparse.ArgumentParser(description="ReMe memory sidecar launcher")
    parser.add_argument("--host", default=os.environ.get("REME_SIDECAR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("REME_SIDECAR_PORT", "8765")))
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--working-dir", default=os.environ.get("REME_SIDECAR_WORKDIR", ".reme-sidecar"))
    parser.add_argument("--venv", default=os.environ.get("REME_SIDECAR_VENV", ".venv_reme_memory"))
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    venv_dir = Path(args.venv)
    if not venv_dir.is_absolute():
        venv_dir = repo_root / venv_dir
    python_exe = venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if not python_exe.exists():
        print(f"[error] ReMe sidecar python not found: {python_exe}")
        return 1

    provider = llm_provider()
    llm_base_url = first_env("REME_LLM_BASE_URL", "LLM_BASE_URL", "BASE_URL")
    embedding_base_url = first_env("REME_EMBEDDING_BASE_URL", "EMBEDDING_BASE_URL")
    if not embedding_base_url and provider != "vllm":
        embedding_base_url = first_env("REME_LLM_BASE_URL", "LLM_BASE_URL", "BASE_URL")
    if provider == "vllm" and not embedding_base_url:
        print("[error] ReMe embedding endpoint is not configured for local vLLM. Set REME_EMBEDDING_BASE_URL.")
        return 1
    if is_local_service_url(embedding_base_url) and not probe_local_service_url(embedding_base_url):
        print(f"[error] ReMe embedding endpoint is not reachable: {embedding_base_url}")
        return 1
    if is_local_service_url(llm_base_url) and not probe_local_service_url(llm_base_url):
        print(f"[error] ReMe LLM endpoint is not reachable: {llm_base_url}")
        return 1

    url = f"http://{args.host}:{args.port}"
    command = [
        str(python_exe),
        "-m",
        "agent_framework.memory.reme_sidecar_app",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--working-dir",
        args.working_dir,
        "--llm-api-key",
        first_env("REME_LLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY", "SILICONFLOW_API_KEY"),
        "--llm-base-url",
        first_env("REME_LLM_BASE_URL", "LLM_BASE_URL", "BASE_URL"),
        "--embedding-api-key",
        first_env(
            "REME_EMBEDDING_API_KEY",
            "EMBEDDING_API_KEY",
            *(() if provider == "vllm" else ("REME_LLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY", "SILICONFLOW_API_KEY")),
        ),
        "--embedding-base-url",
        embedding_base_url,
    ]
    embedding_dimensions = first_env("REME_EMBEDDING_DIMENSIONS")
    if embedding_dimensions:
        command.extend(["--embedding-dimensions", embedding_dimensions])

    process = subprocess.Popen(
        command,
        cwd=repo_root,
        env=build_runtime_env(repo_root),
    )
    if not wait_until_ready(url, process, args.timeout):
        print("[error] ReMe sidecar did not become ready in time.")
        return 1

    print(f"[ok] ReMe sidecar ready at {url}")
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
