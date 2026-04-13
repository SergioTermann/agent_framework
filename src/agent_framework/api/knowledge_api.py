"""
知识库管理 API
=============

提供知识库的 CRUD、检索、联邦搜索、知识图谱、管线调试和质量评估接口。
"""

from flask import Blueprint, request, jsonify
from agent_framework.core.api_utils import json_error as _json_error, json_success as _json_success, request_json as _request_json
from werkzeug.utils import secure_filename
import os
import uuid
import time
import re
import math
import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from agent_framework.vector_db.knowledge_base import knowledge_manager

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/api/knowledge')

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'doc', 'md', 'markdown', 'csv', 'json', 'html', 'htm', 'xlsx', 'xls'}

# ── In-memory stores for annotations, quality reports, etc. ──
_annotations_store = {}   # { doc_id: [ {id, chunk_id, text, label, author, created_at, tags} ] }
_quality_reports = {}     # { kb_id: { report_id, created_at, metrics, ... } }
_search_traces = {}       # { trace_id: { stages: [...], timing, ... } }


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
            'chunks': [
                {
                    'id': chunk.id,
                    'content': chunk.content,
                    'metadata': chunk.metadata,
                }
                for chunk in doc.chunks
            ],
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

        results = knowledge_manager.search(
            kb_id,
            query,
            top_k,
            embedding_endpoint_id=(data.get('embedding_endpoint_id') or '').strip(),
            rerank_endpoint_id=(data.get('rerank_endpoint_id') or '').strip(),
            rag_settings=data.get('rag_settings') if isinstance(data.get('rag_settings'), dict) else None,
        )

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
        total_annotations = 0

        for kb in kbs:
            total_docs += len(kb.documents)
            for doc_id in kb.documents:
                doc = knowledge_manager.get_document(doc_id)
                if doc:
                    total_chunks += len(doc.chunks)
                    total_annotations += len(_annotations_store.get(doc_id, []))

        return jsonify({
            'knowledge_base_count': len(kbs),
            'document_count': total_docs,
            'chunk_count': total_chunks,
            'annotation_count': total_annotations,
            'trace_count': len(_search_traces),
            'quality_report_count': len(_quality_reports),
        })
    except Exception as e:
        return _json_error(str(e), 500)


# ════════════════════════════════════════════════════════════════
#  Federated Search — 跨多知识库联邦搜索
# ════════════════════════════════════════════════════════════════

@knowledge_bp.route('/federated-search', methods=['POST'])
def federated_search():
    """跨多个知识库同时搜索，按分数合并排序"""
    try:
        data = _request_json()
        query = (data.get('query') or '').strip()
        kb_ids = data.get('kb_ids', [])
        top_k = min(int(data.get('top_k', 10) or 10), 50)
        merge_strategy = data.get('merge_strategy', 'score')  # score | round_robin | rrf

        if not query:
            return _json_error('查询内容不能为空')
        if not kb_ids:
            kbs = knowledge_manager.list_knowledge_bases()
            kb_ids = [kb.id for kb in kbs]

        all_results = []
        per_kb_results = {}
        per_kb_timing = {}

        for kb_id in kb_ids:
            kb = knowledge_manager.get_knowledge_base(kb_id)
            if not kb:
                continue
            t0 = time.time()
            results = knowledge_manager.search(kb_id, query, top_k)
            elapsed = time.time() - t0
            per_kb_timing[kb_id] = round(elapsed * 1000, 1)
            tagged = []
            for r in results:
                r['source_kb_id'] = kb_id
                r['source_kb_name'] = kb.name
                tagged.append(r)
            per_kb_results[kb_id] = tagged
            all_results.extend(tagged)

        if merge_strategy == 'rrf':
            merged = _rrf_merge(per_kb_results, top_k)
        elif merge_strategy == 'round_robin':
            merged = _round_robin_merge(per_kb_results, top_k)
        else:
            merged = sorted(all_results, key=lambda x: _extract_score(x), reverse=True)[:top_k]

        overlap = _compute_overlap_matrix(per_kb_results)

        return jsonify({
            'query': query,
            'merge_strategy': merge_strategy,
            'results': merged,
            'per_kb_count': {k: len(v) for k, v in per_kb_results.items()},
            'per_kb_timing_ms': per_kb_timing,
            'overlap_matrix': overlap,
            'total_candidates': len(all_results),
        })
    except Exception as e:
        return _json_error(str(e), 500)


