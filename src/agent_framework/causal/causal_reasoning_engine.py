#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因果推理引擎 —— LLM 驱动的完整因果分析系统

功能：
  1. 因果链分析 —— 分析原因到结果的完整因果链路
  2. 反事实推理 —— "如果 X 不同，结果会怎样？"
  3. 效果预测   —— 给定原因，预测可能的多种结果
  4. 根因分析   —— 从观察到的现象追溯根本原因
  5. 干预分析   —— 评估干预措施的因果影响
  6. 图谱管理   —— 因果节点/链接的 CRUD 与统计
"""

from __future__ import annotations

import agent_framework.core.fast_json as json
import uuid
import time
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from agent_framework.core.config import get_config

try:
    from agent_framework.causal.causal_graph_ops import CausalGraphOps, RUST_CAUSAL_AVAILABLE as _rust_causal_available
except Exception:
    CausalGraphOps = None
    _rust_causal_available = False

_CAUSAL_GRAPH_BACKEND = "rust" if _rust_causal_available and CausalGraphOps is not None else "python"


# ─── 枚举类型 ────────────────────────────────────────────────────────────────

class CausalRelationType(Enum):
    """因果关系类型"""
    DIRECT = "直接导致"
    INDIRECT = "间接影响"
    NECESSARY = "必要条件"
    SUFFICIENT = "充分条件"
    CONTRIBUTORY = "促进因素"
    PREVENTIVE = "抑制因素"
    CORRELATIONAL = "相关关系"


class ConfidenceLevel(Enum):
    """置信度等级"""
    VERY_HIGH = (0.9, 1.0, "非常高")
    HIGH = (0.7, 0.9, "高")
    MEDIUM = (0.5, 0.7, "中等")
    LOW = (0.3, 0.5, "低")
    VERY_LOW = (0.0, 0.3, "非常低")

    @classmethod
    def from_value(cls, value: float):
        for level in cls:
            min_val, max_val, _ = level.value
            if min_val <= value <= max_val:
                return level
        return cls.VERY_LOW


class AnalysisMode(Enum):
    """分析模式"""
    CAUSAL_CHAIN = "causal_chain"
    COUNTERFACTUAL = "counterfactual"
    PREDICTION = "prediction"
    ROOT_CAUSE = "root_cause"
    INTERVENTION = "intervention"


# ─── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class CausalNode:
    """因果节点"""
    id: str
    content: str
    node_type: str  # "cause", "effect", "intermediate", "intervention"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "type": self.node_type,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class CausalLink:
    """因果关系链接"""
    source_id: str
    target_id: str
    relation_type: CausalRelationType
    confidence: float
    evidence: List[str] = field(default_factory=list)
    mechanism: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "relation": self.relation_type.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "mechanism": self.mechanism,
            "metadata": self.metadata,
        }


@dataclass
class CausalChain:
    """因果链"""
    nodes: List[CausalNode]
    links: List[CausalLink]
    chain_confidence: float = 0.0

    def __post_init__(self):
        if self.links:
            # 链式置信度 = 各环节置信度的乘积（联合概率）
            self.chain_confidence = math.prod(l.confidence for l in self.links)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "links": [l.to_dict() for l in self.links],
            "chain_confidence": self.chain_confidence,
        }


# ─── 因果图谱 ────────────────────────────────────────────────────────────────

class CausalGraph:
    """????"""

    def __init__(self):
        self.nodes: Dict[str, CausalNode] = {}
        self.adjacency: Dict[str, List[CausalLink]] = defaultdict(list)
        self.reverse_adjacency: Dict[str, List[CausalLink]] = defaultdict(list)
        self.search_backend = _CAUSAL_GRAPH_BACKEND
        self._path_cache: Dict[Tuple[str, str, int], List[CausalChain]] = {}  # ????
        self._backend_cache_dirty = True
        self._edge_records: List[Tuple[int, str, str]] = []
        self._link_by_edge_id: Dict[int, CausalLink] = {}

    def _invalidate_caches(self):
        self._path_cache.clear()
        self._backend_cache_dirty = True

    def _ensure_backend_cache(self):
        if self.search_backend != "rust":
            return
        if not self._backend_cache_dirty:
            return

        edge_records: List[Tuple[int, str, str]] = []
        link_by_edge_id: Dict[int, CausalLink] = {}
        edge_id = 0

        for source_id, links in self.adjacency.items():
            for link in links:
                edge_records.append((edge_id, source_id, link.target_id))
                link_by_edge_id[edge_id] = link
                edge_id += 1

        self._edge_records = edge_records
        self._link_by_edge_id = link_by_edge_id
        self._backend_cache_dirty = False

    def _chain_from_edge_ids(self, edge_ids: List[int]) -> Optional[CausalChain]:
        if not edge_ids:
            return None

        first_link = self._link_by_edge_id.get(edge_ids[0])
        if not first_link:
            return None

        first_node = self.get_node(first_link.source_id)
        if not first_node:
            return None

        nodes = [first_node]
        links: List[CausalLink] = []

        for edge_id in edge_ids:
            link = self._link_by_edge_id.get(edge_id)
            if not link:
                return None
            target_node = self.get_node(link.target_id)
            if not target_node:
                return None
            links.append(link)
            nodes.append(target_node)

        return CausalChain(nodes=nodes, links=links)

    def add_node(self, node: CausalNode):
        self.nodes[node.id] = node
        self._invalidate_caches()  # ??????

    def add_link(self, link: CausalLink):
        self.adjacency[link.source_id].append(link)
        self.reverse_adjacency[link.target_id].append(link)
        self._invalidate_caches()  # ??????

    def get_node(self, node_id: str) -> Optional[CausalNode]:
        return self.nodes.get(node_id)

    def get_children(self, node_id: str) -> List[Tuple[CausalNode, CausalLink]]:
        children = []
        for link in self.adjacency.get(node_id, []):
            child = self.nodes.get(link.target_id)
            if child:
                children.append((child, link))
        return children

    def get_parents(self, node_id: str) -> List[Tuple[CausalNode, CausalLink]]:
        parents = []
        for link in self.reverse_adjacency.get(node_id, []):
            parent = self.nodes.get(link.source_id)
            if parent:
                parents.append((parent, link))
        return parents

    def find_paths(self, start_id: str, end_id: str, max_depth: int = 5) -> List[CausalChain]:
        """??????????????????"""
        cache_key = (start_id, end_id, max_depth)
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        if start_id not in self.nodes or end_id not in self.nodes:
            return []

        if start_id == end_id:
            start_node = self.get_node(start_id)
            paths = [CausalChain(nodes=[start_node], links=[])] if start_node else []
            self._path_cache[cache_key] = paths
            return paths

        if self.search_backend == "rust" and CausalGraphOps is not None:
            self._ensure_backend_cache()
            try:
                edge_paths = CausalGraphOps.find_paths(self._edge_records, start_id, end_id, max_depth)
                paths = []
                for edge_ids in edge_paths:
                    chain = self._chain_from_edge_ids(edge_ids)
                    if chain is not None:
                        paths.append(chain)
                self._path_cache[cache_key] = paths
                return paths
            except Exception:
                pass

        paths = []
        visited = set()

        def dfs(current_id, path_nodes, path_links, depth):
            if depth > max_depth:
                return
            if current_id == end_id:
                paths.append(CausalChain(nodes=path_nodes.copy(), links=path_links.copy()))
                return
            if current_id in visited:
                return
            visited.add(current_id)
            for child_node, link in self.get_children(current_id):
                path_nodes.append(child_node)
                path_links.append(link)
                dfs(child_node.id, path_nodes, path_links, depth + 1)
                path_nodes.pop()
                path_links.pop()
            visited.remove(current_id)

        start_node = self.get_node(start_id)
        if start_node:
            dfs(start_id, [start_node], [], 0)

        self._path_cache[cache_key] = paths
        return paths

    def shortest_path(self, start_id: str, end_id: str) -> Optional[CausalChain]:
        if start_id not in self.nodes or end_id not in self.nodes:
            return None

        if start_id == end_id:
            return CausalChain(nodes=[self.nodes[start_id]], links=[])

        if self.search_backend == "rust" and CausalGraphOps is not None:
            self._ensure_backend_cache()
            try:
                edge_ids = CausalGraphOps.shortest_path(self._edge_records, start_id, end_id)
                if edge_ids:
                    return self._chain_from_edge_ids(edge_ids)
            except Exception:
                pass

        from collections import deque

        queue = deque([(start_id, [self.nodes[start_id]], [])])
        visited = {start_id}

        while queue:
            current_id, path_nodes, path_links = queue.popleft()

            if current_id == end_id:
                return CausalChain(nodes=path_nodes, links=path_links)

            for child, link in self.get_children(current_id):
                if child.id not in visited:
                    visited.add(child.id)
                    queue.append((child.id, path_nodes + [child], path_links + [link]))

        return None

    def detect_cycles(self) -> List[List[str]]:
        if self.search_backend == "rust" and CausalGraphOps is not None:
            self._ensure_backend_cache()
            try:
                return CausalGraphOps.detect_cycles(self._edge_records)
            except Exception:
                pass

        cycles = []
        visited = set()
        rec_stack = set()
        path = []

        def dfs_cycle(node_id):
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for child, _ in self.get_children(node_id):
                if child.id not in visited:
                    dfs_cycle(child.id)
                elif child.id in rec_stack:
                    cycle_start = path.index(child.id)
                    cycles.append(path[cycle_start:] + [child.id])

            path.pop()
            rec_stack.remove(node_id)

        for node_id in self.nodes.keys():
            if node_id not in visited:
                dfs_cycle(node_id)

        return cycles

    def to_tree_dict(self, root_id: str, max_depth: int = 4) -> Dict[str, Any]:
        root = self.get_node(root_id)
        if not root:
            return {}

        def build(node_id, depth):
            if depth >= max_depth:
                return None
            node = self.get_node(node_id)
            if not node:
                return None
            children = []
            for child, link in self.get_children(node_id):
                child_tree = build(child.id, depth + 1)
                if child_tree:
                    child_tree["relation"] = link.relation_type.value
                    child_tree["mechanism"] = link.mechanism
                    child_tree["evidence"] = link.evidence
                    children.append(child_tree)
            return {
                "id": node.id,
                "content": node.content,
                "type": node.node_type,
                "confidence": node.confidence,
                "children": children,
            }

        return build(root_id, 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "links": [l.to_dict() for links in self.adjacency.values() for l in links],
        }

    def get_isolated_nodes(self) -> List[CausalNode]:
        """获取孤立节点（没有任何连接的节点）"""
        isolated = []
        for node_id, node in self.nodes.items():
            has_outgoing = len(self.adjacency.get(node_id, [])) > 0
            has_incoming = len(self.reverse_adjacency.get(node_id, [])) > 0
            if not has_outgoing and not has_incoming:
                isolated.append(node)
        return isolated

    def get_root_nodes(self) -> List[CausalNode]:
        """获取根节点（只有出边没有入边的节点）"""
        roots = []
        for node_id, node in self.nodes.items():
            has_outgoing = len(self.adjacency.get(node_id, [])) > 0
            has_incoming = len(self.reverse_adjacency.get(node_id, [])) > 0
            if has_outgoing and not has_incoming:
                roots.append(node)
        return roots

    def get_leaf_nodes(self) -> List[CausalNode]:
        """获取叶子节点（只有入边没有出边的节点）"""
        leaves = []
        for node_id, node in self.nodes.items():
            has_outgoing = len(self.adjacency.get(node_id, [])) > 0
            has_incoming = len(self.reverse_adjacency.get(node_id, [])) > 0
            if not has_outgoing and has_incoming:
                leaves.append(node)
        return leaves


# ─── LLM 调用辅助 ────────────────────────────────────────────────────────────

def _call_llm(prompt: str, system: str = "", temperature: float = 0.7, max_tokens: int = 4096) -> str:
    """调用 LLM 获取结构化 JSON 响应"""
    import urllib.request
    import urllib.error
    import logging

    log = logging.getLogger(__name__)
    cfg = get_config()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": cfg.llm.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }, ensure_ascii=False).encode("utf-8")

    url = f"{cfg.llm.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.llm.api_key}",
    }

    last_err: Exception | None = None
    backoff_delays = [0.5, 1, 2]  # 优化退避时间
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=cfg.llm.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError("LLM 返回空内容")
            return content
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last_err = e
            log.warning("LLM 调用失败 (attempt %d/3): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(backoff_delays[attempt])

    raise RuntimeError(f"LLM 调用 3 次均失败: {last_err}") from last_err


def _parse_json_response(text: str) -> Any:
    """从 LLM 响应中提取 JSON"""
    text = text.strip()
    # 尝试提取 ```json ... ``` 块
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    # 使用 raw_decode 从第一个 JSON 对象/数组处开始解析
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            try:
                obj, _ = decoder.raw_decode(text, i)
                return obj
            except json.JSONDecodeError:
                continue

    return json.loads(text)


# ─── 系统提示词 ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT_CAUSAL = """你是因果推理专家。分析事物间的因果关系，构建严谨的因果链。

