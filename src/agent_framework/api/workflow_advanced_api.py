"""
工作流高级功能 API
==================

提供工作流高级功能的REST API接口
"""

from flask import Blueprint, request, jsonify
from agent_framework.core.api_utils import json_error as _json_error, json_success as _json_success
from agent_framework.workflow.visual_workflow import (
    WorkflowNode,
    save_workflow, get_workflow
)
from agent_framework.workflow.workflow_executor_enhanced import EnhancedWorkflowExecutor
from agent_framework.workflow.workflow_advanced import (
    AdvancedNodeType, ScheduleConfig,
    ScheduleExecutor
)
from pathlib import Path
from datetime import datetime

from agent_framework.core.database import get_db_connection

workflow_advanced_bp = Blueprint('workflow_advanced', __name__, url_prefix='/api/workflow-advanced')

# 存储执行器实例
_executors = {}

# 存储定时任务执行器
_schedule_executors = {}

# 定时任务数据库
SCHEDULE_DB_PATH = "data/schedules.db"


def _load_workflow_or_404(workflow_id: str):
    workflow = get_workflow(workflow_id)
    if not workflow:
        return None, _json_error("工作流不存在", 404)
    return workflow, None


def _create_node_response(
    workflow_id: str,
    *,
    node_type,
    default_label: str,
    config: dict,
):
    workflow, error_response = _load_workflow_or_404(workflow_id)
    if error_response:
        return error_response

    data = request.json or {}
    node = WorkflowNode(
        type=node_type,
        label=data.get("label", default_label),
        config=config,
        position=data.get("position", {"x": 0, "y": 0}),
    )

    workflow.add_node(node)
    save_workflow(workflow)

    return jsonify(node.to_dict())


def _serialize_schedule_row(row) -> dict:
    return {
        "schedule_id": row[0],
        "workflow_id": row[1],
        "schedule_type": row[2],
        "cron_expression": row[3],
        "interval_seconds": row[4],
        "start_time": row[5],
        "end_time": row[6],
        "enabled": bool(row[7]),
        "created_at": row[8],
        "updated_at": row[9],
    }


