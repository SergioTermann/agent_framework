from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterable, Optional

from agent_framework.memory.reme_sidecar import ReMeSidecarClient, ReMeSidecarLauncher, build_targets

if TYPE_CHECKING:
    from agent_framework.memory.system import Memory


def _parse_dt(value: str | None) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now()
    for parser in (datetime.fromisoformat, lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S")):
        try:
            return parser(raw)
        except ValueError:
            continue
    return datetime.now()


def _to_memory(memory_payload: dict[str, Any]):
    from agent_framework.memory.system import Memory

    metadata = dict(memory_payload.get("metadata") or {})
    context = dict(metadata.get("context") or {})
    return Memory(
        id=str(memory_payload.get("memory_id") or ""),
        content=str(memory_payload.get("content") or ""),
        memory_type=str(metadata.get("agent_memory_type") or metadata.get("memory_type") or "semantic"),
        importance=float(metadata.get("importance") or memory_payload.get("score") or 0.5),
        created_at=_parse_dt(metadata.get("created_at") or memory_payload.get("time_created")),
        last_accessed=_parse_dt(metadata.get("last_accessed") or memory_payload.get("time_modified") or memory_payload.get("time_created")),
        access_count=int(metadata.get("access_count") or 0),
        tags=list(metadata.get("tags") or []),
        context=context,
        embedding=None,
        scope=str(metadata.get("scope") or "global"),
        confidence=float(metadata.get("confidence") or 0.6),
        status=str(metadata.get("status") or "active"),
        source=str(metadata.get("source") or ""),
        retrieval_success=float(metadata.get("retrieval_success") or 0.0),
        last_feedback_at=_parse_dt(metadata.get("last_feedback_at")) if metadata.get("last_feedback_at") else None,
    )


class ReMeProxyStore:
    def __init__(self, *, client: ReMeSidecarClient, launcher: ReMeSidecarLauncher | None = None):
        self.client = client
        self.launcher = launcher

    def _ensure_ready(self) -> None:
        if self.launcher:
            self.launcher.ensure_started(self.client)
        else:
            self.client.health()

    @staticmethod
    def _target_kind(memory: Memory) -> str:
        return "task" if memory.memory_type == "procedural" else "user"

    @staticmethod
    def _target_name(memory: Memory) -> str:
        context = dict(memory.context or {})
        scope_path = list(context.get("scope_path") or [])
        if scope_path:
            return str(scope_path[0])
        return str(context.get("scope") or memory.scope or "global")

    @staticmethod
    def _reme_metadata_type(memory: Memory) -> str:
        mapping = {
            "semantic": "personal",
            "episodic": "history",
            "procedural": "procedural",
            "working": "summary",
            "tool": "tool",
        }
        return mapping.get(memory.memory_type, "personal")

    @staticmethod
    def _metadata_from_memory(memory: Memory) -> dict[str, Any]:
        return {
            "memory_type": ReMeProxyStore._reme_metadata_type(memory),
            "agent_memory_type": memory.memory_type,
            "importance": memory.importance,
            "tags": list(memory.tags or []),
            "context": dict(memory.context or {}),
            "created_at": memory.created_at.isoformat(),
            "last_accessed": memory.last_accessed.isoformat(),
            "access_count": memory.access_count,
            "scope": memory.scope,
            "confidence": memory.confidence,
            "status": memory.status,
            "source": memory.source,
            "retrieval_success": memory.retrieval_success,
            "last_feedback_at": memory.last_feedback_at.isoformat() if memory.last_feedback_at else None,
        }

    def store_memory(self, memory: "Memory") -> str:
        self._ensure_ready()
        payload = {
            "target_kind": self._target_kind(memory),
            "target_name": self._target_name(memory),
            "memory_content": memory.content,
            "when_to_use": "",
            "message_time": memory.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "author": memory.source or "agent_framework",
            "score": memory.importance,
            "metadata": self._metadata_from_memory(memory),
        }
        node = self.client.add_memory(payload)
        return str(node.get("memory_id") or "")

    def retrieve_memory(self, memory_id: str, touch: bool = True) -> Optional["Memory"]:
        self._ensure_ready()
        try:
            memory = _to_memory(self.client.get_memory(memory_id))
        except Exception:
            return None
        if touch:
            memory.access_count += 1
            memory.last_accessed = datetime.now()
            self.update_memory(memory_id, context_updates={"access_count": memory.access_count, "last_accessed": memory.last_accessed.isoformat()})
        return memory

    def list_memories(
        self,
        memory_type: str | None = None,
        limit: int = 100,
        user_id: str | None = None,
        scopes: Iterable[str] | None = None,
    ) -> list["Memory"]:
        self._ensure_ready()
        memory_types = [memory_type] if memory_type else None
        payload = {
            "limit": limit,
            "targets": build_targets(scopes=scopes, user_id=user_id, memory_types=memory_types),
        }
        results = [_to_memory(item) for item in self.client.list_memories(payload)]
        if memory_type:
            results = [memory for memory in results if memory.memory_type == memory_type]
        return results[:limit]

    def search_memories(
        self,
        query: str,
        memory_type: str | None = None,
        memory_types: Iterable[str] | None = None,
        limit: int = 5,
        similarity_threshold: float = 0.0,
        user_id: str | None = None,
        scopes: Iterable[str] | None = None,
        **_: Any,
    ) -> list[tuple["Memory", float]]:
        self._ensure_ready()
        selected_types = list(memory_types or ([] if memory_type is None else [memory_type]))
        payload = {
            "query": query,
            "limit": limit,
            "targets": build_targets(scopes=scopes, user_id=user_id, memory_types=selected_types),
        }
        results: list[tuple[Memory, float]] = []
        for item in self.client.search_memories(payload):
            memory = _to_memory(item)
            if selected_types and memory.memory_type not in selected_types:
                continue
            score = float(item.get("score") or memory.importance or 0.0)
            if score < similarity_threshold:
                continue
            results.append((memory, score))
        return results[:limit]

    def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
        context_updates: dict[str, Any] | None = None,
        touch: bool = False,
    ) -> Optional["Memory"]:
        existing = self.retrieve_memory(memory_id, touch=False)
        if existing is None:
            return None
        if content is not None:
            existing.content = content
        if importance is not None:
            existing.importance = importance
        if tags is not None:
            existing.tags = list(tags)
        if context_updates:
            if "access_count" in context_updates:
                existing.access_count = int(context_updates["access_count"])
            if "last_accessed" in context_updates:
                existing.last_accessed = _parse_dt(str(context_updates["last_accessed"]))
            existing.context.update({k: v for k, v in context_updates.items() if k not in {"access_count", "last_accessed"}})
        if touch:
            existing.last_accessed = datetime.now()
            existing.access_count += 1

        payload = {
            "memory_id": memory_id,
            "target_kind": self._target_kind(existing),
            "target_name": self._target_name(existing),
            "memory_content": existing.content,
            "score": existing.importance,
            "metadata": self._metadata_from_memory(existing),
        }
        return _to_memory(self.client.update_memory(payload))

    def record_feedback(
        self,
        memory_ids: Iterable[str],
        outcome: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        feedback_key = str(outcome or "retrieved").strip().lower() or "retrieved"
        for memory_id in memory_ids:
            existing = self.retrieve_memory(memory_id, touch=False)
            if existing is None:
                continue
            context = dict(existing.context or {})
            feedback = dict(context.get("feedback") or {})
            feedback[feedback_key] = int(feedback.get(feedback_key, 0) or 0) + 1
            context["feedback"] = feedback
            if metadata:
                context["feedback_meta"] = dict(metadata)
            self.update_memory(memory_id, context_updates=context)
