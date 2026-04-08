"""
LanceDB 记忆存储 - 零配置向量数据库
======================================

优势：
- 单文件存储，无需部署
- 原生向量搜索 + 全文检索
- Apache Arrow 格式，高性能
- 自动索引管理
"""

import lancedb
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
import pyarrow as pa


@dataclass
class Memory:
    """记忆单元"""
    id: str
    content: str
    memory_type: str
    importance: float
    created_at: str
    last_accessed: str
    access_count: int
    tags: List[str]
    context: Dict[str, Any]
    embedding: List[float]

    def to_dict(self) -> Dict:
        return asdict(self)


class LanceMemoryStore:
    """
    基于 LanceDB 的记忆存储

    特性：
    - 向量相似度搜索（原生支持）
    - 全文检索（FTS）
    - 混合查询（向量 + 关键词）
    - 自动索引优化
    """

    def __init__(self, db_path: str = "data/lance_memory"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 连接 LanceDB
        self.db = lancedb.connect(db_path)

        # 创建或打开表
        self._init_table()

    def _init_table(self):
        """初始化表结构"""
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("content", pa.string()),
            pa.field("memory_type", pa.string()),
            pa.field("importance", pa.float32()),
            pa.field("created_at", pa.string()),
            pa.field("last_accessed", pa.string()),
            pa.field("access_count", pa.int32()),
            pa.field("tags", pa.list_(pa.string())),
            pa.field("context", pa.string()),  # JSON string
            pa.field("embedding", pa.list_(pa.float32(), 384)),  # 384 维向量
        ])

        try:
            self.table = self.db.open_table("memories")
        except:
            # 表不存在，创建空表
            self.table = self.db.create_table("memories", schema=schema)
            # 创建 FTS 索引
            self.table.create_fts_index("content")

    def add(self, memory: Memory) -> None:
        """添加记忆"""
        import json
        data = [{
            "id": memory.id,
            "content": memory.content,
            "memory_type": memory.memory_type,
            "importance": memory.importance,
            "created_at": memory.created_at,
            "last_accessed": memory.last_accessed,
            "access_count": memory.access_count,
            "tags": memory.tags,
            "context": json.dumps(memory.context, ensure_ascii=False),
            "embedding": memory.embedding,
        }]
        self.table.add(data)

    def search_vector(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        memory_type: Optional[str] = None,
    ) -> List[Memory]:
        """向量相似度搜索"""
        query = self.table.search(query_embedding).limit(top_k)
        
        if memory_type:
            query = query.where(f"memory_type = '{memory_type}'")
        
        results = query.to_list()
        return [self._row_to_memory(row) for row in results]

    def search_fulltext(
        self,
        query: str,
        top_k: int = 10,
        memory_type: Optional[str] = None,
    ) -> List[Memory]:
        """全文搜索（FTS）"""
        search = self.table.search(query, query_type="fts").limit(top_k)
        
        if memory_type:
            search = search.where(f"memory_type = '{memory_type}'")
        
        results = search.to_list()
        return [self._row_to_memory(row) for row in results]

    def search_hybrid(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        memory_type: Optional[str] = None,
    ) -> List[Memory]:
        """混合搜索（向量 + 全文）- LanceDB 原生支持"""
        search = self.table.search(query_embedding, query_type="hybrid").limit(top_k)
        
        if memory_type:
            search = search.where(f"memory_type = '{memory_type}'")
        
        results = search.to_list()
        return [self._row_to_memory(row) for row in results]

    def get(self, memory_id: str) -> Optional[Memory]:
        """获取单个记忆"""
        results = self.table.search().where(f"id = '{memory_id}'").limit(1).to_list()
        return self._row_to_memory(results[0]) if results else None

    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        self.table.delete(f"id = '{memory_id}'")
        return True

    def _row_to_memory(self, row: Dict) -> Memory:
        """将 LanceDB 行转为 Memory 对象"""
        import json
        return Memory(
            id=row['id'],
            content=row['content'],
            memory_type=row['memory_type'],
            importance=float(row['importance']),
            created_at=row['created_at'],
            last_accessed=row['last_accessed'],
            access_count=int(row['access_count']),
            tags=list(row['tags']),
            context=json.loads(row['context']),
            embedding=list(row['embedding']),
        )
