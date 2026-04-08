"""
因果推理链 API
分析事件之间的因果关系，构建推理链条
"""

from flask import Blueprint, request, jsonify
from agent_framework.agent import AgentBuilder
from agent_framework.agent.thread import latest_assistant_message
from agent_framework.causal.causal_tree_demos import get_demo_by_id, get_demo_list
from agent_framework.core.config import get_config

causal_chain_bp = Blueprint('causal_chain', __name__, url_prefix='/api/causal-chain')


def _build_causal_agent() -> AgentBuilder:
    cfg = get_config()
    return AgentBuilder().with_openai(
        api_key=cfg.llm.api_key,
        model=cfg.llm.model,
        base_url=cfg.llm.base_url,
        timeout=cfg.llm.timeout,
    )


@causal_chain_bp.route('/demos', methods=['GET'])
def get_demos():
    """获取所有演示案例列表"""
    try:
        demos = get_demo_list()
        return jsonify({'demos': demos})
    except Exception as e:
        print(f"Error getting demos: {e}")
        return jsonify({'error': str(e)}), 500


@causal_chain_bp.route('/demos/<demo_id>', methods=['GET'])
def get_demo(demo_id):
    """获取指定演示案例的完整数据"""
    try:
        demo = get_demo_by_id(demo_id)
        if demo:
            return jsonify(demo)
        else:
            return jsonify({'error': '演示案例不存在'}), 404
    except Exception as e:
        print(f"Error getting demo: {e}")
        return jsonify({'error': str(e)}), 500


@causal_chain_bp.route('/analyze', methods=['POST'])
def analyze_causal_chain():
    """分析因果推理链"""
    data = request.json
    cause = data.get('cause', '').strip()
    effect = data.get('effect', '').strip()
    context = data.get('context', '').strip()

    if not cause or not effect:
        return jsonify({'error': '起始事件和目标事件不能为空'}), 400

    try:
        # 构建提示词
        prompt = f"""请分析从"{cause}"到"{effect}"的因果推理链。

任务要求：
1. 识别从起始事件到目标事件之间的中间步骤
2. 每个步骤都要有明确的因果关系
3. 评估每个因果关系的置信度（0-1之间）
4. 按照时间或逻辑顺序排列

"""

        if context:
            prompt += f"\n背景信息：{context}\n"

        prompt += """
请以树形JSON格式返回结果，格式如下：
{
    "tree": {
        "id": "root",
        "content": "起始事件",
        "type": "cause",
        "confidence": 1.0,
        "children": [
            {
                "id": "node1",
                "content": "中间事件1",
                "type": "effect",
                "confidence": 0.8,
                "relation": "直接导致",
                "children": [
                    {
                        "id": "node2",
                        "content": "子事件",
                        "type": "effect",
                        "confidence": 0.7,
                        "relation": "间接影响",
                        "children": []
                    }
                ]
            }
        ]
    }
}

注意：
- 每个节点必须有唯一的id
- type 可以是 "cause"（原因）或 "effect"（结果）
- confidence 是 0-1 之间的数值，表示该因果关系的可信度
- relation 描述与父节点的关系类型（如"直接导致"、"间接影响"、"促进"、"抑制"等）
- children 数组包含子节点，可以为空
- 树的深度应该在 2-4 层之间
- 每个节点最多有 3 个子节点
"""

        # 使用 Agent 进行推理
        builder = _build_causal_agent()
        builder = builder.with_name("因果推理分析师")
        builder = builder.with_role("专业的因果关系分析专家")

        agent = builder.build()
        thread = agent.launch(prompt)

        # 获取最终响应
        response = latest_assistant_message(thread)

        # 解析响应
        import json
        import re

        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            result = json.loads(json_match.group())
            return jsonify(result)
        else:
            # 如果没有找到 JSON，生成默认的树形结构
            tree = {
                "id": "root",
                "content": cause,
                "type": "cause",
                "confidence": 1.0,
                "children": [
                    {
                        "id": "intermediate1",
                        "content": "直接影响",
                        "type": "effect",
                        "confidence": 0.8,
                        "children": [
                            {
                                "id": "final1",
                                "content": effect,
                                "type": "effect",
                                "confidence": 0.7,
                                "children": []
                            }
                        ]
                    },
                    {
                        "id": "intermediate2",
                        "content": "间接影响",
                        "type": "effect",
                        "confidence": 0.6,
                        "children": [
                            {
                                "id": "final2",
                                "content": "相关后果",
                                "type": "effect",
                                "confidence": 0.5,
                                "children": []
                            }
                        ]
                    }
                ]
            }
            return jsonify({"tree": tree})

    except Exception as e:
        print(f"Error analyzing causal chain: {e}")
        return jsonify({'error': str(e)}), 500


