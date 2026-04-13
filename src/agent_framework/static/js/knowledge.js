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
    query_expansion_enabled: true,
};

const retrievalScenarios = [
    {
        id: "ops_qa",
        name: "运维问答",
        description: "验证制度、处置手册和 SOP 是否能准确召回。",
        query: "风机告警升级到区域值守前，现场需要先执行哪些动作？",
        topK: 5,
        threshold: 0.12,
    },
    {
        id: "policy_check",
        name: "制度核验",
        description: "适合验证标准、审批和流程型资料的召回质量。",
        query: "吊装审批最晚要提前多久发起，遇到特殊天气还需要补什么材料？",
        topK: 6,
        threshold: 0.15,
    },
    {
        id: "compare_plan",
        name: "方案对比",
        description: "适合多文档、多章节拼接的复杂检索场景。",
        query: "内蒙古东部和河北北部两个候选区域在建设条件和审批节奏上主要差异是什么？",
        topK: 8,
        threshold: 0.08,
    },
    {
        id: "incident_trace",
        name: "故障排查",
        description: "验证碎片化资料能否在一次检索里拼出完整上下文。",
        query: "连接池耗尽导致服务超时时，数据库扩容和 SQL 优化哪个动作优先级更高？",
        topK: 7,
        threshold: 0.10,
    },
];

function createCompareDraft(rag = DEFAULT_RAG_SETTINGS) {
    return {
        search_top_k: Number(rag.search_top_k ?? DEFAULT_RAG_SETTINGS.search_top_k),
        candidate_top_k: Number(rag.candidate_top_k ?? DEFAULT_RAG_SETTINGS.candidate_top_k),
        retrieval_score_threshold: Number(rag.retrieval_score_threshold ?? DEFAULT_RAG_SETTINGS.retrieval_score_threshold),
        mmr_lambda: Number(rag.mmr_lambda ?? DEFAULT_RAG_SETTINGS.mmr_lambda),
        window_size: Number(rag.window_size ?? DEFAULT_RAG_SETTINGS.window_size),
        section_max_chars: Number(rag.section_max_chars ?? DEFAULT_RAG_SETTINGS.section_max_chars),
        query_expansion_enabled: !!(rag.query_expansion_enabled ?? DEFAULT_RAG_SETTINGS.query_expansion_enabled),
    };
}

const state = {
    currentKB: null,
    knowledgeBases: [],
    servingEndpoints: [],
    kbStats: {
        knowledge_base_count: 0,
        document_count: 0,
        chunk_count: 0,
    },
    kbFilter: "",
    selectedDocId: "",
    selectedDocDetail: null,
    lastSearchResults: [],
    lastSearchQuery: "",
    searchHistory: [],
    activeScenarioId: "",
    compareDraft: createCompareDraft(DEFAULT_RAG_SETTINGS),
    searchComparison: null,
    selectedResultIndex: -1,
    highlightedChunkIds: [],
    federatedResults: null,
    lastPipelineTrace: null,
    knowledgeGraph: null,
    chunkBrowserData: null,
    annotations: null,
    qualityReport: null,
};

document.addEventListener("DOMContentLoaded", async () => {
    renderScenarioList();
    bindBaseEvents();
    await refreshWorkbench();
});

async function refreshWorkbench() {
    await Promise.all([loadStats(), loadKnowledgeBases(), loadServingEndpoints(false)]);
    renderGlobalMetrics();
    renderSearchHistory();
    renderHeroSummary();
    renderKBContent();
}

function bindBaseEvents() {
    initDragAndDrop();
    const quickInput = document.getElementById("quickSearchInput");
    if (quickInput) {
        quickInput.addEventListener("input", (event) => {
            const target = document.getElementById("searchInput");
            if (target) target.value = event.target.value;
        });
    }
}

async function loadStats() {
    try {
        const response = await fetch("/api/knowledge/stats");
        const data = await response.json();
        state.kbStats = {
            knowledge_base_count: Number(data.knowledge_base_count || 0),
            document_count: Number(data.document_count || 0),
            chunk_count: Number(data.chunk_count || 0),
        };
    } catch (error) {
        console.error("加载统计失败:", error);
    }
}

async function loadKnowledgeBases() {
    try {
        const response = await fetch("/api/knowledge/bases");
        const data = await response.json();
        state.knowledgeBases = Array.isArray(data.knowledge_bases) ? data.knowledge_bases : [];
        renderKnowledgeBases();
        updateSelectionChip();
    } catch (error) {
        console.error("加载知识库列表失败:", error);
        document.getElementById("kbList").innerHTML = '<div class="empty-card">知识库列表加载失败。</div>';
    }
}

async function loadServingEndpoints(render = true) {
    try {
        const response = await fetch("/api/pipeline/endpoints/list?status=running");
        const data = await response.json().catch(() => ({}));
        state.servingEndpoints = Array.isArray(data.data) ? data.data : [];
    } catch (error) {
        console.error("加载端点失败:", error);
        state.servingEndpoints = [];
    }
    if (render) {
        renderKBContent();
    }
}

function renderGlobalMetrics() {
    const metrics = [
        { label: "知识目录", value: state.kbStats.knowledge_base_count, copy: "当前已创建知识库" },
        { label: "文档总数", value: state.kbStats.document_count, copy: "所有知识库累计资料" },
        { label: "检索片段", value: state.kbStats.chunk_count, copy: "可进入召回的文本块" },
        { label: "模型端点", value: state.servingEndpoints.length, copy: "当前可绑定向量/重排端点" },
        { label: "标注数", value: state.kbStats.annotation_count || 0, copy: "所有文档的标注总数" },
        { label: "调试追踪", value: state.kbStats.trace_count || 0, copy: "管线调试记录数" },
    ];
    document.getElementById("globalMetricGrid").innerHTML = metrics.map((metric) => `
        <div class="metric-card">
            <div class="metric-label">${escapeHtml(metric.label)}</div>
            <div class="metric-value">${escapeHtml(String(metric.value))}</div>
            <div class="helper-copy">${escapeHtml(metric.copy)}</div>
        </div>
    `).join("");
}

function getFilteredKBs() {
    if (!state.kbFilter) return state.knowledgeBases;
    const keyword = state.kbFilter.toLowerCase();
    return state.knowledgeBases.filter((kb) => {
        const haystack = `${kb.name || ""} ${kb.description || ""}`.toLowerCase();
        return haystack.includes(keyword);
    });
}

function renderKnowledgeBases() {
    const container = document.getElementById("kbList");
    const items = getFilteredKBs();
    if (!items.length) {
        container.innerHTML = '<div class="empty-card">没有符合条件的知识库。可以先新建，或者修改筛选词。</div>';
        return;
    }

    container.innerHTML = items.map((kb) => {
        const isActive = state.currentKB && state.currentKB.id === kb.id;
        const rag = getRAGSettings(kb.metadata || {});
        return `
            <div class="kb-card ${isActive ? "is-active" : ""}" onclick="selectKB('${kb.id}')">
                <div class="card-head">
                    <div>
                        <div class="card-title">${escapeHtml(kb.name || "未命名知识库")}</div>
                        <div class="kb-meta">${escapeHtml(kb.description || "暂无描述")}</div>
                    </div>
                    <span class="chip">${escapeHtml(String(kb.document_count || 0))} 文档</span>
                </div>
                <div class="chip-row">
                    <span class="chip">Top-K ${escapeHtml(String(rag.search_top_k))}</span>
                    <span class="chip">Chunk ${escapeHtml(String(rag.chunk_size))}</span>
                    <span class="chip">${rag.query_expansion_enabled ? "扩展开" : "扩展关"}</span>
                </div>
            </div>
        `;
    }).join("");
}

async function selectKB(kbId) {
    try {
        const response = await fetch(`/api/knowledge/bases/${kbId}`);
        const data = await response.json();
        state.currentKB = data;
        state.selectedDocId = "";
        state.selectedDocDetail = null;
        state.lastSearchResults = [];
        state.selectedResultIndex = -1;
        state.highlightedChunkIds = [];
        state.searchComparison = null;
        state.compareDraft = createCompareDraft(getRAGSettings(data.metadata || {}));
        renderKnowledgeBases();
        renderHeroSummary();
        renderKBContent();
    } catch (error) {
        console.error("加载知识库详情失败:", error);
        window.alert("知识库加载失败");
    }
}

function renderKBContent() {
    renderCurrentKBSummary();
    renderKBMetrics();
    renderEndpointOptions();
    renderKBSettings();
    renderDocuments();
    renderDocDetailPanel();
    renderSearchMetrics();
    renderSearchResults();
    renderComparisonLab();
    renderRetrievalDiagnostics();
    renderSettingsInsights();
}

function renderCurrentKBSummary() {
    const currentChip = document.getElementById("currentKBChip");
    const descText = document.getElementById("kbDescriptionText");
    if (!state.currentKB) {
        currentChip.textContent = "未选择";
        descText.textContent = "当前还没有知识库描述。";
        return;
    }
    currentChip.textContent = `${state.currentKB.name} · ${state.currentKB.document_count || 0} 文档`;
    descText.textContent = state.currentKB.description || "当前知识库没有补充说明，建议写清服务场景和资料边界。";
}

function renderKBMetrics() {
    const container = document.getElementById("kbMetricGrid");
    if (!state.currentKB) {
        container.innerHTML = '<div class="empty-card">先选择一个知识库，这里会显示文档量、分块量和当前配置状态。</div>';
        return;
    }
    const docs = Array.isArray(state.currentKB.documents) ? state.currentKB.documents : [];
    const totalChunks = docs.reduce((sum, doc) => sum + Number(doc.chunk_count || 0), 0);
    const rag = getRAGSettings(state.currentKB.metadata || {});
    const metrics = [
        { label: "文档数", value: docs.length, copy: "当前知识库已入库文档" },
        { label: "分块数", value: totalChunks, copy: "可参与检索的文本块" },
        { label: "默认 Top-K", value: rag.search_top_k, copy: "默认召回条数" },
        { label: "候选召回", value: rag.candidate_top_k, copy: "进入重排的候选数" },
    ];
    container.innerHTML = metrics.map((metric) => `
        <div class="mini-stat">
            <span class="metric-label">${escapeHtml(metric.label)}</span>
            <strong>${escapeHtml(String(metric.value))}</strong>
            <span class="small-copy">${escapeHtml(metric.copy)}</span>
        </div>
    `).join("");
}

