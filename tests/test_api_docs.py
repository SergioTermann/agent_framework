from __future__ import annotations


def test_openapi_spec_exposes_registered_routes():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    spec = response.get_json()
    assert spec["openapi"] == "3.0.3"
    assert "/api/conversations" in spec["paths"]
    assert "/api/gateway/push" in spec["paths"]
    assert "/health" in spec["paths"]

    push_operation = spec["paths"]["/api/gateway/push"]["post"]
    assert push_operation["summary"]
    assert push_operation["tags"] == ["gateway"]
    assert "requestBody" in push_operation


def test_openapi_spec_converts_path_parameters():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    spec = client.get("/api/openapi.json").get_json()

    route = spec["paths"]["/api/gateway/users/{user_id}/connections"]["get"]
    assert route["parameters"] == [
        {
            "name": "user_id",
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        }
    ]


def test_api_docs_page_is_available():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/api/docs")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Agent Framework API Docs" in html
    assert "/api/openapi.json" in html
