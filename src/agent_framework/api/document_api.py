"""
文档解析 API
支持 MinerU 高级 PDF 解析
"""

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
import uuid
from agent_framework.vector_db.document_parser import DocumentLoader, DocumentChunker
from dataclasses import asdict

document_bp = Blueprint('document', __name__, url_prefix='/api/documents')

UPLOAD_FOLDER = 'data/uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'html', 'htm', 'md'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

loader = DocumentLoader()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── MinerU API 接口 ──────────────────────────────────────────────────────────

@document_bp.route('/mineru/parse', methods=['POST'])
def mineru_parse():
    """
    使用 MinerU API 解析 PDF 文档

    请求参数:
    - file: PDF 文件 (multipart/form-data)
    - api_key: MinerU API Key (可选，如果环境变量中已配置)
    - api_url: MinerU API URL (可选，默认使用官方 API)
    - extract_images: 是否提取图片 (true/false)
    - extract_tables: 是否提取表格 (true/false)
    - ocr: 是否使用 OCR (true/false)

    返回:
    - file_id: 文件 ID
    - content: 解析后的文本内容
    - metadata: 文档元数据
    - images: 提取的图片列表 (如果启用)
    - tables: 提取的表格列表 (如果启用)
    """
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    # 只支持 PDF
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"success": False, "error": "Only PDF files are supported for MinerU"}), 400

    # 保存文件
    filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())
    save_path = os.path.join(UPLOAD_FOLDER, f"{file_id}.pdf")
    file.save(save_path)

    try:
        # 获取配置
        api_key = request.form.get('api_key') or os.getenv('MINERU_API_KEY')
        api_url = request.form.get('api_url') or os.getenv('MINERU_API_URL', 'https://api.mineru.ai/v1/parse')
        extract_images = request.form.get('extract_images', 'false').lower() == 'true'
        extract_tables = request.form.get('extract_tables', 'false').lower() == 'true'
        use_ocr = request.form.get('ocr', 'false').lower() == 'true'

        if not api_key:
            return jsonify({
                "success": False,
                "error": "MinerU API Key not provided. Set MINERU_API_KEY environment variable or pass api_key parameter."
            }), 400

        # 调用 MinerU API
        import requests

        with open(save_path, 'rb') as f:
            files = {'file': (filename, f, 'application/pdf')}
            headers = {'Authorization': f'Bearer {api_key}'}
            data = {
                'extract_images': extract_images,
                'extract_tables': extract_tables,
                'ocr': use_ocr,
            }

            response = requests.post(api_url, files=files, headers=headers, data=data, timeout=300)

        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"MinerU API error: {response.text}"
            }), response.status_code

        result = response.json()

        return jsonify({
            "success": True,
            "file_id": file_id,
            "content": result.get('content', ''),
            "metadata": {
                "filename": filename,
                "file_id": file_id,
                "parser": "mineru",
                "pages": result.get('pages', 0),
                "language": result.get('language', 'unknown'),
            },
            "images": result.get('images', []) if extract_images else [],
            "tables": result.get('tables', []) if extract_tables else [],
            "raw_result": result,
        }), 200

    except Exception as e:
        # 清理文件
        if os.path.exists(save_path):
            os.remove(save_path)
        return jsonify({"success": False, "error": str(e)}), 500


@document_bp.route('/mineru/parse-and-upload', methods=['POST'])
def mineru_parse_and_upload():
    """
    使用 MinerU 解析 PDF 并直接上传到知识库

    请求参数:
    - file: PDF 文件
    - kb_id: 知识库 ID
    - api_key: MinerU API Key (可选)
    - chunk_size: 分块大小 (可选，默认 500)
    - chunk_overlap: 重叠大小 (可选，默认 50)
    """
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    kb_id = request.form.get('kb_id')
    if not kb_id:
        return jsonify({"success": False, "error": "kb_id is required"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"success": False, "error": "Only PDF files are supported"}), 400

    # 保存文件
    filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())
    save_path = os.path.join(UPLOAD_FOLDER, f"{file_id}.pdf")
    file.save(save_path)

    try:
        # 获取配置
        api_key = request.form.get('api_key') or os.getenv('MINERU_API_KEY')
        api_url = request.form.get('api_url') or os.getenv('MINERU_API_URL', 'https://api.mineru.ai/v1/parse')

        if not api_key:
            return jsonify({
                "success": False,
                "error": "MinerU API Key not provided"
            }), 400

        # 调用 MinerU API
        import requests

        with open(save_path, 'rb') as f:
            files = {'file': (filename, f, 'application/pdf')}
            headers = {'Authorization': f'Bearer {api_key}'}
            data = {
                'extract_images': False,
                'extract_tables': True,
                'ocr': request.form.get('ocr', 'false').lower() == 'true',
            }

            response = requests.post(api_url, files=files, headers=headers, data=data, timeout=300)

        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"MinerU API error: {response.text}"
            }), response.status_code

        result = response.json()
        content = result.get('content', '')

        if not content:
            return jsonify({
                "success": False,
                "error": "No content extracted from PDF"
            }), 400

        # 分块
        chunk_size = int(request.form.get('chunk_size', 500))
        chunk_overlap = int(request.form.get('chunk_overlap', 50))

        from agent_framework.vector_db.document_parser import Document
        document = Document(
            content=content,
            metadata={
                "filename": filename,
                "file_id": file_id,
                "parser": "mineru",
                "pages": result.get('pages', 0),
            },
            doc_type="pdf",
        )

        chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        chunks = chunker.chunk(document, doc_id=file_id)

        # 上传到知识库
        from agent_framework.api.knowledge_api import KNOWLEDGE_BASES, load_kb_config, create_knowledge_base

        if kb_id not in KNOWLEDGE_BASES:
            config = load_kb_config(kb_id)
            if not config:
                return jsonify({
                    "success": False,
                    "error": "Knowledge base not found"
                }), 404

            kb = create_knowledge_base(
                kb_id=kb_id,
                name=config["name"],
                embedding_type=config["embedding_type"],
                store_type=config["store_type"],
                **config.get("config", {}),
            )
            KNOWLEDGE_BASES[kb_id] = kb

        kb = KNOWLEDGE_BASES[kb_id]

        # 添加文档块
        for chunk in chunks:
            kb.add_text(chunk.content, chunk.metadata, chunk.doc_id)

        # 更新配置
        from agent_framework.api.knowledge_api import save_kb_config
        config = load_kb_config(kb_id)
        config["document_count"] = kb.count()
        save_kb_config(kb_id, config)

        return jsonify({
            "success": True,
            "file_id": file_id,
            "filename": filename,
            "chunks_added": len(chunks),
            "total_documents": kb.count(),
        }), 200

    except Exception as e:
        # 清理文件
        if os.path.exists(save_path):
            os.remove(save_path)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        # 清理临时文件
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass


