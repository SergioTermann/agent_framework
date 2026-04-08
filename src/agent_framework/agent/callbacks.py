"""
回调系统 - 监控 Agent 执行过程
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from agent_framework.agent.thread import Thread


@dataclass
class CallbackEvent:
    """回调事件"""
    event_type: str          # 事件类型
    data: dict[str, Any]     # 事件数据
    thread_id: str           # Thread ID
    timestamp: float = field(default_factory=lambda: __import__('time').time())


class CallbackManager:
    """
    回调管理器 - 统一管理所有回调函数

    支持的事件类型:
        - llm_start: LLM 调用开始
        - llm_end: LLM 调用结束
        - llm_error: LLM 调用错误
        - tool_call_start: 工具调用开始
        - tool_call_end: 工具调用结束
        - tool_call_error: 工具调用错误
        - permission_request: 工具命中 ask 规则，需请求审批
        - permission_denied: 工具被权限规则拒绝
        - round_start: 轮次开始
        - round_end: 轮次结束
        - agent_start: Agent 启动
        - agent_end: Agent 结束
        - error: 错误发生
        - human_request: 人类请求
    """

    def __init__(self):
        self._callbacks: dict[str, list[Callable]] = {}

    def on(self, event_type: str, callback: Callable[[CallbackEvent], None]):
        """注册回调函数"""
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        self._callbacks[event_type].append(callback)

    def off(self, event_type: str, callback: Callable[[CallbackEvent], None]):
        """移除回调函数"""
        if event_type in self._callbacks:
            self._callbacks[event_type].remove(callback)

    def trigger(self, event_type: str, data: dict[str, Any], thread_id: str):
        """触发回调"""
        if event_type not in self._callbacks:
            return

        event = CallbackEvent(
            event_type=event_type,
            data=data,
            thread_id=thread_id,
        )

        for callback in self._callbacks[event_type]:
            try:
                callback(event)
            except Exception as e:
                # 回调错误不应该影响主流程
                print(f"[WARNING] Callback error in {event_type}: {e}")

    def clear(self, event_type: Optional[str] = None):
        """清除回调函数"""
        if event_type:
            self._callbacks[event_type] = []
        else:
            self._callbacks.clear()


# ─── 预定义回调函数 ────────────────────────────────────────────────────────────

def print_callback(event: CallbackEvent):
    """打印回调事件（用于调试）"""
    print(f"[{event.event_type}] {event.data}")


def log_callback(event: CallbackEvent):
    """记录回调事件到日志"""
    import logging
    logger = logging.getLogger("agent.callbacks")
    logger.info(f"{event.event_type}: {event.data}")


class PerformanceMonitor:
    """性能监控回调"""

    def __init__(self):
        self.stats = {
            "llm_calls": 0,
            "llm_total_time": 0.0,
            "tool_calls": 0,
            "tool_total_time": 0.0,
            "rounds": 0,
        }
        self._start_times = {}

    def on_llm_start(self, event: CallbackEvent):
        self._start_times[f"llm_{event.thread_id}"] = event.timestamp

    def on_llm_end(self, event: CallbackEvent):
        key = f"llm_{event.thread_id}"
        if key in self._start_times:
            elapsed = event.timestamp - self._start_times[key]
            self.stats["llm_calls"] += 1
            self.stats["llm_total_time"] += elapsed
            del self._start_times[key]

    def on_tool_call_start(self, event: CallbackEvent):
        key = f"tool_{event.thread_id}_{event.data.get('tool_name', '')}"
        self._start_times[key] = event.timestamp

    def on_tool_call_end(self, event: CallbackEvent):
        key = f"tool_{event.thread_id}_{event.data.get('tool_name', '')}"
        if key in self._start_times:
            elapsed = event.timestamp - self._start_times[key]
            self.stats["tool_calls"] += 1
            self.stats["tool_total_time"] += elapsed
            del self._start_times[key]

    def on_round_end(self, event: CallbackEvent):
        self.stats["rounds"] += 1

    def get_report(self) -> str:
        """生成性能报告"""
        avg_llm = (
            self.stats["llm_total_time"] / self.stats["llm_calls"]
            if self.stats["llm_calls"] > 0
            else 0
        )
        avg_tool = (
            self.stats["tool_total_time"] / self.stats["tool_calls"]
            if self.stats["tool_calls"] > 0
            else 0
        )

        return f"""
性能统计:
  LLM 调用: {self.stats['llm_calls']} 次
  LLM 总耗时: {self.stats['llm_total_time']:.2f}秒
  LLM 平均耗时: {avg_llm:.2f}秒

  工具调用: {self.stats['tool_calls']} 次
  工具总耗时: {self.stats['tool_total_time']:.2f}秒
  工具平均耗时: {avg_tool:.2f}秒

  总轮次: {self.stats['rounds']}
"""


class TokenCounter:
    """Token 使用统计"""

    def __init__(self):
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def on_llm_end(self, event: CallbackEvent):
        usage = event.data.get("usage", {})
        self.total_tokens += usage.get("total_tokens", 0)
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.calls += 1

    def get_report(self) -> str:
        """生成 Token 使用报告"""
        avg_tokens = self.total_tokens / self.calls if self.calls > 0 else 0

        return f"""
Token 使用统计:
  总 Token: {self.total_tokens}
  输入 Token: {self.prompt_tokens}
  输出 Token: {self.completion_tokens}
  调用次数: {self.calls}
  平均 Token: {avg_tokens:.0f}
"""

    def estimate_cost(self, input_price: float = 0.0001, output_price: float = 0.0002) -> float:
        """
        估算成本（美元）

        :param input_price: 输入价格（美元/1K tokens）
        :param output_price: 输出价格（美元/1K tokens）
        """
        input_cost = (self.prompt_tokens / 1000) * input_price
        output_cost = (self.completion_tokens / 1000) * output_price
        return input_cost + output_cost