function renderEndpointOptions() {
    if (!state.currentKB) {
        document.getElementById("embeddingEndpointSelect").innerHTML = '<option value="">先选择知识库</option>';
        document.getElementById("rerankEndpointSelect").innerHTML = '<option value="">先选择知识库</option>';
        return;
    }
    renderEndpointSelect("embeddingEndpointSelect", "embedding", "使用内置本地向量模型");
    renderEndpointSelect("rerankEndpointSelect", "rerank", "使用内置本地重排器");
}

function renderEndpointSelect(selectId, endpointType, emptyText) {
    const select = document.getElementById(selectId);
    if (!select) return;
    const metadata = state.currentKB?.metadata || {};
    const selectedValue = metadata[`${endpointType}_endpoint_id`] || "";
    const endpoints = state.servingEndpoints.filter((endpoint) => endpoint.endpoint_type === endpointType);
    select.innerHTML = [
        `<option value="">${emptyText}</option>`,
        ...endpoints.map((endpoint) => {
            const label = `${endpoint.model_name || endpoint.endpoint_id} · ${endpoint.backend} · ${endpoint.base_url}`;
            return `<option value="${escapeHtml(endpoint.endpoint_id)}" ${endpoint.endpoint_id === selectedValue ? "selected" : ""}>${escapeHtml(label)}</option>`;
        })
    ].join("");
}

function getRAGSettings(metadata = {}) {
    return {
        ...DEFAULT_RAG_SETTINGS,
        ...(metadata.rag_settings || {}),
    };
}

function renderKBSettings() {
    if (!state.currentKB) {
        document.getElementById("ragChunkSizeInput").value = DEFAULT_RAG_SETTINGS.chunk_size;
        document.getElementById("ragChunkOverlapInput").value = DEFAULT_RAG_SETTINGS.chunk_overlap;
        document.getElementById("ragSearchTopKInput").value = DEFAULT_RAG_SETTINGS.search_top_k;
        document.getElementById("ragCandidateTopKInput").value = DEFAULT_RAG_SETTINGS.candidate_top_k;
        document.getElementById("ragScoreThresholdInput").value = DEFAULT_RAG_SETTINGS.retrieval_score_threshold;
        document.getElementById("ragMmrLambdaInput").value = DEFAULT_RAG_SETTINGS.mmr_lambda;
        document.getElementById("ragWindowSizeInput").value = DEFAULT_RAG_SETTINGS.window_size;
        document.getElementById("ragWindowCharsInput").value = DEFAULT_RAG_SETTINGS.window_max_chars;
        document.getElementById("ragSectionCharsInput").value = DEFAULT_RAG_SETTINGS.section_max_chars;
        document.getElementById("ragQueryExpansionInput").checked = DEFAULT_RAG_SETTINGS.query_expansion_enabled;
        setKBSettingsStatus("等待选择知识库。");
        return;
    }
    const metadata = state.currentKB.metadata || {};
    const rag = getRAGSettings(metadata);
    document.getElementById("ragChunkSizeInput").value = rag.chunk_size;
    document.getElementById("ragChunkOverlapInput").value = rag.chunk_overlap;
    document.getElementById("ragSearchTopKInput").value = rag.search_top_k;
    document.getElementById("ragCandidateTopKInput").value = rag.candidate_top_k;
    document.getElementById("ragScoreThresholdInput").value = rag.retrieval_score_threshold;
    document.getElementById("ragMmrLambdaInput").value = rag.mmr_lambda;
    document.getElementById("ragWindowSizeInput").value = rag.window_size;
    document.getElementById("ragWindowCharsInput").value = rag.window_max_chars;
    document.getElementById("ragSectionCharsInput").value = rag.section_max_chars;
    document.getElementById("ragQueryExpansionInput").checked = !!rag.query_expansion_enabled;

    const embeddingName = metadata.embedding_endpoint_name || "内置本地向量模型";
    const rerankName = metadata.rerank_endpoint_name || "内置轻量重排器";
    setKBSettingsStatus(`向量: ${embeddingName} ｜ 重排: ${rerankName} ｜ Chunk=${rag.chunk_size}/${rag.chunk_overlap} ｜ Top-K=${rag.search_top_k}`);
}

function collectRAGSettingsFromInputs() {
    return {
        chunk_size: Number(document.getElementById("ragChunkSizeInput").value || DEFAULT_RAG_SETTINGS.chunk_size),
        chunk_overlap: Number(document.getElementById("ragChunkOverlapInput").value || DEFAULT_RAG_SETTINGS.chunk_overlap),
        search_top_k: Number(document.getElementById("ragSearchTopKInput").value || DEFAULT_RAG_SETTINGS.search_top_k),
        candidate_top_k: Number(document.getElementById("ragCandidateTopKInput").value || DEFAULT_RAG_SETTINGS.candidate_top_k),
        retrieval_score_threshold: Number(document.getElementById("ragScoreThresholdInput").value || DEFAULT_RAG_SETTINGS.retrieval_score_threshold),
        mmr_lambda: Number(document.getElementById("ragMmrLambdaInput").value || DEFAULT_RAG_SETTINGS.mmr_lambda),
        window_size: Number(document.getElementById("ragWindowSizeInput").value || DEFAULT_RAG_SETTINGS.window_size),
        window_max_chars: Number(document.getElementById("ragWindowCharsInput").value || DEFAULT_RAG_SETTINGS.window_max_chars),
        section_max_chars: Number(document.getElementById("ragSectionCharsInput").value || DEFAULT_RAG_SETTINGS.section_max_chars),
        query_expansion_enabled: !!document.getElementById("ragQueryExpansionInput").checked,
    };
}

function setKBSettingsStatus(message, isError = false) {
    const el = document.getElementById("kbSettingsStatus");
    el.textContent = message || "";
    el.style.color = isError ? "#b91c1c" : "#60728b";
}

function renderDocuments() {
    const container = document.getElementById("docList");
    if (!state.currentKB) {
        container.innerHTML = '<div class="empty-card">选择知识库后，这里会出现资料资产卡片。</div>';
        return;
    }
    const docs = Array.isArray(state.currentKB.documents) ? state.currentKB.documents : [];
    if (!docs.length) {
        container.innerHTML = '<div class="empty-card">当前知识库还没有资料，先上传文档再验证检索效果。</div>';
        return;
    }

    container.innerHTML = docs.map((doc) => {
        const isActive = state.selectedDocId === doc.id;
        return `
            <div class="doc-card ${isActive ? "is-active" : ""}" onclick="selectDocument('${doc.id}')">
                <div class="card-head">
                    <div>
                        <div class="card-title">${escapeHtml(doc.name || "未命名文档")}</div>
                        <div class="doc-meta">${escapeHtml(doc.type || "file")} · ${escapeHtml(formatFileSize(doc.size || 0))}</div>
                    </div>
                    <div class="chip-row">
                        <button class="btn btn-ghost" type="button" onclick="event.stopPropagation(); selectDocument('${doc.id}')">
                            <i class="fas fa-eye"></i> 查看
                        </button>
                        <button class="btn btn-danger" type="button" onclick="event.stopPropagation(); deleteDocument('${doc.id}')">
                            <i class="fas fa-trash"></i> 删除
                        </button>
                    </div>
                </div>
                <div class="chip-row">
                    <span class="chip">${escapeHtml(String(doc.chunk_count || 0))} 块</span>
                    <span class="chip">${escapeHtml(formatDate(doc.created_at))}</span>
                </div>
                <div class="card-copy">${escapeHtml(buildDocumentMetaText(doc))}</div>
            </div>
        `;
    }).join("");
}

function buildDocumentMetaText(doc) {
    const meta = doc.metadata || {};
    if (meta.summary) return meta.summary;
    if (meta.source) return `来源 ${meta.source}`;
    return "点击查看后，可以在右侧看到文档内容预览和分块视角。";
}