def _extract_score(result):
    return float(result.get('retrieval_score') or result.get('score') or 0)


def _rrf_merge(per_kb_results, top_k, k=60):
    """Reciprocal Rank Fusion across knowledge bases"""
    scores = defaultdict(float)
    items = {}
    for kb_id, results in per_kb_results.items():
        for rank, r in enumerate(results):
            key = r.get('chunk_id') or r.get('id') or str(id(r))
            scores[key] += 1.0 / (k + rank + 1)
            items[key] = r
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    merged = []
    for key, rrf_score in ranked:
        item = items[key]
        item['rrf_federated_score'] = round(rrf_score, 6)
        merged.append(item)
    return merged


def _round_robin_merge(per_kb_results, top_k):
    """Round-robin interleaving from each KB"""
    merged = []
    iterators = {k: iter(v) for k, v in per_kb_results.items()}
    while len(merged) < top_k and iterators:
        exhausted = []
        for kb_id, it in iterators.items():
            if len(merged) >= top_k:
                break
            try:
                merged.append(next(it))
            except StopIteration:
                exhausted.append(kb_id)
        for k in exhausted:
            del iterators[k]
    return merged


def _compute_overlap_matrix(per_kb_results):
    """Compute chunk overlap between knowledge bases"""
    kb_chunks = {}
    for kb_id, results in per_kb_results.items():
        chunks = set()
        for r in results:
            content = r.get('content') or r.get('snippet') or ''
            if content:
                chunks.add(hashlib.md5(content[:200].encode()).hexdigest())
        kb_chunks[kb_id] = chunks

    matrix = {}
    for kb_a in kb_chunks:
        matrix[kb_a] = {}
        for kb_b in kb_chunks:
            if kb_a == kb_b:
                matrix[kb_a][kb_b] = 1.0
            else:
                union = kb_chunks[kb_a] | kb_chunks[kb_b]
                intersection = kb_chunks[kb_a] & kb_chunks[kb_b]
                matrix[kb_a][kb_b] = round(len(intersection) / max(len(union), 1), 3)
    return matrix


# ════════════════════════════════════════════════════════════════
#  Retrieval Pipeline Debugger — 检索管线调试器
# ════════════════════════════════════════════════════════════════

