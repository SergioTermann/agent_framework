"""
异步任务处理系统
支持长时间运行的任务异步执行，避免阻塞主线程
"""

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
from queue import Queue, Empty
import agent_framework.core.fast_json as json


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 正在执行
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


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
    progress: float = 0.0  # 0.0 - 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        """用于优先级队列排序"""
        return self.priority.value > other.priority.value

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


class AsyncTaskExecutor:
    """异步任务执行器"""

    def __init__(
        self,
        max_workers: int = 4,
        use_processes: bool = False,
        enable_monitoring: bool = True
    ):
        """
        初始化异步任务执行器

        Args:
            max_workers: 最大工作线程/进程数
            use_processes: 是否使用进程池（CPU密集型任务）
            enable_monitoring: 是否启用性能监控
        """
        self.max_workers = max_workers
        self.use_processes = use_processes
        self.enable_monitoring = enable_monitoring

        # 任务存储
        self.tasks: Dict[str, Task] = {}
        self.task_queue = Queue()

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

        # 性能监控
        if enable_monitoring:
            from agent_framework.infra.performance_monitor import get_performance_monitor
            self.monitor = get_performance_monitor()
        else:
            self.monitor = None

    def start(self):
        """启动任务执行器"""
        if self.running:
            return

        self.running = True

        # 启动工作线程
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"AsyncWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        print(f"[AsyncTaskExecutor] 已启动 {self.max_workers} 个工作线程")

    def stop(self, wait: bool = True):
        """停止任务执行器"""
        self.running = False

        if wait:
            # 等待所有任务完成
            self.task_queue.join()

        # 关闭执行器
        self.executor.shutdown(wait=wait)

        print("[AsyncTaskExecutor] 已停止")

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
        提交任务

        Args:
            func: 要执行的函数
            args: 位置参数
            name: 任务名称
            priority: 任务优先级
            metadata: 元数据
            kwargs: 关键字参数

        Returns:
            任务ID
        """
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

        self.tasks[task_id] = task
        self.task_queue.put(task)

        return task_id

    def _worker_loop(self):
        """工作线程循环"""
        while self.running:
            try:
                # 获取任务（超时1秒）
                task = self.task_queue.get(timeout=1)

                # 执行任务
                self._execute_task(task)

                # 标记任务完成
                self.task_queue.task_done()

            except Empty:
                continue
            except Exception as e:
                print(f"[Worker] 错误: {e}")

    def _execute_task(self, task: Task):
        """执行任务"""
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

            # 触发完成回调
            self._trigger_callbacks('on_complete', task)

        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED

            # 触发错误回调
            self._trigger_callbacks('on_error', task)

        finally:
            task.completed_at = time.time()

    def _trigger_callbacks(self, event: str, task: Task):
        """触发回调函数"""
        for callback in self.callbacks.get(event, []):
            try:
                callback(task)
            except Exception as e:
                print(f"[Callback] 错误: {e}")

    def on(self, event: str, callback: Callable):
        """注册回调函数"""
        if event in self.callbacks:
            self.callbacks[event].append(callback)

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        task = self.get_task(task_id)
        return task.status if task else None

    def get_task_result(self, task_id: str) -> Any:
        """获取任务结果"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        if task.status == TaskStatus.COMPLETED:
            return task.result
        elif task.status == TaskStatus.FAILED:
            raise Exception(f"任务失败: {task.error}")
        else:
            raise Exception(f"任务未完成: {task.status.value}")

    def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """等待任务完成并返回结果"""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        start_time = time.time()
        while task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"任务超时: {task_id}")
            time.sleep(0.1)

        return self.get_task_result(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
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
        """获取所有任务"""
        tasks = list(self.tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        # 按创建时间倒序
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[:limit]

    def get_statistics(self) -> dict:
        """获取统计信息"""
        tasks = list(self.tasks.values())

        stats = {
            'total': len(tasks),
            'pending': sum(1 for t in tasks if t.status == TaskStatus.PENDING),
            'running': sum(1 for t in tasks if t.status == TaskStatus.RUNNING),
            'completed': sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            'failed': sum(1 for t in tasks if t.status == TaskStatus.FAILED),
            'cancelled': sum(1 for t in tasks if t.status == TaskStatus.CANCELLED),
        }

        # 计算平均执行时间
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED and t.duration]
        if completed_tasks:
            stats['avg_duration'] = sum(t.duration for t in completed_tasks) / len(completed_tasks)
        else:
            stats['avg_duration'] = 0

        return stats

    def clear_completed_tasks(self, older_than: Optional[float] = None):
        """清理已完成的任务"""
        now = time.time()
        to_remove = []

        for task_id, task in self.tasks.items():
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                if older_than is None or (now - task.completed_at) > older_than:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del self.tasks[task_id]

        return len(to_remove)


# 全局单例
_executor: Optional[AsyncTaskExecutor] = None


def get_async_executor(
    max_workers: int = 4,
    use_processes: bool = False,
    enable_monitoring: bool = True
) -> AsyncTaskExecutor:
    """获取全局异步任务执行器"""
    global _executor

    if _executor is None:
        _executor = AsyncTaskExecutor(
            max_workers=max_workers,
            use_processes=use_processes,
            enable_monitoring=enable_monitoring
        )
        _executor.start()

    return _executor


def async_task(
    name: Optional[str] = None,
    priority: TaskPriority = TaskPriority.NORMAL
):
    """
    异步任务装饰器

    使用示例:
        @async_task(name="process_data", priority=TaskPriority.HIGH)
        def process_large_dataset(data):
            # 长时间运行的任务
            return result

        # 提交任务
        task_id = process_large_dataset(data)

        # 等待结果
        result = executor.wait_for_task(task_id)
    """
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            executor = get_async_executor()
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
def submit_task(func: Callable, *args, **kwargs) -> str:
    """提交异步任务"""
    executor = get_async_executor()
    return executor.submit(func, *args, **kwargs)


def get_task_result(task_id: str, timeout: Optional[float] = None) -> Any:
    """获取任务结果"""
    executor = get_async_executor()
    return executor.wait_for_task(task_id, timeout=timeout)


def get_task_status(task_id: str) -> Optional[TaskStatus]:
    """获取任务状态"""
    executor = get_async_executor()
    return executor.get_task_status(task_id)
