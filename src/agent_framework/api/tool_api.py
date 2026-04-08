"""
工具管理 API
=============

提供用户工具的 CRUD、测试执行和密钥管理。
默认按当前登录用户做作用域隔离，管理员可显式指定 `user_id` 越权查看。
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from agent_framework.api.auth_api import require_auth, resolve_user_scope
from agent_framework.tool.user_tools import (
    UserToolDefinition,
    get_user_tool_executor,
    get_user_tool_storage,
)


tool_bp = Blueprint("tools", __name__, url_prefix="/api/tools")


def _tool_to_dict(tool_def: UserToolDefinition) -> dict:
    return {
        "tool_id": tool_def.tool_id,
        "name": tool_def.name,
        "description": tool_def.description,
        "parameters": tool_def.parameters,
        "execution_type": tool_def.execution_type,
        "execution_config": tool_def.execution_config,
        "user_id": tool_def.user_id,
        "enabled": tool_def.enabled,
        "created_at": tool_def.created_at,
        "updated_at": tool_def.updated_at,
        "tags": tool_def.tags,
    }


def _resolve_target_user_id(payload: dict | None = None) -> str:
    payload = payload or {}
    requested_user_id = payload.get("user_id") or request.args.get("user_id", "")
    return resolve_user_scope(requested_user_id)


def _load_owned_tool(tool_id: str) -> UserToolDefinition | None:
    storage = get_user_tool_storage()
    tool_def = storage.get(tool_id)
    if tool_def is None:
        return None
    resolve_user_scope(tool_def.user_id)
    return tool_def


@tool_bp.route("", methods=["GET"])
@require_auth
def list_tools():
    try:
        user_id = _resolve_target_user_id()
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403

    result: list[dict] = []

    try:
        from agent_framework.tools import discover_tools

        for spec in discover_tools():
            result.append({
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
                "source": "builtin",
                "enabled": True,
            })
    except Exception:
        pass

    try:
        from agent_framework.tools import discover_plugin_tools

        for spec in discover_plugin_tools():
            result.append({
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
                "source": "plugin",
                "enabled": True,
            })
    except Exception:
        pass

    try:
        storage = get_user_tool_storage()
        for tool_def in storage.list_tools(user_id=user_id, enabled_only=False):
            result.append({
                **_tool_to_dict(tool_def),
                "source": "user",
            })
    except Exception:
        pass

    return jsonify({"success": True, "tools": result, "total": len(result)})


@tool_bp.route("", methods=["POST"])
@require_auth
def create_tool():
    body = request.get_json(silent=True) or {}

    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "name is required"}), 400

    description = (body.get("description") or "").strip()
    if not description:
        return jsonify({"success": False, "error": "description is required"}), 400

    execution_config = body.get("execution_config") or {}
    if not execution_config.get("url"):
        return jsonify({"success": False, "error": "execution_config.url is required"}), 400

    try:
        user_id = _resolve_target_user_id(body)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403

    tool_def = UserToolDefinition(
        name=name,
        description=description,
        parameters=body.get("parameters") or {"type": "object", "properties": {}, "required": []},
        execution_type=body.get("execution_type", "http"),
        execution_config=execution_config,
        user_id=user_id,
        enabled=body.get("enabled", True),
        tags=body.get("tags") or [],
    )

    try:
        created = get_user_tool_storage().create(tool_def)
        return jsonify({"success": True, "tool": _tool_to_dict(created)}), 201
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@tool_bp.route("/<tool_id>", methods=["GET"])
@require_auth
def get_tool(tool_id: str):
    try:
        tool_def = _load_owned_tool(tool_id)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    if tool_def is None:
        return jsonify({"success": False, "error": "Tool not found"}), 404
    return jsonify({"success": True, "tool": _tool_to_dict(tool_def)})


@tool_bp.route("/<tool_id>", methods=["PUT"])
@require_auth
def update_tool(tool_id: str):
    body = request.get_json(silent=True) or {}
    try:
        existing = _load_owned_tool(tool_id)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    if existing is None:
        return jsonify({"success": False, "error": "Tool not found"}), 404

    allowed_fields = {
        "name",
        "description",
        "parameters",
        "execution_type",
        "execution_config",
        "enabled",
        "tags",
    }
    updates = {key: value for key, value in body.items() if key in allowed_fields}
    if not updates:
        return jsonify({"success": False, "error": "No valid fields to update"}), 400

    updated = get_user_tool_storage().update(tool_id, **updates)
    if updated is None:
        return jsonify({"success": False, "error": "Tool not found"}), 404
    return jsonify({"success": True, "tool": _tool_to_dict(updated)})


@tool_bp.route("/<tool_id>", methods=["DELETE"])
@require_auth
def delete_tool(tool_id: str):
    try:
        existing = _load_owned_tool(tool_id)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    if existing is None:
        return jsonify({"success": False, "error": "Tool not found"}), 404

    deleted = get_user_tool_storage().delete(tool_id)
    if not deleted:
        return jsonify({"success": False, "error": "Tool not found"}), 404
    return jsonify({"success": True, "message": "Tool deleted"})


@tool_bp.route("/<tool_id>/test", methods=["POST"])
@require_auth
def test_tool(tool_id: str):
    body = request.get_json(silent=True) or {}
    test_params = body.get("params") or body.get("parameters") or {}

    try:
        tool_def = _load_owned_tool(tool_id)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    if tool_def is None:
        return jsonify({"success": False, "error": "Tool not found"}), 404

    try:
        executor = get_user_tool_executor()
        result = executor.execute(tool_def, test_params)
        return jsonify({
            "success": True,
            "tool_id": tool_id,
            "tool_name": tool_def.name,
            "params": test_params,
            "result": result,
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tool_bp.route("/presets", methods=["GET"])
@require_auth
def list_presets():
    from agent_framework.tools import TOOLSET_PRESETS

    presets = {
        name: sorted(tools) if tools is not None else None
        for name, tools in TOOLSET_PRESETS.items()
    }
    return jsonify({"success": True, "presets": presets})


@tool_bp.route("/secrets", methods=["POST"])
@require_auth
def store_secret():
    body = request.get_json(silent=True) or {}
    secret_key = (body.get("key") or "").strip()
    secret_value = body.get("value", "")

    if not secret_key:
        return jsonify({"success": False, "error": "key is required"}), 400
    if not secret_value:
        return jsonify({"success": False, "error": "value is required"}), 400

    try:
        user_id = _resolve_target_user_id(body)
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403

    get_user_tool_storage().set_secret(secret_key, secret_value, user_id=user_id)
    return jsonify({"success": True, "key": secret_key, "message": "Secret stored"})


@tool_bp.route("/secrets/<secret_key>", methods=["DELETE"])
@require_auth
def delete_secret(secret_key: str):
    try:
        user_id = _resolve_target_user_id()
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403

    deleted = get_user_tool_storage().delete_secret(secret_key, user_id=user_id)
    if not deleted:
        return jsonify({"success": False, "error": "Secret not found"}), 404
    return jsonify({"success": True, "message": "Secret deleted"})
