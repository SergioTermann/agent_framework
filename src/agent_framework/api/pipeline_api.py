"""
SFT -> RLHF unified pipeline API.

Stages:
1. SFT fine-tune
2. Start / register model serving
3. Preference collection
4. Reward model training
5. DPO fine-tune
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Dict, List, Optional

from flask import Blueprint, jsonify, request

from agent_framework.reasoning.model_serving import get_model_serving_manager

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/api/pipeline")

PIPELINES_FILE = os.path.join("data", "pipelines.json")

STAGES = [
    {"key": "sft", "name": "SFT", "description": "Supervised fine-tuning"},
    {"key": "serving", "name": "Serving", "description": "Start vLLM / Xinference or register external endpoints"},
    {"key": "preference", "name": "Preference", "description": "Collect A/B preference data"},
    {"key": "reward", "name": "Reward", "description": "Train a Bradley-Terry reward model"},
    {"key": "dpo", "name": "DPO", "description": "Export DPO data and fine-tune again"},
]


def _load_pipelines() -> List[Dict]:
    os.makedirs("data", exist_ok=True)
    if os.path.exists(PIPELINES_FILE):
        try:
            with open(PIPELINES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _save_pipelines(pipelines: List[Dict]):
    with open(PIPELINES_FILE, "w", encoding="utf-8") as f:
        json.dump(pipelines, f, ensure_ascii=False, indent=2)


def _get_pipeline(pipeline_id: str) -> Optional[Dict]:
    for pipeline in _load_pipelines():
        if pipeline["id"] == pipeline_id:
            return pipeline
    return None


def _update_pipeline(pipeline: Dict):
    pipelines = _load_pipelines()
    for idx, item in enumerate(pipelines):
        if item["id"] == pipeline["id"]:
            pipelines[idx] = pipeline
            _save_pipelines(pipelines)
            return
    pipelines.append(pipeline)
    _save_pipelines(pipelines)


def _ok(data=None, **kwargs):
    return jsonify({"success": True, "data": data, **kwargs})


def _err(msg: str, code: int = 400):
    return jsonify({"success": False, "error": msg}), code


def _normalize_model_key(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").rstrip("/").lower()


def _endpoint_matches_model(endpoint, model_value: str) -> bool:
    lookup = _normalize_model_key(model_value)
    if not lookup:
        return False

    candidates = {
        _normalize_model_key(getattr(endpoint, "model_name", "")),
        _normalize_model_key(getattr(endpoint, "model_path", "")),
        _normalize_model_key(os.path.basename(str(getattr(endpoint, "model_path", "") or "").rstrip("/\\"))),
    }
    if lookup in candidates:
        return True

    model_name = _normalize_model_key(getattr(endpoint, "model_name", ""))
    model_path = _normalize_model_key(getattr(endpoint, "model_path", ""))
    return bool(model_name and model_name.endswith(lookup)) or bool(model_path and model_path.endswith(lookup))


def _find_existing_endpoint(mgr, *, endpoint_type: str, model_value: str):
    for endpoint in mgr.list_endpoints(endpoint_type=endpoint_type):
        if _endpoint_matches_model(endpoint, model_value):
            return endpoint
    return None


def _wait_for_endpoint(mgr, endpoint_id: str, timeout_seconds: int = 120):
    deadline = time.time() + max(1, int(timeout_seconds or 0))
    latest = None
    while time.time() < deadline:
        latest = mgr.get_endpoint(endpoint_id)
        if latest is None:
            break
        if latest.status == "running":
            return latest
        if latest.status == "error":
            return latest
        time.sleep(1)
    return latest or mgr.get_endpoint(endpoint_id)


@pipeline_bp.route("/create", methods=["POST"])
def create_pipeline():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip() or f"Pipeline-{time.strftime('%m%d-%H%M')}"

    pipeline = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "current_stage": 0,
        "stages": {stage["key"]: {"status": "pending", "data": {}} for stage in STAGES},
        "config": {
            "base_model": body.get("base_model", ""),
            "sft_task_id": body.get("sft_task_id", ""),
            "model_path": body.get("model_path", ""),
            "endpoint_id": "",
        },
        "created_at": time.time(),
        "updated_at": time.time(),
    }

    pipelines = _load_pipelines()
    pipelines.append(pipeline)
    _save_pipelines(pipelines)
    return _ok(pipeline)


@pipeline_bp.route("/list", methods=["GET"])
def list_pipelines():
    return _ok(_load_pipelines(), stages=STAGES)


@pipeline_bp.route("/<pipeline_id>", methods=["GET"])
def get_pipeline(pipeline_id):
    pipeline = _get_pipeline(pipeline_id)
    if not pipeline:
        return _err("Pipeline not found", 404)
    return _ok(pipeline, stages=STAGES)


@pipeline_bp.route("/<pipeline_id>", methods=["DELETE"])
def delete_pipeline(pipeline_id):
    pipelines = [p for p in _load_pipelines() if p["id"] != pipeline_id]
    _save_pipelines(pipelines)
    return _ok({"deleted": pipeline_id})


@pipeline_bp.route("/<pipeline_id>/advance", methods=["POST"])
def advance_pipeline(pipeline_id):
    pipeline = _get_pipeline(pipeline_id)
    if not pipeline:
        return _err("Pipeline not found", 404)

    body = request.get_json(silent=True) or {}
    current_stage = pipeline["current_stage"]
    stage_key = STAGES[current_stage]["key"]

    pipeline["stages"][stage_key]["status"] = "completed"
    pipeline["stages"][stage_key]["data"].update(body.get("stage_data", {}))

    if current_stage < len(STAGES) - 1:
        pipeline["current_stage"] = current_stage + 1
        next_key = STAGES[current_stage + 1]["key"]
        pipeline["stages"][next_key]["status"] = "active"

    pipeline["updated_at"] = time.time()
    _update_pipeline(pipeline)
    return _ok(pipeline)


@pipeline_bp.route("/<pipeline_id>/stage/<stage_key>/update", methods=["POST"])
def update_stage(pipeline_id, stage_key):
    pipeline = _get_pipeline(pipeline_id)
    if not pipeline:
        return _err("Pipeline not found", 404)
    if stage_key not in pipeline["stages"]:
        return _err(f"Unknown stage: {stage_key}", 400)

    body = request.get_json(silent=True) or {}
    if "status" in body:
        pipeline["stages"][stage_key]["status"] = body["status"]
    if "data" in body:
        pipeline["stages"][stage_key]["data"].update(body["data"])

    pipeline["updated_at"] = time.time()
    _update_pipeline(pipeline)
    return _ok(pipeline)


@pipeline_bp.route("/endpoints/list", methods=["GET"])
def list_endpoints():
    mgr = get_model_serving_manager()
    endpoint_type = (request.args.get("endpoint_type", "") or "").strip().lower()
    status = (request.args.get("status", "") or "").strip().lower()
    endpoints = mgr.list_endpoints(endpoint_type=endpoint_type, status=status)
    return _ok([endpoint.__dict__ for endpoint in endpoints])


@pipeline_bp.route("/endpoints/start", methods=["POST"])
def start_endpoint():
    body = request.get_json(silent=True) or {}
    backend = (body.get("backend", "vllm") or "vllm").strip().lower()
    endpoint_type = (body.get("endpoint_type", "chat") or "chat").strip().lower()
    port = int(body.get("port", 0) or 0)
    finetune_task_id = body.get("finetune_task_id", "")
    model_name = (body.get("model_name", "") or "").strip()
    model_uid = (body.get("model_uid", "") or "").strip()
    host = (body.get("host", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
    tensor_parallel_size = int(body.get("tensor_parallel_size", 1) or 1)
    gpu_memory_utilization = float(body.get("gpu_memory_utilization", 0.9) or 0.9)
    max_model_len = int(body.get("max_model_len", 0) or 0)
    dtype = body.get("dtype", "auto")
    api_key = body.get("api_key", "")

    mgr = get_model_serving_manager()
    try:
        if backend == "vllm":
            model_path = (body.get("model_path", "") or "").strip()
            if not model_path:
                return _err("model_path is required for backend=vllm")
            endpoint = mgr.start_serving(
                model_path=model_path,
                port=port,
                finetune_task_id=finetune_task_id,
                model_name=model_name,
                host=host,
                tensor_parallel_size=tensor_parallel_size,
                gpu_memory_utilization=gpu_memory_utilization,
                max_model_len=max_model_len,
                dtype=dtype,
                api_key=api_key,
                endpoint_type=endpoint_type,
            )
        elif backend == "xinference":
            base_url = (body.get("base_url", "") or "").strip()
            if base_url:
                if not model_name:
                    return _err("model_name is required when registering an existing Xinference endpoint")
                endpoint = mgr.register_xinference(
                    base_url=base_url,
                    model_name=model_name,
                    model_uid=model_uid,
                    finetune_task_id=finetune_task_id,
                    api_key=api_key,
                    endpoint_type=endpoint_type,
                )
            else:
                endpoint = mgr.start_xinference(
                    host=host,
                    port=port,
                    model_name=model_name,
                    model_uid=model_uid,
                    finetune_task_id=finetune_task_id,
                    api_key=api_key,
                    endpoint_type=endpoint_type,
                )
        else:
            return _err(f"unsupported backend: {backend}")
        return _ok(endpoint.__dict__)
    except Exception as exc:
        return _err(str(exc), 500)


@pipeline_bp.route("/endpoints/stop", methods=["POST"])
def stop_endpoint():
    body = request.get_json(silent=True) or {}
    endpoint_id = body.get("endpoint_id", "")
    if not endpoint_id:
        return _err("endpoint_id is required")
    mgr = get_model_serving_manager()
    return _ok({"stopped": mgr.stop_serving(endpoint_id)})


@pipeline_bp.route("/endpoints/ensure", methods=["POST"])
def ensure_endpoint():
    body = request.get_json(silent=True) or {}
    backend = (body.get("backend", "vllm") or "vllm").strip().lower()
    endpoint_type = (body.get("endpoint_type", "chat") or "chat").strip().lower()
    model_value = (body.get("model") or body.get("model_path") or "").strip()
    if not model_value:
        return _err("model is required")
    if endpoint_type == "rerank":
        backend = "rerank"
    if backend not in {"vllm", "rerank"}:
        return _err("Only backend=vllm/rerank is supported by ensure right now")
    if endpoint_type not in {"chat", "embedding", "rerank"}:
        return _err("Auto start currently supports only chat, embedding, and rerank endpoints")

    mgr = get_model_serving_manager()
    existing = _find_existing_endpoint(mgr, endpoint_type=endpoint_type, model_value=model_value)
    created = False
    requested_model_name = (body.get("model_name", "") or "").strip()

    try:
        if existing and existing.status == "running":
            return _ok(existing.__dict__, created=False, reused=True)

        if existing and existing.status == "starting":
            endpoint = existing
        else:
            endpoint = mgr.start_serving(
                model_path=model_value,
                model_name=requested_model_name,
                port=int(body.get("port", 0) or 0),
                finetune_task_id=body.get("finetune_task_id", ""),
                host=(body.get("host", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1",
                tensor_parallel_size=int(body.get("tensor_parallel_size", 1) or 1),
                gpu_memory_utilization=float(body.get("gpu_memory_utilization", 0.9) or 0.9),
                max_model_len=int(body.get("max_model_len", 0) or 0),
                dtype=body.get("dtype", "auto"),
                api_key=body.get("api_key", ""),
                endpoint_type=endpoint_type,
            )
            created = True

        waited = _wait_for_endpoint(mgr, endpoint.endpoint_id, int(body.get("wait_seconds", 120) or 120))
        if waited is None:
            return _err("Endpoint disappeared during startup", 500)
        if waited.status != "running":
            detail = waited.error_msg or f"Endpoint status is {waited.status}"
            return _err(detail, 500)
        return _ok(waited.__dict__, created=created, reused=not created)
    except Exception as exc:
        return _err(str(exc), 500)


@pipeline_bp.route("/endpoints/register", methods=["POST"])
def register_endpoint():
    body = request.get_json(silent=True) or {}
    base_url = (body.get("base_url", "") or "").strip()
    model_name = (body.get("model_name", "") or "").strip()
    if not base_url or not model_name:
        return _err("base_url and model_name are required")

    backend = (body.get("backend", "manual") or "manual").strip().lower()
    endpoint_type = (body.get("endpoint_type", "chat") or "chat").strip().lower()
    mgr = get_model_serving_manager()

    try:
        if backend == "xinference":
            endpoint = mgr.register_xinference(
                base_url=base_url,
                model_name=model_name,
                model_uid=body.get("model_uid", ""),
                finetune_task_id=body.get("finetune_task_id", ""),
                api_key=body.get("api_key", ""),
                endpoint_type=endpoint_type,
            )
        else:
            endpoint = mgr.register_manual(
                base_url=base_url,
                model_name=model_name,
                finetune_task_id=body.get("finetune_task_id", ""),
                api_key=body.get("api_key", ""),
                backend=backend,
                model_uid=body.get("model_uid", ""),
                endpoint_type=endpoint_type,
            )
        return _ok(endpoint.__dict__)
    except Exception as exc:
        return _err(str(exc), 500)


@pipeline_bp.route("/endpoints/models/discover", methods=["POST"])
def discover_models():
    body = request.get_json(silent=True) or {}
    base_url = (body.get("base_url", "") or "").strip()
    api_key = body.get("api_key", "")
    if not base_url:
        return _err("base_url is required")

    mgr = get_model_serving_manager()
    try:
        models = mgr.discover_models(base_url=base_url, api_key=api_key)
        return _ok(models, count=len(models))
    except Exception as exc:
        return _err(str(exc), 500)


@pipeline_bp.route("/endpoints/<endpoint_id>/models", methods=["GET"])
def endpoint_models(endpoint_id):
    mgr = get_model_serving_manager()
    try:
        models = mgr.discover_models(endpoint_id=endpoint_id)
        return _ok(models, count=len(models), endpoint_id=endpoint_id)
    except KeyError:
        return _err("Endpoint not found", 404)
    except Exception as exc:
        return _err(str(exc), 500)


@pipeline_bp.route("/endpoints/<endpoint_id>/health", methods=["GET"])
def check_health(endpoint_id):
    mgr = get_model_serving_manager()
    return _ok({"healthy": mgr.health_check(endpoint_id), "endpoint_id": endpoint_id})


@pipeline_bp.route("/endpoints/<endpoint_id>", methods=["DELETE"])
def remove_endpoint(endpoint_id):
    mgr = get_model_serving_manager()
    return _ok({"removed": mgr.remove_endpoint(endpoint_id)})
