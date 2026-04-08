# 项目架构文档

## 系统架构概览

Agent Framework 采用分层架构设计，从底层基础设施到上层应用界面，提供完整的 AI Agent 开发和运营能力。

```
┌─────────────────────────────────────────────────────────────┐
│                      Web UI Layer                            │
│  (Flask + SocketIO + 响应式前端 + 20+ 功能页面)              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      API Layer                               │
│  (26 个 REST API 模块 + WebSocket 实时通信)                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Application Layer                          │
│  ┌──────────────┬──────────────┬──────────────┐            │
│  │ Agent Engine │ Workflow     │ Knowledge    │            │
│  │ (12-Factor)  │ Orchestrator │ Base (RAG)   │            │
│  └──────────────┴──────────────┴──────────────┘            │
│  ┌──────────────┬──────────────┬──────────────┐            │
│  │ Memory       │ Causal       │ Reasoning    │            │
│  │ System       │ Engine       │ Engine       │            │
│  └──────────────┴──────────────┴──────────────┘            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  Infrastructure Layer                        │
│  ┌──────────────┬──────────────┬──────────────┐            │
│  │ LLM Gateway  │ Vector Store │ Database     │            │
│  │ (Multi-LLM)  │ (Chroma)     │ (SQLite)     │            │
│  └──────────────┴──────────────┴──────────────┘            │
│  ┌──────────────┬──────────────┬──────────────┐            │
│  │ Rate Limiter │ Auth & RBAC  │ Monitoring   │            │
│  │              │              │              │            │
│  └──────────────┴──────────────┴──────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心模块详解

### 1. Agent Engine (12-Factor 设计)

**位置：** `src/agent_framework/agent/`

**核心组件：**
- `builder.py` - 链式 API 构建器
- `runner.py` - 信号驱动执行引擎
- `llm.py` - 多 LLM 供应商抽象层
- `thread.py` - 不可变线程状态管理
- `context.py` - 上下文窗口管理
- `prompts.py` - Prompt 模板系统
- `store.py` - 线程持久化存储
- `callbacks.py` - 事件回调系统

**设计原则：**
1. **不可变状态** - 每次执行创建新的线程状态
2. **信号驱动** - 通过信号控制执行流程
3. **透明控制流** - 不依赖外部框架，所有逻辑可审计
4. **可测试性** - 纯函数设计，易于单元测试

**使用示例：**
```python
from agent_framework.agent import AgentBuilder

agent = AgentBuilder() \
    .with_name("my-agent") \
    .with_model("gpt-4") \
    .with_tools(["search", "calculator"]) \
    .with_memory(enabled=True) \
    .build()

