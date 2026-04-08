"""
异步任务 API
提供异步任务管理的 REST API 接口
"""

from flask import Blueprint, jsonify, request
from agent_framework.core.api_utils import json_error as _json_error, json_success as _json_success, request_json as _request_json
from agent_framework.infra.async_task_system import (
    get_async_executor,
    TaskStatus,
    TaskPriority,
    get_task_status
)
from datetime import datetime
from agent_framework.infra.go_task_client import get_task_executor

async_task_bp = Blueprint('async_task', __name__, url_prefix='/api/tasks')
_GO_TASK_TYPES = {'data_processing', 'report_generation', 'model_training', 'batch_operation'}


def _get_go_executor_if_available():
    executor = get_task_executor()
    return executor if executor.health_check() else None


def _infer_backend(task_id: str) -> str:
    return 'go' if task_id.startswith('go_') else 'python'


def _get_go_executor_or_response():
    executor = _get_go_executor_if_available()
    if not executor:
        return None, _json_error('Go backend unavailable', 503)
    return executor, None


def _task_result_from_status(task_id: str, *, backend: str, status: str, result=None, duration=None, error_message=None):
    if status in {'queued', 'pending'}:
        return _json_error('task pending')
    if status == 'running':
        return _json_error('task running')
    if status == 'failed':
        return _json_error('task failed', 500, message=error_message)
    if status == 'cancelled':
        return _json_error('task cancelled')

    payload = {
        'task_id': task_id,
        'status': status,
        'result': result,
        'backend': backend,
    }
    if duration is not None:
        payload['duration'] = duration
    return jsonify(payload)


@async_task_bp.route('/submit', methods=['POST'])
def submit_async_task():
    """
    提交异步任务

    请求体:
    {
        "task_type": "data_processing",  # 任务类型
        "params": {...},                  # 任务参数
        "priority": "normal"              # 优先级: low, normal, high, urgent
    }
    """
    data = _request_json()

    task_type = data.get('task_type')
    params = data.get('params', {})
    priority_str = data.get('priority', 'normal').upper()

    if not task_type:
        return _json_error('缺少 task_type')

    try:
        priority = TaskPriority[priority_str]
    except KeyError:
        return _json_error(f'无效的优先级: {priority_str}')

    # 根据任务类型执行不同的函数
    task_functions = {
        'data_processing': process_data_task,
        'report_generation': generate_report_task,
        'model_training': train_model_task,
        'batch_operation': batch_operation_task,
    }

    task_func = task_functions.get(task_type)
    if not task_func:
        return _json_error(f'未知的任务类型: {task_type}')

    # Prefer Go backend; fall back to Python when unavailable
    go_executor = _get_go_executor_if_available()
    if go_executor and task_type in _GO_TASK_TYPES:
        task_id = go_executor.submit_task(
            task_type=task_type,
            params=params,
            priority=priority.value
        )
        backend = 'go'
    else:
        executor = get_async_executor()
        task_id = executor.submit(
            task_func,
            params,
            name=task_type,
            priority=priority,
            metadata={'task_type': task_type}
        )
        backend = 'python'

    return _json_success({
        'task_id': task_id,
        'status': 'submitted',
        'backend': backend,
        'message': 'task submitted'
    })


@async_task_bp.route('/<task_id>', methods=['GET'])
def get_task_info(task_id: str):
    """Get task info."""
    backend = _infer_backend(task_id)

    if backend == 'go':
        go_executor, error_response = _get_go_executor_or_response()
        if error_response:
            return error_response
        try:
            return jsonify(go_executor.get_task(task_id))
        except Exception as e:
            return _json_error(str(e), 404)

    executor = get_async_executor()
    task = executor.get_task(task_id)
    if not task:
        return _json_error('task not found', 404)
    payload = task.to_dict()
    payload['backend'] = 'python'
    return jsonify(payload)


@async_task_bp.route('/<task_id>/status', methods=['GET'])
def get_task_status_api(task_id: str):
    """Get task status."""
    backend = _infer_backend(task_id)

    if backend == 'go':
        go_executor, error_response = _get_go_executor_or_response()
        if error_response:
            return error_response
        try:
            return jsonify(go_executor.get_task_status(task_id))
        except Exception as e:
            return _json_error(str(e), 404)

    status = get_task_status(task_id)
    if not status:
        return _json_error('task not found', 404)

    return jsonify({
        'task_id': task_id,
        'status': status.value,
        'backend': 'python'
    })


@async_task_bp.route('/<task_id>/result', methods=['GET'])
def get_task_result_api(task_id: str):
    """Get task result."""
    backend = _infer_backend(task_id)

    if backend == 'go':
        go_executor, error_response = _get_go_executor_or_response()
        if error_response:
            return error_response
        try:
            task = go_executor.get_task(task_id)
        except Exception as e:
            return _json_error(str(e), 404)

        return _task_result_from_status(
            task_id,
            backend='go',
            status=task['status'],
            result=task.get('result'),
            error_message=task.get('error')
        )

    executor = get_async_executor()
    task = executor.get_task(task_id)

    if not task:
        return _json_error('task not found', 404)

    return _task_result_from_status(
        task_id,
        backend='python',
        status=task.status.value,
        result=task.result,
        duration=task.duration,
        error_message=task.error
    )


