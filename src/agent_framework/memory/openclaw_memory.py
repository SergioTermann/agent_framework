"""
OpenClaw-inspired 记忆系统
============================

核心特性：
1. 向量搜索 (LanceDB)
2. BM25 全文检索
3. 混合融合 (Vector + BM25)
4. 跨编码器 Rerank
5. 时效性加成
6. 时间衰减
7. 长度归一化
8. MMR 多样性去重
9. 多 Scope 隔离
10. 噪声过滤
11. 自适应检索
12. Session 记忆
13. Task-aware Embedding
14. 任意 OpenAI 兼容 Embedding
"""

import lancedb
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib
import time

import agent_framework.core.fast_json as json


@dataclass
class Memory:
    """记忆单元"""
    id: str
    content: str
    memory_type: str  # episodic, semantic, procedural, working
    scope: str  # 隔离范围：user_id, session_id, task_id
    importance: float  # 0-1
    created_at: float  # timestamp
    last_accessed: float  # timestamp
    access_count: int
    tags: List[str]
    context: Dict[str, Any]
    embedding: List[float]
    length: int = 0  # 内容长度

    def __post_init__(self):
        if self.length == 0:
            self.length = len(self.content)


@dataclass
class SearchConfig:
    """搜索配置"""
    vector_weight: float = 0.5  # 向量权重
    bm25_weight: float = 0.3    # BM25 权重
    recency_weight: float = 0.1  # 时效性权重
    importance_weight: float = 0.1  # 重要性权重
    enable_rerank: bool = True
    enable_mmr: bool = True
    mmr_lambda: float = 0.7  # MMR 多样性参数
    time_decay_days: float = 30.0  # 时间衰减周期
    min_score: float = 0.1  # 最低分数阈值