要求：
1. 基于逻辑和常识推理
2. 区分因果关系类型（直接导致、间接影响、必要条件、充分条件、促进因素、抑制因素、相关关系）
3. 为每个关系给出置信度（0.0-1.0）
4. 提供证据和机制说明
5. 保持客观，避免过度推断

返回格式：JSON"""


# ─── 因果推理引擎 ─────────────────────────────────────────────────────────────

class CausalReasoningEngine:
    """LLM 驱动的因果推理引擎"""

    MAX_NODES = 2000
    MAX_HISTORY = 100
    CACHE_SIZE = 100  # 增加缓存大小

    def __init__(self):
        self.graph = CausalGraph()
        self.reasoning_history: List[Dict[str, Any]] = []
        self._llm_cache: Dict[str, str] = {}  # LLM 响应缓存
        self._cache_timestamps: Dict[str, float] = {}  # 缓存时间戳
        self._cache_hits = 0
        self._cache_misses = 0
        self.CACHE_TTL = 3600  # 缓存有效期1小时

    def _trim_if_needed(self):
        """当图谱过大时自动清理最早的节点"""
        if len(self.graph.nodes) > self.MAX_NODES:
            # 保留最近一半的节点
            all_ids = list(self.graph.nodes.keys())
            to_remove = all_ids[:len(all_ids) // 2]
            for nid in to_remove:
                self.graph.nodes.pop(nid, None)
                self.graph.adjacency.pop(nid, None)
                self.graph.reverse_adjacency.pop(nid, None)
            self.graph._invalidate_caches()

        if len(self.reasoning_history) > self.MAX_HISTORY:
            self.reasoning_history = self.reasoning_history[-self.MAX_HISTORY:]

        # 清理过期缓存
        current_time = time.time()
        expired_keys = [k for k, t in self._cache_timestamps.items()
                       if current_time - t > self.CACHE_TTL]
        for key in expired_keys:
            self._llm_cache.pop(key, None)
            self._cache_timestamps.pop(key, None)

        # 如果缓存仍然过大，清理最旧的
        if len(self._llm_cache) > self.CACHE_SIZE:
            sorted_keys = sorted(self._cache_timestamps.items(), key=lambda x: x[1])
            to_remove = len(self._llm_cache) - self.CACHE_SIZE
            for key, _ in sorted_keys[:to_remove]:
                self._llm_cache.pop(key, None)
                self._cache_timestamps.pop(key, None)

    def _get_cache_key(self, mode: str, **kwargs) -> str:
        """生成缓存键"""
        import hashlib
        key_str = f"{mode}:{json.dumps(kwargs, sort_keys=True, ensure_ascii=False)}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _call_llm_cached(self, prompt: str, system: str, cache_key: str) -> str:
        """带缓存的 LLM 调用"""
        # 检查缓存是否存在且未过期
        if cache_key in self._llm_cache:
            cache_time = self._cache_timestamps.get(cache_key, 0)
            if time.time() - cache_time < self.CACHE_TTL:
                self._cache_hits += 1
                return self._llm_cache[cache_key]
            else:
                # 缓存过期，清理
                self._llm_cache.pop(cache_key, None)
                self._cache_timestamps.pop(cache_key, None)

        self._cache_misses += 1
        result = _call_llm(prompt, system)
        self._llm_cache[cache_key] = result
        self._cache_timestamps[cache_key] = time.time()
        return result

    # ── 节点 / 链接管理 ──

    def create_node(self, content: str, node_type: str = "effect",
                    confidence: float = 1.0, metadata: Optional[Dict] = None) -> CausalNode:
        node = CausalNode(
            id=str(uuid.uuid4())[:8],
            content=content,
            node_type=node_type,
            confidence=confidence,
            metadata=metadata or {},
        )
        self.graph.add_node(node)
        return node

    def create_link(self, source_id: str, target_id: str,
                    relation_type: CausalRelationType = CausalRelationType.DIRECT,
                    confidence: float = 0.8, evidence: Optional[List[str]] = None,
                    mechanism: str = "") -> CausalLink:
        link = CausalLink(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            confidence=confidence,
            evidence=evidence or [],
            mechanism=mechanism,
        )
        self.graph.add_link(link)
        return link

    # ── 1. 因果链分析（LLM驱动）──

    def analyze_causal_chain(self, cause: str, effect: str,
                             context: Optional[str] = None, use_cache: bool = True) -> Dict[str, Any]:
        """使用 LLM 分析完整的因果链"""
        ctx_part = f"\n背景：{context}" if context else ""

        prompt = f"""分析因果关系，构建多层级推理树。

