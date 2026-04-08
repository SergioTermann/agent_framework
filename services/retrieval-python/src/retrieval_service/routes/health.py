"""Health check routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "retrieval-python",
        "chroma": f"{settings.chroma_host}:{settings.chroma_port}",
    }