@causal_chain_bp.route('/expand-node', methods=['POST'])
def expand_node():
    """展开树形节点，生成子节点"""
    data = request.json
    node_content = data.get('content', '').strip()
    node_type = data.get('type', 'effect')
    context = data.get('context', '').strip()

    if not node_content:
        return jsonify({'error': '节点内容不能为空'}), 400

    try:
        prompt = f"""基于事件"{node_content}"，请生成2-3个可能的后续事件或影响。

任务要求：
1. 生成的事件应该与原事件有直接的因果关系
2. 每个事件都要有置信度评估
3. 事件应该具有逻辑性和现实性

"""

        if context:
            prompt += f"\n背景信息：{context}\n"

        prompt += """
请以JSON格式返回结果：
{
    "children": [
        {
            "id": "unique_id_1",
            "content": "后续事件1",
            "type": "effect",
            "confidence": 0.8,
            "children": []
        },
        {
            "id": "unique_id_2",
            "content": "后续事件2",
            "type": "effect",
            "confidence": 0.7,
            "children": []
        }
    ]
}
"""

        builder = _build_causal_agent()
        builder = builder.with_name("节点展开分析师")
        builder = builder.with_role("因果关系扩展专家")

        agent = builder.build()
        thread = agent.launch(prompt)

        # 获取最终响应
        response = latest_assistant_message(thread)

        # 解析响应
        import json
        import re
        import uuid

        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            result = json.loads(json_match.group())
            # 确保每个子节点都有唯一ID
            for child in result.get('children', []):
                if 'id' not in child:
                    child['id'] = str(uuid.uuid4())[:8]
            return jsonify(result)
        else:
            # 生成默认的子节点
            children = [
                {
                    "id": str(uuid.uuid4())[:8],
                    "content": f"基于'{node_content}'的直接后果",
                    "type": "effect",
                    "confidence": 0.7,
                    "children": []
                },
                {
                    "id": str(uuid.uuid4())[:8],
                    "content": f"'{node_content}'的间接影响",
                    "type": "effect",
                    "confidence": 0.6,
                    "children": []
                }
            ]
            return jsonify({"children": children})

    except Exception as e:
        print(f"Error expanding node: {e}")
        return jsonify({'error': str(e)}), 500


def validate_causal_link():
    """验证两个事件之间的因果关系"""
    data = request.json
    event1 = data.get('event1', '').strip()
    event2 = data.get('event2', '').strip()

    if not event1 or not event2:
        return jsonify({'error': '两个事件都不能为空'}), 400

    try:
        prompt = f"""请评估以下两个事件之间是否存在因果关系：

事件1（可能的原因）：{event1}
事件2（可能的结果）：{event2}

请分析：
1. 是否存在因果关系（是/否）
2. 因果关系的强度（0-1之间）
3. 简要说明理由

以JSON格式返回：
{{
    "has_causal_link": true/false,
    "strength": 0.8,
    "reasoning": "理由说明"
}}
"""

        builder = _build_causal_agent()
        builder = builder.with_name("因果关系验证器")
        builder = builder.with_role("因果关系评估专家")

        agent = builder.build()
        thread = agent.launch(prompt)

        # 获取最终响应
        response = latest_assistant_message(thread)

        # 解析响应
        import json
        import re

        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            result = json.loads(json_match.group())
            return jsonify(result)
        else:
            return jsonify({
                "has_causal_link": True,
                "strength": 0.5,
                "reasoning": "需要更多信息来准确评估"
            })

    except Exception as e:
        print(f"Error validating causal link: {e}")
        return jsonify({'error': str(e)}), 500
