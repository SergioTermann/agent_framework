"""
统一上下文构建器
================

把对话历史、长期记忆、知识库检索结果统一拼装成可供聊天模型或 Agent 使用的上下文。

改进点（相对旧版）：
  - Token-aware 窗口管理：按 token budget 而非固定条数裁剪
  - User-Assistant 配对完整性：选取历史时保证问答对不被拆散
  - 分层摘要架构：近期原文 → 中期 LLM 增量摘要 → 远期主题骨架
  - 增量摘要缓存：每隔 K 轮自动生成/更新摘要，持久化到会话 metadata
  - 主题转折检测：识别话题切换点，在摘要中保留转折上下文
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from agent_framework.web.conversation_manager import ConversationManager, Message, MessageRole
from agent_framework.vector_db.knowledge_base import knowledge_manager
from agent_framework.memory.system import get_memory_manager

logger = logging.getLogger(__name__)

# ─── Token 估算 ─────────────────────────────────────────────────────────────

# 粗略估算：中文约 1.5 token/字，英文约 1.3 token/word，混合场景取均值
_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数。不依赖 tiktoken，但足够做 budget 决策。"""
    if not text:
        return 0
    cjk_chars = len(_CJK_RANGE.findall(text))
    non_cjk = len(text) - cjk_chars
    # CJK 字符约 1.5 token/char，非 CJK 约 0.3 token/char (含空格标点)
    return int(cjk_chars * 1.5 + non_cjk * 0.3) + 1


def estimate_message_tokens(msg: Message) -> int:
    """估算单条消息的 token 数（含 role 开销）。"""
    return estimate_tokens(msg.content) + 4  # role/separator overhead


# ─── 数据模型 ────────────────────────────────────────────────────────────────


@dataclass
class RetrievedMemory:
    memory_id: str
    content: str
    memory_type: str
    score: float
    tags: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedKnowledgeChunk:
    kb_id: str
    kb_name: str
    chunk_id: str
    content: str
    distance: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    snippet: str = ""
    score: float = 0.0
    retrieval_score: float = 0.0
    lexical_score: float = 0.0
    vector_score: float = 0.0
    citation_label: str = ""


@dataclass
class SummaryCache:
    """增量摘要缓存。存储在会话 metadata 中，避免每次重新计算。"""
    # 已摘要覆盖到的消息数
    covered_message_count: int = 0
    # 已摘要覆盖到的 token 数（用于判断是否需要刷新）
    covered_tokens: int = 0
    # LLM 生成的摘要文本
    summary_text: str = ""
    # 提取的主题骨架
    topic_skeleton: List[str] = field(default_factory=list)
    # 关键决策/转折点
    key_decisions: List[str] = field(default_factory=list)
    # 用于校验是否需要刷新的 hash
    content_hash: str = ""


@dataclass
class ContextBundle:
    conversation_id: str
    recent_messages: List[Message] = field(default_factory=list)
    conversation_summary: str = ""
    working_memories: List[RetrievedMemory] = field(default_factory=list)
    memories: List[RetrievedMemory] = field(default_factory=list)
    knowledge_chunks: List[RetrievedKnowledgeChunk] = field(default_factory=list)
    retrieval_plan: Dict[str, Any] = field(default_factory=dict)
    # 新增：token 使用统计
    token_stats: Dict[str, int] = field(default_factory=dict)

    def recent_messages_for_llm(self) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for message in self.recent_messages:
            if message.role in {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM}:
                messages.append({
                    "role": message.role.value,
                    "content": message.content,
                })
        return messages

    def as_prefetch_text(self) -> str:
        parts: List[str] = []

        if self.conversation_summary:
            parts.append(f"[Earlier Summary]\n{self.conversation_summary}")

        if self.recent_messages:
            lines = []
            for msg in self.recent_messages:
                role = {
                    MessageRole.USER: "User",
                    MessageRole.ASSISTANT: "Assistant",
                    MessageRole.SYSTEM: "System",
                    MessageRole.TOOL: "Tool",
                }.get(msg.role, str(msg.role))
                lines.append(f"- {role}: {self._clip(msg.content, 300)}")
            parts.append("[Recent Messages]\n" + "\n".join(lines))

        if self.memories:
            lines = [
                f"- ({item.memory_type}, score={item.score:.3f}) {self._clip(item.content, 280)}"
                for item in self.memories
            ]
            parts.append("[Relevant Memories]\n" + "\n".join(lines))

        if self.working_memories:
            lines = [
                f"- ({item.memory_type}, score={item.score:.3f}) {self._clip(item.content, 280)}"
                for item in self.working_memories
            ]
            parts.append("[Working Memory]\n" + "\n".join(lines))

        if self.knowledge_chunks:
            lines = []
            for idx, item in enumerate(self.knowledge_chunks, 1):
                label = item.citation_label or f"知识#{idx}"
                doc_name = str((item.metadata or {}).get("doc_name", "") or "").strip()
                section_title = str((item.metadata or {}).get("section_title", "") or "").strip()
                window_start = (item.metadata or {}).get("window_start")
                window_end = (item.metadata or {}).get("window_end")

                source_parts = [f"KB={item.kb_name}"]
                if doc_name:
                    source_parts.append(f"doc={doc_name}")
                if section_title:
                    source_parts.append(f"section={section_title}")
                context_mode = str((item.metadata or {}).get("context_mode", "") or "").strip()
                if context_mode:
                    source_parts.append(f"mode={context_mode}")
                if window_start is not None and window_end is not None:
                    source_parts.append(f"chunk={window_start}-{window_end}")
                section_start = (item.metadata or {}).get("section_start")
                section_end = (item.metadata or {}).get("section_end")
                if section_start is not None and section_end is not None:
                    source_parts.append(f"section_span={section_start}-{section_end}")

                snippet = self._clip(item.snippet or item.content, 220)
                merged_context = self._clip(item.content, 420)
                lines.append(
                    f"- [{label}] {' | '.join(source_parts)} | score={item.score:.3f}\n"
                    f"  命中片段: {snippet}\n"
                    f"  扩展上下文: {merged_context}"
                )
            parts.append("[Knowledge Retrieval]\n" + "\n".join(lines))

        return "\n\n".join(parts)

    @staticmethod
    def _clip(text: str, max_len: int) -> str:
        text = " ".join((text or "").split())
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."


