"""
Persistent memory system.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

import agent_framework.core.fast_json as json
from agent_framework.core.database import get_db_connection
from agent_framework.memory.backend_registry import resolve_memory_backend
from agent_framework.memory.config import load_config
from agent_framework.memory.long_term_memory import get_long_term_memory
from agent_framework.memory.reme_proxy import ReMeProxyStore
from agent_framework.memory.reme_sidecar import ReMeSidecarClient, ReMeSidecarLauncher

try:
    from agent_framework.vector_db.vector_ops import VectorOps, RUST_AVAILABLE as _rust_available
except Exception:
    VectorOps = None
    _rust_available = False

try:
    from agent_framework.vector_db.vector_ops_jit import JITVectorOps

    _jit_ops = JITVectorOps()
    _use_jit = True
except ImportError:
    _jit_ops = None
    _use_jit = False


_VECTOR_SEARCH_BACKEND = "rust" if _rust_available and VectorOps is not None else ("jit" if _use_jit else "numpy")
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}")
_PROCEDURAL_HINT_RE = re.compile(
    r"(步骤|流程|先|然后|最后|排查|检查|处理|诊断|建议|操作|step\s*\d+|first|then|finally|check|inspect)",
    re.IGNORECASE,
)
_PREFERENCE_HINT_RE = re.compile(
    r"(记住|记下|以后|请用|不要|偏好|喜欢|习惯|总是|优先|记得|remember|prefer|always|never)",
    re.IGNORECASE,
)
_ERROR_HINT_RE = re.compile(
    r"(错误|异常|失败|问题|告警|报警|故障|risk|warning|error|failed|issue|alarm|fault)",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def _tokenize_text(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


@dataclass
class Memory:
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
    scope: str = "global"
    confidence: float = 0.6
    status: str = "active"
    source: str = ""
    retrieval_success: float = 0.0
    last_feedback_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["last_accessed"] = self.last_accessed.isoformat()
        data["last_feedback_at"] = self.last_feedback_at.isoformat() if self.last_feedback_at else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        payload = dict(data)
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["last_accessed"] = datetime.fromisoformat(payload["last_accessed"])
        if payload.get("last_feedback_at"):
            payload["last_feedback_at"] = datetime.fromisoformat(payload["last_feedback_at"])
        return cls(**payload)

    @property
    def scope_path(self) -> List[str]:
        scope_path = list((self.context or {}).get("scope_path") or [])
        if scope_path:
            return [str(item) for item in scope_path if str(item).strip()]
        return [self.scope] if self.scope else ["global"]


class MemoryEncoder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(model_name, local_files_only=True)
            self.dimension = 384
        except Exception:
            self.model = None
            self.dimension = 128

    def encode(self, text: str) -> List[float]:
        if self.model:
            try:
                embedding = self.model.encode(text)
                return embedding.tolist()
            except Exception:
                return self._simple_encode(text)
        return self._simple_encode(text)

    def _simple_encode(self, text: str) -> List[float]:
        features = [0.0] * self.dimension
        words = text.lower().split()
        for i, word in enumerate(words[: self.dimension]):
            features[i] = hash(word) % 1000 / 1000.0
        return features

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.encode(text) for text in texts]


class MemoryStore:
    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = db_path
        self.encoder = MemoryEncoder()
        self.search_backend = _VECTOR_SEARCH_BACKEND
        self._cache_lock = threading.RLock()
        self._cache_dirty = True
        self._row_cache_by_id: Dict[str, Tuple[Any, ...]] = {}
        self._embedding_cache_by_id: Dict[str, List[float]] = {}
        self._candidate_ids_all: List[str] = []
        self._candidate_embeddings_all_py: List[List[float]] = []
        self._candidate_embeddings_all_np: np.ndarray = np.empty((0, 0), dtype=np.float64)
        self._candidate_ids_by_type: Dict[str, List[str]] = {}
        self._candidate_embeddings_by_type_py: Dict[str, List[List[float]]] = {}
        self._candidate_embeddings_by_type_np: Dict[str, np.ndarray] = {}
        Path("data").mkdir(exist_ok=True)
        self._init_database()

    def _init_database(self):
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    importance REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    tags TEXT,
                    context TEXT,
                    embedding TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memories(memory_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON memories(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_last_accessed ON memories(last_accessed)")

    def _generate_memory_id(self, content: str) -> str:
        return hashlib.md5(f"{content}{time.time()}".encode()).hexdigest()

    @staticmethod
    def _ensure_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(context or {})
        payload.setdefault("scope", payload.get("scope") or "global")
        scope_path = payload.get("scope_path") or []
        if isinstance(scope_path, str):
            scope_path = [scope_path]
        payload["scope_path"] = [str(item) for item in scope_path if str(item).strip()]
        if not payload["scope_path"]:
            payload["scope_path"] = [str(payload["scope"])]
        payload.setdefault("feedback", {})
        payload.setdefault("memory_stage", payload.get("memory_stage") or "raw")
        payload["confidence"] = _clamp(_safe_float(payload.get("confidence"), 0.6))
        payload["status"] = str(payload.get("status") or "active")
        payload["source"] = str(payload.get("source") or "")
        payload["retrieval_success"] = _clamp(_safe_float(payload.get("retrieval_success"), 0.0))
        return payload

    @staticmethod
    def _feedback_score(memory: Memory) -> float:
        feedback = dict((memory.context or {}).get("feedback") or {})
        retrieved = int(feedback.get("retrieved", 0) or 0)
        positive = int(feedback.get("positive", 0) or 0)
        negative = int(feedback.get("negative", 0) or 0)
        corrected = int(feedback.get("corrected", 0) or 0)
        return _clamp(0.45 + positive * 0.12 + retrieved * 0.02 - negative * 0.15 - corrected * 0.18, 0.0, 1.0)

    @staticmethod
    def _recency_score(memory: Memory, time_decay_days: float) -> float:
        age_days = max(0.0, (datetime.now() - memory.created_at).total_seconds() / 86400.0)
        last_access_hours = max(0.0, (datetime.now() - memory.last_accessed).total_seconds() / 3600.0)
        age_component = math.exp(-age_days / max(time_decay_days, 1.0))
        access_component = 1.0 / (1.0 + last_access_hours / 24.0)
        return _clamp(age_component * 0.6 + access_component * 0.4, 0.0, 1.0)

    @staticmethod
    def _lexical_score(query_tokens: List[str], content: str, tags: Optional[List[str]] = None) -> float:
        if not query_tokens:
            return 0.0
        haystack_tokens = set(_tokenize_text(content))
        for tag in tags or []:
            haystack_tokens.update(_tokenize_text(str(tag)))
        if not haystack_tokens:
            return 0.0
        overlaps = sum(1 for token in query_tokens if token in haystack_tokens)
        return overlaps / max(len(set(query_tokens)), 1)

    @staticmethod
    def _retrieval_weights(mode: str) -> Dict[str, float]:
        mode = (mode or "balanced").strip().lower()
        if mode == "recent":
            return {"vector": 0.35, "lexical": 0.15, "recency": 0.25, "importance": 0.15, "feedback": 0.10}
        if mode == "lexical":
            return {"vector": 0.25, "lexical": 0.40, "recency": 0.10, "importance": 0.15, "feedback": 0.10}
        if mode == "exploratory":
            return {"vector": 0.45, "lexical": 0.15, "recency": 0.10, "importance": 0.10, "feedback": 0.20}
        return {"vector": 0.52, "lexical": 0.16, "recency": 0.10, "importance": 0.14, "feedback": 0.08}

    @staticmethod
    def _scope_rank(memory: Memory, scopes: Optional[Iterable[str]]) -> Optional[int]:
        if not scopes:
            return 0
        scope_path = memory.scope_path
        for idx, scope in enumerate(scopes):
            if scope in scope_path or scope == memory.scope:
                return idx
        return None

    @staticmethod
    def _memory_matches_scope(memory: Memory, scopes: Optional[Iterable[str]]) -> bool:
        return MemoryStore._scope_rank(memory, scopes) is not None

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if self.search_backend == "rust" and VectorOps is not None:
            return float(VectorOps.cosine_similarity_batch([vec1], vec2)[0])
        a = np.asarray(vec1, dtype=np.float64)
        b = np.asarray(vec2, dtype=np.float64)
        if self.search_backend == "jit" and _use_jit and _jit_ops is not None:
            return float(_jit_ops.cosine_similarity(a, b))
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b + 1e-10))

    def _top_k_numpy(self, vectors_array: np.ndarray, query_vec: np.ndarray, top_k: int) -> List[Tuple[int, float]]:
        if vectors_array.size == 0 or top_k <= 0:
            return []
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        doc_norms = np.linalg.norm(vectors_array, axis=1)
        dot_products = np.dot(vectors_array, query_vec)
        similarities = dot_products / (doc_norms * query_norm + 1e-10)
        if top_k < len(similarities):
            top_indices = np.argpartition(similarities, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
        else:
            top_indices = np.argsort(similarities)[::-1]
        return [(int(idx), float(similarities[idx])) for idx in top_indices]

    def _rank_similarities(
        self,
        embeddings: List[List[float]],
        embeddings_array: np.ndarray,
        query_embedding: List[float],
        top_k: int,
    ) -> List[Tuple[int, float]]:
        limit = min(top_k, len(embeddings))
        if limit <= 0:
            return []
        if self.search_backend == "rust" and VectorOps is not None:
            return [(int(idx), float(score)) for idx, score in VectorOps.top_k_similar(embeddings, query_embedding, limit)]
        query_array = np.asarray(query_embedding, dtype=np.float64)
        if self.search_backend == "jit" and _use_jit and _jit_ops is not None:
            return [(int(idx), float(score)) for idx, score in _jit_ops.top_k_similar(embeddings_array, query_array, limit)]
        return self._top_k_numpy(embeddings_array, query_array, limit)

    def invalidate_cache(self):
        with self._cache_lock:
            self._cache_dirty = True

    def _touch_cached_rows(self, memory_ids: List[str], now_iso: str):
        with self._cache_lock:
            if self._cache_dirty:
                return
            for memory_id in memory_ids:
                row = self._row_cache_by_id.get(memory_id)
                if not row:
                    continue
                updated_row = list(row)
                updated_row[5] = now_iso
                updated_row[6] = int(updated_row[6]) + 1
                self._row_cache_by_id[memory_id] = tuple(updated_row)

    def _rebuild_search_cache(self):
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM memories").fetchall()

        row_cache_by_id: Dict[str, Tuple[Any, ...]] = {}
        embedding_cache_by_id: Dict[str, List[float]] = {}
        candidate_ids_all: List[str] = []
        candidate_embeddings_all_py: List[List[float]] = []
        candidate_ids_by_type: Dict[str, List[str]] = {}
        candidate_embeddings_by_type_py: Dict[str, List[List[float]]] = {}

        for row in rows:
            memory_id = row[0]
            row_cache_by_id[memory_id] = row
            if not row[9]:
                continue
            embedding = json.loads(row[9])
            if not embedding:
                continue
            embedding_list = [float(x) for x in embedding]
            embedding_cache_by_id[memory_id] = embedding_list
            candidate_ids_all.append(memory_id)
            candidate_embeddings_all_py.append(embedding_list)
            memory_type = row[2]
            candidate_ids_by_type.setdefault(memory_type, []).append(memory_id)
            candidate_embeddings_by_type_py.setdefault(memory_type, []).append(embedding_list)

        candidate_embeddings_all_np = (
            np.asarray(candidate_embeddings_all_py, dtype=np.float64)
            if candidate_embeddings_all_py
            else np.empty((0, 0), dtype=np.float64)
        )
        candidate_embeddings_by_type_np = {
            memory_type: (
                np.asarray(embeddings, dtype=np.float64)
                if embeddings
                else np.empty((0, 0), dtype=np.float64)
            )
            for memory_type, embeddings in candidate_embeddings_by_type_py.items()
        }

        with self._cache_lock:
            self._row_cache_by_id = row_cache_by_id
            self._embedding_cache_by_id = embedding_cache_by_id
            self._candidate_ids_all = candidate_ids_all
            self._candidate_embeddings_all_py = candidate_embeddings_all_py
            self._candidate_embeddings_all_np = candidate_embeddings_all_np
            self._candidate_ids_by_type = candidate_ids_by_type
            self._candidate_embeddings_by_type_py = candidate_embeddings_by_type_py
            self._candidate_embeddings_by_type_np = candidate_embeddings_by_type_np
            self._cache_dirty = False

    def _ensure_search_cache(self):
        with self._cache_lock:
            cache_dirty = self._cache_dirty
        if cache_dirty:
            self._rebuild_search_cache()

    def _get_cached_candidates(self, memory_type: Optional[str] = None) -> Tuple[List[str], List[List[float]], np.ndarray]:
        self._ensure_search_cache()
        with self._cache_lock:
            if memory_type:
                return (
                    list(self._candidate_ids_by_type.get(memory_type, [])),
                    list(self._candidate_embeddings_by_type_py.get(memory_type, [])),
                    self._candidate_embeddings_by_type_np.get(memory_type, np.empty((0, 0), dtype=np.float64)),
                )
            return (
                list(self._candidate_ids_all),
                list(self._candidate_embeddings_all_py),
                self._candidate_embeddings_all_np,
            )

    def _upsert_memory(self, memory: Memory) -> str:
        if not memory.id:
            memory.id = self._generate_memory_id(memory.content)

        context = self._ensure_context(memory.context)
        memory.scope = str(context.get("scope") or memory.scope or "global")
        memory.confidence = _clamp(_safe_float(context.get("confidence"), memory.confidence))
        memory.status = str(context.get("status") or memory.status or "active")
        memory.source = str(context.get("source") or memory.source or "")
        memory.retrieval_success = _clamp(_safe_float(context.get("retrieval_success"), memory.retrieval_success))
        if not memory.embedding:
            memory.embedding = self.encoder.encode(memory.content)
        else:
            memory.embedding = [float(x) for x in memory.embedding]

        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memories
                (id, content, memory_type, importance, created_at, last_accessed,
                 access_count, tags, context, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    memory.content,
                    memory.memory_type,
                    float(memory.importance),
                    memory.created_at.isoformat(),
                    memory.last_accessed.isoformat(),
                    int(memory.access_count),
                    json.dumps(list(memory.tags or [])),
                    json.dumps(context),
                    json.dumps(memory.embedding),
                ),
            )

        self.invalidate_cache()
        return memory.id

    def store_memory(self, memory: Memory) -> str:
        return self._upsert_memory(memory)

    def retrieve_memory(self, memory_id: str, touch: bool = True) -> Optional[Memory]:
        self._ensure_search_cache()
        with self._cache_lock:
            row = self._row_cache_by_id.get(memory_id)
            embedding = self._embedding_cache_by_id.get(memory_id)
        if not row:
            with get_db_connection(self.db_path) as conn:
                cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
                row = cursor.fetchone()
                if not row:
                    return None
        if touch:
            now_iso = datetime.now().isoformat()
            with get_db_connection(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE memories
                    SET last_accessed = ?, access_count = access_count + 1
                    WHERE id = ?
                    """,
                    (now_iso, memory_id),
                )
            self._touch_cached_rows([memory_id], now_iso)
        return self._row_to_memory(row, embedding=embedding)

    def list_memories(
        self,
        memory_type: Optional[str] = None,
        limit: int = 200,
        user_id: Optional[str] = None,
        scopes: Optional[Iterable[str]] = None,
    ) -> List[Memory]:
        self._ensure_search_cache()
        with self._cache_lock:
            rows = list(self._row_cache_by_id.values())
            embedding_cache = dict(self._embedding_cache_by_id)
        memories: List[Memory] = []
        requested_types = {memory_type} if memory_type else set()
        for row in rows:
            memory = self._row_to_memory(row, embedding=embedding_cache.get(row[0]))
            if requested_types and memory.memory_type not in requested_types:
                continue
            if user_id:
                memory_user_id = str((memory.context or {}).get("user_id") or "")
                if memory_user_id and memory_user_id != str(user_id):
                    continue
            if scopes and not self._memory_matches_scope(memory, scopes):
                continue
            memories.append(memory)
        memories.sort(key=lambda item: (item.last_accessed, item.importance, item.created_at), reverse=True)
        return memories[: max(1, limit)]

    def update_memory(
        self,
        memory_id: str,
        *,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        tags: Optional[List[str]] = None,
        context_updates: Optional[Dict[str, Any]] = None,
        access_delta: int = 0,
        touch: bool = False,
    ) -> Optional[str]:
        memory = self.retrieve_memory(memory_id, touch=False)
        if not memory:
            return None
        context = self._ensure_context(memory.context)
        if content is not None and content != memory.content:
            memory.content = _normalize_text(content)
            memory.embedding = None
        if importance is not None:
            memory.importance = _clamp(importance)
        if tags is not None:
            memory.tags = list(dict.fromkeys([*(memory.tags or []), *list(tags or [])]))
        if context_updates:
            context.update(context_updates)
            if context_updates.get("scope_path"):
                context["scope_path"] = [str(item) for item in context_updates["scope_path"] if str(item).strip()]
            context = self._ensure_context(context)
        if touch or access_delta:
            memory.last_accessed = datetime.now()
            memory.access_count = max(0, int(memory.access_count) + int(access_delta or 1))
        memory.context = context
        return self._upsert_memory(memory)

    def record_feedback(
        self,
        memory_ids: Iterable[str],
        signal: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = dict(metadata or {})
        now = datetime.now().isoformat()
        for memory_id in memory_ids:
            memory = self.retrieve_memory(str(memory_id), touch=False)
            if not memory:
                continue
            context = self._ensure_context(memory.context)
            feedback = dict(context.get("feedback") or {})
            feedback["last_signal"] = signal
            feedback["last_signal_at"] = now
            feedback["last_metadata"] = metadata
            feedback[signal] = int(feedback.get(signal, 0) or 0) + 1
            context["feedback"] = feedback
            context["retrieval_success"] = _clamp(
                0.45
                + int(feedback.get("positive", 0) or 0) * 0.12
                + int(feedback.get("retrieved", 0) or 0) * 0.02
                - int(feedback.get("negative", 0) or 0) * 0.15
                - int(feedback.get("corrected", 0) or 0) * 0.18
            )
            importance_delta = {
                "retrieved": 0.01,
                "positive": 0.08,
                "negative": -0.10,
                "corrected": -0.14,
            }.get(signal, 0.0)
            rating = metadata.get("rating")
            if rating is not None:
                rating = int(rating)
                if rating >= 4:
                    importance_delta += 0.03
                elif rating <= 2:
                    importance_delta -= 0.04
            self.update_memory(
                memory.id,
                importance=_clamp(memory.importance + importance_delta),
                context_updates=context,
                touch=signal == "retrieved",
            )

    def search_memories(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.3,
        *,
        memory_types: Optional[List[str]] = None,
        scopes: Optional[Iterable[str]] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        boost_by_type: Optional[Dict[str, float]] = None,
        retrieval_mode: str = "balanced",
        time_decay_days: float = 30.0,
        min_importance: float = 0.0,
    ) -> List[Tuple[Memory, float]]:
        query = _normalize_text(query)
        query_tokens = _tokenize_text(query)
        requested_types = {memory_type} if memory_type else set(memory_types or [])
        boost_by_type = dict(boost_by_type or {})
        weights = self._retrieval_weights(retrieval_mode)

        candidate_ids, embeddings, embeddings_array = self._get_cached_candidates()
        with self._cache_lock:
            row_cache_by_id = dict(self._row_cache_by_id)
            embedding_cache_by_id = dict(self._embedding_cache_by_id)

        vector_scores: Dict[str, float] = {}
        if query and embeddings:
            query_embedding = self.encoder.encode(query)
            ranked = self._rank_similarities(
                embeddings,
                embeddings_array,
                query_embedding,
                max(limit * 12, 48),
            )
            for idx, similarity in ranked:
                vector_scores[candidate_ids[idx]] = float(similarity)

        lexical_scores: Dict[str, float] = {}
        candidate_pool: set[str] = set(vector_scores.keys())
        if query_tokens:
            lexical_ranked: List[Tuple[float, str]] = []
            for memory_id, row in row_cache_by_id.items():
                lexical = self._lexical_score(query_tokens, row[1], json.loads(row[7]) if row[7] else [])
                if lexical > 0:
                    lexical_scores[memory_id] = lexical
                    lexical_ranked.append((lexical, memory_id))
            lexical_ranked.sort(reverse=True)
            candidate_pool.update(memory_id for _, memory_id in lexical_ranked[: max(limit * 12, 48)])
        elif not query:
            candidate_pool.update(row_cache_by_id.keys())

        results: List[Tuple[Memory, float]] = []
        for memory_id in candidate_pool:
            row = row_cache_by_id.get(memory_id)
            if not row:
                continue
            memory = self._row_to_memory(row, embedding=embedding_cache_by_id.get(memory_id))
            if requested_types and memory.memory_type not in requested_types:
                continue
            if memory.importance < min_importance:
                continue
            if str(memory.status or "active") not in {"active", "stable"}:
                continue
            if user_id:
                memory_user_id = str((memory.context or {}).get("user_id") or "")
                if memory_user_id and memory_user_id != str(user_id):
                    continue
            if tags and not set(tags).intersection(set(memory.tags or [])):
                continue
            scope_rank = self._scope_rank(memory, scopes)
            if scopes and scope_rank is None:
                continue

            vector_score = vector_scores.get(memory_id, 0.0)
            lexical_score = lexical_scores.get(memory_id, 0.0)
            if query and vector_score < similarity_threshold and lexical_score < max(0.10, similarity_threshold * 0.35):
                continue

            scope_boost = 1.0 if scope_rank is None else max(0.88, 1.18 - scope_rank * 0.05)
            type_boost = boost_by_type.get(memory.memory_type, 1.0)
            recency_score = self._recency_score(memory, time_decay_days)
            feedback_score = self._feedback_score(memory)
            final_score = (
                vector_score * weights["vector"]
                + lexical_score * weights["lexical"]
                + recency_score * weights["recency"]
                + memory.importance * weights["importance"]
                + feedback_score * weights["feedback"]
            ) * scope_boost * type_boost

            if memory.memory_type == "working":
                final_score += 0.06
            if final_score <= 0:
                continue
            results.append((memory, float(final_score)))

        results.sort(
            key=lambda item: (
                item[1],
                item[0].importance,
                item[0].access_count,
                item[0].last_accessed,
            ),
            reverse=True,
        )
        results = results[: max(1, limit)]
        matched_ids = [memory.id for memory, _ in results]
        if matched_ids:
            now = datetime.now().isoformat()
            with get_db_connection(self.db_path) as conn:
                conn.executemany(
                    """
                    UPDATE memories
                    SET last_accessed = ?, access_count = access_count + 1
                    WHERE id = ?
                    """,
                    [(now, mid) for mid in matched_ids],
                )
            self._touch_cached_rows(matched_ids, now)
        return results

    def _row_to_memory(self, row, embedding: Optional[List[float]] = None) -> Memory:
        context = self._ensure_context(json.loads(row[8]) if row[8] else {})
        if embedding is None:
            embedding = json.loads(row[9]) if row[9] else None
        last_feedback_at = context.get("last_feedback_at")
        return Memory(
            id=row[0],
            content=row[1],
            memory_type=row[2],
            importance=row[3],
            created_at=datetime.fromisoformat(row[4]),
            last_accessed=datetime.fromisoformat(row[5]),
            access_count=row[6],
            tags=json.loads(row[7]) if row[7] else [],
            context=context,
            embedding=embedding,
            scope=str(context.get("scope") or "global"),
            confidence=_safe_float(context.get("confidence"), 0.6),
            status=str(context.get("status") or "active"),
            source=str(context.get("source") or ""),
            retrieval_success=_safe_float(context.get("retrieval_success"), 0.0),
            last_feedback_at=datetime.fromisoformat(last_feedback_at) if isinstance(last_feedback_at, str) else None,
        )


class MemoryManager:
    def __init__(self, store: MemoryStore):
        self.store = store
        self.importance_decay_rate = 0.1
        self.max_working_memory = 6
        self.long_term_memory = get_long_term_memory()

    @staticmethod
    def _clip(text: str, max_len: int) -> str:
        text = _normalize_text(text)
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    @staticmethod
    def infer_task_type(query: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        metadata = metadata or {}
        query = _normalize_text(query).lower()
        if not query:
            return "general"
        if re.search(r"(继续|接着|上次|之前|刚才|follow up|continue|previous)", query, re.IGNORECASE):
            return "continuation"
        if re.search(r"(喜欢|偏好|请用|不要|记住|prefer|style|tone)", query, re.IGNORECASE):
            return "preference"
        if re.search(r"(步骤|流程|怎么做|如何处理|how to|procedure|sop)", query, re.IGNORECASE):
            return "procedural"
        if re.search(r"(故障|告警|报警|错误|排查|诊断|root cause|alarm|fault|issue)", query, re.IGNORECASE):
            return "troubleshooting"
        if metadata.get("assistant_profile") == "wind_maintenance":
            return "troubleshooting"
        return "general"

    def build_scope_hierarchy(
        self,
        *,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        metadata = metadata or {}
        scopes: List[str] = []
        if conversation_id:
            scopes.append(f"conversation:{conversation_id}")
        task_id = str(metadata.get("task_id") or metadata.get("workflow_id") or "").strip()
        if task_id:
            scopes.append(f"task:{task_id}")
        asset_context = metadata.get("asset_context") or {}
        farm_name = str(asset_context.get("farm_name") or "").strip()
        turbine_id = str(asset_context.get("turbine_id") or "").strip()
        if farm_name or turbine_id:
            scopes.append(f"asset:{farm_name or 'unknown'}:{turbine_id or 'unknown'}")
        assistant_profile = str(metadata.get("assistant_profile") or "").strip()
        if assistant_profile:
            scopes.append(f"profile:{assistant_profile}")
        if user_id:
            scopes.append(f"user:{user_id}")
        scopes.append("global")
        return list(dict.fromkeys(scopes))

    def build_retrieval_profile(
        self,
        *,
        query: str,
        user_id: Optional[str],
        conversation_id: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        memory_limit: int = 4,
    ) -> Dict[str, Any]:
        task_type = self.infer_task_type(query, metadata)
        scopes = self.build_scope_hierarchy(
            user_id=user_id,
            conversation_id=conversation_id,
            metadata=metadata,
        )
        profile = {
            "task_type": task_type,
            "memory_limit": memory_limit,
            "working_limit": 2,
            "scopes": scopes,
            "retrieval_mode": "balanced",
            "boost_by_type": {"episodic": 1.0, "semantic": 1.0, "procedural": 1.0, "working": 1.0},
            "memory_types": ["semantic", "episodic", "procedural"],
        }
        if task_type == "continuation":
            profile.update(
                {
                    "retrieval_mode": "recent",
                    "working_limit": 3,
                    "boost_by_type": {"working": 1.6, "episodic": 1.2, "semantic": 0.9, "procedural": 0.8},
                    "memory_types": ["working", "episodic", "semantic"],
                }
            )
        elif task_type == "preference":
            profile.update(
                {
                    "retrieval_mode": "balanced",
                    "boost_by_type": {"semantic": 1.5, "working": 1.2, "episodic": 0.8, "procedural": 0.7},
                    "memory_types": ["semantic", "working", "episodic"],
                }
            )
        elif task_type in {"procedural", "troubleshooting"}:
            profile.update(
                {
                    "retrieval_mode": "lexical",
                    "working_limit": 3,
                    "boost_by_type": {"procedural": 1.45, "working": 1.2, "semantic": 1.05, "episodic": 0.9},
                    "memory_types": ["procedural", "working", "semantic", "episodic"],
                }
            )
        return profile

    def _add_memory(
        self,
        content: str,
        memory_type: str,
        context: Dict[str, Any],
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        *,
        source: str = "",
    ) -> str:
        memory = Memory(
            id="",
            content=_normalize_text(content),
            memory_type=memory_type,
            importance=_clamp(importance),
            created_at=datetime.now(),
            last_accessed=datetime.now(),
            access_count=0,
            tags=tags or [],
            context=dict(context or {}),
            scope=str((context or {}).get("scope") or "global"),
            confidence=_safe_float((context or {}).get("confidence"), 0.6),
            status=str((context or {}).get("status") or "active"),
            source=source or str((context or {}).get("source") or ""),
        )
        return self.store.store_memory(memory)

    def add_episodic_memory(
        self,
        content: str,
        context: Dict[str, Any],
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
    ) -> str:
        return self._add_memory(content, "episodic", context, importance, tags, source="episodic")

    def add_semantic_memory(
        self,
        content: str,
        context: Dict[str, Any],
        importance: float = 0.8,
        tags: Optional[List[str]] = None,
    ) -> str:
        return self._add_memory(content, "semantic", context, importance, tags, source="semantic")

    def add_procedural_memory(
        self,
        content: str,
        context: Dict[str, Any],
        importance: float = 0.9,
        tags: Optional[List[str]] = None,
    ) -> str:
        return self._add_memory(content, "procedural", context, importance, tags, source="procedural")

    def add_working_memory(
        self,
        content: str,
        context: Dict[str, Any],
        importance: float = 0.7,
        tags: Optional[List[str]] = None,
    ) -> str:
        return self._add_memory(content, "working", context, importance, tags, source="working")

    def get_working_memories(
        self,
        *,
        query: str,
        user_id: Optional[str],
        conversation_id: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        limit: int = 3,
    ) -> List[Memory]:
        profile = self.build_retrieval_profile(
            query=query,
            user_id=user_id,
            conversation_id=conversation_id,
            metadata=metadata,
            memory_limit=limit,
        )
        results = self.store.search_memories(
            query=query,
            memory_types=["working"],
            limit=limit,
            similarity_threshold=0.05,
            user_id=user_id,
            scopes=profile["scopes"],
            boost_by_type={"working": 1.6},
            retrieval_mode="recent",
        )
        return [memory for memory, _ in results]

    def recall_relevant_memories(self, query: str, context: Dict[str, Any] = None, limit: int = 5) -> List[Memory]:
        context = dict(context or {})
        profile = self.build_retrieval_profile(
            query=query,
            user_id=context.get("user_id"),
            conversation_id=context.get("conversation_id"),
            metadata=context.get("metadata"),
            memory_limit=limit,
        )
        recall_results = self.store.search_memories(
            query=query,
            limit=limit,
            similarity_threshold=0.08,
            user_id=context.get("user_id"),
            scopes=profile["scopes"],
            boost_by_type=profile["boost_by_type"],
            memory_types=profile["memory_types"],
            retrieval_mode=profile["retrieval_mode"],
        )
        return [memory for memory, _ in recall_results]

    def record_retrieval_outcome(
        self,
        memory_ids: Iterable[str],
        outcome: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.store.record_feedback(memory_ids, outcome, metadata=metadata)

    def _maybe_store_candidate(
        self,
        *,
        content: str,
        memory_type: str,
        context: Dict[str, Any],
        importance: float,
        tags: List[str],
        dedupe_threshold: float = 0.86,
    ) -> Optional[str]:
        content = self._clip(content, 420)
        if len(content) < 12:
            return None
        existing = self.store.search_memories(
            query=content,
            memory_type=memory_type,
            limit=1,
            similarity_threshold=max(0.15, dedupe_threshold - 0.2),
            user_id=context.get("user_id"),
            scopes=context.get("scope_path"),
            retrieval_mode="lexical",
        )
        if existing and existing[0][1] >= dedupe_threshold:
            existing_memory = existing[0][0]
            self.store.update_memory(
                existing_memory.id,
                importance=max(existing_memory.importance, importance),
                tags=tags,
                context_updates={"last_deduped_at": datetime.now().isoformat()},
            )
            return existing_memory.id
        return self._add_memory(content, memory_type, context, importance, tags, source=context.get("source", "capture"))

    def _build_turn_context(
        self,
        *,
        conversation_id: str,
        user_id: Optional[str],
        mode: str,
        metadata: Optional[Dict[str, Any]],
        task_type: str,
    ) -> Dict[str, Any]:
        metadata = dict(metadata or {})
        scope_path = self.build_scope_hierarchy(
            user_id=user_id,
            conversation_id=conversation_id,
            metadata=metadata,
        )
        return {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "mode": mode,
            "scope": scope_path[0] if scope_path else "global",
            "scope_path": scope_path,
            "assistant_profile": metadata.get("assistant_profile", "general"),
            "asset_context": metadata.get("asset_context") or {},
            "task_type": task_type,
            "source": "unified_orchestrator",
            "confidence": 0.68,
            "status": "active",
        }

    def update_working_memory(
        self,
        *,
        conversation_id: str,
        user_id: Optional[str],
        user_input: str,
        assistant_reply: str,
        mode: str,
        metadata: Optional[Dict[str, Any]] = None,
        task_type: Optional[str] = None,
    ) -> Optional[str]:
        task_type = task_type or self.infer_task_type(user_input, metadata)
        metadata = dict(metadata or {})
        context = self._build_turn_context(
            conversation_id=conversation_id,
            user_id=user_id,
            mode=mode,
            metadata=metadata,
            task_type=task_type,
        )
        context["working_memory"] = True
        context["working_key"] = f"conversation:{conversation_id}"

        content_lines = [
            f"Task type: {task_type}",
            f"Latest user goal: {self._clip(user_input, 180)}",
            f"Latest assistant conclusion: {self._clip(assistant_reply, 240)}",
        ]
        asset_context = metadata.get("asset_context") or {}
        farm_name = str(asset_context.get("farm_name") or "").strip()
        turbine_id = str(asset_context.get("turbine_id") or "").strip()
        fault_code = str(asset_context.get("fault_code") or "").strip()
        if farm_name or turbine_id or fault_code:
            content_lines.append("Asset context: " + ", ".join(part for part in [farm_name, turbine_id, fault_code] if part))
        content = "\n".join(content_lines)

        existing = [
            memory
            for memory in self.store.list_memories(
                memory_type="working",
                limit=20,
                user_id=user_id,
                scopes=context["scope_path"],
            )
            if (memory.context or {}).get("working_key") == context["working_key"]
        ]
        if existing:
            target = existing[0]
            self.store.update_memory(
                target.id,
                content=content,
                importance=0.72,
                tags=["working", task_type, mode],
                context_updates=context,
                touch=True,
            )
            working_id = target.id
        else:
            working_id = self.add_working_memory(
                content=content,
                context=context,
                importance=0.72,
                tags=["working", task_type, mode],
            )

        extras = existing[1:] if existing else []
        for stale in extras[self.max_working_memory - 1 :]:
            self.store.update_memory(
                stale.id,
                importance=max(0.05, stale.importance * 0.8),
                context_updates={"status": "archived"},
            )
        return working_id

    def capture_turn(
        self,
        *,
        conversation_id: str,
        user_id: Optional[str],
        user_input: str,
        assistant_reply: str,
        mode: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        metadata = dict(metadata or {})
        task_type = self.infer_task_type(user_input, metadata)
        base_context = self._build_turn_context(
            conversation_id=conversation_id,
            user_id=user_id,
            mode=mode,
            metadata=metadata,
            task_type=task_type,
        )
        stored_ids: List[str] = []

        self.update_working_memory(
            conversation_id=conversation_id,
            user_id=user_id,
            user_input=user_input,
            assistant_reply=assistant_reply,
            mode=mode,
            metadata=metadata,
            task_type=task_type,
        )

        explicit_memory = bool(_PREFERENCE_HINT_RE.search(user_input))
        preference_candidate = (
            explicit_memory
            or task_type == "preference"
            or re.search(r"(请以后|以后都|总是|不要再|prefer|don't|always)", user_input, re.IGNORECASE)
        )
        if preference_candidate:
            pref_context = dict(base_context)
            pref_scope_path: List[str] = []
            if user_id:
                pref_scope_path.append(f"user:{user_id}")
            pref_scope_path.extend(base_context["scope_path"])
            pref_context["scope"] = pref_scope_path[0] if pref_scope_path else base_context["scope"]
            pref_context["scope_path"] = list(dict.fromkeys(pref_scope_path))
            pref_context["memory_stage"] = "promoted"
            pref_context["preference"] = True
            memory_id = self._maybe_store_candidate(
                content=f"User durable preference or instruction: {self._clip(user_input, 260)}",
                memory_type="semantic",
                context=pref_context,
                importance=0.86,
                tags=["preference", "user_instruction", task_type],
            )
            if memory_id:
                stored_ids.append(memory_id)
                if user_id:
                    self.long_term_memory.learn_preference(
                        user_id=user_id,
                        category="conversation",
                        key=f"pref_{hashlib.md5(user_input.encode()).hexdigest()[:10]}",
                        value=self._clip(user_input, 240),
                        confidence=0.78,
                    )

        if assistant_reply and (task_type in {"procedural", "troubleshooting"} or _PROCEDURAL_HINT_RE.search(assistant_reply)):
            proc_context = dict(base_context)
            proc_context["memory_stage"] = "promoted"
            proc_context["derived_from"] = "assistant_reply"
            memory_id = self._maybe_store_candidate(
                content=(
                    f"Procedure or diagnostic guidance learned. "
                    f"Question: {self._clip(user_input, 180)} "
                    f"Answer: {self._clip(assistant_reply, 260)}"
                ),
                memory_type="procedural",
                context=proc_context,
                importance=0.82 if mode == "agent" else 0.74,
                tags=["procedure", task_type, mode],
            )
            if memory_id:
                stored_ids.append(memory_id)

        if explicit_memory or len(assistant_reply) > 180 or _ERROR_HINT_RE.search(f"{user_input}\n{assistant_reply}"):
            episodic_context = dict(base_context)
            episodic_context["memory_stage"] = "raw"
            memory_id = self._maybe_store_candidate(
                content=(
                    f"Conversation turn summary. "
                    f"User: {self._clip(user_input, 180)} "
                    f"Assistant: {self._clip(assistant_reply, 220)}"
                ),
                memory_type="episodic",
                context=episodic_context,
                importance=0.72 if mode == "agent" else 0.62,
                tags=["conversation_turn", task_type, mode],
                dedupe_threshold=0.90,
            )
            if memory_id:
                stored_ids.append(memory_id)

        if user_id and metadata.get("asset_context"):
            asset_context = dict(base_context)
            asset_context["memory_stage"] = "promoted"
            memory_id = self._maybe_store_candidate(
                content=(
                    f"Asset task context: {json.dumps(metadata.get('asset_context'), ensure_ascii=False)}. "
                    f"Current request: {self._clip(user_input, 160)}"
                ),
                memory_type="semantic",
                context=asset_context,
                importance=0.70,
                tags=["asset_context", task_type],
            )
            if memory_id:
                stored_ids.append(memory_id)

        self.consolidate_memories(max_age_days=90, min_importance=0.08, max_promotions=8)
        return stored_ids

    def consolidate_memories(
        self,
        max_age_days: int = 90,
        min_importance: float = 0.1,
        max_promotions: int = 12,
    ):
        promoted = 0
        for memory in self.store.list_memories(limit=300):
            if promoted >= max_promotions:
                break
            if memory.memory_type == "working":
                age_days = (datetime.now() - memory.last_accessed).days
                if age_days > 7:
                    self.store.update_memory(
                        memory.id,
                        importance=max(0.05, memory.importance * 0.75),
                        context_updates={"status": "archived"},
                    )
                continue
            context = dict(memory.context or {})
            if memory.memory_type != "episodic":
                continue
            if context.get("memory_stage") == "promoted":
                continue
            if "preference" in (memory.tags or []):
                promoted += 1
                self.store.update_memory(memory.id, context_updates={"memory_stage": "promoted"})
                self._maybe_store_candidate(
                    content=f"Stable user preference: {self._clip(memory.content, 280)}",
                    memory_type="semantic",
                    context={**context, "memory_stage": "promoted"},
                    importance=max(memory.importance, 0.84),
                    tags=list(dict.fromkeys([*(memory.tags or []), "promoted_from_episodic"])),
                )
                continue
            if _PROCEDURAL_HINT_RE.search(memory.content):
                promoted += 1
                self.store.update_memory(memory.id, context_updates={"memory_stage": "promoted"})
                self._maybe_store_candidate(
                    content=f"Learned procedure: {self._clip(memory.content, 280)}",
                    memory_type="procedural",
                    context={**context, "memory_stage": "promoted"},
                    importance=max(memory.importance, 0.78),
                    tags=list(dict.fromkeys([*(memory.tags or []), "promoted_from_episodic"])),
                )

        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        with get_db_connection(self.store.db_path) as conn:
            conn.execute(
                """
                DELETE FROM memories
                WHERE importance < ? AND last_accessed < ? AND memory_type != 'semantic'
                """,
                (min_importance, cutoff),
            )
        self.store.invalidate_cache()

    def get_memory_statistics(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        memories = self.store.list_memories(limit=10000)
        for memory in memories:
            bucket = stats.setdefault(
                memory.memory_type,
                {
                    "count": 0,
                    "avg_importance": 0.0,
                    "avg_access_count": 0.0,
                    "scopes": {},
                    "positive": 0,
                    "negative": 0,
                },
            )
            bucket["count"] += 1
            bucket["avg_importance"] += memory.importance
            bucket["avg_access_count"] += memory.access_count
            scope_name = memory.scope_path[0] if memory.scope_path else memory.scope
            bucket["scopes"][scope_name] = bucket["scopes"].get(scope_name, 0) + 1
            feedback = (memory.context or {}).get("feedback") or {}
            bucket["positive"] += int(feedback.get("positive", 0) or 0)
            bucket["negative"] += int(feedback.get("negative", 0) or 0)
        for bucket in stats.values():
            count = max(1, bucket["count"])
            bucket["avg_importance"] = round(bucket["avg_importance"] / count, 4)
            bucket["avg_access_count"] = round(bucket["avg_access_count"] / count, 2)
        return stats


_memory_store: Optional[MemoryStore] = None
_memory_manager: Optional[MemoryManager] = None
_memory_backend_info: Optional[dict[str, Any]] = None


class _ReMeMemoryManager(MemoryManager):
    def consolidate_memories(
        self,
        max_age_days: int = 90,
        min_importance: float = 0.1,
        max_promotions: int = 12,
    ):
        return None


def get_memory_manager() -> MemoryManager:
    global _memory_store, _memory_manager, _memory_backend_info
    if _memory_manager is None:
        loaded_config = load_config()
        resolution = resolve_memory_backend(loaded_config)
        _memory_backend_info = {
            "requested": resolution.requested,
            "active": resolution.active,
            "fallback": resolution.fallback,
            "reason": resolution.reason,
        }
        if resolution.fallback:
            logger.warning(
                "Memory backend '%s' is unavailable; falling back to local store (%s).",
                resolution.requested,
                resolution.reason,
            )
        if resolution.active == "reme":
            try:
                reme_cfg = dict((loaded_config.get("backend") or {}).get("reme") or {})
                sidecar_cfg = dict(reme_cfg.get("sidecar") or {})
                client = ReMeSidecarClient(
                    base_url=str(sidecar_cfg.get("base_url") or "http://127.0.0.1:8765"),
                    timeout=float(sidecar_cfg.get("request_timeout", 10)),
                )
                launcher = ReMeSidecarLauncher(reme_cfg)
                _memory_store = ReMeProxyStore(client=client, launcher=launcher)
                _memory_manager = _ReMeMemoryManager(_memory_store)
            except Exception as exc:
                logger.warning("Failed to initialize ReMe memory backend, falling back to local store: %s", exc)
                _memory_backend_info = {
                    "requested": resolution.requested,
                    "active": "local",
                    "fallback": True,
                    "reason": f"reme_init_failed:{type(exc).__name__}:{exc}",
                }
                _memory_store = MemoryStore()
                _memory_manager = MemoryManager(_memory_store)
        else:
            _memory_store = MemoryStore()
            _memory_manager = MemoryManager(_memory_store)
        setattr(_memory_manager, "backend_info", dict(_memory_backend_info))
    return _memory_manager


def get_memory_backend_info() -> dict[str, Any]:
    global _memory_backend_info
    if _memory_backend_info is None:
        resolution = resolve_memory_backend(load_config())
        _memory_backend_info = {
            "requested": resolution.requested,
            "active": resolution.active,
            "fallback": resolution.fallback,
            "reason": resolution.reason,
        }
    return dict(_memory_backend_info)


class FileMemoryLayer:
    """
    File memory layer.

    Directory layout:
      data/memory/
        MEMORY.md
        daily/
          2026-03-15.md
    """

    def __init__(self, base_dir: str = "data/memory"):
        self.base_dir = Path(base_dir)
        self.daily_dir = self.base_dir / "daily"
        self.memory_md_path = self.base_dir / "MEMORY.md"
        self._lock = threading.Lock()
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        if not self.memory_md_path.exists():
            self._write_file(self.memory_md_path, "# Long-Term Memory\n\n> Managed by the memory system.\n")

    def append_daily_note(self, content: str, note_date: date | None = None) -> str:
        note_date = note_date or date.today()
        file_path = self.daily_dir / f"{note_date.isoformat()}.md"
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"\n- [{timestamp}] {content}\n"
        with self._lock:
            if not file_path.exists():
                header = f"# Daily Notes {note_date.isoformat()}\n"
                self._write_file(file_path, header)
            self._append_file(file_path, entry)
        return str(file_path)

    def load_daily_notes(self, days: int = 2) -> str:
        today = date.today()
        parts = []
        for offset in range(days):
            current_day = today - timedelta(days=offset)
            file_path = self.daily_dir / f"{current_day.isoformat()}.md"
            if file_path.exists():
                parts.append(self._read_file(file_path))
        return "\n---\n".join(parts) if parts else ""

    def list_daily_files(self) -> List[str]:
        files = sorted(self.daily_dir.glob("*.md"), reverse=True)
        return [file_path.stem for file_path in files]

    def load_daily_note_by_date(self, note_date: str) -> str:
        file_path = self.daily_dir / f"{note_date}.md"
        if file_path.exists():
            return self._read_file(file_path)
        return ""

    def get_daily_notes_for_consolidation(self, older_than_days: int = 7) -> List[Tuple[str, str]]:
        cutoff = date.today() - timedelta(days=older_than_days)
        results = []
        for file_path in sorted(self.daily_dir.glob("*.md")):
            try:
                file_date = date.fromisoformat(file_path.stem)
                if file_date < cutoff:
                    results.append((file_path.stem, self._read_file(file_path)))
            except ValueError:
                continue
        return results

    def load_memory_md(self) -> str:
        if self.memory_md_path.exists():
            return self._read_file(self.memory_md_path)
        return ""

    def update_memory_md(self, section: str, content: str) -> None:
        with self._lock:
            current = self.load_memory_md()
            section_header = f"## {section}"
            if section_header in current:
                lines = current.split("\n")
                new_lines: List[str] = []
                in_section = False
                appended = False
                for line in lines:
                    if line.strip() == section_header:
                        in_section = True
                    elif in_section and line.startswith("## "):
                        new_lines.append(content)
                        new_lines.append("")
                        in_section = False
                        appended = True
                    new_lines.append(line)
                if in_section and not appended:
                    new_lines.append(content)
                    new_lines.append("")
                self._write_file(self.memory_md_path, "\n".join(new_lines))
            else:
                addition = f"\n{section_header}\n\n{content}\n"
                self._append_file(self.memory_md_path, addition)

    def replace_memory_md(self, full_content: str) -> None:
        with self._lock:
            self._write_file(self.memory_md_path, full_content)

    def _read_file(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _write_file(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def _append_file(self, path: Path, content: str) -> None:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(content)


_file_memory_layer: Optional[FileMemoryLayer] = None


def get_file_memory_layer() -> FileMemoryLayer:
    global _file_memory_layer
    if _file_memory_layer is None:
        _file_memory_layer = FileMemoryLayer()
    return _file_memory_layer
