from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from agent_framework.core.database import DatabaseManager
from .models import GatewayConnection, GatewayNode, PushEvent


class GatewayStorage:
    def __init__(self, db_path: str = "./data/gateway.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_manager = DatabaseManager()
        self._init_db()

    def _init_db(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS gateway_nodes (
            node_id TEXT PRIMARY KEY,
            address TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            last_heartbeat TEXT NOT NULL,
            metadata TEXT,
            connection_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS gateway_connections (
            connection_id TEXT PRIMARY KEY,
            sid TEXT NOT NULL,
            user_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            device_id TEXT,
            connected_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            status TEXT NOT NULL,
            metadata TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_gateway_connections_user_status
        ON gateway_connections(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_gateway_connections_node_status
        ON gateway_connections(node_id, status);

        CREATE TABLE IF NOT EXISTS gateway_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            user_id TEXT NOT NULL,
            conversation_id TEXT,
            message_id TEXT,
            target TEXT NOT NULL,
            device_id TEXT,
            exclude_device_id TEXT,
            connection_id TEXT,
            payload TEXT NOT NULL,
            metadata TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            delivered_at TEXT,
            acked_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_gateway_events_user_status
        ON gateway_events(user_id, status, created_at);

        CREATE TABLE IF NOT EXISTS gateway_deliveries (
            delivery_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            connection_id TEXT NOT NULL,
            sid TEXT NOT NULL,
            device_id TEXT,
            status TEXT NOT NULL,
            delivered_at TEXT,
            acked_at TEXT,
            ack_payload TEXT,
            UNIQUE(event_id, connection_id)
        );

        CREATE INDEX IF NOT EXISTS idx_gateway_deliveries_event
        ON gateway_deliveries(event_id);
        """
        self.db_manager.init_table(self.db_path, schema)

    def upsert_node(self, node: GatewayNode) -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO gateway_nodes (
                    node_id, address, status, started_at, last_heartbeat, metadata, connection_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    address=excluded.address,
                    status=excluded.status,
                    last_heartbeat=excluded.last_heartbeat,
                    metadata=excluded.metadata,
                    connection_count=excluded.connection_count
                """,
                (
                    node.node_id,
                    node.address,
                    node.status,
                    node.started_at,
                    node.last_heartbeat,
                    json.dumps(node.metadata),
                    node.connection_count,
                ),
            )

    def update_node_connection_count(self, node_id: str, connection_count: int, heartbeat_at: str) -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE gateway_nodes
                SET connection_count = ?, last_heartbeat = ?, status = 'UP'
                WHERE node_id = ?
                """,
                (connection_count, heartbeat_at, node_id),
            )

    def list_nodes(self) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM gateway_nodes ORDER BY last_heartbeat DESC"
            ).fetchall()
        return [self._row_to_dict(row, json_fields={"metadata"}) for row in rows]

    def upsert_connection(self, connection: GatewayConnection) -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO gateway_connections (
                    connection_id, sid, user_id, node_id, namespace, device_id,
                    connected_at, last_seen_at, status, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(connection_id) DO UPDATE SET
                    sid=excluded.sid,
                    user_id=excluded.user_id,
                    node_id=excluded.node_id,
                    namespace=excluded.namespace,
                    device_id=excluded.device_id,
                    last_seen_at=excluded.last_seen_at,
                    status=excluded.status,
                    metadata=excluded.metadata
                """,
                (
                    connection.connection_id,
                    connection.sid,
                    connection.user_id,
                    connection.node_id,
                    connection.namespace,
                    connection.device_id,
                    connection.connected_at,
                    connection.last_seen_at,
                    connection.status,
                    json.dumps(connection.metadata),
                ),
            )

    def update_connection_seen(self, connection_id: str, last_seen_at: str) -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE gateway_connections
                SET last_seen_at = ?, status = 'ONLINE'
                WHERE connection_id = ?
                """,
                (last_seen_at, connection_id),
            )

    def set_connection_offline(self, connection_id: str, last_seen_at: str) -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE gateway_connections
                SET status = 'OFFLINE', last_seen_at = ?
                WHERE connection_id = ?
                """,
                (last_seen_at, connection_id),
            )

    def list_user_connections(self, user_id: str, status: str | None = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM gateway_connections WHERE user_id = ?"
        params: list[Any] = [user_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY connected_at ASC"
        with self.db_manager.get_connection(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row, json_fields={"metadata"}) for row in rows]

    def list_online_users(self) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT user_id, COUNT(*) AS connection_count, MAX(last_seen_at) AS last_seen_at
                FROM gateway_connections
                WHERE status = 'ONLINE'
                GROUP BY user_id
                ORDER BY last_seen_at DESC
                """
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def create_event(self, event: PushEvent, status: str = "CREATED") -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO gateway_events (
                    event_id, event_type, user_id, conversation_id, message_id, target,
                    device_id, exclude_device_id, connection_id, payload, metadata,
                    status, created_at, delivered_at, acked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.user_id,
                    event.conversation_id,
                    event.message_id,
                    event.normalized_target().value,
                    event.device_id,
                    event.exclude_device_id,
                    event.connection_id,
                    json.dumps(event.payload),
                    json.dumps(event.metadata),
                    status,
                    event.created_at,
                ),
            )

    def update_event_status(
        self,
        event_id: str,
        status: str,
        *,
        delivered_at: Optional[str] = None,
        acked_at: Optional[str] = None,
    ) -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE gateway_events
                SET status = ?,
                    delivered_at = COALESCE(?, delivered_at),
                    acked_at = COALESCE(?, acked_at)
                WHERE event_id = ?
                """,
                (status, delivered_at, acked_at, event_id),
            )

    def list_pending_events(self, user_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM gateway_events
                WHERE user_id = ? AND status = 'PENDING_OFFLINE'
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_dict(row, json_fields={"payload", "metadata"}) for row in rows]

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        with self.db_manager.get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM gateway_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row, json_fields={"payload", "metadata"})

    def list_event_deliveries(self, event_id: str) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM gateway_deliveries WHERE event_id = ? ORDER BY delivered_at ASC",
                (event_id,),
            ).fetchall()
        return [self._row_to_dict(row, json_fields={"ack_payload"}) for row in rows]

    def add_delivery(
        self,
        *,
        delivery_id: str,
        event_id: str,
        connection: GatewayConnection,
        status: str,
        delivered_at: Optional[str],
    ) -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO gateway_deliveries (
                    delivery_id, event_id, connection_id, sid, device_id, status,
                    delivered_at, acked_at, ack_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                ON CONFLICT(event_id, connection_id) DO UPDATE SET
                    sid=excluded.sid,
                    device_id=excluded.device_id,
                    status=excluded.status,
                    delivered_at=excluded.delivered_at
                """,
                (
                    delivery_id,
                    event_id,
                    connection.connection_id,
                    connection.sid,
                    connection.device_id,
                    status,
                    delivered_at,
                ),
            )

    def mark_delivery_acked(
        self,
        *,
        event_id: str,
        connection_id: str,
        acked_at: str,
        ack_payload: Dict[str, Any],
    ) -> None:
        with self.db_manager.get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE gateway_deliveries
                SET status = 'ACKED', acked_at = ?, ack_payload = ?
                WHERE event_id = ? AND connection_id = ?
                """,
                (acked_at, json.dumps(ack_payload), event_id, connection_id),
            )

    @staticmethod
    def _row_to_dict(row: Any, json_fields: Iterable[str] = ()) -> Dict[str, Any]:
        data = dict(row)
        for field in json_fields:
            if field not in data:
                continue
            if data.get(field):
                data[field] = json.loads(data[field])
            else:
                data[field] = {}
        return data


