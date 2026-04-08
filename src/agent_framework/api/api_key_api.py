"""
API 密钥管理 API
提供 API Key 的 CRUD 和使用统计接口
"""

from flask import Blueprint, request, jsonify
from agent_framework.infra.api_key_manager import APIKeyManager, APIKeyStorage
from datetime import datetime


# 创建 Blueprint
api_key_bp = Blueprint('api_keys', __name__, url_prefix='/api/keys')

# 初始化存储和管理器
storage = APIKeyStorage()
manager = APIKeyManager(storage)


# ─── API 密钥 CRUD ────────────────────────────────────────────────────────────

@api_key_bp.route('/', methods=['GET'])
def list_keys():
    """列出 API 密钥"""
    try:
        user_id = request.args.get('user_id')
        keys = storage.list_keys(user_id=user_id)

        return jsonify({
            "success": True,
            "data": [
                {
                    "key_id": k.key_id,
                    "name": k.name,
                    "created_at": k.created_at,
                    "expires_at": k.expires_at,
                    "is_active": k.is_active,
                    "rate_limit": k.rate_limit,
                    "daily_limit": k.daily_limit,
                    "permissions": k.permissions,
                    "total_requests": k.total_requests,
                    "last_used_at": k.last_used_at,
                    # 不返回 key_hash 保证安全
                }
                for k in keys
            ],
            "total": len(keys),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@api_key_bp.route('/', methods=['POST'])
def create_key():
    """创建 API 密钥"""
    try:
        data = request.json
        name = data.get('name')
        user_id = data.get('user_id')
        rate_limit = data.get('rate_limit', 100)
        daily_limit = data.get('daily_limit', 10000)
        permissions = data.get('permissions', [])
        expires_in_days = data.get('expires_in_days')

        if not name:
            return jsonify({
                "success": False,
                "error": "缺少密钥名称",
            }), 400

        # 生成密钥
        api_key, raw_key = manager.generate_key(
            name=name,
            user_id=user_id,
            rate_limit=rate_limit,
            daily_limit=daily_limit,
            permissions=permissions,
            expires_in_days=expires_in_days,
        )

        return jsonify({
            "success": True,
            "data": {
                "key_id": api_key.key_id,
                "name": api_key.name,
                "api_key": raw_key,  # 只在创建时返回一次
                "created_at": api_key.created_at,
                "expires_at": api_key.expires_at,
                "rate_limit": api_key.rate_limit,
                "daily_limit": api_key.daily_limit,
                "permissions": api_key.permissions,
            },
            "message": "请妥善保管 API 密钥，它只会显示一次",
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@api_key_bp.route('/<key_id>', methods=['PUT'])
def update_key(key_id: str):
    """更新 API 密钥"""
    try:
        # 查找密钥
        keys = storage.list_keys()
        api_key = next((k for k in keys if k.key_id == key_id), None)

        if not api_key:
            return jsonify({
                "success": False,
                "error": "API 密钥不存在",
            }), 404

        # 更新字段
        data = request.json

        if 'name' in data:
            api_key.name = data['name']
        if 'is_active' in data:
            api_key.is_active = data['is_active']
        if 'rate_limit' in data:
            api_key.rate_limit = data['rate_limit']
        if 'daily_limit' in data:
            api_key.daily_limit = data['daily_limit']
        if 'permissions' in data:
            api_key.permissions = data['permissions']

        storage.update_key(api_key)

        return jsonify({
            "success": True,
            "data": {
                "key_id": api_key.key_id,
                "name": api_key.name,
                "is_active": api_key.is_active,
                "rate_limit": api_key.rate_limit,
                "daily_limit": api_key.daily_limit,
                "permissions": api_key.permissions,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@api_key_bp.route('/<key_id>', methods=['DELETE'])
def delete_key(key_id: str):
    """删除 API 密钥"""
    try:
        storage.delete_key(key_id)

        return jsonify({
            "success": True,
            "message": "API 密钥已删除",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 使用统计 ─────────────────────────────────────────────────────────────────

@api_key_bp.route('/<key_id>/stats', methods=['GET'])
def get_key_stats(key_id: str):
    """获取 API 密钥使用统计"""
    try:
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')

        stats = storage.get_usage_stats(
            key_id=key_id,
            start_time=start_time,
            end_time=end_time,
        )

        return jsonify({
            "success": True,
            "data": stats,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@api_key_bp.route('/validate', methods=['POST'])
def validate_key():
    """验证 API 密钥"""
    try:
        data = request.json
        raw_key = data.get('api_key')

        if not raw_key:
            return jsonify({
                "success": False,
                "error": "缺少 API 密钥",
            }), 400

        api_key = manager.validate_key(raw_key)

        if not api_key:
            return jsonify({
                "success": False,
                "valid": False,
                "message": "无效的 API 密钥",
            })

        return jsonify({
            "success": True,
            "valid": True,
            "data": {
                "key_id": api_key.key_id,
                "name": api_key.name,
                "permissions": api_key.permissions,
                "rate_limit": api_key.rate_limit,
                "daily_limit": api_key.daily_limit,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500
