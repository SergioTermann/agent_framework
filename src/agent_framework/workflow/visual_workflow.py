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
import uuid


class NodeType:
    """节点类型"""
    START = "start"
    END = "end"
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

        return True, "验证通过"


class WorkflowExecutor:
    """工作流执行器"""

    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        self.context = {}
        self.execution_log = []

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
        self.context = input_data or {}
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
            self._execute_node(start_nodes[0], callback)
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

    def _execute_node(self, node: WorkflowNode, callback=None):
        """执行单个节点"""
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
            pass  # 开始节点不需要执行
        elif node.type == NodeType.END:
            pass  # 结束节点不需要执行
        elif node.type == NodeType.AGENT:
            self._execute_agent_node(node)
        elif node.type == NodeType.CODE:
            self._execute_code_node(node)
        elif node.type == NodeType.CONDITION:
            self._execute_condition_node(node, callback)
            return  # 条件节点自己处理后续流程
        elif node.type == NodeType.TRANSFORM:
            self._execute_transform_node(node)

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
                self._execute_node(next_node, callback)

    def _execute_agent_node(self, node: WorkflowNode):
        """执行 Agent 节点"""
        config = node.config
        agent_type = config.get('agent_type', 'general')
        prompt = config.get('prompt', '')

        # 替换变量
        for key, value in self.context.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))

        # 这里应该调用实际的 Agent
        # 简化实现,直接返回模拟结果
        result = f"Agent ({agent_type}) 处理结果: {prompt}"
        output_var = config.get('output_var', 'result')
        self.context[output_var] = result

    def _execute_code_node(self, node: WorkflowNode):
        """Code nodes are disabled because the sandbox has been removed."""
        raise RuntimeError("Code sandbox support has been removed; code nodes are no longer available")


    def _execute_condition_node(self, node: WorkflowNode, callback=None):
        """执行条件节点"""
        config = node.config
        condition = config.get('condition', '')

        # 简单的条件判断
        try:
            # 替换变量
            for key, value in self.context.items():
                condition = condition.replace(f"{{{key}}}", str(value))

            # 评估条件
            result = eval(condition)

            # 根据结果选择分支
            next_edges = [e for e in self.workflow.edges if e.source == node.id]
            for edge in next_edges:
                if (result and edge.label == 'true') or (not result and edge.label == 'false'):
                    next_node = self.workflow.get_node(edge.target)
                    if next_node:
                        self._execute_node(next_node, callback)
                    break
        except Exception as e:
            self.execution_log.append({
                'error': f"条件判断失败: {str(e)}"
            })

    def _execute_transform_node(self, node: WorkflowNode):
        """执行转换节点"""
        config = node.config
        transform_type = config.get('transform_type', 'map')
        input_var = config.get('input_var', '')
        output_var = config.get('output_var', 'transformed')

        if input_var in self.context:
            data = self.context[input_var]
            # 简单的转换逻辑
            if transform_type == 'upper':
                self.context[output_var] = str(data).upper()
            elif transform_type == 'lower':
                self.context[output_var] = str(data).lower()
            else:
                self.context[output_var] = data


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
