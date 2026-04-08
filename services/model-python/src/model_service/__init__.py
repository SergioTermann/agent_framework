"""Model-plane service scaffold."""

LANGUAGE_OWNER = "python"


def list_model_capabilities() -> list[str]:
    return [
        "model_serving",
        "multimodal_inference",
        "rlhf_training",
        "reranking",
        "provider_adapters",
    ]