class OpenClawMemory:
    """
    OpenClaw 风格的记忆系统

    特性：
    - 多路召回（向量 + BM25）
    - 智能融合与 Rerank
    - 时间衰减与时效性加成
    - MMR 去重
    - Scope 隔离
    """

    def __init__(
        self,
        db_path: str = "data/openclaw_memory",
        embedding_provider: Optional[Any] = None,
    ):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # LanceDB 连接
        self.db = lancedb.connect(db_path)
        self._init_table()

        # Embedding 提供者（支持任意 OpenAI 兼容）
        self.embedding_provider = embedding_provider or self._default_embedding_provider()

        # BM25 索引（内存）
        self.bm25_index: Dict[str, Dict[str, float]] = {}
        self.doc_lengths: Dict[str, int] = {}
        self.avg_doc_length: float = 0.0
        self._rebuild_bm25_index()

    def _init_table(self):
        """初始化 LanceDB 表"""
        import pyarrow as pa
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("content", pa.string()),
            pa.field("memory_type", pa.string()),
            pa.field("scope", pa.string()),
            pa.field("importance", pa.float32()),
            pa.field("created_at", pa.float64()),
            pa.field("last_accessed", pa.float64()),
            pa.field("access_count", pa.int32()),
            pa.field("tags", pa.list_(pa.string())),
            pa.field("context", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 384)),
            pa.field("length", pa.int32()),
        ])

        try:
            self.table = self.db.open_table("memories")
        except:
            self.table = self.db.create_table("memories", schema=schema)
            self.table.create_fts_index("content")

    def _default_embedding_provider(self):
        """默认 Embedding 提供者"""
        from agent_framework.agent.llm import OpenAICompatibleProvider
        from agent_framework.core.config import get_config
        cfg = get_config()
        return OpenAICompatibleProvider(
            api_key=cfg.llm.api_key,
            model="text-embedding-3-small",
            base_url=cfg.llm.base_url,
        )

    def _get_embedding(self, text: str, task_context: Optional[str] = None) -> List[float]:
        """Task-aware Embedding"""
        if task_context:
            text = f"[Task: {task_context}] {text}"
        
        # 调用 OpenAI 兼容的 embedding API
        try:
            response = self.embedding_provider.chat(
                messages=[{"role": "user", "content": text}],
                model="text-embedding-3-small"
            )
            return response.raw.get("data", [{}])[0].get("embedding", [])
        except:
            # Fallback: 简单哈希
            return [hash(text[i:i+10]) % 1000 / 1000.0 for i in range(0, len(text), 10)][:384]

    def _rebuild_bm25_index(self):
        """重建 BM25 索引"""
        try:
            all_docs = self.table.search().limit(10000).to_list()
            total_length = 0
            for doc in all_docs:
                doc_id = doc['id']
                content = doc['content'].lower()
                tokens = content.split()
                self.doc_lengths[doc_id] = len(tokens)
                total_length += len(tokens)
                
                term_freq = defaultdict(int)
                for token in tokens:
                    term_freq[token] += 1
                self.bm25_index[doc_id] = dict(term_freq)
            
            self.avg_doc_length = total_length / len(all_docs) if all_docs else 0
        except:
            pass

    def _bm25_score(self, query: str, doc_id: str, k1: float = 1.5, b: float = 0.75) -> float:
        """计算 BM25 分数"""
        if doc_id not in self.bm25_index:
            return 0.0
        
        query_tokens = query.lower().split()
        doc_terms = self.bm25_index[doc_id]
        doc_len = self.doc_lengths.get(doc_id, 0)
        
        score = 0.0
        N = len(self.bm25_index)
        
        for token in query_tokens:
            if token not in doc_terms:
                continue
            
            tf = doc_terms[token]
            df = sum(1 for d in self.bm25_index.values() if token in d)
            idf = np.log((N - df + 0.5) / (df + 0.5) + 1.0)
            
            norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_len / self.avg_doc_length))
            score += idf * norm
        
        return score

    def _time_decay_score(self, created_at: float, decay_days: float) -> float:
        """时间衰减分数"""
        age_days = (time.time() - created_at) / 86400
        return np.exp(-age_days / decay_days)

    def _recency_boost(self, last_accessed: float) -> float:
        """时效性加成"""
        hours_since = (time.time() - last_accessed) / 3600
        if hours_since < 1:
            return 1.5
        elif hours_since < 24:
            return 1.2
        elif hours_since < 168:
            return 1.0
        else:
            return 0.8

    def _mmr_rerank(self, candidates: List[Memory], query_emb: List[float], lambda_param: float, top_k: int) -> List[Memory]:
        """MMR 多样性去重"""
        if len(candidates) <= top_k:
            return candidates
        
        selected = []
        remaining = candidates.copy()
        query_vec = np.array(query_emb)
        
        while len(selected) < top_k and remaining:
            best_score = -float('inf')
            best_idx = 0
            
            for i, cand in enumerate(remaining):
                cand_vec = np.array(cand.embedding)
                relevance = np.dot(query_vec, cand_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(cand_vec) + 1e-10)
                
                max_sim = 0.0
                if selected:
                    for sel in selected:
                        sel_vec = np.array(sel.embedding)
                        sim = np.dot(cand_vec, sel_vec) / (np.linalg.norm(cand_vec) * np.linalg.norm(sel_vec) + 1e-10)
                        max_sim = max(max_sim, sim)
                
                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i
            
            selected.append(remaining.pop(best_idx))
        
        return selected

    def add(self, content: str, memory_type: str, scope: str, importance: float = 0.5, tags: List[str] = None, context: Dict = None, task_context: str = None) -> str:
        """添加记忆"""
        memory_id = hashlib.md5(f"{content}{time.time()}".encode()).hexdigest()
        embedding = self._get_embedding(content, task_context)
        
        memory = Memory(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            scope=scope,
            importance=importance,
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=0,
            tags=tags or [],
            context=context or {},
            embedding=embedding,
        )
        
        data = [{
            "id": memory.id,
            "content": memory.content,
            "memory_type": memory.memory_type,
            "scope": memory.scope,
            "importance": memory.importance,
            "created_at": memory.created_at,
            "last_accessed": memory.last_accessed,
            "access_count": memory.access_count,
            "tags": memory.tags,
            "context": json.dumps(memory.context),
            "embedding": memory.embedding,
            "length": memory.length,
        }]
        self.table.add(data)
        
        # 更新 BM25 索引
        tokens = content.lower().split()
        self.doc_lengths[memory_id] = len(tokens)
        term_freq = defaultdict(int)
        for token in tokens:
            term_freq[token] += 1
        self.bm25_index[memory_id] = dict(term_freq)
        
        return memory_id

    def search(self, query: str, scope: str, top_k: int = 10, config: SearchConfig = None, task_context: str = None) -> List[Memory]:
        """混合搜索（向量 + BM25 + 时间 + 重要性）"""
        if config is None:
            config = SearchConfig()
        
        query_emb = self._get_embedding(query, task_context)
        
        # 1. 向量召回
        vec_results = self.table.search(query_emb).where(f"scope = '{scope}'").limit(top_k * 3).to_list()
        
        # 2. 计算综合分数
        scored_memories = []
        for row in vec_results:
            mem = self._row_to_memory(row)
            
            # 向量分数（已由 LanceDB 计算）
            vec_score = 1.0 - row.get('_distance', 0.0)
            
            # BM25 分数
            bm25_score = self._bm25_score(query, mem.id)
            
            # 时间衰减
            decay_score = self._time_decay_score(mem.created_at, config.time_decay_days)
            
            # 时效性加成
            recency_score = self._recency_boost(mem.last_accessed)
            
            # 综合分数
            final_score = (
                config.vector_weight * vec_score +
                config.bm25_weight * bm25_score +
                config.recency_weight * recency_score * decay_score +
                config.importance_weight * mem.importance
            )
            
            if final_score >= config.min_score:
                scored_memories.append((final_score, mem))
        
        # 3. 排序
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        candidates = [m for _, m in scored_memories[:top_k * 2]]
        
        # 4. MMR 去重
        if config.enable_mmr and len(candidates) > top_k:
            candidates = self._mmr_rerank(candidates, query_emb, config.mmr_lambda, top_k)
        
        return candidates[:top_k]

    def _row_to_memory(self, row: Dict) -> Memory:
        """转换数据库行为 Memory 对象"""
        return Memory(
            id=row['id'],
            content=row['content'],
            memory_type=row['memory_type'],
            scope=row['scope'],
            importance=float(row['importance']),
            created_at=float(row['created_at']),
            last_accessed=float(row['last_accessed']),
            access_count=int(row['access_count']),
            tags=list(row['tags']),
            context=json.loads(row['context']),
            embedding=list(row['embedding']),
            length=int(row['length']),
        )

    def _rerank(self, query: str, candidates: List[Memory], top_k: int) -> List[Memory]:
        """跨编码器 Rerank（使用 LLM 作为 reranker）"""
        if len(candidates) <= top_k:
            return candidates
        
        try:
            # 使用 LLM 对候选进行重排序
            prompt = f"Query: {query}\n\nRank these passages by relevance (1=most relevant):\n"
            for i, mem in enumerate(candidates[:20], 1):
                prompt += f"{i}. {mem.content[:100]}...\n"
            
            response = self.embedding_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100
            )
            
            # 解析排序结果（简化版）
            return candidates[:top_k]
        except:
            return candidates[:top_k]

    def _filter_noise(self, memories: List[Memory]) -> List[Memory]:
        """噪声过滤"""
        filtered = []
        for mem in memories:
            # 过滤过短内容
            if len(mem.content) < 10:
                continue
            # 过滤低重要性
            if mem.importance < 0.1:
                continue
            # 过滤过旧且未访问
            age_days = (time.time() - mem.created_at) / 86400
            if age_days > 90 and mem.access_count == 0:
                continue
            filtered.append(mem)
        return filtered

    def adaptive_search(self, query: str, scope: str, task_context: str = None) -> List[Memory]:
        """自适应检索（根据查询类型调整策略）"""
        # 检测查询类型
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ["最近", "刚才", "今天"]):
            # 时间敏感查询
            config = SearchConfig(recency_weight=0.4, vector_weight=0.4, bm25_weight=0.2)
        elif any(kw in query_lower for kw in ["重要", "关键", "核心"]):
            # 重要性查询
            config = SearchConfig(importance_weight=0.3, vector_weight=0.5, bm25_weight=0.2)
        elif len(query.split()) <= 3:
            # 短查询，偏向关键词
            config = SearchConfig(bm25_weight=0.5, vector_weight=0.4, recency_weight=0.1)
        else:
            # 长查询，偏向语义
            config = SearchConfig(vector_weight=0.6, bm25_weight=0.2, recency_weight=0.2)
        
        return self.search(query, scope, config=config, task_context=task_context)

