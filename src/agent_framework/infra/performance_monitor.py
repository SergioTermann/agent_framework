"""
性能监控和分析系统
提供性能指标收集、分析和优化建议
"""

from __future__ import annotations

import time
import threading
import functools
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import statistics


@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    duration: float  # 秒
    timestamp: float
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.metrics: List[PerformanceMetric] = []
        self._lock = threading.RLock()
        self._function_stats = defaultdict(list)

    def record(self, metric: PerformanceMetric):
        """记录性能指标"""
        with self._lock:
            self.metrics.append(metric)
            self._function_stats[metric.name].append(metric.duration)

            # 保持最近 10000 条记录
            if len(self.metrics) > 10000:
                self.metrics = self.metrics[-10000:]

    def get_stats(self, name: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            if name:
                durations = self._function_stats.get(name, [])
                if not durations:
                    return {}

                return {
                    'name': name,
                    'count': len(durations),
                    'total_time': sum(durations),
                    'avg_time': statistics.mean(durations),
                    'min_time': min(durations),
                    'max_time': max(durations),
                    'median_time': statistics.median(durations),
                    'p95_time': self._percentile(durations, 0.95),
                    'p99_time': self._percentile(durations, 0.99)
                }

            # 所有函数的统计
            all_stats = {}
            for func_name, durations in self._function_stats.items():
                all_stats[func_name] = {
                    'count': len(durations),
                    'avg_time': statistics.mean(durations),
                    'total_time': sum(durations)
                }

            return all_stats

    def get_slow_queries(self, threshold: float = 1.0, limit: int = 10) -> List[PerformanceMetric]:
        """获取慢查询"""
        with self._lock:
            slow_metrics = [
                m for m in self.metrics
                if m.duration > threshold
            ]
            slow_metrics.sort(key=lambda m: m.duration, reverse=True)
            return slow_metrics[:limit]

    def get_error_rate(self, name: Optional[str] = None) -> float:
        """获取错误率"""
        with self._lock:
            if name:
                metrics = [m for m in self.metrics if m.name == name]
            else:
                metrics = self.metrics

            if not metrics:
                return 0.0

            errors = sum(1 for m in metrics if not m.success)
            return errors / len(metrics)

    def clear(self):
        """清空指标"""
        with self._lock:
            self.metrics.clear()
            self._function_stats.clear()

    @staticmethod
    def _percentile(data: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def monitor(self, name: Optional[str] = None):
        """性能监控装饰器"""
        def decorator(func: Callable) -> Callable:
            metric_name = name or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                error = None

                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    error = str(e)
                    raise
                finally:
                    duration = time.time() - start_time
                    metric = PerformanceMetric(
                        name=metric_name,
                        duration=duration,
                        timestamp=start_time,
                        success=success,
                        error=error
                    )
                    self.record(metric)

            return wrapper
        return decorator


class PerformanceAnalyzer:
    """性能分析器"""

    def __init__(self, monitor: PerformanceMonitor):
        self.monitor = monitor

    def analyze(self) -> Dict[str, Any]:
        """分析性能"""
        stats = self.monitor.get_stats()
        slow_queries = self.monitor.get_slow_queries()
        error_rate = self.monitor.get_error_rate()

        # 找出最慢的函数
        slowest_functions = sorted(
            stats.items(),
            key=lambda x: x[1].get('avg_time', 0),
            reverse=True
        )[:10]

        # 找出调用最频繁的函数
        most_called = sorted(
            stats.items(),
            key=lambda x: x[1].get('count', 0),
            reverse=True
        )[:10]

        # 找出总耗时最多的函数
        most_time_consuming = sorted(
            stats.items(),
            key=lambda x: x[1].get('total_time', 0),
            reverse=True
        )[:10]

        return {
            'summary': {
                'total_functions': len(stats),
                'total_calls': sum(s.get('count', 0) for s in stats.values()),
                'error_rate': error_rate,
                'slow_queries_count': len(slow_queries)
            },
            'slowest_functions': [
                {
                    'name': name,
                    'avg_time': data.get('avg_time', 0),
                    'count': data.get('count', 0)
                }
                for name, data in slowest_functions
            ],
            'most_called': [
                {
                    'name': name,
                    'count': data.get('count', 0),
                    'avg_time': data.get('avg_time', 0)
                }
                for name, data in most_called
            ],
            'most_time_consuming': [
                {
                    'name': name,
                    'total_time': data.get('total_time', 0),
                    'count': data.get('count', 0)
                }
                for name, data in most_time_consuming
            ],
            'slow_queries': [
                {
                    'name': m.name,
                    'duration': m.duration,
                    'timestamp': datetime.fromtimestamp(m.timestamp).isoformat()
                }
                for m in slow_queries
            ]
        }

    def get_optimization_suggestions(self) -> List[str]:
        """获取优化建议"""
        suggestions = []
        analysis = self.analyze()

        # 检查慢查询
        if analysis['summary']['slow_queries_count'] > 0:
            suggestions.append(
                f"发现 {analysis['summary']['slow_queries_count']} 个慢查询，"
                "建议优化数据库查询或添加索引"
            )

        # 检查错误率
        if analysis['summary']['error_rate'] > 0.01:
            suggestions.append(
                f"错误率较高 ({analysis['summary']['error_rate']:.2%})，"
                "建议检查错误日志并修复问题"
            )

        # 检查最慢的函数
        slowest = analysis['slowest_functions']
        if slowest and slowest[0]['avg_time'] > 1.0:
            suggestions.append(
                f"函数 {slowest[0]['name']} 平均耗时 {slowest[0]['avg_time']:.2f}秒，"
                "建议优化算法或添加缓存"
            )

        # 检查高频调用
        most_called = analysis['most_called']
        if most_called and most_called[0]['count'] > 1000:
            suggestions.append(
                f"函数 {most_called[0]['name']} 被调用 {most_called[0]['count']} 次，"
                "建议添加缓存以减少重复计算"
            )

        # 检查总耗时
        most_time = analysis['most_time_consuming']
        if most_time and most_time[0]['total_time'] > 60:
            suggestions.append(
                f"函数 {most_time[0]['name']} 总耗时 {most_time[0]['total_time']:.2f}秒，"
                "建议优化或考虑异步处理"
            )

        return suggestions


# 全局性能监控器
_global_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


def monitor_performance(name: Optional[str] = None):
    """性能监控装饰器"""
    return get_performance_monitor().monitor(name)


# ═══════════════════════════════════════════════════════════════════════════════
# 使用示例
# ═══════════════════════════════════════════════════════════════════════════════

"""
# 使用装饰器监控性能
@monitor_performance("database_query")
def query_database(sql):
    # 执行数据库查询
    return results

# 手动记录性能
monitor = get_performance_monitor()
start = time.time()
# ... 执行操作 ...
duration = time.time() - start
monitor.record(PerformanceMetric(
    name="custom_operation",
    duration=duration,
    timestamp=start
))

# 获取统计信息
stats = monitor.get_stats("database_query")
print(f"平均耗时: {stats['avg_time']:.3f}秒")
print(f"P95 耗时: {stats['p95_time']:.3f}秒")

# 分析性能
analyzer = PerformanceAnalyzer(monitor)
analysis = analyzer.analyze()
suggestions = analyzer.get_optimization_suggestions()

for suggestion in suggestions:
    print(f"建议: {suggestion}")
"""
