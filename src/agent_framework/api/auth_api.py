"""
认证和用户管理 API
提供用户注册、登录、权限管理接口
"""

import logging
import os
import uuid
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, jsonify, g
from agent_framework.core.auth import (
    AuthManager,
    UserStorage,
    User,
    Organization,
    AuditLog,
    UserRole,
    UserStatus,
)
from agent_framework.core.config import get_config


# 创建 Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')
user_bp = Blueprint('users', __name__, url_prefix='/api/users')
org_bp = Blueprint('organizations', __name__, url_prefix='/api/organizations')

logger = logging.getLogger(__name__)


def _resolve_auth_secret_key() -> str:
    cfg = get_config()
    secret = os.getenv("JWT_SECRET_KEY", "").strip() or cfg.server.secret_key
    if secret in {"", "your-secret-key-change-in-production", "agent-framework-secret-key-change-in-production"}:
        logger.warning("Using a weak default auth secret. Set JWT_SECRET_KEY or SECRET_KEY before deployment.")
    return secret


# 初始化存储和管理器
storage = UserStorage()
auth_manager = AuthManager(storage, secret_key=_resolve_auth_secret_key())


# ─── 认证装饰器 ───────────────────────────────────────────────────────────────

def require_auth(f):
    """需要认证的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 从请求头获取 Token
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({
                "success": False,
                "error": "缺少认证信息",
            }), 401

        token = auth_header[7:]  # 移除 "Bearer " 前缀

        # 验证 Token
        payload = auth_manager.verify_token(token)
        if not payload:
            return jsonify({
                "success": False,
                "error": "无效的认证信息",
            }), 401

        # 获取用户
        user = storage.get_user_by_id(payload['user_id'])
        if not user:
            return jsonify({
                "success": False,
                "error": "用户不存在",
            }), 401

        # 将用户添加到请求上下文
        g.current_user = user

        return f(*args, **kwargs)

    return decorated_function


def _get_authenticated_user():
    user = getattr(g, "current_user", None)
    if user is None:
        raise RuntimeError("current user is not available")
    return user


def is_admin_user(user=None) -> bool:
    user = user or getattr(g, "current_user", None)
    return bool(user and user.role == UserRole.ADMIN)


def resolve_user_scope(requested_user_id: str | None = None) -> str:
    user = _get_authenticated_user()
    candidate = str(requested_user_id or "").strip()
    if not candidate or candidate == user.user_id:
        return user.user_id
    if is_admin_user(user):
        return candidate
    raise PermissionError("forbidden")


def require_admin_scope() -> None:
    if not is_admin_user():
        raise PermissionError("admin access required")


def require_permission(permission: str):
    """需要特定权限的装饰器"""
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            user = g.current_user

            # 检查权限
            if not auth_manager.check_permission(user, permission):
                return jsonify({
                    "success": False,
                    "error": "权限不足",
                }), 403

            return f(*args, **kwargs)

        return decorated_function
    return decorator


def require_role(role: UserRole):
    """需要特定角色的装饰器"""
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            user = g.current_user

            # 检查角色
            if user.role != role and user.role != UserRole.ADMIN:
                return jsonify({
                    "success": False,
                    "error": "权限不足",
                }), 403

            return f(*args, **kwargs)

        return decorated_function
    return decorator


# ─── 认证 API ─────────────────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')

        if not all([username, email, password]):
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        # 注册用户
        user = auth_manager.register_user(username, email, password, full_name)

        # 生成 Token
        token = auth_manager.generate_token(user)

        return jsonify({
            "success": True,
            "data": {
                "user": {
                    "user_id": user.user_id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.value,
                },
                "token": token,
            },
        }), 201

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.json
        username_or_email = data.get('username') or data.get('email')
        password = data.get('password')

        if not all([username_or_email, password]):
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        # 登录
        user, token = auth_manager.login(username_or_email, password)

        # 记录审计日志
        log = AuditLog(
            log_id=str(uuid.uuid4()),
            user_id=user.user_id,
            action="login",
            resource_type="auth",
            resource_id=None,
            timestamp=datetime.now().isoformat(),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
        )
        storage.add_audit_log(log)

        return jsonify({
            "success": True,
            "data": {
                "user": {
                    "user_id": user.user_id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.value,
                    "organization_id": user.organization_id,
                },
                "token": token,
            },
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 401
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """获取当前用户信息"""
    try:
        user = g.current_user

        # 获取用户权限
        permissions = storage.get_user_permissions(user)

        return jsonify({
            "success": True,
            "data": {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value,
                "status": user.status.value,
                "organization_id": user.organization_id,
                "team_ids": user.team_ids,
                "permissions": permissions,
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@auth_bp.route('/logout', methods=['POST'])
@require_auth
def logout():
    """用户登出"""
    try:
        user = g.current_user

        # 记录审计日志
        log = AuditLog(
            log_id=str(uuid.uuid4()),
            user_id=user.user_id,
            action="logout",
            resource_type="auth",
            resource_id=None,
            timestamp=datetime.now().isoformat(),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
        )
        storage.add_audit_log(log)

        return jsonify({
            "success": True,
            "message": "登出成功",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@auth_bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    """修改密码"""
    try:
        user = g.current_user
        data = request.json

        old_password = data.get('old_password')
        new_password = data.get('new_password')

        if not all([old_password, new_password]):
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        # 验证旧密码
        if not auth_manager.verify_password(old_password, user.password_hash):
            return jsonify({
                "success": False,
                "error": "旧密码错误",
            }), 400

        # 更新密码
        user.password_hash = auth_manager.hash_password(new_password)
        user.updated_at = datetime.now().isoformat()
        storage.update_user(user)

        return jsonify({
            "success": True,
            "message": "密码修改成功",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 用户管理 API ─────────────────────────────────────────────────────────────

@user_bp.route('/', methods=['GET'])
@require_permission('user:read')
def list_users():
    """列出用户"""
    try:
        organization_id = request.args.get('organization_id')
        role = request.args.get('role')
        status = request.args.get('status')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        role_enum = UserRole(role) if role else None
        status_enum = UserStatus(status) if status else None

        users = storage.list_users(
            organization_id=organization_id,
            role=role_enum,
            status=status_enum,
            limit=limit,
            offset=offset,
        )

        return jsonify({
            "success": True,
            "data": [
                {
                    "user_id": u.user_id,
                    "username": u.username,
                    "email": u.email,
                    "full_name": u.full_name,
                    "role": u.role.value,
                    "status": u.status.value,
                    "organization_id": u.organization_id,
                    "created_at": u.created_at,
                    "last_login_at": u.last_login_at,
                }
                for u in users
            ],
            "total": len(users),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@user_bp.route('/<user_id>', methods=['GET'])
@require_permission('user:read')
def get_user(user_id: str):
    """获取用户详情"""
    try:
        user = storage.get_user_by_id(user_id)

        if not user:
            return jsonify({
                "success": False,
                "error": "用户不存在",
            }), 404

        permissions = storage.get_user_permissions(user)

        return jsonify({
            "success": True,
            "data": {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value,
                "status": user.status.value,
                "organization_id": user.organization_id,
                "team_ids": user.team_ids,
                "permissions": permissions,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "last_login_at": user.last_login_at,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@user_bp.route('/<user_id>', methods=['PUT'])
@require_permission('user:write')
def update_user(user_id: str):
    """更新用户"""
    try:
        user = storage.get_user_by_id(user_id)

        if not user:
            return jsonify({
                "success": False,
                "error": "用户不存在",
            }), 404

        data = request.json

        # 更新字段
        if 'full_name' in data:
            user.full_name = data['full_name']
        if 'role' in data:
            user.role = UserRole(data['role'])
        if 'status' in data:
            user.status = UserStatus(data['status'])
        if 'organization_id' in data:
            user.organization_id = data['organization_id']

        user.updated_at = datetime.now().isoformat()
        storage.update_user(user)

        return jsonify({
            "success": True,
            "data": {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value,
                "status": user.status.value,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@user_bp.route('/<user_id>', methods=['DELETE'])
@require_permission('user:delete')
def delete_user(user_id: str):
    """删除用户（软删除）"""
    try:
        user = storage.get_user_by_id(user_id)

        if not user:
            return jsonify({
                "success": False,
                "error": "用户不存在",
            }), 404

        # 软删除
        user.status = UserStatus.DELETED
        user.updated_at = datetime.now().isoformat()
        storage.update_user(user)

        return jsonify({
            "success": True,
            "message": "用户已删除",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 组织管理 API ─────────────────────────────────────────────────────────────

@org_bp.route('/', methods=['POST'])
@require_permission('org:write')
def create_organization():
    """创建组织"""
    try:
        data = request.json
        name = data.get('name')
        slug = data.get('slug')

        if not all([name, slug]):
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        now = datetime.now().isoformat()
        org = Organization(
            organization_id=str(uuid.uuid4()),
            name=name,
            slug=slug,
            created_at=now,
            updated_at=now,
            description=data.get('description'),
        )

        storage.create_organization(org)

        return jsonify({
            "success": True,
            "data": {
                "organization_id": org.organization_id,
                "name": org.name,
                "slug": org.slug,
                "created_at": org.created_at,
            },
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@org_bp.route('/<organization_id>', methods=['GET'])
@require_permission('org:read')
def get_organization(organization_id: str):
    """获取组织详情"""
    try:
        org = storage.get_organization(organization_id)

        if not org:
            return jsonify({
                "success": False,
                "error": "组织不存在",
            }), 404

        return jsonify({
            "success": True,
            "data": {
                "organization_id": org.organization_id,
                "name": org.name,
                "slug": org.slug,
                "description": org.description,
                "member_count": org.member_count,
                "team_count": org.team_count,
                "created_at": org.created_at,
                "updated_at": org.updated_at,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500
