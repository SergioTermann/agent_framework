"""待办事项工具"""

TOOL_META = {
    "name": "create_todo_list",
    "description": "生成待办事项清单，按句号或换行拆分",
}


def create_todo_list(text: str) -> str:
    """
    :param text: 待办事项文本
    """
    items = []
    for part in text.replace("。", "\n").splitlines():
        part = part.strip(" -•\t")
        if part:
            items.append(part)
    if not items:
        return "未提取到待办事项"
    return "\n".join(f"[ ] {item}" for item in items)
