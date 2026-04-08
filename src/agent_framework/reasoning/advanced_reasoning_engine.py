"""
高级推理引擎 - Agent Framework
支持多步推理、反思机制、假设验证等高级推理能力
"""

import agent_framework.core.fast_json as json
import time
import uuid
import atexit
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

class ReasoningType(Enum):
    """推理类型枚举"""
    DEDUCTIVE = "deductive"      # 演绎推理
    INDUCTIVE = "inductive"      # 归纳推理
    ABDUCTIVE = "abductive"      # 溯因推理
    ANALOGICAL = "analogical"    # 类比推理
    CAUSAL = "causal"           # 因果推理
    COUNTERFACTUAL = "counterfactual"  # 反事实推理

class ReasoningStep(Enum):
    """推理步骤类型"""
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    ANALYSIS = "analysis"
    INFERENCE = "inference"
    VALIDATION = "validation"
    REFLECTION = "reflection"
    CONCLUSION = "conclusion"

@dataclass
class ReasoningNode:
    """推理节点"""
    id: str
    step_type: ReasoningStep
    content: str
    confidence: float
    evidence: List[str]
    assumptions: List[str]
    timestamp: float
    parent_id: Optional[str] = None
    children_ids: List[str] = None

    def __post_init__(self):
        if self.children_ids is None:
            self.children_ids = []

@dataclass
class Hypothesis:
    """假设"""
    id: str
    content: str
    confidence: float
    supporting_evidence: List[str]
    contradicting_evidence: List[str]
    test_methods: List[str]
    status: str = "pending"  # pending, testing, confirmed, refuted

@dataclass
class ReasoningChain:
    """推理链"""
    id: str
    title: str
    reasoning_type: ReasoningType
    nodes: List[ReasoningNode]
    hypotheses: List[Hypothesis]
    conclusions: List[str]
    confidence_score: float
    created_at: float
    updated_at: float
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class ReflectionEngine:
    """反思引擎"""

    def __init__(self):
        self.reflection_patterns = [
            "是否考虑了所有相关因素？",
            "推理过程中是否存在逻辑漏洞？",
            "证据是否充分支持结论？",
            "是否存在其他可能的解释？",
            "假设是否合理？",
            "推理是否存在偏见？"
        ]

    def reflect_on_reasoning(self, chain: ReasoningChain) -> Dict[str, Any]:
        """对推理链进行反思"""
        reflection_results = {
            "overall_quality": self._assess_overall_quality(chain),
            "logical_consistency": self._check_logical_consistency(chain),
            "evidence_adequacy": self._assess_evidence_adequacy(chain),
            "alternative_explanations": self._generate_alternatives(chain),
            "improvement_suggestions": self._suggest_improvements(chain),
            "confidence_calibration": self._calibrate_confidence(chain)
        }

        return reflection_results

    def _assess_overall_quality(self, chain: ReasoningChain) -> float:
        """评估推理链整体质量"""
        factors = [
            len(chain.nodes) / 10,  # 推理步骤数量
            chain.confidence_score,  # 置信度
            len([h for h in chain.hypotheses if h.status == "confirmed"]) / max(len(chain.hypotheses), 1),  # 假设验证率
            len(chain.conclusions) / 3  # 结论数量
        ]

        return min(sum(factors) / len(factors), 1.0)

    def _check_logical_consistency(self, chain: ReasoningChain) -> Dict[str, Any]:
        """检查逻辑一致性"""
        inconsistencies = []

        # 检查推理步骤之间的逻辑连接
        for i in range(len(chain.nodes) - 1):
            current_node = chain.nodes[i]
            next_node = chain.nodes[i + 1]

            # 简单的逻辑检查（实际应用中需要更复杂的NLP分析）
            if current_node.confidence > 0.8 and next_node.confidence < 0.3:
                inconsistencies.append({
                    "type": "confidence_drop",
                    "nodes": [current_node.id, next_node.id],
                    "description": "推理置信度急剧下降"
                })

        return {
            "is_consistent": len(inconsistencies) == 0,
            "inconsistencies": inconsistencies,
            "consistency_score": max(0, 1 - len(inconsistencies) * 0.2)
        }

    def _assess_evidence_adequacy(self, chain: ReasoningChain) -> Dict[str, Any]:
        """评估证据充分性"""
        total_evidence = sum(len(node.evidence) for node in chain.nodes)
        avg_evidence_per_node = total_evidence / max(len(chain.nodes), 1)

        return {
            "total_evidence_count": total_evidence,
            "average_evidence_per_node": avg_evidence_per_node,
            "adequacy_score": min(avg_evidence_per_node / 3, 1.0),
            "weak_nodes": [node.id for node in chain.nodes if len(node.evidence) < 2]
        }

    def _generate_alternatives(self, chain: ReasoningChain) -> List[str]:
        """生成替代解释"""
        # 这里应该使用LLM生成替代解释
        alternatives = [
            "考虑其他可能的因果关系",
            "检查是否存在混淆变量",
            "评估样本偏差的影响",
            "考虑时间序列的影响"
        ]

        return alternatives[:2]  # 返回前2个建议

    def _suggest_improvements(self, chain: ReasoningChain) -> List[str]:
        """建议改进措施"""
        suggestions = []

        if chain.confidence_score < 0.7:
            suggestions.append("增加更多支持证据")

        if len(chain.hypotheses) < 2:
            suggestions.append("考虑多个竞争假设")

        if len([node for node in chain.nodes if node.step_type == ReasoningStep.VALIDATION]) == 0:
            suggestions.append("添加验证步骤")

        return suggestions

    def _calibrate_confidence(self, chain: ReasoningChain) -> Dict[str, float]:
        """校准置信度"""
        node_confidences = [node.confidence for node in chain.nodes]

        return {
            "original_confidence": chain.confidence_score,
            "calibrated_confidence": sum(node_confidences) / len(node_confidences) * 0.9,  # 保守校准
            "confidence_variance": sum((c - chain.confidence_score) ** 2 for c in node_confidences) / len(node_confidences)
        }

