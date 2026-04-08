"""
应用管理系统
支持应用创建、模板、发布、版本控制
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum
from agent_framework.core.database import DatabaseManager


# ─── 数据模型 ─────────────────────────────────────────────────────────────────

class AppType(str, Enum):
    """应用类型"""
    CHATBOT = "chatbot"          # 聊天机器人
    WORKFLOW = "workflow"        # 工作流应用
    AGENT = "agent"              # Agent 应用
    API = "api"                  # API 应用
    CUSTOM = "custom"            # 自定义应用


class AppStatus(str, Enum):
    """应用状态"""
    DRAFT = "draft"              # 草稿
    PUBLISHED = "published"      # 已发布
    ARCHIVED = "archived"        # 已归档
    DELETED = "deleted"          # 已删除


class AppVisibility(str, Enum):
    """应用可见性"""
    PRIVATE = "private"          # 私有
    TEAM = "team"                # 团队可见
    ORGANIZATION = "organization" # 组织可见
    PUBLIC = "public"            # 公开


@dataclass
class Application:
    """应用"""
    app_id: str
    name: str
    slug: str  # URL 友好标识符
    type: AppType
    status: AppStatus
    visibility: AppVisibility
    created_at: str
    updated_at: str

    # 应用信息
    description: Optional[str] = None
    icon: Optional[str] = None
    cover_image: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # 所有者信息
    owner_id: str = ""
    organization_id: Optional[str] = None
    team_id: Optional[str] = None

    # 配置
    config: Dict = field(default_factory=dict)

    # 统计
    version_count: int = 0
    usage_count: int = 0
    rating: float = 0.0
    rating_count: int = 0

    # 元数据
    metadata: Dict = field(default_factory=dict)


@dataclass
class AppVersion:
    """应用版本"""
    version_id: str
    app_id: str
    version: str  # 版本号 (e.g., "1.0.0")
    created_at: str

    # 版本信息
    changelog: Optional[str] = None
    is_latest: bool = False

    # 配置快照
    config_snapshot: Dict = field(default_factory=dict)

    # 创建者
    created_by: str = ""


@dataclass
class AppTemplate:
    """应用模板"""
    template_id: str
    name: str
    slug: str
    type: AppType
    created_at: str

    # 模板信息
    description: Optional[str] = None
    icon: Optional[str] = None
    cover_image: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    category: Optional[str] = None

    # 模板配置
    config: Dict = field(default_factory=dict)

    # 统计
    usage_count: int = 0
    rating: float = 0.0

    # 是否官方模板
    is_official: bool = False


@dataclass
class AppShare:
    """应用分享"""
    share_id: str
    app_id: str
    created_at: str
    expires_at: Optional[str] = None

    # 分享配置
    share_token: str = ""
    is_public: bool = False
    allow_fork: bool = True

    # 统计
    view_count: int = 0
    fork_count: int = 0


# ─── 应用存储 ─────────────────────────────────────────────────────────────────

class ApplicationStorage:
    """应用持久化存储"""

    def __init__(self, db_path: str = "./data/applications.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 应用表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    app_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    description TEXT,
                    icon TEXT,
                    cover_image TEXT,
                    tags TEXT,
                    owner_id TEXT NOT NULL,
                    organization_id TEXT,
                    team_id TEXT,
                    config TEXT,
                    version_count INTEGER DEFAULT 0,
                    usage_count INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0.0,
                    rating_count INTEGER DEFAULT 0,
                    metadata TEXT
                )
            """)

            # 应用版本表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_versions (
                    version_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    changelog TEXT,
                    is_latest INTEGER DEFAULT 0,
                    config_snapshot TEXT,
                    created_by TEXT NOT NULL,
                    FOREIGN KEY (app_id) REFERENCES applications(app_id),
                    UNIQUE(app_id, version)
                )
            """)

            # 应用模板表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_templates (
                    template_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    description TEXT,
                    icon TEXT,
                    cover_image TEXT,
                    tags TEXT,
                    category TEXT,
                    config TEXT,
                    usage_count INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0.0,
                    is_official INTEGER DEFAULT 0
                )
            """)

            # 应用分享表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_shares (
                    share_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    share_token TEXT UNIQUE NOT NULL,
                    is_public INTEGER DEFAULT 0,
                    allow_fork INTEGER DEFAULT 1,
                    view_count INTEGER DEFAULT 0,
                    fork_count INTEGER DEFAULT 0,
                    FOREIGN KEY (app_id) REFERENCES applications(app_id)
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_apps_owner ON applications(owner_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_apps_org ON applications(organization_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_versions_app ON app_versions(app_id, created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_type ON app_templates(type)")

        # 初始化默认模板
        self._init_default_templates()

    def _init_default_templates(self):
        """初始化默认模板"""
        default_templates = [
            AppTemplate(
                template_id="tpl_chatbot_basic",
                name="基础聊天机器人",
                slug="chatbot-basic",
                type=AppType.CHATBOT,
                created_at=datetime.now().isoformat(),
                description="简单的问答聊天机器人，适合快速开始",
                icon="💬",
                category="聊天",
                tags=["聊天", "基础", "快速开始"],
                is_official=True,
                config={
                    "model": "gpt-4o",
                    "temperature": 0.7,
                    "system_prompt": "你是一个友好的助手。",
                },
            ),
            AppTemplate(
                template_id="tpl_workflow_automation",
                name="工作流自动化",
                slug="workflow-automation",
                type=AppType.WORKFLOW,
                created_at=datetime.now().isoformat(),
                description="自动化业务流程，提高工作效率",
                icon="🔄",
                category="自动化",
                tags=["工作流", "自动化", "效率"],
                is_official=True,
                config={
                    "workflow_type": "sequential",
                    "max_steps": 10,
                },
            ),
            AppTemplate(
                template_id="tpl_rag_qa",
                name="知识库问答",
                slug="rag-qa",
                type=AppType.AGENT,
                created_at=datetime.now().isoformat(),
                description="基于知识库的智能问答系统",
                icon="📚",
                category="知识管理",
                tags=["RAG", "问答", "知识库"],
                is_official=True,
                config={
                    "retrieval_top_k": 3,
                    "model": "gpt-4o",
                },
            ),
            AppTemplate(
                template_id="tpl_api_service",
                name="API 服务",
                slug="api-service",
                type=AppType.API,
                created_at=datetime.now().isoformat(),
                description="将 AI 能力封装为 API 服务",
                icon="🔌",
                category="API",
                tags=["API", "服务", "集成"],
                is_official=True,
                config={
                    "rate_limit": 100,
                    "auth_required": True,
                },
            ),
        ]

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            for template in default_templates:
                cursor.execute("""
                    INSERT OR IGNORE INTO app_templates
                    (template_id, name, slug, type, created_at, description,
                     icon, cover_image, tags, category, config, usage_count,
                     rating, is_official)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    template.template_id,
                    template.name,
                    template.slug,
                    template.type.value,
                    template.created_at,
                    template.description,
                    template.icon,
                    template.cover_image,
                    json.dumps(template.tags),
                    template.category,
                    json.dumps(template.config),
                    template.usage_count,
                    template.rating,
                    1 if template.is_official else 0,
                ))

    def create_application(self, app: Application):
        """创建应用"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO applications
                (app_id, name, slug, type, status, visibility, created_at, updated_at,
                 description, icon, cover_image, tags, owner_id, organization_id,
                 team_id, config, version_count, usage_count, rating, rating_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app.app_id,
                app.name,
                app.slug,
                app.type.value,
                app.status.value,
                app.visibility.value,
                app.created_at,
                app.updated_at,
                app.description,
                app.icon,
                app.cover_image,
                json.dumps(app.tags),
                app.owner_id,
                app.organization_id,
                app.team_id,
                json.dumps(app.config),
                app.version_count,
                app.usage_count,
                app.rating,
                app.rating_count,
                json.dumps(app.metadata),
            ))

    def get_application(self, app_id: str) -> Optional[Application]:
        """获取应用"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM applications WHERE app_id = ?", (app_id,))
            row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_app(row)

    def update_application(self, app: Application):
        """更新应用"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE applications SET
                    name = ?,
                    slug = ?,
                    status = ?,
                    visibility = ?,
                    updated_at = ?,
                    description = ?,
                    icon = ?,
                    cover_image = ?,
                    tags = ?,
                    config = ?,
                    version_count = ?,
                    usage_count = ?,
                    rating = ?,
                    rating_count = ?,
                    metadata = ?
                WHERE app_id = ?
            """, (
                app.name,
                app.slug,
                app.status.value,
                app.visibility.value,
                app.updated_at,
                app.description,
                app.icon,
                app.cover_image,
                json.dumps(app.tags),
                json.dumps(app.config),
                app.version_count,
                app.usage_count,
                app.rating,
                app.rating_count,
                json.dumps(app.metadata),
                app.app_id,
            ))

    def list_applications(
        self,
        owner_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        type: Optional[AppType] = None,
        status: Optional[AppStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Application]:
        """列出应用"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM applications WHERE 1=1"
            params = []

            if owner_id:
                query += " AND owner_id = ?"
                params.append(owner_id)
            if organization_id:
                query += " AND organization_id = ?"
                params.append(organization_id)
            if type:
                query += " AND type = ?"
                params.append(type.value)
            if status:
                query += " AND status = ?"
                params.append(status.value)

            query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [self._row_to_app(row) for row in rows]

    def create_version(self, version: AppVersion):
        """创建版本"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 如果是最新版本，将其他版本设为非最新
            if version.is_latest:
                cursor.execute("""
                    UPDATE app_versions SET is_latest = 0 WHERE app_id = ?
                """, (version.app_id,))

            cursor.execute("""
                INSERT INTO app_versions
                (version_id, app_id, version, created_at, changelog,
                 is_latest, config_snapshot, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                version.version_id,
                version.app_id,
                version.version,
                version.created_at,
                version.changelog,
                1 if version.is_latest else 0,
                json.dumps(version.config_snapshot),
                version.created_by,
            ))

            # 更新应用的版本计数
            cursor.execute("""
                UPDATE applications SET version_count = version_count + 1
                WHERE app_id = ?
            """, (version.app_id,))

    def list_templates(
        self,
        type: Optional[AppType] = None,
        category: Optional[str] = None,
        is_official: Optional[bool] = None,
    ) -> List[AppTemplate]:
        """列出模板"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM app_templates WHERE 1=1"
            params = []

            if type:
                query += " AND type = ?"
                params.append(type.value)
            if category:
                query += " AND category = ?"
                params.append(category)
            if is_official is not None:
                query += " AND is_official = ?"
                params.append(1 if is_official else 0)

            query += " ORDER BY usage_count DESC, rating DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

        templates = []
        for row in rows:
            templates.append(AppTemplate(
                template_id=row[0],
                name=row[1],
                slug=row[2],
                type=AppType(row[3]),
                created_at=row[4],
                description=row[5],
                icon=row[6],
                cover_image=row[7],
                tags=json.loads(row[8]) if row[8] else [],
                category=row[9],
                config=json.loads(row[10]) if row[10] else {},
                usage_count=row[11],
                rating=row[12],
                is_official=bool(row[13]),
            ))

        return templates

    def _row_to_app(self, row) -> Application:
        """将数据库行转换为 Application 对象"""
        return Application(
            app_id=row[0],
            name=row[1],
            slug=row[2],
            type=AppType(row[3]),
            status=AppStatus(row[4]),
            visibility=AppVisibility(row[5]),
            created_at=row[6],
            updated_at=row[7],
            description=row[8],
            icon=row[9],
            cover_image=row[10],
            tags=json.loads(row[11]) if row[11] else [],
            owner_id=row[12],
            organization_id=row[13],
            team_id=row[14],
            config=json.loads(row[15]) if row[15] else {},
            version_count=row[16],
            usage_count=row[17],
            rating=row[18],
            rating_count=row[19],
            metadata=json.loads(row[20]) if row[20] else {},
        )


# ─── 应用管理器 ───────────────────────────────────────────────────────────────

class ApplicationManager:
    """应用管理器"""

    def __init__(self, storage: ApplicationStorage):
        self.storage = storage

    def create_application(
        self,
        name: str,
        type: AppType,
        owner_id: str,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        config: Optional[Dict] = None,
    ) -> Application:
        """创建应用"""
        now = datetime.now().isoformat()

        # 生成 slug
        if not slug:
            slug = name.lower().replace(' ', '-').replace('_', '-')

        app = Application(
            app_id=str(uuid.uuid4()),
            name=name,
            slug=slug,
            type=type,
            status=AppStatus.DRAFT,
            visibility=AppVisibility.PRIVATE,
            created_at=now,
            updated_at=now,
            description=description,
            owner_id=owner_id,
            config=config or {},
        )

        self.storage.create_application(app)
        return app

    def create_from_template(
        self,
        template_id: str,
        name: str,
        owner_id: str,
    ) -> Application:
        """从模板创建应用"""
        # 获取模板
        templates = self.storage.list_templates()
        template = next((t for t in templates if t.template_id == template_id), None)

        if not template:
            raise ValueError("模板不存在")

        # 创建应用
        app = self.create_application(
            name=name,
            type=template.type,
            owner_id=owner_id,
            description=template.description,
            config=template.config.copy(),
        )

        # 更新模板使用计数
        with self.storage.db_manager.get_connection(self.storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE app_templates SET usage_count = usage_count + 1
                WHERE template_id = ?
            """, (template_id,))

        return app

    def publish_application(self, app_id: str, version: str, changelog: Optional[str] = None):
        """发布应用"""
        app = self.storage.get_application(app_id)
        if not app:
            raise ValueError("应用不存在")

        # 创建版本
        app_version = AppVersion(
            version_id=str(uuid.uuid4()),
            app_id=app_id,
            version=version,
            created_at=datetime.now().isoformat(),
            changelog=changelog,
            is_latest=True,
            config_snapshot=app.config.copy(),
            created_by=app.owner_id,
        )

        self.storage.create_version(app_version)

        # 更新应用状态
        app.status = AppStatus.PUBLISHED
        app.updated_at = datetime.now().isoformat()
        self.storage.update_application(app)

    def fork_application(self, app_id: str, new_owner_id: str, new_name: Optional[str] = None) -> Application:
        """复制应用"""
        original_app = self.storage.get_application(app_id)
        if not original_app:
            raise ValueError("应用不存在")

        # 创建新应用
        now = datetime.now().isoformat()
        forked_app = Application(
            app_id=str(uuid.uuid4()),
            name=new_name or f"{original_app.name} (副本)",
            slug=f"{original_app.slug}-fork-{uuid.uuid4().hex[:8]}",
            type=original_app.type,
            status=AppStatus.DRAFT,
            visibility=AppVisibility.PRIVATE,
            created_at=now,
            updated_at=now,
            description=original_app.description,
            icon=original_app.icon,
            tags=original_app.tags.copy(),
            owner_id=new_owner_id,
            config=original_app.config.copy(),
            metadata={"forked_from": app_id},
        )

        self.storage.create_application(forked_app)
        return forked_app
