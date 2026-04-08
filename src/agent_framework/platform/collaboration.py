"""
实时协作系统
支持多人同时编辑工作流、实时光标显示、冲突解决
"""

import agent_framework.core.fast_json as json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set
from enum import Enum
import uuid


class OperationType(str, Enum):
    """操作类型"""
    INSERT = "insert"
    DELETE = "delete"
    UPDATE = "update"
    MOVE = "move"


@dataclass
class Operation:
    """操作"""
    op_id: str
    op_type: OperationType
    user_id: str
    timestamp: float
    target_id: str  # 节点或边的ID
    data: Dict
    position: Optional[int] = None  # 用于OT算法


@dataclass
class User:
    """在线用户"""
    user_id: str
    username: str
    color: str  # 光标颜色
    cursor_position: Optional[Dict] = None
    last_seen: float = field(default_factory=time.time)


@dataclass
class CollaborationSession:
    """协作会话"""
    session_id: str
    workflow_id: str
    created_at: float
    users: Dict[str, User] = field(default_factory=dict)
    operations: List[Operation] = field(default_factory=list)
    version: int = 0


class OperationalTransform:
    """操作转换（OT）算法实现"""

    @staticmethod
    def transform(op1: Operation, op2: Operation) -> tuple[Operation, Operation]:
        """
        转换两个并发操作

        Args:
            op1: 操作1
            op2: 操作2

        Returns:
            转换后的操作对
        """
        # 如果操作目标不同，不需要转换
        if op1.target_id != op2.target_id:
            return op1, op2

        # INSERT vs INSERT
        if op1.op_type == OperationType.INSERT and op2.op_type == OperationType.INSERT:
            if op1.position <= op2.position:
                op2.position += 1
            else:
                op1.position += 1

        # INSERT vs DELETE
        elif op1.op_type == OperationType.INSERT and op2.op_type == OperationType.DELETE:
            if op1.position <= op2.position:
                op2.position += 1
            else:
                op1.position -= 1

        # DELETE vs INSERT
        elif op1.op_type == OperationType.DELETE and op2.op_type == OperationType.INSERT:
            if op1.position < op2.position:
                op2.position -= 1
            else:
                op1.position += 1

        # DELETE vs DELETE
        elif op1.op_type == OperationType.DELETE and op2.op_type == OperationType.DELETE:
            if op1.position < op2.position:
                op2.position -= 1
            elif op1.position > op2.position:
                op1.position -= 1
            else:
                # 删除同一位置，保留一个
                op2.op_type = None

        # UPDATE vs UPDATE
        elif op1.op_type == OperationType.UPDATE and op2.op_type == OperationType.UPDATE:
            # 后来的操作覆盖前面的
            if op1.timestamp > op2.timestamp:
                op2.data = op1.data

        return op1, op2


