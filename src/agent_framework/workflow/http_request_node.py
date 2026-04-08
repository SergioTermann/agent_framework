"""
HTTP 请求节点
为工作流提供 HTTP 请求功能
"""

import requests
import agent_framework.core.fast_json as json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class HttpMethod(Enum):
    """HTTP 方法"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class AuthType(Enum):
    """认证类型"""
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"


@dataclass
class HttpRequestConfig:
    """HTTP 请求配置"""
    url: str
    method: HttpMethod = HttpMethod.GET
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    body: Optional[Any] = None
    auth_type: AuthType = AuthType.NONE
    auth_config: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    follow_redirects: bool = True
    verify_ssl: bool = True
    retry_count: int = 0
    retry_delay: int = 1


@dataclass
class HttpResponse:
    """HTTP 响应"""
    status_code: int
    headers: Dict[str, str]
    body: Any
    text: str
    elapsed_ms: float
    success: bool
    error: Optional[str] = None


class HttpRequestNode:
    """HTTP 请求节点"""

    def __init__(self, config: HttpRequestConfig):
        self.config = config

    def execute(self, context: Dict[str, Any] = None) -> HttpResponse:
        """执行 HTTP 请求"""
        context = context or {}

        # 替换变量
        url = self._replace_variables(self.config.url, context)
        headers = self._replace_dict_variables(self.config.headers, context)
        params = self._replace_dict_variables(self.config.params, context)

        # 处理请求体
        body = None
        if self.config.body:
            if isinstance(self.config.body, str):
                body = self._replace_variables(self.config.body, context)
                # 尝试解析为 JSON
                try:
                    body = json.loads(body)
                except:
                    pass
            else:
                body = self.config.body

        # 添加认证
        auth = None
        if self.config.auth_type == AuthType.BASIC:
            username = self.config.auth_config.get('username', '')
            password = self.config.auth_config.get('password', '')
            auth = (username, password)
        elif self.config.auth_type == AuthType.BEARER:
            token = self.config.auth_config.get('token', '')
            headers['Authorization'] = f'Bearer {token}'
        elif self.config.auth_type == AuthType.API_KEY:
            key_name = self.config.auth_config.get('key_name', 'X-API-Key')
            key_value = self.config.auth_config.get('key_value', '')
            headers[key_name] = key_value

        # 执行请求（带重试）
        for attempt in range(self.config.retry_count + 1):
            try:
                import time
                start_time = time.time()

                response = requests.request(
                    method=self.config.method.value,
                    url=url,
                    headers=headers,
                    params=params,
                    json=body if isinstance(body, (dict, list)) else None,
                    data=body if isinstance(body, str) else None,
                    auth=auth,
                    timeout=self.config.timeout,
                    allow_redirects=self.config.follow_redirects,
                    verify=self.config.verify_ssl
                )

                elapsed_ms = (time.time() - start_time) * 1000

                # 解析响应体
                response_body = None
                try:
                    response_body = response.json()
                except:
                    response_body = response.text

                return HttpResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=response_body,
                    text=response.text,
                    elapsed_ms=elapsed_ms,
                    success=response.ok,
                    error=None if response.ok else f"HTTP {response.status_code}"
                )

            except requests.exceptions.Timeout:
                if attempt < self.config.retry_count:
                    time.sleep(self.config.retry_delay)
                    continue
                return HttpResponse(
                    status_code=0,
                    headers={},
                    body=None,
                    text="",
                    elapsed_ms=0,
                    success=False,
                    error="请求超时"
                )

            except requests.exceptions.ConnectionError as e:
                if attempt < self.config.retry_count:
                    time.sleep(self.config.retry_delay)
                    continue
                return HttpResponse(
                    status_code=0,
                    headers={},
                    body=None,
                    text="",
                    elapsed_ms=0,
                    success=False,
                    error=f"连接错误: {str(e)}"
                )

            except Exception as e:
                return HttpResponse(
                    status_code=0,
                    headers={},
                    body=None,
                    text="",
                    elapsed_ms=0,
                    success=False,
                    error=f"请求失败: {str(e)}"
                )

    def _replace_variables(self, text: str, context: Dict[str, Any]) -> str:
        """替换变量"""
        if not text:
            return text

        # 支持 {{variable}} 格式
        import re
        pattern = r'\{\{([^}]+)\}\}'

        def replacer(match):
            var_name = match.group(1).strip()
            # 支持嵌套访问，如 {{user.name}}
            value = context
            for key in var_name.split('.'):
                if isinstance(value, dict):
                    value = value.get(key, '')
                else:
                    value = ''
                    break
            return str(value)

        return re.sub(pattern, replacer, text)

    def _replace_dict_variables(
        self,
        data: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """替换字典中的变量"""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self._replace_variables(value, context)
            else:
                result[key] = value
        return result


class HttpRequestNodeBuilder:
    """HTTP 请求节点构建器"""

    def __init__(self):
        self.config = HttpRequestConfig(url="")

    def url(self, url: str):
        """设置 URL"""
        self.config.url = url
        return self

    def method(self, method: str):
        """设置方法"""
        self.config.method = HttpMethod[method.upper()]
        return self

    def header(self, key: str, value: str):
        """添加请求头"""
        self.config.headers[key] = value
        return self

    def headers(self, headers: Dict[str, str]):
        """设置请求头"""
        self.config.headers = headers
        return self

    def param(self, key: str, value: Any):
        """添加查询参数"""
        self.config.params[key] = value
        return self

    def params(self, params: Dict[str, Any]):
        """设置查询参数"""
        self.config.params = params
        return self

    def body(self, body: Any):
        """设置请求体"""
        self.config.body = body
        return self

    def json_body(self, data: Dict[str, Any]):
        """设置 JSON 请求体"""
        self.config.body = data
        self.config.headers['Content-Type'] = 'application/json'
        return self

    def basic_auth(self, username: str, password: str):
        """设置 Basic 认证"""
        self.config.auth_type = AuthType.BASIC
        self.config.auth_config = {
            'username': username,
            'password': password
        }
        return self

    def bearer_token(self, token: str):
        """设置 Bearer Token"""
        self.config.auth_type = AuthType.BEARER
        self.config.auth_config = {'token': token}
        return self

    def api_key(self, key_name: str, key_value: str):
        """设置 API Key"""
        self.config.auth_type = AuthType.API_KEY
        self.config.auth_config = {
            'key_name': key_name,
            'key_value': key_value
        }
        return self

    def timeout(self, seconds: int):
        """设置超时时间"""
        self.config.timeout = seconds
        return self

    def retry(self, count: int, delay: int = 1):
        """设置重试"""
        self.config.retry_count = count
        self.config.retry_delay = delay
        return self

    def verify_ssl(self, verify: bool = True):
        """设置 SSL 验证"""
        self.config.verify_ssl = verify
        return self

    def build(self) -> HttpRequestNode:
        """构建节点"""
        return HttpRequestNode(self.config)


# 便捷函数
def http_get(url: str, **kwargs) -> HttpResponse:
    """GET 请求"""
    config = HttpRequestConfig(url=url, method=HttpMethod.GET, **kwargs)
    node = HttpRequestNode(config)
    return node.execute()


def http_post(url: str, body: Any = None, **kwargs) -> HttpResponse:
    """POST 请求"""
    config = HttpRequestConfig(url=url, method=HttpMethod.POST, body=body, **kwargs)
    node = HttpRequestNode(config)
    return node.execute()


def http_put(url: str, body: Any = None, **kwargs) -> HttpResponse:
    """PUT 请求"""
    config = HttpRequestConfig(url=url, method=HttpMethod.PUT, body=body, **kwargs)
    node = HttpRequestNode(config)
    return node.execute()


def http_delete(url: str, **kwargs) -> HttpResponse:
    """DELETE 请求"""
    config = HttpRequestConfig(url=url, method=HttpMethod.DELETE, **kwargs)
    node = HttpRequestNode(config)
    return node.execute()
