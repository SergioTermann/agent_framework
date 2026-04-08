"""
代码片段管理器
提供代码片段的增删改查功能
"""

import agent_framework.core.fast_json as json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from agent_framework.core.database import db_manager


class CodeSnippetManager:
    """代码片段管理器"""

    def __init__(self, db_path: str = "data/code_snippets.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """初始化数据库表"""
        schema = """
        CREATE TABLE IF NOT EXISTS code_snippets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            code TEXT NOT NULL,
            language TEXT NOT NULL,
            tags TEXT,
            is_public INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            execution_count INTEGER DEFAULT 0,
            last_executed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_user_id ON code_snippets(user_id);
        CREATE INDEX IF NOT EXISTS idx_language ON code_snippets(language);
        CREATE INDEX IF NOT EXISTS idx_created_at ON code_snippets(created_at);
        CREATE INDEX IF NOT EXISTS idx_is_public ON code_snippets(is_public);
        """
        db_manager.init_table(self.db_path, schema)

    def create_snippet(
        self,
        title: str,
        code: str,
        language: str,
        user_id: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_public: bool = False
    ) -> int:
        """
        创建代码片段

        Args:
            title: 标题
            code: 代码内容
            language: 编程语言
            user_id: 用户ID
            description: 描述
            tags: 标签列表
            is_public: 是否公开

        Returns:
            片段ID
        """
        now = datetime.now().isoformat()
        tags_str = json.dumps(tags or [], ensure_ascii=False)

        query = """
        INSERT INTO code_snippets
        (user_id, title, description, code, language, tags, is_public, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        with db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (
                user_id, title, description, code, language,
                tags_str, int(is_public), now, now
            ))
            return cursor.lastrowid

    def get_snippet(self, snippet_id: int) -> Optional[Dict[str, Any]]:
        """获取单个代码片段"""
        query = "SELECT * FROM code_snippets WHERE id = ?"
        row = db_manager.execute_one(self.db_path, query, (snippet_id,))
        return self._row_to_dict(row) if row else None

    def update_snippet(
        self,
        snippet_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        code: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_public: Optional[bool] = None
    ) -> bool:
        """更新代码片段"""
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if code is not None:
            updates.append("code = ?")
            params.append(code)
        if language is not None:
            updates.append("language = ?")
            params.append(language)
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags, ensure_ascii=False))
        if is_public is not None:
            updates.append("is_public = ?")
            params.append(int(is_public))

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(snippet_id)

        query = f"UPDATE code_snippets SET {', '.join(updates)} WHERE id = ?"

        with db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.rowcount > 0

    def delete_snippet(self, snippet_id: int) -> bool:
        """删除代码片段"""
        query = "DELETE FROM code_snippets WHERE id = ?"
        with db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (snippet_id,))
            return cursor.rowcount > 0

    def list_snippets(
        self,
        user_id: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_public: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        列出代码片段

        Args:
            user_id: 用户ID过滤
            language: 语言过滤
            tags: 标签过滤
            is_public: 公开状态过滤
            limit: 返回数量
            offset: 偏移量

        Returns:
            代码片段列表
        """
        conditions = []
        params = []

        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if language is not None:
            conditions.append("language = ?")
            params.append(language)
        if is_public is not None:
            conditions.append("is_public = ?")
            params.append(int(is_public))

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
        SELECT * FROM code_snippets
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = db_manager.execute(self.db_path, query, tuple(params))
        snippets = [self._row_to_dict(row) for row in rows]

        # 标签过滤（在内存中进行）
        if tags:
            snippets = [
                s for s in snippets
                if any(tag in s.get('tags', []) for tag in tags)
            ]

        return snippets

    def search_snippets(
        self,
        keyword: str,
        user_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """搜索代码片段（标题、描述、代码内容）"""
        conditions = ["(title LIKE ? OR description LIKE ? OR code LIKE ?)"]
        params = [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]

        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)

        where_clause = f"WHERE {' AND '.join(conditions)}"
        query = f"""
        SELECT * FROM code_snippets
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
        """
        params.append(limit)

        rows = db_manager.execute(self.db_path, query, tuple(params))
        return [self._row_to_dict(row) for row in rows]

    def record_execution(self, snippet_id: int):
        """记录代码片段执行"""
        query = """
        UPDATE code_snippets
        SET execution_count = execution_count + 1,
            last_executed_at = ?
        WHERE id = ?
        """
        with db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (datetime.now().isoformat(), snippet_id))

    def get_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        conditions = []
        params = []

        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
        SELECT
            COUNT(*) as total_snippets,
            COUNT(DISTINCT language) as total_languages,
            SUM(execution_count) as total_executions,
            language,
            COUNT(*) as count
        FROM code_snippets
        {where_clause}
        GROUP BY language
        """

        rows = db_manager.execute(self.db_path, query, tuple(params))

        total_query = f"""
        SELECT
            COUNT(*) as total_snippets,
            SUM(execution_count) as total_executions
        FROM code_snippets
        {where_clause}
        """
        total_row = db_manager.execute_one(self.db_path, total_query, tuple(params))

        return {
            'total_snippets': total_row['total_snippets'] if total_row else 0,
            'total_executions': total_row['total_executions'] if total_row else 0,
            'by_language': [
                {'language': row['language'], 'count': row['count']}
                for row in rows
            ]
        }

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        if not row:
            return {}

        data = dict(row)
        # 解析 JSON 字段
        if 'tags' in data and data['tags']:
            try:
                data['tags'] = json.loads(data['tags'])
            except:
                data['tags'] = []
        else:
            data['tags'] = []

        # 转换布尔值
        if 'is_public' in data:
            data['is_public'] = bool(data['is_public'])

        return data


# 全局单例
_snippet_manager = None

def get_snippet_manager() -> CodeSnippetManager:
    """获取代码片段管理器单例"""
    global _snippet_manager
    if _snippet_manager is None:
        _snippet_manager = CodeSnippetManager()
    return _snippet_manager
