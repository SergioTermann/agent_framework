"""Multimodal inference routes.

Handles image understanding, audio processing, and other
non-text modality inputs.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel, Field

router = APIRouter(tags=["multimodal"])


class VisionRequest(BaseModel):
    model: str | None = None
    image_url: str | None = None
    prompt: str = "Describe this image."
    max_tokens: int = 1024


class VisionResponse(BaseModel):
    success: bool = True
    model: str = ""
    content: str = ""
    usage: dict[str, int] = Field(default_factory=dict)


@router.post("/vision/analyze", response_model=VisionResponse)
async def analyze_image(req: VisionRequest):
    """Analyze an image using a vision-capable model."""
    return VisionResponse(
        model=req.model or "",
        content="[model-python scaffold] vision not yet migrated",
    )


@router.post("/vision/upload")
async def upload_and_analyze(
    file: UploadFile = File(...),
    prompt: str = "Describe this image.",
):
    """Upload an image file and analyze it."""
    return {
        "success": True,
        "filename": file.filename,
        "content": "[model-python scaffold] upload analysis not yet migrated",
    }


@router.get("/multimodal/capabilities")
async def multimodal_capabilities():
    """List supported multimodal capabilities."""
    return {
        "success": True,
        "capabilities": [
            {"type": "vision", "models": ["Qwen/Qwen3-VL-32B-Instruct"]},
        ],
    }
