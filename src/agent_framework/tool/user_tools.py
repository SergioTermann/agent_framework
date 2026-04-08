"""
用户自定义工具 —— 模型 + SQLite 存储 + HTTP 执行器

让用户在运行时创建、管理并执行自己的 HTTP 工具，
无需修改代码或重启服务。工具定义持久化到 SQLite，
运行时自动转为 ToolSpec 参与 function calling。
"""

from __future__ import annotations

import logging
import base64
import hashlib
import hmac
import ipaddress
import os
import re
import socket
import threading
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import agent_framework.core.fast_json as json
from agent_framework.core.config import get_config
from agent_framework.core.database import DatabaseManager
from agent_framework.tool.registry import ToolSpec

logger = logging.getLogger(__name__)

# ── 数据路径 ─────────────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_USER_TOOLS_DB = _DATA_DIR / "user_tools.db"

# ── 常量 ─────────────────────────────────────────────────────────────────────

MAX_TIMEOUT_SECONDS = 60
MAX_RESPONSE_CHARS = 8000
_PRIVATE_URL_OVERRIDE_ENV = "AGENT_FRAMEWORK_ALLOW_PRIVATE_TOOL_URLS"
_SECRET_KEY_ENV = "USER_TOOL_SECRET_KEY"


def _scope_secret_key(secret_key: str, user_id: str = "") -> str:
    return f"{user_id}:{secret_key}" if user_id else secret_key


def _secret_cipher_key() -> bytes:
    cfg = get_config()
    source = os.getenv(_SECRET_KEY_ENV, "").strip() or cfg.server.secret_key
    return hashlib.sha256(source.encode("utf-8")).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        output.extend(block)
        counter += 1
    return bytes(output[:length])


def _encrypt_secret_value(value: str) -> str:
    plaintext = value.encode("utf-8")
    nonce = os.urandom(16)
    key = _secret_cipher_key()
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, _keystream(key, nonce, len(plaintext))))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    packed = nonce + ciphertext + mac
    return "enc:v1:" + base64.urlsafe_b64encode(packed).decode("ascii")


def _decrypt_secret_value(value: str) -> str:
    if not value.startswith("enc:v1:"):
        return value
    packed = base64.urlsafe_b64decode(value.split(":", 2)[2].encode("ascii"))
    if len(packed) < 48:
        raise ValueError("invalid secret payload")
    nonce = packed[:16]
    mac = packed[-32:]
    ciphertext = packed[16:-32]
    key = _secret_cipher_key()
    expected_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("secret integrity check failed")
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, _keystream(key, nonce, len(ciphertext))))
    return plaintext.decode("utf-8")


def _host_is_private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        pass

    lowered = host.lower()
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".local"):
        return True

    try:
        resolved_hosts = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return True

    return any(_host_is_private(item) for item in resolved_hosts)


def _validate_outbound_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("Tool URL must include a hostname")
    if os.getenv(_PRIVATE_URL_OVERRIDE_ENV, "").lower() in {"1", "true", "yes"}:
        return
    if _host_is_private(parsed.hostname):
        raise ValueError("Private, loopback, and local network addresses are blocked for user tools")

# ── 数据模型 ─────────────────────────────────────────────────────────────────


@dataclass
class HttpExecutionConfig:
    """HTTP 工具的执行配置"""
    url: str = ""                   # 支持 {param} 模板变量
    method: str = "POST"            # GET / POST / PUT / DELETE
    headers: dict[str, str] = field(default_factory=dict)
    body_template: str | None = None  # JSON 模板字符串，支持 {param}
    timeout: int = 30
    auth_type: str = "none"         # none / bearer / api_key
    auth_secret_key: str = ""       # 对应 user_tool_secrets 表的 secret_key


@dataclass
class UserToolDefinition:
    """用户工具完整定义"""
    tool_id: str = ""
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=lambda: {
        "type": "object", "properties": {}, "required": [],
    })
    execution_type: str = "http"          # 当前仅支持 http
    execution_config: dict[str, Any] = field(default_factory=dict)
    user_id: str = ""
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)

    def to_tool_spec(self, executor: "UserToolExecutor") -> ToolSpec:
        """转为 ToolSpec，绑定动态 handler"""
        handler = executor.make_handler(self)
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            handler=handler,
        )


