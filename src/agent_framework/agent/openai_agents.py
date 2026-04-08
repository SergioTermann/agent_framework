from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

from agent_framework.agent.context import thread_to_input_items
from agent_framework.agent.store import FileSystemStore, ThreadStore
from agent_framework.agent.thread import Thread
from agent_framework.tool.registry import BUILTIN_TOOLS, DONE_TOOL, PAUSE_TOOL_NAMES, ToolSpec


_CONTROL_TOOL_NAMES = {tool.name for tool in BUILTIN_TOOLS}


@dataclass
class OpenAIAgentsResult:
    reply: str
    usage: dict[str, int]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    metadata: dict[str, Any]


def agents_sdk_is_available() -> bool:
    try:
        import agents  # noqa: F401
        from openai import AsyncOpenAI  # noqa: F401
    except ImportError:
        return False
    return True


def run_openai_agents(
    *,
    user_input: str | list[dict[str, Any]],
    instructions: str,
    tool_specs: Iterable[ToolSpec],
    api_key: str | None,
    model: str,
    base_url: str,
    timeout: int,
    max_turns: int,
    temperature: float,
    max_tokens: int | None,
    top_p: float | None,
    frequency_penalty: float | None,
    presence_penalty: float | None,
    workflow_name: str,
    conversation_id: str | None = None,
    agent_name: str = "Assistant",
    tracing_disabled: bool = True,
    tool_dispatcher: Any | None = None,
    _sdk: Any | None = None,
    _async_openai_cls: Any | None = None,
) -> OpenAIAgentsResult:
    sdk, async_openai_cls = _resolve_sdk(_sdk=_sdk, _async_openai_cls=_async_openai_cls)
    tool_results: list[dict[str, Any]] = []
    tools = _build_function_tools(
        tool_specs=tool_specs,
        sdk=sdk,
        tool_results=tool_results,
        tool_dispatcher=tool_dispatcher,
    )

    client = async_openai_cls(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    model_instance = sdk.OpenAIChatCompletionsModel(model=model, openai_client=client)
    model_settings = sdk.ModelSettings(
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
    )
    agent = sdk.Agent(
        name=agent_name,
        instructions=instructions,
        tools=tools,
        model=model_instance,
        model_settings=model_settings,
        tool_use_behavior=_tool_use_behavior(),
    )
    run_config = sdk.RunConfig(
        tracing_disabled=tracing_disabled,
        workflow_name=workflow_name,
        group_id=conversation_id,
    )
    result = _runner_invoke(
        sdk.Runner.run_sync,
        agent=agent,
        user_input=user_input,
        max_turns=max_turns,
        run_config=run_config,
        conversation_id=conversation_id,
    )

    return _build_openai_agents_result(
        result=result,
        conversation_id=conversation_id,
        tool_results=tool_results,
    )


def run_openai_agents_streamed(
    *,
    user_input: str | list[dict[str, Any]],
    instructions: str,
    tool_specs: Iterable[ToolSpec],
    api_key: str | None,
    model: str,
    base_url: str,
    timeout: int,
    max_turns: int,
    temperature: float,
    max_tokens: int | None,
    top_p: float | None,
    frequency_penalty: float | None,
    presence_penalty: float | None,
    workflow_name: str,
    conversation_id: str | None = None,
    agent_name: str = "Assistant",
    tracing_disabled: bool = True,
    on_stream_chunk: Any | None = None,
    tool_dispatcher: Any | None = None,
    _sdk: Any | None = None,
    _async_openai_cls: Any | None = None,
) -> OpenAIAgentsResult:
    async def _run() -> OpenAIAgentsResult:
        sdk, async_openai_cls = _resolve_sdk(_sdk=_sdk, _async_openai_cls=_async_openai_cls)
        tool_results: list[dict[str, Any]] = []
        tools = _build_function_tools(
            tool_specs=tool_specs,
            sdk=sdk,
            tool_results=tool_results,
            tool_dispatcher=tool_dispatcher,
        )

        client = async_openai_cls(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
        model_instance = sdk.OpenAIChatCompletionsModel(model=model, openai_client=client)
        model_settings = sdk.ModelSettings(
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )
        agent = sdk.Agent(
            name=agent_name,
            instructions=instructions,
            tools=tools,
            model=model_instance,
            model_settings=model_settings,
            tool_use_behavior=_tool_use_behavior(),
        )
        run_config = sdk.RunConfig(
            tracing_disabled=tracing_disabled,
            workflow_name=workflow_name,
            group_id=conversation_id,
        )
        result = _runner_invoke(
            sdk.Runner.run_streamed,
            agent=agent,
            user_input=user_input,
            max_turns=max_turns,
            run_config=run_config,
            conversation_id=conversation_id,
        )

        async for event in result.stream_events():
            if getattr(event, "type", "") != "raw_response_event":
                continue
            data = getattr(event, "data", None)
            if getattr(data, "type", "") != "response.output_text.delta":
                continue
            delta = getattr(data, "delta", "") or ""
            if delta and on_stream_chunk:
                on_stream_chunk(delta)

        return _build_openai_agents_result(
            result=result,
            conversation_id=conversation_id,
            tool_results=tool_results,
        )

    return _run_coro_sync(_run())


def build_agent_instructions(
    *,
    system_prompt: str,
    assistant_context: str = "",
    prefetch_context: str = "",
) -> str:
    sections = [system_prompt.strip()]
    if assistant_context.strip():
        sections.append(f"[Assistant Context]\n{assistant_context.strip()}")
    if prefetch_context.strip():
        sections.append(
            "[Supplemental Context]\n"
            "Use the following context when it is relevant. Do not fabricate facts.\n\n"
            f"{prefetch_context.strip()}"
        )
    return "\n\n".join(section for section in sections if section)


def _builtin_sdk_tool_specs() -> list[ToolSpec]:
    return list(BUILTIN_TOOLS)


def _tool_use_behavior() -> dict[str, list[str]]:
    return {"stop_at_tool_names": sorted(PAUSE_TOOL_NAMES | {DONE_TOOL.name})}


def _resolve_sdk(*, _sdk: Any | None, _async_openai_cls: Any | None) -> tuple[Any, Any]:
    if _sdk is not None and _async_openai_cls is not None:
        return _sdk, _async_openai_cls

    try:
        import agents as sdk
    except ImportError as exc:  # pragma: no cover - exercised via unit injection
        raise ImportError(
            "OpenAI Agents SDK is not installed. Add the `openai-agents` package first."
        ) from exc

    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - exercised via unit injection
        raise ImportError(
            "The `openai` package is required for the OpenAI Agents SDK integration."
        ) from exc

    return _sdk or sdk, _async_openai_cls or AsyncOpenAI


def _runner_invoke(
    runner_method: Any,
    *,
    agent: Any,
    user_input: str | list[dict[str, Any]],
    max_turns: int,
    run_config: Any,
    conversation_id: str | None,
):
    kwargs: dict[str, Any] = {
        "max_turns": max_turns,
        "run_config": run_config,
    }
    try:
        parameters = inspect.signature(runner_method).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        parameters = {}
    if conversation_id and "conversation_id" in parameters:
        kwargs["conversation_id"] = conversation_id
    return runner_method(agent, user_input, **kwargs)


def _build_openai_agents_result(
    *,
    result: Any,
    conversation_id: str | None,
    tool_results: list[dict[str, Any]],
) -> OpenAIAgentsResult:
    tool_calls = _extract_tool_calls(getattr(result, "new_items", []) or [])
    usage = _extract_usage(result)
    metadata = {
        "generation_type": "openai_agents_sdk",
        "thread_id": conversation_id or getattr(result, "last_response_id", None),
        "last_response_id": getattr(result, "last_response_id", None),
        "tool_call_count": len(tool_calls),
        "agent_backend": "openai_agents_sdk",
    }
    return OpenAIAgentsResult(
        reply=str(getattr(result, "final_output", "") or "").strip(),
        usage=usage,
        tool_calls=tool_calls,
        tool_results=tool_results,
        metadata=metadata,
    )


def _build_function_tools(
    *,
    tool_specs: Iterable[ToolSpec],
    sdk: Any,
    tool_results: list[dict[str, Any]],
    tool_dispatcher: Any | None = None,
) -> list[Any]:
    tools: list[Any] = []
    for spec in tool_specs:
        tools.append(
            sdk.FunctionTool(
                name=spec.name,
                description=spec.description or spec.name,
                params_json_schema=spec.parameters,
                on_invoke_tool=_make_tool_invoker(spec, tool_results, tool_dispatcher),
            )
        )
    return tools


def _make_tool_invoker(
    spec: ToolSpec,
    tool_results: list[dict[str, Any]],
    tool_dispatcher: Any | None = None,
):
    async def _invoke(_ctx: Any, args: str) -> str:
        parsed: dict[str, Any] | Any = {}
        try:
            parsed = json.loads(args) if isinstance(args, str) else args
            if not isinstance(parsed, dict):
                result = f"Error: invalid arguments for tool '{spec.name}'"
                tool_results.append({"name": spec.name, "arguments": {}, "result": result})
                return result
            if spec.handler is None:
                if spec.name in _CONTROL_TOOL_NAMES:
                    result = _invoke_control_tool(spec.name, parsed)
                    tool_results.append({"name": spec.name, "arguments": parsed, "result": result})
                    return result
                result = f"Error: tool '{spec.name}' has no handler"
                tool_results.append({"name": spec.name, "arguments": parsed, "result": result})
                return result
            if tool_dispatcher is not None:
                result = tool_dispatcher(spec.name, parsed)
            else:
                result = spec.handler(**parsed)
            if inspect.isawaitable(result):
                result = await result
            result_text = "null" if result is None else str(result)
            tool_results.append({"name": spec.name, "arguments": parsed, "result": result_text})
            return result_text
        except Exception as exc:
            result = f"Error: {exc}"
            tool_results.append(
                {
                    "name": spec.name,
                    "arguments": parsed if isinstance(parsed, dict) else {},
                    "result": result,
                }
            )
            return result

    return _invoke


def _invoke_control_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    if tool_name == DONE_TOOL.name:
        return str(arguments.get("result", "done") or "done")
    question = arguments.get("action") or arguments.get("question") or "Human input required."
    return str(question)


class OpenAIAgentsThreadRunner:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout: int,
        tools,
        config,
        store: ThreadStore | None = None,
        on_human_request: Any | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.tools = tools
        self.config = config
        self.store = store or FileSystemStore()
        self._on_human_request = on_human_request
        self._sdk_tool_specs = list(self.tools) + _builtin_sdk_tool_specs()

    def launch(
        self,
        user_input: str,
        thread_id: str | None = None,
        prefetch_context: str | None = None,
    ) -> Thread:
        thread = Thread()
        if thread_id:
            thread.thread_id = thread_id

        thread.metadata["agent_backend"] = "openai_agents_sdk"
        thread.metadata["prefetch_context"] = prefetch_context or ""
        thread.push("system", {"event": "launched", "backend": "openai_agents_sdk"})
        thread.push("user_message", {"content": user_input})
        self.store.save(thread)

        return self._execute_thread(
            thread=thread,
            input_payload=user_input,
            prefetch_context=prefetch_context or "",
        )

    def resume(self, thread_id: str, human_response: str | None = None) -> Thread:
        thread = self.store.load(thread_id)
        if thread is None:
            raise ValueError(f"Thread not found: {thread_id}")
        if not thread.is_paused():
            raise ValueError(f"Thread {thread_id} is not paused")

        if human_response is not None:
            last_req = thread.last_of_type("human_input_request")
            thread.push(
                "human_input_response",
                {
                    "response": human_response,
                    "responding_to": last_req.event_id if last_req else "",
                },
            )

        thread.push("system", {"event": "resumed", "backend": "openai_agents_sdk"})
        self.store.save(thread)
        input_items = thread_to_input_items(thread)
        return self._execute_thread(
            thread=thread,
            input_payload=input_items,
            prefetch_context=str(thread.metadata.get("prefetch_context", "") or ""),
        )

    def _execute_thread(
        self,
        *,
        thread: Thread,
        input_payload: str | list[dict[str, Any]],
        prefetch_context: str,
    ) -> Thread:
        round_number = 1 + sum(1 for event in thread.events if event.type == "llm_response")

        system_prompt = self.config.system_prompt_template.render(
            agent_name=self.config.agent_name,
            agent_role=self.config.agent_role,
            tools_description=self.tools.describe(),
        )
        instructions = build_agent_instructions(
            system_prompt=system_prompt,
            prefetch_context=prefetch_context or "",
        )

        if self.config.callbacks:
            self.config.callbacks.trigger(
                "round_start",
                {"round": round_number, "max_rounds": self.config.max_rounds},
                thread.thread_id,
            )
            self.config.callbacks.trigger(
                "llm_start",
                {
                    "messages_count": 1 if isinstance(input_payload, str) else len(input_payload),
                    "temperature": self.config.temperature,
                },
                thread.thread_id,
            )

        started_at = time.perf_counter()
        if self.config.stream:
            result = run_openai_agents_streamed(
                user_input=input_payload,
                instructions=instructions,
                tool_specs=self._sdk_tool_specs,
                api_key=self.api_key,
                model=self.model,
                base_url=self.base_url,
                timeout=self.timeout,
                max_turns=self.config.max_rounds,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                workflow_name="agent_builder_compat",
                conversation_id=thread.thread_id,
                agent_name=self.config.agent_name,
                tool_dispatcher=self.tools.dispatch,
                on_stream_chunk=self.config.on_stream_chunk,
            )
        else:
            result = run_openai_agents(
                user_input=input_payload,
                instructions=instructions,
                tool_specs=self._sdk_tool_specs,
                api_key=self.api_key,
                model=self.model,
                base_url=self.base_url,
                timeout=self.timeout,
                max_turns=self.config.max_rounds,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                workflow_name="agent_builder_compat",
                conversation_id=thread.thread_id,
                agent_name=self.config.agent_name,
                tool_dispatcher=self.tools.dispatch,
            )
        elapsed = time.perf_counter() - started_at

        if result.tool_calls:
            thread.push(
                "llm_response",
                {
                    "content": result.reply,
                    "tool_calls": result.tool_calls,
                },
            )

        for index, tool_result in enumerate(result.tool_results):
            call_id = None
            arguments: dict[str, Any] = {}
            tool_name = tool_result.get("name", "")
            if index < len(result.tool_calls):
                call_id = result.tool_calls[index].get("call_id")
                arguments = result.tool_calls[index].get("arguments") or {}
                tool_name = result.tool_calls[index].get("name", tool_name)

            if self.config.callbacks:
                self.config.callbacks.trigger(
                    "tool_call_start",
                    {
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "call_id": call_id,
                    },
                    thread.thread_id,
                )

            thread.push(
                "tool_result",
                {
                    "call_id": call_id or f"tool_call_{index + 1}",
                    "name": tool_name,
                    "result": tool_result.get("result", ""),
                },
            )

            if self.config.callbacks:
                self.config.callbacks.trigger(
                    "tool_call_end",
                    {
                        "tool_name": tool_name,
                        "result": tool_result.get("result", ""),
                        "call_id": call_id,
                    },
                    thread.thread_id,
                )

        thread.metadata.update(result.metadata)

        if self.config.callbacks:
            self.config.callbacks.trigger(
                "llm_end",
                {
                    "content": result.reply,
                    "tool_calls_count": len(result.tool_calls),
                    "usage": result.usage,
                },
                thread.thread_id,
            )

        if not self._handle_control_tools(thread, result, elapsed):
            thread.push("assistant_message", {"content": result.reply})
            thread.push(
                "system",
                {
                    "event": "done",
                    "success": True,
                    "backend": "openai_agents_sdk",
                    "elapsed_seconds": elapsed,
                },
            )

        self.store.save(thread)

        if self.config.callbacks:
            self.config.callbacks.trigger(
                "round_end",
                {"round": round_number, "elapsed_seconds": elapsed},
                thread.thread_id,
            )

        return thread

    def status(self, thread_id: str) -> dict[str, Any]:
        thread = self.store.load(thread_id)
        if thread is None:
            return {"thread_id": thread_id, "status": "not_found"}
        last = thread.events[-1] if thread.events else None
        return {
            "thread_id": thread_id,
            "status": "paused" if thread.is_paused() else ("done" if thread.is_done() else "active"),
            "event_count": len(thread.events),
            "last_event_type": last.type if last else None,
            "created_at": thread.created_at,
            "backend": "openai_agents_sdk",
        }

    def _handle_control_tools(
        self,
        thread: Thread,
        result: OpenAIAgentsResult,
        elapsed: float,
    ) -> bool:
        for index, tool_call in enumerate(result.tool_calls):
            tool_name = tool_call.get("name", "")
            arguments = tool_call.get("arguments") or {}
            call_id = tool_call.get("call_id") or f"tool_call_{index + 1}"

            if tool_name in PAUSE_TOOL_NAMES:
                question = str(arguments.get("action") or arguments.get("question") or "Human input required.")
                request = thread.push(
                    "human_input_request",
                    {
                        "call_id": call_id,
                        "tool": tool_name,
                        "question": question,
                        "details": arguments,
                    },
                )
                if self._on_human_request:
                    self._on_human_request(thread, request.data)
                return True

            if tool_name == DONE_TOOL.name:
                final_result = str(arguments.get("result", result.reply) or "")
                if not _thread_has_tool_result(thread, call_id):
                    thread.push(
                        "tool_result",
                        {
                            "call_id": call_id,
                            "name": tool_name,
                            "result": final_result,
                        },
                    )
                if final_result:
                    thread.push("assistant_message", {"content": final_result})
                thread.push(
                    "system",
                    {
                        "event": "done",
                        "success": bool(arguments.get("success", True)),
                        "result": final_result,
                        "backend": "openai_agents_sdk",
                        "elapsed_seconds": elapsed,
                    },
                )
                return True

        return False


def _thread_has_tool_result(thread: Thread, call_id: str) -> bool:
    return any(
        event.type == "tool_result" and event.data.get("call_id") == call_id
        for event in thread.events
    )


def _extract_tool_calls(items: Iterable[Any]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for item in items:
        raw_item = getattr(item, "raw_item", item)
        payload = _coerce_dict(raw_item)
        item_type = payload.get("type") or getattr(item, "type", "")
        if item_type not in {"tool_call_item", "function_call", "hosted_tool_call"}:
            continue

        name = payload.get("name") or payload.get("tool_name")
        if not name:
            continue

        arguments = payload.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"raw": arguments}
        if arguments is None:
            arguments = {}

        call_id = (
            payload.get("call_id")
            or payload.get("callId")
            or payload.get("id")
            or getattr(raw_item, "call_id", None)
            or getattr(raw_item, "callId", None)
        )
        tool_calls.append(
            {
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            }
        )
    return tool_calls


def _extract_usage(result: Any) -> dict[str, int]:
    total = 0
    prompt = 0
    completion = 0
    calls = 0

    for raw_response in getattr(result, "raw_responses", []) or []:
        usage = _coerce_dict(getattr(raw_response, "usage", raw_response))
        if not usage:
            continue
        total += int(usage.get("total_tokens") or 0)
        prompt += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion += int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        calls += 1

    return {
        "total_tokens": total,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "calls": calls,
    }


def _coerce_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_unset=True)
        if isinstance(dumped, dict):
            return dumped
    dumped = getattr(value, "__dict__", None)
    if isinstance(dumped, dict):
        return dumped
    return {}


def _run_coro_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _worker():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - thread edge case
            error["value"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result["value"]
