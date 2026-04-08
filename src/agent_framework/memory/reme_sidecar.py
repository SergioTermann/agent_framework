from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable


class ReMeSidecarClient:
    def __init__(self, *, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"ReMe sidecar unavailable: {exc}") from exc
        if not result.get("success", False):
            raise RuntimeError(str(result.get("error", "unknown_error")))
        return result

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def add_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/memory/add", payload)["memory"]

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        return self._request("POST", "/memory/get", {"memory_id": memory_id})["memory"]

    def update_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/memory/update", payload)["memory"]

    def list_memories(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return self._request("POST", "/memory/list", payload)["memories"]

    def search_memories(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return self._request("POST", "/memory/search", payload)["memories"]


class ReMeSidecarLauncher:
    def __init__(self, config: dict[str, Any]):
        self.config = dict(config or {})
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def src_dir(self) -> Path:
        return self.repo_root / "src"

    def _python_executable(self) -> Path:
        sidecar = dict(self.config.get("sidecar") or {})
        venv_dir = Path(sidecar.get("venv_dir") or ".venv_reme_memory")
        if not venv_dir.is_absolute():
            venv_dir = self.repo_root / venv_dir
        scripts_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        return scripts_dir / ("python.exe" if os.name == "nt" else "python")

    def _command(self) -> list[str]:
        sidecar = dict(self.config.get("sidecar") or {})
        python_exe = self._python_executable()
        command = [
            str(python_exe),
            "-m",
            "agent_framework.memory.reme_sidecar_app",
            "--host",
            str(sidecar.get("host") or "127.0.0.1"),
            "--port",
            str(sidecar.get("port") or 8765),
            "--working-dir",
            str(sidecar.get("working_dir") or ".reme-sidecar"),
            "--llm-api-key",
            str(sidecar.get("llm_api_key") or ""),
            "--llm-base-url",
            str(sidecar.get("llm_base_url") or ""),
            "--embedding-api-key",
            str(sidecar.get("embedding_api_key") or ""),
            "--embedding-base-url",
            str(sidecar.get("embedding_base_url") or ""),
        ]
        embedding_dimensions = sidecar.get("embedding_dimensions")
        if embedding_dimensions is not None:
            command.extend(["--embedding-dimensions", str(embedding_dimensions)])
        return command

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = str(self.src_dir) if not existing_pythonpath else f"{self.src_dir}{os.pathsep}{existing_pythonpath}"
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def ensure_started(self, client: ReMeSidecarClient) -> None:
        try:
            client.health()
            return
        except Exception:
            pass

        sidecar = dict(self.config.get("sidecar") or {})
        if not sidecar.get("auto_start", True):
            raise RuntimeError("ReMe sidecar is not reachable and auto_start is disabled")

        python_exe = self._python_executable()
        if not python_exe.exists():
            raise RuntimeError(f"ReMe sidecar Python not found: {python_exe}")

        self.process = subprocess.Popen(
            self._command(),
            cwd=self.repo_root,
            env=self._env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.time() + float(sidecar.get("start_timeout", 45))
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"ReMe sidecar exited early with code {self.process.returncode}")
            try:
                client.health()
                return
            except Exception:
                time.sleep(1.0)
        raise RuntimeError("Timed out waiting for ReMe sidecar to become healthy")

def build_targets(*, scopes: Iterable[str] | None = None, user_id: str | None = None, memory_types: Iterable[str] | None = None) -> list[dict[str, str]]:
    scope_list = [str(scope) for scope in (scopes or []) if str(scope).strip()]
    requested_types = {str(item) for item in (memory_types or []) if str(item).strip()}
    targets: list[dict[str, str]] = []
    base_targets = scope_list or ([f"user:{user_id}"] if user_id else ["global"])
    use_task = "procedural" in requested_types if requested_types else False
    for target in base_targets:
        targets.append({"kind": "task" if use_task else "user", "target": target})
    deduped: list[dict[str, str]] = []
    for target in targets:
        if target not in deduped:
            deduped.append(target)
    return deduped
