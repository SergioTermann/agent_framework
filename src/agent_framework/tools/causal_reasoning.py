"""
因果推理工具集 —— 让 Agent 在对话中调用因果分析能力

提供 5 个核心工具：
  1. analyze_causal_chain   — 分析因果链
  2. counterfactual_reason  — 反事实推理
  3. predict_effects        — 效果预测
  4. root_cause_analyze     — 根因分析
  5. intervention_evaluate  — 干预评估
"""

import json
from agent_framework.causal.causal_reasoning_engine import get_causal_engine


# ─── 主工具（TOOL_META 指定）────────────────────────────────────────────────

TOOL_META = {
    "name": "analyze_causal_chain",
    "description": (
        "分析因果链：给定一个原因和结果，推理出完整的因果传导路径，"
        "包括中间环节、因果机制、置信度和替代路径。"
        "适合回答A怎么导致B、X和Y之间有什么因果关系等问题。"
    ),
}


def analyze_causal_chain(cause: str, effect: str, context: str = "") -> str:
    """
    分析从原因到结果的因果链路

    :param cause: 起始原因（如：全球央行加息）
    :param effect: 最终结果（如：房地产市场降温）
    :param context: 背景信息，可选
    """
    try:
        engine = get_causal_engine()
        result = engine.analyze_causal_chain(cause, effect, context if context else None)

        lines = []
        lines.append(f"## 因果链分析：{cause} → {effect}\n")

        if result.get("summary"):
            lines.append(f"**总结：** {result['summary']}\n")

        lines.append(f"**链路置信度：** {result.get('chain_confidence', 0):.0%}")
        lines.append(f"**推理节点数：** {result.get('node_count', 0)}\n")

        # 展示因果树
        tree = result.get("tree")
        if tree:
            lines.append("### 因果推理路径")
            _format_tree(tree, lines, depth=0)

        # 替代路径
        alt_paths = result.get("alternative_paths", [])
        if alt_paths:
            lines.append("\n### 替代路径")
            for p in alt_paths:
                lines.append(f"- {p.get('description', '')}（可能性：{p.get('likelihood', 0):.0%}）")

        # 假设与局限
        assumptions = result.get("assumptions", [])
        if assumptions:
            lines.append("\n### 关键假设")
            for a in assumptions:
                lines.append(f"- {a}")

        limitations = result.get("limitations", [])
        if limitations:
            lines.append("\n### 局限性")
            for l in limitations:
                lines.append(f"- {l}")

        return "\n".join(lines)
    except Exception as e:
        return f"因果链分析失败：{e}"


def _format_tree(node: dict, lines: list, depth: int = 0):
    """递归格式化因果树为文本"""
    if not node:
        return
    indent = "  " * depth
    marker = {"cause": "[原因]", "effect": "[结果]", "intermediate": "[中间]"}.get(
        node.get("type", ""), "[节点]"
    )
    conf = node.get("confidence", 0)
    lines.append(f"{indent}{marker} {node.get('content', '')}（置信度 {conf:.0%}）")

    if node.get("mechanism"):
        lines.append(f"{indent}  ↳ 机制：{node['mechanism']}")
    if node.get("relation"):
        lines.append(f"{indent}  ↳ 关系：{node['relation']}")

    for child in node.get("children", []):
        _format_tree(child, lines, depth + 1)


# ─── 额外工具 ──────────────────────────────────────────────────────────────

EXTRA_TOOLS = [
    {
        "name": "counterfactual_reason",
        "description": (
            "反事实推理：分析如果原因不同结果会怎样变化。"
            "适合回答如果当时选择了B而不是A会怎样、换一种做法会有什么不同等问题。"
        ),
        "handler": None,
    },
    {
        "name": "predict_effects",
        "description": (
            "效果预测：给定一个原因或事件，预测可能产生的多种结果，"
            "包括概率、时间范围、影响程度。"
            "适合回答如果发生X会有什么后果、这个决策有哪些可能的影响等问题。"
        ),
        "handler": None,
    },
    {
        "name": "root_cause_analyze",
        "description": (
            "根因分析：从观察到的现象或问题追溯根本原因，"
            "使用5-Why等方法识别深层原因并提供改进建议。"
            "适合回答为什么会出现这个问题、这个现象的根本原因是什么等问题。"
        ),
        "handler": None,
    },
    {
        "name": "intervention_evaluate",
        "description": (
            "干预评估：评估一项干预措施的因果影响，"
            "分析可行性、有效性、副作用和替代方案。"
            "适合回答采取这个措施效果如何、这个方案有什么风险等问题。"
        ),
        "handler": None,
    },
]


# ── 反事实推理 ──

