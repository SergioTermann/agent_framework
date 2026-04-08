"""Context assembly routes.

Migrated from: src/agent_framework/web/context_builder.py

Responsible for building the prompt context window from:
  - conversation history
  - retrieved knowledge chunks
  - tool definitions
  - system prompt templates
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["context"])


class ContextBuildRequest(BaseModel):
    conversation_id: str
    user_message: str
    max_tokens: int = 4096
    include_knowledge: bool = True
    include_tools: bool = True
    system_prompt: str | None = None


class ContextBuildResponse(BaseModel):
    success: bool = True
    messages: list[dict[str, Any]] = Field(default_factory=list)
    token_count: int = 0
    knowledge_chunks: list[dict[str, Any]] = Field(default_factory=list)
    tools_included: list[str] = Field(default_factory=list)


@router.post("/context/build", response_model=ContextBuildResponse)
async def build_context(req: ContextBuildRequest):
    """Build a context window for LLM consumption.

    Assembles conversation history, knowledge retrieval results,
    tool definitions, and system prompts into a message array.
    """
    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.append({"role": "user", "content": req.user_message})

    return ContextBuildResponse(
        messages=messages,
        token_count=len(req.user_message) // 4,
    )
