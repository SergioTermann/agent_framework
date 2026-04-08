"""Model routing and feedback loop routes.

Responsible for selecting the appropriate model/provider for a given request
based on task type, cost constraints, and quality requirements.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["model-routing"])


class RouteRequest(BaseModel):
    task_type: str = "chat"
    input_tokens: int = 0
    quality: str = "balanced"
    max_cost_per_1k: float | None = None
    preferred_providers: list[str] = Field(default_factory=list)


class RouteResponse(BaseModel):
    success: bool = True
    model: str = ""
    provider: str = ""
    estimated_cost_per_1k: float = 0.0
    reason: str = ""


@router.post("/model/route", response_model=RouteResponse)
async def route_model(req: RouteRequest):
    """Select the optimal model for a given task."""
    return RouteResponse(
        model="Qwen/Qwen3-VL-32B-Instruct",
        provider="siliconflow",
        estimated_cost_per_1k=0.002,
        reason="default model (routing not yet migrated)",
    )


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    rating: int = 0
    feedback_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/model/feedback")
async def submit_feedback(req: FeedbackRequest):
    """Submit quality feedback for model output."""
    return {
        "success": True,
        "message": "feedback recorded",
    }


@router.get("/model/providers")
async def list_providers():
    """List available model providers and their capabilities."""
    return {
        "success": True,
        "providers": [
            {
                "name": "siliconflow",
                "models": ["Qwen/Qwen3-VL-32B-Instruct"],
                "capabilities": ["chat", "vision", "function_calling"],
            },
        ],
    }