async function selectDocument(docId) {
    if (!state.currentKB) return;
    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/documents/${docId}`);
        const data = await response.json();
        state.selectedDocId = docId;
        state.selectedDocDetail = data;
        renderDocuments();
        renderDocDetailPanel();
        renderHeroSummary();
    } catch (error) {
        console.error("加载文档详情失败:", error);
        window.alert("文档详情加载失败");
    }
}

function renderDocDetailPanel() {
    const panel = document.getElementById("docDetailPanel");
    if (!state.currentKB) {
        panel.innerHTML = '<div class="empty-card">当前没有选中知识库。</div>';
        return;
    }
    if (!state.selectedDocDetail) {
        panel.innerHTML = '<div class="empty-card">点一份文档，这里会展示内容预览、分块数量和入库时间。</div>';
        return;
    }

    const doc = state.selectedDocDetail;
    const metadata = doc.metadata || {};
    const contentPreview = truncateText(doc.content || "", 1400);
    panel.innerHTML = `
        <div class="detail-card">
            <div class="card-head">
                <div>
                    <div class="card-title">${escapeHtml(doc.name || "未命名文档")}</div>
                    <div class="doc-meta">${escapeHtml(doc.type || "file")} · ${escapeHtml(formatFileSize(doc.size || 0))} · ${escapeHtml(formatDate(doc.created_at))}</div>
                </div>
                <span class="chip">${escapeHtml(String(doc.chunk_count || 0))} 块</span>
            </div>
        </div>
        <div class="detail-card">
            <div class="card-title">内容预览</div>
            <div class="card-copy">${escapeHtml(contentPreview || "当前文档没有可显示的正文内容。").replace(/\n/g, "<br>")}</div>
        </div>
        <div class="detail-card">
            <div class="card-title">元信息</div>
            <div class="doc-meta">${renderMetadata(meta)}</div>
        </div>
    `;
}

function renderMetadata(meta) {
    const entries = Object.entries(meta || {});
    if (!entries.length) return "当前文档没有额外元信息。";
    return entries.slice(0, 12).map(([key, value]) => `${escapeHtml(key)}: ${escapeHtml(formatMetaValue(value))}`).join("<br>");
}

function formatMetaValue(value) {
    if (Array.isArray(value)) return value.join(", ");
    if (value && typeof value === "object") return JSON.stringify(value);
    return String(value ?? "");
}

function renderSearchMetrics() {
    const container = document.getElementById("searchMetricGrid");
    if (!state.currentKB) {
        container.innerHTML = '<div class="empty-card">选择知识库后，这里会显示检索表现摘要。</div>';
        return;
    }

    const results = state.lastSearchResults || [];
    const avgScore = results.length
        ? results.reduce((sum, item) => sum + formatSearchScore(item), 0) / results.length
        : 0;
    const uniqueDocs = new Set(results.map((item) => item.metadata?.doc_name || item.metadata?.doc_id || item.id)).size;
    const mergedCount = results.reduce((sum, item) => sum + (Array.isArray(item.metadata?.merged_chunk_ids) ? item.metadata.merged_chunk_ids.length : 1), 0);
    const metrics = [
        { label: "结果数", value: results.length, copy: "最近一次召回的结果条数" },
        { label: "平均得分", value: `${(avgScore * 100).toFixed(1)}%`, copy: "按最终召回得分估算" },
        { label: "命中文档", value: uniqueDocs, copy: "最近一次检索涉及的文档数" },
        { label: "合并块数", value: mergedCount, copy: "最近一次上下文扩展后的块数" },
    ];
    container.innerHTML = metrics.map((metric) => `
        <div class="mini-stat">
            <span class="metric-label">${escapeHtml(metric.label)}</span>
            <strong>${escapeHtml(String(metric.value))}</strong>
            <span class="small-copy">${escapeHtml(metric.copy)}</span>
        </div>
    `).join("");
}

function renderSearchResults() {
    const container = document.getElementById("searchResults");
    const results = state.lastSearchResults || [];
    if (!results.length) {
        container.innerHTML = '<div class="empty-card">还没有检索结果。输入一个真实问题后，这里会显示分数、上下文和命中文档。</div>';
        return;
    }
    container.innerHTML = results.map((result, index) => renderSearchResultCard(result, index)).join("");
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
    const snippet = truncateText(result.snippet || result.content || "", 260);
    const content = truncateText(result.content || "", 620);
    const sourceLabel = metadata.doc_name || metadata.doc_id || "未知文档";

    return `
        <div class="result-card">
            <div class="card-head">
                <div>
                    <div class="card-title">命中 #${index + 1} · ${escapeHtml(sourceLabel)}</div>
                    <div class="result-meta">${escapeHtml(buildResultSourceMeta(metadata))}</div>
                </div>
                <span class="chip is-success">${(score * 100).toFixed(1)}%</span>
            </div>
            <div class="result-score-row">
                <span class="score-pill">Rerank ${(rerankerScore * 100).toFixed(1)}%</span>
                <span class="score-pill">Hybrid ${(hybridScore * 100).toFixed(1)}%</span>
                <span class="score-pill">Lexical ${(lexicalScore * 100).toFixed(1)}%</span>
                <span class="score-pill">Vector ${(vectorScore * 100).toFixed(1)}%</span>
                <span class="score-pill">合并块 ${mergedChunkIds.length || 1}</span>
                <span class="score-pill">Section块 ${sectionChunkIds.length || 0}</span>
            </div>
            <div class="card-copy"><strong>命中片段：</strong>${escapeHtml(snippet)}</div>
            <div class="card-copy" style="margin-top:10px;"><strong>扩展上下文：</strong>${escapeHtml(content)}</div>
        </div>
    `;
}

function buildResultSourceMeta(metadata) {
    const parts = [];
    if (metadata.section_title) parts.push(metadata.section_title);
    if (metadata.context_mode) parts.push(`模式 ${metadata.context_mode}`);
    if (metadata.window_start !== undefined && metadata.window_end !== undefined) {
        parts.push(`chunk ${metadata.window_start}-${metadata.window_end}`);
    }
    if (metadata.section_start !== undefined && metadata.section_end !== undefined) {
        parts.push(`section ${metadata.section_start}-${metadata.section_end}`);
    }
    return parts.length ? parts.join(" · ") : "当前结果没有额外来源标记";
}

function renderRetrievalDiagnostics() {
    const container = document.getElementById("retrievalDiagnosticList");
    const results = state.lastSearchResults || [];
    if (!results.length) {
        container.innerHTML = '<div class="empty-card">检索后，这里会显示命中分布、最佳文档和上下文扩展情况。</div>';
        document.getElementById("retrievalSummaryChip").textContent = "等待检索";
        return;
    }

    const avgScore = results.reduce((sum, item) => sum + formatSearchScore(item), 0) / results.length;
    const best = results[0];
    const docs = {};
    results.forEach((item) => {
        const name = item.metadata?.doc_name || item.metadata?.doc_id || "未知文档";
        docs[name] = (docs[name] || 0) + 1;
    });
    const topDoc = Object.entries(docs).sort((a, b) => b[1] - a[1])[0];
    const mergedBlockCount = results.reduce((sum, item) => sum + (Array.isArray(item.metadata?.merged_chunk_ids) ? item.metadata.merged_chunk_ids.length : 1), 0);

    container.innerHTML = [
        {
            title: "最佳命中文档",
            copy: `${best.metadata?.doc_name || best.metadata?.doc_id || "未知文档"} · 得分 ${(formatSearchScore(best) * 100).toFixed(1)}%`
        },
        {
            title: "覆盖最广文档",
            copy: topDoc ? `${topDoc[0]} · 命中 ${topDoc[1]} 条` : "暂无命中文档覆盖信息"
        },
        {
            title: "平均召回质量",
            copy: `当前平均得分 ${(avgScore * 100).toFixed(1)}%，共返回 ${results.length} 条结果`
        },
        {
            title: "上下文扩展",
            copy: `最近一次结果合并了 ${mergedBlockCount} 个扩展块，用于拼装连续上下文`
        },
    ].map((item) => `
        <div class="detail-card">
            <div class="card-title">${escapeHtml(item.title)}</div>
            <div class="card-copy">${escapeHtml(item.copy)}</div>
        </div>
    `).join("");

    document.getElementById("retrievalSummaryChip").textContent = `${results.length} 条结果 · 平均 ${(avgScore * 100).toFixed(1)}%`;
}

function renderSettingsInsights() {
    const container = document.getElementById("settingsInsightList");
    if (!state.currentKB) {
        container.innerHTML = '<div class="empty-card">当前还没有知识库配置可透视。</div>';
        return;
    }
    const metadata = state.currentKB.metadata || {};
    const rag = getRAGSettings(metadata);
    const insights = [
        {
            title: "向量接入",
            copy: metadata.embedding_endpoint_name || metadata.embedding_endpoint_id || "当前使用内置本地向量模型"
        },
        {
            title: "重排接入",
            copy: metadata.rerank_endpoint_name || metadata.rerank_endpoint_id || "当前使用内置轻量重排器"
        },
        {
            title: "分块策略",
            copy: `Chunk ${rag.chunk_size} / Overlap ${rag.chunk_overlap} / 窗口 ${rag.window_size}`
        },
        {
            title: "召回策略",
            copy: `Top-K ${rag.search_top_k} / 候选 ${rag.candidate_top_k} / 阈值 ${rag.retrieval_score_threshold} / MMR ${rag.mmr_lambda}`
        },
        {
            title: "扩展策略",
            copy: rag.query_expansion_enabled ? "已启用查询扩展和领域词扩展" : "当前关闭查询扩展"
        },
    ];
    container.innerHTML = insights.map((item) => `
        <div class="detail-card">
            <div class="card-title">${escapeHtml(item.title)}</div>
            <div class="card-copy">${escapeHtml(item.copy)}</div>
        </div>
    `).join("");
}

function renderHeroSummary() {
    const badge = document.getElementById("focusBadge");
    const title = document.getElementById("heroSummaryTitle");
    const copy = document.getElementById("heroSummaryCopy");
    const insights = document.getElementById("heroInsights");

    if (!state.currentKB) {
        badge.textContent = "未选择知识库";
        title.textContent = "知识底座还没选中";
        copy.textContent = "先从左边选择一套知识库，页面会自动切换到更完整的资料、参数和检索视图。";
        insights.innerHTML = '<div class="empty-card">这里会显示当前知识库的关键观察、最佳命中文档和资料状态。</div>';
        return;
    }

    const docs = Array.isArray(state.currentKB.documents) ? state.currentKB.documents : [];
    const totalChunks = docs.reduce((sum, doc) => sum + Number(doc.chunk_count || 0), 0);
    badge.textContent = state.currentKB.name;
    title.textContent = docs.length ? `${state.currentKB.name} 已经进入工作态` : `${state.currentKB.name} 还缺资料`;
    copy.textContent = docs.length
        ? `当前共有 ${docs.length} 份资料、${totalChunks} 个检索块。${state.lastSearchResults.length ? `最近一次检索返回 ${state.lastSearchResults.length} 条结果。` : "可以直接在中间的检索实验台验证效果。"}`
        : "当前知识库还没有文档，建议先上传资料，再调分块、重排和检索参数。";

    const cards = [];
    if (state.selectedDocDetail) {
        cards.push({
            title: `当前文档：${state.selectedDocDetail.name}`,
            copy: `${state.selectedDocDetail.chunk_count || 0} 个分块 · ${formatFileSize(state.selectedDocDetail.size || 0)}`
        });
    }
    if (state.lastSearchResults.length) {
        const best = state.lastSearchResults[0];
        cards.push({
            title: "最佳命中",
            copy: `${best.metadata?.doc_name || best.metadata?.doc_id || "未知文档"} · ${(formatSearchScore(best) * 100).toFixed(1)}%`
        });
    }
    cards.push({
        title: "资料状态",
        copy: docs.length ? `已有 ${docs.length} 份资料进入知识底座` : "当前还没有资料进入知识底座"
    });
    insights.innerHTML = cards.map((item) => `
        <div class="insight-card">
            <div class="card-title">${escapeHtml(item.title)}</div>
            <div class="card-copy">${escapeHtml(item.copy)}</div>
        </div>
    `).join("");
}

function renderScenarioList() {
    const container = document.getElementById("scenarioList");
    container.innerHTML = retrievalScenarios.map((scenario) => `
        <div class="scenario-card ${state.activeScenarioId === scenario.id ? "is-active" : ""}" onclick="applyScenario('${scenario.id}')">
            <div class="card-head">
                <div>
                    <div class="card-title">${escapeHtml(scenario.name)}</div>
                    <div class="card-copy">${escapeHtml(scenario.description)}</div>
                </div>
                <span class="chip">${escapeHtml(String(scenario.topK))} 条</span>
            </div>
        </div>
    `).join("");
}

function applyScenario(scenarioId) {
    const scenario = retrievalScenarios.find((item) => item.id === scenarioId);
    if (!scenario) return;
    state.activeScenarioId = scenarioId;
    renderScenarioList();
    document.getElementById("searchInput").value = scenario.query;
    document.getElementById("quickSearchInput").value = scenario.query;
    document.getElementById("ragSearchTopKInput").value = scenario.topK;
    document.getElementById("ragScoreThresholdInput").value = scenario.threshold;
}

function renderSearchHistory() {
    const container = document.getElementById("searchHistoryList");
    if (!state.searchHistory.length) {
        container.innerHTML = '<div class="empty-card">还没有检索历史。跑几轮真实问题后，这里会变成你的对比列表。</div>';
        return;
    }
    container.innerHTML = state.searchHistory.map((item) => `
        <div class="history-card">
            <div class="card-head">
                <div>
                    <div class="card-title">${escapeHtml(truncateText(item.query, 54))}</div>
                    <div class="card-copy">${escapeHtml(item.timestamp)} · ${escapeHtml(String(item.resultCount))} 条结果</div>
                </div>
                <button class="btn btn-ghost" type="button" onclick="reuseHistoryQuery('${escapeHtmlForAttr(item.query)}')">
                    <i class="fas fa-rotate-left"></i> 重用
                </button>
            </div>
        </div>
    `).join("");
}

function pushSearchHistory(query, resultCount) {
    const timestamp = formatDate(new Date().toISOString());
    state.searchHistory = [
        { query, resultCount, timestamp },
        ...state.searchHistory.filter((item) => item.query !== query),
    ].slice(0, 8);
    renderSearchHistory();
}

function updateSelectionChip() {
    document.getElementById("selectionSummaryChip").textContent = `${getFilteredKBs().length} 个目录`;
}

function handleKBFilterChange() {
    state.kbFilter = document.getElementById("kbFilterInput").value.trim();
    renderKnowledgeBases();
    updateSelectionChip();
}

function handleQuickSearchKeydown(event) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const text = event.target.value.trim();
    document.getElementById("searchInput").value = text;
    searchKnowledge();
}

function reuseLastQuery() {
    if (!state.lastSearchQuery) {
        window.alert("当前还没有上一次查询");
        return;
    }
    document.getElementById("searchInput").value = state.lastSearchQuery;
    document.getElementById("quickSearchInput").value = state.lastSearchQuery;
}

function reuseHistoryQuery(query) {
    const decoded = decodeURIComponent(query);
    document.getElementById("searchInput").value = decoded;
    document.getElementById("quickSearchInput").value = decoded;
}

function showCreateKBModal() {
    document.getElementById("createKBModal").classList.add("active");
    document.getElementById("kbName").value = "";
    document.getElementById("kbDescription").value = "";
}

function closeCreateKBModal() {
    document.getElementById("createKBModal").classList.remove("active");
}

async function createKB() {
    const name = document.getElementById("kbName").value.trim();
    const description = document.getElementById("kbDescription").value.trim();
    if (!name) {
        window.alert("先填写知识库名称");
        return;
    }
    try {
        const response = await fetch("/api/knowledge/bases", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, description }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "创建失败");
        }
        closeCreateKBModal();
        await refreshWorkbench();
        await selectKB(data.id);
    } catch (error) {
        console.error("创建知识库失败:", error);
        window.alert(`新建知识库失败: ${error.message || error}`);
    }
}

async function saveKBSettings() {
    if (!state.currentKB) {
        window.alert("请先选择一个知识库");
        return;
    }
    const embedding_endpoint_id = document.getElementById("embeddingEndpointSelect").value;
    const rerank_endpoint_id = document.getElementById("rerankEndpointSelect").value;
    const rag_settings = collectRAGSettingsFromInputs();
    setKBSettingsStatus("正在保存设置...");

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/settings`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ embedding_endpoint_id, rerank_endpoint_id, rag_settings }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "保存失败");
        }
        state.currentKB = {
            ...state.currentKB,
            ...data,
        };
        setKBSettingsStatus("设置已保存。如果你改了分块或 embedding，建议马上重建向量。");
        renderKBContent();
        renderKnowledgeBases();
    } catch (error) {
        console.error("保存设置失败:", error);
        setKBSettingsStatus(error.message || "保存设置失败", true);
        window.alert(`保存设置失败: ${error.message || error}`);
    }
}

