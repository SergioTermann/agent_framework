from __future__ import annotations

import argparse
import asyncio
import json
import re
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


@dataclass
class RegistryState:
    path: Path
    targets: list[dict[str, str]] = field(default_factory=list)
    memory_index: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "RegistryState":
        if not path.exists():
            return cls(path=path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            path=path,
            targets=list(payload.get("targets") or []),
            memory_index=dict(payload.get("memory_index") or {}),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "targets": self.targets,
                    "memory_index": self.memory_index,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def remember_target(self, *, kind: str, target: str) -> None:
        record = {"kind": kind, "target": target}
        if record not in self.targets:
            self.targets.append(record)
            self.save()

    def remember_memory(self, memory_id: str, *, kind: str, target: str) -> None:
        self.memory_index[memory_id] = {"kind": kind, "target": target}
        self.remember_target(kind=kind, target=target)
        self.save()

    def forget_memory(self, memory_id: str) -> None:
        if memory_id in self.memory_index:
            del self.memory_index[memory_id]
            self.save()


class ReMeRuntime:
    def __init__(
        self,
        *,
        working_dir: str,
        llm_api_key: str | None,
        llm_base_url: str | None,
        embedding_api_key: str | None,
        embedding_base_url: str | None,
        embedding_dimensions: int | None,
    ):
        from reme import ReMe
        from reme.core.enumeration import MemoryType

        self._reme_cls = ReMe
        self._memory_type_cls = MemoryType
        self.working_dir = Path(working_dir)
        self.registry = RegistryState.load(self.working_dir / "registry.json")
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.embedding_api_key = embedding_api_key
        self.embedding_base_url = embedding_base_url
        self.embedding_dimensions = embedding_dimensions
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.reme = self._call(self._start())

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _call(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    async def _start(self):
        self.working_dir.mkdir(parents=True, exist_ok=True)
        reme = self._reme_cls(
            working_dir=str(self.working_dir),
            llm_api_key=self.llm_api_key,
            llm_base_url=self.llm_base_url,
            embedding_api_key=self.embedding_api_key,
            embedding_base_url=self.embedding_base_url,
            default_embedding_model_config={"dimensions": self.embedding_dimensions} if self.embedding_dimensions else None,
            enable_logo=False,
        )
        await reme.start()
        return reme

    async def _close(self) -> None:
        await self.reme.close()

    def close(self) -> None:
        self._call(self._close())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)

    def _memory_type(self, kind: str):
        mapping = {
            "user": self._memory_type_cls.PERSONAL,
            "task": self._memory_type_cls.PROCEDURAL,
            "tool": self._memory_type_cls.TOOL,
        }
        return mapping[kind]

    def _target_kwargs(self, kind: str, target: str) -> dict[str, str]:
        if kind == "task":
            return {"task_name": target}
        if kind == "tool":
            return {"tool_name": target}
        return {"user_name": target}

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return _TOKEN_RE.findall((text or "").lower())

    @staticmethod
    def _normalize_metadata_type(metadata: dict[str, Any]) -> dict[str, Any]:
        payload = dict(metadata or {})
        original = str(payload.get("agent_memory_type") or payload.get("memory_type") or "").strip().lower()
        mapping = {
            "semantic": "personal",
            "episodic": "history",
            "procedural": "procedural",
            "working": "summary",
            "tool": "tool",
            "personal": "personal",
            "history": "history",
            "summary": "summary",
        }
        normalized = mapping.get(original, "personal")
        if original:
            payload["agent_memory_type"] = original
        payload["memory_type"] = normalized
        return payload

    def _remember_target(self, *, kind: str, target: str) -> None:
        self.reme._add_meta_memory(self._memory_type(kind), target)  # type: ignore[attr-defined]
        self.registry.remember_target(kind=kind, target=target)

    @staticmethod
    def _dump_node(node: Any) -> dict[str, Any]:
        dumped = node.model_dump() if hasattr(node, "model_dump") else dict(node)
        dumped["memory_type"] = str(dumped.get("memory_type", ""))
        return dumped

    async def _add_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(payload["target_kind"])
        target = str(payload["target_name"])
        metadata = self._normalize_metadata_type(dict(payload.get("metadata") or {}))
        self._remember_target(kind=kind, target=target)
        node = await self.reme.add_memory(
            memory_content=str(payload["memory_content"]),
            when_to_use=str(payload.get("when_to_use") or ""),
            message_time=str(payload.get("message_time") or ""),
            ref_memory_id=str(payload.get("ref_memory_id") or ""),
            author=str(payload.get("author") or ""),
            score=float(payload.get("score") or 0.0),
            **self._target_kwargs(kind, target),
            **metadata,
        )
        dumped = self._dump_node(node)
        self.registry.remember_memory(dumped["memory_id"], kind=kind, target=target)
        return dumped

    def add_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(self._add_memory(payload))

    async def _get_memory(self, memory_id: str) -> dict[str, Any]:
        node = await self.reme.get_memory(memory_id)
        return self._dump_node(node)

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        return self._call(self._get_memory(memory_id))

    async def _update_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        memory_id = str(payload["memory_id"])
        target_info = self.registry.memory_index.get(memory_id) or {}
        kind = str(payload.get("target_kind") or target_info.get("kind") or "user")
        target = str(payload.get("target_name") or target_info.get("target") or "global")
        metadata = self._normalize_metadata_type(dict(payload.get("metadata") or {}))
        self._remember_target(kind=kind, target=target)
        node = await self.reme.update_memory(
            memory_id=memory_id,
            memory_content=payload.get("memory_content"),
            when_to_use=payload.get("when_to_use"),
            message_time=payload.get("message_time"),
            ref_memory_id=payload.get("ref_memory_id"),
            author=payload.get("author"),
            score=payload.get("score"),
            **self._target_kwargs(kind, target),
            **metadata,
        )
        dumped = self._dump_node(node)
        self.registry.remember_memory(memory_id, kind=kind, target=target)
        return dumped

    def update_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(self._update_memory(payload))

    async def _list_for_target(self, *, kind: str, target: str, limit: int | None) -> list[dict[str, Any]]:
        self._remember_target(kind=kind, target=target)
        nodes = await self.reme.list_memory(limit=limit, **self._target_kwargs(kind, target))
        return [self._dump_node(node) for node in nodes]

    def list_memories(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        limit = payload.get("limit")
        requested = payload.get("targets") or self.registry.targets
        all_nodes: list[dict[str, Any]] = []
        for target in requested:
            all_nodes.extend(
                self._call(
                    self._list_for_target(
                        kind=str(target["kind"]),
                        target=str(target["target"]),
                        limit=limit,
                    )
                )
            )
        if not all_nodes:
            all_nodes.extend(self._registry_list_memories(requested))
        deduped = {node["memory_id"]: node for node in all_nodes}
        result = list(deduped.values())
        result.sort(key=lambda item: item.get("time_modified", ""), reverse=True)
        if isinstance(limit, int) and limit > 0:
            result = result[:limit]
        return result

    def _registry_list_memories(self, requested: list[dict[str, Any]]) -> list[dict[str, Any]]:
        requested_pairs = {(str(item["kind"]), str(item["target"])) for item in (requested or [])}
        all_nodes: list[dict[str, Any]] = []
        for memory_id, target_info in list(self.registry.memory_index.items()):
            pair = (str(target_info.get("kind") or ""), str(target_info.get("target") or ""))
            if requested_pairs and pair not in requested_pairs:
                continue
            try:
                all_nodes.append(self.get_memory(memory_id))
            except Exception:
                continue
        return all_nodes

    def _fallback_search(self, *, query: str, requested: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        query_tokens = set(self._tokenize(query))
        ranked: list[tuple[float, dict[str, Any]]] = []
        for node in self._registry_list_memories(requested):
            content = str(node.get("content") or "")
            content_lower = content.lower()
            tokens = set(self._tokenize(content))
            overlap = len(query_tokens & tokens) / max(len(query_tokens), 1) if query_tokens else 0.0
            substring_bonus = 0.35 if query and query.lower() in content_lower else 0.0
            score = max(float(node.get("score") or 0.0), overlap + substring_bonus)
            ranked.append((score, {**node, "score": score}))
        ranked.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        for score, node in ranked[:limit]:
            if score > 0.0 or not query:
                results.append(node)
        return results

    async def _search_target(self, *, kind: str, target: str, query: str, limit: int) -> list[dict[str, Any]]:
        self._remember_target(kind=kind, target=target)
        handler = self.reme.get_memory_handler(target)
        nodes = await handler.search(query, limit=limit)
        return [self._dump_node(node) for node in nodes]

    def search_memories(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(payload.get("query") or "")
        limit = int(payload.get("limit") or 5)
        requested = payload.get("targets") or self.registry.targets
        all_nodes: list[dict[str, Any]] = []
        for target in requested:
            all_nodes.extend(
                self._call(
                    self._search_target(
                        kind=str(target["kind"]),
                        target=str(target["target"]),
                        query=query,
                        limit=limit,
                    )
                )
            )
        if not all_nodes:
            all_nodes.extend(self._fallback_search(query=query, requested=requested, limit=limit))
        deduped = {node["memory_id"]: node for node in all_nodes}
        result = list(deduped.values())
        result.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        return result[:limit]

    async def _delete_memory(self, memory_id: str) -> None:
        await self.reme.delete_memory(memory_id)

    def delete_memory(self, memory_id: str) -> None:
        self._call(self._delete_memory(memory_id))
        self.registry.forget_memory(memory_id)


class ReMeRequestHandler(BaseHTTPRequestHandler):
    runtime: ReMeRuntime

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            _json_response(self, 200, {"success": True, "status": "ok"})
            return
        _json_response(self, 404, {"success": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = _read_json(self)
            if self.path == "/memory/add":
                _json_response(self, 200, {"success": True, "memory": self.runtime.add_memory(payload)})
                return
            if self.path == "/memory/get":
                _json_response(self, 200, {"success": True, "memory": self.runtime.get_memory(str(payload["memory_id"]))})
                return
            if self.path == "/memory/update":
                _json_response(self, 200, {"success": True, "memory": self.runtime.update_memory(payload)})
                return
            if self.path == "/memory/list":
                _json_response(self, 200, {"success": True, "memories": self.runtime.list_memories(payload)})
                return
            if self.path == "/memory/search":
                _json_response(self, 200, {"success": True, "memories": self.runtime.search_memories(payload)})
                return
            if self.path == "/memory/delete":
                self.runtime.delete_memory(str(payload["memory_id"]))
                _json_response(self, 200, {"success": True})
                return
            _json_response(self, 404, {"success": False, "error": "not_found"})
        except Exception as exc:  # pragma: no cover - runtime path
            _json_response(self, 500, {"success": False, "error": f"{type(exc).__name__}: {exc}"})


def main() -> int:
    parser = argparse.ArgumentParser(description="ReMe memory sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--working-dir", default=".reme-sidecar")
    parser.add_argument("--llm-api-key", default="")
    parser.add_argument("--llm-base-url", default="")
    parser.add_argument("--embedding-api-key", default="")
    parser.add_argument("--embedding-base-url", default="")
    parser.add_argument("--embedding-dimensions", type=int, default=None)
    args = parser.parse_args()

    runtime = ReMeRuntime(
        working_dir=args.working_dir,
        llm_api_key=args.llm_api_key or None,
        llm_base_url=args.llm_base_url or None,
        embedding_api_key=args.embedding_api_key or None,
        embedding_base_url=args.embedding_base_url or None,
        embedding_dimensions=args.embedding_dimensions,
    )
    ReMeRequestHandler.runtime = runtime
    server = ThreadingHTTPServer((args.host, args.port), ReMeRequestHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
