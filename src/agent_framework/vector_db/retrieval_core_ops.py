"""
retrieval_core — Rust 加速的 RAG 检索核心操作

提供 tokenize / BM25 / lexical 评分的 Rust 实现，
当编译产物不可用时自动回退到纯 Python 实现。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _import_retrieval_core():
    """尝试按优先级导入编译后的 Rust 扩展模块"""
    try:
        return importlib.import_module("retrieval_core"), None
    except ImportError as exc:
        import_error = exc

    candidate_roots = []
    for parent in Path(__file__).resolve().parents:
        candidate_roots.append(parent)
        if len(candidate_roots) >= 5:
            break
    candidate_roots.append(Path.cwd())

    search_dirs = []
    for project_root in candidate_roots:
        search_dirs.extend([
            project_root / "rust_extensions" / "retrieval_core" / "target" / "release",
        project_root / "rust_extensions" / "retrieval_core" / "target" / "debug",
        ])
    patterns = ("retrieval_core*.pyd", "retrieval_core*.so", "retrieval_core*.dylib")

    for directory in search_dirs:
        if not directory.exists():
            continue
        if not any(directory.glob(pattern) for pattern in patterns):
            continue

        sys.path.insert(0, str(directory))
        try:
            return importlib.import_module("retrieval_core"), None
        except ImportError:
            sys.path.pop(0)

    return None, import_error


_rc_mod, _RC_IMPORT_ERROR = _import_retrieval_core()
RUST_RETRIEVAL_AVAILABLE: bool = _rc_mod is not None

if not RUST_RETRIEVAL_AVAILABLE:
    print(f"[retrieval_core_ops] Rust retrieval_core not available, using Python fallback ({_RC_IMPORT_ERROR})")


# ─── Public API ───────────────────────────────────────────────────────────────

def rust_tokenize(text: str, include_numbers: bool = False) -> List[str]:
    """Rust 加速分词。无 Rust 时返回 None 以让调用方回退。"""
    if _rc_mod is not None:
        return _rc_mod.tokenize(text, include_numbers)
    return None


def rust_bm25_score_batch(
    doc_term_freqs: List[Dict[str, int]],
    doc_lengths: List[int],
    idf: Dict[str, float],
    query_tokens: List[str],
    candidate_indices: List[int],
    k1: float = 1.2,
    b: float = 0.75,
    avgdl: float = 1.0,
) -> Optional[List[Tuple[int, float]]]:
    """批量 BM25 评分。返回 [(doc_idx, score), ...] 按分数降序。"""
    if _rc_mod is None:
        return None
    return _rc_mod.bm25_score_batch(
        doc_term_freqs, doc_lengths, idf, query_tokens,
        candidate_indices, k1, b, avgdl,
    )


def rust_lexical_score_batch(
    doc_term_freqs: List[Dict[str, int]],
    doc_lengths: List[int],
    query_token_freqs: Dict[str, int],
    query_total: int,
    candidate_indices: List[int],
) -> Optional[List[Tuple[int, float]]]:
    """批量词面匹配评分。"""
    if _rc_mod is None:
        return None
    return _rc_mod.lexical_score_batch(
        doc_term_freqs, doc_lengths, query_token_freqs,
        query_total, candidate_indices,
    )


def rust_fused_score_batch(
    doc_term_freqs: List[Dict[str, int]],
    doc_lengths: List[int],
    idf: Dict[str, float],
    query_tokens: List[str],
    query_token_freqs: Dict[str, int],
    query_total: int,
    candidate_indices: List[int],
    k1: float = 1.2,
    b: float = 0.75,
    avgdl: float = 1.0,
) -> Optional[List[Tuple[int, float, float, float]]]:
    """融合评分：单次遍历同时算 BM25 + lexical。
    返回 [(doc_idx, fused_score, bm25_raw, lexical_score), ...]"""
    if _rc_mod is None:
        return None
    return _rc_mod.fused_score_batch(
        doc_term_freqs, doc_lengths, idf, query_tokens,
        query_token_freqs, query_total, candidate_indices,
        k1, b, avgdl,
    )
