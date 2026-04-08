"""
RAG Agent 集成
将 RAG 知识库无缝集成到 12-Factor Agent 框架
"""

from typing import Optional, List
from agent_framework.agent import AgentBuilder
from agent_framework.vector_db.rag import RAGKnowledgeBase


class RAGAgent:
    """
    RAG 增强的 Agent
    自动将检索到的上下文注入到 Agent 对话中
    """

    def __init__(
        self,
        builder: AgentBuilder,
        knowledge_base: RAGKnowledgeBase,
        auto_retrieve: bool = True,
        top_k: int = 3,
    ):
        """
        :param builder: AgentBuilder 实例
        :param knowledge_base: RAG 知识库
        :param auto_retrieve: 是否自动检索
        :param top_k: 检索结果数量
        """
        self.builder = builder
        self.kb = knowledge_base
        self.auto_retrieve = auto_retrieve
        self.top_k = top_k

        # 注册 RAG 工具
        self._register_rag_tools()

    def _register_rag_tools(self):
        """注册 RAG 相关工具"""

        @self.builder.tool(description="从知识库检索相关信息")
        def search_knowledge(query: str, top_k: int = None) -> str:
            """
            从知识库检索相关信息

            :param query: 查询文本
            :param top_k: 返回结果数量
            :return: 检索结果
            """
            k = top_k or self.top_k
            return self.kb.get_context(query, top_k=k)

        @self.builder.tool(description="获取知识库统计信息")
        def get_kb_stats() -> str:
            """获取知识库统计信息"""
            stats = self.kb.stats()
            return (
                f"知识库统计:\n"
                f"  文档块数: {stats['total_chunks']}\n"
                f"  词汇量: {stats['vocab_size']}\n"
                f"  来源数: {len(stats['sources'])}"
            )

    def build(self):
        """构建 RAG Agent"""
        return self.builder.build()

    def launch_with_context(self, user_input: str, prefetch_top_k: int = None):
        """
        启动 Agent 并自动注入检索上下文

        :param user_input: 用户输入
        :param prefetch_top_k: 预取检索结果数量
        :return: Thread
        """
        runner = self.build()

        if self.auto_retrieve:
            # 自动检索相关上下文
            k = prefetch_top_k or self.top_k
            context = self.kb.get_context(user_input, top_k=k)

            # 构建预取上下文
            prefetch_context = f"""
<knowledge_base_context>
以下是从知识库检索到的相关信息，请参考这些信息回答用户问题：

{context}
</knowledge_base_context>
"""
            return runner.launch(user_input, prefetch_context=prefetch_context)
        else:
            return runner.launch(user_input)


# ─── 便捷函数 ─────────────────────────────────────────────────────────────────

def create_rag_agent(
    knowledge_base: RAGKnowledgeBase,
    provider: str = "siliconflow",
    model_name: str = "qwen2.5-7b",
    auto_retrieve: bool = True,
    top_k: int = 3,
    **config_overrides,
) -> RAGAgent:
    """
    快速创建 RAG Agent

    :param knowledge_base: RAG 知识库
    :param provider: 模型提供商
    :param model_name: 模型名称
    :param auto_retrieve: 是否自动检索
    :param top_k: 检索结果数量
    :param config_overrides: 配置覆盖参数
    :return: RAGAgent 实例

    示例:
        kb = RAGKnowledgeBase()
        kb.add_directory("./docs")

        rag_agent = create_rag_agent(
            knowledge_base=kb,
            provider="siliconflow",
            model_name="qwen2.5-7b",
            temperature=0.7,
        )

        runner = rag_agent.build()
        thread = rag_agent.launch_with_context("什么是 RAG？")
    """
    from agent_framework.core.config import get_model_config

    config = get_model_config(provider, model_name, **config_overrides)

    builder = AgentBuilder().with_openai(
        api_key=config.api_key,
        model=config.model,
        base_url=config.base_url,
        timeout=config.timeout,
    )

    return RAGAgent(
        builder=builder,
        knowledge_base=knowledge_base,
        auto_retrieve=auto_retrieve,
        top_k=top_k,
    )


def create_rag_kb_from_directory(
    dir_path: str,
    chunk_size: int = 500,
    overlap: int = 50,
    extensions: List[str] = None,
) -> RAGKnowledgeBase:
    """
    从目录快速创建知识库

    :param dir_path: 目录路径
    :param chunk_size: 块大小
    :param overlap: 重叠窗口
    :param extensions: 文件扩展名过滤
    :return: RAGKnowledgeBase 实例

    示例:
        kb = create_rag_kb_from_directory(
            "./docs",
            chunk_size=500,
            extensions=[".md", ".txt"],
        )
    """
    kb = RAGKnowledgeBase(chunk_size=chunk_size, overlap=overlap)
    kb.add_directory(dir_path, extensions=extensions)
    return kb


# ─── RAG 工具注册器 ───────────────────────────────────────────────────────────

def register_rag_tools(
    builder: AgentBuilder,
    knowledge_base: RAGKnowledgeBase,
    top_k: int = 3,
):
    """
    将 RAG 工具注册到现有 AgentBuilder

    :param builder: AgentBuilder 实例
    :param knowledge_base: RAG 知识库
    :param top_k: 默认检索结果数量

    示例:
        builder = AgentBuilder().with_openai(...)

        kb = RAGKnowledgeBase()
        kb.add_directory("./docs")

        register_rag_tools(builder, kb)

        runner = builder.build()
    """

    @builder.tool(description="从知识库检索相关信息")
    def search_knowledge(query: str, top_k_param: int = None) -> str:
        k = top_k_param or top_k
        return knowledge_base.get_context(query, top_k=k)

    @builder.tool(description="获取知识库统计信息")
    def get_kb_stats() -> str:
        stats = knowledge_base.stats()
        return (
            f"知识库统计:\n"
            f"  文档块数: {stats['total_chunks']}\n"
            f"  词汇量: {stats['vocab_size']}\n"
            f"  来源: {', '.join(stats['sources'][:5])}"
        )
