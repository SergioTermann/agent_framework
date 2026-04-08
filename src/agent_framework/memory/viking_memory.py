from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any


@dataclass
class ExternalBackendProbe:
    name: str
    available: bool
    reason: str = ""


def probe_viking_backend(config: Mapping[str, Any] | None = None) -> ExternalBackendProbe:
    payload = dict(config or {})
    try:
        from vikingdb.memory import VikingMem  # noqa: F401
    except Exception as exc:
        return ExternalBackendProbe(
            name="viking",
            available=False,
            reason=f"import_failed:{type(exc).__name__}:{exc}",
        )

    access_key = str(payload.get("access_key") or "").strip()
    secret_key = str(payload.get("secret_key") or "").strip()
    if not access_key or not secret_key:
        return ExternalBackendProbe(
            name="viking",
            available=False,
            reason="missing_credentials",
        )

    return ExternalBackendProbe(name="viking", available=True, reason="ok")
