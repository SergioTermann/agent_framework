"""
Webhook API
提供 Webhook 管理和接收的 REST API
"""

from flask import Blueprint, jsonify, request
from agent_framework.web.webhook_system import (
    get_webhook_manager,
    WebhookStatus,
    WebhookEventStatus
)

webhook_bp = Blueprint('webhook', __name__, url_prefix='/api/webhooks')


@webhook_bp.route('/', methods=['GET'])
def list_webhooks():
    """列出所有 Webhook"""
    status = request.args.get('status')

    manager = get_webhook_manager()

    if status:
        try:
            status_enum = WebhookStatus(status)
            webhooks = manager.list_webhooks(status=status_enum)
        except ValueError:
            return jsonify({'error': '无效的状态'}), 400
    else:
        webhooks = manager.list_webhooks()

    return jsonify({
        'webhooks': [wh.to_dict() for wh in webhooks],
        'count': len(webhooks)
    })


@webhook_bp.route('/', methods=['POST'])
def create_webhook():
    """
    创建 Webhook

    请求体:
    {
        "name": "GitHub Webhook",
        "url_path": "/webhooks/github",
        "description": "接收 GitHub 事件",
        "events": ["push", "pull_request"],
        "verify_signature": true
    }
    """
    data = request.json

    name = data.get('name')
    url_path = data.get('url_path')

    if not name or not url_path:
        return jsonify({'error': '缺少必需字段'}), 400

    # 确保路径以 /webhooks/ 开头
    if not url_path.startswith('/webhooks/'):
        url_path = f'/webhooks/{url_path}'

    manager = get_webhook_manager()

    try:
        webhook = manager.create_webhook(
            name=name,
            url_path=url_path,
            description=data.get('description', ''),
            events=data.get('events', []),
            verify_signature=data.get('verify_signature', True),
            signature_header=data.get('signature_header', 'X-Hub-Signature-256'),
            signature_algorithm=data.get('signature_algorithm', 'sha256')
        )

        return jsonify({
            'webhook': webhook.to_dict(),
            'secret': webhook.secret,
            'message': 'Webhook 创建成功'
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@webhook_bp.route('/<webhook_id>', methods=['GET'])
def get_webhook(webhook_id: str):
    """获取 Webhook 详情"""
    manager = get_webhook_manager()
    webhook = manager.get_webhook(webhook_id)

    if not webhook:
        return jsonify({'error': 'Webhook 不存在'}), 404

    return jsonify({'webhook': webhook.to_dict()})


@webhook_bp.route('/<webhook_id>', methods=['PUT'])
def update_webhook(webhook_id: str):
    """
    更新 Webhook

    请求体:
    {
        "name": "新名称",
        "description": "新描述",
        "status": "active",
        "events": ["push"]
    }
    """
    data = request.json
    manager = get_webhook_manager()

    # 处理状态
    if 'status' in data:
        try:
            data['status'] = WebhookStatus(data['status'])
        except ValueError:
            return jsonify({'error': '无效的状态'}), 400

    webhook = manager.update_webhook(webhook_id, **data)

    if not webhook:
        return jsonify({'error': 'Webhook 不存在'}), 404

    return jsonify({
        'webhook': webhook.to_dict(),
        'message': 'Webhook 更新成功'
    })


@webhook_bp.route('/<webhook_id>', methods=['DELETE'])
def delete_webhook(webhook_id: str):
    """删除 Webhook"""
    manager = get_webhook_manager()

    webhook = manager.get_webhook(webhook_id)
    if not webhook:
        return jsonify({'error': 'Webhook 不存在'}), 404

    manager.delete_webhook(webhook_id)

    return jsonify({'message': 'Webhook 删除成功'})


@webhook_bp.route('/<webhook_id>/regenerate-secret', methods=['POST'])
def regenerate_secret(webhook_id: str):
    """重新生成密钥"""
    manager = get_webhook_manager()

    webhook = manager.get_webhook(webhook_id)
    if not webhook:
        return jsonify({'error': 'Webhook 不存在'}), 404

    import hashlib
    import uuid
    new_secret = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()

    webhook = manager.update_webhook(webhook_id, secret=new_secret)

    return jsonify({
        'secret': new_secret,
        'message': '密钥已重新生成'
    })


@webhook_bp.route('/<webhook_id>/events', methods=['GET'])
def list_webhook_events(webhook_id: str):
    """列出 Webhook 的事件"""
    manager = get_webhook_manager()

    webhook = manager.get_webhook(webhook_id)
    if not webhook:
        return jsonify({'error': 'Webhook 不存在'}), 404

    status = request.args.get('status')
    limit = request.args.get('limit', 100, type=int)

    status_enum = None
    if status:
        try:
            status_enum = WebhookEventStatus(status)
        except ValueError:
            return jsonify({'error': '无效的状态'}), 400

    events = manager.storage.list_events(
        webhook_id=webhook_id,
        status=status_enum,
        limit=limit
    )

    return jsonify({
        'events': [event.to_dict() for event in events],
        'count': len(events)
    })


@webhook_bp.route('/events', methods=['GET'])
def list_all_events():
    """列出所有事件"""
    manager = get_webhook_manager()

    status = request.args.get('status')
    limit = request.args.get('limit', 100, type=int)

    status_enum = None
    if status:
        try:
            status_enum = WebhookEventStatus(status)
        except ValueError:
            return jsonify({'error': '无效的状态'}), 400

    events = manager.storage.list_events(
        status=status_enum,
        limit=limit
    )

    return jsonify({
        'events': [event.to_dict() for event in events],
        'count': len(events)
    })


@webhook_bp.route('/events/<event_id>', methods=['GET'])
def get_event(event_id: str):
    """获取事件详情"""
    manager = get_webhook_manager()
    event = manager.storage.get_event(event_id)

    if not event:
        return jsonify({'error': '事件不存在'}), 404

    return jsonify({'event': event.to_dict()})


@webhook_bp.route('/test', methods=['POST'])
def test_webhook():
    """
    测试 Webhook

    请求体:
    {
        "webhook_id": "xxx",
        "payload": {"test": "data"},
        "event_type": "test"
    }
    """
    data = request.json

    webhook_id = data.get('webhook_id')
    payload = data.get('payload', {})
    event_type = data.get('event_type', 'test')

    if not webhook_id:
        return jsonify({'error': '缺少 webhook_id'}), 400

    manager = get_webhook_manager()
    webhook = manager.get_webhook(webhook_id)

    if not webhook:
        return jsonify({'error': 'Webhook 不存在'}), 404

    # 创建测试事件
    import uuid
    from agent_framework.web.webhook_system import WebhookEvent

    event = WebhookEvent(
        event_id=str(uuid.uuid4()),
        webhook_id=webhook_id,
        event_type=event_type,
        payload=payload,
        headers={'X-Event-Type': event_type, 'X-Test': 'true'}
    )

    manager.storage.save_event(event)
    manager._process_event(event, webhook)

    return jsonify({
        'event': event.to_dict(),
        'message': '测试事件已发送'
    })


# Webhook 接收端点（动态路由）
def create_webhook_receiver(app):
    """创建 Webhook 接收端点"""

    @app.route('/webhooks/<path:webhook_path>', methods=['POST'])
    def receive_webhook(webhook_path):
        """接收 Webhook"""
        url_path = f'/webhooks/{webhook_path}'

        manager = get_webhook_manager()

        try:
            # 获取请求数据
            if request.is_json:
                payload = request.json
            else:
                payload = {'data': request.data.decode('utf-8')}

            headers = dict(request.headers)

            # 处理请求
            event = manager.handle_request(url_path, payload, headers)

            return jsonify({
                'event_id': event.event_id,
                'status': 'received',
                'message': 'Webhook 已接收'
            }), 200

        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': f'处理失败: {str(e)}'}), 500
