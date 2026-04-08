from __future__ import annotations

import pytest

from agent_framework.core.config import reload_config


@pytest.fixture(autouse=True)
def _reset_config_cache():
    reload_config()
    try:
        yield
    finally:
        reload_config()


def test_readiness_route_returns_report(monkeypatch):
    from agent_framework.web.web_ui import app

    with monkeypatch.context() as m:
        m.setenv("SECRET_KEY", "this-is-a-strong-test-secret-123")
        m.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
        m.setenv("LLM_MODEL", "test-model")
        m.delenv("LLM_API_KEY", raising=False)
        reload_config()

        client = app.test_client()
        response = client.get("/health/ready")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ready"] is True
        assert payload["summary"]["fail"] == 0
        assert any(check["name"] == "llm_configuration" for check in payload["checks"])


def test_readiness_fails_when_go_control_plane_is_unreachable(monkeypatch):
    from agent_framework.core.harness_health import build_readiness_report
    from agent_framework.web.web_ui import app

    with monkeypatch.context() as m:
        m.setenv("SECRET_KEY", "this-is-a-strong-test-secret-123")
        m.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
        m.setenv("LLM_MODEL", "test-model")
        m.setenv("GATEWAY_CONTROL_PLANE", "go")
        m.setenv("GATEWAY_CONTROL_PLANE_URL", "http://gateway-go-control-plane:7000")
        m.setattr(
            "agent_framework.core.harness_health._probe_json",
            lambda url: (_ for _ in ()).throw(RuntimeError("unreachable")),
        )
        reload_config()

        report = build_readiness_report(app)

        assert report["ready"] is False
        assert report["status"] == "not_ready"
        failing = {check["name"]: check for check in report["checks"] if check["status"] == "fail"}
        assert "gateway_control_plane" in failing


def test_doctor_report_contains_readiness_and_status(monkeypatch):
    from agent_framework.core.harness_doctor import build_doctor_report, render_text_report
    from agent_framework.web.web_ui import app

    with monkeypatch.context() as m:
        m.setenv("SECRET_KEY", "this-is-a-strong-test-secret-123")
        m.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
        m.setenv("LLM_MODEL", "test-model")
        reload_config()

        report = build_doctor_report(app)
        text = render_text_report(report)

        assert report["liveness"]["status"] == "alive"
        assert "readiness" in report
        assert "system_status" in report
        assert "Agent Framework Doctor" in text
