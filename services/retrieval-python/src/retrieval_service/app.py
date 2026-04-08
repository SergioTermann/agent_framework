"""FastAPI application for the retrieval-plane service."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from .config import settings
from .routes.health import router as health_router
from .routes.knowledge import router as knowledge_router
from .routes.rag import router as rag_router
from .routes.documents import router as documents_router

app = FastAPI(
    title="Agent Framework Retrieval Service",
    version="0.1.0",
    description="Retrieval-plane: RAG composition, knowledge base, document processing",
)

app.include_router(health_router)
app.include_router(knowledge_router, prefix="/api/v1/retrieval")
app.include_router(rag_router, prefix="/api/v1/retrieval")
app.include_router(documents_router, prefix="/api/v1/retrieval")


def main() -> None:
    uvicorn.run(
        "retrieval_service.app:app",
        host=settings.listen_host,
        port=settings.listen_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
