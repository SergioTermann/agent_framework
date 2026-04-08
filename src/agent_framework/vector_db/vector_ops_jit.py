"""
超高性能向量计算模块 - Numba JIT 加速版本
使用 Numba JIT 编译实现接近 C/Rust 的性能

特性:
- JIT 编译到机器码
- SIMD 自动向量化
- 并行计算支持
- 零 Python 开销

预期性能提升: 10-30x
"""

import numpy as np
from numba import jit, prange, float32, float64
from typing import List, Tuple, Optional
import time


@jit(nopython=True, fastmath=True, cache=True)
def cosine_similarity_jit(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    JIT 编译的余弦相似度计算（单对）

    优化:
    - JIT 编译到机器码
    - fastmath 启用快速数学运算
    - 缓存编译结果
    """
    dot_product = 0.0
    norm1 = 0.0
    norm2 = 0.0

    for i in range(len(vec1)):
        dot_product += vec1[i] * vec2[i]
        norm1 += vec1[i] * vec1[i]
        norm2 += vec2[i] * vec2[i]

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    return dot_product / (np.sqrt(norm1) * np.sqrt(norm2))


@jit(nopython=True, parallel=True, fastmath=True, cache=True)
def cosine_similarity_batch_jit(vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
    """
    JIT 编译的批量余弦相似度计算

    优化:
    - parallel=True 启用并行计算
    - 使用 prange 并行循环
    - SIMD 自动向量化

    Args:
        vectors: (N, D) 向量矩阵
        query: (D,) 查询向量

    Returns:
        (N,) 相似度数组
    """
    n = vectors.shape[0]
    similarities = np.empty(n, dtype=np.float64)

    # 预计算查询向量的范数
    query_norm = 0.0
    for i in range(len(query)):
        query_norm += query[i] * query[i]
    query_norm = np.sqrt(query_norm)

    if query_norm == 0.0:
        similarities[:] = 0.0
        return similarities

    # 并行计算每个向量的相似度
    for i in prange(n):
        dot_product = 0.0
        vec_norm = 0.0

        for j in range(vectors.shape[1]):
            dot_product += vectors[i, j] * query[j]
            vec_norm += vectors[i, j] * vectors[i, j]

        vec_norm = np.sqrt(vec_norm)

        if vec_norm == 0.0:
            similarities[i] = 0.0
        else:
            similarities[i] = dot_product / (vec_norm * query_norm)

    return similarities


@jit(nopython=True, fastmath=True, cache=True)
def euclidean_distance_jit(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """JIT 编译的欧氏距离计算"""
    distance = 0.0
    for i in range(len(vec1)):
        diff = vec1[i] - vec2[i]
        distance += diff * diff
    return np.sqrt(distance)


@jit(nopython=True, parallel=True, fastmath=True, cache=True)
def euclidean_distance_batch_jit(vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
    """JIT 编译的批量欧氏距离计算"""
    n = vectors.shape[0]
    distances = np.empty(n, dtype=np.float64)

    for i in prange(n):
        distance = 0.0
        for j in range(vectors.shape[1]):
            diff = vectors[i, j] - query[j]
            distance += diff * diff
        distances[i] = np.sqrt(distance)

    return distances


@jit(nopython=True, fastmath=True, cache=True)
def dot_product_jit(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """JIT 编译的点积计算"""
    result = 0.0
    for i in range(len(vec1)):
        result += vec1[i] * vec2[i]
    return result


@jit(nopython=True, parallel=True, fastmath=True, cache=True)
def dot_product_batch_jit(vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
    """JIT 编译的批量点积计算"""
    n = vectors.shape[0]
    results = np.empty(n, dtype=np.float64)

    for i in prange(n):
        result = 0.0
        for j in range(vectors.shape[1]):
            result += vectors[i, j] * query[j]
        results[i] = result

    return results


@jit(nopython=True, fastmath=True, cache=True)
def normalize_vector_jit(vec: np.ndarray) -> np.ndarray:
    """JIT 编译的向量归一化"""
    norm = 0.0
    for i in range(len(vec)):
        norm += vec[i] * vec[i]
    norm = np.sqrt(norm)

    if norm == 0.0:
        return vec.copy()

    result = np.empty_like(vec)
    for i in range(len(vec)):
        result[i] = vec[i] / norm
    return result


@jit(nopython=True, parallel=True, fastmath=True, cache=True)
def normalize_vectors_batch_jit(vectors: np.ndarray) -> np.ndarray:
    """JIT 编译的批量向量归一化"""
    n = vectors.shape[0]
    d = vectors.shape[1]
    result = np.empty_like(vectors)

    for i in prange(n):
        norm = 0.0
        for j in range(d):
            norm += vectors[i, j] * vectors[i, j]
        norm = np.sqrt(norm)

        if norm == 0.0:
            for j in range(d):
                result[i, j] = vectors[i, j]
        else:
            for j in range(d):
                result[i, j] = vectors[i, j] / norm

    return result


def top_k_similar_jit(vectors: np.ndarray, query: np.ndarray, k: int) -> List[Tuple[int, float]]:
    """
    JIT 加速的 Top-K 相似度搜索

    优化:
    - 使用 JIT 编译的相似度计算
    - NumPy argpartition 快速分区
    - 避免完全排序

    Args:
        vectors: (N, D) 向量矩阵
        query: (D,) 查询向量
        k: 返回前 k 个结果

    Returns:
        [(index, similarity), ...] 按相似度降序排列
    """
    # 使用 JIT 编译的批量计算
    similarities = cosine_similarity_batch_jit(vectors, query)

    # 使用 argpartition 快速找到 top-k（O(n) 而不是 O(n log n)）
    if k >= len(similarities):
        indices = np.argsort(similarities)[::-1]
    else:
        # argpartition: 部分排序，只保证前 k 个是最大的
        indices = np.argpartition(similarities, -k)[-k:]
        # 对 top-k 进行排序
        indices = indices[np.argsort(similarities[indices])[::-1]]

    return [(int(idx), float(similarities[idx])) for idx in indices]


class JITVectorOps:
    """
    JIT 加速的向量操作类

    提供与 OptimizedVectorOps 兼容的接口
    """

    def __init__(self):
        """初始化并预热 JIT 编译"""
        # 预热 JIT 编译器
        self._warmup()

    def _warmup(self):
        """预热 JIT 编译器（首次调用会编译）"""
        dummy_vec = np.random.randn(100).astype(np.float64)
        dummy_vecs = np.random.randn(10, 100).astype(np.float64)

        # 触发编译
        _ = cosine_similarity_jit(dummy_vec, dummy_vec)
        _ = cosine_similarity_batch_jit(dummy_vecs, dummy_vec)
        _ = normalize_vector_jit(dummy_vec)
        _ = normalize_vectors_batch_jit(dummy_vecs)

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算两个向量的余弦相似度"""
        return cosine_similarity_jit(vec1, vec2)

    def cosine_similarity_batch(self, vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
        """批量计算余弦相似度"""
        return cosine_similarity_batch_jit(vectors, query)

    def euclidean_distance(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算欧氏距离"""
        return euclidean_distance_jit(vec1, vec2)

    def euclidean_distance_batch(self, vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
        """批量计算欧氏距离"""
        return euclidean_distance_batch_jit(vectors, query)

    def dot_product(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算点积"""
        return dot_product_jit(vec1, vec2)

    def dot_product_batch(self, vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
        """批量计算点积"""
        return dot_product_batch_jit(vectors, query)

    def normalize(self, vec: np.ndarray) -> np.ndarray:
        """归一化向量"""
        return normalize_vector_jit(vec)

    def normalize_batch(self, vectors: np.ndarray) -> np.ndarray:
        """批量归一化向量"""
        return normalize_vectors_batch_jit(vectors)

    def top_k_similar(self, vectors: np.ndarray, query: np.ndarray, k: int) -> List[Tuple[int, float]]:
        """Top-K 相似度搜索"""
        return top_k_similar_jit(vectors, query, k)


# 便捷函数
def create_jit_vector_ops() -> JITVectorOps:
    """创建 JIT 向量操作实例"""
    return JITVectorOps()


# 使用示例
if __name__ == "__main__":
    print("=" * 70)
    print("JIT 向量计算模块测试")
    print("=" * 70)

    # 创建实例
    ops = JITVectorOps()

    # 生成测试数据
    print("\n生成测试数据...")
    n_vectors = 10000
    dim = 768
    vectors = np.random.randn(n_vectors, dim).astype(np.float64)
    query = np.random.randn(dim).astype(np.float64)

    print(f"向量数量: {n_vectors}")
    print(f"向量维度: {dim}")

    # 测试余弦相似度
    print("\n测试 1: 批量余弦相似度")
    start = time.time()
    similarities = ops.cosine_similarity_batch(vectors, query)
    elapsed = time.time() - start
    print(f"  耗时: {elapsed:.4f} 秒")
    print(f"  吞吐量: {n_vectors/elapsed:.0f} 向量/秒")
    print(f"  结果示例: {similarities[:5]}")

    # 测试 Top-K
    print("\n测试 2: Top-K 相似度搜索")
    k = 10
    start = time.time()
    top_k = ops.top_k_similar(vectors, query, k)
    elapsed = time.time() - start
    print(f"  K = {k}")
    print(f"  耗时: {elapsed:.4f} 秒")
    print(f"  Top-3 结果: {top_k[:3]}")

    # 测试归一化
    print("\n测试 3: 批量归一化")
    start = time.time()
    normalized = ops.normalize_batch(vectors)
    elapsed = time.time() - start
    print(f"  耗时: {elapsed:.4f} 秒")
    print(f"  吞吐量: {n_vectors/elapsed:.0f} 向量/秒")

    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)