async function rebuildKBEmbeddings() {
    if (!state.currentKB) {
        window.alert("请先选择一个知识库");
        return;
    }
    if (!window.confirm("确定要根据当前 embedding 配置重建这套知识库的向量吗？")) {
        return;
    }
    setKBSettingsStatus("正在重建向量...");
    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/reindex`, {
            method: "POST",
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "重建失败");
        }
        setKBSettingsStatus("向量已重建完成。");
        await selectKB(state.currentKB.id);
        await loadStats();
        renderGlobalMetrics();
    } catch (error) {
        console.error("重建向量失败:", error);
        setKBSettingsStatus(error.message || "重建失败", true);
        window.alert(`重建向量失败: ${error.message || error}`);
    }
}

async function deleteCurrentKB() {
    if (!state.currentKB) return;
    if (!window.confirm(`确定要删除知识库「${state.currentKB.name}」吗？此操作不可恢复。`)) {
        return;
    }
    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}`, {
            method: "DELETE",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "删除失败");
        state.currentKB = null;
        state.selectedDocId = "";
        state.selectedDocDetail = null;
        state.lastSearchResults = [];
        await refreshWorkbench();
    } catch (error) {
        console.error("删除知识库失败:", error);
        window.alert(`删除失败: ${error.message || error}`);
    }
}

async function uploadFile(event) {
    if (!state.currentKB) {
        window.alert("先选择一个知识库");
        return;
    }
    const file = event.target.files?.[0];
    if (!file) return;
    const uploadArea = document.getElementById("uploadArea");
    const originalMarkup = uploadArea.innerHTML;
    const formData = new FormData();
    formData.append("file", file);
    uploadArea.innerHTML = '<div class="card-title">资料上传中...</div><div class="card-copy">正在解析、分块并写入知识底座。</div>';

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/documents`, {
            method: "POST",
            body: formData,
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "上传失败");
        }
        uploadArea.innerHTML = originalMarkup;
        await selectKB(state.currentKB.id);
        await loadStats();
        renderGlobalMetrics();
    } catch (error) {
        console.error("上传文件失败:", error);
        uploadArea.innerHTML = originalMarkup;
        window.alert(`资料上传失败: ${error.message || error}`);
    } finally {
        event.target.value = "";
    }
}

async function deleteDocument(docId) {
    if (!state.currentKB) return;
    if (!window.confirm("确定要删除这个文档吗？")) return;
    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/documents/${docId}`, {
            method: "DELETE",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "删除失败");
        if (state.selectedDocId === docId) {
            state.selectedDocId = "";
            state.selectedDocDetail = null;
        }
        await selectKB(state.currentKB.id);
        await loadStats();
        renderGlobalMetrics();
    } catch (error) {
        console.error("删除文档失败:", error);
        window.alert(`删除资料失败: ${error.message || error}`);
    }
}

async function searchKnowledge() {
    if (!state.currentKB) {
        window.alert("请先选择一个知识库");
        return;
    }
    const query = document.getElementById("searchInput").value.trim();
    const topK = Number(document.getElementById("ragSearchTopKInput").value || DEFAULT_RAG_SETTINGS.search_top_k);
    if (!query) {
        window.alert("先输入一个要验证的业务问题");
        return;
    }
    document.getElementById("searchResults").innerHTML = '<div class="empty-card">正在检索这套知识底座...</div>';
    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, top_k: topK }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "搜索失败");
        }
        state.lastSearchQuery = query;
        state.lastSearchResults = Array.isArray(data.results) ? data.results : [];
        pushSearchHistory(query, state.lastSearchResults.length);
        renderSearchResults();
        renderSearchMetrics();
        renderRetrievalDiagnostics();
        renderHeroSummary();
    } catch (error) {
        console.error("搜索失败:", error);
        document.getElementById("searchResults").innerHTML = '<div class="empty-card">检索失败，请稍后再试。</div>';
    }
}

function initDragAndDrop() {
    const uploadArea = document.getElementById("uploadArea");
    if (!uploadArea) return;
    uploadArea.addEventListener("dragover", (event) => {
        event.preventDefault();
        uploadArea.classList.add("dragover");
    });
    uploadArea.addEventListener("dragleave", () => {
        uploadArea.classList.remove("dragover");
    });
    uploadArea.addEventListener("drop", (event) => {
        event.preventDefault();
        uploadArea.classList.remove("dragover");
        if (!state.currentKB) {
            window.alert("先选择一个知识库");
            return;
        }
        const files = event.dataTransfer.files;
        if (!files.length) return;
        const fileInput = document.getElementById("fileInput");
        fileInput.files = files;
        uploadFile({ target: fileInput });
    });
}

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
    if (!value) return "未知时间";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function truncateText(text, maxLength = 240) {
    const normalized = String(text ?? "").replace(/\s+/g, " ").trim();
    if (normalized.length <= maxLength) return normalized;
    return `${normalized.slice(0, Math.max(0, maxLength - 3))}...`;
}

function formatSearchScore(result) {
    const rawScore = Number(
        result.retrieval_score
        ?? result.score
        ?? (typeof result.distance === "number" ? (1 - result.distance) : 0)
    );
    return Number.isFinite(rawScore) ? Math.max(0, Math.min(1, rawScore)) : 0;
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;",
    }[char]));
}

function escapeHtmlForAttr(value) {
    return encodeURIComponent(String(value ?? ""));
}

// ════════════════════════════════════════════════════════════════
//  Comparison Lab — 参数对比实验
// ════════════════════════════════════════════════════════════════

function captureCompareDraft() {
    state.compareDraft = {
        search_top_k: Number(document.getElementById("compareTopKInput").value || state.compareDraft.search_top_k),
        candidate_top_k: Number(document.getElementById("compareCandidateTopKInput").value || state.compareDraft.candidate_top_k),
        retrieval_score_threshold: Number(document.getElementById("compareThresholdInput").value || state.compareDraft.retrieval_score_threshold),
        mmr_lambda: Number(document.getElementById("compareMmrInput").value || state.compareDraft.mmr_lambda),
        window_size: Number(document.getElementById("compareWindowSizeInput").value || state.compareDraft.window_size),
        section_max_chars: Number(document.getElementById("compareSectionCharsInput").value || state.compareDraft.section_max_chars),
        query_expansion_enabled: !!document.getElementById("compareQueryExpansionInput").checked,
    };
}

function syncCompareDraftFromMain() {
    const rag = state.currentKB ? getRAGSettings(state.currentKB.metadata || {}) : DEFAULT_RAG_SETTINGS;
    state.compareDraft = createCompareDraft(rag);
    renderComparisonLab();
}

function applyExperimentToMain() {
    if (!state.currentKB) return;
    document.getElementById("ragSearchTopKInput").value = state.compareDraft.search_top_k;
    document.getElementById("ragCandidateTopKInput").value = state.compareDraft.candidate_top_k;
    document.getElementById("ragScoreThresholdInput").value = state.compareDraft.retrieval_score_threshold;
    document.getElementById("ragMmrLambdaInput").value = state.compareDraft.mmr_lambda;
    document.getElementById("ragWindowSizeInput").value = state.compareDraft.window_size;
    document.getElementById("ragSectionCharsInput").value = state.compareDraft.section_max_chars;
    document.getElementById("ragQueryExpansionInput").checked = state.compareDraft.query_expansion_enabled;
}

