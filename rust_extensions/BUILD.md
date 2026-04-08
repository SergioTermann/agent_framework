# Rust 扩展构建

## 先决条件
- 安装 Rust / Cargo
- 安装 Python 开发环境
- 建议安装 `maturin`

## 构建 vector_core
```powershell
cd rust_extensions/vector_core
cargo build --release
```

## 构建 causal_core
```powershell
cd rust_extensions/causal_core
cargo build --release
```

## 构建 retrieval_core
```powershell
cd rust_extensions/retrieval_core
cargo build --release
```

提供的功能：
- `tokenize` — 单遍分词（英文 + CJK 双字组），替代 `retrieval_utils._tokenize_python`
- `bm25_score_batch` — 基于 Rayon 的并行 BM25 批量评分
- `lexical_score_batch` — 并行词面匹配评分
- `fused_score_batch` — 单次遍历同时算 BM25 + lexical（`rag.py` 使用）

Python 入口：`retrieval_core_ops.py`（自动检测 `.pyd`/`.so`/`.dylib`，无 Rust 时回退到纯 Python）

## 运行方式
构建完成后，Python 会自动从以下目录加载扩展：
- `rust_extensions/vector_core/target/release`
- `rust_extensions/causal_core/target/release`
- `rust_extensions/retrieval_core/target/release`

无需改 Python 代码。