class CollaborationManager:
    """协作管理器"""

    def __init__(self):
        self.sessions: Dict[str, CollaborationSession] = {}
        self.user_colors = [
            "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A",
            "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E2"
        ]
        self.color_index = 0

    def create_session(self, workflow_id: str) -> CollaborationSession:
        """创建协作会话"""
        session_id = str(uuid.uuid4())
        session = CollaborationSession(
            session_id=session_id,
            workflow_id=workflow_id,
            created_at=time.time()
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[CollaborationSession]:
        """获取协作会话"""
        return self.sessions.get(session_id)

    def join_session(self, session_id: str, user_id: str, username: str) -> Optional[User]:
        """加入协作会话"""
        session = self.get_session(session_id)
        if not session:
            return None

        # 分配颜色
        color = self.user_colors[self.color_index % len(self.user_colors)]
        self.color_index += 1

        user = User(
            user_id=user_id,
            username=username,
            color=color
        )

        session.users[user_id] = user
        return user

    def leave_session(self, session_id: str, user_id: str):
        """离开协作会话"""
        session = self.get_session(session_id)
        if session and user_id in session.users:
            del session.users[user_id]

            # 如果没有用户了，清理会话
            if not session.users:
                del self.sessions[session_id]

    def update_cursor(self, session_id: str, user_id: str, position: Dict):
        """更新光标位置"""
        session = self.get_session(session_id)
        if session and user_id in session.users:
            session.users[user_id].cursor_position = position
            session.users[user_id].last_seen = time.time()

    def apply_operation(self, session_id: str, operation: Operation) -> bool:
        """应用操作"""
        session = self.get_session(session_id)
        if not session:
            return False

        # 对所有未确认的操作进行OT转换
        ot = OperationalTransform()
        for existing_op in reversed(session.operations[-10:]):  # 只考虑最近10个操作
            if existing_op.timestamp > operation.timestamp:
                operation, existing_op = ot.transform(operation, existing_op)

        # 添加操作到历史
        session.operations.append(operation)
        session.version += 1

        # 保持操作历史在合理范围内
        if len(session.operations) > 1000:
            session.operations = session.operations[-500:]

        return True

    def get_operations_since(self, session_id: str, version: int) -> List[Operation]:
        """获取指定版本之后的所有操作"""
        session = self.get_session(session_id)
        if not session:
            return []

        # 计算需要返回的操作
        start_index = max(0, len(session.operations) - (session.version - version))
        return session.operations[start_index:]

    def get_active_users(self, session_id: str) -> List[User]:
        """获取活跃用户列表"""
        session = self.get_session(session_id)
        if not session:
            return []

        current_time = time.time()
        active_users = []

        for user in session.users.values():
            # 5分钟内有活动的用户
            if current_time - user.last_seen < 300:
                active_users.append(user)

        return active_users

    def resolve_conflict(self, session_id: str, op1: Operation, op2: Operation) -> Operation:
        """解决冲突"""
        # 使用时间戳作为优先级
        if op1.timestamp > op2.timestamp:
            return op1
        return op2

    def get_session_state(self, session_id: str) -> Dict:
        """获取会话状态"""
        session = self.get_session(session_id)
        if not session:
            return {}

        return {
            "session_id": session.session_id,
            "workflow_id": session.workflow_id,
            "version": session.version,
            "users": [
                {
                    "user_id": user.user_id,
                    "username": user.username,
                    "color": user.color,
                    "cursor_position": user.cursor_position,
                    "last_seen": user.last_seen
                }
                for user in self.get_active_users(session_id)
            ],
            "operation_count": len(session.operations)
        }


class CommentSystem:
    """评论系统"""

    def __init__(self):
        self.comments: Dict[str, List[Dict]] = {}

    def add_comment(self, workflow_id: str, node_id: str, user_id: str,
                   username: str, content: str) -> Dict:
        """添加评论"""
        comment = {
            "comment_id": str(uuid.uuid4()),
            "node_id": node_id,
            "user_id": user_id,
            "username": username,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "replies": []
        }

        key = f"{workflow_id}:{node_id}"
        if key not in self.comments:
            self.comments[key] = []

        self.comments[key].append(comment)
        return comment

    def add_reply(self, workflow_id: str, node_id: str, comment_id: str,
                 user_id: str, username: str, content: str) -> Optional[Dict]:
        """添加回复"""
        key = f"{workflow_id}:{node_id}"
        if key not in self.comments:
            return None

        for comment in self.comments[key]:
            if comment["comment_id"] == comment_id:
                reply = {
                    "reply_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "username": username,
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                }
                comment["replies"].append(reply)
                return reply

        return None

    def get_comments(self, workflow_id: str, node_id: str) -> List[Dict]:
        """获取评论列表"""
        key = f"{workflow_id}:{node_id}"
        return self.comments.get(key, [])

    def delete_comment(self, workflow_id: str, node_id: str, comment_id: str) -> bool:
        """删除评论"""
        key = f"{workflow_id}:{node_id}"
        if key not in self.comments:
            return False

        self.comments[key] = [
            c for c in self.comments[key]
            if c["comment_id"] != comment_id
        ]
        return True


# 全局实例
_collaboration_manager = None
_comment_system = None


def get_collaboration_manager() -> CollaborationManager:
    """获取协作管理器实例"""
    global _collaboration_manager
    if _collaboration_manager is None:
        _collaboration_manager = CollaborationManager()
    return _collaboration_manager


def get_comment_system() -> CommentSystem:
    """获取评论系统实例"""
    global _comment_system
    if _comment_system is None:
        _comment_system = CommentSystem()
    return _comment_system
