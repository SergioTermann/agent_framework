"""天气查询工具 —— 通过 OpenWeatherMap API 获取实时天气"""

from __future__ import annotations

import logging

import requests

from agent_framework.core.config import get_config

logger = logging.getLogger(__name__)

_cfg = get_config()

# ─── 天气图标映射 ──────────────────────────────────────────────────────────────

_ICON_MAP = {
    "01": "☀️", "02": "⛅", "03": "☁️", "04": "☁️",
    "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "🌨️", "50": "🌫️",
}


def _weather_icon(icon_code: str) -> str:
    return _ICON_MAP.get(icon_code[:2], "") if icon_code else ""


# ─── 工具实现 ─────────────────────────────────────────────────────────────────


def get_weather(city: str) -> str:
    """查询指定城市的实时天气信息，包括温度、体感温度、湿度、风速和天气描述。

    :param city: 城市名称（中文或英文，如"北京"或"Beijing"）
    """
    wth = _cfg.weather

    if not wth.api_key:
        return (
            f"天气服务未配置 API Key。\n"
            f"请设置环境变量 WEATHER_API_KEY（OpenWeatherMap）。\n"
            f"免费注册: https://openweathermap.org/api"
        )

    params = {
        "q": city,
        "appid": wth.api_key,
        "units": wth.units,
        "lang": wth.language,
    }

    try:
        resp = requests.get(
            f"{wth.base_url}/weather",
            params=params,
            timeout=wth.timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("OpenWeatherMap 请求失败: %s", e)
        return f"天气服务暂不可用: {e}"

    try:
        data = resp.json()
    except ValueError:
        return "天气服务暂不可用: 返回数据格式异常"

    if data.get("cod") != 200:
        msg = data.get("message", "未知错误")
        return f"查询失败: {msg}"

    # 解析数据
    weather_list = data.get("weather", [{}])
    main_weather = weather_list[0] if weather_list else {}
    main = data.get("main", {})
    wind = data.get("wind", {})
    clouds = data.get("clouds", {})
    sys_info = data.get("sys", {})

    icon = _weather_icon(main_weather.get("icon", ""))
    desc = main_weather.get("description", "")
    temp = main.get("temp", "")
    feels_like = main.get("feels_like", "")
    humidity = main.get("humidity", "")
    temp_min = main.get("temp_min", "")
    temp_max = main.get("temp_max", "")
    wind_speed = wind.get("speed", "")
    cloud_pct = clouds.get("all", "")
    country = sys_info.get("country", "")

    unit_symbol = {"metric": "°C", "imperial": "°F", "standard": "K"}.get(wth.units, "°C")

    city_name = data.get("name", city)
    location = f"{city_name}, {country}" if country else city_name

    lines = [
        f"## {icon} {location} 天气",
        f"**天气:** {desc}",
        f"**温度:** {temp}{unit_symbol}（体感 {feels_like}{unit_symbol}）",
        f"**温度范围:** {temp_min}{unit_symbol} ~ {temp_max}{unit_symbol}",
        f"**湿度:** {humidity}%",
        f"**风速:** {wind_speed} m/s",
        f"**云量:** {cloud_pct}%",
    ]

    return "\n".join(lines)


# ─── 工具注册 ──────────────────────────────────────────────────────────────────

if _cfg.weather.enabled:
    TOOL_META = {
        "name": "get_weather",
        "description": "查询指定城市的实时天气信息，包括温度、湿度、风速等。",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称（中文或英文，如 '北京' 或 'Beijing'）",
                },
            },
            "required": ["city"],
        },
    }