@async_task_bp.route('/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id: str):
    """Cancel task."""
    backend = _infer_backend(task_id)

    if backend == 'go':
        go_executor, error_response = _get_go_executor_or_response()
        if error_response:
            return error_response
        success = go_executor.cancel_task(task_id)
    else:
        executor = get_async_executor()
        success = executor.cancel_task(task_id)

    if not success:
        return _json_error('unable to cancel task')

    return _json_success({
        'task_id': task_id,
        'status': 'cancelled',
        'backend': backend,
        'message': 'task cancelled'
    })


@async_task_bp.route('/list', methods=['GET'])
def list_tasks():
    """List tasks."""
    status_str = request.args.get('status')
    limit = max(1, min(request.args.get('limit', 100, type=int), 200))

    executor = get_async_executor()

    status_filter = None
    if status_str:
        try:
            status_filter = TaskStatus(status_str)
        except ValueError:
            return _json_error(f'invalid status: {status_str}')

    tasks = [dict(task.to_dict(), backend='python') for task in executor.get_all_tasks(status=status_filter, limit=limit)]

    go_executor = _get_go_executor_if_available()
    if go_executor:
        try:
            go_tasks = go_executor.list_tasks(status=status_str, limit=limit).get('tasks', [])
            tasks.extend(go_tasks)
        except Exception:
            pass

    tasks.sort(key=lambda task: task.get('created_at') or '', reverse=True)
    tasks = tasks[:limit]

    return jsonify({
        'tasks': tasks,
        'count': len(tasks)
    })


@async_task_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """Get task statistics."""
    python_stats = get_async_executor().get_statistics()
    go_stats = None

    go_executor = _get_go_executor_if_available()
    if go_executor:
        try:
            go_stats = go_executor.get_statistics()
        except Exception:
            go_stats = None

    aggregate = {
        'backend': 'hybrid',
        'python': python_stats,
        'go': go_stats,
        'total_submitted': python_stats.get('total_submitted', 0) + (go_stats or {}).get('total_submitted', 0),
        'total_completed': python_stats.get('total_completed', 0) + (go_stats or {}).get('total_completed', 0),
        'total_failed': python_stats.get('total_failed', 0) + (go_stats or {}).get('total_failed', 0),
        'queue_length': python_stats.get('queue_length', 0) + (go_stats or {}).get('queue_length', 0),
        'running': python_stats.get('running', 0) + (go_stats or {}).get('running', 0),
    }
    return jsonify(aggregate)


@async_task_bp.route('/clear', methods=['POST'])
def clear_completed():
    """Clear completed tasks."""
    older_than = request.args.get('older_than', type=float)

    python_removed = get_async_executor().clear_completed_tasks(older_than=older_than)
    go_removed = 0

    go_executor = _get_go_executor_if_available()
    if go_executor:
        try:
            go_removed = go_executor.clear_completed(older_than=older_than).get('removed', 0)
        except Exception:
            go_removed = 0

    removed = python_removed + go_removed
    return jsonify({
        'removed': removed,
        'python_removed': python_removed,
        'go_removed': go_removed,
        'message': f'cleared {removed} tasks'
    })


# ============================================================================
# 示例任务函数
# ============================================================================

def process_data_task(params: dict):
    """数据处理任务示例"""
    import time

    data_size = params.get('data_size', 1000)
    delay = params.get('delay', 0.001)

    result = []
    for i in range(data_size):
        # 模拟数据处理
        result.append(i * 2)
        time.sleep(delay)

    return {
        'processed': len(result),
        'sample': result[:10]
    }


def generate_report_task(params: dict):
    """报告生成任务示例"""
    import time

    report_type = params.get('type', 'summary')
    time.sleep(2)  # 模拟报告生成

    return {
        'report_type': report_type,
        'generated_at': datetime.now().isoformat(),
        'pages': 10,
        'url': f'/reports/{report_type}_report.pdf'
    }


def train_model_task(params: dict):
    """模型训练任务示例"""
    import time

    model_type = params.get('model_type', 'linear')
    epochs = params.get('epochs', 10)

    for epoch in range(epochs):
        time.sleep(0.5)  # 模拟训练

    return {
        'model_type': model_type,
        'epochs': epochs,
        'accuracy': 0.95,
        'model_path': f'/models/{model_type}_model.pkl'
    }


def batch_operation_task(params: dict):
    """批量操作任务示例"""
    import time

    operation = params.get('operation', 'update')
    items = params.get('items', [])

    results = []
    for item in items:
        time.sleep(0.1)  # 模拟操作
        results.append({
            'item': item,
            'status': 'success'
        })

    return {
        'operation': operation,
        'total': len(items),
        'success': len(results),
        'failed': 0
    }
