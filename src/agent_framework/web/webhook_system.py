"""
Webhook 系统
支持接收和处理外部系统的 Webhook 事件
"""

import hashlib
import hmac
import agent_framework.core.fast_json as json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from threading import Lock
from agent_framework.core.database import DatabaseManager, open_sqlite_connection


class WebhookStatus(Enum):
    """Webhook 状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISABLED = "disabled"


class WebhookEventStatus(Enum):
    """事件处理状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"


@dataclass
class Webhook:
    """Webhook 配置"""
    webhook_id: str
    name: str
    url_path: str  # 如 /webhooks/github
    secret: str
    status: WebhookStatus = WebhookStatus.ACTIVE
    description: str = ""
    events: List[str] = field(default_factory=list)  # 允许的事件类型
    headers: Dict[str, str] = field(default_factory=dict)  # 必需的请求头
    verify_signature: bool = True
    signature_header: str = "X-Hub-Signature-256"
    signature_algorithm: str = "sha256"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'webhook_id': self.webhook_id,
            'name': self.name,
            'url_path': self.url_path,
            'status': self.status.value,
            'description': self.description,
            'events': self.events,
            'verify_signature': self.verify_signature,
            'created_at': datetime.fromtimestamp(self.created_at).isoformat(),
            'updated_at': datetime.fromtimestamp(self.updated_at).isoformat(),
            'metadata': self.metadata
        }


@dataclass
class WebhookEvent:
    """Webhook 事件"""
    event_id: str
    webhook_id: str
    event_type: str
    payload: Dict[str, Any]
    headers: Dict[str, str]
    status: WebhookEventStatus = WebhookEventStatus.PENDING
    error: Optional[str] = None
    retry_count: int = 0
    received_at: float = field(default_factory=time.time)
    processed_at: Optional[float] = None
    result: Optional[Any] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'event_id': self.event_id,
            'webhook_id': self.webhook_id,
            'event_type': self.event_type,
            'payload': self.payload,
            'status': self.status.value,
            'error': self.error,
            'retry_count': self.retry_count,
            'received_at': datetime.fromtimestamp(self.received_at).isoformat(),
            'processed_at': datetime.fromtimestamp(self.processed_at).isoformat() if self.processed_at else None,
            'result': self.result
        }


