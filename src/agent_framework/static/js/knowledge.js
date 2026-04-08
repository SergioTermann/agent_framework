/**
 * 知识库管理前端脚本
 */

let currentKB = null;
let knowledgeBases = [];
let servingEndpoints = [];
const DEFAULT_RAG_SETTINGS = {
    chunk_size: 500,
    chunk_overlap: 50,
    search_top_k: 5,
    candidate_top_k: 30,
    retrieval_score_threshold: 0.1,
    mmr_lambda: 0.78,
    window_size: 1,
    window_max_chars: 1600,
    section_max_chars: 2400,
    query_expansion_enabled: true
};

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    loadStats();
    loadKnowledgeBases();
    loadServingEndpoints();
    initDragAndDrop();
});

// 加载统计信息
async function loadStats() {
    try {
        const response = await fetch('/api/knowledge/stats');
        const data = await response.json();

        document.getElementById('kbCount').textContent = data.knowledge_base_count || 0;
        document.getElementById('docCount').textContent = data.document_count || 0;
        document.getElementById('chunkCount').textContent = data.chunk_count || 0;
    } catch (error) {
        console.error('加载统计信息失败:', error);
    }
}

// 加载知识库列表
async function loadKnowledgeBases() {
    try {
        const response = await fetch('/api/knowledge/bases');
        const data = await response.json();

        knowledgeBases = data.knowledge_bases || [];
        renderKnowledgeBases();
    } catch (error) {
        console.error('加载知识库列表失败:', error);
        document.getElementById('kbList').innerHTML = '<div class="loading">加载失败</div>';
    }
}

// 渲染知识库列表
function renderKnowledgeBases() {
    const list = document.getElementById('kbList');

    if (knowledgeBases.length === 0) {
        list.innerHTML = '<div class="empty-state" style="padding: 20px;"><p>还没有知识库，先建一个再把资料收进来。</p></div>';
        return;
    }

    list.innerHTML = '';
    knowledgeBases.forEach(kb => {
        const item = document.createElement('div');
        item.className = 'kb-item';
        if (currentKB && currentKB.id === kb.id) {
            item.classList.add('active');
        }

        item.innerHTML = `
            <div class="kb-name">${kb.name}</div>
            <div class="kb-info">${kb.document_count} 个文档</div>
        `;

        item.onclick = () => selectKB(kb.id);
        list.appendChild(item);
    });
}

// 选择知识库
async function selectKB(kbId) {
    try {
        const response = await fetch(`/api/knowledge/bases/${kbId}`);
        const data = await response.json();

        currentKB = data;
        await loadServingEndpoints(false);
        renderKnowledgeBases();
        renderKBContent();
    } catch (error) {
        console.error('加载知识库详情失败:', error);
        alert('知识库加载失败');
    }
}

async function loadServingEndpoints(render = true) {
    try {
        const response = await fetch('/api/pipeline/endpoints/list?status=running');
        const data = await response.json();
        servingEndpoints = data.data || [];
        if (render && currentKB) {
            renderKBSettings();
        }
    } catch (error) {
        console.error('加载模型端点失败:', error);
        servingEndpoints = [];
        if (render && currentKB) {
            renderKBSettings();
        }
    }
}

function renderEndpointOptions(selectId, endpointType, selectedValue, emptyText) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const endpoints = servingEndpoints.filter(ep => ep.endpoint_type === endpointType);
    const options = [
        `<option value="">${emptyText}</option>`,
        ...endpoints.map(ep => {
            const label = `${ep.model_name || ep.endpoint_id} · ${ep.backend} · ${ep.base_url}`;
            const selected = ep.endpoint_id === selectedValue ? 'selected' : '';
            return `<option value="${ep.endpoint_id}" ${selected}>${label}</option>`;
        })
    ];
    select.innerHTML = options.join('');
}

function getRAGSettings(metadata = {}) {
    return {
        ...DEFAULT_RAG_SETTINGS,
        ...(metadata.rag_settings || {})
    };
}

