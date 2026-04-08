"""
Skill Creator API
提供技能创建、编辑、测试和管理功能
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

from agent_framework.core.database import get_db_connection

skill_creator_bp = Blueprint("skill_creator", __name__, url_prefix="/api/skills")

# 技能数据库路径
SKILL_DB_PATH = "data/skills.db"
SKILL_STORAGE_DIR = Path("data/skills")


def init_skill_db():
    """初始化技能数据库"""
    Path(SKILL_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    SKILL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    with get_db_connection(SKILL_DB_PATH) as conn:
        cursor = conn.cursor()

        # 技能表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT,
                icon TEXT,
                prompt_template TEXT NOT NULL,
                input_schema TEXT,
                output_schema TEXT,
                examples TEXT,
                tags TEXT,
                author TEXT,
                version TEXT DEFAULT '1.0.0',
                is_public INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                usage_count INTEGER DEFAULT 0
            )
        """)

        # 技能执行历史
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_executions (
                execution_id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                input_data TEXT,
                output_data TEXT,
                status TEXT,
                error_message TEXT,
                execution_time REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES skills(skill_id)
            )
        """)

        # 技能评分
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id TEXT NOT NULL,
                user_id TEXT,
                rating INTEGER NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES skills(skill_id)
            )
        """)


init_skill_db()


