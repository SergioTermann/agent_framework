"""插件市场 API。"""

from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
import shutil
from typing import Any

from flask import Blueprint, jsonify, request

from agent_framework.core.database import get_db_connection

plugin_market_bp = Blueprint("plugin_market", __name__, url_prefix="/api/plugins")

PLUGIN_DB_PATH = "data/plugins.db"
PLUGIN_INSTALL_DIR = "plugins"

CATEGORY_META = {
    "all": {"label": "全部"},
    "integration": {"label": "系统集成"},
    "ai": {"label": "AI 能力"},
    "data": {"label": "数据处理"},
    "automation": {"label": "自动化"},
    "utility": {"label": "运维工具"},
}

PLUGIN_CATALOG: list[dict[str, Any]] = [
    {
        "id": "weather-api",
        "name": "天气查询",
        "author": "Agent Team",
        "description": "提供多城市天气查询、告警摘要和简易环境建议，适合 Agent 快速拉取实时外部环境信息。",
        "readme": (
            "# 天气查询\n\n"
            "用于在工作流和 Agent 对话中获取天气信息。\n"
            "- 支持按城市检索\n"
            "- 输出简洁摘要\n"
            "- 适合作为调度、巡检前置条件"
        ),
        "icon": "cloud",
        "category": "integration",
        "tags": ["weather", "api", "ops"],
        "rating": 4.8,
        "downloads": 1250,
        "version": "1.2.0",
        "updated_at": "2026-03-26T09:30:00",
        "verified": True,
        "featured": True,
        "compatibility": "Agent Framework 0.7+",
        "highlights": ["实时天气摘要", "城市级查询", "适合运维调度"],
        "accent": "#4f7cff",
    },
    {
        "id": "text-analyzer",
        "name": "文本分析",
        "author": "AI Labs",
        "description": "提供情绪分析、关键词抽取、摘要生成和结构化标签能力，适合工单、日志和报告清洗。",
        "readme": (
            "# 文本分析\n\n"
            "面向文本理解场景的基础插件。\n"
            "- 支持关键词与摘要输出\n"
            "- 支持情绪与主题识别\n"
            "- 可作为知识入库前处理步骤"
        ),
        "icon": "psychology",
        "category": "ai",
        "tags": ["nlp", "summary", "classification"],
        "rating": 4.9,
        "downloads": 2100,
        "version": "2.0.1",
        "updated_at": "2026-04-02T14:20:00",
        "verified": True,
        "featured": True,
        "compatibility": "Agent Framework 0.7+",
        "highlights": ["摘要生成", "关键词提取", "工单语义分类"],
        "accent": "#08b6d6",
    },
    {
        "id": "knowledge-sync",
        "name": "知识库同步",
        "author": "Platform Team",
        "description": "连接内部知识库和外部文档源，支持增量同步、元数据透传和同步结果回写。",
        "readme": (
            "# 知识库同步\n\n"
            "帮助你将外部文档和平台知识库连接起来。\n"
            "- 支持批量增量同步\n"
            "- 记录同步时间与结果\n"
            "- 适合知识入库与文档管道"
        ),
        "icon": "hub",
        "category": "integration",
        "tags": ["knowledge", "sync", "documents"],
        "rating": 4.7,
        "downloads": 1680,
        "version": "1.6.3",
        "updated_at": "2026-03-18T16:05:00",
        "verified": True,
        "featured": False,
        "compatibility": "Agent Framework 0.8+",
        "highlights": ["增量同步", "同步状态回写", "文档元数据保留"],
        "accent": "#5b8c5a",
    },
    {
        "id": "data-cleanroom",
        "name": "数据清洗工坊",
        "author": "Data Works",
        "description": "为表格和结构化文本提供字段映射、缺失补齐、重复检测和批量导出能力。",
        "readme": (
            "# 数据清洗工坊\n\n"
            "适合数据入湖、报表治理和批量结构化处理。\n"
            "- 字段标准化\n"
            "- 缺失值修复\n"
            "- 异常记录排查"
        ),
        "icon": "database",
        "category": "data",
        "tags": ["etl", "quality", "dataset"],
        "rating": 4.6,
        "downloads": 980,
        "version": "1.3.4",
        "updated_at": "2026-03-11T11:40:00",
        "verified": False,
        "featured": False,
        "compatibility": "Agent Framework 0.7+",
        "highlights": ["字段对齐", "数据去重", "批量导出"],
        "accent": "#16a34a",
    },
    {
        "id": "workflow-copilot",
        "name": "工作流副驾",
        "author": "Automation Guild",
        "description": "将多步工具调用组合成可复用自动化流程，适合巡检、日报生成和标准化任务编排。",
        "readme": (
            "# 工作流副驾\n\n"
            "让常用 Agent 流程沉淀为可重复执行的自动化模板。\n"
            "- 多步流程编排\n"
            "- 支持人工确认节点\n"
            "- 支持模板复用"
        ),
        "icon": "bolt",
        "category": "automation",
        "tags": ["workflow", "automation", "assistant"],
        "rating": 4.85,
        "downloads": 1540,
        "version": "2.1.0",
        "updated_at": "2026-04-05T08:15:00",
        "verified": True,
        "featured": True,
        "compatibility": "Agent Framework 0.8+",
        "highlights": ["可复用模板", "多步编排", "人工确认节点"],
        "accent": "#f97316",
    },
    {
        "id": "prompt-guard",
        "name": "Prompt 守卫",
        "author": "Security Lab",
        "description": "为提示词和上下文输入增加脱敏、敏感词拦截和规则审计，适合生产环境护栏。",
        "readme": (
            "# Prompt 守卫\n\n"
            "聚焦生产可控性和安全护栏。\n"
            "- 敏感内容识别\n"
            "- 规则审计日志\n"
            "- 支持上线前预检"
        ),
        "icon": "shield",
        "category": "utility",
        "tags": ["security", "guardrail", "compliance"],
        "rating": 4.75,
        "downloads": 1430,
        "version": "1.8.2",
        "updated_at": "2026-03-30T19:00:00",
        "verified": True,
        "featured": False,
        "compatibility": "Agent Framework 0.7+",
        "highlights": ["提示词脱敏", "规则审计", "上线前预检"],
        "accent": "#e11d48",
    },
]


