"""数字处理工具"""

TOOL_META = {
    "name": "sum_numbers",
    "description": "将逗号分隔的数字列表求和，例如 1,2,3",
}


def sum_numbers(numbers: str) -> str:
    """
    :param numbers: 逗号分隔的数字列表
    """
    try:
        values = [float(item.strip()) for item in numbers.split(",") if item.strip()]
        return str(sum(values))
    except Exception as e:
        return f"求和错误: {e}"
