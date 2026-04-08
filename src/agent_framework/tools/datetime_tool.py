"""日期时间工具"""

from datetime import datetime

TOOL_META = {
    "name": "get_datetime",
    "description": "获取当前日期和时间",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def get_datetime() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
