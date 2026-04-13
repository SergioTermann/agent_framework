"""
可视化工作流编排系统
==================

提供拖拽式的工作流设计和执行功能。

特性:
- 可视化节点编辑器
- 拖拽式连接
- 节点配置
- 工作流执行
- 实时预览
"""

from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict
from datetime import datetime
import agent_framework.core.fast_json as json
import re
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
import uuid


class NodeType:
    """节点类型"""
    START = "start"
    END = "end"
    LLM = "llm"
    AGENT = "agent"
    CODE = "code"
    CONDITION = "condition"
    LOOP = "loop"
    API = "api"
    TRANSFORM = "transform"
    MERGE = "merge"


@dataclass
class WorkflowNode:
    """工作流节点"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = NodeType.AGENT
    label: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0})
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.type,
            'label': self.label,
            'config': self.config,
            'position': self.position,
            'inputs': self.inputs,
            'outputs': self.outputs
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowNode':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            type=data.get('type', NodeType.AGENT),
            label=data.get('label', ''),
            config=data.get('config', {}),
            position=data.get('position', {"x": 0, "y": 0}),
            inputs=data.get('inputs', []),
            outputs=data.get('outputs', [])
        )


@dataclass
class WorkflowEdge:
    """工作流连接"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    target: str = ""
    label: str = ""
    condition: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'source': self.source,
            'target': self.target,
            'label': self.label,
            'condition': self.condition
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowEdge':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            source=data.get('source', ''),
            target=data.get('target', ''),
            label=data.get('label', ''),
            condition=data.get('condition')
        )


