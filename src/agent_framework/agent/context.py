"""
Factor 3  ── 掌控上下文窗口
Factor 13 ── 预取所有可能需要的上下文

上下文工程的核心：LLM 是无状态函数，输入质量决定输出质量。
将 Thread 序列化为 LLM 可消费的 messages 格式：
  - 当前轮次的事件用标准 OpenAI messages 格式（保证 tool_call 配对正确）
  - 超出 budget 的旧历史做智能压缩（XML 块 + 内容截断）

改进点：
  - Token-aware 切分：按 token budget 而非固定 event 数量决定压缩边界
  - 工具结果压缩：过长的 tool_result 在 XML 中截断，保留关键信息
  - Tool-call 配对完整性：确保 llm_response + tool_result 组不被拆散
  - 旧消息内容截断：user/assistant 纯文本在 XML 中做长度限制
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import re
from typing import Any

from agent_framework.agent.thread import Thread, Event


# ─── Token 估算 ─────────────────────────────────────────────────────────────

_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")

# 旧历史 XML 中各类事件的最大内容长度
_XML_CLIP_USER = 200       # user 消息在 XML 中最多保留 200 字符
_XML_CLIP_ASSISTANT = 300  # assistant 消息保留多一些（含结论）
_XML_CLIP_TOOL_RESULT = 150  # tool 结果大幅截断（通常很长）
_XML_CLIP_ERROR = 120


def _estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数。"""
    if not text:
        return 0
    cjk_chars = len(_CJK_RANGE.findall(text))
    non_cjk = len(text) - cjk_chars
    return int(cjk_chars * 1.5 + non_cjk * 0.3) + 1


def _estimate_event_tokens(event: Event) -> int:
    """估算单个 event 序列化后的 token 数。"""
    d = event.data
    if event.type in ("user_message", "assistant_message"):
        return _estimate_tokens(d.get("content", "")) + 4
    if event.type == "llm_response":
        content_tokens = _estimate_tokens(d.get("content", "") or "")
        calls = d.get("tool_calls", [])
        call_tokens = sum(
            _estimate_tokens(c.get("name", "")) + _estimate_tokens(
                json.dumps(c.get("arguments", {}), ensure_ascii=False)
            )
            for c in calls
        )
        return content_tokens + call_tokens + 8
    if event.type == "tool_result":
        return _estimate_tokens(str(d.get("result", ""))) + 8
    if event.type == "error":
        return _estimate_tokens(d.get("message", "")) + 8
    return _estimate_tokens(json.dumps(d, ensure_ascii=False)) + 4


def _clip(text: str, max_len: int) -> str:
    """截断文本，保留前 max_len 字符。"""
    text = " ".join((text or "").split())
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


# ─── XML 序列化（Factor 3：自定义高密度上下文格式）─────────────────────────────


