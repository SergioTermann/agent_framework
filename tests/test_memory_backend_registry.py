from __future__ import annotations

from pathlib import Path

from agent_framework.memory.backend_registry import resolve_memory_backend
from agent_framework.memory.reme_sidecar import ReMeSidecarLauncher, build_targets
from agent_framework.memory.system import get_memory_backend_info


def test_resolve_memory_backend_defaults_to_local():
    resolution = resolve_memory_backend({"backend": {"provider": "local", "fallback_to_local": True}})

    assert resolution.requested == "local"
    assert resolution.active == "local"
    assert resolution.fallback is False
    assert resolution.reason == "configured_local"


def test_resolve_memory_backend_falls_back_when_reme_unavailable(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.memory.backend_registry.probe_reme_backend",
        lambda: type("Probe", (), {"available": False, "reason": "import_failed:test"})(),
    )

    resolution = resolve_memory_backend(
        {
            "backend": {
                "provider": "reme",
                "fallback_to_local": True,
                "reme": {
                    "sidecar": {
                        "enabled": False,
                    }
                },
            }
        }
    )

    assert resolution.requested == "reme"
    assert resolution.active == "local"
    assert resolution.fallback is True
    assert resolution.reason == "reme_unavailable:import_failed:test"


def test_resolve_memory_backend_falls_back_when_viking_credentials_missing(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.memory.backend_registry.probe_viking_backend",
        lambda config: type("Probe", (), {"available": False, "reason": "missing_credentials"})(),
    )

    resolution = resolve_memory_backend({"backend": {"provider": "viking", "fallback_to_local": True, "viking": {}}})

    assert resolution.requested == "viking"
    assert resolution.active == "local"
    assert resolution.fallback is True
    assert resolution.reason == "viking_unavailable:missing_credentials"


def test_get_memory_backend_info_returns_snapshot(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.memory.system.resolve_memory_backend",
        lambda config: type(
            "Resolution",
            (),
            {
                "requested": "reme",
                "active": "local",
                "fallback": True,
                "reason": "reme_unavailable:import_failed",
            },
        )(),
    )
    monkeypatch.setattr("agent_framework.memory.system._memory_backend_info", None)

    info = get_memory_backend_info()

    assert info == {
        "requested": "reme",
        "active": "local",
        "fallback": True,
        "reason": "reme_unavailable:import_failed",
    }


def test_resolve_memory_backend_uses_reme_sidecar_when_venv_exists(workspace_tmp_dir, monkeypatch):
    venv_dir = workspace_tmp_dir / ".venv_reme_memory"
    scripts_dir = venv_dir / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr("agent_framework.memory.backend_registry._repo_root", lambda: workspace_tmp_dir)
    monkeypatch.setattr("agent_framework.memory.backend_registry._probe_local_service_url", lambda value, timeout=0.5: True)

    resolution = resolve_memory_backend(
        {
            "backend": {
                "provider": "reme",
                "fallback_to_local": True,
                "reme": {
                    "sidecar": {
                        "enabled": True,
                        "venv_dir": ".venv_reme_memory",
                    }
                },
            }
        }
    )

    assert resolution.requested == "reme"
    assert resolution.active == "reme"
    assert resolution.fallback is False
    assert resolution.reason == "reme_sidecar_ready"


def test_resolve_memory_backend_falls_back_when_reme_local_dependency_unreachable(workspace_tmp_dir, monkeypatch):
    venv_dir = workspace_tmp_dir / ".venv_reme_memory"
    scripts_dir = venv_dir / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr("agent_framework.memory.backend_registry._repo_root", lambda: workspace_tmp_dir)
    monkeypatch.setattr("agent_framework.memory.backend_registry._probe_local_service_url", lambda value, timeout=0.5: False)

    resolution = resolve_memory_backend(
        {
            "backend": {
                "provider": "reme",
                "fallback_to_local": True,
                "reme": {
                    "sidecar": {
                        "enabled": True,
                        "venv_dir": ".venv_reme_memory",
                        "embedding_base_url": "http://127.0.0.1:8000/v1",
                    }
                },
            }
        }
    )

    assert resolution.requested == "reme"
    assert resolution.active == "local"
    assert resolution.fallback is True
    assert resolution.reason == "reme_sidecar_dependency_unreachable:embedding_base_url_unreachable"


def test_resolve_memory_backend_falls_back_when_vllm_embedding_endpoint_missing(workspace_tmp_dir, monkeypatch):
    venv_dir = workspace_tmp_dir / ".venv_reme_memory"
    scripts_dir = venv_dir / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr("agent_framework.memory.backend_registry._repo_root", lambda: workspace_tmp_dir)

    resolution = resolve_memory_backend(
        {
            "backend": {
                "provider": "reme",
                "fallback_to_local": True,
                "reme": {
                    "sidecar": {
                        "enabled": True,
                        "venv_dir": ".venv_reme_memory",
                        "llm_provider": "vllm",
                        "llm_base_url": "http://127.0.0.1:8000/v1",
                        "embedding_base_url": "",
                    }
                },
            }
        }
    )

    assert resolution.requested == "reme"
    assert resolution.active == "local"
    assert resolution.fallback is True
    assert resolution.reason == "reme_sidecar_dependency_unreachable:embedding_base_url_missing_for_vllm"


def test_build_targets_prefers_task_for_procedural():
    targets = build_targets(scopes=["conversation:1", "global"], memory_types=["procedural"])

    assert targets == [
        {"kind": "task", "target": "conversation:1"},
        {"kind": "task", "target": "global"},
    ]


def test_reme_sidecar_launcher_builds_command():
    launcher = ReMeSidecarLauncher(
        {
            "sidecar": {
                "host": "127.0.0.1",
                "port": 8765,
                "working_dir": ".reme-sidecar",
                "venv_dir": ".venv_reme_memory",
            }
        }
    )

    command = launcher._command()

    assert command[1:4] == ["-m", "agent_framework.memory.reme_sidecar_app", "--host"]
    assert "8765" in command
    assert ".reme-sidecar" in command
    assert Path(command[0]).name in {"python", "python.exe"}
    assert "--embedding-dimensions" not in command


def test_reme_sidecar_launcher_includes_embedding_dimensions_when_configured():
    launcher = ReMeSidecarLauncher(
        {
            "sidecar": {
                "host": "127.0.0.1",
                "port": 8765,
                "working_dir": ".reme-sidecar",
                "venv_dir": ".venv_reme_memory",
                "embedding_dimensions": 768,
            }
        }
    )

    command = launcher._command()

    assert "--embedding-dimensions" in command
    assert "768" in command
