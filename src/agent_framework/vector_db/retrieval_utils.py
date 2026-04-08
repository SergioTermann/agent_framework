"""
RAG 检索共享工具
================

提取 reranker / rag / knowledge_base 三处重复的分词、停用词、
查询扩展与查询分类逻辑，统一维护。

当 Rust retrieval_core 可用时，tokenize 自动委托给 Rust 实现。
"""

from __future__ import annotations

import re
from enum import Enum
from functools import lru_cache
from typing import Dict, List, Tuple

# ─── Rust 加速（可选）────────────────────────────────────────────────────────

try:
    from agent_framework.vector_db.retrieval_core_ops import rust_tokenize, RUST_RETRIEVAL_AVAILABLE
except ImportError:
    rust_tokenize = None
    RUST_RETRIEVAL_AVAILABLE = False

# ─── 停用词 ──────────────────────────────────────────────────────────────────

STOPWORDS: frozenset = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "with",
    "what", "when", "where", "who", "why",
})

# ─── 查询扩展词典（27 组同义词，取 reranker 完整版本）────────────────────────

QUERY_EXPANSION_MAP: Dict[str, List[str]] = {
    "gearbox": ["齿轮箱", "gear box", "传动箱"],
    "齿轮箱": ["gearbox", "gear box"],
    "temperature": ["温度", "过温", "发热"],
    "温度": ["temperature", "overheat", "hot"],
    "alarm": ["告警", "报警", "异常", "fault"],
    "告警": ["alarm", "fault", "warning"],
    "lubrication": ["润滑", "润滑油", "油位", "lubricant", "oil"],
    "润滑": ["lubrication", "lubricant", "oil"],
    "oil pump": ["油泵", "pump"],
    "油泵": ["oil pump", "pump"],
    "filter": ["过滤器", "滤芯"],
    "过滤器": ["filter"],
    "radiator": ["散热器", "cooler", "冷却器"],
    "散热器": ["radiator", "cooler"],
    "bearing": ["轴承"],
    "轴承": ["bearing"],
    "pitch": ["变桨"],
    "变桨": ["pitch"],
    "yaw": ["偏航"],
    "偏航": ["yaw"],
    "converter": ["变流器"],
    "变流器": ["converter"],
    "generator": ["发电机"],
    "发电机": ["generator"],
    "vibration": ["振动", "震动"],
    "振动": ["vibration"],
    "trip": ["停机", "跳闸", "shutdown"],
    "停机": ["trip", "shutdown"],
    "fault": ["故障", "异常"],
    "故障": ["fault", "failure", "abnormal"],
}

# ─── 文本归一化 ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=8192)
def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()

# ─── 分词 ────────────────────────────────────────────────────────────────────

def _tokenize_python(text: str, include_numbers: bool = False) -> Tuple[str, ...]:
    """纯 Python 分词实现"""
    text = (text or "").strip()
    if not text:
        return ()

    normalized = normalize_text(text)
    tokens: List[str] = []

    if include_numbers:
        tokens.extend(
            token
            for token in re.findall(r"[a-z0-9_]+", normalized)
            if len(token) > 1 and token not in STOPWORDS
        )
    else:
        tokens.extend(
            token
            for token in re.findall(r"[a-z_]+", normalized)
            if len(token) > 1 and token not in STOPWORDS
        )

    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in chinese_runs:
        tokens.extend(run)  # str is iterable over chars
        if len(run) >= 2:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))

    if include_numbers:
        existing = set(tokens)
        for num in re.findall(r"\d+", text):
            if num not in existing:
                tokens.append(num)
                existing.add(num)

    return tuple(tokens)


@lru_cache(maxsize=16384)
def tokenize(text: str, *, include_numbers: bool = False) -> Tuple[str, ...]:
    """分词：Rust 可用时委托给 Rust，否则回退到 Python。

    结果被 lru_cache 缓存，Rust 仅在 cache miss 时调用。
    """
    if RUST_RETRIEVAL_AVAILABLE and rust_tokenize is not None:
        result = rust_tokenize(text, include_numbers)
        if result is not None:
            return tuple(result)
    return _tokenize_python(text, include_numbers)