def event_to_xml(event: Event, compressed: bool = False) -> str:
    """
    将单个事件序列化为 XML 片段，用于历史压缩。

    Args:
        event: 事件对象
        compressed: True 时对内容做截断压缩，False 时保留原文
    """
    t = event.type
    d = event.data
    ts = event.timestamp[:19].replace("T", " ")

    if t == "user_message":
        content = d.get("content", "")
        if compressed:
            content = _clip(content, _XML_CLIP_USER)
        return f'<user ts="{ts}">{_esc(content)}</user>'

    if t == "assistant_message":
        content = d.get("content", "")
        if compressed:
            content = _clip(content, _XML_CLIP_ASSISTANT)
        return f'<assistant ts="{ts}">{_esc(content)}</assistant>'

    if t == "llm_response":
        calls = d.get("tool_calls", [])
        if calls:
            parts = []
            for c in calls:
                args_str = json.dumps(c.get("arguments", {}), ensure_ascii=False)
                if compressed and len(args_str) > 200:
                    args_str = args_str[:197] + "..."
                parts.append(f'<call name="{c["name"]}">{args_str}</call>')
            return f'<llm_response ts="{ts}">{"".join(parts)}</llm_response>'
        content = d.get("content", "")
        if compressed:
            content = _clip(content, _XML_CLIP_ASSISTANT)
        return f'<llm_response ts="{ts}">{_esc(content)}</llm_response>'

    if t == "tool_result":
        result = str(d.get("result", ""))
        if compressed:
            result = _clip(result, _XML_CLIP_TOOL_RESULT)
        return (
            f'<tool_result name="{d.get("name", "")}" '
            f'call_id="{d.get("call_id", "")}" ts="{ts}">'
            f'{_esc(result)}'
            f'</tool_result>'
        )

    if t == "error":
        msg = d.get("message", "")
        if compressed:
            msg = _clip(msg, _XML_CLIP_ERROR)
        return (
            f'<error tool="{d.get("name", d.get("tool", ""))}" '
            f'ts="{ts}">{_esc(msg)}</error>'
        )

    if t == "human_input_request":
        return f'<human_request ts="{ts}">{_esc(d.get("question", str(d)))}</human_request>'

    if t == "human_input_response":
        return f'<human_response ts="{ts}">{_esc(d.get("response", ""))}</human_response>'

    if t == "compact_summary":
        summary = d.get("summary", "")
        compacted = d.get("compacted_events", 0)
        return (
            f'<compact_summary compacted_events="{compacted}" ts="{ts}">'
            f'{_esc(summary)}'
            f'</compact_summary>'
        )

    # system / 其他
    return f'<system ts="{ts}">{_esc(json.dumps(d, ensure_ascii=False))}</system>'


def _esc(text: str) -> str:
    """简单 XML 转义，防止内容中的 < > & 破坏结构"""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


# ─── Tool-call 分组 ─────────────────────────────────────────────────────────


def _group_events_by_toolcall(events: list[Event]) -> list[list[Event]]:
    """
    将事件按 tool-call 组分组，保证 llm_response + 对应 tool_result/error 不被拆散。

    分组规则：
      - llm_response(有 tool_calls) + 后续匹配的 tool_result/error → 一组
      - user_message, assistant_message, 其他 → 各自独立一组
    """
    groups: list[list[Event]] = []
    i = 0
    while i < len(events):
        ev = events[i]
        if ev.type == "llm_response" and ev.data.get("tool_calls"):
            # 收集这个 llm_response 及其后续的 tool_result/error
            call_ids = {c["call_id"] for c in ev.data["tool_calls"]}
            group = [ev]
            j = i + 1
            while j < len(events) and events[j].type in ("tool_result", "error"):
                group.append(events[j])
                cid = events[j].data.get("call_id", "")
                call_ids.discard(cid)
                j += 1
                if not call_ids:
                    break
            groups.append(group)
            i = j
        else:
            groups.append([ev])
            i += 1
    return groups


# ─── 核心：Thread → LLM messages ──────────────────────────────────────────────


# 默认 token budget: 旧历史 + 最近事件一共不超过此值
DEFAULT_CONTEXT_TOKEN_BUDGET = 12000


