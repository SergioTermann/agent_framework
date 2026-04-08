"""
多 Agent 协作系统
==================

支持多个 Agent 之间的协作、通信和任务分配。

核心概念:
- Agent: 独立的智能体,具有特定的角色和能力
- Coordinator: 协调器,负责任务分配和结果聚合
- Message: Agent 之间的通信消息
- Task: 可分配的任务单元
"""

from __future__ import annotations
import agent_framework.core.fast_json as json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from datetime import datetime
from enum import Enum


class AgentRole(Enum):
    """Agent 角色类型"""
    COORDINATOR = "coordinator"  # 协调器
    RESEARCHER = "researcher"    # 研究员
    CODER = "coder"             # 编码员
    ANALYST = "analyst"         # 分析师
    WRITER = "writer"           # 写作者
    REVIEWER = "reviewer"       # 审查员
    EXECUTOR = "executor"       # 执行者


class MessageType(Enum):
    """消息类型"""
    TASK_ASSIGN = "task_assign"      # 任务分配
    TASK_RESULT = "task_result"      # 任务结果
    QUESTION = "question"            # 提问
    ANSWER = "answer"                # 回答
    COLLABORATION = "collaboration"  # 协作请求
    STATUS_UPDATE = "status_update"  # 状态更新


@dataclass
class Message:
    """Agent 之间的通信消息"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = ""
    to_agent: str = ""
    type: MessageType = MessageType.COLLABORATION
    content: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'from_agent': self.from_agent,
            'to_agent': self.to_agent,
            'type': self.type.value,
            'content': self.content,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }


@dataclass
class AgentTask:
    """可分配的任务"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    assigned_to: Optional[str] = None
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'description': self.description,
            'assigned_to': self.assigned_to,
            'status': self.status,
            'result': self.result,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'completed_at': self.completed_at
        }


class CollaborativeAgent:
    """协作 Agent 基类"""

    def __init__(
        self,
        agent_id: str,
        role: AgentRole,
        name: str,
        system_prompt: str,
        llm_provider=None
    ):
        self.agent_id = agent_id
        self.role = role
        self.name = name
        self.system_prompt = system_prompt
        self.llm_provider = llm_provider
        self.message_queue: list[Message] = []
        self.task_queue: list[AgentTask] = []
        self.completed_tasks: list[AgentTask] = []

    def receive_message(self, message: Message):
        """接收消息"""
        self.message_queue.append(message)

    def send_message(self, to_agent: str, msg_type: MessageType, content: str, metadata: dict = None) -> Message:
        """发送消息"""
        message = Message(
            from_agent=self.agent_id,
            to_agent=to_agent,
            type=msg_type,
            content=content,
            metadata=metadata or {}
        )
        return message

    def assign_task(self, task: AgentTask):
        """分配任务"""
        task.assigned_to = self.agent_id
        task.status = "pending"
        self.task_queue.append(task)

    def execute_task(self, task: AgentTask) -> str:
        """执行任务 - 子类需要实现"""
        raise NotImplementedError

    def process_messages(self) -> list[Message]:
        """处理消息队列"""
        responses = []
        while self.message_queue:
            message = self.message_queue.pop(0)
            response = self._handle_message(message)
            if response:
                responses.append(response)
        return responses

    def _handle_message(self, message: Message) -> Optional[Message]:
        """处理单个消息"""
        if message.type == MessageType.TASK_ASSIGN:
            # 处理任务分配
            task_data = message.metadata.get('task')
            if task_data:
                task = AgentTask(**task_data)
                self.assign_task(task)
        elif message.type == MessageType.QUESTION:
            # 处理提问
            answer = self._answer_question(message.content)
            return self.send_message(
                message.from_agent,
                MessageType.ANSWER,
                answer
            )
        return None

    def _answer_question(self, question: str) -> str:
        """回答问题"""
        if not self.llm_provider:
            return "无法回答,未配置 LLM"

        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': question}
        ]
        response = self.llm_provider.chat(messages)
        return response.content if hasattr(response, 'content') else str(response)

    def to_dict(self) -> dict:
        return {
            'agent_id': self.agent_id,
            'role': self.role.value,
            'name': self.name,
            'task_queue_size': len(self.task_queue),
            'completed_tasks': len(self.completed_tasks)
        }


