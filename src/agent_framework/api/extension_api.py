"""
扩展系统 API - Agent Framework
提供插件管理、集成管理、API文档生成等API接口
"""

from flask import Blueprint, request, jsonify
from agent_framework.core.api_utils import handle_api_exception, json_error as _json_error, json_success as _json_success, request_json as _request_json
import logging
from datetime import datetime
import yaml

from agent_framework.platform.extension_system import (
    get_extension_system,
    IntegrationType,
    PluginStatus
)

logger = logging.getLogger(__name__)

# 创建蓝图
extension_bp = Blueprint('extension', __name__, url_prefix='/api/extensions')
def _handle_api_exception(prefix: str, exc: Exception):
    return handle_api_exception(logger, prefix, exc)

# ==================== 插件管理 API ====================

@extension_bp.route('/plugins', methods=['GET'])
def list_plugins():
    """获取插件列表"""
    try:
        system = get_extension_system()
        plugins = system.plugin_manager.list_plugins()

        return _json_success({
            "plugins": plugins,
            "total": len(plugins)
        })

    except Exception as e:
        return _handle_api_exception("获取插件列表失败", e)

@extension_bp.route('/plugins/<plugin_name>', methods=['GET'])
def get_plugin_info(plugin_name: str):
    """获取插件详细信息"""
    try:
        system = get_extension_system()
        plugin_info = system.plugin_manager.get_plugin_info(plugin_name)

        if not plugin_info:
            return _json_error("插件不存在", 404)

        return _json_success({
            "plugin": plugin_info
        })

    except Exception as e:
        return _handle_api_exception("获取插件信息失败", e)

@extension_bp.route('/plugins/<plugin_name>/load', methods=['POST'])
async def load_plugin(plugin_name: str):
    """加载插件"""
    try:
        data = _request_json()
        config = data.get('config', {})

        system = get_extension_system()
        success = await system.plugin_manager.load_plugin(plugin_name, config)

        if success:
            return _json_success({
                "message": f"插件 {plugin_name} 加载成功"
            })
        else:
            return _json_error(f"插件 {plugin_name} 加载失败", 400, success=False)

    except Exception as e:
        return _handle_api_exception("加载插件失败", e)

@extension_bp.route('/plugins/<plugin_name>/unload', methods=['POST'])
async def unload_plugin(plugin_name: str):
    """卸载插件"""
    try:
        system = get_extension_system()
        success = await system.plugin_manager.unload_plugin(plugin_name)

        if success:
            return _json_success({
                "message": f"插件 {plugin_name} 卸载成功"
            })
        else:
            return _json_error(f"插件 {plugin_name} 卸载失败", 400, success=False)

    except Exception as e:
        return _handle_api_exception("卸载插件失败", e)

@extension_bp.route('/plugins/<plugin_name>/execute-tool', methods=['POST'])
def execute_plugin_tool(plugin_name: str):
    """执行插件工具"""
    try:
        data = _request_json()
        tool_name = data.get('tool_name')
        args = data.get('args', [])
        kwargs = data.get('kwargs', {})

        if not tool_name:
            return _json_error("工具名称不能为空")

        full_tool_name = f"{plugin_name}.{tool_name}"

        system = get_extension_system()
        result = system.plugin_manager.execute_tool(full_tool_name, *args, **kwargs)

        return _json_success({
            "result": result
        })

    except ValueError as e:
        return _json_error(str(e), 404)
    except Exception as e:
        return _handle_api_exception("执行插件工具失败", e)

@extension_bp.route('/hooks/<hook_name>/execute', methods=['POST'])
async def execute_hook(hook_name: str):
    """执行钩子"""
    try:
        data = _request_json()
        args = data.get('args', [])
        kwargs = data.get('kwargs', {})

        system = get_extension_system()
        results = await system.plugin_manager.execute_hook(hook_name, *args, **kwargs)

        return _json_success({
            "results": results,
            "count": len(results)
        })

    except Exception as e:
        return _handle_api_exception("执行钩子失败", e)

# ==================== 集成管理 API ====================

@extension_bp.route('/integrations', methods=['GET'])
def list_integrations():
    """获取集成列表"""
    try:
        system = get_extension_system()
        integrations = system.integration_manager.list_integrations()

        return _json_success({
            "integrations": integrations,
            "total": len(integrations)
        })

    except Exception as e:
        return _handle_api_exception("获取集成列表失败", e)

