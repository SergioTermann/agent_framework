from __future__ import annotations

from types import SimpleNamespace

import agent_framework.web.context_builder as context_builder_module
from agent_framework.web.context_builder import ContextBuilder
from agent_framework.web.conversation_manager import Message, MessageRole


_MESSAGE_SEQ = 0


class _FakeConversationManager:
    def __init__(self, messages):
        self._messages = messages

    def get_conversation_history(self, conversation_id):
        return object(), list(self._messages)


class _FakeMemoryStore:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def search_memories(self, **kwargs):
        self.calls += 1
        return list(self.results)


class _FakeMemoryManager:
    def __init__(self, results):
        self.store = _FakeMemoryStore(results)


class _PlanningMemoryManager(_FakeMemoryManager):
    def __init__(self, results, working_memories):
        super().__init__(results)
        self._working_memories = working_memories

    def build_retrieval_profile(self, **kwargs):
        return {
            "task_type": "continuation",
            "working_limit": 2,
            "memory_types": ["working", "episodic", "semantic"],
            "boost_by_type": {"working": 1.6, "episodic": 1.2, "semantic": 0.9},
            "retrieval_mode": "recent",
            "scopes": ["conversation:conv-1", "user:user-1", "global"],
        }

    def get_working_memories(self, **kwargs):
        return list(self._working_memories)


class _FakeKnowledgeManager:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def get_knowledge_base(self, kb_id):
        return SimpleNamespace(id=kb_id, name=kb_id)

    def list_knowledge_bases(self):
        return [SimpleNamespace(id="kb-1", name="KB-1")]

    def search(self, kb_id, query, top_k, **kwargs):
        self.calls += 1
        return list(self.results)


def _message(role: MessageRole, content: str) -> Message:
    global _MESSAGE_SEQ
    _MESSAGE_SEQ += 1
    return Message(
        message_id=f"msg-{_MESSAGE_SEQ}",
        conversation_id="conv-1",
        role=role,
        content=content,
        timestamp="2026-01-01T00:00:00",
    )


def test_context_builder_skips_memory_and_knowledge_for_simple_followup(monkeypatch):
    fake_memory = _FakeMemoryManager(
        [
            (
                SimpleNamespace(
                    id="mem-1",
                    content="历史记忆",
                    memory_type="episodic",
                    tags=[],
                    context={},
                ),
                0.9,
            )
        ]
    )
    fake_knowledge = _FakeKnowledgeManager(
        [{"id": "chunk-1", "content": "知识片段", "distance": 0.1, "metadata": {}}]
    )
    monkeypatch.setattr(context_builder_module, "get_memory_manager", lambda: fake_memory)
    monkeypatch.setattr(context_builder_module, "knowledge_manager", fake_knowledge)

    builder = ContextBuilder(
        _FakeConversationManager(
            [
                _message(MessageRole.USER, "偏航报警怎么处理"),
                _message(MessageRole.ASSISTANT, "先检查偏航电机和编码器。"),
            ]
        )
    )

    bundle = builder.build(
        conversation_id="conv-1",
        user_input="好的",
        knowledge_base_ids=["kb-1"],
        enable_knowledge_retrieval=True,
    )

    assert bundle.memories == []
    assert bundle.knowledge_chunks == []
    assert bundle.retrieval_plan["use_memory"] is False
    assert bundle.retrieval_plan["use_knowledge"] is False
    assert fake_memory.store.calls == 0
    assert fake_knowledge.calls == 0


def test_context_builder_uses_knowledge_for_domain_question(monkeypatch):
    fake_memory = _FakeMemoryManager([])
    fake_knowledge = _FakeKnowledgeManager(
        [
            {
                "id": "chunk-1",
                "content": "偏航报警可先检查风向标、编码器和偏航驱动。",
                "distance": 0.08,
                "metadata": {"doc_id": "doc-1"},
            }
        ]
    )
    monkeypatch.setattr(context_builder_module, "get_memory_manager", lambda: fake_memory)
    monkeypatch.setattr(context_builder_module, "knowledge_manager", fake_knowledge)

    builder = ContextBuilder(_FakeConversationManager([_message(MessageRole.USER, "你好")]))
    bundle = builder.build(
        conversation_id="conv-1",
        user_input="偏航报警频繁，给我排查步骤",
        knowledge_base_ids=["kb-1"],
        enable_knowledge_retrieval=True,
        rag_top_k=5,
    )

    assert bundle.retrieval_plan["use_knowledge"] is True
    assert bundle.retrieval_plan["rag_top_k"] >= 1
    assert len(bundle.knowledge_chunks) == 1
    assert fake_knowledge.calls == 1


