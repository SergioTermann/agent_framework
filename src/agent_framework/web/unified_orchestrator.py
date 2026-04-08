"""
统一编排层
==========

把对话、RAG、记忆、微调模型路由、Agent 执行与反馈闭环串成一个入口。
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import threading
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent_framework.agent import AgentBuilder
from agent_framework.agent.callbacks import CallbackManager, TokenCounter
from agent_framework.agent.openai_agents import (
    agents_sdk_is_available,
    build_agent_instructions,
    run_openai_agents,
)
from agent_framework.agent.thread import collect_tool_calls, latest_assistant_message
from agent_framework.core.config import get_config
from agent_framework.web.context_builder import ContextBuilder, ContextBundle
from agent_framework.web.conversation_manager import ConversationManager, ConversationStorage
from agent_framework.reasoning.feedback_loop import FeedbackLoop
from agent_framework.agent.llm import OpenAICompatibleProvider
from agent_framework.reasoning.model_router import ModelRouter, RouteDecision
from agent_framework.reasoning.model_serving import get_model_serving_manager
from agent_framework.tool.registry import ToolRegistry
from agent_framework.tool.middleware import create_tool_hook_middleware, create_tool_result_limit_middleware
from agent_framework.tool.permissions import ToolPermissionHook
from agent_framework.tools import register_selected_tools, resolve_tool_specs
from agent_framework.memory.system import get_memory_manager


class UnifiedOrchestrator:
    """统一调度入口。"""

    def __init__(self):
        self.config = get_config()
        self.conversation_manager = ConversationManager(ConversationStorage())
        self.context_builder = ContextBuilder(self.conversation_manager)
        self.model_router = ModelRouter()
        self.model_serving_manager = get_model_serving_manager()
        self.feedback_loop = FeedbackLoop()
        self.memory_manager = get_memory_manager()
        self._default_tool_result_limit = 4000

    def chat(
        self,
        *,
        user_input: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        mode: str = "auto",
        use_agent: Optional[bool] = None,
        knowledge_base_ids: Optional[List[str]] = None,
        prefer_finetuned: bool = False,
        endpoint_id: str = "",
        model_name: str = "",
        base_url: str = "",
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        user_input = (user_input or "").strip()
        if not user_input:
            raise ValueError("user_input is required")
        metadata = dict(metadata or {})
        for endpoint_type in ("embedding", "rerank"):
            override_endpoint_id = str(metadata.get(f"{endpoint_type}_endpoint_id") or "").strip()
            if not override_endpoint_id:
                continue
            endpoint = self.model_serving_manager.get_endpoint(override_endpoint_id)
            if endpoint is None:
                raise ValueError(f"{endpoint_type} endpoint not found: {override_endpoint_id}")
            if endpoint.status != "running":
                raise ValueError(f"{endpoint_type} endpoint is not running: {override_endpoint_id}")
            if getattr(endpoint, "endpoint_type", "chat") != endpoint_type:
                raise ValueError(f"Endpoint {override_endpoint_id} is not a {endpoint_type} endpoint")

        conversation = self._resolve_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            title=title or self._build_title(user_input),
        )

        user_message = self.conversation_manager.add_user_message(
            conversation.conversation_id,
            user_input,
            metadata=metadata,
        )

        route = self.model_router.decide(
            user_input=user_input,
            mode=mode,
            use_agent=use_agent,
            knowledge_base_ids=knowledge_base_ids,
            prefer_finetuned=prefer_finetuned,
            endpoint_id=endpoint_id,
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
        )

        context = self.context_builder.build(
            conversation_id=conversation.conversation_id,
            user_input=user_input,
            user_id=user_id,
            knowledge_base_ids=knowledge_base_ids if route.use_rag else [],
            metadata=metadata,
            enable_knowledge_retrieval=route.use_rag,
            retrieval_options={
                "embedding_endpoint_id": str(metadata.get("embedding_endpoint_id") or "").strip(),
                "rerank_endpoint_id": str(metadata.get("rerank_endpoint_id") or "").strip(),
            },
            token_budget=int(metadata.get("context_token_budget", 0) or 0) or None,
        )

        if route.use_agent:
            generation = self._run_agent(
                user_input=user_input,
                context=context,
                route=route,
                metadata=metadata,
            )
        else:
            generation = self._run_chat_completion(
                context=context,
                route=route,
                metadata=metadata,
            )

        assistant_metadata = {
            "route": {
                "mode": route.mode,
                "reason": route.reason,
                "model_source": route.target.source,
                "endpoint_id": route.target.endpoint_id,
                "backend": route.target.backend,
            },
            "retrieval": {
                "working_memory_count": len(getattr(context, "working_memories", []) or []),
                "memory_count": len(context.memories),
                "memory_ids": [item.memory_id for item in context.memories],
                "working_memory_ids": [item.memory_id for item in getattr(context, "working_memories", []) or []],
                "knowledge_count": len(context.knowledge_chunks),
                "knowledge_base_ids": knowledge_base_ids or [],
                "embedding_endpoint_id": str(metadata.get("embedding_endpoint_id") or "").strip(),
                "rerank_endpoint_id": str(metadata.get("rerank_endpoint_id") or "").strip(),
                "plan": context.retrieval_plan,
            },
            "generation": generation.get("metadata", {}),
        }

        assistant_message = self.conversation_manager.add_assistant_message(
            conversation.conversation_id,
            generation["reply"],
            model=route.target.model,
            tokens=generation.get("tokens"),
            tool_calls=generation.get("tool_calls") or [],
            metadata=assistant_metadata,
        )

        retrieval_results = {
            "retrieval_plan": context.retrieval_plan,
            "conversation_summary": context.conversation_summary,
            "working_memories": [asdict(item) for item in getattr(context, "working_memories", []) or []],
            "memories": [asdict(item) for item in context.memories],
            "knowledge_chunks": [asdict(item) for item in context.knowledge_chunks],
            "recent_messages": [
                {
                    "message_id": msg.message_id,
                    "role": msg.role.value,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                }
                for msg in context.recent_messages
            ],
            "token_stats": context.token_stats,
        }
        causal_result = self._build_causal_result(
            user_input=user_input,
            context=context,
            metadata=metadata,
        )
        model_info = self._build_model_info(
            route=route,
            metadata=metadata,
            context=context,
        )

        # 后台异步存储记忆和反馈（避免阻塞响应）
        def _background_storage():
            try:
                self._store_turn_memory(
                    conversation_id=conversation.conversation_id,
                    user_id=user_id,
                    user_input=user_input,
                    assistant_reply=generation["reply"],
                    mode=route.mode,
                    metadata=metadata,
                )
            except Exception:
                pass
            try:
                retrieved_memory_ids = [
                    *[item.memory_id for item in context.memories],
                    *[item.memory_id for item in getattr(context, "working_memories", []) or []],
                ]
                if retrieved_memory_ids:
                    self.memory_manager.record_retrieval_outcome(
                        retrieved_memory_ids,
                        "retrieved",
                        metadata={
                            "conversation_id": conversation.conversation_id,
                            "task_type": context.retrieval_plan.get("task_type"),
                        },
                    )
            except Exception:
                pass
            try:
                self.feedback_loop.capture_interaction(
                    conversation_id=conversation.conversation_id,
                    user_id=user_id,
                    user_input=user_input,
                    assistant_reply=generation["reply"],
                    route={
                        "mode": route.mode,
                        "reason": route.reason,
                        "model": route.target.model,
                        "base_url": route.target.base_url,
                        "model_source": route.target.source,
                        "endpoint_id": route.target.endpoint_id,
                    },
                    context={
                        "working_memory_count": len(getattr(context, "working_memories", []) or []),
                        "memory_count": len(context.memories),
                        "knowledge_count": len(context.knowledge_chunks),
                        "has_summary": bool(context.conversation_summary),
                        "retrieval_plan": context.retrieval_plan,
                    },
                )
            except Exception:
                pass

        thread = threading.Thread(target=_background_storage, daemon=True)
        thread.start()

        return {
            "success": True,
            "conversation_id": conversation.conversation_id,
            "user_message_id": user_message.message_id,
            "assistant_message_id": assistant_message.message_id,
            "reply": generation["reply"],
            "answer": generation["reply"],
            "route": {
                "mode": route.mode,
                "reason": route.reason,
                "model": route.target.model,
                "base_url": route.target.base_url,
                "model_source": route.target.source,
                "endpoint_id": route.target.endpoint_id,
            },
            "context": {
                "retrieval_plan": context.retrieval_plan,
                "conversation_summary": context.conversation_summary,
                "working_memories": [asdict(item) for item in getattr(context, "working_memories", []) or []],
                "memories": [asdict(item) for item in context.memories],
                "knowledge_chunks": [asdict(item) for item in context.knowledge_chunks],
                "recent_messages": [
                    {
                        "message_id": msg.message_id,
                        "role": msg.role.value,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                    }
                    for msg in context.recent_messages
                ],
            },
            "retrieval_results": retrieval_results,
            "causal_result": causal_result,
            "model_info": model_info,
            "usage": generation.get("usage", {}),
            "timestamp": datetime.now().isoformat(),
        }

    def submit_feedback(
        self,
        *,
        conversation_id: str,
        rating: int,
        feedback: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if rating < 1 or rating > 5:
            raise ValueError("rating must be between 1 and 5")

        conversation, messages = self.conversation_manager.get_conversation_history(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation not found: {conversation_id}")

        self.conversation_manager.rate_conversation(conversation_id, rating, feedback=feedback)
        self.feedback_loop.capture_feedback(
            conversation_id=conversation_id,
            rating=rating,
            feedback=feedback,
            metadata=metadata,
        )
        try:
            assistant_messages = [msg for msg in messages if msg.role.value == "assistant"]
            if assistant_messages:
                latest_assistant = assistant_messages[-1]
                retrieval_meta = dict((latest_assistant.metadata or {}).get("retrieval") or {})
                memory_ids = [
                    *list(retrieval_meta.get("memory_ids") or []),
                    *list(retrieval_meta.get("working_memory_ids") or []),
                ]
                if memory_ids:
                    outcome = "positive" if rating >= 4 else "negative" if rating <= 2 else "retrieved"
                    self.memory_manager.record_retrieval_outcome(
                        memory_ids,
                        outcome,
                        metadata={
                            "conversation_id": conversation_id,
                            "rating": rating,
                            "feedback": feedback,
                        },
                    )
        except Exception:
            pass

        return {
            "success": True,
            "conversation_id": conversation_id,
            "rating": rating,
            "feedback": feedback,
            "message_count": len(messages),
        }

    def _resolve_conversation(self, conversation_id: Optional[str], user_id: Optional[str], title: str):
        if conversation_id:
            conversation = self.conversation_manager.storage.get_conversation(conversation_id)
            if conversation is None:
                raise ValueError(f"Conversation not found: {conversation_id}")
            return conversation
        return self.conversation_manager.create_conversation(title=title, user_id=user_id)

    def _run_chat_completion(
        self,
        *,
        context: ContextBundle,
        route: RouteDecision,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metadata = metadata or {}
        provider = OpenAICompatibleProvider(
            api_key=route.target.api_key,
            model=route.target.model,
            base_url=route.target.base_url,
            timeout=self.config.llm.timeout,
        )

        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(
                    has_knowledge=bool(context.knowledge_chunks),
                    metadata=metadata,
                ),
            }
        ]

        assistant_context = self._build_assistant_context(metadata)
        if assistant_context:
            messages.append({
                "role": "system",
                "content": assistant_context,
            })

        supplemental_context = context.as_prefetch_text()
        if supplemental_context:
            messages.append({
                "role": "system",
                "content": f"可用补充上下文如下，请优先利用，但不要编造：\n\n{supplemental_context}",
            })

        messages.extend(context.recent_messages_for_llm())

        # ── 工具 function calling（Chat 模式轻量版）───────────────────────
        enable_tools = metadata.get("enable_tools", False)
        tools_schema: list[dict] | None = None
        tool_registry: Optional[ToolRegistry] = None

        if enable_tools:
            user_id = metadata.get("user_id", "")
            specs = resolve_tool_specs(
                allowed_tools=metadata.get("allowed_tools"),
                blocked_tools=metadata.get("blocked_tools"),
                toolsets=metadata.get("toolsets") or metadata.get("toolset"),
                include_plugin_tools=bool(metadata.get("include_plugin_tools", True)),
                user_id=user_id,
            )
            if specs:
                tools_schema = [s.to_llm_format() for s in specs]
                tool_registry = self._build_runtime_tool_registry(specs=specs, metadata=metadata)

        response = provider.chat(
            messages=messages,
            tools=tools_schema,
            temperature=self.config.agent.temperature,
            max_tokens=self.config.agent.max_tokens,
            top_p=self.config.agent.top_p,
            frequency_penalty=self.config.agent.frequency_penalty,
            presence_penalty=self.config.agent.presence_penalty,
        )

        all_tool_calls: List[Dict[str, Any]] = []
        max_tool_rounds = 5

        # tool calling 循环
        while response.has_tool_calls and tool_registry and max_tool_rounds > 0:
            max_tool_rounds -= 1

            # 把 assistant 的 tool_calls 消息追加到 messages
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if response.content:
                assistant_msg["content"] = response.content
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                }
                for tc in response.tool_calls
            ]
            messages.append(assistant_msg)

            # 逐个执行工具并拼 tool result messages
            for tc in response.tool_calls:
                all_tool_calls.append({
                    "call_id": tc.call_id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                })
                if tc.name not in tool_registry:
                    result_str = f"Unknown tool: {tc.name}"
                else:
                    try:
                        result_str = str(tool_registry.dispatch(tc.name, tc.arguments))
                    except Exception as e:
                        result_str = f"Error: {e}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.call_id,
                    "content": result_str,
                })

            # 带工具结果再调 LLM
            response = provider.chat(
                messages=messages,
                tools=tools_schema,
                temperature=self.config.agent.temperature,
                max_tokens=self.config.agent.max_tokens,
                top_p=self.config.agent.top_p,
                frequency_penalty=self.config.agent.frequency_penalty,
                presence_penalty=self.config.agent.presence_penalty,
            )

        return {
            "reply": (response.content or "").strip(),
            "tokens": response.usage.get("total_tokens"),
            "usage": response.usage,
            "tool_calls": all_tool_calls,
            "metadata": {
                "generation_type": "chat_completion",
                "tool_call_count": len(all_tool_calls),
            },
        }

    def _run_agent(
        self,
        *,
        user_input: str,
        context: ContextBundle,
        route: RouteDecision,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metadata = metadata or {}
        backend = str(metadata.get("agent_backend") or "openai_agents_sdk").strip().lower()
        prefer_openai_agents = backend not in {"legacy", "legacy_runner", "custom"}

        if prefer_openai_agents and agents_sdk_is_available():
            tool_specs = resolve_tool_specs(
                allowed_tools=metadata.get("allowed_tools"),
                blocked_tools=metadata.get("blocked_tools"),
                toolsets=metadata.get("toolsets") or metadata.get("toolset"),
                include_plugin_tools=bool(metadata.get("include_plugin_tools", True)),
                user_id=metadata.get("user_id", ""),
            )
            system_prompt = self._build_system_prompt(
                has_knowledge=bool(context.knowledge_chunks),
                metadata=metadata,
            )
            assistant_context = self._build_assistant_context(metadata)
            instructions = build_agent_instructions(
                system_prompt=system_prompt,
                assistant_context=assistant_context,
                prefetch_context=context.as_prefetch_text(),
            )
            agent_name = "Assistant"
            if metadata.get("assistant_profile") == "wind_maintenance":
                agent_name = "椋庣數杩愮淮鏅哄鍔╂墜"

            result = run_openai_agents(
                user_input=user_input,
                instructions=instructions,
                tool_specs=tool_specs,
                tool_dispatcher=self._build_runtime_tool_registry(
                    specs=tool_specs,
                    metadata=metadata,
                ).dispatch,
                api_key=route.target.api_key,
                model=route.target.model,
                base_url=route.target.base_url,
                timeout=self.config.llm.timeout,
                max_turns=self.config.agent.max_rounds,
                temperature=self.config.agent.temperature,
                max_tokens=self.config.agent.max_tokens,
                top_p=self.config.agent.top_p,
                frequency_penalty=self.config.agent.frequency_penalty,
                presence_penalty=self.config.agent.presence_penalty,
                workflow_name="unified_orchestrator_agent",
                conversation_id=context.conversation_id,
                agent_name=agent_name,
            )
            return {
                "reply": result.reply,
                "tokens": result.usage.get("total_tokens") or None,
                "usage": result.usage,
                "tool_calls": result.tool_calls,
                "metadata": result.metadata,
            }

        legacy_result = self._run_legacy_agent(
            user_input=user_input,
            context=context,
            route=route,
            metadata=metadata,
        )
        if prefer_openai_agents and not agents_sdk_is_available():
            legacy_result.setdefault("metadata", {})
            legacy_result["metadata"]["agent_backend"] = "legacy"
            legacy_result["metadata"]["agent_backend_reason"] = "openai_agents_sdk_unavailable"
        else:
            legacy_result.setdefault("metadata", {})
            legacy_result["metadata"].setdefault("agent_backend", "legacy")
        return legacy_result

    def _build_runtime_tool_registry(
        self,
        *,
        specs: List[Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ToolRegistry:
        metadata = metadata or {}
        registry = ToolRegistry()
        registry.use(
            create_tool_result_limit_middleware(
                lambda: int(metadata.get("max_tool_result_chars", 0) or 0) or self._default_tool_result_limit
            )
        )
        permission_hook = ToolPermissionHook.from_raw(metadata.get("tool_permission_rules"))
        if permission_hook is not None:
            registry.use(create_tool_hook_middleware([permission_hook]))
        for spec in specs:
            registry.add(spec)
        return registry

    def _run_legacy_agent(
        self,
        *,
        user_input: str,
        context: ContextBundle,
        route: RouteDecision,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        callbacks = CallbackManager()
        token_counter = TokenCounter()
        callbacks.on("llm_end", token_counter.on_llm_end)

        builder = (
            AgentBuilder()
            .with_openai(
                api_key=route.target.api_key,
                model=route.target.model,
                base_url=route.target.base_url,
                timeout=self.config.llm.timeout,
            )
            .with_temperature(self.config.agent.temperature)
            .with_max_tokens(self.config.agent.max_tokens)
            .with_top_p(self.config.agent.top_p)
            .with_frequency_penalty(self.config.agent.frequency_penalty)
            .with_presence_penalty(self.config.agent.presence_penalty)
            .with_max_rounds(self.config.agent.max_rounds)
            .with_callbacks(callbacks)
            .with_tool_permission_rules(metadata.get("tool_permission_rules") if metadata else None)
            .with_tool_result_limit(
                int((metadata or {}).get("max_tool_result_chars", 0) or 0) or self._default_tool_result_limit
            )
        )

        metadata = metadata or {}
        if metadata.get("assistant_profile") == "wind_maintenance":
            builder = (
                builder
                .with_name("风电运维智导助手")
                .with_role("聚焦风机告警分析、根因定位、排查步骤和安全处置建议。")
            )

        register_selected_tools(
            builder,
            allowed_tools=metadata.get("allowed_tools"),
            blocked_tools=metadata.get("blocked_tools"),
            toolsets=metadata.get("toolsets") or metadata.get("toolset"),
            include_plugin_tools=bool(metadata.get("include_plugin_tools", True)),
            user_id=metadata.get("user_id", ""),
        )

        runner = builder.build()
        assistant_context = self._build_assistant_context(metadata)
        prefetch_context = context.as_prefetch_text()
        if assistant_context:
            prefetch_context = (
                f"{assistant_context}\n\n{prefetch_context}".strip()
                if prefetch_context
                else assistant_context
            )
        thread = runner.launch(
            user_input,
            prefetch_context=prefetch_context,
        )

        reply = latest_assistant_message(thread)
        tool_calls = collect_tool_calls(thread)

        return {
            "reply": reply.strip(),
            "tokens": token_counter.total_tokens or None,
            "usage": {
                "total_tokens": token_counter.total_tokens,
                "prompt_tokens": token_counter.prompt_tokens,
                "completion_tokens": token_counter.completion_tokens,
                "calls": token_counter.calls,
            },
            "tool_calls": tool_calls,
            "metadata": {
                "generation_type": "agent",
                "thread_id": thread.thread_id,
                "tool_call_count": len(tool_calls),
                "agent_backend": "legacy",
            },
        }

    def _store_turn_memory(
        self,
        *,
        conversation_id: str,
        user_id: Optional[str],
        user_input: str,
        assistant_reply: str,
        mode: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.memory_manager.capture_turn(
            conversation_id=conversation_id,
            user_id=user_id,
            user_input=user_input,
            assistant_reply=assistant_reply,
            mode=mode,
            metadata=metadata or {},
        )
        return
        """
        选择性存储记忆（避免与对话历史重复）

        存储策略：
        - 对话历史已持久化到 ConversationStorage，无需重复存
        - 仅在以下情况存储到长期记忆：
          1. 用户明确要求记住（"记住"、"保存"等关键词）
          2. 重要决策或配置变更
          3. 错误和解决方案
        """
        # 检查是否包含记忆触发关键词
        memory_triggers = [
            "记住", "保存", "记录", "别忘了",
            "remember", "save", "keep in mind",
            "配置", "设置", "修改",
            "错误", "问题", "解决",
        ]

        should_store = any(kw in user_input.lower() for kw in memory_triggers)

        # Agent 模式的重要交互也存储（工具调用 > 3 次）
        if mode == "agent" and len(assistant_reply) > 500:
            should_store = True

        if not should_store:
            return

        content = (
            f"会话 {conversation_id}\n"
            f"用户：{user_input.strip()}\n"
            f"助手：{assistant_reply.strip()}"
        ).strip()

        if len(content) < 20:
            return

        importance = 0.7 if mode == "agent" else 0.6
        self.memory_manager.add_episodic_memory(
            content=content,
            context={
                "conversation_id": conversation_id,
                "user_id": user_id,
                "mode": mode,
                "source": "unified_orchestrator",
            },
            importance=importance,
            tags=[mode, "conversation_turn", "important"],
        )

    @staticmethod
    def _build_title(user_input: str) -> str:
        title = " ".join((user_input or "").split())
        return title[:40] or "新对话"

    @staticmethod
    def _build_system_prompt(has_knowledge: bool, metadata: Optional[Dict[str, Any]] = None) -> str:
        metadata = metadata or {}
        prompt = [
            "你是统一编排后的 AI 助手。",
            "回答时请综合使用对话历史、召回记忆和给定知识。",
            "如果知识不足，请明确说明不确定，不要编造。",
        ]
        if metadata.get("assistant_profile") == "wind_maintenance":
            prompt.extend([
                "当前角色是风电运维智导助手，重点服务于风机告警分析、故障诊断、检修建议和安全提醒。",
                "优先输出：现象判断、可能根因、建议排查步骤、风险提示、是否需要升级专家支持。",
            ])
            if metadata.get("enable_causal"):
                prompt.append("回答时请尽量显式给出因果链路和根因排序。")
            if metadata.get("enable_rlhf"):
                prompt.append("请优先给出利于运维闭环执行的建议，步骤清晰、便于落实。")
        if has_knowledge:
            prompt.extend([
                "若答案明显依赖知识检索内容，请优先基于检索结果回答。",
                "若引用检索结果，请尽量在对应句末标注 [知识#序号]。",
            ])

        developer_system_prompt = str(metadata.get("developer_system_prompt") or "").strip()
        developer_answer_style = str(metadata.get("developer_answer_style") or "").strip()
        if developer_system_prompt:
            prompt.extend([
                "[开发版提示词覆写]",
                developer_system_prompt,
            ])
        if developer_answer_style:
            prompt.append(f"[开发版回答风格]\n{developer_answer_style}")
        return "\n".join(prompt)

    @staticmethod
    def _build_assistant_context(metadata: Dict[str, Any]) -> str:
        if not metadata:
            return ""

        asset_context = metadata.get("asset_context") or {}
        lines: List[str] = []

        if metadata.get("assistant_profile") == "wind_maintenance":
            lines.append("[助手设定]")
            lines.append("你正在处理风电运维诊断任务。")

        if asset_context:
            lines.append("[设备上下文]")
            field_map = {
                "farm_name": "场站",
                "turbine_id": "机组编号",
                "fault_code": "故障代码",
                "operating_mode": "运行工况",
                "symptom": "现场现象",
            }
            for key, label in field_map.items():
                value = str(asset_context.get(key, "") or "").strip()
                if value:
                    lines.append(f"- {label}: {value}")

        developer_context = str(metadata.get("developer_context") or "").strip()
        if developer_context:
            lines.append("[开发版附加上下文]")
            lines.append(developer_context)

        return "\n".join(lines).strip()

    def _build_causal_result(
        self,
        *,
        user_input: str,
        context: ContextBundle,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not metadata.get("enable_causal"):
            return {
                "enabled": False,
                "message": "本轮未启用因果分析。",
            }

        assistant_context = self._build_assistant_context(metadata)
        knowledge_hint = "\n".join(
            (
                f"- {item.citation_label or '知识'} | {item.kb_name}"
                f": {self._clip_text(item.snippet or item.content, 120)}"
            )
            for item in context.knowledge_chunks[:2]
        )
        analysis_context = "\n".join(
            part for part in [assistant_context, knowledge_hint] if part
        ).strip() or None

        try:
            from agent_framework.causal.causal_reasoning_engine import get_causal_engine

            engine = get_causal_engine()
            result = engine.root_cause_analysis(
                observed_effect=user_input,
                context=analysis_context,
                depth=3,
            )

            return {
                "enabled": True,
                "analysis_method": result.get("analysis_method", "Root Cause Analysis"),
                "confidence_score": result.get("confidence_score"),
                "observed_effect": result.get("observed_effect", user_input),
                "root_causes": result.get("root_causes", [])[:3],
                "recommended_actions": result.get("recommended_actions", [])[:3],
                "contributing_factors": result.get("contributing_factors", [])[:3],
            }
        except Exception:
            return self._fallback_causal_result(user_input)

    def _build_model_info(
        self,
        *,
        route: RouteDecision,
        metadata: Dict[str, Any],
        context: ContextBundle,
    ) -> Dict[str, Any]:
        endpoints = self.model_serving_manager.list_endpoints()
        running_endpoints = [ep for ep in endpoints if ep.status == "running"]
        finetuned_endpoints = [ep for ep in running_endpoints if ep.finetune_task_id]
        chat_endpoints = [ep for ep in running_endpoints if getattr(ep, "endpoint_type", "chat") == "chat"]
        embedding_endpoints = [ep for ep in running_endpoints if getattr(ep, "endpoint_type", "chat") == "embedding"]
        rerank_endpoints = [ep for ep in running_endpoints if getattr(ep, "endpoint_type", "chat") == "rerank"]

        selected_chat_endpoint_id = str(metadata.get("endpoint_id") or route.target.endpoint_id or "").strip()
        selected_embedding_endpoint_id = str(metadata.get("embedding_endpoint_id") or "").strip()
        selected_rerank_endpoint_id = str(metadata.get("rerank_endpoint_id") or "").strip()

        selected_chat_endpoint = self.model_serving_manager.get_endpoint(selected_chat_endpoint_id) if selected_chat_endpoint_id else None
        selected_embedding_endpoint = (
            self.model_serving_manager.get_endpoint(selected_embedding_endpoint_id)
            if selected_embedding_endpoint_id else None
        )
        selected_rerank_endpoint = (
            self.model_serving_manager.get_endpoint(selected_rerank_endpoint_id)
            if selected_rerank_endpoint_id else None
        )

        rlhf_stats: Dict[str, Any] = {
            "enabled_for_this_turn": bool(metadata.get("enable_rlhf")),
            "feedback_loop_enabled": True,
        }

        try:
            from agent_framework.reasoning.llm_rlhf_engine import get_llm_rlhf_engine

            engine = get_llm_rlhf_engine()
            rlhf_stats.update(engine.get_stats())
            rlhf_stats["reward_model_info"] = engine.get_reward_model_info()
        except Exception as e:
            rlhf_stats["error"] = str(e)

        return {
            "assistant_profile": metadata.get("assistant_profile", "general"),
            "current_model": route.target.model,
            "model_source": route.target.source,
            "base_url": route.target.base_url,
            "endpoint_id": route.target.endpoint_id,
            "backend": route.target.backend,
            "selected_chat_endpoint_id": selected_chat_endpoint_id,
            "selected_chat_endpoint_name": getattr(selected_chat_endpoint, "model_name", "") or "",
            "selected_embedding_endpoint_id": selected_embedding_endpoint_id,
            "selected_embedding_endpoint_name": getattr(selected_embedding_endpoint, "model_name", "") or "",
            "selected_rerank_endpoint_id": selected_rerank_endpoint_id,
            "selected_rerank_endpoint_name": getattr(selected_rerank_endpoint, "model_name", "") or "",
            "agent_enabled": route.use_agent,
            "retrieval_enabled": route.use_rag,
            "causal_enabled": bool(metadata.get("enable_causal")),
            "prefer_finetuned": bool(metadata.get("prefer_finetuned")),
            "selected_knowledge_base_ids": metadata.get("selected_knowledge_base_ids", []),
            "memory_hits": len(context.memories),
            "knowledge_hits": len(context.knowledge_chunks),
            "available_endpoints": len(endpoints),
            "running_endpoints": len(running_endpoints),
            "chat_endpoints": len(chat_endpoints),
            "embedding_endpoints": len(embedding_endpoints),
            "rerank_endpoints": len(rerank_endpoints),
            "available_finetuned_endpoints": len(finetuned_endpoints),
            "rlhf": rlhf_stats,
        }

    @staticmethod
    def _fallback_causal_result(user_input: str) -> Dict[str, Any]:
        text = (user_input or "").strip()
        lowered = text.lower()
        keyword_map = [
            ("振动", "传动链磨损、对中偏差或轴承状态异常"),
            ("温度", "润滑不足、冷却异常或电气负载升高"),
            ("偏航", "偏航编码器、偏航电机或风向跟踪异常"),
            ("变桨", "变桨驱动、液压/电机执行器或叶片角度反馈异常"),
            ("功率", "来风条件变化、限功率策略或部件效率下降"),
            ("alarm", "控制系统告警、传感器异常或保护逻辑触发"),
        ]

        inferred_causes = [
            description for keyword, description in keyword_map
            if keyword in text or keyword in lowered
        ] or [
            "需要结合告警、SCADA 趋势和检修记录进一步判断根因"
        ]

        return {
            "enabled": True,
            "analysis_method": "Heuristic fallback",
            "confidence_score": 0.42,
            "observed_effect": text,
            "root_causes": [
                {
                    "cause": cause,
                    "confidence": round(max(0.3, 0.75 - idx * 0.12), 2),
                    "category": "技术因素",
                    "severity": "中",
                    "causal_chain": [text, cause],
                    "evidence": [],
                }
                for idx, cause in enumerate(inferred_causes[:3])
            ],
            "recommended_actions": [
                {
                    "action": "先核对最新告警、关键测点趋势和最近一次检修记录。",
                    "priority": "高",
                    "expected_impact": "快速缩小根因范围，避免误判。",
                },
                {
                    "action": "如风险持续上升，按现场规程执行限功率或停机检查。",
                    "priority": "高",
                    "expected_impact": "降低设备进一步损伤风险。",
                },
            ],
            "contributing_factors": [],
        }

    @staticmethod
    def _clip_text(text: str, max_len: int = 120) -> str:
        normalized = " ".join((text or "").split())
        if len(normalized) <= max_len:
            return normalized
        return normalized[: max_len - 3] + "..."


_orchestrator: Optional[UnifiedOrchestrator] = None


def get_unified_orchestrator() -> UnifiedOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = UnifiedOrchestrator()
    return _orchestrator
