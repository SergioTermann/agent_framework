"""Model serving routes.

Migrated from: src/agent_framework/reasoning/model_serving.py

Handles LLM inference requests, provider routing, and response formatting.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["serving"])


class InferenceRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.9
    stream: bool = False
    tools: list[dict[str, Any]] = Field(default_factory=list)


class InferenceResponse(BaseModel):
    success: bool = True
    model: str = ""
    content: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    finish_reason: str = "stop"


@router.post("/inference", response_model=InferenceResponse)
async def inference(req: InferenceRequest):
    """Run model inference.

    Proxies to the configured LLM provider (SiliconFlow, vLLM, Ollama, etc.)
    and normalizes the response format.
    """
    return InferenceResponse(
        model=req.model or "",
        content="[model-python scaffold] inference not yet migrated",
    )


@router.get("/models")
async def list_models():
    """List available models from all configured providers."""
    return {
        "success": True,
        "models": [
            {
                "id": "Qwen/Qwen3-VL-32B-Instruct",
                "provider": "siliconflow",
                "type": "chat",
                "capabilities": ["chat", "vision", "function_calling"],
            },
        ],
    }


@router.get("/models/{model_id:path}")
async def get_model(model_id: str):
    """Get details for a specific model."""
    return {
        "success": True,
        "model_id": model_id,
        "status": "available",
    }
