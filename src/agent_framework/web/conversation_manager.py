"""
对话历史管理系统
支持对话持久化、搜索、标注、导出
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

from agent_framework.core.database import DatabaseManager
from agent_framework.infra.cache_layer import get_cache


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

    # 扩展字段
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

    # 元数据
    user_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 统计信息
    message_count: int = 0
    total_tokens: int = 0

    # 评分和反馈
    rating: Optional[int] = None  # 1-5 星
    feedback: Optional[str] = None


@dataclass
class Annotation:
    """标注"""
    annotation_id: str
    conversation_id: str
    message_id: Optional[str]
    annotation_type: str  # 'label', 'correction', 'comment'
    content: str
    created_at: str
    created_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── 对话存储 ─────────────────────────────────────────────────────────────────

class ConversationStorage:
    """对话持久化存储（SQLite）"""

    def __init__(self, db_path: str = "./data/conversations.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_manager = DatabaseManager()

        # 初始化缓存
        self._conversation_cache = get_cache("conversations", max_size=500, ttl_seconds=300)
        self._message_cache = get_cache("messages", max_size=1000, ttl_seconds=300)

        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 对话表
            cursor.execute("""
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
                )
            """)

            # 消息表
            cursor.execute("""
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
                )
            """)

            # 标注表
            cursor.execute("""
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
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user
                ON conversations(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_created
                ON conversations(created_at DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, timestamp)
            """)

    def create_conversation(self, conversation: Conversation) -> str:
        """创建对话"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO conversations
                (conversation_id, title, created_at, updated_at, status, user_id,
                 tags, metadata, message_count, total_tokens, rating, feedback)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
                conversation.feedback,
            ))

            return conversation.conversation_id

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话（带缓存）"""
        # 尝试从缓存获取
        cached = self._conversation_cache.get(conversation_id)
        if cached is not None:
            return cached

        # 从数据库获取
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM conversations WHERE conversation_id = ?
            """, (conversation_id,))

            row = cursor.fetchone()

        if not row:
            return None

        conversation = Conversation(
            conversation_id=row[0],
            title=row[1],
            created_at=row[2],
            updated_at=row[3],
            status=ConversationStatus(row[4]),
            user_id=row[5],
            tags=json.loads(row[6]) if row[6] else [],
            metadata=json.loads(row[7]) if row[7] else {},
            message_count=row[8],
            total_tokens=row[9],
            rating=row[10],
            feedback=row[11],
        )

        # 缓存结果
        self._conversation_cache.set(conversation_id, conversation)
        return conversation

    def update_conversation(self, conversation: Conversation):
        """更新对话"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE conversations SET
                    title = ?,
                    updated_at = ?,
                    status = ?,
                    tags = ?,
                    metadata = ?,
                    message_count = ?,
                    total_tokens = ?,
                    rating = ?,
                    feedback = ?
                WHERE conversation_id = ?
            """, (
                conversation.title,
                conversation.updated_at,
                conversation.status.value,
                json.dumps(conversation.tags),
                json.dumps(conversation.metadata),
                conversation.message_count,
                conversation.total_tokens,
                conversation.rating,
                conversation.feedback,
                conversation.conversation_id,
            ))

        # 使缓存失效
        self._conversation_cache.delete(conversation.conversation_id)

    def delete_conversation(self, conversation_id: str):
        """删除对话（软删除）"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE conversations SET status = ? WHERE conversation_id = ?
            """, (ConversationStatus.DELETED.value, conversation_id))

        # 使缓存失效
        self._conversation_cache.delete(conversation_id)

    def list_conversations(
        self,
        user_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Conversation]:
        """列出对话"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM conversations WHERE 1=1"
            params = []

            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)

            if status:
                query += " AND status = ?"
                params.append(status.value)

            # 标签过滤（简单实现）
            if tags:
                for tag in tags:
                    query += " AND tags LIKE ?"
                    params.append(f'%"{tag}"%')

            query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            conversations = []
            for row in rows:
                conversations.append(Conversation(
                    conversation_id=row[0],
                    title=row[1],
                    created_at=row[2],
                    updated_at=row[3],
                    status=ConversationStatus(row[4]),
                    user_id=row[5],
                    tags=json.loads(row[6]) if row[6] else [],
                    metadata=json.loads(row[7]) if row[7] else {},
                    message_count=row[8],
                    total_tokens=row[9],
                    rating=row[10],
                    feedback=row[11],
                ))

            return conversations

    def add_message(self, message: Message):
        """添加消息"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Debug: print types
            # print(f"Debug: message_id={message.message_id}, type={type(message.message_id)}")
            # print(f"Debug: conversation_id={message.conversation_id}, type={type(message.conversation_id)}")

            cursor.execute("""
                INSERT INTO messages
                (message_id, conversation_id, role, content, timestamp, metadata,
                 tool_calls, tool_results, tokens, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(message.message_id),
                str(message.conversation_id),
                message.role.value if hasattr(message.role, 'value') else str(message.role),
                str(message.content),
                str(message.timestamp),
                json.dumps(message.metadata) if message.metadata else '{}',
                json.dumps(message.tool_calls) if message.tool_calls else '[]',
                json.dumps(message.tool_results) if message.tool_results else '[]',
                message.tokens,
                message.model,
            ))

            # 更新对话统计
            cursor.execute("""
                UPDATE conversations SET
                    message_count = message_count + 1,
                    total_tokens = total_tokens + ?,
                    updated_at = ?
                WHERE conversation_id = ?
            """, (message.tokens or 0, message.timestamp, message.conversation_id))

    def get_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
    ) -> List[Message]:
        """获取对话消息"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """
            params = [conversation_id]

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            messages = []
            for row in rows:
                messages.append(Message(
                    message_id=row[0],
                    conversation_id=row[1],
                    role=MessageRole(row[2]),
                    content=row[3],
                    timestamp=row[4],
                    metadata=json.loads(row[5]) if row[5] else {},
                    tool_calls=json.loads(row[6]) if row[6] else [],
                    tool_results=json.loads(row[7]) if row[7] else [],
                    tokens=row[8],
                    model=row[9],
                ))

            return messages

    def search_conversations(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Conversation]:
        """搜索对话"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            sql = """
                SELECT DISTINCT c.* FROM conversations c
                LEFT JOIN messages m ON c.conversation_id = m.conversation_id
                WHERE (c.title LIKE ? OR m.content LIKE ?)
            """
            params = [f"%{query}%", f"%{query}%"]

            if user_id:
                sql += " AND c.user_id = ?"
                params.append(user_id)

            sql += " ORDER BY c.updated_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            conversations = []
            for row in rows:
                conversations.append(Conversation(
                    conversation_id=row[0],
                    title=row[1],
                    created_at=row[2],
                    updated_at=row[3],
                    status=ConversationStatus(row[4]),
                    user_id=row[5],
                    tags=json.loads(row[6]) if row[6] else [],
                    metadata=json.loads(row[7]) if row[7] else {},
                    message_count=row[8],
                    total_tokens=row[9],
                    rating=row[10],
                    feedback=row[11],
                ))

            return conversations

    def add_annotation(self, annotation: Annotation):
        """添加标注"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO annotations
                (annotation_id, conversation_id, message_id, annotation_type,
                 content, created_at, created_by, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                annotation.annotation_id,
                annotation.conversation_id,
                annotation.message_id,
                annotation.annotation_type,
                annotation.content,
                annotation.created_at,
                annotation.created_by,
                json.dumps(annotation.metadata),
            ))

    def get_annotations(
        self,
        conversation_id: str,
        message_id: Optional[str] = None,
    ) -> List[Annotation]:
        """获取标注"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            if message_id:
                cursor.execute("""
                    SELECT * FROM annotations
                    WHERE conversation_id = ? AND message_id = ?
                    ORDER BY created_at DESC
                """, (conversation_id, message_id))
            else:
                cursor.execute("""
                    SELECT * FROM annotations
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC
                """, (conversation_id,))

            rows = cursor.fetchall()

            annotations = []
            for row in rows:
                annotations.append(Annotation(
                    annotation_id=row[0],
                    conversation_id=row[1],
                    message_id=row[2],
                    annotation_type=row[3],
                    content=row[4],
                    created_at=row[5],
                    created_by=row[6],
                    metadata=json.loads(row[7]) if row[7] else {},
                ))

            return annotations


# ─── 对话管理器 ───────────────────────────────────────────────────────────────

class ConversationManager:
    """对话管理器 - 高级 API"""

    def __init__(self, storage: ConversationStorage):
        self.storage = storage

    def create_conversation(
        self,
        title: str,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Conversation:
        """创建新对话"""
        now = datetime.now().isoformat()
        conversation = Conversation(
            conversation_id=str(uuid.uuid4()),
            title=title,
            created_at=now,
            updated_at=now,
            user_id=user_id,
            tags=tags or [],
        )
        self.storage.create_conversation(conversation)
        return conversation

    def add_user_message(
        self,
        conversation_id: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> Message:
        """添加用户消息"""
        message = Message(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=content,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {},
        )
        self.storage.add_message(message)
        return message

    def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        model: Optional[str] = None,
        tokens: Optional[int] = None,
        tool_calls: Optional[List[Dict]] = None,
        metadata: Optional[Dict] = None,
    ) -> Message:
        """添加助手消息"""
        message = Message(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=content,
            timestamp=datetime.now().isoformat(),
            model=model,
            tokens=tokens,
            tool_calls=tool_calls or [],
            metadata=metadata or {},
        )
        self.storage.add_message(message)
        return message

    def get_conversation_history(
        self,
        conversation_id: str,
    ) -> tuple[Conversation, List[Message]]:
        """获取完整对话历史"""
        conversation = self.storage.get_conversation(conversation_id)
        messages = self.storage.get_messages(conversation_id)
        return conversation, messages

    def rate_conversation(
        self,
        conversation_id: str,
        rating: int,
        feedback: Optional[str] = None,
    ):
        """评价对话"""
        conversation = self.storage.get_conversation(conversation_id)
        if conversation:
            conversation.rating = rating
            conversation.feedback = feedback
            conversation.updated_at = datetime.now().isoformat()
            self.storage.update_conversation(conversation)

    def add_tag(self, conversation_id: str, tag: str):
        """添加标签"""
        conversation = self.storage.get_conversation(conversation_id)
        if conversation and tag not in conversation.tags:
            conversation.tags.append(tag)
            conversation.updated_at = datetime.now().isoformat()
            self.storage.update_conversation(conversation)

    def export_conversation(
        self,
        conversation_id: str,
        format: str = "json",
    ) -> str:
        """导出对话"""
        conversation, messages = self.get_conversation_history(conversation_id)

        if format == "json":
            data = {
                "conversation": asdict(conversation),
                "messages": [asdict(m) for m in messages],
            }
            return json.dumps(data, indent=2, ensure_ascii=False)

        elif format == "markdown":
            lines = [
                f"# {conversation.title}",
                f"",
                f"创建时间: {conversation.created_at}",
                f"消息数: {conversation.message_count}",
                f"",
                "---",
                "",
            ]

            for msg in messages:
                role_name = "用户" if msg.role == MessageRole.USER else "助手"
                lines.append(f"## {role_name}")
                lines.append(f"")
                lines.append(msg.content)
                lines.append(f"")

            return "\n".join(lines)

        else:
            raise ValueError(f"不支持的格式: {format}")
