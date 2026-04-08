# LanceDB 记忆存储

## 为什么选择 LanceDB

✅ **零配置** - 单文件存储，像 SQLite 一样简单
✅ **原生向量** - 无需插件，开箱即用
✅ **混合查询** - 内置向量 + 全文搜索
✅ **高性能** - Rust + Apache Arrow，比 Python 快 100x
✅ **自动索引** - 智能优化，无需手动管理

## 安装

```bash
pip install lancedb pyarrow
```

## 使用示例

```python
from agent_framework.memory.lance_store import LanceMemoryStore, Memory
from datetime import datetime

# 初始化（自动创建 data/lance_memory/ 目录）
store = LanceMemoryStore()

# 添加记忆
memory = Memory(
    id="mem_001",
    content="用户配置了 SCADA API 地址",
    memory_type="semantic",
    importance=0.8,
    created_at=datetime.now().isoformat(),
    last_accessed=datetime.now().isoformat(),
    access_count=0,
    tags=["config", "scada"],
    context={"user_id": "wind_admin"},
    embedding=[0.1, 0.2, ...],  # 384 维
)
store.add(memory)
```

## 搜索方式

### 1. 向量搜索
```python
results = store.search_vector(
    query_embedding=embedding,
    top_k=5,
    memory_type="semantic"
)
```

### 2. 全文搜索
```python
results = store.search_fulltext(
    query="SCADA 配置",
    top_k=5
)
```

### 3. 混合搜索（推荐）
```python
results = store.search_hybrid(
    query="SCADA 配置",
    query_embedding=embedding,
    top_k=5
)
```

## 性能对比

| 存储方案 | 10K 记忆 | 100K 记忆 | 依赖 |
|---------|---------|----------|------|
| NumPy 手动 | ~500ms | ~5s | NumPy |
| sqlite-vec | ~10ms | ~50ms | 插件 |
| **LanceDB** | **~5ms** | **~20ms** | lancedb |

## 优势

1. **单文件** - `data/lance_memory/` 目录，可直接备份
2. **自动优化** - 智能索引，无需手动调优
3. **增量更新** - 支持流式写入
4. **版本控制** - 内置数据版本管理
5. **SQL 查询** - 支持 SQL 语法过滤

## 迁移

```python
# 从旧存储迁移
old_store = MemoryStore()
new_store = LanceMemoryStore()

for mem in old_store.get_all():
    new_store.add(mem)
```
