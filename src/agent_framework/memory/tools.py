"""
记忆工具集 - 为Agent添加记忆相关的工具
"""

from typing import Dict, Any, List
import agent_framework.core.fast_json as json
from datetime import datetime

from agent_framework.memory.system import get_memory_manager, get_file_memory_layer
from agent_framework.memory.enhanced_agent import MemoryTools

# 记忆类型中文映射
MEMORY_TYPE_NAMES = {
    'episodic': '情节记忆',
    'semantic': '语义记忆',
    'procedural': '程序性记忆',
    'working': '工作记忆',
}

class MemoryToolsRegistry:
    """记忆工具注册器"""

    @staticmethod
    def register_memory_tools(builder):
        """为AgentBuilder注册记忆相关工具"""

        @builder.tool(description="保存重要信息到永久记忆，类型可选：episodic(情节), semantic(语义), procedural(程序性)")
        def save_memory(content: str, memory_type: str = "semantic", importance: str = "0.5", tags: str = "") -> str:
            """保存记忆到永久存储"""
            try:
                memory_manager = get_memory_manager()

                # 解析参数
                importance_val = float(importance) if importance else 0.5
                tags_list = [tag.strip() for tag in tags.split(',') if tag.strip()] if tags else []

                # 构建上下文
                context = {
                    'source': 'agent_tool',
                    'timestamp': datetime.now().isoformat(),
                    'auto_saved': True
                }

                # 根据类型保存记忆
                if memory_type == "episodic":
                    memory_id = memory_manager.add_episodic_memory(
                        content=content,
                        context=context,
                        importance=importance_val,
                        tags=tags_list
                    )
                elif memory_type == "semantic":
                    memory_id = memory_manager.add_semantic_memory(
                        content=content,
                        context=context,
                        importance=importance_val,
                        tags=tags_list
                    )
                elif memory_type == "procedural":
                    memory_id = memory_manager.add_procedural_memory(
                        content=content,
                        context=context,
                        importance=importance_val,
                        tags=tags_list
                    )
                else:
                    return f"错误：不支持的记忆类型 '{memory_type}'。支持的类型：episodic, semantic, procedural"

                return f"✅ 记忆已保存！\n记忆ID: {memory_id}\n类型: {memory_type}\n重要性: {importance_val}"

            except Exception as e:
                return f"❌ 保存记忆失败: {str(e)}"

        @builder.tool(description="搜索相关记忆，可指定记忆类型和相似度阈值")
        def search_memory(query: str, memory_type: str = "", limit: str = "5", threshold: str = "0.3") -> str:
            """搜索相关记忆"""
            try:
                memory_manager = get_memory_manager()

                # 解析参数
                limit_val = int(limit) if limit else 5
                threshold_val = float(threshold) if threshold else 0.3
                memory_type_val = memory_type if memory_type else None

                # 搜索记忆
                results = memory_manager.store.search_memories(
                    query=query,
                    memory_type=memory_type_val,
                    limit=limit_val,
                    similarity_threshold=threshold_val
                )

                if not results:
                    return f"🔍 未找到与 '{query}' 相关的记忆"

                # 格式化结果
                output = [f"🧠 找到 {len(results)} 条相关记忆：\n"]

                for i, (memory, score) in enumerate(results, 1):
                    memory_type_name = MEMORY_TYPE_NAMES.get(memory.memory_type, memory.memory_type)

                    output.append(f"{i}. [{memory_type_name}] (相似度: {score:.3f})")
                    output.append(f"   内容: {memory.content}")
                    output.append(f"   标签: {', '.join(memory.tags) if memory.tags else '无'}")
                    output.append(f"   创建时间: {memory.created_at.strftime('%Y-%m-%d %H:%M')}")
                    output.append("")

                return "\n".join(output)

            except Exception as e:
                return f"❌ 搜索记忆失败: {str(e)}"

        @builder.tool(description="回忆与当前对话相关的记忆")
        def recall_memory(context_info: str, limit: str = "3") -> str:
            """智能回忆相关记忆"""
            try:
                memory_manager = get_memory_manager()

                # 解析参数
                limit_val = int(limit) if limit else 3

                # 构建上下文
                context = {
                    'conversation_context': context_info,
                    'recall_time': datetime.now().isoformat()
                }

                # 回忆记忆
                memories = memory_manager.recall_relevant_memories(
                    query=context_info,
                    context=context,
                    limit=limit_val
                )

                if not memories:
                    return f"🤔 暂无与当前对话相关的记忆"

                # 格式化结果
                output = [f"💭 回忆起 {len(memories)} 条相关记忆：\n"]

                for i, memory in enumerate(memories, 1):
                    memory_type_name = MEMORY_TYPE_NAMES.get(memory.memory_type, memory.memory_type)

                    output.append(f"{i}. [{memory_type_name}] (重要性: {memory.importance:.2f})")
                    output.append(f"   {memory.content}")
                    output.append(f"   访问次数: {memory.access_count} | 最后访问: {memory.last_accessed.strftime('%m-%d %H:%M')}")
                    output.append("")

                return "\n".join(output)

            except Exception as e:
                return f"❌ 回忆记忆失败: {str(e)}"

        @builder.tool(description="获取记忆系统统计信息")
        def memory_stats() -> str:
            """获取记忆统计"""
            try:
                memory_manager = get_memory_manager()
                stats = memory_manager.get_memory_statistics()

                if not stats:
                    return "📊 记忆系统暂无数据"

                output = ["📊 记忆系统统计：\n"]

                total_memories = sum(stat.get('count', 0) for stat in stats.values())
                output.append(f"总记忆数: {total_memories}")
                output.append("")

                for memory_type, stat in stats.items():
                    type_name = {
                        'episodic': '情节记忆',
                        'semantic': '语义记忆',
                        'procedural': '程序性记忆',
                        'working': '工作记忆'
                    }.get(memory_type, memory_type)

                    count = stat.get('count', 0)
                    avg_importance = stat.get('avg_importance', 0)
                    avg_access = stat.get('avg_access_count', 0)

                    output.append(f"{type_name}:")
                    output.append(f"  数量: {count}")
                    output.append(f"  平均重要性: {avg_importance:.2f}")
                    output.append(f"  平均访问次数: {avg_access:.1f}")
                    output.append("")

                return "\n".join(output)

            except Exception as e:
                return f"❌ 获取统计信息失败: {str(e)}"

        @builder.tool(description="创建记忆快照备份")
        def create_memory_snapshot(description: str = "手动创建的快照") -> str:
            """创建记忆快照"""
            try:
                context = {
                    'description': description,
                    'created_by': 'agent_tool',
                    'creation_time': datetime.now().isoformat()
                }

                snapshot_id = MemoryTools.create_memory_snapshot(
                    agent_id='agent_session',
                    context=context
                )

                return f"📸 记忆快照创建成功！\n快照ID: {snapshot_id}\n描述: {description}"

            except Exception as e:
                return f"❌ 创建快照失败: {str(e)}"

        @builder.tool(description="导出记忆数据，可指定过滤条件")
        def export_memories(query: str = "", memory_type: str = "") -> str:
            """导出记忆数据"""
            try:
                filter_criteria = {}
                if query:
                    filter_criteria['query'] = query
                if memory_type:
                    filter_criteria['memory_type'] = memory_type

                filepath = MemoryTools.export_memories(filter_criteria)

                return f"📤 记忆数据导出成功！\n文件路径: {filepath}\n过滤条件: {filter_criteria or '无'}"

            except Exception as e:
                return f"❌ 导出记忆失败: {str(e)}"

        # ── 三层记忆架构：每日笔记 + MEMORY.md 工具 ──────────────────────────

        @builder.tool(description="查看最近的每日笔记，可指定天数(默认2天)")
        def view_daily_notes(days: str = "2") -> str:
            """查看最近每日笔记"""
            try:
                file_memory = get_file_memory_layer()
                days_val = int(days) if days else 2
                content = file_memory.load_daily_notes(days=days_val)

                if not content.strip():
                    return "📓 最近没有每日笔记"

                return f"📓 最近 {days_val} 天的每日笔记：\n\n{content}"

            except Exception as e:
                return f"❌ 查看每日笔记失败: {str(e)}"

        @builder.tool(description="添加一条今日笔记")
        def add_daily_note(content: str) -> str:
            """添加今日笔记"""
            try:
                if not content or len(content.strip()) < 5:
                    return "❌ 笔记内容太短，请至少输入5个字符"

                file_memory = get_file_memory_layer()
                file_path = file_memory.append_daily_note(content)

                return f"📝 笔记已添加到今日笔记\n文件: {file_path}"

            except Exception as e:
                return f"❌ 添加笔记失败: {str(e)}"

        @builder.tool(description="查看长期记忆(MEMORY.md)内容")
        def view_long_term_memory() -> str:
            """查看 MEMORY.md"""
            try:
                file_memory = get_file_memory_layer()
                content = file_memory.load_memory_md()

                if not content.strip():
                    return "📋 MEMORY.md 暂无内容"

                return f"📋 长期记忆 (MEMORY.md)：\n\n{content}"

            except Exception as e:
                return f"❌ 查看长期记忆失败: {str(e)}"

        @builder.tool(description="更新长期记忆(MEMORY.md)的指定章节")
        def update_long_term_memory(section: str, content: str) -> str:
            """更新 MEMORY.md 指定章节"""
            try:
                if not section or not content:
                    return "❌ 请提供章节名和内容"

                file_memory = get_file_memory_layer()
                file_memory.update_memory_md(section, content)

                return f"✅ MEMORY.md 章节 \"{section}\" 已更新"

            except Exception as e:
                return f"❌ 更新长期记忆失败: {str(e)}"

        return builder

