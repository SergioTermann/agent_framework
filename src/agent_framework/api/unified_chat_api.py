"""
统一聊天 API
============
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from agent_framework.api.auth_api import require_auth, resolve_user_scope
from agent_framework.gateway.control_plane import publish_event_to_control_plane, use_go_control_plane
from agent_framework.gateway.models import PushEvent
from agent_framework.gateway.service import get_gateway_service
from agent_framework.web.unified_orchestrator import get_unified_orchestrator


unified_bp = Blueprint("unified", __name__)


@unified_bp.route("/chat", methods=["POST"])
@require_auth
def unified_chat():
    try:
        body = request.get_json(silent=True) or {}
        user_input = (body.get("message") or body.get("input") or "").strip()
        if not user_input:
            return jsonify({"success": False, "error": "message is required"}), 400

        user_id = resolve_user_scope(body.get("user_id"))
        metadata = body.get("metadata") or {}
        metadata.setdefault("user_id", user_id)

        orchestrator = get_unified_orchestrator()
        result = orchestrator.chat(
            user_input=user_input,
            conversation_id=body.get("conversation_id"),
            user_id=user_id,
            title=body.get("title"),
            metadata=metadata,
            mode=body.get("mode", "auto"),
            use_agent=body.get("use_agent"),
            knowledge_base_ids=body.get("knowledge_base_ids"),
            prefer_finetuned=bool(body.get("prefer_finetuned", False)),
            endpoint_id=body.get("endpoint_id", ""),
            model_name=body.get("model_name", ""),
            base_url=body.get("base_url", ""),
            api_key=body.get("api_key"),
        )

        delivery = body.get("delivery") or {}
        if delivery.get("enabled"):
            target_user_id = (
                delivery.get("user_id")
                or body.get("push_user_id")
                or user_id
            )
            target_user_id = resolve_user_scope(target_user_id)
            push_event = PushEvent(
                user_id=target_user_id,
                event_type=delivery.get("event", "chat.message"),
                target=delivery.get("target", "ALL"),
                device_id=delivery.get("device_id"),
                exclude_device_id=delivery.get("exclude_device_id"),
                connection_id=delivery.get("connection_id"),
                conversation_id=result.get("conversation_id"),
                message_id=result.get("assistant_message_id"),
                payload=dict(result),
                metadata=delivery.get("metadata") or {"source": "api.unified.chat"},
            )
            if use_go_control_plane():
                push_result = get_gateway_service().deliver_live_event(push_event)
                try:
                    control_plane_result = publish_event_to_control_plane(push_event)
                    push_result["control_plane"] = {
                        "synced": True,
                        "event_id": control_plane_result.get("event_id"),
                        "delivered_count": control_plane_result.get("delivered_count"),
                        "offline_queued": control_plane_result.get("offline_queued"),
                    }
                except Exception as exc:
                    push_result["control_plane"] = {
                        "synced": False,
                        "error": str(exc),
                    }
            else:
                push_result = get_gateway_service().publish_event(push_event)
            result["delivery"] = push_result
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@unified_bp.route("/feedback", methods=["POST"])
@require_auth
def unified_feedback():
    try:
        body = request.get_json(silent=True) or {}
        conversation_id = (body.get("conversation_id") or "").strip()
        rating = int(body.get("rating", 0) or 0)

        if not conversation_id:
            return jsonify({"success": False, "error": "conversation_id is required"}), 400
        if rating <= 0:
            return jsonify({"success": False, "error": "rating is required"}), 400

        orchestrator = get_unified_orchestrator()
        result = orchestrator.submit_feedback(
            conversation_id=conversation_id,
            rating=rating,
            feedback=body.get("feedback", ""),
            metadata=body.get("metadata"),
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
