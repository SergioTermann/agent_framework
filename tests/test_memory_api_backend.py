from __future__ import annotations


def test_memory_backend_endpoint_returns_backend_snapshot(monkeypatch):
    from agent_framework.web.web_ui import app
    from agent_framework.api import memory_api as memory_api_module

    monkeypatch.setattr(
        memory_api_module,
        "get_memory_backend_info",
        lambda: {
            "requested": "reme",
            "active": "reme",
            "fallback": False,
            "reason": "reme_sidecar_ready",
        },
    )

    client = app.test_client()
    response = client.get("/api/memory/backend")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "backend": {
            "requested": "reme",
            "active": "reme",
            "fallback": False,
            "reason": "reme_sidecar_ready",
        },
    }
