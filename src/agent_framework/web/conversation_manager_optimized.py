"""
优化后的对话管理系统
使用统一数据库管理层
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

# 使用统一数据库管理
from agent_framework.core.database import get_db_connection, execute_query, execute_one, init_table


# ─── 数据模型 ─────────────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationStatus(str, Enum):
    """对话状态"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class Message:
    """消息"""
    message_id: str
    conversation_id: str
    role: MessageRole
    content: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)
    tokens: Optional[int] = None
    model: Optional[str] = None


@dataclass
class Conversation:
    """对话"""
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    status: ConversationStatus = ConversationStatus.ACTIVE
    user_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    total_tokens: int = 0
    rating: Optional[int] = None
    feedback: Optional[str] = None


@dataclass
class Annotation:
    """标注"""
    annotation_id: str
    conversation_id: str
    message_id: Optional[str]
    annotation_type: str
    content: str
    created_at: str
    created_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── 优化后的对话存储 ─────────────────────────────────────────────────────────

class ConversationStorageOptimized:
    """优化后的对话存储 - 使用统一数据库管理"""

    def __init__(self, db_path: str = "./data/conversations.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        schema = """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                user_id TEXT,
                tags TEXT,
                metadata TEXT,
                message_count INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                rating INTEGER,
                feedback TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);
            CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);

            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT,
                tool_calls TEXT,
                tool_results TEXT,
                tokens INTEGER,
                model TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

            CREATE TABLE IF NOT EXISTS annotations (
                annotation_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                message_id TEXT,
                annotation_type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT,
                metadata TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            );

            CREATE INDEX IF NOT EXISTS idx_annotations_conversation_id ON annotations(conversation_id);
        """
        init_table(self.db_path, schema)

    def create_conversation(self, conversation: Conversation) -> str:
        """创建对话"""
        execute_query(
            self.db_path,
            """
            INSERT INTO conversations
            (conversation_id, title, created_at, updated_at, status, user_id, tags, metadata,
             message_count, total_tokens, rating, feedback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation.conversation_id,
                conversation.title,
                conversation.created_at,
                conversation.updated_at,
                conversation.status.value,
                conversation.user_id,
                json.dumps(conversation.tags),
                json.dumps(conversation.metadata),
                conversation.message_count,
                conversation.total_tokens,
                conversation.rating,
                conversation.feedback
            )
        )
        return conversation.conversation_id

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话"""
        row = execute_one(
            self.db_path,
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,)
        )

        if not row:
            return None

        return Conversation(
            conversation_id=row['conversation_id'],
            title=row['title'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            status=ConversationStatus(row['status']),
            user_id=row['user_id'],
            tags=json.loads(row['tags']) if row['tags'] else [],
            metadata=json.loads(row['metadata']) if row['metadata'] else {},
            message_count=row['message_count'],
            total_tokens=row['total_tokens'],
            rating=row['rating'],
            feedback=row['feedback']
        )

    def list_conversations(
        self,
        user_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Conversation]:
        """列出对话"""
        query = "SELECT * FROM conversations WHERE 1=1"
        params = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = execute_query(self.db_path, query, tuple(params))

        return [
            Conversation(
                conversation_id=row['conversation_id'],
                title=row['title'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                status=ConversationStatus(row['status']),
                user_id=row['user_id'],
                tags=json.loads(row['tags']) if row['tags'] else [],
                metadata=json.loads(row['metadata']) if row['metadata'] else {},
                message_count=row['message_count'],
                total_tokens=row['total_tokens'],
                rating=row['rating'],
                feedback=row['feedback']
            )
            for row in rows
        ]

    def add_message(self, message: Message):
        """添加消息"""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 插入消息
            cursor.execute(
                """
                INSERT INTO messages
                (message_id, conversation_id, role, content, timestamp, metadata,
                 tool_calls, tool_results, tokens, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.conversation_id,
                    message.role.value,
                    message.content,
                    message.timestamp,
                    json.dumps(message.metadata),
                    json.dumps(message.tool_calls),
                    json.dumps(message.tool_results),
                    message.tokens,
                    message.model
                )
            )

            # 更新对话统计
            cursor.execute(
                """
                UPDATE conversations
                SET message_count = message_count + 1,
                    total_tokens = total_tokens + ?,
                    updated_at = ?
                WHERE conversation_id = ?
                """,
                (message.tokens or 0, message.timestamp, message.conversation_id)
            )

    def get_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Message]:
        """获取对话消息"""
        query = """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """
        params = [conversation_id]

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = execute_query(self.db_path, query, tuple(params))

        return [
            Message(
                message_id=row['message_id'],
                conversation_id=row['conversation_id'],
                role=MessageRole(row['role']),
                content=row['content'],
                timestamp=row['timestamp'],
                metadata=json.loads(row['metadata']) if row['metadata'] else {},
                tool_calls=json.loads(row['tool_calls']) if row['tool_calls'] else [],
                tool_results=json.loads(row['tool_results']) if row['tool_results'] else [],
                tokens=row['tokens'],
                model=row['model']
            )
            for row in rows
        ]

    def update_conversation(
        self,
        conversation_id: str,
        **kwargs
    ):
        """更新对话"""
        allowed_fields = ['title', 'status', 'tags', 'metadata', 'rating', 'feedback']
        updates = []
        params = []

        for key, value in kwargs.items():
            if key in allowed_fields:
                if key in ['tags', 'metadata']:
                    value = json.dumps(value)
                elif key == 'status' and isinstance(value, ConversationStatus):
                    value = value.value
                updates.append(f"{key} = ?")
                params.append(value)

        if not updates:
            return

        params.extend([datetime.now().isoformat(), conversation_id])

        execute_query(
            self.db_path,
            f"""
            UPDATE conversations
            SET {', '.join(updates)}, updated_at = ?
            WHERE conversation_id = ?
            """,
            tuple(params)
        )

    def delete_conversation(self, conversation_id: str):
        """删除对话（软删除）"""
        self.update_conversation(
            conversation_id,
            status=ConversationStatus.DELETED
        )

    def search_conversations(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Conversation]:
        """搜索对话"""
        sql = """
            SELECT DISTINCT c.* FROM conversations c
            LEFT JOIN messages m ON c.conversation_id = m.conversation_id
            WHERE (c.title LIKE ? OR m.content LIKE ?)
            AND c.status != 'deleted'
        """
        params = [f"%{query}%", f"%{query}%"]

        if user_id:
            sql += " AND c.user_id = ?"
            params.append(user_id)

        sql += " ORDER BY c.updated_at DESC LIMIT ?"
        params.append(limit)

        rows = execute_query(self.db_path, sql, tuple(params))

        return [
            Conversation(
                conversation_id=row['conversation_id'],
                title=row['title'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                status=ConversationStatus(row['status']),
                user_id=row['user_id'],
                tags=json.loads(row['tags']) if row['tags'] else [],
                metadata=json.loads(row['metadata']) if row['metadata'] else {},
                message_count=row['message_count'],
                total_tokens=row['total_tokens'],
                rating=row['rating'],
                feedback=row['feedback']
            )
            for row in rows
        ]


# ─── 对话管理器 ───────────────────────────────────────────────────────────────

class ConversationManagerOptimized:
    """优化后的对话管理器"""

    def __init__(self, storage: ConversationStorageOptimized):
        self.storage = storage
        self._cache = {}  # 简单的内存缓存

    def create_conversation(
        self,
        title: str = "新对话",
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Conversation:
        """创建新对话"""
        now = datetime.now().isoformat()
        conversation = Conversation(
            conversation_id=str(uuid.uuid4()),
            title=title,
            created_at=now,
            updated_at=now,
            user_id=user_id,
            metadata=metadata or {}
        )

        self.storage.create_conversation(conversation)
        self._cache[conversation.conversation_id] = conversation

        return conversation

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话（带缓存）"""
        if conversation_id in self._cache:
            return self._cache[conversation_id]

        conversation = self.storage.get_conversation(conversation_id)
        if conversation:
            self._cache[conversation_id] = conversation

        return conversation

    def add_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        **kwargs
    ) -> Message:
        """添加消息"""
        message = Message(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            **kwargs
        )

        self.storage.add_message(message)

        # 清除缓存
        if conversation_id in self._cache:
            del self._cache[conversation_id]

        return message

    def get_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Message]:
        """获取消息"""
        return self.storage.get_messages(conversation_id, limit)

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
