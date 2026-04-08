# OpenClaw 记忆系统

## 核心特性

✅ **向量搜索** - LanceDB 原生支持
✅ **BM25 全文检索** - 内存索引
✅ **混合融合** - Vector + BM25 + 时间 + 重要性
✅ **时间衰减** - 指数衰减
✅ **时效性加成** - 最近访问加权
✅ **MMR 去重** - 多样性保证
✅ **Scope 隔离** - 多租户支持
✅ **Task-aware Embedding** - 任务上下文增强
✅ **OpenAI 兼容** - 任意 Embedding API

## 快速开始

```python
from agent_framework.memory.openclaw_memory import OpenClawMemory, SearchConfig

# 初始化
memory = OpenClawMemory()

# 添加记忆
memory.add(
    content="用户配置了 SCADA API",
    memory_type="semantic",
    scope="user:wind_admin",
    importance=0.8,
    tags=["config"],
    task_context="系统配置"
)

# 搜索
results = memory.search(
    query="SCADA 配置",
    scope="user:wind_admin",
    top_k=5,
    task_context="故障排查"
)
```

## 配置参数

```python
config = SearchConfig(
    vector_weight=0.5,      # 向量权重
    bm25_weight=0.3,        # BM25 权重
    recency_weight=0.1,     # 时效性权重
    importance_weight=0.1,  # 重要性权重
    enable_mmr=True,        # MMR 去重
    mmr_lambda=0.7,         # 多样性参数
    time_decay_days=30.0,   # 衰减周期
    min_score=0.1           # 最低分数
)
```

## Scope 隔离

```python
# 用户级
memory.add(content="...", scope="user:123")

# 会话级
memory.add(content="...", scope="session:abc")

# 任务级
memory.add(content="...", scope="task:xyz")
```

## 安装依赖

```bash
pip install lancedb pyarrow numpy
```
