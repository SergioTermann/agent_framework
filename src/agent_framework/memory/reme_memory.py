from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExternalBackendProbe:
    name: str
    available: bool
    reason: str = ""


def probe_reme_backend() -> ExternalBackendProbe:
    try:
        import reme  # noqa: F401
    except Exception as exc:
        return ExternalBackendProbe(
            name="reme",
            available=False,
            reason=f"import_failed:{type(exc).__name__}:{exc}",
        )
    return ExternalBackendProbe(name="reme", available=True, reason="ok")
