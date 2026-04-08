"""
记忆增强Agent - 为现有Agent添加永久记忆能力
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import agent_framework.core.fast_json as json
import logging

from agent_framework.memory.system import get_memory_manager, Memory

logger = logging.getLogger(__name__)

class MemoryEnhancedAgent:
    """记忆增强Agent包装器"""

    def __init__(self, base_agent, memory_config: Dict[str, Any] = None):
        self.base_agent = base_agent
        self.memory_manager = get_memory_manager()
        self.config = memory_config or {}

        # 记忆配置
        self.auto_memory = self.config.get('auto_memory', True)
        self.memory_threshold = self.config.get('memory_threshold', 0.5)
        self.max_context_memories = self.config.get('max_context_memories', 5)

    def process_with_memory(self, user_input: str, context: Dict[str, Any] = None) -> str:
        """带记忆的处理流程"""
        try:
            # 1. 回忆相关记忆
            relevant_memories = self._recall_memories(user_input, context)

            # 2. 构建增强上下文
            enhanced_context = self._build_enhanced_context(
                user_input, context, relevant_memories
            )

            # 3. 调用基础Agent处理
            response = self.base_agent.process(user_input, enhanced_context)

            # 4. 自动记录重要交互
            if self.auto_memory:
                self._auto_record_interaction(user_input, response, context)

            return response

        except Exception as e:
            logger.error(f"记忆增强处理失败: {str(e)}")
            # 降级到基础Agent
            return self.base_agent.process(user_input, context)

    def _recall_memories(self, query: str, context: Dict[str, Any] = None) -> List[Memory]:
        """回忆相关记忆"""
        try:
            memories = self.memory_manager.recall_relevant_memories(
                query=query,
                context=context,
                limit=self.max_context_memories
            )

            logger.info(f"回忆到 {len(memories)} 条相关记忆")
            return memories

        except Exception as e:
            logger.error(f"回忆记忆失败: {str(e)}")
            return []

    def _build_enhanced_context(self, user_input: str, context: Dict[str, Any],
                               memories: List[Memory]) -> Dict[str, Any]:
        """构建增强上下文"""
        enhanced_context = context.copy() if context else {}

        if memories:
            # 添加记忆信息到上下文
            memory_context = {
                'relevant_memories': [],
                'memory_summary': self._summarize_memories(memories)
            }

            for memory in memories:
                memory_context['relevant_memories'].append({
                    'content': memory.content,
                    'type': memory.memory_type,
                    'importance': memory.importance,
                    'tags': memory.tags,
                    'created_at': memory.created_at.isoformat()
                })

            enhanced_context['memory_context'] = memory_context

        return enhanced_context

    def _summarize_memories(self, memories: List[Memory]) -> str:
        """总结记忆内容"""
        if not memories:
            return "无相关记忆"

        summary_parts = []

        # 按类型分组
        memory_types = {}
        for memory in memories:
            if memory.memory_type not in memory_types:
                memory_types[memory.memory_type] = []
            memory_types[memory.memory_type].append(memory)

        # 生成摘要
        for mem_type, mems in memory_types.items():
            type_name = {
                'episodic': '情节记忆',
                'semantic': '语义记忆',
                'procedural': '程序性记忆',
                'working': '工作记忆'
            }.get(mem_type, mem_type)

            summary_parts.append(f"{type_name}: {len(mems)}条")

        return f"相关记忆摘要 - {', '.join(summary_parts)}"

    def _auto_record_interaction(self, user_input: str, response: str,
                                context: Dict[str, Any] = None):
        """自动记录交互"""
        try:
            # 判断是否值得记录
            if not self._should_record(user_input, response):
                return

            # 记录用户输入（情节记忆）
            self.memory_manager.add_episodic_memory(
                content=f"用户输入: {user_input}",
                context={
                    'type': 'user_input',
                    'timestamp': datetime.now().isoformat(),
                    'context': context or {}
                },
                importance=self._calculate_importance(user_input),
                tags=['user_input', 'interaction']
            )

            # 记录Agent响应（程序性记忆）
            self.memory_manager.add_procedural_memory(
                content=f"Agent响应: {response}",
                context={
                    'type': 'agent_response',
                    'user_input': user_input,
                    'timestamp': datetime.now().isoformat(),
                    'context': context or {}
                },
                importance=self._calculate_importance(response),
                tags=['agent_response', 'interaction']
            )

            logger.info("自动记录交互完成")

        except Exception as e:
            logger.error(f"自动记录交互失败: {str(e)}")

    def _should_record(self, user_input: str, response: str) -> bool:
        """判断是否应该记录"""
        # 简单的启发式规则
        if len(user_input) < 10 or len(response) < 10:
            return False

        # 排除简单的问候语
        greetings = ['你好', 'hello', 'hi', '谢谢', 'thank you']
        if any(greeting in user_input.lower() for greeting in greetings):
            return False

        return True

    def _calculate_importance(self, text: str) -> float:
        """计算重要性评分"""
        # 基于文本长度和关键词的简单评分
        base_score = min(len(text) / 200, 0.5)  # 基础分数

        # 关键词加权
        important_keywords = [
            '重要', '关键', '问题', '错误', '解决', '方案',
            '配置', '设置', '部署', '优化', '性能'
        ]

        keyword_score = 0
        for keyword in important_keywords:
            if keyword in text:
                keyword_score += 0.1

        return min(base_score + keyword_score, 1.0)

class MemoryTools:
    """记忆系统工具集"""

    @staticmethod
    def create_memory_snapshot(agent_id: str, context: Dict[str, Any]) -> str:
        """创建记忆快照"""
        try:
            memory_manager = get_memory_manager()

            # 获取Agent相关的所有记忆
            memories = memory_manager.store.search_memories(
                query=agent_id,
                limit=100
            )

            snapshot = {
                'agent_id': agent_id,
                'timestamp': datetime.now().isoformat(),
                'context': context,
                'memories': [memory.to_dict() for memory, _ in memories]
            }

            # 保存快照
            snapshot_id = memory_manager.add_semantic_memory(
                content=f"记忆快照: {agent_id}",
                context=snapshot,
                importance=0.8,
                tags=['snapshot', 'backup', agent_id]
            )

            logger.info(f"创建记忆快照: {snapshot_id}")
            return snapshot_id

        except Exception as e:
            logger.error(f"创建记忆快照失败: {str(e)}")
            raise

    @staticmethod
    def restore_memory_snapshot(snapshot_id: str) -> Dict[str, Any]:
        """恢复记忆快照"""
        try:
            memory_manager = get_memory_manager()
            snapshot_memory = memory_manager.store.retrieve_memory(snapshot_id)

            if not snapshot_memory:
                raise ValueError(f"快照不存在: {snapshot_id}")

            snapshot_data = snapshot_memory.context
            logger.info(f"恢复记忆快照: {snapshot_id}")

            return snapshot_data

        except Exception as e:
            logger.error(f"恢复记忆快照失败: {str(e)}")
            raise

    @staticmethod
    def export_memories(filter_criteria: Dict[str, Any] = None) -> str:
        """导出记忆数据"""
        try:
            memory_manager = get_memory_manager()

            # 获取所有记忆或根据条件过滤
            if filter_criteria:
                query = filter_criteria.get('query', '')
                memory_type = filter_criteria.get('memory_type')
                memories = memory_manager.store.search_memories(
                    query=query,
                    memory_type=memory_type,
                    limit=1000
                )
            else:
                # 导出所有记忆
                memories = memory_manager.store.search_memories(
                    query='',
                    limit=10000
                )

            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'filter_criteria': filter_criteria,
                'memory_count': len(memories),
                'memories': [memory.to_dict() for memory, _ in memories]
            }

            # 保存到文件
            filename = f"memory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = f"data/{filename}"

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            logger.info(f"导出记忆数据: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"导出记忆数据失败: {str(e)}")
            raise

    @staticmethod
    def import_memories(filepath: str) -> int:
        """导入记忆数据"""
        try:
            memory_manager = get_memory_manager()

            with open(filepath, 'r', encoding='utf-8') as f:
                import_data = json.load(f)

            imported_count = 0
            for memory_data in import_data.get('memories', []):
                try:
                    memory = Memory.from_dict(memory_data)
                    memory_manager.store.store_memory(memory)
                    imported_count += 1
                except Exception as e:
                    logger.warning(f"导入记忆失败: {str(e)}")
                    continue

            logger.info(f"导入记忆数据完成: {imported_count}条")
            return imported_count

        except Exception as e:
            logger.error(f"导入记忆数据失败: {str(e)}")
            raise

def enhance_agent_with_memory(agent, memory_config: Dict[str, Any] = None):
    """为Agent添加记忆能力的装饰器"""
    def decorator(agent_class):
        class MemoryEnhancedAgentClass(agent_class):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.memory_enhanced = MemoryEnhancedAgent(self, memory_config)

            def process(self, user_input: str, context: Dict[str, Any] = None) -> str:
                return self.memory_enhanced.process_with_memory(user_input, context)

        return MemoryEnhancedAgentClass

    return decorator(agent) if agent else decorator