def init_plugin_db() -> None:
    """初始化插件市场数据库。"""
    Path(PLUGIN_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection(PLUGIN_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS installed_plugins (
                plugin_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                installed_at TEXT NOT NULL,
                enabled INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS plugin_ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id TEXT NOT NULL,
                user_id TEXT,
                rating INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_plugin_ratings_plugin_user
            ON plugin_ratings(plugin_id, user_id);
            """
        )


def _parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        parsed = int((value or "").strip())
    except (TypeError, ValueError):
        parsed = default

    if parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _normalize_category(value: str | None) -> str:
    category = (value or "all").strip().lower()
    if category in CATEGORY_META:
        return category
    return "all"


def _normalize_sort(value: str | None) -> str:
    sort_key = (value or "popular").strip().lower()
    if sort_key in {"popular", "rating", "recent", "name", "installed"}:
        return sort_key
    return "popular"


def _normalize_user_id(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized or "anonymous"


def _catalog_map() -> dict[str, dict[str, Any]]:
    return {plugin["id"]: dict(plugin) for plugin in PLUGIN_CATALOG}


def _get_installed_plugins() -> dict[str, dict[str, Any]]:
    with get_db_connection(PLUGIN_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT plugin_id, name, version, installed_at, enabled
            FROM installed_plugins
            """
        )
        rows = cursor.fetchall()

    return {
        row["plugin_id"]: {
            "plugin_id": row["plugin_id"],
            "name": row["name"],
            "version": row["version"],
            "installed_at": row["installed_at"],
            "enabled": bool(row["enabled"]),
        }
        for row in rows
    }


def _get_rating_summary() -> dict[str, dict[str, Any]]:
    with get_db_connection(PLUGIN_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT plugin_id, AVG(rating) AS average_rating, COUNT(*) AS rating_count
            FROM plugin_ratings
            GROUP BY plugin_id
            """
        )
        rows = cursor.fetchall()

    return {
        row["plugin_id"]: {
            "average_rating": round(row["average_rating"], 2) if row["average_rating"] is not None else 0.0,
            "rating_count": row["rating_count"],
        }
        for row in rows
    }


def _serialize_plugin(
    plugin: dict[str, Any],
    *,
    installed_plugins: dict[str, dict[str, Any]] | None = None,
    rating_summary: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    installed_plugins = installed_plugins or {}
    rating_summary = rating_summary or {}

    plugin_id = plugin["id"]
    installed_info = installed_plugins.get(plugin_id)
    rating_info = rating_summary.get(plugin_id)

    plugin_data = dict(plugin)
    plugin_data["installed"] = installed_info is not None
    plugin_data["enabled"] = installed_info["enabled"] if installed_info else False
    plugin_data["installed_at"] = installed_info["installed_at"] if installed_info else None
    plugin_data["installed_version"] = installed_info["version"] if installed_info else None
    plugin_data["category_label"] = CATEGORY_META.get(plugin["category"], {}).get("label", plugin["category"])

    if rating_info:
        plugin_data["rating"] = rating_info["average_rating"]
        plugin_data["rating_count"] = rating_info["rating_count"]
    else:
        plugin_data["rating_count"] = 0

    return plugin_data


def _apply_filters(
    plugins: list[dict[str, Any]],
    *,
    category: str = "all",
    search: str = "",
    installed_only: bool = False,
) -> list[dict[str, Any]]:
    normalized_search = search.strip().lower()
    filtered = plugins

    if installed_only:
        filtered = [plugin for plugin in filtered if plugin["installed"]]

    if normalized_search:
        filtered = [
            plugin
            for plugin in filtered
            if normalized_search in plugin["name"].lower()
            or normalized_search in plugin["description"].lower()
            or normalized_search in plugin["author"].lower()
            or any(normalized_search in tag.lower() for tag in plugin["tags"])
        ]

    if category != "all":
        filtered = [plugin for plugin in filtered if plugin["category"] == category]

    return filtered


def _sort_plugins(plugins: list[dict[str, Any]], sort_key: str) -> list[dict[str, Any]]:
    sort_key = (sort_key or "popular").strip().lower()

    if sort_key == "rating":
        return sorted(
            plugins,
            key=lambda item: (item["rating"], item.get("rating_count", 0), item["downloads"]),
            reverse=True,
        )
    if sort_key == "recent":
        return sorted(plugins, key=lambda item: item["updated_at"], reverse=True)
    if sort_key == "name":
        return sorted(plugins, key=lambda item: item["name"].lower())
    if sort_key == "installed":
        return sorted(
            plugins,
            key=lambda item: (
                item["installed"],
                item.get("enabled", False),
                item["downloads"],
            ),
            reverse=True,
        )
    return sorted(plugins, key=lambda item: item["downloads"], reverse=True)


def _build_categories(plugins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    categories = [
        {
            "id": "all",
            "label": CATEGORY_META["all"]["label"],
            "count": len(plugins),
        }
    ]
    for category_id, meta in CATEGORY_META.items():
        if category_id == "all":
            continue
        categories.append(
            {
                "id": category_id,
                "label": meta["label"],
                "count": sum(1 for plugin in plugins if plugin["category"] == category_id),
            }
        )
    return categories


def _build_stats(plugins: list[dict[str, Any]]) -> dict[str, Any]:
    total_plugins = len(plugins)
    total_rating = sum(plugin["rating"] for plugin in plugins)
    return {
        "total_plugins": total_plugins,
        "installed_plugins": sum(1 for plugin in plugins if plugin["installed"]),
        "enabled_plugins": sum(1 for plugin in plugins if plugin["enabled"]),
        "total_downloads": sum(plugin["downloads"] for plugin in plugins),
        "avg_rating": round(total_rating / total_plugins, 2) if total_plugins else 0.0,
        "verified_plugins": sum(1 for plugin in plugins if plugin.get("verified")),
        "featured_plugins": sum(1 for plugin in plugins if plugin.get("featured")),
    }


def _build_featured_plugins(plugins: list[dict[str, Any]], *, limit: int = 2) -> list[dict[str, Any]]:
    featured = [plugin for plugin in plugins if plugin.get("featured")]
    featured.sort(
        key=lambda item: (item["rating"], item["downloads"], item["updated_at"]),
        reverse=True,
    )
    return featured[:limit]


def _paginate_plugins(
    plugins: list[dict[str, Any]],
    *,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total_items = len(plugins)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    end = start + page_size
    return (
        plugins[start:end],
        {
            "page": current_page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
        },
    )


def _get_plugin_or_404(plugin_id: str):
    plugin = _catalog_map().get(plugin_id)
    if not plugin:
        return None, (
            jsonify({"success": False, "error": f"插件不存在: {plugin_id}"}),
            404,
        )
    return plugin, None


def _ensure_plugin_installed(plugin_id: str):
    installed_plugins = _get_installed_plugins()
    installed_info = installed_plugins.get(plugin_id)
    if not installed_info:
        return None, (
            jsonify({"success": False, "error": "插件尚未安装"}),
            400,
        )
    return installed_info, None


def _build_plugin_module_code(plugin: dict[str, Any]) -> str:
    plugin_name = plugin["name"].replace('"', '\\"')
    plugin_id = plugin["id"]
    description = plugin["description"].replace('"', '\\"')
    return f'''# Plugin: {plugin_id}
"""Auto-generated marketplace plugin."""


def init():
    """Initialize plugin."""
    print("Plugin {plugin_name} initialized")


def execute(**kwargs):
    """Execute plugin."""
    return {{
        "success": True,
        "plugin_id": "{plugin_id}",
        "name": "{plugin_name}",
        "description": "{description}",
        "kwargs": kwargs,
    }}
'''


init_plugin_db()


@plugin_market_bp.route("/", methods=["GET"])
def list_plugins():
    """获取插件列表。"""
    try:
        category = _normalize_category(request.args.get("category"))
        search = request.args.get("search", "")
        sort_key = _normalize_sort(request.args.get("sort"))
        installed_only = _parse_bool(request.args.get("installed_only"))
        page = _parse_int(request.args.get("page"), 1, minimum=1)
        page_size = _parse_int(request.args.get("page_size"), 6, minimum=1, maximum=24)

        installed_plugins = _get_installed_plugins()
        rating_summary = _get_rating_summary()

        catalog_plugins = [
            _serialize_plugin(
                plugin,
                installed_plugins=installed_plugins,
                rating_summary=rating_summary,
            )
            for plugin in PLUGIN_CATALOG
        ]

        scoped_plugins = _apply_filters(
            catalog_plugins,
            category="all",
            search=search,
            installed_only=installed_only,
        )
        filtered_plugins = _apply_filters(scoped_plugins, category=category)
        ordered_plugins = _sort_plugins(filtered_plugins, sort_key)
        paginated_plugins, pagination = _paginate_plugins(
            ordered_plugins,
            page=page,
            page_size=page_size,
        )

        return jsonify(
            {
                "success": True,
                "plugins": paginated_plugins,
                "featured_plugins": _build_featured_plugins(catalog_plugins),
                "total": len(ordered_plugins),
                "pagination": pagination,
                "stats": _build_stats(catalog_plugins),
                "categories": _build_categories(scoped_plugins),
                "applied_filters": {
                    "category": category,
                    "search": search,
                    "sort": sort_key,
                    "installed_only": installed_only,
                    "page": pagination["page"],
                    "page_size": page_size,
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@plugin_market_bp.route("/<plugin_id>", methods=["GET"])
def get_plugin(plugin_id: str):
    """获取插件详情。"""
    try:
        plugin, error_response = _get_plugin_or_404(plugin_id)
        if error_response:
            return error_response

        plugin_data = _serialize_plugin(
            plugin,
            installed_plugins=_get_installed_plugins(),
            rating_summary=_get_rating_summary(),
        )
        return jsonify({"success": True, "plugin": plugin_data})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@plugin_market_bp.route("/<plugin_id>/install", methods=["POST"])
def install_plugin(plugin_id: str):
    """安装插件。"""
    try:
        plugin, error_response = _get_plugin_or_404(plugin_id)
        if error_response:
            return error_response

        with get_db_connection(PLUGIN_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM installed_plugins WHERE plugin_id = ?", (plugin_id,))
            if cursor.fetchone():
                return jsonify({"success": False, "error": "插件已经安装"}), 400

        Path(PLUGIN_INSTALL_DIR).mkdir(parents=True, exist_ok=True)
        plugin_dir = Path(PLUGIN_INSTALL_DIR) / plugin_id
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True, exist_ok=True)

        plugin_file = plugin_dir / "__init__.py"
        plugin_file.write_text(_build_plugin_module_code(plugin), encoding="utf-8")

        try:
            spec = importlib.util.spec_from_file_location(plugin_id, plugin_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "init"):
                    module.init()
        except Exception as exc:
            shutil.rmtree(plugin_dir, ignore_errors=True)
            return jsonify({"success": False, "error": f"插件加载失败: {exc}"}), 500

        with get_db_connection(PLUGIN_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO installed_plugins (plugin_id, name, version, installed_at, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    plugin_id,
                    plugin["name"],
                    plugin["version"],
                    datetime.now().isoformat(),
                    1,
                ),
            )

        return jsonify(
            {
                "success": True,
                "message": "插件安装成功",
                "plugin_id": plugin_id,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@plugin_market_bp.route("/<plugin_id>/uninstall", methods=["POST"])
def uninstall_plugin(plugin_id: str):
    """卸载插件。"""
    try:
        plugin, error_response = _get_plugin_or_404(plugin_id)
        if error_response:
            return error_response

        with get_db_connection(PLUGIN_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM installed_plugins WHERE plugin_id = ?", (plugin_id,))
            if not cursor.fetchone():
                return jsonify({"success": False, "error": "插件尚未安装"}), 400

        plugin_dir = Path(PLUGIN_INSTALL_DIR) / plugin_id
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        with get_db_connection(PLUGIN_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM installed_plugins WHERE plugin_id = ?", (plugin_id,))

        return jsonify(
            {
                "success": True,
                "message": "插件卸载成功",
                "plugin_id": plugin["id"],
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@plugin_market_bp.route("/<plugin_id>/enable", methods=["POST"])
def enable_plugin(plugin_id: str):
    """启用已安装插件。"""
    try:
        _, error_response = _get_plugin_or_404(plugin_id)
        if error_response:
            return error_response

        installed_info, install_error = _ensure_plugin_installed(plugin_id)
        if install_error:
            return install_error

        if installed_info["enabled"]:
            return jsonify(
                {
                    "success": True,
                    "message": "插件已经启用",
                    "plugin_id": plugin_id,
                    "enabled": True,
                }
            )

        with get_db_connection(PLUGIN_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE installed_plugins SET enabled = 1 WHERE plugin_id = ?",
                (plugin_id,),
            )

        return jsonify(
            {
                "success": True,
                "message": "插件已启用",
                "plugin_id": plugin_id,
                "enabled": True,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@plugin_market_bp.route("/<plugin_id>/disable", methods=["POST"])
def disable_plugin(plugin_id: str):
    """停用已安装插件。"""
    try:
        _, error_response = _get_plugin_or_404(plugin_id)
        if error_response:
            return error_response

        installed_info, install_error = _ensure_plugin_installed(plugin_id)
        if install_error:
            return install_error

        if not installed_info["enabled"]:
            return jsonify(
                {
                    "success": True,
                    "message": "插件已经停用",
                    "plugin_id": plugin_id,
                    "enabled": False,
                }
            )

        with get_db_connection(PLUGIN_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE installed_plugins SET enabled = 0 WHERE plugin_id = ?",
                (plugin_id,),
            )

        return jsonify(
            {
                "success": True,
                "message": "插件已停用",
                "plugin_id": plugin_id,
                "enabled": False,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@plugin_market_bp.route("/<plugin_id>/rate", methods=["POST"])
def rate_plugin(plugin_id: str):
    """为插件评分。"""
    try:
        _, error_response = _get_plugin_or_404(plugin_id)
        if error_response:
            return error_response

        data = request.get_json(silent=True) or {}
        try:
            rating = int(data.get("rating", 5))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "评分必须是 1 到 5 之间的整数"}), 400
        user_id = _normalize_user_id(data.get("user_id"))

        if not 1 <= rating <= 5:
            return jsonify({"success": False, "error": "评分必须在 1 到 5 之间"}), 400

        with get_db_connection(PLUGIN_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO plugin_ratings (plugin_id, user_id, rating, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(plugin_id, user_id)
                DO UPDATE SET
                    rating = excluded.rating,
                    created_at = excluded.created_at
                """,
                (plugin_id, user_id, rating, datetime.now().isoformat()),
            )
            cursor.execute(
                """
                SELECT AVG(rating) AS average_rating, COUNT(*) AS rating_count
                FROM plugin_ratings
                WHERE plugin_id = ?
                """,
                (plugin_id,),
            )
            result = cursor.fetchone()

        return jsonify(
            {
                "success": True,
                "message": "评分成功",
                "average_rating": round(result["average_rating"], 2) if result and result["average_rating"] else 0,
                "total_ratings": result["rating_count"] if result else 0,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@plugin_market_bp.route("/stats", methods=["GET"])
def get_stats():
    """获取插件市场统计信息。"""
    try:
        installed_plugins = _get_installed_plugins()
        rating_summary = _get_rating_summary()
        plugins = [
            _serialize_plugin(
                plugin,
                installed_plugins=installed_plugins,
                rating_summary=rating_summary,
            )
            for plugin in PLUGIN_CATALOG
        ]
        return jsonify(
            {
                "success": True,
                "stats": _build_stats(plugins),
                "categories": _build_categories(plugins),
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
