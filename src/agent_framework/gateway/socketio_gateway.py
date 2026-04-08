from __future__ import annotations

import uuid

from flask import request
from flask_socketio import emit

from .control_plane import (
    ack_event_in_control_plane,
    connect_connection_to_control_plane,
    disconnect_connection_from_control_plane,
    publish_event_to_control_plane,
    replay_pending_events_from_control_plane,
    touch_connection_in_control_plane,
    use_go_control_plane,
)
from .models import PushEvent
from .service import get_gateway_service


_registered_socketio_ids: set[int] = set()
_auth_tokens_by_session: dict[tuple[str, str], str] = {}


def _payload(data):
    return data if isinstance(data, dict) else {}


def _session_key(namespace: str, sid: str) -> tuple[str, str]:
    return namespace, sid


def _extract_token(payload: dict) -> str:
    token = str(payload.get("token") or "").strip()
    if token:
        return token
    authorization = str(payload.get("authorization") or payload.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return authorization


def register_gateway_socketio(socketio) -> None:
    socketio_id = id(socketio)
    if socketio_id in _registered_socketio_ids:
        get_gateway_service().bind_socketio(socketio)
        return

    service = get_gateway_service()
    service.bind_socketio(socketio)
    namespace = service.namespace

    @socketio.on("connect", namespace=namespace)
    def gateway_connect(auth):
        payload = _payload(auth)
        payload.update(request.args.to_dict(flat=True))
        go_control_plane = use_go_control_plane()
        try:
            connection, replayed = service.connect_client(
                sid=request.sid,
                namespace=namespace,
                auth_payload=payload,
                replay_pending=not go_control_plane,
            )
            session_key = _session_key(namespace, request.sid)
            if go_control_plane:
                token = _extract_token(payload)
                if not token:
                    service.disconnect_client(sid=request.sid, namespace=namespace)
                    raise ValueError("token is required when GATEWAY_CONTROL_PLANE=go")
                connect_connection_to_control_plane(connection, token=token)
                _auth_tokens_by_session[session_key] = token
                replay_result = replay_pending_events_from_control_plane(connection.connection_id, token=token)
                replayed_items = replay_result.get("replayed") or []
                for item in replayed_items:
                    event_name = str(item.get("event_type") or "").strip()
                    envelope = item.get("envelope") or {}
                    if not event_name or not isinstance(envelope, dict):
                        continue
                    socketio.emit(
                        event_name,
                        envelope,
                        to=request.sid,
                        namespace=namespace,
                    )
                replayed = len(replayed_items)
            emit(
                "gateway.connected",
                {
                    "nodeId": service.node_id,
                    "namespace": namespace,
                    "connectionId": connection.connection_id,
                    "userId": connection.user_id,
                    "deviceId": connection.device_id,
                    "replayedEvents": replayed,
                },
            )
        except Exception as exc:
            if go_control_plane:
                token = _auth_tokens_by_session.pop(_session_key(namespace, request.sid), None)
                connection = service.get_session(sid=request.sid, namespace=namespace)
                if connection is not None:
                    service.disconnect_client(sid=request.sid, namespace=namespace)
                    if token:
                        try:
                            disconnect_connection_from_control_plane(connection.connection_id, token=token)
                        except Exception:
                            pass
            emit("gateway.error", {"error": str(exc)})
            return False

    @socketio.on("disconnect", namespace=namespace)
    def gateway_disconnect():
        session_key = _session_key(namespace, request.sid)
        connection = service.disconnect_client(sid=request.sid, namespace=namespace)
        token = _auth_tokens_by_session.pop(session_key, None)
        if use_go_control_plane() and connection is not None and token:
            try:
                disconnect_connection_from_control_plane(connection.connection_id, token=token)
            except Exception:
                pass

    @socketio.on("gateway.heartbeat", namespace=namespace)
    def gateway_heartbeat(data):
        try:
            connection = service.touch_connection(sid=request.sid, namespace=namespace)
            if use_go_control_plane():
                token = _auth_tokens_by_session.get(_session_key(namespace, request.sid))
                if not token:
                    raise ValueError("gateway session token not found")
                try:
                    touch_connection_in_control_plane(connection.connection_id, token=token)
                except Exception as exc:
                    emit(
                        "gateway.heartbeat.ok",
                        {
                            "connectionId": connection.connection_id,
                            "lastSeenAt": connection.last_seen_at,
                            "controlPlane": {
                                "synced": False,
                                "error": str(exc),
                            },
                        },
                    )
                    return
            emit(
                "gateway.heartbeat.ok",
                {
                    "connectionId": connection.connection_id,
                    "lastSeenAt": connection.last_seen_at,
                },
            )
        except Exception as exc:
            emit("gateway.error", {"error": str(exc)})

    @socketio.on("message.ack", namespace=namespace)
    def gateway_ack(data):
        payload = _payload(data)
        ack_id = str(payload.get("ackId") or payload.get("event_id") or payload.get("message_id") or "").strip()
        try:
            if use_go_control_plane():
                connection = service.get_session(sid=request.sid, namespace=namespace)
                if connection is None:
                    raise ValueError("connection not found")
                token = _auth_tokens_by_session.get(_session_key(namespace, request.sid))
                if not token:
                    raise ValueError("gateway session token not found")
                try:
                    control_plane_result = ack_event_in_control_plane(
                        ack_id,
                        connection_id=connection.connection_id,
                        ack_payload=payload,
                        token=token,
                    )
                    result = {
                        "success": True,
                        "event_id": ack_id,
                        "connection_id": connection.connection_id,
                        "acked_at": control_plane_result.get("acked_at"),
                        "control_plane": {
                            "synced": True,
                            "acked_at": control_plane_result.get("acked_at"),
                        },
                    }
                except Exception as exc:
                    result = {
                        "success": False,
                        "event_id": ack_id,
                        "connection_id": connection.connection_id,
                        "control_plane": {
                            "synced": False,
                            "error": str(exc),
                        },
                    }
            else:
                result = service.ack_event(
                    sid=request.sid,
                    namespace=namespace,
                    ack_id=ack_id,
                    ack_payload=payload,
                )
            emit("message.ack.ok", result)
        except Exception as exc:
            emit("gateway.error", {"error": str(exc)})

    @socketio.on("chat.send", namespace=namespace)
    def gateway_chat_send(data):
        payload = _payload(data)
        message = str(payload.get("message") or payload.get("input") or "").strip()
        if not message:
            emit("chat.error", {"error": "message is required"})
            return

        connection = service.get_session(sid=request.sid, namespace=namespace)
        if connection is None:
            emit("chat.error", {"error": "connection not found"})
            return

        request_id = str(payload.get("requestId") or uuid.uuid4())
        session_key = _session_key(namespace, request.sid)
        control_plane_token = _auth_tokens_by_session.get(session_key)
        emit(
            "request.accepted",
            {
                "requestId": request_id,
                "conversationId": payload.get("conversation_id"),
                "status": "processing",
            },
        )

        def run_chat() -> None:
            try:
                from agent_framework.web.unified_orchestrator import get_unified_orchestrator

                orchestrator = get_unified_orchestrator()
                result = orchestrator.chat(
                    user_input=message,
                    conversation_id=payload.get("conversation_id"),
                    user_id=connection.user_id,
                    title=payload.get("title"),
                    metadata=payload.get("metadata"),
                    mode=payload.get("mode", "auto"),
                    use_agent=payload.get("use_agent"),
                    knowledge_base_ids=payload.get("knowledge_base_ids"),
                    prefer_finetuned=bool(payload.get("prefer_finetuned", False)),
                    endpoint_id=payload.get("endpoint_id", ""),
                    model_name=payload.get("model_name", ""),
                    base_url=payload.get("base_url", ""),
                    api_key=payload.get("api_key"),
                )
                delivery = _payload(payload.get("delivery"))
                target = delivery.get("target", "CONNECTION")
                push_event = PushEvent(
                    user_id=connection.user_id,
                    event_type=delivery.get("event", "chat.message"),
                    target=target,
                    device_id=delivery.get("device_id") or (
                        connection.device_id if str(target).upper() in {"DEVICE", "CURRENT_DEVICE"} else None
                    ),
                    connection_id=delivery.get("connection_id") or (
                        connection.connection_id if str(target).upper() in {"CONNECTION", "CURRENT_CONNECTION"} else None
                    ),
                    conversation_id=result.get("conversation_id"),
                    message_id=result.get("assistant_message_id"),
                    payload={
                        **result,
                        "requestId": request_id,
                    },
                    metadata={"source": "chat.send"},
                )
                if use_go_control_plane():
                    delivery_result = service.deliver_live_event(push_event)
                    if not control_plane_token:
                        raise ValueError("gateway session token not found")
                    try:
                        control_plane_result = publish_event_to_control_plane(push_event, token=control_plane_token)
                        delivery_result["control_plane"] = {
                            "synced": True,
                            "event_id": control_plane_result.get("event_id"),
                            "delivered_count": control_plane_result.get("delivered_count"),
                            "offline_queued": control_plane_result.get("offline_queued"),
                        }
                    except Exception as exc:
                        delivery_result["control_plane"] = {
                            "synced": False,
                            "error": str(exc),
                        }
                else:
                    delivery_result = service.publish_event(push_event)
                socketio.emit(
                    "chat.completed",
                    {
                        "requestId": request_id,
                        "conversationId": result.get("conversation_id"),
                        "assistantMessageId": result.get("assistant_message_id"),
                        "delivery": delivery_result,
                    },
                    to=request.sid,
                    namespace=namespace,
                )
            except Exception as exc:
                socketio.emit(
                    "chat.error",
                    {"requestId": request_id, "error": str(exc)},
                    to=request.sid,
                    namespace=namespace,
                )

        socketio.start_background_task(run_chat)

    _registered_socketio_ids.add(socketio_id)
