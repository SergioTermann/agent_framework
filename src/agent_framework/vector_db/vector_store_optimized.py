"""
优化的向量存储 - 集成高性能向量计算
"""

from agent_framework.vector_db.vector_store import *
from agent_framework.vector_db.vector_ops_optimized import OptimizedVectorOps

# 创建全局优化实例
_vector_ops = OptimizedVectorOps(use_multiprocessing=False)


class OptimizedSimpleVectorStore:
    """
    优化的简单向量存储
    使用 NumPy 加速的向量计算
    """

    def __init__(self, embedding_model: Optional[EmbeddingModel] = None):
        self.embedding_model = embedding_model or SimpleEmbeddingModel()
        self.documents: List[Document] = []
        self.embeddings: List[List[float]] = []

    def add_document(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """添加文档"""
        doc_id = str(uuid.uuid4())
        embedding = self.embedding_model.embed_text(content)

        doc = Document(
            doc_id=doc_id,
            content=content,
            metadata=metadata or {},
            embedding=embedding
        )

        self.documents.append(doc)
        self.embeddings.append(embedding)

        return doc_id

    def add_documents(self, contents: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """批量添加文档（优化版）"""
        # 批量向量化
        embeddings = self.embedding_model.embed_batch(contents)

        doc_ids = []
        for i, (content, embedding) in enumerate(zip(contents, embeddings)):
            doc_id = str(uuid.uuid4())
            metadata = metadatas[i] if metadatas and i < len(metadatas) else {}

            doc = Document(
                doc_id=doc_id,
                content=content,
                metadata=metadata,
                embedding=embedding
            )

            self.documents.append(doc)
            self.embeddings.append(embedding)
            doc_ids.append(doc_id)

        return doc_ids

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        搜索相似文档（优化版）

        使用高性能向量计算
        """
        if not self.documents:
            return []

        # 向量化查询
        query_embedding = self.embedding_model.embed_text(query)

        # 过滤文档
        if filter_metadata:
            filtered_indices = [
                i for i, doc in enumerate(self.documents)
                if all(doc.metadata.get(k) == v for k, v in filter_metadata.items())
            ]
            filtered_embeddings = [self.embeddings[i] for i in filtered_indices]
            filtered_docs = [self.documents[i] for i in filtered_indices]
        else:
            filtered_embeddings = self.embeddings
            filtered_docs = self.documents
            filtered_indices = list(range(len(self.documents)))

        if not filtered_embeddings:
            return []

        # 使用优化的 Top-K 搜索
        top_results = _vector_ops.top_k_similar(
            filtered_embeddings,
            query_embedding,
            min(top_k, len(filtered_embeddings))
        )

        # 构建搜索结果
        results = []
        for rank, (idx, score) in enumerate(top_results, 1):
            results.append(SearchResult(
                document=filtered_docs[idx],
                score=score,
                rank=rank
            ))

        return results

    def get_document(self, doc_id: str) -> Optional[Document]:
        """获取文档"""
        for doc in self.documents:
            if doc.doc_id == doc_id:
                return doc
        return None

    def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        for i, doc in enumerate(self.documents):
            if doc.doc_id == doc_id:
                del self.documents[i]
                del self.embeddings[i]
                return True
        return False

    def update_document(
        self,
        doc_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新文档"""
        for i, doc in enumerate(self.documents):
            if doc.doc_id == doc_id:
                if content is not None:
                    doc.content = content
                    doc.embedding = self.embedding_model.embed_text(content)
                    self.embeddings[i] = doc.embedding

                if metadata is not None:
                    doc.metadata.update(metadata)

                return True
        return False

    def count(self) -> int:
        """文档数量"""
        return len(self.documents)

    def clear(self):
        """清空所有文档"""
        self.documents.clear()
        self.embeddings.clear()

    def save(self, path: str):
        """保存到文件"""
        data = {
            'documents': [
                {
                    'doc_id': doc.doc_id,
                    'content': doc.content,
                    'metadata': doc.metadata,
                    'embedding': doc.embedding
                }
                for doc in self.documents
            ]
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        """从文件加载"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.documents.clear()
        self.embeddings.clear()

        for doc_data in data['documents']:
            doc = Document(
                doc_id=doc_data['doc_id'],
                content=doc_data['content'],
                metadata=doc_data['metadata'],
                embedding=doc_data['embedding']
            )
            self.documents.append(doc)
            self.embeddings.append(doc.embedding)


# 便捷函数
def create_optimized_vector_store(embedding_model: Optional[EmbeddingModel] = None) -> OptimizedSimpleVectorStore:
    """创建优化的向量存储"""
    return OptimizedSimpleVectorStore(embedding_model)