class HypothesisGenerator:
    """假设生成器"""

    def __init__(self):
        self.hypothesis_templates = [
            "如果{condition}，那么{outcome}",
            "由于{cause}，导致{effect}",
            "假设{assumption}成立，则{conclusion}",
            "基于{evidence}，可能{hypothesis}"
        ]

    def generate_hypotheses(self, context: str, evidence: List[str]) -> List[Hypothesis]:
        """生成假设"""
        hypotheses = []

        # 基于证据生成假设
        for i, template in enumerate(self.hypothesis_templates[:3]):
            hypothesis_content = f"假设{i+1}: 基于现有证据的推测"

            hypothesis = Hypothesis(
                id=str(uuid.uuid4()),
                content=hypothesis_content,
                confidence=0.6 + i * 0.1,
                supporting_evidence=evidence[:2],
                contradicting_evidence=[],
                test_methods=[f"验证方法{i+1}"]
            )

            hypotheses.append(hypothesis)

        return hypotheses

    def test_hypothesis(self, hypothesis: Hypothesis, new_evidence: List[str]) -> Hypothesis:
        """测试假设"""
        # 简化的假设测试逻辑
        supporting_count = len(hypothesis.supporting_evidence)
        contradicting_count = len(hypothesis.contradicting_evidence)

        # 更新假设状态
        if supporting_count > contradicting_count * 2:
            hypothesis.status = "confirmed"
            hypothesis.confidence = min(hypothesis.confidence + 0.2, 1.0)
        elif contradicting_count > supporting_count:
            hypothesis.status = "refuted"
            hypothesis.confidence = max(hypothesis.confidence - 0.3, 0.0)
        else:
            hypothesis.status = "testing"

        return hypothesis

class MultiStepReasoner:
    """多步推理器"""

    def __init__(self):
        self.max_steps = 10
        self.min_confidence = 0.3

    def reason_step_by_step(self, problem: str, context: Dict[str, Any]) -> ReasoningChain:
        """逐步推理"""
        chain_id = str(uuid.uuid4())
        nodes = []

        # 步骤1: 观察和问题分析
        observation_node = ReasoningNode(
            id=str(uuid.uuid4()),
            step_type=ReasoningStep.OBSERVATION,
            content=f"问题观察: {problem}",
            confidence=0.9,
            evidence=[problem],
            assumptions=[],
            timestamp=time.time()
        )
        nodes.append(observation_node)

        # 步骤2: 分析问题
        analysis_node = ReasoningNode(
            id=str(uuid.uuid4()),
            step_type=ReasoningStep.ANALYSIS,
            content="分析问题的关键要素和约束条件",
            confidence=0.8,
            evidence=list(context.get('evidence', [])),
            assumptions=list(context.get('assumptions', [])),
            timestamp=time.time(),
            parent_id=observation_node.id
        )
        nodes.append(analysis_node)

        # 步骤3: 推理过程
        current_confidence = 0.8
        for step in range(3, min(self.max_steps, 7)):
            if current_confidence < self.min_confidence:
                break

            inference_node = ReasoningNode(
                id=str(uuid.uuid4()),
                step_type=ReasoningStep.INFERENCE,
                content=f"推理步骤 {step-2}: 基于前面的分析进行逻辑推导",
                confidence=current_confidence,
                evidence=[f"推理证据{step-2}"],
                assumptions=[f"推理假设{step-2}"],
                timestamp=time.time(),
                parent_id=nodes[-1].id
            )
            nodes.append(inference_node)
            current_confidence *= 0.9  # 逐步降低置信度

        # 步骤4: 结论
        conclusion_node = ReasoningNode(
            id=str(uuid.uuid4()),
            step_type=ReasoningStep.CONCLUSION,
            content="基于多步推理得出的结论",
            confidence=current_confidence,
            evidence=["综合推理结果"],
            assumptions=[],
            timestamp=time.time(),
            parent_id=nodes[-1].id
        )
        nodes.append(conclusion_node)

        # 创建推理链
        chain = ReasoningChain(
            id=chain_id,
            title=f"多步推理: {problem[:50]}...",
            reasoning_type=ReasoningType.DEDUCTIVE,
            nodes=nodes,
            hypotheses=[],
            conclusions=["基于逐步推理的结论"],
            confidence_score=current_confidence,
            created_at=time.time(),
            updated_at=time.time()
        )

        return chain

