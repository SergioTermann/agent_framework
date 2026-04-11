<p align="center">
  <h1 align="center">Agent Framework Platform</h1>
  <p align="center">
    基于 12-Factor 设计原则的企业级 AI Agent 开发平台
    <br />
    <strong>原生 Python · 零框架依赖 · 白盒控制流 · 生产就绪</strong>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/docker-ready-blue?logo=docker&logoColor=white" alt="Docker Ready">
  <img src="https://img.shields.io/badge/LLM-OpenAI%20%7C%20vLLM%20%7C%20SiliconFlow-orange" alt="LLM Support">
</p>

---

## 概述

Agent Framework 是一个功能完整的 AI Agent 开发与运营平台，覆盖 **构建 → 编排 → 部署 → 监控** 全链路。核心 Agent 引擎基于 [12-Factor Agent](https://github.com/humanlayer/12-factor-agents) 设计理念，以原生 Python 实现——不包裹 LangChain / LlamaIndex 等外部框架，所有控制流透明可审计。

**适用场景：** 风电运维智能诊断、企业知识管理、多 Agent 协作、复杂工作流自动化。

## 核心特性

| 模块 | 说明 |
|---|---|
| **Agent 引擎** | 基于 12-Factor 设计，Builder 链式 API、不可变线程状态、信号驱动控制流 |
| **工作流编排** | 可视化拖拽编辑器，支持条件分支 / 循环 / 并行，DAG 拓扑排序执行 |
| **向量知识库 (RAG)** | 多格式文档解析（PDF/Word/Excel/PPT/Markdown），Chroma 向量存储，混合检索 + 重排序 |
| **多层记忆系统** | 情景记忆 / 语义记忆 / 程序性记忆 / 工作记忆，重要度评分与自动裁剪 |
| **因果推理引擎** | 因果链分析、反事实推理、根因定位、干预评估、交互式可视化 |
| **基础设施** | API Key 管理、限流、JWT 认证 / RBAC 权限、成本追踪、性能监控 |
| **Web 平台** | Flask + SocketIO 实时通信，20+ 页面模板，响应式 UI |

## 架构一览

```
src/agent_framework/
├── agent/          # 12-Factor Agent 引擎
│   ├── builder.py      # 链式 AgentBuilder API
│   ├── runner.py       # 信号驱动执行引擎
│   ├── llm.py          # LLM 多供应商抽象 (OpenAI / vLLM / SiliconFlow / Xinference)
│   ├── thread.py       # 不可变线程状态
│   ├── context.py      # 上下文窗口管理
│   ├── prompts.py      # Prompt 模板系统
│   ├── store.py        # 线程持久化 (FileSystem / SQLite)
│   └── callbacks.py    # 回调与 Token 计数
├── workflow/       # 工作流引擎 (DAG 编排)
├── vector_db/      # 向量知识库 & RAG
├── memory/         # 多层记忆系统
├── causal/         # 因果推理引擎
├── reasoning/      # 推理与重排序
├── tools/          # 内置工具集 (天气/搜索/计算/因果分析...)
├── infra/          # API Key / 限流 / 监控 / 缓存 / 事件桥
├── core/           # 认证 (JWT) / RBAC / 统一配置
├── platform/       # 插件与扩展系统
├── api/            # 45+ REST API Blueprint
├── web/            # Flask + SocketIO Web 服务
└── templates/      # 20+ 页面模板
```

## 快速开始

### 环境要求

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (推荐) 或 pip

### 1. 安装

```bash
git clone <repo-url> && cd agent_framework

# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

可选重型依赖按需安装：

```bash
pip install sentence-transformers opencv-python-headless pytesseract redis pandas
```

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 LLM API 配置：

**SiliconFlow（推荐）：**
```env
SILICONFLOW_API_KEY=your_api_key_here
DEFAULT_MODEL=Qwen/Qwen3-VL-32B-Instruct
BASE_URL=https://api.siliconflow.cn/v1
SECRET_KEY=your-secret-key-change-in-production
```

**本地 vLLM：**
```env
LLM_PROVIDER=vllm
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_API_KEY=
SECRET_KEY=your-secret-key-change-in-production
```

<details>
<summary>vLLM 启动示例</summary>

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --host 127.0.0.1 \
  --port 8000
```
</details>

### 3. 启动

```bash
uv run agent-framework-web
```

本地仓库未安装为可执行脚本时，也可以直接运行：

```bash
python start_app.py
```

运行 harness 自检：

```bash
uv run agent-framework-doctor --format text

# 或直接在仓库里运行
python doctor.py --format json
```

### 4. 访问

| 页面 | 地址 |
|---|---|
| 门户首页 | http://localhost:5000 |
| 用户入口 | http://localhost:5000/user |
| 风电运维助手 | http://localhost:5000/maintenance-assistant |
| 开发控制台 | http://localhost:5000/developer |
| 工作流编辑器 | http://localhost:5000/workflow |
| 知识库管理 | http://localhost:5000/knowledge |
| 应用管理 | http://localhost:5000/apps |
| 管理后台 | http://localhost:5000/dashboard |
| 数据分析 | http://localhost:5000/analytics |
| 系统设置 | http://localhost:5000/settings |
| API 文档 | http://localhost:5000/api/docs |
| 系统状态 | http://localhost:5000/system-status |

### 5. 健康检查与自检

| 能力 | 地址 |
|---|---|
| Liveness | http://localhost:5000/health |
| Readiness | http://localhost:5000/health/ready |
| 系统状态 JSON | http://localhost:5000/api/system/status |
| Readiness JSON | http://localhost:5000/api/system/readiness |
| OpenAPI JSON | http://localhost:5000/api/openapi.json |

## Docker 部署

### 单服务

```bash
docker build -t agent-framework .
docker run --rm -p 5000:5000 --env-file .env agent-framework
```

### 完整栈 (docker-compose)

包含 ChromaDB + Redis + PostgreSQL + Nginx：

```bash
docker compose up -d
```

## 代码示例

### 创建一个带工具的 Agent

```python
from agent_framework.agent import AgentBuilder

builder = AgentBuilder().with_openai(api_key="sk-...")

@builder.tool(description="查询天气")
def get_weather(city: str) -> str:
    return f"{city}: 晴天 22°C"

runner = builder.build()
thread = runner.launch("北京今天天气怎么样？")
```

### 使用本地 vLLM

```python
from agent_framework.agent import AgentBuilder

builder = AgentBuilder().with_vllm(
    model="Qwen/Qwen2.5-7B-Instruct",
    base_url="http://127.0.0.1:8000/v1",
)

runner = builder.build()
thread = runner.launch("帮我分析一下这段日志")
```

### 工作流 API

```bash
# 创建工作流
curl -X POST http://localhost:5000/api/workflows/ \
  -H "Content-Type: application/json" \
  -d '{"name": "故障诊断流程"}'

# 执行工作流
curl -X POST http://localhost:5000/api/workflows/{id}/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"user_input": "风机振动异常"}}'
```

### 知识库 API

```bash
# 创建知识库
curl -X POST http://localhost:5000/api/knowledge/ \
  -H "Content-Type: application/json" \
  -d '{"name": "运维手册", "embedding_type": "simple"}'

# 语义检索
curl -X POST http://localhost:5000/api/knowledge/{kb_id}/search \
  -H "Content-Type: application/json" \
  -d '{"query": "齿轮箱异响处理方案", "top_k": 5}'
```

## 12-Factor Agent 设计原则

本框架的 Agent 引擎遵循 12 条设计因子：

| # | 原则 | 实现 |
|---|---|---|
| 1 | 自然语言 → 工具调用 | LLM 原生 function calling |
| 2 | 拥有你的 Prompt | 模板系统，完全可控 |
| 3 | 上下文工程 | 智能窗口管理与消息构建 |
| 4 | 工具即结构化输出 | 强类型工具注册与校验 |
| 5 | 统一 LLM 与 Agent 状态 | 不可变 Thread 对象 |
| 6 | 可暂停 / 可恢复 | 信号驱动，支持中断与续接 |
| 7 | 联系真实世界 | Webhook & HTTP 节点 |
| 8 | 自带"后退"按钮 | 线程历史与状态回滚 |
| 9 | 错误压缩入上下文 | 错误转化为 LLM 可读消息 |
| 10 | 小而专注的 Agent | 模块化 Agent 组合 |
| 11 | 无状态 Reducer | 确定性状态转移 |
| 12 | 预加载上下文 | 检索增强的上下文注入 |

## 技术栈

| 类别 | 技术 |
|---|---|
| Web 框架 | Flask 3.0+, Flask-SocketIO 5.3+ |
| LLM 接口 | OpenAI-compatible API (SiliconFlow / vLLM / Xinference / Ollama) |
| 向量数据库 | ChromaDB 0.5+ |
| 文档解析 | PyPDF2, python-docx, openpyxl, python-pptx, BeautifulSoup4 |
| 图计算 | NetworkX 3.2+ |
| 可视化 | Matplotlib, Plotly |
| 认证 | PyJWT, Werkzeug |
| 性能加速 | Numba (JIT), Rust 扩展 |
| 容器化 | Docker, docker-compose |
| 包管理 | uv / hatchling |

## 项目结构

```
agent_framework/
├── src/agent_framework/   # 核心源码 (145 模块, ~49,000 行)
├── plugins/               # 插件目录
├── rust_extensions/        # Rust 性能扩展
├── go_services/            # Go 微服务 (任务执行器)
├── data/                   # 数据存储 (知识库/工作流/对话)
├── pyproject.toml          # 依赖与构建配置
├── Dockerfile              # 容器镜像
├── docker-compose.yml      # 完整栈编排
└── .env.example            # 环境变量模板
```

## 路线图

- [ ] Swagger / OpenAPI 文档生成
- [ ] 多 Agent 协作优化
- [ ] 插件市场
- [ ] 团队协作与权限精细化
- [ ] 企业版功能

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

[MIT License](LICENSE)

## macOS Quick Start

On macOS you can start the project directly with the same Python entrypoint:

```bash
uv sync
cp .env.example .env
uv run python start_app.py
```

If you prefer a local virtualenv instead of `uv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 start_app.py
```

For Finder-based startup on macOS, use `start.command`.

Notes:

- `--with-gateway` and `--with-go-control-plane` require Go to be installed on macOS because the launcher will build the local Go binaries for the current platform.
- If an old Go binary from another platform is present, `start_app.py` now rebuilds it automatically when startup detects an exec-format or permission mismatch.
