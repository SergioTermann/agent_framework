# 快速参考指南

Agent Framework 常用功能速查表。

## 快速开始

### 安装
```bash
pip install -e .
```

### 启动服务
```bash
python -m agent_framework.web.web_ui
```

访问：http://localhost:5000

---

## 常用 API 端点

### 创建 Agent
```bash
curl -X POST http://localhost:5000/api/agent/create \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "model": "gpt-4"}'
```

### 发送消息
```bash
curl -X POST http://localhost:5000/api/conversation/{id}/message \
  -H "Content-Type: application/json" \
  -d '{"content": "你好"}'
```

### 搜索知识库
```bash
curl -X POST http://localhost:5000/api/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "搜索内容", "top_k": 5}'
```

---

## 页面导航

| 功能 | 路径 | 说明 |
|------|------|------|
| 主页 | `/` | 平台首页 |
| Agent 管理 | `/agents` | 管理 Agent |
| 对话 | `/chat` | 聊天界面 |
| 知识库 | `/knowledge` | 知识库管理 |
| 工作流 | `/workflow` | 工作流编排 |
| 提示词库 | `/prompts` | 提示词管理 |
| 文档中心 | `/documents` | 文档上传 |
| A/B 测试 | `/ab-testing` | 实验对比 |
| 高级推理 | `/reasoning` | 推理实验 |
| 发布管理 | `/publish` | 应用发布 |
| 配置预设 | `/config-presets` | 配置管理 |
| HTTP 工具 | `/http-tools` | 请求测试 |
| 高级工作流 | `/workflow-advanced` | 可视化编排 |
| 协作管理 | `/collaboration` | 团队协作 |
| 监控面板 | `/monitoring` | 系统监控 |
| 多模态 | `/multimodal` | 多模态处理 |
| 扩展管理 | `/extensions` | 插件管理 |
| 插件市场 | `/plugins` | 插件市场 |
| 系统设置 | `/settings` | 平台设置 |
| 日志中心 | `/logs` | 日志查询 |

---

## 配置文件

### 主配置文件
`config/config.yaml`

```yaml
server:
  host: 0.0.0.0
  port: 5000
  debug: false

llm:
  provider: openai
  model: gpt-4
  api_key: ${OPENAI_API_KEY}

database:
  path: data/agent_framework.db

vector_store:
  type: faiss
  dimension: 1536
```

### 环境变量
`.env`

```bash
OPENAI_API_KEY=your_api_key
DATABASE_URL=sqlite:///data/agent_framework.db
LOG_LEVEL=INFO
```

---

## Python SDK

### 创建 Agent
```python
from agent_framework import AgentBuilder

agent = AgentBuilder() \
    .with_name("my-agent") \
    .with_model("gpt-4") \
    .with_tools(["search", "calculator"]) \
    .build()

response = agent.run("你好，世界")
print(response)
```

### 使用知识库
```python
from agent_framework.vector_db import KnowledgeBase

kb = KnowledgeBase()
kb.add_document("文档内容", metadata={"source": "test"})

results = kb.search("查询内容", top_k=5)
for result in results:
    print(result.content, result.score)
```

### 工作流编排
```python
from agent_framework.workflow import Workflow

workflow = Workflow()
workflow.add_node("step1", agent1)
workflow.add_node("step2", agent2)
workflow.add_edge("step1", "step2")

result = workflow.execute({"input": "数据"})
```

---

## 常见问题

### 如何更换 LLM 模型？
在配置文件中修改 `llm.model` 或在创建 Agent 时指定。

### 如何添加自定义工具？
```python
from agent_framework.tools import Tool

@Tool.register("my_tool")
def my_tool(input: str) -> str:
    return f"处理: {input}"
```

### 如何启用日志？
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 如何备份数据？
```bash
cp -r data/ backup/
```

---

## 性能优化

### 启用缓存
```python
agent = AgentBuilder() \
    .with_cache(enabled=True, ttl=3600) \
    .build()
```

### 批量处理
```python
results = agent.batch_run([
    "问题1",
    "问题2",
    "问题3"
])
```

### 异步执行
```python
import asyncio

async def main():
    result = await agent.arun("异步查询")
    print(result)

asyncio.run(main())
```

---

## 故障排查

### 服务无法启动
1. 检查端口是否被占用：`netstat -ano | findstr :5000`
2. 检查配置文件是否正确
3. 查看日志：`tail -f logs/app.log`

### API 调用失败
1. 检查 API Key 是否配置
2. 检查网络连接
3. 查看错误日志

### 知识库搜索无结果
1. 确认文档已添加
2. 检查向量维度是否匹配
3. 调整搜索参数

---

## 更多资源

- [完整 API 文档](api_reference.md)
- [用户工具指南](user_tools_guide.md)
- [架构设计](migration_target_architecture.md)
- [GitHub 仓库](https://github.com/your-repo/agent-framework)