# ─── 查询扩展 ────────────────────────────────────────────────────────────────

# 预缓存 trigger/synonym 的 tokens 和归一化形式（模块初始化时一次性构建）
def _build_expansion_cache():
    """构建查询扩展预计算缓存，避免每次查询重复 tokenize/normalize"""
    cache = []
    for trigger, synonyms in QUERY_EXPANSION_MAP.items():
        trigger_normalized = normalize_text(trigger)
        trigger_token_set = frozenset(tokenize(trigger))
        trigger_token_set_num = frozenset(tokenize(trigger, include_numbers=True))
        synonym_tokens = [tokenize(s) for s in synonyms]
        synonym_tokens_num = [tokenize(s, include_numbers=True) for s in synonyms]
        cache.append((
            trigger_normalized,
            trigger_token_set,
            trigger_token_set_num,
            synonym_tokens,
            synonym_tokens_num,
        ))
    return tuple(cache)

_EXPANSION_CACHE = _build_expansion_cache()


@lru_cache(maxsize=2048)
def expand_query_tokens(query: str, *, include_numbers: bool = False) -> Tuple[str, ...]:
    base_tokens = tokenize(query, include_numbers=include_numbers)
    normalized_query = normalize_text(query)
    base_token_set = set(base_tokens)
    expanded: List[str] = list(base_tokens)

    for (
        trigger_normalized,
        trigger_token_set,
        trigger_token_set_num,
        synonym_tokens,
        synonym_tokens_num,
    ) in _EXPANSION_CACHE:
        t_set = trigger_token_set_num if include_numbers else trigger_token_set
        s_list = synonym_tokens_num if include_numbers else synonym_tokens
        if (
            trigger_normalized in normalized_query
            or (t_set and not t_set.isdisjoint(base_token_set))
        ):
            for s_tokens in s_list:
                expanded.extend(s_tokens)

    seen: set = set()
    deduped: List[str] = []
    for token in expanded:
        if token and token not in seen:
            seen.add(token)
            deduped.append(token)
    return tuple(deduped)

# ─── 查询分类 ────────────────────────────────────────────────────────────────

class QueryType(Enum):
    KEYWORD = "keyword"
    QUESTION = "question"
    HYBRID = "hybrid"


_QUESTION_STARTERS = re.compile(
    r"^(what|how|why|when|where|who|which|can|could|would|should|is|are|do|does|did)\b",
    re.IGNORECASE,
)
_CHINESE_QUESTION_WORDS = re.compile(
    r"(什么|怎么|为什么|哪里|哪个|如何|是否|能否|多少|几个|谁)",
)


def classify_query(query: str) -> QueryType:
    query = (query or "").strip()
    if not query:
        return QueryType.KEYWORD

    if "?" in query or "？" in query:
        return QueryType.QUESTION

    if _QUESTION_STARTERS.search(query):
        return QueryType.QUESTION

    if _CHINESE_QUESTION_WORDS.search(query):
        return QueryType.QUESTION

    # Count "word-level" units: English words + Chinese characters
    # (bigrams from tokenizer are expansion artifacts, not separate concepts)
    normalized = normalize_text(query)
    english_words = [
        w for w in re.findall(r"[a-z]+", normalized)
        if len(w) > 1 and w not in STOPWORDS
    ]
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", query)
    word_count = len(english_words) + len(chinese_chars)

    if word_count <= 3:
        return QueryType.KEYWORD

    return QueryType.HYBRID


def get_retrieval_weights(query_type: QueryType) -> Dict[str, float]:
    if query_type == QueryType.KEYWORD:
        return {"lexical": 0.80, "vector": 0.20}
    elif query_type == QueryType.QUESTION:
        return {"lexical": 0.45, "vector": 0.55}
    else:
        return {"lexical": 0.60, "vector": 0.40}
