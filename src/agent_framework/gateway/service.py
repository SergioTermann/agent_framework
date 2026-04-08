from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import os
import socket
import threading
import uuid
from typing import Any, Dict, Iterable, List, Optional

from agent_framework.api.auth_api import auth_manager
from agent_framework.core.config import get_config
from .models import GatewayConnection, GatewayNode, PushEvent, PushTarget, utcnow_iso
from .storage import GatewayStorage, NoopGatewayStorage


class GatewayService:
    def __init__(
        self,
        *,
        storage: GatewayStorage | None = None,
        namespace: str | None = None,
        node_id: str | None = None,
        db_path: str | None = None,
        allow_user_id_fallback: bool = False,
    ):
        cfg = get_config()
        gateway_cfg = getattr(cfg, "gateway", None)
        self.namespace = namespace or getattr(gateway_cfg, "namespace", "/gateway")
        self.node_id = node_id or self._default_node_id()
        resolved_db_path = db_path or getattr(gateway_cfg, "db_path", "./data/gateway.db")
        if storage is not None:
            self.storage = storage
        elif self._use_noop_storage():
            self.storage = NoopGatewayStorage(os.getenv("GATEWAY_DB_PATH", resolved_db_path))
        else:
            self.storage = GatewayStorage(os.getenv("GATEWAY_DB_PATH", resolved_db_path))
        self.allow_user_id_fallback = allow_user_id_fallback and getattr(
            gateway_cfg,
            "allow_user_id_fallback",
            True,
        )
        self.socketio = None
        self._lock = threading.RLock()
        self._sessions_by_key: dict[tuple[str, str], GatewayConnection] = {}
        self._user_index: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self._register_node()

    def bind_socketio(self, socketio) -> None:
        self.socketio = socketio
        self._register_node()

    def connect_client(
        self,
        *,
        sid: str,
        namespace: str,
        auth_payload: Optional[Dict[str, Any]] = None,
        replay_pending: bool = True,
    ) -> tuple[GatewayConnection, int]:
        principal = self._authenticate(auth_payload or {})
        now = utcnow_iso()
        connection = GatewayConnection(
            connection_id=str(uuid.uuid4()),
            sid=sid,
            user_id=principal["user_id"],
            node_id=self.node_id,
            namespace=namespace,
            device_id=principal.get("device_id"),
            connected_at=now,
            last_seen_at=now,
            metadata=principal.get("metadata", {}),
        )
        key = (namespace, sid)
        with self._lock:
            self._sessions_by_key[key] = connection
            self._user_index[connection.user_id].add(key)
        self.storage.upsert_connection(connection)
        self._sync_node_state(now)
        replayed = self.replay_pending_events(connection) if replay_pending else 0
        return connection, replayed

    def disconnect_client(self, *, sid: str, namespace: str) -> Optional[GatewayConnection]:
        key = (namespace, sid)
        now = utcnow_iso()
        with self._lock:
            connection = self._sessions_by_key.pop(key, None)
            if connection is not None:
                indexed = self._user_index.get(connection.user_id)
                if indexed is not None:
                    indexed.discard(key)
                    if not indexed:
                        self._user_index.pop(connection.user_id, None)
        if connection is not None:
            self.storage.set_connection_offline(connection.connection_id, now)
            self._sync_node_state(now)
        return connection

    def touch_connection(self, *, sid: str, namespace: str) -> GatewayConnection:
        key = (namespace, sid)
        now = utcnow_iso()
        with self._lock:
            connection = self._sessions_by_key.get(key)
            if connection is None:
                raise ValueError("connection not found")
            updated = replace(connection, last_seen_at=now)
            self._sessions_by_key[key] = updated
        self.storage.update_connection_seen(updated.connection_id, now)
        self._sync_node_state(now)
        return updated

    def get_session(self, *, sid: str, namespace: str) -> Optional[GatewayConnection]:
        with self._lock:
            return self._sessions_by_key.get((namespace, sid))

    def publish_event(self, event: PushEvent) -> Dict[str, Any]:
        normalized = replace(event, target=event.normalized_target())
        self.storage.create_event(normalized)
        sessions = self._select_sessions(normalized)
        if not sessions or self.socketio is None:
            self.storage.update_event_status(normalized.event_id, "PENDING_OFFLINE")
            return {
                "success": True,
                "event_id": normalized.event_id,
                "delivered_count": 0,
                "offline_queued": True,
            }

        delivered_count = self._deliver_event(normalized, sessions)
        if delivered_count == 0:
            self.storage.update_event_status(normalized.event_id, "PENDING_OFFLINE")
        else:
            self.storage.update_event_status(
                normalized.event_id,
                "DELIVERED",
                delivered_at=utcnow_iso(),
            )
        return {
            "success": True,
            "event_id": normalized.event_id,
            "delivered_count": delivered_count,
            "offline_queued": delivered_count == 0,
        }

    def deliver_live_event(self, event: PushEvent) -> Dict[str, Any]:
        normalized = replace(event, target=event.normalized_target())
        sessions = self._select_sessions(normalized)
        if not sessions or self.socketio is None:
            return {
                "success": True,
                "event_id": normalized.event_id,
                "delivered_count": 0,
                "offline_queued": True,
            }

        delivered_count = self._emit_event(normalized, sessions, persist_delivery=False)
        return {
            "success": True,
            "event_id": normalized.event_id,
            "delivered_count": delivered_count,
            "offline_queued": delivered_count == 0,
        }

    def replay_pending_events(self, connection: GatewayConnection) -> int:
        pending_events = self.storage.list_pending_events(connection.user_id)
        delivered = 0
        for record in pending_events:
            event = PushEvent(
                event_id=record["event_id"],
                event_type=record["event_type"],
                user_id=record["user_id"],
                conversation_id=record.get("conversation_id"),
                message_id=record.get("message_id"),
                target=record.get("target"),
                device_id=record.get("device_id"),
                exclude_device_id=record.get("exclude_device_id"),
                connection_id=record.get("connection_id"),
                payload=record.get("payload") or {},
                metadata=record.get("metadata") or {},
                created_at=record.get("created_at") or utcnow_iso(),
            )
            if self._connection_matches_event(connection, event):
                delivered += self._deliver_event(event, [connection])
                self.storage.update_event_status(event.event_id, "DELIVERED", delivered_at=utcnow_iso())
        return delivered

    def ack_event(
        self,
        *,
        sid: str,
        namespace: str,
        ack_id: str,
        ack_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not ack_id:
            raise ValueError("ack_id is required")
        connection = self.get_session(sid=sid, namespace=namespace)
        if connection is None:
            raise ValueError("connection not found")
        acked_at = utcnow_iso()
        self.storage.mark_delivery_acked(
            event_id=ack_id,
            connection_id=connection.connection_id,
            acked_at=acked_at,
            ack_payload=ack_payload or {},
        )
        self.storage.update_event_status(ack_id, "ACKED", acked_at=acked_at)
        return {
            "success": True,
            "event_id": ack_id,
            "connection_id": connection.connection_id,
            "acked_at": acked_at,
        }

    def list_nodes(self) -> List[Dict[str, Any]]:
        return self.storage.list_nodes()

    def list_online_users(self) -> List[Dict[str, Any]]:
        return self.storage.list_online_users()

    def list_user_connections(self, user_id: str, *, include_offline: bool = False) -> List[Dict[str, Any]]:
        return self.storage.list_user_connections(user_id, status=None if include_offline else "ONLINE")

    def list_pending_events(self, user_id: str) -> List[Dict[str, Any]]:
        return self.storage.list_pending_events(user_id)

    def get_event_status(self, event_id: str) -> Dict[str, Any] | None:
        event = self.storage.get_event(event_id)
        if event is None:
            return None
        event["deliveries"] = self.storage.list_event_deliveries(event_id)
        return event

    def _deliver_event(self, event: PushEvent, sessions: Iterable[GatewayConnection]) -> int:
        return self._emit_event(event, sessions, persist_delivery=True)

    def _emit_event(
        self,
        event: PushEvent,
        sessions: Iterable[GatewayConnection],
        *,
        persist_delivery: bool,
    ) -> int:
        delivered = 0
        if self.socketio is None:
            return delivered
        for session in sessions:
            try:
                self.socketio.emit(
                    event.event_type,
                    event.envelope(),
                    to=session.sid,
                    namespace=session.namespace,
                )
                if persist_delivery:
                    self.storage.add_delivery(
                        delivery_id=str(uuid.uuid4()),
                        event_id=event.event_id,
                        connection=session,
                        status="DELIVERED",
                        delivered_at=utcnow_iso(),
                    )
                delivered += 1
            except Exception:
                continue
        return delivered

    def _select_sessions(self, event: PushEvent) -> List[GatewayConnection]:
        with self._lock:
            keys = list(self._user_index.get(event.user_id, set()))
            sessions = [self._sessions_by_key[key] for key in keys if key in self._sessions_by_key]
        return [session for session in sessions if self._connection_matches_event(session, event)]

    def _connection_matches_event(self, connection: GatewayConnection, event: PushEvent) -> bool:
        if connection.user_id != event.user_id:
            return False
        target = event.normalized_target()
        if target is PushTarget.CONNECTION:
            return bool(event.connection_id) and connection.connection_id == event.connection_id
        if target is PushTarget.DEVICE:
            return bool(event.device_id) and connection.device_id == event.device_id
        if target is PushTarget.EXCLUDE_DEVICE:
            return connection.device_id != event.exclude_device_id
        return True

    def _authenticate(self, auth_payload: Dict[str, Any]) -> Dict[str, Any]:
        token = str(auth_payload.get("token") or "").strip()
        device_id = str(auth_payload.get("device_id") or "").strip() or None
        metadata = dict(auth_payload.get("metadata") or {})
        if token:
            claims = auth_manager.verify_token(token)
            if not claims:
                raise ValueError("invalid token")
            metadata["auth_mode"] = "token"
            metadata["claims"] = {
                key: value
                for key, value in claims.items()
                if key not in {"exp", "iat"}
            }
            return {
                "user_id": claims["user_id"],
                "device_id": device_id,
                "metadata": metadata,
            }
        if self.allow_user_id_fallback:
            user_id = str(auth_payload.get("user_id") or "").strip()
            if not user_id:
                raise ValueError("token or user_id is required")
            metadata["auth_mode"] = "user_id"
            return {
                "user_id": user_id,
                "device_id": device_id,
                "metadata": metadata,
            }
        raise ValueError("token is required")

    def _register_node(self) -> None:
        cfg = get_config()
        address = f"{cfg.server.host}:{cfg.server.port}{self.namespace}"
        now = utcnow_iso()
        node = GatewayNode(
            node_id=self.node_id,
            address=address,
            started_at=now,
            last_heartbeat=now,
            metadata={"hostname": socket.gethostname()},
            connection_count=self._connection_count(),
        )
        self.storage.upsert_node(node)

    def _sync_node_state(self, now: Optional[str] = None) -> None:
        self.storage.update_node_connection_count(
            self.node_id,
            self._connection_count(),
            now or utcnow_iso(),
        )

    def _connection_count(self) -> int:
        with self._lock:
            return len(self._sessions_by_key)

    @staticmethod
    def _default_node_id() -> str:
        return f"gw-{socket.gethostname()}-{os.getpid()}"

    @staticmethod
    def _use_noop_storage() -> bool:
        return str(os.getenv("GATEWAY_CONTROL_PLANE") or "python").strip().lower() == "go"


_gateway_service: GatewayService | None = None


def get_gateway_service() -> GatewayService:
    global _gateway_service
    if _gateway_service is None:
        _gateway_service = GatewayService()
    return _gateway_service


def set_gateway_service(service: GatewayService | None) -> None:
    global _gateway_service
    _gateway_service = service
