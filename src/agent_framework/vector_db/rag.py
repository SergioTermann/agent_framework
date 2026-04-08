"""
RAG (Retrieval-Augmented Generation) 系统
纯原生实现，零第三方依赖，完全融合 12-Factor Agent 框架

核心特性：
  - 纯 Python 标准库实现
  - 支持多种文档格式（txt, md, json, py, etc）
  - 基于 BM25 的文本检索（词频饱和 + 文档长度归一化）
  - 语义分块与重叠窗口
  - 向量化存储与快速检索
  - 与 Agent 工具系统无缝集成
"""

import agent_framework.core.fast_json as json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from agent_framework.vector_db.reranker import LightweightReranker
from agent_framework.vector_db.retrieval_utils import tokenize, expand_query_tokens, normalize_text

# Rust 加速（可选）
try:
    from agent_framework.vector_db.retrieval_core_ops import (
        rust_fused_score_batch,
        RUST_RETRIEVAL_AVAILABLE,
    )
except ImportError:
    rust_fused_score_batch = None
    RUST_RETRIEVAL_AVAILABLE = False


# ─── 文档分块器 ───────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    """文档块"""
    content: str
    metadata: Dict[str, any] = field(default_factory=dict)
    chunk_id: str = ""
    source: str = ""
    start_pos: int = 0
    end_pos: int = 0