def enhance_agent_session_with_memory(session_class):
    """为AgentSession添加记忆增强功能"""

    class MemoryEnhancedSession(session_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.memory_manager = get_memory_manager()

        def create_agent(self):
            """创建带记忆功能的Agent"""
            builder = super().create_agent_builder() if hasattr(super(), 'create_agent_builder') else None

            if builder is None:
                # 如果没有builder方法，使用原始的create_agent
                agent = super().create_agent()
                return agent

            # 注册记忆工具
            builder = MemoryToolsRegistry.register_memory_tools(builder)

            return builder.build()

        def _on_agent_complete(self, final_result: str, user_input: str):
            """Agent完成时自动保存重要交互到记忆"""
            try:
                # 保存用户输入
                self.memory_manager.add_episodic_memory(
                    content=f"用户提问: {user_input}",
                    context={
                        'session_id': self.session_id,
                        'type': 'user_input',
                        'timestamp': datetime.now().isoformat()
                    },
                    importance=0.6,
                    tags=['user_input', 'conversation']
                )

                # 保存Agent响应
                if final_result and len(final_result) > 20:  # 只保存有意义的响应
                    self.memory_manager.add_procedural_memory(
                        content=f"Agent回答: {final_result[:500]}...",  # 截取前500字符
                        context={
                            'session_id': self.session_id,
                            'type': 'agent_response',
                            'user_input': user_input,
                            'timestamp': datetime.now().isoformat()
                        },
                        importance=0.7,
                        tags=['agent_response', 'conversation']
                    )

            except Exception as e:
                print(f"自动保存记忆失败: {e}")

    return MemoryEnhancedSession