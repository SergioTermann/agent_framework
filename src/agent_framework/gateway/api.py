from __future__ import annotations

import json
import urllib.error
import urllib.request

from flask import Blueprint, Response, jsonify, request

from agent_framework.api.auth_api import require_admin_scope, require_auth, resolve_user_scope
from agent_framework.gateway.control_plane import gateway_control_plane_url, use_go_control_plane

from .models import PushEvent
from .service import get_gateway_service


gateway_bp = Blueprint("gateway", __name__, url_prefix="/api/gateway")


def _proxy_gateway_request(path_suffix: str, body: bytes | None = None):
    if not use_go_control_plane():
        return None

    suffix = path_suffix if path_suffix.startswith("/") else f"/{path_suffix}"
    upstream_url = f"{gateway_control_plane_url()}/api/gateway{suffix}"
    query_string = request.query_string.decode("utf-8", errors="ignore")
    if query_string:
        upstream_url = f"{upstream_url}?{query_string}"

    headers = {}
    for header_name in ("Authorization", "Content-Type", "Accept", "User-Agent", "X-Request-Id"):
        value = request.headers.get(header_name)
        if value:
            headers[header_name] = value

    payload = body
    if payload is None and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        payload = request.get_data()

    upstream_request = urllib.request.Request(
        upstream_url,
        data=payload,
        headers=headers,
        method=request.method,
    )
    try:
        with urllib.request.urlopen(upstream_request, timeout=15) as response:
            response_body = response.read()
            status_code = response.status
            content_type = response.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as exc:
        response_body = exc.read()
        status_code = exc.code
        content_type = exc.headers.get("Content-Type", "application/json")
    except urllib.error.URLError as exc:
        return jsonify({
            "success": False,
            "error": f"go gateway unavailable: {exc.reason}",
        }), 502

    return Response(response_body, status=status_code, content_type=content_type)


def _load_visible_event(event_id: str):
    event = get_gateway_service().get_event_status(event_id)
    if event is None:
        return None
    resolve_user_scope(event.get("user_id"))
    return event


@gateway_bp.route("/nodes", methods=["GET"])
@require_auth
def list_nodes():
    try:
        require_admin_scope()
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    proxied = _proxy_gateway_request("/nodes")
    if proxied is not None:
        return proxied
    service = get_gateway_service()
    return jsonify({"success": True, "data": service.list_nodes()})


@gateway_bp.route("/online-users", methods=["GET"])
@require_auth
def list_online_users():
    try:
        require_admin_scope()
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    proxied = _proxy_gateway_request("/online-users")
    if proxied is not None:
        return proxied
    service = get_gateway_service()
    return jsonify({"success": True, "data": service.list_online_users()})


@gateway_bp.route("/users/<user_id>/connections", methods=["GET"])
@require_auth
def list_user_connections(user_id: str):
    try:
        scoped_user_id = resolve_user_scope(user_id)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    proxied = _proxy_gateway_request(f"/users/{scoped_user_id}/connections")
    if proxied is not None:
        return proxied
    service = get_gateway_service()
    include_offline = str(request.args.get("include_offline", "")).lower() in {"1", "true", "yes"}
    return jsonify({
        "success": True,
        "data": service.list_user_connections(scoped_user_id, include_offline=include_offline),
    })


@gateway_bp.route("/users/<user_id>/offline-events", methods=["GET"])
@require_auth
def list_offline_events(user_id: str):
    try:
        scoped_user_id = resolve_user_scope(user_id)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    proxied = _proxy_gateway_request(f"/users/{scoped_user_id}/offline-events")
    if proxied is not None:
        return proxied
    service = get_gateway_service()
    return jsonify({"success": True, "data": service.list_pending_events(scoped_user_id)})


@gateway_bp.route("/events/<event_id>", methods=["GET"])
@require_auth
def get_event(event_id: str):
    proxied = _proxy_gateway_request(f"/events/{event_id}")
    if proxied is not None:
        return proxied
    try:
        event = _load_visible_event(event_id)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    if event is None:
        return jsonify({"success": False, "error": "event not found"}), 404
    return jsonify({"success": True, "data": event})


@gateway_bp.route("/events/<event_id>/ack", methods=["POST"])
@require_auth
def ack_event(event_id: str):
    proxied = _proxy_gateway_request(f"/events/{event_id}/ack")
    if proxied is not None:
        return proxied
    return jsonify({
        "success": False,
        "error": "event ack is only available when GATEWAY_CONTROL_PLANE=go",
    }), 501


@gateway_bp.route("/connections/<connection_id>/replay-pending", methods=["POST"])
@require_auth
def replay_pending_events(connection_id: str):
    proxied = _proxy_gateway_request(f"/connections/{connection_id}/replay-pending")
    if proxied is not None:
        return proxied
    return jsonify({
        "success": False,
        "error": "pending replay is only available when GATEWAY_CONTROL_PLANE=go",
    }), 501


@gateway_bp.route("/push", methods=["POST"])
@require_auth
def push_event():
    body = request.get_json(silent=True) or {}
    event_type = str(body.get("event") or body.get("event_type") or "").strip()
    payload = body.get("payload") or {}

    if not event_type:
        return jsonify({"success": False, "error": "event is required"}), 400
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "payload must be an object"}), 400

    try:
        user_id = resolve_user_scope(body.get("user_id"))
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403

    proxied_body = dict(body)
    proxied_body["user_id"] = user_id
    proxied = _proxy_gateway_request(
        "/push",
        body=json.dumps(proxied_body).encode("utf-8"),
    )
    if proxied is not None:
        return proxied

    event = PushEvent(
        user_id=user_id,
        event_type=event_type,
        payload=payload,
        target=body.get("target", "ALL"),
        device_id=body.get("device_id"),
        exclude_device_id=body.get("exclude_device_id"),
        connection_id=body.get("connection_id"),
        conversation_id=body.get("conversation_id"),
        message_id=body.get("message_id"),
        metadata=body.get("metadata") or {},
    )
    result = get_gateway_service().publish_event(event)
    return jsonify({"success": True, "data": result})