class WebhookStorage:
    """Webhook 存储"""

    def __init__(self, db_path: str = "data/webhooks.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Webhook 配置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    webhook_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url_path TEXT UNIQUE NOT NULL,
                    secret TEXT NOT NULL,
                    status TEXT NOT NULL,
                    description TEXT,
                    events TEXT,
                    headers TEXT,
                    verify_signature INTEGER,
                    signature_header TEXT,
                    signature_algorithm TEXT,
                    created_at REAL,
                    updated_at REAL,
                    metadata TEXT
                )
            """)

            # Webhook 事件表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhook_events (
                    event_id TEXT PRIMARY KEY,
                    webhook_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    headers TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    received_at REAL NOT NULL,
                    processed_at REAL,
                    result TEXT,
                    FOREIGN KEY (webhook_id) REFERENCES webhooks(webhook_id)
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_url ON webhooks(url_path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_webhook ON webhook_events(webhook_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_status ON webhook_events(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_received ON webhook_events(received_at)")

    def save_webhook(self, webhook: Webhook):
        """保存 Webhook"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO webhooks
                (webhook_id, name, url_path, secret, status, description, events, headers,
                 verify_signature, signature_header, signature_algorithm, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                webhook.webhook_id,
                webhook.name,
                webhook.url_path,
                webhook.secret,
                webhook.status.value,
                webhook.description,
                json.dumps(webhook.events),
                json.dumps(webhook.headers),
                1 if webhook.verify_signature else 0,
                webhook.signature_header,
                webhook.signature_algorithm,
                webhook.created_at,
                webhook.updated_at,
                json.dumps(webhook.metadata)
            ))

    def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        """获取 Webhook"""
        conn = open_sqlite_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM webhooks WHERE webhook_id = ?", (webhook_id,))
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return None

        return self._row_to_webhook(row)

    def get_webhook_by_path(self, url_path: str) -> Optional[Webhook]:
        """根据路径获取 Webhook"""
        conn = open_sqlite_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM webhooks WHERE url_path = ?", (url_path,))
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return None

        return self._row_to_webhook(row)

    def list_webhooks(self, status: Optional[WebhookStatus] = None) -> List[Webhook]:
        """列出所有 Webhook"""
        conn = open_sqlite_connection(self.db_path)
        try:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM webhooks WHERE status = ? ORDER BY created_at DESC", (status.value,))
            else:
                cursor.execute("SELECT * FROM webhooks ORDER BY created_at DESC")
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [self._row_to_webhook(row) for row in rows]

    def delete_webhook(self, webhook_id: str):
        """删除 Webhook"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM webhooks WHERE webhook_id = ?", (webhook_id,))
            cursor.execute("DELETE FROM webhook_events WHERE webhook_id = ?", (webhook_id,))

    def save_event(self, event: WebhookEvent):
        """保存事件"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO webhook_events
                (event_id, webhook_id, event_type, payload, headers, status, error,
                 retry_count, received_at, processed_at, result)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.webhook_id,
                event.event_type,
                json.dumps(event.payload),
                json.dumps(event.headers),
                event.status.value,
                event.error,
                event.retry_count,
                event.received_at,
                event.processed_at,
                json.dumps(event.result) if event.result else None
            ))

    def get_event(self, event_id: str) -> Optional[WebhookEvent]:
        """获取事件"""
        conn = open_sqlite_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM webhook_events WHERE event_id = ?", (event_id,))
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return None

        return self._row_to_event(row)

    def list_events(
        self,
        webhook_id: Optional[str] = None,
        status: Optional[WebhookEventStatus] = None,
        limit: int = 100
    ) -> List[WebhookEvent]:
        """列出事件"""
        conn = open_sqlite_connection(self.db_path)
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM webhook_events WHERE 1=1"
            params = []

            if webhook_id:
                query += " AND webhook_id = ?"
                params.append(webhook_id)

            if status:
                query += " AND status = ?"
                params.append(status.value)

            query += " ORDER BY received_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [self._row_to_event(row) for row in rows]

    def _row_to_webhook(self, row) -> Webhook:
        """数据库行转 Webhook"""
        return Webhook(
            webhook_id=row['webhook_id'],
            name=row['name'],
            url_path=row['url_path'],
            secret=row['secret'],
            status=WebhookStatus(row['status']),
            description=row['description'] or "",
            events=json.loads(row['events']) if row['events'] else [],
            headers=json.loads(row['headers']) if row['headers'] else {},
            verify_signature=bool(row['verify_signature']),
            signature_header=row['signature_header'],
            signature_algorithm=row['signature_algorithm'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            metadata=json.loads(row['metadata']) if row['metadata'] else {}
        )

    def _row_to_event(self, row) -> WebhookEvent:
        """数据库行转事件"""
        return WebhookEvent(
            event_id=row['event_id'],
            webhook_id=row['webhook_id'],
            event_type=row['event_type'],
            payload=json.loads(row['payload']),
            headers=json.loads(row['headers']) if row['headers'] else {},
            status=WebhookEventStatus(row['status']),
            error=row['error'],
            retry_count=row['retry_count'],
            received_at=row['received_at'],
            processed_at=row['processed_at'],
            result=json.loads(row['result']) if row['result'] else None
        )


class WebhookManager:
    """Webhook 管理器"""

    def __init__(self, storage: WebhookStorage):
        self.storage = storage
        self.handlers: Dict[str, List[Callable]] = {}
        self.lock = Lock()

    def create_webhook(
        self,
        name: str,
        url_path: str,
        secret: Optional[str] = None,
        **kwargs
    ) -> Webhook:
        """创建 Webhook"""
        webhook_id = str(uuid.uuid4())

        if not secret:
            secret = self._generate_secret()

        webhook = Webhook(
            webhook_id=webhook_id,
            name=name,
            url_path=url_path,
            secret=secret,
            **kwargs
        )

        self.storage.save_webhook(webhook)
        return webhook

    def update_webhook(self, webhook_id: str, **kwargs) -> Optional[Webhook]:
        """更新 Webhook"""
        webhook = self.storage.get_webhook(webhook_id)
        if not webhook:
            return None

        # 更新字段
        for key, value in kwargs.items():
            if hasattr(webhook, key):
                setattr(webhook, key, value)

        webhook.updated_at = time.time()
        self.storage.save_webhook(webhook)
        return webhook

    def delete_webhook(self, webhook_id: str):
        """删除 Webhook"""
        self.storage.delete_webhook(webhook_id)

    def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        """获取 Webhook"""
        return self.storage.get_webhook(webhook_id)

    def list_webhooks(self, status: Optional[WebhookStatus] = None) -> List[Webhook]:
        """列出 Webhook"""
        return self.storage.list_webhooks(status)

    def register_handler(self, webhook_id: str, handler: Callable):
        """注册事件处理器"""
        with self.lock:
            if webhook_id not in self.handlers:
                self.handlers[webhook_id] = []
            self.handlers[webhook_id].append(handler)

    def handle_request(
        self,
        url_path: str,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> WebhookEvent:
        """处理 Webhook 请求"""
        # 查找 Webhook
        webhook = self.storage.get_webhook_by_path(url_path)
        if not webhook:
            raise ValueError(f"Webhook 不存在: {url_path}")

        if webhook.status != WebhookStatus.ACTIVE:
            raise ValueError(f"Webhook 未激活: {url_path}")

        # 验证签名
        if webhook.verify_signature:
            signature = headers.get(webhook.signature_header, '')
            if not self._verify_signature(payload, webhook.secret, signature, webhook.signature_algorithm):
                raise ValueError("签名验证失败")

        # 提取事件类型
        event_type = headers.get('X-Event-Type', 'unknown')

        # 创建事件
        event = WebhookEvent(
            event_id=str(uuid.uuid4()),
            webhook_id=webhook.webhook_id,
            event_type=event_type,
            payload=payload,
            headers=headers
        )

        self.storage.save_event(event)

        # 异步处理事件
        self._process_event(event, webhook)

        return event

    def _process_event(self, event: WebhookEvent, webhook: Webhook):
        """处理事件"""
        try:
            event.status = WebhookEventStatus.PROCESSING
            self.storage.save_event(event)

            # 调用处理器
            handlers = self.handlers.get(webhook.webhook_id, [])
            results = []

            for handler in handlers:
                try:
                    result = handler(event, webhook)
                    results.append(result)
                except Exception as e:
                    results.append({'error': str(e)})

            event.status = WebhookEventStatus.SUCCESS
            event.result = results
            event.processed_at = time.time()

        except Exception as e:
            event.status = WebhookEventStatus.FAILED
            event.error = str(e)
            event.processed_at = time.time()

        finally:
            self.storage.save_event(event)

    def _verify_signature(
        self,
        payload: Dict[str, Any],
        secret: str,
        signature: str,
        algorithm: str = "sha256"
    ) -> bool:
        """验证签名"""
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')

        if algorithm == "sha256":
            expected = hmac.new(
                secret.encode('utf-8'),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
        elif algorithm == "sha1":
            expected = hmac.new(
                secret.encode('utf-8'),
                payload_bytes,
                hashlib.sha1
            ).hexdigest()
        else:
            return False

        # 支持多种签名格式
        if signature.startswith('sha256='):
            signature = signature[7:]
        elif signature.startswith('sha1='):
            signature = signature[5:]

        return hmac.compare_digest(expected, signature)

    def _generate_secret(self) -> str:
        """生成密钥"""
        return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()


# 全局单例
_webhook_manager: Optional[WebhookManager] = None


def get_webhook_manager() -> WebhookManager:
    """获取 Webhook 管理器"""
    global _webhook_manager

    if _webhook_manager is None:
        storage = WebhookStorage()
        _webhook_manager = WebhookManager(storage)

    return _webhook_manager