async function runSearchComparison() {
    if (!state.currentKB) {
        window.alert("请先选择一个知识库");
        return;
    }
    const query = document.getElementById("searchInput").value.trim();
    if (!query) {
        window.alert("先输入业务问题");
        return;
    }

    document.getElementById("compareStatusChip").textContent = "对比中…";
    document.getElementById("compareStatusText").textContent = "正在执行两组参数的对比检索…";

    try {
        const mainRag = collectRAGSettingsFromInputs();
        const expRag = { ...mainRag, ...state.compareDraft };

        const [mainRes, expRes] = await Promise.all([
            fetch(`/api/knowledge/bases/${state.currentKB.id}/search`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, top_k: mainRag.search_top_k, rag_settings: mainRag }),
            }).then(r => r.json()),
            fetch(`/api/knowledge/bases/${state.currentKB.id}/search`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, top_k: expRag.search_top_k, rag_settings: expRag }),
            }).then(r => r.json()),
        ]);

        const mainResults = Array.isArray(mainRes.results) ? mainRes.results : [];
        const expResults = Array.isArray(expRes.results) ? expRes.results : [];

        const mainAvg = mainResults.length ? mainResults.reduce((s, r) => s + formatSearchScore(r), 0) / mainResults.length : 0;
        const expAvg = expResults.length ? expResults.reduce((s, r) => s + formatSearchScore(r), 0) / expResults.length : 0;

        const mainDocs = new Set(mainResults.map(r => r.metadata?.doc_name || r.metadata?.doc_id || ""));
        const expDocs = new Set(expResults.map(r => r.metadata?.doc_name || r.metadata?.doc_id || ""));
        const overlap = [...mainDocs].filter(d => expDocs.has(d)).length;

        state.searchComparison = {
            query,
            main: { count: mainResults.length, avg_score: mainAvg, docs: mainDocs.size },
            experiment: { count: expResults.length, avg_score: expAvg, docs: expDocs.size },
            doc_overlap: overlap,
            score_delta: expAvg - mainAvg,
            count_delta: expResults.length - mainResults.length,
        };

        document.getElementById("compareStatusChip").textContent = "对比完成";
        document.getElementById("compareStatusText").textContent =
            `对比完成：主参数 ${mainResults.length} 条(均分 ${(mainAvg*100).toFixed(1)}%)，实验 ${expResults.length} 条(均分 ${(expAvg*100).toFixed(1)}%)`;
        renderComparisonLab();
    } catch (error) {
        console.error("对比实验失败:", error);
        document.getElementById("compareStatusChip").textContent = "对比失败";
        document.getElementById("compareStatusText").textContent = error.message || "对比失败";
    }
}

function renderComparisonLab() {
    const container = document.getElementById("compareResults");
    if (!container) return;

    document.getElementById("compareTopKInput").value = state.compareDraft.search_top_k;
    document.getElementById("compareCandidateTopKInput").value = state.compareDraft.candidate_top_k;
    document.getElementById("compareThresholdInput").value = state.compareDraft.retrieval_score_threshold;
    document.getElementById("compareMmrInput").value = state.compareDraft.mmr_lambda;
    document.getElementById("compareWindowSizeInput").value = state.compareDraft.window_size;
    document.getElementById("compareSectionCharsInput").value = state.compareDraft.section_max_chars;
    document.getElementById("compareQueryExpansionInput").checked = state.compareDraft.query_expansion_enabled;

    if (!state.searchComparison) {
        container.innerHTML = '<div class="empty-card">运行对比后，这里会展示参数组合之间的定量差异。</div>';
        return;
    }

    const c = state.searchComparison;
    const deltaClass = c.score_delta > 0 ? "delta-positive" : (c.score_delta < 0 ? "delta-negative" : "delta-neutral");
    const deltaSign = c.score_delta > 0 ? "+" : "";

    container.innerHTML = `
        <div class="compare-matrix">
            <div class="compare-metric">
                <span class="metric-label">主参数结果</span>
                <strong>${c.main.count}</strong>
                <span class="small-copy">均分 ${(c.main.avg_score*100).toFixed(1)}% · ${c.main.docs} 文档</span>
            </div>
            <div class="compare-metric">
                <span class="metric-label">实验参数结果</span>
                <strong>${c.experiment.count}</strong>
                <span class="small-copy">均分 ${(c.experiment.avg_score*100).toFixed(1)}% · ${c.experiment.docs} 文档</span>
            </div>
            <div class="compare-metric">
                <span class="metric-label">分数变化</span>
                <strong class="${deltaClass}">${deltaSign}${(c.score_delta*100).toFixed(1)}%</strong>
                <span class="small-copy">${c.score_delta > 0 ? "实验参数胜出" : (c.score_delta < 0 ? "主参数更优" : "持平")}</span>
            </div>
            <div class="compare-metric">
                <span class="metric-label">文档重叠</span>
                <strong>${c.doc_overlap}</strong>
                <span class="small-copy">两组结果中出现的相同文档数</span>
            </div>
        </div>
    `;
}


// ════════════════════════════════════════════════════════════════
//  Federated Search — 联邦搜索
// ════════════════════════════════════════════════════════════════

function showFederatedSearchModal() {
    document.getElementById("federatedSearchModal").classList.add("active");
    renderFederatedKBSelector();
}

function closeFederatedSearchModal() {
    document.getElementById("federatedSearchModal").classList.remove("active");
}

function renderFederatedKBSelector() {
    const container = document.getElementById("federatedKBList");
    if (!state.knowledgeBases.length) {
        container.innerHTML = '<div class="empty-card">暂无可选知识库</div>';
        return;
    }
    container.innerHTML = state.knowledgeBases.map(kb => `
        <label class="federated-kb-item" style="display:flex;gap:8px;align-items:center;padding:10px;border-radius:12px;border:1px solid var(--kb-border);cursor:pointer;">
            <input type="checkbox" class="federated-kb-check" value="${escapeHtml(kb.id)}" checked style="accent-color:var(--kb-accent);">
            <div>
                <div class="card-title">${escapeHtml(kb.name)}</div>
                <div class="small-copy">${escapeHtml(String(kb.document_count || 0))} 文档</div>
            </div>
        </label>
    `).join("");
}

