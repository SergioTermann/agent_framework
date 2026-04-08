# 用户工具管理和选择机制

## 概述

用户可以在运行时创建、管理并执行自定义 HTTP 工具，无需修改代码或重启服务。

## 核心特性

- **动态创建工具** - 通过 REST API 创建工具，立即生效
- **HTTP 执行器** - 支持 GET/POST/PUT/DELETE，URL 模板变量，Bearer/API Key 认证
- **密钥管理** - 安全存储 API 密钥，不在接口暴露
- **Chat 模式 function calling** - Chat 模式现在支持工具调用（最多 5 轮）
- **Agent 模式集成** - 用户工具自动纳入 Agent 工具池

## API 端点

### 1. 列出所有工具
```http
GET /api/tools?user_id=wind_admin
```

返回 builtin + plugin + user 工具，带 `source` 标记。

### 2. 创建工具
```http
POST /api/tools
Content-Type: application/json

{
  "name": "query_scada",
  "description": "查询 SCADA 系统风机数据",
  "user_id": "wind_admin",
  "parameters": {
    "type": "object",
    "properties": {
      "turbine_id": {"type": "string", "description": "风机编号"},
      "metric": {"type": "string", "description": "指标名称"}
    },
    "required": ["turbine_id"]
  },
  "execution_config": {
    "url": "https://scada.example.com/api/v1/turbines/{turbine_id}/metrics",
    "method": "GET",
    "headers": {"Accept": "application/json"},
    "timeout": 15,
    "auth_type": "bearer",
    "auth_secret_key": "scada_token"
  },
  "tags": ["scada", "wind"]
}
```

### 3. 存储密钥
```http
POST /api/tools/secrets
Content-Type: application/json

{
  "key": "scada_token",
  "value": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user_id": "wind_admin"
}
```

### 4. 测试工具
```http
POST /api/tools/<tool_id>/test
Content-Type: application/json

{
  "params": {
    "turbine_id": "WT-001",
    "metric": "power"
  }
}
```

### 5. 更新工具
```http
PUT /api/tools/<tool_id>
Content-Type: application/json

{
  "description": "查询 SCADA 系统风机数据 v2",
  "enabled": true
}
```

### 6. 删除工具
```http
DELETE /api/tools/<tool_id>
```

## 使用场景

### Chat 模式调用工具
```http
POST /api/unified/chat
Content-Type: application/json

{
  "message": "查一下 WT-001 的实时功率",
  "user_id": "wind_admin",
  "metadata": {
    "enable_tools": true,
    "allowed_tools": ["query_scada", "calculate"],
    "toolsets": ["basic"]
  }
}
```

**流程：**
1. LLM 看到用户工具 `query_scada` + builtin 工具
2. LLM 决定调用 `query_scada(turbine_id="WT-001")`
3. 系统执行 HTTP 请求到 SCADA API
4. 结果返回给 LLM
5. LLM 基于结果生成最终回复

### Agent 模式自动集成
```http
POST /api/unified/chat
Content-Type: application/json

{
  "message": "分析 WT-001 的故障原因",
  "user_id": "wind_admin",
  "use_agent": true,
  "metadata": {
    "toolsets": ["wind_maintenance"]
  }
}
```

用户工具自动加入 Agent 工具池，无需额外配置。

## 执行配置

### URL 模板
```json
{
  "url": "https://api.example.com/users/{user_id}/posts/{post_id}",
  "method": "GET"
}
```

调用 `tool(user_id="123", post_id="456")` → `GET https://api.example.com/users/123/posts/456`

### Body 模板
```json
{
  "url": "https://api.example.com/alerts",
  "method": "POST",
  "body_template": "{\"message\": \"{text}\", \"level\": \"{level}\"}"
}
```

调用 `tool(text="故障", level="critical")` → `POST {"message": "故障", "level": "critical"}`

### 认证

**Bearer Token:**
```json
{
  "auth_type": "bearer",
  "auth_secret_key": "my_token"
}
```
→ `Authorization: Bearer <secret_value>`

