"""
轻量级 RAG reranker
==================

不依赖外部模型，提供更接近 cross-encoder 行为的启发式重排：
- 查询覆盖率
- 精确短语命中
- 标题/小节命中
- 命中片段优先
- 词项邻近度
- 顺序一致性
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from agent_framework.vector_db.retrieval_utils import normalize_text, tokenize, expand_query_tokens


class LightweightReranker:

    @staticmethod
    def _bounded(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _coverage_score(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0
        query_freq = Counter(query_tokens)
        doc_freq = Counter(doc_tokens)
        overlap = sum(min(freq, doc_freq.get(token, 0)) for token, freq in query_freq.items())
        if overlap <= 0:
            return 0.0
        coverage = overlap / max(1, sum(query_freq.values()))
        unique_coverage = len(query_freq.keys() & doc_freq.keys()) / max(1, len(query_freq))
        density = overlap / max(1, len(doc_tokens))
        return self._bounded(0.55 * coverage + 0.25 * unique_coverage + 0.20 * min(1.0, density * 10))

    def _phrase_score(self, query: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> float:
        normalized_query = normalize_text(query)
        normalized_text = normalize_text(text)
        if not normalized_query or not normalized_text:
            return 0.0

        score = 0.0
        if normalized_query in normalized_text:
            score += 1.0

        metadata = metadata or {}
        for field, weight in (("doc_name", 0.45), ("section_title", 0.55)):
            field_text = normalize_text(metadata.get(field, ""))
            if normalized_query and field_text and normalized_query in field_text:
                score += weight

        return self._bounded(score)

    def _proximity_score(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        if len(query_tokens) < 2 or len(doc_tokens) < 2:
            return 0.0

        positions: Dict[str, List[int]] = {}
        query_set = set(query_tokens)
        for idx, token in enumerate(doc_tokens):
            if token in query_set:
                positions.setdefault(token, []).append(idx)

        if len(positions) < 2:
            return 0.0

        flat_positions = sorted(pos for token_positions in positions.values() for pos in token_positions)
        if len(flat_positions) < 2:
            return 0.0

        min_gap = min(
            max(0, flat_positions[i + 1] - flat_positions[i] - 1)
            for i in range(len(flat_positions) - 1)
        )
        span_bonus = 1.0 / (1.0 + min_gap)
        distinct_ratio = len(positions) / max(2, len(set(query_tokens)))
        return self._bounded(0.7 * span_bonus + 0.3 * distinct_ratio)

    def _order_score(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0

        doc_positions: Dict[str, List[int]] = {}
        for idx, token in enumerate(doc_tokens):
            doc_positions.setdefault(token, []).append(idx)

        matched = 0
        last_pos = -1
        for token in query_tokens:
            token_positions = doc_positions.get(token, [])
            next_pos = next((pos for pos in token_positions if pos > last_pos), None)
            if next_pos is None:
                continue
            matched += 1
            last_pos = next_pos

        return self._bounded(matched / max(1, len(query_tokens)))

    def _language_alignment_score(self, query: str, text: str) -> float:
        query_has_chinese = bool(re.search(r"[\u4e00-\u9fff]", query or ""))
        text_has_chinese = bool(re.search(r"[\u4e00-\u9fff]", text or ""))
        query_has_english = bool(re.search(r"[a-zA-Z]{2,}", query or ""))
        text_has_english = bool(re.search(r"[a-zA-Z]{2,}", text or ""))

        score = 0.5
        if query_has_chinese:
            score += 0.3 if text_has_chinese else -0.2
        if query_has_english:
            score += 0.3 if text_has_english else -0.2
        return self._bounded(score)

    def score(
        self,
        *,
        query: str,
        snippet: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        retrieval_prior: float = 0.0,
        lexical_score: float = 0.0,
        vector_score: float = 0.0,
    ) -> Dict[str, float]:
        metadata = metadata or {}
        literal_query_tokens = tokenize(query)
        query_tokens = expand_query_tokens(query)
        content_tokens = tokenize(content)

        content_coverage = self._coverage_score(query_tokens, content_tokens)
        literal_content_coverage = self._coverage_score(literal_query_tokens, content_tokens)

        # snippet == content 时跳过重复分词和评分
        if snippet == content:
            snippet_tokens = content_tokens
            snippet_coverage = content_coverage
            literal_snippet_coverage = literal_content_coverage
        else:
            snippet_tokens = tokenize(snippet)
            snippet_coverage = self._coverage_score(query_tokens, snippet_tokens)
            literal_snippet_coverage = self._coverage_score(literal_query_tokens, snippet_tokens)
        phrase_score = max(
            self._phrase_score(query, snippet, metadata),
            0.85 * self._phrase_score(query, content, metadata),
        )
        title_score = self._bounded(self._phrase_score(query, "", metadata))
        proximity_score = max(
            self._proximity_score(query_tokens, snippet_tokens),
            0.9 * self._proximity_score(query_tokens, content_tokens),
        )
        order_score = max(
            self._order_score(query_tokens, snippet_tokens),
            0.85 * self._order_score(query_tokens, content_tokens),
        )
        language_score = self._language_alignment_score(query, f"{snippet}\n{content}")

        final_score = self._bounded(
            0.12 * self._bounded(retrieval_prior)
            + 0.10 * self._bounded(lexical_score)
            + 0.04 * self._bounded(vector_score)
            + 0.16 * snippet_coverage
            + 0.10 * content_coverage
            + 0.16 * literal_snippet_coverage
            + 0.08 * literal_content_coverage
            + 0.10 * phrase_score
            + 0.05 * title_score
            + 0.06 * language_score
            + 0.03 * proximity_score
            + 0.02 * order_score
        )

        return {
            "final_score": final_score,
            "snippet_coverage": round(snippet_coverage, 6),
            "content_coverage": round(content_coverage, 6),
            "literal_snippet_coverage": round(literal_snippet_coverage, 6),
            "literal_content_coverage": round(literal_content_coverage, 6),
            "phrase_score": round(phrase_score, 6),
            "title_score": round(title_score, 6),
            "language_score": round(language_score, 6),
            "proximity_score": round(proximity_score, 6),
            "order_score": round(order_score, 6),
        }
