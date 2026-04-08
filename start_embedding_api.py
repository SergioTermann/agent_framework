from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


def ensure_dotenv_loaded() -> None:
    if load_dotenv is not None:
        load_dotenv()


class EmbeddingRuntime:
    def __init__(self, *, model_name: str, device: str = "cpu", max_length: int = 512):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
        self.model.to(device)
        self.model.eval()

    def embed(self, inputs: list[str]) -> tuple[list[list[float]], int]:
        encoded = self.tokenizer(
            inputs,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with self._torch.no_grad():
            outputs = self.model(**encoded)
            hidden = outputs.last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            normalized = self._torch.nn.functional.normalize(pooled, p=2, dim=1)
        token_count = int(encoded["attention_mask"].sum().item())
        return normalized.cpu().tolist(), token_count


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


class EmbeddingHandler(BaseHTTPRequestHandler):
    runtime: EmbeddingRuntime

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/v1/health"}:
            json_response(self, 200, {"status": "ok", "model": self.runtime.model_name})
            return
        if self.path in {"/models", "/v1/models"}:
            json_response(
                self,
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.runtime.model_name,
                            "object": "model",
                            "owned_by": "local",
                        }
                    ],
                },
            )
            return
        json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/embeddings", "/v1/embeddings"}:
            json_response(self, 404, {"error": "not_found"})
            return
        try:
            payload = read_json(self)
            raw_input = payload.get("input", [])
            if isinstance(raw_input, str):
                inputs = [raw_input]
            elif isinstance(raw_input, list):
                inputs = [str(item) for item in raw_input]
            else:
                raise ValueError("input must be a string or list of strings")
            embeddings, token_count = self.runtime.embed(inputs)
            json_response(
                self,
                200,
                {
                    "object": "list",
                    "model": str(payload.get("model") or self.runtime.model_name),
                    "data": [
                        {
                            "object": "embedding",
                            "index": index,
                            "embedding": embedding,
                        }
                        for index, embedding in enumerate(embeddings)
                    ],
                    "usage": {
                        "prompt_tokens": token_count,
                        "total_tokens": token_count,
                    },
                },
            )
        except Exception as exc:  # pragma: no cover - runtime path
            json_response(self, 500, {"error": f"{type(exc).__name__}: {exc}"})


def main() -> int:
    ensure_dotenv_loaded()
    parser = argparse.ArgumentParser(description="Local OpenAI-compatible embedding API")
    parser.add_argument("--model", default=os.environ.get("EMBEDDING_MODEL", "Alibaba-NLP/gte-multilingual-base"))
    parser.add_argument("--host", default=os.environ.get("EMBEDDING_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("EMBEDDING_PORT", "8001")))
    parser.add_argument("--device", default=os.environ.get("EMBEDDING_DEVICE", "cpu"))
    parser.add_argument("--max-length", type=int, default=int(os.environ.get("EMBEDDING_MAX_LENGTH", "512")))
    args = parser.parse_args()

    runtime = EmbeddingRuntime(model_name=args.model, device=args.device, max_length=args.max_length)
    EmbeddingHandler.runtime = runtime
    server = ThreadingHTTPServer((args.host, args.port), EmbeddingHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