起始原因：{cause}
最终结果：{effect}{ctx_part}

返回JSON：
{{
  "summary": "因果链总结",
  "chain": [
    {{
      "content": "节点描述",
      "type": "cause/intermediate/effect",
      "confidence": 0.0-1.0,
      "relation_to_next": "直接导致/间接影响/必要条件/充分条件/促进因素/抑制因素/相关关系",
      "mechanism": "因果机制",
      "evidence": ["证据1", "证据2"]
    }}
  ],
  "alternative_paths": [
    {{"description": "替代路径", "likelihood": 0.0-1.0}}
  ],
  "assumptions": ["假设1"],
  "limitations": ["局限性1"]
}}

要求：
- chain包含4-6个节点
- 每个节点有机制和证据
- 至少2条替代路径"""

        try:
            if use_cache:
                cache_key = self._get_cache_key("causal_chain", cause=cause, effect=effect, context=context)
                raw = self._call_llm_cached(prompt, SYSTEM_PROMPT_CAUSAL, cache_key)
            else:
                raw = _call_llm(prompt, SYSTEM_PROMPT_CAUSAL)
            parsed = _parse_json_response(raw)
        except Exception as e:
            # LLM 调用失败时使用回退逻辑
            parsed = self._fallback_chain(cause, effect, context)

        # 构建图谱
        chain_data = parsed.get("chain", [])
        if not chain_data:
            chain_data = [
                {"content": cause, "type": "cause", "confidence": 1.0,
                 "relation_to_next": "直接导致", "mechanism": "", "evidence": []},
                {"content": effect, "type": "effect", "confidence": 0.8,
                 "relation_to_next": "", "mechanism": "", "evidence": []},
            ]

        # 创建节点和链接
        nodes = []
        for item in chain_data:
            node = self.create_node(
                content=item.get("content", ""),
                node_type=item.get("type", "intermediate"),
                confidence=item.get("confidence", 0.7),
            )
            nodes.append(node)

        # 连接节点
        relation_map = {v.value: v for v in CausalRelationType}
        for i in range(len(nodes) - 1):
            rel_str = chain_data[i].get("relation_to_next", "直接导致")
            rel_type = relation_map.get(rel_str, CausalRelationType.DIRECT)
            self.create_link(
                nodes[i].id, nodes[i + 1].id,
                relation_type=rel_type,
                confidence=chain_data[i].get("confidence", 0.7),
                evidence=chain_data[i].get("evidence", []),
                mechanism=chain_data[i].get("mechanism", ""),
            )

        tree = self.graph.to_tree_dict(nodes[0].id, max_depth=8)

        result = {
            "tree": tree,
            "summary": parsed.get("summary", ""),
            "alternative_paths": parsed.get("alternative_paths", []),
            "assumptions": parsed.get("assumptions", []),
            "limitations": parsed.get("limitations", []),
            "node_count": len(nodes),
            "chain_confidence": sum(n.confidence for n in nodes) / len(nodes) if nodes else 0,
        }

        self.reasoning_history.append({
            "type": "causal_chain",
            "cause": cause,
            "effect": effect,
            "context": context,
            "timestamp": time.time(),
        })
        self._trim_if_needed()

        return result

    def _fallback_chain(self, cause: str, effect: str, context: Optional[str]) -> Dict:
        """LLM 调用失败时的回退逻辑"""
        return {
            "summary": f"从「{cause}」到「{effect}」的因果分析（离线模式）",
            "chain": [
                {"content": cause, "type": "cause", "confidence": 1.0,
                 "relation_to_next": "直接导致", "mechanism": "初始触发因素",
                 "evidence": ["作为起始条件"]},
                {"content": f"{cause}引发的直接反应", "type": "intermediate", "confidence": 0.85,
                 "relation_to_next": "促进因素", "mechanism": "连锁效应",
                 "evidence": ["常见的因果传递模式"]},
                {"content": f"向{effect}方向的演变", "type": "intermediate", "confidence": 0.75,
                 "relation_to_next": "间接影响", "mechanism": "逐步累积",
                 "evidence": ["趋势性变化"]},
                {"content": effect, "type": "effect", "confidence": 0.7,
                 "relation_to_next": "", "mechanism": "最终结果呈现",
                 "evidence": ["可观测的结果"]},
            ],
            "alternative_paths": [
                {"description": "可能存在其他中间传导路径", "likelihood": 0.5}
            ],
            "assumptions": ["假设因果关系是线性传递的", "假设没有外部干预因素"],
            "limitations": ["未使用 LLM 进行深度分析，结果为简化推理"],
        }

    # ── 2. 反事实推理 ──

    def counterfactual_reasoning(self, original_cause: str,
                                  alternative_cause: str,
                                  observed_effect: str,
                                  context: Optional[str] = None) -> Dict[str, Any]:
        """反事实推理：如果原因不同，结果会如何变化"""
        ctx_part = f"\n背景：{context}" if context else ""

        prompt = f"""反事实推理分析。

