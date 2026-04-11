from __future__ import annotations

import errno
import shutil
import uuid
from pathlib import Path

import start_app


class _DummyProcess:
    pass


def _workspace_temp_dir():
    base_dir = Path.cwd() / "data" / "test_start_app"
    base_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = base_dir / uuid.uuid4().hex
    temp_dir.mkdir()
    return temp_dir


def test_resolve_go_binary_path_uses_platform_suffix(monkeypatch):
    temp_dir = _workspace_temp_dir()
    try:
        base_dir = temp_dir / "bin"
        base_dir.mkdir()

        monkeypatch.setattr(start_app.sys, "platform", "win32")
        assert start_app.resolve_go_binary_path(base_dir, "gateway").name == "gateway.exe"

        monkeypatch.setattr(start_app.sys, "platform", "darwin")
        assert start_app.resolve_go_binary_path(base_dir, "gateway").name == "gateway"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_build_runtime_env_accepts_host_and_port(monkeypatch):
    temp_dir = _workspace_temp_dir()
    try:
        monkeypatch.delenv("HOST", raising=False)
        monkeypatch.delenv("PORT", raising=False)

        env = start_app.build_runtime_env(temp_dir, host="127.0.0.1", port=9100)

        assert env["HOST"] == "127.0.0.1"
        assert env["PORT"] == "9100"
        assert str(temp_dir / "src") in env["PYTHONPATH"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_launch_process_rebuilds_unrunnable_binary(monkeypatch):
    temp_path = _workspace_temp_dir()
    try:
        original = temp_path / "gateway-go"
        rebuilt = temp_path / "gateway-go-rebuilt"
        calls: list[list[str]] = []
        attempts = {"count": 0}

        def fake_popen(command, cwd, env):
            calls.append(command)
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise OSError(errno.ENOEXEC, "Exec format error")
            return _DummyProcess()

        def rebuild():
            return rebuilt

        monkeypatch.setattr(start_app.subprocess, "Popen", fake_popen)

        process = start_app.launch_process(
            [str(original)],
            cwd=temp_path,
            env={"PYTHONPATH": "src"},
            rebuild=rebuild,
            label="gateway-go control plane",
        )

        assert isinstance(process, _DummyProcess)
        assert calls == [[str(original)], [str(rebuilt)]]
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


def test_build_gateway_control_plane_force_rebuild_replaces_existing_binary(monkeypatch):
    repo_root = _workspace_temp_dir()
    try:
        gateway_dir = repo_root / "services" / "gateway-go"
        gateway_dir.mkdir(parents=True)
        binary_path = gateway_dir / "gateway-go"
        binary_path.write_text("stale-binary", encoding="utf-8")
        recorded: dict[str, object] = {}

        class _Completed:
            returncode = 0

        def fake_run(command, cwd, env):
            recorded["command"] = command
            recorded["cwd"] = cwd
            recorded["env"] = env
            return _Completed()

        monkeypatch.setattr(start_app.sys, "platform", "darwin")
        monkeypatch.setattr(start_app.subprocess, "run", fake_run)

        result = start_app.build_gateway_control_plane(repo_root, force_rebuild=True)

        assert result == binary_path
        assert recorded["command"] == ["go", "build", "-o", str(binary_path), "./cmd/gateway"]
        assert recorded["cwd"] == gateway_dir
        assert recorded["env"]["CGO_ENABLED"] == "0"
        assert not binary_path.exists()
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
