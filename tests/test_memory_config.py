from __future__ import annotations


def test_load_config_reme_sidecar_falls_back_to_global_llm_env(monkeypatch):
    from agent_framework.memory import config as config_module

    monkeypatch.setattr(config_module, "_dotenv_loaded", True)
    load_config = config_module.load_config

    for key in [
        "REME_LLM_API_KEY",
        "REME_LLM_BASE_URL",
        "REME_EMBEDDING_API_KEY",
        "REME_EMBEDDING_BASE_URL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_BASE_URL",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_PROVIDER",
        "OPENAI_API_KEY",
        "SILICONFLOW_API_KEY",
        "BASE_URL",
        "REME_EMBEDDING_DIMENSIONS",
    ]:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_API_KEY", "global-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")

    config = load_config()
    sidecar = config["backend"]["reme"]["sidecar"]

    assert sidecar["llm_api_key"] == "global-key"
    assert sidecar["llm_base_url"] == "http://127.0.0.1:8000/v1"
    assert sidecar["embedding_api_key"] == "global-key"
    assert sidecar["embedding_base_url"] == "http://127.0.0.1:8000/v1"
    assert sidecar["embedding_dimensions"] is None


def test_load_config_reme_sidecar_does_not_reuse_vllm_chat_endpoint_for_embedding(monkeypatch):
    from agent_framework.memory import config as config_module

    monkeypatch.setattr(config_module, "_dotenv_loaded", True)
    load_config = config_module.load_config

    for key in [
        "REME_LLM_API_KEY",
        "REME_LLM_BASE_URL",
        "REME_EMBEDDING_API_KEY",
        "REME_EMBEDDING_BASE_URL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_BASE_URL",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "OPENAI_API_KEY",
        "SILICONFLOW_API_KEY",
        "BASE_URL",
        "LLM_PROVIDER",
        "REME_EMBEDDING_DIMENSIONS",
    ]:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    monkeypatch.setenv("LLM_API_KEY", "global-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")

    config = load_config()
    sidecar = config["backend"]["reme"]["sidecar"]

    assert sidecar["llm_api_key"] == "global-key"
    assert sidecar["llm_base_url"] == "http://127.0.0.1:8000/v1"
    assert sidecar["embedding_api_key"] == ""
    assert sidecar["embedding_base_url"] == ""
    assert sidecar["embedding_dimensions"] is None


def test_load_config_reme_sidecar_uses_explicit_embedding_dimensions(monkeypatch):
    from agent_framework.memory import config as config_module

    monkeypatch.setattr(config_module, "_dotenv_loaded", True)
    load_config = config_module.load_config
    monkeypatch.setenv("REME_EMBEDDING_DIMENSIONS", "768")

    config = load_config()

    assert config["backend"]["reme"]["sidecar"]["embedding_dimensions"] == 768