response = agent.run("你好，世界")
```

---

### 2. Workflow Orchestrator

**位置：** `src/agent_framework/workflow/`

**核心功能：**
- DAG 拓扑排序执行
- 条件分支和循环
- 并行节点执行
- 可视化编辑器
- 工作流版本管理

**工作流类型：**
- **基础工作流** (`workflow.py`) - 简单的顺序执行
- **高级工作流** (`workflow_advanced.py`) - 支持复杂逻辑和优化

**节点类型：**
- Agent 节点 - 执行 Agent 任务
- 条件节点 - 根据条件分支
- 循环节点 - 重复执行
- 并行节点 - 同时执行多个任务
- 工具节点 - 调用外部工具

---

### 3. Knowledge Base (RAG)

**位置：** `src/agent_framework/vector_db/`

**核心组件：**
- `knowledge_base.py` (1837 行) - 主要知识库实现
- `vector_store.py` - 向量存储抽象
- `vector_ops.py` - 向量操作（支持 JIT 优化）
- `embedding.py` - 嵌入模型接口

**支持的文档格式：**
- PDF (PyPDF2)
- Word (python-docx)
- Excel (openpyxl)
- PowerPoint (python-pptx)
- Markdown
- 纯文本

**检索策略：**
- 向量相似度搜索
- 混合检索（向量 + 关键词）
- 重排序（Rerank）
- 多跳推理

**向量存储后端：**
- Chroma (默认)
- LanceDB
- FAISS

---

### 4. Memory System

**位置：** `src/agent_framework/memory/`

**核心文件：** `system.py` (1493 行)

**记忆类型：**

1. **情景记忆 (Episodic Memory)**
   - 存储对话历史
   - 时间戳标记
   - 自动裁剪

2. **语义记忆 (Semantic Memory)**
   - 长期知识存储
   - 向量化检索
   - 知识图谱

3. **程序性记忆 (Procedural Memory)**
   - 技能和工具
   - 执行历史
   - 性能优化

4. **工作记忆 (Working Memory)**
   - 当前上下文
   - 临时变量
   - 中间结果

**记忆管理：**
- 重要度评分
- 自动遗忘机制
- 记忆压缩
- 跨会话持久化

---

### 5. Causal Reasoning Engine

**位置：** `src/agent_framework/causal/`

**核心文件：** `causal_reasoning_engine.py` (1481 行)

**功能模块：**
- 因果链分析
- 反事实推理
- 根因定位
- 干预评估
- 因果图可视化

**应用场景：**
- 故障诊断
- 决策支持
- 风险评估
- 效果预测

---

### 6. Infrastructure Layer

**位置：** `src/agent_framework/infra/`

**核心组件：**

1. **LLM Gateway** (`gateway/`)
   - 多供应商支持（OpenAI, vLLM, SiliconFlow, Xinference）
   - 负载均衡
   - 故障转移
   - 成本追踪

2. **Rate Limiter** (`rate_limiter_optimized.py`)
   - 令牌桶算法
   - 滑动窗口
   - 分布式限流

3. **Authentication & Authorization** (`auth/`)
   - JWT Token 认证
   - RBAC 权限控制
   - API Key 管理

4. **Monitoring** (`monitoring/`)
   - 性能指标收集
   - 日志聚合
   - 告警系统

5. **Async Task System** (`async_task_system_optimized.py`)
   - 异步任务队列
   - 任务调度
   - 结果缓存

---

### 7. Web UI Layer

**位置：** `src/agent_framework/web/` 和 `src/agent_framework/templates/`

**核心文件：**
- `web_ui.py` (1433 行) - Flask 应用主文件
- `context_builder.py` (1289 行) - 上下文构建器
- `unified_orchestrator.py` (991 行) - 统一编排器

**页面模块：** (20+ 页面)
- 主页和导航
- Agent 管理
- 对话界面
- 工作流编辑器
- 知识库管理
- 提示词库
- 文档中心
- A/B 测试
- 高级推理
- 发布管理
- 配置预设
- HTTP 工具
- 协作管理
- 监控面板
- 多模态处理
- 扩展管理
- 插件市场
- 系统设置
- 日志中心

**技术栈：**
- Flask 3.0+ (Web 框架)
- Flask-SocketIO (实时通信)
- Jinja2 (模板引擎)
- 响应式 CSS (统一蓝色主题 #1363df)
- Material Symbols (图标)

---

## 数据流

### 1. 用户请求流程

```
用户 → Web UI → API Layer → Application Layer → Infrastructure Layer
                                                          ↓
                                                    LLM / Database
                                                          ↓
用户 ← Web UI ← API Layer ← Application Layer ← Infrastructure Layer
```

### 2. Agent 执行流程

```
1. 接收用户输入
2. 加载上下文和记忆
3. 构建 Prompt
4. 调用 LLM
5. 解析响应
6. 执行工具调用（如需要）
7. 更新记忆
8. 返回结果
```

### 3. RAG 检索流程

```
1. 接收查询
2. 生成查询嵌入
3. 向量相似度搜索
4. 重排序结果
5. 提取相关文档
6. 构建增强 Prompt
7. 生成回答
```

---

## 配置管理

### 配置优先级

```
环境变量 > config.yaml > 默认值
```

### 主要配置文件

1. **`.env`** - 环境变量（敏感信息）
2. **`src/agent_framework/core/config.yaml`** - 主配置文件
3. **`pyproject.toml`** - 项目依赖和元数据

### 关键配置项

```yaml
llm:
  provider: openai-compatible
  model: gpt-4
  base_url: https://api.openai.com/v1