async function runFederatedSearch() {
    const query = document.getElementById("federatedQueryInput").value.trim();
    if (!query) {
        window.alert("请输入查询内容");
        return;
    }

    const checks = document.querySelectorAll(".federated-kb-check:checked");
    const kb_ids = Array.from(checks).map(c => c.value);
    if (!kb_ids.length) {
        window.alert("至少选择一个知识库");
        return;
    }

    const strategy = document.getElementById("federatedMergeStrategy").value || "score";
    const topK = Number(document.getElementById("federatedTopK").value || 10);

    document.getElementById("federatedResults").innerHTML = '<div class="empty-card">正在跨库检索…</div>';
    document.getElementById("federatedStatusChip").textContent = "搜索中…";

    try {
        const response = await fetch("/api/knowledge/federated-search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, kb_ids, top_k: topK, merge_strategy: strategy }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "联邦搜索失败");

        state.federatedResults = data;
        document.getElementById("federatedStatusChip").textContent = `${data.results?.length || 0} 条结果`;
        renderFederatedResults(data);
    } catch (error) {
        console.error("联邦搜索失败:", error);
        document.getElementById("federatedResults").innerHTML = `<div class="empty-card">搜索失败: ${escapeHtml(error.message)}</div>`;
        document.getElementById("federatedStatusChip").textContent = "失败";
    }
}

function renderFederatedResults(data) {
    const container = document.getElementById("federatedResults");
    const results = data.results || [];
    if (!results.length) {
        container.innerHTML = '<div class="empty-card">没有找到匹配结果</div>';
        return;
    }

    // Timing summary
    const timingHTML = Object.entries(data.per_kb_timing_ms || {}).map(([kbId, ms]) =>
        `<span class="score-pill">${escapeHtml(data.per_kb_count?.[kbId] || 0)} 条 · ${ms}ms</span>`
    ).join("");

    // Overlap matrix
    let overlapHTML = '';
    if (data.overlap_matrix) {
        const kbIds = Object.keys(data.overlap_matrix);
        if (kbIds.length > 1) {
            overlapHTML = `
                <div class="detail-card" style="margin-top:12px;">
                    <div class="card-title">知识库交叉覆盖</div>
                    <div class="card-copy">Jaccard 相似度矩阵，数值越高说明两个知识库在该查询上的命中片段越接近</div>
                    <div style="display:grid;grid-template-columns:repeat(${kbIds.length + 1},auto);gap:4px;font-size:11px;margin-top:8px;">
                        <div></div>
                        ${kbIds.map(k => `<div style="font-weight:800;text-align:center;">${escapeHtml(k.slice(0, 6))}</div>`).join("")}
                        ${kbIds.map(row => `
                            <div style="font-weight:800;">${escapeHtml(row.slice(0, 6))}</div>
                            ${kbIds.map(col => {
                                const val = data.overlap_matrix[row]?.[col] || 0;
                                const bg = val > 0.5 ? 'rgba(15,118,110,0.15)' : (val > 0 ? 'rgba(19,99,223,0.08)' : 'transparent');
                                return `<div style="text-align:center;padding:4px;border-radius:6px;background:${bg};">${(val * 100).toFixed(0)}%</div>`;
                            }).join("")}
                        `).join("")}
                    </div>
                </div>
            `;
        }
    }

    container.innerHTML = `
        <div class="chip-row" style="margin-bottom:8px;">
            <span class="chip">总候选 ${data.total_candidates || 0}</span>
            <span class="chip is-success">返回 ${results.length}</span>
            <span class="chip is-warn">${data.merge_strategy}</span>
            ${timingHTML}
        </div>
        ${results.map((r, i) => `
            <div class="result-card">
                <div class="card-head">
                    <div>
                        <div class="card-title">命中 #${i + 1} · ${escapeHtml(r.source_kb_name || r.source_kb_id || '未知')}</div>
                        <div class="result-meta">${escapeHtml(r.metadata?.doc_name || '未知文档')}</div>
                    </div>
                    <span class="chip is-success">${(formatSearchScore(r) * 100).toFixed(1)}%</span>
                </div>
                <div class="result-score-row">
                    ${r.rrf_federated_score ? `<span class="score-pill">FedRRF ${(r.rrf_federated_score * 100).toFixed(2)}%</span>` : ''}
                    <span class="score-pill">来源 ${escapeHtml(r.source_kb_name || r.source_kb_id || '')}</span>
                </div>
                <div class="card-copy">${escapeHtml(truncateText(r.content || r.snippet || '', 300))}</div>
            </div>
        `).join("")}
        ${overlapHTML}
    `;
}


// ════════════════════════════════════════════════════════════════
//  Pipeline Debugger — 检索管线调试
// ════════════════════════════════════════════════════════════════

async function runPipelineDebug() {
    if (!state.currentKB) {
        window.alert("请先选择知识库");
        return;
    }
    const query = document.getElementById("searchInput").value.trim();
    if (!query) {
        window.alert("请先输入查询");
        return;
    }

    const topK = Number(document.getElementById("ragSearchTopKInput").value || 5);
    document.getElementById("pipelineDebugPanel").innerHTML = '<div class="empty-card">正在进行管线调试…</div>';

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/search-debug`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, top_k: topK }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "调试失败");

        state.lastPipelineTrace = data;
        renderPipelineDebug(data);
    } catch (error) {
        console.error("管线调试失败:", error);
        document.getElementById("pipelineDebugPanel").innerHTML = `<div class="empty-card">调试失败: ${escapeHtml(error.message)}</div>`;
    }
}

function renderPipelineDebug(trace) {
    const container = document.getElementById("pipelineDebugPanel");
    if (!trace || !trace.stages) {
        container.innerHTML = '<div class="empty-card">无调试数据</div>';
        return;
    }

    const totalTime = trace.total_duration_ms || 0;

    container.innerHTML = `
        <div class="chip-row" style="margin-bottom:12px;">
            <span class="chip">追踪 ${escapeHtml(trace.trace_id)}</span>
            <span class="chip is-success">总耗时 ${totalTime.toFixed(1)}ms</span>
            <span class="chip is-warn">瓶颈: ${escapeHtml(trace.bottleneck || '无')}</span>
            <span class="chip">${trace.stage_count || 0} 阶段</span>
        </div>
        <div class="pipeline-stages" style="display:grid;gap:10px;">
            ${trace.stages.map((stage, idx) => {
                const pct = totalTime > 0 ? (stage.duration_ms / totalTime * 100) : 0;
                const isBottleneck = stage.name === trace.bottleneck;
                return `
                    <div class="detail-card ${isBottleneck ? 'is-bottleneck' : ''}" style="${isBottleneck ? 'border-color:rgba(180,83,9,0.3);background:rgba(180,83,9,0.04);' : ''}">
                        <div class="card-head">
                            <div>
                                <div class="card-title">
                                    <span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:var(--kb-accent);color:#fff;font-size:11px;font-weight:800;margin-right:6px;">${idx + 1}</span>
                                    ${escapeHtml(stage.label || stage.name)}
                                </div>
                                <div class="small-copy">输入 ${stage.input_count || 0} → 输出 ${stage.output_count || 0}</div>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-weight:800;font-size:15px;">${stage.duration_ms.toFixed(1)}ms</div>
                                <div class="small-copy">${pct.toFixed(1)}%</div>
                            </div>
                        </div>
                        <div style="height:6px;border-radius:3px;background:rgba(19,99,223,0.08);overflow:hidden;margin-top:6px;">
                            <div style="height:100%;width:${Math.max(pct, 2)}%;border-radius:3px;background:${isBottleneck ? 'var(--kb-amber)' : 'var(--kb-accent)'};transition:width 0.4s ease;"></div>
                        </div>
                        ${_renderStageOutput(stage)}
                    </div>
                `;
            }).join("")}
        </div>
    `;
}

function _renderStageOutput(stage) {
    const output = stage.output;
    if (!output || typeof output !== 'object') return '';

    const entries = Object.entries(output).slice(0, 8);
    return `
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px;margin-top:8px;">
            ${entries.map(([key, value]) => {
                let display = value;
                if (Array.isArray(value)) {
                    display = value.length > 4 ? `[${value.slice(0, 3).join(', ')}... +${value.length - 3}]` : `[${value.join(', ')}]`;
                } else if (typeof value === 'object' && value !== null) {
                    display = JSON.stringify(value).slice(0, 60);
                }
                return `
                    <div style="padding:8px;border-radius:10px;background:rgba(19,99,223,0.04);border:1px solid rgba(19,99,223,0.06);">
                        <div class="metric-label">${escapeHtml(key)}</div>
                        <div style="font-size:12px;font-weight:700;word-break:break-all;">${escapeHtml(String(display))}</div>
                    </div>
                `;
            }).join("")}
        </div>
    `;
}


// ════════════════════════════════════════════════════════════════
//  Knowledge Graph — 知识图谱
// ════════════════════════════════════════════════════════════════

async function loadKnowledgeGraph() {
    if (!state.currentKB) {
        window.alert("请先选择知识库");
        return;
    }
    document.getElementById("knowledgeGraphPanel").innerHTML = '<div class="empty-card">正在提取知识图谱…</div>';

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/knowledge-graph`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "提取失败");

        state.knowledgeGraph = data;
        renderKnowledgeGraph(data);
    } catch (error) {
        console.error("知识图谱加载失败:", error);
        document.getElementById("knowledgeGraphPanel").innerHTML = `<div class="empty-card">加载失败: ${escapeHtml(error.message)}</div>`;
    }
}

function renderKnowledgeGraph(graph) {
    const container = document.getElementById("knowledgeGraphPanel");
    if (!graph || !graph.nodes?.length) {
        container.innerHTML = '<div class="empty-card">当前知识库没有提取到实体。请先上传文档。</div>';
        return;
    }

    const typeColors = {
        document: '#1363df',
        organization: '#0f766e',
        location: '#b45309',
        system: '#7c3aed',
        equipment: '#0284c7',
        regulation: '#be123c',
        technology: '#059669',
    };

    const typeCounts = {};
    graph.nodes.forEach(n => {
        typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
    });

    // Entity type legend
    const legendHTML = Object.entries(typeCounts).map(([type, count]) => {
        const color = typeColors[type] || '#60728b';
        return `<span class="score-pill" style="background:${color}15;color:${color};"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};"></span> ${escapeHtml(type)} (${count})</span>`;
    }).join("");

    // Top entities by frequency
    const topEntities = graph.nodes
        .filter(n => n.type !== 'document')
        .sort((a, b) => (b.size || 0) - (a.size || 0))
        .slice(0, 20);

    // Force-directed layout simulation (simple)
    const canvasId = 'kgCanvas_' + Date.now();
    const nodesByType = {};
    graph.nodes.forEach(n => {
        if (!nodesByType[n.type]) nodesByType[n.type] = [];
        nodesByType[n.type].push(n);
    });

    container.innerHTML = `
        <div class="chip-row" style="margin-bottom:12px;">
            <span class="chip">${graph.node_count} 节点</span>
            <span class="chip">${graph.edge_count} 关系</span>
            <span class="chip is-success">${Object.keys(typeCounts).length} 类型</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
            ${legendHTML}
        </div>
        <canvas id="${canvasId}" width="780" height="420" style="width:100%;border-radius:16px;background:#0f172a;cursor:grab;"></canvas>
        <div style="margin-top:12px;">
            <div class="card-title">高频实体 Top-20</div>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-top:8px;">
                ${topEntities.map(entity => {
                    const color = typeColors[entity.type] || '#60728b';
                    return `
                        <div style="padding:10px;border-radius:12px;border:1px solid ${color}30;background:${color}08;">
                            <div style="font-weight:800;font-size:13px;color:${color};">${escapeHtml(entity.label)}</div>
                            <div class="small-copy">${escapeHtml(entity.type)} · 频率 ${entity.size || 1}</div>
                        </div>
                    `;
                }).join("")}
            </div>
        </div>
    `;

    // Draw knowledge graph on canvas
    requestAnimationFrame(() => drawKnowledgeGraphCanvas(canvasId, graph, typeColors));
}

function drawKnowledgeGraphCanvas(canvasId, graph, typeColors) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;

    // Position nodes
    const positions = {};
    const nodes = graph.nodes.slice(0, 80);
    const edges = graph.edges.slice(0, 200);

    nodes.forEach((n, i) => {
        const angle = (i / nodes.length) * Math.PI * 2;
        const radius = n.type === 'document' ? 80 : (120 + Math.random() * 100);
        positions[n.id] = {
            x: W / 2 + Math.cos(angle) * radius + (Math.random() - 0.5) * 60,
            y: H / 2 + Math.sin(angle) * radius + (Math.random() - 0.5) * 60,
        };
    });

    // Simple force simulation (10 iterations)
    for (let iter = 0; iter < 15; iter++) {
        // Repulsion
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const a = positions[nodes[i].id];
                const b = positions[nodes[j].id];
                if (!a || !b) continue;
                const dx = b.x - a.x;
                const dy = b.y - a.y;
                const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
                const force = 800 / (dist * dist);
                const fx = dx / dist * force;
                const fy = dy / dist * force;
                a.x -= fx; a.y -= fy;
                b.x += fx; b.y += fy;
            }
        }
        // Attraction along edges
        edges.forEach(e => {
            const a = positions[e.source];
            const b = positions[e.target];
            if (!a || !b) return;
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
            const force = (dist - 80) * 0.01;
            const fx = dx / dist * force;
            const fy = dy / dist * force;
            a.x += fx; a.y += fy;
            b.x -= fx; b.y -= fy;
        });
        // Center gravity
        nodes.forEach(n => {
            const p = positions[n.id];
            if (!p) return;
            p.x += (W / 2 - p.x) * 0.02;
            p.y += (H / 2 - p.y) * 0.02;
            p.x = Math.max(20, Math.min(W - 20, p.x));
            p.y = Math.max(20, Math.min(H - 20, p.y));
        });
    }

    // Draw edges
    ctx.clearRect(0, 0, W, H);
    edges.forEach(e => {
        const a = positions[e.source];
        const b = positions[e.target];
        if (!a || !b) return;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = e.relation === 'co_occurs' ? 'rgba(255,255,255,0.06)' : 'rgba(99,150,255,0.18)';
        ctx.lineWidth = Math.min(e.weight || 1, 3);
        ctx.stroke();
    });

    // Draw nodes
    nodes.forEach(n => {
        const p = positions[n.id];
        if (!p) return;
        const color = typeColors[n.type] || '#60728b';
        const r = n.type === 'document' ? 8 : Math.min(3 + (n.size || 1) * 1.5, 10);

        // Glow
        ctx.beginPath();
        ctx.arc(p.x, p.y, r + 3, 0, Math.PI * 2);
        ctx.fillStyle = color + '30';
        ctx.fill();

        // Node
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Label
        if (n.type === 'document' || (n.size || 1) >= 2) {
            ctx.font = '10px sans-serif';
            ctx.fillStyle = 'rgba(255,255,255,0.8)';
            ctx.textAlign = 'center';
            ctx.fillText(n.label.slice(0, 10), p.x, p.y - r - 5);
        }
    });
}