实际情况：
- 原因：{original_cause}
- 结果：{observed_effect}

反事实假设：
- 假设原因改为：{alternative_cause}{ctx_part}

返回JSON：
{{
  "original_analysis": {{
    "cause": "{original_cause}",
    "effect": "{observed_effect}",
    "causal_mechanism": "实际因果机制",
    "confidence": 0.0-1.0
  }},
  "counterfactual_analysis": {{
    "alternative_cause": "{alternative_cause}",
    "predicted_effect": "替代原因下的预测结果",
    "effect_probability": 0.0-1.0,
    "reasoning": "推理说明"
  }},
  "comparison": {{
    "key_differences": ["差异1"],
    "unchanged_aspects": ["不变方面"],
    "sensitivity": "高/中/低",
    "butterfly_effects": ["蝴蝶效应"]
  }},
  "conclusion": "总结",
  "confidence_score": 0.0-1.0
}}"""

        try:
            raw = _call_llm(prompt, SYSTEM_PROMPT_CAUSAL)
            result = _parse_json_response(raw)
        except Exception:
            result = {
                "original_analysis": {
                    "cause": original_cause,
                    "effect": observed_effect,
                    "causal_mechanism": "（离线模式：无法深度分析）",
                    "confidence": 0.6,
                },
                "counterfactual_analysis": {
                    "alternative_cause": alternative_cause,
                    "predicted_effect": f"若以「{alternative_cause}」替代，结果可能显著不同",
                    "effect_probability": 0.5,
                    "reasoning": "基于常识推断",
                },
                "comparison": {
                    "key_differences": ["驱动因素不同"],
                    "unchanged_aspects": ["部分外部条件不变"],
                    "sensitivity": "中",
                    "butterfly_effects": ["需进一步分析"],
                },
                "conclusion": "需 LLM 支持获得更准确结果",
                "confidence_score": 0.4,
            }

        self.reasoning_history.append({
            "type": "counterfactual",
            "original_cause": original_cause,
            "alternative_cause": alternative_cause,
            "timestamp": time.time(),
        })
        self._trim_if_needed()

        return result

    # ── 3. 效果预测 ──

    def predict_effects(self, cause: str, context: Optional[str] = None,
                        num_predictions: int = 5) -> Dict[str, Any]:
        """预测给定原因可能产生的多种结果"""
        ctx_part = f"\n背景：{context}" if context else ""

        prompt = f"""预测以下原因可能产生的{num_predictions}个结果。

