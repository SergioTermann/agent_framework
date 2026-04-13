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
        workflow = Workflow.from_dict({
            'name': data.get('name', '未命名工作流'),
            'description': data.get('description', ''),
            'nodes': data.get('nodes', []),
            'edges': data.get('edges', []),
            'variables': data.get('variables', {}),
        })
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
            'category': '控制',
            'description': '工作流的起点',
            'default_config': {
                'input_schema': 'user_query:string\nsession_id:string',
                'output_var': 'input'
            },
            'fields': [
                {'key': 'input_schema', 'label': '输入字段', 'type': 'textarea', 'placeholder': 'user_query:string\nsession_id:string'},
                {'key': 'output_var', 'label': '输出变量', 'type': 'text', 'placeholder': 'input'},
            ]
        },
        {
            'type': NodeType.END,
            'label': '结束',
            'icon': '⏹️',
            'color': '#ef4444',
            'category': '控制',
            'description': '工作流的终点',
            'default_config': {
                'response_template': '{{result}}',
                'output_key': 'final_answer'
            },
            'fields': [
                {'key': 'response_template', 'label': '响应模板', 'type': 'textarea', 'placeholder': '{{result}}'},
                {'key': 'output_key', 'label': '输出键名', 'type': 'text', 'placeholder': 'final_answer'},
            ]
        },
        {
            'type': NodeType.AGENT,
            'label': 'Agent',
            'icon': '🤖',
            'color': '#58a6ff',
            'category': '智能',
            'description': '调用 AI Agent 处理任务',
            'default_config': {
                'agent_type': 'general',
                'provider': 'openai',
                'model': 'auto',
                'temperature': 0.4,
                'top_p': 1,
                'max_tokens': 1200,
                'system_prompt': '',
                'prompt': '处理用户输入: {user_query}',
                'context_mode': 'shared',
                'memory_window': 6,
                'enable_stream': True,
                'output_var': 'result',
                'retry_count': 1,
                'timeout_ms': 30000
            },
            'fields': [
                {'key': 'agent_type', 'label': 'Agent 类型', 'type': 'select', 'group': '基础设置', 'options': [
                    {'value': 'general', 'label': '通用'},
                    {'value': 'analysis', 'label': '分析'},
                    {'value': 'planner', 'label': '规划'},
                    {'value': 'router', 'label': '路由'},
                ]},
                {'key': 'provider', 'label': 'LLM 提供方', 'type': 'select', 'group': '模型设置', 'options': [
                    {'value': 'openai', 'label': 'OpenAI'},
                    {'value': 'azure-openai', 'label': 'Azure OpenAI'},
                    {'value': 'anthropic', 'label': 'Anthropic'},
                    {'value': 'qwen', 'label': 'Qwen'},
                    {'value': 'deepseek', 'label': 'DeepSeek'},
                    {'value': 'custom', 'label': '自定义'},
                ]},
                {'key': 'model', 'label': '模型名称', 'type': 'text', 'group': '模型设置', 'placeholder': 'auto / gpt-4.1 / qwen3'},
                {'key': 'temperature', 'label': 'Temperature', 'type': 'number', 'group': '采样参数', 'placeholder': '0.4'},
                {'key': 'top_p', 'label': 'Top P', 'type': 'number', 'group': '采样参数', 'placeholder': '1'},
                {'key': 'max_tokens', 'label': '最大输出', 'type': 'number', 'group': '采样参数', 'placeholder': '1200'},
                {'key': 'system_prompt', 'label': '系统提示', 'type': 'textarea', 'group': '提示编排', 'placeholder': '补充角色设定、约束和风格'},
                {'key': 'prompt', 'label': '用户提示模板', 'type': 'textarea', 'group': '提示编排', 'placeholder': '处理用户输入: {user_query}'},
                {'key': 'context_mode', 'label': '上下文策略', 'type': 'select', 'group': '运行策略', 'options': [
                    {'value': 'shared', 'label': '共享上下文'},
                    {'value': 'isolated', 'label': '隔离上下文'},
                    {'value': 'memory_first', 'label': '记忆优先'},
                ]},
                {'key': 'memory_window', 'label': '上下文窗口轮数', 'type': 'number', 'group': '运行策略', 'placeholder': '6'},
                {'key': 'enable_stream', 'label': '流式输出', 'type': 'checkbox', 'group': '运行策略'},
                {'key': 'output_var', 'label': '输出变量', 'type': 'text', 'group': '输出结果', 'placeholder': 'result'},
                {'key': 'retry_count', 'label': '重试次数', 'type': 'number', 'group': '运行策略', 'placeholder': '1'},
                {'key': 'timeout_ms', 'label': '超时毫秒', 'type': 'number', 'group': '运行策略', 'placeholder': '30000'},
            ]
        },
        {
            'type': NodeType.LLM,
            'label': 'LLM',
            'icon': '🧠',
            'color': '#2563eb',
            'category': '智能',
            'description': '独立的大模型调用节点，支持完整模型参数配置',
            'default_config': {
                'provider': 'openai',
                'model': 'gpt-4.1-mini',
                'endpoint_id': '',
                'base_url': '',
                'api_key': '',
                'model_uid': '',
                'completion_mode': 'chat',
                'system_prompt': '你是工作流里的核心推理节点。',
                'prompt': '{user_query}',
                'temperature': 0.7,
                'top_p': 1,
                'max_tokens': 1500,
                'presence_penalty': 0,
                'frequency_penalty': 0,
                'context_mode': 'shared',
                'memory_window': 8,
                'enable_stream': True,
                'response_format': 'text',
                'json_schema': '',
                'stop': '',
                'vision_enabled': False,
                'output_var': 'llm_result'
            },
            'fields': [
                {'key': 'provider', 'label': '提供方', 'type': 'select', 'group': '模型设置', 'options': [
                    {'value': 'openai', 'label': 'OpenAI'},
                    {'value': 'azure-openai', 'label': 'Azure OpenAI'},
                    {'value': 'anthropic', 'label': 'Anthropic'},
                    {'value': 'qwen', 'label': 'Qwen'},
                    {'value': 'deepseek', 'label': 'DeepSeek'},
                    {'value': 'custom', 'label': '自定义'},
                ]},
                {'key': 'model', 'label': '模型名称', 'type': 'text', 'group': '模型设置', 'placeholder': 'gpt-4.1-mini'},
                {'key': 'endpoint_id', 'label': '部署端点 ID', 'type': 'text', 'group': '部署接入', 'placeholder': 'chat_xxx'},
                {'key': 'base_url', 'label': '端点 Base URL', 'type': 'text', 'group': '部署接入', 'placeholder': 'http://127.0.0.1:8001/v1'},
                {'key': 'model_uid', 'label': '模型 UID', 'type': 'text', 'group': '部署接入', 'placeholder': '可选'},
                {'key': 'api_key', 'label': '端点 API Key', 'type': 'text', 'group': '部署接入', 'placeholder': 'not-needed / sk-...'},
                {'key': 'completion_mode', 'label': '调用模式', 'type': 'select', 'group': '模型设置', 'options': [
                    {'value': 'chat', 'label': 'Chat'},
                    {'value': 'completion', 'label': 'Completion'},
                    {'value': 'reasoning', 'label': 'Reasoning'},
                ]},
                {'key': 'system_prompt', 'label': 'System Prompt', 'type': 'textarea', 'group': '提示编排', 'placeholder': '你是工作流里的核心推理节点。'},
                {'key': 'prompt', 'label': 'Prompt 模板', 'type': 'textarea', 'group': '提示编排', 'placeholder': '{user_query}'},
                {'key': 'temperature', 'label': 'Temperature', 'type': 'number', 'group': '采样参数', 'placeholder': '0.7'},
                {'key': 'top_p', 'label': 'Top P', 'type': 'number', 'group': '采样参数', 'placeholder': '1'},
                {'key': 'max_tokens', 'label': '最大输出', 'type': 'number', 'group': '采样参数', 'placeholder': '1500'},
                {'key': 'presence_penalty', 'label': 'Presence Penalty', 'type': 'number', 'group': '采样参数', 'placeholder': '0'},
                {'key': 'frequency_penalty', 'label': 'Frequency Penalty', 'type': 'number', 'group': '采样参数', 'placeholder': '0'},
                {'key': 'context_mode', 'label': '上下文策略', 'type': 'select', 'group': '上下文记忆', 'options': [
                    {'value': 'shared', 'label': '共享上下文'},
                    {'value': 'isolated', 'label': '隔离上下文'},
                    {'value': 'memory_first', 'label': '记忆优先'},
                ]},
                {'key': 'memory_window', 'label': '记忆窗口', 'type': 'number', 'group': '上下文记忆', 'placeholder': '8'},
                {'key': 'enable_stream', 'label': '流式输出', 'type': 'checkbox', 'group': '上下文记忆'},
                {'key': 'response_format', 'label': '输出格式', 'type': 'select', 'group': '输出控制', 'options': [
                    {'value': 'text', 'label': '文本'},
                    {'value': 'json', 'label': 'JSON'},
                    {'value': 'markdown', 'label': 'Markdown'},
                ]},
                {'key': 'json_schema', 'label': 'JSON Schema', 'type': 'textarea', 'group': '输出控制', 'placeholder': '{"type":"object","properties":{"answer":{"type":"string"}}}'},
                {'key': 'stop', 'label': '停止词', 'type': 'text', 'group': '输出控制', 'placeholder': '</final>'},
                {'key': 'vision_enabled', 'label': '多模态输入', 'type': 'checkbox', 'group': '输出控制'},
                {'key': 'output_var', 'label': '输出变量', 'type': 'text', 'group': '输出控制', 'placeholder': 'llm_result'},
            ]
        },
        {
            'type': NodeType.CONDITION,
            'label': '条件',
            'icon': '🔀',
            'color': '#fbbf24',
            'category': '控制',
            'description': '根据条件分支',
            'default_config': {
                'condition': '{score} > 0.8',
                'expression_hint': '支持用上下文变量拼接条件表达式'
            },
            'fields': [
                {'key': 'condition', 'label': '条件表达式', 'type': 'text', 'placeholder': '{score} > 0.8'},
                {'key': 'expression_hint', 'label': '表达式提示', 'type': 'text', 'placeholder': '支持 Python 风格表达式'},
            ]
        },
        {
            'type': NodeType.TRANSFORM,
            'label': '转换',
            'icon': '🔄',
            'color': '#06b6d4',
            'category': '数据',
            'description': '数据转换',
            'default_config': {
                'transform_type': 'template',
                'template': '{"summary":"{result}"}',
                'output_var': 'transformed'
            },
            'fields': [
                {'key': 'transform_type', 'label': '转换方式', 'type': 'select', 'options': [
                    {'value': 'template', 'label': '模板映射'},
                    {'value': 'json', 'label': 'JSON 拼装'},
                    {'value': 'text', 'label': '文本拼接'},
                ]},
                {'key': 'template', 'label': '转换模板', 'type': 'textarea', 'placeholder': '{"summary":"{result}"}'},
                {'key': 'output_var', 'label': '输出变量', 'type': 'text', 'placeholder': 'transformed'},
            ]
        },
        {
            'type': NodeType.API,
            'label': 'API',
            'icon': '🌐',
            'color': '#8b5cf6',
            'category': '集成',
            'description': '调用外部 API',
            'default_config': {
                'method': 'POST',
                'url': 'https://api.example.com/v1/query',
                'headers': '{"Authorization":"Bearer ..."}',
                'body': '{"query":"{user_query}"}',
                'output_var': 'api_result'
            },
            'fields': [
                {'key': 'method', 'label': '请求方法', 'type': 'select', 'options': [
                    {'value': 'GET', 'label': 'GET'},
                    {'value': 'POST', 'label': 'POST'},
                    {'value': 'PUT', 'label': 'PUT'},
                    {'value': 'DELETE', 'label': 'DELETE'},
                ]},
                {'key': 'url', 'label': '请求地址', 'type': 'text', 'placeholder': 'https://api.example.com/v1/query'},
                {'key': 'headers', 'label': '请求头', 'type': 'textarea', 'placeholder': '{"Authorization":"Bearer ..."}'},
                {'key': 'body', 'label': '请求体', 'type': 'textarea', 'placeholder': '{"query":"{user_query}"}'},
                {'key': 'output_var', 'label': '输出变量', 'type': 'text', 'placeholder': 'api_result'},
            ]
        },
        {
            'type': NodeType.LOOP,
            'label': '循环',
            'icon': '🔁',
            'color': '#0ea5e9',
            'category': '控制',
            'description': '批量处理列表数据',
            'default_config': {
                'loop_source': 'items',
                'item_var': 'item',
                'max_iterations': 20,
                'output_var': 'loop_result'
            },
            'fields': [
                {'key': 'loop_source', 'label': '循环来源', 'type': 'text', 'placeholder': 'items'},
                {'key': 'item_var', 'label': '迭代变量', 'type': 'text', 'placeholder': 'item'},
                {'key': 'max_iterations', 'label': '最大轮次', 'type': 'number', 'placeholder': '20'},
                {'key': 'output_var', 'label': '输出变量', 'type': 'text', 'placeholder': 'loop_result'},
            ]
        },
        {
            'type': NodeType.MERGE,
            'label': '合流',
            'icon': '🧩',
            'color': '#f97316',
            'category': '数据',
            'description': '汇总多条支路结果',
            'default_config': {
                'merge_mode': 'append',
                'source_vars': 'branch_a,branch_b',
                'output_var': 'merged'
            },
            'fields': [
                {'key': 'merge_mode', 'label': '合流方式', 'type': 'select', 'options': [
                    {'value': 'append', 'label': '顺序拼接'},
                    {'value': 'object', 'label': '对象合并'},
                    {'value': 'first_non_empty', 'label': '首个非空'},
                ]},
                {'key': 'source_vars', 'label': '来源变量', 'type': 'text', 'placeholder': 'branch_a,branch_b'},
                {'key': 'output_var', 'label': '输出变量', 'type': 'text', 'placeholder': 'merged'},
            ]
        },
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
            'id': 'rag-answer',
            'name': '知识问答链',
            'description': '输入整理 → Agent 检索问答 → 输出整形',
            'nodes': [
                {
                    'id': 'start',
                    'type': NodeType.START,
                    'label': '接收问题',
                    'position': {'x': 120, 'y': 180},
                    'config': {
                        'input_schema': 'user_query:string\nkb_scope:string',
                        'output_var': 'input'
                    }
                },
                {
                    'id': 'agent',
                    'type': NodeType.AGENT,
                    'label': '检索增强 Agent',
                    'position': {'x': 380, 'y': 180},
                    'config': {
                        'agent_type': 'analysis',
                        'model': 'auto',
                        'prompt': '结合知识范围 {kb_scope} 回答问题: {user_query}',
                        'output_var': 'answer'
                    }
                },
                {
                    'id': 'transform',
                    'type': NodeType.TRANSFORM,
                    'label': '整理输出',
                    'position': {'x': 640, 'y': 180},
                    'config': {
                        'transform_type': 'json',
                        'template': '{"answer":"{answer}","source":"workflow"}',
                        'output_var': 'result'
                    }
                },
                {
                    'id': 'end',
                    'type': NodeType.END,
                    'label': '返回结果',
                    'position': {'x': 900, 'y': 180},
                    'config': {
                        'response_template': '{{result}}',
                        'output_key': 'final_answer'
                    }
                }
            ],
            'edges': [
                {'source': 'start', 'target': 'agent'},
                {'source': 'agent', 'target': 'transform'},
                {'source': 'transform', 'target': 'end'}
            ]
        },
        {
            'id': 'llm-chat',
            'name': 'LLM 对话链',
            'description': '开始 → LLM → 结束，适合直接调模型参数',
            'nodes': [
                {
                    'id': 'start',
                    'type': NodeType.START,
                    'label': '接收输入',
                    'position': {'x': 120, 'y': 180},
                    'config': {
                        'input_schema': 'user_query:string\nstyle:string',
                        'output_var': 'input'
                    }
                },
                {
                    'id': 'llm',
                    'type': NodeType.LLM,
                    'label': '核心 LLM',
                    'position': {'x': 420, 'y': 180},
                    'config': {
                        'provider': 'openai',
                        'model': 'gpt-4.1-mini',
                        'completion_mode': 'chat',
                        'system_prompt': '你是一个严谨的业务助手。',
                        'prompt': '请根据用户问题 {user_query} 生成 {style} 风格的回答。',
                        'temperature': 0.7,
                        'top_p': 1,
                        'max_tokens': 1200,
                        'response_format': 'text',
                        'output_var': 'llm_result'
                    }
                },
                {
                    'id': 'end',
                    'type': NodeType.END,
                    'label': '返回结果',
                    'position': {'x': 760, 'y': 180},
                    'config': {
                        'response_template': '{llm_result_text}',
                        'output_key': 'final_answer'
                    }
                }
            ],
            'edges': [
                {'source': 'start', 'target': 'llm'},
                {'source': 'llm', 'target': 'end'}
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
        },
        {
            'id': 'triage-api',
            'name': '告警分流链',
            'description': '判定风险等级，再决定走 API 还是专家 Agent',
            'nodes': [
                {
                    'id': 'start',
                    'type': NodeType.START,
                    'label': '接收告警',
                    'position': {'x': 100, 'y': 220}
                },
                {
                    'id': 'condition',
                    'type': NodeType.CONDITION,
                    'label': '判断紧急度',
                    'position': {'x': 340, 'y': 220},
                    'config': {
                        'condition': '{severity} >= 3'
                    }
                },
                {
                    'id': 'api',
                    'type': NodeType.API,
                    'label': '同步外部工单',
                    'position': {'x': 620, 'y': 110},
                    'config': {
                        'method': 'POST',
                        'url': 'https://api.example.com/tickets',
                        'body': '{"alarm":"{alarm_id}","severity":"{severity}"}',
                        'output_var': 'ticket'
                    }
                },
                {
                    'id': 'agent',
                    'type': NodeType.AGENT,
                    'label': '专家分析',
                    'position': {'x': 620, 'y': 330},
                    'config': {
                        'agent_type': 'analysis',
                        'prompt': '分析这条中低优先级告警并给出处置建议: {alarm_id}',
                        'output_var': 'analysis'
                    }
                },
                {
                    'id': 'merge',
                    'type': NodeType.MERGE,
                    'label': '收拢结果',
                    'position': {'x': 900, 'y': 220},
                    'config': {
                        'merge_mode': 'object',
                        'source_vars': 'ticket,analysis',
                        'output_var': 'result'
                    }
                },
                {
                    'id': 'end',
                    'type': NodeType.END,
                    'label': '输出结论',
                    'position': {'x': 1140, 'y': 220}
                }
            ],
            'edges': [
                {'source': 'start', 'target': 'condition'},
                {'source': 'condition', 'target': 'api', 'label': 'true', 'condition': '高优先级'},
                {'source': 'condition', 'target': 'agent', 'label': 'false', 'condition': '常规优先级'},
                {'source': 'api', 'target': 'merge'},
                {'source': 'agent', 'target': 'merge'},
                {'source': 'merge', 'target': 'end'}
            ]
        },
        {
            'id': 'agent-review-loop',
            'name': 'Agent 复核闭环',
            'description': '起草、复核、条件判断、回写修订的完整闭环',
            'nodes': [
                {
                    'id': 'start',
                    'type': NodeType.START,
                    'label': '接收任务',
                    'position': {'x': 100, 'y': 220},
                    'config': {
                        'input_schema': 'user_query:string\nquality_bar:string',
                        'output_var': 'input'
                    }
                },
                {
                    'id': 'draft',
                    'type': NodeType.LLM,
                    'label': '起草 LLM',
                    'position': {'x': 360, 'y': 220},
                    'config': {
                        'provider': 'openai',
                        'model': 'gpt-4.1-mini',
                        'prompt': '根据用户问题生成第一版回答：{user_query}',
                        'output_var': 'draft_answer'
                    }
                },
                {
                    'id': 'review',
                    'type': NodeType.AGENT,
                    'label': '复核 Agent',
                    'position': {'x': 640, 'y': 220},
                    'config': {
                        'agent_type': 'analysis',
                        'prompt': '按照质量门槛 {quality_bar} 评审：{draft_answer_text}',
                        'output_var': 'review_result'
                    }
                },
                {
                    'id': 'judge',
                    'type': NodeType.CONDITION,
                    'label': '是否通过',
                    'position': {'x': 920, 'y': 220},
                    'config': {
                        'condition': '"通过" in review_result'
                    }
                },
                {
                    'id': 'rewrite',
                    'type': NodeType.TRANSFORM,
                    'label': '修订指令',
                    'position': {'x': 1180, 'y': 120},
                    'config': {
                        'transform_type': 'template',
                        'template': '请根据复核意见重写回答：{review_result}',
                        'output_var': 'rewrite_prompt'
                    }
                },
                {
                    'id': 'end_rewrite',
                    'type': NodeType.END,
                    'label': '返回修订版',
                    'position': {'x': 1450, 'y': 120},
                    'config': {
                        'response_template': '{rewrite_prompt}',
                        'output_key': 'final_answer'
                    }
                },
                {
                    'id': 'end_pass',
                    'type': NodeType.END,
                    'label': '直接返回',
                    'position': {'x': 1180, 'y': 330},
                    'config': {
                        'response_template': '{draft_answer_text}',
                        'output_key': 'final_answer'
                    }
                }
            ],
            'edges': [
                {'source': 'start', 'target': 'draft'},
                {'source': 'draft', 'target': 'review'},
                {'source': 'review', 'target': 'judge'},
                {'source': 'judge', 'target': 'rewrite', 'label': 'false'},
                {'source': 'judge', 'target': 'end_pass', 'label': 'true'},
                {'source': 'rewrite', 'target': 'end_rewrite'}
            ],
            'variables': {
                'quality_bar': {'value': '结论准确、结构清晰、风险明确', 'type': 'string', 'description': '回答质量门槛'}
            }
        },
        {
            'id': 'multi-stage-rag',
            'name': '多阶段检索决策链',
            'description': '问题判断、检索增强、快速回答和格式化输出组成的复杂问答链',
            'nodes': [
                {
                    'id': 'start',
                    'type': NodeType.START,
                    'label': '接收问题',
                    'position': {'x': 100, 'y': 210},
                    'config': {
                        'input_schema': 'user_query:string\nkb_scope:string\nanswer_style:string',
                        'output_var': 'input'
                    }
                },
                {
                    'id': 'route',
                    'type': NodeType.CONDITION,
                    'label': '是否复杂问题',
                    'position': {'x': 330, 'y': 210},
                    'config': {
                        'condition': 'len(user_query) > 20'
                    }
                },
                {
                    'id': 'rag_agent',
                    'type': NodeType.AGENT,
                    'label': '检索 Agent',
                    'position': {'x': 610, 'y': 110},
                    'config': {
                        'agent_type': 'router',
                        'prompt': '结合知识范围 {kb_scope} 检索并汇总：{user_query}',
                        'output_var': 'retrieved_answer'
                    }
                },
                {
                    'id': 'quick_llm',
                    'type': NodeType.LLM,
                    'label': '快速回答',
                    'position': {'x': 610, 'y': 320},
                    'config': {
                        'provider': 'openai',
                        'model': 'gpt-4.1-mini',
                        'prompt': '直接简洁回答：{user_query}',
                        'output_var': 'retrieved_answer'
                    }
                },
                {
                    'id': 'formatter',
                    'type': NodeType.TRANSFORM,
                    'label': '结果格式化',
                    'position': {'x': 920, 'y': 210},
                    'config': {
                        'transform_type': 'json',
                        'template': '{"answer":"{retrieved_answer}","style":"{answer_style}","source":"workflow"}',
                        'output_var': 'formatted_result'
                    }
                },
                {
                    'id': 'end',
                    'type': NodeType.END,
                    'label': '返回结果',
                    'position': {'x': 1210, 'y': 210},
                    'config': {
                        'response_template': '{formatted_result}',
                        'output_key': 'final_answer'
                    }
                }
            ],
            'edges': [
                {'source': 'start', 'target': 'route'},
                {'source': 'route', 'target': 'rag_agent', 'label': 'true'},
                {'source': 'route', 'target': 'quick_llm', 'label': 'false'},
                {'source': 'rag_agent', 'target': 'formatter'},
                {'source': 'quick_llm', 'target': 'formatter'},
                {'source': 'formatter', 'target': 'end'}
            ],
            'variables': {
                'answer_style': {'value': '结构化摘要', 'type': 'string', 'description': '统一输出风格'}
            }
        }
    ]
    return jsonify({'templates': templates})
