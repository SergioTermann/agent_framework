"""
LLM-First Reinforcement Learning REST API
=========================================
URL 前缀：/api/rl

这个模块不再暴露传统游戏/控制类 RL 接口，而是统一面向：
  - 偏好数据采集
  - 奖励模型训练与打分
  - LLM-as-Judge 评测
  - Prompt / Policy 优化
  - RLHF / DPO 数据闭环
"""

from flask import Blueprint, jsonify, request

from agent_framework.reasoning.llm_rlhf_engine import get_llm_rlhf_engine

rl_bp = Blueprint("rl", __name__, url_prefix="/api/rl")


def _ok(data=None, **kwargs):
    return jsonify({"success": True, "data": data, **kwargs})


def _err(msg: str, code: int = 400):
    return jsonify({"success": False, "error": msg}), code


def _engine():
    return get_llm_rlhf_engine()


def _scenario_catalog():
    return [
        {
            "id": "instruction_policy",
            "name": "指令遵循与回复策略",
            "description": "围绕直接回答、结构化回答、澄清、拒答与工具调用，学习更适合大模型回复生成的策略。",
            "reward_signal": ["人工偏好", "规则打分", "Judge 评分", "安全约束"],
        },
        {
            "id": "rag_policy",
            "name": "RAG检索决策",
            "description": "在证据充分、证据冲突、证据不足等情况下学习继续检索、引用作答或请求补充信息。",
            "reward_signal": ["答案正确率", "引用质量", "幻觉率", "用户满意度"],
        },
        {
            "id": "tool_agent",
            "name": "工具调用代理",
            "description": "面向 Agent 工作流，在日志、知识库、执行验证与输出建议之间学习动作顺序。",
            "reward_signal": ["任务完成率", "调用成本", "步骤长度", "结果可执行性"],
        },
        {
            "id": "preference_pipeline",
            "name": "偏好数据采样",
            "description": "面向 RLHF / DPO 数据生产，学习何时生成对比样本、请求人工偏好和导出训练数据。",
            "reward_signal": ["样本质量", "偏好一致性", "标注效率"],
        },
        {
            "id": "maintenance_ticket",
            "name": "运维工单诊断",
            "description": "贴合平台主场景，将告警初判、SOP 检索、日志排查和结构化工单输出串成反馈闭环。",
            "reward_signal": ["问题闭环率", "误报率", "响应时间", "专家复核通过率"],
        },
    ]


def _method_catalog():
    return [
        {
            "id": "preference_collection",
            "name": "偏好采集",
            "description": "生成 A/B 回复候选并记录人工偏好，作为 RLHF / DPO 的基础数据。",
            "endpoints": [
                "/api/rl/preference/generate",
                "/api/rl/preference/record",
                "/api/rl/preference/pairs",
                "/api/rl/datasets/dpo",
            ],
        },
        {
            "id": "reward_modeling",
            "name": "奖励模型",
            "description": "基于偏好数据训练奖励模型，并对候选回答进行打分。",
            "endpoints": [
                "/api/rl/reward-model/train",
                "/api/rl/reward-model/score",
                "/api/rl/reward-model/info",
            ],
        },
        {
            "id": "judge_evaluation",
            "name": "Judge 评测",
            "description": "使用 LLM-as-Judge 对回答按准确性、帮助性、安全性、创造性进行评估。",
            "endpoints": [
                "/api/rl/evaluate",
                "/api/rl/leaderboard",
                "/api/rl/stats",
            ],
        },
        {
            "id": "policy_optimization",
            "name": "Prompt / Policy 优化",
            "description": "面向提示词与策略迭代，执行种群生成、评估和多轮优化。",
            "endpoints": [
                "/api/rl/optimization/create",
                "/api/rl/optimization/<run_id>/step",
                "/api/rl/optimization/<run_id>/run-all",
                "/api/rl/optimization/<run_id>",
                "/api/rl/optimization/runs",
            ],
        },
        {
            "id": "model_endpoint",
            "name": "训练端点管理",
            "description": "切换当前用于采样、评测和优化的模型服务端点。",
            "endpoints": [
                "/api/rl/endpoint/set",
                "/api/rl/endpoint/clear",
                "/api/rl/endpoint/current",
            ],
        },
    ]


@rl_bp.route("/overview", methods=["GET"])
def overview():
    """返回 /api/rl 的整体能力说明。"""
    return _ok({
        "api_style": "llm_first_rl",
        "description": "面向大模型、Agent 与 RLHF / DPO 闭环的强化学习 API。",
        "scenarios": _scenario_catalog(),
        "methods": _method_catalog(),
        "current_endpoint": _engine().get_current_endpoint(),
    })


@rl_bp.route("/scenarios", methods=["GET"])
def scenarios():
    """列出当前支持的 LLM / Agent 强化学习场景。"""
    return _ok(_scenario_catalog())


@rl_bp.route("/methods", methods=["GET"])
def methods():
    """列出当前支持的 LLM-RL 方法与接口。"""
    return _ok(_method_catalog())


