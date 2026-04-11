"""Chroma telemetry helpers."""

from chromadb.telemetry.product import ProductTelemetryClient, ProductTelemetryEvent
from overrides import override


class NoOpProductTelemetryClient(ProductTelemetryClient):
    """Drop Chroma product telemetry events without touching PostHog."""

    @override
    def capture(self, event: ProductTelemetryEvent) -> None:
        return None
