"""
HTTP 请求 API
提供 HTTP 请求测试和管理功能
"""

from flask import Blueprint, jsonify, request
from agent_framework.workflow.http_request_node import (
    HttpRequestNode,
    HttpRequestConfig,
    HttpMethod,
    AuthType,
    http_get,
    http_post,
    http_put,
    http_delete
)
import agent_framework.core.fast_json as json

http_request_bp = Blueprint('http_request', __name__, url_prefix='/api/http')


@http_request_bp.route('/test', methods=['POST'])
def test_request():
    """
    测试 HTTP 请求

    请求体:
    {
        "url": "https://api.example.com/users",
        "method": "GET",
        "headers": {"Authorization": "Bearer token"},
        "params": {"page": 1},
        "body": {"name": "test"},
        "auth": {
            "type": "bearer",
            "config": {"token": "xxx"}
        },
        "timeout": 30,
        "retry": 3
    }
    """
    data = request.json

    url = data.get('url')
    if not url:
        return jsonify({'error': '缺少 URL'}), 400

    # 构建配置
    try:
        method = HttpMethod[data.get('method', 'GET').upper()]
    except KeyError:
        return jsonify({'error': '无效的 HTTP 方法'}), 400

    config = HttpRequestConfig(
        url=url,
        method=method,
        headers=data.get('headers', {}),
        params=data.get('params', {}),
        body=data.get('body'),
        timeout=data.get('timeout', 30),
        retry_count=data.get('retry', 0)
    )

    # 处理认证
    auth = data.get('auth', {})
    auth_type = auth.get('type', 'none')

    if auth_type == 'basic':
        config.auth_type = AuthType.BASIC
        config.auth_config = auth.get('config', {})
    elif auth_type == 'bearer':
        config.auth_type = AuthType.BEARER
        config.auth_config = auth.get('config', {})
    elif auth_type == 'api_key':
        config.auth_type = AuthType.API_KEY
        config.auth_config = auth.get('config', {})

    # 执行请求
    node = HttpRequestNode(config)
    response = node.execute()

    return jsonify({
        'status_code': response.status_code,
        'headers': response.headers,
        'body': response.body,
        'text': response.text[:1000] if response.text else None,  # 限制长度
        'elapsed_ms': response.elapsed_ms,
        'success': response.success,
        'error': response.error
    })


@http_request_bp.route('/methods', methods=['GET'])
def get_methods():
    """获取支持的 HTTP 方法"""
    return jsonify({
        'methods': [method.value for method in HttpMethod]
    })


@http_request_bp.route('/auth-types', methods=['GET'])
def get_auth_types():
    """获取支持的认证类型"""
    return jsonify({
        'auth_types': [
            {'value': 'none', 'label': '无认证'},
            {'value': 'basic', 'label': 'Basic Auth'},
            {'value': 'bearer', 'label': 'Bearer Token'},
            {'value': 'api_key', 'label': 'API Key'}
        ]
    })


@http_request_bp.route('/templates', methods=['GET'])
def get_templates():
    """获取请求模板"""
    templates = [
        {
            'name': 'GET 请求',
            'description': '简单的 GET 请求',
            'config': {
                'method': 'GET',
                'url': 'https://api.example.com/users',
                'headers': {},
                'params': {'page': 1, 'limit': 10}
            }
        },
        {
            'name': 'POST JSON',
            'description': 'POST JSON 数据',
            'config': {
                'method': 'POST',
                'url': 'https://api.example.com/users',
                'headers': {'Content-Type': 'application/json'},
                'body': {'name': 'John', 'email': 'john@example.com'}
            }
        },
        {
            'name': 'Bearer Token',
            'description': '使用 Bearer Token 认证',
            'config': {
                'method': 'GET',
                'url': 'https://api.example.com/protected',
                'auth': {
                    'type': 'bearer',
                    'config': {'token': 'your_token_here'}
                }
            }
        },
        {
            'name': 'API Key',
            'description': '使用 API Key 认证',
            'config': {
                'method': 'GET',
                'url': 'https://api.example.com/data',
                'auth': {
                    'type': 'api_key',
                    'config': {
                        'key_name': 'X-API-Key',
                        'key_value': 'your_api_key'
                    }
                }
            }
        }
    ]

    return jsonify({'templates': templates})


@http_request_bp.route('/quick/<method>', methods=['POST'])
def quick_request(method: str):
    """
    快速请求

    请求体:
    {
        "url": "https://api.example.com",
        "headers": {},
        "body": {}
    }
    """
    data = request.json
    url = data.get('url')

    if not url:
        return jsonify({'error': '缺少 URL'}), 400

    try:
        method_enum = HttpMethod[method.upper()]
    except KeyError:
        return jsonify({'error': '无效的 HTTP 方法'}), 400

    # 执行快速请求
    if method_enum == HttpMethod.GET:
        response = http_get(url, headers=data.get('headers', {}))
    elif method_enum == HttpMethod.POST:
        response = http_post(url, body=data.get('body'), headers=data.get('headers', {}))
    elif method_enum == HttpMethod.PUT:
        response = http_put(url, body=data.get('body'), headers=data.get('headers', {}))
    elif method_enum == HttpMethod.DELETE:
        response = http_delete(url, headers=data.get('headers', {}))
    else:
        return jsonify({'error': '不支持的方法'}), 400

    return jsonify({
        'status_code': response.status_code,
        'body': response.body,
        'success': response.success,
        'error': response.error
    })
