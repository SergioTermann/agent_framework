"""
高级推理引擎 API - Agent Framework
提供推理链管理、多步推理、假设验证等API接口
"""

from flask import Blueprint, request, jsonify
from typing import Dict, List, Any, Optional
import agent_framework.core.fast_json as json
import logging
from datetime import datetime

from agent_framework.reasoning.advanced_reasoning_engine import (
    get_reasoning_engine,
    ReasoningType,
    ReasoningStep,
    AdvancedReasoningEngine
)

logger = logging.getLogger(__name__)

# 创建蓝图
reasoning_bp = Blueprint('reasoning', __name__, url_prefix='/api/reasoning')

@reasoning_bp.route('/chains', methods=['POST'])
def create_reasoning_chain():
    """创建推理链"""
    try:
        data = request.get_json()

        problem = data.get('problem')
        if not problem:
            return jsonify({"error": "问题描述不能为空"}), 400

        reasoning_type_str = data.get('reasoning_type', 'deductive')
        try:
            reasoning_type = ReasoningType(reasoning_type_str)
        except ValueError:
            return jsonify({"error": f"无效的推理类型: {reasoning_type_str}"}), 400

        context = data.get('context', {})

        engine = get_reasoning_engine()
        chain_id = engine.create_reasoning_chain(problem, reasoning_type, context)

        return jsonify({
            "success": True,
            "chain_id": chain_id,
            "message": "推理链创建成功"
        })

    except Exception as e:
        logger.error(f"创建推理链失败: {str(e)}")
        return jsonify({"error": f"创建推理链失败: {str(e)}"}), 500

