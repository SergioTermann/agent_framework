"""
知识库管理 API
=============

提供知识库的 CRUD 和检索接口。
"""

from flask import Blueprint, request, jsonify
from agent_framework.core.api_utils import json_error as _json_error, json_success as _json_success, request_json as _request_json
from werkzeug.utils import secure_filename
import os
from agent_framework.vector_db.knowledge_base import knowledge_manager

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/api/knowledge')

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'doc', 'md', 'markdown'}


def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@knowledge_bp.route('/bases', methods=['GET'])
def list_knowledge_bases():
    """获取所有知识库"""
    try:
        kbs = knowledge_manager.list_knowledge_bases()
        return jsonify({
            'knowledge_bases': [kb.to_dict() for kb in kbs]
        })
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases', methods=['POST'])
def create_knowledge_base():
    """创建知识库"""
    try:
        data = _request_json()
        name = (data.get('name') or '').strip()
        description = data.get('description', '')

        if not name:
            return _json_error('知识库名称不能为空')

        kb = knowledge_manager.create_knowledge_base(name, description)
        return jsonify(kb.to_dict())
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>', methods=['GET'])
def get_knowledge_base(kb_id):
    """获取知识库详情"""
    try:
        kb = knowledge_manager.get_knowledge_base(kb_id)
        if not kb:
            return _json_error('知识库不存在', 404)

        # 获取文档列表
        documents = []
        for doc_id in kb.documents:
            doc = knowledge_manager.get_document(doc_id)
            if doc:
                documents.append(doc.to_dict())

        result = kb.to_dict()
        result['documents'] = documents

        return jsonify(result)
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>/settings', methods=['PUT'])
def update_knowledge_base_settings(kb_id):
    """Update knowledge base endpoint bindings and advanced RAG settings."""
    try:
        data = _request_json()
        kb = knowledge_manager.update_knowledge_base_settings(
            kb_id,
            embedding_endpoint_id=(data.get('embedding_endpoint_id') or '').strip(),
            rerank_endpoint_id=(data.get('rerank_endpoint_id') or '').strip(),
            rag_settings=data.get('rag_settings') or {},
        )
        return jsonify(kb.to_dict())
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>', methods=['DELETE'])
def delete_knowledge_base(kb_id):
    """删除知识库"""
    try:
        knowledge_manager.delete_knowledge_base(kb_id)
        return _json_success()
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>/documents', methods=['POST'])
def upload_document(kb_id):
    """上传文档到知识库"""
    upload_path = None
    try:
        if 'file' not in request.files:
            return _json_error('没有文件')

        file = request.files['file']
        if file.filename == '':
            return _json_error('文件名为空')

        if not allowed_file(file.filename):
            return _json_error(f'不支持的文件类型，支持的类型: {", ".join(sorted(ALLOWED_EXTENSIONS))}')

        # 保存文件
        filename = secure_filename(file.filename)
        upload_path = os.path.join(knowledge_manager.upload_dir, filename)
        file.save(upload_path)

        # 处理文档
        doc = knowledge_manager.upload_document(kb_id, upload_path, filename)

        return jsonify(doc.to_dict())
    except Exception as e:
        return _json_error(str(e), 500)
    finally:
        if upload_path and os.path.exists(upload_path):
            os.remove(upload_path)


@knowledge_bp.route('/bases/<kb_id>/documents/<doc_id>', methods=['DELETE'])
def delete_document(kb_id, doc_id):
    """删除文档"""
    try:
        knowledge_manager.delete_document(kb_id, doc_id)
        return _json_success()
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>/documents/<doc_id>', methods=['GET'])
def get_document(kb_id, doc_id):
    """获取文档详情"""
    try:
        doc = knowledge_manager.get_document(doc_id)
        if not doc:
            return _json_error('文档不存在', 404)

        return jsonify({
            'id': doc.id,
            'name': doc.name,
            'type': doc.type,
            'size': doc.size,
            'content': doc.content,
            'chunk_count': len(doc.chunks),
            'metadata': doc.metadata,
            'created_at': doc.created_at
        })
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>/reindex', methods=['POST'])
def rebuild_knowledge_base(kb_id):
    """Rebuild vector embeddings for a knowledge base."""
    try:
        kb = knowledge_manager.rebuild_knowledge_base_vectors(kb_id)
        return jsonify({
            'success': True,
            'knowledge_base': kb.to_dict(),
        })
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>/search', methods=['POST'])
def search_knowledge_base(kb_id):
    """在知识库中搜索"""
    try:
        data = _request_json()
        query = (data.get('query') or '').strip()
        top_k_raw = data.get('top_k', 0)
        try:
            parsed_top_k = int(top_k_raw or 0)
        except (TypeError, ValueError):
            parsed_top_k = 0
        top_k = 0 if parsed_top_k <= 0 else min(parsed_top_k, 50)

        if not query:
            return _json_error('查询内容不能为空')

        results = knowledge_manager.search(kb_id, query, top_k)

        return jsonify({
            'query': query,
            'results': results
        })
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/stats', methods=['GET'])
def get_stats():
    """获取统计信息"""
    try:
        kbs = knowledge_manager.list_knowledge_bases()

        total_docs = 0
        total_chunks = 0

        for kb in kbs:
            total_docs += len(kb.documents)
            for doc_id in kb.documents:
                doc = knowledge_manager.get_document(doc_id)
                if doc:
                    total_chunks += len(doc.chunks)

        return jsonify({
            'knowledge_base_count': len(kbs),
            'document_count': total_docs,
            'chunk_count': total_chunks
        })
    except Exception as e:
        return _json_error(str(e), 500)
