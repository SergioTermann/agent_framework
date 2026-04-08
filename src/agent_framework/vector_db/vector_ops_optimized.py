"""
优化的向量计算模块 - 使用 NumPy + 多进程
在没有 Rust 的情况下也能获得显著性能提升
"""

import numpy as np
from typing import List, Tuple, Optional
from multiprocessing import Pool, cpu_count
import functools


class OptimizedVectorOps:
    """优化的向量运算类"""

    def __init__(self, use_multiprocessing: bool = True, num_workers: Optional[int] = None):
        self.use_multiprocessing = use_multiprocessing
        self.num_workers = num_workers or cpu_count()

    @staticmethod
    def _cosine_similarity_chunk(args):
        """计算一批向量的余弦相似度（用于多进程）"""
        vectors_chunk, query = args
        vectors_np = np.array(vectors_chunk)
        query_np = np.array(query)

        dot_products = np.dot(vectors_np, query_np)
        norms_vectors = np.linalg.norm(vectors_np, axis=1)
        norm_query = np.linalg.norm(query_np)

        similarities = dot_products / (norms_vectors * norm_query + 1e-10)
        return similarities.tolist()

    def cosine_similarity_batch(self, vectors: List[List[float]], query: List[float]) -> List[float]:
        """
        批量计算余弦相似度（优化版）

        Args:
            vectors: 向量列表
            query: 查询向量

        Returns:
            相似度列表
        """
        if not self.use_multiprocessing or len(vectors) < 1000:
            # 小数据集直接用 NumPy
            vectors_np = np.array(vectors)
            query_np = np.array(query)

            dot_products = np.dot(vectors_np, query_np)
            norms_vectors = np.linalg.norm(vectors_np, axis=1)
            norm_query = np.linalg.norm(query_np)

            similarities = dot_products / (norms_vectors * norm_query + 1e-10)
            return similarities.tolist()
        else:
            # 大数据集使用多进程
            chunk_size = len(vectors) // self.num_workers
            chunks = [
                (vectors[i:i + chunk_size], query)
                for i in range(0, len(vectors), chunk_size)
            ]

            with Pool(self.num_workers) as pool:
                results = pool.map(self._cosine_similarity_chunk, chunks)

            # 合并结果
            return [item for sublist in results for item in sublist]

    def euclidean_distance_batch(self, vectors: List[List[float]], query: List[float]) -> List[float]:
        """批量计算欧氏距离（优化版）"""
        vectors_np = np.array(vectors)
        query_np = np.array(query)
        distances = np.linalg.norm(vectors_np - query_np, axis=1)
        return distances.tolist()

    def normalize_vector(self, vector: List[float]) -> List[float]:
        """向量归一化"""
        vector_np = np.array(vector)
        norm = np.linalg.norm(vector_np)
        if norm == 0:
            return vector
        return (vector_np / norm).tolist()

    def normalize_vectors_batch(self, vectors: List[List[float]]) -> List[List[float]]:
        """批量向量归一化（优化版）"""
        vectors_np = np.array(vectors)
        norms = np.linalg.norm(vectors_np, axis=1, keepdims=True)
        norms[norms == 0] = 1
        normalized = vectors_np / norms
        return normalized.tolist()

    def top_k_similar(
        self,
        vectors: List[List[float]],
        query: List[float],
        k: int
    ) -> List[Tuple[int, float]]:
        """
        Top-K 相似度搜索（优化版）

        Args:
            vectors: 向量列表
            query: 查询向量
            k: 返回数量

        Returns:
            [(索引, 相似度), ...]
        """
        # 使用 NumPy 的 argpartition 进行部分排序（O(n) 而非 O(n log n)）
        vectors_np = np.array(vectors)
        query_np = np.array(query)

        dot_products = np.dot(vectors_np, query_np)
        norms_vectors = np.linalg.norm(vectors_np, axis=1)
        norm_query = np.linalg.norm(query_np)

        similarities = dot_products / (norms_vectors * norm_query + 1e-10)

        # 使用 argpartition 找到 top-k（比完全排序快）
        if k < len(similarities):
            top_k_indices = np.argpartition(similarities, -k)[-k:]
            top_k_indices = top_k_indices[np.argsort(similarities[top_k_indices])[::-1]]
        else:
            top_k_indices = np.argsort(similarities)[::-1]

        return [(int(idx), float(similarities[idx])) for idx in top_k_indices]

    def dot_product(self, a: List[float], b: List[float]) -> float:
        """向量点积"""
        return float(np.dot(a, b))

    def dot_product_batch(self, vectors: List[List[float]], query: List[float]) -> List[float]:
        """批量点积计算"""
        vectors_np = np.array(vectors)
        query_np = np.array(query)
        return np.dot(vectors_np, query_np).tolist()

    def vector_add(self, a: List[float], b: List[float]) -> List[float]:
        """向量加法"""
        return (np.array(a) + np.array(b)).tolist()

    def vector_sub(self, a: List[float], b: List[float]) -> List[float]:
        """向量减法"""
        return (np.array(a) - np.array(b)).tolist()

    def vector_scale(self, vector: List[float], scalar: float) -> List[float]:
        """向量标量乘法"""
        return (np.array(vector) * scalar).tolist()

    def l2_norm(self, vector: List[float]) -> float:
        """L2 范数"""
        return float(np.linalg.norm(vector))

    def l2_norm_batch(self, vectors: List[List[float]]) -> List[float]:
        """批量 L2 范数计算"""
        vectors_np = np.array(vectors)
        return np.linalg.norm(vectors_np, axis=1).tolist()


# 全局单例
_optimized_ops = OptimizedVectorOps()


# 便捷函数
def cosine_similarity_batch(vectors: List[List[float]], query: List[float]) -> List[float]:
    return _optimized_ops.cosine_similarity_batch(vectors, query)


def euclidean_distance_batch(vectors: List[List[float]], query: List[float]) -> List[float]:
    return _optimized_ops.euclidean_distance_batch(vectors, query)


def normalize_vector(vector: List[float]) -> List[float]:
    return _optimized_ops.normalize_vector(vector)


def normalize_vectors_batch(vectors: List[List[float]]) -> List[List[float]]:
    return _optimized_ops.normalize_vectors_batch(vectors)


def top_k_similar(vectors: List[List[float]], query: List[float], k: int) -> List[Tuple[int, float]]:
    return _optimized_ops.top_k_similar(vectors, query, k)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    return cosine_similarity_batch([a], b)[0]


def euclidean_distance(a: List[float], b: List[float]) -> float:
    """计算两个向量的欧氏距离"""
    return euclidean_distance_batch([a], b)[0]
