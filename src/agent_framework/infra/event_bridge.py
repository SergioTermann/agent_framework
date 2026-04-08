"""
事件桥接 —— 将 CallbackManager 事件转发到 EventBus

用法：
    from agent_framework.infra.event_bridge import EventBridge
    from agent_framework.agent.callbacks import CallbackManager
    from agent_framework.platform.extension_system import EventBus

    cb = CallbackManager()
    bus = EventBus()
    bridge = EventBridge(cb, bus)
    bridge.connect()
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_framework.agent.callbacks import CallbackManager, CallbackEvent
    from agent_framework.platform.extension_system import EventBus

logger = logging.getLogger(__name__)

# 需要桥接的事件类型
_BRIDGED_EVENTS = [
    "llm_start",
    "llm_end",
    "llm_error",
    "tool_call_start",
    "tool_call_end",
    "tool_call_error",
    "permission_request",
    "permission_denied",
    "round_start",
    "round_end",
]


class EventBridge:
    """CallbackManager → EventBus 单向桥接"""

    def __init__(self, callback_manager: "CallbackManager", event_bus: "EventBus"):
        self._cb = callback_manager
        self._bus = event_bus

    def connect(self, events: list[str] | None = None) -> None:
        """注册桥接回调，将指定事件从 CallbackManager 转发到 EventBus"""
        for event_name in (events or _BRIDGED_EVENTS):
            self._cb.on(event_name, self._make_forwarder(event_name))

    def _make_forwarder(self, event_name: str):
        bus = self._bus

        def forwarder(event: "CallbackEvent"):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(bus.emit(event_name, event.data))
                else:
                    loop.run_until_complete(bus.emit(event_name, event.data))
            except RuntimeError:
                # 没有事件循环时同步触发同步监听器
                for cb in bus.listeners.get(event_name, []):
                    if not asyncio.iscoroutinefunction(cb):
                        try:
                            cb(event.data)
                        except Exception as e:
                            logger.warning("EventBridge 同步转发失败 %s: %s", event_name, e)

        return forwarder