class AdvancedReasoningEngine:
    """高级推理引擎主类"""

    def __init__(self):
        self.reflection_engine = ReflectionEngine()
        self.hypothesis_generator = HypothesisGenerator()
        self.multi_step_reasoner = MultiStepReasoner()
        self.reasoning_chains: Dict[str, ReasoningChain] = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._max_chains = 1000  # 防止无限增长

    def shutdown(self):
        """关闭引擎，释放资源"""
        self.executor.shutdown(wait=False)
        self.reasoning_chains.clear()

    def create_reasoning_chain(self,
                             problem: str,
                             reasoning_type: ReasoningType = ReasoningType.DEDUCTIVE,
                             context: Dict[str, Any] = None) -> str:
        """创建推理链"""
        if context is None:
            context = {}

        # 使用多步推理器创建基础推理链
        chain = self.multi_step_reasoner.reason_step_by_step(problem, context)
        chain.reasoning_type = reasoning_type

        # 生成假设
        evidence = context.get('evidence', [])
        hypotheses = self.hypothesis_generator.generate_hypotheses(problem, evidence)
        chain.hypotheses = hypotheses

        # 存储推理链
        self.reasoning_chains[chain.id] = chain

        # 自动清理过多的推理链
        if len(self.reasoning_chains) > self._max_chains:
            self.cleanup_old_chains(max_age_hours=1)

        return chain.id

    def add_reasoning_step(self,
                          chain_id: str,
                          step_type: ReasoningStep,
                          content: str,
                          evidence: List[str] = None,
                          assumptions: List[str] = None,
                          parent_id: str = None) -> str:
        """添加推理步骤"""
        if chain_id not in self.reasoning_chains:
            raise ValueError(f"推理链 {chain_id} 不存在")

        chain = self.reasoning_chains[chain_id]

        node = ReasoningNode(
            id=str(uuid.uuid4()),
            step_type=step_type,
            content=content,
            confidence=0.7,  # 默认置信度
            evidence=evidence or [],
            assumptions=assumptions or [],
            timestamp=time.time(),
            parent_id=parent_id
        )

        chain.nodes.append(node)
        chain.updated_at = time.time()

        # 更新父节点的子节点列表
        if parent_id:
            for existing_node in chain.nodes:
                if existing_node.id == parent_id:
                    existing_node.children_ids.append(node.id)
                    break

        return node.id

    def reflect_on_reasoning(self, chain_id: str) -> Dict[str, Any]:
        """对推理进行反思"""
        if chain_id not in self.reasoning_chains:
            raise ValueError(f"推理链 {chain_id} 不存在")

        chain = self.reasoning_chains[chain_id]
        reflection_results = self.reflection_engine.reflect_on_reasoning(chain)

        # 添加反思节点
        reflection_node = ReasoningNode(
            id=str(uuid.uuid4()),
            step_type=ReasoningStep.REFLECTION,
            content=f"反思结果: 整体质量 {reflection_results['overall_quality']:.2f}",
            confidence=reflection_results['overall_quality'],
            evidence=[json.dumps(reflection_results, ensure_ascii=False)],
            assumptions=[],
            timestamp=time.time()
        )

        chain.nodes.append(reflection_node)
        chain.updated_at = time.time()

        return reflection_results

    def test_hypotheses(self, chain_id: str, new_evidence: List[str]) -> Dict[str, Any]:
        """测试假设"""
        if chain_id not in self.reasoning_chains:
            raise ValueError(f"推理链 {chain_id} 不存在")

        chain = self.reasoning_chains[chain_id]
        results = {}

        for hypothesis in chain.hypotheses:
            updated_hypothesis = self.hypothesis_generator.test_hypothesis(hypothesis, new_evidence)
            results[hypothesis.id] = {
                "status": updated_hypothesis.status,
                "confidence": updated_hypothesis.confidence,
                "change": updated_hypothesis.confidence - hypothesis.confidence
            }

        # 添加验证节点
        validation_node = ReasoningNode(
            id=str(uuid.uuid4()),
            step_type=ReasoningStep.VALIDATION,
            content=f"假设验证完成，测试了 {len(chain.hypotheses)} 个假设",
            confidence=0.8,
            evidence=new_evidence,
            assumptions=[],
            timestamp=time.time()
        )

        chain.nodes.append(validation_node)
        chain.updated_at = time.time()

        return results

    def generate_alternative_explanations(self, chain_id: str, count: int = 3) -> List[str]:
        """生成替代解释"""
        if chain_id not in self.reasoning_chains:
            raise ValueError(f"推理链 {chain_id} 不存在")

        chain = self.reasoning_chains[chain_id]

        # 这里应该使用LLM生成更智能的替代解释
        alternatives = [
            f"替代解释 {i+1}: 从不同角度分析问题"
            for i in range(count)
        ]

        return alternatives

    def get_reasoning_chain(self, chain_id: str) -> Optional[ReasoningChain]:
        """获取推理链"""
        return self.reasoning_chains.get(chain_id)

    def list_reasoning_chains(self) -> List[Dict[str, Any]]:
        """列出所有推理链"""
        return [
            {
                "id": chain.id,
                "title": chain.title,
                "reasoning_type": chain.reasoning_type.value,
                "confidence_score": chain.confidence_score,
                "node_count": len(chain.nodes),
                "hypothesis_count": len(chain.hypotheses),
                "created_at": chain.created_at,
                "updated_at": chain.updated_at
            }
            for chain in self.reasoning_chains.values()
        ]

    def export_reasoning_chain(self, chain_id: str) -> Dict[str, Any]:
        """导出推理链"""
        if chain_id not in self.reasoning_chains:
            raise ValueError(f"推理链 {chain_id} 不存在")

        chain = self.reasoning_chains[chain_id]
        return asdict(chain)

    def import_reasoning_chain(self, chain_data: Dict[str, Any]) -> str:
        """导入推理链"""
        # 重构节点
        nodes = [ReasoningNode(**node_data) for node_data in chain_data['nodes']]

        # 重构假设
        hypotheses = [Hypothesis(**hyp_data) for hyp_data in chain_data['hypotheses']]

        # 重构推理链
        chain = ReasoningChain(
            id=chain_data['id'],
            title=chain_data['title'],
            reasoning_type=ReasoningType(chain_data['reasoning_type']),
            nodes=nodes,
            hypotheses=hypotheses,
            conclusions=chain_data['conclusions'],
            confidence_score=chain_data['confidence_score'],
            created_at=chain_data['created_at'],
            updated_at=chain_data['updated_at'],
            metadata=chain_data.get('metadata', {})
        )

        self.reasoning_chains[chain.id] = chain
        return chain.id

    async def async_reasoning(self, problem: str, context: Dict[str, Any] = None) -> str:
        """异步推理"""
        loop = asyncio.get_running_loop()

        # 在线程池中执行推理
        chain_id = await loop.run_in_executor(
            self.executor,
            self.create_reasoning_chain,
            problem,
            ReasoningType.DEDUCTIVE,
            context
        )

        # 异步反思
        await loop.run_in_executor(
            self.executor,
            self.reflect_on_reasoning,
            chain_id
        )

        return chain_id

    def cleanup_old_chains(self, max_age_hours: int = 24):
        """清理旧的推理链"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        chains_to_remove = [
            chain_id for chain_id, chain in self.reasoning_chains.items()
            if current_time - chain.created_at > max_age_seconds
        ]

        for chain_id in chains_to_remove:
            del self.reasoning_chains[chain_id]

        logger.info(f"清理了 {len(chains_to_remove)} 个过期推理链")

        return len(chains_to_remove)

# 全局推理引擎实例
reasoning_engine = AdvancedReasoningEngine()
atexit.register(reasoning_engine.shutdown)

def get_reasoning_engine() -> AdvancedReasoningEngine:
    """获取推理引擎实例"""
    return reasoning_engine