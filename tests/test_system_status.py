from __future__ import annotations

from pathlib import Path


def test_system_status_api_reports_runtime_snapshot():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/api/system/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["service"] == "agent-framework"
    assert payload["routes"]["total"] >= payload["routes"]["api"]
    assert payload["routes"]["api"] > 0
    assert payload["tools"]["builtin_count"] > 0
    assert payload["memory"]["active"]
    assert payload["services"]["app_go"]["status"] == "bootstrap"


def test_system_status_reports_go_control_plane_when_enabled(monkeypatch):
    from agent_framework.core.system_status import collect_system_status
    from agent_framework.web.web_ui import app

    monkeypatch.setenv("GATEWAY_CONTROL_PLANE", "go")
    monkeypatch.setenv("GATEWAY_CONTROL_PLANE_URL", "http://gateway-go-control-plane:7000")
    monkeypatch.setattr(
        "agent_framework.core.system_status._probe_json_url",
        lambda url: {"status": "ok", "service": "gateway-go"},
    )

    payload = collect_system_status(app)

    assert payload["gateway"]["mode"] == "go"
    assert payload["gateway"]["control_plane"]["reachable"] is True
    assert payload["gateway"]["control_plane"]["service"] == "gateway-go"
    assert payload["gateway"]["storage"] == "noop"


def test_system_status_page_is_available():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/system-status")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Harness Status" in html
    assert "/api/system/status" in html


def test_root_redirects_to_developer_home():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portal")


def test_home_redirects_to_developer_home():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/home")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portal")


def test_portal_page_is_available():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/portal")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Luminous Intelligence" in html
    assert "Windrise Domain - AI Technical Suite" in html
    assert 'id="portal-dialog-form"' in html
    assert 'id="route-search"' in html
    assert "/maintenance-assistant" in html
    assert "Gearbox Overheating" in html


def test_developer_home_uses_light_console_layout():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/dev")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "dev-console-light" in html
    assert "workspace-shell" in html
    assert "服务总览" in html
    assert "/visual-workflow" in html
    assert "/knowledge" in html


def test_module_workspace_page_is_available():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/modules/guide-assistant")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "智导助手" in html
    assert "/maintenance-assistant" in html


def test_unknown_module_redirects_to_portal():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/modules/not-exists")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portal")


def test_module_frontend_page_is_available():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/modules/weather-siting/app")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "气象选址" in html
    assert "Task Composer" in html


def test_unknown_module_frontend_redirects_to_portal():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/modules/not-exists/app")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portal")


def test_return_home_links_do_not_hardcode_root_path():
    templates_dir = Path(__file__).resolve().parents[1] / "src" / "agent_framework" / "templates"

    for template_path in templates_dir.glob("*.html"):
        content = template_path.read_text(encoding="utf-8")
        if "返回主页" not in content and "返回首页" not in content:
            continue

        assert 'href="/"' not in content, f"{template_path.name} hardcodes root href for home navigation"
        assert "window.location.href='/'" not in content, (
            f"{template_path.name} hardcodes root JS navigation for home navigation"
        )


def test_developer_tool_pages_return_to_developer_home():
    templates_dir = Path(__file__).resolve().parents[1] / "src" / "agent_framework" / "templates"
    tool_templates = [
        "analytics_dashboard.html",
        "api_keys.html",
        "causal_chain.html",
        "causal_chain_backup.html",
        "causal_reasoning.html",
        "causal_tree.html",
        "dashboard.html",
        "demo_gallery.html",
        "finetune.html",
        "industry_knowledge.html",
        "knowledge.html",
        "llm_rlhf_dashboard.html",
        "multi_agent.html",
        "pipeline_dashboard.html",
        "rl_dashboard.html",
        "settings.html",
        "visual_workflow.html",
    ]

    for template_name in tool_templates:
        content = (templates_dir / template_name).read_text(encoding="utf-8")
        assert "url_for('developer_home')" in content, f"{template_name} should return to developer_home"
