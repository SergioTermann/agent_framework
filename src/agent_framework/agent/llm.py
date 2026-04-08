"""
Factor 1 ── 自然语言 → 工具调用

LLM 提供商抽象层：将用户自然语言转化为结构化 JSON 工具调用。
使用纯原生 urllib，无任何第三方依赖。
兼容所有 OpenAI Chat Completions 协议（OpenAI / DeepSeek / Ollama / Azure 等）。
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass
class ToolCall:
    """LLM 决定调用的一个工具"""
    call_id: str       # OpenAI 返回的 id，用于匹配 tool_result
    name: str          # 工具名称
    arguments: dict    # 解析后的参数字典


@dataclass
class LLMResponse:
    """LLM 响应的统一格式（屏蔽各提供商差异）"""
    content: str | None              # 文本回复（纯文本场景）
    tool_calls: list[ToolCall]       # 工具调用列表（可能为空列表）
    usage: dict[str, int] = field(default_factory=dict)   # token 用量
    raw: dict = field(default_factory=dict)               # 原始响应体

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMProvider(ABC):
    """LLM 后端抽象接口"""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...


def is_local_openai_compatible_url(base_url: str) -> bool:
    """判断 base_url 是否指向本地/回环 OpenAI 兼容服务。"""
    try:
        parsed = urlparse(base_url)
    except Exception:
        return False

    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class OpenAICompatibleProvider(LLMProvider):
    """
    OpenAI Chat Completions 兼容接口实现。
    使用纯原生 urllib，支持：
      - 指数退避自动重试（429 / 5xx）
      - 可配置 base_url（接入国内代理或本地模型）
    """

    def __init__(
        self,
        api_key: str | None,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 120,
        max_retries: int = 3,
    ):
        self.api_key = (api_key or "").strip()
        self._model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def model_name(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        stream: bool = False,
        stream_callback=None,
        model: str | None = None,
        stop: list[str] | str | None = None,
        response_format: dict | None = None,
        extra_body: dict[str, Any] | None = None,
        **kwargs,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if top_p is not None:
            payload["top_p"] = top_p
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        if stop:
            payload["stop"] = stop
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if extra_body:
            payload.update(extra_body)
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                if stream and stream_callback:
                    return self._call_stream(payload, stream_callback)
                else:
                    return self._call(payload)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"HTTP {e.code}: {err_body}")
                # 429 限流 / 5xx 服务端错误 → 指数退避重试
                if e.code in (429, 500, 502, 503) and attempt < self.max_retries - 1:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                raise last_error from e
            except urllib.error.URLError as e:
                last_error = RuntimeError(f"网络错误: {e.reason}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error from e

        raise last_error or RuntimeError("LLM 请求失败，超过最大重试次数")

    def _call(self, payload: dict) -> LLMResponse:
        """发送单次 HTTP 请求并解析响应"""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=self._build_headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body: dict = json.loads(resp.read().decode("utf-8"))
        return self._parse(body)

    def _call_stream(self, payload: dict, stream_callback) -> LLMResponse:
        """发送流式 HTTP 请求并实时回调"""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=self._build_headers(),
            method="POST",
        )

        full_content = ""
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        chunk_data = json.loads(line[6:])
                        delta = chunk_data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_content += content
                            stream_callback(content)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        return LLMResponse(
            content=full_content,
            tool_calls=[],
            usage={},
            raw={},
        )

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _parse(self, body: dict) -> LLMResponse:
        """将 OpenAI 原始响应解析为 LLMResponse"""
        choice = body["choices"][0]
        message = choice["message"]
        content: str | None = message.get("content")
        usage: dict = body.get("usage", {})

        raw_calls = message.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for tc in raw_calls:
            try:
                args = json.loads(tc["function"].get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(
                call_id=tc["id"],
                name=tc["function"]["name"],
                arguments=args,
            ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            raw=body,
        )

    def __repr__(self) -> str:
        return f"<OpenAICompatibleProvider model={self._model} base={self.base_url}>"


def get_llm_client(
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int | None = None,
) -> OpenAICompatibleProvider:
    """Return the default OpenAI-compatible LLM client from platform config."""
    from agent_framework.core.config import get_config

    cfg = get_config()
    return OpenAICompatibleProvider(
        api_key=cfg.llm.api_key if api_key is None else api_key,
        model=model or cfg.llm.model,
        base_url=base_url or cfg.llm.base_url,
        timeout=cfg.llm.timeout if timeout is None else timeout,
    )
