"""
Factor 4 ── 工具只是结构化输出
Factor 7 ── 用工具联系人类

工具的本质：LLM 输出一段 JSON，确定性代码解析并执行。
调度机制：简单的字典查表 + 函数调用，无框架黑盒。
内置人类交互工具：将"询问人类"也定义为一种工具，使控制流统一清晰。
"""

from __future__ import annotations

import inspect
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 中间件类型：接收 (tool_name, arguments, next_fn) → Any
ToolMiddleware = Callable[..., Any]


@dataclass
class ToolSpec:
    """工具规格说明 —— 告诉 LLM 工具的签名与语义"""

    name: str
    description: str
    parameters: dict[str, Any]       # JSON Schema
    handler: Callable | None = None  # 实际执行函数（None 表示由 Runner 特殊处理）
    concurrency_safe: bool = True    # 是否可并发执行（借鉴 Claude Code isConcurrencySafe）

    def to_llm_format(self) -> dict:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __repr__(self) -> str:
        return f"<ToolSpec name={self.name!r}>"


class ToolRegistry:
    """
    工具注册表 —— Factor 4 的实现。
    用字典查表替代框架的魔法调度，透明可控。
    """

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        self._middlewares: list[ToolMiddleware] = []

    # ── 注册方式 1：装饰器 ─────────────────────────────────────────────────────

    def register(
        self,
        name: str | None = None,
        description: str = "",
        parameters: dict | None = None,
        concurrency_safe: bool = True,
    ):
        """
        装饰器：注册一个普通函数为 Agent 工具。
        参数 schema 未指定时，从函数签名自动推断。

        :param concurrency_safe: 是否可安全并发执行（默认 True）。
            对于有副作用的工具（如写文件、修改数据库），应设为 False。
        """
        def decorator(fn: Callable) -> Callable:
            tool_name = name or fn.__name__
            schema = parameters or _infer_schema(fn)
            spec = ToolSpec(
                name=tool_name,
                description=description or (fn.__doc__ or "").strip().splitlines()[0],
                parameters=schema,
                handler=fn,
                concurrency_safe=concurrency_safe,
            )
            self._tools[tool_name] = spec
            fn._tool_spec = spec   # 方便外部查看
            return fn

        return decorator

    # ── 注册方式 2：直接添加 ToolSpec ──────────────────────────────────────────

    def add(self, spec: ToolSpec) -> None:
        """直接注册 ToolSpec（用于更精细的控制）"""
        self._tools[spec.name] = spec

    # ── 中间件 ────────────────────────────────────────────────────────────────

    def use(self, middleware: ToolMiddleware) -> None:
        """
        添加中间件。中间件签名：(name, arguments, next_fn) -> Any
        next_fn 调用下一个中间件或最终 handler。

        用法：
            def logging_mw(name, arguments, next_fn):
                print(f"调用工具: {name}")
                result = next_fn(name, arguments)
                print(f"工具结果: {result}")
                return result

            registry.use(logging_mw)
        """
        self._middlewares.append(middleware)

    # ── 调度（Factor 4 核心）──────────────────────────────────────────────────

    def dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        """
        Factor 4: 工具调度 = 字典查表 + 中间件链 + 调用。
        LLM 决定做什么（结构化 JSON），代码决定怎么做（确定性执行）。
        """
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"未注册的工具: '{name}'")
        if spec.handler is None:
            raise ValueError(f"工具 '{name}' 没有绑定 handler（由 Runner 特殊处理）")

        # 安全过滤：只保留 schema 中声明的参数，丢弃 LLM 注入的未知 key
        allowed_keys = set(spec.parameters.get("properties", {}).keys())
        if allowed_keys:
            arguments = {k: v for k, v in arguments.items() if k in allowed_keys}

        # 构建中间件链
        def final_handler(_name: str, _args: dict[str, Any]) -> Any:
            return spec.handler(**_args)

        handler = final_handler
        for mw in reversed(self._middlewares):
            prev = handler
            def make_next(m, p):
                return lambda n, a: m(n, a, p)
            handler = make_next(mw, prev)

        return handler(name, arguments)

    # ── 查询 ────────────────────────────────────────────────────────────────

    def get(self, name: str) -> ToolSpec | None:
        """按名称获取 ToolSpec"""
        return self._tools.get(name)

    def names(self) -> list[str]:
        """返回所有已注册工具名称"""
        return list(self._tools.keys())

    def to_llm_format(self) -> list[dict]:
        """获取所有工具的 LLM 格式列表"""
        return [spec.to_llm_format() for spec in self._tools.values()]

    def describe(self) -> str:
        """生成工具描述字符串，用于注入 Prompt（Factor 2）"""
        if not self._tools:
            return "（暂无自定义工具）"
        lines = [f"- {spec.name}: {spec.description}" for spec in self._tools.values()]
        return "\n".join(lines)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())

    def __repr__(self) -> str:
        names = list(self._tools.keys())
        return f"<ToolRegistry tools={names}>"