@reasoning_bp.route('/chains/<chain_id>/steps', methods=['POST'])
def add_reasoning_step(chain_id: str):
    """添加推理步骤"""
    try:
        data = request.get_json()

        step_type_str = data.get('step_type')
        if not step_type_str:
            return jsonify({"error": "步骤类型不能为空"}), 400

        try:
            step_type = ReasoningStep(step_type_str)
        except ValueError:
            return jsonify({"error": f"无效的步骤类型: {step_type_str}"}), 400

        content = data.get('content')
        if not content:
            return jsonify({"error": "步骤内容不能为空"}), 400

        evidence = data.get('evidence', [])
        assumptions = data.get('assumptions', [])
        parent_id = data.get('parent_id')

        engine = get_reasoning_engine()
        step_id = engine.add_reasoning_step(
            chain_id, step_type, content, evidence, assumptions, parent_id
        )

        return jsonify({
            "success": True,
            "step_id": step_id,
            "message": "推理步骤添加成功"
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"添加推理步骤失败: {str(e)}")
        return jsonify({"error": f"添加推理步骤失败: {str(e)}"}), 500

@reasoning_bp.route('/chains/<chain_id>/reflect', methods=['POST'])
def reflect_on_reasoning(chain_id: str):
    """对推理进行反思"""
    try:
        engine = get_reasoning_engine()
        reflection_results = engine.reflect_on_reasoning(chain_id)

        return jsonify({
            "success": True,
            "reflection_results": reflection_results,
            "message": "推理反思完成"
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"推理反思失败: {str(e)}")
        return jsonify({"error": f"推理反思失败: {str(e)}"}), 500

@reasoning_bp.route('/chains/<chain_id>/test-hypotheses', methods=['POST'])
def test_hypotheses(chain_id: str):
    """测试假设"""
    try:
        data = request.get_json()
        new_evidence = data.get('evidence', [])

        engine = get_reasoning_engine()
        test_results = engine.test_hypotheses(chain_id, new_evidence)

        return jsonify({
            "success": True,
            "test_results": test_results,
            "message": "假设测试完成"
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"假设测试失败: {str(e)}")
        return jsonify({"error": f"假设测试失败: {str(e)}"}), 500

@reasoning_bp.route('/chains/<chain_id>/alternatives', methods=['GET'])
def generate_alternatives(chain_id: str):
    """生成替代解释"""
    try:
        count = request.args.get('count', 3, type=int)

        engine = get_reasoning_engine()
        alternatives = engine.generate_alternative_explanations(chain_id, count)

        return jsonify({
            "success": True,
            "alternatives": alternatives,
            "count": len(alternatives)
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"生成替代解释失败: {str(e)}")
        return jsonify({"error": f"生成替代解释失败: {str(e)}"}), 500

@reasoning_bp.route('/chains/<chain_id>', methods=['GET'])
def get_reasoning_chain(chain_id: str):
    """获取推理链详情"""
    try:
        engine = get_reasoning_engine()
        chain = engine.get_reasoning_chain(chain_id)

        if not chain:
            return jsonify({"error": "推理链不存在"}), 404

        # 转换为可序列化的格式
        chain_data = engine.export_reasoning_chain(chain_id)

        return jsonify({
            "success": True,
            "chain": chain_data
        })

    except Exception as e:
        logger.error(f"获取推理链失败: {str(e)}")
        return jsonify({"error": f"获取推理链失败: {str(e)}"}), 500

@reasoning_bp.route('/chains', methods=['GET'])
def list_reasoning_chains():
    """列出所有推理链"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        reasoning_type = request.args.get('reasoning_type')

        engine = get_reasoning_engine()
        all_chains = engine.list_reasoning_chains()

        # 过滤推理类型
        if reasoning_type:
            all_chains = [
                chain for chain in all_chains
                if chain['reasoning_type'] == reasoning_type
            ]

        # 分页
        total = len(all_chains)
        start = (page - 1) * per_page
        end = start + per_page
        chains = all_chains[start:end]

        return jsonify({
            "success": True,
            "chains": chains,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        })

    except Exception as e:
        logger.error(f"列出推理链失败: {str(e)}")
        return jsonify({"error": f"列出推理链失败: {str(e)}"}), 500

@reasoning_bp.route('/chains/<chain_id>/export', methods=['GET'])
def export_reasoning_chain(chain_id: str):
    """导出推理链"""
    try:
        engine = get_reasoning_engine()
        chain_data = engine.export_reasoning_chain(chain_id)

        return jsonify({
            "success": True,
            "chain_data": chain_data,
            "export_time": datetime.now().isoformat()
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"导出推理链失败: {str(e)}")
        return jsonify({"error": f"导出推理链失败: {str(e)}"}), 500

@reasoning_bp.route('/chains/import', methods=['POST'])
def import_reasoning_chain():
    """导入推理链"""
    try:
        data = request.get_json()
        chain_data = data.get('chain_data')

        if not chain_data:
            return jsonify({"error": "推理链数据不能为空"}), 400

        engine = get_reasoning_engine()
        chain_id = engine.import_reasoning_chain(chain_data)

        return jsonify({
            "success": True,
            "chain_id": chain_id,
            "message": "推理链导入成功"
        })

    except Exception as e:
        logger.error(f"导入推理链失败: {str(e)}")
        return jsonify({"error": f"导入推理链失败: {str(e)}"}), 500

@reasoning_bp.route('/chains/<chain_id>', methods=['DELETE'])
def delete_reasoning_chain(chain_id: str):
    """删除推理链"""
    try:
        engine = get_reasoning_engine()

        if chain_id not in engine.reasoning_chains:
            return jsonify({"error": "推理链不存在"}), 404

        del engine.reasoning_chains[chain_id]

        return jsonify({
            "success": True,
            "message": "推理链删除成功"
        })

    except Exception as e:
        logger.error(f"删除推理链失败: {str(e)}")
        return jsonify({"error": f"删除推理链失败: {str(e)}"}), 500

@reasoning_bp.route('/async-reasoning', methods=['POST'])
def async_reasoning():
    """异步推理"""
    try:
        data = request.get_json()

        problem = data.get('problem')
        if not problem:
            return jsonify({"error": "问题描述不能为空"}), 400

        context = data.get('context', {})

        # 这里应该使用异步任务队列，简化处理
        engine = get_reasoning_engine()
        chain_id = engine.create_reasoning_chain(problem, ReasoningType.DEDUCTIVE, context)

        # 自动进行反思
        reflection_results = engine.reflect_on_reasoning(chain_id)

        return jsonify({
            "success": True,
            "chain_id": chain_id,
            "reflection_results": reflection_results,
            "message": "异步推理完成"
        })

    except Exception as e:
        logger.error(f"异步推理失败: {str(e)}")
        return jsonify({"error": f"异步推理失败: {str(e)}"}), 500

@reasoning_bp.route('/cleanup', methods=['POST'])
def cleanup_old_chains():
    """清理旧推理链"""
    try:
        data = request.get_json() or {}
        max_age_hours = data.get('max_age_hours', 24)

        engine = get_reasoning_engine()
        cleaned_count = engine.cleanup_old_chains(max_age_hours)

        return jsonify({
            "success": True,
            "cleaned_count": cleaned_count,
            "message": f"清理了 {cleaned_count} 个过期推理链"
        })

    except Exception as e:
        logger.error(f"清理推理链失败: {str(e)}")
        return jsonify({"error": f"清理推理链失败: {str(e)}"}), 500

@reasoning_bp.route('/types', methods=['GET'])
def get_reasoning_types():
    """获取推理类型列表"""
    try:
        types = [
            {
                "value": rt.value,
                "name": rt.name,
                "description": {
                    "deductive": "演绎推理 - 从一般到特殊",
                    "inductive": "归纳推理 - 从特殊到一般",
                    "abductive": "溯因推理 - 寻找最佳解释",
                    "analogical": "类比推理 - 基于相似性推理",
                    "causal": "因果推理 - 分析因果关系",
                    "counterfactual": "反事实推理 - 假设性分析"
                }.get(rt.value, "")
            }
            for rt in ReasoningType
        ]

        return jsonify({
            "success": True,
            "reasoning_types": types
        })

    except Exception as e:
        logger.error(f"获取推理类型失败: {str(e)}")
        return jsonify({"error": f"获取推理类型失败: {str(e)}"}), 500

@reasoning_bp.route('/step-types', methods=['GET'])
def get_step_types():
    """获取推理步骤类型列表"""
    try:
        step_types = [
            {
                "value": st.value,
                "name": st.name,
                "description": {
                    "observation": "观察 - 收集和记录信息",
                    "hypothesis": "假设 - 提出可能的解释",
                    "analysis": "分析 - 深入分析问题",
                    "inference": "推理 - 逻辑推导过程",
                    "validation": "验证 - 测试和确认",
                    "reflection": "反思 - 评估和改进",
                    "conclusion": "结论 - 最终结果"
                }.get(st.value, "")
            }
            for st in ReasoningStep
        ]

        return jsonify({
            "success": True,
            "step_types": step_types
        })

    except Exception as e:
        logger.error(f"获取步骤类型失败: {str(e)}")
        return jsonify({"error": f"获取步骤类型失败: {str(e)}"}), 500

@reasoning_bp.route('/stats', methods=['GET'])
def get_reasoning_stats():
    """获取推理统计信息"""
    try:
        engine = get_reasoning_engine()
        chains = engine.list_reasoning_chains()

        # 统计信息
        total_chains = len(chains)
        avg_confidence = sum(chain['confidence_score'] for chain in chains) / max(total_chains, 1)

        type_distribution = {}
        for chain in chains:
            rt = chain['reasoning_type']
            type_distribution[rt] = type_distribution.get(rt, 0) + 1

        recent_chains = [
            chain for chain in chains
            if datetime.now().timestamp() - chain['created_at'] < 86400  # 24小时内
        ]

        stats = {
            "total_chains": total_chains,
            "recent_chains": len(recent_chains),
            "average_confidence": round(avg_confidence, 3),
            "type_distribution": type_distribution,
            "total_nodes": sum(chain['node_count'] for chain in chains),
            "total_hypotheses": sum(chain['hypothesis_count'] for chain in chains)
        }

        return jsonify({
            "success": True,
            "stats": stats
        })

    except Exception as e:
        logger.error(f"获取推理统计失败: {str(e)}")
        return jsonify({"error": f"获取推理统计失败: {str(e)}"}), 500

# 错误处理
@reasoning_bp.errorhandler(404)
def not_found(error):
    return jsonify({"error": "API端点不存在"}), 404

@reasoning_bp.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "HTTP方法不允许"}), 405

@reasoning_bp.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "内部服务器错误"}), 500