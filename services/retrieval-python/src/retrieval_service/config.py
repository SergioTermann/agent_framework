"""Retrieval-plane service configuration."""

import os


class Settings:
    listen_host: str = os.environ.get("RETRIEVAL_SERVICE_HOST", "0.0.0.0")
    listen_port: int = int(os.environ.get("RETRIEVAL_SERVICE_PORT", "7005"))
    chroma_host: str = os.environ.get("CHROMA_HOST", "127.0.0.1")
    chroma_port: int = int(os.environ.get("CHROMA_PORT", "8000"))
    model_backend_url: str = os.environ.get("MODEL_BACKEND_URL", "http://127.0.0.1:7004")
    knowledge_data_dir: str = os.environ.get("KNOWLEDGE_DATA_DIR", "data/knowledge")


settings = Settings()