# ─── Factor 7: 内置人类交互工具 ────────────────────────────────────────────────
# 把"联系人类"定义为工具，LLM 始终输出结构化 JSON，控制流清晰统一。

HUMAN_APPROVAL_TOOL = ToolSpec(
    name="request_human_approval",
    description=(
        "请求人类审批某项危险或不可逆的操作。"
        "调用后 Agent 将立即暂停，等待人类通过 /resume 接口响应后继续。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "action":     {"type": "string", "description": "需要审批的操作描述"},
            "reason":     {"type": "string", "description": "为什么需要人类审批"},
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "操作风险等级",
            },
        },
        "required": ["action", "reason"],
    },
    handler=None,   # 由 Runner 特殊处理，触发 PAUSE 信号
)

REQUEST_INFO_TOOL = ToolSpec(
    name="request_more_information",
    description=(
        "当信息不足以安全完成任务时，向用户提问。"
        "调用后 Agent 暂停，等待用户通过 /resume 接口回答后继续。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "需要用户回答的问题"},
            "context":  {"type": "string", "description": "为什么需要此信息"},
        },
        "required": ["question"],
    },
    handler=None,
)

DONE_TOOL = ToolSpec(
    name="done",
    description="任务完成时调用此工具，汇报最终结果并结束 Agent 循环。",
    parameters={
        "type": "object",
        "properties": {
            "result":  {"type": "string", "description": "任务完成结果摘要"},
            "success": {"type": "boolean", "description": "任务是否成功"},
        },
        "required": ["result"],
    },
    handler=None,
)

# 内置工具集（不走用户注册的 ToolRegistry，由 Runner 统一处理）
BUILTIN_TOOLS: list[ToolSpec] = [
    HUMAN_APPROVAL_TOOL,
    REQUEST_INFO_TOOL,
    DONE_TOOL,
]

# 触发暂停的内置工具名称集合
PAUSE_TOOL_NAMES: set[str] = {
    HUMAN_APPROVAL_TOOL.name,
    REQUEST_INFO_TOOL.name,
}


# ─── 工具 Schema 自动推断 ──────────────────────────────────────────────────────

_PY_TO_JSON_TYPE: dict[type, str] = {
    str:   "string",
    int:   "integer",
    float: "number",
    bool:  "boolean",
    list:  "array",
    dict:  "object",
}


def _infer_schema(fn: Callable) -> dict:
    """
    从函数签名自动推断 JSON Schema（轻量实现）。
    支持从 docstring 中提取 :param xxx: 格式的参数描述。
    """
    sig = inspect.signature(fn)
    doc = fn.__doc__ or ""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        py_type = param.annotation
        json_type = _PY_TO_JSON_TYPE.get(py_type, "string")
        prop: dict[str, Any] = {"type": json_type}

        # 从 docstring 提取参数描述
        m = re.search(rf":param\s+{param_name}\s*:\s*(.+)", doc)
        if m:
            prop["description"] = m.group(1).strip()

        properties[param_name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
