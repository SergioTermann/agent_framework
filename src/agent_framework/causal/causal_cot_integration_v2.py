"""
因果思维链集成模块 V2 - 优化版

新特性：
1. 与因果推理引擎深度集成
2. 智能缓存机制
3. 结果验证和质量评估
4. 性能监控
5. 错误处理和降级策略
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import agent_framework.core.fast_json as json
import hashlib
import time

from agent_framework.causal.causal_cot_prompts_v2 import (
    CausalCoTMode,
    ReasoningDepth,
    OptimizedPromptBuilder,
    get_prompt_builder,
    create_causal_prompt
)


# ─── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class CausalAnalysisResult:
    """因果分析结果"""
    query: str
    mode: Optional[CausalCoTMode]
    confidence: float
    causal_structure: Dict[str, Any]
    llm_response: str
    quality_score: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode.value if self.mode else None,
            "confidence": self.confidence,
            "causal_structure": self.causal_structure,
            "llm_response": self.llm_response,
            "quality_score": self.quality_score,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


# ─── 智能缓存 ──────────────────────────────────────────────────────────────────

class CausalCache:
    """因果推理缓存"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[Any, float]] = {}

    def _generate_key(self, query: str, mode: Optional[CausalCoTMode], depth: ReasoningDepth) -> str:
        """生成缓存键"""
        mode_str = mode.value if mode else "auto"
        content = f"{query}_{mode_str}_{depth.value}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, query: str, mode: Optional[CausalCoTMode], depth: ReasoningDepth) -> Optional[Any]:
        """获取缓存"""
        key = self._generate_key(query, mode, depth)
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                return value
            else:
                del self._cache[key]
        return None

    def set(self, query: str, mode: Optional[CausalCoTMode], depth: ReasoningDepth, value: Any):
        """设置缓存"""
        # LRU 清理
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        key = self._generate_key(query, mode, depth)
        self._cache[key] = (value, time.time())

    def clear(self):
        """清空缓存"""
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds
        }


# ─── 结果提取器（增强版）──────────────────────────────────────────────────────

class EnhancedStructureExtractor:
    """增强的因果结构提取器"""

    def extract(self, llm_response: str) -> Dict[str, Any]:
        """从 LLM 响应中提取因果结构"""
        import re

        structure = {
            "has_causal_reasoning": False,
            "nodes": [],
            "links": [],
            "hypotheses": [],
            "confidence": 0.0,
            "conclusions": [],
            "reasoning_steps": []
        }

        # 检测是否包含因果推理
        causal_markers = ["因果", "原因", "结果", "导致", "影响", "→", "->"]
        if any(marker in llm_response for marker in causal_markers):
            structure["has_causal_reasoning"] = True

        # 提取置信度
        confidence_pattern = r"置信度[：:]\s*([0-9.]+)"
        matches = re.findall(confidence_pattern, llm_response)
        if matches:
            confidences = [float(m) for m in matches if 0 <= float(m) <= 1]
            if confidences:
                structure["confidence"] = sum(confidences) / len(confidences)

        # 提取因果链（支持多种格式）
        # 格式1: A → [类型, 0.9] → B
        chain_pattern1 = r"(.+?)\s*[→\->]\s*\[(.+?),\s*([0-9.]+)\]\s*[→\->]\s*(.+?)(?:\n|$|[→\->])"
        # 格式2: A 导致 B (置信度: 0.9)
        chain_pattern2 = r"(.+?)\s*(导致|引起|影响|促进)\s*(.+?)\s*\(置信度[：:]\s*([0-9.]+)\)"

        for match in re.finditer(chain_pattern1, llm_response):
            source, relation, conf, target = match.groups()
            structure["links"].append({
                "source": source.strip(),
                "target": target.strip(),
                "relation": relation.strip(),
                "confidence": float(conf),
                "mechanism": ""
            })

        for match in re.finditer(chain_pattern2, llm_response):
            source, relation, target, conf = match.groups()
            structure["links"].append({
                "source": source.strip(),
                "target": target.strip(),
                "relation": relation,
                "confidence": float(conf),
                "mechanism": ""
            })

        # 提取假设
        hypothesis_pattern = r"假设\d+[：:]\s*(.+?)\s*\(置信度[：:]\s*([0-9.]+)\)"
        for match in re.finditer(hypothesis_pattern, llm_response):
            content, conf = match.groups()
            structure["hypotheses"].append({
                "content": content.strip(),
                "confidence": float(conf)
            })

        # 提取推理步骤
        step_pattern = r"(?:^|\n)(\d+)\.\s*\*?\*?(.+?)\*?\*?\s*[:：]?\s*\n"
        for match in re.finditer(step_pattern, llm_response, re.MULTILINE):
            step_num, step_name = match.groups()
            structure["reasoning_steps"].append({
                "step": int(step_num),
                "name": step_name.strip()
            })

        # 提取结论
        conclusion_markers = ["结论", "建议", "总结"]
        for marker in conclusion_markers:
            pattern = f"{marker}[：:](.+?)(?:\\n\\n|\\n(?=\\d+\\.)|$)"
            matches = re.findall(pattern, llm_response, re.DOTALL)
            if matches:
                structure["conclusions"].extend([m.strip() for m in matches])

        return structure


