"""
通用 API 辅助函数
统一 JSON 响应、请求体读取、分页参数和异常处理。
"""

from __future__ import annotations

from logging import Logger

from flask import jsonify, request


def json_success(payload: dict | None = None, status_code: int = 200):
    body = {"success": True}
    if payload:
        body.update(payload)
    return jsonify(body), status_code


def json_error(message: str, status_code: int = 400, **extra):
    body = {"error": message}
    if extra:
        body.update(extra)
    return jsonify(body), status_code


def request_json():
    return request.get_json(silent=True) or {}


def parse_pagination(default_limit: int = 50, max_limit: int = 200) -> tuple[int, int]:
    limit = request.args.get("limit", default_limit, type=int)
    offset = request.args.get("offset", 0, type=int)
    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset


def handle_api_exception(
    logger: Logger,
    prefix: str,
    exc: Exception,
    status_code: int = 500,
):
    logger.error("%s: %s", prefix, exc)
    return json_error(f"{prefix}: {exc}", status_code)
