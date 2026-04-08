"""
LRU 文件状态缓存 —— 借鉴 Claude Code 的文件状态管理

核心能力：
  1. 读取缓存：文件读取命中缓存时直接返回（校验 mtime）
  2. 写入失效：文件写入后自动失效缓存
  3. LRU 淘汰：按条目数 + 总大小进行淘汰
  4. 压缩快照：为上下文压缩提供文件状态快照

设计参考：
  - Claude Code 的文件状态缓存机制
  - 基于 mtime 的缓存校验（避免读取过期内容）
"""

from __future__ import annotations

import logging
import os
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── FileState ────────────────────────────────────────────────────────────────

@dataclass
class FileState:
    """单个文件的缓存状态"""
    content: str
    timestamp: float        # time.time() 读取时间
    mtime: float           # 文件修改时间 (os.path.getmtime)
    size: int              # 文件大小（字节）
    is_partial: bool       # 是否部分读取


# ─── FileStateCache ──────────────────────────────────────────────────────────

class FileStateCache:
    """
    LRU 文件状态缓存。

    特性：
      - 基于 mtime 校验：如果文件已修改，缓存自动失效
      - 双重 LRU 淘汰：按条目数 + 总内存大小
      - 线程安全：所有操作加锁

    用法：
        cache = FileStateCache()
        state = cache.get("/path/to/file.py")
        if state is None:
            content = open("/path/to/file.py").read()
            cache.set("/path/to/file.py", FileState(
                content=content,
                timestamp=time.time(),
                mtime=os.path.getmtime("/path/to/file.py"),
                size=len(content.encode()),
                is_partial=False,
            ))
    """

    MAX_ENTRIES = 100
    MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

    def __init__(
        self,
        max_entries: int = MAX_ENTRIES,
        max_size_bytes: int = MAX_SIZE_BYTES,
    ):
        self._max_entries = max_entries
        self._max_size_bytes = max_size_bytes
        self._cache: OrderedDict[str, FileState] = OrderedDict()
        self._total_size = 0
        self._lock = threading.Lock()
        self._hit_count = 0
        self._miss_count = 0

    def get(self, path: str) -> FileState | None:
        """
        查缓存 + 校验 mtime。

        :param path: 文件绝对路径
        :returns: FileState 或 None（未命中或已过期）
        """
        normalized = self._normalize_path(path)

        with self._lock:
            state = self._cache.get(normalized)
            if state is None:
                self._miss_count += 1
                return None

            # 校验文件是否被修改
            try:
                current_mtime = os.path.getmtime(path)
                if current_mtime != state.mtime:
                    # 文件已修改，缓存失效
                    self._remove_entry(normalized)
                    self._miss_count += 1
                    return None
            except OSError:
                # 文件不存在或不可访问，移除缓存
                self._remove_entry(normalized)
                self._miss_count += 1
                return None

            # 命中：移到末尾（最近使用）
            self._cache.move_to_end(normalized)
            self._hit_count += 1
            return state

    def set(self, path: str, state: FileState) -> None:
        """
        写入缓存 + LRU 淘汰。

        :param path: 文件绝对路径
        :param state: 文件状态
        """
        normalized = self._normalize_path(path)

        with self._lock:
            # 如果已存在，先移除旧条目
            if normalized in self._cache:
                self._remove_entry(normalized)

            self._cache[normalized] = state
            self._total_size += state.size

            # LRU 淘汰
            self._evict_if_needed()

    def invalidate(self, path: str) -> None:
        """
        写操作后失效缓存。

        :param path: 文件绝对路径
        """
        normalized = self._normalize_path(path)

        with self._lock:
            if normalized in self._cache:
                self._remove_entry(normalized)
                logger.debug(f"缓存失效: {path}")

    def invalidate_all(self) -> None:
        """清空全部缓存"""
        with self._lock:
            self._cache.clear()
            self._total_size = 0

    def snapshot(self) -> dict[str, FileState]:
        """
        压缩前快照 —— 返回缓存的浅拷贝。

        :returns: {normalized_path: FileState} 字典
        """
        with self._lock:
            return dict(self._cache)

    def merge(self, other: dict[str, FileState]) -> None:
        """
        恢复时合并缓存（仅合并不存在的条目）。

        :param other: 来自 snapshot() 的缓存字典
        """
        with self._lock:
            for path, state in other.items():
                if path not in self._cache:
                    self._cache[path] = state
                    self._total_size += state.size
            self._evict_if_needed()

    @property
    def stats(self) -> dict[str, Any]:
        """缓存统计"""
        with self._lock:
            total = self._hit_count + self._miss_count
            return {
                "entries": len(self._cache),
                "total_size_bytes": self._total_size,
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_rate": self._hit_count / total if total > 0 else 0.0,
            }

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _normalize_path(self, path: str) -> str:
        """路径标准化"""
        return os.path.normpath(os.path.abspath(path))

    def _remove_entry(self, normalized: str) -> None:
        """移除条目（调用方需持有锁）"""
        state = self._cache.pop(normalized, None)
        if state:
            self._total_size -= state.size

    def _evict_if_needed(self) -> None:
        """LRU 淘汰（按大小 + 条目数，调用方需持有锁）"""
        while (
            len(self._cache) > self._max_entries
            or self._total_size > self._max_size_bytes
        ) and self._cache:
            # 淘汰最旧的条目（OrderedDict 头部）
            _, evicted = self._cache.popitem(last=False)
            self._total_size -= evicted.size


# ─── 缓存中间件 ──────────────────────────────────────────────────────────────

# 文件读取类工具名称
_READ_TOOLS = {"read_file", "cat_file", "view_file", "file_read"}
# 文件写入类工具名称
_WRITE_TOOLS = {"write_file", "edit_file", "create_file", "file_write", "append_file"}


def create_file_cache_middleware(cache: FileStateCache):
    """
    创建文件缓存中间件。

    - 文件读取工具命中缓存时直接返回
    - 文件写入工具执行后失效缓存

    :param cache: FileStateCache 实例
    :returns: ToolMiddleware 函数
    """
    def middleware(name: str, arguments: dict[str, Any], next_fn: Callable) -> Any:
        # 文件读取：尝试命中缓存
        if name in _READ_TOOLS:
            file_path = arguments.get("path") or arguments.get("file_path") or ""
            if file_path:
                cached = cache.get(file_path)
                if cached is not None:
                    logger.debug(f"文件缓存命中: {file_path}")
                    return cached.content

        # 执行工具
        result = next_fn(name, arguments)

        # 文件读取成功：写入缓存
        if name in _READ_TOOLS:
            file_path = arguments.get("path") or arguments.get("file_path") or ""
            if file_path and result is not None:
                try:
                    content = str(result)
                    mtime = os.path.getmtime(file_path)
                    cache.set(file_path, FileState(
                        content=content,
                        timestamp=time.time(),
                        mtime=mtime,
                        size=len(content.encode("utf-8", errors="replace")),
                        is_partial=False,
                    ))
                except OSError:
                    pass  # 文件不存在或不可访问

        # 文件写入：失效缓存
        if name in _WRITE_TOOLS:
            file_path = arguments.get("path") or arguments.get("file_path") or ""
            if file_path:
                cache.invalidate(file_path)

        return result

    return middleware
