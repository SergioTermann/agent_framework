from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from agent_framework.agent.openai_agents import build_agent_instructions, run_openai_agents
from agent_framework.agent.builder import AgentBuilder
from agent_framework.agent.callbacks import CallbackManager
from agent_framework.agent.store import FileSystemStore
from agent_framework.tool.registry import ToolSpec
from agent_framework.web.unified_orchestrator import UnifiedOrchestrator


def _test_store(name: str) -> FileSystemStore:
    base_dir = Path(".tmp_test_threads") / f"{name}_{uuid4().hex}"
    return FileSystemStore(str(base_dir))


class _FakeAsyncOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeFunctionTool:
    def __init__(self, **kwargs):
        self.name = kwargs["name"]
        self.description = kwargs["description"]
        self.params_json_schema = kwargs["params_json_schema"]
        self.on_invoke_tool = kwargs["on_invoke_tool"]


class _FakeModelSettings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeAgent:
    def __init__(self, **kwargs):
        self.name = kwargs["name"]
        self.instructions = kwargs["instructions"]
        self.tools = kwargs["tools"]
        self.model = kwargs["model"]
        self.model_settings = kwargs["model_settings"]
        self.tool_use_behavior = kwargs.get("tool_use_behavior")


class _FakeRunConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeRunner:
    last_call = None

    @classmethod
    def run_sync(cls, agent, user_input, *, max_turns, run_config):
        cls.last_call = {
            "agent": agent,
            "user_input": user_input,
            "max_turns": max_turns,
            "run_config": run_config,
        }
        return SimpleNamespace(
            final_output="42",
            last_response_id="resp_123",
            new_items=[
                SimpleNamespace(
                    raw_item={
                        "type": "function_call",
                        "name": "calculate",
                        "arguments": '{"expression":"6*7"}',
                        "call_id": "call_1",
                    }
                )
            ],
            raw_responses=[
                SimpleNamespace(
                    usage={
                        "total_tokens": 30,
                        "input_tokens": 18,
                        "output_tokens": 12,
                    }
                )
            ],
        )


class _FakeSDK:
    FunctionTool = _FakeFunctionTool
    ModelSettings = _FakeModelSettings
    OpenAIChatCompletionsModel = _FakeModel
    Agent = _FakeAgent
    RunConfig = _FakeRunConfig
    Runner = _FakeRunner


