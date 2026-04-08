"""
Prompt 管理系统
支持 Prompt 模板库、版本管理、变量注入、A/B 测试
"""

import agent_framework.core.fast_json as json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import re
from agent_framework.core.database import DatabaseManager


@dataclass
class PromptTemplate:
    """Prompt 模板"""
    id: str
    name: str
    content: str
    variables: List[str]  # 变量列表，如 ["user_name", "task"]
    description: str = ""
    category: str = "general"  # general, code, creative, analysis
    tags: List[str] = None
    version: int = 1
    parent_id: Optional[str] = None  # 父版本 ID
    created_at: str = ""
    updated_at: str = ""
    usage_count: int = 0
    avg_rating: float = 0.0

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


@dataclass
class PromptTest:
    """Prompt 测试记录"""
    id: str
    prompt_id: str
    test_name: str
    variables: Dict[str, str]
    result: str
    rating: Optional[int] = None  # 1-5 星
    notes: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class PromptManager:
    """Prompt 管理器"""

    def __init__(self, db_path: str = "data/prompts.db"):
        self.db_path = db_path
        self.db_manager = DatabaseManager()
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Prompt 模板表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    variables TEXT,
                    description TEXT,
                    category TEXT,
                    tags TEXT,
                    version INTEGER DEFAULT 1,
                    parent_id TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    usage_count INTEGER DEFAULT 0,
                    avg_rating REAL DEFAULT 0.0
                )
            """)

            # Prompt 测试表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prompt_tests (
                    id TEXT PRIMARY KEY,
                    prompt_id TEXT NOT NULL,
                    test_name TEXT,
                    variables TEXT,
                    result TEXT,
                    rating INTEGER,
                    notes TEXT,
                    created_at TEXT,
                    FOREIGN KEY (prompt_id) REFERENCES prompts(id)
                )
            """)

            # A/B 测试表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_tests (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    prompt_a_id TEXT NOT NULL,
                    prompt_b_id TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TEXT,
                    FOREIGN KEY (prompt_a_id) REFERENCES prompts(id),
                    FOREIGN KEY (prompt_b_id) REFERENCES prompts(id)
                )
            """)

    def create_prompt(
        self,
        name: str,
        content: str,
        description: str = "",
        category: str = "general",
        tags: List[str] = None,
    ) -> PromptTemplate:
        """创建新的 Prompt 模板"""
        # 提取变量
        variables = self._extract_variables(content)

        prompt = PromptTemplate(
            id=str(uuid.uuid4()),
            name=name,
            content=content,
            variables=variables,
            description=description,
            category=category,
            tags=tags or [],
        )

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prompts
                (id, name, content, variables, description, category, tags,
                 version, parent_id, created_at, updated_at, usage_count, avg_rating)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prompt.id, prompt.name, prompt.content,
                json.dumps(prompt.variables),
                prompt.description, prompt.category,
                json.dumps(prompt.tags),
                prompt.version, prompt.parent_id,
                prompt.created_at, prompt.updated_at,
                prompt.usage_count, prompt.avg_rating
            ))

        return prompt

    def _extract_variables(self, content: str) -> List[str]:
        """从 Prompt 内容中提取变量"""
        # 支持 {{variable}} 和 {variable} 两种格式
        pattern = r'\{\{(\w+)\}\}|\{(\w+)\}'
        matches = re.findall(pattern, content)
        variables = []
        for match in matches:
            var = match[0] or match[1]
            if var and var not in variables:
                variables.append(var)
        return variables

    def get_prompt(self, prompt_id: str) -> Optional[PromptTemplate]:
        """获取 Prompt 模板"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
            row = cursor.fetchone()

        if not row:
            return None

        return PromptTemplate(
            id=row[0],
            name=row[1],
            content=row[2],
            variables=json.loads(row[3]),
            description=row[4],
            category=row[5],
            tags=json.loads(row[6]),
            version=row[7],
            parent_id=row[8],
            created_at=row[9],
            updated_at=row[10],
            usage_count=row[11],
            avg_rating=row[12],
        )

    def list_prompts(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
    ) -> List[PromptTemplate]:
        """列出 Prompt 模板"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM prompts WHERE 1=1"
            params = []

            if category:
                query += " AND category = ?"
                params.append(category)

            if search:
                query += " AND (name LIKE ? OR description LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

        prompts = []
        for row in rows:
            prompt = PromptTemplate(
                id=row[0],
                name=row[1],
                content=row[2],
                variables=json.loads(row[3]),
                description=row[4],
                category=row[5],
                tags=json.loads(row[6]),
                version=row[7],
                parent_id=row[8],
                created_at=row[9],
                updated_at=row[10],
                usage_count=row[11],
                avg_rating=row[12],
            )

            # 标签过滤
            if tags and not any(tag in prompt.tags for tag in tags):
                continue

            prompts.append(prompt)

        return prompts

    def update_prompt(
        self,
        prompt_id: str,
        name: Optional[str] = None,
        content: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[PromptTemplate]:
        """更新 Prompt 模板"""
        prompt = self.get_prompt(prompt_id)
        if not prompt:
            return None

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if name is not None:
                updates.append("name = ?")
                params.append(name)

            if content is not None:
                updates.append("content = ?")
                params.append(content)
                # 重新提取变量
                variables = self._extract_variables(content)
                updates.append("variables = ?")
                params.append(json.dumps(variables))

            if description is not None:
                updates.append("description = ?")
                params.append(description)

            if category is not None:
                updates.append("category = ?")
                params.append(category)

            if tags is not None:
                updates.append("tags = ?")
                params.append(json.dumps(tags))

            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())

            params.append(prompt_id)

            query = f"UPDATE prompts SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)

        return self.get_prompt(prompt_id)

    def create_version(self, prompt_id: str, changes: str = "") -> Optional[PromptTemplate]:
        """创建新版本"""
        parent = self.get_prompt(prompt_id)
        if not parent:
            return None

        new_prompt = PromptTemplate(
            id=str(uuid.uuid4()),
            name=parent.name,
            content=parent.content,
            variables=parent.variables,
            description=parent.description,
            category=parent.category,
            tags=parent.tags,
            version=parent.version + 1,
            parent_id=prompt_id,
        )

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prompts
                (id, name, content, variables, description, category, tags,
                 version, parent_id, created_at, updated_at, usage_count, avg_rating)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_prompt.id, new_prompt.name, new_prompt.content,
                json.dumps(new_prompt.variables),
                new_prompt.description, new_prompt.category,
                json.dumps(new_prompt.tags),
                new_prompt.version, new_prompt.parent_id,
                new_prompt.created_at, new_prompt.updated_at,
                new_prompt.usage_count, new_prompt.avg_rating
            ))

        return new_prompt

    def render_prompt(self, prompt_id: str, variables: Dict[str, str]) -> str:
        """渲染 Prompt（替换变量）"""
        prompt = self.get_prompt(prompt_id)
        if not prompt:
            raise ValueError(f"Prompt {prompt_id} not found")

        content = prompt.content

        # 替换 {{variable}} 格式
        for var, value in variables.items():
            content = content.replace(f"{{{{{var}}}}}", str(value))
            content = content.replace(f"{{{var}}}", str(value))

        # 增加使用计数
        self._increment_usage(prompt_id)

        return content

    def _increment_usage(self, prompt_id: str):
        """增加使用计数"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE prompts SET usage_count = usage_count + 1 WHERE id = ?",
                (prompt_id,)
            )

    def create_test(
        self,
        prompt_id: str,
        test_name: str,
        variables: Dict[str, str],
        result: str,
        rating: Optional[int] = None,
        notes: str = "",
    ) -> PromptTest:
        """创建测试记录"""
        test = PromptTest(
            id=str(uuid.uuid4()),
            prompt_id=prompt_id,
            test_name=test_name,
            variables=variables,
            result=result,
            rating=rating,
            notes=notes,
        )

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prompt_tests
                (id, prompt_id, test_name, variables, result, rating, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test.id, test.prompt_id, test.test_name,
                json.dumps(test.variables),
                test.result, test.rating, test.notes, test.created_at
            ))

        # 更新平均评分
        if rating is not None:
            self._update_avg_rating(prompt_id)

        return test

    def _update_avg_rating(self, prompt_id: str):
        """更新平均评分"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT AVG(rating) FROM prompt_tests
                WHERE prompt_id = ? AND rating IS NOT NULL
            """, (prompt_id,))

            avg = cursor.fetchone()[0] or 0.0

            cursor.execute(
                "UPDATE prompts SET avg_rating = ? WHERE id = ?",
                (avg, prompt_id)
            )

    def get_tests(self, prompt_id: str) -> List[PromptTest]:
        """获取测试记录"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM prompt_tests WHERE prompt_id = ? ORDER BY created_at DESC",
                (prompt_id,)
            )
            rows = cursor.fetchall()

        tests = []
        for row in rows:
            tests.append(PromptTest(
                id=row[0],
                prompt_id=row[1],
                test_name=row[2],
                variables=json.loads(row[3]),
                result=row[4],
                rating=row[5],
                notes=row[6],
                created_at=row[7],
            ))

        return tests

    def create_ab_test(
        self,
        name: str,
        prompt_a_id: str,
        prompt_b_id: str,
    ) -> str:
        """创建 A/B 测试"""
        ab_test_id = str(uuid.uuid4())

        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ab_tests (id, name, prompt_a_id, prompt_b_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                ab_test_id, name, prompt_a_id, prompt_b_id,
                "active", datetime.now().isoformat()
            ))

        return ab_test_id

    def get_ab_test_results(self, ab_test_id: str) -> Dict[str, Any]:
        """获取 A/B 测试结果"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM ab_tests WHERE id = ?", (ab_test_id,))
            row = cursor.fetchone()

            if not row:
                return None

            prompt_a_id = row[2]
            prompt_b_id = row[3]

            # 获取两个 Prompt 的统计数据
            cursor.execute("""
                SELECT
                    COUNT(*) as test_count,
                    AVG(rating) as avg_rating,
                    SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) as positive_count
                FROM prompt_tests
                WHERE prompt_id = ? AND rating IS NOT NULL
            """, (prompt_a_id,))
            stats_a = cursor.fetchone()

            cursor.execute("""
                SELECT
                    COUNT(*) as test_count,
                    AVG(rating) as avg_rating,
                    SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) as positive_count
                FROM prompt_tests
                WHERE prompt_id = ? AND rating IS NOT NULL
            """, (prompt_b_id,))
            stats_b = cursor.fetchone()

        return {
            "ab_test_id": ab_test_id,
            "name": row[1],
            "status": row[4],
            "prompt_a": {
                "id": prompt_a_id,
                "test_count": stats_a[0],
                "avg_rating": stats_a[1] or 0.0,
                "positive_count": stats_a[2] or 0,
            },
            "prompt_b": {
                "id": prompt_b_id,
                "test_count": stats_b[0],
                "avg_rating": stats_b[1] or 0.0,
                "positive_count": stats_b[2] or 0,
            },
        }

    def delete_prompt(self, prompt_id: str) -> bool:
        """删除 Prompt"""
        with self.db_manager.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
            deleted = cursor.rowcount > 0

        return deleted
