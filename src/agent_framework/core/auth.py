"""
用户认证和授权系统
支持用户注册、登录、JWT Token、密码加密
"""

from __future__ import annotations

import hashlib
import hmac
import jwt
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum
from agent_framework.core.database import DatabaseManager


# ─── 数据模型 ─────────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    """用户角色"""
    ADMIN = "admin"          # 管理员
    OWNER = "owner"          # 所有者
    MEMBER = "member"        # 成员
    VIEWER = "viewer"        # 查看者
    GUEST = "guest"          # 访客


class UserStatus(str, Enum):
    """用户状态"""
    ACTIVE = "active"        # 激活
    INACTIVE = "inactive"    # 未激活
    SUSPENDED = "suspended"  # 暂停
    DELETED = "deleted"      # 已删除


@dataclass
class User:
    """用户"""
    user_id: str
    username: str
    email: str
    password_hash: str
    role: UserRole = UserRole.MEMBER
    status: UserStatus = UserStatus.ACTIVE
    created_at: str = ""
    updated_at: str = ""
    last_login_at: Optional[str] = None

    # 个人信息
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None

    # 元数据
    metadata: Dict = field(default_factory=dict)

    # 组织信息
    organization_id: Optional[str] = None
    team_ids: List[str] = field(default_factory=list)


@dataclass
class Organization:
    """组织"""
    organization_id: str
    name: str
    slug: str  # URL 友好的标识符
    created_at: str
    updated_at: str

    # 组织信息
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None

    # 配置
    settings: Dict = field(default_factory=dict)

    # 统计
    member_count: int = 0
    team_count: int = 0


@dataclass
class Team:
    """团队"""
    team_id: str
    organization_id: str
    name: str
    slug: str
    created_at: str
    updated_at: str

    # 团队信息
    description: Optional[str] = None

    # 统计
    member_count: int = 0


@dataclass
class Permission:
    """权限"""
    permission_id: str
    name: str
    resource: str  # 资源类型: workflow, conversation, knowledge, etc.
    action: str    # 操作: read, write, delete, execute, etc.
    description: str = ""


@dataclass
class AuditLog:
    """审计日志"""
    log_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: Optional[str]
    timestamp: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Dict = field(default_factory=dict)


# ─── 用户存储 ─────────────────────────────────────────────────────────────────