**API Key:**
```json
{
  "auth_type": "api_key",
  "auth_secret_key": "my_key"
}
```
→ `X-API-Key: <secret_value>`

## 安全限制

- **Timeout 硬上限**: 60 秒
- **响应截断**: 8000 字符
- **密钥隔离**: 密钥值仅在 `POST /api/tools/secrets` 写入，不在其他接口返回

## 数据库

SQLite 存储在 `data/user_tools.db`：

**user_tools 表:**
- tool_id (PK)
- name, description, parameters (JSON)
- execution_type, execution_config (JSON)
- user_id, enabled, created_at, updated_at, tags (JSON)
- UNIQUE(name, user_id)

**user_tool_secrets 表:**
- secret_key (PK)
- secret_value, user_id, created_at

## 示例：风电运维场景

```python
# 1. 创建 SCADA 查询工具
POST /api/tools
{
  "name": "query_scada",
  "description": "查询风机实时数据",
  "user_id": "wind_admin",
  "parameters": {
    "type": "object",
    "properties": {
      "turbine_id": {"type": "string"}
    },
    "required": ["turbine_id"]
  },
  "execution_config": {
    "url": "https://scada.internal/api/turbines/{turbine_id}",
    "method": "GET",
    "auth_type": "bearer",
    "auth_secret_key": "scada_token"
  }
}

# 2. 创建告警工具
POST /api/tools
{
  "name": "send_wechat_alert",
  "description": "发送企业微信告警",
  "user_id": "wind_admin",
  "parameters": {
    "type": "object",
    "properties": {
      "message": {"type": "string"}
    },
    "required": ["message"]
  },
  "execution_config": {
    "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
    "method": "POST",
    "body_template": "{\"msgtype\": \"text\", \"text\": {\"content\": \"{message}\"}}",
    "auth_type": "none"
  }
}

# 3. 存储密钥
POST /api/tools/secrets
{"key": "scada_token", "value": "eyJhbGci...", "user_id": "wind_admin"}

# 4. Chat 调用
POST /api/unified/chat
{
  "message": "WT-001 功率异常，查一下数据并发告警",
  "user_id": "wind_admin",
  "metadata": {"enable_tools": true}
}
```

LLM 会：
1. 调用 `query_scada(turbine_id="WT-001")`
2. 分析数据
3. 调用 `send_wechat_alert(message="WT-001 功率异常：...")`
4. 返回处理结果

## 工具选择器

**allowed_tools** - 白名单
```json
{"metadata": {"allowed_tools": ["query_scada", "calculate"]}}
```

**blocked_tools** - 黑名单
```json
{"metadata": {"blocked_tools": ["web_search"]}}
```

**toolsets** - 预设集合
```json
{"metadata": {"toolsets": ["wind_maintenance"]}}
```

预设包含：`none`, `all`, `basic`, `text`, `research`, `causal`, `travel`, `wind_maintenance`

## 工具池优先级

1. Builtin 工具（`tools/` 目录自动发现）
2. Plugin 工具（扩展系统）
3. User 工具（按 `user_id` 加载）

同名工具：User > Plugin > Builtin

## 故障排查

**工具未出现在列表：**
- 检查 `enabled=true`
- 检查 `user_id` 匹配
- 检查数据库 `data/user_tools.db`

**执行失败：**
- 检查 URL 模板变量是否匹配参数名
- 检查密钥是否存储（`POST /api/tools/secrets`）
- 检查目标 API 是否可达（timeout 默认 30s）

**Chat 模式不调用工具：**
- 确保 `metadata.enable_tools = true`
- 检查 LLM 是否支持 function calling
- 查看响应中的 `tool_calls` 字段

## 限制

- 当前仅支持 HTTP 执行器（未来可扩展 Python/Shell）
- Chat 模式最多 5 轮工具调用（防止死循环）
- 响应截断 8000 字符（防止 token 溢出）