function renderRAGSettingsInputs(ragSettings) {
    document.getElementById('ragChunkSizeInput').value = ragSettings.chunk_size;
    document.getElementById('ragChunkOverlapInput').value = ragSettings.chunk_overlap;
    document.getElementById('ragSearchTopKInput').value = ragSettings.search_top_k;
    document.getElementById('ragCandidateTopKInput').value = ragSettings.candidate_top_k;
    document.getElementById('ragScoreThresholdInput').value = ragSettings.retrieval_score_threshold;
    document.getElementById('ragMmrLambdaInput').value = ragSettings.mmr_lambda;
    document.getElementById('ragWindowSizeInput').value = ragSettings.window_size;
    document.getElementById('ragWindowCharsInput').value = ragSettings.window_max_chars;
    document.getElementById('ragSectionCharsInput').value = ragSettings.section_max_chars;
    document.getElementById('ragQueryExpansionInput').checked = !!ragSettings.query_expansion_enabled;
}

function collectRAGSettingsFromInputs() {
    return {
        chunk_size: Number(document.getElementById('ragChunkSizeInput').value || DEFAULT_RAG_SETTINGS.chunk_size),
        chunk_overlap: Number(document.getElementById('ragChunkOverlapInput').value || DEFAULT_RAG_SETTINGS.chunk_overlap),
        search_top_k: Number(document.getElementById('ragSearchTopKInput').value || DEFAULT_RAG_SETTINGS.search_top_k),
        candidate_top_k: Number(document.getElementById('ragCandidateTopKInput').value || DEFAULT_RAG_SETTINGS.candidate_top_k),
        retrieval_score_threshold: Number(document.getElementById('ragScoreThresholdInput').value || DEFAULT_RAG_SETTINGS.retrieval_score_threshold),
        mmr_lambda: Number(document.getElementById('ragMmrLambdaInput').value || DEFAULT_RAG_SETTINGS.mmr_lambda),
        window_size: Number(document.getElementById('ragWindowSizeInput').value || DEFAULT_RAG_SETTINGS.window_size),
        window_max_chars: Number(document.getElementById('ragWindowCharsInput').value || DEFAULT_RAG_SETTINGS.window_max_chars),
        section_max_chars: Number(document.getElementById('ragSectionCharsInput').value || DEFAULT_RAG_SETTINGS.section_max_chars),
        query_expansion_enabled: !!document.getElementById('ragQueryExpansionInput').checked
    };
}

function setKBSettingsStatus(message, isError = false) {
    const status = document.getElementById('kbSettingsStatus');
    if (!status) return;
    status.textContent = message || '';
    status.style.color = isError ? '#b91c1c' : '#64748b';
}

function renderKBSettings() {
    if (!currentKB) return;
    const metadata = currentKB.metadata || {};
    const ragSettings = getRAGSettings(metadata);
    renderEndpointOptions('embeddingEndpointSelect', 'embedding', metadata.embedding_endpoint_id || '', '\u4f7f\u7528\u5185\u7f6e\u672c\u5730\u5411\u91cf\u6a21\u578b');
    renderEndpointOptions('rerankEndpointSelect', 'rerank', metadata.rerank_endpoint_id || '', '\u4f7f\u7528\u5185\u7f6e\u672c\u5730\u91cd\u6392\u6a21\u578b');
    renderRAGSettingsInputs(ragSettings);

    const embeddingName = metadata.embedding_endpoint_name
        ? `\u5411\u91cf\u6a21\u578b\uff1a${metadata.embedding_endpoint_name}`
        : '\u5411\u91cf\u6a21\u578b\uff1a\u672c\u5730\u54c8\u5e0c\u5411\u91cf';
    const rerankName = metadata.rerank_endpoint_name
        ? `\u91cd\u6392\u6a21\u578b\uff1a${metadata.rerank_endpoint_name}`
        : '\u91cd\u6392\u6a21\u578b\uff1a\u672c\u5730\u8f7b\u91cf\u91cd\u6392\u5668';
    setKBSettingsStatus(`${embeddingName} \uff5c ${rerankName} \uff5c Chunk=${ragSettings.chunk_size}/${ragSettings.chunk_overlap} \uff5c Top-K=${ragSettings.search_top_k}`);
}

