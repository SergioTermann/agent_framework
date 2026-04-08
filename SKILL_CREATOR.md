# Skill Creator - 技能创建器

## 概述

Skill Creator 是一个可视化的技能创建和管理平台，允许用户通过图形界面创建、编辑、测试和分享自定义 AI 技能。

## 功能特性

### 1. 技能管理
- **创建技能**：通过可视化表单创建新技能
- **编辑技能**：修改现有技能的配置和提示词
- **删除技能**：移除不需要的技能
- **搜索过滤**：按名称、描述、标签搜索技能
- **分类浏览**：按类别（数据分析、文本处理、代码生成等）浏览

### 2. 技能配置

每个技能包含以下配置项：

- **基本信息**
  - 名称：技能的显示名称
  - 描述：技能功能说明
  - 图标：技能的图标（emoji）
  - 类别：技能所属分类
  - 标签：便于搜索的关键词

- **提示词模板**
  - 支持变量占位符（如 `{input}`, `{context}`）
  - 支持多行文本编辑
  - 实时预览效果

- **输入输出定义**
  - 输入参数 Schema（JSON Schema 格式）
  - 输出格式 Schema
  - 参数验证规则

- **示例数据**
  - 输入示例
  - 预期输出示例
  - 用于测试和文档

### 3. 技能测试

- **在线测试**：直接在界面中测试技能
- **输入验证**：自动验证输入是否符合 Schema
- **执行历史**：查看历史执行记录
- **性能统计**：执行时间、成功率等指标

### 4. 技能评分

- **用户评分**：1-5 星评分系统
- **评论反馈**：用户可以留下使用评论
- **平均评分**：显示技能的平均评分和评分人数

### 5. 技能分享

- **公开技能**：将技能设为公开，供其他用户使用
- **私有技能**：仅自己可见和使用
- **导出导入**：支持技能的导出和导入（JSON 格式）

## 技能分类

系统预设以下技能分类：

- **数据分析**：数据处理、统计分析、可视化
- **文本处理**：文本生成、摘要、翻译、情感分析
- **代码生成**：代码编写、调试、重构
- **图像处理**：图像分析、描述生成
- **业务流程**：工作流自动化、业务逻辑
- **知识问答**：问答系统、知识检索
- **创意写作**：文章、故事、诗歌创作
- **其他**：未分类的技能

## API 接口

### 技能管理 API

```
GET    /api/skills              # 获取技能列表
GET    /api/skills/{id}         # 获取技能详情
POST   /api/skills              # 创建新技能
PUT    /api/skills/{id}         # 更新技能
DELETE /api/skills/{id}         # 删除技能
```

### 技能执行 API

```
POST   /api/skills/{id}/execute # 执行技能
GET    /api/skills/{id}/history # 获取执行历史
```

### 技能评分 API

```
POST   /api/skills/{id}/rate    # 评分技能
GET    /api/skills/{id}/ratings # 获取评分列表
```

### 统计 API

```
GET    /api/skills/stats        # 获取统计信息
GET    /api/skills/categories   # 获取分类列表
```

## 使用示例

### 创建一个文本摘要技能

```json
{
  "name": "智能文本摘要",
  "description": "将长文本压缩为简洁的摘要",
  "category": "text-processing",
  "icon": "📝",
  "tags": ["摘要", "文本处理", "NLP"],
  "prompt_template": "请将以下文本总结为 {length} 字以内的摘要：\n\n{text}",
  "input_schema": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "需要摘要的文本"
      },
      "length": {
        "type": "integer",
        "description": "摘要长度限制",
        "default": 100
      }
    },
    "required": ["text"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "summary": {
        "type": "string",
        "description": "生成的摘要"
      }
    }
  },
  "examples": [
    {
      "input": {
        "text": "人工智能是计算机科学的一个分支...",
        "length": 50
      },
      "output": {
        "summary": "人工智能是模拟人类智能的技术，应用广泛。"
      }
    }
  ]
}
```

### 执行技能

```javascript
// 前端调用示例
async function executeSkill(skillId, input) {
  const response = await fetch(`/api/skills/${skillId}/execute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ input })
  });

  const result = await response.json();
  return result;
}

// 使用
const result = await executeSkill('skill-123', {
  text: '这是一段很长的文本...',
  length: 100
});
console.log(result.output.summary);
```

## 数据存储

技能数据存储在 SQLite 数据库中：

- **数据库文件**：`data/skills.db`
- **技能定义**：`skills` 表
- **执行历史**：`skill_executions` 表
- **评分记录**：`skill_ratings` 表

## 访问方式

1. **从门户进入**：`http://localhost:5000/portal` → 点击 "Skill Creator"
2. **直接访问**：`http://localhost:5000/skill-creator`

## 界面布局

### 主界面
- **左侧边栏**：分类导航、搜索框
- **中间区域**：技能卡片网格
- **右侧面板**：技能详情、编辑器、测试工具

### 技能卡片
- 图标和名称
- 简短描述
- 标签
- 评分和使用次数
- 快速操作按钮（编辑、测试、删除）

### 创建/编辑器
- 基本信息表单
- 提示词编辑器（支持语法高亮）
- Schema 编辑器（JSON 格式）
- 示例数据编辑
- 实时预览

### 测试面板
- 输入参数表单
- 执行按钮
- 输出结果显示
- 执行历史列表

## 技术实现

### 前端
- 纯 HTML + CSS + JavaScript
- 无框架依赖，轻量级
- 响应式设计
- 实时表单验证

### 后端
- Flask Blueprint
- SQLite 数据库
- RESTful API
- JSON Schema 验证

### 集成
- 与 Agent Framework 深度集成
- 可调用系统内置工具
- 支持与其他模块协作

## 最佳实践

### 编写好的提示词
1. **清晰明确**：明确说明任务目标
2. **结构化**：使用分段、列表等结构
3. **示例驱动**：提供输入输出示例
4. **变量占位**：使用 `{variable}` 标记可变部分

### 定义 Schema
1. **完整性**：定义所有必需和可选参数
2. **验证规则**：添加类型、格式、范围限制
3. **描述清晰**：为每个字段添加说明
4. **默认值**：为可选参数提供合理默认值

### 测试技能
1. **边界测试**：测试极端情况
2. **错误处理**：验证错误提示是否友好
3. **性能测试**：检查执行时间
4. **多样化输入**：使用不同类型的输入测试

## 扩展功能（规划中）

- [ ] 技能版本管理
- [ ] 技能市场（公开分享）
- [ ] 技能组合（链式调用）
- [ ] 可视化流程编排
- [ ] A/B 测试
- [ ] 性能优化建议
- [ ] 自动生成文档
- [ ] 批量导入导出
- [ ] 权限管理
- [ ] 使用统计分析

## 故障排查

### 技能执行失败
1. 检查输入是否符合 Schema
2. 验证提示词模板是否正确
3. 查看执行历史中的错误信息
4. 检查 LLM 配置是否正常

### 无法保存技能
1. 检查数据库文件权限
2. 验证 JSON Schema 格式
3. 确保必填字段已填写
4. 查看浏览器控制台错误

### 界面显示异常
1. 清除浏览器缓存
2. 检查 CSS 文件是否加载
3. 验证 API 响应格式
4. 查看网络请求状态

## 贡献指南

欢迎贡献新功能和改进：

1. Fork 项目
2. 创建功能分支
3. 提交代码
4. 发起 Pull Request

## 许可证

与 Agent Framework 主项目保持一致
