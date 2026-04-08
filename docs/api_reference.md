# API 参考文档

本文档提供 Agent Framework 所有 API 端点的完整参考。

## 目录

- [核心功能 API](#核心功能-api)
- [工作流 API](#工作流-api)
- [知识库 API](#知识库-api)
- [监控与管理 API](#监控与管理-api)
- [工具与配置 API](#工具与配置-api)

---

## 核心功能 API

### 1. Agent API (`/api/agent`)
管理 Agent 的创建、配置和执行。

**端点：**
- `POST /api/agent/create` - 创建新 Agent
- `GET /api/agent/{agent_id}` - 获取 Agent 信息
- `POST /api/agent/{agent_id}/run` - 运行 Agent
- `DELETE /api/agent/{agent_id}` - 删除 Agent

### 2. 对话 API (`/api/conversation`)
管理对话会话和消息历史。

**端点：**
- `POST /api/conversation/create` - 创建新对话
- `GET /api/conversation/{conversation_id}` - 获取对话详情
- `POST /api/conversation/{conversation_id}/message` - 发送消息
- `GET /api/conversation/{conversation_id}/history` - 获取历史记录

### 3. 提示词 API (`/api/prompts`)
管理提示词模板库。

**端点：**
- `GET /api/prompts` - 列出所有提示词
- `POST /api/prompts` - 创建提示词
- `PUT /api/prompts/{prompt_id}` - 更新提示词
- `DELETE /api/prompts/{prompt_id}` - 删除提示词

### 4. 技能 API (`/api/skills`)
创建和管理可复用的技能。

**端点：**
- `GET /api/skills` - 列出所有技能
- `POST /api/skills` - 创建技能
- `POST /api/skills/{skill_id}/execute` - 执行技能
- `GET /api/skills/{skill_id}/history` - 获取执行历史

---

## 工作流 API

### 5. 工作流 API (`/api/workflow`)
基础工作流编排功能。

**端点：**
- `POST /api/workflow/create` - 创建工作流
- `POST /api/workflow/{workflow_id}/execute` - 执行工作流
- `GET /api/workflow/{workflow_id}/status` - 查询状态

### 6. 高级工作流 API (`/api/workflow-advanced`)
高级工作流编排，支持复杂节点和条件分支。

**端点：**
- `POST /api/workflow-advanced/create` - 创建高级工作流
- `POST /api/workflow-advanced/{workflow_id}/validate` - 验证工作流
- `POST /api/workflow-advanced/{workflow_id}/execute` - 执行工作流

### 7. 异步任务 API (`/api/async-tasks`)
管理长时间运行的异步任务。

**端点：**
- `POST /api/async-tasks/submit` - 提交任务
- `GET /api/async-tasks/{task_id}` - 查询任务状态
- `DELETE /api/async-tasks/{task_id}` - 取消任务

---

## 知识库 API

### 8. 知识库 API (`/api/knowledge`)
管理知识库和文档检索。

**端点：**
- `POST /api/knowledge/add` - 添加文档
- `POST /api/knowledge/search` - 搜索文档
- `DELETE /api/knowledge/{doc_id}` - 删除文档

### 9. 文档 API (`/api/documents`)
文档上传和管理。

**端点：**
- `POST /api/documents/upload` - 上传文档
- `GET /api/documents` - 列出文档
- `GET /api/documents/{doc_id}` - 获取文档详情
- `DELETE /api/documents/{doc_id}` - 删除文档

### 10. 检索 API (`/api/retrieval`)
高级检索和向量搜索。

**端点：**
- `POST /api/retrieval/search` - 向量搜索
- `POST /api/retrieval/hybrid` - 混合搜索
- `POST /api/retrieval/rerank` - 重排序结果

---

## 监控与管理 API

### 11. 监控 API (`/api/monitoring`)
系统监控和性能指标。

**端点：**
- `GET /api/monitoring/metrics` - 获取系统指标
- `GET /api/monitoring/health` - 健康检查
- `GET /api/monitoring/services` - 服务状态

### 12. 日志 API (`/api/logs`)
日志查询和管理。

**端点：**
- `GET /api/logs` - 查询日志
- `GET /api/logs/{log_id}` - 获取日志详情
- `DELETE /api/logs` - 清理日志

### 13. 协作 API (`/api/collaboration`)
团队协作和共享功能。

**端点：**
- `GET /api/collaboration/teams` - 列出团队
- `POST /api/collaboration/share` - 共享资源
- `GET /api/collaboration/activity` - 获取活动记录

---

## 工具与配置 API

### 14. 配置预设 API (`/api/config-presets`)
管理配置预设模板。

**端点：**
- `GET /api/config-presets` - 列出预设
- `POST /api/config-presets` - 创建预设
- `PUT /api/config-presets/{preset_id}` - 更新预设
- `DELETE /api/config-presets/{preset_id}` - 删除预设

### 15. HTTP 请求 API (`/api/http-request`)
HTTP 请求工具和测试。

**端点：**
- `POST /api/http-request/execute` - 执行 HTTP 请求
- `GET /api/http-request/history` - 获取请求历史

### 16. 扩展 API (`/api/extensions`)
插件和扩展管理。

**端点：**
- `GET /api/extensions` - 列出扩展
- `POST /api/extensions/install` - 安装扩展
- `POST /api/extensions/{ext_id}/enable` - 启用扩展
- `POST /api/extensions/{ext_id}/disable` - 禁用扩展

---

## 高级功能 API

### 17. A/B 测试 API (`/api/ab-testing`)
实验管理和效果对比。

**端点：**
- `POST /api/ab-testing/experiments` - 创建实验
- `POST /api/ab-testing/experiments/{exp_id}/variants` - 添加变体
- `GET /api/ab-testing/experiments/{exp_id}/results` - 获取结果

### 18. 推理 API (`/api/reasoning`)
高级推理和思维链。

**端点：**
- `POST /api/reasoning/chain-of-thought` - 思维链推理
- `POST /api/reasoning/tree-search` - 树搜索推理
- `POST /api/reasoning/analyze` - 分析推理过程

### 19. 发布 API (`/api/publish`)
应用发布和版本管理。

**端点：**
- `POST /api/publish/release` - 创建发布
- `GET /api/publish/releases` - 列出发布
- `POST /api/publish/deploy` - 部署应用

### 20. 多模态 API (`/api/multimodal`)
多模态内容处理。

**端点：**
- `POST /api/multimodal/process` - 处理多模态输入
- `POST /api/multimodal/image` - 图像处理
- `POST /api/multimodal/audio` - 音频处理
- `POST /api/multimodal/video` - 视频处理

---

## 其他 API

### 21. 插件市场 API (`/api/plugins`)
插件市场和管理。

### 22. 网关 API (`/api/gateway`)
统一网关和路由。

### 23. 因果推理 API (`/api/causal`)
因果关系分析。

### 24. 代码片段 API (`/api/code-snippet`)
代码片段管理。

### 25. 本体 API (`/api/ontology`)
知识图谱和本体管理。

### 26. 统一聊天 API (`/api/unified-chat`)
统一聊天接口。

---

## 认证

所有 API 端点都需要认证。在请求头中包含：

```
Authorization: Bearer <your_token>
```

## 错误处理

API 使用标准 HTTP 状态码：

- `200` - 成功
- `400` - 请求错误
- `401` - 未授权
- `404` - 未找到
- `500` - 服务器错误

错误响应格式：

```json
{
  "error": "错误描述",
  "code": "ERROR_CODE",
  "details": {}
}
```

## 速率限制

- 默认：100 请求/分钟
- 认证用户：1000 请求/分钟

## 更多信息

- [快速开始指南](../README.md)
- [用户工具指南](user_tools_guide.md)
- [架构文档](migration_target_architecture.md)