// 渲染知识库内容
function renderKBContent() {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('kbContent').style.display = 'block';

    document.getElementById('kbTitle').textContent = currentKB.name;
    renderKBSettings();

    // 渲染文档列表
    const docList = document.getElementById('docList');
    docList.innerHTML = '';

    if (!currentKB.documents || currentKB.documents.length === 0) {
        docList.innerHTML = '<div class="empty-state"><p>这套知识还没有资料，先上传文档再验证检索效果。</p></div>';
        return;
    }

    currentKB.documents.forEach(doc => {
        const item = document.createElement('div');
        item.className = 'doc-item';

        const icon = getFileIcon(doc.type);
        const size = formatFileSize(doc.size);

        item.innerHTML = `
            <div class="doc-header">
                <div class="doc-icon">${icon}</div>
                <div class="doc-actions">
                    <button class="icon-btn" onclick="deleteDocument('${doc.id}')" title="删除">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="doc-name">${doc.name}</div>
            <div class="doc-info">${size} · ${doc.chunk_count} 块</div>
        `;

        docList.appendChild(item);
    });
}

// 获取文件图标
function getFileIcon(type) {
    const icons = {
        'pdf': '📄',
        'docx': '📝',
        'doc': '📝',
        'md': '📋',
        'markdown': '📋',
        'txt': '📃'
    };
    return icons[type] || '📄';
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// 显示创建知识库模态框
function showCreateKBModal() {
    document.getElementById('createKBModal').classList.add('active');
    document.getElementById('kbName').value = '';
    document.getElementById('kbDescription').value = '';
}

// 关闭创建知识库模态框
function closeCreateKBModal() {
    document.getElementById('createKBModal').classList.remove('active');
}

// 创建知识库
async function createKB() {
    const name = document.getElementById('kbName').value.trim();
    const description = document.getElementById('kbDescription').value.trim();

    if (!name) {
        alert('先填写知识库名称');
        return;
    }

    try {
        const response = await fetch('/api/knowledge/bases', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });

        if (!response.ok) {
            throw new Error('创建失败');
        }

        const data = await response.json();

        closeCreateKBModal();
        await loadKnowledgeBases();
        await loadStats();
        await selectKB(data.id);
    } catch (error) {
        console.error('创建知识库失败:', error);
        alert('新建知识库失败');
    }
}

async function saveKBSettings() {
    if (!currentKB) {
        alert('\u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u77e5\u8bc6\u5e93');
        return;
    }

    const embedding_endpoint_id = document.getElementById('embeddingEndpointSelect').value;
    const rerank_endpoint_id = document.getElementById('rerankEndpointSelect').value;
    const rag_settings = collectRAGSettingsFromInputs();
    setKBSettingsStatus('\u6b63\u5728\u4fdd\u5b58\u8bbe\u7f6e...');

    try {
        const response = await fetch(`/api/knowledge/bases/${currentKB.id}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ embedding_endpoint_id, rerank_endpoint_id, rag_settings })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || '\u4fdd\u5b58\u8bbe\u7f6e\u5931\u8d25');
        }

        currentKB.metadata = data.metadata || {};
        setKBSettingsStatus('\u8bbe\u7f6e\u5df2\u4fdd\u5b58\uff1b\u5982\u679c\u4f60\u4fee\u6539\u4e86\u5206\u5757\u53c2\u6570\u6216\u66f4\u6362\u4e86\u5411\u91cf\u6a21\u578b\u7aef\u70b9\uff0c\u5efa\u8bae\u7acb\u5373\u91cd\u5efa\u5411\u91cf\u3002');
        renderKBSettings();
    } catch (error) {
        console.error('\u4fdd\u5b58\u77e5\u8bc6\u5e93\u8bbe\u7f6e\u5931\u8d25:', error);
        setKBSettingsStatus(error.message || '\u4fdd\u5b58\u8bbe\u7f6e\u5931\u8d25', true);
        alert('\u4fdd\u5b58\u8bbe\u7f6e\u5931\u8d25: ' + (error.message || '\u672a\u77e5\u9519\u8bef'));
    }
}

async function rebuildKBEmbeddings() {
    if (!currentKB) {
        alert('请先选择一个知识库');
        return;
    }

    if (!confirm('确定要根据当前 embedding 配置重建该知识库的向量吗？这会重新写入全部文档块向量。')) {
        return;
    }

    setKBSettingsStatus('\u6b63\u5728\u91cd\u5efa\u5411\u91cf...');

    try {
        const response = await fetch(`/api/knowledge/bases/${currentKB.id}/reindex`, {
            method: 'POST'
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || '重建向量失败');
        }

        currentKB.metadata = (data.knowledge_base || {}).metadata || currentKB.metadata || {};
        setKBSettingsStatus('向量已重建完成。');
        await selectKB(currentKB.id);
        await loadStats();
    } catch (error) {
        console.error('重建知识库向量失败:', error);
        setKBSettingsStatus(error.message || '重建向量失败', true);
        alert('重建向量失败: ' + (error.message || '未知错误'));
    }
}

// 删除当前知识库
async function deleteCurrentKB() {
    if (!currentKB) return;

    if (!confirm(`确定要删除知识库"${currentKB.name}"吗？此操作不可恢复。`)) {
        return;
    }

    try {
        const response = await fetch(`/api/knowledge/bases/${currentKB.id}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('删除失败');
        }

        currentKB = null;
        document.getElementById('emptyState').style.display = 'block';
        document.getElementById('kbContent').style.display = 'none';

        await loadKnowledgeBases();
        await loadStats();
    } catch (error) {
        console.error('删除知识库失败:', error);
        alert('删除当前知识库失败');
    }
}

