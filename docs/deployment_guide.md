# 部署指南

本文档提供 Agent Framework 的部署方案和最佳实践。

## 目录

- [部署方式](#部署方式)
- [Docker 部署](#docker-部署)
- [生产环境配置](#生产环境配置)
- [性能优化](#性能优化)
- [监控和日志](#监控和日志)
- [备份和恢复](#备份和恢复)
- [安全加固](#安全加固)

---

## 部署方式

### 1. 单机部署

适用于开发、测试和小规模生产环境。

**优点：**
- 部署简单
- 维护成本低
- 适合快速验证

**缺点：**
- 单点故障
- 扩展性有限

### 2. Docker 部署

推荐用于生产环境。

**优点：**
- 环境一致性
- 易于扩展
- 资源隔离

### 3. Kubernetes 部署

适用于大规模生产环境。

**优点：**
- 高可用
- 自动扩展
- 服务编排

---

## Docker 部署

### 1. 构建镜像

```bash
# 构建主应用镜像
docker build -t agent-framework:latest .

# 查看镜像
docker images | grep agent-framework
```

### 2. 使用 Docker Compose

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f web

# 停止服务
docker-compose down
```

### 3. Docker Compose 配置

`docker-compose.yml`:

```yaml
version: '3.8'

services:
  web:
    build: .
    image: agent-framework:latest
    container_name: agent-framework-web
    ports:
      - "5000:5000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=sqlite:////data/agent_framework.db
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - ./data:/data
      - ./logs:/logs
    depends_on:
      - redis
    restart: unless-stopped
    networks:
      - agent-network

  redis:
    image: redis:7-alpine
    container_name: agent-framework-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped
    networks:
      - agent-network

  nginx:
    image: nginx:alpine
    container_name: agent-framework-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - web
    restart: unless-stopped
    networks:
      - agent-network

volumes:
  redis-data:

networks:
  agent-network:
    driver: bridge
```

### 4. Nginx 反向代理配置

`nginx.conf`:

```nginx
upstream agent_framework {
    server web:5000;
}

server {
    listen 80;
    server_name your-domain.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 日志
    access_log /var/log/nginx/agent_framework_access.log;
    error_log /var/log/nginx/agent_framework_error.log;

    # 静态文件
    location /static {
        alias /app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # WebSocket 支持
    location /socket.io {
        proxy_pass http://agent_framework;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API 请求
    location / {
        proxy_pass http://agent_framework;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # 缓冲设置
        proxy_buffering off;
    }
}
```

---

## 生产环境配置

### 1. 环境变量

生产环境 `.env`:

```bash
# 生产模式
DEBUG=False
FLASK_ENV=production

# 安全密钥（使用强随机字符串）
SECRET_KEY=your-very-long-random-secret-key-here

# LLM 配置
OPENAI_API_KEY=sk-...
DEFAULT_MODEL=gpt-4

# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/agent_framework

# Redis
REDIS_URL=redis://localhost:6379/0

# 日志级别
LOG_LEVEL=INFO

# 限流配置
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=100

# CORS 配置
CORS_ORIGINS=https://your-domain.com

# 会话配置
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
```

### 2. 数据库迁移到 PostgreSQL

```python
# config.yaml
database:
  type: postgresql
  host: localhost
  port: 5432
  name: agent_framework
  user: agent_user
  password: ${DB_PASSWORD}
  pool_size: 20
  max_overflow: 10
```

### 3. 使用 Gunicorn

```bash
# 安装 Gunicorn
pip install gunicorn gevent

# 启动应用
gunicorn -w 4 -k gevent \
  --bind 0.0.0.0:5000 \
  --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  agent_framework.web.web_ui:app
```

`gunicorn.conf.py`:

```python
import multiprocessing

# 服务器配置
bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gevent"
worker_connections = 1000
timeout = 120
keepalive = 5

# 日志
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"

# 进程命名
proc_name = "agent-framework"

# 优雅重启
graceful_timeout = 30
```

### 4. Systemd 服务

`/etc/systemd/system/agent-framework.service`:

```ini
[Unit]
Description=Agent Framework Web Service
After=network.target

[Service]
Type=notify
User=agent
Group=agent
WorkingDirectory=/opt/agent-framework
Environment="PATH=/opt/agent-framework/.venv/bin"
ExecStart=/opt/agent-framework/.venv/bin/gunicorn -c gunicorn.conf.py agent_framework.web.web_ui:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
KillSignal=SIGQUIT
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-framework
sudo systemctl start agent-framework
sudo systemctl status agent-framework
```

---

## 性能优化

### 1. 应用层优化

**启用缓存：**

```python
# Redis 缓存
from redis import Redis
from functools import lru_cache

redis_client = Redis.from_url(os.getenv('REDIS_URL'))

@lru_cache(maxsize=1000)
def get_cached_result(key: str):
    cached = redis_client.get(key)
    if cached:
        return json.loads(cached)
    return None
```

**数据库连接池：**

```python
# config.yaml
database:
  pool_size: 20
  max_overflow: 10
  pool_recycle: 3600
```

**异步处理：**

```python
from celery import Celery

celery = Celery('agent_framework', broker='redis://localhost:6379/0')

@celery.task
def process_document_async(doc_id: str):
    # 异步处理文档
    pass
```

### 2. 数据库优化

**索引优化：**

```sql
-- 为常用查询添加索引
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
```

**查询优化：**

```python
# 使用批量查询
documents = session.query(Document).filter(
    Document.id.in_(doc_ids)
).all()

# 使用 eager loading
conversations = session.query(Conversation).options(
    joinedload(Conversation.messages)
).all()
```

### 3. 向量数据库优化

```python
# 使用更快的向量存储
from agent_framework.vector_db import KnowledgeBase

kb = KnowledgeBase(
    backend="faiss",  # 或 "lancedb"
    index_type="IVF",  # 倒排索引
    nlist=100,  # 聚类中心数
    nprobe=10   # 搜索的聚类数
)
```

### 4. LLM 调用优化

```python
# 启用流式响应
agent = AgentBuilder() \
    .with_stream(True) \
    .build()

# 使用更快的模型
agent = AgentBuilder() \
    .with_model("gpt-3.5-turbo") \
    .build()

# 批量处理
results = agent.batch_run(queries, max_workers=5)
```

---

## 监控和日志

### 1. 日志配置

```python
# logging_config.py
import logging.config

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'default',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/app.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'level': 'INFO',
            'formatter': 'detailed',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/error.log',
            'maxBytes': 10485760,
            'backupCount': 10,
            'level': 'ERROR',
            'formatter': 'detailed',
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console', 'file', 'error_file'],
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
```

### 2. 性能监控

使用 Prometheus + Grafana：

```python
from prometheus_client import Counter, Histogram, Gauge
from flask import request
import time

# 指标定义
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')
active_users = Gauge('active_users', 'Number of active users')

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - request.start_time
    request_duration.observe(duration)
    request_count.labels(
        method=request.method,
        endpoint=request.endpoint,
        status=response.status_code
    ).inc()
    return response
```

### 3. 健康检查

```python
@app.route('/health')
def health_check():
    """健康检查端点"""
    checks = {
        'database': check_database(),
        'redis': check_redis(),
        'llm': check_llm_connection(),
    }

    all_healthy = all(checks.values())
    status_code = 200 if all_healthy else 503

    return jsonify({
        'status': 'healthy' if all_healthy else 'unhealthy',
        'checks': checks,
        'timestamp': datetime.now().isoformat()
    }), status_code
```

---

## 备份和恢复

### 1. 数据库备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# 备份 SQLite
cp data/agent_framework.db "$BACKUP_DIR/agent_framework_$DATE.db"

# 备份 PostgreSQL
pg_dump -U agent_user agent_framework > "$BACKUP_DIR/agent_framework_$DATE.sql"

# 压缩备份
gzip "$BACKUP_DIR/agent_framework_$DATE.sql"

# 删除 7 天前的备份
find "$BACKUP_DIR" -name "*.db" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete
```

### 2. 向量数据库备份

```bash
# 备份 Chroma
tar -czf "$BACKUP_DIR/chroma_$DATE.tar.gz" data/chroma/

# 备份 LanceDB
tar -czf "$BACKUP_DIR/lancedb_$DATE.tar.gz" data/lancedb/
```

### 3. 自动备份

```bash
# 添加到 crontab
crontab -e

# 每天凌晨 2 点备份
0 2 * * * /opt/agent-framework/backup.sh
```

### 4. 恢复数据

```bash
# 恢复 SQLite
cp /backups/agent_framework_20240409.db data/agent_framework.db

# 恢复 PostgreSQL
gunzip < /backups/agent_framework_20240409.sql.gz | psql -U agent_user agent_framework

# 恢复向量数据库
tar -xzf /backups/chroma_20240409.tar.gz -C data/
```

---

## 安全加固

### 1. HTTPS 配置

```bash
# 使用 Let's Encrypt 获取免费证书
sudo certbot --nginx -d your-domain.com
```

### 2. 防火墙配置

```bash
# UFW 配置
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 3. 限流和防护

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per minute"],
    storage_uri="redis://localhost:6379/1"
)

@app.route('/api/chat')
@limiter.limit("10 per minute")
def chat():
    pass
```

### 4. 安全头配置

```python
from flask_talisman import Talisman

Talisman(app,
    force_https=True,
    strict_transport_security=True,
    content_security_policy={
        'default-src': "'self'",
        'script-src': ["'self'", "'unsafe-inline'"],
        'style-src': ["'self'", "'unsafe-inline'"],
    }
)
```

### 5. API Key 管理

```python
# 使用环境变量或密钥管理服务
import os
from cryptography.fernet import Fernet

# 加密存储
key = os.getenv('ENCRYPTION_KEY').encode()
cipher = Fernet(key)

def encrypt_api_key(api_key: str) -> str:
    return cipher.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    return cipher.decrypt(encrypted_key.encode()).decode()
```

---

## 故障排查

### 常见问题

1. **服务无法启动**
   - 检查端口占用
   - 查看日志文件
   - 验证配置文件

2. **性能下降**
   - 检查数据库连接数
   - 查看 Redis 内存使用
   - 分析慢查询日志

3. **内存泄漏**
   - 使用 memory_profiler 分析
   - 检查缓存配置
   - 定期重启服务

---

## 扩展阅读

- [Docker 官方文档](https://docs.docker.com/)
- [Nginx 配置指南](https://nginx.org/en/docs/)
- [Gunicorn 部署指南](https://docs.gunicorn.org/)
- [PostgreSQL 性能优化](https://www.postgresql.org/docs/current/performance-tips.html)
