"""
系统集成和扩展能力 - Agent Framework
提供插件系统、第三方服务集成、API文档生成等功能
"""

import agent_framework.core.fast_json as json
import uuid
import importlib
import inspect
import asyncio
from typing import Dict, List, Any, Optional, Callable, Type
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import logging
from abc import ABC, abstractmethod
import yaml
import requests
from datetime import datetime

from agent_framework.tool.registry import ToolSpec, _infer_schema

logger = logging.getLogger(__name__)

class IntegrationType(Enum):
    """集成类型"""
    WEBHOOK = "webhook"
    API = "api"
    DATABASE = "database"
    MESSAGE_QUEUE = "message_queue"
    FILE_STORAGE = "file_storage"
    AUTHENTICATION = "authentication"
    MONITORING = "monitoring"
    NOTIFICATION = "notification"

class PluginStatus(Enum):
    """插件状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    LOADING = "loading"

@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str
    description: str
    author: str
    homepage: str
    license: str
    dependencies: List[str]
    permissions: List[str]
    api_version: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime

@dataclass
class IntegrationConfig:
    """集成配置"""
    id: str
    name: str
    type: IntegrationType
    endpoint: str
    credentials: Dict[str, Any]
    settings: Dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime

class BasePlugin(ABC):
    """插件基类"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.metadata = self.get_metadata()
        self.status = PluginStatus.INACTIVE

    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """获取插件元数据"""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """初始化插件"""
        pass

    @abstractmethod
    async def cleanup(self) -> bool:
        """清理插件资源"""
        pass

    @abstractmethod
    def get_api_routes(self) -> List[Dict[str, Any]]:
        """获取插件提供的API路由"""
        pass

    def get_hooks(self) -> Dict[str, Callable]:
        """获取插件提供的钩子函数"""
        return {}

    def get_tools(self) -> Dict[str, Callable]:
        """获取插件提供的工具函数"""
        return {}

