"""
多 Agent 协作 API
================

提供多 Agent 协作的 HTTP API 接口。
"""

from flask import Blueprint, request, jsonify
from agent_framework.platform.multi_agent import AgentCoordinator
from agent_framework.platform.multi_agent_impl import create_default_agents
from agent_framework.agent.llm import OpenAICompatibleProvider
from agent_framework.core.config import get_config

multi_agent_bp = Blueprint('multi_agent', __name__, url_prefix='/api/multi-agent')

# 全局协调器实例
_coordinator = None


def get_coordinator():
    """获取协调器实例"""
    global _coordinator
    if _coordinator is None:
        cfg = get_config()
        llm_provider = OpenAICompatibleProvider(
            api_key=cfg.llm.api_key,
            model=cfg.llm.model,
            base_url=cfg.llm.base_url,
            timeout=120
        )

        _coordinator = AgentCoordinator(llm_provider)

        # 注册默认 Agent
        agents = create_default_agents(llm_provider)
        for agent in agents:
            _coordinator.register_agent(agent)

    return _coordinator


@multi_agent_bp.route('/agents', methods=['GET'])
def list_agents():
    """获取所有 Agent 列表"""
    coordinator = get_coordinator()
    agents = [agent.to_dict() for agent in coordinator.agents.values()]
    return jsonify({'agents': agents})


@multi_agent_bp.route('/status', methods=['GET'])
def get_status():
    """获取协调器状态"""
    coordinator = get_coordinator()
    status = coordinator.get_status()
    return jsonify(status)


@multi_agent_bp.route('/execute', methods=['POST'])
def execute_task():
    """执行协作任务"""
    data = request.json
    query = data.get('query', '')

    if not query:
        return jsonify({'error': '查询不能为空'}), 400

    coordinator = get_coordinator()

    try:
        result = coordinator.execute_collaborative_task(query)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@multi_agent_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """获取所有任务"""
    coordinator = get_coordinator()
    tasks = [task.to_dict() for task in coordinator.tasks.values()]
    return jsonify({'tasks': tasks})


@multi_agent_bp.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """获取指定任务"""
    coordinator = get_coordinator()
    task = coordinator.tasks.get(task_id)

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    return jsonify(task.to_dict())


@multi_agent_bp.route('/messages', methods=['GET'])
def list_messages():
    """获取消息历史"""
    coordinator = get_coordinator()
    messages = [msg.to_dict() for msg in coordinator.message_bus]
    return jsonify({'messages': messages})