// 上传文件
async function uploadFile(event) {
    if (!currentKB) {
        alert('先选择一个知识库');
        return;
    }

    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        // 显示上传中状态
        const uploadArea = document.getElementById('uploadArea');
        uploadArea.innerHTML = '<div class="loading">资料上传中...</div>';

        const response = await fetch(`/api/knowledge/bases/${currentKB.id}/documents`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || '上传失败');
        }

        // 重新加载知识库
        await selectKB(currentKB.id);
        await loadStats();

        // 恢复上传区域
        uploadArea.innerHTML = `
            <div class="upload-icon"><i class="fas fa-cloud-upload-alt"></i></div>
            <div class="upload-text">把资料拖进来，先把知识底座搭起来</div>
            <div class="upload-hint">支持 PDF、Word、Markdown、TXT，上传后会进入分块与检索流程</div>
        `;

        alert('资料已经入库，可以开始检索验证了');
    } catch (error) {
        console.error('上传文件失败:', error);
        alert('资料上传失败: ' + error.message);

        // 恢复上传区域
        const uploadArea = document.getElementById('uploadArea');
        uploadArea.innerHTML = `
            <div class="upload-icon"><i class="fas fa-cloud-upload-alt"></i></div>
            <div class="upload-text">把资料拖进来，先把知识底座搭起来</div>
            <div class="upload-hint">支持 PDF、Word、Markdown、TXT，上传后会进入分块与检索流程</div>
        `;
    }

    // 清空文件输入
    event.target.value = '';
}

