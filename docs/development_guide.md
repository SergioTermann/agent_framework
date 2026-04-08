# 开发指南

本文档为 Agent Framework 的开发者提供详细的开发指导。

## 目录

- [开发环境设置](#开发环境设置)
- [项目结构](#项目结构)
- [编码规范](#编码规范)
- [测试指南](#测试指南)
- [调试技巧](#调试技巧)
- [贡献流程](#贡献流程)

---

## 开发环境设置

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/agent-framework.git
cd agent-framework
```

### 2. 创建虚拟环境

```bash
# 使用 venv
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 或使用 uv（推荐）
uv venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
# 开发模式安装
pip install -e .

# 或使用 uv
uv pip install -e .
```

### 4. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的配置
# 至少需要配置：
# - OPENAI_API_KEY 或 SILICONFLOW_API_KEY
# - SECRET_KEY
```

### 5. 初始化数据库

```bash
python -c "from agent_framework.core.database import init_all_databases; init_all_databases()"
```

### 6. 启动开发服务器

```bash
python start_app.py
```

访问 http://localhost:5000

---

## 项目结构

```
agent_framework/
├── src/agent_framework/     # 主要源代码
│   ├── agent/              # Agent 引擎
│   ├── api/                # REST API 端点
│   ├── causal/             # 因果推理引擎
│   ├── core/               # 核心功能（数据库、配置等）
│   ├── gateway/            # LLM 网关
│   ├── infra/              # 基础设施（限流、认证等）
│   ├── memory/             # 记忆系统
│   ├── reasoning/          # 推理引擎
│   ├── tools/              # 工具集合
│   ├── vector_db/          # 向量数据库和知识库
│   ├── web/                # Web 应用
│   ├── workflow/           # 工作流引擎
│   ├── static/             # 静态资源
│   └── templates/          # HTML 模板
├── tests/                  # 测试文件
├── docs/                   # 文档
├── data/                   # 数据存储（不提交到 git）
├── plugins/                # 插件
├── services/               # 微服务
├── pyproject.toml          # 项目配置
├── .env.example            # 环境变量模板
└── README.md               # 项目说明
```

---

## 编码规范

### Python 代码风格

遵循 PEP 8 规范：

```python
# 好的示例
def calculate_similarity(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    """
    计算两个向量的余弦相似度。

    Args:
        vector_a: 第一个向量
        vector_b: 第二个向量

    Returns:
        相似度分数 (0-1)
    """
    dot_product = np.dot(vector_a, vector_b)
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)
```

### 命名约定

- **类名**: PascalCase - `AgentBuilder`, `KnowledgeBase`
- **函数名**: snake_case - `create_agent()`, `search_documents()`
- **常量**: UPPER_SNAKE_CASE - `MAX_TOKENS`, `DEFAULT_MODEL`
- **私有方法**: 前缀下划线 - `_internal_method()`

### 类型注解

使用类型注解提高代码可读性：

```python
from typing import List, Dict, Optional, Union

def process_documents(
    documents: List[str],
    metadata: Optional[Dict[str, str]] = None,
    batch_size: int = 100
) -> List[Dict[str, Union[str, float]]]:
    """处理文档并返回结果"""
    pass
```

### 文档字符串

使用 Google 风格的文档字符串：

```python
def search_knowledge_base(
    query: str,
    top_k: int = 5,
    threshold: float = 0.7
) -> List[Document]:
    """
    在知识库中搜索相关文档。

    Args:
        query: 搜索查询
        top_k: 返回的最大结果数
        threshold: 相似度阈值

    Returns:
        匹配的文档列表

    Raises:
        ValueError: 如果 top_k 小于 1

    Example:
        >>> kb = KnowledgeBase()
        >>> results = kb.search("AI agent", top_k=3)
        >>> print(len(results))
        3
    """
    pass
```

### 错误处理

```python
# 好的示例
try:
    result = risky_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    raise
except Exception as e:
    logger.exception("Unexpected error")
    return default_value

# 避免
try:
    result = risky_operation()
except:  # 不要使用裸 except
    pass
```

### 日志记录

使用 logging 模块，不要使用 print：

```python
import logging

logger = logging.getLogger(__name__)

# 好的示例
logger.info("Processing document: %s", doc_id)
logger.warning("Rate limit approaching: %d/%d", current, limit)
logger.error("Failed to connect to database: %s", error)

# 避免
print("Processing document:", doc_id)  # 不要在生产代码中使用 print
```

---

## 测试指南

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_agent_runtime_optimizations.py

# 运行特定测试函数
pytest tests/test_agent_runtime_optimizations.py::test_agent_creation

# 显示详细输出
pytest -v

# 显示打印输出
pytest -s

# 生成覆盖率报告
pytest --cov=agent_framework --cov-report=html
```

### 编写测试

```python
import pytest
from agent_framework.agent import AgentBuilder

def test_agent_creation():
    """测试 Agent 创建"""
    agent = AgentBuilder() \
        .with_name("test-agent") \
        .with_model("gpt-3.5-turbo") \
        .build()

    assert agent.name == "test-agent"
    assert agent.model == "gpt-3.5-turbo"

def test_agent_run():
    """测试 Agent 执行"""
    agent = AgentBuilder() \
        .with_name("test-agent") \
        .build()

    response = agent.run("Hello")
    assert response is not None
    assert len(response) > 0

@pytest.fixture
def knowledge_base():
    """知识库 fixture"""
    from agent_framework.vector_db import KnowledgeBase
    kb = KnowledgeBase()
    yield kb
    kb.clear()  # 清理

def test_knowledge_base_search(knowledge_base):
    """测试知识库搜索"""
    knowledge_base.add_document("Test document")
    results = knowledge_base.search("test", top_k=1)
    assert len(results) == 1
```

### 测试覆盖率目标

- 核心模块：>80%
- API 端点：>70%
- 工具函数：>90%

---

## 调试技巧

### 1. 使用 Python 调试器

```python
# 在代码中设置断点
import pdb; pdb.set_trace()

# 或使用 ipdb（更友好）
import ipdb; ipdb.set_trace()
```

### 2. 启用详细日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 3. 使用 Flask 调试模式

```python
# 在 .env 中设置
DEBUG=True

# 或在代码中
app.run(debug=True)
```

### 4. 性能分析

```python
import cProfile
import pstats

# 分析函数性能
profiler = cProfile.Profile()
profiler.enable()

# 你的代码
result = expensive_function()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)  # 显示前 10 个最慢的函数
```

### 5. 内存分析

```python
import tracemalloc

tracemalloc.start()

# 你的代码
result = memory_intensive_function()

current, peak = tracemalloc.get_traced_memory()
print(f"Current: {current / 1024 / 1024:.2f} MB")
print(f"Peak: {peak / 1024 / 1024:.2f} MB")

tracemalloc.stop()
```

---

## 贡献流程

### 1. Fork 项目

在 GitHub 上 fork 项目到你的账户。

### 2. 创建分支

```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

### 3. 开发和测试

- 编写代码
- 添加测试
- 确保所有测试通过
- 更新文档

### 4. 提交代码

```bash
git add .
git commit -m "feat: add new feature

- Detailed description of changes
- Why this change is needed
- Any breaking changes"
```

提交信息格式：
- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `style:` 代码格式（不影响功能）
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 构建/工具相关

### 5. 推送到 GitHub

```bash
git push origin feature/your-feature-name
```

### 6. 创建 Pull Request

在 GitHub 上创建 PR，描述你的更改。

### 7. 代码审查

- 响应审查意见
- 进行必要的修改
- 等待合并

---

## 常见开发任务

### 添加新的 API 端点

1. 在 `src/agent_framework/api/` 创建新文件
2. 定义 Blueprint
3. 实现端点函数
4. 在 `web_ui.py` 中注册 Blueprint
5. 添加测试
6. 更新 API 文档

示例：

```python
# src/agent_framework/api/my_api.py
from flask import Blueprint, jsonify, request

my_bp = Blueprint('my_api', __name__, url_prefix='/api/my')

@my_bp.route('/endpoint', methods=['POST'])
def my_endpoint():
    data = request.get_json()
    # 处理逻辑
    return jsonify({"result": "success"})
```

### 添加新的工具

1. 在 `src/agent_framework/tools/` 创建工具文件
2. 实现工具函数
3. 注册工具
4. 添加测试
5. 更新文档

### 添加新的页面

1. 在 `src/agent_framework/templates/` 创建 HTML 模板
2. 在 `web_ui.py` 添加路由
3. 添加必要的 API 端点
4. 更新导航菜单

---

## 性能优化建议

1. **使用缓存**
   - LRU 缓存函数结果
   - Redis 缓存 API 响应

2. **批量处理**
   - 批量插入数据库
   - 批量向量化文档

3. **异步处理**
   - 使用 async/await
   - 后台任务队列

4. **数据库优化**
   - 添加索引
   - 使用连接池
   - 避免 N+1 查询

5. **向量操作优化**
   - 使用 NumPy 向量化
   - 启用 Numba JIT
   - 使用 FAISS 加速搜索

---

## 更多资源

- [API 参考](api_reference.md)
- [架构文档](architecture.md)
- [故障排查](troubleshooting.md)
- [快速参考](quick_reference.md)
