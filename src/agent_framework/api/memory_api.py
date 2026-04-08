"""
记忆系统API - 提供RESTful接口管理永久记忆
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from typing import Dict, Any
import logging

from agent_framework.memory.system import get_memory_backend_info, get_memory_manager, get_file_memory_layer, Memory

# 创建Blueprint
memory_bp = Blueprint('memory', __name__, url_prefix='/api/memory')

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@memory_bp.route('/backend', methods=['GET'])
def get_memory_backend():
    try:
        return jsonify({
            'success': True,
            'backend': get_memory_backend_info(),
        })
    except Exception as e:
        logger.error(f"获取 memory backend 失败: {str(e)}")
        return jsonify({'error': f'获取 memory backend 失败: {str(e)}'}), 500

@memory_bp.route('/episodic', methods=['POST'])
def add_episodic_memory():
    """添加情节记忆"""
    try:
        data = request.get_json()

        content = data.get('content', '')
        context = data.get('context', {})
        importance = data.get('importance', 0.5)
        tags = data.get('tags', [])

        if not content:
            return jsonify({'error': '记忆内容不能为空'}), 400

        memory_manager = get_memory_manager()
        memory_id = memory_manager.add_episodic_memory(
            content=content,
            context=context,
            importance=importance,
            tags=tags
        )

        logger.info(f"添加情节记忆: {memory_id}")

        return jsonify({
            'success': True,
            'memory_id': memory_id,
            'message': '情节记忆添加成功'
        })

    except Exception as e:
        logger.error(f"添加情节记忆失败: {str(e)}")
        return jsonify({'error': f'添加记忆失败: {str(e)}'}), 500

@memory_bp.route('/semantic', methods=['POST'])
def add_semantic_memory():
    """添加语义记忆"""
    try:
        data = request.get_json()

        content = data.get('content', '')
        context = data.get('context', {})
        importance = data.get('importance', 0.8)
        tags = data.get('tags', [])

        if not content:
            return jsonify({'error': '记忆内容不能为空'}), 400

        memory_manager = get_memory_manager()
        memory_id = memory_manager.add_semantic_memory(
            content=content,
            context=context,
            importance=importance,
            tags=tags
        )

        logger.info(f"添加语义记忆: {memory_id}")

        return jsonify({
            'success': True,
            'memory_id': memory_id,
            'message': '语义记忆添加成功'
        })

    except Exception as e:
        logger.error(f"添加语义记忆失败: {str(e)}")
        return jsonify({'error': f'添加记忆失败: {str(e)}'}), 500

@memory_bp.route('/procedural', methods=['POST'])
def add_procedural_memory():
    """添加程序性记忆"""
    try:
        data = request.get_json()

        content = data.get('content', '')
        context = data.get('context', {})
        importance = data.get('importance', 0.9)
        tags = data.get('tags', [])

        if not content:
            return jsonify({'error': '记忆内容不能为空'}), 400

        memory_manager = get_memory_manager()
        memory_id = memory_manager.add_procedural_memory(
            content=content,
            context=context,
            importance=importance,
            tags=tags
        )

        logger.info(f"添加程序性记忆: {memory_id}")

        return jsonify({
            'success': True,
            'memory_id': memory_id,
            'message': '程序性记忆添加成功'
        })

    except Exception as e:
        logger.error(f"添加程序性记忆失败: {str(e)}")
        return jsonify({'error': f'添加记忆失败: {str(e)}'}), 500

@memory_bp.route('/recall', methods=['POST'])
def recall_memories():
    """回忆相关记忆"""
    try:
        data = request.get_json()

        query = data.get('query', '')
        context = data.get('context', {})
        limit = data.get('limit', 5)

        if not query:
            return jsonify({'error': '查询内容不能为空'}), 400

        memory_manager = get_memory_manager()
        memories = memory_manager.recall_relevant_memories(
            query=query,
            context=context,
            limit=limit
        )

        # 转换为JSON格式
        result = []
        for memory in memories:
            result.append({
                'id': memory.id,
                'content': memory.content,
                'memory_type': memory.memory_type,
                'importance': memory.importance,
                'created_at': memory.created_at.isoformat(),
                'last_accessed': memory.last_accessed.isoformat(),
                'access_count': memory.access_count,
                'tags': memory.tags,
                'context': memory.context
            })

        logger.info(f"回忆记忆: 查询='{query}', 找到{len(result)}条记忆")

        return jsonify({
            'success': True,
            'memories': result,
            'count': len(result)
        })

    except Exception as e:
        logger.error(f"回忆记忆失败: {str(e)}")
        return jsonify({'error': f'回忆记忆失败: {str(e)}'}), 500

@memory_bp.route('/search', methods=['POST'])
def search_memories():
    """搜索记忆"""
    try:
        data = request.get_json()

        query = data.get('query', '')
        memory_type = data.get('memory_type')
        memory_types = data.get('memory_types')
        limit = data.get('limit', 10)
        similarity_threshold = data.get('similarity_threshold', 0.3)
        scopes = data.get('scopes')
        user_id = data.get('user_id')
        retrieval_mode = data.get('retrieval_mode', 'balanced')

        if not query:
            return jsonify({'error': '搜索内容不能为空'}), 400

        memory_manager = get_memory_manager()
        results = memory_manager.store.search_memories(
            query=query,
            memory_type=memory_type,
            memory_types=memory_types,
            limit=limit,
            similarity_threshold=similarity_threshold,
            scopes=scopes,
            user_id=user_id,
            retrieval_mode=retrieval_mode,
        )

        # 转换为JSON格式
        memories = []
        for memory, score in results:
            memories.append({
                'id': memory.id,
                'content': memory.content,
                'memory_type': memory.memory_type,
                'importance': memory.importance,
                'created_at': memory.created_at.isoformat(),
                'last_accessed': memory.last_accessed.isoformat(),
                'access_count': memory.access_count,
                'tags': memory.tags,
                'context': memory.context,
                'similarity_score': score
            })

        logger.info(f"搜索记忆: 查询='{query}', 找到{len(memories)}条记忆")

        return jsonify({
            'success': True,
            'memories': memories,
            'count': len(memories)
        })

    except Exception as e:
        logger.error(f"搜索记忆失败: {str(e)}")
        return jsonify({'error': f'搜索记忆失败: {str(e)}'}), 500

@memory_bp.route('/feedback', methods=['POST'])
def record_memory_feedback():
    """回写记忆反馈"""
    try:
        data = request.get_json()
        memory_ids = data.get('memory_ids', [])
        outcome = str(data.get('outcome', '') or '').strip()
        metadata = data.get('metadata', {})

        if not memory_ids or not outcome:
            return jsonify({'error': 'memory_ids 和 outcome 不能为空'}), 400

        memory_manager = get_memory_manager()
        memory_manager.record_retrieval_outcome(memory_ids, outcome, metadata=metadata)

        return jsonify({
            'success': True,
            'updated': len(memory_ids),
            'outcome': outcome
        })

    except Exception as e:
        logger.error(f"回写记忆反馈失败: {str(e)}")
        return jsonify({'error': f'回写记忆反馈失败: {str(e)}'}), 500

@memory_bp.route('/<memory_id>', methods=['GET'])
def get_memory(memory_id):
    """获取特定记忆"""
    try:
        memory_manager = get_memory_manager()
        memory = memory_manager.store.retrieve_memory(memory_id)

        if not memory:
            return jsonify({'error': '记忆不存在'}), 404

        result = {
            'id': memory.id,
            'content': memory.content,
            'memory_type': memory.memory_type,
            'importance': memory.importance,
            'created_at': memory.created_at.isoformat(),
            'last_accessed': memory.last_accessed.isoformat(),
            'access_count': memory.access_count,
            'tags': memory.tags,
            'context': memory.context
        }

        return jsonify({
            'success': True,
            'memory': result
        })

    except Exception as e:
        logger.error(f"获取记忆失败: {str(e)}")
        return jsonify({'error': f'获取记忆失败: {str(e)}'}), 500

@memory_bp.route('/statistics', methods=['GET'])
def get_memory_statistics():
    """获取记忆统计信息"""
    try:
        memory_manager = get_memory_manager()
        stats = memory_manager.get_memory_statistics()

        return jsonify({
            'success': True,
            'statistics': stats
        })

    except Exception as e:
        logger.error(f"获取记忆统计失败: {str(e)}")
        return jsonify({'error': f'获取记忆统计失败: {str(e)}'}), 500

@memory_bp.route('/consolidate', methods=['POST'])
def consolidate_memories():
    """记忆整合"""
    try:
        memory_manager = get_memory_manager()
        memory_manager.consolidate_memories()

        return jsonify({
            'success': True,
            'message': '记忆整合完成'
        })

    except Exception as e:
        logger.error(f"记忆整合失败: {str(e)}")
        return jsonify({'error': f'记忆整合失败: {str(e)}'}), 500

# ─── 三层记忆架构 API：每日笔记 ─────────────────────────────────────────────────

@memory_bp.route('/daily-notes', methods=['GET'])
def get_daily_notes():
    """获取最近 N 天的每日笔记"""
    try:
        days = request.args.get('days', 2, type=int)
        file_memory = get_file_memory_layer()
        content = file_memory.load_daily_notes(days=days)

        return jsonify({
            'success': True,
            'content': content,
            'days': days
        })
    except Exception as e:
        logger.error(f"获取每日笔记失败: {str(e)}")
        return jsonify({'error': f'获取每日笔记失败: {str(e)}'}), 500


@memory_bp.route('/daily-notes/files', methods=['GET'])
def list_daily_note_files():
    """列出所有每日笔记文件"""
    try:
        file_memory = get_file_memory_layer()
        files = file_memory.list_daily_files()

        return jsonify({
            'success': True,
            'files': files,
            'count': len(files)
        })
    except Exception as e:
        logger.error(f"列出每日笔记文件失败: {str(e)}")
        return jsonify({'error': f'列出文件失败: {str(e)}'}), 500


@memory_bp.route('/daily-notes/<date_str>', methods=['GET'])
def get_daily_note_by_date(date_str):
    """获取指定日期的每日笔记"""
    try:
        file_memory = get_file_memory_layer()
        content = file_memory.load_daily_note_by_date(date_str)

        if not content:
            return jsonify({'error': f'{date_str} 无笔记'}), 404

        return jsonify({
            'success': True,
            'date': date_str,
            'content': content
        })
    except Exception as e:
        logger.error(f"获取每日笔记失败: {str(e)}")
        return jsonify({'error': f'获取每日笔记失败: {str(e)}'}), 500


@memory_bp.route('/daily-notes', methods=['POST'])
def add_daily_note():
    """手动添加每日笔记"""
    try:
        data = request.get_json()
        content = data.get('content', '')

        if not content:
            return jsonify({'error': '笔记内容不能为空'}), 400

        file_memory = get_file_memory_layer()
        file_path = file_memory.append_daily_note(content)

        return jsonify({
            'success': True,
            'message': '笔记已添加',
            'file_path': file_path
        })
    except Exception as e:
        logger.error(f"添加每日笔记失败: {str(e)}")
        return jsonify({'error': f'添加笔记失败: {str(e)}'}), 500


# ─── 三层记忆架构 API：MEMORY.md 长期记忆 ─────────────────────────────────────────

@memory_bp.route('/memory-md', methods=['GET'])
def get_memory_md():
    """获取 MEMORY.md 内容"""
    try:
        file_memory = get_file_memory_layer()
        content = file_memory.load_memory_md()

        return jsonify({
            'success': True,
            'content': content
        })
    except Exception as e:
        logger.error(f"获取 MEMORY.md 失败: {str(e)}")
        return jsonify({'error': f'获取 MEMORY.md 失败: {str(e)}'}), 500


@memory_bp.route('/memory-md', methods=['PUT'])
def replace_memory_md():
    """替换 MEMORY.md 内容"""
    try:
        data = request.get_json()
        content = data.get('content', '')

        file_memory = get_file_memory_layer()
        file_memory.replace_memory_md(content)

        return jsonify({
            'success': True,
            'message': 'MEMORY.md 已更新'
        })
    except Exception as e:
        logger.error(f"替换 MEMORY.md 失败: {str(e)}")
        return jsonify({'error': f'替换 MEMORY.md 失败: {str(e)}'}), 500


@memory_bp.route('/memory-md/section', methods=['POST'])
def update_memory_md_section():
    """更新 MEMORY.md 指定章节"""
    try:
        data = request.get_json()
        section = data.get('section', '')
        content = data.get('content', '')

        if not section or not content:
            return jsonify({'error': '章节名和内容不能为空'}), 400

        file_memory = get_file_memory_layer()
        file_memory.update_memory_md(section, content)

        return jsonify({
            'success': True,
            'message': f'章节 "{section}" 已更新'
        })
    except Exception as e:
        logger.error(f"更新 MEMORY.md 章节失败: {str(e)}")
        return jsonify({'error': f'更新章节失败: {str(e)}'}), 500


# 记忆系统中间件
class MemoryMiddleware:
    """记忆系统中间件 - 自动记录对话和操作"""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """初始化应用"""
        app.before_request(self.before_request)
        app.after_request(self.after_request)

    def before_request(self):
        """请求前处理"""
        # 记录请求开始时间
        request.start_time = datetime.now()

    def after_request(self, response):
        """请求后处理"""
        try:
            # 自动记录重要的API调用
            if request.endpoint and request.method == 'POST':
                self._auto_record_interaction(request, response)
        except Exception as e:
            logger.error(f"自动记录交互失败: {str(e)}")

        return response

    def _auto_record_interaction(self, req, resp):
        """自动记录交互"""
        # 只记录成功的重要操作
        if resp.status_code == 200 and req.endpoint in [
            'workflow.create_workflow',
            'conversation.send_message',
            'knowledge.add_document'
        ]:
            try:
                memory_manager = get_memory_manager()

                content = f"API调用: {req.endpoint}"
                context = {
                    'endpoint': req.endpoint,
                    'method': req.method,
                    'timestamp': datetime.now().isoformat(),
                    'user_agent': req.headers.get('User-Agent', ''),
                    'ip_address': req.remote_addr
                }

                memory_manager.add_episodic_memory(
                    content=content,
                    context=context,
                    importance=0.3,
                    tags=['api_call', 'interaction']
                )

            except Exception as e:
                logger.error(f"记录API调用失败: {str(e)}")

def register_memory_system(app):
    """注册记忆系统到Flask应用"""
    # 注册Blueprint
    app.register_blueprint(memory_bp)

    # 注册中间件
    memory_middleware = MemoryMiddleware(app)

    logger.info("记忆系统已注册到Flask应用")
