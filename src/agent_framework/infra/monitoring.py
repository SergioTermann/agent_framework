"""
监控和分析系统
提供实时监控、性能分析、成本统计
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum
from agent_framework.core.database import DatabaseManager


# ─── 数据模型 ─────────────────────────────────────────────────────────────────

class MetricType(str, Enum):
    """指标类型"""
    COUNTER = "counter"      # 计数器
    GAUGE = "gauge"          # 仪表
    HISTOGRAM = "histogram"  # 直方图
    TIMER = "timer"          # 计时器


@dataclass
class Metric:
    """指标"""
    metric_id: str
    name: str
    type: MetricType
    value: float
    timestamp: str
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceRecord:
    """性能记录"""
    record_id: str
    operation: str
    duration: float  # 秒
    timestamp: str
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CostRecord:
    """成本记录"""
    record_id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float  # 美元
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── 监控存储 ─────────────────────────────────────────────────────────────────

class MonitoringStorage:
    """监控数据持久化存储"""

    def __init__(self, db_path: str = "./data/monitoring.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 指标表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    metric_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    value REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    tags TEXT,
                    metadata TEXT
                )
            """)

            # 性能记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_records (
                    record_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    duration REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error TEXT,
                    metadata TEXT
                )
            """)

            # 成本记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cost_records (
                    record_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    cost REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_name_timestamp
                ON metrics(name, timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_performance_operation
                ON performance_records(operation, timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_model
                ON cost_records(model, timestamp DESC)
            """)

    def add_metric(self, metric: Metric):
        """添加指标"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO metrics
                (metric_id, name, type, value, timestamp, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.metric_id,
                metric.name,
                metric.type.value,
                metric.value,
                metric.timestamp,
                json.dumps(metric.tags),
                json.dumps(metric.metadata),
            ))

    def add_performance_record(self, record: PerformanceRecord):
        """添加性能记录"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO performance_records
                (record_id, operation, duration, timestamp, success, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                record.record_id,
                record.operation,
                record.duration,
                record.timestamp,
                1 if record.success else 0,
                record.error,
                json.dumps(record.metadata),
            ))

    def add_cost_record(self, record: CostRecord):
        """添加成本记录"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cost_records
                (record_id, model, input_tokens, output_tokens, total_tokens, cost, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.record_id,
                record.model,
                record.input_tokens,
                record.output_tokens,
                record.total_tokens,
                record.cost,
                record.timestamp,
                json.dumps(record.metadata),
            ))

    def get_metrics(
        self,
        name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Metric]:
        """获取指标"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM metrics WHERE 1=1"
            params = []

            if name:
                query += " AND name = ?"
                params.append(name)
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

        metrics = []
        for row in rows:
            metrics.append(Metric(
                metric_id=row[0],
                name=row[1],
                type=MetricType(row[2]),
                value=row[3],
                timestamp=row[4],
                tags=json.loads(row[5]) if row[5] else {},
                metadata=json.loads(row[6]) if row[6] else {},
            ))

        return metrics

    def get_performance_stats(
        self,
        operation: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict:
        """获取性能统计"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = """
                SELECT
                    COUNT(*) as total_count,
                    AVG(duration) as avg_duration,
                    MIN(duration) as min_duration,
                    MAX(duration) as max_duration,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count
                FROM performance_records
                WHERE 1=1
            """
            params = []

            if operation:
                query += " AND operation = ?"
                params.append(operation)
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            cursor.execute(query, params)
            row = cursor.fetchone()

        return {
            "total_count": row[0] or 0,
            "avg_duration": round(row[1], 3) if row[1] else 0,
            "min_duration": round(row[2], 3) if row[2] else 0,
            "max_duration": round(row[3], 3) if row[3] else 0,
            "success_count": row[4] or 0,
            "error_count": row[5] or 0,
            "success_rate": round((row[4] or 0) / (row[0] or 1) * 100, 2),
        }

    def get_cost_stats(
        self,
        model: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict:
        """获取成本统计"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = """
                SELECT
                    COUNT(*) as total_requests,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(total_tokens) as total_tokens,
                    SUM(cost) as total_cost
                FROM cost_records
                WHERE 1=1
            """
            params = []

            if model:
                query += " AND model = ?"
                params.append(model)
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            cursor.execute(query, params)
            row = cursor.fetchone()

        return {
            "total_requests": row[0] or 0,
            "total_input_tokens": row[1] or 0,
            "total_output_tokens": row[2] or 0,
            "total_tokens": row[3] or 0,
            "total_cost": round(row[4], 4) if row[4] else 0,
            "avg_cost_per_request": round((row[4] or 0) / (row[0] or 1), 4),
        }


# ─── 监控管理器 ───────────────────────────────────────────────────────────────

class MonitoringManager:
    """监控管理器"""

    def __init__(self, storage: MonitoringStorage):
        self.storage = storage

    def record_metric(
        self,
        name: str,
        value: float,
        type: MetricType = MetricType.GAUGE,
        tags: Optional[Dict[str, str]] = None,
    ):
        """记录指标"""
        import uuid

        metric = Metric(
            metric_id=str(uuid.uuid4()),
            name=name,
            type=type,
            value=value,
            timestamp=datetime.now().isoformat(),
            tags=tags or {},
        )

        self.storage.add_metric(metric)

    def record_performance(
        self,
        operation: str,
        duration: float,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """记录性能"""
        import uuid

        record = PerformanceRecord(
            record_id=str(uuid.uuid4()),
            operation=operation,
            duration=duration,
            timestamp=datetime.now().isoformat(),
            success=success,
            error=error,
            metadata=metadata or {},
        )

        self.storage.add_performance_record(record)

    def record_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        metadata: Optional[Dict] = None,
    ):
        """记录成本"""
        import uuid

        record = CostRecord(
            record_id=str(uuid.uuid4()),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost=cost,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {},
        )

        self.storage.add_cost_record(record)

    def get_dashboard_data(
        self,
        time_range: str = "24h",
    ) -> Dict:
        """获取仪表板数据"""
        import random

        # 计算时间范围
        now = datetime.now()
        if time_range == "1h":
            start_time = (now - timedelta(hours=1)).isoformat()
            intervals = 12  # 5分钟间隔
        elif time_range == "6h":
            start_time = (now - timedelta(hours=6)).isoformat()
            intervals = 24  # 15分钟间隔
        elif time_range == "24h":
            start_time = (now - timedelta(days=1)).isoformat()
            intervals = 24  # 1小时间隔
        elif time_range == "7d":
            start_time = (now - timedelta(days=7)).isoformat()
            intervals = 28  # 6小时间隔
        elif time_range == "30d":
            start_time = (now - timedelta(days=30)).isoformat()
            intervals = 30  # 1天间隔
        else:
            start_time = None
            intervals = 24

        # 获取统计数据
        perf_stats = self.storage.get_performance_stats(start_time=start_time)
        cost_stats = self.storage.get_cost_stats(start_time=start_time)

        # 生成时间标签
        time_labels = []
        for i in range(intervals):
            if time_range == "1h":
                t = now - timedelta(minutes=5 * (intervals - i - 1))
                time_labels.append(t.strftime("%H:%M"))
            elif time_range == "6h":
                t = now - timedelta(minutes=15 * (intervals - i - 1))
                time_labels.append(t.strftime("%H:%M"))
            elif time_range == "24h":
                t = now - timedelta(hours=(intervals - i - 1))
                time_labels.append(t.strftime("%H:00"))
            elif time_range == "7d":
                t = now - timedelta(hours=6 * (intervals - i - 1))
                time_labels.append(t.strftime("%m-%d %H:00"))
            else:  # 30d
                t = now - timedelta(days=(intervals - i - 1))
                time_labels.append(t.strftime("%m-%d"))

        # 生成模拟数据（实际应从数据库查询）
        conversation_series = [random.randint(50, 200) for _ in range(intervals)]
        user_series = [random.randint(10, 50) for _ in range(intervals)]
        input_tokens_series = [random.randint(5000, 20000) for _ in range(intervals)]
        output_tokens_series = [random.randint(3000, 15000) for _ in range(intervals)]

        # Agent 分布
        agent_distribution = [
            {"value": random.randint(200, 500), "name": "通用Agent"},
            {"value": random.randint(150, 400), "name": "代码Agent"},
            {"value": random.randint(100, 300), "name": "因果推理"},
            {"value": random.randint(80, 250), "name": "数据分析"},
        ]

        # 工作流统计
        workflow_names = ["客服对话", "文档问答", "代码生成", "数据分析", "内容创作"]
        workflow_success_rates = [random.uniform(85, 99) for _ in range(5)]
        workflow_durations = [random.uniform(1, 10) for _ in range(5)]

        # 响应时间分布
        response_time_distribution = [
            random.randint(300, 600),  # <1s
            random.randint(200, 400),  # 1-2s
            random.randint(100, 250),  # 2-5s
            random.randint(30, 100),   # 5-10s
            random.randint(10, 50),    # >10s
        ]

        # 热门工作流
        top_workflows = [
            {
                "name": "智能客服对话",
                "count": random.randint(500, 1500),
                "success_rate": random.uniform(92, 99),
                "avg_duration": random.uniform(1.5, 5.0),
                "last_executed": (now - timedelta(minutes=random.randint(1, 60))).isoformat()
            },
            {
                "name": "文档知识问答",
                "count": random.randint(300, 1000),
                "success_rate": random.uniform(88, 97),
                "avg_duration": random.uniform(2.0, 6.0),
                "last_executed": (now - timedelta(minutes=random.randint(1, 60))).isoformat()
            },
            {
                "name": "代码生成助手",
                "count": random.randint(200, 800),
                "success_rate": random.uniform(85, 95),
                "avg_duration": random.uniform(3.0, 8.0),
                "last_executed": (now - timedelta(minutes=random.randint(1, 60))).isoformat()
            },
            {
                "name": "数据分析报告",
                "count": random.randint(150, 600),
                "success_rate": random.uniform(90, 98),
                "avg_duration": random.uniform(5.0, 12.0),
                "last_executed": (now - timedelta(minutes=random.randint(1, 60))).isoformat()
            },
            {
                "name": "内容创作工具",
                "count": random.randint(100, 500),
                "success_rate": random.uniform(87, 96),
                "avg_duration": random.uniform(2.5, 7.0),
                "last_executed": (now - timedelta(minutes=random.randint(1, 60))).isoformat()
            }
        ]

        # 统计数据
        total_conversations = sum(conversation_series)
        active_users = sum(user_series)
        total_tokens = sum(input_tokens_series) + sum(output_tokens_series)
        total_cost = total_tokens * 0.00002  # 假设每token 0.00002美元

        return {
            "time_range": time_range,
            "timestamp": now.isoformat(),

            # 统计卡片数据
            "total_conversations": total_conversations,
            "active_users": active_users,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "conversations_change": random.uniform(5, 25),
            "users_change": random.uniform(3, 20),
            "tokens_change": random.uniform(8, 30),
            "cost_change": random.uniform(8, 30),

            # 图表数据
            "time_labels": time_labels,
            "conversation_series": conversation_series,
            "user_series": user_series,
            "input_tokens_series": input_tokens_series,
            "output_tokens_series": output_tokens_series,
            "agent_distribution": agent_distribution,
            "workflow_names": workflow_names,
            "workflow_success_rates": workflow_success_rates,
            "workflow_durations": workflow_durations,
            "response_time_distribution": response_time_distribution,
            "top_workflows": top_workflows,

            # 原有数据
            "performance": perf_stats,
            "cost": cost_stats,
        }

    def get_time_series(
        self,
        metric_name: str,
        time_range: str = "24h",
        interval: str = "1h",
    ) -> List[Dict]:
        """获取时间序列数据"""
        # 计算时间范围
        now = datetime.now()
        if time_range == "1h":
            start_time = (now - timedelta(hours=1)).isoformat()
        elif time_range == "24h":
            start_time = (now - timedelta(days=1)).isoformat()
        elif time_range == "7d":
            start_time = (now - timedelta(days=7)).isoformat()
        else:
            start_time = None

        # 获取指标
        metrics = self.storage.get_metrics(
            name=metric_name,
            start_time=start_time,
        )

        # 按时间间隔聚合
        # 简单实现：直接返回原始数据
        return [
            {
                "timestamp": m.timestamp,
                "value": m.value,
            }
            for m in metrics
        ]


# ─── 告警系统 ─────────────────────────────────────────────────────────────────

class AlertRule:
    """告警规则"""

    def __init__(
        self,
        name: str,
        metric_name: str,
        condition: str,  # "gt", "lt", "eq"
        threshold: float,
        duration: int = 60,  # 秒
    ):
        self.name = name
        self.metric_name = metric_name
        self.condition = condition
        self.threshold = threshold
        self.duration = duration
        self.triggered = False
        self.trigger_time = None

    def check(self, value: float) -> bool:
        """检查是否触发告警"""
        triggered = False

        if self.condition == "gt" and value > self.threshold:
            triggered = True
        elif self.condition == "lt" and value < self.threshold:
            triggered = True
        elif self.condition == "eq" and value == self.threshold:
            triggered = True

        if triggered:
            if not self.triggered:
                self.triggered = True
                self.trigger_time = time.time()
            elif time.time() - self.trigger_time >= self.duration:
                return True
        else:
            self.triggered = False
            self.trigger_time = None

        return False


class AlertManager:
    """告警管理器"""

    def __init__(self):
        self.rules: List[AlertRule] = []
        self.alerts: List[Dict] = []

    def add_rule(self, rule: AlertRule):
        """添加告警规则"""
        self.rules.append(rule)

    def check_metrics(self, metrics: List[Metric]):
        """检查指标并触发告警"""
        for metric in metrics:
            for rule in self.rules:
                if rule.metric_name == metric.name:
                    if rule.check(metric.value):
                        self._trigger_alert(rule, metric)

    def _trigger_alert(self, rule: AlertRule, metric: Metric):
        """触发告警"""
        alert = {
            "rule_name": rule.name,
            "metric_name": metric.name,
            "value": metric.value,
            "threshold": rule.threshold,
            "condition": rule.condition,
            "timestamp": datetime.now().isoformat(),
        }

        self.alerts.append(alert)

        # 这里可以发送通知（邮件、Slack、钉钉等）
        print(f"⚠️ 告警触发: {rule.name} - {metric.name} = {metric.value}")

    def get_alerts(self, limit: int = 100) -> List[Dict]:
        """获取告警列表"""
        return self.alerts[-limit:]


# ─── 成本计算器 ───────────────────────────────────────────────────────────────

class CostCalculator:
    """成本计算器"""

    # 模型定价（美元/1M tokens）
    PRICING = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "claude-3-opus": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
        # 国内模型（假设定价）
        "qwen-turbo": {"input": 0.10, "output": 0.30},
        "qwen-plus": {"input": 0.30, "output": 0.90},
        "deepseek-chat": {"input": 0.20, "output": 0.60},
    }

    @classmethod
    def calculate_cost(
        cls,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """计算成本"""
        pricing = cls.PRICING.get(model)

        if not pricing:
            # 未知模型，使用默认定价
            pricing = {"input": 1.00, "output": 3.00}

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    @classmethod
    def estimate_monthly_cost(
        cls,
        model: str,
        daily_requests: int,
        avg_input_tokens: int,
        avg_output_tokens: int,
    ) -> Dict:
        """估算月度成本"""
        daily_cost = cls.calculate_cost(
            model,
            daily_requests * avg_input_tokens,
            daily_requests * avg_output_tokens,
        )

        monthly_cost = daily_cost * 30

        return {
            "model": model,
            "daily_requests": daily_requests,
            "avg_input_tokens": avg_input_tokens,
            "avg_output_tokens": avg_output_tokens,
            "daily_cost": round(daily_cost, 2),
            "monthly_cost": round(monthly_cost, 2),
        }
