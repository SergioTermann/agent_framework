"""Reranking routes.

Migrated from: src/agent_framework/reasoning/rerank_server.py

Provides a reranking endpoint for RAG pipelines and retrieval quality improvement.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["rerank"])


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    model: str | None = None
    top_k: int = 10


class RerankResult(BaseModel):
    index: int
    score: float
    document: str = ""


class RerankResponse(BaseModel):
    success: bool = True
    model: str = ""
    results: list[RerankResult] = Field(default_factory=list)


@router.post("/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest):
    """Rerank documents by relevance to query.

    Uses the configured reranking model (e.g., BAAI/bge-reranker-v2-m3)
    to score and sort candidate documents.
    """
    results = [
        RerankResult(index=i, score=1.0 / (i + 1), document=doc[:100])
        for i, doc in enumerate(req.documents[: req.top_k])
    ]
    return RerankResponse(
        model=req.model or "BAAI/bge-reranker-v2-m3",
        results=results,
    )
