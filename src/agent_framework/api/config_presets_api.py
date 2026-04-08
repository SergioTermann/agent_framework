"""
配置预设 API - 管理工作流配置预设
允许用户保存、加载和管理常用的配置组合
"""

from flask import Blueprint, request, jsonify
import agent_framework.core.fast_json as json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# 创建 Blueprint
config_presets_bp = Blueprint('config_presets', __name__, url_prefix='/api/config-presets')

# 预设存储目录
PRESETS_DIR = Path("./data/config_presets")
PRESETS_DIR.mkdir(parents=True, exist_ok=True)


class ConfigPresetsStorage:
    """配置预设存储"""

    @staticmethod
    def save(preset_id: str, preset_data: Dict):
        """保存预设"""
        file_path = PRESETS_DIR / f"{preset_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(preset_data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load(preset_id: str) -> Dict:
        """加载预设"""
        file_path = PRESETS_DIR / f"{preset_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def delete(preset_id: str):
        """删除预设"""
        file_path = PRESETS_DIR / f"{preset_id}.json"
        if file_path.exists():
            file_path.unlink()

    @staticmethod
    def list_all() -> List[Dict]:
        """列出所有预设"""
        presets = []
        for file_path in PRESETS_DIR.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    presets.append({
                        "preset_id": data["preset_id"],
                        "name": data["name"],
                        "description": data.get("description", ""),
                        "category": data.get("category", "custom"),
                        "created_at": data.get("created_at"),
                    })
            except Exception as e:
                print(f"加载预设失败 {file_path}: {e}")
        return presets


# API 路由

@config_presets_bp.route('/', methods=['GET'])
def list_presets():
    """列出所有配置预设"""
    try:
        presets = ConfigPresetsStorage.list_all()

        # 添加内置预设
        builtin_presets = get_builtin_presets()
        all_presets = builtin_presets + presets

        return jsonify({
            "success": True,
            "data": all_presets,
            "total": len(all_presets),
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@config_presets_bp.route('/', methods=['POST'])
def create_preset():
    """创建配置预设"""
    try:
        data = request.json
        name = data.get("name")
        config = data.get("config", {})

        if not name:
            return jsonify({
                "success": False,
                "error": "缺少预设名称",
            }), 400

        # 生成预设 ID
        import uuid
        preset_id = str(uuid.uuid4())

        preset_data = {
            "preset_id": preset_id,
            "name": name,
            "description": data.get("description", ""),
            "category": data.get("category", "custom"),
            "config": config,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        # 保存
        ConfigPresetsStorage.save(preset_id, preset_data)

        return jsonify({
            "success": True,
            "data": preset_data,
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@config_presets_bp.route('/<preset_id>', methods=['GET'])
def get_preset(preset_id: str):
    """获取配置预设详情"""
    try:
        # 先检查是否是内置预设
        builtin = get_builtin_preset(preset_id)
        if builtin:
            return jsonify({
                "success": True,
                "data": builtin,
            })

        # 加载自定义预设
        preset_data = ConfigPresetsStorage.load(preset_id)
        if not preset_data:
            return jsonify({
                "success": False,
                "error": "预设不存在",
            }), 404

        return jsonify({
            "success": True,
            "data": preset_data,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@config_presets_bp.route('/<preset_id>', methods=['PUT'])
def update_preset(preset_id: str):
    """更新配置预设"""
    try:
        # 检查预设是否存在
        existing = ConfigPresetsStorage.load(preset_id)
        if not existing:
            return jsonify({
                "success": False,
                "error": "预设不存在",
            }), 404

        # 更新数据
        data = request.json
        existing.update({
            "name": data.get("name", existing["name"]),
            "description": data.get("description", existing.get("description", "")),
            "category": data.get("category", existing.get("category", "custom")),
            "config": data.get("config", existing["config"]),
            "updated_at": datetime.now().isoformat(),
        })

        # 保存
        ConfigPresetsStorage.save(preset_id, existing)

        return jsonify({
            "success": True,
            "data": existing,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@config_presets_bp.route('/<preset_id>', methods=['DELETE'])
def delete_preset(preset_id: str):
    """删除配置预设"""
    try:
        # 检查预设是否存在
        existing = ConfigPresetsStorage.load(preset_id)
        if not existing:
            return jsonify({
                "success": False,
                "error": "预设不存在",
            }), 404

        # 删除
        ConfigPresetsStorage.delete(preset_id)

        return jsonify({
            "success": True,
            "message": "预设已删除",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# 内置预设

def get_builtin_presets() -> List[Dict]:
    """获取内置预设列表"""
    return [
        {
            "preset_id": "creative",
            "name": "创意写作",
            "description": "高温度、高随机性，适合创意内容生成",
            "category": "builtin",
            "builtin": True,
        },
        {
            "preset_id": "precise",
            "name": "精确回答",
            "description": "低温度、低随机性，适合事实性问答",
            "category": "builtin",
            "builtin": True,
        },
        {
            "preset_id": "balanced",
            "name": "平衡模式",
            "description": "中等参数，适合大多数场景",
            "category": "builtin",
            "builtin": True,
        },
        {
            "preset_id": "code",
            "name": "代码生成",
            "description": "优化的代码生成参数",
            "category": "builtin",
            "builtin": True,
        },
        {
            "preset_id": "chat",
            "name": "对话助手",
            "description": "友好的对话参数设置",
            "category": "builtin",
            "builtin": True,
        },
    ]


def get_builtin_preset(preset_id: str) -> Dict:
    """获取内置预设详情"""
    presets = {
        "creative": {
            "preset_id": "creative",
            "name": "创意写作",
            "description": "高温度、高随机性，适合创意内容生成",
            "category": "builtin",
            "builtin": True,
            "config": {
                "temperature": 1.2,
                "max_tokens": 4096,
                "top_p": 0.95,
                "frequency_penalty": 0.5,
                "presence_penalty": 0.5,
                "max_rounds": 10,
                "stream": True,
                "response_format": "text",
            }
        },
        "precise": {
            "preset_id": "precise",
            "name": "精确回答",
            "description": "低温度、低随机性，适合事实性问答",
            "category": "builtin",
            "builtin": True,
            "config": {
                "temperature": 0.3,
                "max_tokens": 2048,
                "top_p": 0.9,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "max_rounds": 5,
                "stream": True,
                "response_format": "text",
            }
        },
        "balanced": {
            "preset_id": "balanced",
            "name": "平衡模式",
            "description": "中等参数，适合大多数场景",
            "category": "builtin",
            "builtin": True,
            "config": {
                "temperature": 0.7,
                "max_tokens": 2048,
                "top_p": 0.95,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "max_rounds": 15,
                "stream": True,
                "response_format": "text",
            }
        },
        "code": {
            "preset_id": "code",
            "name": "代码生成",
            "description": "优化的代码生成参数",
            "category": "builtin",
            "builtin": True,
            "config": {
                "temperature": 0.2,
                "max_tokens": 4096,
                "top_p": 0.95,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "max_rounds": 20,
                "stream": True,
                "response_format": "text",
                "stop_sequences": "```\n\n,### End",
            }
        },
        "chat": {
            "preset_id": "chat",
            "name": "对话助手",
            "description": "友好的对话参数设置",
            "category": "builtin",
            "builtin": True,
            "config": {
                "temperature": 0.8,
                "max_tokens": 2048,
                "top_p": 0.95,
                "frequency_penalty": 0.3,
                "presence_penalty": 0.3,
                "max_rounds": 15,
                "stream": True,
                "response_format": "text",
            }
        },
    }

    return presets.get(preset_id)