def build_context_messages(
    thread: Thread,
    system_prompt: str,
    tools_schema: list[dict],
    max_recent_events: int = 40,
    prefetch_context: str | None = None,
    memory_context: str | None = None,
    recalled_memories: str | None = None,
    context_token_budget: int | None = None,
) -> list[dict[str, Any]]:
    """
    将 Thread 构建为 LLM 可消费的 messages 列表。

    策略（Factor 3）：
      1. 系统 Prompt
      2. [可选] 持久记忆上下文（MEMORY.md + 每日笔记）
      3. [可选] 预取上下文（Factor 13）—— 确定性地注入已知信息，省 LLM round-trip
      4. [可选] 自动检索到的相关记忆
      5. 超出 budget 的旧历史 → 压缩为 XML 块（含内容截断）
      6. 最近事件 → 按 OpenAI messages 格式逐条转换

    改进：
      - Token-aware: 按 token budget 动态决定 recent/old 边界
      - Tool-call 分组: llm_response + tool_result 作为原子组不被拆散
      - 压缩时截断: 旧历史中的长内容在 XML 中做截断
    """
    budget = context_token_budget or DEFAULT_CONTEXT_TOKEN_BUDGET

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt}
    ]

    # 三层记忆架构：注入 MEMORY.md + 每日笔记
    if memory_context:
        messages.append({
            "role": "user",
            "content": f"<persistent_memory>\n{memory_context}\n</persistent_memory>",
        })
        messages.append({
            "role": "assistant",
            "content": "已读取持久记忆上下文。",
        })

    # Factor 13：注入预取的上下文
    if prefetch_context:
        messages.append({
            "role": "user",
            "content": f"<prefetched_context>\n{prefetch_context}\n</prefetched_context>",
        })
        messages.append({
            "role": "assistant",
            "content": "已读取预取上下文。",
        })

    # 自动回忆：注入语义检索到的相关记忆
    if recalled_memories:
        messages.append({
            "role": "user",
            "content": f"<recalled_memories>\n{recalled_memories}\n</recalled_memories>",
        })
        messages.append({
            "role": "assistant",
            "content": "已读取相关记忆。",
        })

    # 过滤掉纯系统内部事件（不送给 LLM）
    visible: list[Event] = [
        e for e in thread.events if e.type != "system"
    ]

    # Token-aware 切分：按组从尾部向前填充 recent，超出的进 old
    groups = _group_events_by_toolcall(visible)
    recent_groups, old_groups = _split_by_budget(
        groups, budget=budget, max_recent=max_recent_events,
    )

    # 将旧历史压缩为 XML（Factor 3）—— 内容截断以节省 token
    if old_groups:
        old_events = [ev for group in old_groups for ev in group]
        xml = "\n".join(event_to_xml(e, compressed=True) for e in old_events)
        messages.append({
            "role": "user",
            "content": (
                f"<conversation_history "
                f"compressed_events='{len(old_events)}'>\n{xml}\n</conversation_history>"
            ),
        })
        messages.append({
            "role": "assistant",
            "content": "已读取历史对话记录。",
        })

    # 将最近事件逐条转换为标准 OpenAI messages
    recent_events = [ev for group in recent_groups for ev in group]
    messages.extend(_events_to_messages(recent_events))
    return messages


def _split_by_budget(
    groups: list[list[Event]],
    budget: int,
    max_recent: int,
) -> tuple[list[list[Event]], list[list[Event]]]:
    """
    从尾部向前填充 recent 组，直到超出 token budget 或 max_recent event 数。
    返回 (recent_groups, old_groups)，均保持原始顺序。
    """
    if not groups:
        return [], []

    # 计算所有组的 token 数
    group_tokens = [
        sum(_estimate_event_tokens(ev) for ev in group)
        for group in groups
    ]

    total_tokens = sum(group_tokens)
    total_events = sum(len(g) for g in groups)

    # 全部都能放下
    if total_tokens <= budget and total_events <= max_recent:
        return list(groups), []

    # 从尾部向前收集
    recent_indices: list[int] = []
    used_tokens = 0
    used_events = 0

    for i in range(len(groups) - 1, -1, -1):
        g_tokens = group_tokens[i]
        g_events = len(groups[i])
        if used_tokens + g_tokens > budget or used_events + g_events > max_recent:
            break
        recent_indices.append(i)
        used_tokens += g_tokens
        used_events += g_events

    recent_indices.reverse()
    split_point = recent_indices[0] if recent_indices else len(groups)

    old_groups = groups[:split_point]
    recent_groups = groups[split_point:]

    return recent_groups, old_groups


