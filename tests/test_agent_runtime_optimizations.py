from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from agent_framework.agent.builder import AgentBuilder
from agent_framework.agent.llm import LLMProvider, LLMResponse, ToolCall
from agent_framework.agent.store import FileSystemStore
from agent_framework.tool.middleware import BeforeToolResult
from agent_framework.tool.registry import ToolSpec
from agent_framework.web.unified_orchestrator import UnifiedOrchestrator


def _test_store(name: str) -> FileSystemStore:
    base_dir = Path(".tmp_test_threads") / f"{name}_{uuid4().hex}"
    return FileSystemStore(str(base_dir))


class _SequenceLLM(LLMProvider):
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    @property
    def model_name(self) -> str:
        return "fake-sequence"

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools or [], "kwargs": kwargs})
        return self._responses.pop(0)


class _SuffixHook:
    def before_tool(self, invocation):
        return BeforeToolResult(
            updated_arguments={"text": f"{invocation.arguments['text']}-hooked"}
        )


def test_legacy_runner_applies_tool_hook_and_result_limit():
    llm = _SequenceLLM(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(call_id="call_1", name="echo", arguments={"text": "abc"})],
            ),
            LLMResponse(content="done", tool_calls=[]),
        ]
    )

    builder = (
        AgentBuilder()
        .with_llm(llm)
        .with_agent_backend("legacy")
        .with_store(_test_store("legacy_runtime"))
        .with_tool_hook(_SuffixHook())
        .with_tool_result_limit(80)
    )

    @builder.tool(description="Echo a large payload")
    def echo(text: str) -> str:
        return (text + "|") * 80

    thread = builder.build().launch("run echo")

    tool_results = [event for event in thread.events if event.type == "tool_result"]
    assert len(tool_results) == 1
    result_text = tool_results[0].data["result"]
    assert "abc-hooked" in result_text
    assert "[truncated" in result_text
    assert len(result_text) <= 80

    second_call_messages = llm.calls[1]["messages"]
    tool_messages = [message for message in second_call_messages if message.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"] == result_text


def test_openai_agents_runner_passes_registry_dispatcher(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.agent.builder.agents_sdk_is_available",
        lambda: True,
    )

    captured: dict[str, object] = {}

    def _run(**kwargs):
        captured["tool_dispatcher"] = kwargs.get("tool_dispatcher")
        return SimpleNamespace(
            reply="done",
            usage={"total_tokens": 4, "prompt_tokens": 2, "completion_tokens": 2, "calls": 1},
            tool_calls=[],
            tool_results=[],
            metadata={"generation_type": "openai_agents_sdk", "agent_backend": "openai_agents_sdk"},
        )

    monkeypatch.setattr("agent_framework.agent.openai_agents.run_openai_agents", _run)

    builder = (
        AgentBuilder()
        .with_openai(api_key="test-key", model="gpt-4o", base_url="https://example.com/v1")
        .with_store(_test_store("openai_agents_dispatch"))
        .with_tool_result_limit(40)
    )

    @builder.tool(description="Echo text")
    def echo(text: str) -> str:
        return text * 20

    runner = builder.build()
    runner.launch("say hi")

    dispatcher = captured["tool_dispatcher"]
    assert callable(dispatcher)
    limited = dispatcher("echo", {"text": "abcdef"})
    assert isinstance(limited, str)
    assert "[truncated" in limited
    assert len(limited) <= 40


def test_legacy_runner_blocks_tool_via_permission_rules():
    llm = _SequenceLLM(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(call_id="call_1", name="echo", arguments={"text": "secret payload"})],
            ),
            LLMResponse(content="stopped", tool_calls=[]),
        ]
    )

    builder = (
        AgentBuilder()
        .with_llm(llm)
        .with_agent_backend("legacy")
        .with_store(_test_store("legacy_permission_rules"))
        .with_tool_permission_rules(
            [
                {
                    "tool_name": "echo",
                    "decision": "ask",
                    "constraints": {"text": {"contains": "secret"}},
                    "reason": "secret payload requires approval",
                }
            ]
        )
    )

    @builder.tool(description="Echo text")
    def echo(text: str) -> str:
        return text

    thread = builder.build().launch("run secret echo")

    errors = [event for event in thread.events if event.type == "error"]
    assert len(errors) == 1
    assert "secret payload requires approval" in errors[0].data["message"]
    second_call_messages = llm.calls[1]["messages"]
    tool_messages = [message for message in second_call_messages if message.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "request_human_approval" in tool_messages[0]["content"]


def test_unified_orchestrator_chat_completion_uses_permission_runtime(monkeypatch):
    responses = [
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(call_id="call_1", name="echo", arguments={"text": "secret payload"})],
            usage={"total_tokens": 3, "prompt_tokens": 2, "completion_tokens": 1},
        ),
        LLMResponse(
            content="fallback answer",
            tool_calls=[],
            usage={"total_tokens": 4, "prompt_tokens": 2, "completion_tokens": 2},
        ),
    ]
    captured_messages: list[list[dict]] = []

    class _FakeProvider:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def chat(self, messages, tools=None, **kwargs):
            captured_messages.append(messages)
            return responses.pop(0)

    monkeypatch.setattr(
        "agent_framework.web.unified_orchestrator.OpenAICompatibleProvider",
        _FakeProvider,
    )
    monkeypatch.setattr(
        "agent_framework.web.unified_orchestrator.resolve_tool_specs",
        lambda **kwargs: [
            ToolSpec(
                name="echo",
                description="Echo text",
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                handler=lambda text: text,
            )
        ],
    )

    orchestrator = object.__new__(UnifiedOrchestrator)
    orchestrator.config = SimpleNamespace(
        llm=SimpleNamespace(timeout=30),
        agent=SimpleNamespace(
            temperature=0.1,
            max_tokens=256,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            max_rounds=3,
        ),
    )
    orchestrator._default_tool_result_limit = 4000
    orchestrator._build_system_prompt = lambda **kwargs: "system"
    orchestrator._build_assistant_context = lambda metadata: ""

    result = orchestrator._run_chat_completion(
        context=SimpleNamespace(
            knowledge_chunks=[],
            as_prefetch_text=lambda: "",
            recent_messages_for_llm=lambda: [{"role": "user", "content": "run secret echo"}],
        ),
        route=SimpleNamespace(
            target=SimpleNamespace(api_key="k", model="m", base_url="https://example.com/v1")
        ),
        metadata={
            "enable_tools": True,
            "user_id": "u1",
            "tool_permission_rules": [
                {
                    "tool_name": "echo",
                    "decision": "ask",
                    "constraints": {"text": {"contains": "secret"}},
                    "reason": "secret payload requires approval",
                }
            ],
        },
    )

    assert result["reply"] == "fallback answer"
    tool_messages = [message for message in captured_messages[1] if message.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "secret payload requires approval" in tool_messages[0]["content"]
    assert "request_human_approval" in tool_messages[0]["content"]
