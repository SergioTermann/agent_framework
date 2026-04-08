"""文本处理工具集"""

TOOL_META = {
    "name": "to_uppercase",
    "description": "将文本转换为大写",
}


def to_uppercase(text: str) -> str:
    """
    :param text: 输入文本
    """
    return text.upper()


# ── 额外工具（同文件多工具，通过 EXTRA_TOOLS 导出）──

EXTRA_TOOLS = [
    {
        "name": "to_lowercase",
        "description": "将文本转换为小写",
        "handler": lambda text: text.lower(),
    },
    {
        "name": "analyze_text",
        "description": "统计文本信息，包括字符数、单词数、行数",
        "handler": None,  # 下方定义
    },
    {
        "name": "split_text",
        "description": "将文本按分隔符拆分成列表，格式: 文本|分隔符",
        "handler": None,
    },
]


def analyze_text(text: str) -> str:
    """
    :param text: 输入文本
    """
    lines = text.splitlines() or [text]
    words = text.split()
    chars = len(text)
    return f"字符数: {chars}\n单词数: {len(words)}\n行数: {len(lines)}"


def split_text(payload: str) -> str:
    """
    :param payload: 格式为 '文本|分隔符'
    """
    try:
        text, separator = payload.split("|", 1)
        parts = [part.strip() for part in text.split(separator)]
        return "\n".join(f"{idx + 1}. {part}" for idx, part in enumerate(parts))
    except ValueError:
        return "格式错误: 请使用 '文本|分隔符'"


# 绑定 handler
EXTRA_TOOLS[1]["handler"] = analyze_text
EXTRA_TOOLS[2]["handler"] = split_text