def counterfactual_reason(original_cause: str, alternative_cause: str,
                          observed_effect: str, context: str = "") -> str:
    """
    反事实推理：比较实际原因与假设原因带来的不同结果

    :param original_cause: 实际发生的原因
    :param alternative_cause: 假设的替代原因
    :param observed_effect: 实际观察到的结果
    :param context: 背景信息，可选
    """
    try:
        engine = get_causal_engine()
        result = engine.counterfactual_reasoning(
            original_cause, alternative_cause, observed_effect,
            context if context else None,
        )

        lines = []
        lines.append("## 反事实推理分析\n")

        # 原始场景
        orig = result.get("original_analysis", {})
        lines.append("### 实际场景")
        lines.append(f"- **原因：** {orig.get('cause', original_cause)}")
        lines.append(f"- **结果：** {orig.get('effect', observed_effect)}")
        lines.append(f"- **因果机制：** {orig.get('causal_mechanism', '')}")
        lines.append(f"- **置信度：** {orig.get('confidence', 0):.0%}\n")

        # 反事实场景
        cf = result.get("counterfactual_analysis", {})
        lines.append("### 反事实场景（假设）")
        lines.append(f"- **假设原因：** {cf.get('alternative_cause', alternative_cause)}")
        lines.append(f"- **预测结果：** {cf.get('predicted_effect', '')}")
        lines.append(f"- **结果概率：** {cf.get('effect_probability', 0):.0%}")
        lines.append(f"- **推理过程：** {cf.get('reasoning', '')}\n")

        # 对比
        cmp = result.get("comparison", {})
        if cmp.get("key_differences"):
            lines.append("### 关键差异")
            for d in cmp["key_differences"]:
                lines.append(f"- {d}")

        if cmp.get("sensitivity"):
            lines.append(f"\n**结果敏感度：** {cmp['sensitivity']}")

        if cmp.get("butterfly_effects"):
            lines.append("\n### 蝴蝶效应")
            for b in cmp["butterfly_effects"]:
                lines.append(f"- {b}")

        # 结论
        if result.get("conclusion"):
            lines.append(f"\n### 结论\n{result['conclusion']}")

        lines.append(f"\n**整体置信度：** {result.get('confidence_score', 0):.0%}")

        return "\n".join(lines)
    except Exception as e:
        return f"反事实推理失败：{e}"


# ── 效果预测 ──

def predict_effects(cause: str, context: str = "",
                    num_predictions: int = 5) -> str:
    """
    预测给定原因或事件可能产生的多种结果

    :param cause: 原因或事件描述
    :param context: 背景信息，可选
    :param num_predictions: 预测结果数量，默认5个
    """
    try:
        engine = get_causal_engine()
        result = engine.predict_effects(
            cause, context if context else None, num_predictions,
        )

        lines = []
        lines.append(f"## 效果预测：{cause}\n")

        if result.get("overall_assessment"):
            lines.append(f"**整体评估：** {result['overall_assessment']}\n")

        preds = result.get("predictions", [])
        for i, p in enumerate(preds, 1):
            lines.append(f"### 预测 {i}：{p.get('effect', '')}")
            lines.append(f"- **概率：** {p.get('probability', 0):.0%}")
            if p.get("timeframe"):
                lines.append(f"- **时间范围：** {p['timeframe']}")
            if p.get("impact_level"):
                lines.append(f"- **影响程度：** {p['impact_level']}")
            if p.get("category"):
                lines.append(f"- **类别：** {p['category']}")
            if p.get("reasoning"):
                lines.append(f"- **理由：** {p['reasoning']}")
            if p.get("preconditions"):
                lines.append(f"- **前提条件：** {', '.join(p['preconditions'])}")
            lines.append("")

        risks = result.get("risk_factors", [])
        if risks:
            lines.append("### 风险因素")
            for r in risks:
                lines.append(f"- {r}")

        return "\n".join(lines)
    except Exception as e:
        return f"效果预测失败：{e}"


# ── 根因分析 ──

