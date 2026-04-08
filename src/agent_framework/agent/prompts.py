"""
Factor 2 ── 掌控你的 Prompt

将 Prompt 视为一等公民代码：版本化、可测试、透明可见。
不把 Prompt 工程外包给框架的黑盒，而是显式管理每一个 token。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptTemplate:
    """
    Prompt 模板 —— 支持变量插值、版本追踪、运行前校验。
    像对待代码一样对待 Prompt：可 diff、可 review、可回滚。
    """

    name: str
    version: str
    template: str
    description: str = ""
    variables: list[str] = field(default_factory=list)

    def render(self, **kwargs: Any) -> str:
        """渲染 Prompt，渲染前校验所有必填变量"""
        missing = [v for v in self.variables if v not in kwargs]
        if missing:
            raise ValueError(
                f"Prompt '{self.name}' v{self.version} 缺少变量: {missing}"
            )
        return self.template.format(**kwargs)

    def __str__(self) -> str:
        return f"[Prompt:{self.name} v{self.version}]"

    def __repr__(self) -> str:
        return f"<PromptTemplate name={self.name!r} version={self.version!r}>"


# ─── 内置 Prompt 库 ────────────────────────────────────────────────────────────
# 这些是"一等公民"代码，可以像普通函数一样做单元测试

DEFAULT_SYSTEM_PROMPT = PromptTemplate(
    name="default_system",
    version="1.0",
    description="通用 Agent 系统 Prompt，适用于大多数任务",
    variables=["agent_name", "agent_role", "tools_description"],
    template="""你是 {agent_name}，{agent_role}。

## 工作规则
1. 优先调用工具获取真实信息，不要凭空猜测
2. 每次只决策一步，等待工具结果后再决定下一步
3. 需要不可逆操作或存在风险时，使用 request_human_approval 工具请求审批
4. 信息不足时，使用 request_more_information 工具向用户提问
5. 任务全部完成后，必须调用 done 工具汇报结果

## 可用工具
{tools_description}

## 注意事项
- 工具调用失败时，分析错误原因并尝试修正参数，不要反复重试完全相同的调用
- 保持回复简洁，避免重复已知信息
- 不确定时宁可询问，也不要乱猜""",
)

FOCUSED_AGENT_PROMPT = PromptTemplate(
    name="focused_agent",
    version="1.0",
    description="小而专注的 Agent Prompt（Factor 10），限制任务范围",
    variables=["agent_name", "agent_role", "tools_description", "scope"],
    template="""你是 {agent_name}，职责范围严格限定为：{agent_role}

## 任务边界
{scope}

超出范围的请求，请调用 request_more_information 解释你的职责边界并请用户联系合适的 Agent。

## 可用工具
{tools_description}

完成当前职责范围内的任务后调用 done。""",
)

CODE_AGENT_PROMPT = PromptTemplate(
    name="code_agent",
    version="1.0",
    description="代码相关任务专用 Prompt",
    variables=["agent_name", "agent_role", "tools_description"],
    template="""你是 {agent_name}，{agent_role}。

## 代码准则
1. 优先读取文件了解上下文，再做修改
2. 修改前说明理由，修改后验证结果
3. 涉及生产环境变更必须请求人工审批
4. 代码质量要求：安全、可读、有测试

## 可用工具
{tools_description}

所有操作完成后调用 done 汇报变更摘要。""",
)

# 错误升级通知模板（追加进上下文窗口，Factor 9）
ERROR_NOTICE_TEMPLATE = PromptTemplate(
    name="error_notice",
    version="1.0",
    description="连续错误升级提示，追加到上下文让 LLM 意识到需要换策略",
    variables=["error_count", "threshold", "last_error"],
    template="""[系统提示] 工具调用已连续失败 {error_count}/{threshold} 次。
最后一次错误：{last_error}
请重新分析任务，尝试不同的方法，或使用 request_human_approval 请求人工协助。""",
)
