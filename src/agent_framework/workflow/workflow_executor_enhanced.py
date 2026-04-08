"""
增强的工作流执行器
==================

集成所有高级功能的工作流执行引擎
"""

from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
import agent_framework.core.fast_json as json
import uuid

from agent_framework.workflow.visual_workflow import (
    Workflow, WorkflowNode, WorkflowEdge, NodeType,
    save_workflow, get_workflow
)
from agent_framework.workflow.workflow_advanced import (
    AdvancedNodeType, ExecutionContext, ExecutionStatus,
    LoopConfig, LoopExecutor,
    ParallelConfig, ParallelExecutor,
    RetryConfig, RetryExecutor,
    TryCatchConfig, TryCatchExecutor,
    SubflowConfig, SubflowExecutor,
    ScheduleConfig, ScheduleExecutor,
    WorkflowDebugger, WorkflowVersionControl
)
from agent_framework.infra.go_task_client import get_task_executor


class EnhancedWorkflowExecutor:
    """增强的工作流执行器"""

    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        self.debugger = WorkflowDebugger()
        self.version_control = WorkflowVersionControl()
        self.execution_history = []
        self.callbacks = []

    def _get_go_executor_if_available(self):
        executor = get_task_executor()
        return executor if executor.health_check() else None

    def _render_string_template(self, template: str, context: ExecutionContext) -> str:
        rendered = template
        for key, value in context.variables.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return rendered

    def _render_json_template(self, value: Any, context: ExecutionContext) -> Any:
        if isinstance(value, str):
            return self._render_string_template(value, context)
        if isinstance(value, list):
            return [self._render_json_template(item, context) for item in value]
        if isinstance(value, dict):
            return {k: self._render_json_template(v, context) for k, v in value.items()}
        return value

    def execute(self, input_data: Dict[str, Any] = None,
                debug_mode: bool = False) -> Dict[str, Any]:
        """执行工作流"""
        # 创建执行上下文
        context = ExecutionContext(
            workflow_id=self.workflow.id,
            variables=input_data or {}
        )
        context.status = ExecutionStatus.RUNNING
        context.start_time = datetime.now()

        try:
            # 验证工作流
            valid, message = self.workflow.validate()
            if not valid:
                raise ValueError(f"工作流验证失败: {message}")

            # 查找开始节点
            start_nodes = [n for n in self.workflow.nodes if n.type == NodeType.START]
            if not start_nodes:
                raise ValueError("未找到开始节点")

            # 执行工作流
            self._execute_node(start_nodes[0], context, debug_mode)

            context.status = ExecutionStatus.SUCCESS
            context.end_time = datetime.now()

            # 记录执行历史
            self._record_execution(context)

            return {
                'success': True,
                'execution_id': context.execution_id,
                'result': context.variables,
                'duration': (context.end_time - context.start_time).total_seconds()
            }

        except Exception as e:
            context.status = ExecutionStatus.FAILED
            context.end_time = datetime.now()
            context.error = str(e)

            self._record_execution(context)

            return {
                'success': False,
                'execution_id': context.execution_id,
                'error': str(e),
                'duration': (context.end_time - context.start_time).total_seconds() if context.end_time else 0
            }

    def _execute_node(self, node: WorkflowNode, context: ExecutionContext,
                      debug_mode: bool = False):
        """执行单个节点"""
        # 调试检查
        if debug_mode and self.debugger.should_pause(node.id, context):
            self.debugger.pause()
            self._notify_debug_pause(node, context)

        # 等待调试器恢复
        while self.debugger.paused:
            import time
            time.sleep(0.1)

        # 记录调用栈
        self.debugger.execution_stack.append({
            'node_id': node.id,
            'node_type': node.type,
            'timestamp': datetime.now().isoformat()
        })

        # 通知回调
        self._notify_callbacks('node_start', node, context)

        try:
            # 根据节点类型执行
            if node.type == NodeType.START:
                pass  # 开始节点不需要执行

            elif node.type == NodeType.END:
                pass  # 结束节点不需要执行

            elif node.type == NodeType.AGENT:
                self._execute_agent_node(node, context)

            elif node.type == NodeType.CODE:
                self._execute_code_node(node, context)

            elif node.type == NodeType.CONDITION:
                self._execute_condition_node(node, context, debug_mode)
                return  # 条件节点自己处理后续流程

            elif node.type == NodeType.TRANSFORM:
                self._execute_transform_node(node, context)

            elif node.type == NodeType.API:
                self._execute_api_node(node, context)

            # 高级节点类型
            elif node.type == AdvancedNodeType.LOOP:
                self._execute_loop_node(node, context, debug_mode)
                return  # 循环节点自己处理后续流程

            elif node.type == AdvancedNodeType.PARALLEL:
                self._execute_parallel_node(node, context, debug_mode)

            elif node.type == AdvancedNodeType.RETRY:
                self._execute_retry_node(node, context, debug_mode)

            elif node.type == AdvancedNodeType.TRY_CATCH:
                self._execute_try_catch_node(node, context, debug_mode)
                return  # try-catch节点自己处理后续流程

            elif node.type == AdvancedNodeType.SUBFLOW:
                self._execute_subflow_node(node, context)

            # 通知回调
            self._notify_callbacks('node_complete', node, context)

            # 执行下一个节点
            self._execute_next_nodes(node, context, debug_mode)

        except Exception as e:
            self._notify_callbacks('node_error', node, context, error=str(e))
            raise

        finally:
            # 弹出调用栈
            if self.debugger.execution_stack:
                self.debugger.execution_stack.pop()

    def _execute_agent_node(self, node: WorkflowNode, context: ExecutionContext):
        """执行Agent节点"""
        config = node.config
        agent_type = config.get('agent_type', 'general')
        prompt = config.get('prompt', '')
        model = config.get('model', 'gpt-4o')
        temperature = config.get('temperature', 0.7)

        # 替换变量
        for key, value in context.variables.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))

        # 调用实际的Agent
        try:
            from agent_framework.agent import AgentBuilder
            from agent_framework.agent.llm import get_llm_client

            # 根据 agent_type 构建不同的 Agent
            if agent_type == 'rag':
                # RAG Agent
                from agent_framework.vector_db.rag_agent import RAGAgent
                knowledge_base = config.get('knowledge_base', '')
                agent = RAGAgent(knowledge_base=knowledge_base)
                result = agent.query(prompt)

            elif agent_type == 'multi_agent':
                # 多 Agent 协作
                from agent_framework.platform.multi_agent_impl import MultiAgentSystem
                agents = config.get('agents', [])
                system = MultiAgentSystem()
                result = system.execute_task(prompt, agents)

            else:
                # 通用 Agent - 使用 LLM 直接调用
                llm_client = get_llm_client()
                system_prompt = config.get('system_prompt', '你是一个智能助手。')

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]

                response = llm_client.chat(messages, model=model, temperature=temperature)
                result = response.content if hasattr(response, 'content') else response

            output_var = config.get('output_var', 'result')
            context.set_variable(output_var, result)

        except Exception as e:
            raise Exception(f"Agent 执行失败: {str(e)}")

    def _execute_code_node(self, node: WorkflowNode, context: ExecutionContext):
        """Code nodes are disabled because the sandbox has been removed."""
        raise RuntimeError("Code sandbox support has been removed; code nodes can no longer run")


    def _execute_condition_node(self, node: WorkflowNode, context: ExecutionContext,
                                 debug_mode: bool = False):
        """执行条件节点"""
        config = node.config
        condition = config.get('condition', '')

        # 替换变量
        for key, value in context.variables.items():
            condition = condition.replace(f"{{{key}}}", repr(value))

        # 评估条件
        try:
            result = eval(condition)
        except Exception as e:
            raise Exception(f"条件评估失败: {str(e)}")

        # 根据结果选择分支
        next_edges = [e for e in self.workflow.edges if e.source == node.id]
        for edge in next_edges:
            if (result and edge.label == 'true') or (not result and edge.label == 'false'):
                next_node = self.workflow.get_node(edge.target)
                if next_node:
                    self._execute_node(next_node, context, debug_mode)
                break

    def _execute_transform_node(self, node: WorkflowNode, context: ExecutionContext):
        """Execute transform node."""
        config = node.config
        transform_type = config.get('transform_type', 'map')
        input_var = config.get('input_var', '')
        output_var = config.get('output_var', 'transformed')
        go_executor = self._get_go_executor_if_available()
        go_supported_transform_types = {'upper', 'lower', 'json_parse', 'json_stringify'}

        if input_var in context.variables:
            data = context.get_variable(input_var)

            if go_executor and transform_type in go_supported_transform_types:
                task = go_executor.submit_and_wait(
                    'transform_data',
                    {
                        'transform_type': transform_type,
                        'input_value': data
                    },
                    timeout=config.get('timeout', 30)
                )
                if task.get('status') != 'completed':
                    raise Exception(task.get('error') or f"Go transform task failed: {transform_type}")
                context.set_variable(output_var, task.get('result', {}).get('output'))
                return

            if transform_type == 'upper':
                context.set_variable(output_var, str(data).upper())
            elif transform_type == 'lower':
                context.set_variable(output_var, str(data).lower())
            elif transform_type == 'json_parse':
                context.set_variable(output_var, json.loads(str(data)))
            elif transform_type == 'json_stringify':
                context.set_variable(output_var, json.dumps(data))
            else:
                context.set_variable(output_var, data)

    def _execute_api_node(self, node: WorkflowNode, context: ExecutionContext):
        """Execute API node."""
        config = node.config
        method = config.get('method', 'GET')
        url = self._render_string_template(config.get('url', ''), context)
        headers = self._render_json_template(config.get('headers', {}), context)
        body = self._render_json_template(config.get('body', {}), context)
        output_var = config.get('output_var', 'api_result')
        timeout = config.get('timeout', 30)
        go_executor = self._get_go_executor_if_available()

        if go_executor:
            try:
                task = go_executor.submit_and_wait(
                    'http_request',
                    {
                        'method': method,
                        'url': url,
                        'headers': headers,
                        'body': body,
                        'timeout': timeout,
                    },
                    timeout=timeout + 5
                )
                if task.get('status') != 'completed':
                    raise Exception(task.get('error') or f"Go http task failed: {method} {url}")
                payload = task.get('result', {})
                context.set_variable(output_var, payload.get('body'))
                context.set_variable(f"{output_var}_status", payload.get('status_code'))
                return
            except Exception as e:
                raise Exception(f"API call failed: {str(e)}")

        import requests

        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, json=body, headers=headers, timeout=timeout)
            elif method.upper() == 'PUT':
                response = requests.put(url, json=body, headers=headers, timeout=timeout)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)
            elif method.upper() == 'PATCH':
                response = requests.patch(url, json=body, headers=headers, timeout=timeout)
            else:
                raise Exception(f"Unsupported HTTP method: {method}")

            try:
                result = response.json()
            except:
                result = response.text

            context.set_variable(output_var, result)
            context.set_variable(f"{output_var}_status", response.status_code)

        except Exception as e:
            raise Exception(f"API call failed: {str(e)}")

    def _execute_loop_node(self, node: WorkflowNode, context: ExecutionContext,
                           debug_mode: bool = False):
        """执行循环节点"""
        config = node.config
        loop_config = LoopConfig(
            loop_type=config.get('loop_type', 'count'),
            count=config.get('count', 1),
            condition=config.get('condition', ''),
            items_var=config.get('items_var', ''),
            item_var=config.get('item_var', 'item'),
            index_var=config.get('index_var', 'index'),
            max_iterations=config.get('max_iterations', 100)
        )

        # 查找循环体节点
        loop_body_edges = [e for e in self.workflow.edges if e.source == node.id and e.label == 'body']
        if not loop_body_edges:
            raise Exception("循环节点缺少循环体")

        loop_body_node = self.workflow.get_node(loop_body_edges[0].target)
        if not loop_body_node:
            raise Exception("循环体节点不存在")

        # 执行循环
        executor = LoopExecutor(loop_config)
        result = executor.execute(
            context,
            lambda n, ctx: self._execute_node(n, ctx, debug_mode),
            loop_body_node
        )

        # 保存循环结果
        output_var = config.get('output_var', 'loop_results')
        context.set_variable(output_var, result)

        # 执行循环后的节点
        next_edges = [e for e in self.workflow.edges if e.source == node.id and e.label != 'body']
        for edge in next_edges:
            next_node = self.workflow.get_node(edge.target)
            if next_node:
                self._execute_node(next_node, context, debug_mode)

    def _execute_parallel_node(self, node: WorkflowNode, context: ExecutionContext,
                                debug_mode: bool = False):
        """执行并行节点"""
        config = node.config
        parallel_config = ParallelConfig(
            branches=config.get('branches', []),
            wait_all=config.get('wait_all', True),
            timeout=config.get('timeout', 300),
            merge_results=config.get('merge_results', True)
        )

        # 查找所有分支节点
        branch_nodes = []
        for branch_id in parallel_config.branches:
            branch_node = self.workflow.get_node(branch_id)
            if branch_node:
                branch_nodes.append(branch_node)

        if not branch_nodes:
            raise Exception("并行节点缺少分支")

        # 执行并行
        executor = ParallelExecutor(parallel_config)
        result = executor.execute(
            context,
            lambda n, ctx: self._execute_node(n, ctx, debug_mode),
            branch_nodes
        )

        # 保存并行结果
        output_var = config.get('output_var', 'parallel_results')
        context.set_variable(output_var, result)

    def _execute_retry_node(self, node: WorkflowNode, context: ExecutionContext,
                            debug_mode: bool = False):
        """执行重试节点"""
        config = node.config
        retry_config = RetryConfig(
            max_retries=config.get('max_retries', 3),
            retry_delay=config.get('retry_delay', 1.0),
            backoff_multiplier=config.get('backoff_multiplier', 2.0),
            retry_on_errors=config.get('retry_on_errors', [])
        )

        # 查找目标节点
        target_edges = [e for e in self.workflow.edges if e.source == node.id]
        if not target_edges:
            raise Exception("重试节点缺少目标节点")

        target_node = self.workflow.get_node(target_edges[0].target)
        if not target_node:
            raise Exception("目标节点不存在")

        # 执行重试
        executor = RetryExecutor(retry_config)
        executor.execute(
            context,
            lambda n, ctx: self._execute_node(n, ctx, debug_mode),
            target_node
        )

    def _execute_try_catch_node(self, node: WorkflowNode, context: ExecutionContext,
                                 debug_mode: bool = False):
        """执行try-catch节点"""
        config = node.config
        try_catch_config = TryCatchConfig(
            try_node=config.get('try_node', ''),
            catch_node=config.get('catch_node', ''),
            finally_node=config.get('finally_node', ''),
            error_var=config.get('error_var', 'error')
        )

        # 查找try/catch/finally节点
        try_node = self.workflow.get_node(try_catch_config.try_node)
        catch_node = self.workflow.get_node(try_catch_config.catch_node) if try_catch_config.catch_node else None
        finally_node = self.workflow.get_node(try_catch_config.finally_node) if try_catch_config.finally_node else None

        if not try_node:
            raise Exception("try-catch节点缺少try块")

        # 执行try-catch
        executor = TryCatchExecutor(try_catch_config)
        result = executor.execute(
            context,
            lambda n, ctx: self._execute_node(n, ctx, debug_mode),
            try_node,
            catch_node,
            finally_node
        )

        # 保存结果
        output_var = config.get('output_var', 'try_catch_result')
        context.set_variable(output_var, result)

        # 执行后续节点
        next_edges = [e for e in self.workflow.edges
                      if e.source == node.id and e.label == 'next']
        for edge in next_edges:
            next_node = self.workflow.get_node(edge.target)
            if next_node:
                self._execute_node(next_node, context, debug_mode)

    def _execute_subflow_node(self, node: WorkflowNode, context: ExecutionContext):
        """执行子工作流节点"""
        config = node.config
        subflow_config = SubflowConfig(
            workflow_id=config.get('workflow_id', ''),
            input_mapping=config.get('input_mapping', {}),
            output_mapping=config.get('output_mapping', {})
        )

        # 执行子工作流
        executor = SubflowExecutor(subflow_config)
        result = executor.execute(
            context,
            lambda wf_id, ctx: self._execute_subworkflow(wf_id, ctx)
        )

        # 保存结果
        output_var = config.get('output_var', 'subflow_result')
        context.set_variable(output_var, result)

    def _execute_subworkflow(self, workflow_id: str, context: ExecutionContext) -> Dict[str, Any]:
        """执行子工作流"""
        subworkflow = get_workflow(workflow_id)
        if not subworkflow:
            raise Exception(f"子工作流不存在: {workflow_id}")

        sub_executor = EnhancedWorkflowExecutor(subworkflow)
        return sub_executor.execute(context.variables)

    def _execute_next_nodes(self, node: WorkflowNode, context: ExecutionContext,
                            debug_mode: bool = False):
        """执行下一个节点"""
        next_edges = [e for e in self.workflow.edges if e.source == node.id]
        for edge in next_edges:
            next_node = self.workflow.get_node(edge.target)
            if next_node:
                self._execute_node(next_node, context, debug_mode)

    def _record_execution(self, context: ExecutionContext):
        """记录执行历史"""
        self.execution_history.append({
            'execution_id': context.execution_id,
            'workflow_id': context.workflow_id,
            'status': context.status.value,
            'start_time': context.start_time.isoformat() if context.start_time else None,
            'end_time': context.end_time.isoformat() if context.end_time else None,
            'error': context.error,
            'variables': context.variables
        })

    def add_callback(self, callback: Callable):
        """添加回调函数"""
        self.callbacks.append(callback)

    def _notify_callbacks(self, event_type: str, node: WorkflowNode,
                          context: ExecutionContext, **kwargs):
        """通知回调"""
        for callback in self.callbacks:
            try:
                callback({
                    'type': event_type,
                    'node': node.to_dict(),
                    'context': {
                        'execution_id': context.execution_id,
                        'variables': context.variables,
                        'status': context.status.value
                    },
                    **kwargs
                })
            except Exception:
                pass  # 忽略回调错误

    def _notify_debug_pause(self, node: WorkflowNode, context: ExecutionContext):
        """通知调试暂停"""
        self._notify_callbacks('debug_pause', node, context,
                               watched_variables=self.debugger.get_watched_variables(context),
                               stack_trace=self.debugger.get_stack_trace())

    def get_execution_history(self, limit: int = 100) -> List[Dict]:
        """获取执行历史"""
        return self.execution_history[-limit:]

    def commit_version(self, message: str, user: str = "system") -> str:
        """提交工作流版本"""
        version = self.version_control.commit(
            self.workflow.id,
            self.workflow.to_dict(),
            message,
            user
        )
        return version.version_number

    def rollback_version(self, version_number: str) -> bool:
        """回滚到指定版本"""
        version = self.version_control.rollback(self.workflow.id, version_number)
        if version:
            # 恢复工作流数据
            self.workflow = Workflow.from_dict(version.workflow_data)
            return True
        return False
