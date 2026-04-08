from __future__ import annotations

import pytest

from agent_framework.tool.user_tools import UserToolStorage, UserToolExecutor


@pytest.fixture
def isolated_tool_storage(workspace_tmp_dir, monkeypatch):
    from agent_framework.api import tool_api as tool_api_module

    storage = UserToolStorage(db_path=workspace_tmp_dir / "user_tools.db")
    executor = UserToolExecutor(storage)
    monkeypatch.setattr(tool_api_module, "get_user_tool_storage", lambda: storage)
    monkeypatch.setattr(tool_api_module, "get_user_tool_executor", lambda: executor)
    return storage


def test_tool_api_scopes_tools_per_user(isolated_tool_storage, make_auth_headers):
    from agent_framework.web.web_ui import app

    owner_headers, owner = make_auth_headers()
    other_headers, _other = make_auth_headers()
    client = app.test_client()

    create_response = client.post(
        "/api/tools",
        headers=owner_headers,
        json={
            "name": "status_probe",
            "description": "probe remote status",
            "execution_config": {"url": "https://example.com/api/status", "method": "GET"},
        },
    )
    assert create_response.status_code == 201
    tool_id = create_response.get_json()["tool"]["tool_id"]

    owner_list = client.get("/api/tools", headers=owner_headers)
    assert owner_list.status_code == 200
    owner_tools = [item for item in owner_list.get_json()["tools"] if item.get("source") == "user"]
    assert any(item["tool_id"] == tool_id and item["user_id"] == owner.user_id for item in owner_tools)

    forbidden = client.get(f"/api/tools/{tool_id}", headers=other_headers)
    assert forbidden.status_code == 403


def test_tool_api_encrypts_secrets_and_blocks_private_urls(isolated_tool_storage, make_auth_headers):
    from agent_framework.web.web_ui import app

    headers, user = make_auth_headers()
    client = app.test_client()

    secret_response = client.post(
        "/api/tools/secrets",
        headers=headers,
        json={"key": "internal-token", "value": "super-secret"},
    )
    assert secret_response.status_code == 200

    raw_row = isolated_tool_storage._db.execute_one(
        isolated_tool_storage.db_path,
        "SELECT secret_value FROM user_tool_secrets WHERE secret_key = ?",
        (f"{user.user_id}:internal-token",),
    )
    assert raw_row is not None
    assert raw_row["secret_value"] != "super-secret"

    create_response = client.post(
        "/api/tools",
        headers=headers,
        json={
            "name": "private_probe",
            "description": "must not hit localhost",
            "execution_config": {"url": "http://127.0.0.1/internal", "method": "GET"},
        },
    )
    assert create_response.status_code == 201
    tool_id = create_response.get_json()["tool"]["tool_id"]

    test_response = client.post(f"/api/tools/{tool_id}/test", headers=headers, json={"params": {}})
    assert test_response.status_code == 500
    assert "Private" in test_response.get_json()["error"]