@document_bp.route('/mineru/config', methods=['GET'])
def get_mineru_config():
    """获取 MinerU 配置状态"""
    api_key = os.getenv('MINERU_API_KEY')
    api_url = os.getenv('MINERU_API_URL', 'https://api.mineru.ai/v1/parse')

    return jsonify({
        "success": True,
        "configured": bool(api_key),
        "api_url": api_url,
        "features": {
            "pdf_parsing": True,
            "ocr": True,
            "table_extraction": True,
            "image_extraction": True,
        }
    })


# ─── 原有接口 ─────────────────────────────────────────────────────────────────



@document_bp.route('/upload', methods=['POST'])
def upload_document():
    """上传并解析文档"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File type not supported"}), 400

    # 保存文件
    filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())
    file_ext = filename.rsplit('.', 1)[1].lower()
    save_path = os.path.join(UPLOAD_FOLDER, f"{file_id}.{file_ext}")
    file.save(save_path)

    try:
        # 解析文档
        document = loader.load(save_path)

        # 可选：分块
        chunk_size = request.form.get('chunk_size', type=int, default=500)
        chunk_overlap = request.form.get('chunk_overlap', type=int, default=50)

        if request.form.get('chunk', 'false').lower() == 'true':
            chunker = DocumentChunker(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            chunks = chunker.chunk(document, doc_id=file_id)

            return jsonify({
                "file_id": file_id,
                "document": {
                    "content": document.content[:500] + "..." if len(document.content) > 500 else document.content,
                    "metadata": document.metadata,
                    "doc_type": document.doc_type,
                },
                "chunks": [
                    {
                        "content": chunk.content,
                        "metadata": chunk.metadata,
                        "chunk_index": chunk.chunk_index,
                    }
                    for chunk in chunks
                ],
                "chunk_count": len(chunks),
            }), 201

        return jsonify({
            "file_id": file_id,
            "document": {
                "content": document.content,
                "metadata": document.metadata,
                "doc_type": document.doc_type,
            },
        }), 201

    except Exception as e:
        # 清理文件
        if os.path.exists(save_path):
            os.remove(save_path)
        return jsonify({"error": str(e)}), 500


@document_bp.route('/parse', methods=['POST'])
def parse_document():
    """解析已上传的文档"""
    data = request.json
    file_path = data.get('file_path')

    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    try:
        document = loader.load(file_path)

        return jsonify({
            "document": {
                "content": document.content,
                "metadata": document.metadata,
                "doc_type": document.doc_type,
            },
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@document_bp.route('/chunk', methods=['POST'])
def chunk_document():
    """对文档进行分块"""
    data = request.json
    content = data.get('content')
    chunk_size = data.get('chunk_size', 500)
    chunk_overlap = data.get('chunk_overlap', 50)
    method = data.get('method', 'paragraph')  # paragraph or sentence

    if not content:
        return jsonify({"error": "No content provided"}), 400

    from agent_framework.vector_db.document_parser import Document

    document = Document(
        content=content,
        metadata=data.get('metadata', {}),
        doc_type="text",
    )

    chunker = DocumentChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if method == 'sentence':
        chunks = chunker.chunk_by_sentences(document)
    else:
        chunks = chunker.chunk(document)

    return jsonify({
        "chunks": [
            {
                "content": chunk.content,
                "metadata": chunk.metadata,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunks
        ],
        "chunk_count": len(chunks),
    })


@document_bp.route('/supported-formats', methods=['GET'])
def get_supported_formats():
    """获取支持的文件格式"""
    return jsonify({
        "formats": [
            {"ext": "txt", "name": "纯文本", "mime": "text/plain"},
            {"ext": "md", "name": "Markdown", "mime": "text/markdown"},
            {"ext": "pdf", "name": "PDF", "mime": "application/pdf"},
            {"ext": "docx", "name": "Word 文档", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            {"ext": "doc", "name": "Word 文档 (旧版)", "mime": "application/msword"},
            {"ext": "xlsx", "name": "Excel 表格", "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            {"ext": "xls", "name": "Excel 表格 (旧版)", "mime": "application/vnd.ms-excel"},
            {"ext": "pptx", "name": "PowerPoint", "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
            {"ext": "ppt", "name": "PowerPoint (旧版)", "mime": "application/vnd.ms-powerpoint"},
            {"ext": "html", "name": "HTML", "mime": "text/html"},
            {"ext": "htm", "name": "HTML", "mime": "text/html"},
        ]
    })
