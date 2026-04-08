"""Web 搜索工具 —— 通过 SearXNG 搜索互联网 + 抓取网页正文"""

from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup

from agent_framework.core.config import get_config

logger = logging.getLogger(__name__)

_cfg = get_config()

# ─── 工具实现 ─────────────────────────────────────────────────────────────────


def web_search(
    query: str,
    num_results: int = 5,
    category: str = "general",
    language: str = "",
) -> str:
    """搜索互联网获取实时信息。返回相关网页的标题、链接和摘要。

    :param query: 搜索关键词
    :param num_results: 返回结果数量，默认 5
    :param category: 搜索类别（general / images / news / science / files / it / videos）
    :param language: 语言代码（留空自动检测，或 zh-CN / en-US 等）
    """
    ws = _cfg.web_search

    params = {
        "q": query,
        "format": "json",
        "categories": category,
        "pageno": 1,
        "safesearch": ws.safesearch,
    }
    lang = language or ws.language
    if lang:
        params["language"] = lang

    try:
        resp = requests.get(
            f"{ws.base_url}/search",
            params=params,
            timeout=ws.timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("SearXNG 请求失败: %s", e)
        return f"搜索服务暂不可用: {e}"

    try:
        data = resp.json()
    except ValueError:
        return "搜索服务暂不可用: 返回数据格式异常"

    results = data.get("results", [])
    if not results:
        return f"未找到关于「{query}」的搜索结果。"

    limit = min(num_results, ws.max_results, len(results))
    lines: list[str] = []
    for i, r in enumerate(results[:limit], 1):
        title = r.get("title", "无标题")
        url = r.get("url", "")
        content = r.get("content", "")
        engine = r.get("engine", "")
        engine_tag = f" ({engine})" if engine else ""

        lines.append(f"{i}. **{title}**{engine_tag}")
        if url:
            lines.append(f"   URL: {url}")
        if content:
            lines.append(f"   {content}")
        lines.append("")

    return "\n".join(lines).strip()


def fetch_url(url: str, max_chars: int = 4000) -> str:
    """获取指定网页的正文内容。用于在搜索摘要不够详细时获取完整页面。

    :param url: 要抓取的网页 URL
    :param max_chars: 返回正文的最大字符数，默认 4000
    """
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AgentFramework/1.0)"},
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("抓取页面失败 %s: %s", url, e)
        return f"无法获取页面内容: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")

    # 移除无关标签
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # 优先提取正文容器
    body = (
        soup.find("article")
        or soup.find("main")
        or soup.find("body")
    )
    if body is None:
        return "无法解析页面内容。"

    text = body.get_text(separator="\n", strip=True)

    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n...(内容已截断)"

    return text


# ─── 工具注册（仅在启用时导出 TOOL_META） ─────────────────────────────────────

if _cfg.web_search.enabled:
    TOOL_META = {
        "name": "web_search",
        "description": "搜索互联网获取实时信息。输入搜索关键词，返回相关网页的标题、链接和摘要。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5",
                    "default": 5,
                },
                "category": {
                    "type": "string",
                    "description": "搜索类别：general / images / news / science / files / it / videos",
                    "default": "general",
                },
                "language": {
                    "type": "string",
                    "description": "语言代码，留空自动检测，或 zh-CN / en-US 等",
                    "default": "",
                },
            },
            "required": ["query"],
        },
    }

    EXTRA_TOOLS = [
        {
            "name": "fetch_url",
            "description": "获取指定网页的正文内容。当搜索摘要不够详细时，可用此工具获取完整页面。",
            "handler": fetch_url,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要抓取的网页 URL",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "返回正文的最大字符数，默认 4000",
                        "default": 4000,
                    },
                },
                "required": ["url"],
            },
        }
    ]
