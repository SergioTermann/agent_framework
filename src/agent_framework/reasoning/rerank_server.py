from __future__ import annotations

import argparse
from typing import Any, Dict, List

from flask import Flask, jsonify, request


def create_app(model_name_or_path: str, served_model_name: str, api_key: str = "") -> Flask:
    from sentence_transformers import CrossEncoder

    app = Flask(__name__)
    model = CrossEncoder(model_name_or_path)
    served_name = (served_model_name or model_name_or_path).strip() or model_name_or_path
    expected_api_key = (api_key or "").strip()

    def _authorized() -> bool:
        if not expected_api_key:
            return True
        header = request.headers.get("Authorization", "").strip()
        return header == f"Bearer {expected_api_key}"

    @app.before_request
    def _require_auth():
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401
        return None

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "model": served_name})

    @app.get("/v1/models")
    def list_models():
        return jsonify(
            {
                "object": "list",
                "data": [
                    {
                        "id": served_name,
                        "object": "model",
                        "owned_by": "local-rerank",
                        "task": "rerank",
                        "model_name": served_name,
                    }
                ],
            }
        )

    @app.post("/rerank")
    def rerank():
        payload: Dict[str, Any] = request.get_json(silent=True) or {}
        query = str(payload.get("query") or "").strip()
        documents = payload.get("documents") or []
        top_n = int(payload.get("top_n") or len(documents) or 0)
        return_documents = bool(payload.get("return_documents"))

        if not query:
            return jsonify({"error": "query is required"}), 400
        if not isinstance(documents, list) or not documents:
            return jsonify({"error": "documents must be a non-empty list"}), 400

        pairs = [[query, str(document or "")] for document in documents]
        scores = model.predict(pairs)

        results: List[Dict[str, Any]] = []
        for index, score in enumerate(scores):
            item: Dict[str, Any] = {
                "index": index,
                "relevance_score": float(score),
            }
            if return_documents:
                item["document"] = documents[index]
            results.append(item)

        results.sort(key=lambda item: float(item.get("relevance_score", 0.0)), reverse=True)
        if top_n > 0:
            results = results[:top_n]

        return jsonify(
            {
                "model": served_name,
                "results": results,
            }
        )

    return app


def main():
    parser = argparse.ArgumentParser(description="Local rerank service")
    parser.add_argument("--model", required=True)
    parser.add_argument("--served-model-name", default="")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8005)
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    app = create_app(args.model, args.served_model_name, args.api_key)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
