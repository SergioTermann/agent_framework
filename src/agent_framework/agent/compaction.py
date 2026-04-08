"""
智能上下文压缩 —— 借鉴 Claude Code 的 compaction 机制

核心能力：
  1. 自动压缩检测：token 使用率超阈值时触发
  2. LLM 摘要压缩：调用 LLM 对旧历史生成摘要，替换原始事件
  3. 反应式压缩：收到 context_too_long 错误后紧急压缩
  4. 微压缩：截断单个超大工具结果，不调用 LLM

设计参考：
  - Claude Code 的 compactConversation / shouldAutoCompact
  - Claude Code 的 reactive compact on PTL (prompt-too-long)
  - Claude Code 的 microcompact for oversized tool results
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_framework.agent.thread import Thread, Event
from agent_framework.agent.context import (
    _estimate_tokens,
    _estimate_event_tokens,
    _group_events_by_toolcall,
)

logger = logging.getLogger(__name__)


# ─── 配置 ────────────────────────────────────────────────────────────────────

@dataclass
class CompactionConfig:
    """上下文压缩配置"""

    auto_compact_threshold: float = 0.85
    """token 使用率超过此值时触发自动压缩"""

    context_window_tokens: int = 128_000
    """模型上下文窗口大小（token）"""

    max_ptl_retries: int = 3
    """prompt-too-long 最大重试次数"""

    post_compact_max_files: int = 5
    """压缩后恢复的最大文件数"""

    post_compact_max_tokens_per_file: int = 5000
    """压缩后每文件最大 token"""

    microcompact_threshold: int = 3000
    """单个工具结果超此 token 数触发微压缩"""

    summary_max_tokens: int = 2000
    """LLM 生成摘要的最大 token"""


# ─── 压缩结果 ─────────────────────────────────────────────────────────────────

@dataclass
class CompactionResult:
    """压缩操作结果"""
    success: bool
    events_before: int = 0
    events_after: int = 0
    tokens_saved: int = 0
    summary: str = ""
    method: str = ""  # "auto", "reactive", "micro", "truncate_head"


# ─── 摘要 Prompt ─────────────────────────────────────────────────────────────

_COMPACTION_SYSTEM_PROMPT = """\
You are a conversation summarizer. Given a conversation history between a user and an AI assistant, \
create a concise summary that preserves:
1. The user's original task/goal
2. Key decisions and actions taken
3. Important tool results and findings
4. Current progress and next steps
5. Any errors encountered and how they were resolved

Output ONLY the summary, no preamble. Keep it under {max_tokens} tokens. \
Use bullet points for clarity. Preserve critical details like file paths, \
variable names, and specific values."""

_COMPACTION_USER_PROMPT = """\
Summarize the following conversation history. Focus on preserving information \
needed to continue the task effectively.

