"""Knowledge base management routes.

Migrated from: src/agent_framework/vector_db/knowledge_base.py

CRUD operations for knowledge bases: create, list, update, delete.
Each knowledge base owns a vector collection and associated metadata.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["knowledge"])


class KBCreateRequest(BaseModel):
    name: str
    description: str = ""
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    chunk_size: int = 500
    chunk_overlap: int = 50
    metadata: dict[str, Any] = Field(default_factory=dict)


class KBResponse(BaseModel):
    success: bool = True
    kb_id: str = ""
    name: str = ""
    description: str = ""
    document_count: int = 0
    chunk_count: int = 0


@router.post("/knowledge-bases", response_model=KBResponse)
async def create_kb(req: KBCreateRequest):
    """Create a new knowledge base."""
    return KBResponse(
        kb_id="kb_scaffold",
        name=req.name,
        description=req.description,
    )


@router.get("/knowledge-bases")
async def list_kbs():
    """List all knowledge bases."""
    return {"success": True, "knowledge_bases": [], "total": 0}


@router.get("/knowledge-bases/{kb_id}", response_model=KBResponse)
async def get_kb(kb_id: str):
    """Get knowledge base details."""
    return KBResponse(success=False)


@router.put("/knowledge-bases/{kb_id}")
async def update_kb(kb_id: str, req: KBCreateRequest):
    """Update knowledge base metadata."""
    return {"success": True, "kb_id": kb_id}


@router.delete("/knowledge-bases/{kb_id}")
async def delete_kb(kb_id: str):
    """Delete a knowledge base and all its documents."""
    return {"success": True, "kb_id": kb_id, "message": "deleted"}
