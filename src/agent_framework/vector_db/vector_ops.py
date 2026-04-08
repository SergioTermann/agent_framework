"""
????????? - Rust ????
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np


def _import_vector_core():
    """???????????????????? Rust ???????"""
    try:
        return importlib.import_module("vector_core"), None
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
            project_root / "rust_extensions" / "vector_core" / "target" / "release",
        project_root / "rust_extensions" / "vector_core" / "target" / "debug",
        ])
    patterns = ("vector_core*.pyd", "vector_core*.so", "vector_core*.dylib")

    for directory in search_dirs:
        if not directory.exists():
            continue
        if not any(directory.glob(pattern) for pattern in patterns):
            continue

        sys.path.insert(0, str(directory))
        try:
            return importlib.import_module("vector_core"), None
        except ImportError:
            sys.path.pop(0)

    return None, import_error


vector_core, _VECTOR_CORE_IMPORT_ERROR = _import_vector_core()
RUST_AVAILABLE = vector_core is not None

if not RUST_AVAILABLE:
    print(f"Warning: Rust vector_core not available, falling back to NumPy ({_VECTOR_CORE_IMPORT_ERROR})")


class VectorOps:
    """???????"""

    @staticmethod
    def cosine_similarity_batch(vectors: List[List[float]], query: List[float]) -> List[float]:
        if RUST_AVAILABLE:
            return vector_core.cosine_similarity_batch(vectors, query)

        vectors_np = np.array(vectors)
        query_np = np.array(query)
        dot_products = np.dot(vectors_np, query_np)
        norms_vectors = np.linalg.norm(vectors_np, axis=1)
        norm_query = np.linalg.norm(query_np)
        similarities = dot_products / (norms_vectors * norm_query + 1e-10)
        return similarities.tolist()

    @staticmethod
    def euclidean_distance_batch(vectors: List[List[float]], query: List[float]) -> List[float]:
        if RUST_AVAILABLE:
            return vector_core.euclidean_distance_batch(vectors, query)

        vectors_np = np.array(vectors)
        query_np = np.array(query)
        distances = np.linalg.norm(vectors_np - query_np, axis=1)
        return distances.tolist()

    @staticmethod
    def normalize_vector(vector: List[float]) -> List[float]:
        if RUST_AVAILABLE:
            return vector_core.normalize_vector(vector)

        vector_np = np.array(vector)
        norm = np.linalg.norm(vector_np)
        if norm == 0:
            return vector
        return (vector_np / norm).tolist()

    @staticmethod
    def normalize_vectors_batch(vectors: List[List[float]]) -> List[List[float]]:
        if RUST_AVAILABLE:
            return vector_core.normalize_vectors_batch(vectors)

        vectors_np = np.array(vectors)
        norms = np.linalg.norm(vectors_np, axis=1, keepdims=True)
        norms[norms == 0] = 1
        normalized = vectors_np / norms
        return normalized.tolist()

    @staticmethod
    def top_k_similar(vectors: List[List[float]], query: List[float], k: int) -> List[Tuple[int, float]]:
        if RUST_AVAILABLE:
            return vector_core.top_k_similar(vectors, query, k)

        similarities = VectorOps.cosine_similarity_batch(vectors, query)
        indexed = list(enumerate(similarities))
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed[:k]

    @staticmethod
    def dot_product(a: List[float], b: List[float]) -> float:
        if RUST_AVAILABLE:
            return vector_core.dot_product(a, b)
        return float(np.dot(a, b))

    @staticmethod
    def dot_product_batch(vectors: List[List[float]], query: List[float]) -> List[float]:
        if RUST_AVAILABLE:
            return vector_core.dot_product_batch(vectors, query)

        vectors_np = np.array(vectors)
        query_np = np.array(query)
        return np.dot(vectors_np, query_np).tolist()

    @staticmethod
    def vector_add(a: List[float], b: List[float]) -> List[float]:
        if RUST_AVAILABLE:
            return vector_core.vector_add(a, b)
        return (np.array(a) + np.array(b)).tolist()

    @staticmethod
    def vector_sub(a: List[float], b: List[float]) -> List[float]:
        if RUST_AVAILABLE:
            return vector_core.vector_sub(a, b)
        return (np.array(a) - np.array(b)).tolist()

    @staticmethod
    def vector_scale(vector: List[float], scalar: float) -> List[float]:
        if RUST_AVAILABLE:
            return vector_core.vector_scale(vector, scalar)
        return (np.array(vector) * scalar).tolist()

    @staticmethod
    def l2_norm(vector: List[float]) -> float:
        if RUST_AVAILABLE:
            return vector_core.l2_norm(vector)
        return float(np.linalg.norm(vector))

    @staticmethod
    def l2_norm_batch(vectors: List[List[float]]) -> List[float]:
        if RUST_AVAILABLE:
            return vector_core.l2_norm_batch(vectors)

        vectors_np = np.array(vectors)
        return np.linalg.norm(vectors_np, axis=1).tolist()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    return VectorOps.cosine_similarity_batch([a], b)[0]


def euclidean_distance(a: List[float], b: List[float]) -> float:
    return VectorOps.euclidean_distance_batch([a], b)[0]
