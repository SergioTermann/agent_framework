"""评分等级工具"""

TOOL_META = {
    "name": "score_grade",
    "description": "根据数字评分给出等级，输入 0-100",
}


def score_grade(score: str) -> str:
    """
    :param score: 0-100 的数字评分
    """
    try:
        value = float(score)
        if value >= 90:
            return "A - 优秀"
        if value >= 80:
            return "B - 良好"
        if value >= 70:
            return "C - 中等"
        if value >= 60:
            return "D - 及格"
        return "F - 需改进"
    except Exception as e:
        return f"评分错误: {e}"