def init_schedule_db():
    """初始化定时任务数据库"""
    Path(SCHEDULE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection(SCHEDULE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                schedule_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                cron_expression TEXT,
                interval_seconds INTEGER,
                start_time TEXT,
                end_time TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


# 初始化数据库
init_schedule_db()


def get_executor(workflow_id: str) -> EnhancedWorkflowExecutor:
    """获取或创建执行器"""
    if workflow_id not in _executors:
        workflow = get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"工作流不存在: {workflow_id}")
        _executors[workflow_id] = EnhancedWorkflowExecutor(workflow)
    return _executors[workflow_id]


# ═══════════════════════════════════════════════════════════════════════════════
# 工作流执行
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/execute', methods=['POST'])
def execute_workflow_advanced(workflow_id):
    """执行工作流（增强版）"""
    try:
        data = request.json or {}
        input_data = data.get('input', {})
        debug_mode = data.get('debug', False)

        executor = get_executor(workflow_id)
        result = executor.execute(input_data, debug_mode)

        return jsonify(result)

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/execute/history', methods=['GET'])
def get_execution_history(workflow_id):
    """获取执行历史"""
    try:
        limit = request.args.get('limit', 100, type=int)
        executor = get_executor(workflow_id)
        history = executor.get_execution_history(limit)

        return jsonify({'history': history})

    except Exception as e:
        return _json_error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 循环节点
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/nodes/loop', methods=['POST'])
def add_loop_node(workflow_id):
    """添加循环节点"""
    try:
        data = request.json or {}
        return _create_node_response(
            workflow_id,
            node_type=AdvancedNodeType.LOOP,
            default_label='循环',
            config={
                'loop_type': data.get('loop_type', 'count'),  # count, while, foreach
                'count': data.get('count', 1),
                'condition': data.get('condition', ''),
                'items_var': data.get('items_var', ''),
                'item_var': data.get('item_var', 'item'),
                'index_var': data.get('index_var', 'index'),
                'max_iterations': data.get('max_iterations', 100),
                'output_var': data.get('output_var', 'loop_results')
            },
        )

    except Exception as e:
        return _json_error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 并行节点
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/nodes/parallel', methods=['POST'])
def add_parallel_node(workflow_id):
    """添加并行节点"""
    try:
        data = request.json or {}
        return _create_node_response(
            workflow_id,
            node_type=AdvancedNodeType.PARALLEL,
            default_label='并行执行',
            config={
                'branches': data.get('branches', []),
                'wait_all': data.get('wait_all', True),
                'timeout': data.get('timeout', 300),
                'merge_results': data.get('merge_results', True),
                'output_var': data.get('output_var', 'parallel_results')
            },
        )

    except Exception as e:
        return _json_error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 重试节点
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/nodes/retry', methods=['POST'])
def add_retry_node(workflow_id):
    """添加重试节点"""
    try:
        data = request.json or {}
        return _create_node_response(
            workflow_id,
            node_type=AdvancedNodeType.RETRY,
            default_label='重试',
            config={
                'max_retries': data.get('max_retries', 3),
                'retry_delay': data.get('retry_delay', 1.0),
                'backoff_multiplier': data.get('backoff_multiplier', 2.0),
                'retry_on_errors': data.get('retry_on_errors', [])
            },
        )

    except Exception as e:
        return _json_error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 错误处理节点
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/nodes/try-catch', methods=['POST'])
def add_try_catch_node(workflow_id):
    """添加错误处理节点"""
    try:
        data = request.json or {}
        return _create_node_response(
            workflow_id,
            node_type=AdvancedNodeType.TRY_CATCH,
            default_label='错误处理',
            config={
                'try_node': data.get('try_node', ''),
                'catch_node': data.get('catch_node', ''),
                'finally_node': data.get('finally_node', ''),
                'error_var': data.get('error_var', 'error'),
                'output_var': data.get('output_var', 'try_catch_result')
            },
        )

    except Exception as e:
        return _json_error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 子工作流节点
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/nodes/subflow', methods=['POST'])
def add_subflow_node(workflow_id):
    """添加子工作流节点"""
    try:
        data = request.json or {}
        return _create_node_response(
            workflow_id,
            node_type=AdvancedNodeType.SUBFLOW,
            default_label='子工作流',
            config={
                'workflow_id': data.get('subworkflow_id', ''),
                'input_mapping': data.get('input_mapping', {}),
                'output_mapping': data.get('output_mapping', {}),
                'output_var': data.get('output_var', 'subflow_result')
            },
        )

    except Exception as e:
        return _json_error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 调试功能
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/debug/breakpoints', methods=['POST'])
def add_breakpoint(workflow_id):
    """添加断点"""
    try:
        data = request.json or {}
        node_id = data.get('node_id')
        condition = data.get('condition')

        executor = get_executor(workflow_id)
        executor.debugger.add_breakpoint(node_id, condition)

        return _json_success()

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/debug/breakpoints/<node_id>', methods=['DELETE'])
def remove_breakpoint(workflow_id, node_id):
    """移除断点"""
    try:
        executor = get_executor(workflow_id)
        executor.debugger.remove_breakpoint(node_id)

        return _json_success()

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/debug/pause', methods=['POST'])
def pause_execution(workflow_id):
    """暂停执行"""
    try:
        executor = get_executor(workflow_id)
        executor.debugger.pause()

        return _json_success()

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/debug/resume', methods=['POST'])
def resume_execution(workflow_id):
    """继续执行"""
    try:
        executor = get_executor(workflow_id)
        executor.debugger.resume()

        return _json_success()

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/debug/step', methods=['POST'])
def step_execution(workflow_id):
    """单步执行"""
    try:
        executor = get_executor(workflow_id)
        executor.debugger.step_over()

        return _json_success()

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/debug/watch', methods=['POST'])
def watch_variable(workflow_id):
    """监视变量"""
    try:
        data = request.json or {}
        var_name = data.get('variable')

        executor = get_executor(workflow_id)
        executor.debugger.watch_variable(var_name)

        return _json_success()

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/debug/stack', methods=['GET'])
def get_stack_trace(workflow_id):
    """获取调用栈"""
    try:
        executor = get_executor(workflow_id)
        stack = executor.debugger.get_stack_trace()

        return jsonify({'stack': stack})

    except Exception as e:
        return _json_error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 版本控制
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/versions', methods=['POST'])
def commit_version(workflow_id):
    """提交版本"""
    try:
        data = request.json or {}
        message = data.get('message', '更新工作流')
        user = data.get('user', 'system')

        executor = get_executor(workflow_id)
        version_number = executor.commit_version(message, user)

        return _json_success({'version': version_number})

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/versions', methods=['GET'])
def list_versions(workflow_id):
    """列出所有版本"""
    try:
        executor = get_executor(workflow_id)
        versions = executor.version_control.list_versions(workflow_id)

        return jsonify({
            'versions': [
                {
                    'version_id': v.version_id,
                    'version_number': v.version_number,
                    'created_at': v.created_at.isoformat(),
                    'created_by': v.created_by,
                    'commit_message': v.commit_message,
                    'tags': v.tags
                }
                for v in versions
            ]
        })

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/versions/<version_number>', methods=['GET'])
def get_version(workflow_id, version_number):
    """获取指定版本"""
    try:
        executor = get_executor(workflow_id)
        version = executor.version_control.get_version(workflow_id, version_number)

        if not version:
            return _json_error('版本不存在', 404)

        return jsonify({
            'version_id': version.version_id,
            'version_number': version.version_number,
            'workflow_data': version.workflow_data,
            'created_at': version.created_at.isoformat(),
            'created_by': version.created_by,
            'commit_message': version.commit_message,
            'tags': version.tags
        })

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/versions/<version_number>/rollback', methods=['POST'])
def rollback_version(workflow_id, version_number):
    """回滚到指定版本"""
    try:
        executor = get_executor(workflow_id)
        success = executor.rollback_version(version_number)

        if not success:
            return _json_error('回滚失败', 400)

        return _json_success()

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/versions/<version_number>/tag', methods=['POST'])
def tag_version(workflow_id, version_number):
    """给版本打标签"""
    try:
        data = request.json or {}
        tag = data.get('tag')

        if not tag:
            return _json_error('标签不能为空', 400)

        executor = get_executor(workflow_id)
        executor.version_control.tag_version(workflow_id, version_number, tag)

        return _json_success()

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/versions/compare', methods=['GET'])
def compare_versions(workflow_id):
    """比较两个版本"""
    try:
        version1 = request.args.get('version1')
        version2 = request.args.get('version2')

        if not version1 or not version2:
            return _json_error('需要提供两个版本号', 400)

        executor = get_executor(workflow_id)
        diff = executor.version_control.compare_versions(workflow_id, version1, version2)

        return jsonify(diff)

    except Exception as e:
        return _json_error(str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 定时触发
# ═══════════════════════════════════════════════════════════════════════════════

@workflow_advanced_bp.route('/workflows/<workflow_id>/schedule', methods=['POST'])
def create_schedule(workflow_id):
    """创建定时触发"""
    try:
        import uuid
        data = request.json or {}
        schedule_config = ScheduleConfig(
            schedule_type=data.get('schedule_type', 'cron'),
            cron_expression=data.get('cron_expression', ''),
            interval_seconds=data.get('interval_seconds', 0),
            start_time=data.get('start_time', ''),
            end_time=data.get('end_time', ''),
            enabled=data.get('enabled', True)
        )

        # 保存到数据库
        schedule_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        with get_db_connection(SCHEDULE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO schedules
                (schedule_id, workflow_id, schedule_type, cron_expression,
                 interval_seconds, start_time, end_time, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                schedule_id, workflow_id, schedule_config.schedule_type,
                schedule_config.cron_expression, schedule_config.interval_seconds,
                schedule_config.start_time, schedule_config.end_time,
                1 if schedule_config.enabled else 0, now, now
            ))

        # 启动定时任务
        if schedule_config.enabled:
            executor = get_executor(workflow_id)
            schedule_executor = ScheduleExecutor(schedule_config)
            schedule_executor.start(
                lambda wf_id, ctx: executor.execute(ctx.variables),
                workflow_id
            )
            _schedule_executors[schedule_id] = schedule_executor

        return _json_success({
            'schedule_id': schedule_id,
            'message': '定时任务已创建'
        })

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/schedule', methods=['DELETE'])
def delete_schedule(workflow_id):
    """删除定时触发"""
    try:
        # 查询该工作流的所有定时任务
        with get_db_connection(SCHEDULE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT schedule_id FROM schedules WHERE workflow_id = ?", (workflow_id,))
            schedule_ids = [row[0] for row in cursor.fetchall()]

            # 停止并删除定时任务
            for schedule_id in schedule_ids:
                if schedule_id in _schedule_executors:
                    _schedule_executors[schedule_id].stop()
                    del _schedule_executors[schedule_id]

            # 从数据库删除
            cursor.execute("DELETE FROM schedules WHERE workflow_id = ?", (workflow_id,))

        return _json_success({'deleted_count': len(schedule_ids)})

    except Exception as e:
        return _json_error(str(e))


@workflow_advanced_bp.route('/workflows/<workflow_id>/schedule', methods=['GET'])
def get_schedule(workflow_id):
    """获取定时任务信息"""
    try:
        with get_db_connection(SCHEDULE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedules WHERE workflow_id = ?", (workflow_id,))
            rows = cursor.fetchall()

        schedules = [_serialize_schedule_row(row) for row in rows]

        return jsonify({'schedules': schedules})

    except Exception as e:
        return _json_error(str(e))