// ════════════════════════════════════════════════════════════════
//  Chunk Browser — 分块浏览器
// ════════════════════════════════════════════════════════════════

async function loadChunkBrowser() {
    if (!state.currentKB || !state.selectedDocId) {
        document.getElementById("chunkBrowserPanel").innerHTML = '<div class="empty-card">先选择文档，再打开分块浏览器。</div>';
        return;
    }

    document.getElementById("chunkBrowserPanel").innerHTML = '<div class="empty-card">正在加载分块…</div>';

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/documents/${state.selectedDocId}/chunks`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "加载失败");

        state.chunkBrowserData = data;
        renderChunkBrowser(data);
    } catch (error) {
        console.error("分块浏览器加载失败:", error);
        document.getElementById("chunkBrowserPanel").innerHTML = `<div class="empty-card">加载失败: ${escapeHtml(error.message)}</div>`;
    }
}

function renderChunkBrowser(data) {
    const container = document.getElementById("chunkBrowserPanel");
    if (!data || !data.chunks?.length) {
        container.innerHTML = '<div class="empty-card">当前文档没有分块数据</div>';
        return;
    }

    // Hit chunks from last search
    const hitChunkIds = new Set();
    (state.lastSearchResults || []).forEach(r => {
        const meta = r.metadata || {};
        if (meta.retrieved_chunk_id) hitChunkIds.add(meta.retrieved_chunk_id);
        (meta.merged_chunk_ids || []).forEach(id => hitChunkIds.add(id));
    });

    container.innerHTML = `
        <div class="chip-row" style="margin-bottom:12px;">
            <span class="chip">${data.total_chunks} 块</span>
            <span class="chip">${data.total_chars} 字符</span>
            <span class="chip is-success">向量覆盖 ${(data.embedding_coverage * 100).toFixed(0)}%</span>
            <span class="chip is-warn">命中 ${hitChunkIds.size} 块</span>
        </div>
        <div style="display:grid;gap:8px;max-height:500px;overflow-y:auto;padding-right:4px;">
            ${data.chunks.map(chunk => {
                const isHit = hitChunkIds.has(chunk.id);
                return `
                    <div class="chunk-card ${isHit ? 'is-hit' : ''}" style="position:relative;">
                        <div class="chunk-meta">
                            <span style="font-weight:800;">#${chunk.index}</span>
                            <span>${chunk.char_count} 字</span>
                            <span>${chunk.has_embedding ? '向量就绪' : '无向量'}</span>
                            ${isHit ? '<span style="color:var(--kb-emerald);font-weight:800;">命中</span>' : ''}
                            <span style="opacity:0.5;">${chunk.content_hash}</span>
                        </div>
                        <div class="card-copy" style="font-size:12px;line-height:1.7;">${escapeHtml(truncateText(chunk.content, 200))}</div>
                        ${isHit ? '<div style="position:absolute;top:8px;right:8px;width:8px;height:8px;border-radius:50%;background:var(--kb-emerald);"></div>' : ''}
                    </div>
                `;
            }).join("")}
        </div>
    `;
}


// ════════════════════════════════════════════════════════════════
//  Retrieval Heatmap — 检索热力图
// ════════════════════════════════════════════════════════════════

async function loadRetrievalHeatmap() {
    if (!state.currentKB || !state.selectedDocId) {
        document.getElementById("heatmapPanel").innerHTML = '<div class="empty-card">先选择文档再查看热力图</div>';
        return;
    }
    const query = document.getElementById("searchInput").value.trim();
    if (!query) {
        document.getElementById("heatmapPanel").innerHTML = '<div class="empty-card">先输入查询问题再生成热力图</div>';
        return;
    }

    document.getElementById("heatmapPanel").innerHTML = '<div class="empty-card">正在生成热力图…</div>';

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/retrieval-heatmap`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, doc_id: state.selectedDocId, top_k: 20 }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "生成失败");

        renderRetrievalHeatmap(data);
    } catch (error) {
        console.error("热力图生成失败:", error);
        document.getElementById("heatmapPanel").innerHTML = `<div class="empty-card">生成失败: ${escapeHtml(error.message)}</div>`;
    }
}

function renderRetrievalHeatmap(data) {
    const container = document.getElementById("heatmapPanel");
    if (!data || !data.heatmap?.length) {
        container.innerHTML = '<div class="empty-card">没有热力图数据</div>';
        return;
    }

    const intensityColors = {
        high: '#0f766e',
        medium: '#0284c7',
        low: '#1363df',
        none: 'rgba(148,163,184,0.12)',
    };

    container.innerHTML = `
        <div class="chip-row" style="margin-bottom:12px;">
            <span class="chip">命中率 ${(data.hit_rate * 100).toFixed(1)}%</span>
            <span class="chip is-success">平均命中分 ${(data.avg_hit_score * 100).toFixed(1)}%</span>
            <span class="chip">${data.total_chunks_scored} 块被评分</span>
        </div>
        <div style="display:flex;gap:2px;flex-wrap:wrap;padding:8px;border-radius:12px;background:#0f172a;margin-bottom:12px;">
            ${data.heatmap.map(h => {
                const color = intensityColors[h.intensity] || intensityColors.none;
                const opacity = h.is_hit ? (0.3 + h.score * 0.7) : 0.08;
                return `<div title="块 #${h.chunk_index}: ${(h.score * 100).toFixed(1)}%" style="width:14px;height:14px;border-radius:3px;background:${color};opacity:${opacity};cursor:pointer;" onclick="showHeatmapChunkDetail(${h.chunk_index})"></div>`;
            }).join("")}
        </div>
        <div style="display:flex;gap:12px;margin-bottom:8px;">
            <span class="small-copy" style="display:flex;align-items:center;gap:4px;"><span style="width:12px;height:12px;border-radius:2px;background:${intensityColors.high};"></span> 高 (>60%)</span>
            <span class="small-copy" style="display:flex;align-items:center;gap:4px;"><span style="width:12px;height:12px;border-radius:2px;background:${intensityColors.medium};"></span> 中 (30-60%)</span>
            <span class="small-copy" style="display:flex;align-items:center;gap:4px;"><span style="width:12px;height:12px;border-radius:2px;background:${intensityColors.low};"></span> 低 (>0%)</span>
            <span class="small-copy" style="display:flex;align-items:center;gap:4px;"><span style="width:12px;height:12px;border-radius:2px;background:${intensityColors.none};"></span> 无</span>
        </div>
        <div id="heatmapChunkDetail"></div>
    `;
}

function showHeatmapChunkDetail(chunkIndex) {
    const data = state.chunkBrowserData;
    if (!data || !data.chunks) return;
    const chunk = data.chunks[chunkIndex];
    if (!chunk) return;
    const container = document.getElementById("heatmapChunkDetail");
    if (!container) return;
    container.innerHTML = `
        <div class="detail-card">
            <div class="card-title">块 #${chunkIndex}</div>
            <div class="card-copy" style="font-size:12px;line-height:1.8;">${escapeHtml(chunk.content)}</div>
        </div>
    `;
}


// ════════════════════════════════════════════════════════════════
//  Document Annotations — 文档标注
// ════════════════════════════════════════════════════════════════

async function loadAnnotations() {
    if (!state.currentKB || !state.selectedDocId) {
        document.getElementById("annotationPanel").innerHTML = '<div class="empty-card">先选择文档再查看标注</div>';
        return;
    }

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/documents/${state.selectedDocId}/annotations`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "加载失败");

        state.annotations = data;
        renderAnnotations(data);
    } catch (error) {
        console.error("标注加载失败:", error);
        document.getElementById("annotationPanel").innerHTML = `<div class="empty-card">加载失败: ${escapeHtml(error.message)}</div>`;
    }
}

function renderAnnotations(data) {
    const container = document.getElementById("annotationPanel");
    const annotations = data.annotations || [];

    const labelColors = {
        note: '#1363df',
        issue: '#be123c',
        question: '#b45309',
        highlight: '#0f766e',
        qa_pair: '#7c3aed',
    };

    // Tag summary
    const tagHTML = Object.entries(data.tag_summary || {}).map(([tag, count]) =>
        `<span class="score-pill">${escapeHtml(tag)} (${count})</span>`
    ).join("") || '<span class="small-copy">暂无标签</span>';

    container.innerHTML = `
        <div class="chip-row" style="margin-bottom:8px;">
            <span class="chip">${annotations.length} 条标注</span>
            ${tagHTML}
        </div>
        <div class="detail-card" style="margin-bottom:12px;">
            <div class="card-title">新建标注</div>
            <div style="display:grid;gap:8px;">
                <select id="annotationLabelSelect" class="select" style="min-height:36px;">
                    <option value="note">笔记</option>
                    <option value="issue">问题</option>
                    <option value="question">疑问</option>
                    <option value="highlight">重点</option>
                    <option value="qa_pair">问答对</option>
                </select>
                <input id="annotationTextInput" class="input" placeholder="标注内容…" style="min-height:36px;">
                <input id="annotationTagsInput" class="input" placeholder="标签（逗号分隔）" style="min-height:36px;">
                <input id="annotationQAInput" class="input" placeholder="如选问答对，此处填参考答案" style="min-height:36px;">
                <button class="btn btn-primary" type="button" onclick="createAnnotation()" style="min-height:36px;">
                    <i class="fas fa-plus"></i> 添加标注
                </button>
            </div>
        </div>
        <div style="display:grid;gap:8px;max-height:400px;overflow-y:auto;">
            ${annotations.length ? annotations.map(ann => {
                const color = labelColors[ann.label] || '#60728b';
                return `
                    <div class="detail-card" style="border-left:3px solid ${color};">
                        <div class="card-head">
                            <div>
                                <span class="score-pill" style="background:${color}15;color:${color};">${escapeHtml(ann.label)}</span>
                                ${ann.chunk_id ? `<span class="small-copy">关联块 ${escapeHtml(ann.chunk_id.slice(0, 8))}</span>` : ''}
                            </div>
                            <button class="btn btn-danger" style="min-height:28px;padding:0 10px;font-size:11px;" onclick="deleteAnnotation('${escapeHtml(ann.id)}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                        <div class="card-copy">${escapeHtml(ann.text)}</div>
                        ${ann.qa_answer ? `<div class="card-copy" style="margin-top:4px;color:var(--kb-emerald);"><strong>答案：</strong>${escapeHtml(ann.qa_answer)}</div>` : ''}
                        <div class="chunk-meta">
                            ${(ann.tags || []).map(t => `<span class="score-pill">${escapeHtml(t)}</span>`).join("")}
                            <span>${escapeHtml(formatDate(ann.created_at))}</span>
                            <span>${escapeHtml(ann.author)}</span>
                        </div>
                    </div>
                `;
            }).join("") : '<div class="empty-card">当前文档还没有标注。</div>'}
        </div>
    `;
}

async function createAnnotation() {
    if (!state.currentKB || !state.selectedDocId) return;
    const text = document.getElementById("annotationTextInput").value.trim();
    if (!text) {
        window.alert("标注内容不能为空");
        return;
    }

    const label = document.getElementById("annotationLabelSelect").value;
    const tags = document.getElementById("annotationTagsInput").value.split(",").map(t => t.trim()).filter(Boolean);
    const qa_answer = document.getElementById("annotationQAInput").value.trim();

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/documents/${state.selectedDocId}/annotations`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, label, tags, qa_answer }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "创建失败");

        document.getElementById("annotationTextInput").value = "";
        document.getElementById("annotationTagsInput").value = "";
        document.getElementById("annotationQAInput").value = "";
        await loadAnnotations();
    } catch (error) {
        console.error("创建标注失败:", error);
        window.alert(`创建失败: ${error.message}`);
    }
}