原因/事件：{cause}{ctx_part}

返回JSON：
{{
  "cause": "{cause}",
  "predictions": [
    {{
      "effect": "预测结果",
      "probability": 0.0-1.0,
      "timeframe": "时间范围",
      "impact_level": "高/中/低",
      "category": "经济/社会/技术/环境/政治等",
      "reasoning": "预测理由",
      "preconditions": ["前提条件"]
    }}
  ],
  "overall_assessment": "整体评估",
  "risk_factors": ["风险因素"]
}}

要求：按概率从高到低排序，多维度覆盖。"""

        try:
            raw = _call_llm(prompt, SYSTEM_PROMPT_CAUSAL)
            result = _parse_json_response(raw)
        except Exception:
            result = {
                "cause": cause,
                "predictions": [
                    {
                        "effect": f"基于「{cause}」的第{i+1}个可能影响",
                        "probability": round(0.85 - i * 0.12, 2),
                        "timeframe": ["短期", "中期", "长期"][min(i, 2)],
                        "impact_level": ["高", "中", "低"][min(i, 2)],
                        "category": "综合",
                        "reasoning": "（离线模式：简化推理）",
                        "preconditions": [],
                    }
                    for i in range(num_predictions)
                ],
                "overall_assessment": "需 LLM 支持获取精确预测",
                "risk_factors": ["分析深度有限"],
            }

        # 构建图谱节点
        cause_node = self.create_node(cause, "cause", 1.0)
        for pred in result.get("predictions", []):
            effect_node = self.create_node(
                pred.get("effect", ""),
                "effect",
                pred.get("probability", 0.5),
            )
            self.create_link(
                cause_node.id, effect_node.id,
                CausalRelationType.CONTRIBUTORY,
                pred.get("probability", 0.5),
                mechanism=pred.get("reasoning", ""),
            )

        self.reasoning_history.append({
            "type": "prediction",
            "cause": cause,
            "prediction_count": len(result.get("predictions", [])),
            "timestamp": time.time(),
        })
        self._trim_if_needed()

        return result

    # ── 4. 根因分析 ──

    def root_cause_analysis(self, observed_effect: str,
                             context: Optional[str] = None,
                             depth: int = 3) -> Dict[str, Any]:
        """从观察到的现象追溯根本原因"""
        ctx_part = f"\n背景信息：{context}" if context else ""

        prompt = f"""请对以下观察到的现象进行根因分析（Root Cause Analysis）。

观察到的现象/问题：{observed_effect}{ctx_part}

分析深度：追溯{depth}层原因

请返回JSON：
{{
  "observed_effect": "{observed_effect}",
  "root_causes": [
    {{
      "cause": "根本原因描述",
      "confidence": 0.0-1.0,
      "category": "人为因素/系统因素/环境因素/流程因素/技术因素",
      "causal_chain": ["直接原因 → 中间原因 → 根本原因"],
      "evidence": ["支撑证据"],
      "severity": "高/中/低"
    }}
  ],
  "contributing_factors": [
    {{
      "factor": "促进因素",
      "influence": 0.0-1.0
    }}
  ],
  "recommended_actions": [
    {{
      "action": "建议采取的措施",
      "priority": "高/中/低",
      "expected_impact": "预期效果"
    }}
  ],
  "analysis_method": "使用的分析方法（如5-Why、鱼骨图等）",
  "confidence_score": 0.0-1.0
}}

