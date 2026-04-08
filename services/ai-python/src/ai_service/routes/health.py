"""Health check routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "ai-python",
        "model_backend": settings.model_backend_url,
        "retrieval_backend": settings.retrieval_backend_url,
    }