server:
  host: 0.0.0.0
  port: 5000

agent:
  temperature: 0.7
  max_tokens: 2048
  max_rounds: 15

data:
  data_dir: ./data
```

---

## 扩展性设计

### 1. 插件系统

**位置：** `src/agent_framework/plugins/`

- 动态加载插件
- 插件生命周期管理
- 插件市场

### 2. 工具注册

```python
from agent_framework.tools import Tool

@Tool.register("my_tool")
def my_tool(input: str) -> str:
    return f"处理: {input}"
```

### 3. 自定义 LLM 供应商

```python
from agent_framework.agent.llm import LLMProvider

class MyLLMProvider(LLMProvider):
    def chat_completion(self, messages, **kwargs):
        # 实现自定义逻辑
        pass
```

---

## 性能优化

### 1. 缓存策略

- LLM 响应缓存
- 向量检索缓存
- 会话状态缓存

### 2. 并发处理

- 异步 I/O (asyncio)
- 多进程池
- 批量处理

### 3. 资源管理

- 连接池
- 内存限制
- 磁盘缓存

---

## 安全性

### 1. 认证授权

- JWT Token
- API Key
- RBAC 权限

### 2. 数据保护

- 敏感信息加密
- SQL 注入防护
- XSS 防护

### 3. 速率限制

- API 调用限流
- 成本控制
- 滥用检测

---

## 监控和日志

### 1. 性能监控

- 请求延迟
- Token 使用量
- 错误率
- 系统资源

### 2. 日志系统

- 结构化日志
- 日志级别控制
- 日志轮转
- 集中式日志

### 3. 告警机制

- 错误告警
- 性能告警
- 成本告警

---

## 部署架构

### 1. 单机部署

```
┌─────────────────┐
│  Agent Framework│
│  (All-in-One)   │
│  - Web UI       │
│  - API Server   │
│  - Database     │
│  - Vector Store │
└─────────────────┘
```

### 2. 分布式部署

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Web UI   │───▶│ API      │───▶│ LLM      │
│ (Nginx)  │    │ Gateway  │    │ Service  │
└──────────┘    └──────────┘    └──────────┘
                      │
                      ▼
                ┌──────────┐    ┌──────────┐
                │ Database │    │ Vector   │
                │ (SQLite) │    │ Store    │
                └──────────┘    └──────────┘
```

---

## 技术栈总结

| 层级 | 技术 |
|------|------|
| **Web 框架** | Flask 3.0+, Flask-SocketIO |
| **LLM** | OpenAI, vLLM, SiliconFlow, Xinference |
| **向量数据库** | Chroma, LanceDB, FAISS |
| **关系数据库** | SQLite |
| **缓存** | 内存缓存, 磁盘缓存 |
| **任务队列** | 内置异步任务系统 |
| **前端** | Jinja2, 响应式 CSS, Material Symbols |
| **Python 版本** | 3.10+ |

---

## 代码统计

- **Python 文件数：** 171
- **代码总行数：** 60,741
- **最大文件：** knowledge_base.py (1837 行)
- **API 模块数：** 26
- **页面模板数：** 20+
- **文档文件数：** 14

---

## 更多资源

- [API 参考文档](api_reference.md)
- [快速参考指南](quick_reference.md)
- [故障排查指南](troubleshooting.md)
- [用户工具指南](user_tools_guide.md)
- [迁移路线图](migration_roadmap.md)
