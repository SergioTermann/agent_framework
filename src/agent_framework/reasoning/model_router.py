"""
统一模型路由器
==============

负责在基础模型、已部署微调模型、Agent 模式之间做选择。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from agent_framework.core.config import get_config
from agent_framework.reasoning.model_serving import get_model_serving_manager


@dataclass
class ModelTarget:
    model: str
    base_url: str
    api_key: str
    source: str
    endpoint_id: str = ""
    backend: str = ""


@dataclass
class RouteDecision:
    mode: str
    use_agent: bool
    use_rag: bool
    reason: str
    target: ModelTarget


class ModelRouter:
    """统一任务路由。"""

    def __init__(self):
        self.config = get_config()
        self.serving_manager = get_model_serving_manager()

    def decide(
        self,
        user_input: str,
        mode: str = "auto",
        use_agent: Optional[bool] = None,
        knowledge_base_ids: Optional[List[str]] = None,
        prefer_finetuned: bool = False,
        endpoint_id: str = "",
        model_name: str = "",
        base_url: str = "",
        api_key: Optional[str] = None,
    ) -> RouteDecision:
        explicit_mode = (mode or "auto").strip().lower()
        target = self._select_model(
            prefer_finetuned=prefer_finetuned,
            endpoint_id=endpoint_id,
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
        )

        if use_agent is None:
            resolved_use_agent = explicit_mode == "agent" or (
                explicit_mode == "auto" and self._looks_like_agent_task(user_input)
            )
        else:
            resolved_use_agent = bool(use_agent)

        resolved_use_rag = (
            explicit_mode in {"rag", "agent"}
            or bool(knowledge_base_ids)
            or (explicit_mode == "auto" and self._looks_like_knowledge_task(user_input))
        )

        if explicit_mode == "chat":
            resolved_use_agent = False
            resolved_use_rag = False
        elif explicit_mode == "rag":
            resolved_use_agent = False
            resolved_use_rag = True
        elif explicit_mode == "agent":
            resolved_use_agent = True
            resolved_use_rag = True

        resolved_mode = "agent" if resolved_use_agent else ("rag" if resolved_use_rag else "chat")

        return RouteDecision(
            mode=resolved_mode,
            use_agent=resolved_use_agent,
            use_rag=resolved_use_rag,
            reason=self._build_reason(
                explicit_mode=explicit_mode,
                use_agent=resolved_use_agent,
                use_rag=resolved_use_rag,
                target=target,
            ),
            target=target,
        )

    def _select_model(
        self,
        prefer_finetuned: bool,
        endpoint_id: str,
        model_name: str,
        base_url: str,
        api_key: Optional[str],
    ) -> ModelTarget:
        if model_name and base_url:
            return ModelTarget(
                model=model_name,
                base_url=base_url.rstrip("/"),
                api_key=api_key or "",
                source="request_override",
            )

        if endpoint_id:
            endpoint = self.serving_manager.get_endpoint(endpoint_id)
            if endpoint and endpoint.status == "running" and endpoint.endpoint_type == "chat":
                return ModelTarget(
                    model=endpoint.model_name,
                    base_url=endpoint.base_url.rstrip("/"),
                    api_key=endpoint.api_key or "",
                    source="registered_endpoint",
                    endpoint_id=endpoint.endpoint_id,
                    backend=endpoint.backend,
                )

        if prefer_finetuned:
            endpoint = self._first_running_endpoint()
            if endpoint:
                return ModelTarget(
                    model=endpoint.model_name,
                    base_url=endpoint.base_url.rstrip("/"),
                    api_key=endpoint.api_key or "",
                    source="finetuned_endpoint",
                    endpoint_id=endpoint.endpoint_id,
                    backend=endpoint.backend,
                )

        cfg = self.config.llm
        return ModelTarget(
            model=cfg.model,
            base_url=cfg.base_url.rstrip("/"),
            api_key=api_key if api_key is not None else cfg.api_key,
            source="default_config",
        )

    def _first_running_endpoint(self):
        return self.serving_manager.get_best_endpoint("chat")

    @staticmethod
    def _looks_like_agent_task(text: str) -> bool:
        text = (text or "").lower()
        keywords = [
            "步骤",
            "规划",
            "plan",
            "执行",
            "agent",
            "工作流",
            "workflow",
            "调用工具",
            "帮我完成",
            "自动",
            "先",
            "然后",
        ]
        return any(keyword in text for keyword in keywords) or len(text) > 180

    @staticmethod
    def _looks_like_knowledge_task(text: str) -> bool:
        text = (text or "").lower()
        keywords = [
            "知识库",
            "文档",
            "资料",
            "根据",
            "rag",
            "文件",
            "手册",
            "pdf",
        ]
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _build_reason(
        explicit_mode: str,
        use_agent: bool,
        use_rag: bool,
        target: ModelTarget,
    ) -> str:
        parts = [f"mode={explicit_mode}", f"model_source={target.source}"]
        if use_agent:
            parts.append("agent_enabled")
        if use_rag:
            parts.append("rag_enabled")
        return ", ".join(parts)
