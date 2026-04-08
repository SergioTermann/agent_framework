"""
对话管理 API
提供对话的 CRUD、搜索、导出等接口
"""

from flask import Blueprint, request, jsonify, send_file
from agent_framework.web.conversation_manager import (
    ConversationManager,
    ConversationStorage,
    ConversationStatus,
    Annotation,
)
from datetime import datetime
import uuid
import io


# 创建 Blueprint
conversation_bp = Blueprint('conversation', __name__, url_prefix='/api/conversations')

# 初始化存储和管理器
storage = ConversationStorage()
manager = ConversationManager(storage)


# ─── 对话 CRUD ────────────────────────────────────────────────────────────────

@conversation_bp.route('/', methods=['GET'])
def list_conversations():
    """列出对话"""
    try:
        user_id = request.args.get('user_id')
        status = request.args.get('status')
        tags = request.args.getlist('tags')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        status_enum = ConversationStatus(status) if status else None

        conversations = storage.list_conversations(
            user_id=user_id,
            status=status_enum,
            tags=tags if tags else None,
            limit=limit,
            offset=offset,
        )

        return jsonify({
            "success": True,
            "data": [
                {
                    "conversation_id": c.conversation_id,
                    "title": c.title,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                    "status": c.status.value,
                    "user_id": c.user_id,
                    "tags": c.tags,
                    "message_count": c.message_count,
                    "total_tokens": c.total_tokens,
                    "rating": c.rating,
                }
                for c in conversations
            ],
            "total": len(conversations),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@conversation_bp.route('/', methods=['POST'])
def create_conversation():
    """创建对话"""
    try:
        data = request.json
        title = data.get('title', '新对话')
        user_id = data.get('user_id')
        tags = data.get('tags', [])

        conversation = manager.create_conversation(
            title=title,
            user_id=user_id,
            tags=tags,
        )

        return jsonify({
            "success": True,
            "data": {
                "conversation_id": conversation.conversation_id,
                "title": conversation.title,
                "created_at": conversation.created_at,
                "status": conversation.status.value,
            },
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@conversation_bp.route('/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id: str):
    """获取对话详情"""
    try:
        conversation, messages = manager.get_conversation_history(conversation_id)

        if not conversation:
            return jsonify({
                "success": False,
                "error": "对话不存在",
            }), 404

        return jsonify({
            "success": True,
            "data": {
                "conversation": {
                    "conversation_id": conversation.conversation_id,
                    "title": conversation.title,
                    "created_at": conversation.created_at,
                    "updated_at": conversation.updated_at,
                    "status": conversation.status.value,
                    "user_id": conversation.user_id,
                    "tags": conversation.tags,
                    "message_count": conversation.message_count,
                    "total_tokens": conversation.total_tokens,
                    "rating": conversation.rating,
                    "feedback": conversation.feedback,
                    "metadata": conversation.metadata,
                },
                "messages": [
                    {
                        "message_id": m.message_id,
                        "role": m.role.value,
                        "content": m.content,
                        "timestamp": m.timestamp,
                        "tokens": m.tokens,
                        "model": m.model,
                        "tool_calls": m.tool_calls,
                        "tool_results": m.tool_results,
                        "metadata": m.metadata,
                    }
                    for m in messages
                ],
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@conversation_bp.route('/<conversation_id>', methods=['PUT'])
def update_conversation(conversation_id: str):
    """更新对话"""
    try:
        conversation = storage.get_conversation(conversation_id)
        if not conversation:
            return jsonify({
                "success": False,
                "error": "对话不存在",
            }), 404

        data = request.json

        if 'title' in data:
            conversation.title = data['title']
        if 'tags' in data:
            conversation.tags = data['tags']
        if 'status' in data:
            conversation.status = ConversationStatus(data['status'])

        conversation.updated_at = datetime.now().isoformat()
        storage.update_conversation(conversation)

        return jsonify({
            "success": True,
            "data": {
                "conversation_id": conversation.conversation_id,
                "title": conversation.title,
                "updated_at": conversation.updated_at,
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@conversation_bp.route('/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id: str):
    """删除对话"""
    try:
        storage.delete_conversation(conversation_id)

        return jsonify({
            "success": True,
            "message": "对话已删除",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 消息管理 ─────────────────────────────────────────────────────────────────

@conversation_bp.route('/<conversation_id>/messages', methods=['POST'])
def add_message(conversation_id: str):
    """添加消息"""
    try:
        data = request.json
        role = data.get('role', 'user')
        content = data.get('content', '')
        metadata = data.get('metadata', {})

        if role == 'user':
            message = manager.add_user_message(
                conversation_id=conversation_id,
                content=content,
                metadata=metadata,
            )
        elif role == 'assistant':
            message = manager.add_assistant_message(
                conversation_id=conversation_id,
                content=content,
                model=data.get('model'),
                tokens=data.get('tokens'),
                tool_calls=data.get('tool_calls'),
                metadata=metadata,
            )
        else:
            return jsonify({
                "success": False,
                "error": f"不支持的角色: {role}",
            }), 400

        return jsonify({
            "success": True,
            "data": {
                "message_id": message.message_id,
                "role": message.role.value,
                "content": message.content,
                "timestamp": message.timestamp,
            },
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@conversation_bp.route('/<conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id: str):
    """获取消息列表"""
    try:
        limit = request.args.get('limit', type=int)
        messages = storage.get_messages(conversation_id, limit=limit)

        return jsonify({
            "success": True,
            "data": [
                {
                    "message_id": m.message_id,
                    "role": m.role.value,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "tokens": m.tokens,
                    "model": m.model,
                }
                for m in messages
            ],
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 搜索 ─────────────────────────────────────────────────────────────────────

@conversation_bp.route('/search', methods=['GET'])
def search_conversations():
    """搜索对话"""
    try:
        query = request.args.get('q', '')
        user_id = request.args.get('user_id')
        limit = int(request.args.get('limit', 20))

        if not query:
            return jsonify({
                "success": False,
                "error": "缺少搜索关键词",
            }), 400

        conversations = storage.search_conversations(
            query=query,
            user_id=user_id,
            limit=limit,
        )

        return jsonify({
            "success": True,
            "data": [
                {
                    "conversation_id": c.conversation_id,
                    "title": c.title,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                    "message_count": c.message_count,
                    "tags": c.tags,
                }
                for c in conversations
            ],
            "total": len(conversations),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 评价和反馈 ───────────────────────────────────────────────────────────────

@conversation_bp.route('/<conversation_id>/rating', methods=['POST'])
def rate_conversation(conversation_id: str):
    """评价对话"""
    try:
        data = request.json
        rating = data.get('rating')
        feedback = data.get('feedback')

        if rating is None or not (1 <= rating <= 5):
            return jsonify({
                "success": False,
                "error": "评分必须在 1-5 之间",
            }), 400

        manager.rate_conversation(
            conversation_id=conversation_id,
            rating=rating,
            feedback=feedback,
        )

        return jsonify({
            "success": True,
            "message": "评价已保存",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 标注 ─────────────────────────────────────────────────────────────────────

@conversation_bp.route('/<conversation_id>/annotations', methods=['POST'])
def add_annotation(conversation_id: str):
    """添加标注"""
    try:
        data = request.json
        message_id = data.get('message_id')
        annotation_type = data.get('type', 'comment')
        content = data.get('content', '')
        created_by = data.get('created_by')

        annotation = Annotation(
            annotation_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            message_id=message_id,
            annotation_type=annotation_type,
            content=content,
            created_at=datetime.now().isoformat(),
            created_by=created_by,
        )

        storage.add_annotation(annotation)

        return jsonify({
            "success": True,
            "data": {
                "annotation_id": annotation.annotation_id,
                "created_at": annotation.created_at,
            },
        }), 201

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@conversation_bp.route('/<conversation_id>/annotations', methods=['GET'])
def get_annotations(conversation_id: str):
    """获取标注"""
    try:
        message_id = request.args.get('message_id')
        annotations = storage.get_annotations(conversation_id, message_id)

        return jsonify({
            "success": True,
            "data": [
                {
                    "annotation_id": a.annotation_id,
                    "message_id": a.message_id,
                    "type": a.annotation_type,
                    "content": a.content,
                    "created_at": a.created_at,
                    "created_by": a.created_by,
                }
                for a in annotations
            ],
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 导出 ─────────────────────────────────────────────────────────────────────

@conversation_bp.route('/<conversation_id>/export', methods=['GET'])
def export_conversation(conversation_id: str):
    """导出对话"""
    try:
        format = request.args.get('format', 'json')

        if format not in ['json', 'markdown']:
            return jsonify({
                "success": False,
                "error": "不支持的格式，仅支持 json 或 markdown",
            }), 400

        content = manager.export_conversation(conversation_id, format=format)

        # 创建文件响应
        conversation = storage.get_conversation(conversation_id)
        filename = f"{conversation.title}_{conversation_id[:8]}.{format}"

        return send_file(
            io.BytesIO(content.encode('utf-8')),
            mimetype='application/json' if format == 'json' else 'text/markdown',
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 统计 ─────────────────────────────────────────────────────────────────────

@conversation_bp.route('/stats', methods=['GET'])
def get_stats():
    """获取统计信息"""
    try:
        user_id = request.args.get('user_id')

        # 获取所有对话
        conversations = storage.list_conversations(
            user_id=user_id,
            status=ConversationStatus.ACTIVE,
            limit=1000,
        )

        total_conversations = len(conversations)
        total_messages = sum(c.message_count for c in conversations)
        total_tokens = sum(c.total_tokens for c in conversations)

        # 评分统计
        rated_conversations = [c for c in conversations if c.rating is not None]
        avg_rating = (
            sum(c.rating for c in rated_conversations) / len(rated_conversations)
            if rated_conversations else 0
        )

        return jsonify({
            "success": True,
            "data": {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "total_tokens": total_tokens,
                "average_rating": round(avg_rating, 2),
                "rated_count": len(rated_conversations),
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500