@skill_creator_bp.route("/", methods=["GET"])
def list_skills():
    """获取技能列表"""
    try:
        category = request.args.get("category")
        search = request.args.get("search", "").lower()

        with get_db_connection(SKILL_DB_PATH) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM skills WHERE 1=1"
            params = []

            if category:
                query += " AND category = ?"
                params.append(category)

            if search:
                query += " AND (name LIKE ? OR description LIKE ? OR tags LIKE ?)"
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern, search_pattern])

            query += " ORDER BY usage_count DESC, created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            skills = []
            for row in rows:
                skill = dict(row)
                skill["tags"] = json.loads(skill["tags"]) if skill["tags"] else []
                skill["examples"] = json.loads(skill["examples"]) if skill["examples"] else []
                skill["input_schema"] = json.loads(skill["input_schema"]) if skill["input_schema"] else {}
                skill["output_schema"] = json.loads(skill["output_schema"]) if skill["output_schema"] else {}

                # 获取评分
                cursor.execute("""
                    SELECT AVG(rating) as avg_rating, COUNT(*) as rating_count
                    FROM skill_ratings WHERE skill_id = ?
                """, (skill["skill_id"],))
                rating_row = cursor.fetchone()
                skill["avg_rating"] = round(rating_row["avg_rating"], 1) if rating_row["avg_rating"] else 0
                skill["rating_count"] = rating_row["rating_count"]

                skills.append(skill)

        return jsonify({
            "success": True,
            "skills": skills,
            "total": len(skills)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@skill_creator_bp.route("/<skill_id>", methods=["GET"])
def get_skill(skill_id: str):
    """获取单个技能详情"""
    try:
        with get_db_connection(SKILL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skills WHERE skill_id = ?", (skill_id,))
            row = cursor.fetchone()

            if not row:
                return jsonify({
                    "success": False,
                    "error": "Skill not found"
                }), 404

            skill = dict(row)
            skill["tags"] = json.loads(skill["tags"]) if skill["tags"] else []
            skill["examples"] = json.loads(skill["examples"]) if skill["examples"] else []
            skill["input_schema"] = json.loads(skill["input_schema"]) if skill["input_schema"] else {}
            skill["output_schema"] = json.loads(skill["output_schema"]) if skill["output_schema"] else {}

            # 获取最近执行记录
            cursor.execute("""
                SELECT * FROM skill_executions
                WHERE skill_id = ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (skill_id,))
            executions = [dict(row) for row in cursor.fetchall()]
            skill["recent_executions"] = executions

            return jsonify({
                "success": True,
                "skill": skill
            })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@skill_creator_bp.route("/", methods=["POST"])
def create_skill():
    """创建新技能"""
    try:
        data = request.json

        # 验证必填字段
        required_fields = ["name", "prompt_template"]
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "success": False,
                    "error": f"Missing required field: {field}"
                }), 400

        skill_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        with get_db_connection(SKILL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO skills (
                    skill_id, name, description, category, icon,
                    prompt_template, input_schema, output_schema,
                    examples, tags, author, version, is_public,
                    created_at, updated_at, usage_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                skill_id,
                data["name"],
                data.get("description", ""),
                data.get("category", "custom"),
                data.get("icon", "⚡"),
                data["prompt_template"],
                json.dumps(data.get("input_schema", {})),
                json.dumps(data.get("output_schema", {})),
                json.dumps(data.get("examples", [])),
                json.dumps(data.get("tags", [])),
                data.get("author", "Anonymous"),
                data.get("version", "1.0.0"),
                data.get("is_public", 0),
                now,
                now,
                0
            ))

        return jsonify({
            "success": True,
            "skill_id": skill_id,
            "message": "Skill created successfully"
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@skill_creator_bp.route("/<skill_id>", methods=["PUT"])
def update_skill(skill_id: str):
    """更新技能"""
    try:
        data = request.json
        now = datetime.now().isoformat()

        with get_db_connection(SKILL_DB_PATH) as conn:
            cursor = conn.cursor()

            # 检查技能是否存在
            cursor.execute("SELECT skill_id FROM skills WHERE skill_id = ?", (skill_id,))
            if not cursor.fetchone():
                return jsonify({
                    "success": False,
                    "error": "Skill not found"
                }), 404

            # 构建更新语句
            update_fields = []
            params = []

            for field in ["name", "description", "category", "icon", "prompt_template", "author", "version"]:
                if field in data:
                    update_fields.append(f"{field} = ?")
                    params.append(data[field])

            for field in ["input_schema", "output_schema", "examples", "tags"]:
                if field in data:
                    update_fields.append(f"{field} = ?")
                    params.append(json.dumps(data[field]))

            if "is_public" in data:
                update_fields.append("is_public = ?")
                params.append(data["is_public"])

            update_fields.append("updated_at = ?")
            params.append(now)
            params.append(skill_id)

            query = f"UPDATE skills SET {', '.join(update_fields)} WHERE skill_id = ?"
            cursor.execute(query, params)

        return jsonify({
            "success": True,
            "message": "Skill updated successfully"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@skill_creator_bp.route("/<skill_id>", methods=["DELETE"])
def delete_skill(skill_id: str):
    """删除技能"""
    try:
        with get_db_connection(SKILL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM skills WHERE skill_id = ?", (skill_id,))

            if cursor.rowcount == 0:
                return jsonify({
                    "success": False,
                    "error": "Skill not found"
                }), 404

            # 删除相关执行记录
            cursor.execute("DELETE FROM skill_executions WHERE skill_id = ?", (skill_id,))
            cursor.execute("DELETE FROM skill_ratings WHERE skill_id = ?", (skill_id,))

        return jsonify({
            "success": True,
            "message": "Skill deleted successfully"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@skill_creator_bp.route("/<skill_id>/execute", methods=["POST"])
def execute_skill(skill_id: str):
    """执行技能（测试）"""
    try:
        data = request.json
        input_data = data.get("input", {})

        with get_db_connection(SKILL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skills WHERE skill_id = ?", (skill_id,))
            row = cursor.fetchone()

            if not row:
                return jsonify({
                    "success": False,
                    "error": "Skill not found"
                }), 404

            skill = dict(row)

            # 构建提示词
            prompt = skill["prompt_template"]
            for key, value in input_data.items():
                prompt = prompt.replace(f"{{{key}}}", str(value))

            # 调用 LLM 执行技能
            import time
            start_time = time.time()

            try:
                # 尝试使用 OpenAI API
                from openai import OpenAI
                client = OpenAI()

                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "你是一个专业的AI助手，请根据用户的提示词完成任务。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7
                )

                result_text = response.choices[0].message.content
                output_data = {
                    "result": result_text,
                    "prompt": prompt,
                    "input": input_data,
                    "model": "gpt-3.5-turbo"
                }
            except Exception as e:
                # 如果 LLM 调用失败，返回模拟结果
                output_data = {
                    "result": f"执行技能 '{skill['name']}' 的结果（模拟模式，LLM调用失败: {str(e)}）",
                    "prompt": prompt,
                    "input": input_data,
                    "error": str(e)
                }

            execution_time = time.time() - start_time

            # 记录执行历史
            execution_id = str(uuid.uuid4())
            now = datetime.now().isoformat()

            cursor.execute("""
                INSERT INTO skill_executions (
                    execution_id, skill_id, input_data, output_data,
                    status, execution_time, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                execution_id,
                skill_id,
                json.dumps(input_data),
                json.dumps(output_data),
                "success",
                execution_time,
                now
            ))

            # 更新使用次数
            cursor.execute("""
                UPDATE skills SET usage_count = usage_count + 1
                WHERE skill_id = ?
            """, (skill_id,))

        return jsonify({
            "success": True,
            "execution_id": execution_id,
            "output": output_data,
            "execution_time": execution_time
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@skill_creator_bp.route("/<skill_id>/rate", methods=["POST"])
def rate_skill(skill_id: str):
    """评分技能"""
    try:
        data = request.json
        rating = data.get("rating")
        comment = data.get("comment", "")
        user_id = data.get("user_id", "anonymous")

        if not rating or rating < 1 or rating > 5:
            return jsonify({
                "success": False,
                "error": "Rating must be between 1 and 5"
            }), 400

        with get_db_connection(SKILL_DB_PATH) as conn:
            cursor = conn.cursor()

            # 检查技能是否存在
            cursor.execute("SELECT skill_id FROM skills WHERE skill_id = ?", (skill_id,))
            if not cursor.fetchone():
                return jsonify({
                    "success": False,
                    "error": "Skill not found"
                }), 404

            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO skill_ratings (skill_id, user_id, rating, comment, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (skill_id, user_id, rating, comment, now))

        return jsonify({
            "success": True,
            "message": "Rating submitted successfully"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@skill_creator_bp.route("/categories", methods=["GET"])
def get_categories():
    """获取技能分类"""
    categories = [
        {"id": "text", "name": "文本处理", "icon": "📝"},
        {"id": "data", "name": "数据分析", "icon": "📊"},
        {"id": "code", "name": "代码生成", "icon": "💻"},
        {"id": "creative", "name": "创意写作", "icon": "✨"},
        {"id": "business", "name": "商业分析", "icon": "💼"},
        {"id": "research", "name": "研究助手", "icon": "🔬"},
        {"id": "translation", "name": "翻译转换", "icon": "🌐"},
        {"id": "custom", "name": "自定义", "icon": "⚙️"},
    ]

    return jsonify({
        "success": True,
        "categories": categories
    })


@skill_creator_bp.route("/templates", methods=["GET"])
def get_templates():
    """获取技能模板"""
    templates = [
        {
            "id": "summarizer",
            "name": "文本摘要",
            "description": "将长文本总结为简短摘要",
            "category": "text",
            "prompt_template": "请将以下文本总结为简短摘要：\n\n{text}\n\n摘要：",
            "input_schema": {
                "text": {"type": "string", "label": "输入文本", "required": True}
            },
            "examples": [
                {"text": "这是一段很长的文本..."}
            ]
        },
        {
            "id": "translator",
            "name": "语言翻译",
            "description": "将文本翻译成目标语言",
            "category": "translation",
            "prompt_template": "请将以下{source_lang}文本翻译成{target_lang}：\n\n{text}",
            "input_schema": {
                "text": {"type": "string", "label": "原文", "required": True},
                "source_lang": {"type": "string", "label": "源语言", "default": "中文"},
                "target_lang": {"type": "string", "label": "目标语言", "default": "英文"}
            }
        },
        {
            "id": "code_generator",
            "name": "代码生成",
            "description": "根据需求生成代码",
            "category": "code",
            "prompt_template": "请用{language}编写代码实现以下功能：\n\n{requirement}\n\n代码：",
            "input_schema": {
                "requirement": {"type": "string", "label": "功能需求", "required": True},
                "language": {"type": "string", "label": "编程语言", "default": "Python"}
            }
        }
    ]

    return jsonify({
        "success": True,
        "templates": templates
    })


@skill_creator_bp.route("/stats", methods=["GET"])
def get_stats():
    """获取统计信息"""
    try:
        with get_db_connection(SKILL_DB_PATH) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as total FROM skills")
            total_skills = cursor.fetchone()["total"]

            cursor.execute("SELECT SUM(usage_count) as total FROM skills")
            total_executions = cursor.fetchone()["total"] or 0

            cursor.execute("SELECT COUNT(*) as total FROM skill_ratings")
            total_ratings = cursor.fetchone()["total"]

            cursor.execute("SELECT AVG(rating) as avg FROM skill_ratings")
            avg_rating = cursor.fetchone()["avg"] or 0

        return jsonify({
            "success": True,
            "stats": {
                "total_skills": total_skills,
                "total_executions": total_executions,
                "total_ratings": total_ratings,
                "avg_rating": round(avg_rating, 1)
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