<conversation>
{conversation}
</conversation>"""


# ─── CompactionService ────────────────────────────────────────────────────────

class CompactionService:
    """
    智能上下文压缩服务。

    提供三种压缩策略：
      - 自动压缩：token 使用率超阈值时，用 LLM 生成摘要替换旧事件
      - 反应式压缩：收到 context_too_long 错误后紧急截断 + 压缩
      - 微压缩：截断超大工具结果（不调用 LLM）
    """

    def __init__(self, config: CompactionConfig | None = None):
        self.config = config or CompactionConfig()
        self._ptl_attempts = 0

    def should_auto_compact(self, thread: Thread, config: Any = None) -> bool:
        """
        检查当前 token 使用率是否超过自动压缩阈值。

        :param thread: 当前线程
        :param config: RunConfig（可选，用于动态阈值）
        :returns: 是否应触发自动压缩
        """
        visible_events = [e for e in thread.events if e.type != "system"]
        if len(visible_events) < 10:
            return False

        total_tokens = sum(_estimate_event_tokens(e) for e in visible_events)
        threshold = self.config.context_window_tokens * self.config.auto_compact_threshold
        should = total_tokens > threshold

        if should:
            logger.info(
                f"自动压缩检测：{total_tokens} tokens > "
                f"{threshold:.0f} threshold ({self.config.auto_compact_threshold:.0%})"
            )

        return should

    def compact(
        self,
        thread: Thread,
        llm: Any,
        system_prompt: str = "",
    ) -> CompactionResult:
        """
        对旧历史调用 LLM 生成摘要，替换原始事件。

        策略：
          1. 将事件按 tool-call 分组
          2. 保留最近 N 组作为 recent
          3. 对 old 事件生成文本表示
          4. 调用 LLM 生成摘要
          5. 用 compact_summary 事件替换 old 事件

        :param thread: 当前线程
        :param llm: LLM 实例（需有 chat 方法）
        :param system_prompt: 可选的系统提示
        :returns: 压缩结果
        """
        visible = [e for e in thread.events if e.type != "system"]
        system_events = [e for e in thread.events if e.type == "system"]

        if len(visible) < 10:
            return CompactionResult(success=False, method="auto")

        events_before = len(thread.events)
        tokens_before = sum(_estimate_event_tokens(e) for e in visible)

        # 分组并保留最近的事件
        groups = _group_events_by_toolcall(visible)
        keep_recent = max(3, len(groups) // 3)  # 至少保留 3 组或 1/3
        keep_recent = min(keep_recent, 15)  # 最多保留 15 组

        if len(groups) <= keep_recent:
            return CompactionResult(success=False, method="auto")

        old_groups = groups[:-keep_recent]
        recent_groups = groups[-keep_recent:]

        # 生成旧事件的文本表示
        old_text_parts = []
        for group in old_groups:
            for event in group:
                old_text_parts.append(_event_to_text(event))
        old_text = "\n".join(old_text_parts)

        # 调用 LLM 生成摘要
        try:
            summary = self._generate_summary(llm, old_text)
        except Exception as e:
            logger.warning(f"LLM 摘要生成失败，回退到截断压缩: {e}")
            summary = self._fallback_summary(old_groups)

        # 重建事件列表：system 事件 + compact_summary + recent 事件
        new_events: list[Event] = []

        # 保留初始系统事件（用 event_id 匹配，序列化安全）
        early_ids = {e.event_id for e in thread.events[:5]}
        for e in system_events:
            if e.event_id in early_ids:
                new_events.append(e)

        # 插入摘要事件
        summary_event = Event(
            type="compact_summary",
            data={
                "summary": summary,
                "compacted_events": sum(len(g) for g in old_groups),
                "method": "llm_summary",
            },
        )
        new_events.append(summary_event)

        # 保留最近事件
        for group in recent_groups:
            new_events.extend(group)

        # 替换线程事件
        thread.events = new_events

        tokens_after = sum(
            _estimate_event_tokens(e) for e in thread.events if e.type != "system"
        )

        result = CompactionResult(
            success=True,
            events_before=events_before,
            events_after=len(thread.events),
            tokens_saved=max(0, tokens_before - tokens_after),
            summary=summary[:200],
            method="auto",
        )

        logger.info(
            f"上下文压缩完成: {result.events_before} → {result.events_after} 事件, "
            f"节省 ~{result.tokens_saved} tokens"
        )

        return result

    def reactive_compact(
        self,
        thread: Thread,
        llm: Any,
        error: Exception,
    ) -> CompactionResult:
        """
        收到 context_too_long 错误后紧急压缩。

        策略更激进：
          1. 先做微压缩（截断大工具结果）
          2. 如果还不够，尝试 LLM 摘要压缩
          3. 如果 LLM 也失败，直接截断最旧的事件组

        :param thread: 当前线程
        :param llm: LLM 实例
        :param error: 触发压缩的错误
        :returns: 压缩结果
        """
        self._ptl_attempts += 1

        if self._ptl_attempts > self.config.max_ptl_retries:
            logger.warning(f"PTL 重试次数已达上限 ({self.config.max_ptl_retries})")
            return CompactionResult(success=False, method="reactive")

        logger.info(f"反应式压缩 (尝试 {self._ptl_attempts}/{self.config.max_ptl_retries})")

        # 第一步：微压缩
        micro_saved = self.microcompact_tool_results(thread)
        if micro_saved > 0:
            logger.info(f"微压缩节省 ~{micro_saved} tokens")

        # 第二步：解析 token 差额并截断头部
        token_gap = _extract_token_gap(error)
        if token_gap and token_gap > 0:
            truncated = self._truncate_head_for_ptl(thread, token_gap)
            if truncated:
                return CompactionResult(
                    success=True,
                    tokens_saved=token_gap,
                    method="reactive_truncate",
                )

        # 第三步：尝试 LLM 摘要压缩
        try:
            result = self.compact(thread, llm)
            if result.success:
                result.method = "reactive"
                self._ptl_attempts = 0
                return result
        except Exception as e:
            logger.warning(f"反应式 LLM 压缩失败: {e}")

        # 第四步：强制截断最旧的一半事件
        visible = [e for e in thread.events if e.type != "system"]
        if len(visible) > 4:
            cut_point = len(visible) // 2
            system_events = [e for e in thread.events if e.type == "system"]
            kept_visible = visible[cut_point:]

            summary_text = f"[压缩] 已移除 {cut_point} 条旧事件以释放上下文空间。"
            summary_event = Event(
                type="compact_summary",
                data={
                    "summary": summary_text,
                    "compacted_events": cut_point,
                    "method": "forced_truncation",
                },
            )

            new_events = []
            early_ids = {e.event_id for e in thread.events[:5]}
            for e in system_events:
                if e.event_id in early_ids:
                    new_events.append(e)
            new_events.append(summary_event)
            new_events.extend(kept_visible)
            thread.events = new_events

            return CompactionResult(
                success=True,
                events_before=len(visible) + len(system_events),
                events_after=len(thread.events),
                method="reactive_forced",
            )

        return CompactionResult(success=False, method="reactive")

    def microcompact_tool_results(self, thread: Thread) -> int:
        """
        截断单个超大工具结果（不调用 LLM）。

        遍历所有 tool_result 事件，将超过阈值的结果截断。

        :param thread: 当前线程
        :returns: 估计节省的 token 数
        """
        threshold = self.config.microcompact_threshold
        total_saved = 0

        for event in thread.events:
            if event.type != "tool_result":
                continue

            result_str = str(event.data.get("result", ""))
            result_tokens = _estimate_tokens(result_str)

            if result_tokens <= threshold:
                continue

            # 截断到阈值大小
            # 粗略估计：1 token ≈ 3 chars（取保守值）
            max_chars = threshold * 3
            if len(result_str) > max_chars:
                truncated = result_str[:max_chars]
                truncated += f"\n...[microcompacted: {len(result_str) - max_chars} chars removed]"
                event.data["result"] = truncated
                event.data["_microcompacted"] = True

                saved = result_tokens - _estimate_tokens(truncated)
                total_saved += max(0, saved)

                logger.debug(
                    f"微压缩工具结果 '{event.data.get('name', '')}': "
                    f"~{result_tokens} → ~{result_tokens - saved} tokens"
                )

        return total_saved

    def reset_ptl_counter(self) -> None:
        """重置 PTL 重试计数器（成功调用后调用）"""
        self._ptl_attempts = 0

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _generate_summary(self, llm: Any, conversation_text: str) -> str:
        """调用 LLM 生成摘要"""
        messages = [
            {
                "role": "system",
                "content": _COMPACTION_SYSTEM_PROMPT.format(
                    max_tokens=self.config.summary_max_tokens
                ),
            },
            {
                "role": "user",
                "content": _COMPACTION_USER_PROMPT.format(
                    conversation=conversation_text
                ),
            },
        ]

        response = llm.chat(
            messages,
            max_tokens=self.config.summary_max_tokens,
            temperature=0.3,
        )

        return response.content or ""

    def _fallback_summary(self, old_groups: list[list[Event]]) -> str:
        """LLM 失败时的回退摘要策略：提取关键信息"""
        parts = ["[Compacted History Summary]"]

        # 提取用户消息
        user_msgs = []
        tool_results = []
        for group in old_groups:
            for event in group:
                if event.type == "user_message":
                    content = event.data.get("content", "")
                    if content:
                        user_msgs.append(content[:100])
                elif event.type == "tool_result":
                    name = event.data.get("name", "unknown")
                    result = str(event.data.get("result", ""))[:80]
                    tool_results.append(f"{name}: {result}")

        if user_msgs:
            parts.append("User queries: " + " | ".join(user_msgs[:5]))
        if tool_results:
            parts.append("Tool results: " + " | ".join(tool_results[:5]))

        total_events = sum(len(g) for g in old_groups)
        parts.append(f"({total_events} events compacted)")

        return "\n".join(parts)

    def _truncate_head_for_ptl(self, thread: Thread, token_gap: int) -> bool:
        """
        PTL 重试时丢弃最旧的事件组以释放 token_gap 大小的空间。

        :param thread: 当前线程
        :param token_gap: 需要释放的 token 数
        :returns: 是否成功截断
        """
        visible = [e for e in thread.events if e.type != "system"]
        if len(visible) < 4:
            return False

        groups = _group_events_by_toolcall(visible)
        if len(groups) < 3:
            return False

        # 从头部开始移除组，直到释放足够 token
        freed = 0
        remove_count = 0
        for group in groups:
            if freed >= token_gap * 1.2:  # 多释放 20% 留余量
                break
            freed += sum(_estimate_event_tokens(e) for e in group)
            remove_count += 1

        # 至少保留 2 组
        if remove_count >= len(groups) - 1:
            remove_count = max(1, len(groups) - 2)

        if remove_count == 0:
            return False

        # 重建事件
        kept_groups = groups[remove_count:]
        system_events = [e for e in thread.events if e.type == "system"]

        new_events = []
        early_ids = {e.event_id for e in thread.events[:5]}
        for e in system_events:
            if e.event_id in early_ids:
                new_events.append(e)

        removed_count = sum(len(g) for g in groups[:remove_count])
        summary_event = Event(
            type="compact_summary",
            data={
                "summary": f"[Truncated] Removed {removed_count} oldest events to fit context window.",
                "compacted_events": removed_count,
                "method": "ptl_truncation",
            },
        )
        new_events.append(summary_event)

        for group in kept_groups:
            new_events.extend(group)

        thread.events = new_events

        logger.info(f"PTL 截断: 移除 {remove_count} 组 ({removed_count} 事件), 释放 ~{freed} tokens")
        return True


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _event_to_text(event: Event) -> str:
    """将事件转为简洁的文本表示（用于生成摘要的输入）"""
    t = event.type
    d = event.data

    if t == "user_message":
        return f"[User] {d.get('content', '')}"
    if t == "assistant_message":
        return f"[Assistant] {d.get('content', '')}"
    if t == "llm_response":
        calls = d.get("tool_calls", [])
        if calls:
            call_strs = [f"{c['name']}({c.get('arguments', {})})" for c in calls]
            content = d.get("content", "")
            prefix = f"[Assistant] {content}\n" if content else ""
            return f"{prefix}[Tool Calls] {', '.join(call_strs)}"
        return f"[Assistant] {d.get('content', '')}"
    if t == "tool_result":
        result = str(d.get("result", ""))
        if len(result) > 500:
            result = result[:500] + "..."
        return f"[Tool Result: {d.get('name', '')}] {result}"
    if t == "error":
        return f"[Error: {d.get('name', d.get('tool', ''))}] {d.get('message', '')}"
    if t == "human_input_request":
        return f"[Human Request] {d.get('question', str(d))}"
    if t == "human_input_response":
        return f"[Human Response] {d.get('response', '')}"
    if t == "compact_summary":
        return f"[Previous Summary] {d.get('summary', '')}"

    return f"[{t}] {d}"


def _extract_token_gap(error: Exception) -> int | None:
    """
    从错误消息中解析 token 差额。

    常见格式：
      - "maximum context length is 128000 tokens. However, you requested 150000 tokens"
      - "prompt is too long: 150000 tokens > 128000 token limit"
    """
    import re
    msg = str(error)

    # 格式 1: "requested X tokens ... maximum ... Y tokens"
    m = re.search(r"requested\s+(\d+)\s+tokens.*?maximum.*?(\d+)", msg, re.IGNORECASE)
    if m:
        requested = int(m.group(1))
        maximum = int(m.group(2))
        return requested - maximum

    # 格式 2: "X tokens > Y token limit"
    m = re.search(r"(\d+)\s+tokens?\s*>\s*(\d+)", msg, re.IGNORECASE)
    if m:
        actual = int(m.group(1))
        limit = int(m.group(2))
        return actual - limit

    # 格式 3: "maximum context length is Y ... you requested X"
    m = re.search(r"maximum.*?(\d+).*?requested.*?(\d+)", msg, re.IGNORECASE)
    if m:
        maximum = int(m.group(1))
        requested = int(m.group(2))
        return requested - maximum

    return None
