"""
工作流高级功能
==================

实现工作流的高级特性:
1. 循环节点 (LOOP)
2. 并行执行 (PARALLEL)
3. 错误处理 (TRY-CATCH)
4. 重试机制 (RETRY)
5. 子工作流调用 (SUBFLOW)
6. 定时触发 (SCHEDULE)
"""

from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict, Callable
from datetime import datetime, timedelta
import asyncio
import threading
import time
import uuid
from enum import Enum
from agent_framework.infra.async_task_system_optimized import get_optimized_async_executor


class AdvancedNodeType:
    """高级节点类型"""
    LOOP = "loop"              # 循环节点
    PARALLEL = "parallel"      # 并行节点
    TRY_CATCH = "try_catch"    # 错误处理节点
    RETRY = "retry"            # 重试节点
    SUBFLOW = "subflow"        # 子工作流节点
    SCHEDULE = "schedule"      # 定时触发节点
    MERGE = "merge"            # 合并节点
    SPLIT = "split"            # 分流节点


class ExecutionStatus(str, Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass
class LoopConfig:
    """循环配置"""
    loop_type: str = "count"  # count, while, foreach
    count: int = 1            # 循环次数（count模式）
    condition: str = ""       # 循环条件（while模式）
    items_var: str = ""       # 迭代变量（foreach模式）
    item_var: str = "item"    # 当前项变量名
    index_var: str = "index"  # 索引变量名
    max_iterations: int = 100 # 最大迭代次数（防止死循环）


@dataclass
class ParallelConfig:
    """并行配置"""
    branches: List[str] = field(default_factory=list)  # 并行分支节点ID
    wait_all: bool = True      # 是否等待所有分支完成
    timeout: int = 300         # 超时时间（秒）
    merge_results: bool = True # 是否合并结果


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3           # 最大重试次数
    retry_delay: float = 1.0       # 重试延迟（秒）
    backoff_multiplier: float = 2.0 # 退避倍数
    retry_on_errors: List[str] = field(default_factory=list)  # 重试的错误类型


@dataclass
class TryCatchConfig:
    """错误处理配置"""
    try_node: str = ""         # try块节点ID
    catch_node: str = ""       # catch块节点ID
    finally_node: str = ""     # finally块节点ID
    error_var: str = "error"   # 错误变量名


@dataclass
class SubflowConfig:
    """子工作流配置"""
    workflow_id: str = ""      # 子工作流ID
    input_mapping: Dict[str, str] = field(default_factory=dict)  # 输入映射
    output_mapping: Dict[str, str] = field(default_factory=dict) # 输出映射


@dataclass
class ScheduleConfig:
    """定时触发配置"""
    schedule_type: str = "cron"  # cron, interval, once
    cron_expression: str = ""    # Cron表达式
    interval_seconds: int = 0    # 间隔秒数
    start_time: str = ""         # 开始时间
    end_time: str = ""           # 结束时间
    enabled: bool = True         # 是否启用


@dataclass
class ExecutionContext:
    """执行上下文"""
    workflow_id: str
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    variables: Dict[str, Any] = field(default_factory=dict)
    status: ExecutionStatus = ExecutionStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None
    parent_context: Optional['ExecutionContext'] = None

    def get_variable(self, name: str, default=None):
        """获取变量（支持父上下文查找）"""
        if name in self.variables:
            return self.variables[name]
        if self.parent_context:
            return self.parent_context.get_variable(name, default)
        return default

    def set_variable(self, name: str, value: Any):
        """设置变量"""
        self.variables[name] = value


class LoopExecutor:
    """循环执行器"""

    def __init__(self, config: LoopConfig):
        self.config = config

    def execute(self, context: ExecutionContext, node_executor: Callable, loop_body_node) -> Dict[str, Any]:
        """执行循环"""
        results = []

        if self.config.loop_type == "count":
            # 计数循环
            for i in range(self.config.count):
                context.set_variable(self.config.index_var, i)
                result = node_executor(loop_body_node, context)
                results.append(result)

        elif self.config.loop_type == "while":
            # 条件循环
            iteration = 0
            while iteration < self.config.max_iterations:
                # 评估条件
                condition_result = self._evaluate_condition(self.config.condition, context)
                if not condition_result:
                    break

                context.set_variable(self.config.index_var, iteration)
                result = node_executor(loop_body_node, context)
                results.append(result)
                iteration += 1

        elif self.config.loop_type == "foreach":
            # 遍历循环
            items = context.get_variable(self.config.items_var, [])
            for i, item in enumerate(items):
                context.set_variable(self.config.item_var, item)
                context.set_variable(self.config.index_var, i)
                result = node_executor(loop_body_node, context)
                results.append(result)

        return {
            'results': results,
            'iterations': len(results)
        }

    def _evaluate_condition(self, condition: str, context: ExecutionContext) -> bool:
        """评估条件"""
        try:
            # 替换变量
            for key, value in context.variables.items():
                condition = condition.replace(f"{{{key}}}", repr(value))
            return eval(condition)
        except Exception:
            return False


class ParallelExecutor:
    """并行执行器"""

    def __init__(self, config: ParallelConfig):
        self.config = config

    def execute(self, context: ExecutionContext, node_executor: Callable, branch_nodes: List) -> Dict[str, Any]:
        """并行执行多个分支"""
        results = {}
        errors = {}
        optimized_executor = get_optimized_async_executor(enable_monitoring=False)
        branch_task_ids = {}
        branch_contexts = {}
        branch_results = {}

        def execute_branch(branch_node, branch_context):
            return node_executor(branch_node, branch_context)

        # 通过统一执行器提交并行分支；执行器内部可继续选择 Python / Go 后端
        for i, branch_node in enumerate(branch_nodes):
            branch_id = f"branch_{i}"
            branch_context = ExecutionContext(
                workflow_id=context.workflow_id,
                variables=context.variables.copy(),
                parent_context=context
            )
            branch_contexts[branch_id] = branch_context
            branch_task_ids[branch_id] = optimized_executor.submit(
                execute_branch,
                branch_node,
                branch_context,
                name=f"workflow_parallel_{getattr(branch_node, 'id', branch_id)}",
                metadata={
                    'task_type': 'workflow_parallel_branch',
                    'branch_id': branch_id,
                    'node_id': getattr(branch_node, 'id', ''),
                    'node_type': getattr(branch_node, 'type', ''),
                }
            )

        start_time = time.time()
        for branch_id, task_id in branch_task_ids.items():
            try:
                remaining_time = self.config.timeout - (time.time() - start_time)
                if remaining_time <= 0:
                    raise TimeoutError(f"branch timeout: {branch_id}")
                result = optimized_executor.wait_for_task(task_id, timeout=remaining_time)
                branch_results[branch_id] = {
                    'success': True,
                    'result': result,
                    'context': branch_contexts[branch_id].variables
                }
            except Exception as e:
                branch_results[branch_id] = {
                    'success': False,
                    'error': str(e)
                }

        # 收集结果
        for branch_id, result in branch_results.items():
            if result['success']:
                results[branch_id] = result['result']
                if self.config.merge_results:
                    context.variables.update(result['context'])
            else:
                errors[branch_id] = result['error']

        # 检查是否所有分支都成功
        all_success = len(errors) == 0
        if self.config.wait_all and not all_success:
            raise Exception(f"部分分支执行失败: {errors}")

        return {
            'results': results,
            'errors': errors,
            'success_count': len(results),
            'error_count': len(errors)
        }


class RetryExecutor:
    """重试执行器"""

    def __init__(self, config: RetryConfig):
        self.config = config

    def execute(self, context: ExecutionContext, node_executor: Callable, target_node) -> Any:
        """执行带重试的节点"""
        last_error = None
        delay = self.config.retry_delay

        for attempt in range(self.config.max_retries + 1):
            try:
                context.status = ExecutionStatus.RUNNING if attempt == 0 else ExecutionStatus.RETRYING
                result = node_executor(target_node, context)
                context.status = ExecutionStatus.SUCCESS
                return result

            except Exception as e:
                last_error = e
                error_type = type(e).__name__

                # 检查是否应该重试此类错误
                if self.config.retry_on_errors and error_type not in self.config.retry_on_errors:
                    raise

                # 如果还有重试次数
                if attempt < self.config.max_retries:
                    time.sleep(delay)
                    delay *= self.config.backoff_multiplier
                else:
                    context.status = ExecutionStatus.FAILED
                    raise

        raise last_error


class TryCatchExecutor:
    """错误处理执行器"""

    def __init__(self, config: TryCatchConfig):
        self.config = config

    def execute(self, context: ExecutionContext, node_executor: Callable,
                try_node, catch_node=None, finally_node=None) -> Dict[str, Any]:
        """执行try-catch-finally"""
        result = None
        error = None

        try:
            # 执行try块
            result = node_executor(try_node, context)

        except Exception as e:
            # 捕获错误
            error = e
            context.set_variable(self.config.error_var, {
                'type': type(e).__name__,
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })

            # 执行catch块
            if catch_node:
                try:
                    result = node_executor(catch_node, context)
                except Exception as catch_error:
                    # catch块也失败了
                    error = catch_error

        finally:
            # 执行finally块
            if finally_node:
                try:
                    node_executor(finally_node, context)
                except Exception:
                    pass  # finally块的错误不影响结果

        if error and not catch_node:
            raise error

        return {
            'result': result,
            'error': str(error) if error else None,
            'has_error': error is not None
        }


class SubflowExecutor:
    """子工作流执行器"""

    def __init__(self, config: SubflowConfig):
        self.config = config

    def execute(self, context: ExecutionContext, workflow_executor: Callable) -> Dict[str, Any]:
        """执行子工作流"""
        # 创建子工作流上下文
        subflow_context = ExecutionContext(
            workflow_id=self.config.workflow_id,
            parent_context=context
        )

        # 映射输入变量
        for subflow_var, parent_var in self.config.input_mapping.items():
            value = context.get_variable(parent_var)
            subflow_context.set_variable(subflow_var, value)

        # 执行子工作流
        result = workflow_executor(self.config.workflow_id, subflow_context)

        # 映射输出变量
        for parent_var, subflow_var in self.config.output_mapping.items():
            value = subflow_context.get_variable(subflow_var)
            context.set_variable(parent_var, value)

        return result


class ScheduleExecutor:
    """定时触发执行器"""

    def __init__(self, config: ScheduleConfig):
        self.config = config
        self.running = False
        self.thread = None

    def start(self, workflow_executor: Callable, workflow_id: str):
        """启动定时任务"""
        if not self.config.enabled:
            return

        self.running = True

        if self.config.schedule_type == "interval":
            self.thread = threading.Thread(
                target=self._run_interval,
                args=(workflow_executor, workflow_id)
            )
        elif self.config.schedule_type == "cron":
            self.thread = threading.Thread(
                target=self._run_cron,
                args=(workflow_executor, workflow_id)
            )
        elif self.config.schedule_type == "once":
            self.thread = threading.Thread(
                target=self._run_once,
                args=(workflow_executor, workflow_id)
            )

        if self.thread:
            self.thread.daemon = True
            self.thread.start()

    def stop(self):
        """停止定时任务"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _run_interval(self, workflow_executor: Callable, workflow_id: str):
        """间隔执行"""
        while self.running:
            try:
                context = ExecutionContext(workflow_id=workflow_id)
                workflow_executor(workflow_id, context)
            except Exception as e:
                print(f"定时任务执行失败: {e}")

            time.sleep(self.config.interval_seconds)

    def _run_cron(self, workflow_executor: Callable, workflow_id: str):
        """Cron表达式执行"""
        try:
            from croniter import croniter
        except ImportError:
            print("Warning: croniter not installed. Install with: pip install croniter")
            print("Falling back to simple interval execution every 60 seconds")
            while self.running:
                time.sleep(60)
                try:
                    context = ExecutionContext(workflow_id=workflow_id)
                    workflow_executor(workflow_id, context)
                except Exception as e:
                    print(f"定时任务执行失败: {e}")
            return

        # 使用 croniter 解析 Cron 表达式
        base_time = datetime.now()
        cron = croniter(self.config.cron_expression, base_time)

        while self.running:
            # 获取下次执行时间
            next_run = cron.get_next(datetime)

            # 等待到下次执行时间
            now = datetime.now()
            if next_run > now:
                delay = (next_run - now).total_seconds()
                if delay > 0:
                    time.sleep(min(delay, 1))  # 最多睡眠1秒，以便及时响应停止信号
                    continue

            # 执行工作流
            try:
                context = ExecutionContext(workflow_id=workflow_id)
                workflow_executor(workflow_id, context)
            except Exception as e:
                print(f"定时任务执行失败: {e}")

            # 移动到下一个执行时间
            cron = croniter(self.config.cron_expression, datetime.now())

    def _run_once(self, workflow_executor: Callable, workflow_id: str):
        """一次性执行"""
        if self.config.start_time:
            # 等待到指定时间
            start_dt = datetime.fromisoformat(self.config.start_time)
            now = datetime.now()
            if start_dt > now:
                delay = (start_dt - now).total_seconds()
                time.sleep(delay)

        try:
            context = ExecutionContext(workflow_id=workflow_id)
            workflow_executor(workflow_id, context)
        except Exception as e:
            print(f"定时任务执行失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 工作流调试器
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Breakpoint:
    """断点"""
    node_id: str
    condition: Optional[str] = None  # 条件断点
    enabled: bool = True


class WorkflowDebugger:
    """工作流调试器"""

    def __init__(self):
        self.breakpoints: Dict[str, Breakpoint] = {}
        self.paused = False
        self.step_mode = False
        self.current_node = None
        self.execution_stack = []
        self.watch_variables = set()

    def add_breakpoint(self, node_id: str, condition: Optional[str] = None):
        """添加断点"""
        self.breakpoints[node_id] = Breakpoint(
            node_id=node_id,
            condition=condition
        )

    def remove_breakpoint(self, node_id: str):
        """移除断点"""
        if node_id in self.breakpoints:
            del self.breakpoints[node_id]

    def should_pause(self, node_id: str, context: ExecutionContext) -> bool:
        """检查是否应该暂停"""
        if self.step_mode:
            return True

        if node_id in self.breakpoints:
            bp = self.breakpoints[node_id]
            if not bp.enabled:
                return False

            # 检查条件断点
            if bp.condition:
                try:
                    condition = bp.condition
                    for key, value in context.variables.items():
                        condition = condition.replace(f"{{{key}}}", repr(value))
                    return eval(condition)
                except Exception:
                    return False

            return True

        return False

    def pause(self):
        """暂停执行"""
        self.paused = True

    def resume(self):
        """继续执行"""
        self.paused = False
        self.step_mode = False

    def step_over(self):
        """单步执行"""
        self.step_mode = True
        self.paused = False

    def get_stack_trace(self) -> List[Dict]:
        """获取调用栈"""
        return self.execution_stack.copy()

    def watch_variable(self, var_name: str):
        """监视变量"""
        self.watch_variables.add(var_name)

    def get_watched_variables(self, context: ExecutionContext) -> Dict[str, Any]:
        """获取监视的变量值"""
        return {
            var: context.get_variable(var)
            for var in self.watch_variables
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 工作流版本控制
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class WorkflowVersion:
    """工作流版本"""
    version_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    version_number: str = "1.0.0"
    workflow_data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""
    commit_message: str = ""
    tags: List[str] = field(default_factory=list)


class WorkflowVersionControl:
    """工作流版本控制"""

    def __init__(self):
        self.versions: Dict[str, List[WorkflowVersion]] = {}

    def commit(self, workflow_id: str, workflow_data: Dict[str, Any],
               message: str, user: str = "system") -> WorkflowVersion:
        """提交新版本"""
        if workflow_id not in self.versions:
            self.versions[workflow_id] = []

        # 计算版本号
        versions = self.versions[workflow_id]
        if versions:
            last_version = versions[-1].version_number
            major, minor, patch = map(int, last_version.split('.'))
            new_version = f"{major}.{minor}.{patch + 1}"
        else:
            new_version = "1.0.0"

        # 创建版本
        version = WorkflowVersion(
            workflow_id=workflow_id,
            version_number=new_version,
            workflow_data=workflow_data,
            created_by=user,
            commit_message=message
        )

        self.versions[workflow_id].append(version)
        return version

    def get_version(self, workflow_id: str, version_number: str) -> Optional[WorkflowVersion]:
        """获取指定版本"""
        if workflow_id not in self.versions:
            return None

        for version in self.versions[workflow_id]:
            if version.version_number == version_number:
                return version

        return None

    def get_latest_version(self, workflow_id: str) -> Optional[WorkflowVersion]:
        """获取最新版本"""
        if workflow_id not in self.versions or not self.versions[workflow_id]:
            return None

        return self.versions[workflow_id][-1]

    def list_versions(self, workflow_id: str) -> List[WorkflowVersion]:
        """列出所有版本"""
        return self.versions.get(workflow_id, [])

    def rollback(self, workflow_id: str, version_number: str) -> Optional[WorkflowVersion]:
        """回滚到指定版本"""
        version = self.get_version(workflow_id, version_number)
        if not version:
            return None

        # 创建新版本（基于旧版本）
        return self.commit(
            workflow_id,
            version.workflow_data,
            f"回滚到版本 {version_number}",
            "system"
        )

    def tag_version(self, workflow_id: str, version_number: str, tag: str):
        """给版本打标签"""
        version = self.get_version(workflow_id, version_number)
        if version and tag not in version.tags:
            version.tags.append(tag)

    def compare_versions(self, workflow_id: str, version1: str, version2: str) -> Dict[str, Any]:
        """比较两个版本"""
        v1 = self.get_version(workflow_id, version1)
        v2 = self.get_version(workflow_id, version2)

        if not v1 or not v2:
            return {'error': '版本不存在'}

        # 简单的差异比较
        return {
            'version1': version1,
            'version2': version2,
            'nodes_added': len(v2.workflow_data.get('nodes', [])) - len(v1.workflow_data.get('nodes', [])),
            'edges_added': len(v2.workflow_data.get('edges', [])) - len(v1.workflow_data.get('edges', [])),
            'variables_changed': v1.workflow_data.get('variables') != v2.workflow_data.get('variables')
        }
