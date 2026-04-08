"""
长期记忆系统增强版
支持跨会话记忆、用户偏好学习、知识图谱
"""

import agent_framework.core.fast_json as json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import hashlib
from agent_framework.core.database import DatabaseManager


@dataclass
class LongTermMemory:
    """长期记忆"""
    memory_id: str
    user_id: str
    content: str
    memory_type: str  # fact, preference, skill, relationship
    importance: float
    access_count: int
    last_accessed: str
    created_at: str
    tags: List[str]
    metadata: Dict


class LongTermMemorySystem:
    """长期记忆系统"""

    def __init__(self, db_path: str = "data/long_term_memory.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 长期记忆表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    memory_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    importance REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT,
                    created_at TEXT NOT NULL,
                    tags TEXT,
                    metadata TEXT
                )
            ''')

            # 用户偏好表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    pref_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    updated_at TEXT NOT NULL
                )
            ''')

            # 知识图谱表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS knowledge_graph (
                    edge_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    source_entity TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target_entity TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL
                )
            ''')

    def add_memory(self, user_id: str, content: str, memory_type: str,
                  importance: float = 0.5, tags: Optional[List[str]] = None,
                  metadata: Optional[Dict] = None) -> str:
        """添加长期记忆"""
        import uuid

        memory_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO long_term_memories
                (memory_id, user_id, content, memory_type, importance, created_at, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                memory_id,
                user_id,
                content,
                memory_type,
                importance,
                now,
                json.dumps(tags or []),
                json.dumps(metadata or {})
            ))

        return memory_id

    def retrieve_memories(self, user_id: str, query: Optional[str] = None,
                         memory_type: Optional[str] = None,
                         min_importance: float = 0.0,
                         limit: int = 10) -> List[LongTermMemory]:
        """检索记忆"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            sql = '''
                SELECT memory_id, user_id, content, memory_type, importance,
                       access_count, last_accessed, created_at, tags, metadata
                FROM long_term_memories
                WHERE user_id = ? AND importance >= ?
            '''
            params = [user_id, min_importance]

            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)

            if query:
                sql += " AND content LIKE ?"
                params.append(f"%{query}%")

            sql += " ORDER BY importance DESC, access_count DESC LIMIT ?"
            params.append(limit)

            cursor.execute(sql, params)

            memories = []
            for row in cursor.fetchall():
                memories.append(LongTermMemory(
                    memory_id=row[0],
                    user_id=row[1],
                    content=row[2],
                    memory_type=row[3],
                    importance=row[4],
                    access_count=row[5],
                    last_accessed=row[6],
                    created_at=row[7],
                    tags=json.loads(row[8]) if row[8] else [],
                    metadata=json.loads(row[9]) if row[9] else {}
                ))

            # 更新访问计数
            for memory in memories:
                cursor.execute('''
                    UPDATE long_term_memories
                    SET access_count = access_count + 1,
                        last_accessed = ?
                    WHERE memory_id = ?
                ''', (datetime.now().isoformat(), memory.memory_id))

        return memories

    def forget_old_memories(self, user_id: str, days: int = 90):
        """遗忘旧记忆（降低重要性）"""
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 降低旧记忆的重要性
            cursor.execute('''
                UPDATE long_term_memories
                SET importance = importance * 0.8
                WHERE user_id = ?
                  AND last_accessed < ?
                  AND importance > 0.1
            ''', (user_id, cutoff_date))

            # 删除非常不重要的记忆
            cursor.execute('''
                DELETE FROM long_term_memories
                WHERE user_id = ?
                  AND importance < 0.1
                  AND access_count < 2
            ''', (user_id,))

    def learn_preference(self, user_id: str, category: str, key: str,
                        value: str, confidence: float = 1.0):
        """学习用户偏好"""
        import uuid

        pref_id = str(uuid.uuid4())

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 检查是否已存在
            cursor.execute('''
                SELECT pref_id, confidence FROM user_preferences
                WHERE user_id = ? AND category = ? AND key = ?
            ''', (user_id, category, key))

            existing = cursor.fetchone()

            if existing:
                # 更新现有偏好
                new_confidence = (existing[1] + confidence) / 2
                cursor.execute('''
                    UPDATE user_preferences
                    SET value = ?, confidence = ?, updated_at = ?
                    WHERE pref_id = ?
                ''', (value, new_confidence, datetime.now().isoformat(), existing[0]))
            else:
                # 创建新偏好
                cursor.execute('''
                    INSERT INTO user_preferences
                    (pref_id, user_id, category, key, value, confidence, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pref_id,
                    user_id,
                    category,
                    key,
                    value,
                    confidence,
                    datetime.now().isoformat()
                ))

    def get_preferences(self, user_id: str, category: Optional[str] = None) -> Dict:
        """获取用户偏好"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            if category:
                cursor.execute('''
                    SELECT key, value, confidence
                    FROM user_preferences
                    WHERE user_id = ? AND category = ?
                    ORDER BY confidence DESC
                ''', (user_id, category))
            else:
                cursor.execute('''
                    SELECT category, key, value, confidence
                    FROM user_preferences
                    WHERE user_id = ?
                    ORDER BY confidence DESC
                ''', (user_id,))

            preferences = {}
            for row in cursor.fetchall():
                if category:
                    preferences[row[0]] = {
                        'value': row[1],
                        'confidence': row[2]
                    }
                else:
                    cat = row[0]
                    if cat not in preferences:
                        preferences[cat] = {}
                    preferences[cat][row[1]] = {
                        'value': row[2],
                        'confidence': row[3]
                    }

        return preferences

    def add_knowledge_edge(self, user_id: str, source: str, relation: str,
                          target: str, weight: float = 1.0):
        """添加知识图谱边"""
        import uuid

        edge_id = str(uuid.uuid4())

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO knowledge_graph
                (edge_id, user_id, source_entity, relation, target_entity, weight, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                edge_id,
                user_id,
                source,
                relation,
                target,
                weight,
                datetime.now().isoformat()
            ))

    def get_related_entities(self, user_id: str, entity: str, max_depth: int = 2) -> List[Dict]:
        """获取相关实体"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT source_entity, relation, target_entity, weight
                FROM knowledge_graph
                WHERE user_id = ?
                  AND (source_entity = ? OR target_entity = ?)
                ORDER BY weight DESC
            ''', (user_id, entity, entity))

            related = []
            for row in cursor.fetchall():
                related.append({
                    'source': row[0],
                    'relation': row[1],
                    'target': row[2],
                    'weight': row[3]
                })

        return related


# 全局实例
_long_term_memory = None


def get_long_term_memory() -> LongTermMemorySystem:
    """获取长期记忆系统实例"""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemorySystem()
    return _long_term_memory