要求：
- 至少识别3个可能的根本原因
- 每个根因都要有完整的因果链条
- 提供可执行的改进建议"""

        try:
            raw = _call_llm(prompt, SYSTEM_PROMPT_CAUSAL)
            result = _parse_json_response(raw)
        except Exception:
            result = {
                "observed_effect": observed_effect,
                "root_causes": [
                    {
                        "cause": f"可能的根因{i+1}",
                        "confidence": round(0.7 - i * 0.1, 2),
                        "category": ["系统因素", "人为因素", "环境因素"][i % 3],
                        "causal_chain": [f"直接原因{i+1}", f"间接原因{i+1}", f"根本原因{i+1}"],
                        "evidence": ["（需要 LLM 支持进行深度分析）"],
                        "severity": ["高", "中", "低"][i % 3],
                    }
                    for i in range(3)
                ],
                "contributing_factors": [
                    {"factor": "环境条件", "influence": 0.3}
                ],
                "recommended_actions": [
                    {"action": "建议接入 LLM 获取精确分析", "priority": "高",
                     "expected_impact": "显著提升分析准确度"}
                ],
                "analysis_method": "简化的5-Why分析",
                "confidence_score": 0.4,
            }

        self.reasoning_history.append({
            "type": "root_cause",
            "observed_effect": observed_effect,
            "root_cause_count": len(result.get("root_causes", [])),
            "timestamp": time.time(),
        })
        self._trim_if_needed()

        return result

    # ── 5. 干预分析 ──

    def intervention_analysis(self, current_situation: str,
                               proposed_intervention: str,
                               desired_outcome: str,
                               context: Optional[str] = None) -> Dict[str, Any]:
        """评估干预措施的因果影响"""
        ctx_part = f"\n背景：{context}" if context else ""

        prompt = f"""请分析以下干预措施的因果影响。

当前状况：{current_situation}
提议的干预措施：{proposed_intervention}
期望的结果：{desired_outcome}{ctx_part}