@rl_bp.route("/preference/generate", methods=["POST"])
def generate_preference_pair():
    """生成 A/B 对比回复，用于偏好标注。"""
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return _err("prompt is required")

    try:
        result = _engine().generate_pair(
            prompt,
            temp_a=body.get("temp_a", 0.3),
            temp_b=body.get("temp_b", 0.9),
        )
        return _ok(result)
    except Exception as e:
        return _err(str(e), 500)


@rl_bp.route("/preference/record", methods=["POST"])
def record_preference():
    """记录人工偏好选择。"""
    body = request.get_json(silent=True) or {}
    required = ["pair_id", "prompt", "response_a", "response_b", "chosen"]
    for field in required:
        if field not in body:
            return _err(f"{field} is required")

    result = _engine().record_preference(
        body["pair_id"],
        body["prompt"],
        body["response_a"],
        body["response_b"],
        body["chosen"],
    )
    if "error" in result:
        return _err(result["error"])
    return _ok(result)


@rl_bp.route("/preference/pairs", methods=["GET"])
def preference_pairs():
    """查看已收集的偏好样本。"""
    limit = request.args.get("limit", 50, type=int)
    return _ok(_engine().get_preference_pairs(limit))


@rl_bp.route("/datasets/dpo", methods=["GET"])
def export_dpo_dataset():
    """导出 DPO 训练数据。"""
    dataset = _engine().export_dpo_dataset()
    return _ok(dataset, count=len(dataset))


@rl_bp.route("/reward-model/train", methods=["POST"])
def train_reward_model():
    """训练奖励模型。"""
    body = request.get_json(silent=True) or {}
    result = _engine().train_reward_model(
        lr=body.get("lr", 0.1),
        epochs=body.get("epochs", 100),
    )
    if "error" in result:
        return _err(result["error"])
    return _ok(result)


@rl_bp.route("/reward-model/score", methods=["POST"])
def score_response():
    """对单条回答进行奖励模型打分。"""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return _err("text is required")

    result = _engine().score_response(text)
    if "error" in result:
        return _err(result["error"])
    return _ok(result)


@rl_bp.route("/reward-model/info", methods=["GET"])
def reward_model_info():
    """查看奖励模型状态。"""
    return _ok(_engine().get_reward_model_info())


@rl_bp.route("/optimization/create", methods=["POST"])
def create_optimization():
    """创建 Prompt / Policy 优化任务。"""
    body = request.get_json(silent=True) or {}
    base_prompt = (body.get("base_prompt") or "").strip()
    test_input = (body.get("test_input") or "").strip()
    if not base_prompt or not test_input:
        return _err("base_prompt and test_input are required")

    result = _engine().create_optimization(
        base_prompt=base_prompt,
        test_input=test_input,
        population_size=body.get("population_size", 6),
        max_generations=body.get("max_generations", 3),
    )
    return _ok(result)


@rl_bp.route("/optimization/<run_id>/step", methods=["POST"])
def optimization_step(run_id):
    """运行一代优化。"""
    result = _engine().run_optimization_step(run_id)
    if "error" in result:
        return _err(result["error"])
    return _ok(result)


@rl_bp.route("/optimization/<run_id>/run-all", methods=["POST"])
def optimization_run_all(run_id):
    """运行剩余全部优化迭代。"""
    return _ok(_engine().run_optimization_all(run_id))


@rl_bp.route("/optimization/<run_id>", methods=["GET"])
def get_optimization(run_id):
    """查看指定优化任务。"""
    result = _engine().get_optimization(run_id)
    if result is None:
        return _err("Run not found", 404)
    return _ok(result)


@rl_bp.route("/optimization/runs", methods=["GET"])
def list_optimizations():
    """列出所有优化任务。"""
    return _ok(_engine().list_optimizations())


@rl_bp.route("/evaluate", methods=["POST"])
def evaluate():
    """使用 LLM-as-Judge 评估单个回答。"""
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    response = (body.get("response") or "").strip()
    if not prompt or not response:
        return _err("prompt and response are required")

    try:
        return _ok(_engine().evaluate(prompt, response))
    except Exception as e:
        return _err(str(e), 500)


@rl_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    """查看 ELO 排行。"""
    return _ok(_engine().get_leaderboard())


@rl_bp.route("/stats", methods=["GET"])
def stats():
    """查看 LLM-RL 总览统计。"""
    engine = _engine()
    return _ok({
        **engine.get_stats(),
        "current_endpoint": engine.get_current_endpoint(),
        "scenario_count": len(_scenario_catalog()),
        "method_count": len(_method_catalog()),
    })


@rl_bp.route("/endpoint/set", methods=["POST"])
def set_endpoint():
    """设置当前采样 / 评测模型端点。"""
    body = request.get_json(silent=True) or {}
    base_url = (body.get("base_url") or "").strip()
    model = (body.get("model") or "").strip()
    api_key = body.get("api_key", "not-needed")

    if not base_url:
        return _err("base_url is required")
    if not model:
        return _err("model is required")

    return _ok(_engine().set_endpoint(base_url, model, api_key))


@rl_bp.route("/endpoint/clear", methods=["POST"])
def clear_endpoint():
    """恢复默认模型端点。"""
    return _ok(_engine().clear_endpoint())


@rl_bp.route("/endpoint/current", methods=["GET"])
def current_endpoint():
    """查看当前活跃模型端点。"""
    return _ok(_engine().get_current_endpoint())