class PluginManager:
    """插件管理器"""

    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugins: Dict[str, BasePlugin] = {}
        self.plugin_configs: Dict[str, Dict[str, Any]] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        self.tools: Dict[str, Callable] = {}

        # 确保插件目录存在
        self.plugin_dir.mkdir(exist_ok=True)

    async def load_plugin(self, plugin_name: str, config: Dict[str, Any] = None) -> bool:
        """加载插件"""
        try:
            # 动态导入插件模块
            module_path = f"{self.plugin_dir.name}.{plugin_name}"
            module = importlib.import_module(module_path)

            # 查找插件类
            plugin_class = None
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and
                    issubclass(obj, BasePlugin) and
                    obj != BasePlugin):
                    plugin_class = obj
                    break

            if not plugin_class:
                logger.error(f"插件 {plugin_name} 中未找到有效的插件类")
                return False

            # 创建插件实例
            plugin = plugin_class(config)
            plugin.status = PluginStatus.LOADING

            # 初始化插件
            if await plugin.initialize():
                plugin.status = PluginStatus.ACTIVE
                self.plugins[plugin_name] = plugin
                self.plugin_configs[plugin_name] = config or {}

                # 注册钩子和工具
                self._register_plugin_hooks(plugin_name, plugin)
                self._register_plugin_tools(plugin_name, plugin)

                logger.info(f"插件 {plugin_name} 加载成功")
                return True
            else:
                plugin.status = PluginStatus.ERROR
                logger.error(f"插件 {plugin_name} 初始化失败")
                return False

        except Exception as e:
            logger.error(f"加载插件 {plugin_name} 失败: {str(e)}")
            return False

    async def unload_plugin(self, plugin_name: str) -> bool:
        """卸载插件"""
        try:
            if plugin_name not in self.plugins:
                return False

            plugin = self.plugins[plugin_name]

            # 清理插件资源
            await plugin.cleanup()

            # 移除钩子和工具
            self._unregister_plugin_hooks(plugin_name)
            self._unregister_plugin_tools(plugin_name)

            # 移除插件
            del self.plugins[plugin_name]
            del self.plugin_configs[plugin_name]

            logger.info(f"插件 {plugin_name} 卸载成功")
            return True

        except Exception as e:
            logger.error(f"卸载插件 {plugin_name} 失败: {str(e)}")
            return False

    def _register_plugin_hooks(self, plugin_name: str, plugin: BasePlugin):
        """注册插件钩子"""
        hooks = plugin.get_hooks()
        for hook_name, hook_func in hooks.items():
            if hook_name not in self.hooks:
                self.hooks[hook_name] = []
            self.hooks[hook_name].append(hook_func)

    def _unregister_plugin_hooks(self, plugin_name: str):
        """注销插件钩子"""
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            hooks = plugin.get_hooks()
            for hook_name, hook_func in hooks.items():
                if hook_name in self.hooks:
                    try:
                        self.hooks[hook_name].remove(hook_func)
                    except ValueError:
                        pass

    def _register_plugin_tools(self, plugin_name: str, plugin: BasePlugin):
        """注册插件工具"""
        tools = plugin.get_tools()
        for tool_name, tool_func in tools.items():
            full_tool_name = f"{plugin_name}.{tool_name}"
            self.tools[full_tool_name] = tool_func

    def get_tool_specs(self) -> List[ToolSpec]:
        """将所有插件工具转换为 ToolSpec 列表，用于注册到核心 ToolRegistry"""
        specs: List[ToolSpec] = []
        for full_name, handler in self.tools.items():
            doc = (handler.__doc__ or "").strip().split("\n")[0] if handler.__doc__ else full_name
            try:
                schema = _infer_schema(handler)
            except Exception:
                schema = {"type": "object", "properties": {}, "required": []}
            specs.append(ToolSpec(
                name=full_name,
                description=doc,
                parameters=schema,
                handler=handler,
            ))
        return specs

    def _unregister_plugin_tools(self, plugin_name: str):
        """注销插件工具"""
        tools_to_remove = [
            tool_name for tool_name in self.tools.keys()
            if tool_name.startswith(f"{plugin_name}.")
        ]
        for tool_name in tools_to_remove:
            del self.tools[tool_name]

    async def execute_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """执行钩子"""
        results = []
        if hook_name in self.hooks:
            for hook_func in self.hooks[hook_name]:
                try:
                    if asyncio.iscoroutinefunction(hook_func):
                        result = await hook_func(*args, **kwargs)
                    else:
                        result = hook_func(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    logger.error(f"执行钩子 {hook_name} 失败: {str(e)}")
        return results

    def execute_tool(self, tool_name: str, *args, **kwargs) -> Any:
        """执行工具"""
        if tool_name in self.tools:
            try:
                return self.tools[tool_name](*args, **kwargs)
            except Exception as e:
                logger.error(f"执行工具 {tool_name} 失败: {str(e)}")
                raise
        else:
            raise ValueError(f"工具 {tool_name} 不存在")

    def list_plugins(self) -> List[Dict[str, Any]]:
        """列出所有插件"""
        return [
            {
                "name": name,
                "metadata": asdict(plugin.metadata),
                "status": plugin.status.value,
                "config": self.plugin_configs.get(name, {})
            }
            for name, plugin in self.plugins.items()
        ]

    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """获取插件信息"""
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            return {
                "name": plugin_name,
                "metadata": asdict(plugin.metadata),
                "status": plugin.status.value,
                "config": self.plugin_configs.get(plugin_name, {}),
                "hooks": list(plugin.get_hooks().keys()),
                "tools": list(plugin.get_tools().keys()),
                "api_routes": plugin.get_api_routes()
            }
        return None

class IntegrationManager:
    """集成管理器"""

    def __init__(self):
        self.integrations: Dict[str, IntegrationConfig] = {}
        self.active_connections: Dict[str, Any] = {}

    def add_integration(self,
                       name: str,
                       integration_type: IntegrationType,
                       endpoint: str,
                       credentials: Dict[str, Any],
                       settings: Dict[str, Any] = None) -> str:
        """添加集成"""
        integration_id = str(uuid.uuid4())

        integration = IntegrationConfig(
            id=integration_id,
            name=name,
            type=integration_type,
            endpoint=endpoint,
            credentials=credentials,
            settings=settings or {},
            enabled=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self.integrations[integration_id] = integration
        return integration_id

    async def test_integration(self, integration_id: str) -> Dict[str, Any]:
        """测试集成连接"""
        if integration_id not in self.integrations:
            return {"success": False, "error": "集成不存在"}

        integration = self.integrations[integration_id]

        try:
            if integration.type == IntegrationType.API:
                return await self._test_api_integration(integration)
            elif integration.type == IntegrationType.WEBHOOK:
                return await self._test_webhook_integration(integration)
            elif integration.type == IntegrationType.DATABASE:
                return await self._test_database_integration(integration)
            else:
                return {"success": False, "error": f"不支持的集成类型: {integration.type}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _test_api_integration(self, integration: IntegrationConfig) -> Dict[str, Any]:
        """测试API集成"""
        try:
            headers = integration.credentials.get("headers", {})
            timeout = integration.settings.get("timeout", 30)

            response = requests.get(
                integration.endpoint,
                headers=headers,
                timeout=timeout
            )

            return {
                "success": response.status_code < 400,
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds()
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _test_webhook_integration(self, integration: IntegrationConfig) -> Dict[str, Any]:
        """测试Webhook集成"""
        try:
            test_payload = {"test": True, "timestamp": datetime.now().isoformat()}
            headers = integration.credentials.get("headers", {})

            response = requests.post(
                integration.endpoint,
                json=test_payload,
                headers=headers,
                timeout=30
            )

            return {
                "success": response.status_code < 400,
                "status_code": response.status_code
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _test_database_integration(self, integration: IntegrationConfig) -> Dict[str, Any]:
        """测试数据库集成"""
        # 这里应该根据数据库类型实现具体的连接测试
        return {"success": True, "message": "数据库连接测试需要具体实现"}

    def send_webhook(self, integration_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送Webhook"""
        if integration_id not in self.integrations:
            return {"success": False, "error": "集成不存在"}

        integration = self.integrations[integration_id]

        if integration.type != IntegrationType.WEBHOOK:
            return {"success": False, "error": "不是Webhook集成"}

        try:
            headers = integration.credentials.get("headers", {})
            response = requests.post(
                integration.endpoint,
                json=payload,
                headers=headers,
                timeout=30
            )

            return {
                "success": response.status_code < 400,
                "status_code": response.status_code,
                "response": response.text
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_integrations(self) -> List[Dict[str, Any]]:
        """列出所有集成"""
        return [
            {
                "id": integration.id,
                "name": integration.name,
                "type": integration.type.value,
                "endpoint": integration.endpoint,
                "enabled": integration.enabled,
                "created_at": integration.created_at.isoformat(),
                "updated_at": integration.updated_at.isoformat()
            }
            for integration in self.integrations.values()
        ]

class APIDocGenerator:
    """API文档生成器"""

    def __init__(self, app_name: str = "Agent Framework"):
        self.app_name = app_name
        self.endpoints: List[Dict[str, Any]] = []
        self.schemas: Dict[str, Dict[str, Any]] = {}

    def add_endpoint(self,
                    path: str,
                    method: str,
                    summary: str,
                    description: str = "",
                    parameters: List[Dict[str, Any]] = None,
                    request_body: Dict[str, Any] = None,
                    responses: Dict[str, Dict[str, Any]] = None,
                    tags: List[str] = None):
        """添加API端点"""
        endpoint = {
            "path": path,
            "method": method.upper(),
            "summary": summary,
            "description": description,
            "parameters": parameters or [],
            "request_body": request_body,
            "responses": responses or {},
            "tags": tags or []
        }

        self.endpoints.append(endpoint)

    def add_schema(self, name: str, schema: Dict[str, Any]):
        """添加数据模式"""
        self.schemas[name] = schema

    def generate_openapi_spec(self) -> Dict[str, Any]:
        """生成OpenAPI规范"""
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": self.app_name,
                "version": "1.0.0",
                "description": f"{self.app_name} API文档"
            },
            "servers": [
                {
                    "url": "http://localhost:5000",
                    "description": "开发服务器"
                }
            ],
            "paths": {},
            "components": {
                "schemas": self.schemas,
                "securitySchemes": {
                    "ApiKeyAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-API-Key"
                    }
                }
            }
        }

        # 组织端点
        for endpoint in self.endpoints:
            path = endpoint["path"]
            method = endpoint["method"].lower()

            if path not in spec["paths"]:
                spec["paths"][path] = {}

            spec["paths"][path][method] = {
                "summary": endpoint["summary"],
                "description": endpoint["description"],
                "tags": endpoint["tags"],
                "parameters": endpoint["parameters"],
                "responses": endpoint["responses"]
            }

            if endpoint["request_body"]:
                spec["paths"][path][method]["requestBody"] = endpoint["request_body"]

        return spec

    def generate_markdown_docs(self) -> str:
        """生成Markdown文档"""
        docs = f"# {self.app_name} API文档\n\n"

        # 按标签分组
        tags = {}
        for endpoint in self.endpoints:
            for tag in endpoint["tags"]:
                if tag not in tags:
                    tags[tag] = []
                tags[tag].append(endpoint)

        for tag, endpoints in tags.items():
            docs += f"## {tag}\n\n"

            for endpoint in endpoints:
                docs += f"### {endpoint['method']} {endpoint['path']}\n\n"
                docs += f"{endpoint['summary']}\n\n"

                if endpoint['description']:
                    docs += f"{endpoint['description']}\n\n"

                if endpoint['parameters']:
                    docs += "**参数:**\n\n"
                    for param in endpoint['parameters']:
                        docs += f"- `{param['name']}` ({param.get('in', 'query')}): {param.get('description', '')}\n"
                    docs += "\n"

                docs += "**响应:**\n\n"
                for status, response in endpoint['responses'].items():
                    docs += f"- {status}: {response.get('description', '')}\n"
                docs += "\n"

        return docs

class ExtensionSystem:
    """扩展系统主类"""

    def __init__(self):
        self.plugin_manager = PluginManager()
        self.integration_manager = IntegrationManager()
        self.api_doc_generator = APIDocGenerator()
        self.event_bus = EventBus()

    async def initialize(self):
        """初始化扩展系统"""
        # 自动加载插件
        await self._auto_load_plugins()

        # 注册核心API文档
        self._register_core_api_docs()

    async def _auto_load_plugins(self):
        """自动加载插件"""
        plugin_config_file = self.plugin_manager.plugin_dir / "plugins.yaml"

        if plugin_config_file.exists():
            try:
                with open(plugin_config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                for plugin_name, plugin_config in config.get('plugins', {}).items():
                    if plugin_config.get('enabled', True):
                        await self.plugin_manager.load_plugin(plugin_name, plugin_config)

            except Exception as e:
                logger.error(f"加载插件配置失败: {str(e)}")

    def _register_core_api_docs(self):
        """注册核心API文档"""
        # 这里可以注册核心API的文档
        self.api_doc_generator.add_endpoint(
            path="/api/plugins",
            method="GET",
            summary="获取插件列表",
            description="获取所有已加载的插件信息",
            tags=["插件管理"],
            responses={
                "200": {"description": "成功返回插件列表"}
            }
        )

class EventBus:
    """事件总线"""

    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, callback: Callable):
        """订阅事件"""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable):
        """取消订阅"""
        if event_name in self.listeners:
            try:
                self.listeners[event_name].remove(callback)
            except ValueError:
                pass

    async def emit(self, event_name: str, data: Any = None):
        """发布事件"""
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"事件处理失败 {event_name}: {str(e)}")

# 全局扩展系统实例
extension_system = ExtensionSystem()

def get_extension_system() -> ExtensionSystem:
    """获取扩展系统实例"""
    return extension_system