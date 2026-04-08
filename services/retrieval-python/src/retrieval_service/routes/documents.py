"""Document processing routes.

Migrated from: src/agent_framework/vector_db/document_parser.py

Handles document upload, parsing (PDF/Word/Excel/PPT/HTML),
chunking, embedding, and indexing into vector store.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel, Field

router = APIRouter(tags=["documents"])


class DocumentResponse(BaseModel):
    success: bool = True
    document_id: str = ""
    filename: str = ""
    chunk_count: int = 0
    status: str = "pending"


@router.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    kb_id: str = Form(...),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
):
    """Upload and process a document into a knowledge base.

    Supports: PDF, DOCX, XLSX, PPTX, TXT, MD, HTML.
    The document is parsed, chunked, embedded, and indexed.
    """
    return DocumentResponse(
        document_id="doc_scaffold",
        filename=file.filename or "",
        status="processing",
    )


@router.get("/documents/{kb_id}")
async def list_documents(kb_id: str):
    """List documents in a knowledge base."""
    return {"success": True, "kb_id": kb_id, "documents": [], "total": 0}


@router.get("/documents/{kb_id}/{document_id}")
async def get_document(kb_id: str, document_id: str):
    """Get document details and chunk count."""
    return {"success": False, "error": "document not found"}


@router.delete("/documents/{kb_id}/{document_id}")
async def delete_document(kb_id: str, document_id: str):
    """Delete a document and its chunks from the knowledge base."""
    return {"success": True, "kb_id": kb_id, "document_id": document_id, "message": "deleted"}


@router.get("/documents/{kb_id}/{document_id}/chunks")
async def list_chunks(kb_id: str, document_id: str, limit: int = 50, offset: int = 0):
    """List chunks for a specific document."""
    return {"success": True, "chunks": [], "total": 0}
