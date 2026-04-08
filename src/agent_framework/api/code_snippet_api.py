"""
代码片段 API
提供 RESTful 接口管理代码片段
"""

from flask import Blueprint, request, jsonify
from agent_framework.core.api_utils import json_error as _json_error, json_success as _json_success, parse_pagination as _parse_pagination, request_json as _request_json
from agent_framework.platform.code_snippet_manager import get_snippet_manager

snippet_bp = Blueprint('snippet', __name__, url_prefix='/api/snippets')


@snippet_bp.route('', methods=['POST'])
def create_snippet():
    """创建代码片段"""
    try:
        data = _request_json()

        # 验证必填字段
        required_fields = ['title', 'code', 'language']
        for field in required_fields:
            if field not in data:
                return _json_error(f'缺少必填字段: {field}')

        manager = get_snippet_manager()
        snippet_id = manager.create_snippet(
            title=data['title'],
            code=data['code'],
            language=data['language'],
            user_id=data.get('user_id'),
            description=data.get('description'),
            tags=data.get('tags', []),
            is_public=data.get('is_public', False)
        )

        return _json_success({
            'snippet_id': snippet_id,
            'message': '代码片段创建成功'
        }, 201)

    except Exception as e:
        return _json_error(str(e), 500)


@snippet_bp.route('/<int:snippet_id>', methods=['GET'])
def get_snippet(snippet_id):
    """获取代码片段"""
    try:
        manager = get_snippet_manager()
        snippet = manager.get_snippet(snippet_id)

        if not snippet:
            return _json_error('代码片段不存在', 404)

        return jsonify(snippet)

    except Exception as e:
        return _json_error(str(e), 500)


@snippet_bp.route('/<int:snippet_id>', methods=['PUT'])
def update_snippet(snippet_id):
    """更新代码片段"""
    try:
        data = _request_json()
        manager = get_snippet_manager()

        success = manager.update_snippet(
            snippet_id=snippet_id,
            title=data.get('title'),
            description=data.get('description'),
            code=data.get('code'),
            language=data.get('language'),
            tags=data.get('tags'),
            is_public=data.get('is_public')
        )

        if not success:
            return _json_error('更新失败或片段不存在', 404)

        return _json_success({'message': '代码片段更新成功'})

    except Exception as e:
        return _json_error(str(e), 500)


@snippet_bp.route('/<int:snippet_id>', methods=['DELETE'])
def delete_snippet(snippet_id):
    """删除代码片段"""
    try:
        manager = get_snippet_manager()
        success = manager.delete_snippet(snippet_id)

        if not success:
            return _json_error('删除失败或片段不存在', 404)

        return _json_success({'message': '代码片段删除成功'})

    except Exception as e:
        return _json_error(str(e), 500)


@snippet_bp.route('', methods=['GET'])
def list_snippets():
    """列出代码片段"""
    try:
        # 获取查询参数
        user_id = request.args.get('user_id')
        language = request.args.get('language')
        tags = request.args.getlist('tags')
        is_public = request.args.get('is_public')
        limit, offset = _parse_pagination()

        # 转换 is_public
        if is_public is not None:
            is_public = is_public.lower() in ('true', '1', 'yes')

        manager = get_snippet_manager()
        snippets = manager.list_snippets(
            user_id=user_id,
            language=language,
            tags=tags if tags else None,
            is_public=is_public,
            limit=limit,
            offset=offset
        )

        return jsonify({
            'snippets': snippets,
            'count': len(snippets),
            'limit': limit,
            'offset': offset
        })

    except Exception as e:
        return _json_error(str(e), 500)


@snippet_bp.route('/search', methods=['GET'])
def search_snippets():
    """搜索代码片段"""
    try:
        keyword = request.args.get('q', '')
        user_id = request.args.get('user_id')
        limit, _ = _parse_pagination()

        if not keyword:
            return _json_error('搜索关键词不能为空')

        manager = get_snippet_manager()
        snippets = manager.search_snippets(
            keyword=keyword,
            user_id=user_id,
            limit=limit
        )

        return jsonify({
            'snippets': snippets,
            'count': len(snippets),
            'keyword': keyword
        })

    except Exception as e:
        return _json_error(str(e), 500)


@snippet_bp.route('/<int:snippet_id>/execute', methods=['POST'])
def execute_snippet(snippet_id):
    """记录代码片段执行"""
    try:
        manager = get_snippet_manager()
        snippet = manager.get_snippet(snippet_id)

        if not snippet:
            return _json_error('代码片段不存在', 404)

        manager.record_execution(snippet_id)

        return _json_success({'message': '执行记录已保存'})

    except Exception as e:
        return _json_error(str(e), 500)


@snippet_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """获取统计信息"""
    try:
        user_id = request.args.get('user_id')
        manager = get_snippet_manager()
        stats = manager.get_statistics(user_id=user_id)

        return jsonify(stats)

    except Exception as e:
        return _json_error(str(e), 500)


@snippet_bp.route('/languages', methods=['GET'])
def get_languages():
    """获取支持的编程语言列表"""
    languages = [
        {'id': 'python', 'name': 'Python', 'icon': '🐍'},
        {'id': 'javascript', 'name': 'JavaScript', 'icon': '📜'},
        {'id': 'typescript', 'name': 'TypeScript', 'icon': '📘'},
        {'id': 'java', 'name': 'Java', 'icon': '☕'},
        {'id': 'cpp', 'name': 'C++', 'icon': '⚙️'},
        {'id': 'csharp', 'name': 'C#', 'icon': '🔷'},
        {'id': 'go', 'name': 'Go', 'icon': '🐹'},
        {'id': 'rust', 'name': 'Rust', 'icon': '🦀'},
        {'id': 'php', 'name': 'PHP', 'icon': '🐘'},
        {'id': 'ruby', 'name': 'Ruby', 'icon': '💎'},
        {'id': 'swift', 'name': 'Swift', 'icon': '🦅'},
        {'id': 'kotlin', 'name': 'Kotlin', 'icon': '🅺'},
        {'id': 'sql', 'name': 'SQL', 'icon': '🗄️'},
        {'id': 'html', 'name': 'HTML', 'icon': '🌐'},
        {'id': 'css', 'name': 'CSS', 'icon': '🎨'},
        {'id': 'bash', 'name': 'Bash', 'icon': '💻'},
        {'id': 'other', 'name': 'Other', 'icon': '📄'}
    ]

    return jsonify({'languages': languages})
