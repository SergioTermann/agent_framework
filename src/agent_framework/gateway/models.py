from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, Optional
import uuid


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


class PushTarget(str, Enum):
    ALL = "ALL"
    DEVICE = "DEVICE"
    EXCLUDE_DEVICE = "EXCLUDE_DEVICE"
    CONNECTION = "CONNECTION"

    @classmethod
    def from_value(cls, value: str | None) -> "PushTarget":
        normalized = str(value or cls.ALL.value).strip().upper()
        alias_map = {
            "CURRENT_DEVICE": cls.DEVICE,
            "CURRENT_CONNECTION": cls.CONNECTION,
            "EXCLUDE_CURRENT_DEVICE": cls.EXCLUDE_DEVICE,
        }
        if normalized in alias_map:
            return alias_map[normalized]
        try:
            return cls(normalized)
        except ValueError:
            return cls.ALL


@dataclass(slots=True)
class GatewayNode:
    node_id: str
    address: str
    status: str = "UP"
    started_at: str = field(default_factory=utcnow_iso)
    last_heartbeat: str = field(default_factory=utcnow_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)
    connection_count: int = 0


@dataclass(slots=True)
class GatewayConnection:
    connection_id: str
    sid: str
    user_id: str
    node_id: str
    namespace: str
    device_id: Optional[str] = None
    connected_at: str = field(default_factory=utcnow_iso)
    last_seen_at: str = field(default_factory=utcnow_iso)
    status: str = "ONLINE"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PushEvent:
    user_id: str
    event_type: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=utcnow_iso)
    target: PushTarget | str = PushTarget.ALL
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    device_id: Optional[str] = None
    exclude_device_id: Optional[str] = None
    connection_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalized_target(self) -> PushTarget:
        if isinstance(self.target, PushTarget):
            return self.target
        return PushTarget.from_value(self.target)

    def envelope(self) -> Dict[str, Any]:
        envelope = {
            "traceId": self.event_id,
            "event": self.event_type,
            "timestamp": now_ms(),
            "data": self.payload,
            "ackId": self.event_id,
        }
        if self.metadata:
            envelope["metadata"] = self.metadata
        return envelope
