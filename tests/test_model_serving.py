from __future__ import annotations


def test_wsl_vllm_command_includes_hf_mirror(monkeypatch):
    from agent_framework.reasoning.model_serving import _wsl_vllm_command

    monkeypatch.setenv("VLLM_WSL_DISTRO", "Ubuntu-24.04")
    monkeypatch.setenv("VLLM_WSL_PYTHON", "/home/kevin/vllm-env/bin/python")
    monkeypatch.setenv("VLLM_HF_ENDPOINT", "https://hf-mirror.com")

    command = _wsl_vllm_command(["-m", "vllm.entrypoints.openai.api_server", "--help"])

    assert command[:4] == ["wsl", "-d", "Ubuntu-24.04", "--"]
    assert "HF_ENDPOINT=https://hf-mirror.com" in command[-1]
    assert "/home/kevin/vllm-env/bin/python" in command[-1]
