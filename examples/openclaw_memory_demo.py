"""
OpenClaw 记忆系统完整示例
"""

from agent_framework.memory.openclaw_memory import OpenClawMemory, SearchConfig

# 初始化
memory = OpenClawMemory()

# 1. 添加不同类型的记忆
memory.add(
    content="用户配置了 SCADA API 地址为 https://scada.example.com",
    memory_type="semantic",
    scope="user:wind_admin",
    importance=0.9,
    tags=["config", "scada"],
    task_context="系统配置"
)

memory.add(
    content="WT-001 风机昨天出现功率异常",
    memory_type="episodic",
    scope="user:wind_admin",
    importance=0.7,
    tags=["fault", "WT-001"]
)

# 2. 基础搜索
results = memory.search(
    query="SCADA 配置",
    scope="user:wind_admin",
    top_k=5
)

# 3. 自定义配置搜索
config = SearchConfig(
    vector_weight=0.6,
    bm25_weight=0.2,
    recency_weight=0.1,
    importance_weight=0.1,
    enable_mmr=True,
    mmr_lambda=0.7
)

results = memory.search(
    query="风机故障",
    scope="user:wind_admin",
    config=config
)

# 4. 自适应搜索（自动调整策略）
results = memory.adaptive_search(
    query="最近的告警",
    scope="user:wind_admin"
)

# 5. Session 记忆
session = memory.create_session("session_123")
session.add("用户询问了 WT-001 的状态")
session.add("系统返回了实时数据")

# 获取 session 上下文
context = session.get_context()
print(context)

# 6. 统计信息
stats = memory.stats(scope="user:wind_admin")
print(f"总记忆数: {stats['total']}")
print(f"按类型: {stats['by_type']}")