class TextChunker:
    """
    文本分块器
    支持固定大小分块、语义分块、重叠窗口
    """

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        separators: List[str] = None,
    ):
        """
        :param chunk_size: 块大小（字符数）
        :param overlap: 重叠窗口大小
        :param separators: 分隔符优先级列表
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separators = separators or ["\n\n", "\n", "。", ".", " "]

    @staticmethod
    def _extract_section_title(chunk_text: str) -> str:
        lines = [line.strip() for line in (chunk_text or "").splitlines() if line.strip()]
        if not lines:
            return ""

        first_line = re.sub(r"\s+", " ", lines[0]).strip(" -#*\t")
        if not first_line:
            return ""

        if len(first_line) <= 60:
            return first_line[:80]
        return ""

    def chunk_text(self, text: str, source: str = "") -> List[Chunk]:
        """
        将文本分块

        :param text: 输入文本
        :param source: 来源标识
        :return: 块列表
        """
        if not text:
            return []

        chunks = []
        start = 0

        while start < len(text):
            # 确定块结束位置
            end = min(start + self.chunk_size, len(text))

            # 如果不是最后一块，尝试在分隔符处断开
            if end < len(text):
                end = self._find_split_point(text, start, end)

            # 提取块内容
            chunk_text = text[start:end].strip()

            if chunk_text:
                section_title = self._extract_section_title(chunk_text)
                chunk = Chunk(
                    content=chunk_text,
                    chunk_id=f"{source}_{start}_{end}",
                    source=source,
                    start_pos=start,
                    end_pos=end,
                    metadata={
                        "length": len(chunk_text),
                        **({"section_title": section_title} if section_title else {}),
                    },
                )
                chunks.append(chunk)

            # 移动到下一个块（考虑重叠）
            start = end - self.overlap if end < len(text) else end

        return chunks

    def _find_split_point(self, text: str, start: int, end: int) -> int:
        """在合适的分隔符处断开"""
        # 在结束位置附近查找分隔符
        search_start = max(start, end - 100)
        search_text = text[search_start:end]

        for separator in self.separators:
            pos = search_text.rfind(separator)
            if pos != -1:
                return search_start + pos + len(separator)

        return end

    def chunk_code(self, code: str, language: str = "python") -> List[Chunk]:
        """
        代码分块（按函数/类分割）

        :param code: 代码文本
        :param language: 编程语言
        :return: 块列表
        """
        chunks = []

        if language == "python":
            # 简单的 Python 函数/类提取
            pattern = r"(^(?:def|class)\s+\w+.*?(?=^(?:def|class)|\Z))"
            matches = re.finditer(pattern, code, re.MULTILINE | re.DOTALL)

            for i, match in enumerate(matches):
                content = match.group(1).strip()
                chunks.append(
                    Chunk(
                        content=content,
                        chunk_id=f"code_{i}",
                        source="code",
                        metadata={"language": language, "type": "function"},
                    )
                )

        if not chunks:
            # 回退到普通分块
            return self.chunk_text(code, source="code")

        return chunks


# ─── BM25 检索器 ──────────────────────────────────────────────────────────────

class BM25Retriever:
    """
    基于 BM25 的文本检索器
    纯 Python 实现，带词频饱和与文档长度归一化。
    支持增量索引 — add_documents() 仅处理新增 chunk。
    """

    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b

        self.documents: List[Chunk] = []
        self.vocab: Set[str] = set()
        self.idf: Dict[str, float] = {}

        # 增量索引结构
        self._doc_lengths: List[int] = []
        self._doc_term_freqs: List[Counter] = []
        self._doc_freqs: Dict[str, int] = defaultdict(int)
        self._inverted_index: Dict[str, Set[int]] = defaultdict(set)
        self._total_token_count: int = 0
        self._avgdl: float = 0.0
        self._indexed_count: int = 0

    def add_documents(self, chunks: List[Chunk]):
        """增量添加文档到索引 — 仅处理新增 chunk，O(new)"""
        if not chunks:
            return

        base_idx = len(self.documents)
        self.documents.extend(chunks)

        for offset, chunk in enumerate(chunks):
            doc_idx = base_idx + offset
            tokens = tokenize(chunk.content, include_numbers=True)
            term_freq = Counter(tokens)
            self._doc_term_freqs.append(term_freq)
            self._doc_lengths.append(len(tokens))
            self._total_token_count += len(tokens)

            for term in term_freq:
                self._doc_freqs[term] += 1
                self._inverted_index[term].add(doc_idx)
                self.vocab.add(term)

        self._indexed_count = len(self.documents)

        # 重算 avgdl 和 IDF — O(vocab) 轻量操作
        self._avgdl = self._total_token_count / max(1, self._indexed_count)
        self._rebuild_idf()

    def _rebuild_idf(self):
        """重算所有 IDF 值"""
        n = self._indexed_count
        self.idf = {
            term: max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1))
            for term, df in self._doc_freqs.items()
        }

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Chunk, float]]:
        """
        检索相关文档

        :param query: 查询文本
        :param top_k: 返回前 k 个结果
        :return: [(chunk, score), ...]
        """
        if not self.documents:
            return []

        query_tokens = expand_query_tokens(query, include_numbers=True)
        query_freq = Counter(query_tokens)
        unique_query_tokens = query_freq.keys()  # KeysView — O(1)，无需 set(tuple)

        # 通过倒排索引收集候选文档
        candidate_indices: Set[int] = set()
        for token in unique_query_tokens:
            posting = self._inverted_index.get(token)
            if posting:
                candidate_indices.update(posting)

        if not candidate_indices:
            return []

        # Rust 加速路径：单次遍历同时算 BM25 + lexical
        if RUST_RETRIEVAL_AVAILABLE and rust_fused_score_batch is not None:
            rust_result = self._search_rust(
                query_tokens, query_freq, candidate_indices
            )
            if rust_result is not None:
                rust_result.sort(key=lambda x: x[1], reverse=True)
                return rust_result[:top_k]

        # Python 回退路径
        return self._search_python(
            unique_query_tokens, query_freq, candidate_indices, top_k
        )

    def _search_rust(
        self,
        query_tokens: Tuple,
        query_freq: Counter,
        candidate_indices: Set[int],
    ) -> Optional[List[Tuple[Chunk, float]]]:
        """Rust 加速的融合评分路径"""
        candidate_list = list(candidate_indices)
        query_total = sum(query_freq.values())
        unique_tokens = list(query_freq.keys())  # Counter.keys() 即去重 tokens

        result = rust_fused_score_batch(
            self._doc_term_freqs,  # Counter 继承 dict，PyO3 可直接提取
            self._doc_lengths,
            self.idf,
            unique_tokens,
            query_freq,  # Counter 即 dict，无需 dict() 转换
            query_total,
            candidate_list,
            self.k1,
            self.b,
            self._avgdl,
        )

        if result is None:
            return None

        # result: [(doc_idx, fused_score, bm25_raw, lexical_score), ...]
        # 归一化 BM25 并融合
        max_bm25 = max((r[2] for r in result), default=0.0)
        scores = []
        for doc_idx, _, bm25_raw, lexical_score in result:
            bm25_norm = bm25_raw / max_bm25 if max_bm25 > 0 else 0.0
            score = max(lexical_score, 0.82 * lexical_score + 0.18 * bm25_norm)
            if lexical_score <= 0.0 and score < 0.12:
                continue
            if score <= 0.03:
                continue
            scores.append((self.documents[doc_idx], score))

        return scores

    def _search_python(
        self,
        unique_query_tokens: Set[str],
        query_freq: Counter,
        candidate_indices: Set[int],
        top_k: int,
    ) -> List[Tuple[Chunk, float]]:
        """纯 Python 评分路径"""
        raw_scores: Dict[int, float] = {}
        max_bm25 = 0.0

        for i in candidate_indices:
            bm25 = self._bm25_score(unique_query_tokens, i)
            raw_scores[i] = bm25
            if bm25 > max_bm25:
                max_bm25 = bm25

        scores = []
        for i, bm25_raw in raw_scores.items():
            bm25_norm = bm25_raw / max_bm25 if max_bm25 > 0 else 0.0
            lexical_score = self._lexical_score_indexed(query_freq, i)
            score = max(lexical_score, 0.82 * lexical_score + 0.18 * bm25_norm)
            if lexical_score <= 0.0 and score < 0.12:
                continue
            if score <= 0.03:
                continue
            scores.append((self.documents[i], score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _bm25_score(self, unique_query_tokens: Set[str], doc_idx: int) -> float:
        """计算单篇文档的 BM25 分数"""
        term_freq = self._doc_term_freqs[doc_idx]
        dl = self._doc_lengths[doc_idx]
        score = 0.0

        for token in unique_query_tokens:
            tf = term_freq.get(token, 0)
            if tf <= 0:
                continue
            idf = self.idf.get(token, 0.0)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * dl / max(1.0, self._avgdl))
            score += idf * numerator / denominator

        return score

    def _lexical_score_indexed(self, query_freq: Counter, doc_idx: int) -> float:
        """利用已索引的 term_freq 计算词面匹配分数，避免重复分词"""
        content_freq = self._doc_term_freqs[doc_idx]
        doc_len = self._doc_lengths[doc_idx]
        if not query_freq or doc_len == 0:
            return 0.0

        overlap = sum(min(freq, content_freq.get(token, 0)) for token, freq in query_freq.items())
        if overlap <= 0:
            return 0.0

        coverage = overlap / max(1, sum(query_freq.values()))
        density = overlap / max(1, doc_len)
        return max(0.0, min(1.0, 0.72 * coverage + 0.28 * min(1.0, density * 8)))


# 向后兼容
TFIDFRetriever = BM25Retriever


# ─── 文档加载器 ───────────────────────────────────────────────────────────────

class DocumentLoader:
    """文档加载器，支持多种格式"""

    @staticmethod
    def load_file(file_path: str) -> str:
        """
        加载文件内容

        :param file_path: 文件路径
        :return: 文件内容
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 根据扩展名选择加载方式
        ext = path.suffix.lower()

        if ext in [".txt", ".md", ".py", ".js", ".java", ".go", ".rs"]:
            return DocumentLoader._load_text(path)
        elif ext == ".json":
            return DocumentLoader._load_json(path)
        else:
            # 尝试作为文本加载
            try:
                return DocumentLoader._load_text(path)
            except Exception:
                raise ValueError(f"不支持的文件格式: {ext}")

    @staticmethod
    def _load_text(path: Path) -> str:
        """加载文本文件"""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    @staticmethod
    def _load_json(path: Path) -> str:
        """加载 JSON 文件"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 将 JSON 转换为可读文本
            return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def load_directory(
        dir_path: str,
        extensions: List[str] = None,
        recursive: bool = True,
    ) -> Dict[str, str]:
        """
        加载目录下的所有文件

        :param dir_path: 目录路径
        :param extensions: 文件扩展名过滤
        :param recursive: 是否递归
        :return: {file_path: content}
        """
        extensions = extensions or [".txt", ".md", ".py", ".json"]
        documents = {}

        path = Path(dir_path)
        if not path.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")

        # 遍历文件
        pattern = "**/*" if recursive else "*"
        for file_path in path.glob(pattern):
            if file_path.is_file() and file_path.suffix in extensions:
                try:
                    content = DocumentLoader.load_file(str(file_path))
                    documents[str(file_path)] = content
                except Exception as e:
                    print(f"加载文件失败 {file_path}: {e}")

        return documents


# ─── RAG 知识库 ───────────────────────────────────────────────────────────────

class RAGKnowledgeBase:
    """
    RAG 知识库
    整合文档加载、分块、索引、检索
    """

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        top_k: int = 5,
    ):
        """
        :param chunk_size: 块大小
        :param overlap: 重叠窗口
        :param top_k: 默认返回结果数
        """
        self.chunker = TextChunker(chunk_size=chunk_size, overlap=overlap)
        self.retriever = BM25Retriever()
        self.reranker = LightweightReranker()
        self.top_k = top_k
        self.metadata: Dict[str, any] = {}

    def add_text(self, text: str, source: str = "text", metadata: Dict = None):
        """
        添加文本到知识库

        :param text: 文本内容
        :param source: 来源标识
        :param metadata: 元数据
        """
        chunks = self.chunker.chunk_text(text, source=source)

        # 添加元数据
        if metadata:
            for chunk in chunks:
                chunk.metadata.update(metadata)

        self.retriever.add_documents(chunks)

    def add_file(self, file_path: str, metadata: Dict = None):
        """
        添加文件到知识库

        :param file_path: 文件路径
        :param metadata: 元数据
        """
        content = DocumentLoader.load_file(file_path)
        source = Path(file_path).name

        # 代码文件特殊处理
        ext = Path(file_path).suffix
        if ext in [".py", ".js", ".java", ".go"]:
            chunks = self.chunker.chunk_code(content, language=ext[1:])
        else:
            chunks = self.chunker.chunk_text(content, source=source)

        # 添加元数据
        file_metadata = {"file_path": file_path, "file_type": ext}
        if metadata:
            file_metadata.update(metadata)

        for chunk in chunks:
            chunk.metadata.update(file_metadata)

        self.retriever.add_documents(chunks)

    def add_directory(
        self,
        dir_path: str,
        extensions: List[str] = None,
        recursive: bool = True,
    ):
        """
        添加目录到知识库

        :param dir_path: 目录路径
        :param extensions: 文件扩展名过滤
        :param recursive: 是否递归
        """
        documents = DocumentLoader.load_directory(
            dir_path, extensions=extensions, recursive=recursive
        )

        for file_path, content in documents.items():
            try:
                self.add_file(file_path)
            except Exception as e:
                print(f"添加文件失败 {file_path}: {e}")

    def search(self, query: str, top_k: int = None) -> List[Tuple[Chunk, float]]:
        """
        检索相关文档

        :param query: 查询文本
        :param top_k: 返回结果数
        :return: [(chunk, score), ...]
        """
        k = top_k or self.top_k
        initial_results = self.retriever.search(query, top_k=k * 2)
        if not initial_results:
            return []

        reranked: List[Tuple[Chunk, float]] = []
        for chunk, retrieval_score in initial_results:
            rerank_payload = self.reranker.score(
                query=query,
                snippet=chunk.content,
                content=chunk.content,
                metadata=chunk.metadata,
                retrieval_prior=retrieval_score,
                lexical_score=retrieval_score,
                vector_score=0.0,
            )
            final_score = float(rerank_payload.get("final_score", retrieval_score) or retrieval_score)
            chunk.metadata = {
                **dict(chunk.metadata or {}),
                "reranker_score": round(final_score, 6),
                "rerank_features": rerank_payload,
            }
            reranked.append((chunk, final_score))

        reranked.sort(key=lambda item: item[1], reverse=True)
        return reranked[:k]

    def get_context(self, query: str, top_k: int = None) -> str:
        """
        获取检索上下文（格式化为字符串）

        :param query: 查询文本
        :param top_k: 返回结果数
        :return: 格式化的上下文文本
        """
        results = self.search(query, top_k=top_k)

        if not results:
            return "未找到相关内容"

        context_parts = []
        for i, (chunk, score) in enumerate(results, 1):
            section_title = str((chunk.metadata or {}).get("section_title", "") or "").strip()
            header = f"[知识#{i}] 来源: {chunk.source} | 相关度: {score:.3f}"
            if section_title:
                header += f" | 小节: {section_title}"
            context_parts.append(header)
            context_parts.append(f"内容:\n{chunk.content}")
            context_parts.append("")

        return "\n".join(context_parts)

    def save(self, file_path: str):
        """保存知识库到文件"""
        data = {
            "chunks": [
                {
                    "content": chunk.content,
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "metadata": chunk.metadata,
                }
                for chunk in self.retriever.documents
            ],
            "metadata": self.metadata,
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, file_path: str):
        """从文件加载知识库"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chunks = [
            Chunk(
                content=c["content"],
                chunk_id=c["chunk_id"],
                source=c["source"],
                metadata=c["metadata"],
            )
            for c in data["chunks"]
        ]

        self.retriever.add_documents(chunks)
        self.metadata = data.get("metadata", {})

    def stats(self) -> Dict[str, any]:
        """获取知识库统计信息"""
        return {
            "total_chunks": len(self.retriever.documents),
            "vocab_size": len(self.retriever.vocab),
            "sources": list(set(c.source for c in self.retriever.documents)),
        }
