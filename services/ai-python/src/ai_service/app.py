"""FastAPI application for the AI-plane service."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from .config import settings
from .routes.chat import router as chat_router
from .routes.context import router as context_router
from .routes.multi_agent import router as multi_agent_router
from .routes.model_routing import router as model_routing_router
from .routes.health import router as health_router

app = FastAPI(
    title="Agent Framework AI Service",
    version="0.1.0",
    description="AI-plane: unified chat orchestration, context building, multi-agent coordination",
)

app.include_router(health_router)
app.include_router(chat_router, prefix="/api/v1/ai")
app.include_router(context_router, prefix="/api/v1/ai")
app.include_router(multi_agent_router, prefix="/api/v1/ai")
app.include_router(model_routing_router, prefix="/api/v1/ai")


def main() -> None:
    uvicorn.run(
        "ai_service.app:app",
        host=settings.listen_host,
        port=settings.listen_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