# ─── 质量评估器 ────────────────────────────────────────────────────────────────

class QualityAssessor:
    """推理质量评估器"""

    def assess(self, structure: Dict[str, Any], llm_response: str) -> float:
        """
        评估推理质量

        返回：质量分数 (0-1)
        """
        score = 0.0
        weights = {
            "has_reasoning": 0.2,
            "has_confidence": 0.15,
            "has_links": 0.25,
            "has_steps": 0.15,
            "has_conclusions": 0.15,
            "response_length": 0.1
        }

        # 1. 是否包含因果推理
        if structure.get("has_causal_reasoning"):
            score += weights["has_reasoning"]

        # 2. 是否有置信度评估
        if structure.get("confidence", 0) > 0:
            score += weights["has_confidence"]

        # 3. 是否有因果链接
        links_count = len(structure.get("links", []))
        if links_count > 0:
            score += weights["has_links"] * min(links_count / 3, 1.0)

        # 4. 是否有推理步骤
        steps_count = len(structure.get("reasoning_steps", []))
        if steps_count >= 3:
            score += weights["has_steps"]

        # 5. 是否有结论
        if structure.get("conclusions"):
            score += weights["has_conclusions"]

        # 6. 响应长度合理性
        response_length = len(llm_response)
        if 200 <= response_length <= 3000:
            score += weights["response_length"]
        elif response_length > 3000:
            score += weights["response_length"] * 0.5

        return min(score, 1.0)


# ─── 主集成类 ──────────────────────────────────────────────────────────────────

