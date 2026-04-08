"""
Prompt 管理 API
"""

from flask import Blueprint, request, jsonify
from agent_framework.platform.prompt_manager import PromptManager
from dataclasses import asdict

prompt_bp = Blueprint('prompt', __name__, url_prefix='/api/prompts')
manager = PromptManager()


@prompt_bp.route('/', methods=['GET'])
def list_prompts():
    """列出所有 Prompt"""
    category = request.args.get('category')
    tags = request.args.getlist('tags')
    search = request.args.get('search')

    prompts = manager.list_prompts(
        category=category,
        tags=tags if tags else None,
        search=search,
    )

    return jsonify({
        "prompts": [asdict(p) for p in prompts],
        "total": len(prompts),
    })


@prompt_bp.route('/', methods=['POST'])
def create_prompt():
    """创建新 Prompt"""
    data = request.json

    prompt = manager.create_prompt(
        name=data['name'],
        content=data['content'],
        description=data.get('description', ''),
        category=data.get('category', 'general'),
        tags=data.get('tags', []),
    )

    return jsonify(asdict(prompt)), 201


@prompt_bp.route('/<prompt_id>', methods=['GET'])
def get_prompt(prompt_id):
    """获取 Prompt 详情"""
    prompt = manager.get_prompt(prompt_id)
    if not prompt:
        return jsonify({"error": "Prompt not found"}), 404

    return jsonify(asdict(prompt))


@prompt_bp.route('/<prompt_id>', methods=['PUT'])
def update_prompt(prompt_id):
    """更新 Prompt"""
    data = request.json

    prompt = manager.update_prompt(
        prompt_id=prompt_id,
        name=data.get('name'),
        content=data.get('content'),
        description=data.get('description'),
        category=data.get('category'),
        tags=data.get('tags'),
    )

    if not prompt:
        return jsonify({"error": "Prompt not found"}), 404

    return jsonify(asdict(prompt))


@prompt_bp.route('/<prompt_id>', methods=['DELETE'])
def delete_prompt(prompt_id):
    """删除 Prompt"""
    success = manager.delete_prompt(prompt_id)
    if not success:
        return jsonify({"error": "Prompt not found"}), 404

    return jsonify({"message": "Prompt deleted"}), 200


@prompt_bp.route('/<prompt_id>/versions', methods=['POST'])
def create_version(prompt_id):
    """创建新版本"""
    data = request.json
    changes = data.get('changes', '')

    new_prompt = manager.create_version(prompt_id, changes)
    if not new_prompt:
        return jsonify({"error": "Prompt not found"}), 404

    return jsonify(asdict(new_prompt)), 201


@prompt_bp.route('/<prompt_id>/render', methods=['POST'])
def render_prompt(prompt_id):
    """渲染 Prompt"""
    data = request.json
    variables = data.get('variables', {})

    try:
        rendered = manager.render_prompt(prompt_id, variables)
        return jsonify({"rendered": rendered})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@prompt_bp.route('/<prompt_id>/tests', methods=['GET'])
def get_tests(prompt_id):
    """获取测试记录"""
    tests = manager.get_tests(prompt_id)
    return jsonify({
        "tests": [asdict(t) for t in tests],
        "total": len(tests),
    })


@prompt_bp.route('/<prompt_id>/tests', methods=['POST'])
def create_test(prompt_id):
    """创建测试记录"""
    data = request.json

    test = manager.create_test(
        prompt_id=prompt_id,
        test_name=data['test_name'],
        variables=data['variables'],
        result=data['result'],
        rating=data.get('rating'),
        notes=data.get('notes', ''),
    )

    return jsonify(asdict(test)), 201


@prompt_bp.route('/ab-tests', methods=['POST'])
def create_ab_test():
    """创建 A/B 测试"""
    data = request.json

    ab_test_id = manager.create_ab_test(
        name=data['name'],
        prompt_a_id=data['prompt_a_id'],
        prompt_b_id=data['prompt_b_id'],
    )

    return jsonify({"ab_test_id": ab_test_id}), 201


@prompt_bp.route('/ab-tests/<ab_test_id>', methods=['GET'])
def get_ab_test_results(ab_test_id):
    """获取 A/B 测试结果"""
    results = manager.get_ab_test_results(ab_test_id)
    if not results:
        return jsonify({"error": "A/B test not found"}), 404

    return jsonify(results)


@prompt_bp.route('/categories', methods=['GET'])
def get_categories():
    """获取所有分类"""
    return jsonify({
        "categories": [
            {"value": "general", "label": "通用"},
            {"value": "code", "label": "代码"},
            {"value": "creative", "label": "创意"},
            {"value": "analysis", "label": "分析"},
            {"value": "translation", "label": "翻译"},
            {"value": "summarization", "label": "摘要"},
        ]
    })
