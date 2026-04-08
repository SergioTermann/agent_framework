"""Model-plane service configuration."""

import os


class Settings:
    listen_host: str = os.environ.get("MODEL_SERVICE_HOST", "0.0.0.0")
    listen_port: int = int(os.environ.get("MODEL_SERVICE_PORT", "7004"))
    default_model: str = os.environ.get("DEFAULT_MODEL", "Qwen/Qwen3-VL-32B-Instruct")
    base_url: str = os.environ.get("BASE_URL", "https://api.siliconflow.cn/v1")
    api_key: str = os.environ.get("SILICONFLOW_API_KEY", "")
    rerank_model: str = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")


settings = Settings()