def _events_to_messages(events: list[Event]) -> list[dict[str, Any]]:
    """
    将事件列表转换为 OpenAI messages 格式。

    关键约束（OpenAI API 要求）：
      每个 assistant 消息中的 tool_call_id 必须有一个对应的 tool 消息。
    我们的 Thread 设计：
      llm_response 事件存储一次 LLM 调用产生的全部 tool_calls（含 call_id），
      tool_result / error 事件各自携带 call_id 对应回去。
    因此 llm_response → assistant message，tool_result/error → tool message，天然配对。
    """
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(events):
        event = events[i]

        # ── 用户消息 ──────────────────────────────────────────────────────────
        if event.type == "user_message":
            out.append({"role": "user", "content": event.data.get("content", "")})

        # ── 纯文本 LLM 回复 ────────────────────────────────────────────────────
        elif event.type == "assistant_message":
            out.append({"role": "assistant", "content": event.data.get("content", "")})

        # ── LLM 响应（含工具调用）────────────────────────────────────────────
        elif event.type == "llm_response":
            tool_calls = event.data.get("tool_calls", [])
            content = event.data.get("content")
            if tool_calls:
                # 将 tool_calls 列表格式化为 OpenAI 期望的结构
                out.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tc["call_id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(
                                    tc.get("arguments", {}),
                                    ensure_ascii=False,
                                ),
                            },
                        }
                        for tc in tool_calls
                    ],
                })
            elif content:
                out.append({"role": "assistant", "content": content})

        # ── 工具执行结果 ───────────────────────────────────────────────────────
        elif event.type == "tool_result":
            out.append({
                "role": "tool",
                "tool_call_id": event.data.get("call_id", ""),
                "content": str(event.data.get("result", "")),
            })

        # ── 工具执行错误（Factor 9：压缩进上下文，让 LLM 自愈）────────────────
        elif event.type == "error":
            call_id = event.data.get("call_id", "")
            msg = event.data.get("message", "未知错误")
            err_type = event.data.get("type", "Error")
            if call_id:
                # 对应已有的 tool_call，作为 tool 消息返回
                out.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": f"[{err_type}] {msg}",
                })
            else:
                # 独立错误（如 LLM 调用失败），作为 user 消息提示
                out.append({
                    "role": "user",
                    "content": f"[系统错误] {err_type}: {msg}",
                })

        # ── 人类交互 ───────────────────────────────────────────────────────────
        elif event.type == "human_input_request":
            # 已记录在 Thread 中，重建消息时无需再发给 LLM（除非后续恢复时需要上下文）
            pass

        elif event.type == "human_input_response":
            out.append({
                "role": "user",
                "content": f"[Human Response] {event.data.get('response', '')}",
            })

        # ── 压缩摘要（注入为 user 消息，让 LLM 了解之前的上下文）──────────────
        elif event.type == "compact_summary":
            summary = event.data.get("summary", "")
            compacted = event.data.get("compacted_events", 0)
            out.append({
                "role": "user",
                "content": (
                    f"<compacted_history events='{compacted}'>\n"
                    f"{summary}\n"
                    f"</compacted_history>"
                ),
            })
            out.append({
                "role": "assistant",
                "content": "已读取压缩的历史上下文。",
            })

        i += 1
    return out


def thread_to_input_items(thread: Thread) -> list[dict[str, Any]]:
    """Convert a thread into replayable non-system input items for SDK resume flows."""
    visible: list[Event] = [event for event in thread.events if event.type != "system"]
    return _events_to_messages(visible)


# ─── 记忆刷写检测 ──────────────────────────────────────────────────────────────

def should_flush_memories(thread: Thread, threshold: int = 30) -> bool:
    """
    当可见事件数 >= threshold 时返回 True，提示应在压缩前刷写记忆。

    用于 runner 在每轮循环中检测是否需要将上下文中的重要信息
    持久化到每日笔记/MEMORY.md，防止压缩时丢失。
    """
    visible = [e for e in thread.events if e.type != "system"]
    return len(visible) >= threshold