class AgentCoordinator:
    """Agent 协调器 - 负责任务分配和结果聚合"""

    def __init__(self, llm_provider=None):
        self.agents: dict[str, CollaborativeAgent] = {}
        self.message_bus: list[Message] = []
        self.tasks: dict[str, AgentTask] = {}
        self.llm_provider = llm_provider

    def register_agent(self, agent: CollaborativeAgent):
        """注册 Agent"""
        self.agents[agent.agent_id] = agent

    def create_task(self, description: str, metadata: dict = None) -> AgentTask:
        """创建任务"""
        task = AgentTask(description=description, metadata=metadata or {})
        self.tasks[task.id] = task
        return task

    def assign_task(self, task: AgentTask, agent_id: str):
        """分配任务给指定 Agent"""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} 不存在")

        agent = self.agents[agent_id]
        agent.assign_task(task)

        # 发送任务分配消息
        message = Message(
            from_agent="coordinator",
            to_agent=agent_id,
            type=MessageType.TASK_ASSIGN,
            content=f"分配任务: {task.description}",
            metadata={'task': task.to_dict()}
        )
        self.send_message(message)

    def auto_assign_task(self, task: AgentTask) -> Optional[str]:
        """自动分配任务给最合适的 Agent"""
        if not self.agents:
            return None

        # 简单策略: 根据任务描述选择合适的 Agent
        task_lower = task.description.lower()

        # 优先级匹配
        if any(keyword in task_lower for keyword in ['代码', '编程', 'code', 'python', 'java']):
            coder_agents = [a for a in self.agents.values() if a.role == AgentRole.CODER]
            if coder_agents:
                agent = coder_agents[0]
                self.assign_task(task, agent.agent_id)
                return agent.agent_id

        if any(keyword in task_lower for keyword in ['分析', '数据', 'analyze', 'data']):
            analyst_agents = [a for a in self.agents.values() if a.role == AgentRole.ANALYST]
            if analyst_agents:
                agent = analyst_agents[0]
                self.assign_task(task, agent.agent_id)
                return agent.agent_id

        if any(keyword in task_lower for keyword in ['研究', '调查', 'research', 'investigate']):
            researcher_agents = [a for a in self.agents.values() if a.role == AgentRole.RESEARCHER]
            if researcher_agents:
                agent = researcher_agents[0]
                self.assign_task(task, agent.agent_id)
                return agent.agent_id

        # 默认分配给第一个可用的 Agent
        agent = list(self.agents.values())[0]
        self.assign_task(task, agent.agent_id)
        return agent.agent_id

    def send_message(self, message: Message):
        """发送消息到消息总线"""
        self.message_bus.append(message)

        # 路由消息到目标 Agent
        if message.to_agent in self.agents:
            self.agents[message.to_agent].receive_message(message)

    def process_messages(self):
        """处理所有 Agent 的消息"""
        for agent in self.agents.values():
            responses = agent.process_messages()
            for response in responses:
                self.send_message(response)

    def execute_collaborative_task(self, user_query: str, callback: Callable = None) -> dict:
        """执行协作任务"""
        # 1. 分解任务
        subtasks = self._decompose_task(user_query)

        # 2. 分配任务
        task_assignments = {}
        for subtask_desc in subtasks:
            task = self.create_task(subtask_desc)
            agent_id = self.auto_assign_task(task)
            task_assignments[task.id] = agent_id

            if callback:
                callback({
                    'type': 'task_assigned',
                    'task': task.to_dict(),
                    'agent_id': agent_id
                })

        # 3. 执行任务
        results = {}
        for task_id, agent_id in task_assignments.items():
            task = self.tasks[task_id]
            agent = self.agents[agent_id]

            if callback:
                callback({
                    'type': 'task_executing',
                    'task': task.to_dict(),
                    'agent': agent.to_dict()
                })

            # 执行任务
            try:
                result = agent.execute_task(task)
                task.status = "completed"
                task.result = result
                task.completed_at = datetime.now().isoformat()
                results[task_id] = result

                if callback:
                    callback({
                        'type': 'task_completed',
                        'task': task.to_dict(),
                        'result': result
                    })
            except Exception as e:
                task.status = "failed"
                task.result = f"执行失败: {str(e)}"
                results[task_id] = task.result

                if callback:
                    callback({
                        'type': 'task_failed',
                        'task': task.to_dict(),
                        'error': str(e)
                    })

        # 4. 聚合结果
        final_result = self._aggregate_results(user_query, results)

        if callback:
            callback({
                'type': 'all_completed',
                'final_result': final_result
            })

        return {
            'query': user_query,
            'subtasks': [self.tasks[tid].to_dict() for tid in task_assignments.keys()],
            'results': results,
            'final_result': final_result
        }

    def _decompose_task(self, user_query: str) -> list[str]:
        """分解任务为子任务"""
        if not self.llm_provider:
            # 简单分解
            return [user_query]

        prompt = f"""请将以下任务分解为3-5个可以并行执行的子任务。
每个子任务应该清晰、具体、可执行。

任务: {user_query}

请以 JSON 数组格式返回子任务列表,例如:
["子任务1", "子任务2", "子任务3"]
"""

        messages = [{'role': 'user', 'content': prompt}]
        response = self.llm_provider.chat(messages)
        content = response.content if hasattr(response, 'content') else str(response)

        try:
            # 尝试解析 JSON
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                subtasks = json.loads(json_match.group())
                return subtasks
        except:
            pass

        # 解析失败,返回原始任务
        return [user_query]

    def _aggregate_results(self, user_query: str, results: dict[str, str]) -> str:
        """聚合多个 Agent 的结果"""
        if not self.llm_provider:
            # 简单聚合
            return "\n\n".join([f"结果 {i+1}:\n{result}" for i, result in enumerate(results.values())])

        results_text = "\n\n".join([
            f"子任务 {i+1} 结果:\n{result}"
            for i, result in enumerate(results.values())
        ])

        prompt = f"""请根据以下子任务的执行结果,生成一个完整、连贯的最终答案。

原始问题: {user_query}

子任务结果:
{results_text}

请综合以上结果,给出一个完整的答案:
"""

        messages = [{'role': 'user', 'content': prompt}]
        response = self.llm_provider.chat(messages)
        return response.content if hasattr(response, 'content') else str(response)

    def get_status(self) -> dict:
        """获取协调器状态"""
        return {
            'agents': [agent.to_dict() for agent in self.agents.values()],
            'total_tasks': len(self.tasks),
            'pending_tasks': len([t for t in self.tasks.values() if t.status == 'pending']),
            'completed_tasks': len([t for t in self.tasks.values() if t.status == 'completed']),
            'message_queue_size': len(self.message_bus)
        }