@extension_bp.route('/integrations', methods=['POST'])
def create_integration():
    """创建集成"""
    try:
        data = _request_json()

        name = data.get('name')
        integration_type = data.get('type')
        endpoint = data.get('endpoint')
        credentials = data.get('credentials', {})
        settings = data.get('settings', {})

        if not all([name, integration_type, endpoint]):
            return _json_error("名称、类型和端点不能为空")

        try:
            int_type = IntegrationType(integration_type)
        except ValueError:
            return _json_error(f"无效的集成类型: {integration_type}")

        system = get_extension_system()
        integration_id = system.integration_manager.add_integration(
            name, int_type, endpoint, credentials, settings
        )

        return _json_success({
            "integration_id": integration_id,
            "message": "集成创建成功"
        })

    except Exception as e:
        return _handle_api_exception("创建集成失败", e)

@extension_bp.route('/integrations/<integration_id>/test', methods=['POST'])
async def test_integration(integration_id: str):
    """测试集成"""
    try:
        system = get_extension_system()
        result = await system.integration_manager.test_integration(integration_id)

        return jsonify({
            "success": result["success"],
            "test_result": result
        })

    except Exception as e:
        return _handle_api_exception("测试集成失败", e)

@extension_bp.route('/integrations/<integration_id>/webhook', methods=['POST'])
def send_webhook(integration_id: str):
    """发送Webhook"""
    try:
        data = _request_json()
        payload = data.get('payload', {})

        system = get_extension_system()
        result = system.integration_manager.send_webhook(integration_id, payload)

        return jsonify({
            "success": result["success"],
            "webhook_result": result
        })

    except Exception as e:
        return _handle_api_exception("发送Webhook失败", e)

@extension_bp.route('/integrations/<integration_id>', methods=['DELETE'])
def delete_integration(integration_id: str):
    """删除集成"""
    try:
        system = get_extension_system()

        if integration_id not in system.integration_manager.integrations:
            return _json_error("集成不存在", 404)

        del system.integration_manager.integrations[integration_id]

        return _json_success({
            "message": "集成删除成功"
        })

    except Exception as e:
        return _handle_api_exception("删除集成失败", e)

# ==================== API文档生成 API ====================

@extension_bp.route('/api-docs/openapi.json', methods=['GET'])
def get_openapi_spec():
    """获取OpenAPI规范"""
    try:
        system = get_extension_system()
        spec = system.api_doc_generator.generate_openapi_spec()

        return jsonify(spec)

    except Exception as e:
        return _handle_api_exception("生成OpenAPI规范失败", e)

@extension_bp.route('/api-docs/markdown', methods=['GET'])
def get_markdown_docs():
    """获取Markdown文档"""
    try:
        system = get_extension_system()
        docs = system.api_doc_generator.generate_markdown_docs()

        return docs, 200, {'Content-Type': 'text/markdown; charset=utf-8'}

    except Exception as e:
        return _handle_api_exception("生成Markdown文档失败", e)

@extension_bp.route('/api-docs/endpoints', methods=['POST'])
def add_api_endpoint():
    """添加API端点文档"""
    try:
        data = _request_json()

        required_fields = ['path', 'method', 'summary']
        for field in required_fields:
            if field not in data:
                return _json_error(f"缺少必需字段: {field}")

        system = get_extension_system()
        system.api_doc_generator.add_endpoint(
            path=data['path'],
            method=data['method'],
            summary=data['summary'],
            description=data.get('description', ''),
            parameters=data.get('parameters', []),
            request_body=data.get('request_body'),
            responses=data.get('responses', {}),
            tags=data.get('tags', [])
        )

        return _json_success({
            "message": "API端点文档添加成功"
        })

    except Exception as e:
        return _handle_api_exception("添加API端点文档失败", e)

@extension_bp.route('/api-docs/schemas', methods=['POST'])
def add_api_schema():
    """添加API数据模式"""
    try:
        data = _request_json()

        name = data.get('name')
        schema = data.get('schema')

        if not name or not schema:
            return _json_error("名称和模式不能为空")

        system = get_extension_system()
        system.api_doc_generator.add_schema(name, schema)

        return _json_success({
            "message": "API数据模式添加成功"
        })

    except Exception as e:
        return _handle_api_exception("添加API数据模式失败", e)

# ==================== 事件总线 API ====================