def test_run_openai_agents_builds_sdk_result():
    result = run_openai_agents(
        user_input="calculate 6*7",
        instructions="You are a calculator.",
        tool_specs=[
            ToolSpec(
                name="calculate",
                description="Calculate an expression",
                parameters={
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
                handler=lambda expression: eval(expression),
            )
        ],
        api_key="test-key",
        model="gpt-4o",
        base_url="https://example.com/v1",
        timeout=30,
        max_turns=8,
        temperature=0.2,
        max_tokens=512,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        workflow_name="test_workflow",
        conversation_id="conv_123",
        agent_name="CalcBot",
        _sdk=_FakeSDK,
        _async_openai_cls=_FakeAsyncOpenAI,
    )

    assert result.reply == "42"
    assert result.usage == {
        "total_tokens": 30,
        "prompt_tokens": 18,
        "completion_tokens": 12,
        "calls": 1,
    }
    assert result.tool_calls == [
        {
            "call_id": "call_1",
            "name": "calculate",
            "arguments": {"expression": "6*7"},
        }
    ]
    assert result.metadata["generation_type"] == "openai_agents_sdk"
    assert _FakeRunner.last_call["max_turns"] == 8
    assert _FakeRunner.last_call["agent"].name == "CalcBot"
    assert _FakeRunner.last_call["agent"].tool_use_behavior == {
        "stop_at_tool_names": ["done", "request_human_approval", "request_more_information"]
    }

    tool = _FakeRunner.last_call["agent"].tools[0]
    tool_output = asyncio.run(tool.on_invoke_tool(None, '{"expression":"6*7"}'))
    assert tool_output == "42"


def test_build_agent_instructions_keeps_sections():
    instructions = build_agent_instructions(
        system_prompt="system",
        assistant_context="assistant",
        prefetch_context="prefetch",
    )

    assert "system" in instructions
    assert "[Assistant Context]" in instructions
    assert "[Supplemental Context]" in instructions


def test_run_agent_falls_back_to_legacy_when_sdk_missing(monkeypatch):
    orchestrator = object.__new__(UnifiedOrchestrator)

    monkeypatch.setattr(
        "agent_framework.web.unified_orchestrator.agents_sdk_is_available",
        lambda: False,
    )

    def _legacy(**kwargs):
        return {
            "reply": "legacy",
            "usage": {"total_tokens": 1, "prompt_tokens": 1, "completion_tokens": 0, "calls": 1},
            "tool_calls": [],
            "metadata": {"generation_type": "agent"},
        }

    orchestrator._run_legacy_agent = _legacy

    result = orchestrator._run_agent(
        user_input="hello",
        context=SimpleNamespace(conversation_id="conv_1", knowledge_chunks=[]),
        route=SimpleNamespace(),
        metadata={},
    )

    assert result["reply"] == "legacy"
    assert result["metadata"]["agent_backend"] == "legacy"
    assert result["metadata"]["agent_backend_reason"] == "openai_agents_sdk_unavailable"


def test_agent_builder_uses_openai_agents_runner_when_possible(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.agent.builder.agents_sdk_is_available",
        lambda: True,
    )

    builder = AgentBuilder().with_openai(
        api_key="test-key",
        model="gpt-4o",
        base_url="https://example.com/v1",
    )

    runner = builder.build()

    assert runner.__class__.__name__ == "OpenAIAgentsThreadRunner"


def test_agent_builder_uses_openai_agents_runner_for_streaming(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.agent.builder.agents_sdk_is_available",
        lambda: True,
    )

    builder = (
        AgentBuilder()
        .with_openai(api_key="test-key", model="gpt-4o", base_url="https://example.com/v1")
        .with_stream(True)
    )

    runner = builder.build()

    assert runner.__class__.__name__ == "OpenAIAgentsThreadRunner"


def test_agent_builder_keeps_openai_agents_runner_with_human_request(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.agent.builder.agents_sdk_is_available",
        lambda: True,
    )

    builder = (
        AgentBuilder()
        .with_openai(api_key="test-key", model="gpt-4o", base_url="https://example.com/v1")
        .with_store(_test_store("human_request"))
        .on_human_request(lambda thread, request: None)
    )

    runner = builder.build()

    assert runner.__class__.__name__ == "OpenAIAgentsThreadRunner"


def test_openai_agents_runner_triggers_callback_events(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.agent.builder.agents_sdk_is_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_framework.agent.openai_agents.run_openai_agents",
        lambda **kwargs: SimpleNamespace(
            reply="done",
            usage={"total_tokens": 9, "prompt_tokens": 4, "completion_tokens": 5, "calls": 1},
            tool_calls=[{"call_id": "call_1", "name": "echo", "arguments": {"text": "hi"}}],
            tool_results=[{"name": "echo", "arguments": {"text": "hi"}, "result": "hi"}],
            metadata={"generation_type": "openai_agents_sdk", "agent_backend": "openai_agents_sdk"},
        ),
    )

    events = []
    callbacks = CallbackManager()
    for event_name in ("round_start", "llm_start", "tool_call_start", "tool_call_end", "llm_end", "round_end"):
        callbacks.on(event_name, lambda event, _name=event_name: events.append(_name))

    builder = (
        AgentBuilder()
        .with_openai(api_key="test-key", model="gpt-4o", base_url="https://example.com/v1")
        .with_callbacks(callbacks)
    )

    @builder.tool(description="Echo text")
    def echo(text: str) -> str:
        return text

    runner = builder.build()
    thread = runner.launch("say hi")

    assert thread.events[-2].type == "assistant_message"
    assert "tool_result" in [event.type for event in thread.events]
    assert events == ["round_start", "llm_start", "tool_call_start", "tool_call_end", "llm_end", "round_end"]


def test_openai_agents_runner_streams_chunks(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.agent.builder.agents_sdk_is_available",
        lambda: True,
    )

    streamed = []
    monkeypatch.setattr(
        "agent_framework.agent.openai_agents.run_openai_agents_streamed",
        lambda **kwargs: (
            kwargs["on_stream_chunk"]("hel"),
            kwargs["on_stream_chunk"]("lo"),
            SimpleNamespace(
                reply="hello",
                usage={"total_tokens": 7, "prompt_tokens": 3, "completion_tokens": 4, "calls": 1},
                tool_calls=[],
                tool_results=[],
                metadata={"generation_type": "openai_agents_sdk", "agent_backend": "openai_agents_sdk"},
            ),
        )[-1],
    )

    builder = (
        AgentBuilder()
        .with_openai(api_key="test-key", model="gpt-4o", base_url="https://example.com/v1")
        .with_stream(True, on_chunk=streamed.append)
    )

    runner = builder.build()
    thread = runner.launch("say hello")

    assert streamed == ["hel", "lo"]
    assert thread.events[-2].data["content"] == "hello"


def test_openai_agents_runner_pauses_and_resumes(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.agent.builder.agents_sdk_is_available",
        lambda: True,
    )

    captured_inputs = []
    human_requests = []
    results = [
        SimpleNamespace(
            reply="",
            usage={"total_tokens": 4, "prompt_tokens": 3, "completion_tokens": 1, "calls": 1},
            tool_calls=[
                {
                    "call_id": "call_pause",
                    "name": "request_more_information",
                    "arguments": {"question": "Which environment should I use?"},
                }
            ],
            tool_results=[],
            metadata={"generation_type": "openai_agents_sdk", "agent_backend": "openai_agents_sdk"},
        ),
        SimpleNamespace(
            reply="",
            usage={"total_tokens": 5, "prompt_tokens": 3, "completion_tokens": 2, "calls": 1},
            tool_calls=[
                {
                    "call_id": "call_done",
                    "name": "done",
                    "arguments": {"result": "used the staging environment", "success": True},
                }
            ],
            tool_results=[],
            metadata={"generation_type": "openai_agents_sdk", "agent_backend": "openai_agents_sdk"},
        ),
    ]

    def _run(**kwargs):
        captured_inputs.append(kwargs["user_input"])
        return results.pop(0)

    monkeypatch.setattr("agent_framework.agent.openai_agents.run_openai_agents", _run)

    builder = (
        AgentBuilder()
        .with_openai(api_key="test-key", model="gpt-4o", base_url="https://example.com/v1")
        .with_store(_test_store("pause_resume"))
        .on_human_request(lambda thread, request: human_requests.append(request))
    )

    runner = builder.build()
    thread = runner.launch("prepare the release")

    assert thread.is_paused()
    assert thread.events[-1].type == "human_input_request"
    assert human_requests == [
        {
            "call_id": "call_pause",
            "tool": "request_more_information",
            "question": "Which environment should I use?",
            "details": {"question": "Which environment should I use?"},
        }
    ]

    resumed = runner.resume(thread.thread_id, "Use staging.")

    assert resumed.is_done()
    assert not resumed.is_paused()
    assert resumed.events[-2].type == "assistant_message"
    assert resumed.events[-2].data["content"] == "used the staging environment"
    assert any(
        event.type == "human_input_response" and event.data["response"] == "Use staging."
        for event in resumed.events
    )
    assert isinstance(captured_inputs[1], list)
    assert {"role": "user", "content": "[Human Response] Use staging."} in captured_inputs[1]


def test_openai_agents_runner_handles_done_tool(monkeypatch):
    monkeypatch.setattr(
        "agent_framework.agent.builder.agents_sdk_is_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_framework.agent.openai_agents.run_openai_agents",
        lambda **kwargs: SimpleNamespace(
            reply="",
            usage={"total_tokens": 5, "prompt_tokens": 2, "completion_tokens": 3, "calls": 1},
            tool_calls=[
                {
                    "call_id": "call_done",
                    "name": "done",
                    "arguments": {"result": "completed via done", "success": True},
                }
            ],
            tool_results=[],
            metadata={"generation_type": "openai_agents_sdk", "agent_backend": "openai_agents_sdk"},
        ),
    )

    builder = (
        AgentBuilder()
        .with_openai(api_key="test-key", model="gpt-4o", base_url="https://example.com/v1")
        .with_store(_test_store("done_tool"))
    )

    runner = builder.build()
    thread = runner.launch("finish the task")

    assert thread.is_done()
    assert thread.events[-2].type == "assistant_message"
    assert thread.events[-2].data["content"] == "completed via done"
    assert any(
        event.type == "tool_result"
        and event.data["call_id"] == "call_done"
        and event.data["name"] == "done"
        for event in thread.events
    )
