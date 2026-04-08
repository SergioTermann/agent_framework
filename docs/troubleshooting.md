# 故障排查指南

本文档提供 Agent Framework 常见问题的诊断和解决方案。

## 目录

- [服务启动问题](#服务启动问题)
- [API 调用问题](#api-调用问题)
- [知识库问题](#知识库问题)
- [性能问题](#性能问题)
- [数据库问题](#数据库问题)
- [LLM 调用问题](#llm-调用问题)

---

## 服务启动问题

### 问题：端口被占用

**症状：**
```
OSError: [Errno 98] Address already in use
```

**解决方案：**

1. 查找占用端口的进程：
```bash
# Windows
netstat -ano | findstr :5000

# Linux/Mac
lsof -i :5000
```

2. 终止进程或更换端口：
```bash
# 终止进程
kill -9 <PID>

# 或在配置文件中更换端口
server:
  port: 5001
```

### 问题：模块导入失败

**症状：**
```
ModuleNotFoundError: No module named 'agent_framework'
```

**解决方案：**

1. 确认已安装：
```bash
pip install -e .
```

2. 检查 Python 路径：
```bash
python -c "import sys; print(sys.path)"
```

3. 设置 PYTHONPATH：
```bash
export PYTHONPATH="${PYTHONPATH}:/path/to/agent_framework"
```

### 问题：配置文件错误

**症状：**
```
yaml.scanner.ScannerError: mapping values are not allowed here
```

**解决方案：**

1. 检查 YAML 语法：
```bash
python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

2. 验证缩进（使用空格，不要用 Tab）

3. 检查特殊字符是否需要引号

---

## API 调用问题

### 问题：401 未授权

**症状：**
```json
{"error": "Unauthorized", "code": 401}
```

**解决方案：**

1. 检查 API Key：
```bash
echo $OPENAI_API_KEY
```

2. 在请求头中添加认证：
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" ...
```

3. 验证 Token 是否过期

### 问题：429 速率限制

**症状：**
```json
{"error": "Rate limit exceeded", "code": 429}
```

**解决方案：**

1. 等待限制重置（通常 1 分钟）

2. 增加请求间隔：
```python
import time
time.sleep(1)  # 每次请求间隔 1 秒
```

3. 升级账户配额

### 问题：500 服务器错误

**症状：**
```json
{"error": "Internal server error", "code": 500}
```

**解决方案：**

1. 查看服务器日志：
```bash
tail -f logs/app.log
```

2. 检查数据库连接

3. 验证依赖服务状态

---

## 知识库问题

### 问题：搜索无结果

**症状：**
搜索返回空列表或相关性很低的结果。

**解决方案：**

1. 确认文档已添加：
```python
kb = KnowledgeBase()
print(kb.count())  # 查看文档数量
```

2. 检查向量维度：
```python
# 确保嵌入模型维度一致
print(kb.embedding_model.dimension)
```

3. 调整搜索参数：
```python
results = kb.search(
    query="查询内容",
    top_k=10,  # 增加返回数量
    threshold=0.5  # 降低相似度阈值
)
```

4. 重建索引：
```python
kb.rebuild_index()
```

### 问题：向量存储损坏

**症状：**
```
RuntimeError: Index is corrupted
```

**解决方案：**

1. 备份数据：
```bash
cp -r data/vector_store data/vector_store.backup
```

2. 重建索引：
```python
from agent_framework.vector_db import KnowledgeBase

kb = KnowledgeBase()
kb.rebuild_index(force=True)
```

3. 如果失败，从备份恢复：
```bash
rm -rf data/vector_store
cp -r data/vector_store.backup data/vector_store
```

### 问题：内存不足

**症状：**
```
MemoryError: Unable to allocate array
```

**解决方案：**

1. 使用分批处理：
```python
batch_size = 100
for i in range(0, len(documents), batch_size):
    batch = documents[i:i+batch_size]
    kb.add_documents(batch)
```

2. 启用磁盘缓存：
```python
kb = KnowledgeBase(use_disk_cache=True)
```

3. 增加系统内存或使用更小的嵌入模型

---

## 性能问题

### 问题：响应时间过长

**诊断步骤：**

1. 启用性能分析：
```python
import cProfile
cProfile.run('agent.run("query")')
```

2. 检查日志中的耗时：
```bash
grep "execution_time" logs/app.log
```

**解决方案：**

1. 启用缓存：
```python
agent = AgentBuilder() \
    .with_cache(enabled=True, ttl=3600) \
    .build()
```

2. 使用更快的模型：
```python
agent = AgentBuilder() \
    .with_model("gpt-3.5-turbo")  # 比 gpt-4 更快
    .build()
```

3. 优化知识库搜索：
```python
results = kb.search(query, top_k=3)  # 减少返回数量
```

4. 使用异步处理：
```python
async def process():
    result = await agent.arun("query")
    return result
```

### 问题：内存使用过高

**诊断：**
```python
import psutil
process = psutil.Process()
print(f"内存使用: {process.memory_info().rss / 1024 / 1024:.2f} MB")
```

**解决方案：**

1. 限制缓存大小：
```python
agent = AgentBuilder() \
    .with_cache(max_size=1000) \
    .build()
```

2. 定期清理：
```python
kb.clear_cache()
agent.clear_history()
```

3. 使用流式处理：
```python
for chunk in agent.stream("query"):
    print(chunk, end="")
```

### 问题：CPU 使用率过高

**解决方案：**

1. 限制并发数：
```python
from agent_framework.infra import RateLimiter

limiter = RateLimiter(max_requests=10, time_window=60)
```

2. 使用进程池：
```python
from multiprocessing import Pool

with Pool(processes=4) as pool:
    results = pool.map(agent.run, queries)
```

---

## 数据库问题

### 问题：数据库锁定

**症状：**
```
sqlite3.OperationalError: database is locked
```

**解决方案：**

1. 增加超时时间：
```python
import sqlite3
conn = sqlite3.connect('data/db.sqlite', timeout=30)
```

2. 使用 WAL 模式：
```python
conn.execute('PRAGMA journal_mode=WAL')
```

3. 检查是否有未关闭的连接

### 问题：数据库损坏

**症状：**
```
sqlite3.DatabaseError: database disk image is malformed
```

**解决方案：**

1. 尝试修复：
```bash
sqlite3 data/db.sqlite "PRAGMA integrity_check"
```

2. 从备份恢复：
```bash
cp data/db.sqlite.backup data/db.sqlite
```

3. 重建数据库：
```bash
rm data/db.sqlite
python -m agent_framework.core.database --init
```

---

## LLM 调用问题

### 问题：API Key 无效

**症状：**
```
openai.error.AuthenticationError: Invalid API key
```

**解决方案：**

1. 验证 API Key：
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

2. 检查环境变量：
```bash
echo $OPENAI_API_KEY
```

3. 在配置文件中设置：
```yaml
llm:
  api_key: sk-...
```

### 问题：超时

**症状：**
```
openai.error.Timeout: Request timed out
```

**解决方案：**

1. 增加超时时间：
```python
from openai import OpenAI
client = OpenAI(timeout=60.0)
```

2. 使用重试机制：
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
def call_llm():
    return client.chat.completions.create(...)
```

3. 检查网络连接

### 问题：Token 超限

**症状：**
```
openai.error.InvalidRequestError: maximum context length exceeded
```

**解决方案：**

1. 减少输入长度：
```python
# 截断历史消息
messages = messages[-10:]  # 只保留最近 10 条
```

2. 使用更大上下文的模型：
```python
agent = AgentBuilder() \
    .with_model("gpt-4-32k") \
    .build()
```

3. 启用消息压缩：
```python
agent = AgentBuilder() \
    .with_message_compression(enabled=True) \
    .build()
```

---

## 日志和调试

### 启用详细日志

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug.log'),
        logging.StreamHandler()
    ]
)
```

### 查看特定模块日志

```python
logger = logging.getLogger('agent_framework.vector_db')
logger.setLevel(logging.DEBUG)
```

### 性能分析

```python
import time

start = time.time()
result = agent.run("query")
print(f"耗时: {time.time() - start:.2f}s")
```

---

## 获取帮助

如果以上方法无法解决问题：

1. 查看完整日志：`logs/app.log`
2. 搜索 GitHub Issues
3. 提交新 Issue，包含：
   - 错误信息
   - 复现步骤
   - 系统环境
   - 日志片段

---

## 相关文档

- [API 参考](api_reference.md)
- [快速参考](quick_reference.md)
- [用户工具指南](user_tools_guide.md)