async function deleteAnnotation(annId) {
    if (!state.currentKB || !state.selectedDocId) return;
    if (!window.confirm("确定删除这条标注？")) return;

    try {
        await fetch(`/api/knowledge/bases/${state.currentKB.id}/documents/${state.selectedDocId}/annotations/${annId}`, {
            method: "DELETE",
        });
        await loadAnnotations();
    } catch (error) {
        console.error("删除标注失败:", error);
    }
}


// ════════════════════════════════════════════════════════════════
//  Quality Report — 质量报告
// ════════════════════════════════════════════════════════════════

async function runQualityReport() {
    if (!state.currentKB) {
        window.alert("请先选择知识库");
        return;
    }
    document.getElementById("qualityReportPanel").innerHTML = '<div class="empty-card">正在评估知识库质量…</div>';

    try {
        const response = await fetch(`/api/knowledge/bases/${state.currentKB.id}/quality-report`, {
            method: "POST",
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "评估失败");

        state.qualityReport = data;
        renderQualityReport(data);
    } catch (error) {
        console.error("质量评估失败:", error);
        document.getElementById("qualityReportPanel").innerHTML = `<div class="empty-card">评估失败: ${escapeHtml(error.message)}</div>`;
    }
}

function renderQualityReport(report) {
    const container = document.getElementById("qualityReportPanel");
    if (!report) {
        container.innerHTML = '<div class="empty-card">暂无质量报告</div>';
        return;
    }

    const gradeColors = { A: '#0f766e', B: '#1363df', C: '#b45309', D: '#be123c' };
    const gradeColor = gradeColors[report.grade] || '#60728b';

    const scoreEntries = Object.entries(report.scores || {}).map(([key, val]) => {
        const pct = (val * 100).toFixed(0);
        const color = val > 0.7 ? '#0f766e' : (val > 0.4 ? '#b45309' : '#be123c');
        return `
            <div style="display:grid;gap:4px;">
                <div style="display:flex;justify-content:space-between;">
                    <span class="metric-label">${escapeHtml(key.replace(/_/g, ' '))}</span>
                    <span style="font-weight:800;color:${color};">${pct}%</span>
                </div>
                <div style="height:6px;border-radius:3px;background:rgba(19,99,223,0.08);overflow:hidden;">
                    <div style="height:100%;width:${pct}%;border-radius:3px;background:${color};"></div>
                </div>
            </div>
        `;
    }).join("");

    const recoHTML = (report.recommendations || []).map(r => {
        const typeColors = { critical: '#be123c', warning: '#b45309', info: '#1363df' };
        const color = typeColors[r.type] || '#60728b';
        return `
            <div style="padding:10px;border-radius:10px;border-left:3px solid ${color};background:${color}06;">
                <div class="small-copy" style="color:${color};font-weight:800;">${escapeHtml(r.area)}</div>
                <div class="card-copy">${escapeHtml(r.message)}</div>
            </div>
        `;
    }).join("");

    const docHTML = (report.doc_analyses || []).map(d => `
        <div class="detail-card">
            <div class="card-head">
                <div>
                    <div class="card-title">${escapeHtml(d.doc_name)}</div>
                    <div class="small-copy">${d.chunk_count} 块 · ${d.total_chars} 字符 · 向量 ${(d.embedding_coverage * 100).toFixed(0)}%</div>
                </div>
                <span class="chip">${d.doc_type}</span>
            </div>
            <div class="chunk-meta">
                <span>均块 ${d.avg_chunk_size}</span>
                <span>极差 ${d.min_chunk_size}-${d.max_chunk_size}</span>
                <span>标准差 ${d.chunk_size_std}</span>
                <span>${d.annotation_count} 标注</span>
            </div>
        </div>
    `).join("");

    container.innerHTML = `
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
            <div style="width:80px;height:80px;border-radius:50%;background:${gradeColor}12;border:3px solid ${gradeColor};display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <span style="font-size:36px;font-weight:900;color:${gradeColor};">${report.grade}</span>
            </div>
            <div>
                <div style="font-size:20px;font-weight:800;">综合评分 ${(report.overall_score * 100).toFixed(0)}%</div>
                <div class="small-copy">${report.overview?.document_count || 0} 文档 · ${report.overview?.total_chunks || 0} 分块 · ${report.overview?.total_chars || 0} 字符</div>
            </div>
        </div>

        <div class="detail-card" style="margin-bottom:12px;">
            <div class="card-title">维度评分</div>
            <div style="display:grid;gap:10px;margin-top:8px;">
                ${scoreEntries}
            </div>
        </div>

        <div class="detail-card" style="margin-bottom:12px;">
            <div class="card-title">总览指标</div>
            <div class="stats-grid" style="margin-top:8px;">
                <div class="mini-stat"><span class="metric-label">向量就绪</span><strong>${report.overview?.embedding_ready || 0}</strong></div>
                <div class="mini-stat"><span class="metric-label">重复块</span><strong>${report.overview?.duplicate_chunks || 0}</strong></div>
                <div class="mini-stat"><span class="metric-label">过短块</span><strong>${report.overview?.short_chunks || 0}</strong></div>
                <div class="mini-stat"><span class="metric-label">过长块</span><strong>${report.overview?.long_chunks || 0}</strong></div>
            </div>
        </div>

        ${recoHTML ? `<div class="detail-card" style="margin-bottom:12px;"><div class="card-title">改进建议</div><div style="display:grid;gap:8px;margin-top:8px;">${recoHTML}</div></div>` : ''}

        <div class="detail-card">
            <div class="card-title">文档分析</div>
            <div style="display:grid;gap:8px;margin-top:8px;max-height:300px;overflow-y:auto;">${docHTML || '<div class="empty-card">无文档数据</div>'}</div>
        </div>
    `;
}


// ════════════════════════════════════════════════════════════════
//  Search Trace History — 追踪历史
// ════════════════════════════════════════════════════════════════

async function loadTraceHistory() {
    try {
        const response = await fetch("/api/knowledge/traces");
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "加载失败");
        renderTraceHistory(data.traces || []);
    } catch (error) {
        console.error("追踪历史加载失败:", error);
        document.getElementById("traceHistoryPanel").innerHTML = `<div class="empty-card">加载失败</div>`;
    }
}

function renderTraceHistory(traces) {
    const container = document.getElementById("traceHistoryPanel");
    if (!traces.length) {
        container.innerHTML = '<div class="empty-card">暂无调试追踪记录。运行管线调试后会出现在这里。</div>';
        return;
    }
    container.innerHTML = traces.map(t => `
        <div class="history-card" style="cursor:pointer;" onclick="viewTrace('${escapeHtml(t.trace_id)}')">
            <div class="card-head">
                <div>
                    <div class="card-title">${escapeHtml(truncateText(t.query, 40))}</div>
                    <div class="small-copy">${escapeHtml(formatDate(t.created_at))} · ${t.result_count} 结果 · ${t.total_duration_ms.toFixed(0)}ms</div>
                </div>
                <span class="chip is-warn">${escapeHtml(t.bottleneck || '—')}</span>
            </div>
        </div>
    `).join("");
}

async function viewTrace(traceId) {
    try {
        const response = await fetch(`/api/knowledge/traces/${traceId}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "加载失败");
        renderPipelineDebug(data);
    } catch (error) {
        console.error("追踪加载失败:", error);
    }
}


// ════════════════════════════════════════════════════════════════
//  Window exports
// ════════════════════════════════════════════════════════════════

window.refreshWorkbench = refreshWorkbench;
window.handleKBFilterChange = handleKBFilterChange;
window.handleQuickSearchKeydown = handleQuickSearchKeydown;
window.showCreateKBModal = showCreateKBModal;
window.closeCreateKBModal = closeCreateKBModal;
window.createKB = createKB;
window.selectKB = selectKB;
window.selectDocument = selectDocument;
window.saveKBSettings = saveKBSettings;
window.rebuildKBEmbeddings = rebuildKBEmbeddings;
window.deleteCurrentKB = deleteCurrentKB;
window.uploadFile = uploadFile;
window.deleteDocument = deleteDocument;
window.searchKnowledge = searchKnowledge;
window.loadServingEndpoints = loadServingEndpoints;
window.applyScenario = applyScenario;
window.reuseLastQuery = reuseLastQuery;
window.reuseHistoryQuery = reuseHistoryQuery;
window.captureCompareDraft = captureCompareDraft;
window.syncCompareDraftFromMain = syncCompareDraftFromMain;
window.applyExperimentToMain = applyExperimentToMain;
window.runSearchComparison = runSearchComparison;
window.showFederatedSearchModal = showFederatedSearchModal;
window.closeFederatedSearchModal = closeFederatedSearchModal;
window.runFederatedSearch = runFederatedSearch;
window.runPipelineDebug = runPipelineDebug;
window.loadKnowledgeGraph = loadKnowledgeGraph;
window.loadChunkBrowser = loadChunkBrowser;
window.loadRetrievalHeatmap = loadRetrievalHeatmap;
window.loadAnnotations = loadAnnotations;
window.createAnnotation = createAnnotation;
window.deleteAnnotation = deleteAnnotation;
window.runQualityReport = runQualityReport;
window.loadTraceHistory = loadTraceHistory;
window.viewTrace = viewTrace;
window.showHeatmapChunkDetail = showHeatmapChunkDetail;
