"""FastAPI application for the model-plane service."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from .config import settings
from .routes.health import router as health_router
from .routes.serving import router as serving_router
from .routes.rerank import router as rerank_router
from .routes.rlhf import router as rlhf_router
from .routes.multimodal import router as multimodal_router

app = FastAPI(
    title="Agent Framework Model Service",
    version="0.1.0",
    description="Model-plane: model serving, RLHF, reranking, multimodal inference",
)

app.include_router(health_router)
app.include_router(serving_router, prefix="/api/v1/model")
app.include_router(rerank_router, prefix="/api/v1/model")
app.include_router(rlhf_router, prefix="/api/v1/model")
app.include_router(multimodal_router, prefix="/api/v1/model")


def main() -> None:
    uvicorn.run(
        "model_service.app:app",
        host=settings.listen_host,
        port=settings.listen_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
