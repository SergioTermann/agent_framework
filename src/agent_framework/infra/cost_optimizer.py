"""
成本优化引擎
自动选择最优模型、成本预测、预算控制
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

from agent_framework.core.database import DatabaseManager


@dataclass
class ModelInfo:
    """模型信息"""
    model_id: str
    name: str
    provider: str  # openai, anthropic, etc
    input_price: float  # 每1K tokens价格
    output_price: float
    context_window: int
    performance_score: float  # 性能评分 (0-100)
    latency_ms: int  # 平均延迟


@dataclass
class CostRecord:
    """成本记录"""
    record_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost: float
    timestamp: str
    user_id: Optional[str] = None
    workflow_id: Optional[str] = None


class CostOptimizer:
    """成本优化器"""

    def __init__(self, db_path: str = "data/cost_optimizer.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        self._init_db()
        self._load_models()

    def _init_db(self):
        """初始化数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cost_records (
                    record_id TEXT PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    workflow_id TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS budgets (
                    budget_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    workflow_id TEXT,
                    daily_limit REAL,
                    monthly_limit REAL,
                    current_daily REAL DEFAULT 0,
                    current_monthly REAL DEFAULT 0,
                    last_reset_daily TEXT,
                    last_reset_monthly TEXT
                )
            ''')

    def _load_models(self):
        """加载模型信息"""
        self.models = {
            "gpt-4o": ModelInfo(
                model_id="gpt-4o",
                name="GPT-4o",
                provider="openai",
                input_price=0.005,
                output_price=0.015,
                context_window=128000,
                performance_score=95,
                latency_ms=1500
            ),
            "gpt-4o-mini": ModelInfo(
                model_id="gpt-4o-mini",
                name="GPT-4o Mini",
                provider="openai",
                input_price=0.00015,
                output_price=0.0006,
                context_window=128000,
                performance_score=85,
                latency_ms=800
            ),
            "gpt-3.5-turbo": ModelInfo(
                model_id="gpt-3.5-turbo",
                name="GPT-3.5 Turbo",
                provider="openai",
                input_price=0.0005,
                output_price=0.0015,
                context_window=16385,
                performance_score=75,
                latency_ms=500
            ),
            "claude-opus-4": ModelInfo(
                model_id="claude-opus-4",
                name="Claude Opus 4",
                provider="anthropic",
                input_price=0.015,
                output_price=0.075,
                context_window=200000,
                performance_score=98,
                latency_ms=2000
            ),
            "claude-sonnet-4": ModelInfo(
                model_id="claude-sonnet-4",
                name="Claude Sonnet 4",
                provider="anthropic",
                input_price=0.003,
                output_price=0.015,
                context_window=200000,
                performance_score=90,
                latency_ms=1200
            )
        }

    def select_optimal_model(self, task_type: str, max_cost: Optional[float] = None,
                           min_performance: Optional[float] = None,
                           max_latency: Optional[int] = None) -> Optional[ModelInfo]:
        """
        选择最优模型

        Args:
            task_type: 任务类型 (simple, complex, creative)
            max_cost: 最大成本（每1K tokens）
            min_performance: 最小性能要求
            max_latency: 最大延迟要求（毫秒）

        Returns:
            最优模型
        """
        candidates = list(self.models.values())

        # 应用过滤条件
        if max_cost:
            candidates = [m for m in candidates if m.output_price <= max_cost]

        if min_performance:
            candidates = [m for m in candidates if m.performance_score >= min_performance]

        if max_latency:
            candidates = [m for m in candidates if m.latency_ms <= max_latency]

        if not candidates:
            return None

        # 根据任务类型选择
        if task_type == "simple":
            # 简单任务：优先考虑成本
            return min(candidates, key=lambda m: m.output_price)
        elif task_type == "complex":
            # 复杂任务：优先考虑性能
            return max(candidates, key=lambda m: m.performance_score)
        elif task_type == "creative":
            # 创意任务：平衡性能和成本
            return max(candidates, key=lambda m: m.performance_score / (m.output_price * 100))
        else:
            # 默认：性价比最高
            return max(candidates, key=lambda m: m.performance_score / (m.output_price * 100))

    def calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """计算成本"""
        model = self.models.get(model_id)
        if not model:
            return 0.0

        input_cost = (input_tokens / 1000) * model.input_price
        output_cost = (output_tokens / 1000) * model.output_price

        return input_cost + output_cost

    def record_cost(self, model_id: str, input_tokens: int, output_tokens: int,
                   user_id: Optional[str] = None, workflow_id: Optional[str] = None) -> CostRecord:
        """记录成本"""
        import uuid

        cost = self.calculate_cost(model_id, input_tokens, output_tokens)

        record = CostRecord(
            record_id=str(uuid.uuid4()),
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            workflow_id=workflow_id
        )

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO cost_records
                (record_id, model_id, input_tokens, output_tokens, cost, timestamp, user_id, workflow_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.record_id,
                record.model_id,
                record.input_tokens,
                record.output_tokens,
                record.cost,
                record.timestamp,
                record.user_id,
                record.workflow_id
            ))

            # 更新预算使用情况
            cursor.execute("""
                UPDATE budgets
                SET current_daily = current_daily + ?,
                    current_monthly = current_monthly + ?
                WHERE (user_id = ? OR user_id IS NULL)
                  AND (workflow_id = ? OR workflow_id IS NULL)
            """, (cost, cost, user_id, workflow_id))

        return record

    def get_total_cost(self, start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      user_id: Optional[str] = None,
                      workflow_id: Optional[str] = None) -> float:
        """获取总成本"""
        query = "SELECT SUM(cost) FROM cost_records WHERE 1=1"
        params = []

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if workflow_id:
            query += " AND workflow_id = ?"
            params.append(workflow_id)

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()[0]

        return result or 0.0

    def predict_cost(self, model_id: str, estimated_tokens: int) -> Dict:
        """预测成本"""
        model = self.models.get(model_id)
        if not model:
            return {}

        # 假设输入输出比例为 1:2
        input_tokens = estimated_tokens // 3
        output_tokens = estimated_tokens * 2 // 3

        cost = self.calculate_cost(model_id, input_tokens, output_tokens)

        return {
            "model_id": model_id,
            "model_name": model.name,
            "estimated_input_tokens": input_tokens,
            "estimated_output_tokens": output_tokens,
            "estimated_cost": cost,
            "cost_per_request": cost
        }

    def set_budget(self, user_id: Optional[str] = None, workflow_id: Optional[str] = None,
                  daily_limit: Optional[float] = None, monthly_limit: Optional[float] = None):
        """设置预算"""
        import uuid

        budget_id = str(uuid.uuid4())

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO budgets
                (budget_id, user_id, workflow_id, daily_limit, monthly_limit,
                 last_reset_daily, last_reset_monthly)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                budget_id,
                user_id,
                workflow_id,
                daily_limit,
                monthly_limit,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))

    def check_budget(self, user_id: Optional[str] = None,
                    workflow_id: Optional[str] = None) -> Dict:
        """检查预算"""
        # 查询预算设置
        query = "SELECT * FROM budgets WHERE 1=1"
        params = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if workflow_id:
            query += " AND workflow_id = ?"
            params.append(workflow_id)

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            budget_row = cursor.fetchone()

            if not budget_row:
                return {
                    "within_budget": True,
                    "daily_remaining": None,
                    "monthly_remaining": None,
                    "message": "No budget set"
                }

            budget_id, _, _, daily_limit, monthly_limit, current_daily, current_monthly, last_reset_daily, last_reset_monthly = budget_row

            now = datetime.now()

            # 检查是否需要重置每日预算
            if last_reset_daily:
                last_reset = datetime.fromisoformat(last_reset_daily)
                if now.date() > last_reset.date():
                    current_daily = 0
                    cursor.execute("""
                        UPDATE budgets SET current_daily = 0, last_reset_daily = ?
                        WHERE budget_id = ?
                    """, (now.isoformat(), budget_id))

            # 检查是否需要重置每月预算
            if last_reset_monthly:
                last_reset = datetime.fromisoformat(last_reset_monthly)
                if now.month != last_reset.month or now.year != last_reset.year:
                    current_monthly = 0
                    cursor.execute("""
                        UPDATE budgets SET current_monthly = 0, last_reset_monthly = ?
                        WHERE budget_id = ?
                    """, (now.isoformat(), budget_id))

        # 检查预算
        within_budget = True
        messages = []

        if daily_limit and current_daily >= daily_limit:
            within_budget = False
            messages.append(f"Daily budget exceeded: ${current_daily:.2f} / ${daily_limit:.2f}")

        if monthly_limit and current_monthly >= monthly_limit:
            within_budget = False
            messages.append(f"Monthly budget exceeded: ${current_monthly:.2f} / ${monthly_limit:.2f}")

        return {
            "within_budget": within_budget,
            "daily_remaining": (daily_limit - current_daily) if daily_limit else None,
            "monthly_remaining": (monthly_limit - current_monthly) if monthly_limit else None,
            "current_daily": current_daily,
            "current_monthly": current_monthly,
            "daily_limit": daily_limit,
            "monthly_limit": monthly_limit,
            "messages": messages
        }


# 全局实例
_cost_optimizer = None


def get_cost_optimizer() -> CostOptimizer:
    """获取成本优化器实例"""
    global _cost_optimizer
    if _cost_optimizer is None:
        _cost_optimizer = CostOptimizer()
    return _cost_optimizer
