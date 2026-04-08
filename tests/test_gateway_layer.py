from __future__ import annotations

import json
from pathlib import Path

from flask import Flask
from flask_socketio import SocketIO

from agent_framework.core.auth import UserRole
from agent_framework.gateway.api import gateway_bp
from agent_framework.gateway.service import GatewayService, set_gateway_service
from agent_framework.gateway.storage import NoopGatewayStorage
from agent_framework.gateway.socketio_gateway import register_gateway_socketio


def create_gateway_app(db_dir: Path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    socketio = SocketIO(app, async_mode="threading")

    service = GatewayService(
        namespace="/gateway",
        node_id="gw-test",
        db_path=str(db_dir / "gateway.db"),
        allow_user_id_fallback=False,
    )
    set_gateway_service(service)
    app.register_blueprint(gateway_bp)
    register_gateway_socketio(socketio)
    return app, socketio, service


def test_gateway_push_and_ack(workspace_tmp_dir, make_auth_headers):
    headers, user = make_auth_headers()
    token = headers["Authorization"].split(" ", 1)[1]

    app, socketio, _service = create_gateway_app(workspace_tmp_dir)
    http_client = app.test_client()
    ws_client = socketio.test_client(
        app,
        namespace="/gateway",
        query_string=f"token={token}&device_id=web-1",
    )
    assert ws_client.is_connected("/gateway")

    connections = http_client.get(
        f"/api/gateway/users/{user.user_id}/connections",
        headers=headers,
    ).get_json()["data"]
    assert len(connections) == 1

    response = http_client.post(
        "/api/gateway/push",
        headers=headers,
        json={
            "user_id": user.user_id,
            "event": "notify.system",
            "payload": {"text": "hello"},
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    event_id = body["data"]["event_id"]
    assert body["data"]["delivered_count"] == 1

    status_before_ack = http_client.get(
        f"/api/gateway/events/{event_id}",
        headers=headers,
    ).get_json()["data"]
    assert status_before_ack["status"] == "DELIVERED"
    assert len(status_before_ack["deliveries"]) == 1

    ws_client.emit("message.ack", {"ackId": event_id}, namespace="/gateway")

    status_response = http_client.get(f"/api/gateway/events/{event_id}", headers=headers)
    assert status_response.status_code == 200
    status_body = status_response.get_json()["data"]
    assert status_body["status"] == "ACKED"


def test_gateway_replays_offline_events_on_connect(workspace_tmp_dir, make_auth_headers):
    headers, user = make_auth_headers()
    token = headers["Authorization"].split(" ", 1)[1]

    app, socketio, _service = create_gateway_app(workspace_tmp_dir)
    http_client = app.test_client()

    response = http_client.post(
        "/api/gateway/push",
        headers=headers,
        json={
            "user_id": user.user_id,
            "event": "notify.system",
            "payload": {"text": "offline"},
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["offline_queued"] is True

    pending_before = http_client.get(
        f"/api/gateway/users/{user.user_id}/offline-events",
        headers=headers,
    ).get_json()["data"]
    assert len(pending_before) == 1

    ws_client = socketio.test_client(
        app,
        namespace="/gateway",
        query_string=f"token={token}&device_id=web-2",
    )
    assert ws_client.is_connected("/gateway")

    pending_after = http_client.get(
        f"/api/gateway/users/{user.user_id}/offline-events",
        headers=headers,
    ).get_json()["data"]
    assert pending_after == []

    event_id = body["data"]["event_id"]
    event_status = http_client.get(f"/api/gateway/events/{event_id}", headers=headers).get_json()["data"]
    assert event_status["status"] == "DELIVERED"
    assert len(event_status["deliveries"]) == 1


def test_gateway_nodes_require_admin(workspace_tmp_dir, make_auth_headers):
    member_headers, _member = make_auth_headers()
    admin_headers, admin_user = make_auth_headers(role=UserRole.ADMIN)
    token = admin_headers["Authorization"].split(" ", 1)[1]

    app, socketio, _service = create_gateway_app(workspace_tmp_dir)
    http_client = app.test_client()
    ws_client = socketio.test_client(
        app,
        namespace="/gateway",
        query_string=f"token={token}&device_id=admin-web",
    )
    assert ws_client.is_connected("/gateway")

    forbidden = http_client.get("/api/gateway/nodes", headers=member_headers)
    assert forbidden.status_code == 403

    allowed = http_client.get("/api/gateway/nodes", headers=admin_headers)
    assert allowed.status_code == 200
    payload = allowed.get_json()["data"]
    assert payload
    assert payload[0]["node_id"] == "gw-test"
    assert admin_user.user_id


def test_gateway_demo_assets_exist():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/gateway-demo")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/static/js/gateway-demo.js" in html
    assert "Gateway + WebSocket" in html


def test_maintenance_assistant_pages_include_gateway_bridge():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    for path in ("/maintenance-assistant", "/dev/assistant"):
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "socket.io.min.js" in html
        assert "/static/js/maintenance-assistant-gateway.js" in html


def test_maintenance_assistant_pages_expose_tool_selection_controls():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    for path in ("/maintenance-assistant", "/dev/assistant"):
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'id="toolsetSelection"' in html
        assert 'id="allowedToolsInput"' in html
        assert 'id="blockedToolsInput"' in html
        assert 'id="includePluginTools"' in html
        assert "wind_maintenance" in html
        assert "calculate" in html
        if path == "/dev/assistant":
            assert 'id="statusModeValue"' in html
            assert '<div class="bubble"><div>这里是开发版维护助手。' in html


def test_gateway_service_uses_noop_storage_in_go_mode(workspace_tmp_dir, monkeypatch, make_auth_headers):
    db_path = workspace_tmp_dir / "gateway.db"
    monkeypatch.setenv("GATEWAY_CONTROL_PLANE", "go")
    headers, user = make_auth_headers()
    token = headers["Authorization"].split(" ", 1)[1]

    service = GatewayService(
        namespace="/gateway",
        node_id="gw-go-mode",
        db_path=str(db_path),
        allow_user_id_fallback=False,
    )

    assert isinstance(service.storage, NoopGatewayStorage)
    assert not db_path.exists()

    connection, replayed = service.connect_client(
        sid="sid-go-1",
        namespace="/gateway",
        auth_payload={"token": token, "device_id": "web-go-1"},
    )
    assert replayed == 0
    assert connection.user_id == user.user_id
    assert service.list_pending_events(user.user_id) == []


def test_gateway_api_proxies_replay_pending_in_go_mode(monkeypatch, make_auth_headers):
    headers, _user = make_auth_headers()
    captured = {}

    class _MockResponse:
        def __init__(self, body: dict):
            self.status = 200
            self.headers = {"Content-Type": "application/json"}
            self._body = json.dumps(body).encode("utf-8")

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _mock_urlopen(request_obj, timeout=0):
        captured["url"] = request_obj.full_url
        captured["method"] = request_obj.get_method()
        captured["authorization"] = request_obj.headers.get("Authorization")
        captured["timeout"] = timeout
        return _MockResponse({
            "success": True,
            "data": {
                "connection_id": "conn-proxy-1",
                "replayed": [{"event_id": "evt-proxy-1", "event_type": "notice"}],
                "replayed_count": 1,
            },
        })

    monkeypatch.setenv("GATEWAY_CONTROL_PLANE", "go")
    monkeypatch.setenv("GATEWAY_CONTROL_PLANE_URL", "http://gateway-go-control-plane:7000")
    monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.register_blueprint(gateway_bp)

    response = app.test_client().post(
        "/api/gateway/connections/conn-proxy-1/replay-pending",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["replayed_count"] == 1
    assert captured["url"] == "http://gateway-go-control-plane:7000/api/gateway/connections/conn-proxy-1/replay-pending"
    assert captured["method"] == "POST"
    assert captured["authorization"] == headers["Authorization"]
