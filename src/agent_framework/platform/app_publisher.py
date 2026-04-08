"""
应用发布系统
支持应用一键发布为 API、生成访问密钥、嵌入代码
"""

import agent_framework.core.fast_json as json
import uuid
import secrets
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

from agent_framework.core.database import DatabaseManager


@dataclass
class PublishedApp:
    """已发布的应用"""
    publish_id: str
    app_id: str
    version_id: str
    api_key: str
    endpoint: str
    status: str  # active, paused, revoked
    created_at: str
    expires_at: Optional[str] = None

    # 访问控制
    allowed_origins: List[str] = None
    rate_limit: int = 100  # 每分钟请求数

    # 统计
    request_count: int = 0
    last_accessed: Optional[str] = None

    def __post_init__(self):
        if self.allowed_origins is None:
            self.allowed_origins = ["*"]


class AppPublisher:
    """应用发布管理器"""

    def __init__(self, db_path: str = "data/published_apps.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        self._init_db()

    @staticmethod
    def _row_to_published_app(row) -> PublishedApp:
        return PublishedApp(
            publish_id=row[0],
            app_id=row[1],
            version_id=row[2],
            api_key=row[3],
            endpoint=row[4],
            status=row[5],
            created_at=row[6],
            expires_at=row[7],
            allowed_origins=json.loads(row[8]),
            rate_limit=row[9],
            request_count=row[10],
            last_accessed=row[11],
        )

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 已发布应用表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS published_apps (
                    publish_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    api_key TEXT UNIQUE NOT NULL,
                    endpoint TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TEXT,
                    expires_at TEXT,
                    allowed_origins TEXT,
                    rate_limit INTEGER DEFAULT 100,
                    request_count INTEGER DEFAULT 0,
                    last_accessed TEXT
                )
            """)

            # 嵌入配置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS embed_configs (
                    embed_id TEXT PRIMARY KEY,
                    publish_id TEXT NOT NULL,
                    embed_type TEXT NOT NULL,
                    config TEXT,
                    created_at TEXT,
                    FOREIGN KEY (publish_id) REFERENCES published_apps(publish_id)
                )
            """)

            # API 调用日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_logs (
                    log_id TEXT PRIMARY KEY,
                    publish_id TEXT NOT NULL,
                    timestamp TEXT,
                    method TEXT,
                    path TEXT,
                    status_code INTEGER,
                    response_time REAL,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (publish_id) REFERENCES published_apps(publish_id)
                )
            """)

    def publish_app(
        self,
        app_id: str,
        version_id: str,
        allowed_origins: List[str] = None,
        rate_limit: int = 100,
        expires_at: Optional[str] = None,
    ) -> PublishedApp:
        """发布应用"""
        publish_id = str(uuid.uuid4())
        api_key = f"sk-{secrets.token_urlsafe(32)}"
        endpoint = f"/api/apps/{publish_id}/invoke"

        published_app = PublishedApp(
            publish_id=publish_id,
            app_id=app_id,
            version_id=version_id,
            api_key=api_key,
            endpoint=endpoint,
            status="active",
            created_at=datetime.now().isoformat(),
            expires_at=expires_at,
            allowed_origins=allowed_origins or ["*"],
            rate_limit=rate_limit,
        )

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO published_apps
                (publish_id, app_id, version_id, api_key, endpoint, status,
                 created_at, expires_at, allowed_origins, rate_limit, request_count, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                published_app.publish_id,
                published_app.app_id,
                published_app.version_id,
                published_app.api_key,
                published_app.endpoint,
                published_app.status,
                published_app.created_at,
                published_app.expires_at,
                json.dumps(published_app.allowed_origins),
                published_app.rate_limit,
                published_app.request_count,
                published_app.last_accessed,
            ))

        return published_app

    def get_published_app(self, publish_id: str) -> Optional[PublishedApp]:
        """获取已发布应用"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM published_apps WHERE publish_id = ?", (publish_id,))
            row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_published_app(row)

    def verify_api_key(self, api_key: str) -> Optional[PublishedApp]:
        """验证 API Key"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM published_apps WHERE api_key = ? AND status = 'active'",
                (api_key,)
            )
            row = cursor.fetchone()

        if not row:
            return None

        # 检查是否过期
        if row[7]:  # expires_at
            expires_at = datetime.fromisoformat(row[7])
            if datetime.now() > expires_at:
                return None

        return self._row_to_published_app(row)

    def update_status(self, publish_id: str, status: str) -> bool:
        """更新发布状态"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE published_apps SET status = ? WHERE publish_id = ?",
                (status, publish_id)
            )
            updated = cursor.rowcount > 0

        return updated

    def increment_request_count(self, publish_id: str):
        """增加请求计数"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE published_apps
                SET request_count = request_count + 1,
                    last_accessed = ?
                WHERE publish_id = ?
            """, (datetime.now().isoformat(), publish_id))

    def generate_embed_code(
        self,
        publish_id: str,
        embed_type: str = "iframe",
        config: Dict = None,
    ) -> str:
        """生成嵌入代码"""
        published_app = self.get_published_app(publish_id)
        if not published_app:
            raise ValueError("Published app not found")

        config = config or {}
        embed_id = str(uuid.uuid4())

        # 保存嵌入配置
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO embed_configs (embed_id, publish_id, embed_type, config, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                embed_id,
                publish_id,
                embed_type,
                json.dumps(config),
                datetime.now().isoformat(),
            ))

        # 生成代码
        if embed_type == "iframe":
            width = config.get("width", "100%")
            height = config.get("height", "600px")
            return f'''<iframe
    src="https://your-domain.com/embed/{embed_id}"
    width="{width}"
    height="{height}"
    frameborder="0"
    allow="microphone; camera"
></iframe>'''

        elif embed_type == "widget":
            return f'''<div id="agent-widget-{embed_id}"></div>
<script src="https://your-domain.com/widget.js"></script>
<script>
  AgentWidget.init({{
    embedId: "{embed_id}",
    apiKey: "{published_app.api_key}",
    ...{json.dumps(config, indent=2)}
  }});
</script>'''

        elif embed_type == "sdk":
            return f'''// JavaScript SDK
import {{ AgentClient }} from '@agent-framework/sdk';

const client = new AgentClient({{
  apiKey: '{published_app.api_key}',
  endpoint: '{published_app.endpoint}',
}});

// 调用应用
const response = await client.invoke({{
  input: 'Your input here',
  ...{json.dumps(config, indent=2)}
}});

console.log(response);'''

        else:
            raise ValueError(f"Unknown embed type: {embed_type}")

    def log_api_call(
        self,
        publish_id: str,
        method: str,
        path: str,
        status_code: int,
        response_time: float,
        ip_address: str = None,
        user_agent: str = None,
    ):
        """记录 API 调用"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_logs
                (log_id, publish_id, timestamp, method, path, status_code,
                 response_time, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                publish_id,
                datetime.now().isoformat(),
                method,
                path,
                status_code,
                response_time,
                ip_address,
                user_agent,
            ))

    def get_api_stats(self, publish_id: str, time_range: str = "24h") -> Dict:
        """获取 API 统计"""
        # 计算时间范围
        from datetime import timedelta
        now = datetime.now()
        if time_range == "1h":
            start_time = now - timedelta(hours=1)
        elif time_range == "24h":
            start_time = now - timedelta(days=1)
        elif time_range == "7d":
            start_time = now - timedelta(days=7)
        elif time_range == "30d":
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(days=1)

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 总请求数
            cursor.execute("""
                SELECT COUNT(*) FROM api_logs
                WHERE publish_id = ? AND timestamp >= ?
            """, (publish_id, start_time.isoformat()))
            total_requests = cursor.fetchone()[0]

            # 平均响应时间
            cursor.execute("""
                SELECT AVG(response_time) FROM api_logs
                WHERE publish_id = ? AND timestamp >= ?
            """, (publish_id, start_time.isoformat()))
            avg_response_time = cursor.fetchone()[0] or 0.0

            # 错误率
            cursor.execute("""
                SELECT
                    COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count,
                    COUNT(*) as total_count
                FROM api_logs
                WHERE publish_id = ? AND timestamp >= ?
            """, (publish_id, start_time.isoformat()))
            error_count, total_count = cursor.fetchone()
        error_rate = (error_count / total_count * 100) if total_count > 0 else 0.0

        return {
            "total_requests": total_requests,
            "avg_response_time": round(avg_response_time, 2),
            "error_rate": round(error_rate, 2),
            "time_range": time_range,
        }

    def list_published_apps(self, app_id: Optional[str] = None) -> List[PublishedApp]:
        """列出已发布应用"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            if app_id:
                cursor.execute("SELECT * FROM published_apps WHERE app_id = ?", (app_id,))
            else:
                cursor.execute("SELECT * FROM published_apps")

            rows = cursor.fetchall()

        apps = []
        for row in rows:
            apps.append(self._row_to_published_app(row))

        return apps