def test_context_builder_uses_memory_when_query_references_history(monkeypatch):
    fake_memory = _FakeMemoryManager(
        [
            (
                SimpleNamespace(
                    id="mem-1",
                    content="上次诊断建议先查偏航编码器",
                    memory_type="episodic",
                    tags=[],
                    context={"user_id": "user-1"},
                ),
                0.91,
            )
        ]
    )
    fake_knowledge = _FakeKnowledgeManager([])
    monkeypatch.setattr(context_builder_module, "get_memory_manager", lambda: fake_memory)
    monkeypatch.setattr(context_builder_module, "knowledge_manager", fake_knowledge)

    builder = ContextBuilder(
        _FakeConversationManager(
            [
                _message(MessageRole.USER, "我们之前聊过偏航问题"),
                _message(MessageRole.ASSISTANT, "当时建议检查编码器。"),
            ]
        )
    )

    bundle = builder.build(
        conversation_id="conv-1",
        user_input="根据之前的结论继续分析",
        user_id="user-1",
        enable_knowledge_retrieval=False,
    )

    assert bundle.retrieval_plan["use_memory"] is True
    assert len(bundle.memories) == 1
    assert fake_memory.store.calls == 1
    assert fake_knowledge.calls == 0


def test_context_builder_selects_relevant_older_history(monkeypatch):
    monkeypatch.setattr(context_builder_module, "get_memory_manager", lambda: _FakeMemoryManager([]))
    monkeypatch.setattr(context_builder_module, "knowledge_manager", _FakeKnowledgeManager([]))

    messages = [
        _message(MessageRole.USER, "gearbox temperature kept rising last night"),
        _message(MessageRole.ASSISTANT, "first inspect lubrication and oil cooling loop"),
        _message(MessageRole.USER, "noted"),
        _message(MessageRole.ASSISTANT, "okay"),
        _message(MessageRole.USER, "different topic"),
        _message(MessageRole.ASSISTANT, "ack"),
        _message(MessageRole.USER, "hello"),
        _message(MessageRole.ASSISTANT, "hi"),
        _message(MessageRole.USER, "continue"),
        _message(MessageRole.ASSISTANT, "go on"),
    ]

    builder = ContextBuilder(_FakeConversationManager(messages))
    bundle = builder.build(
        conversation_id="conv-1",
        user_input="gearbox root cause analysis",
        history_window=6,
        enable_knowledge_retrieval=False,
    )

    recent_contents = [msg.content for msg in bundle.recent_messages]
    assert "gearbox temperature kept rising last night" in recent_contents
    assert "first inspect lubrication and oil cooling loop" in recent_contents
    assert len(bundle.recent_messages) == 6


def test_context_builder_builds_structured_summary(monkeypatch):
    monkeypatch.setattr(context_builder_module, "get_memory_manager", lambda: _FakeMemoryManager([]))
    monkeypatch.setattr(context_builder_module, "knowledge_manager", _FakeKnowledgeManager([]))

    messages = [
        _message(MessageRole.USER, "yaw alarm appeared twice in the morning"),
        _message(MessageRole.ASSISTANT, "earlier advice was to inspect yaw encoder and wind vane"),
        _message(MessageRole.USER, "encoder was replaced last month"),
        _message(MessageRole.ASSISTANT, "then check cabling and controller input quality"),
        _message(MessageRole.USER, "okay"),
        _message(MessageRole.ASSISTANT, "understood"),
        _message(MessageRole.USER, "please continue"),
        _message(MessageRole.ASSISTANT, "ready"),
    ]

    builder = ContextBuilder(_FakeConversationManager(messages))
    bundle = builder.build(
        conversation_id="conv-1",
        user_input="yaw alarm next diagnostic step",
        history_window=4,
        summary_window=2,
        enable_knowledge_retrieval=False,
    )

    assert "Earlier turns:" in bundle.conversation_summary
    assert "Recurring topics:" in bundle.conversation_summary
    assert "Earlier user intents:" in bundle.conversation_summary
    assert "Earlier assistant takeaways:" in bundle.conversation_summary


def test_context_builder_uses_task_profile_and_working_memory(monkeypatch):
    fake_memory = _PlanningMemoryManager(
        [
            (
                SimpleNamespace(
                    id="mem-1",
                    content="上次建议先检查偏航编码器",
                    memory_type="episodic",
                    tags=["continuation"],
                    context={"user_id": "user-1", "scope_path": ["conversation:conv-1"]},
                ),
                0.88,
            )
        ],
        working_memories=[
            SimpleNamespace(
                id="wm-1",
                content="当前任务: 继续偏航告警排查，已确认编码器上月更换",
                memory_type="working",
                tags=["working"],
                context={"user_id": "user-1", "scope_path": ["conversation:conv-1"]},
                importance=0.8,
            )
        ],
    )
    monkeypatch.setattr(context_builder_module, "get_memory_manager", lambda: fake_memory)
    monkeypatch.setattr(context_builder_module, "knowledge_manager", _FakeKnowledgeManager([]))

    builder = ContextBuilder(
        _FakeConversationManager(
            [
                _message(MessageRole.USER, "我们刚才在排查偏航告警"),
                _message(MessageRole.ASSISTANT, "已经确认编码器近期更换过"),
            ]
        )
    )

    bundle = builder.build(
        conversation_id="conv-1",
        user_input="继续上个任务，把剩余排查项列出来",
        user_id="user-1",
        enable_knowledge_retrieval=False,
    )

    assert bundle.retrieval_plan["task_type"] == "continuation"
    assert bundle.retrieval_plan["retrieval_mode"] == "recent"
    assert bundle.retrieval_plan["working_limit"] == 2
    assert len(bundle.working_memories) == 1
    assert bundle.working_memories[0].memory_id == "wm-1"
    assert "[Working Memory]" in bundle.as_prefetch_text()