def root_cause_analyze(observed_effect: str, context: str = "",
                       depth: int = 3) -> str:
    """
    对观察到的现象进行根因分析，追溯根本原因

    :param observed_effect: 观察到的现象或问题
    :param context: 背景信息，可选
    :param depth: 分析深度（2=快速，3=标准，5=深度），默认3
    """
    try:
        engine = get_causal_engine()
        result = engine.root_cause_analysis(
            observed_effect, context if context else None, depth,
        )

        lines = []
        lines.append(f"## 根因分析：{observed_effect}\n")

        if result.get("analysis_method"):
            lines.append(f"**分析方法：** {result['analysis_method']}")
        lines.append(f"**分析置信度：** {result.get('confidence_score', 0):.0%}\n")

        causes = result.get("root_causes", [])
        for i, c in enumerate(causes, 1):
            lines.append(f"### 根因 {i}：{c.get('cause', '')}")
            lines.append(f"- **置信度：** {c.get('confidence', 0):.0%}")
            if c.get("category"):
                lines.append(f"- **类别：** {c['category']}")
            if c.get("severity"):
                lines.append(f"- **严重度：** {c['severity']}")
            chain = c.get("causal_chain", [])
            if chain:
                lines.append(f"- **因果链条：** {' → '.join(chain)}")
            evidence = c.get("evidence", [])
            if evidence:
                lines.append(f"- **证据：** {'; '.join(evidence)}")
            lines.append("")

        factors = result.get("contributing_factors", [])
        if factors:
            lines.append("### 促进因素")
            for f in factors:
                lines.append(f"- {f.get('factor', '')}（影响度 {f.get('influence', 0):.0%}）")
            lines.append("")

        actions = result.get("recommended_actions", [])
        if actions:
            lines.append("### 建议措施")
            for a in actions:
                priority = f"[{a.get('priority', '')}]" if a.get("priority") else ""
                lines.append(f"- {priority} {a.get('action', '')}")
                if a.get("expected_impact"):
                    lines.append(f"  预期效果：{a['expected_impact']}")

        return "\n".join(lines)
    except Exception as e:
        return f"根因分析失败：{e}"


# ── 干预评估 ──

def intervention_evaluate(current_situation: str, proposed_intervention: str,
                          desired_outcome: str, context: str = "") -> str:
    """
    评估干预措施的因果影响，分析可行性、有效性和副作用

    :param current_situation: 当前状况描述
    :param proposed_intervention: 提议的干预措施
    :param desired_outcome: 期望达到的结果
    :param context: 背景信息，可选
    """
    try:
        engine = get_causal_engine()
        result = engine.intervention_analysis(
            current_situation, proposed_intervention, desired_outcome,
            context if context else None,
        )

        lines = []
        lines.append(f"## 干预评估：{proposed_intervention}\n")

        # 综合评估
        assess = result.get("intervention_assessment", {})
        lines.append("### 综合评估")
        if assess.get("feasibility") is not None:
            lines.append(f"- **可行性：** {assess['feasibility']:.0%}")
        if assess.get("effectiveness") is not None:
            lines.append(f"- **有效性：** {assess['effectiveness']:.0%}")
        if assess.get("risk_level"):
            lines.append(f"- **风险等级：** {assess['risk_level']}")
        if assess.get("time_to_effect"):
            lines.append(f"- **预计生效时间：** {assess['time_to_effect']}")
        if result.get("success_probability") is not None:
            lines.append(f"- **成功概率：** {result['success_probability']:.0%}")
        lines.append("")

        # 因果路径
        pathway = result.get("causal_pathway", {})

        direct = pathway.get("direct_effects", [])
        if direct:
            lines.append("### 直接效果")
            for e in direct:
                lines.append(f"- {e.get('effect', '')}（概率 {e.get('probability', 0):.0%}）")
                if e.get("mechanism"):
                    lines.append(f"  机制：{e['mechanism']}")

        indirect = pathway.get("indirect_effects", [])
        if indirect:
            lines.append("\n### 间接效果")
            for e in indirect:
                lines.append(f"- {e.get('effect', '')}（概率 {e.get('probability', 0):.0%}）")
                if e.get("delay"):
                    lines.append(f"  延迟：{e['delay']}")

        side = pathway.get("side_effects", [])
        if side:
            lines.append("\n### 潜在副作用")
            for e in side:
                sev = f"[{e.get('severity', '')}]" if e.get("severity") else ""
                lines.append(f"- {sev} {e.get('effect', '')}（概率 {e.get('probability', 0):.0%}）")

        # 替代方案
        alts = result.get("alternative_interventions", [])
        if alts:
            lines.append("\n### 替代方案")
            for a in alts:
                lines.append(f"- **{a.get('intervention', '')}**")
                if a.get("advantage"):
                    lines.append(f"  优势：{a['advantage']}")
                if a.get("disadvantage"):
                    lines.append(f"  劣势：{a['disadvantage']}")

        # 最终建议
        if result.get("recommendation"):
            lines.append(f"\n### 最终建议\n{result['recommendation']}")

        lines.append(f"\n**分析置信度：** {result.get('confidence_score', 0):.0%}")

        return "\n".join(lines)
    except Exception as e:
        return f"干预评估失败：{e}"


# ── 绑定 handler ──

EXTRA_TOOLS[0]["handler"] = counterfactual_reason
EXTRA_TOOLS[1]["handler"] = predict_effects
EXTRA_TOOLS[2]["handler"] = root_cause_analyze
EXTRA_TOOLS[3]["handler"] = intervention_evaluate
