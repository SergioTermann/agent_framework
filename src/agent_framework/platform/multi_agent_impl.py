"""
具体的协作 Agent 实现
====================

提供不同角色的 Agent 实现。
"""

from agent_framework.platform.multi_agent import CollaborativeAgent, AgentRole, AgentTask


class ResearcherAgent(CollaborativeAgent):
    """研究员 Agent - 负责信息收集和研究"""

    def __init__(self, agent_id: str, name: str, llm_provider=None):
        system_prompt = """你是一个专业的研究员,擅长:
- 收集和整理信息
- 分析和总结资料
- 提供准确的研究结果

请以专业、客观的方式完成研究任务。"""
        super().__init__(agent_id, AgentRole.RESEARCHER, name, system_prompt, llm_provider)

    def execute_task(self, task: AgentTask) -> str:
        """执行研究任务"""
        task.status = "in_progress"

        if not self.llm_provider:
            return f"研究任务: {task.description} (未配置 LLM)"

        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': f"请研究以下问题:\n{task.description}"}
        ]

        response = self.llm_provider.chat(messages)
        result = response.content if hasattr(response, 'content') else str(response)

        task.status = "completed"
        task.result = result
        self.completed_tasks.append(task)

        return result


class CoderAgent(CollaborativeAgent):
    """编码员 Agent - 负责编写代码"""

    def __init__(self, agent_id: str, name: str, llm_provider=None):
        system_prompt = """你是一个专业的程序员,擅长:
- 编写高质量、可维护的代码
- 代码优化和重构
- 解决编程问题

请提供完整、可运行的代码,并添加必要的注释。"""
        super().__init__(agent_id, AgentRole.CODER, name, system_prompt, llm_provider)

    def execute_task(self, task: AgentTask) -> str:
        """执行编码任务"""
        task.status = "in_progress"

        if not self.llm_provider:
            return f"编码任务: {task.description} (未配置 LLM)"

        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': f"请完成以下编程任务:\n{task.description}"}
        ]

        response = self.llm_provider.chat(messages)
        result = response.content if hasattr(response, 'content') else str(response)

        task.status = "completed"
        task.result = result
        self.completed_tasks.append(task)

        return result


class AnalystAgent(CollaborativeAgent):
    """分析师 Agent - 负责数据分析"""

    def __init__(self, agent_id: str, name: str, llm_provider=None):
        system_prompt = """你是一个专业的数据分析师,擅长:
- 数据分析和解读
- 趋势识别和预测
- 提供数据驱动的洞察

请提供清晰、有洞察力的分析结果。"""
        super().__init__(agent_id, AgentRole.ANALYST, name, system_prompt, llm_provider)

    def execute_task(self, task: AgentTask) -> str:
        """执行分析任务"""
        task.status = "in_progress"

        if not self.llm_provider:
            return f"分析任务: {task.description} (未配置 LLM)"

        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': f"请分析以下问题:\n{task.description}"}
        ]

        response = self.llm_provider.chat(messages)
        result = response.content if hasattr(response, 'content') else str(response)

        task.status = "completed"
        task.result = result
        self.completed_tasks.append(task)

        return result


class WriterAgent(CollaborativeAgent):
    """写作者 Agent - 负责内容创作"""

    def __init__(self, agent_id: str, name: str, llm_provider=None):
        system_prompt = """你是一个专业的写作者,擅长:
- 撰写清晰、流畅的文章
- 内容组织和结构化
- 语言润色和优化

请提供高质量、易读的内容。"""
        super().__init__(agent_id, AgentRole.WRITER, name, system_prompt, llm_provider)

    def execute_task(self, task: AgentTask) -> str:
        """执行写作任务"""
        task.status = "in_progress"

        if not self.llm_provider:
            return f"写作任务: {task.description} (未配置 LLM)"

        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': f"请完成以下写作任务:\n{task.description}"}
        ]

        response = self.llm_provider.chat(messages)
        result = response.content if hasattr(response, 'content') else str(response)

        task.status = "completed"
        task.result = result
        self.completed_tasks.append(task)

        return result


def create_default_agents(llm_provider) -> list[CollaborativeAgent]:
    """创建默认的 Agent 团队"""
    agents = [
        ResearcherAgent("researcher_1", "研究员 Alice", llm_provider),
        CoderAgent("coder_1", "程序员 Bob", llm_provider),
        AnalystAgent("analyst_1", "分析师 Charlie", llm_provider),
        WriterAgent("writer_1", "写作者 Diana", llm_provider),
    ]
    return agents
