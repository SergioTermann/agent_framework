from __future__ import annotations


def test_plugin_market_page_renders_core_ui():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/plugins")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "插件市场" in html
    assert 'id="search-input"' in html
    assert 'id="installed-only"' in html
    assert 'id="sort-select"' in html
    assert 'id="page-size-select"' in html
    assert 'id="share-button"' in html
    assert 'id="category-filter-bar"' in html
    assert 'id="plugins-grid"' in html
    assert 'id="pagination-bar"' in html
    assert 'id="plugin-modal"' in html
    assert "params.get('plugin')" in html
    assert "copyCurrentLink" in html
    assert "fetchPluginDetail" in html


def test_plugin_market_list_api_includes_stats_and_categories():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/api/plugins/")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["total"] >= 1
    assert "stats" in payload
    assert "categories" in payload
    assert "featured_plugins" in payload
    assert "enabled_plugins" in payload["stats"]
    assert any(category["id"] == "all" for category in payload["categories"])

    plugin = payload["plugins"][0]
    for field in (
        "id",
        "name",
        "description",
        "compatibility",
        "highlights",
        "updated_at",
        "verified",
        "rating_count",
        "enabled",
    ):
        assert field in plugin


def test_plugin_market_list_api_honors_query_filters(workspace_tmp_dir, monkeypatch):
    from agent_framework.api import plugin_market_api
    from agent_framework.web.web_ui import app

    db_path = workspace_tmp_dir / "plugins.db"
    install_dir = workspace_tmp_dir / "plugins"

    monkeypatch.setattr(plugin_market_api, "PLUGIN_DB_PATH", str(db_path))
    monkeypatch.setattr(plugin_market_api, "PLUGIN_INSTALL_DIR", str(install_dir))
    plugin_market_api.init_plugin_db()

    client = app.test_client()

    response = client.get("/api/plugins/?category=ai&sort=rating")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["plugins"]
    assert all(plugin["category"] == "ai" for plugin in payload["plugins"])

    response = client.get("/api/plugins/?search=weather")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert any(plugin["id"] == "weather-api" for plugin in payload["plugins"])

    client.post("/api/plugins/weather-api/install")
    response = client.get("/api/plugins/?installed_only=1")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["total"] == 1
    assert payload["plugins"][0]["id"] == "weather-api"

    response = client.get("/api/plugins/?page=2&page_size=2")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["pagination"]["page"] == 2
    assert payload["pagination"]["page_size"] == 2
    assert payload["pagination"]["total_pages"] >= 3
    assert len(payload["plugins"]) == 2
    assert len(payload["featured_plugins"]) >= 1

    response = client.get("/api/plugins/?page_size=999")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["pagination"]["page_size"] == 24


def test_plugin_market_list_api_normalizes_invalid_query_values():
    from agent_framework.web.web_ui import app

    client = app.test_client()
    response = client.get("/api/plugins/?category=unknown&sort=broken&page=-4&page_size=0")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["applied_filters"]["category"] == "all"
    assert payload["applied_filters"]["sort"] == "popular"
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["page_size"] == 1
    assert payload["total"] == payload["stats"]["total_plugins"]


def test_plugin_market_detail_api_returns_plugin_outside_current_page():
    from agent_framework.web.web_ui import app

    client = app.test_client()

    list_response = client.get("/api/plugins/?category=ai&page=1&page_size=1")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["success"] is True
    assert len(list_payload["plugins"]) == 1
    assert list_payload["plugins"][0]["id"] == "text-analyzer"

    detail_response = client.get("/api/plugins/workflow-copilot")
    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload["success"] is True
    assert detail_payload["plugin"]["id"] == "workflow-copilot"
    assert detail_payload["plugin"]["featured"] is True

    missing_response = client.get("/api/plugins/not-found")
    assert missing_response.status_code == 404
    missing_payload = missing_response.get_json()
    assert missing_payload["success"] is False


