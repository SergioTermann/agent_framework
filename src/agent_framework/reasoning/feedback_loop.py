"""
统一反馈闭环
============

把线上对话沉淀成可供后续 SFT / 偏好优化使用的数据。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional


class FeedbackLoop:
    def __init__(self, root_dir: str = "data/feedback"):
        self.root_dir = root_dir
        self._lock = threading.Lock()
        os.makedirs(self.root_dir, exist_ok=True)

        self.interactions_file = os.path.join(self.root_dir, "unified_interactions.jsonl")
        self.sft_file = os.path.join(self.root_dir, "sft_candidates.jsonl")
        self.feedback_file = os.path.join(self.root_dir, "conversation_feedback.jsonl")

    def capture_interaction(
        self,
        *,
        conversation_id: str,
        user_id: Optional[str],
        user_input: str,
        assistant_reply: str,
        route: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "conversation_id": conversation_id,
            "user_id": user_id,
            "user_input": user_input,
            "assistant_reply": assistant_reply,
            "route": route,
            "context": context,
        }
        self._append_jsonl(self.interactions_file, payload)

        if user_input.strip() and assistant_reply.strip():
            self._append_jsonl(
                self.sft_file,
                {
                    "messages": [
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": assistant_reply},
                    ],
                    "metadata": {
                        "timestamp": payload["timestamp"],
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "route_mode": route.get("mode"),
                        "model": route.get("model"),
                    },
                },
            )

    def capture_feedback(
        self,
        *,
        conversation_id: str,
        rating: int,
        feedback: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "conversation_id": conversation_id,
            "rating": rating,
            "feedback": feedback,
            "metadata": metadata or {},
        }
        self._append_jsonl(self.feedback_file, payload)

    def _append_jsonl(self, path: str, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