# ── SQLite 存储 ──────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_tools (
    tool_id       TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    parameters    TEXT NOT NULL DEFAULT '{}',
    execution_type TEXT NOT NULL DEFAULT 'http',
    execution_config TEXT NOT NULL DEFAULT '{}',
    user_id       TEXT NOT NULL DEFAULT '',
    enabled       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    tags          TEXT NOT NULL DEFAULT '[]',
    UNIQUE(name, user_id)
);

CREATE TABLE IF NOT EXISTS user_tool_secrets (
    secret_key    TEXT PRIMARY KEY,
    secret_value  TEXT NOT NULL,
    user_id       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
"""


class UserToolStorage:
    """用户工具 SQLite 持久化"""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or _USER_TOOLS_DB)
        self._db = DatabaseManager()
        self._db.init_table(self.db_path, _SCHEMA)

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(self, tool: UserToolDefinition) -> UserToolDefinition:
        if not tool.tool_id:
            tool.tool_id = uuid.uuid4().hex
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        tool.created_at = tool.created_at or now
        tool.updated_at = tool.updated_at or now

        self._db.execute(
            self.db_path,
            """INSERT INTO user_tools
               (tool_id, name, description, parameters,
                execution_type, execution_config,
                user_id, enabled, created_at, updated_at, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tool.tool_id,
                tool.name,
                tool.description,
                json.dumps(tool.parameters, ensure_ascii=False),
                tool.execution_type,
                json.dumps(tool.execution_config, ensure_ascii=False),
                tool.user_id,
                int(tool.enabled),
                tool.created_at,
                tool.updated_at,
                json.dumps(tool.tags, ensure_ascii=False),
            ),
        )
        return tool

    def get(self, tool_id: str) -> UserToolDefinition | None:
        row = self._db.execute_one(
            self.db_path,
            "SELECT * FROM user_tools WHERE tool_id = ?",
            (tool_id,),
        )
        return self._row_to_def(row) if row else None

    def get_by_name(self, name: str, user_id: str = "") -> UserToolDefinition | None:
        row = self._db.execute_one(
            self.db_path,
            "SELECT * FROM user_tools WHERE name = ? AND user_id = ?",
            (name, user_id),
        )
        return self._row_to_def(row) if row else None

    def list_tools(self, user_id: str = "", enabled_only: bool = True) -> list[UserToolDefinition]:
        query = "SELECT * FROM user_tools WHERE user_id = ?"
        params: list[Any] = [user_id]
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY created_at DESC"
        rows = self._db.execute(self.db_path, query, tuple(params))
        return [self._row_to_def(r) for r in rows]

    def update(self, tool_id: str, **fields: Any) -> UserToolDefinition | None:
        existing = self.get(tool_id)
        if existing is None:
            return None

        fields["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        set_clauses = []
        values: list[Any] = []

        _json_fields = {"parameters", "execution_config", "tags"}
        for key, value in fields.items():
            if key in ("tool_id", "created_at"):
                continue
            if key in _json_fields:
                value = json.dumps(value, ensure_ascii=False)
            if key == "enabled":
                value = int(value)
            set_clauses.append(f"{key} = ?")
            values.append(value)

        if not set_clauses:
            return existing

        values.append(tool_id)
        self._db.execute(
            self.db_path,
            f"UPDATE user_tools SET {', '.join(set_clauses)} WHERE tool_id = ?",
            tuple(values),
        )
        return self.get(tool_id)

    def delete(self, tool_id: str) -> bool:
        existing = self.get(tool_id)
        if existing is None:
            return False
        self._db.execute(
            self.db_path,
            "DELETE FROM user_tools WHERE tool_id = ?",
            (tool_id,),
        )
        return True

    # ── 密钥管理 ─────────────────────────────────────────────────────────

    def set_secret(self, secret_key: str, secret_value: str, user_id: str = "") -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        scoped_key = _scope_secret_key(secret_key, user_id)
        self._db.execute(
            self.db_path,
            """INSERT INTO user_tool_secrets (secret_key, secret_value, user_id, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(secret_key) DO UPDATE SET secret_value = excluded.secret_value""",
            (scoped_key, _encrypt_secret_value(secret_value), user_id, now),
        )

    def get_secret(self, secret_key: str, user_id: str = "") -> str | None:
        scoped_key = _scope_secret_key(secret_key, user_id)
        row = self._db.execute_one(
            self.db_path,
            "SELECT secret_value FROM user_tool_secrets WHERE secret_key = ?",
            (scoped_key,),
        )
        if not row:
            return None
        return _decrypt_secret_value(row["secret_value"])

    def delete_secret(self, secret_key: str, user_id: str = "") -> bool:
        scoped_key = _scope_secret_key(secret_key, user_id)
        row = self._db.execute_one(
            self.db_path,
            "SELECT 1 FROM user_tool_secrets WHERE secret_key = ?",
            (scoped_key,),
        )
        if not row:
            return False
        self._db.execute(
            self.db_path,
            "DELETE FROM user_tool_secrets WHERE secret_key = ?",
            (scoped_key,),
        )
        return True

    # ── 内部 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_def(row) -> UserToolDefinition:
        return UserToolDefinition(
            tool_id=row["tool_id"],
            name=row["name"],
            description=row["description"],
            parameters=json.loads(row["parameters"]),
            execution_type=row["execution_type"],
            execution_config=json.loads(row["execution_config"]),
            user_id=row["user_id"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tags=json.loads(row["tags"]),
        )


# ── HTTP 执行器 ──────────────────────────────────────────────────────────────

_TEMPLATE_VAR = re.compile(r"\{(\w+)\}")


def _render_template(template: str, params: dict[str, Any]) -> str:
    """替换模板中的 {param} 占位符"""
    def _replace(m: re.Match) -> str:
        key = m.group(1)
        value = params.get(key, m.group(0))
        return str(value)
    return _TEMPLATE_VAR.sub(_replace, template)


class UserToolExecutor:
    """根据 UserToolDefinition 生成可执行的工具闭包"""

    def __init__(self, storage: UserToolStorage):
        self.storage = storage

    def make_handler(self, tool_def: UserToolDefinition) -> Callable:
        """生成闭包：接收 LLM 传参 → 执行 HTTP 请求 → 返回文本结果"""
        if tool_def.execution_type != "http":
            raise ValueError(f"Unsupported execution type: {tool_def.execution_type}")

        cfg = HttpExecutionConfig(**tool_def.execution_config)
        storage = self.storage

        def _handler(**kwargs: Any) -> str:
            return _execute_http(cfg, kwargs, storage, user_id=tool_def.user_id)

        _handler.__name__ = tool_def.name
        _handler.__doc__ = tool_def.description
        return _handler

    def execute(self, tool_def: UserToolDefinition, params: dict[str, Any]) -> str:
        """直接执行，用于测试接口"""
        handler = self.make_handler(tool_def)
        return handler(**params)


def _execute_http(
    cfg: HttpExecutionConfig,
    params: dict[str, Any],
    storage: UserToolStorage,
    *,
    user_id: str = "",
) -> str:
    """执行单次 HTTP 请求"""
    url = _render_template(cfg.url, params)
    _validate_outbound_url(url)
    timeout = min(cfg.timeout, MAX_TIMEOUT_SECONDS)

    headers: dict[str, str] = dict(cfg.headers)
    headers.setdefault("Content-Type", "application/json")

    # 认证
    if cfg.auth_type == "bearer" and cfg.auth_secret_key:
        secret = storage.get_secret(cfg.auth_secret_key, user_id=user_id)
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
    elif cfg.auth_type == "api_key" and cfg.auth_secret_key:
        secret = storage.get_secret(cfg.auth_secret_key, user_id=user_id)
        if secret:
            headers["X-API-Key"] = secret

    # 构建 body
    body_bytes: bytes | None = None
    method = cfg.method.upper()
    if method in ("POST", "PUT", "PATCH"):
        if cfg.body_template:
            rendered = _render_template(cfg.body_template, params)
            body_bytes = rendered.encode("utf-8")
        else:
            body_bytes = json.dumps(params, ensure_ascii=False).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if len(raw) > MAX_RESPONSE_CHARS:
                raw = raw[:MAX_RESPONSE_CHARS] + "\n...(truncated)"
            return raw
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:2000]
        return f"HTTP {e.code} Error: {err_body}"
    except urllib.error.URLError as e:
        return f"Connection error: {e.reason}"
    except Exception as e:
        return f"Execution error: {e}"


# ── 单例 ─────────────────────────────────────────────────────────────────────

_storage: UserToolStorage | None = None
_lock = threading.Lock()


def get_user_tool_storage() -> UserToolStorage:
    global _storage
    if _storage is None:
        with _lock:
            if _storage is None:
                _storage = UserToolStorage()
    return _storage


def get_user_tool_executor() -> UserToolExecutor:
    return UserToolExecutor(get_user_tool_storage())