@dataclass
class Workflow:
    """工作流"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    nodes: List[WorkflowNode] = field(default_factory=list)
    edges: List[WorkflowEdge] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'nodes': [node.to_dict() for node in self.nodes],
            'edges': [edge.to_dict() for edge in self.edges],
            'variables': self.variables,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Workflow':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', ''),
            description=data.get('description', ''),
            nodes=[WorkflowNode.from_dict(n) for n in data.get('nodes', [])],
            edges=[WorkflowEdge.from_dict(e) for e in data.get('edges', [])],
            variables=data.get('variables', {}),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat())
        )

    def add_node(self, node: WorkflowNode):
        """添加节点"""
        self.nodes.append(node)
        self.updated_at = datetime.now().isoformat()

    def add_edge(self, edge: WorkflowEdge):
        """添加连接"""
        self.edges.append(edge)
        self.updated_at = datetime.now().isoformat()

    def remove_node(self, node_id: str):
        """删除节点"""
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [e for e in self.edges if e.source != node_id and e.target != node_id]
        self.updated_at = datetime.now().isoformat()

    def remove_edge(self, edge_id: str):
        """删除连接"""
        self.edges = [e for e in self.edges if e.id != edge_id]
        self.updated_at = datetime.now().isoformat()

    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        """获取节点"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def validate(self) -> tuple[bool, str]:
        """验证工作流"""
        # 检查是否有开始节点
        start_nodes = [n for n in self.nodes if n.type == NodeType.START]
        if not start_nodes:
            return False, "缺少开始节点"

        # 检查是否有结束节点
        end_nodes = [n for n in self.nodes if n.type == NodeType.END]
        if not end_nodes:
            return False, "缺少结束节点"

        # 检查连接是否有效
        node_ids = {n.id for n in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids:
                return False, f"连接源节点不存在: {edge.source}"
            if edge.target not in node_ids:
                return False, f"连接目标节点不存在: {edge.target}"

        for node in self.nodes:
            if node.type == NodeType.LLM and not node.config.get('prompt'):
                return False, f"LLM 节点缺少提示模板: {node.label or node.id}"
            if node.type == NodeType.AGENT and not node.config.get('prompt'):
                return False, f"Agent 节点缺少提示模板: {node.label or node.id}"
            if node.type == NodeType.CONDITION and not node.config.get('condition'):
                return False, f"条件节点缺少表达式: {node.label or node.id}"
            if node.type == NodeType.API and not node.config.get('url'):
                return False, f"API 节点缺少 URL: {node.label or node.id}"
            if node.type == NodeType.MERGE and not node.config.get('source_vars'):
                return False, f"合流节点缺少来源变量: {node.label or node.id}"

        return True, "验证通过"


class WorkflowExecutor:
    """工作流执行器"""

    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        self.context = {}
        self.execution_log = []
        self.max_steps = 200

    def execute(self, input_data: dict = None, callback=None) -> dict:
        """执行工作流"""
        # 验证工作流
        valid, message = self.workflow.validate()
        if not valid:
            return {
                'success': False,
                'error': message
            }

        # 初始化上下文
        self.context = self._build_initial_context(input_data or {})
        self.execution_log = []

        # 查找开始节点
        start_nodes = [n for n in self.workflow.nodes if n.type == NodeType.START]
        if not start_nodes:
            return {
                'success': False,
                'error': '未找到开始节点'
            }

        # 从开始节点执行
        try:
            self._execute_node(start_nodes[0], callback, depth=0)
            return {
                'success': True,
                'context': self.context,
                'log': self.execution_log
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'log': self.execution_log
            }

    def _execute_node(self, node: WorkflowNode, callback=None, depth: int = 0):
        """执行单个节点"""
        if depth > self.max_steps:
            raise RuntimeError('工作流执行超过最大步数限制')

        self.execution_log.append({
            'node_id': node.id,
            'node_type': node.type,
            'node_label': node.label,
            'timestamp': datetime.now().isoformat()
        })

        if callback:
            callback({
                'type': 'node_start',
                'node': node.to_dict()
            })

        # 根据节点类型执行
        if node.type == NodeType.START:
            self._execute_start_node(node)
        elif node.type == NodeType.END:
            self._execute_end_node(node)
            if callback:
                callback({
                    'type': 'node_complete',
                    'node': node.to_dict(),
                    'context': self.context
                })
            return
        elif node.type == NodeType.LLM:
            self._execute_llm_node(node)
        elif node.type == NodeType.AGENT:
            self._execute_agent_node(node)
        elif node.type == NodeType.CODE:
            self._execute_code_node(node)
        elif node.type == NodeType.CONDITION:
            self._execute_condition_node(node, callback, depth)
            return  # 条件节点自己处理后续流程
        elif node.type == NodeType.TRANSFORM:
            self._execute_transform_node(node)
        elif node.type == NodeType.API:
            self._execute_api_node(node)
        elif node.type == NodeType.LOOP:
            self._execute_loop_node(node)
        elif node.type == NodeType.MERGE:
            self._execute_merge_node(node)

        if callback:
            callback({
                'type': 'node_complete',
                'node': node.to_dict(),
                'context': self.context
            })

        # 查找下一个节点
        next_edges = [e for e in self.workflow.edges if e.source == node.id]
        for edge in next_edges:
            next_node = self.workflow.get_node(edge.target)
            if next_node:
                self._execute_node(next_node, callback, depth + 1)

    def _build_initial_context(self, input_data: dict) -> dict:
        """合并流程默认变量与运行时输入。"""
        context: Dict[str, Any] = {}
        for key, value in (self.workflow.variables or {}).items():
            if isinstance(value, dict) and ('value' in value or 'type' in value or 'description' in value):
                context[key] = value.get('value')
            else:
                context[key] = value
        context.update(input_data)
        return context

    def _resolve_template(self, value: Any) -> Any:
        """把 {var} 模板替换成上下文里的值。"""
        if value is None:
            return value
        if isinstance(value, dict):
            return {key: self._resolve_template(val) for key, val in value.items()}
        if isinstance(value, list):
            return [self._resolve_template(item) for item in value]
        if not isinstance(value, str):
            return value

        def replace(match):
            key = match.group(1)
            resolved = self.context.get(key, "")
            if isinstance(resolved, (dict, list)):
                return json.dumps(resolved, ensure_ascii=False)
            return str(resolved)

        return re.sub(r'\{([^{}]+)\}', replace, value)

    def _parse_json_like(self, value: str, default: Any):
        """尽量把字符串解析成 JSON。"""
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return default

    def _safe_eval(self, expression: str) -> Any:
        """在受限上下文里执行简单表达式。"""
        safe_globals = {"__builtins__": {}, "len": len, "sum": sum, "min": min, "max": max, "any": any, "all": all}
        return eval(expression, safe_globals, dict(self.context))

    def _execute_start_node(self, node: WorkflowNode):
        """执行开始节点。"""
        config = node.config or {}
        output_var = config.get('output_var')
        if output_var:
            self.context[output_var] = dict(self.context)

    def _execute_end_node(self, node: WorkflowNode):
        """执行结束节点。"""
        config = node.config or {}
        response_template = config.get('response_template')
        output_key = config.get('output_key', 'final_answer')

        if response_template:
            resolved = self._resolve_template(response_template)
            self.context[output_key] = resolved
            self.context['final_output'] = resolved
        elif output_key in self.context:
            self.context['final_output'] = self.context[output_key]

    def _execute_agent_node(self, node: WorkflowNode):
        """执行 Agent 节点"""
        config = node.config
        agent_type = config.get('agent_type', 'general')
        prompt = self._resolve_template(config.get('prompt', ''))
        system_prompt = self._resolve_template(config.get('system_prompt', ''))
        model = config.get('model', 'auto')

        # 这里应该调用实际的 Agent
        # 简化实现,直接返回模拟结果
        result = f"Agent ({agent_type}/{model}) 处理结果: {prompt}"
        if system_prompt:
            result = f"{system_prompt}\n{result}"
        output_var = config.get('output_var', 'result')
        self.context[output_var] = result

    def _execute_llm_node(self, node: WorkflowNode):
        """执行 LLM 节点。"""
        config = node.config or {}
        provider = config.get('provider', 'openai')
        model = config.get('model', 'gpt-4.1-mini')
        mode = config.get('completion_mode', 'chat')
        system_prompt = self._resolve_template(config.get('system_prompt', ''))
        prompt = self._resolve_template(config.get('prompt', ''))
        temperature = config.get('temperature', 0.7)
        top_p = config.get('top_p', 1)
        max_tokens = config.get('max_tokens', 1024)
        response_format = config.get('response_format', 'text')
        stop_words = config.get('stop', '')
        output_var = config.get('output_var', 'llm_result')

        response = {
            'provider': provider,
            'model': model,
            'mode': mode,
            'temperature': temperature,
            'top_p': top_p,
            'max_tokens': max_tokens,
            'response_format': response_format,
            'stop': stop_words,
            'system_prompt': system_prompt,
            'prompt': prompt,
            'text': f"LLM ({provider}/{model}) 响应: {prompt}",
        }
        self.context[output_var] = response
        self.context[f'{output_var}_text'] = response['text']

    def _execute_code_node(self, node: WorkflowNode):
        """Code nodes are disabled because the sandbox has been removed."""
        raise RuntimeError("Code sandbox support has been removed; code nodes are no longer available")


    def _execute_condition_node(self, node: WorkflowNode, callback=None, depth: int = 0):
        """执行条件节点"""
        config = node.config
        condition = self._resolve_template(config.get('condition', ''))

        # 简单的条件判断
        try:
            # 评估条件
            result = bool(self._safe_eval(condition))
            self.context[f"{node.id}_condition_result"] = result

            # 根据结果选择分支
            next_edges = [e for e in self.workflow.edges if e.source == node.id]
            matched = False
            for edge in next_edges:
                label = (edge.label or '').lower()
                if (result and label == 'true') or (not result and label == 'false'):
                    next_node = self.workflow.get_node(edge.target)
                    if next_node:
                        self._execute_node(next_node, callback, depth + 1)
                        matched = True
                    break
            if not matched:
                for edge in next_edges:
                    if not edge.label:
                        next_node = self.workflow.get_node(edge.target)
                        if next_node:
                            self._execute_node(next_node, callback, depth + 1)
                        break
        except Exception as e:
            self.execution_log.append({
                'error': f"条件判断失败: {str(e)}"
            })

    def _execute_transform_node(self, node: WorkflowNode):
        """执行转换节点"""
        config = node.config or {}
        transform_type = config.get('transform_type', 'template')
        output_var = config.get('output_var', 'transformed')
        template_value = self._resolve_template(config.get('template', ''))
        input_var = config.get('input_var', '')
        source_data = self.context.get(input_var) if input_var else self.context

        if transform_type == 'template':
            self.context[output_var] = template_value or source_data
            return

        if transform_type == 'json':
            parsed = self._parse_json_like(template_value, {})
            self.context[output_var] = parsed if parsed != {} or template_value == '{}' else template_value
            return

        if transform_type == 'text':
            self.context[output_var] = template_value
            return

        if transform_type == 'upper':
            self.context[output_var] = str(source_data).upper()
            return

        if transform_type == 'lower':
            self.context[output_var] = str(source_data).lower()
            return

        self.context[output_var] = source_data

    def _execute_api_node(self, node: WorkflowNode):
        """执行 API 节点。"""
        config = node.config or {}
        method = str(config.get('method', 'GET')).upper()
        url = self._resolve_template(config.get('url', ''))
        headers = self._parse_json_like(self._resolve_template(config.get('headers', '{}')), {})
        body = self._resolve_template(config.get('body', ''))
        output_var = config.get('output_var', 'api_result')
        timeout_ms = int(config.get('timeout_ms', 10000) or 10000)

        if not url:
            self.context[output_var] = {'error': 'API 节点缺少 URL'}
            return

        if url.startswith('mock://'):
            self.context[output_var] = {
                'mock': True,
                'url': url,
                'method': method,
                'headers': headers,
                'body': self._parse_json_like(body, body),
            }
            return

        request_body = None
        if method != 'GET' and body not in (None, ''):
            if isinstance(body, str):
                request_body = body.encode('utf-8')
            else:
                request_body = json.dumps(body, ensure_ascii=False).encode('utf-8')

        if method == 'GET' and body:
            params = self._parse_json_like(body, {})
            if isinstance(params, dict) and params:
                url = f"{url}?{urllib_parse.urlencode(params, doseq=True)}"

        request_obj = urllib_request.Request(url, data=request_body, method=method)
        for key, value in headers.items():
            request_obj.add_header(str(key), str(value))

        try:
            with urllib_request.urlopen(request_obj, timeout=timeout_ms / 1000) as response:
                raw = response.read().decode('utf-8')
                self.context[output_var] = {
                    'status': response.status,
                    'headers': dict(response.headers.items()),
                    'data': self._parse_json_like(raw, raw),
                }
        except urllib_error.HTTPError as exc:
            self.context[output_var] = {
                'status': exc.code,
                'error': exc.reason,
            }
        except Exception as exc:
            self.context[output_var] = {
                'error': str(exc),
            }

    def _execute_loop_node(self, node: WorkflowNode):
        """执行循环节点。"""
        config = node.config or {}
        loop_source = config.get('loop_source', 'items')
        item_var = config.get('item_var', 'item')
        max_iterations = int(config.get('max_iterations', 20) or 20)
        output_var = config.get('output_var', 'loop_result')

        items = self.context.get(loop_source, [])
        if not isinstance(items, list):
            items = [items]

        results = []
        for index, item in enumerate(items[:max_iterations]):
            entry = {
                'index': index,
                item_var: item,
            }
            results.append(entry)
        self.context[output_var] = results

    def _execute_merge_node(self, node: WorkflowNode):
        """执行合流节点。"""
        config = node.config or {}
        merge_mode = config.get('merge_mode', 'append')
        source_vars = [item.strip() for item in str(config.get('source_vars', '')).split(',') if item.strip()]
        output_var = config.get('output_var', 'merged')
        values = [self.context.get(name) for name in source_vars]

        if merge_mode == 'object':
            merged: Dict[str, Any] = {}
            for name, value in zip(source_vars, values):
                if isinstance(value, dict):
                    merged.update(value)
                else:
                    merged[name] = value
            self.context[output_var] = merged
            return

        if merge_mode == 'first_non_empty':
            for value in values:
                if value not in (None, '', [], {}):
                    self.context[output_var] = value
                    return
            self.context[output_var] = None
            return

        appended = []
        for value in values:
            if isinstance(value, list):
                appended.extend(value)
            elif value not in (None, ''):
                appended.append(value)
        self.context[output_var] = appended


# 工作流存储
_workflows: Dict[str, Workflow] = {}


def save_workflow(workflow: Workflow):
    """保存工作流"""
    _workflows[workflow.id] = workflow


def get_workflow(workflow_id: str) -> Optional[Workflow]:
    """获取工作流"""
    return _workflows.get(workflow_id)


def list_workflows() -> List[Workflow]:
    """列出所有工作流"""
    return list(_workflows.values())


def delete_workflow(workflow_id: str):
    """删除工作流"""
    if workflow_id in _workflows:
        del _workflows[workflow_id]