# ─── 核心：ContextBuilder ─────────────────────────────────────────────────────


class ContextBuilder:
    """Unified conversational context builder with tiered summarization."""

    # ── 配置常量 ──

    # Token budget: recent window 占多少 token（默认约 3000）
    DEFAULT_TOKEN_BUDGET = 3000
    # 摘要触发阈值：older messages 总 token 超过此值才做 LLM 摘要
    # 低于此值用启发式即可，避免浪费 LLM 调用
    SUMMARY_LLM_TOKEN_THRESHOLD = 800
    # 增量摘要刷新阈值：缓存命中后，新增 token 超过此值才刷新摘要
    # 低于此值复用旧缓存 + 追加增量，保持长对话的摘要稳定
    SUMMARY_INCREMENTAL_TOKEN_THRESHOLD = 600
    # 摘要全量重建阈值：新增 token 超过此值时放弃增量，做全量重建
    # 增量追加太多次后摘要会碎片化，需要重新整理
    SUMMARY_FULL_REBUILD_TOKEN_THRESHOLD = 2400
    # 过渡区消息数：recent window 和 summary 之间的轻量压缩区域
    TRANSITION_ZONE_SIZE = 4
    # 过渡区消息截断长度
    TRANSITION_CLIP_LEN = 120

    SIMPLE_CHAT_PATTERNS = [
        r"^(好|好的|行|可以|收到|明白|了解|嗯|嗯嗯|哦|哦哦|ok|okay|roger)[!！。.]?$",
        r"^(谢谢|谢了|thanks|thank you)[!！。.]?$",
        r"^(继续|接着|然后呢|还有吗|再说说|展开一下|详细一点|说简单点|总结一下)[!！。.]?$",
    ]
    MEMORY_CUE_PATTERN = re.compile(
        r"(之前|上次|刚才|历史|回顾|总结前面|根据之前|还记得|延续上个|继续上个|结合前文|前面提到)",
        re.IGNORECASE,
    )
    KNOWLEDGE_CUE_PATTERN = re.compile(
        r"(知识库|文档|资料|手册|sop|pdf|根据.*资料|故障|告警|报警|根因|排查|诊断|步骤|原因|scada|偏航|齿轮箱|机组|风机|turbine|gearbox|yaw|alarm|manual|document|kb\b)",
        re.IGNORECASE,
    )
    # 话题转折信号词
    _TOPIC_SHIFT_PATTERNS = re.compile(
        r"(另外|换个话题|还有一个问题|其他的|顺便问|by the way|btw|另一个|不过我想|那如果|还想问)",
        re.IGNORECASE,
    )

    def __init__(self, conversation_manager: ConversationManager):
        self.conversation_manager = conversation_manager
        self.memory_manager = get_memory_manager()

    # ── 主入口 ──

    def build(
        self,
        conversation_id: str,
        user_input: str,
        user_id: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None,
        retrieval_options: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        enable_knowledge_retrieval: bool = True,
        history_window: int = 8,
        summary_window: int = 8,
        memory_limit: int = 4,
        rag_top_k: int = 5,
        token_budget: Optional[int] = None,
    ) -> ContextBundle:
        conversation, messages = self.conversation_manager.get_conversation_history(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation not found: {conversation_id}")

        budget = token_budget or self.DEFAULT_TOKEN_BUDGET

        # 1) Token-aware 选取近期消息（保证配对完整性）
        recent_messages, transition_messages = self._select_recent_messages_token_aware(
            messages=messages,
            user_input=user_input,
            token_budget=budget,
            max_messages=history_window,
        )

        # 2) 分层摘要：缓存 + 增量 + 过渡区
        recent_ids = {msg.message_id for msg in recent_messages}
        transition_ids = {msg.message_id for msg in transition_messages}
        older_messages = [
            msg for msg in messages
            if msg.message_id not in recent_ids and msg.message_id not in transition_ids
        ]

        summary = self._build_tiered_summary(
            conversation=conversation,
            older_messages=older_messages,
            transition_messages=transition_messages,
            user_input=user_input,
        )

        # 3) Retrieval plan（不变）
        retrieval_plan = self._build_retrieval_plan(
            user_input=user_input,
            recent_messages=recent_messages,
            conversation_id=conversation_id,
            user_id=user_id,
            knowledge_base_ids=knowledge_base_ids,
            metadata=metadata or {},
            enable_knowledge_retrieval=enable_knowledge_retrieval,
            memory_limit=memory_limit,
            rag_top_k=rag_top_k,
        )

        # 4) 检索
        working_memories = self._retrieve_working_memories(
            user_input,
            conversation_id=conversation_id,
            user_id=user_id,
            retrieval_plan=retrieval_plan,
            metadata=metadata or {},
        ) if retrieval_plan.get("use_memory") else []
        memories = self._retrieve_memories(
            user_input,
            conversation_id=conversation_id,
            user_id=user_id,
            retrieval_plan=retrieval_plan,
            metadata=metadata or {},
            limit=int(retrieval_plan.get("memory_limit", 0) or 0),
        ) if retrieval_plan.get("use_memory") else []
        knowledge_chunks = self._retrieve_knowledge(
            user_input,
            knowledge_base_ids=knowledge_base_ids,
            top_k=int(retrieval_plan.get("rag_top_k", 0) or 0),
            retrieval_options=retrieval_options,
        ) if retrieval_plan.get("use_knowledge") else []

        # Token 统计
        recent_tokens = sum(estimate_message_tokens(m) for m in recent_messages)
        summary_tokens = estimate_tokens(summary)

        return ContextBundle(
            conversation_id=conversation_id,
            recent_messages=recent_messages,
            conversation_summary=summary,
            working_memories=working_memories,
            memories=memories,
            knowledge_chunks=knowledge_chunks,
            retrieval_plan=retrieval_plan,
            token_stats={
                "recent_messages_tokens": recent_tokens,
                "summary_tokens": summary_tokens,
                "working_memory_count": len(working_memories),
                "memory_count": len(memories),
                "recent_message_count": len(recent_messages),
                "transition_message_count": len(transition_messages),
                "older_message_count": len(older_messages),
                "total_message_count": len(messages),
                "token_budget": budget,
            },
        )

    # ── Token-aware 历史选取 ──

    def _select_recent_messages_token_aware(
        self,
        *,
        messages: List[Message],
        user_input: str,
        token_budget: int,
        max_messages: int,
    ) -> Tuple[List[Message], List[Message]]:
        """
        按 token budget 从尾部向前选取消息，保证 user-assistant 配对完整性。

        返回 (recent_messages, transition_messages):
          - recent_messages: 保留原文，送入 LLM
          - transition_messages: 在摘要中做轻量压缩（截断但保留要点）
        """
        if not messages:
            return [], []

        # 全部消息都在预算内，直接返回
        total_tokens = sum(estimate_message_tokens(m) for m in messages)
        if total_tokens <= token_budget and len(messages) <= max_messages:
            return list(messages), []

        # 从尾部开始，按配对向前收集
        pairs = self._group_into_pairs(messages)

        selected_pairs: List[List[Message]] = []
        used_tokens = 0

        # 先从最近的 pair 开始填充
        for pair in reversed(pairs):
            pair_tokens = sum(estimate_message_tokens(m) for m in pair)
            if used_tokens + pair_tokens > token_budget:
                break
            if sum(len(p) for p in selected_pairs) + len(pair) > max_messages:
                break
            selected_pairs.append(pair)
            used_tokens += pair_tokens

        selected_pairs.reverse()
        message_positions = {msg.message_id: idx for idx, msg in enumerate(messages)}
        query_terms = set(self._extract_terms(user_input))

        def pair_tokens(pair: List[Message]) -> int:
            return sum(estimate_message_tokens(m) for m in pair)

        def pair_score(pair: List[Message], idx: int) -> float:
            combined = " ".join(m.content for m in pair)
            relevance = self._message_relevance_score(combined, query_terms)
            recency = idx / max(1, len(pairs) - 1)
            return relevance + recency * 0.3

        selected_indices = {
            idx for idx, pair in enumerate(pairs)
            if any(pair is chosen for chosen in selected_pairs)
        }
        remaining_budget = token_budget - used_tokens
        remaining_slots = max_messages - sum(len(pair) for pair in selected_pairs)

        scored_candidates: List[Tuple[float, int, List[Message]]] = []
        for idx, pair in enumerate(pairs):
            if idx in selected_indices:
                continue
            score = pair_score(pair, idx)
            if score <= 0:
                continue
            scored_candidates.append((score, idx, pair))
        scored_candidates.sort(reverse=True)

        if remaining_budget > 100 and remaining_slots >= 2:
            for _score, idx, pair in scored_candidates:
                current_pair_tokens = pair_tokens(pair)
                if current_pair_tokens > remaining_budget or len(pair) > remaining_slots:
                    continue
                selected_pairs.append(pair)
                selected_indices.add(idx)
                remaining_budget -= current_pair_tokens
                remaining_slots -= len(pair)
        elif scored_candidates and selected_pairs:
            scored_selected = sorted(
                (
                    (pair_score(pair, idx), idx, pair)
                    for idx, pair in enumerate(pairs)
                    if idx in selected_indices
                ),
                key=lambda item: (item[0], item[1]),
            )
            for candidate_score, candidate_idx, candidate_pair in scored_candidates:
                weakest_score, weakest_idx, weakest_pair = scored_selected[0]
                if candidate_score <= weakest_score + 0.2:
                    break
                token_delta = pair_tokens(candidate_pair) - pair_tokens(weakest_pair)
                if used_tokens + token_delta > token_budget:
                    continue
                weakest_pair_id = tuple(msg.message_id for msg in weakest_pair)
                selected_pairs = [
                    candidate_pair if tuple(msg.message_id for msg in pair) == weakest_pair_id else pair
                    for pair in selected_pairs
                ]
                selected_indices.discard(weakest_idx)
                selected_indices.add(candidate_idx)
                used_tokens += token_delta
                scored_selected[0] = (candidate_score, candidate_idx, candidate_pair)
                scored_selected.sort(key=lambda item: (item[0], item[1]))

        selected_pairs.sort(key=lambda pair: min(message_positions[msg.message_id] for msg in pair))
        recent = [msg for pair in selected_pairs for msg in pair]

        # 过渡区：recent 之前的 N 条消息
        recent_ids = {m.message_id for m in recent}
        non_recent = [m for m in messages if m.message_id not in recent_ids]
        transition = non_recent[-self.TRANSITION_ZONE_SIZE:] if len(non_recent) > self.TRANSITION_ZONE_SIZE else []

        return recent, transition

    @staticmethod
    def _group_into_pairs(messages: List[Message]) -> List[List[Message]]:
        """
        将消息按 user-assistant 配对分组。
        确保一个 user 消息和紧跟的 assistant 消息不会被拆散。
        """
        pairs: List[List[Message]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.role == MessageRole.USER and i + 1 < len(messages) and messages[i + 1].role == MessageRole.ASSISTANT:
                pairs.append([msg, messages[i + 1]])
                i += 2
            else:
                pairs.append([msg])
                i += 1
        return pairs

    # ── 分层摘要 ──

    def _build_tiered_summary(
        self,
        *,
        conversation: Any,
        older_messages: List[Message],
        transition_messages: List[Message],
        user_input: str,
    ) -> str:
        """
        三层摘要架构：
          Layer 1 (远期) - LLM 增量摘要 / 缓存命中
          Layer 2 (中期) - 过渡区轻量压缩
          Layer 3 (近期) - 原文保留（不在此处理，在 recent_messages 中）
        """
        if not older_messages and not transition_messages:
            return ""

        parts: List[str] = []

        # Layer 1: 远期摘要（token-driven 缓存策略）
        if older_messages:
            older_tokens = sum(estimate_message_tokens(m) for m in older_messages)
            cached = self._load_summary_cache(conversation)
            content_hash = self._compute_messages_hash(older_messages)

            if cached and cached.content_hash == content_hash and cached.summary_text:
                # 完全命中：消息集合没变
                parts.append(cached.summary_text)
            elif cached and cached.summary_text and cached.covered_tokens > 0:
                # 有旧缓存，计算 token 增量决定策略
                token_delta = older_tokens - cached.covered_tokens

                if token_delta <= 0:
                    # 消息减少了（不太常见），用旧缓存
                    parts.append(cached.summary_text)
                elif token_delta < self.SUMMARY_INCREMENTAL_TOKEN_THRESHOLD:
                    # 增量小：复用旧摘要，不刷新
                    parts.append(cached.summary_text)
                elif token_delta < self.SUMMARY_FULL_REBUILD_TOKEN_THRESHOLD:
                    # 增量适中：增量追加
                    new_summary = self._generate_summary(
                        older_messages=older_messages,
                        older_tokens=older_tokens,
                        user_input=user_input,
                        previous_cache=cached,
                        force_mode="incremental",
                    )
                    parts.append(new_summary.summary_text)
                    new_summary.content_hash = content_hash
                    self._save_summary_cache(conversation, new_summary)
                else:
                    # 增量太大：全量重建
                    new_summary = self._generate_summary(
                        older_messages=older_messages,
                        older_tokens=older_tokens,
                        user_input=user_input,
                        previous_cache=None,
                        force_mode="full",
                    )
                    parts.append(new_summary.summary_text)
                    new_summary.content_hash = content_hash
                    self._save_summary_cache(conversation, new_summary)
            else:
                # 无缓存：首次生成
                new_summary = self._generate_summary(
                    older_messages=older_messages,
                    older_tokens=older_tokens,
                    user_input=user_input,
                    previous_cache=None,
                    force_mode=None,
                )
                parts.append(new_summary.summary_text)
                new_summary.content_hash = content_hash
                self._save_summary_cache(conversation, new_summary)

        # Layer 2: 过渡区压缩
        if transition_messages:
            transition_text = self._compress_transition_zone(transition_messages)
            if transition_text:
                parts.append(transition_text)

        return "\n\n".join(parts)

    def _generate_summary(
        self,
        *,
        older_messages: List[Message],
        older_tokens: int,
        user_input: str,
        previous_cache: Optional[SummaryCache],
        force_mode: Optional[str] = None,
    ) -> SummaryCache:
        """
        生成摘要。触发策略完全基于 token 用量。

        Args:
            older_tokens: older_messages 的总 token 数
            force_mode: "incremental" / "full" / None(自动)
        """
        # 增量模式：有旧缓存，只处理新增部分
        if force_mode == "incremental" and previous_cache and previous_cache.summary_text:
            new_msg_count = len(older_messages) - previous_cache.covered_message_count
            if new_msg_count > 0:
                new_messages = older_messages[-new_msg_count:]
                new_tokens = sum(estimate_message_tokens(m) for m in new_messages)
                incremental = self._heuristic_summary_block(new_messages, user_input, max_items=4)
                merged_text = (
                    f"{previous_cache.summary_text}\n"
                    f"[+{new_msg_count} messages, ~{new_tokens} tokens]\n{incremental}"
                )
                return SummaryCache(
                    covered_message_count=len(older_messages),
                    covered_tokens=older_tokens,
                    summary_text=merged_text,
                    topic_skeleton=previous_cache.topic_skeleton + self._extract_topics(new_messages, top_n=2),
                    key_decisions=previous_cache.key_decisions + self._detect_key_decisions(new_messages),
                )

        # 全量摘要：token 达到阈值才用 LLM
        if older_tokens >= self.SUMMARY_LLM_TOKEN_THRESHOLD:
            llm_summary = self._try_llm_summarize(older_messages)
            if llm_summary:
                topics = self._extract_topics(older_messages, top_n=5)
                decisions = self._detect_key_decisions(older_messages)
                full_text = llm_summary
                if decisions:
                    full_text += "\nKey decisions: " + " | ".join(decisions[:3])
                return SummaryCache(
                    covered_message_count=len(older_messages),
                    covered_tokens=older_tokens,
                    summary_text=full_text,
                    topic_skeleton=topics,
                    key_decisions=decisions,
                )

        # 回退：启发式（token 少，不值得调 LLM）
        heuristic_text = self._heuristic_summary_full(older_messages, user_input)
        return SummaryCache(
            covered_message_count=len(older_messages),
            covered_tokens=older_tokens,
            summary_text=heuristic_text,
            topic_skeleton=self._extract_topics(older_messages, top_n=5),
            key_decisions=self._detect_key_decisions(older_messages),
        )

    def _try_llm_summarize(self, messages: List[Message]) -> Optional[str]:
        """尝试用 LLM 做摘要。失败返回 None，不中断主流程。"""
        try:
            from agent_framework.agent.llm import get_llm_client

            client = get_llm_client()

            # 构建待摘要文本，每轮对话截断到合理长度
            turns: List[str] = []
            total_chars = 0
            max_chars = 4000  # 输入上限，防止 prompt 过长

            for msg in messages:
                role = "用户" if msg.role == MessageRole.USER else "助手"
                content = " ".join((msg.content or "").split())
                if len(content) > 200:
                    content = content[:197] + "..."
                turn = f"{role}: {content}"
                if total_chars + len(turn) > max_chars:
                    break
                turns.append(turn)
                total_chars += len(turn)

            if not turns:
                return None

            conversation_text = "\n".join(turns)

            response = client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是对话摘要助手。请将以下对话历史压缩为简洁摘要。\n"
                            "要求：\n"
                            "1. 保留关键问题、结论和决策\n"
                            "2. 标注话题转折点\n"
                            "3. 用中文输出，不超过 300 字\n"
                            "4. 格式：先给一句话总结，再列要点"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"请摘要以下 {len(turns)} 轮对话：\n\n{conversation_text}",
                    },
                ],
                temperature=0.3,
                max_tokens=512,
            )
            result = (response.content or "").strip()
            if len(result) < 10:
                return None
            return result
        except Exception as e:
            logger.debug("LLM summarization failed, falling back to heuristic: %s", e)
            return None

    def _heuristic_summary_full(self, older_messages: List[Message], user_input: str) -> str:
        """改进版启发式全量摘要。比旧版增加了：话题分段、轮次压缩、决策检测。"""
        if not older_messages:
            return ""

        user_messages = [msg for msg in older_messages if msg.role == MessageRole.USER]
        assistant_messages = [msg for msg in older_messages if msg.role == MessageRole.ASSISTANT]

        # 话题分段
        segments = self._segment_by_topic(older_messages)

        lines: List[str] = [
            f"Earlier turns: {len(older_messages)} messages, "
            f"{len(user_messages)} user turns, {len(segments)} topic segments.",
        ]

        # 主题骨架
        topics = self._extract_topics(older_messages, top_n=5)
        if topics:
            lines.append("Recurring topics: " + ", ".join(topics))

        # 每个话题段取一个代表性 user+assistant 对
        query_terms = set(self._extract_terms(user_input))
        user_intents: List[str] = []
        assistant_takeaways: List[str] = []
        for seg_idx, segment in enumerate(segments):
            seg_user = [m for m in segment if m.role == MessageRole.USER]
            seg_assistant = [m for m in segment if m.role == MessageRole.ASSISTANT]
            if not seg_user:
                continue

            # 取该段中与当前查询最相关的 user 消息
            best_user = max(
                seg_user,
                key=lambda m: self._message_relevance_score(m.content, query_terms)
                + (0.5 if m == seg_user[-1] else 0),  # 偏好段内最后一条
            )
            user_text = self._clip(best_user.content, 140)
            user_intents.append(user_text)

            # 取最相关的 assistant 回复
            assistant_text = ""
            if seg_assistant:
                best_assistant = max(
                    seg_assistant,
                    key=lambda m: self._message_relevance_score(m.content, query_terms)
                    + (0.5 if m == seg_assistant[-1] else 0),
                )
                assistant_text = self._clip(best_assistant.content, 140)
                assistant_takeaways.append(assistant_text)

            lines.append(f"[Segment {seg_idx + 1}] Q: {user_text}")
            if assistant_text:
                lines.append(f"  A: {assistant_text}")

        if user_intents:
            lines.append("Earlier user intents: " + " | ".join(user_intents[:3]))
        if assistant_takeaways:
            lines.append("Earlier assistant takeaways: " + " | ".join(assistant_takeaways[:3]))

        # 关键决策
        decisions = self._detect_key_decisions(older_messages)
        if decisions:
            lines.append("Key decisions: " + " | ".join(decisions[:3]))

        return "\n".join(lines)

    def _heuristic_summary_block(
        self, messages: List[Message], user_input: str, max_items: int = 4
    ) -> str:
        """对一小块消息做启发式摘要（用于增量追加）。"""
        query_terms = set(self._extract_terms(user_input))
        user_msgs = [m for m in messages if m.role == MessageRole.USER]
        assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]

        lines: List[str] = []
        for m in user_msgs[:max_items]:
            lines.append(f"- Q: {self._clip(m.content, 120)}")
        for m in assistant_msgs[:max_items]:
            lines.append(f"- A: {self._clip(m.content, 120)}")
        return "\n".join(lines) if lines else ""

    # ── 过渡区压缩 ──

    def _compress_transition_zone(self, messages: List[Message]) -> str:
        """过渡区消息：保留问答结构但截断内容。"""
        if not messages:
            return ""
        lines = ["[Transition context]"]
        for msg in messages:
            role = "Q" if msg.role == MessageRole.USER else "A"
            lines.append(f"- {role}: {self._clip(msg.content, self.TRANSITION_CLIP_LEN)}")
        return "\n".join(lines)

    # ── 话题分段 ──

    def _segment_by_topic(self, messages: List[Message]) -> List[List[Message]]:
        """
        将消息按话题分段。检测方式：
          1. 显式转折信号词
          2. 连续 user 消息（前一轮无 assistant 回复 → 可能是追问或新话题）
          3. 关键词集合变化超过阈值
        """
        if len(messages) <= 4:
            return [messages]

        segments: List[List[Message]] = []
        current_segment: List[Message] = []
        prev_terms: set = set()

        for i, msg in enumerate(messages):
            is_shift = False

            if msg.role == MessageRole.USER:
                content = msg.content or ""
                # 信号词检测
                if self._TOPIC_SHIFT_PATTERNS.search(content):
                    is_shift = True

                # 关键词变化检测
                if not is_shift and prev_terms:
                    current_terms = set(self._extract_terms(content))
                    if current_terms:
                        overlap = len(prev_terms & current_terms)
                        union = len(prev_terms | current_terms)
                        jaccard = overlap / max(1, union)
                        if jaccard < 0.15:  # 关键词重叠极少 → 新话题
                            is_shift = True

                prev_terms = set(self._extract_terms(content))

            if is_shift and current_segment:
                segments.append(current_segment)
                current_segment = []

            current_segment.append(msg)

        if current_segment:
            segments.append(current_segment)

        return segments

    # ── 关键决策检测 ──

    def _detect_key_decisions(self, messages: List[Message]) -> List[str]:
        """检测对话中的关键决策/结论。"""
        decision_patterns = re.compile(
            r"(建议|决定|结论|方案是|确认|总结.*[：:]|最终|应该|需要先|优先)",
            re.IGNORECASE,
        )
        decisions: List[str] = []
        for msg in messages:
            if msg.role != MessageRole.ASSISTANT:
                continue
            content = msg.content or ""
            if decision_patterns.search(content):
                # 提取含决策关键词的那一句
                for sentence in re.split(r"[。！\n]", content):
                    sentence = sentence.strip()
                    if sentence and decision_patterns.search(sentence):
                        decisions.append(self._clip(sentence, 80))
                        break
            if len(decisions) >= 5:
                break
        return decisions

    # ── 摘要缓存 ──

    def _load_summary_cache(self, conversation: Any) -> Optional[SummaryCache]:
        """从会话 metadata 加载摘要缓存。"""
        try:
            meta = conversation.metadata or {}
            cache_data = meta.get("_summary_cache")
            if not cache_data or not isinstance(cache_data, dict):
                return None
            return SummaryCache(
                covered_message_count=cache_data.get("covered_message_count", 0),
                covered_tokens=cache_data.get("covered_tokens", 0),
                summary_text=cache_data.get("summary_text", ""),
                topic_skeleton=cache_data.get("topic_skeleton", []),
                key_decisions=cache_data.get("key_decisions", []),
                content_hash=cache_data.get("content_hash", ""),
            )
        except Exception:
            return None

    def _save_summary_cache(self, conversation: Any, cache: SummaryCache) -> None:
        """将摘要缓存写入会话 metadata。"""
        try:
            if not hasattr(conversation, 'metadata') or conversation.metadata is None:
                conversation.metadata = {}
            conversation.metadata["_summary_cache"] = {
                "covered_message_count": cache.covered_message_count,
                "covered_tokens": cache.covered_tokens,
                "summary_text": cache.summary_text,
                "topic_skeleton": cache.topic_skeleton[:10],
                "key_decisions": cache.key_decisions[:5],
                "content_hash": cache.content_hash,
            }
            conversation.updated_at = __import__("datetime").datetime.now().isoformat()
            self.conversation_manager.storage.update_conversation(conversation)
        except Exception as e:
            logger.debug("Failed to save summary cache: %s", e)

    @staticmethod
    def _compute_messages_hash(messages: List[Message]) -> str:
        """计算消息列表的内容 hash，用于判断摘要缓存是否失效。"""
        h = hashlib.md5(usedforsecurity=False)
        for msg in messages:
            h.update(msg.message_id.encode())
        return h.hexdigest()[:12]

    # ── 主题提取 ──

    def _extract_topics(self, messages: List[Message], top_n: int = 5) -> List[str]:
        """改进版主题提取：TF 加权 + 跨消息 IDF 惩罚高频停用词。"""
        doc_count: Dict[str, int] = {}
        term_freq: Counter = Counter()
        total_docs = 0

        for msg in messages:
            terms = set(self._extract_terms(msg.content))
            if not terms:
                continue
            total_docs += 1
            for t in terms:
                doc_count[t] = doc_count.get(t, 0) + 1
                term_freq[t] += 1

        if total_docs == 0:
            return []

        # TF-IDF 式评分：频次高但不是每条消息都出现的词
        import math
        scored: List[Tuple[float, str]] = []
        for term, freq in term_freq.items():
            df = doc_count.get(term, 1)
            # IDF: 如果一个词在所有消息中都出现，权重低
            idf = math.log((total_docs + 1) / (df + 1)) + 0.5
            score = freq * idf
            scored.append((score, term))

        scored.sort(reverse=True)
        return [term for _, term in scored[:top_n]]

    # ── 工具方法（保持兼容） ──

    def _build_retrieval_plan(
        self,
        *,
        user_input: str,
        recent_messages: List[Message],
        conversation_id: str,
        user_id: Optional[str],
        knowledge_base_ids: Optional[List[str]],
        metadata: Dict[str, Any],
        enable_knowledge_retrieval: bool,
        memory_limit: int,
        rag_top_k: int,
    ) -> Dict[str, Any]:
        strategy = str(
            metadata.get("context_strategy")
            or metadata.get("context_retrieval_strategy")
            or "auto"
        ).strip().lower()
        query = " ".join((user_input or "").split())
        recent_user_turns = sum(1 for item in recent_messages if item.role == MessageRole.USER)
        has_recent_assistant = any(item.role == MessageRole.ASSISTANT for item in recent_messages[-3:])
        simple_chat = self._is_simple_chat_turn(query)
        has_memory_cue = bool(self.MEMORY_CUE_PATTERN.search(query))
        has_knowledge_cue = bool(self.KNOWLEDGE_CUE_PATTERN.search(query))
        selected_knowledge_bases = bool(knowledge_base_ids)
        looks_complex = len(query) >= 32 or query.count("?") + query.count(",") + query.count("\n") >= 2
        task_profile: Dict[str, Any] = {}
        if hasattr(self.memory_manager, "build_retrieval_profile"):
            try:
                task_profile = self.memory_manager.build_retrieval_profile(
                    query=query,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    metadata=metadata,
                    memory_limit=memory_limit,
                ) or {}
            except Exception:
                task_profile = {}
        task_type = str(task_profile.get("task_type") or "general")

        use_memory = False
        use_knowledge = False
        reasons: List[str] = []

        if strategy in {"off", "none", "recent_only"}:
            reasons.append("strategy_recent_only")
        elif strategy in {"full", "always", "aggressive"}:
            use_memory = memory_limit > 0
            use_knowledge = enable_knowledge_retrieval and rag_top_k > 0
            reasons.append("strategy_full")
        else:
            if simple_chat and has_recent_assistant:
                reasons.append("simple_followup_recent_context_only")
            else:
                use_memory = memory_limit > 0 and (
                    has_memory_cue
                    or task_type in {"continuation", "preference", "procedural", "troubleshooting"}
                    or (looks_complex and recent_user_turns >= 4)
                    or bool(metadata.get("force_memory_retrieval"))
                )
                use_knowledge = enable_knowledge_retrieval and rag_top_k > 0 and (
                    has_knowledge_cue
                    or (selected_knowledge_bases and not simple_chat)
                    or (looks_complex and len(query) >= 48)
                    or bool(metadata.get("force_knowledge_retrieval"))
                )
                if use_memory:
                    reasons.append("memory_needed")
                if use_knowledge:
                    reasons.append("knowledge_needed")
                if not use_memory and not use_knowledge:
                    reasons.append("recent_context_sufficient")

        planned_memory_limit = 0 if not use_memory else max(1, min(memory_limit, 2 if not has_memory_cue else memory_limit))
        planned_rag_top_k = 0 if not use_knowledge else max(1, min(rag_top_k, 3 if not looks_complex else rag_top_k))

        return {
            "strategy": strategy or "auto",
            "task_type": task_type,
            "use_memory": use_memory,
            "use_knowledge": use_knowledge,
            "memory_limit": planned_memory_limit,
            "working_limit": int(task_profile.get("working_limit", 0) or 0),
            "rag_top_k": planned_rag_top_k,
            "memory_types": list(task_profile.get("memory_types") or []),
            "boost_by_type": dict(task_profile.get("boost_by_type") or {}),
            "retrieval_mode": str(task_profile.get("retrieval_mode") or "balanced"),
            "scopes": list(task_profile.get("scopes") or []),
            "simple_chat": simple_chat,
            "has_memory_cue": has_memory_cue,
            "has_knowledge_cue": has_knowledge_cue,
            "recent_user_turns": recent_user_turns,
            "reason": ", ".join(reasons),
        }

    def _is_simple_chat_turn(self, query: str) -> bool:
        normalized = (query or "").strip().lower()
        if not normalized:
            return True
        if len(normalized) > 24:
            return False
        return any(re.fullmatch(pattern, normalized, flags=re.IGNORECASE) for pattern in self.SIMPLE_CHAT_PATTERNS)

    def _extract_terms(self, text: str) -> List[str]:
        normalized = (text or "").lower()
        parts = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{3,}", normalized)
        stop_terms = {
            "什么", "怎么", "如何", "为什么", "可以", "一下", "这个", "那个", "还是", "就是",
            "已经", "可能", "应该", "需要", "知道", "没有", "please", "about",
        }
        terms: List[str] = []
        seen: set = set()
        for part in parts:
            if part in stop_terms or part in seen:
                continue
            seen.add(part)
            terms.append(part)
        return terms

    def _message_relevance_score(self, content: str, query_terms: set) -> float:
        normalized = (content or "").lower()
        if not normalized:
            return 0.0
        if not query_terms:
            return 0.2
        score = 0.0
        for term in query_terms:
            if term in normalized:
                score += 1.0 if len(term) >= 4 else 0.6
        return score

    @staticmethod
    def _clip(text: str, max_len: int) -> str:
        return ContextBundle._clip(text, max_len)

    # ── 检索（不变） ──

    def _retrieve_memories(
        self,
        query: str,
        conversation_id: str,
        user_id: Optional[str],
        retrieval_plan: Dict[str, Any],
        metadata: Dict[str, Any],
        limit: int,
    ) -> List[RetrievedMemory]:
        if not query.strip() or limit <= 0:
            return []

        try:
            raw_results = self.memory_manager.store.search_memories(
                query=query,
                limit=max(limit * 4, limit),
                similarity_threshold=0.08,
                user_id=user_id,
                scopes=retrieval_plan.get("scopes") or None,
                memory_types=retrieval_plan.get("memory_types") or None,
                boost_by_type=retrieval_plan.get("boost_by_type") or None,
                retrieval_mode=str(retrieval_plan.get("retrieval_mode") or "balanced"),
            )
        except Exception:
            return []

        items: List[RetrievedMemory] = []
        seen_ids: set = set()

        for memory, score in raw_results:
            if memory.id in seen_ids:
                continue

            memory_user_id = (memory.context or {}).get("user_id")
            if user_id and memory_user_id not in (None, "", user_id):
                continue
            if memory.memory_type == "working":
                continue

            items.append(
                RetrievedMemory(
                    memory_id=memory.id,
                    content=memory.content,
                    memory_type=memory.memory_type,
                    score=float(score),
                    tags=list(memory.tags or []),
                    context=dict(memory.context or {}),
                )
            )
            seen_ids.add(memory.id)

            if len(items) >= limit:
                break

        return items

    def _retrieve_working_memories(
        self,
        query: str,
        conversation_id: str,
        user_id: Optional[str],
        retrieval_plan: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> List[RetrievedMemory]:
        limit = int(retrieval_plan.get("working_limit", 0) or 0)
        if limit <= 0:
            return []

        raw_results = []
        if hasattr(self.memory_manager, "get_working_memories"):
            try:
                working_memories = self.memory_manager.get_working_memories(
                    query=query,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    metadata=metadata,
                    limit=limit,
                )
                raw_results = [(memory, getattr(memory, "importance", 0.7)) for memory in working_memories]
            except Exception:
                raw_results = []

        if not raw_results:
            try:
                raw_results = self.memory_manager.store.search_memories(
                    query=query,
                    limit=limit,
                    similarity_threshold=0.05,
                    user_id=user_id,
                    scopes=retrieval_plan.get("scopes") or None,
                    memory_types=["working"],
                    boost_by_type={"working": 1.6},
                    retrieval_mode="recent",
                )
            except Exception:
                raw_results = []

        items: List[RetrievedMemory] = []
        seen_ids: set = set()
        for memory, score in raw_results:
            if memory.id in seen_ids:
                continue
            items.append(
                RetrievedMemory(
                    memory_id=memory.id,
                    content=memory.content,
                    memory_type=memory.memory_type,
                    score=float(score),
                    tags=list(memory.tags or []),
                    context=dict(memory.context or {}),
                )
            )
            seen_ids.add(memory.id)
            if len(items) >= limit:
                break
        return items

    def _retrieve_knowledge(
        self,
        query: str,
        knowledge_base_ids: Optional[List[str]],
        top_k: int,
        retrieval_options: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedKnowledgeChunk]:
        if not query.strip() or top_k <= 0:
            return []

        retrieval_options = retrieval_options or {}
        embedding_endpoint_id = str(retrieval_options.get("embedding_endpoint_id") or "").strip()
        rerank_endpoint_id = str(retrieval_options.get("rerank_endpoint_id") or "").strip()

        if knowledge_base_ids:
            knowledge_bases = [
                knowledge_manager.get_knowledge_base(kb_id)
                for kb_id in knowledge_base_ids
            ]
            knowledge_bases = [kb for kb in knowledge_bases if kb is not None]
        else:
            knowledge_bases = knowledge_manager.list_knowledge_bases()

        if not knowledge_bases:
            return []

        aggregated: List[RetrievedKnowledgeChunk] = []
        per_kb_top_k = max(3, min(max(top_k * 2, 3), 8))

        for kb in knowledge_bases:
            try:
                results = knowledge_manager.search(
                    kb.id,
                    query,
                    top_k=per_kb_top_k,
                    embedding_endpoint_id=embedding_endpoint_id,
                    rerank_endpoint_id=rerank_endpoint_id,
                )
            except Exception:
                continue

            for item in results:
                metadata = dict(item.get("metadata") or {})
                distance = float(item.get("distance", 0.0) or 0.0)
                score = float(
                    item.get(
                        "retrieval_score",
                        item.get("score", max(0.0, 1.0 - distance)),
                    ) or 0.0
                )
                aggregated.append(
                    RetrievedKnowledgeChunk(
                        kb_id=kb.id,
                        kb_name=kb.name,
                        chunk_id=str(item.get("id", "")),
                        content=str(item.get("content", "")),
                        distance=distance,
                        metadata=metadata,
                        snippet=str(item.get("snippet", "") or ""),
                        score=score,
                        retrieval_score=float(item.get("retrieval_score", score) or score),
                        lexical_score=float(item.get("lexical_score", 0.0) or 0.0),
                        vector_score=float(item.get("vector_score", 0.0) or 0.0),
                    )
                )

        aggregated.sort(key=lambda chunk: chunk.distance)

        deduped: List[RetrievedKnowledgeChunk] = []
        seen_keys: set = set()
        doc_counts: Dict[str, int] = {}

        for chunk in aggregated:
            if chunk.score < 0.08:
                continue

            normalized = re.sub(r"\s+", " ", chunk.content.strip().lower())[:220]
            if not normalized:
                continue

            doc_id = str((chunk.metadata or {}).get("doc_id", ""))
            dedup_key = (chunk.kb_id, chunk.chunk_id or normalized)
            if dedup_key in seen_keys or normalized in seen_keys:
                continue

            if doc_id and doc_counts.get(doc_id, 0) >= 2:
                continue

            deduped.append(chunk)
            seen_keys.add(dedup_key)
            seen_keys.add(normalized)
            if doc_id:
                doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

            if len(deduped) >= top_k:
                break

        for idx, chunk in enumerate(deduped, 1):
            chunk.citation_label = chunk.citation_label or f"知识#{idx}"
            chunk.metadata.setdefault("citation_label", chunk.citation_label)

        return deduped
