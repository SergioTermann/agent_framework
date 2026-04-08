use pyo3::prelude::*;
use pyo3::types::PyList;
use ndarray::{Array1, Array2};
use rayon::prelude::*;
use std::f32;

/// 计算两个向量的余弦相似度
#[inline]
fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() {
        return 0.0;
    }

    let dot_product: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let norm_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let norm_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();

    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }

    dot_product / (norm_a * norm_b)
}

/// 批量计算余弦相似度（并行）
#[pyfunction]
fn cosine_similarity_batch(vectors: Vec<Vec<f32>>, query: Vec<f32>) -> PyResult<Vec<f32>> {
    let results: Vec<f32> = vectors
        .par_iter()
        .map(|v| cosine_similarity(v, &query))
        .collect();

    Ok(results)
}

/// 计算欧氏距离
#[inline]
fn euclidean_distance(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() {
        return f32::INFINITY;
    }

    a.iter()
        .zip(b.iter())
        .map(|(x, y)| (x - y).powi(2))
        .sum::<f32>()
        .sqrt()
}

/// 批量计算欧氏距离（并行）
#[pyfunction]
fn euclidean_distance_batch(vectors: Vec<Vec<f32>>, query: Vec<f32>) -> PyResult<Vec<f32>> {
    let results: Vec<f32> = vectors
        .par_iter()
        .map(|v| euclidean_distance(v, &query))
        .collect();

    Ok(results)
}

/// 向量归一化
#[pyfunction]
fn normalize_vector(vector: Vec<f32>) -> PyResult<Vec<f32>> {
    let norm: f32 = vector.iter().map(|x| x * x).sum::<f32>().sqrt();

    if norm == 0.0 {
        return Ok(vector);
    }

    Ok(vector.iter().map(|x| x / norm).collect())
}

/// 批量向量归一化（并行）
#[pyfunction]
fn normalize_vectors_batch(vectors: Vec<Vec<f32>>) -> PyResult<Vec<Vec<f32>>> {
    let results: Vec<Vec<f32>> = vectors
        .par_iter()
        .map(|v| {
            let norm: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
            if norm == 0.0 {
                v.clone()
            } else {
                v.iter().map(|x| x / norm).collect()
            }
        })
        .collect();

    Ok(results)
}

/// Top-K 相似度搜索（返回索引和分数）
#[pyfunction]
fn top_k_similar(
    vectors: Vec<Vec<f32>>,
    query: Vec<f32>,
    k: usize,
) -> PyResult<Vec<(usize, f32)>> {
    let mut similarities: Vec<(usize, f32)> = vectors
        .par_iter()
        .enumerate()
        .map(|(idx, v)| (idx, cosine_similarity(v, &query)))
        .collect();

    // 按相似度降序排序
    similarities.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());

    // 返回 Top-K
    Ok(similarities.into_iter().take(k).collect())
}

/// 向量点积
#[pyfunction]
fn dot_product(a: Vec<f32>, b: Vec<f32>) -> PyResult<f32> {
    if a.len() != b.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Vectors must have the same length",
        ));
    }

    Ok(a.iter().zip(b.iter()).map(|(x, y)| x * y).sum())
}

/// 批量点积计算（并行）
#[pyfunction]
fn dot_product_batch(vectors: Vec<Vec<f32>>, query: Vec<f32>) -> PyResult<Vec<f32>> {
    let results: Vec<f32> = vectors
        .par_iter()
        .map(|v| {
            if v.len() != query.len() {
                0.0
            } else {
                v.iter().zip(query.iter()).map(|(x, y)| x * y).sum()
            }
        })
        .collect();

    Ok(results)
}

/// 向量加法
#[pyfunction]
fn vector_add(a: Vec<f32>, b: Vec<f32>) -> PyResult<Vec<f32>> {
    if a.len() != b.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Vectors must have the same length",
        ));
    }

    Ok(a.iter().zip(b.iter()).map(|(x, y)| x + y).collect())
}

/// 向量减法
#[pyfunction]
fn vector_sub(a: Vec<f32>, b: Vec<f32>) -> PyResult<Vec<f32>> {
    if a.len() != b.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Vectors must have the same length",
        ));
    }

    Ok(a.iter().zip(b.iter()).map(|(x, y)| x - y).collect())
}

/// 向量标量乘法
#[pyfunction]
fn vector_scale(vector: Vec<f32>, scalar: f32) -> PyResult<Vec<f32>> {
    Ok(vector.iter().map(|x| x * scalar).collect())
}

/// 计算向量的 L2 范数
#[pyfunction]
fn l2_norm(vector: Vec<f32>) -> PyResult<f32> {
    Ok(vector.iter().map(|x| x * x).sum::<f32>().sqrt())
}

/// 批量 L2 范数计算（并行）
#[pyfunction]
fn l2_norm_batch(vectors: Vec<Vec<f32>>) -> PyResult<Vec<f32>> {
    let results: Vec<f32> = vectors
        .par_iter()
        .map(|v| v.iter().map(|x| x * x).sum::<f32>().sqrt())
        .collect();

    Ok(results)
}

/// Python 模块定义
#[pymodule]
fn vector_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cosine_similarity_batch, m)?)?;
    m.add_function(wrap_pyfunction!(euclidean_distance_batch, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_vector, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_vectors_batch, m)?)?;
    m.add_function(wrap_pyfunction!(top_k_similar, m)?)?;
    m.add_function(wrap_pyfunction!(dot_product, m)?)?;
    m.add_function(wrap_pyfunction!(dot_product_batch, m)?)?;
    m.add_function(wrap_pyfunction!(vector_add, m)?)?;
    m.add_function(wrap_pyfunction!(vector_sub, m)?)?;
    m.add_function(wrap_pyfunction!(vector_scale, m)?)?;
    m.add_function(wrap_pyfunction!(l2_norm, m)?)?;
    m.add_function(wrap_pyfunction!(l2_norm_batch, m)?)?;

    Ok(())
}