@knowledge_bp.route('/bases/<kb_id>/search-debug', methods=['POST'])
def search_with_debug(kb_id):
    """带管线调试信息的增强搜索"""
    try:
        data = _request_json()
        query = (data.get('query') or '').strip()
        top_k = min(int(data.get('top_k', 5) or 5), 50)

        if not query:
            return _json_error('查询内容不能为空')

        trace_id = str(uuid.uuid4())[:12]
        stages = []
        t_start = time.time()

        # Stage 1: Query Analysis
        t0 = time.time()
        query_tokens = list(set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', query)))
        query_analysis = {
            'original_query': query,
            'tokens': query_tokens,
            'token_count': len(query_tokens),
            'char_count': len(query),
            'language': 'zh' if any('\u4e00' <= c <= '\u9fff' for c in query) else 'en',
            'has_question_mark': '？' in query or '?' in query,
            'estimated_intent': _classify_query_intent(query),
        }
        stages.append({
            'name': 'query_analysis',
            'label': '查询分析',
            'duration_ms': round((time.time() - t0) * 1000, 2),
            'output': query_analysis,
            'input_count': 1,
            'output_count': len(query_tokens),
        })

        # Stage 2: Query Expansion
        t0 = time.time()
        expanded_terms = _expand_query_terms(query_tokens)
        stages.append({
            'name': 'query_expansion',
            'label': '查询扩展',
            'duration_ms': round((time.time() - t0) * 1000, 2),
            'output': {
                'original_tokens': query_tokens,
                'expanded_terms': expanded_terms,
                'expansion_ratio': round(len(expanded_terms) / max(len(query_tokens), 1), 2),
            },
            'input_count': len(query_tokens),
            'output_count': len(expanded_terms),
        })

        # Stage 3: Retrieval
        t0 = time.time()
        results = knowledge_manager.search(kb_id, query, top_k)
        retrieval_time = time.time() - t0
        stages.append({
            'name': 'hybrid_retrieval',
            'label': '混合检索',
            'duration_ms': round(retrieval_time * 1000, 2),
            'output': {
                'result_count': len(results),
                'score_range': [
                    round(_extract_score(results[-1]), 4) if results else 0,
                    round(_extract_score(results[0]), 4) if results else 0,
                ],
                'unique_documents': len(set(
                    r.get('metadata', {}).get('doc_name', '') for r in results
                )),
            },
            'input_count': len(expanded_terms),
            'output_count': len(results),
        })

        # Stage 4: Score Analysis
        t0 = time.time()
        score_distribution = _analyze_score_distribution(results)
        stages.append({
            'name': 'score_analysis',
            'label': '分数分析',
            'duration_ms': round((time.time() - t0) * 1000, 2),
            'output': score_distribution,
            'input_count': len(results),
            'output_count': len(results),
        })

        # Stage 5: Context Expansion Analysis
        t0 = time.time()
        context_stats = _analyze_context_expansion(results)
        stages.append({
            'name': 'context_expansion',
            'label': '上下文扩展',
            'duration_ms': round((time.time() - t0) * 1000, 2),
            'output': context_stats,
            'input_count': len(results),
            'output_count': context_stats.get('total_expanded_chunks', 0),
        })

        # Stage 6: Diversity Analysis
        t0 = time.time()
        diversity = _analyze_result_diversity(results)
        stages.append({
            'name': 'diversity_check',
            'label': '多样性检查',
            'duration_ms': round((time.time() - t0) * 1000, 2),
            'output': diversity,
            'input_count': len(results),
            'output_count': diversity.get('unique_documents', 0),
        })

        total_time = round((time.time() - t_start) * 1000, 2)

        trace = {
            'trace_id': trace_id,
            'query': query,
            'kb_id': kb_id,
            'created_at': datetime.now().isoformat(),
            'total_duration_ms': total_time,
            'stages': stages,
            'stage_count': len(stages),
            'results': results,
            'bottleneck': max(stages, key=lambda s: s['duration_ms'])['name'] if stages else None,
        }
        _search_traces[trace_id] = trace

        return jsonify(trace)
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/traces', methods=['GET'])
def list_search_traces():
    """列出最近的搜索调试追踪"""
    try:
        traces = sorted(_search_traces.values(), key=lambda x: x['created_at'], reverse=True)[:50]
        return jsonify({
            'traces': [{
                'trace_id': t['trace_id'],
                'query': t['query'],
                'kb_id': t['kb_id'],
                'total_duration_ms': t['total_duration_ms'],
                'stage_count': t['stage_count'],
                'result_count': len(t.get('results', [])),
                'bottleneck': t.get('bottleneck'),
                'created_at': t['created_at'],
            } for t in traces]
        })
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/traces/<trace_id>', methods=['GET'])
def get_search_trace(trace_id):
    """获取完整调试追踪"""
    try:
        trace = _search_traces.get(trace_id)
        if not trace:
            return _json_error('追踪不存在', 404)
        return jsonify(trace)
    except Exception as e:
        return _json_error(str(e), 500)


def _classify_query_intent(query):
    """简单的查询意图分类"""
    if any(kw in query for kw in ['什么', '哪些', '怎么', '如何', '为什么', 'what', 'how', 'why']):
        return 'factual_qa'
    if any(kw in query for kw in ['对比', '差异', '区别', '不同', 'compare', 'difference']):
        return 'comparison'
    if any(kw in query for kw in ['故障', '错误', '异常', '超时', 'error', 'fail', 'timeout']):
        return 'troubleshooting'
    if any(kw in query for kw in ['步骤', '流程', '操作', '执行', 'step', 'process']):
        return 'procedural'
    return 'general'


def _expand_query_terms(tokens):
    """模拟查询扩展"""
    expanded = list(tokens)
    synonym_map = {
        '故障': ['异常', '错误', '问题'],
        '告警': ['报警', '预警', '监控'],
        '处理': ['处置', '操作', '执行'],
        '审批': ['审核', '批准', '确认'],
        '风机': ['机组', '风力发电机'],
        '数据库': ['DB', '存储'],
        '优化': ['调优', '改进', '提升'],
    }
    for token in tokens:
        if token in synonym_map:
            expanded.extend(synonym_map[token])
    return list(set(expanded))


def _analyze_score_distribution(results):
    """分析分数分布"""
    if not results:
        return {'histogram': [], 'mean': 0, 'std': 0, 'median': 0, 'p90': 0, 'skew': 'empty'}

    scores = [_extract_score(r) for r in results]
    scores.sort()
    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    std = math.sqrt(variance) if variance > 0 else 0
    median = scores[n // 2]
    p90 = scores[int(n * 0.9)] if n > 1 else scores[0]

    # Histogram buckets: [0-0.2), [0.2-0.4), [0.4-0.6), [0.6-0.8), [0.8-1.0]
    buckets = [0] * 5
    for s in scores:
        idx = min(int(s * 5), 4)
        buckets[idx] += 1

    skew = 'right_skewed' if mean > median else ('left_skewed' if mean < median else 'symmetric')

    return {
        'histogram': [
            {'range': '0-20%', 'count': buckets[0]},
            {'range': '20-40%', 'count': buckets[1]},
            {'range': '40-60%', 'count': buckets[2]},
            {'range': '60-80%', 'count': buckets[3]},
            {'range': '80-100%', 'count': buckets[4]},
        ],
        'mean': round(mean, 4),
        'std': round(std, 4),
        'median': round(median, 4),
        'p90': round(p90, 4),
        'skew': skew,
        'quality_grade': 'A' if mean > 0.7 else ('B' if mean > 0.5 else ('C' if mean > 0.3 else 'D')),
    }


def _analyze_context_expansion(results):
    """分析上下文扩展效果"""
    total_merged = 0
    total_section = 0
    window_modes = 0
    section_modes = 0

    for r in results:
        meta = r.get('metadata', {})
        merged = meta.get('merged_chunk_ids', [])
        section = meta.get('section_chunk_ids', [])
        total_merged += len(merged) if isinstance(merged, list) else 0
        total_section += len(section) if isinstance(section, list) else 0
        mode = meta.get('context_mode', '')
        if mode == 'window':
            window_modes += 1
        elif mode == 'section':
            section_modes += 1

    return {
        'total_expanded_chunks': total_merged + total_section,
        'avg_merged_per_result': round(total_merged / max(len(results), 1), 2),
        'avg_section_per_result': round(total_section / max(len(results), 1), 2),
        'window_mode_count': window_modes,
        'section_mode_count': section_modes,
        'expansion_ratio': round((total_merged + total_section) / max(len(results), 1), 2),
    }


def _analyze_result_diversity(results):
    """分析结果多样性"""
    if not results:
        return {'unique_documents': 0, 'diversity_score': 0, 'doc_distribution': []}

    doc_counts = Counter()
    for r in results:
        meta = r.get('metadata', {})
        doc_name = meta.get('doc_name') or meta.get('doc_id') or 'unknown'
        doc_counts[doc_name] += 1

    unique = len(doc_counts)
    total = len(results)
    entropy = 0
    for count in doc_counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(total) if total > 1 else 1
    diversity_score = round(entropy / max(max_entropy, 1), 4)

    return {
        'unique_documents': unique,
        'diversity_score': diversity_score,
        'doc_distribution': [
            {'doc_name': name, 'hit_count': count, 'ratio': round(count / total, 3)}
            for name, count in doc_counts.most_common()
        ],
        'concentration': 'high' if diversity_score < 0.3 else ('medium' if diversity_score < 0.6 else 'low'),
    }


# ════════════════════════════════════════════════════════════════
#  Knowledge Graph — 知识图谱抽取
# ════════════════════════════════════════════════════════════════

@knowledge_bp.route('/bases/<kb_id>/knowledge-graph', methods=['GET'])
def get_knowledge_graph(kb_id):
    """从知识库文档中抽取实体和关系组成知识图谱"""
    try:
        kb = knowledge_manager.get_knowledge_base(kb_id)
        if not kb:
            return _json_error('知识库不存在', 404)

        nodes = []
        edges = []
        node_set = set()
        edge_set = set()

        # Extract entities from documents
        for doc_id in kb.documents:
            doc = knowledge_manager.get_document(doc_id)
            if not doc:
                continue

            doc_node_id = f"doc_{doc_id[:8]}"
            if doc_node_id not in node_set:
                nodes.append({
                    'id': doc_node_id,
                    'label': doc.name,
                    'type': 'document',
                    'size': len(doc.chunks),
                    'metadata': {'doc_id': doc_id, 'file_type': doc.type},
                })
                node_set.add(doc_node_id)

            content = doc.content or ''
            entities = _extract_entities(content)

            for entity in entities:
                eid = f"entity_{hashlib.md5(entity['text'].encode()).hexdigest()[:10]}"
                if eid not in node_set:
                    nodes.append({
                        'id': eid,
                        'label': entity['text'],
                        'type': entity['type'],
                        'size': entity.get('frequency', 1),
                        'metadata': {'source_doc': doc.name},
                    })
                    node_set.add(eid)

                edge_key = f"{doc_node_id}->{eid}"
                if edge_key not in edge_set:
                    edges.append({
                        'source': doc_node_id,
                        'target': eid,
                        'relation': 'mentions',
                        'weight': entity.get('frequency', 1),
                    })
                    edge_set.add(edge_key)

            # Cross-entity relations
            for i, e1 in enumerate(entities):
                for e2 in entities[i + 1:]:
                    eid1 = f"entity_{hashlib.md5(e1['text'].encode()).hexdigest()[:10]}"
                    eid2 = f"entity_{hashlib.md5(e2['text'].encode()).hexdigest()[:10]}"
                    edge_key = f"{eid1}<->{eid2}"
                    if edge_key not in edge_set and eid1 != eid2:
                        edges.append({
                            'source': eid1,
                            'target': eid2,
                            'relation': 'co_occurs',
                            'weight': 1,
                        })
                        edge_set.add(edge_key)

        return jsonify({
            'kb_id': kb_id,
            'node_count': len(nodes),
            'edge_count': len(edges),
            'nodes': nodes[:200],
            'edges': edges[:500],
            'entity_types': list(set(n['type'] for n in nodes)),
        })
    except Exception as e:
        return _json_error(str(e), 500)


def _extract_entities(text):
    """从文本中抽取命名实体（简易规则引擎）"""
    entities = []
    entity_map = {}

    # Chinese org/location/tech patterns
    patterns = [
        (r'(?:[\u4e00-\u9fff]{2,6}(?:公司|集团|部门|中心|局|厅|院|所|站|厂))', 'organization'),
        (r'(?:[\u4e00-\u9fff]{2,6}(?:省|市|区|县|镇|街|路|号))', 'location'),
        (r'(?:[\u4e00-\u9fff]{2,8}(?:系统|平台|模块|组件|服务|接口|数据库|中间件))', 'system'),
        (r'(?:[\u4e00-\u9fff]{2,6}(?:风机|机组|变压器|主变|线路|开关|设备))', 'equipment'),
        (r'(?:[\u4e00-\u9fff]{2,8}(?:规程|制度|标准|规范|手册|流程|方案|预案))', 'regulation'),
        (r'(?:[A-Z][a-zA-Z]+(?:SQL|DB|API|SDK|HTTP|TCP|IP|DNS|SSL|TLS|JWT|OAuth|SSH|FTP))', 'technology'),
        (r'(?:(?:MongoDB|Redis|MySQL|PostgreSQL|Elasticsearch|Kafka|RabbitMQ|Docker|Kubernetes|K8s))', 'technology'),
    ]

    for pattern, entity_type in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) < 2 or len(match) > 20:
                continue
            key = match.strip()
            if key in entity_map:
                entity_map[key]['frequency'] += 1
            else:
                entity_map[key] = {
                    'text': key,
                    'type': entity_type,
                    'frequency': 1,
                }

    entities = sorted(entity_map.values(), key=lambda x: x['frequency'], reverse=True)
    return entities[:60]


# ════════════════════════════════════════════════════════════════
#  Chunk Browser — 分块浏览器
# ════════════════════════════════════════════════════════════════

@knowledge_bp.route('/bases/<kb_id>/documents/<doc_id>/chunks', methods=['GET'])
def get_document_chunks(kb_id, doc_id):
    """获取文档的所有分块详情，含向量就绪状态"""
    try:
        doc = knowledge_manager.get_document(doc_id)
        if not doc:
            return _json_error('文档不存在', 404)

        chunks = []
        for i, chunk in enumerate(doc.chunks):
            has_embedding = chunk.embedding is not None and len(chunk.embedding) > 0
            chunks.append({
                'id': chunk.id,
                'index': i,
                'content': chunk.content,
                'char_count': len(chunk.content),
                'word_count': len(chunk.content.split()),
                'has_embedding': has_embedding,
                'metadata': chunk.metadata,
                'content_hash': hashlib.md5(chunk.content.encode()).hexdigest()[:12],
            })

        return jsonify({
            'doc_id': doc_id,
            'doc_name': doc.name,
            'total_chunks': len(chunks),
            'total_chars': sum(c['char_count'] for c in chunks),
            'embedding_coverage': round(
                sum(1 for c in chunks if c['has_embedding']) / max(len(chunks), 1), 3
            ),
            'chunks': chunks,
        })
    except Exception as e:
        return _json_error(str(e), 500)


# ════════════════════════════════════════════════════════════════
#  Document Annotations — 文档标注系统
# ════════════════════════════════════════════════════════════════

@knowledge_bp.route('/bases/<kb_id>/documents/<doc_id>/annotations', methods=['GET'])
def list_annotations(kb_id, doc_id):
    """列出文档的所有标注"""
    try:
        annotations = _annotations_store.get(doc_id, [])
        return jsonify({
            'doc_id': doc_id,
            'annotation_count': len(annotations),
            'annotations': annotations,
            'tag_summary': dict(Counter(
                tag for a in annotations for tag in a.get('tags', [])
            )),
        })
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>/documents/<doc_id>/annotations', methods=['POST'])
def create_annotation(kb_id, doc_id):
    """创建文档标注（可关联到具体 chunk）"""
    try:
        data = _request_json()
        text = (data.get('text') or '').strip()
        if not text:
            return _json_error('标注内容不能为空')

        annotation = {
            'id': str(uuid.uuid4())[:12],
            'doc_id': doc_id,
            'chunk_id': (data.get('chunk_id') or '').strip(),
            'text': text,
            'label': data.get('label', 'note'),  # note | issue | question | highlight | qa_pair
            'author': data.get('author', 'anonymous'),
            'tags': data.get('tags', []),
            'qa_answer': data.get('qa_answer', ''),  # For QA pair annotations
            'created_at': datetime.now().isoformat(),
        }

        if doc_id not in _annotations_store:
            _annotations_store[doc_id] = []
        _annotations_store[doc_id].append(annotation)

        return jsonify(annotation)
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>/documents/<doc_id>/annotations/<ann_id>', methods=['DELETE'])
def delete_annotation(kb_id, doc_id, ann_id):
    """删除标注"""
    try:
        annotations = _annotations_store.get(doc_id, [])
        _annotations_store[doc_id] = [a for a in annotations if a['id'] != ann_id]
        return _json_success()
    except Exception as e:
        return _json_error(str(e), 500)


# ════════════════════════════════════════════════════════════════
#  Quality Assessment — 知识库质量评估
# ════════════════════════════════════════════════════════════════

@knowledge_bp.route('/bases/<kb_id>/quality-report', methods=['POST'])
def generate_quality_report(kb_id):
    """生成知识库质量评估报告"""
    try:
        kb = knowledge_manager.get_knowledge_base(kb_id)
        if not kb:
            return _json_error('知识库不存在', 404)

        report_id = str(uuid.uuid4())[:12]
        docs = []
        all_chunks = []
        doc_analyses = []

        for doc_id in kb.documents:
            doc = knowledge_manager.get_document(doc_id)
            if not doc:
                continue
            docs.append(doc)
            all_chunks.extend(doc.chunks)

            # Per-document analysis
            chunk_sizes = [len(c.content) for c in doc.chunks]
            embedding_ready = sum(1 for c in doc.chunks if c.embedding and len(c.embedding) > 0)
            doc_analyses.append({
                'doc_id': doc_id,
                'doc_name': doc.name,
                'doc_type': doc.type,
                'chunk_count': len(doc.chunks),
                'avg_chunk_size': round(sum(chunk_sizes) / max(len(chunk_sizes), 1)),
                'min_chunk_size': min(chunk_sizes) if chunk_sizes else 0,
                'max_chunk_size': max(chunk_sizes) if chunk_sizes else 0,
                'chunk_size_std': round(_std(chunk_sizes), 1),
                'embedding_coverage': round(embedding_ready / max(len(doc.chunks), 1), 3),
                'total_chars': len(doc.content or ''),
                'annotation_count': len(_annotations_store.get(doc_id, [])),
            })

        # Overall metrics
        total_chunks = len(all_chunks)
        chunk_sizes = [len(c.content) for c in all_chunks]
        embedding_ready = sum(1 for c in all_chunks if c.embedding and len(c.embedding) > 0)

        # Content diversity check
        content_hashes = set()
        duplicate_chunks = 0
        for c in all_chunks:
            h = hashlib.md5(c.content.encode()).hexdigest()
            if h in content_hashes:
                duplicate_chunks += 1
            content_hashes.add(h)

        # Chunk length analysis
        short_chunks = sum(1 for s in chunk_sizes if s < 50)
        long_chunks = sum(1 for s in chunk_sizes if s > 2000)

        # Calculate quality score
        scores = {
            'embedding_coverage': round(embedding_ready / max(total_chunks, 1), 3),
            'duplicate_ratio': round(1 - duplicate_chunks / max(total_chunks, 1), 3),
            'chunk_quality': round(1 - (short_chunks + long_chunks) / max(total_chunks, 1), 3),
            'doc_diversity': round(min(len(docs) / 5, 1.0), 3),
            'annotation_density': round(min(
                sum(len(_annotations_store.get(d.id, [])) for d in docs) / max(total_chunks, 1), 1.0
            ), 3),
        }
        overall_score = round(sum(scores.values()) / max(len(scores), 1), 3)

        # Grade
        if overall_score >= 0.85:
            grade = 'A'
        elif overall_score >= 0.70:
            grade = 'B'
        elif overall_score >= 0.50:
            grade = 'C'
        else:
            grade = 'D'

        # Recommendations
        recommendations = []
        if scores['embedding_coverage'] < 0.9:
            recommendations.append({
                'type': 'warning',
                'area': 'embedding',
                'message': f"向量覆盖率 {scores['embedding_coverage']*100:.0f}%，建议重建向量索引",
            })
        if duplicate_chunks > 0:
            recommendations.append({
                'type': 'info',
                'area': 'duplicate',
                'message': f"检测到 {duplicate_chunks} 个重复分块，可能影响检索精度",
            })
        if short_chunks > 0:
            recommendations.append({
                'type': 'warning',
                'area': 'chunk_size',
                'message': f"有 {short_chunks} 个过短分块（<50字符），可能缺乏语义信息",
            })
        if long_chunks > 0:
            recommendations.append({
                'type': 'info',
                'area': 'chunk_size',
                'message': f"有 {long_chunks} 个过长分块（>2000字符），可能降低召回精度",
            })
        if not docs:
            recommendations.append({
                'type': 'critical',
                'area': 'content',
                'message': "知识库没有文档，请先上传资料",
            })

        report = {
            'report_id': report_id,
            'kb_id': kb_id,
            'kb_name': kb.name,
            'created_at': datetime.now().isoformat(),
            'overview': {
                'document_count': len(docs),
                'total_chunks': total_chunks,
                'total_chars': sum(len(d.content or '') for d in docs),
                'embedding_ready': embedding_ready,
                'duplicate_chunks': duplicate_chunks,
                'short_chunks': short_chunks,
                'long_chunks': long_chunks,
            },
            'scores': scores,
            'overall_score': overall_score,
            'grade': grade,
            'doc_analyses': doc_analyses,
            'chunk_size_stats': {
                'mean': round(sum(chunk_sizes) / max(len(chunk_sizes), 1)),
                'std': round(_std(chunk_sizes), 1),
                'min': min(chunk_sizes) if chunk_sizes else 0,
                'max': max(chunk_sizes) if chunk_sizes else 0,
                'median': sorted(chunk_sizes)[len(chunk_sizes) // 2] if chunk_sizes else 0,
            },
            'recommendations': recommendations,
        }

        _quality_reports[kb_id] = report
        return jsonify(report)
    except Exception as e:
        return _json_error(str(e), 500)


@knowledge_bp.route('/bases/<kb_id>/quality-report', methods=['GET'])
def get_quality_report(kb_id):
    """获取最近一次质量评估报告"""
    try:
        report = _quality_reports.get(kb_id)
        if not report:
            return _json_error('暂无质量报告，请先运行评估', 404)
        return jsonify(report)
    except Exception as e:
        return _json_error(str(e), 500)


def _std(values):
    if not values:
        return 0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


# ════════════════════════════════════════════════════════════════
#  Retrieval Heatmap — 检索热力图
# ════════════════════════════════════════════════════════════════

@knowledge_bp.route('/bases/<kb_id>/retrieval-heatmap', methods=['POST'])
def retrieval_heatmap(kb_id):
    """对指定文档的所有分块运行查询，生成按块的热力图分布"""
    try:
        data = _request_json()
        query = (data.get('query') or '').strip()
        doc_id = (data.get('doc_id') or '').strip()
        top_k = min(int(data.get('top_k', 20) or 20), 100)

        if not query:
            return _json_error('查询内容不能为空')

        results = knowledge_manager.search(kb_id, query, top_k)

        # Build chunk score map
        chunk_scores = {}
        for r in results:
            meta = r.get('metadata', {})
            chunk_id = meta.get('retrieved_chunk_id') or r.get('chunk_id') or r.get('id')
            if chunk_id:
                chunk_scores[chunk_id] = _extract_score(r)
            for mid in meta.get('merged_chunk_ids', []):
                if mid and mid not in chunk_scores:
                    chunk_scores[mid] = _extract_score(r) * 0.7

        # Get document chunks if doc_id specified
        heatmap_data = []
        if doc_id:
            doc = knowledge_manager.get_document(doc_id)
            if doc:
                for i, chunk in enumerate(doc.chunks):
                    score = chunk_scores.get(chunk.id, 0)
                    heatmap_data.append({
                        'chunk_index': i,
                        'chunk_id': chunk.id,
                        'score': round(score, 4),
                        'is_hit': score > 0,
                        'content_preview': chunk.content[:120],
                        'intensity': 'high' if score > 0.6 else ('medium' if score > 0.3 else ('low' if score > 0 else 'none')),
                    })

        return jsonify({
            'query': query,
            'kb_id': kb_id,
            'doc_id': doc_id,
            'total_chunks_scored': len(chunk_scores),
            'heatmap': heatmap_data,
            'hit_rate': round(sum(1 for h in heatmap_data if h['is_hit']) / max(len(heatmap_data), 1), 3),
            'avg_hit_score': round(
                sum(h['score'] for h in heatmap_data if h['is_hit']) / max(sum(1 for h in heatmap_data if h['is_hit']), 1), 4
            ),
        })
    except Exception as e:
        return _json_error(str(e), 500)
