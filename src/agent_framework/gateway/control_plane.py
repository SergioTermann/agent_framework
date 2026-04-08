from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from flask import has_request_context, request

from .models import GatewayConnection, PushEvent


def gateway_control_plane_mode() -> str:
    return str(os.getenv("GATEWAY_CONTROL_PLANE") or "python").strip().lower()


def use_go_control_plane() -> bool:
    return gateway_control_plane_mode() == "go"


def gateway_control_plane_url() -> str:
    return str(os.getenv("GATEWAY_CONTROL_PLANE_URL") or "http://127.0.0.1:7000").strip().rstrip("/")


def publish_event_to_control_plane(
    event: PushEvent,
    *,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    if not use_go_control_plane():
        return None
    body = {
        "event_id": event.event_id,
        "created_at": event.created_at,
        "user_id": event.user_id,
        "event": event.event_type,
        "payload": event.payload,
        "target": event.normalized_target().value,
        "device_id": event.device_id,
        "exclude_device_id": event.exclude_device_id,
        "connection_id": event.connection_id,
        "conversation_id": event.conversation_id,
        "message_id": event.message_id,
        "metadata": event.metadata,
    }
    return _request_json("POST", "/api/gateway/push", body=body, authorization=authorization, token=token)


def connect_connection_to_control_plane(
    connection: GatewayConnection,
    *,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    if not use_go_control_plane():
        return None
    body = {
        "connection_id": connection.connection_id,
        "user_id": connection.user_id,
        "sid": connection.sid,
        "namespace": connection.namespace,
        "device_id": connection.device_id,
        "metadata": connection.metadata,
    }
    return _request_json("POST", "/api/gateway/connections", body=body, authorization=authorization, token=token)


def touch_connection_in_control_plane(
    connection_id: str,
    *,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    if not use_go_control_plane():
        return None
    return _request_json(
        "POST",
        f"/api/gateway/connections/{connection_id}/heartbeat",
        body={},
        authorization=authorization,
        token=token,
    )


def disconnect_connection_from_control_plane(
    connection_id: str,
    *,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    if not use_go_control_plane():
        return None
    return _request_json(
        "DELETE",
        f"/api/gateway/connections/{connection_id}",
        authorization=authorization,
        token=token,
    )


def ack_event_in_control_plane(
    event_id: str,
    *,
    connection_id: str,
    ack_payload: dict[str, Any] | None = None,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    if not use_go_control_plane():
        return None
    return _request_json(
        "POST",
        f"/api/gateway/events/{event_id}/ack",
        body={
            "connection_id": connection_id,
            "ack_payload": ack_payload or {},
        },
        authorization=authorization,
        token=token,
    )


def replay_pending_events_from_control_plane(
    connection_id: str,
    *,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    if not use_go_control_plane():
        return None
    return _request_json(
        "POST",
        f"/api/gateway/connections/{connection_id}/replay-pending",
        body={},
        authorization=authorization,
        token=token,
    )


def _request_json(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    auth_header = _resolve_authorization(authorization=authorization, token=token)
    if not auth_header:
        raise ValueError("authorization is required for go gateway control plane")

    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    upstream_request = urllib.request.Request(
        f"{gateway_control_plane_url()}{path}",
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(upstream_request, timeout=15) as response:
            raw_body = response.read()
            status_code = response.status
    except urllib.error.HTTPError as exc:
        raw_body = exc.read()
        status_code = exc.code
    except urllib.error.URLError as exc:
        raise RuntimeError(f"go gateway unavailable: {exc.reason}") from exc

    try:
        parsed = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid response from go gateway control plane") from exc

    if status_code >= 400 or not parsed.get("success", False):
        error = parsed.get("error") or parsed.get("message") or f"go gateway error ({status_code})"
        raise RuntimeError(str(error))

    data = parsed.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("go gateway control plane returned invalid data")
    return data


def _resolve_authorization(*, authorization: str | None = None, token: str | None = None) -> str | None:
    explicit = str(authorization or "").strip()
    if explicit:
        return explicit

    raw_token = str(token or "").strip()
    if raw_token:
        if raw_token.lower().startswith("bearer "):
            return raw_token
        return f"Bearer {raw_token}"

    if has_request_context():
        request_auth = str(request.headers.get("Authorization") or "").strip()
        if request_auth:
            return request_auth

    return None