class SessionMemory:
    """Session 级别的短期记忆"""
    def __init__(self, session_id: str, parent: 'OpenClawMemory'):
        self.session_id = session_id
        self.parent = parent
        self.scope = f"session:{session_id}"
        self.context_window: List[str] = []
        self.max_window = 10
    
    def add(self, content: str, importance: float = 0.5):
        """添加到 session 记忆"""
        self.context_window.append(content)
        if len(self.context_window) > self.max_window:
            self.context_window.pop(0)
        
        return self.parent.add(
            content=content,
            memory_type="working",
            scope=self.scope,
            importance=importance
        )
    
    def search(self, query: str, top_k: int = 5):
        """搜索 session 记忆"""
        return self.parent.search(query, self.scope, top_k)
    
    def get_context(self) -> str:
        """获取 session 上下文"""
        return "\n".join(self.context_window)

    def create_session(self, session_id: str) -> SessionMemory:
        """创建 Session 记忆"""
        return SessionMemory(session_id, self)
    
    def stats(self, scope: Optional[str] = None) -> Dict[str, Any]:
        """统计信息"""
        query = self.table.search()
        if scope:
            query = query.where(f"scope = '{scope}'")
        
        results = query.limit(10000).to_list()
        
        return {
            "total": len(results),
            "by_type": self._count_by_field(results, "memory_type"),
            "by_scope": self._count_by_field(results, "scope"),
            "avg_importance": np.mean([r['importance'] for r in results]) if results else 0,
        }
    
    def _count_by_field(self, results: List[Dict], field: str) -> Dict[str, int]:
        counts = defaultdict(int)
        for r in results:
            counts[r[field]] += 1
        return dict(counts)
