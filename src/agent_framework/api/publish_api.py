"""
应用发布 API
"""

from flask import Blueprint, request, jsonify
from agent_framework.platform.app_publisher import AppPublisher
from dataclasses import asdict
import time

publish_bp = Blueprint('publish', __name__, url_prefix='/api/publish')
publisher = AppPublisher()


@publish_bp.route('/apps/<app_id>', methods=['POST'])
def publish_app(app_id):
    """发布应用"""
    data = request.json

    published_app = publisher.publish_app(
        app_id=app_id,
        version_id=data.get('version_id', 'latest'),
        allowed_origins=data.get('allowed_origins', ['*']),
        rate_limit=data.get('rate_limit', 100),
        expires_at=data.get('expires_at'),
    )

    return jsonify(asdict(published_app)), 201


@publish_bp.route('/apps/<publish_id>', methods=['GET'])
def get_published_app(publish_id):
    """获取已发布应用"""
    published_app = publisher.get_published_app(publish_id)
    if not published_app:
        return jsonify({"error": "Published app not found"}), 404

    return jsonify(asdict(published_app))


@publish_bp.route('/apps/<publish_id>/status', methods=['PUT'])
def update_status(publish_id):
    """更新发布状态"""
    data = request.json
    status = data.get('status')

    if status not in ['active', 'paused', 'revoked']:
        return jsonify({"error": "Invalid status"}), 400

    success = publisher.update_status(publish_id, status)
    if not success:
        return jsonify({"error": "Published app not found"}), 404

    return jsonify({"message": "Status updated"})


@publish_bp.route('/apps/<publish_id>/embed', methods=['POST'])
def generate_embed_code(publish_id):
    """生成嵌入代码"""
    data = request.json
    embed_type = data.get('embed_type', 'iframe')
    config = data.get('config', {})

    try:
        code = publisher.generate_embed_code(publish_id, embed_type, config)
        return jsonify({"code": code, "embed_type": embed_type})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@publish_bp.route('/apps/<publish_id>/stats', methods=['GET'])
def get_api_stats(publish_id):
    """获取 API 统计"""
    time_range = request.args.get('time_range', '24h')

    stats = publisher.get_api_stats(publish_id, time_range)
    return jsonify(stats)


@publish_bp.route('/apps', methods=['GET'])
def list_published_apps():
    """列出已发布应用"""
    app_id = request.args.get('app_id')

    apps = publisher.list_published_apps(app_id)
    return jsonify({
        "apps": [asdict(app) for app in apps],
        "total": len(apps),
    })


@publish_bp.route('/apps/<publish_id>/invoke', methods=['POST'])
def invoke_app(publish_id):
    """调用已发布的应用"""
    start_time = time.time()

    # 验证 API Key
    api_key = request.headers.get('X-API-Key') or request.json.get('api_key')
    if not api_key:
        return jsonify({"error": "API key required"}), 401

    published_app = publisher.verify_api_key(api_key)
    if not published_app or published_app.publish_id != publish_id:
        return jsonify({"error": "Invalid API key"}), 401

    # 检查 CORS
    origin = request.headers.get('Origin')
    if origin and '*' not in published_app.allowed_origins:
        if origin not in published_app.allowed_origins:
            return jsonify({"error": "Origin not allowed"}), 403

    # 增加请求计数
    publisher.increment_request_count(publish_id)

    # 执行应用逻辑（这里需要集成实际的应用执行逻辑）
    data = request.json
    user_input = data.get('input', '')

    try:
        # 实际执行应用
        from agent_framework.platform.application import ApplicationStorage
        from agent_framework.agent import AgentBuilder
        from agent_framework.agent.llm import get_llm_client

        # 获取应用配置
        app_storage = ApplicationStorage()
        app = app_storage.get_application(published_app.app_id)

        if not app:
            return jsonify({"error": "Application not found"}), 404

        # 根据应用类型执行
        if app.type.value == "chatbot":
            # 聊天机器人应用
            config = app.config
            model = config.get('model', 'gpt-4o')
            temperature = config.get('temperature', 0.7)
            system_prompt = config.get('system_prompt', '你是一个友好的助手。')

            llm_client = get_llm_client()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]

            response = llm_client.chat(messages, model=model, temperature=temperature)
            result = {
                "output": response.content if hasattr(response, "content") else response,
                "status": "success",
                "app_type": "chatbot"
            }

        elif app.type.value == "agent":
            # Agent 应用
            config = app.config
            agent_builder = AgentBuilder()
            agent = agent_builder.build_agent(config)

            response = agent.run(user_input)
            result = {
                "output": response,
                "status": "success",
                "app_type": "agent"
            }

        elif app.type.value == "workflow":
            # 工作流应用
            from agent_framework.workflow.workflow_executor_enhanced import EnhancedWorkflowExecutor
            from agent_framework.workflow.visual_workflow import get_workflow

            workflow_id = app.config.get('workflow_id')
            if not workflow_id:
                return jsonify({"error": "Workflow ID not configured"}), 400

            workflow = get_workflow(workflow_id)
            if not workflow:
                return jsonify({"error": "Workflow not found"}), 404

            executor = EnhancedWorkflowExecutor(workflow)
            exec_result = executor.execute({"input": user_input})

            result = {
                "output": exec_result.get('output', ''),
                "status": "success",
                "app_type": "workflow"
            }

        else:
            # 其他类型应用
            result = {
                "output": f"处理结果: {user_input}",
                "status": "success",
                "app_type": app.type.value
            }

        response_time = time.time() - start_time

        # 记录 API 调用
        publisher.log_api_call(
            publish_id=publish_id,
            method=request.method,
            path=request.path,
            status_code=200,
            response_time=response_time,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
        )

        return jsonify(result)

    except Exception as e:
        response_time = time.time() - start_time

        # 记录错误
        publisher.log_api_call(
            publish_id=publish_id,
            method=request.method,
            path=request.path,
            status_code=500,
            response_time=response_time,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
        )

        return jsonify({"error": str(e)}), 500


@publish_bp.route('/verify', methods=['POST'])
def verify_api_key():
    """验证 API Key"""
    data = request.json
    api_key = data.get('api_key')

    if not api_key:
        return jsonify({"error": "API key required"}), 400

    published_app = publisher.verify_api_key(api_key)
    if not published_app:
        return jsonify({"valid": False}), 200

    return jsonify({
        "valid": True,
        "publish_id": published_app.publish_id,
        "app_id": published_app.app_id,
        "rate_limit": published_app.rate_limit,
    })