// 删除文档
async function deleteDocument(docId) {
    if (!currentKB) return;

    if (!confirm('确定要删除这个文档吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/knowledge/bases/${currentKB.id}/documents/${docId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('删除失败');
        }

        await selectKB(currentKB.id);
        await loadStats();
    } catch (error) {
        console.error('删除文档失败:', error);
        alert('删除资料失败');
    }
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

function truncateText(text, maxLength = 220) {
    const normalized = String(text ?? '').replace(/\s+/g, ' ').trim();
    if (normalized.length <= maxLength) {
        return normalized;
    }
    return normalized.slice(0, Math.max(0, maxLength - 3)) + '...';
}

function formatSearchScore(result) {
    const rawScore = Number(
        result.retrieval_score
        ?? result.score
        ?? (typeof result.distance === 'number' ? (1 - result.distance) : 0)
    );
    return Number.isFinite(rawScore) ? Math.max(0, Math.min(1, rawScore)) : 0;
}

function renderSearchResultCard(result, index) {
    const metadata = result.metadata || {};
    const score = formatSearchScore(result);
    const rerankerScore = Number(result.reranker_score ?? result.score ?? 0) || 0;
    const hybridScore = Number(result.hybrid_score ?? result.retrieval_score ?? result.score ?? 0) || 0;
    const lexicalScore = Number(result.lexical_score ?? 0) || 0;
    const vectorScore = Number(result.vector_score ?? 0) || 0;
    const mergedChunkIds = Array.isArray(metadata.merged_chunk_ids) ? metadata.merged_chunk_ids : [];
    const sectionChunkIds = Array.isArray(metadata.section_chunk_ids) ? metadata.section_chunk_ids : [];
    const docName = metadata.doc_name || '未知文档';
    const sectionTitle = metadata.section_title ? ` · ${metadata.section_title}` : '';
    const windowRange = (
        metadata.window_start !== undefined && metadata.window_end !== undefined
            ? ` · chunk ${metadata.window_start}-${metadata.window_end}`
            : ''
    );
    const sectionRange = (
        metadata.section_start !== undefined && metadata.section_end !== undefined
            ? ` · section ${metadata.section_start}-${metadata.section_end}`
            : ''
    );
    const contextMode = metadata.context_mode ? ` · 模式: ${metadata.context_mode}` : '';
    const rerankSource = metadata.rerank_features?.source ? ` · Rerank源: ${metadata.rerank_features.source}` : '';
    const snippet = truncateText(result.snippet || result.content || '', 240);
    const mergedContext = truncateText(result.content || '', 520);

    return `
        <div class="result-item">
            <div class="result-meta" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px;">
                <strong>知识#${index + 1}</strong>
                <span>来源: ${escapeHtml(docName)}${escapeHtml(sectionTitle)}${escapeHtml(windowRange)}${escapeHtml(sectionRange)}${escapeHtml(contextMode)}${escapeHtml(rerankSource)}</span>
                <span>最终分: ${(score * 100).toFixed(1)}%</span>
                <span>Rerank: ${(rerankerScore * 100).toFixed(1)}%</span>
                <span>Hybrid: ${(hybridScore * 100).toFixed(1)}%</span>
                <span>Lexical: ${(lexicalScore * 100).toFixed(1)}%</span>
                <span>Vector: ${(vectorScore * 100).toFixed(1)}%</span>
            </div>
            <div class="result-content"><strong>命中片段：</strong>${escapeHtml(snippet)}</div>
            <div class="result-content" style="margin-top:10px;"><strong>扩展上下文：</strong>${escapeHtml(mergedContext)}</div>
            <div class="result-meta" style="margin-top:10px;">
                合并块数: ${mergedChunkIds.length || 1} · Section块数: ${sectionChunkIds.length || 0}
            </div>
        </div>
    `;
}

// 搜索知识
async function searchKnowledge() {
    if (!currentKB) {
        alert('请先选择一个知识库');
        return;
    }

    const query = document.getElementById('searchInput').value.trim();
    const topK = Number(document.getElementById('ragSearchTopKInput')?.value || DEFAULT_RAG_SETTINGS.search_top_k);
    if (!query) {
        alert('先输入一个要验证的业务问题');
        return;
    }

    const resultsDiv = document.getElementById('searchResults');
    resultsDiv.innerHTML = '<div class="loading">正在验证这套知识能不能答上来...</div>';

    try {
        const response = await fetch(`/api/knowledge/bases/${currentKB.id}/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, top_k: topK })
        });

        if (!response.ok) {
            throw new Error('搜索失败');
        }

        const data = await response.json();

        if (!data.results || data.results.length === 0) {
            resultsDiv.innerHTML = '<div class="empty-state"><p>这套知识暂时没召回到相关内容，建议回头调整资料或检索参数。</p></div>';
            return;
        }

        resultsDiv.innerHTML = data.results
            .map((result, index) => renderSearchResultCard(result, index))
            .join('');
    } catch (error) {
        console.error('搜索失败:', error);
        resultsDiv.innerHTML = '<div class="empty-state"><p>检索失败，请稍后再试。</p></div>';
    }
}

// 初始化拖拽上传
function initDragAndDrop() {
    const uploadArea = document.getElementById('uploadArea');

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');

        if (!currentKB) {
            alert('先选择一个知识库');
            return;
        }

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const fileInput = document.getElementById('fileInput');
            fileInput.files = files;
            uploadFile({ target: fileInput });
        }
    });
}

// 回车搜索
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                searchKnowledge();
            }
        });
    }
});
