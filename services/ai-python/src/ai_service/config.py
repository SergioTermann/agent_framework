"""AI-plane service configuration."""

import os


class Settings:
    listen_host: str = os.environ.get("AI_SERVICE_HOST", "0.0.0.0")
    listen_port: int = int(os.environ.get("AI_SERVICE_PORT", "7002"))
    model_backend_url: str = os.environ.get("MODEL_BACKEND_URL", "http://127.0.0.1:7004")
    retrieval_backend_url: str = os.environ.get("RETRIEVAL_BACKEND_URL", "http://127.0.0.1:7005")
    default_model: str = os.environ.get("DEFAULT_MODEL", "Qwen/Qwen3-VL-32B-Instruct")
    base_url: str = os.environ.get("BASE_URL", "https://api.siliconflow.cn/v1")
    api_key: str = os.environ.get("SILICONFLOW_API_KEY", "")


settings = Settings()
