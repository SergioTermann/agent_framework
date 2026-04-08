"""
优化的记忆存储 - 使用 sqlite-vec + FTS5
==========================================

性能优化：
1. sqlite-vec 插件 - 原生向量相似度搜索
2. FTS5 - 全文检索
3. 混合检索 - 向量 + 关键词
"""

import sqlite3
import hashlib
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict

import agent_framework.core.fast_json as json


@dataclass
class Memory:
    """记忆单元"""
    id: str
    content: str
    memory_type: str
    importance: float
    created_at: datetime
    last_accessed: datetime
    access_count: int
    tags: List[str]
    context: Dict[str, Any]
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['last_accessed'] = self.last_accessed.isoformat()
        return data


class OptimizedMemoryStore:
    """
    优化的记忆存储

    使用 sqlite-vec 进行向量检索，FTS5 进行全文搜索
    """

    def __init__(self, db_path: str = "data/memory_optimized.db"):
        self.db_path = db_path
        Path("data").mkdir(exist_ok=True)
        self._init_database()

    def _init_database(self):
        """初始化数据库（尝试加载 sqlite-vec）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # 尝试加载 sqlite-vec 扩展
        self.vec_available = False
        try:
            conn.enable_load_extension(True)
            # 尝试常见路径
            for path in ["vec0", "sqlite-vec", "./vec0.so", "./vec0.dll"]:
                try:
                    conn.load_extension(path)
                    self.vec_available = True
                    break
                except:
                    continue
            conn.enable_load_extension(False)
        except:
            pass

        # 创建主表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                importance REAL NOT NULL,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                access_count INTEGER DEFAULT 0,
                tags TEXT,
                context TEXT
            )
        """)

        # 创建 FTS5 全文索引
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                id UNINDEXED,
                content,
                tags,
                tokenize='porter unicode61'
            )
        """)

        # 如果 sqlite-vec 可用，创建向量表
        if self.vec_available:
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(
                        id TEXT PRIMARY KEY,
                        embedding FLOAT[384]
                    )
                """)
            except:
                self.vec_available = False

        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memories(memory_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance DESC)")

        conn.commit()
        conn.close()

    def add(self, memory: Memory) -> None:
        """添加记忆"""
        conn = sqlite3.connect(self.db_path)

        # 插入主表
        conn.execute("""
            INSERT OR REPLACE INTO memories
            (id, content, memory_type, importance, created_at, last_accessed,
             access_count, tags, context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory.id,
            memory.content,
            memory.memory_type,
            memory.importance,
            memory.created_at.isoformat(),
            memory.last_accessed.isoformat(),
            memory.access_count,
            json.dumps(memory.tags, ensure_ascii=False),
            json.dumps(memory.context, ensure_ascii=False),
        ))

        # 插入 FTS5
        conn.execute("""
            INSERT OR REPLACE INTO memories_fts (id, content, tags)
            VALUES (?, ?, ?)
        """, (memory.id, memory.content, " ".join(memory.tags)))

        # 插入向量表（如果可用且有 embedding）
        if self.vec_available and memory.embedding:
            try:
                # sqlite-vec 使用 vec_f32 函数
                embedding_blob = self._float_list_to_blob(memory.embedding)
                conn.execute("""
                    INSERT OR REPLACE INTO memories_vec (id, embedding)
                    VALUES (?, vec_f32(?))
                """, (memory.id, embedding_blob))
            except:
                pass

        conn.commit()
        conn.close()

    def search_vector(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        memory_type: Optional[str] = None,
    ) -> List[Memory]:
        """向量相似度搜索（使用 sqlite-vec）"""
        if not self.vec_available:
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        query_blob = self._float_list_to_blob(query_embedding)

        # sqlite-vec 的 KNN 搜索
        if memory_type:
            cursor = conn.execute("""
                SELECT m.*, vec_distance_cosine(v.embedding, vec_f32(?)) as distance
                FROM memories_vec v
                JOIN memories m ON v.id = m.id
                WHERE m.memory_type = ?
                ORDER BY distance
                LIMIT ?
            """, (query_blob, memory_type, top_k))
        else:
            cursor = conn.execute("""
                SELECT m.*, vec_distance_cosine(v.embedding, vec_f32(?)) as distance
                FROM memories_vec v
                JOIN memories m ON v.id = m.id
                ORDER BY distance
                LIMIT ?
            """, (query_blob, top_k))

        results = [self._row_to_memory(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def search_fulltext(
        self,
        query: str,
        top_k: int = 10,
        memory_type: Optional[str] = None,
    ) -> List[Memory]:
        """全文搜索（使用 FTS5）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        if memory_type:
            cursor = conn.execute("""
                SELECT m.*, fts.rank
                FROM memories_fts fts
                JOIN memories m ON fts.id = m.id
                WHERE fts.content MATCH ? AND m.memory_type = ?
                ORDER BY fts.rank
                LIMIT ?
            """, (query, memory_type, top_k))
        else:
            cursor = conn.execute("""
                SELECT m.*, fts.rank
                FROM memories_fts fts
                JOIN memories m ON fts.id = m.id
                WHERE fts.content MATCH ?
                ORDER BY fts.rank
                LIMIT ?
            """, (query, top_k))

        results = [self._row_to_memory(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def search_hybrid(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        vector_weight: float = 0.7,
        memory_type: Optional[str] = None,
    ) -> List[Memory]:
        """混合搜索（向量 + 全文）"""
        vec_results = self.search_vector(query_embedding, top_k * 2, memory_type)
        fts_results = self.search_fulltext(query, top_k * 2, memory_type)

        # 合并结果并重排序
        scores: Dict[str, float] = {}
        memories: Dict[str, Memory] = {}

        for i, mem in enumerate(vec_results):
            score = (1.0 - i / len(vec_results)) * vector_weight
            scores[mem.id] = scores.get(mem.id, 0) + score
            memories[mem.id] = mem

        for i, mem in enumerate(fts_results):
            score = (1.0 - i / len(fts_results)) * (1 - vector_weight)
            scores[mem.id] = scores.get(mem.id, 0) + score
            memories[mem.id] = mem

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return [memories[mid] for mid in sorted_ids[:top_k]]

    def get(self, memory_id: str) -> Optional[Memory]:
        """获取单个记忆"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_memory(row) if row else None

    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.execute("DELETE FROM memories_fts WHERE id = ?", (memory_id,))
        if self.vec_available:
            conn.execute("DELETE FROM memories_vec WHERE id = ?", (memory_id,))
        conn.commit()
        affected = conn.total_changes
        conn.close()
        return affected > 0

    def _row_to_memory(self, row) -> Memory:
        """将数据库行转为 Memory 对象"""
        return Memory(
            id=row['id'],
            content=row['content'],
            memory_type=row['memory_type'],
            importance=row['importance'],
            created_at=datetime.fromisoformat(row['created_at']),
            last_accessed=datetime.fromisoformat(row['last_accessed']),
            access_count=row['access_count'],
            tags=json.loads(row['tags']),
            context=json.loads(row['context']),
            embedding=None,
        )

    def _float_list_to_blob(self, floats: List[float]) -> bytes:
        """将浮点列表转为 blob（用于 sqlite-vec）"""
        import struct
        return struct.pack(f'{len(floats)}f', *floats)

    def _blob_to_float_list(self, blob: bytes) -> List[float]:
        """将 blob 转为浮点列表"""
        import struct
        return list(struct.unpack(f'{len(blob)//4}f', blob))
