from __future__ import annotations

from datetime import datetime

from agent_framework.memory.reme_proxy import ReMeProxyStore
from agent_framework.memory.system import Memory


class FakeLauncher:
    def __init__(self):
        self.ensure_started_calls = 0

    def ensure_started(self, client) -> None:
        self.ensure_started_calls += 1


class FakeReMeClient:
    def __init__(self):
        self.health_calls = 0
        self.last_add_payload = None
        self.last_list_payload = None
        self.last_search_payload = None
        self._counter = 0
        self._memories: dict[str, dict] = {}

    def health(self) -> dict:
        self.health_calls += 1
        return {"success": True, "status": "ok"}

    def add_memory(self, payload: dict) -> dict:
        self.last_add_payload = payload
        self._counter += 1
        memory_id = f"mem-{self._counter}"
        now = payload.get("message_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "memory_id": memory_id,
            "content": payload["memory_content"],
            "score": payload.get("score", 0.0),
            "metadata": dict(payload.get("metadata") or {}),
            "time_created": now,
            "time_modified": now,
            "target_kind": payload.get("target_kind"),
            "target_name": payload.get("target_name"),
        }
        self._memories[memory_id] = record
        return dict(record)

    def get_memory(self, memory_id: str) -> dict:
        if memory_id not in self._memories:
            raise RuntimeError("not_found")
        return dict(self._memories[memory_id])

    def update_memory(self, payload: dict) -> dict:
        memory_id = payload["memory_id"]
        if memory_id not in self._memories:
            raise RuntimeError("not_found")
        current = dict(self._memories[memory_id])
        updated = {
            **current,
            "content": payload.get("memory_content", current["content"]),
            "score": payload.get("score", current.get("score", 0.0)),
            "metadata": dict(payload.get("metadata") or current.get("metadata") or {}),
            "target_kind": payload.get("target_kind", current.get("target_kind")),
            "target_name": payload.get("target_name", current.get("target_name")),
            "time_modified": datetime.now().isoformat(),
        }
        self._memories[memory_id] = updated
        return dict(updated)

    def list_memories(self, payload: dict) -> list[dict]:
        self.last_list_payload = payload
        targets = {(item["kind"], item["target"]) for item in payload.get("targets") or []}
        results = []
        for item in self._memories.values():
            if targets and (item.get("target_kind"), item.get("target_name")) not in targets:
                continue
            results.append(dict(item))
        return results

    def search_memories(self, payload: dict) -> list[dict]:
        self.last_search_payload = payload
        query = str(payload.get("query") or "").lower()
        targets = {(item["kind"], item["target"]) for item in payload.get("targets") or []}
        matches = []
        for item in self._memories.values():
            if targets and (item.get("target_kind"), item.get("target_name")) not in targets:
                continue
            content = str(item.get("content") or "").lower()
            if query and query not in content:
                continue
            score = float(item.get("score") or 0.0)
            matches.append({**item, "score": score})
        matches.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        return matches[: int(payload.get("limit") or 5)]


def make_memory(*, memory_type: str, content: str, scope: str, tags: list[str] | None = None) -> Memory:
    now = datetime(2026, 3, 28, 12, 0, 0)
    return Memory(
        id="",
        content=content,
        memory_type=memory_type,
        importance=0.82,
        created_at=now,
        last_accessed=now,
        access_count=0,
        tags=list(tags or []),
        context={"scope": scope, "scope_path": [scope], "source": "test"},
        scope=scope,
        confidence=0.7,
        status="active",
        source="test-suite",
    )


def test_reme_proxy_store_maps_procedural_memory_to_task_target():
    client = FakeReMeClient()
    launcher = FakeLauncher()
    store = ReMeProxyStore(client=client, launcher=launcher)

    memory_id = store.store_memory(
        make_memory(
            memory_type="procedural",
            content="Inspect gearbox oil temperature before reset.",
            scope="conversation:42",
            tags=["procedure"],
        )
    )

    loaded = store.retrieve_memory(memory_id, touch=False)

    assert launcher.ensure_started_calls >= 2
    assert client.last_add_payload["target_kind"] == "task"
    assert client.last_add_payload["target_name"] == "conversation:42"
    assert client.last_add_payload["metadata"]["memory_type"] == "procedural"
    assert client.last_add_payload["metadata"]["agent_memory_type"] == "procedural"
    assert loaded is not None
    assert loaded.memory_type == "procedural"
    assert loaded.content == "Inspect gearbox oil temperature before reset."
    assert loaded.scope == "conversation:42"


def test_reme_proxy_store_touch_and_feedback_update_context():
    client = FakeReMeClient()
    store = ReMeProxyStore(client=client)
    memory_id = store.store_memory(
        make_memory(
            memory_type="semantic",
            content="User prefers concise Chinese replies.",
            scope="user:u-1",
            tags=["preference"],
        )
    )

    touched = store.retrieve_memory(memory_id, touch=True)
    updated = store.retrieve_memory(memory_id, touch=False)
    store.record_feedback([memory_id], "positive", metadata={"source": "unit-test"})
    with_feedback = store.retrieve_memory(memory_id, touch=False)

    assert touched is not None
    assert updated is not None
    assert updated.access_count == 1
    assert updated.last_accessed >= touched.last_accessed
    assert with_feedback is not None
    assert client.last_add_payload["metadata"]["memory_type"] == "personal"
    assert client.last_add_payload["metadata"]["agent_memory_type"] == "semantic"
    assert with_feedback.context["feedback"]["positive"] == 1
    assert with_feedback.context["feedback_meta"] == {"source": "unit-test"}
    assert with_feedback.context["scope_path"] == ["user:u-1"]


def test_reme_proxy_store_list_and_search_respect_type_filters():
    client = FakeReMeClient()
    store = ReMeProxyStore(client=client)

    store.store_memory(
        make_memory(
            memory_type="semantic",
            content="Wind turbine T-7 has a recurring yaw calibration issue.",
            scope="user:u-2",
            tags=["asset"],
        )
    )
    store.store_memory(
        make_memory(
            memory_type="procedural",
            content="Wind turbine restart checklist for maintenance mode.",
            scope="conversation:77",
            tags=["procedure"],
        )
    )

    listed = store.list_memories(memory_type="procedural", scopes=["conversation:77"])
    searched = store.search_memories(
        query="wind turbine",
        memory_types=["semantic"],
        scopes=["user:u-2"],
        limit=5,
        similarity_threshold=0.8,
    )

    assert len(listed) == 1
    assert listed[0].memory_type == "procedural"
    assert client.last_list_payload["targets"] == [{"kind": "task", "target": "conversation:77"}]
    assert len(searched) == 1
    assert searched[0][0].memory_type == "semantic"
    assert searched[0][1] == 0.82
    assert client.last_search_payload["targets"] == [{"kind": "user", "target": "user:u-2"}]
