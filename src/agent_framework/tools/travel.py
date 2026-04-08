"""旅行建议工具 —— 通过高德地图 API 获取 POI 和旅行信息"""

from __future__ import annotations

import logging

import requests

from agent_framework.core.config import get_config

logger = logging.getLogger(__name__)

_cfg = get_config()

# ─── 工具实现 ─────────────────────────────────────────────────────────────────


def travel_tip(city: str, keyword: str = "景点", num_results: int = 5) -> str:
    """获取城市的旅行建议和热门地点推荐。

    :param city: 中文城市名（如"杭州"）
    :param keyword: 搜索关键词（景点 / 美食 / 酒店 / 交通），默认"景点"
    :param num_results: 返回结果数量，默认 5
    """
    trv = _cfg.travel

    if not trv.api_key:
        return (
            f"旅行服务未配置 API Key。\n"
            f"请设置环境变量 AMAP_API_KEY（高德地图）。\n"
            f"免费申请: https://console.amap.com/dev/key/app"
        )

    # 使用高德 POI 搜索
    params = {
        "key": trv.api_key,
        "keywords": keyword,
        "city": city,
        "citylimit": "true",
        "offset": min(num_results, 20),
        "page": 1,
        "extensions": "all",
    }

    try:
        resp = requests.get(
            f"{trv.base_url}/place/text",
            params=params,
            timeout=trv.timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("高德 API 请求失败: %s", e)
        return f"旅行服务暂不可用: {e}"

    try:
        data = resp.json()
    except ValueError:
        return "旅行服务暂不可用: 返回数据格式异常"

    if data.get("status") != "1":
        info = data.get("info", "未知错误")
        return f"查询失败: {info}"

    pois = data.get("pois", [])
    if not pois:
        return f"未找到{city}的「{keyword}」相关地点。"

    lines = [f"## {city} · {keyword}推荐\n"]

    for i, poi in enumerate(pois[:num_results], 1):
        name = poi.get("name", "")
        address = poi.get("address", "")
        tel = poi.get("tel", "")
        ptype = poi.get("type", "")
        rating = poi.get("biz_ext", {}).get("rating", "")

        lines.append(f"**{i}. {name}**")
        if ptype:
            type_short = ptype.split(";")[0] if ";" in ptype else ptype
            lines.append(f"   类型: {type_short}")
        if address:
            lines.append(f"   地址: {address}")
        if rating:
            lines.append(f"   评分: {rating}")
        if tel:
            lines.append(f"   电话: {tel}")
        lines.append("")

    lines.append(f"> 以上数据来自高德地图，共找到 {data.get('count', '?')} 条结果。")

    return "\n".join(lines)


# ─── 工具注册 ──────────────────────────────────────────────────────────────────

if _cfg.travel.enabled:
    TOOL_META = {
        "name": "travel_tip",
        "description": "获取城市的旅行建议和热门地点推荐（景点、美食、酒店等）。通过高德地图 API 提供实时 POI 信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "中文城市名，如 '杭州'、'北京'",
                },
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词：景点 / 美食 / 酒店 / 交通",
                    "default": "景点",
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5",
                    "default": 5,
                },
            },
            "required": ["city"],
        },
    }
