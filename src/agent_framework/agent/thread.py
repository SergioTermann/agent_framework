"""
Factor 5 ── 统一执行状态与业务状态
Factor 12 ── 无状态 Reducer

Thread = 有序事件列表，是系统唯一真实来源。
Agent 本质是 (Thread, Event) -> Thread 的纯函数，自身不保存任何运行时状态。
"""

from __future__ import annotations

import copy
import agent_framework.core.fast_json as json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# 所有合法的事件类型
EventType = Literal[
    "user_message",          # 用户输入
    "assistant_message",     # LLM 纯文本回复（无工具调用）
    "llm_response",          # LLM 完整响应（含 tool_calls 数组）
    "tool_result",           # 工具执行成功结果
    "error",                 # 工具执行失败
    "human_input_request",   # Agent 请求人类决策（Factor 7）
    "human_input_response",  # 人类的响应
    "system",                # 系统内部事件（启动/暂停/恢复/超限）
    "compact_summary",       # 上下文压缩摘要（替换被压缩的旧事件）
]


@dataclass
class Event:
    """Thread 的原子单元 —— 单次发生的事情"""

    type: EventType
    data: dict[str, Any]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    event_id: str = field(
        default_factory=lambda: str(uuid.uuid4())[:8]
    )

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            type=d["type"],
            data=d["data"],
            timestamp=d.get("timestamp", ""),
            event_id=d.get("event_id", ""),
        )


@dataclass
class Thread:
    """
    对话线程 = 事件的有序集合

    Factor 5 : 执行状态（当前步骤、重试次数）和业务状态（工具调用历史）
               统一存储于此，无需两套数据结构。
    Factor 12: 完全可序列化，支持随时 fork / 恢复 / 回放。
    """

    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    events: list[Event] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── 写入 ──────────────────────────────────────────────────────────────────

    def push(self, event_type: EventType, data: dict[str, Any]) -> Event:
        """追加事件并返回该事件"""
        event = Event(type=event_type, data=data)
        self.events.append(event)
        return event

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def last_of_type(self, event_type: EventType) -> Event | None:
        """获取最后一个指定类型的事件"""
        for event in reversed(self.events):
            if event.type == event_type:
                return event
        return None

    def consecutive_errors(self) -> int:
        """
        统计末尾连续错误数（Factor 9）
        遇到第一个非 error 事件即停止计数
        """
        count = 0
        for event in reversed(self.events):
            if event.type == "error":
                count += 1
            elif event.type not in ("system",):
                break
        return count

    def is_paused(self) -> bool:
        """判断线程是否正在等待人类输入（Factor 6 / 7）"""
        # 跳过 system 事件，找到最后一个语义相关的事件
        for event in reversed(self.events):
            if event.type == "system":
                continue
            return event.type == "human_input_request"
        return False

    def is_done(self) -> bool:
        """判断任务是否已完成"""
        last = self.events[-1] if self.events else None
        if last is None:
            return False
        if last.type == "system":
            return last.data.get("event") in (
                "done", "max_rounds_reached", "error_escalated"
            )
        return last.type == "assistant_message"

    # ── 序列化 ────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "events": [e.to_dict() for e in self.events],
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Thread":
        return cls(
            thread_id=d["thread_id"],
            events=[Event.from_dict(e) for e in d.get("events", [])],
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", ""),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, s: str) -> "Thread":
        return cls.from_dict(json.loads(s))

    # ── 分叉（用于并行子 Agent / 回滚）──────────────────────────────────────

    def fork(self, new_id: str | None = None) -> "Thread":
        """
        深拷贝当前 Thread，生成独立快照。
        适用于：多路并行探索、实验性操作前的保护点。
        """
        t = Thread(
            thread_id=new_id or str(uuid.uuid4()),
            metadata=dict(self.metadata),
            created_at=self.created_at,
        )
        t.events = copy.deepcopy(self.events)
        t.metadata["forked_from"] = self.thread_id
        return t

    def __repr__(self) -> str:
        status = "paused" if self.is_paused() else ("done" if self.is_done() else "active")
        return f"<Thread id={self.thread_id[:8]} events={len(self.events)} status={status}>"


def latest_assistant_message(thread: Thread) -> str:
    """Return the latest assistant message content from a thread."""
    for event in reversed(thread.events):
        if event.type == "assistant_message":
            return str(event.data.get("content", "") or "")
    return ""


def collect_tool_calls(thread: Thread) -> list[dict[str, Any]]:
    """Collect normalized tool calls recorded in thread llm_response events."""
    tool_calls: list[dict[str, Any]] = []
    for event in thread.events:
        if event.type != "llm_response":
            continue
        for tool_call in event.data.get("tool_calls", []):
            if isinstance(tool_call, dict):
                tool_calls.append(tool_call)
    return tool_calls