@extension_bp.route('/events/<event_name>/emit', methods=['POST'])
async def emit_event(event_name: str):
    """发布事件"""
    try:
        data = _request_json()
        event_data = data.get('data')

        system = get_extension_system()
        await system.event_bus.emit(event_name, event_data)

        return _json_success({
            "message": f"事件 {event_name} 发布成功"
        })

    except Exception as e:
        return _handle_api_exception("发布事件失败", e)

# ==================== 系统信息 API ====================

@extension_bp.route('/system/info', methods=['GET'])
def get_system_info():
    """获取扩展系统信息"""
    try:
        system = get_extension_system()

        info = {
            "plugin_count": len(system.plugin_manager.plugins),
            "integration_count": len(system.integration_manager.integrations),
            "hook_count": len(system.plugin_manager.hooks),
            "tool_count": len(system.plugin_manager.tools),
            "api_endpoint_count": len(system.api_doc_generator.endpoints),
            "schema_count": len(system.api_doc_generator.schemas)
        }

        return _json_success({
            "system_info": info
        })

    except Exception as e:
        return _handle_api_exception("获取系统信息失败", e)

@extension_bp.route('/system/health', methods=['GET'])
def get_system_health():
    """获取系统健康状态"""
    try:
        system = get_extension_system()

        # 检查插件状态
        plugin_health = {}
        for name, plugin in system.plugin_manager.plugins.items():
            plugin_health[name] = {
                "status": plugin.status.value,
                "healthy": plugin.status == PluginStatus.ACTIVE
            }

        # 检查集成状态
        integration_health = {}
        for integration_id, integration in system.integration_manager.integrations.items():
            integration_health[integration_id] = {
                "name": integration.name,
                "enabled": integration.enabled,
                "healthy": integration.enabled
            }

        overall_health = (
            all(p["healthy"] for p in plugin_health.values()) and
            all(i["healthy"] for i in integration_health.values())
        )

        return _json_success({
            "overall_health": overall_health,
            "plugin_health": plugin_health,
            "integration_health": integration_health,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return _handle_api_exception("获取系统健康状态失败", e)

# ==================== 配置管理 API ====================

@extension_bp.route('/config/plugins', methods=['GET'])
def get_plugin_config():
    """获取插件配置"""
    try:
        system = get_extension_system()
        plugin_config_file = system.plugin_manager.plugin_dir / "plugins.yaml"

        if plugin_config_file.exists():
            with open(plugin_config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        else:
            config = {"plugins": {}}

        return _json_success({
            "config": config
        })

    except Exception as e:
        return _handle_api_exception("获取插件配置失败", e)

@extension_bp.route('/config/plugins', methods=['POST'])
def update_plugin_config():
    """更新插件配置"""
    try:
        data = _request_json()
        config = data.get('config')

        if not config:
            return _json_error("配置不能为空")

        system = get_extension_system()
        plugin_config_file = system.plugin_manager.plugin_dir / "plugins.yaml"

        with open(plugin_config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        return _json_success({
            "message": "插件配置更新成功"
        })

    except Exception as e:
        return _handle_api_exception("更新插件配置失败", e)

# ==================== 工具函数 ====================

@extension_bp.route('/integration-types', methods=['GET'])
def get_integration_types():
    """获取集成类型列表"""
    try:
        types = [
            {
                "value": it.value,
                "name": it.name,
                "description": {
                    "webhook": "Webhook - HTTP回调集成",
                    "api": "API - RESTful API集成",
                    "database": "数据库 - 数据库连接集成",
                    "message_queue": "消息队列 - 异步消息集成",
                    "file_storage": "文件存储 - 文件存储服务集成",
                    "authentication": "认证 - 身份认证服务集成",
                    "monitoring": "监控 - 监控服务集成",
                    "notification": "通知 - 通知服务集成"
                }.get(it.value, "")
            }
            for it in IntegrationType
        ]

        return _json_success({
            "integration_types": types
        })

    except Exception as e:
        return _handle_api_exception("获取集成类型失败", e)

# 错误处理
@extension_bp.errorhandler(404)
def not_found(error):
    return _json_error("API端点不存在", 404)

@extension_bp.errorhandler(405)
def method_not_allowed(error):
    return _json_error("HTTP方法不允许", 405)

@extension_bp.errorhandler(500)
def internal_error(error):
    return _json_error("内部服务器错误", 500)
