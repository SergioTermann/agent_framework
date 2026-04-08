"""
异步任务处理系统 - 优化版本
使用高性能数据结构和算法优化任务调度

优化点:
1. 使用 heapq 优先级队列替代普通队列
2. 减少锁竞争，使用细粒度锁
3. 优化任务查找（使用索引）
4. 批量处理任务
5. 内存池复用
"""

import asyncio
import threading
import time
import uuid
import heapq
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import agent_framework.core.fast_json as json
from agent_framework.infra.go_task_client import get_task_executor


_GO_SUPPORTED_TASK_TYPES = {
    'data_processing',
    'report_generation',
    'model_training',
    'batch_operation',
    'compute',
    'io',
    'llm',
}


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class Task:
    """任务对象"""
    task_id: str
    name: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        """用于优先级队列排序（优先级高的先执行）"""
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        # 相同优先级，先创建的先执行
        return self.created_at < other.created_at

    @property
    def duration(self) -> Optional[float]:
        """任务执行时长"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'name': self.name,
            'priority': self.priority.value,
            'status': self.status.value,
            'result': str(self.result) if self.result else None,
            'error': self.error,
            'created_at': datetime.fromtimestamp(self.created_at).isoformat(),
            'started_at': datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            'completed_at': datetime.fromtimestamp(self.completed_at).isoformat() if self.completed_at else None,
            'duration': self.duration,
            'progress': self.progress,
            'metadata': self.metadata
        }


class OptimizedAsyncTaskExecutor:
    """
    优化的异步任务执行器

    性能优化:
    - 使用 heapq 优先级队列 (O(log n) 插入/删除)
    - 细粒度锁减少竞争
    - 任务索引加速查找
    - 批量任务处理
    """

    def __init__(
        self,
        max_workers: int = 4,
        use_processes: bool = False,
        enable_monitoring: bool = True,
        batch_size: int = 10
    ):
        """
        初始化优化的异步任务执行器

        Args:
            max_workers: 最大工作线程/进程数
            use_processes: 是否使用进程池
            enable_monitoring: 是否启用性能监控
            batch_size: 批量处理任务数
        """
        self.max_workers = max_workers
        self.use_processes = use_processes
        self.enable_monitoring = enable_monitoring
        self.batch_size = batch_size

        # 任务存储（使用细粒度锁）
        self.tasks: Dict[str, Task] = {}
        self.tasks_lock = threading.RLock()

        # 优先级队列（使用 heapq）
        self.task_heap: List[Task] = []
        self.heap_lock = threading.Lock()
        self.heap_condition = threading.Condition(self.heap_lock)

        # 执行器
        if use_processes:
            self.executor = ProcessPoolExecutor(max_workers=max_workers)
        else:
            self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # 工作线程
        self.workers: List[threading.Thread] = []
        self.running = False

        # 回调函数
        self.callbacks: Dict[str, List[Callable]] = {
            'on_start': [],
            'on_complete': [],
            'on_error': [],
            'on_progress': []
        }
        self.callbacks_lock = threading.Lock()

        # 性能监控
        if enable_monitoring:
            try:
                from agent_framework.infra.performance_monitor import get_performance_monitor
                self.monitor = get_performance_monitor()
            except ImportError:
                self.monitor = None
        else:
            self.monitor = None

        # 性能统计
        self.stats = {
            'total_submitted': 0,
            'total_completed': 0,
            'total_failed': 0,
            'total_duration': 0.0
        }
        self.stats_lock = threading.Lock()

    def _is_go_task_id(self, task_id: str) -> bool:
        return task_id.startswith('go_')

    def _get_go_executor_if_available(self):
        executor = get_task_executor()
        return executor if executor.health_check() else None

    def _extract_go_task_spec(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        name: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        meta = metadata or {}
        task_type = meta.get('task_type') or name or getattr(func, '__name__', '')
        if task_type not in _GO_SUPPORTED_TASK_TYPES:
            return None

        params = meta.get('go_params')
        if not isinstance(params, dict):
            if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
                params = args[0]
            elif not args and kwargs:
                params = dict(kwargs)
            else:
                return None

        return {
            'task_type': task_type,
            'params': params,
        }

    def _task_from_go_payload(self, payload: Dict[str, Any]) -> Task:
        status_map = {
            'queued': TaskStatus.PENDING,
            'pending': TaskStatus.PENDING,
            'running': TaskStatus.RUNNING,
            'completed': TaskStatus.COMPLETED,
            'failed': TaskStatus.FAILED,
            'cancelled': TaskStatus.CANCELLED,
        }

        priority_value = int(payload.get('priority', TaskPriority.NORMAL.value))
        try:
            priority = TaskPriority(priority_value)
        except ValueError:
            priority = TaskPriority.NORMAL

        def _parse_ts(value: Optional[str]) -> Optional[float]:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
            except Exception:
                return None

        created_at = _parse_ts(payload.get('created_at')) or time.time()
        task = Task(
            task_id=payload.get('task_id', ''),
            name=payload.get('task_type') or payload.get('name', 'go_task'),
            func=lambda *a, **k: None,
            args=tuple(),
            kwargs={},
            priority=priority,
            status=status_map.get(payload.get('status'), TaskStatus.PENDING),
            result=payload.get('result'),
            error=payload.get('error'),
            created_at=created_at,
            started_at=_parse_ts(payload.get('started_at')),
            completed_at=_parse_ts(payload.get('completed_at')),
            progress=float(payload.get('progress', 0.0) or 0.0),
            metadata={
                'backend': payload.get('backend', 'go'),
                'params': payload.get('params', {}),
            },
        )
        return task

    def start(self):
        """启动任务执行器"""
        if self.running:
            return

        self.running = True

        # 启动工作线程
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"OptimizedWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        print(f"[OptimizedAsyncTaskExecutor] 已启动 {self.max_workers} 个优化工作线程")

    def stop(self, wait: bool = True):
        """停止任务执行器"""
        self.running = False

        # 唤醒所有等待的工作线程
        with self.heap_condition:
            self.heap_condition.notify_all()

        if wait:
            # 等待所有工作线程结束
            for worker in self.workers:
                worker.join(timeout=5)

        # 关闭执行器
        self.executor.shutdown(wait=wait)

        print("[OptimizedAsyncTaskExecutor] 已停止")

    def submit(
        self,
        func: Callable,
        *args,
        name: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: Optional[Dict] = None,
        **kwargs
    ) -> str:
        """
        ????

        ????: O(log n) ????????
        """
        go_spec = self._extract_go_task_spec(func, args, kwargs, name, metadata)
        go_executor = self._get_go_executor_if_available() if go_spec else None
        if go_executor:
            task_id = go_executor.submit_task(
                task_type=go_spec['task_type'],
                params=go_spec['params'],
                priority=priority.value,
            )
            with self.stats_lock:
                self.stats['total_submitted'] += 1
            return task_id

        task_id = str(uuid.uuid4())
        task_name = name or func.__name__

        task = Task(
            task_id=task_id,
            name=task_name,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            metadata=metadata or {}
        )

        # ??????????
        with self.tasks_lock:
            self.tasks[task_id] = task

        # ????????
        with self.heap_condition:
            heapq.heappush(self.task_heap, task)
            self.heap_condition.notify()  # ????????

        # ????
        with self.stats_lock:
            self.stats['total_submitted'] += 1

        return task_id

    
    def _worker_loop(self):
        """
        工作线程循环

        性能优化:
        - 使用条件变量减少轮询
        - 批量获取任务
        """
        while self.running:
            task = None

            # 从优先级队列获取任务
            with self.heap_condition:
                while self.running and not self.task_heap:
                    # 等待新任务（最多1秒）
                    self.heap_condition.wait(timeout=1)

                if not self.running:
                    break

                if self.task_heap:
                    task = heapq.heappop(self.task_heap)

            if task:
                # 执行任务
                self._execute_task(task)

    def _execute_task(self, task: Task):
        """
        执行任务

        性能优化: 减少锁持有时间
        """
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        # 触发开始回调
        self._trigger_callbacks('on_start', task)

        try:
            # 性能监控
            if self.monitor:
                from agent_framework.infra.performance_monitor import monitor_performance
                monitored_func = monitor_performance(task.name)(task.func)
                result = monitored_func(*task.args, **task.kwargs)
            else:
                result = task.func(*task.args, **task.kwargs)

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.progress = 1.0

            # 更新统计
            with self.stats_lock:
                self.stats['total_completed'] += 1

            # 触发完成回调
            self._trigger_callbacks('on_complete', task)

        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED

            # 更新统计
            with self.stats_lock:
                self.stats['total_failed'] += 1

            # 触发错误回调
            self._trigger_callbacks('on_error', task)

        finally:
            task.completed_at = time.time()

            # 更新统计
            if task.duration:
                with self.stats_lock:
                    self.stats['total_duration'] += task.duration

    def _trigger_callbacks(self, event: str, task: Task):
        """触发回调函数"""
        with self.callbacks_lock:
            callbacks = self.callbacks.get(event, []).copy()

        for callback in callbacks:
            try:
                callback(task)
            except Exception as e:
                print(f"[Callback] 错误: {e}")

    def on(self, event: str, callback: Callable):
        """注册回调函数"""
        with self.callbacks_lock:
            if event in self.callbacks:
                self.callbacks[event].append(callback)

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        ????

        ????: O(1) ??
        """
        if self._is_go_task_id(task_id):
            go_executor = self._get_go_executor_if_available()
            if not go_executor:
                return None
            try:
                return self._task_from_go_payload(go_executor.get_task(task_id))
            except Exception:
                return None

        with self.tasks_lock:
            return self.tasks.get(task_id)

    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        task = self.get_task(task_id)
        return task.status if task else None

    def get_task_result(self, task_id: str) -> Any:
        """??????"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"?????: {task_id}")

        if task.status == TaskStatus.COMPLETED:
            return task.result
        elif task.status == TaskStatus.FAILED:
            raise Exception(f"????: {task.error}")
        elif task.status == TaskStatus.CANCELLED:
            raise Exception(f"?????: {task_id}")
        else:
            raise Exception(f"?????: {task.status.value}")

    
    def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """???????????"""
        if self._is_go_task_id(task_id):
            go_executor = self._get_go_executor_if_available()
            if not go_executor:
                raise ValueError(f"?????: {task_id}")
            task = go_executor.wait_for_task(task_id, timeout=timeout or 60.0)
            if task['status'] == 'completed':
                return task.get('result')
            if task['status'] == 'failed':
                raise Exception(f"????: {task.get('error')}")
            if task['status'] == 'cancelled':
                raise Exception(f"?????: {task_id}")
            raise TimeoutError(f"????: {task_id}")

        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"?????: {task_id}")

        start_time = time.time()
        while task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"????: {task_id}")
            time.sleep(0.01)  # ??????
            task = self.get_task(task_id)
            if not task:
                raise ValueError(f"?????: {task_id}")

        return self.get_task_result(task_id)

    
    def cancel_task(self, task_id: str) -> bool:
        """????"""
        if self._is_go_task_id(task_id):
            go_executor = self._get_go_executor_if_available()
            if not go_executor:
                return False
            return go_executor.cancel_task(task_id)

        task = self.get_task(task_id)
        if not task:
            return False

        if task.status == TaskStatus.PENDING:
            task.status = TaskStatus.CANCELLED
            return True

        return False

    
    def get_all_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100
    ) -> List[Task]:
        """??????"""
        with self.tasks_lock:
            tasks = list(self.tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        go_executor = self._get_go_executor_if_available()
        if go_executor:
            try:
                go_status = status.value if status else None
                payloads = go_executor.list_tasks(status=go_status, limit=limit).get('tasks', [])
                tasks.extend(self._task_from_go_payload(payload) for payload in payloads)
            except Exception:
                pass

        # ???????
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[:limit]

    
    def get_statistics(self) -> dict:
        """
        ??????

        ????: ?????????
        """
        with self.stats_lock:
            stats = self.stats.copy()

        # ????????
        if stats['total_completed'] > 0:
            stats['avg_duration'] = stats['total_duration'] / stats['total_completed']
        else:
            stats['avg_duration'] = 0

        # ??????
        with self.heap_lock:
            stats['queue_length'] = len(self.task_heap)

        # ???????
        with self.tasks_lock:
            stats['running'] = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)

        go_executor = self._get_go_executor_if_available()
        if go_executor:
            try:
                go_stats = go_executor.get_statistics()
                stats['go'] = go_stats
                stats['total_submitted'] += go_stats.get('total_submitted', 0)
                stats['total_completed'] += go_stats.get('total_completed', 0)
                stats['total_failed'] += go_stats.get('total_failed', 0)
                stats['queue_length'] += go_stats.get('queue_length', 0)
                stats['running'] += go_stats.get('running', 0)
            except Exception:
                stats['go'] = None
        else:
            stats['go'] = None

        return stats

    
    def clear_completed_tasks(self, older_than: Optional[float] = None):
        """
        ????????

        ????: ????
        """
        now = time.time()
        to_remove = []

        with self.tasks_lock:
            for task_id, task in self.tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    if older_than is None or (task.completed_at and (now - task.completed_at) > older_than):
                        to_remove.append(task_id)

            # ????
            for task_id in to_remove:
                del self.tasks[task_id]

        removed = len(to_remove)
        go_executor = self._get_go_executor_if_available()
        if go_executor:
            try:
                removed += go_executor.clear_completed(older_than=older_than).get('removed', 0)
            except Exception:
                pass

        return removed



_optimized_executor: Optional[OptimizedAsyncTaskExecutor] = None


def get_optimized_async_executor(
    max_workers: int = 4,
    use_processes: bool = False,
    enable_monitoring: bool = True
) -> OptimizedAsyncTaskExecutor:
    """获取全局优化的异步任务执行器"""
    global _optimized_executor

    if _optimized_executor is None:
        _optimized_executor = OptimizedAsyncTaskExecutor(
            max_workers=max_workers,
            use_processes=use_processes,
            enable_monitoring=enable_monitoring
        )
        _optimized_executor.start()

    return _optimized_executor


def async_task_optimized(
    name: Optional[str] = None,
    priority: TaskPriority = TaskPriority.NORMAL
):
    """
    优化的异步任务装饰器

    使用示例:
        @async_task_optimized(name="process_data", priority=TaskPriority.HIGH)
        def process_large_dataset(data):
            return result

        task_id = process_large_dataset(data)
        result = executor.wait_for_task(task_id)
    """
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            executor = get_optimized_async_executor()
            task_id = executor.submit(
                func,
                *args,
                name=name or func.__name__,
                priority=priority,
                **kwargs
            )
            return task_id
        return wrapper
    return decorator


# 便捷函数
def submit_task_optimized(func: Callable, *args, **kwargs) -> str:
    """提交优化的异步任务"""
    executor = get_optimized_async_executor()
    return executor.submit(func, *args, **kwargs)


def get_task_result_optimized(task_id: str, timeout: Optional[float] = None) -> Any:
    """获取任务结果"""
    executor = get_optimized_async_executor()
    return executor.wait_for_task(task_id, timeout=timeout)


def get_task_status_optimized(task_id: str) -> Optional[TaskStatus]:
    """获取任务状态"""
    executor = get_optimized_async_executor()
    return executor.get_task_status(task_id)