请返回JSON：
{{
  "intervention_assessment": {{
    "feasibility": 0.0-1.0,
    "effectiveness": 0.0-1.0,
    "risk_level": "高/中/低",
    "time_to_effect": "预计生效时间"
  }},
  "causal_pathway": {{
    "direct_effects": [
      {{
        "effect": "直接效果描述",
        "probability": 0.0-1.0,
        "mechanism": "作用机制"
      }}
    ],
    "indirect_effects": [
      {{
        "effect": "间接效果描述",
        "probability": 0.0-1.0,
        "delay": "延迟时间"
      }}
    ],
    "side_effects": [
      {{
        "effect": "副作用描述",
        "severity": "高/中/低",
        "probability": 0.0-1.0
      }}
    ]
  }},
  "success_probability": 0.0-1.0,
  "alternative_interventions": [
    {{
      "intervention": "替代方案描述",
      "advantage": "优势",
      "disadvantage": "劣势"
    }}
  ],
  "recommendation": "最终建议",
  "confidence_score": 0.0-1.0
}}"""

        try:
            raw = _call_llm(prompt, SYSTEM_PROMPT_CAUSAL)
            result = _parse_json_response(raw)
        except Exception:
            result = {
                "intervention_assessment": {
                    "feasibility": 0.6,
                    "effectiveness": 0.5,
                    "risk_level": "中",
                    "time_to_effect": "需要进一步分析",
                },
                "causal_pathway": {
                    "direct_effects": [
                        {"effect": f"「{proposed_intervention}」的直接影响",
                         "probability": 0.6, "mechanism": "直接作用"}
                    ],
                    "indirect_effects": [
                        {"effect": "需 LLM 分析间接效果",
                         "probability": 0.4, "delay": "不确定"}
                    ],
                    "side_effects": [
                        {"effect": "可能存在未预见的副作用",
                         "severity": "中", "probability": 0.3}
                    ],
                },
                "success_probability": 0.5,
                "alternative_interventions": [],
                "recommendation": "建议接入 LLM 进行完整的干预效果评估",
                "confidence_score": 0.4,
            }

        self.reasoning_history.append({
            "type": "intervention",
            "intervention": proposed_intervention,
            "timestamp": time.time(),
        })
        self._trim_if_needed()

        return result

    # ── 评估与查询 ──

    def evaluate_causal_strength(self, cause_id: str, effect_id: str) -> Dict[str, Any]:
        paths = self.graph.find_paths(cause_id, effect_id)
        if not paths:
            return {
                "has_causal_relation": False,
                "strength": 0.0,
                "confidence_level": "无",
                "paths_count": 0,
            }
        best = max(paths, key=lambda c: c.chain_confidence)
        level = ConfidenceLevel.from_value(best.chain_confidence)
        return {
            "has_causal_relation": True,
            "strength": best.chain_confidence,
            "confidence_level": level.value[2],
            "paths_count": len(paths),
            "strongest_path": best.to_dict(),
        }

    def find_common_causes(self, effect_ids: List[str]) -> List[CausalNode]:
        if not effect_ids:
            return []
        common = set()
        for link in self.graph.reverse_adjacency.get(effect_ids[0], []):
            common.add(link.source_id)
        for eid in effect_ids[1:]:
            causes = {l.source_id for l in self.graph.reverse_adjacency.get(eid, [])}
            common &= causes
        return [self.graph.get_node(nid) for nid in common if self.graph.get_node(nid)]

    def find_common_effects(self, cause_ids: List[str]) -> List[CausalNode]:
        if not cause_ids:
            return []
        common = set()
        for link in self.graph.adjacency.get(cause_ids[0], []):
            common.add(link.target_id)
        for cid in cause_ids[1:]:
            effects = {l.target_id for l in self.graph.adjacency.get(cid, [])}
            common &= effects
        return [self.graph.get_node(nid) for nid in common if self.graph.get_node(nid)]

    def explain_causation(self, cause_id: str, effect_id: str) -> Dict[str, Any]:
        paths = self.graph.find_paths(cause_id, effect_id)
        if not paths:
            return {"explanation": "未找到明确的因果关系", "has_path": False}
        best = max(paths, key=lambda p: p.chain_confidence)
        steps = []
        for i, link in enumerate(best.links):
            src = self.graph.get_node(link.source_id)
            tgt = self.graph.get_node(link.target_id)
            steps.append({
                "step": i + 1,
                "from": src.content if src else "未知",
                "to": tgt.content if tgt else "未知",
                "relation": link.relation_type.value,
                "confidence": link.confidence,
                "mechanism": link.mechanism,
            })
        return {
            "explanation": "找到因果路径",
            "has_path": True,
            "path_confidence": best.chain_confidence,
            "steps": steps,
            "total_steps": len(steps),
        }

    # ── 统计与管理 ──

    def get_graph_statistics(self) -> Dict[str, Any]:
        nodes = self.graph.nodes
        total_links = sum(len(ls) for ls in self.graph.adjacency.values())

        # 优化：一次遍历完成所有统计
        cause_count = effect_count = intermediate_count = 0
        total_confidence = 0.0
        for node in nodes.values():
            if node.node_type == "cause":
                cause_count += 1
            elif node.node_type == "effect":
                effect_count += 1
            elif node.node_type == "intermediate":
                intermediate_count += 1
            total_confidence += node.confidence

        return {
            "total_nodes": len(nodes),
            "total_links": total_links,
            "cause_nodes": cause_count,
            "effect_nodes": effect_count,
            "intermediate_nodes": intermediate_count,
            "avg_confidence": (total_confidence / len(nodes)) if nodes else 0,
            "history_count": len(self.reasoning_history),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": (self._cache_hits / (self._cache_hits + self._cache_misses)) if (self._cache_hits + self._cache_misses) > 0 else 0,
        }

    def get_reasoning_history(self) -> List[Dict[str, Any]]:
        return list(reversed(self.reasoning_history[-20:]))

    def export_graph(self) -> Dict[str, Any]:
        return self.graph.to_dict()

    def clear_graph(self, clear_cache: bool = False):
        """清空图谱和历史记录

        :param clear_cache: 是否同时清空 LLM 缓存
        """
        self.graph = CausalGraph()
        self.reasoning_history.clear()
        if clear_cache:
            self._llm_cache.clear()
            self._cache_timestamps.clear()
            self._cache_hits = 0
            self._cache_misses = 0

    def batch_analyze(self, pairs: List[Tuple[str, str]],
                     context: Optional[str] = None) -> List[Dict[str, Any]]:
        """批量分析多个因果对

        :param pairs: [(cause1, effect1), (cause2, effect2), ...]
        :param context: 共享的背景信息
        :return: 分析结果列表
        """
        results = []
        for cause, effect in pairs:
            try:
                result = self.analyze_causal_chain(cause, effect, context, use_cache=True)
                results.append({"success": True, "cause": cause, "effect": effect, "result": result})
            except Exception as e:
                results.append({"success": False, "cause": cause, "effect": effect, "error": str(e)})
        return results

    def get_node_importance(self, node_id: str) -> Dict[str, Any]:
        """计算节点的重要性指标

        :param node_id: 节点ID
        :return: 包含多个重要性指标的字典
        """
        node = self.graph.get_node(node_id)
        if not node:
            return {"error": "节点不存在"}

        # 出度和入度
        out_degree = len(self.graph.adjacency.get(node_id, []))
        in_degree = len(self.graph.reverse_adjacency.get(node_id, []))

        # 计算影响范围（能到达的节点数）
        reachable = set()
        visited = set()

        def dfs_reach(nid, depth=0):
            if depth > 10 or nid in visited:
                return
            visited.add(nid)
            for child, _ in self.graph.get_children(nid):
                reachable.add(child.id)
                dfs_reach(child.id, depth + 1)

        dfs_reach(node_id)

        # 计算被影响范围（能到达该节点的节点数）
        influenced_by = set()
        visited.clear()

        def dfs_influenced(nid, depth=0):
            if depth > 10 or nid in visited:
                return
            visited.add(nid)
            for parent, _ in self.graph.get_parents(nid):
                influenced_by.add(parent.id)
                dfs_influenced(parent.id, depth + 1)

        dfs_influenced(node_id)

        return {
            "node_id": node_id,
            "content": node.content,
            "out_degree": out_degree,
            "in_degree": in_degree,
            "total_degree": out_degree + in_degree,
            "reachable_nodes": len(reachable),
            "influenced_by_nodes": len(influenced_by),
            "confidence": node.confidence,
            "importance_score": (out_degree * 2 + in_degree + len(reachable) * 0.5 + len(influenced_by) * 0.3) * node.confidence,
        }

    def find_critical_nodes(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """找出图谱中最关键的节点

        :param top_n: 返回前N个关键节点
        :return: 按重要性排序的节点列表
        """
        importance_list = []
        for node_id in self.graph.nodes.keys():
            importance = self.get_node_importance(node_id)
            if "error" not in importance:
                importance_list.append(importance)

        importance_list.sort(key=lambda x: x["importance_score"], reverse=True)
        return importance_list[:top_n]

    def detect_cycles(self) -> List[List[str]]:
        """检测图中的环路

        :return: 环路列表，每个环路是节点ID的列表
        """
        return self.graph.detect_cycles()

    def get_shortest_path(self, start_id: str, end_id: str) -> Optional[CausalChain]:
        """获取两个节点之间的最短路径

        :param start_id: 起始节点ID
        :param end_id: 目标节点ID
        :return: 最短路径的因果链，如果不存在则返回None
        """
        return self.graph.shortest_path(start_id, end_id)

    def merge_similar_nodes(self, similarity_threshold: float = 0.8) -> int:
        """合并相似的节点以减少冗余

        :param similarity_threshold: 相似度阈值（0-1）
        :return: 合并的节点数量
        """
        from difflib import SequenceMatcher

        def similarity(a: str, b: str) -> float:
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()

        nodes_list = list(self.graph.nodes.values())
        merged_count = 0
        merged_ids = set()

        for i, node1 in enumerate(nodes_list):
            if node1.id in merged_ids:
                continue

            for node2 in nodes_list[i + 1:]:
                if node2.id in merged_ids:
                    continue

                if node1.node_type == node2.node_type and similarity(node1.content, node2.content) >= similarity_threshold:
                    # 合并 node2 到 node1
                    # 重定向所有指向 node2 的链接到 node1
                    for parent, link in self.graph.get_parents(node2.id):
                        new_link = CausalLink(
                            source_id=parent.id,
                            target_id=node1.id,
                            relation_type=link.relation_type,
                            confidence=max(link.confidence, node1.confidence),
                            evidence=link.evidence,
                            mechanism=link.mechanism,
                        )
                        self.graph.add_link(new_link)

                    # 重定向所有从 node2 出发的链接
                    for child, link in self.graph.get_children(node2.id):
                        new_link = CausalLink(
                            source_id=node1.id,
                            target_id=child.id,
                            relation_type=link.relation_type,
                            confidence=max(link.confidence, node1.confidence),
                            evidence=link.evidence,
                            mechanism=link.mechanism,
                        )
                        self.graph.add_link(new_link)

                    # 删除 node2
                    self.graph.nodes.pop(node2.id, None)
                    self.graph.adjacency.pop(node2.id, None)
                    self.graph.reverse_adjacency.pop(node2.id, None)
                    merged_ids.add(node2.id)
                    merged_count += 1

        if merged_count > 0:
            self.graph._invalidate_caches()

        return merged_count

    def get_subgraph(self, node_ids: List[str], depth: int = 2) -> Dict[str, Any]:
        """提取以指定节点为中心的子图

        :param node_ids: 中心节点ID列表
        :param depth: 扩展深度
        :return: 子图的字典表示
        """
        subgraph_nodes = set(node_ids)
        visited = set()

        def expand(nid, current_depth):
            if current_depth >= depth or nid in visited:
                return
            visited.add(nid)
            for child, _ in self.graph.get_children(nid):
                subgraph_nodes.add(child.id)
                expand(child.id, current_depth + 1)
            for parent, _ in self.graph.get_parents(nid):
                subgraph_nodes.add(parent.id)
                expand(parent.id, current_depth + 1)

        for nid in node_ids:
            expand(nid, 0)

        # 构建子图
        nodes = [self.graph.nodes[nid].to_dict() for nid in subgraph_nodes if nid in self.graph.nodes]
        links = []
        for nid in subgraph_nodes:
            for link in self.graph.adjacency.get(nid, []):
                if link.target_id in subgraph_nodes:
                    links.append(link.to_dict())

        return {
            "nodes": nodes,
            "links": links,
            "node_count": len(nodes),
            "link_count": len(links),
        }

    def analyze_graph_structure(self) -> Dict[str, Any]:
        """分析图谱的整体结构特征

        :return: 结构分析结果
        """
        total_nodes = len(self.graph.nodes)
        if total_nodes == 0:
            return {"error": "图谱为空"}

        # 计算度分布
        in_degrees = []
        out_degrees = []
        for node_id in self.graph.nodes.keys():
            in_degrees.append(len(self.graph.reverse_adjacency.get(node_id, [])))
            out_degrees.append(len(self.graph.adjacency.get(node_id, [])))

        # 计算连通分量数量
        visited = set()
        components = 0

        def dfs_component(nid):
            if nid in visited:
                return
            visited.add(nid)
            for child, _ in self.graph.get_children(nid):
                dfs_component(child.id)
            for parent, _ in self.graph.get_parents(nid):
                dfs_component(parent.id)

        for node_id in self.graph.nodes.keys():
            if node_id not in visited:
                components += 1
                dfs_component(node_id)

        # 计算平均路径长度（采样）
        import random
        sample_size = min(50, total_nodes)
        sampled_nodes = random.sample(list(self.graph.nodes.keys()), sample_size)
        path_lengths = []

        for i, start in enumerate(sampled_nodes):
            for end in sampled_nodes[i + 1:]:
                path = self.get_shortest_path(start, end)
                if path:
                    path_lengths.append(len(path.links))

        avg_path_length = sum(path_lengths) / len(path_lengths) if path_lengths else 0

        return {
            "total_nodes": total_nodes,
            "total_links": sum(len(ls) for ls in self.graph.adjacency.values()),
            "connected_components": components,
            "avg_in_degree": sum(in_degrees) / total_nodes,
            "avg_out_degree": sum(out_degrees) / total_nodes,
            "max_in_degree": max(in_degrees) if in_degrees else 0,
            "max_out_degree": max(out_degrees) if out_degrees else 0,
            "avg_path_length": avg_path_length,
            "isolated_nodes": len(self.graph.get_isolated_nodes()),
            "root_nodes": len(self.graph.get_root_nodes()),
            "leaf_nodes": len(self.graph.get_leaf_nodes()),
            "cycles_detected": len(self.detect_cycles()),
        }


# ─── 全局单例 ─────────────────────────────────────────────────────────────────

_engine_instance = None


def get_causal_engine() -> CausalReasoningEngine:
    """获取因果推理引擎单例"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = CausalReasoningEngine()
    return _engine_instance
