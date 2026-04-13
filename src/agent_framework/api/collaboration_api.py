"""
实时协作 API
提供 WebSocket 实时协作接口
"""

from flask import Blueprint, request, jsonify
from flask_socketio import emit, join_room, leave_room
from agent_framework.platform.collaboration import (
    get_collaboration_manager,
    get_comment_system,
    Operation,
    OperationType
)
import time

collaboration_bp = Blueprint('collaboration', __name__, url_prefix='/api/collaboration')


# WebSocket 事件处理
def register_collaboration_events(socketio):
    """注册协作相关的 WebSocket 事件"""

    @socketio.on('join_collaboration')
    def handle_join(data):
        """加入协作会话"""
        session_id = data.get('session_id')
        user_id = data.get('user_id')
        username = data.get('username')

        manager = get_collaboration_manager()
        user = manager.join_session(session_id, user_id, username)

        if user:
            join_room(session_id)

            # 通知其他用户
            emit('user_joined', {
                'user_id': user.user_id,
                'username': user.username,
                'color': user.color
            }, room=session_id, skip_sid=request.sid)

            # 返回当前会话状态
            emit('session_state', manager.get_session_state(session_id))

    @socketio.on('leave_collaboration')
    def handle_leave(data):
        """离开协作会话"""
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        manager = get_collaboration_manager()
        manager.leave_session(session_id, user_id)

        leave_room(session_id)

        # 通知其他用户
        emit('user_left', {
            'user_id': user_id
        }, room=session_id)

    @socketio.on('cursor_move')
    def handle_cursor_move(data):
        """光标移动"""
        session_id = data.get('session_id')
        user_id = data.get('user_id')
        position = data.get('position')

        manager = get_collaboration_manager()
        manager.update_cursor(session_id, user_id, position)

        # 广播光标位置
        emit('cursor_update', {
            'user_id': user_id,
            'position': position
        }, room=session_id, skip_sid=request.sid)

    @socketio.on('operation')
    def handle_operation(data):
        """处理操作"""
        session_id = data.get('session_id')
        user_id = data.get('user_id')
        op_type = data.get('op_type')
        target_id = data.get('target_id')
        op_data = data.get('data')

        operation = Operation(
            op_id=data.get('op_id'),
            op_type=OperationType(op_type),
            user_id=user_id,
            timestamp=time.time(),
            target_id=target_id,
            data=op_data,
            position=data.get('position')
        )

        manager = get_collaboration_manager()
        if manager.apply_operation(session_id, operation):
            # 广播操作
            emit('operation_applied', {
                'op_id': operation.op_id,
                'op_type': operation.op_type.value,
                'user_id': operation.user_id,
                'target_id': operation.target_id,
                'data': operation.data,
                'timestamp': operation.timestamp
            }, room=session_id, skip_sid=request.sid)

    @socketio.on('request_sync')
    def handle_sync_request(data):
        """请求同步"""
        session_id = data.get('session_id')
        version = data.get('version', 0)

        manager = get_collaboration_manager()
        operations = manager.get_operations_since(session_id, version)

        emit('sync_response', {
            'operations': [
                {
                    'op_id': op.op_id,
                    'op_type': op.op_type.value,
                    'user_id': op.user_id,
                    'target_id': op.target_id,
                    'data': op.data,
                    'timestamp': op.timestamp
                }
                for op in operations
            ],
            'version': manager.get_session(session_id).version if manager.get_session(session_id) else 0
        })


# REST API
@collaboration_bp.route('/sessions', methods=['POST'])
def create_session():
    """创建协作会话"""
    try:
        data = request.json
        workflow_id = data.get('workflow_id')

        manager = get_collaboration_manager()
        session = manager.create_session(workflow_id)

        return jsonify({
            'success': True,
            'session': {
                'session_id': session.session_id,
                'workflow_id': session.workflow_id,
                'created_at': session.created_at
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@collaboration_bp.route('/sessions', methods=['GET'])
def list_sessions():
    """获取协作会话列表"""
    try:
        manager = get_collaboration_manager()
        sessions = []
        for session in manager.sessions.values():
            active_users = manager.get_active_users(session.session_id)
            sessions.append({
                'session_id': session.session_id,
                'workflow_id': session.workflow_id,
                'created_at': session.created_at,
                'version': session.version,
                'operation_count': len(session.operations),
                'active_user_count': len(active_users),
                'users': [
                    {
                        'user_id': user.user_id,
                        'username': user.username,
                        'color': user.color,
                        'cursor_position': user.cursor_position,
                    }
                    for user in active_users
                ],
            })

        sessions.sort(key=lambda item: item['created_at'], reverse=True)
        return jsonify({
            'success': True,
            'sessions': sessions
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@collaboration_bp.route('/sessions/<session_id>', methods=['GET'])
def get_session(session_id: str):
    """获取会话状态"""
    try:
        manager = get_collaboration_manager()
        state = manager.get_session_state(session_id)

        if not state:
            return jsonify({
                'success': False,
                'error': '会话不存在'
            }), 404

        return jsonify({
            'success': True,
            'session': state
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@collaboration_bp.route('/sessions/<session_id>/users', methods=['GET'])
def get_active_users(session_id: str):
    """获取活跃用户"""
    try:
        manager = get_collaboration_manager()
        users = manager.get_active_users(session_id)

        return jsonify({
            'success': True,
            'users': [
                {
                    'user_id': user.user_id,
                    'username': user.username,
                    'color': user.color,
                    'cursor_position': user.cursor_position
                }
                for user in users
            ]
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@collaboration_bp.route('/comments', methods=['POST'])
def add_comment():
    """添加评论"""
    try:
        data = request.json
        workflow_id = data.get('workflow_id')
        node_id = data.get('node_id')
        user_id = data.get('user_id')
        username = data.get('username')
        content = data.get('content')

        comment_system = get_comment_system()
        comment = comment_system.add_comment(
            workflow_id, node_id, user_id, username, content
        )

        return jsonify({
            'success': True,
            'comment': comment
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@collaboration_bp.route('/comments/<comment_id>/replies', methods=['POST'])
def add_reply(comment_id: str):
    """添加回复"""
    try:
        data = request.json
        workflow_id = data.get('workflow_id')
        node_id = data.get('node_id')
        user_id = data.get('user_id')
        username = data.get('username')
        content = data.get('content')

        comment_system = get_comment_system()
        reply = comment_system.add_reply(
            workflow_id, node_id, comment_id, user_id, username, content
        )

        if reply:
            return jsonify({
                'success': True,
                'reply': reply
            })
        else:
            return jsonify({
                'success': False,
                'error': '评论不存在'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@collaboration_bp.route('/comments', methods=['GET'])
def get_comments():
    """获取评论列表"""
    try:
        workflow_id = request.args.get('workflow_id')
        node_id = request.args.get('node_id')

        comment_system = get_comment_system()
        comments = comment_system.get_comments(workflow_id, node_id)

        return jsonify({
            'success': True,
            'comments': comments
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@collaboration_bp.route('/comments/<comment_id>', methods=['DELETE'])
def delete_comment(comment_id: str):
    """删除评论"""
    try:
        workflow_id = request.args.get('workflow_id')
        node_id = request.args.get('node_id')

        comment_system = get_comment_system()
        success = comment_system.delete_comment(workflow_id, node_id, comment_id)

        if success:
            return jsonify({
                'success': True,
                'message': '评论已删除'
            })
        else:
            return jsonify({
                'success': False,
                'error': '评论不存在'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
