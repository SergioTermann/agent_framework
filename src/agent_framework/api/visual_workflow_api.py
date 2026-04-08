"""
可视化工作流编排 API
==================

提供工作流的 CRUD 和执行接口。
"""

from flask import Blueprint, request, jsonify
from agent_framework.workflow.visual_workflow import (
    Workflow, WorkflowNode, WorkflowEdge, WorkflowExecutor,
    save_workflow, get_workflow, list_workflows, delete_workflow,
    NodeType
)

visual_workflow_bp = Blueprint('visual_workflow', __name__, url_prefix='/api/visual-workflow')


@visual_workflow_bp.route('/workflows', methods=['GET'])
def get_workflows():
    """获取所有工作流"""
    workflows = list_workflows()
    return jsonify({
        'workflows': [w.to_dict() for w in workflows]
    })


@visual_workflow_bp.route('/workflows', methods=['POST'])
def create_workflow():
    """创建工作流"""
    try:
        data = request.json
        workflow = Workflow(
            name=data.get('name', '未命名工作流'),
            description=data.get('description', '')
        )
        save_workflow(workflow)
        return jsonify(workflow.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@visual_workflow_bp.route('/workflows/<workflow_id>', methods=['GET'])
def get_workflow_detail(workflow_id):
    """获取工作流详情"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        return jsonify({'error': '工作流不存在'}), 404
    return jsonify(workflow.to_dict())


@visual_workflow_bp.route('/workflows/<workflow_id>', methods=['PUT'])
def update_workflow(workflow_id):
    """更新工作流"""
    try:
        workflow = get_workflow(workflow_id)
        if not workflow:
            return jsonify({'error': '工作流不存在'}), 404

        data = request.json
        workflow.name = data.get('name', workflow.name)
        workflow.description = data.get('description', workflow.description)

        # 更新节点
        if 'nodes' in data:
            workflow.nodes = [WorkflowNode.from_dict(n) for n in data['nodes']]

        # 更新连接
        if 'edges' in data:
            workflow.edges = [WorkflowEdge.from_dict(e) for e in data['edges']]

        # 更新变量
        if 'variables' in data:
            workflow.variables = data['variables']

        save_workflow(workflow)
        return jsonify(workflow.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@visual_workflow_bp.route('/workflows/<workflow_id>', methods=['DELETE'])
def delete_workflow_api(workflow_id):
    """删除工作流"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        return jsonify({'error': '工作流不存在'}), 404

    delete_workflow(workflow_id)
    return jsonify({'success': True})


@visual_workflow_bp.route('/workflows/<workflow_id>/execute', methods=['POST'])
def execute_workflow(workflow_id):
    """执行工作流"""
    try:
        workflow = get_workflow(workflow_id)
        if not workflow:
            return jsonify({'error': '工作流不存在'}), 404

        data = request.json
        input_data = data.get('input', {})

        executor = WorkflowExecutor(workflow)
        result = executor.execute(input_data)

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@visual_workflow_bp.route('/workflows/<workflow_id>/validate', methods=['POST'])
def validate_workflow(workflow_id):
    """验证工作流"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        return jsonify({'error': '工作流不存在'}), 404

    valid, message = workflow.validate()
    return jsonify({
        'valid': valid,
        'message': message
    })


@visual_workflow_bp.route('/node-types', methods=['GET'])
def get_node_types():
    """获取节点类型列表"""
    node_types = [
        {
            'type': NodeType.START,
            'label': '开始',
            'icon': '▶️',
            'color': '#34d399',
            'description': '工作流的起点'
        },
        {
            'type': NodeType.END,
            'label': '结束',
            'icon': '⏹️',
            'color': '#ef4444',
            'description': '工作流的终点'
        },
        {
            'type': NodeType.AGENT,
            'label': 'Agent',
            'icon': '🤖',
            'color': '#58a6ff',
            'description': '调用 AI Agent 处理任务'
        },
        {
            'type': NodeType.CONDITION,
            'label': '条件',
            'icon': '🔀',
            'color': '#fbbf24',
            'description': '根据条件分支'
        },
        {
            'type': NodeType.TRANSFORM,
            'label': '转换',
            'icon': '🔄',
            'color': '#06b6d4',
            'description': '数据转换'
        },
        {
            'type': NodeType.API,
            'label': 'API',
            'icon': '🌐',
            'color': '#8b5cf6',
            'description': '调用外部 API'
        }
    ]
    return jsonify({'node_types': node_types})


@visual_workflow_bp.route('/templates', methods=['GET'])
def get_templates():
    """获取工作流模板"""
    templates = [
        {
            'id': 'simple',
            'name': '简单流程',
            'description': '开始 → Agent → 结束',
            'nodes': [
                {
                    'id': 'start',
                    'type': NodeType.START,
                    'label': '开始',
                    'position': {'x': 100, 'y': 100}
                },
                {
                    'id': 'agent',
                    'type': NodeType.AGENT,
                    'label': 'AI 处理',
                    'position': {'x': 300, 'y': 100},
                    'config': {
                        'agent_type': 'general',
                        'prompt': '处理用户输入: {input}',
                        'output_var': 'result'
                    }
                },
                {
                    'id': 'end',
                    'type': NodeType.END,
                    'label': '结束',
                    'position': {'x': 500, 'y': 100}
                }
            ],
            'edges': [
                {'source': 'start', 'target': 'agent'},
                {'source': 'agent', 'target': 'end'}
            ]
        },
        {
            'id': 'conditional',
            'name': '条件分支',
            'description': '根据条件执行不同的分支',
            'nodes': [
                {
                    'id': 'start',
                    'type': NodeType.START,
                    'label': '开始',
                    'position': {'x': 100, 'y': 200}
                },
                {
                    'id': 'condition',
                    'type': NodeType.CONDITION,
                    'label': '判断条件',
                    'position': {'x': 300, 'y': 200},
                    'config': {
                        'condition': '{value} > 10'
                    }
                },
                {
                    'id': 'agent1',
                    'type': NodeType.AGENT,
                    'label': '分支 A',
                    'position': {'x': 500, 'y': 100},
                    'config': {
                        'agent_type': 'general',
                        'prompt': '处理大于10的情况',
                        'output_var': 'result'
                    }
                },
                {
                    'id': 'agent2',
                    'type': NodeType.AGENT,
                    'label': '分支 B',
                    'position': {'x': 500, 'y': 300},
                    'config': {
                        'agent_type': 'general',
                        'prompt': '处理小于等于10的情况',
                        'output_var': 'result'
                    }
                },
                {
                    'id': 'end',
                    'type': NodeType.END,
                    'label': '结束',
                    'position': {'x': 700, 'y': 200}
                }
            ],
            'edges': [
                {'source': 'start', 'target': 'condition'},
                {'source': 'condition', 'target': 'agent1', 'label': 'true'},
                {'source': 'condition', 'target': 'agent2', 'label': 'false'},
                {'source': 'agent1', 'target': 'end'},
                {'source': 'agent2', 'target': 'end'}
            ]
        }
    ]
    return jsonify({'templates': templates})
