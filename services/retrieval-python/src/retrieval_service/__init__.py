"""Retrieval-plane service scaffold."""

LANGUAGE_OWNER = "python"


def list_retrieval_capabilities() -> list[str]:
    return [
        "knowledge_base_orchestration",
        "rag_pipeline_composition",
        "document_parsing",
        "vector_search",
        "hybrid_retrieval",
    ]
