"""
LLM RLHF REST API
=================
URL 前缀：/api/llm-rl
提供偏好收集、奖励模型、提示词优化、评估排名等接口。
"""

from flask import Blueprint, request, jsonify
from agent_framework.reasoning.llm_rlhf_engine import get_llm_rlhf_engine

llm_rlhf_bp = Blueprint("llm_rlhf", __name__, url_prefix="/api/llm-rl")


# ─── 工具 ─────────────────────────────────────────────────────────────────────

def _ok(data=None, **kwargs):
    return jsonify({"success": True, "data": data, **kwargs})

def _err(msg: str, code: int = 400):
    return jsonify({"success": False, "error": msg}), code


# ═══════════════════════════════════════════════════════════════════════════════
# 偏好收集
# ═══════════════════════════════════════════════════════════════════════════════

@llm_rlhf_bp.route("/preference/generate", methods=["POST"])
def generate_pair():
    """生成 A/B 对比对。"""
    body = request.get_json(silent=True) or {}
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return _err("prompt is required")

    temp_a = body.get("temp_a", 0.3)
    temp_b = body.get("temp_b", 0.9)

    try:
        engine = get_llm_rlhf_engine()
        result = engine.generate_pair(prompt, temp_a=temp_a, temp_b=temp_b)
        return _ok(result)
    except Exception as e:
        return _err(str(e), 500)


@llm_rlhf_bp.route("/preference/record", methods=["POST"])
def record_preference():
    """记录人类选择。"""
    body = request.get_json(silent=True) or {}
    required = ["pair_id", "prompt", "response_a", "response_b", "chosen"]
    for field in required:
        if field not in body:
            return _err(f"{field} is required")

    engine = get_llm_rlhf_engine()
    result = engine.record_preference(
        body["pair_id"], body["prompt"],
        body["response_a"], body["response_b"], body["chosen"],
    )
    if "error" in result:
        return _err(result["error"])
    return _ok(result)


@llm_rlhf_bp.route("/preference/pairs", methods=["GET"])
def get_pairs():
    """查看已收集的偏好对。"""
    limit = request.args.get("limit", 50, type=int)
    engine = get_llm_rlhf_engine()
    return _ok(engine.get_preference_pairs(limit))


@llm_rlhf_bp.route("/preference/export", methods=["GET"])
def export_dpo():
    """导出 DPO 格式数据集。"""
    engine = get_llm_rlhf_engine()
    dataset = engine.export_dpo_dataset()
    return _ok(dataset, count=len(dataset))


# ═══════════════════════════════════════════════════════════════════════════════
# 奖励模型
# ═══════════════════════════════════════════════════════════════════════════════

@llm_rlhf_bp.route("/reward-model/train", methods=["POST"])
def train_reward_model():
    """训练奖励模型。"""
    body = request.get_json(silent=True) or {}
    lr = body.get("lr", 0.1)
    epochs = body.get("epochs", 100)

    engine = get_llm_rlhf_engine()
    result = engine.train_reward_model(lr=lr, epochs=epochs)
    if "error" in result:
        return _err(result["error"])
    return _ok(result)


@llm_rlhf_bp.route("/reward-model/score", methods=["POST"])
def score_response():
    """给回答打分。"""
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return _err("text is required")

    engine = get_llm_rlhf_engine()
    result = engine.score_response(text)
    if "error" in result:
        return _err(result["error"])
    return _ok(result)


@llm_rlhf_bp.route("/reward-model/info", methods=["GET"])
def reward_model_info():
    """奖励模型信息。"""
    engine = get_llm_rlhf_engine()
    return _ok(engine.get_reward_model_info())


# ═══════════════════════════════════════════════════════════════════════════════
# 提示词优化
# ═══════════════════════════════════════════════════════════════════════════════

@llm_rlhf_bp.route("/optimization/create", methods=["POST"])
def create_optimization():
    """创建优化任务。"""
    body = request.get_json(silent=True) or {}
    base_prompt = body.get("base_prompt", "").strip()
    test_input = body.get("test_input", "").strip()
    if not base_prompt or not test_input:
        return _err("base_prompt and test_input are required")

    engine = get_llm_rlhf_engine()
    result = engine.create_optimization(
        base_prompt, test_input,
        population_size=body.get("population_size", 6),
        max_generations=body.get("max_generations", 3),
    )
    return _ok(result)


@llm_rlhf_bp.route("/optimization/<run_id>/step", methods=["POST"])
def optimization_step(run_id):
    """运行一代。"""
    engine = get_llm_rlhf_engine()
    result = engine.run_optimization_step(run_id)
    if "error" in result:
        return _err(result["error"])
    return _ok(result)


@llm_rlhf_bp.route("/optimization/<run_id>/run-all", methods=["POST"])
def optimization_run_all(run_id):
    """运行全部代。"""
    engine = get_llm_rlhf_engine()
    result = engine.run_optimization_all(run_id)
    return _ok(result)


@llm_rlhf_bp.route("/optimization/<run_id>", methods=["GET"])
def get_optimization(run_id):
    """查看优化进度。"""
    engine = get_llm_rlhf_engine()
    result = engine.get_optimization(run_id)
    if result is None:
        return _err("Run not found", 404)
    return _ok(result)


@llm_rlhf_bp.route("/optimization/runs", methods=["GET"])
def list_optimizations():
    """列出所有优化任务。"""
    engine = get_llm_rlhf_engine()
    return _ok(engine.list_optimizations())


# ═══════════════════════════════════════════════════════════════════════════════
# 评估 & 排名
# ═══════════════════════════════════════════════════════════════════════════════

@llm_rlhf_bp.route("/evaluate", methods=["POST"])
def evaluate():
    """评估单个输出。"""
    body = request.get_json(silent=True) or {}
    prompt = body.get("prompt", "").strip()
    response = body.get("response", "").strip()
    if not prompt or not response:
        return _err("prompt and response are required")

    try:
        engine = get_llm_rlhf_engine()
        result = engine.evaluate(prompt, response)
        return _ok(result)
    except Exception as e:
        return _err(str(e), 500)


@llm_rlhf_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    """ELO 排行榜。"""
    engine = get_llm_rlhf_engine()
    return _ok(engine.get_leaderboard())


@llm_rlhf_bp.route("/stats", methods=["GET"])
def stats():
    """总览统计。"""
    engine = get_llm_rlhf_engine()
    return _ok(engine.get_stats())


# ═══════════════════════════════════════════════════════════════════════════════
# 端点管理（自定义模型端点）
# ═══════════════════════════════════════════════════════════════════════════════

@llm_rlhf_bp.route("/endpoint/set", methods=["POST"])
def set_endpoint():
    """设置自定义端点（本地微调模型）。"""
    body = request.get_json(silent=True) or {}
    base_url = body.get("base_url", "").strip()
    model = body.get("model", "").strip()
    api_key = body.get("api_key", "not-needed")

    if not base_url:
        return _err("base_url is required")
    if not model:
        return _err("model is required")

    engine = get_llm_rlhf_engine()
    result = engine.set_endpoint(base_url, model, api_key)
    return _ok(result)


@llm_rlhf_bp.route("/endpoint/clear", methods=["POST"])
def clear_endpoint():
    """恢复默认模型。"""
    engine = get_llm_rlhf_engine()
    result = engine.clear_endpoint()
    return _ok(result)


@llm_rlhf_bp.route("/endpoint/current", methods=["GET"])
def current_endpoint():
    """查看当前活跃端点。"""
    engine = get_llm_rlhf_engine()
    return _ok(engine.get_current_endpoint())
