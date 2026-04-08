"""Minimal boundary declarations for the AI-plane service."""

LANGUAGE_OWNER = "python"


def list_ai_capabilities() -> list[str]:
    return [
        "unified_chat_orchestration",
        "context_building",
        "rag_composition",
        "multi_agent_coordination",
        "model_routing",
    ]