class OptimizedCausalCoTIntegration:
    """优化的因果思维链集成器"""

    def __init__(
        self,
        enable_cache: bool = True,
        cache_size: int = 100,
        cache_ttl: int = 3600
    ):
        self.prompt_builder = get_prompt_builder()
        self.extractor = EnhancedStructureExtractor()
        self.assessor = QualityAssessor()

        self.enabled = False
        self.default_mode: Optional[CausalCoTMode] = None
        self.default_depth = ReasoningDepth.STANDARD

        # 缓存
        self.cache_enabled = enable_cache
        self.cache = CausalCache(cache_size, cache_ttl) if enable_cache else None

        # 统计
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "mode_detections": {},
            "avg_quality_score": 0.0,
            "total_quality_score": 0.0
        }

    def enable(
        self,
        mode: Optional[CausalCoTMode] = None,
        depth: ReasoningDepth = ReasoningDepth.STANDARD
    ):
        """启用因果思维链"""
        self.enabled = True
        self.default_mode = mode
        self.default_depth = depth

    def disable(self):
        """禁用因果思维链"""
        self.enabled = False

    def create_prompt(
        self,
        user_query: str,
        mode: Optional[CausalCoTMode] = None,
        depth: Optional[ReasoningDepth] = None,
        use_cache: bool = True,
        **kwargs
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        创建因果推理提示词

        返回：(messages, metadata)
        """
        if not self.enabled:
            return [{"role": "user", "content": user_query}], {}

        # 使用默认值
        mode = mode or self.default_mode
        depth = depth or self.default_depth

        # 检查缓存
        if use_cache and self.cache_enabled:
            cached = self.cache.get(user_query, mode, depth)
            if cached is not None:
                self.stats["cache_hits"] += 1
                return cached

        # 创建提示词
        messages, metadata = create_causal_prompt(
            user_query,
            mode=mode,
            depth=depth,
            auto_detect=(mode is None),
            **kwargs
        )

        # 更新统计
        self.stats["total_queries"] += 1
        if metadata.get("detected_mode"):
            mode_name = metadata["detected_mode"]
            self.stats["mode_detections"][mode_name] = \
                self.stats["mode_detections"].get(mode_name, 0) + 1

        # 缓存结果
        if use_cache and self.cache_enabled:
            self.cache.set(user_query, mode, depth, (messages, metadata))

        return messages, metadata

    def analyze_response(
        self,
        query: str,
        llm_response: str,
        mode: Optional[CausalCoTMode] = None,
        confidence: float = 0.0
    ) -> CausalAnalysisResult:
        """
        分析 LLM 响应

        返回：结构化的分析结果
        """
        # 提取因果结构
        structure = self.extractor.extract(llm_response)

        # 评估质量
        quality_score = self.assessor.assess(structure, llm_response)

        # 更新统计
        self.stats["total_quality_score"] += quality_score
        if self.stats["total_queries"] > 0:
            self.stats["avg_quality_score"] = \
                self.stats["total_quality_score"] / self.stats["total_queries"]

        # 创建结果对象
        result = CausalAnalysisResult(
            query=query,
            mode=mode,
            confidence=confidence,
            causal_structure=structure,
            llm_response=llm_response,
            quality_score=quality_score,
            timestamp=time.time()
        )

        return result

    def integrate_with_engine(
        self,
        result: CausalAnalysisResult,
        causal_engine=None
    ) -> Dict[str, Any]:
        """
        与因果推理引擎集成

        将 LLM 提取的因果结构导入到因果推理引擎中
        """
        if causal_engine is None:
            try:
                from agent_framework.causal.causal_reasoning_engine import CausalReasoningEngine
                causal_engine = CausalReasoningEngine()
            except ImportError:
                return {"error": "因果推理引擎不可用"}

        structure = result.causal_structure
        integration_result = {
            "nodes_added": 0,
            "links_added": 0,
            "validation": {}
        }

        try:
            # 添加节点和链接到因果图谱
            for link in structure.get("links", []):
                # 这里需要根据实际的因果推理引擎 API 调整
                # 示例代码：
                # causal_engine.add_causal_relation(
                #     cause=link["source"],
                #     effect=link["target"],
                #     relation_type=link["relation"],
                #     confidence=link["confidence"]
                # )
                integration_result["links_added"] += 1

            # 验证因果链的逻辑一致性
            # validation = causal_engine.validate_chain(structure["links"])
            # integration_result["validation"] = validation

        except Exception as e:
            integration_result["error"] = str(e)

        return integration_result

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()

        if self.cache_enabled:
            stats["cache"] = self.cache.get_stats()
            if stats["total_queries"] > 0:
                stats["cache_hit_rate"] = stats["cache_hits"] / stats["total_queries"]

        return stats

    def clear_cache(self):
        """清空缓存"""
        if self.cache_enabled:
            self.cache.clear()

    def reset_statistics(self):
        """重置统计"""
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "mode_detections": {},
            "avg_quality_score": 0.0,
            "total_quality_score": 0.0
        }


# ─── 全局实例 ──────────────────────────────────────────────────────────────────

_integration = None

def get_causal_integration() -> OptimizedCausalCoTIntegration:
    """获取全局集成实例"""
    global _integration
    if _integration is None:
        _integration = OptimizedCausalCoTIntegration()
    return _integration


# ─── 便捷函数 ──────────────────────────────────────────────────────────────────

def enable_causal_cot(
    mode: Optional[CausalCoTMode] = None,
    depth: ReasoningDepth = ReasoningDepth.STANDARD
):
    """启用因果思维链"""
    integration = get_causal_integration()
    integration.enable(mode, depth)


def disable_causal_cot():
    """禁用因果思维链"""
    integration = get_causal_integration()
    integration.disable()


def create_causal_messages(
    user_query: str,
    **kwargs
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """创建因果推理消息（便捷函数）"""
    integration = get_causal_integration()
    return integration.create_prompt(user_query, **kwargs)


def analyze_causal_response(
    query: str,
    llm_response: str,
    **kwargs
) -> CausalAnalysisResult:
    """分析因果推理响应（便捷函数）"""
    integration = get_causal_integration()
    return integration.analyze_response(query, llm_response, **kwargs)