def test_plugin_market_install_enable_disable_and_uninstall_flow(workspace_tmp_dir, monkeypatch):
    from agent_framework.api import plugin_market_api
    from agent_framework.web.web_ui import app

    db_path = workspace_tmp_dir / "plugins.db"
    install_dir = workspace_tmp_dir / "plugins"

    monkeypatch.setattr(plugin_market_api, "PLUGIN_DB_PATH", str(db_path))
    monkeypatch.setattr(plugin_market_api, "PLUGIN_INSTALL_DIR", str(install_dir))
    plugin_market_api.init_plugin_db()

    client = app.test_client()

    install_response = client.post("/api/plugins/weather-api/install")
    assert install_response.status_code == 200
    install_payload = install_response.get_json()
    assert install_payload["success"] is True
    assert (install_dir / "weather-api" / "__init__.py").exists()

    list_payload = client.get("/api/plugins/").get_json()
    weather_plugin = next(plugin for plugin in list_payload["plugins"] if plugin["id"] == "weather-api")
    assert weather_plugin["installed"] is True
    assert weather_plugin["enabled"] is True

    disable_response = client.post("/api/plugins/weather-api/disable")
    assert disable_response.status_code == 200
    disable_payload = disable_response.get_json()
    assert disable_payload["success"] is True
    assert disable_payload["enabled"] is False

    list_payload = client.get("/api/plugins/").get_json()
    weather_plugin = next(plugin for plugin in list_payload["plugins"] if plugin["id"] == "weather-api")
    assert weather_plugin["enabled"] is False

    enable_response = client.post("/api/plugins/weather-api/enable")
    assert enable_response.status_code == 200
    enable_payload = enable_response.get_json()
    assert enable_payload["success"] is True
    assert enable_payload["enabled"] is True

    list_payload = client.get("/api/plugins/").get_json()
    weather_plugin = next(plugin for plugin in list_payload["plugins"] if plugin["id"] == "weather-api")
    assert weather_plugin["enabled"] is True

    uninstall_response = client.post("/api/plugins/weather-api/uninstall")
    assert uninstall_response.status_code == 200
    uninstall_payload = uninstall_response.get_json()
    assert uninstall_payload["success"] is True
    assert not (install_dir / "weather-api").exists()

    list_payload = client.get("/api/plugins/").get_json()
    weather_plugin = next(plugin for plugin in list_payload["plugins"] if plugin["id"] == "weather-api")
    assert weather_plugin["installed"] is False


def test_plugin_market_rating_updates_summary(workspace_tmp_dir, monkeypatch):
    from agent_framework.api import plugin_market_api
    from agent_framework.web.web_ui import app

    db_path = workspace_tmp_dir / "plugins.db"

    monkeypatch.setattr(plugin_market_api, "PLUGIN_DB_PATH", str(db_path))
    plugin_market_api.init_plugin_db()

    client = app.test_client()

    response = client.post("/api/plugins/text-analyzer/rate", json={"rating": 5, "user_id": "alice"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["average_rating"] >= 4.9
    assert payload["total_ratings"] == 1

    response = client.post("/api/plugins/text-analyzer/rate", json={"rating": 3, "user_id": "bob"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["total_ratings"] == 2

    response = client.post("/api/plugins/text-analyzer/rate", json={"rating": 4, "user_id": "alice"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["total_ratings"] == 2

    list_payload = client.get("/api/plugins/").get_json()
    plugin = next(item for item in list_payload["plugins"] if item["id"] == "text-analyzer")
    assert plugin["rating_count"] == 2
    assert plugin["rating"] == 3.5


def test_plugin_market_rating_rejects_invalid_value_and_normalizes_user_id(workspace_tmp_dir, monkeypatch):
    from agent_framework.api import plugin_market_api
    from agent_framework.web.web_ui import app

    db_path = workspace_tmp_dir / "plugins.db"

    monkeypatch.setattr(plugin_market_api, "PLUGIN_DB_PATH", str(db_path))
    plugin_market_api.init_plugin_db()

    client = app.test_client()

    response = client.post("/api/plugins/text-analyzer/rate", json={"rating": "bad"})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False

    response = client.post("/api/plugins/text-analyzer/rate", json={"rating": 5, "user_id": None})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["total_ratings"] == 1

    response = client.post("/api/plugins/text-analyzer/rate", json={"rating": 2, "user_id": ""})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["total_ratings"] == 1
    assert payload["average_rating"] == 2
