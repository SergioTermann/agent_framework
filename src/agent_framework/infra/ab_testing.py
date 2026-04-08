"""
A/B 测试系统
支持工作流版本对比、流量分配、效果统计
"""

import agent_framework.core.fast_json as json
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pathlib import Path
from agent_framework.core.database import DatabaseManager


class TestStatus(str, Enum):
    """测试状态"""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass
class Variant:
    """变体"""
    variant_id: str
    name: str
    workflow_id: str
    traffic_percentage: float  # 流量百分比 (0-100)
    description: str = ""


@dataclass
class ABTest:
    """A/B 测试"""
    test_id: str
    name: str
    description: str
    status: TestStatus
    variants: List[Variant]
    created_at: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None

    # 统计数据
    total_requests: int = 0
    metrics: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class TestResult:
    """测试结果"""
    variant_id: str
    request_count: int
    success_count: int
    error_count: int
    avg_duration: float
    metrics: Dict[str, float]


class ABTestManager:
    """A/B 测试管理器"""

    def __init__(self, db_path: str = "data/ab_tests.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 创建测试表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ab_tests (
                    test_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL,
                    variants TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    total_requests INTEGER DEFAULT 0
                )
            ''')

            # 创建结果表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS test_results (
                    result_id TEXT PRIMARY KEY,
                    test_id TEXT NOT NULL,
                    variant_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    duration REAL NOT NULL,
                    metrics TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (test_id) REFERENCES ab_tests (test_id)
                )
            ''')

    def create_test(self, name: str, description: str, variants: List[Dict]) -> ABTest:
        """
        创建 A/B 测试

        Args:
            name: 测试名称
            description: 测试描述
            variants: 变体列表

        Returns:
            创建的测试
        """
        test_id = str(uuid.uuid4())

        # 验证流量分配
        total_traffic = sum(v['traffic_percentage'] for v in variants)
        if abs(total_traffic - 100) > 0.01:
            raise ValueError(f"流量分配总和必须为100%，当前为{total_traffic}%")

        # 创建变体对象
        variant_objects = [
            Variant(
                variant_id=str(uuid.uuid4()),
                name=v['name'],
                workflow_id=v['workflow_id'],
                traffic_percentage=v['traffic_percentage'],
                description=v.get('description', '')
            )
            for v in variants
        ]

        test = ABTest(
            test_id=test_id,
            name=name,
            description=description,
            status=TestStatus.DRAFT,
            variants=variant_objects,
            created_at=datetime.now().isoformat()
        )

        # 保存到数据库
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO ab_tests (test_id, name, description, status, variants, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                test.test_id,
                test.name,
                test.description,
                test.status.value,
                json.dumps([{
                    'variant_id': v.variant_id,
                    'name': v.name,
                    'workflow_id': v.workflow_id,
                    'traffic_percentage': v.traffic_percentage,
                    'description': v.description
                } for v in test.variants]),
                test.created_at
            ))

        return test

    def get_test(self, test_id: str) -> Optional[ABTest]:
        """获取测试"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT test_id, name, description, status, variants, created_at,
                       started_at, ended_at, total_requests
                FROM ab_tests
                WHERE test_id = ?
            ''', (test_id,))
            row = cursor.fetchone()

        if not row:
            return None

        variants_data = json.loads(row[4])
        variants = [
            Variant(
                variant_id=v['variant_id'],
                name=v['name'],
                workflow_id=v['workflow_id'],
                traffic_percentage=v['traffic_percentage'],
                description=v.get('description', '')
            )
            for v in variants_data
        ]

        return ABTest(
            test_id=row[0],
            name=row[1],
            description=row[2],
            status=TestStatus(row[3]),
            variants=variants,
            created_at=row[5],
            started_at=row[6],
            ended_at=row[7],
            total_requests=row[8]
        )

    def start_test(self, test_id: str) -> bool:
        """开始测试"""
        test = self.get_test(test_id)
        if not test or test.status != TestStatus.DRAFT:
            return False

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE ab_tests
                SET status = ?, started_at = ?
                WHERE test_id = ?
            ''', (TestStatus.RUNNING.value, datetime.now().isoformat(), test_id))

        return True

    def stop_test(self, test_id: str) -> bool:
        """停止测试"""
        test = self.get_test(test_id)
        if not test or test.status != TestStatus.RUNNING:
            return False

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE ab_tests
                SET status = ?, ended_at = ?
                WHERE test_id = ?
            ''', (TestStatus.COMPLETED.value, datetime.now().isoformat(), test_id))

        return True

    def select_variant(self, test_id: str) -> Optional[Variant]:
        """
        根据流量分配选择变体

        Args:
            test_id: 测试ID

        Returns:
            选中的变体
        """
        test = self.get_test(test_id)
        if not test or test.status != TestStatus.RUNNING:
            return None

        # 根据流量百分比随机选择
        rand = random.uniform(0, 100)
        cumulative = 0

        for variant in test.variants:
            cumulative += variant.traffic_percentage
            if rand <= cumulative:
                return variant

        # 默认返回第一个变体
        return test.variants[0] if test.variants else None

    def record_result(self, test_id: str, variant_id: str, success: bool,
                     duration: float, metrics: Optional[Dict] = None):
        """
        记录测试结果

        Args:
            test_id: 测试ID
            variant_id: 变体ID
            success: 是否成功
            duration: 执行时长
            metrics: 其他指标
        """
        result_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO test_results
                (result_id, test_id, variant_id, request_id, success, duration, metrics, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result_id,
                test_id,
                variant_id,
                request_id,
                1 if success else 0,
                duration,
                json.dumps(metrics or {}),
                datetime.now().isoformat()
            ))

            # 更新总请求数
            cursor.execute('''
                UPDATE ab_tests
                SET total_requests = total_requests + 1
                WHERE test_id = ?
            ''', (test_id,))

    def get_results(self, test_id: str) -> List[TestResult]:
        """获取测试结果"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    variant_id,
                    COUNT(*) as request_count,
                    SUM(success) as success_count,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count,
                    AVG(duration) as avg_duration
                FROM test_results
                WHERE test_id = ?
                GROUP BY variant_id
            ''', (test_id,))

            results = []
            for row in cursor.fetchall():
                results.append(TestResult(
                    variant_id=row[0],
                    request_count=row[1],
                    success_count=row[2],
                    error_count=row[3],
                    avg_duration=row[4],
                    metrics={}
                ))

        return results

    def get_winner(self, test_id: str, metric: str = "success_rate") -> Optional[str]:
        """
        获取获胜变体

        Args:
            test_id: 测试ID
            metric: 评判指标 (success_rate, avg_duration)

        Returns:
            获胜变体ID
        """
        results = self.get_results(test_id)
        if not results:
            return None

        if metric == "success_rate":
            # 按成功率排序
            best = max(results, key=lambda r: r.success_count / r.request_count if r.request_count > 0 else 0)
        elif metric == "avg_duration":
            # 按平均时长排序（越小越好）
            best = min(results, key=lambda r: r.avg_duration)
        else:
            return None

        return best.variant_id

    def list_tests(self, status: Optional[TestStatus] = None) -> List[ABTest]:
        """列出所有测试"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute('''
                    SELECT test_id, name, description, status, variants, created_at,
                           started_at, ended_at, total_requests
                    FROM ab_tests
                    WHERE status = ?
                    ORDER BY created_at DESC
                ''', (status.value,))
            else:
                cursor.execute('''
                    SELECT test_id, name, description, status, variants, created_at,
                           started_at, ended_at, total_requests
                    FROM ab_tests
                    ORDER BY created_at DESC
                ''')

            tests = []
            for row in cursor.fetchall():
                variants_data = json.loads(row[4])
                variants = [
                    Variant(
                        variant_id=v['variant_id'],
                        name=v['name'],
                        workflow_id=v['workflow_id'],
                        traffic_percentage=v['traffic_percentage'],
                        description=v.get('description', '')
                    )
                    for v in variants_data
                ]

                tests.append(ABTest(
                    test_id=row[0],
                    name=row[1],
                    description=row[2],
                    status=TestStatus(row[3]),
                    variants=variants,
                    created_at=row[5],
                    started_at=row[6],
                    ended_at=row[7],
                    total_requests=row[8]
                ))

        return tests


# 全局实例
_ab_test_manager = None


def get_ab_test_manager() -> ABTestManager:
    """获取 A/B 测试管理器实例"""
    global _ab_test_manager
    if _ab_test_manager is None:
        _ab_test_manager = ABTestManager()
    return _ab_test_manager
