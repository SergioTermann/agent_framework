"""Unified chat orchestration routes.

This module owns the core chat loop: receiving user messages, building context,
calling the LLM, executing tool calls, and streaming responses back.

In the monolith these live in:
  - src/agent_framework/api/unified_chat_api.py
  - src/agent_framework/web/unified_orchestrator.py
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    tools: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    success: bool = True
    conversation_id: str = ""
    message: str = ""
    model: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/chat", response_model=ChatResponse)
async def unified_chat(req: ChatRequest):
    """Unified chat endpoint.

    Current implementation returns a scaffold response.
    Full orchestration logic will be migrated from the monolith's
    ``UnifiedOrchestrator.process_message``.
    """
    return ChatResponse(
        conversation_id=req.conversation_id or "new",
        message="[ai-python scaffold] orchestration not yet migrated",
        model=req.model or "",
    )


@router.post("/chat/stream")
async def unified_chat_stream(req: ChatRequest):
    """Streaming chat endpoint (SSE).

    Will wrap the same orchestration loop but yield Server-Sent Events.
    """
    return {
        "success": False,
        "error": "streaming not yet migrated",
    }
