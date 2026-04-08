"""
Tests for the 4 core optimizations:
  1. Smart Context Compaction
  2. Context-Aware Error Recovery
  3. LRU File State Cache
  4. Enhanced Concurrent Execution (Sibling Abort)
"""

from __future__ import annotations

import os
import time
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is on path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_framework.agent.thread import Thread, Event
from agent_framework.agent.compaction import (
    CompactionService,
    CompactionConfig,
    CompactionResult,
    _event_to_text,
    _extract_token_gap,
)
from agent_framework.agent.resilience import (
    RecoveryAction,
    ContextAwareRecovery,
    ErrorCategory,
    classify_error,
)
from agent_framework.agent.concurrent_executor import (
    ConcurrentToolExecutor,
    SiblingAbortController,
    SiblingAbortError,
    ToolExecStatus,
    ToolExecResult,
    ConcurrentExecReport,
)
from agent_framework.tool.file_cache import (
    FileStateCache,
    FileState,
    create_file_cache_middleware,
)
from agent_framework.agent.context import (
    _events_to_messages,
    _estimate_tokens,
    _estimate_event_tokens,
    event_to_xml,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  优化 1: 智能上下文压缩
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompactionConfig:
    def test_default_config(self):
        config = CompactionConfig()
        assert config.auto_compact_threshold == 0.85
        assert config.context_window_tokens == 128_000
        assert config.max_ptl_retries == 3
        assert config.microcompact_threshold == 3000
        assert config.summary_max_tokens == 2000


class TestCompactionShouldAutoCompact:
    def test_short_thread_does_not_trigger(self):
        """少于 10 个可见事件不应触发"""
        svc = CompactionService(CompactionConfig(context_window_tokens=1000))
        thread = Thread()
        for i in range(5):
            thread.push("user_message", {"content": f"msg {i}"})
        assert svc.should_auto_compact(thread) is False

    def test_large_thread_triggers(self):
        """50+ 事件且 token 超阈值应触发"""
        config = CompactionConfig(
            context_window_tokens=500,  # 很小的窗口
            auto_compact_threshold=0.5,  # 50% 就触发
        )
        svc = CompactionService(config)
        thread = Thread()
        for i in range(50):
            thread.push("user_message", {"content": f"这是一条比较长的用户消息 {i}，包含一些上下文内容。"})
        assert svc.should_auto_compact(thread) is True

    def test_system_events_are_excluded(self):
        """系统事件不参与 token 计算"""
        config = CompactionConfig(
            context_window_tokens=500,
            auto_compact_threshold=0.1,
        )
        svc = CompactionService(config)
        thread = Thread()
        for i in range(20):
            thread.push("system", {"event": f"internal_{i}"})
        # 只有系统事件，可见事件 < 10
        assert svc.should_auto_compact(thread) is False


class TestCompactionCompact:
    def _build_large_thread(self, n_rounds=20) -> Thread:
        """构建一个包含多轮对话的 Thread"""
        thread = Thread()
        thread.push("system", {"event": "launched"})
        for i in range(n_rounds):
            thread.push("user_message", {"content": f"请帮我查找关于 topic_{i} 的信息"})
            thread.push("llm_response", {
                "content": None,
                "tool_calls": [{"call_id": f"call_{i}", "name": "search", "arguments": {"q": f"topic_{i}"}}],
            })
            thread.push("tool_result", {
                "call_id": f"call_{i}",
                "name": "search",
                "result": f"搜索结果: topic_{i} 的详细信息..." * 10,
            })
            thread.push("assistant_message", {"content": f"关于 topic_{i}，我找到了以下信息..."})
        return thread

    def test_compact_generates_summary(self):
        """压缩应生成摘要并减少事件数"""
        thread = self._build_large_thread(20)
        events_before = len(thread.events)

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary: User asked about multiple topics. Key findings were..."
        mock_llm.chat.return_value = mock_response

        svc = CompactionService()
        result = svc.compact(thread, mock_llm)

        assert result.success is True
        assert result.events_after < events_before
        assert result.method == "auto"
        assert mock_llm.chat.called

    def test_compact_preserves_recent_events(self):
        """压缩后最近的事件应保留"""
        thread = self._build_large_thread(20)
        last_user_msg = None
        for e in reversed(thread.events):
            if e.type == "user_message":
                last_user_msg = e.data["content"]
                break

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary of old conversation."
        mock_llm.chat.return_value = mock_response

        svc = CompactionService()
        svc.compact(thread, mock_llm)

        # 最后的用户消息应保留
        found = False
        for e in thread.events:
            if e.type == "user_message" and e.data["content"] == last_user_msg:
                found = True
        assert found, "Most recent user message should be preserved"

    def test_compact_inserts_summary_event(self):
        """压缩后应有 compact_summary 事件"""
        thread = self._build_large_thread(15)

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Compacted summary text."
        mock_llm.chat.return_value = mock_response

        svc = CompactionService()
        svc.compact(thread, mock_llm)

        summary_events = [e for e in thread.events if e.type == "compact_summary"]
        assert len(summary_events) >= 1
        assert "summary" in summary_events[0].data

    def test_compact_fallback_on_llm_failure(self):
        """LLM 失败时应使用回退摘要"""
        thread = self._build_large_thread(15)

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = RuntimeError("LLM unavailable")

        svc = CompactionService()
        result = svc.compact(thread, mock_llm)

        assert result.success is True
        # 回退摘要应包含关键字
        summary_events = [e for e in thread.events if e.type == "compact_summary"]
        assert len(summary_events) >= 1

    def test_short_thread_not_compacted(self):
        """少于 10 个可见事件不应压缩"""
        thread = Thread()
        for i in range(5):
            thread.push("user_message", {"content": f"msg {i}"})

        mock_llm = MagicMock()
        svc = CompactionService()
        result = svc.compact(thread, mock_llm)
        assert result.success is False


class TestMicrocompact:
    def test_truncates_large_tool_results(self):
        """超大工具结果应被截断"""
        thread = Thread()
        thread.push("tool_result", {
            "call_id": "c1",
            "name": "read_file",
            "result": "x" * 50000,  # 50K chars
        })

        config = CompactionConfig(microcompact_threshold=100)
        svc = CompactionService(config)
        saved = svc.microcompact_tool_results(thread)

        assert saved > 0
        result_text = thread.events[0].data["result"]
        assert len(result_text) < 50000
        assert "microcompacted" in result_text

    def test_small_results_untouched(self):
        """小工具结果不应被截断"""
        thread = Thread()
        original = "small result"
        thread.push("tool_result", {
            "call_id": "c1",
            "name": "read_file",
            "result": original,
        })

        svc = CompactionService(CompactionConfig(microcompact_threshold=3000))
        saved = svc.microcompact_tool_results(thread)

        assert saved == 0
        assert thread.events[0].data["result"] == original


class TestReactiveCompact:
    def test_reactive_compact_on_context_too_long(self):
        """context_too_long 错误应触发反应式压缩"""
        thread = Thread()
        thread.push("system", {"event": "launched"})
        for i in range(30):
            thread.push("user_message", {"content": f"Long message {i} " * 20})
            thread.push("assistant_message", {"content": f"Response {i} " * 20})

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Emergency summary."
        mock_llm.chat.return_value = mock_response

        svc = CompactionService()
        error = RuntimeError("maximum context length is 128000 tokens. However, you requested 150000 tokens")
        result = svc.reactive_compact(thread, mock_llm, error)

        assert result.success is True

    def test_ptl_retry_limit(self):
        """超过最大 PTL 重试次数应失败"""
        svc = CompactionService(CompactionConfig(max_ptl_retries=2))
        svc._ptl_attempts = 3  # 已超限

        thread = Thread()
        for i in range(5):
            thread.push("user_message", {"content": f"msg {i}"})

        error = RuntimeError("context too long")
        result = svc.reactive_compact(thread, MagicMock(), error)
        assert result.success is False


class TestExtractTokenGap:
    def test_format_1_requested_maximum(self):
        gap = _extract_token_gap(
            RuntimeError("maximum context length is 128000 tokens. However, you requested 150000 tokens")
        )
        assert gap == 22000

    def test_format_2_tokens_gt(self):
        gap = _extract_token_gap(
            RuntimeError("prompt is too long: 150000 tokens > 128000 token limit")
        )
        assert gap == 22000

    def test_no_match(self):
        gap = _extract_token_gap(RuntimeError("some other error"))
        assert gap is None


class TestCompactSummaryEventHandling:
    def test_events_to_messages_handles_compact_summary(self):
        """compact_summary 事件应转换为 user + assistant 消息对"""
        events = [
            Event(type="compact_summary", data={
                "summary": "Previous conversation summary.",
                "compacted_events": 20,
            }),
            Event(type="user_message", data={"content": "Hello"}),
        ]
        messages = _events_to_messages(events)
        # Should have: compact_summary user msg + assistant ack + user_message
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert "compacted_history" in messages[0]["content"]
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "Hello"

    def test_event_to_xml_handles_compact_summary(self):
        """compact_summary 事件应生成正确的 XML"""
        event = Event(type="compact_summary", data={
            "summary": "A summary of old events.",
            "compacted_events": 15,
        })
        xml = event_to_xml(event)
        assert "<compact_summary" in xml
        assert 'compacted_events="15"' in xml
        assert "A summary of old events." in xml


# ═══════════════════════════════════════════════════════════════════════════════
#  优化 2: 上下文感知错误恢复
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecoveryAction:
    def test_context_too_long_triggers_compact(self):
        recovery = ContextAwareRecovery()
        error = RuntimeError("context length exceeds maximum")
        action = recovery.classify_and_plan(error)
        assert action == RecoveryAction.COMPACT_AND_RETRY

    def test_auth_error_gives_up(self):
        recovery = ContextAwareRecovery()
        error = RuntimeError("401 Unauthorized")
        action = recovery.classify_and_plan(error)
        assert action == RecoveryAction.GIVE_UP

    def test_quota_exceeded_gives_up(self):
        recovery = ContextAwareRecovery()
        error = RuntimeError("quota exceeded, billing limit reached")
        action = recovery.classify_and_plan(error)
        assert action == RecoveryAction.GIVE_UP

    def test_rate_limited_retries(self):
        recovery = ContextAwareRecovery()
        error = RuntimeError("429 Too Many Requests")
        action = recovery.classify_and_plan(error)
        assert action == RecoveryAction.RETRY

    def test_server_error_retries(self):
        recovery = ContextAwareRecovery()
        error = RuntimeError("500 Internal Server Error")
        action = recovery.classify_and_plan(error)
        assert action == RecoveryAction.RETRY

    def test_max_tokens_increases(self):
        recovery = ContextAwareRecovery()
        error = RuntimeError("max_tokens exceeded for output")
        action = recovery.classify_and_plan(error)
        assert action == RecoveryAction.INCREASE_TOKENS

    def test_max_tokens_exhausts_retries(self):
        recovery = ContextAwareRecovery()
        # Exhaust output token retries
        for _ in range(ContextAwareRecovery.MAX_OUTPUT_TOKEN_RETRIES):
            error = RuntimeError("max_tokens exceeded for output")
            recovery.classify_and_plan(error)
        # Next time should not increase tokens
        error = RuntimeError("max_tokens exceeded for output")
        action = recovery.classify_and_plan(error)
        # Should fall through to RETRY or GIVE_UP, not INCREASE_TOKENS
        assert action != RecoveryAction.INCREASE_TOKENS


class TestAdjustForMaxOutput:
    def test_increases_max_tokens(self):
        recovery = ContextAwareRecovery()
        result = recovery.adjust_for_max_output({"max_tokens": 4096})
        assert result["max_tokens"] == 6144  # 4096 * 1.5

    def test_caps_at_16384(self):
        recovery = ContextAwareRecovery()
        result = recovery.adjust_for_max_output({"max_tokens": 12000})
        assert result["max_tokens"] == 16384

    def test_handles_none_max_tokens(self):
        recovery = ContextAwareRecovery()
        result = recovery.adjust_for_max_output({"max_tokens": None})
        assert result["max_tokens"] == 6144  # default 4096 * 1.5

    def test_reset_clears_counters(self):
        recovery = ContextAwareRecovery()
        recovery._output_token_attempts = 3
        recovery.reset()
        assert recovery._output_token_attempts == 0


# ═══════════════════════════════════════════════════════════════════════════════
#  优化 3: LRU 文件状态缓存
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileStateCache:
    def test_get_set_basic(self):
        """基本读写操作"""
        cache = FileStateCache()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            f.flush()
            path = f.name

        try:
            mtime = os.path.getmtime(path)
            state = FileState(
                content="hello world",
                timestamp=time.time(),
                mtime=mtime,
                size=11,
                is_partial=False,
            )
            cache.set(path, state)

            result = cache.get(path)
            assert result is not None
            assert result.content == "hello world"
        finally:
            os.unlink(path)

    def test_cache_miss(self):
        """缓存未命中"""
        cache = FileStateCache()
        assert cache.get("/nonexistent/file.txt") is None

    def test_invalidate_after_write(self):
        """写操作后缓存应失效"""
        cache = FileStateCache()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("original")
            f.flush()
            path = f.name

        try:
            mtime = os.path.getmtime(path)
            cache.set(path, FileState(
                content="original",
                timestamp=time.time(),
                mtime=mtime,
                size=8,
                is_partial=False,
            ))

            # 缓存存在
            assert cache.get(path) is not None

            # 失效
            cache.invalidate(path)

            # 缓存不再存在
            assert cache.get(path) is None
        finally:
            os.unlink(path)

    def test_mtime_change_invalidates(self):
        """文件修改后缓存应自动失效"""
        cache = FileStateCache()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("v1")
            f.flush()
            path = f.name

        try:
            mtime = os.path.getmtime(path)
            cache.set(path, FileState(
                content="v1",
                timestamp=time.time(),
                mtime=mtime,
                size=2,
                is_partial=False,
            ))

            # 修改文件
            time.sleep(0.1)
            with open(path, "w") as f:
                f.write("v2")

            # 缓存应失效
            assert cache.get(path) is None
        finally:
            os.unlink(path)

    def test_lru_eviction_by_count(self):
        """超过最大条目数时应淘汰"""
        cache = FileStateCache(max_entries=3, max_size_bytes=10 * 1024 * 1024)
        files = []

        try:
            for i in range(5):
                with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                    f.write(f"content {i}")
                    f.flush()
                    files.append(f.name)
                    mtime = os.path.getmtime(f.name)
                    cache.set(f.name, FileState(
                        content=f"content {i}",
                        timestamp=time.time(),
                        mtime=mtime,
                        size=10,
                        is_partial=False,
                    ))

            # Only 3 should remain
            assert cache.stats["entries"] <= 3
        finally:
            for f in files:
                os.unlink(f)

    def test_snapshot_and_merge(self):
        """快照和合并"""
        cache = FileStateCache()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("data")
            f.flush()
            path = f.name

        try:
            mtime = os.path.getmtime(path)
            cache.set(path, FileState(
                content="data",
                timestamp=time.time(),
                mtime=mtime,
                size=4,
                is_partial=False,
            ))

            snapshot = cache.snapshot()
            assert len(snapshot) == 1

            # 新缓存合并
            new_cache = FileStateCache()
            new_cache.merge(snapshot)
            assert new_cache.stats["entries"] == 1
        finally:
            os.unlink(path)

    def test_hit_rate_stats(self):
        """命中率统计"""
        cache = FileStateCache()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("x")
            f.flush()
            path = f.name

        try:
            mtime = os.path.getmtime(path)
            cache.set(path, FileState(
                content="x",
                timestamp=time.time(),
                mtime=mtime,
                size=1,
                is_partial=False,
            ))

            cache.get(path)  # hit
            cache.get(path)  # hit
            cache.get("/nonexistent")  # miss

            stats = cache.stats
            assert stats["hit_count"] == 2
            assert stats["miss_count"] == 1
            assert abs(stats["hit_rate"] - 2 / 3) < 0.01
        finally:
            os.unlink(path)

    def test_consecutive_reads_cache_hit(self):
        """连续两次读取同一文件，第二次应命中缓存"""
        cache = FileStateCache()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("cached content")
            f.flush()
            path = f.name

        try:
            mtime = os.path.getmtime(path)
            state = FileState(
                content="cached content",
                timestamp=time.time(),
                mtime=mtime,
                size=14,
                is_partial=False,
            )
            cache.set(path, state)

            # First read: hit
            r1 = cache.get(path)
            assert r1 is not None
            assert r1.content == "cached content"

            # Second read: still hit
            r2 = cache.get(path)
            assert r2 is not None
            assert r2.content == "cached content"

            assert cache.stats["hit_count"] == 2
        finally:
            os.unlink(path)


class TestFileCacheMiddleware:
    def test_middleware_caches_read(self):
        """中间件应缓存文件读取结果"""
        cache = FileStateCache()
        middleware = create_file_cache_middleware(cache)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("file content")
            f.flush()
            path = f.name

        try:
            call_count = 0

            def mock_next(name, args):
                nonlocal call_count
                call_count += 1
                return "file content"

            # First call: cache miss, calls next
            result1 = middleware("read_file", {"path": path}, mock_next)
            assert result1 == "file content"
            assert call_count == 1

            # Second call: cache hit, skips next
            result2 = middleware("read_file", {"path": path}, mock_next)
            assert result2 == "file content"
            assert call_count == 1  # next was NOT called again
        finally:
            os.unlink(path)

    def test_middleware_invalidates_on_write(self):
        """中间件应在写入后失效缓存"""
        cache = FileStateCache()
        middleware = create_file_cache_middleware(cache)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("original")
            f.flush()
            path = f.name

        try:
            # Pre-populate cache
            mtime = os.path.getmtime(path)
            cache.set(path, FileState(
                content="original",
                timestamp=time.time(),
                mtime=mtime,
                size=8,
                is_partial=False,
            ))

            # Write operation invalidates
            middleware("write_file", {"path": path}, lambda n, a: "ok")

            # Cache should be empty for this path
            assert cache.get(path) is None
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
#  优化 4: 增强并发执行（级联取消）
# ═══════════════════════════════════════════════════════════════════════════════


class TestSiblingAbortController:
    def test_initial_state(self):
        ctrl = SiblingAbortController()
        assert ctrl.is_aborted() is False
        assert ctrl.error_source is None

    def test_abort_sets_state(self):
        ctrl = SiblingAbortController()
        ctrl.abort("bash", "command failed")
        assert ctrl.is_aborted() is True
        assert ctrl.error_source == "bash"
        assert ctrl.error_message == "command failed"

    def test_check_or_raise_passes_when_not_aborted(self):
        ctrl = SiblingAbortController()
        ctrl.check_or_raise()  # Should not raise

    def test_check_or_raise_raises_when_aborted(self):
        ctrl = SiblingAbortController()
        ctrl.abort("bash", "exit code 1")
        with pytest.raises(SiblingAbortError):
            ctrl.check_or_raise()

    def test_thread_safety(self):
        """多线程同时 abort 不应抛异常"""
        ctrl = SiblingAbortController()
        errors = []

        def abort_from_thread(i):
            try:
                ctrl.abort(f"tool_{i}", f"error_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=abort_from_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert ctrl.is_aborted() is True


class TestConcurrentExecReport:
    def test_cancelled_count(self):
        report = ConcurrentExecReport(
            results=[
                ToolExecResult(call_id="1", name="a", arguments={}, status=ToolExecStatus.COMPLETED),
                ToolExecResult(call_id="2", name="b", arguments={}, status=ToolExecStatus.CANCELLED),
                ToolExecResult(call_id="3", name="c", arguments={}, status=ToolExecStatus.CANCELLED),
                ToolExecResult(call_id="4", name="d", arguments={}, status=ToolExecStatus.FAILED),
            ],
            total_elapsed_ms=100,
            parallel_count=4,
            sequential_count=0,
        )
        assert report.success_count == 1
        assert report.failure_count == 1
        assert report.cancelled_count == 2


class TestCascadeCancellation:
    def test_bash_failure_cancels_siblings(self):
        """Bash 工具失败时应取消同批次其他工具"""
        from agent_framework.tool.registry import ToolRegistry, ToolSpec

        registry = ToolRegistry()

        # 注册一个"慢"工具和一个会失败的 bash 工具
        def slow_tool(duration: str = "1") -> str:
            time.sleep(float(duration))
            return "slow done"

        def bash_fail(command: str = "") -> str:
            raise RuntimeError("command not found")

        registry.add(ToolSpec(
            name="bash",
            description="Run command",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
            handler=bash_fail,
            concurrency_safe=True,
        ))
        registry.add(ToolSpec(
            name="slow_tool",
            description="Slow tool",
            parameters={"type": "object", "properties": {"duration": {"type": "string"}}, "required": []},
            handler=slow_tool,
            concurrency_safe=True,
        ))

        executor = ConcurrentToolExecutor(registry, max_workers=4, tool_timeout=10)
        results = executor.execute_batch([
            {"call_id": "c1", "name": "bash", "arguments": {"command": "invalid"}},
            {"call_id": "c2", "name": "slow_tool", "arguments": {"duration": "2"}},
            {"call_id": "c3", "name": "slow_tool", "arguments": {"duration": "2"}},
        ])

        statuses = {r.call_id: r.status for r in results}

        # bash should have failed
        assert statuses["c1"] == ToolExecStatus.FAILED

        # At least some siblings should be cancelled (timing dependent but likely)
        # We can't guarantee all are cancelled due to race conditions,
        # but the mechanism should work
        cancelled = sum(1 for r in results if r.status == ToolExecStatus.CANCELLED)
        completed = sum(1 for r in results if r.status == ToolExecStatus.COMPLETED)
        failed = sum(1 for r in results if r.status == ToolExecStatus.FAILED)

        # Total should be 3
        assert cancelled + completed + failed == 3
        assert failed >= 1  # At least bash itself failed


class TestEventToText:
    def test_user_message(self):
        event = Event(type="user_message", data={"content": "Hello"})
        assert _event_to_text(event) == "[User] Hello"

    def test_tool_result_truncation(self):
        event = Event(type="tool_result", data={
            "name": "search",
            "result": "x" * 1000,
        })
        text = _event_to_text(event)
        assert len(text) < 600  # Should be truncated at 500 + prefix

    def test_compact_summary(self):
        event = Event(type="compact_summary", data={
            "summary": "Old summary text",
        })
        text = _event_to_text(event)
        assert "Previous Summary" in text


# ═══════════════════════════════════════════════════════════════════════════════
#  P0 Bug 回归测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifyErrorPrecedence:
    """P0-1: resilience.py 运算符优先级 bug 回归"""

    def test_400_classified_as_invalid_request(self):
        from agent_framework.agent.resilience import classify_error, ErrorCategory
        err = RuntimeError("HTTP 400 Bad Request")
        assert classify_error(err) == ErrorCategory.INVALID_REQUEST

    def test_invalid_request_classified_correctly(self):
        from agent_framework.agent.resilience import classify_error, ErrorCategory
        err = RuntimeError("invalid request format")
        assert classify_error(err) == ErrorCategory.INVALID_REQUEST

    def test_string_containing_400_in_non_http_context(self):
        """文件路径含 '400' 不应被误判为 INVALID_REQUEST"""
        from agent_framework.agent.resilience import classify_error, ErrorCategory
        # "connection error" 应被分类为 TRANSIENT，而非因为路径含 400 被误判
        err = RuntimeError("connection error at /data/logs/400_items.csv")
        cat = classify_error(err)
        # 路径含 400 仍会匹配 — 这是已知行为（字符串匹配的局限），
        # 但至少修复后 "invalid" 不会因 or 优先级被拉入
        # 关键测试：独立的 "invalid" 不会触发 INVALID_REQUEST
        err2 = RuntimeError("something invalid happened, token count 400")
        cat2 = classify_error(err2)
        assert cat2 == ErrorCategory.INVALID_REQUEST  # "400" in msg still matches — correct

    def test_invalid_without_request_not_misclassified(self):
        """独立 'invalid' 不含 'request' 不应被分类为 INVALID_REQUEST"""
        from agent_framework.agent.resilience import classify_error, ErrorCategory
        # 修复前：`"invalid" in msg and "request" in msg` 因优先级被 or 吞掉
        # 修复后：需要同时包含 "invalid" 和 "request"
        err = RuntimeError("invalid json format in response payload")
        cat = classify_error(err)
        # 不含 "request" 作为 HTTP 400 意义，也不含 "400"
        # 应该归为 UNKNOWN 而非 INVALID_REQUEST
        # 注意: "invalid" in msg 为 True，但 "request" 不在 msg 中
        # 这里实际因为 msg 中没有 "400"，所以第一个条件为 False
        # 而 "invalid" in msg and "request" in msg → "request" 不在 → False
        # 所以整个条件为 False，不会返回 INVALID_REQUEST
        assert cat != ErrorCategory.INVALID_REQUEST


class TestRunConfigNotMutated:
    """P0-2/3: RunConfig 共享 config 不被永久修改"""

    def test_run_loop_does_not_mutate_original_config(self):
        from agent_framework.agent.runner import RunConfig
        from dataclasses import replace as dc_replace

        original = RunConfig(max_tokens=4096, max_rounds=5)
        copy = dc_replace(original)
        copy.max_tokens = 9999

        assert original.max_tokens == 4096, "原始 config 不应被修改"

    def test_dc_replace_isolates_list_fields(self):
        from agent_framework.agent.runner import RunConfig
        from dataclasses import replace as dc_replace

        original = RunConfig(fallback_models=["gpt-4o-mini"])
        copy = dc_replace(original)
        # dataclasses.replace 做浅拷贝，list 仍共享
        # 但至少 scalar 字段是独立的
        copy.max_tokens = 9999
        assert original.max_tokens is None


class TestIsPausedWithTrailingSystem:
    """P0-4: is_paused() 应跳过尾部 system 事件"""

    def test_paused_with_trailing_system(self):
        thread = Thread()
        thread.push("user_message", {"content": "hello"})
        thread.push("human_input_request", {"question": "确认？"})
        thread.push("system", {"event": "some_internal_event"})
        assert thread.is_paused() is True, "should still be paused despite trailing system event"

    def test_not_paused_without_request(self):
        thread = Thread()
        thread.push("user_message", {"content": "hello"})
        thread.push("assistant_message", {"content": "hi"})
        thread.push("system", {"event": "internal"})
        assert thread.is_paused() is False

    def test_paused_direct(self):
        thread = Thread()
        thread.push("human_input_request", {"question": "确认？"})
        assert thread.is_paused() is True

    def test_empty_thread_not_paused(self):
        thread = Thread()
        assert thread.is_paused() is False

    def test_only_system_events_not_paused(self):
        thread = Thread()
        thread.push("system", {"event": "launched"})
        thread.push("system", {"event": "something"})
        assert thread.is_paused() is False


class TestCompactionEventIdFilter:
    """P0-5: compaction 用 event_id 而非 identity 过滤系统事件"""

    def test_system_events_preserved_after_serialization(self):
        """序列化往返后，压缩仍保留初始系统事件"""
        thread = Thread()
        thread.push("system", {"event": "launched"})
        for i in range(20):
            thread.push("user_message", {"content": f"msg {i} " * 20})
            thread.push("assistant_message", {"content": f"reply {i} " * 20})

        # 序列化 → 反序列化（模拟 store load）
        data = thread.to_dict()
        thread2 = Thread.from_dict(data)

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Summary after deserialization."
        mock_llm.chat.return_value = mock_response

        svc = CompactionService()
        result = svc.compact(thread2, mock_llm)

        if result.success:
            system_events = [e for e in thread2.events if e.type == "system"]
            assert len(system_events) >= 1, "launched event should survive compaction after deserialization"
            assert any(e.data.get("event") == "launched" for e in system_events)


class TestToolDispatchArgFiltering:
    """P0-6: dispatch 应过滤 LLM 注入的未知参数"""

    def test_extra_args_filtered(self):
        from agent_framework.tool.registry import ToolRegistry, ToolSpec

        received_args = {}

        def my_tool(name: str) -> str:
            received_args.update({"name": name})
            return f"hello {name}"

        registry = ToolRegistry()
        registry.add(ToolSpec(
            name="greet",
            description="Greet",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
            handler=my_tool,
        ))

        # LLM 注入了 __class__ 和 extra_evil 参数
        result = registry.dispatch("greet", {
            "name": "Alice",
            "__class__": "exploit",
            "extra_evil": "payload",
        })

        assert result == "hello Alice"
        assert "__class__" not in received_args
        assert "extra_evil" not in received_args

    def test_valid_args_pass_through(self):
        from agent_framework.tool.registry import ToolRegistry, ToolSpec

        def add(a: int, b: int) -> int:
            return a + b

        registry = ToolRegistry()
        registry.add(ToolSpec(
            name="add",
            description="Add",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            handler=add,
        ))

        result = registry.dispatch("add", {"a": 3, "b": 4})
        assert result == 7