class NoopGatewayStorage:
    def __init__(self, db_path: str = "./data/gateway.db"):
        self.db_path = db_path

    def upsert_node(self, node: GatewayNode) -> None:
        return None

    def update_node_connection_count(self, node_id: str, connection_count: int, heartbeat_at: str) -> None:
        return None

    def list_nodes(self) -> List[Dict[str, Any]]:
        return []

    def upsert_connection(self, connection: GatewayConnection) -> None:
        return None

    def update_connection_seen(self, connection_id: str, last_seen_at: str) -> None:
        return None

    def set_connection_offline(self, connection_id: str, last_seen_at: str) -> None:
        return None

    def list_user_connections(self, user_id: str, status: str | None = None) -> List[Dict[str, Any]]:
        return []

    def list_online_users(self) -> List[Dict[str, Any]]:
        return []

    def create_event(self, event: PushEvent, status: str = "CREATED") -> None:
        return None

    def update_event_status(
        self,
        event_id: str,
        status: str,
        *,
        delivered_at: Optional[str] = None,
        acked_at: Optional[str] = None,
    ) -> None:
        return None

    def list_pending_events(self, user_id: str) -> List[Dict[str, Any]]:
        return []

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        return None

    def list_event_deliveries(self, event_id: str) -> List[Dict[str, Any]]:
        return []

    def add_delivery(
        self,
        *,
        delivery_id: str,
        event_id: str,
        connection: GatewayConnection,
        status: str,
        delivered_at: Optional[str],
    ) -> None:
        return None

    def mark_delivery_acked(
        self,
        *,
        event_id: str,
        connection_id: str,
        acked_at: str,
        ack_payload: Dict[str, Any],
    ) -> None:
        return None