class UserStorage:
    """用户数据持久化存储"""

    def __init__(self, db_path: str = "./data/users.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT,
                    full_name TEXT,
                    avatar_url TEXT,
                    phone TEXT,
                    metadata TEXT,
                    organization_id TEXT,
                    team_ids TEXT
                )
            """)

            # 组织表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS organizations (
                    organization_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    description TEXT,
                    logo_url TEXT,
                    website TEXT,
                    settings TEXT,
                    member_count INTEGER DEFAULT 0,
                    team_count INTEGER DEFAULT 0
                )
            """)

            # 团队表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    team_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    description TEXT,
                    member_count INTEGER DEFAULT 0,
                    FOREIGN KEY (organization_id) REFERENCES organizations(organization_id),
                    UNIQUE(organization_id, slug)
                )
            """)

            # 权限表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS permissions (
                    permission_id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    resource TEXT NOT NULL,
                    action TEXT NOT NULL,
                    description TEXT
                )
            """)

            # 角色权限关联表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS role_permissions (
                    role TEXT NOT NULL,
                    permission_id TEXT NOT NULL,
                    PRIMARY KEY (role, permission_id),
                    FOREIGN KEY (permission_id) REFERENCES permissions(permission_id)
                )
            """)

            # 审计日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT,
                    timestamp TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    details TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_teams_org ON teams(organization_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, timestamp DESC)")

        # 初始化默认权限
        self._init_default_permissions()

    def _init_default_permissions(self):
        """初始化默认权限"""
        default_permissions = [
            # 工作流权限
            Permission("perm_workflow_read", "workflow:read", "workflow", "read", "查看工作流"),
            Permission("perm_workflow_write", "workflow:write", "workflow", "write", "编辑工作流"),
            Permission("perm_workflow_delete", "workflow:delete", "workflow", "delete", "删除工作流"),
            Permission("perm_workflow_execute", "workflow:execute", "workflow", "execute", "执行工作流"),

            # 对话权限
            Permission("perm_conversation_read", "conversation:read", "conversation", "read", "查看对话"),
            Permission("perm_conversation_write", "conversation:write", "conversation", "write", "创建对话"),
            Permission("perm_conversation_delete", "conversation:delete", "conversation", "delete", "删除对话"),

            # 知识库权限
            Permission("perm_knowledge_read", "knowledge:read", "knowledge", "read", "查看知识库"),
            Permission("perm_knowledge_write", "knowledge:write", "knowledge", "write", "编辑知识库"),
            Permission("perm_knowledge_delete", "knowledge:delete", "knowledge", "delete", "删除知识库"),

            # 用户管理权限
            Permission("perm_user_read", "user:read", "user", "read", "查看用户"),
            Permission("perm_user_write", "user:write", "user", "write", "管理用户"),
            Permission("perm_user_delete", "user:delete", "user", "delete", "删除用户"),

            # 组织管理权限
            Permission("perm_org_read", "org:read", "organization", "read", "查看组织"),
            Permission("perm_org_write", "org:write", "organization", "write", "管理组织"),
            Permission("perm_org_delete", "org:delete", "organization", "delete", "删除组织"),
        ]

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            for perm in default_permissions:
                cursor.execute("""
                    INSERT OR IGNORE INTO permissions
                    (permission_id, name, resource, action, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (perm.permission_id, perm.name, perm.resource, perm.action, perm.description))

            # 配置默认角色权限
            role_permissions = {
                UserRole.ADMIN: [p.permission_id for p in default_permissions],  # 管理员拥有所有权限
                UserRole.OWNER: [p.permission_id for p in default_permissions if "delete" not in p.action],  # 所有者不能删除
                UserRole.MEMBER: [p.permission_id for p in default_permissions if p.action in ["read", "write", "execute"]],
                UserRole.VIEWER: [p.permission_id for p in default_permissions if p.action == "read"],
                UserRole.GUEST: ["perm_workflow_read", "perm_conversation_read"],
            }

            for role, perm_ids in role_permissions.items():
                for perm_id in perm_ids:
                    cursor.execute("""
                        INSERT OR IGNORE INTO role_permissions (role, permission_id)
                        VALUES (?, ?)
                    """, (role.value, perm_id))

    def create_user(self, user: User):
        """创建用户"""
        import json
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users
                (user_id, username, email, password_hash, role, status,
                 created_at, updated_at, last_login_at, full_name, avatar_url,
                 phone, metadata, organization_id, team_ids)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user.user_id,
                user.username,
                user.email,
                user.password_hash,
                user.role.value,
                user.status.value,
                user.created_at,
                user.updated_at,
                user.last_login_at,
                user.full_name,
                user.avatar_url,
                user.phone,
                json.dumps(user.metadata),
                user.organization_id,
                json.dumps(user.team_ids),
            ))

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """通过 ID 获取用户"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_user(row)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """通过邮箱获取用户"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_user(row)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """通过用户名获取用户"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_user(row)

    def update_user(self, user: User):
        """更新用户"""
        import json
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET
                    username = ?,
                    email = ?,
                    role = ?,
                    status = ?,
                    updated_at = ?,
                    last_login_at = ?,
                    full_name = ?,
                    avatar_url = ?,
                    phone = ?,
                    metadata = ?,
                    organization_id = ?,
                    team_ids = ?
                WHERE user_id = ?
            """, (
                user.username,
                user.email,
                user.role.value,
                user.status.value,
                user.updated_at,
                user.last_login_at,
                user.full_name,
                user.avatar_url,
                user.phone,
                json.dumps(user.metadata),
                user.organization_id,
                json.dumps(user.team_ids),
                user.user_id,
            ))

    def list_users(
        self,
        organization_id: Optional[str] = None,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[User]:
        """列出用户"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM users WHERE 1=1"
            params = []

            if organization_id:
                query += " AND organization_id = ?"
                params.append(organization_id)
            if role:
                query += " AND role = ?"
                params.append(role.value)
            if status:
                query += " AND status = ?"
                params.append(status.value)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [self._row_to_user(row) for row in rows]

    def _row_to_user(self, row) -> User:
        """将数据库行转换为 User 对象"""
        import json

        return User(
            user_id=row[0],
            username=row[1],
            email=row[2],
            password_hash=row[3],
            role=UserRole(row[4]),
            status=UserStatus(row[5]),
            created_at=row[6],
            updated_at=row[7],
            last_login_at=row[8],
            full_name=row[9],
            avatar_url=row[10],
            phone=row[11],
            metadata=json.loads(row[12]) if row[12] else {},
            organization_id=row[13],
            team_ids=json.loads(row[14]) if row[14] else [],
        )

    def create_organization(self, org: Organization):
        """创建组织"""
        import json
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO organizations
                (organization_id, name, slug, created_at, updated_at,
                 description, logo_url, website, settings, member_count, team_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                org.organization_id,
                org.name,
                org.slug,
                org.created_at,
                org.updated_at,
                org.description,
                org.logo_url,
                org.website,
                json.dumps(org.settings),
                org.member_count,
                org.team_count,
            ))

    def get_organization(self, organization_id: str) -> Optional[Organization]:
        """获取组织"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM organizations WHERE organization_id = ?", (organization_id,))
            row = cursor.fetchone()

        if not row:
            return None

        import json

        return Organization(
            organization_id=row[0],
            name=row[1],
            slug=row[2],
            created_at=row[3],
            updated_at=row[4],
            description=row[5],
            logo_url=row[6],
            website=row[7],
            settings=json.loads(row[8]) if row[8] else {},
            member_count=row[9],
            team_count=row[10],
        )

    def add_audit_log(self, log: AuditLog):
        """添加审计日志"""
        import json
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs
                (log_id, user_id, action, resource_type, resource_id,
                 timestamp, ip_address, user_agent, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log.log_id,
                log.user_id,
                log.action,
                log.resource_type,
                log.resource_id,
                log.timestamp,
                log.ip_address,
                log.user_agent,
                json.dumps(log.details),
            ))

    def get_user_permissions(self, user: User) -> List[str]:
        """获取用户权限列表"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.name FROM permissions p
                JOIN role_permissions rp ON p.permission_id = rp.permission_id
                WHERE rp.role = ?
            """, (user.role.value,))
            rows = cursor.fetchall()

        return [row[0] for row in rows]


# ─── 认证管理器 ───────────────────────────────────────────────────────────────

class AuthManager:
    """认证管理器"""

    def __init__(self, storage: UserStorage, secret_key: str):
        self.storage = storage
        self.secret_key = secret_key

    def hash_password(self, password: str) -> str:
        """密码哈希"""
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return f"{salt}${pwd_hash.hex()}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            salt, pwd_hash = password_hash.split('$')
            new_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            return hmac.compare_digest(new_hash.hex(), pwd_hash)
        except:
            return False

    def register_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> User:
        """注册用户"""
        import uuid

        # 检查用户名和邮箱是否已存在
        if self.storage.get_user_by_username(username):
            raise ValueError("用户名已存在")
        if self.storage.get_user_by_email(email):
            raise ValueError("邮箱已存在")

        # 创建用户
        now = datetime.now().isoformat()
        user = User(
            user_id=str(uuid.uuid4()),
            username=username,
            email=email,
            password_hash=self.hash_password(password),
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            full_name=full_name,
        )

        self.storage.create_user(user)
        return user

    def login(self, username_or_email: str, password: str) -> tuple[User, str]:
        """登录"""
        # 查找用户
        user = self.storage.get_user_by_username(username_or_email)
        if not user:
            user = self.storage.get_user_by_email(username_or_email)

        if not user:
            raise ValueError("用户不存在")

        # 验证密码
        if not self.verify_password(password, user.password_hash):
            raise ValueError("密码错误")

        # 检查用户状态
        if user.status != UserStatus.ACTIVE:
            raise ValueError(f"用户状态异常: {user.status.value}")

        # 更新最后登录时间
        user.last_login_at = datetime.now().isoformat()
        self.storage.update_user(user)

        # 生成 JWT Token
        token = self.generate_token(user)

        return user, token

    def generate_token(self, user: User, expires_in: int = 86400) -> str:
        """生成 JWT Token"""
        now = datetime.now(UTC)
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "exp": now + timedelta(seconds=expires_in),
            "iat": now,
        }

        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def verify_token(self, token: str) -> Optional[Dict]:
        """验证 JWT Token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def check_permission(self, user: User, permission: str) -> bool:
        """检查用户权限"""
        user_permissions = self.storage.get_user_permissions(user)
        return permission in user_permissions
