#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因果推理引擎 API
提供因果分析、反事实推理、效果预测、根因分析、干预分析的 HTTP 接口
"""

from flask import Blueprint, request, jsonify
from agent_framework.causal.causal_reasoning_engine import (
    get_causal_engine,
    CausalRelationType,
    ConfidenceLevel,
    AnalysisMode,
)

causal_reasoning_bp = Blueprint('causal_reasoning', __name__, url_prefix='/api/causal-reasoning')


# ── 1. 因果链分析 ──

@causal_reasoning_bp.route('/analyze', methods=['POST'])
def analyze_causal_chain():
    """分析因果链"""
    data = request.json
    cause = data.get('cause', '').strip()
    effect = data.get('effect', '').strip()
    context = data.get('context', '').strip()

    if not cause or not effect:
        return jsonify({'error': '起始事件和目标事件不能为空'}), 400

    try:
        engine = get_causal_engine()
        result = engine.analyze_causal_chain(cause, effect, context if context else None)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 2. 反事实推理 ──

@causal_reasoning_bp.route('/counterfactual', methods=['POST'])
def counterfactual_reasoning():
    """反事实推理"""
    data = request.json
    original_cause = data.get('original_cause', '').strip()
    alternative_cause = data.get('alternative_cause', '').strip()
    observed_effect = data.get('observed_effect', '').strip()
    context = data.get('context', '').strip()

    if not original_cause or not alternative_cause or not observed_effect:
        return jsonify({'error': '所有字段都不能为空'}), 400

    try:
        engine = get_causal_engine()
        result = engine.counterfactual_reasoning(
            original_cause, alternative_cause, observed_effect,
            context if context else None
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 3. 效果预测 ──

@causal_reasoning_bp.route('/predict-effects', methods=['POST'])
def predict_effects():
    """预测可能的结果"""
    data = request.json
    cause = data.get('cause', '').strip()
    context = data.get('context', '').strip()
    num_predictions = data.get('num_predictions', 5)

    if not cause:
        return jsonify({'error': '原因不能为空'}), 400

    try:
        engine = get_causal_engine()
        result = engine.predict_effects(
            cause, context if context else None, num_predictions
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 4. 根因分析 ──

@causal_reasoning_bp.route('/root-cause', methods=['POST'])
def root_cause_analysis():
    """根因分析"""
    data = request.json
    observed_effect = data.get('observed_effect', '').strip()
    context = data.get('context', '').strip()
    depth = data.get('depth', 3)

    if not observed_effect:
        return jsonify({'error': '观察到的现象不能为空'}), 400

    try:
        engine = get_causal_engine()
        result = engine.root_cause_analysis(
            observed_effect, context if context else None, depth
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 5. 干预分析 ──

@causal_reasoning_bp.route('/intervention', methods=['POST'])
def intervention_analysis():
    """干预分析"""
    data = request.json
    current_situation = data.get('current_situation', '').strip()
    proposed_intervention = data.get('proposed_intervention', '').strip()
    desired_outcome = data.get('desired_outcome', '').strip()
    context = data.get('context', '').strip()

    if not current_situation or not proposed_intervention or not desired_outcome:
        return jsonify({'error': '当前状况、干预措施和期望结果都不能为空'}), 400

    try:
        engine = get_causal_engine()
        result = engine.intervention_analysis(
            current_situation, proposed_intervention, desired_outcome,
            context if context else None
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 评估与查询 ──

@causal_reasoning_bp.route('/evaluate-strength', methods=['POST'])
def evaluate_strength():
    """评估因果关系强度"""
    data = request.json
    cause_id = data.get('cause_id', '').strip()
    effect_id = data.get('effect_id', '').strip()

    if not cause_id or not effect_id:
        return jsonify({'error': '原因ID和结果ID不能为空'}), 400

    try:
        engine = get_causal_engine()
        result = engine.evaluate_causal_strength(cause_id, effect_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/explain', methods=['POST'])
def explain_causation():
    """解释因果关系"""
    data = request.json
    cause_id = data.get('cause_id', '').strip()
    effect_id = data.get('effect_id', '').strip()

    if not cause_id or not effect_id:
        return jsonify({'error': '原因ID和结果ID不能为空'}), 400

    try:
        engine = get_causal_engine()
        result = engine.explain_causation(cause_id, effect_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/common-causes', methods=['POST'])
def find_common_causes():
    """查找共同原因"""
    data = request.json
    effect_ids = data.get('effect_ids', [])

    if not effect_ids or len(effect_ids) < 2:
        return jsonify({'error': '至少需要两个结果ID'}), 400

    try:
        engine = get_causal_engine()
        common = engine.find_common_causes(effect_ids)
        return jsonify({'common_causes': [n.to_dict() for n in common]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/common-effects', methods=['POST'])
def find_common_effects():
    """查找共同结果"""
    data = request.json
    cause_ids = data.get('cause_ids', [])

    if not cause_ids or len(cause_ids) < 2:
        return jsonify({'error': '至少需要两个原因ID'}), 400

    try:
        engine = get_causal_engine()
        common = engine.find_common_effects(cause_ids)
        return jsonify({'common_effects': [n.to_dict() for n in common]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 图谱管理 ──

@causal_reasoning_bp.route('/graph/statistics', methods=['GET'])
def get_statistics():
    """获取图谱统计信息"""
    try:
        engine = get_causal_engine()
        return jsonify(engine.get_graph_statistics())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/graph/export', methods=['GET'])
def export_graph():
    """导出完整图谱"""
    try:
        engine = get_causal_engine()
        return jsonify(engine.export_graph())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/graph/clear', methods=['POST'])
def clear_graph():
    """清空图谱"""
    try:
        engine = get_causal_engine()
        engine.clear_graph()
        return jsonify({'message': '图谱已清空'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/history', methods=['GET'])
def get_history():
    """获取推理历史"""
    try:
        engine = get_causal_engine()
        return jsonify({'history': engine.get_reasoning_history()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 高级查询 ──

@causal_reasoning_bp.route('/node/importance', methods=['POST'])
def get_node_importance():
    """获取节点重要性"""
    data = request.json
    node_id = data.get('node_id', '').strip()

    if not node_id:
        return jsonify({'error': '节点ID不能为空'}), 400

    try:
        engine = get_causal_engine()
        result = engine.get_node_importance(node_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/graph/critical-nodes', methods=['GET'])
def get_critical_nodes():
    """获取关键节点"""
    top_n = request.args.get('top_n', 10, type=int)

    try:
        engine = get_causal_engine()
        result = engine.find_critical_nodes(top_n)
        return jsonify({'critical_nodes': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/graph/cycles', methods=['GET'])
def detect_cycles():
    """检测环路"""
    try:
        engine = get_causal_engine()
        cycles = engine.detect_cycles()
        return jsonify({'cycles': cycles, 'count': len(cycles)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/graph/shortest-path', methods=['POST'])
def get_shortest_path():
    """获取最短路径"""
    data = request.json
    start_id = data.get('start_id', '').strip()
    end_id = data.get('end_id', '').strip()

    if not start_id or not end_id:
        return jsonify({'error': '起始ID和目标ID不能为空'}), 400

    try:
        engine = get_causal_engine()
        path = engine.get_shortest_path(start_id, end_id)
        if path:
            return jsonify({'path': path.to_dict()})
        else:
            return jsonify({'path': None, 'message': '未找到路径'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/graph/topology', methods=['GET'])
def get_graph_topology():
    """获取图谱拓扑信息"""
    try:
        engine = get_causal_engine()
        isolated = engine.graph.get_isolated_nodes()
        roots = engine.graph.get_root_nodes()
        leaves = engine.graph.get_leaf_nodes()

        return jsonify({
            'isolated_nodes': [n.to_dict() for n in isolated],
            'root_nodes': [n.to_dict() for n in roots],
            'leaf_nodes': [n.to_dict() for n in leaves],
            'isolated_count': len(isolated),
            'root_count': len(roots),
            'leaf_count': len(leaves),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@causal_reasoning_bp.route('/batch-analyze', methods=['POST'])
def batch_analyze():
    """批量分析因果对"""
    data = request.json
    pairs = data.get('pairs', [])
    context = data.get('context', '').strip()

    if not pairs or not isinstance(pairs, list):
        return jsonify({'error': 'pairs 必须是非空列表'}), 400

    # 验证格式
    for pair in pairs:
        if not isinstance(pair, dict) or 'cause' not in pair or 'effect' not in pair:
            return jsonify({'error': '每个 pair 必须包含 cause 和 effect 字段'}), 400

    try:
        engine = get_causal_engine()
        pairs_tuples = [(p['cause'], p['effect']) for p in pairs]
        results = engine.batch_analyze(pairs_tuples, context if context else None)
        return jsonify({'results': results, 'total': len(results)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 元信息 ──

@causal_reasoning_bp.route('/relation-types', methods=['GET'])
def get_relation_types():
    """获取所有因果关系类型"""
    return jsonify({
        'relation_types': [
            {'value': r.value, 'name': r.name} for r in CausalRelationType
        ]
    })


@causal_reasoning_bp.route('/confidence-levels', methods=['GET'])
def get_confidence_levels():
    """获取置信度等级定义"""
    return jsonify({
        'confidence_levels': [
            {'name': l.name, 'min': l.value[0], 'max': l.value[1], 'label': l.value[2]}
            for l in ConfidenceLevel
        ]
    })


@causal_reasoning_bp.route('/analysis-modes', methods=['GET'])
def get_analysis_modes():
    """获取分析模式列表"""
    modes = {
        "causal_chain": {"name": "因果链分析", "description": "分析原因到结果的完整因果链路"},
        "counterfactual": {"name": "反事实推理", "description": "如果原因不同，结果会如何变化"},
        "prediction": {"name": "效果预测", "description": "预测给定原因可能产生的多种结果"},
        "root_cause": {"name": "根因分析", "description": "从观察到的现象追溯根本原因"},
        "intervention": {"name": "干预分析", "description": "评估干预措施的因果影响"},
    }
    return jsonify({'modes': modes})


# ── 案例库 ──

@causal_reasoning_bp.route('/examples', methods=['GET'])
def get_examples():
    """获取各分析模式的案例列表"""
    mode = request.args.get('mode', '')
    examples = _get_examples()
    if mode and mode in examples:
        return jsonify({'examples': examples[mode]})
    return jsonify({'examples': examples})


def _get_examples():
    return {
        "causal_chain": [
            {"label": "央行加息与资本外流", "cause": "全球央行同步加息", "effect": "新兴市场经济体出现资本外流", "context": "在全球通胀压力上升、美联储带头激进加息的背景下，多个主要经济体央行跟随收紧货币政策。"},
            {"label": "AI 技术与就业结构", "cause": "大规模部署通用人工智能技术", "effect": "全球劳动力市场结构发生根本性变革", "context": "AI 技术从文本生成扩展到自主决策、代码开发、科研辅助等领域，各行业加速部署。"},
            {"label": "气候变暖与粮食安全", "cause": "全球平均气温较工业化前上升2°C", "effect": "全球粮食价格大幅波动并引发社会动荡", "context": "极端天气事件频发，主要粮食产区均受到不同程度影响。"},
            {"label": "社交媒体与青少年心理", "cause": "青少年日均社交媒体使用时间超过4小时", "effect": "青少年抑郁和焦虑症发病率显著上升", "context": "短视频平台算法推荐导致使用成瘾，社交比较效应加剧。"},
            {"label": "远程办公与城市格局", "cause": "大型科技公司全面推行永久远程办公", "effect": "一线城市房价下跌而二三线城市房价上涨", "context": "员工不再需要居住在公司所在城市，开始向生活成本更低的地区迁移。"},
        ],
        "counterfactual": [
            {"label": "数字化转型策略", "original_cause": "渐进式数字化转型策略", "alternative_cause": "一次性全面数字化改造", "observed_effect": "三年内实现50%运营效率提升", "context": "拥有5000名员工的传统制造企业。"},
            {"label": "新能源汽车路线之争", "original_cause": "押注纯电动路线投入500亿研发", "alternative_cause": "氢燃料电池与混动并行技术路线", "observed_effect": "五年后成为新能源汽车销量前三", "context": "2020年中国新能源汽车市场竞争激烈。"},
            {"label": "教育政策假设", "original_cause": "严格高考制度作为唯一入学标准", "alternative_cause": "综合素质评价加多元化录取制度", "observed_effect": "培养出大量高分但创新能力参差不齐的毕业生", "context": "14亿人口，每年约1000万高考考生。"},
            {"label": "疫情应对策略", "original_cause": "疫情初期严格封控清零", "alternative_cause": "群体免疫加重点保护策略", "observed_effect": "死亡率控制在较低水平但经济受较大冲击", "context": "2020年初全球新冠疫情爆发。"},
        ],
        "prediction": [
            {"label": "四天工作制", "cause": "某国全面推行四天工作制", "context": "发达经济体，服务业占GDP的70%。"},
            {"label": "量子计算机商用", "cause": "百万量子比特通用量子计算机商用", "context": "量子计算在密码学、药物研发、材料科学等领域具备实用价值。"},
            {"label": "全球碳交易统一", "cause": "联合国建立全球统一碳交易市场，碳价下限100美元/吨", "context": "目前各国碳交易市场碎片化。"},
            {"label": "脑机接口普及", "cause": "非侵入式脑机接口成本降至消费级", "context": "当前脑机接口主要用于医疗辅助。"},
            {"label": "人口负增长拐点", "cause": "中国人口连续5年负增长年均减少800万", "context": "生育率降至0.8以下，老龄化加速。"},
        ],
        "root_cause": [
            {"label": "平台用户流失", "observed_effect": "互联网平台用户活跃度连续三季度下降", "context": "5亿注册用户，日活从1.5亿下滑至1亿以下。"},
            {"label": "芯片制造良率", "observed_effect": "3nm芯片量产良率始终低于50%", "context": "投入超200亿美元，拥有最新光刻机。"},
            {"label": "电商退货率飙升", "observed_effect": "电商平台服装品类退货率从20%飙升至45%", "context": "月活3亿用户，退货率6个月内急剧上升。"},
            {"label": "创业公司倒闭潮", "observed_effect": "科技园区一年内超40%创业公司倒闭", "context": "入驻约200家初创企业，以AI和生物科技为主。"},
            {"label": "员工离职率异常", "observed_effect": "知名科技公司核心研发团队年离职率35%", "context": "市值增长3倍，薪资中上水平，但关键骨干持续流失。"},
        ],
        "intervention": [
            {"label": "城市交通治理", "current_situation": "早晚高峰平均通勤超90分钟", "proposed_intervention": "分区限行并大力发展公共交通", "desired_outcome": "通勤降至60分钟以内", "context": "1500万人口特大城市。"},
            {"label": "在线教育改革", "current_situation": "农村教育质量远低于城市", "proposed_intervention": "部署AI个性化教学加城乡教师轮岗", "desired_outcome": "城乡升学率差距缩小到1.5倍", "context": "农村师资薄弱但智能手机普及率90%。"},
            {"label": "抗生素耐药性", "current_situation": "超级细菌感染年增15%", "proposed_intervention": "禁止畜牧业预防性用抗生素并设100亿研发基金", "desired_outcome": "感染增长率降至5%以下", "context": "全球年70万人死于耐药性感染。"},
            {"label": "新能源电网改造", "current_situation": "可再生能源40%但弃风弃光严重", "proposed_intervention": "投资2000亿建设储能和智能电网", "desired_outcome": "弃风弃光率从15%降至3%", "context": "风电光伏快速增长但储能严重滞后。"},
            {"label": "老年人数字鸿沟", "current_situation": "65岁以上仅30%能独立使用数字服务", "proposed_intervention": "老年人数字培训加强制保留线下通道", "desired_outcome": "独立使用率提升至60%", "context": "社会服务快速数字化，老年人被排斥。"},
        ],
    }
