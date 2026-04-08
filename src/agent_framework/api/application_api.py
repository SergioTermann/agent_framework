"""
应用管理 API
提供应用的 CRUD、模板、发布、版本管理接口
"""

from flask import Blueprint, request, jsonify, g
from agent_framework.platform.application import (
    ApplicationManager,
    ApplicationStorage,
    Application,
    AppType,
    AppStatus,
    AppVisibility,
)
from agent_framework.api.auth_api import require_auth, require_permission
from datetime import datetime
import uuid


# 创建 Blueprint
app_bp = Blueprint('applications', __name__, url_prefix='/api/applications')

# 初始化存储和管理器
storage = ApplicationStorage()
manager = ApplicationManager(storage)


# ─── 应用 CRUD ────────────────────────────────────────────────────────────────

@app_bp.route('/', methods=['GET'])
@require_auth
def list_applications():
    """列出应用"""
    try:
        user = g.current_user

        owner_id = request.args.get('owner_id', user.user_id)
        organization_id = request.args.get('organization_id')
        type_str = request.args.get('type')
        status_str = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        type_enum = AppType(type_str) if type_str else None
        status_enum = AppStatus(status_str) if status_str else None

        apps = storage.list_applications(
            owner_id=owner_id,
            organization_id=organization_id,
            type=type_enum,
            status=status_enum,
            limit=limit,
            offset=offset,
        )

        return jsonify({
            "success": True,
            "data": [
                {
                    "app_id": app.app_id,
                    "name": app.name,
                    "slug": app.slug,
                    "type": app.type.value,
                    "status": app.status.value,
                    "visibility": app.visibility.value,
                    "description": app.description,
                    "icon": app.icon,
                    "tags": app.tags,
                    "version_count": app.version_count,
                    "usage_count": app.usage_count,
                    "rating": app.rating,
                    "created_at": app.created_at,
                    "updated_at": app.updated_at,
                }
                for app in apps
            ],
            "total": len(apps),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app_bp.route('/', methods=['POST'])
@require_auth
@require_permission('workflow:write')
def create_application():
    """创建应用"""
    try:
        user = g.current_user
        data = request.json

        name = data.get('name')
        type_str = data.get('type')
        slug = data.get('slug')
        description = data.get('description')
        config = data.get('config', {})

        if not all([name, type_str]):
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        type_enum = AppType(type_str)

        app = manager.create_application(
            name=name,
            type=type_enum,
            owner_id=user.user_id,
            slug=slug,
            description=description,
            config=config,
        )

        return jsonify({
            "success": True,
            "data": {
                "app_id": app.app_id,
                "name": app.name,
                "slug": app.slug,
                "type": app.type.value,
                "status": app.status.value,
                "created_at": app.created_at,
            },
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app_bp.route('/<app_id>', methods=['GET'])
@require_auth
def get_application(app_id: str):
    """获取应用详情"""
    try:
        app = storage.get_application(app_id)

        if not app:
            return jsonify({
                "success": False,
                "error": "应用不存在",
            }), 404

        return jsonify({
            "success": True,
            "data": {
                "app_id": app.app_id,
                "name": app.name,
                "slug": app.slug,
                "type": app.type.value,
                "status": app.status.value,
                "visibility": app.visibility.value,
                "description": app.description,
                "icon": app.icon,
                "cover_image": app.cover_image,
                "tags": app.tags,
                "owner_id": app.owner_id,
                "organization_id": app.organization_id,
                "config": app.config,
                "version_count": app.version_count,
                "usage_count": app.usage_count,
                "rating": app.rating,
                "rating_count": app.rating_count,
                "created_at": app.created_at,
                "updated_at": app.updated_at,
                "metadata": app.metadata,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app_bp.route('/<app_id>', methods=['PUT'])
@require_auth
@require_permission('workflow:write')
def update_application(app_id: str):
    """更新应用"""
    try:
        app = storage.get_application(app_id)

        if not app:
            return jsonify({
                "success": False,
                "error": "应用不存在",
            }), 404

        # 检查权限
        user = g.current_user
        if app.owner_id != user.user_id and user.role.value != 'admin':
            return jsonify({
                "success": False,
                "error": "无权限修改此应用",
            }), 403

        data = request.json

        # 更新字段
        if 'name' in data:
            app.name = data['name']
        if 'description' in data:
            app.description = data['description']
        if 'icon' in data:
            app.icon = data['icon']
        if 'tags' in data:
            app.tags = data['tags']
        if 'config' in data:
            app.config = data['config']
        if 'visibility' in data:
            app.visibility = AppVisibility(data['visibility'])

        app.updated_at = datetime.now().isoformat()
        storage.update_application(app)

        return jsonify({
            "success": True,
            "data": {
                "app_id": app.app_id,
                "name": app.name,
                "updated_at": app.updated_at,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app_bp.route('/<app_id>', methods=['DELETE'])
@require_auth
@require_permission('workflow:delete')
def delete_application(app_id: str):
    """删除应用（软删除）"""
    try:
        app = storage.get_application(app_id)

        if not app:
            return jsonify({
                "success": False,
                "error": "应用不存在",
            }), 404

        # 检查权限
        user = g.current_user
        if app.owner_id != user.user_id and user.role.value != 'admin':
            return jsonify({
                "success": False,
                "error": "无权限删除此应用",
            }), 403

        # 软删除
        app.status = AppStatus.DELETED
        app.updated_at = datetime.now().isoformat()
        storage.update_application(app)

        return jsonify({
            "success": True,
            "message": "应用已删除",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 应用发布 ─────────────────────────────────────────────────────────────────

@app_bp.route('/<app_id>/publish', methods=['POST'])
@require_auth
@require_permission('workflow:write')
def publish_application(app_id: str):
    """发布应用"""
    try:
        app = storage.get_application(app_id)

        if not app:
            return jsonify({
                "success": False,
                "error": "应用不存在",
            }), 404

        # 检查权限
        user = g.current_user
        if app.owner_id != user.user_id and user.role.value != 'admin':
            return jsonify({
                "success": False,
                "error": "无权限发布此应用",
            }), 403

        data = request.json
        version = data.get('version', '1.0.0')
        changelog = data.get('changelog')

        manager.publish_application(app_id, version, changelog)

        return jsonify({
            "success": True,
            "message": "应用已发布",
            "data": {
                "version": version,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app_bp.route('/<app_id>/fork', methods=['POST'])
@require_auth
def fork_application(app_id: str):
    """复制应用"""
    try:
        user = g.current_user
        data = request.json
        new_name = data.get('name')

        forked_app = manager.fork_application(app_id, user.user_id, new_name)

        return jsonify({
            "success": True,
            "data": {
                "app_id": forked_app.app_id,
                "name": forked_app.name,
                "slug": forked_app.slug,
            },
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 应用模板 ─────────────────────────────────────────────────────────────────

@app_bp.route('/templates', methods=['GET'])
def list_templates():
    """列出应用模板"""
    try:
        type_str = request.args.get('type')
        category = request.args.get('category')
        is_official = request.args.get('is_official')

        type_enum = AppType(type_str) if type_str else None
        is_official_bool = is_official == 'true' if is_official else None

        templates = storage.list_templates(
            type=type_enum,
            category=category,
            is_official=is_official_bool,
        )

        return jsonify({
            "success": True,
            "data": [
                {
                    "template_id": t.template_id,
                    "name": t.name,
                    "slug": t.slug,
                    "type": t.type.value,
                    "description": t.description,
                    "icon": t.icon,
                    "category": t.category,
                    "tags": t.tags,
                    "usage_count": t.usage_count,
                    "rating": t.rating,
                    "is_official": t.is_official,
                }
                for t in templates
            ],
            "total": len(templates),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app_bp.route('/templates/<template_id>', methods=['POST'])
@require_auth
def create_from_template(template_id: str):
    """从模板创建应用"""
    try:
        user = g.current_user
        data = request.json
        name = data.get('name')

        if not name:
            return jsonify({
                "success": False,
                "error": "缺少应用名称",
            }), 400

        app = manager.create_from_template(template_id, name, user.user_id)

        return jsonify({
            "success": True,
            "data": {
                "app_id": app.app_id,
                "name": app.name,
                "slug": app.slug,
                "type": app.type.value,
            },
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 应用统计 ─────────────────────────────────────────────────────────────────

@app_bp.route('/stats', methods=['GET'])
@require_auth
def get_stats():
    """获取应用统计"""
    try:
        user = g.current_user

        # 获取用户的所有应用
        apps = storage.list_applications(owner_id=user.user_id, limit=1000)

        # 统计
        total_apps = len(apps)
        published_apps = len([a for a in apps if a.status == AppStatus.PUBLISHED])
        draft_apps = len([a for a in apps if a.status == AppStatus.DRAFT])
        total_usage = sum(a.usage_count for a in apps)

        # 按类型统计
        by_type = {}
        for app in apps:
            type_name = app.type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

        return jsonify({
            "success": True,
            "data": {
                "total_apps": total_apps,
                "published_apps": published_apps,
                "draft_apps": draft_apps,
                "total_usage": total_usage,
                "by_type": by_type,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500
