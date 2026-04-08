from __future__ import annotations

import inspect
import re
from collections import defaultdict
from typing import Any

from flask import Flask, jsonify, render_template


_PATH_PARAM_RE = re.compile(r"<(?:[^:<>]+:)?([^<>]+)>")
_EXCLUDED_ENDPOINTS = {"static"}
_EXCLUDED_METHODS = {"HEAD", "OPTIONS"}
_JSON_BODY_METHODS = {"POST", "PUT", "PATCH"}


def register_openapi_routes(app: Flask) -> None:
    @app.route("/api/openapi.json", methods=["GET"])
    def openapi_spec():
        return jsonify(generate_openapi_spec(app))

    @app.route("/api/docs", methods=["GET"])
    def openapi_docs():
        return render_template("api_docs.html")


def generate_openapi_spec(app: Flask) -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = defaultdict(dict)

    for rule in sorted(app.url_map.iter_rules(), key=lambda current: current.rule):
        if rule.endpoint in _EXCLUDED_ENDPOINTS:
            continue

        methods = sorted(set(rule.methods or ()) - _EXCLUDED_METHODS)
        if not methods:
            continue

        normalized_path = _normalize_path(rule.rule)
        view_func = app.view_functions.get(rule.endpoint)
        if view_func is None:
            continue

        for method in methods:
            paths[normalized_path][method.lower()] = _build_operation(
                rule=rule,
                method=method,
                view_func=view_func,
            )

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Agent Framework API",
            "version": "0.1.0",
            "description": "Auto-generated API documentation for the Flask application.",
        },
        "servers": [
            {
                "url": "/",
                "description": "Current server",
            }
        ],
        "paths": dict(paths),
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                },
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                },
            }
        },
    }


def _normalize_path(path: str) -> str:
    normalized = _PATH_PARAM_RE.sub(r"{\1}", path)
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def _build_operation(*, rule: Any, method: str, view_func: Any) -> dict[str, Any]:
    summary, description = _extract_docs(view_func, rule.endpoint)
    tag = _infer_tag(rule.rule, rule.endpoint)
    operation = {
        "summary": summary,
        "description": description,
        "operationId": f"{rule.endpoint}_{method.lower()}",
        "tags": [tag],
        "parameters": _build_parameters(rule),
        "responses": {
            "200": {
                "description": "Successful response",
            }
        },
    }

    if method in _JSON_BODY_METHODS and rule.rule.startswith("/api/"):
        operation["requestBody"] = {
            "required": False,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "additionalProperties": True,
                    }
                }
            },
        }

    return operation


def _extract_docs(view_func: Any, endpoint: str) -> tuple[str, str]:
    doc = inspect.getdoc(view_func) or ""
    if doc:
        lines = [line.strip() for line in doc.splitlines() if line.strip()]
        if lines:
            return lines[0], "\n".join(lines[1:])
    fallback = endpoint.split(".")[-1].replace("_", " ").strip().title()
    return fallback or "Endpoint", ""


def _infer_tag(path: str, endpoint: str) -> str:
    if path.startswith("/api/"):
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            return parts[1]
        return "api"
    if path == "/health":
        return "system"
    return endpoint.split(".")[0]


def _build_parameters(rule: Any) -> list[dict[str, Any]]:
    parameters = []
    for argument in sorted(rule.arguments):
        parameters.append(
            {
                "name": argument,
                "in": "path",
                "required": True,
                "schema": {
                    "type": "string",
                },
            }
        )
    return parameters
