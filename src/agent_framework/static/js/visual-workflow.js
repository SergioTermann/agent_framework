/**
 * 可视化工作流编排 JavaScript
 */

const state = {
    workflow: createEmptyWorkflow(),
    nodeTypes: [],
    nodeTypeMap: {},
    templates: [],
    savedWorkflows: [],
    deployedModels: [],
    deployedModelsLoading: false,
    currentScenarioId: "",
    selectedRunPresetId: "",
    selectedNodeId: null,
    selectedEdgeId: null,
    workflowDirty: false,
    isDragging: false,
    dragMoved: false,
    draggedNodeId: null,
    dragOffset: { x: 0, y: 0 },
    isConnecting: false,
    connectionStartNodeId: null,
    tempLine: null,
    editorTabs: {},
    focusedConfigField: null,
    llmModalNodeId: null,
};

const workflowScenarios = [
    {
        id: "incident_command",
        name: "智能值守指挥链",
        description: "告警研判、分级路由、SOP 查询和结果合流压成一条完整链路。",
        complexity: "L4",
        tags: ["运维指挥", "分支路由", "SOP"],
        workflow: {
            name: "智能值守指挥链",
            description: "针对风场告警的根因研判与动作建议流。",
            variables: {
                ops_mode: { value: "night-shift", type: "string", description: "值守模式" },
                response_policy: { value: "优先现场可执行动作", type: "string", description: "处置策略" },
            },
            nodes: [
                { id: "start", type: "start", label: "接收告警", position: { x: 100, y: 230 }, config: { input_schema: "user_query:string\nalarm_text:string\nseverity:number\nasset_id:string", output_var: "input" } },
                { id: "triage", type: "llm", label: "告警研判", position: { x: 350, y: 230 }, config: { provider: "openai", model: "gpt-4.1-mini", response_format: "json", prompt: "基于告警内容 {alarm_text}、等级 {severity} 和策略 {response_policy} 输出根因、证据和建议动作。", output_var: "triage_result" } },
                { id: "judge", type: "condition", label: "是否升级", position: { x: 650, y: 230 }, config: { condition: "severity >= 3" } },
                { id: "sop_api", type: "api", label: "调取 SOP", position: { x: 940, y: 120 }, config: { method: "POST", url: "mock://ops/sop-query", body: '{"asset_id":"{asset_id}","alarm":"{alarm_text}"}', output_var: "sop_payload" } },
                { id: "quick_transform", type: "transform", label: "普通告警整理", position: { x: 940, y: 340 }, config: { transform_type: "json", template: '{"mode":"fast","summary":"{triage_result_text}"}', output_var: "command_payload" } },
                { id: "merge", type: "merge", label: "合并处置结果", position: { x: 1230, y: 230 }, config: { merge_mode: "object", source_vars: "triage_result,sop_payload", output_var: "command_payload" } },
                { id: "end", type: "end", label: "返回指令", position: { x: 1510, y: 230 }, config: { response_template: "{command_payload}", output_key: "final_answer" } },
            ],
            edges: [
                { source: "start", target: "triage" },
                { source: "triage", target: "judge" },
                { source: "judge", target: "sop_api", label: "true", condition: "高优先级" },
                { source: "judge", target: "quick_transform", label: "false", condition: "常规优先级" },
                { source: "sop_api", target: "merge" },
                { source: "merge", target: "end" },
                { source: "quick_transform", target: "end" },
            ],
        },
        runPresets: [
            {
                id: "night_major_alarm",
                name: "夜间高优告警",
                description: "适合验证升级分支和 SOP 接入。",
                input: {
                    user_query: "帮我判断是否需要立即升级",
                    alarm_text: "风机 17 偏航系统连续过流，主控心跳中断 7 秒，并网允许信号未恢复",
                    severity: 4,
                    asset_id: "WT-17"
                }
            },
            {
                id: "normal_alarm",
                name: "普通告警整理",
                description: "适合验证普通分支直出。",
                input: {
                    user_query: "总结这条告警并输出建议",
                    alarm_text: "箱变温度短时升高后回落，当前设备运行正常",
                    severity: 1,
                    asset_id: "BOX-03"
                }
            },
        ],
    },
    {
        id: "multi_agent_delivery",
        name: "多 Agent 交付链",
        description: "需求拆解、方案起草、风险复核和结果收口组成更接近 Dify 的复杂协作链。",
        complexity: "L4",
        tags: ["多 Agent", "复核闭环", "交付"],
        workflow: {
            name: "多 Agent 交付链",
            description: "适合方案评审、需求交付或跨团队编排。",
            variables: {
                release_window: { value: "今晚 20:00-22:00", type: "string", description: "计划上线时间窗" },
                quality_bar: { value: "方案清晰、风险明确、owner 完整", type: "string", description: "复核门槛" },
            },
            nodes: [
                { id: "start", type: "start", label: "接收需求", position: { x: 100, y: 220 }, config: { input_schema: "user_query:string\nscope:string", output_var: "input" } },
                { id: "planner", type: "agent", label: "规划 Agent", position: { x: 360, y: 220 }, config: { agent_type: "planner", prompt: "把任务拆成执行步骤和 owner：{user_query}，范围 {scope}", output_var: "plan_result" } },
                { id: "writer", type: "llm", label: "方案起草", position: { x: 650, y: 220 }, config: { provider: "openai", model: "gpt-4.1-mini", prompt: "基于规划结果输出交付方案：{plan_result}", output_var: "draft_result" } },
                { id: "reviewer", type: "agent", label: "风险复核", position: { x: 950, y: 220 }, config: { agent_type: "analysis", prompt: "按照标准 {quality_bar} 和上线窗 {release_window} 复核方案：{draft_result_text}", output_var: "review_result" } },
                { id: "judge", type: "condition", label: "是否通过", position: { x: 1240, y: 220 }, config: { condition: '"通过" in review_result' } },
                { id: "rewrite", type: "transform", label: "修订动作", position: { x: 1510, y: 120 }, config: { transform_type: "template", template: "请根据复核结果补充方案：{review_result}", output_var: "final_payload" } },
                { id: "merge", type: "merge", label: "收敛结果", position: { x: 1510, y: 320 }, config: { merge_mode: "object", source_vars: "plan_result,draft_result,review_result", output_var: "final_payload" } },
                { id: "end_a", type: "end", label: "返回修订建议", position: { x: 1780, y: 120 }, config: { response_template: "{final_payload}", output_key: "final_answer" } },
                { id: "end_b", type: "end", label: "返回完整方案", position: { x: 1780, y: 320 }, config: { response_template: "{final_payload}", output_key: "final_answer" } },
            ],
            edges: [
                { source: "start", target: "planner" },
                { source: "planner", target: "writer" },
                { source: "writer", target: "reviewer" },
                { source: "reviewer", target: "judge" },
                { source: "judge", target: "rewrite", label: "false" },
                { source: "judge", target: "merge", label: "true" },
                { source: "rewrite", target: "end_a" },
                { source: "merge", target: "end_b" },
            ],
        },
        runPresets: [
            {
                id: "feature_delivery",
                name: "功能交付评审",
                description: "覆盖规划、起草、复核与通过分支。",
                input: {
                    user_query: "为可视化工作流二期输出上线方案",
                    scope: "节点参数弹窗、执行日志、发布入口"
                }
            },
            {
                id: "risk_heavy_delivery",
                name: "高风险交付",
                description: "更适合观察复核节点对风险的反馈。",
                input: {
                    user_query: "今晚同时发布技能创建器、可视化工作流和协作管理升级",
                    scope: "多页面联动、接口变更、回滚预案"
                }
            },
        ],
    },
    {
        id: "knowledge_router",
        name: "知识路由答复链",
        description: "复杂问答先路由，再分流到检索或快速回复，最后统一格式化输出。",
        complexity: "L3",
        tags: ["知识路由", "检索", "结构化输出"],
        workflow: {
            name: "知识路由答复链",
            description: "适合制度问答、资产核验和多知识源答复。",
            variables: {
                answer_style: { value: "结构化摘要", type: "string", description: "输出风格" },
                kb_scope: { value: "风场运维制度库", type: "string", description: "知识范围" },
            },
            nodes: [
                { id: "start", type: "start", label: "接收问题", position: { x: 100, y: 220 }, config: { input_schema: "user_query:string\nmemory:string", output_var: "input" } },
                { id: "route", type: "condition", label: "是否需要检索", position: { x: 340, y: 220 }, config: { condition: "len(user_query) > 18" } },
                { id: "rag_agent", type: "agent", label: "检索 Agent", position: { x: 620, y: 120 }, config: { agent_type: "router", prompt: "结合知识范围 {kb_scope} 和会话记忆 {memory} 检索并回答：{user_query}", output_var: "answer_result" } },
                { id: "quick_llm", type: "llm", label: "快速回答", position: { x: 620, y: 320 }, config: { provider: "openai", model: "gpt-4.1-mini", prompt: "直接回答：{user_query}", output_var: "answer_result" } },
                { id: "formatter", type: "transform", label: "结果格式化", position: { x: 940, y: 220 }, config: { transform_type: "json", template: '{"answer":"{answer_result}","style":"{answer_style}","scope":"{kb_scope}"}', output_var: "final_payload" } },
                { id: "end", type: "end", label: "返回结果", position: { x: 1230, y: 220 }, config: { response_template: "{final_payload}", output_key: "final_answer" } },
            ],
            edges: [
                { source: "start", target: "route" },
                { source: "route", target: "rag_agent", label: "true" },
                { source: "route", target: "quick_llm", label: "false" },
                { source: "rag_agent", target: "formatter" },
                { source: "quick_llm", target: "formatter" },
                { source: "formatter", target: "end" },
            ],
        },
        runPresets: [
            {
                id: "policy_qa",
                name: "制度问答",
                description: "验证检索分支与结构化输出。",
                input: {
                    user_query: "风机大部件更换前，吊装审批最晚要提前多久发起？",
                    memory: "当前用户来自东北区域运维中心"
                }
            },
            {
                id: "small_talk",
                name: "短问题直答",
                description: "验证快速回答分支。",
                input: {
                    user_query: "今天风场值守重点看什么？",
                    memory: "夜班值守"
                }
            },
        ],
    },
];

const llmPresets = [
    {
        id: "precision_json",
        name: "精确抽取",
        description: "低温度、JSON 输出，适合结构化抽取和节点对接。",
        config: { temperature: 0.1, top_p: 0.9, max_tokens: 1200, response_format: "json", completion_mode: "chat", json_schema: '{"type":"object","properties":{"answer":{"type":"string"}}}' }
    },
    {
        id: "balanced_chat",
        name: "平衡对话",
        description: "兼顾稳定性和表达力，适合大多数助手节点。",
        config: { temperature: 0.6, top_p: 0.95, max_tokens: 1800, response_format: "markdown", completion_mode: "chat" }
    },
    {
        id: "reasoning_mode",
        name: "深度推理",
        description: "拉高输出上限，适合复杂分析和多步骤解释。",
        config: { temperature: 0.4, top_p: 1, max_tokens: 2800, response_format: "markdown", completion_mode: "reasoning", presence_penalty: 0.1 }
    },
    {
        id: "fast_reply",
        name: "极速回复",
        description: "更短更快，适合路由和轻量判断节点。",
        config: { temperature: 0.2, top_p: 0.85, max_tokens: 600, response_format: "text", completion_mode: "chat" }
    },
];

document.addEventListener("DOMContentLoaded", async () => {
    bindBaseEvents();
    initCanvas();
    renderAll();
    await Promise.all([
        loadNodeTypes(),
        loadTemplates(),
        loadWorkflowLibrary(),
        loadDeployedModels(),
    ]);
});

function createEmptyWorkflow() {
    return {
        id: null,
        name: "",
        description: "",
        nodes: [],
        edges: [],
        variables: {},
    };
}

function bindBaseEvents() {
    const workflowName = document.getElementById("workflowName");
    const workflowDescription = document.getElementById("workflowDescription");
    const workflowSettings = document.getElementById("workflowSettings");
    const workflowImportInput = document.getElementById("workflowImportInput");
    const configContent = document.getElementById("configContent");
    const llmModal = document.getElementById("llmConfigModal");

    workflowName?.addEventListener("input", (event) => {
        state.workflow.name = event.target.value;
        markWorkflowDirty();
    });

    workflowDescription?.addEventListener("input", (event) => {
        state.workflow.description = event.target.value;
        markWorkflowDirty();
    });

    workflowSettings?.addEventListener("input", handleWorkflowSettingsInput);
    workflowSettings?.addEventListener("change", handleWorkflowSettingsInput);
    workflowSettings?.addEventListener("click", handleWorkflowSettingsClick);
    workflowImportInput?.addEventListener("change", handleWorkflowImport);
    configContent?.addEventListener("focusin", handleConfigFocusIn);
    llmModal?.addEventListener("click", handleLLMModalBackdropClick);

    window.addEventListener("resize", renderConnections);
    document.addEventListener("keydown", handleKeydown);
}

function initCanvas() {
    const canvas = document.getElementById("canvas");
    canvas?.addEventListener("dragover", handleCanvasDragOver);
    canvas?.addEventListener("drop", handleCanvasDrop);
    canvas?.addEventListener("click", handleCanvasClick);
}

async function loadNodeTypes() {
    try {
        const response = await fetch("/api/visual-workflow/node-types");
        const data = await response.json();
        state.nodeTypes = Array.isArray(data.node_types) ? data.node_types : [];
        state.nodeTypeMap = Object.fromEntries(state.nodeTypes.map((item) => [item.type, item]));
        renderNodePalette();
        renderAll();
    } catch (error) {
        console.error("加载节点类型失败:", error);
    }
}

async function loadTemplates() {
    try {
        const response = await fetch("/api/visual-workflow/templates");
        const data = await response.json();
        state.templates = Array.isArray(data.templates) ? data.templates : [];
        renderTemplates();
    } catch (error) {
        console.error("加载模板失败:", error);
    }
}

async function loadWorkflowLibrary() {
    try {
        const response = await fetch("/api/visual-workflow/workflows");
        const data = await response.json();
        state.savedWorkflows = Array.isArray(data.workflows) ? data.workflows : [];
        renderWorkflowLibrary();
    } catch (error) {
        console.error("加载流程列表失败:", error);
    }
}

async function loadDeployedModels() {
    state.deployedModelsLoading = true;
    renderDeployedModels();
    try {
        const response = await fetch("/api/pipeline/endpoints/list?endpoint_type=chat");
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || "加载已部署模型失败");
        }
        state.deployedModels = normalizeDeployedModels(data.data || []);
    } catch (error) {
        console.error("加载已部署 LLM 失败:", error);
        state.deployedModels = [];
    } finally {
        state.deployedModelsLoading = false;
        renderDeployedModels();
    }
}

function renderAll() {
    syncWorkflowMetaInputs();
    renderWorkflow();
    renderWorkflowLibrary();
    renderDeployedModels();
    renderScenarioList();
    renderWorkflowSettings();
    renderSelectionPanel();
    renderWorkflowOutline();
    renderWorkflowLab();
    updateWorkflowMeta();
    renderLLMModal();
}

function syncWorkflowMetaInputs() {
    const workflowName = document.getElementById("workflowName");
    const workflowDescription = document.getElementById("workflowDescription");
    if (workflowName) workflowName.value = state.workflow.name || "";
    if (workflowDescription) workflowDescription.value = state.workflow.description || "";
}

function renderNodePalette() {
    const palette = document.getElementById("nodePalette");
    if (!palette) return;
    palette.innerHTML = "";

    state.nodeTypes.forEach((type) => {
        const item = document.createElement("div");
        item.className = "node-item";
        item.draggable = true;
        item.dataset.nodeType = type.type;
        item.innerHTML = `
            <div class="node-icon">${type.icon}</div>
            <div>${escapeHtml(type.label)}</div>
        `;
        item.addEventListener("dragstart", handlePaletteDragStart);
        palette.appendChild(item);
    });
}

function renderTemplates() {
    const list = document.getElementById("templateList");
    if (!list) return;

    if (!state.templates.length) {
        list.innerHTML = '<div class="config-empty"><strong>暂无模板</strong><span>可以先从节点库搭一条新的流程。</span></div>';
        return;
    }

    list.innerHTML = state.templates.map((template) => `
        <div class="node-item" style="grid-column: 1 / -1;" onclick="loadTemplateById('${template.id}')">
            <div style="font-weight: 700; margin-bottom: 4px;">${escapeHtml(template.name)}</div>
            <div style="font-size: 10px; color: #7f8c8d;">${escapeHtml(template.description || "")}</div>
        </div>
    `).join("");
}

function renderScenarioList() {
    const container = document.getElementById("workflowScenarioList");
    if (!container) return;
    container.innerHTML = workflowScenarios.map((scenario) => `
        <div class="scenario-card ${state.currentScenarioId === scenario.id ? "is-active" : ""}" onclick="loadWorkflowScenario('${scenario.id}')">
            <div class="scenario-head">
                <div>
                    <div class="scenario-title">${escapeHtml(scenario.name)}</div>
                    <div class="scenario-copy">${escapeHtml(scenario.description)}</div>
                </div>
                <span class="scenario-chip">${escapeHtml(scenario.complexity)}</span>
            </div>
            <div class="scenario-chip-row">
                ${(scenario.tags || []).map((tag) => `<span class="scenario-chip">${escapeHtml(tag)}</span>`).join("")}
                <span class="scenario-chip">节点 ${(scenario.workflow?.nodes || []).length}</span>
            </div>
        </div>
    `).join("");
}

function renderWorkflowLibrary() {
    const container = document.getElementById("workflowLibrary");
    if (!container) return;

    if (!state.savedWorkflows.length) {
        container.innerHTML = '<div class="config-empty"><strong>还没有已保存流程。</strong><span>保存之后，这里会出现可继续编辑的流程列表。</span></div>';
        return;
    }

    container.innerHTML = state.savedWorkflows.map((workflow) => `
        <div class="saved-flow-item ${workflow.id === state.workflow.id ? "is-active" : ""}" onclick="openWorkflow('${workflow.id}')">
            <div class="saved-flow-head">
                <div class="saved-flow-title">${escapeHtml(workflow.name || "未命名流程")}</div>
                <div class="saved-flow-actions">
                    <button class="icon-btn" type="button" onclick="event.stopPropagation(); openWorkflow('${workflow.id}')" aria-label="打开流程">
                        <i class="fas fa-arrow-up-right-from-square"></i>
                    </button>
                    <button class="icon-btn" type="button" onclick="event.stopPropagation(); removeWorkflowFromLibrary('${workflow.id}')" aria-label="删除流程">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="saved-flow-desc">${escapeHtml(workflow.description || "暂无流程说明")}</div>
            <div class="saved-flow-meta">节点 ${workflow.nodes?.length || 0} · 连接 ${workflow.edges?.length || 0}</div>
        </div>
    `).join("");
}

function renderDeployedModels() {
    const container = document.getElementById("deployedLLMList");
    if (!container) return;

    if (state.deployedModelsLoading) {
        container.innerHTML = '<div class="config-empty"><strong>正在读取已部署模型。</strong><span>稍等一下，这里会列出当前可直接调用的 LLM 端点。</span></div>';
        return;
    }

    if (!state.deployedModels.length) {
        container.innerHTML = '<div class="config-empty"><strong>当前没有可用的已部署 LLM。</strong><span>去模型服务页先拉起聊天端点，这里就会变成一键进入的模型入口。</span></div>';
        return;
    }

    const activeNode = getEditableLLMNode();
    container.innerHTML = state.deployedModels.map((deployment) => {
        const isActive = Boolean(
            activeNode
            && activeNode.config
            && (
                (deployment.endpointId && activeNode.config.endpoint_id === deployment.endpointId)
                || (
                    deployment.model
                    && activeNode.config.model === deployment.model
                    && String(activeNode.config.base_url || "") === String(deployment.baseUrl || "")
                )
            )
        );
        return `
            <div class="deployed-llm-item ${isActive ? "is-active" : ""}" onclick="activateDeployedLLM('${deployment.id}')">
                <div class="deployed-llm-head">
                    <div>
                        <div class="deployed-llm-title">${escapeHtml(deployment.label)}</div>
                        <div class="deployed-llm-desc">${escapeHtml(deployment.providerLabel)} · 点一下直接进入参数配置</div>
                    </div>
                    <span class="deployed-llm-pill is-status">${escapeHtml(deployment.statusLabel)}</span>
                </div>
                <div class="deployed-llm-meta">
                    <span class="deployed-llm-pill">${escapeHtml(deployment.backendLabel)}</span>
                    <span class="deployed-llm-pill">${escapeHtml(deployment.model || "未命名模型")}</span>
                </div>
                <div class="deployed-llm-foot">${escapeHtml(deployment.baseUrl || "未配置 Base URL")}</div>
            </div>
        `;
    }).join("");
}

function renderWorkflow() {
    const content = document.getElementById("canvasContent");
    if (!content) return;

    content.innerHTML = "";
    state.workflow.nodes.forEach((node) => {
        const nodeEl = createNodeElement(node);
        content.appendChild(nodeEl);
    });

    renderConnections();
    updateCanvasGuide();
    updateSelectionState();
    updateStructureSummary();
}

function createNodeElement(node) {
    const typeInfo = state.nodeTypeMap[node.type] || {};
    const div = document.createElement("div");
    div.className = `workflow-node ${state.selectedNodeId === node.id ? "selected" : ""}`;
    div.dataset.nodeId = node.id;
    div.style.left = `${node.position.x}px`;
    div.style.top = `${node.position.y}px`;

    div.innerHTML = `
        <div class="node-header">
            <div class="node-icon-large">${typeInfo.icon || "📦"}</div>
            <div>
                <div class="node-label">${escapeHtml(node.label || typeInfo.label || node.type)}</div>
                <div class="node-type">${escapeHtml(typeInfo.label || node.type)}</div>
            </div>
        </div>
        <div class="node-summary">
            <div class="summary-pill-row">
                <span class="summary-pill"><i class="fas fa-arrow-right-to-bracket"></i><span>入 ${node.inputs?.length || 0}</span></span>
                <span class="summary-pill"><i class="fas fa-arrow-right-from-bracket"></i><span>出 ${node.outputs?.length || 0}</span></span>
            </div>
            <div class="summary-text">${escapeHtml(buildNodeSummary(node))}</div>
        </div>
        <div class="node-ports">
            <div class="node-port input-port" data-port="input"></div>
            <div class="node-port output-port" data-port="output"></div>
        </div>
    `;

    div.addEventListener("mousedown", (event) => handleNodeMouseDown(event, node.id));
    div.addEventListener("click", (event) => {
        event.stopPropagation();
        if (state.dragMoved) {
            state.dragMoved = false;
            return;
        }
        selectNode(node.id);
    });
    div.querySelectorAll(".node-port").forEach((port) => {
        port.addEventListener("mousedown", (event) => {
            event.stopPropagation();
            handlePortMouseDown(event, node.id, port.dataset.port);
        });
    });

    return div;
}

function buildNodeSummary(node) {
    const config = node.config || {};
    if (node.type === "llm") {
        return `${config.provider || "openai"} / ${config.model || "未选模型"} · Temp ${config.temperature ?? 0.7}`;
    }
    if (node.type === "agent") {
        return config.model ? `模型 ${config.model} · 输出 ${config.output_var || "result"}` : `输出 ${config.output_var || "result"}`;
    }
    if (node.type === "condition") {
        return config.condition || "补一条条件表达式";
    }
    if (node.type === "api") {
        return `${config.method || "GET"} ${config.url || "补请求地址"}`;
    }
    if (node.type === "transform") {
        return `${config.transform_type || "template"} · 输出 ${config.output_var || "transformed"}`;
    }
    if (node.type === "merge") {
        return `${config.merge_mode || "append"} · ${config.source_vars || "待配置来源"}`;
    }
    if (node.type === "loop") {
        return `${config.loop_source || "items"} → ${config.item_var || "item"}`;
    }
    if (node.type === "end") {
        return config.output_key ? `结果写入 ${config.output_key}` : "返回最终结果";
    }
    return config.output_var ? `输出 ${config.output_var}` : "点击右侧继续补参数";
}

function renderConnections() {
    const svg = document.getElementById("connectionsSvg");
    if (!svg) return;

    svg.innerHTML = "";
    const svgRect = svg.getBoundingClientRect();

    state.workflow.edges.forEach((edge) => {
        const sourceNode = document.querySelector(`[data-node-id="${edge.source}"]`);
        const targetNode = document.querySelector(`[data-node-id="${edge.target}"]`);
        if (!sourceNode || !targetNode) return;

        const sourcePort = sourceNode.querySelector(".output-port");
        const targetPort = targetNode.querySelector(".input-port");
        if (!sourcePort || !targetPort) return;

        const sourceRect = sourcePort.getBoundingClientRect();
        const targetRect = targetPort.getBoundingClientRect();
        const x1 = sourceRect.left + sourceRect.width / 2 - svgRect.left;
        const y1 = sourceRect.top + sourceRect.height / 2 - svgRect.top;
        const x2 = targetRect.left + targetRect.width / 2 - svgRect.left;
        const y2 = targetRect.top + targetRect.height / 2 - svgRect.top;
        const curve = `M ${x1} ${y1} C ${x1 + 90} ${y1}, ${x2 - 90} ${y2}, ${x2} ${y2}`;
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;

        const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
        group.setAttribute("class", `edge-group ${state.selectedEdgeId === edge.id ? "is-selected" : ""}`.trim());
        group.dataset.edgeId = edge.id;

        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("class", "edge-path");
        path.setAttribute("d", curve);
        group.appendChild(path);

        const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
        hit.setAttribute("class", "edge-hit");
        hit.setAttribute("d", curve);
        hit.addEventListener("click", (event) => {
            event.stopPropagation();
            selectEdge(edge.id);
        });
        group.appendChild(hit);

        if (edge.label || edge.condition) {
            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
            text.setAttribute("class", "edge-label");
            text.setAttribute("x", midX);
            text.setAttribute("y", midY - 8);
            text.setAttribute("text-anchor", "middle");
            text.textContent = edge.label || edge.condition;
            group.appendChild(text);
        }

        svg.appendChild(group);
    });
}

function renderWorkflowOutline() {
    const outline = document.getElementById("workflowOutline");
    const selectionSummary = document.getElementById("selectionSummary");
    if (!outline) return;

    const items = [];
    state.workflow.nodes.forEach((node) => {
        const typeInfo = state.nodeTypeMap[node.type] || {};
        items.push(`
            <div class="outline-item ${state.selectedNodeId === node.id ? "is-active" : ""}" onclick="selectNode('${node.id}')">
                <div class="outline-head">
                    <div class="outline-title">${typeInfo.icon || "📦"} ${escapeHtml(node.label || typeInfo.label || node.type)}</div>
                    <span class="outline-badge">节点</span>
                </div>
                <div class="outline-meta">${escapeHtml(buildNodeSummary(node))}</div>
            </div>
        `);
    });
    state.workflow.edges.forEach((edge) => {
        const sourceNode = getNode(edge.source);
        const targetNode = getNode(edge.target);
        items.push(`
            <div class="outline-item ${state.selectedEdgeId === edge.id ? "is-active" : ""}" onclick="selectEdge('${edge.id}')">
                <div class="outline-head">
                    <div class="outline-title">${escapeHtml(sourceNode?.label || edge.source)} → ${escapeHtml(targetNode?.label || edge.target)}</div>
                    <span class="outline-badge">连线</span>
                </div>
                <div class="outline-meta">${escapeHtml(edge.label || edge.condition || "未命名分支")}</div>
            </div>
        `);
    });

    outline.innerHTML = items.length
        ? items.join("")
        : '<div class="config-empty"><strong>画布还是空的。</strong><span>先拖一个起点或直接加载模板。</span></div>';

    if (selectionSummary) {
        if (state.selectedNodeId) {
            const node = getNode(state.selectedNodeId);
            selectionSummary.textContent = node ? `当前选中节点：${node.label || node.type}` : "还没有选中节点或连线。";
        } else if (state.selectedEdgeId) {
            const edge = getEdge(state.selectedEdgeId);
            selectionSummary.textContent = edge ? `当前选中连线：${edge.label || "未命名分支"}` : "还没有选中节点或连线。";
        } else {
            selectionSummary.textContent = "还没有选中节点或连线。";
        }
    }
}

function renderWorkflowLab() {
    renderWorkflowMetrics();
    renderWorkflowPresets();
    renderWorkflowRoutes();
    renderWorkflowNextSteps();
    renderWorkflowInventory();
}

function renderWorkflowMetrics() {
    const container = document.getElementById("workflowMetricGrid");
    if (!container) return;
    const analysis = analyzeWorkflow();
    const metrics = [
        { title: "编排复杂度", value: analysis.complexityScore, suffix: "%", copy: `节点 ${analysis.nodeCount} · 分支 ${analysis.branchCount}` },
        { title: "结构完成度", value: analysis.structureScore, suffix: "%", copy: `已配置 ${analysis.configuredNodeCount}/${analysis.nodeCount || 1} 个节点` },
        { title: "变量覆盖率", value: analysis.variableCoverage, suffix: "%", copy: `变量 ${analysis.variableCount} · 命中 ${analysis.referencedVariableCount}` },
        { title: "发布准备度", value: analysis.releaseReadiness, suffix: "%", copy: analysis.issues.length ? `${analysis.issues.length} 个待处理项` : "当前无明显结构阻塞" },
    ];

    container.innerHTML = metrics.map((metric) => `
        <div class="metric-card">
            <div class="metric-head">
                <div class="metric-title">${escapeHtml(metric.title)}</div>
                <span class="metric-chip">${escapeHtml(String(metric.value))}${escapeHtml(metric.suffix)}</span>
            </div>
            <div class="metric-value">${escapeHtml(String(metric.value))}${escapeHtml(metric.suffix)}</div>
            <div class="metric-track">
                <div class="metric-fill" style="width:${Math.max(0, Math.min(metric.value, 100))}%"></div>
            </div>
            <div class="metric-copy">${escapeHtml(metric.copy)}</div>
        </div>
    `).join("");
}

function renderWorkflowPresets() {
    const container = document.getElementById("workflowPresetList");
    if (!container) return;
    const presets = getCurrentRunPresets();
    if (!presets.length) {
        container.innerHTML = '<div class="config-empty"><strong>当前没有 demo 运行场景。</strong><span>从左侧复杂 Demo 进入后，这里会变成一组一键回归样例。</span></div>';
        return;
    }
    container.innerHTML = presets.map((preset) => `
        <div class="preset-item">
            <div class="preset-head">
                <div>
                    <div class="preset-title">${escapeHtml(preset.name)}</div>
                    <div class="preset-copy">${escapeHtml(preset.description || "用于工作流测试")}</div>
                </div>
                <span class="preset-chip">${escapeHtml(state.selectedRunPresetId === preset.id ? "当前" : "Demo")}</span>
            </div>
            <div class="preset-chip-row">
                <span class="preset-chip">字段 ${escapeHtml(String(Object.keys(preset.input || {}).length))}</span>
            </div>
            <div class="editor-actions">
                <button class="btn btn-ghost" type="button" onclick="applyRunPreset('${preset.id}')">
                    <i class="fas fa-vial"></i> 写入测试区
                </button>
            </div>
        </div>
    `).join("");
}

function renderWorkflowRoutes() {
    const container = document.getElementById("workflowRouteList");
    if (!container) return;
    const routes = buildRouteSummaries();
    container.innerHTML = routes.length
        ? routes.map((route, index) => `
            <div class="route-item">
                <div class="route-head">
                    <div class="route-title">路径 ${index + 1}</div>
                    <span class="scenario-chip">${escapeHtml(route.kind)}</span>
                </div>
                <div class="route-copy">${escapeHtml(route.summary)}</div>
            </div>
        `).join("")
        : '<div class="config-empty"><strong>还没有路径可预览。</strong><span>放入开始节点并连线后，这里会显示主要执行链路。</span></div>';
}

function renderWorkflowNextSteps() {
    const container = document.getElementById("workflowNextSteps");
    if (!container) return;
    const steps = buildNextSteps();
    container.innerHTML = steps.map((step) => `
        <div class="next-step-item">
            <div class="route-title">${escapeHtml(step.title)}</div>
            <div class="route-copy">${escapeHtml(step.copy)}</div>
        </div>
    `).join("");
}

function renderWorkflowInventory() {
    const container = document.getElementById("workflowInventory");
    if (!container) return;
    const inventory = buildNodeInventory();
    container.innerHTML = inventory.length
        ? inventory.map((item) => `
            <div class="inventory-item">
                <div class="inventory-head">
                    <div class="inventory-title">${escapeHtml(item.label)}</div>
                    <span class="scenario-chip">${escapeHtml(String(item.count))}</span>
                </div>
                <div class="inventory-copy">${escapeHtml(item.copy)}</div>
            </div>
        `).join("")
        : '<div class="config-empty"><strong>当前还没有节点盘点。</strong><span>开始搭流程后，这里会统计各类节点与连接关系。</span></div>';
}

function renderWorkflowSettings() {
    const container = document.getElementById("workflowSettings");
    if (!container) return;

    const variables = getVariableEntries();
    container.innerHTML = `
        <div class="config-section">
            <h4>全局变量</h4>
            <div class="section-copy">这些字段会跟随整条流程一起保存，节点里的提示词、条件、API 请求都可以引用。</div>
            <div class="variable-actions">
                <button class="btn btn-ghost" type="button" data-action="add-variable">
                    <i class="fas fa-plus"></i> 新增变量
                </button>
            </div>
            <div class="variable-list">
                ${variables.length ? variables.map((entry, index) => renderVariableItem(entry, index)).join("") : `
                    <div class="config-empty">
                        <strong>还没有全局变量。</strong>
                        <span>可以先建 user_query、tenant_id、kb_scope 这类常用上下文。</span>
                    </div>
                `}
            </div>
        </div>
    `;
}

function renderVariableItem(entry, index) {
    return `
        <div class="variable-item">
            <div class="variable-grid">
                <div class="form-group">
                    <label class="form-label">变量名</label>
                    <input class="form-input" data-variable-index="${index}" data-field="name" value="${escapeHtml(entry.name)}" placeholder="user_query">
                </div>
                <div class="form-group">
                    <label class="form-label">类型</label>
                    <select class="form-input" data-variable-index="${index}" data-field="type">
                        ${["string", "number", "boolean", "object", "array"].map((type) => `
                            <option value="${type}" ${entry.meta.type === type ? "selected" : ""}>${type}</option>
                        `).join("")}
                    </select>
                </div>
                <div class="form-group is-wide">
                    <label class="form-label">默认值</label>
                    <input class="form-input" data-variable-index="${index}" data-field="value" value="${escapeHtml(stringifyVariableValue(entry.meta.value))}" placeholder="默认值">
                </div>
                <div class="form-group is-wide">
                    <label class="form-label">说明</label>
                    <textarea class="form-input" data-variable-index="${index}" data-field="description" placeholder="描述这个变量在流程里的作用">${escapeHtml(entry.meta.description || "")}</textarea>
                </div>
            </div>
            <div class="variable-actions">
                <button class="btn" type="button" data-action="remove-variable" data-variable-index="${index}">
                    <i class="fas fa-trash"></i> 删除变量
                </button>
            </div>
        </div>
    `;
}

function renderSelectionPanel() {
    const title = document.getElementById("configTitle");
    const description = document.getElementById("configDescription");
    const content = document.getElementById("configContent");
    if (!content || !title || !description) return;

    if (state.selectedNodeId) {
        const node = getNode(state.selectedNodeId);
        const typeInfo = state.nodeTypeMap[node?.type] || {};
        title.textContent = `${typeInfo.label || "节点"}配置`;
        description.textContent = typeInfo.description || "编辑当前节点的参数、输入输出和高级属性。";
        content.innerHTML = renderNodeEditor(node, typeInfo);
        return;
    }

    if (state.selectedEdgeId) {
        const edge = getEdge(state.selectedEdgeId);
        title.textContent = "连接配置";
        description.textContent = "补标签、条件和分支说明，也可以直接删除这条连接。";
        content.innerHTML = renderEdgeEditor(edge);
        return;
    }

    title.textContent = "选中对象";
    description.textContent = "节点、边都能在这里改。";
    content.innerHTML = `
        <div class="config-empty">
            <strong>还没有选中对象。</strong>
            <span>点击任意节点或连线，这里会切换到对应的编辑面板。</span>
        </div>
    `;
}

function renderNodeEditor(node, typeInfo) {
    if (!node) return "";
    const fields = Array.isArray(typeInfo.fields) ? typeInfo.fields : [];
    const groupedFields = fields.reduce((acc, field) => {
        const group = field.group || "节点参数";
        if (!acc[group]) acc[group] = [];
        acc[group].push(field);
        return acc;
    }, {});
    const tabs = getNodeEditorTabs(node, groupedFields);
    const activeTab = tabs.length ? (state.editorTabs[node.id] || tabs[0].key) : "";
    const activeGroups = tabs.length
        ? tabs.find((tab) => tab.key === activeTab)?.groups || []
        : Object.keys(groupedFields);
    return `
        <div class="config-section">
            <h4>基础信息</h4>
            <div class="field-grid">
                <div class="form-group">
                    <label class="form-label">节点名称</label>
                    <input class="form-input" value="${escapeHtml(node.label || "")}" onchange="updateNodeLabel('${node.id}', this.value)">
                </div>
                <div class="form-group">
                    <label class="form-label">节点类型</label>
                    <input class="form-input" value="${escapeHtml(typeInfo.label || node.type)}" disabled>
                </div>
                <div class="form-group is-wide">
                    <label class="form-label">节点说明</label>
                    <textarea class="form-input" onchange="updateNodeConfig('${node.id}', 'node_note', this.value)" placeholder="记录这个节点的职责和补充说明">${escapeHtml(node.config?.node_note || "")}</textarea>
                </div>
            </div>
        </div>
        <div class="config-section">
            <h4>${node.type === "llm" ? "LLM 参数" : "节点参数"}</h4>
            <div class="section-copy">${node.type === "llm" ? "这里按 Dify 的用法把模型、采样、提示和输出控制分组展开。" : "根据节点类型自动展开编辑项，尽量把提示词、变量和输出在这里配清楚。"}</div>
            ${node.type === "llm" ? `
                <div class="editor-actions">
                    <button class="btn btn-primary" type="button" onclick="openLLMConfigModal('${node.id}')">
                        <i class="fas fa-sliders"></i> 弹出参数框编辑
                    </button>
                </div>
            ` : ""}
            ${tabs.length ? `
                <div class="config-tabs">
                    ${tabs.map((tab) => `
                        <button class="config-tab ${tab.key === activeTab ? "is-active" : ""}" type="button" onclick="setNodeEditorTab('${node.id}', '${tab.key}')">
                            ${escapeHtml(tab.label)}
                        </button>
                    `).join("")}
                </div>
            ` : ""}
            ${Object.keys(groupedFields).length ? Object.entries(groupedFields)
                .filter(([groupName]) => !tabs.length || activeGroups.includes(groupName))
                .map(([groupName, items]) => `
                <div class="config-group">
                    <div class="config-group-head">
                        <strong>${escapeHtml(groupName)}</strong>
                    </div>
                    <div class="field-grid">
                        ${items.map((field) => renderNodeField(node, field)).join("")}
                    </div>
                </div>
            `).join("") : '<div class="empty-state">当前节点没有额外配置项。</div>'}
        </div>
        <div class="config-section">
            <h4>输入输出</h4>
            <div class="field-grid">
                <div class="form-group">
                    <label class="form-label">输入变量</label>
                    <input class="form-input" value="${escapeHtml((node.inputs || []).join(", "))}" onchange="updateNodeIO('${node.id}', 'inputs', this.value)" placeholder="user_query, kb_scope">
                </div>
                <div class="form-group">
                    <label class="form-label">输出变量</label>
                    <input class="form-input" value="${escapeHtml((node.outputs || []).join(", "))}" onchange="updateNodeIO('${node.id}', 'outputs', this.value)" placeholder="result, traces">
                </div>
            </div>
        </div>
        <div class="config-section">
            <h4>快捷操作</h4>
            <div class="editor-actions">
                <button class="btn" type="button" onclick="duplicateNode('${node.id}')">
                    <i class="fas fa-copy"></i> 复制节点
                </button>
                <button class="btn" type="button" onclick="focusNodeInCanvas('${node.id}')">
                    <i class="fas fa-crosshairs"></i> 定位节点
                </button>
                <button class="btn" type="button" onclick="deleteNode('${node.id}')">
                    <i class="fas fa-trash"></i> 删除节点
                </button>
            </div>
        </div>
    `;
}

function renderNodeField(node, field) {
    const config = node.config || {};
    const value = config[field.key] ?? "";
    const isWide = field.type === "textarea";
    const helper = renderFieldHelper(node, field);
    if (field.type === "checkbox") {
        return `
            <div class="form-group">
                <label class="form-label">${escapeHtml(field.label)}</label>
                <label class="toggle-field">
                    <input type="checkbox" ${value ? "checked" : ""} onchange="updateNodeCheckbox('${node.id}', '${field.key}', this.checked)">
                    <span>${value ? "已启用" : "未启用"}</span>
                </label>
                ${helper}
            </div>
        `;
    }
    if (field.type === "select") {
        return `
            <div class="form-group ${isWide ? "is-wide" : ""}">
                <label class="form-label">${escapeHtml(field.label)}</label>
                <select class="form-input" data-node-id="${node.id}" data-field-key="${field.key}" onchange="updateNodeConfig('${node.id}', '${field.key}', this.value)">
                    ${(field.options || []).map((option) => `
                        <option value="${escapeHtml(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>${escapeHtml(option.label)}</option>
                    `).join("")}
                </select>
                ${helper}
            </div>
        `;
    }
    if (field.type === "textarea") {
        return `
            <div class="form-group is-wide">
                <label class="form-label">${escapeHtml(field.label)}</label>
                <textarea class="form-input form-textarea" data-node-id="${node.id}" data-field-key="${field.key}" placeholder="${escapeHtml(field.placeholder || "")}" onchange="updateNodeConfig('${node.id}', '${field.key}', this.value)">${escapeHtml(value)}</textarea>
                ${helper}
            </div>
        `;
    }
    return `
        <div class="form-group ${field.wide ? "is-wide" : ""}">
            <label class="form-label">${escapeHtml(field.label)}</label>
            <input class="form-input" data-node-id="${node.id}" data-field-key="${field.key}" type="${field.type === "number" ? "number" : "text"}" value="${escapeHtml(value)}" placeholder="${escapeHtml(field.placeholder || "")}" onchange="updateNodeConfig('${node.id}', '${field.key}', this.value)">
            ${helper}
        </div>
    `;
}

function getNodeEditorTabs(node, groupedFields) {
    if (node.type === "llm") {
        return [
            { key: "deployment", label: "部署", groups: ["部署接入"] },
            { key: "prompt", label: "Prompt", groups: ["提示编排"] },
            { key: "model", label: "模型", groups: ["模型设置", "采样参数"] },
            { key: "context", label: "上下文", groups: ["上下文记忆"] },
            { key: "output", label: "输出", groups: ["输出控制"] },
        ].filter((tab) => tab.groups.some((group) => groupedFields[group]));
    }
    if (node.type === "agent") {
        return [
            { key: "prompt", label: "Prompt", groups: ["提示编排"] },
            { key: "model", label: "模型", groups: ["基础设置", "模型设置", "采样参数"] },
            { key: "context", label: "上下文", groups: ["运行策略"] },
            { key: "output", label: "输出", groups: ["输出结果"] },
        ].filter((tab) => tab.groups.some((group) => groupedFields[group]));
    }
    return [];
}

function renderFieldHelper(node, field) {
    if (!shouldShowFieldHelper(field)) return "";
    const tokens = getFieldHelperTokens(node, field.key);
    if (!tokens.length) return "";
    return `
        <div class="field-helper">
            <div class="helper-chip-row">
                ${tokens.map((token) => `
                    <button class="helper-chip" type="button" onclick="insertVariableToken('${node.id}', '${field.key}', '${escapeHtml(token.value)}')">
                        ${escapeHtml(token.label)}
                    </button>
                `).join("")}
            </div>
            <div class="helper-caption">点一下直接插入变量占位符，不需要手动记字段名。</div>
        </div>
    `;
}

function shouldShowFieldHelper(field) {
    return ["system_prompt", "prompt", "template", "body", "response_template", "condition", "json_schema"].includes(field.key);
}

function getFieldHelperTokens(node, fieldKey) {
    const tokens = [];
    const seen = new Set();
    const addToken = (label, value) => {
        if (!value || seen.has(value)) return;
        seen.add(value);
        tokens.push({ label, value });
    };

    getVariableEntries().forEach((entry) => addToken(entry.name, `{${entry.name}}`));
    (node.inputs || []).forEach((name) => addToken(name, `{${name}}`));
    (node.outputs || []).forEach((name) => addToken(name, `{${name}}`));
    ["user_query", "result", "llm_result_text", "final_output"].forEach((name) => addToken(name, `{${name}}`));

    if (fieldKey === "json_schema") {
        addToken("JSON 模板", '{"type":"object","properties":{"answer":{"type":"string"}}}');
    }
    return tokens.slice(0, 10);
}

function renderEdgeEditor(edge) {
    if (!edge) return "";
    const source = getNode(edge.source);
    const target = getNode(edge.target);
    return `
        <div class="config-section">
            <h4>连接关系</h4>
            <div class="field-grid">
                <div class="form-group">
                    <label class="form-label">起点</label>
                    <input class="form-input" value="${escapeHtml(source?.label || edge.source)}" disabled>
                </div>
                <div class="form-group">
                    <label class="form-label">终点</label>
                    <input class="form-input" value="${escapeHtml(target?.label || edge.target)}" disabled>
                </div>
                <div class="form-group">
                    <label class="form-label">分支标签</label>
                    <input class="form-input" value="${escapeHtml(edge.label || "")}" placeholder="true / false / default" onchange="updateEdgeField('${edge.id}', 'label', this.value)">
                </div>
                <div class="form-group">
                    <label class="form-label">命中条件</label>
                    <input class="form-input" value="${escapeHtml(edge.condition || "")}" placeholder="高优先级 / 审核通过" onchange="updateEdgeField('${edge.id}', 'condition', this.value)">
                </div>
            </div>
        </div>
        <div class="config-section">
            <h4>快捷操作</h4>
            <div class="editor-actions">
                <button class="btn" type="button" onclick="deleteEdge('${edge.id}')">
                    <i class="fas fa-trash"></i> 删除连线
                </button>
            </div>
        </div>
    `;
}

function handleCanvasDragOver(event) {
    event.preventDefault();
}

function handlePaletteDragStart(event) {
    event.dataTransfer.setData("nodeType", event.currentTarget.dataset.nodeType);
}

function handleCanvasDrop(event) {
    event.preventDefault();
    const nodeType = event.dataTransfer.getData("nodeType");
    if (!nodeType) return;

    const rect = event.currentTarget.getBoundingClientRect();
    createNode(nodeType, event.clientX - rect.left, event.clientY - rect.top);
}

function createNode(type, x, y) {
    const typeInfo = state.nodeTypeMap[type];
    if (!typeInfo) return;

    const node = {
        id: generateId("node"),
        type,
        label: typeInfo.label,
        position: {
            x: Math.max(36, Math.round(x)),
            y: Math.max(36, Math.round(y)),
        },
        config: deepClone(typeInfo.default_config || {}),
        inputs: [],
        outputs: [],
    };

    state.workflow.nodes.push(node);
    selectNode(node.id);
    markWorkflowDirty();
    renderAll();
}

function handleNodeMouseDown(event, nodeId) {
    if (event.target.classList.contains("node-port")) return;
    state.isDragging = true;
    state.dragMoved = false;
    state.draggedNodeId = nodeId;
    selectNode(nodeId);

    const nodeEl = document.querySelector(`[data-node-id="${nodeId}"]`);
    const rect = nodeEl.getBoundingClientRect();
    state.dragOffset.x = event.clientX - rect.left;
    state.dragOffset.y = event.clientY - rect.top;

    document.addEventListener("mousemove", handleNodeMouseMove);
    document.addEventListener("mouseup", handleNodeMouseUp);
}

function handleNodeMouseMove(event) {
    if (!state.isDragging || !state.draggedNodeId) return;
    const node = getNode(state.draggedNodeId);
    const canvas = document.getElementById("canvas");
    const rect = canvas.getBoundingClientRect();
    node.position.x = Math.max(24, Math.round(event.clientX - rect.left - state.dragOffset.x));
    node.position.y = Math.max(24, Math.round(event.clientY - rect.top - state.dragOffset.y));

    const nodeEl = document.querySelector(`[data-node-id="${node.id}"]`);
    if (nodeEl) {
        nodeEl.style.left = `${node.position.x}px`;
        nodeEl.style.top = `${node.position.y}px`;
    }
    state.dragMoved = true;
    renderConnections();
}

function handleNodeMouseUp() {
    if (state.isDragging) {
        markWorkflowDirty();
        renderWorkflowOutline();
    }
    state.isDragging = false;
    state.draggedNodeId = null;
    document.removeEventListener("mousemove", handleNodeMouseMove);
    document.removeEventListener("mouseup", handleNodeMouseUp);
}

function handlePortMouseDown(event, nodeId, portType) {
    if (portType === "input") return;
    state.isConnecting = true;
    state.connectionStartNodeId = nodeId;
    document.addEventListener("mousemove", handleConnectionMouseMove);
    document.addEventListener("mouseup", handleConnectionMouseUp);
}

function handleConnectionMouseMove(event) {
    if (!state.isConnecting || !state.connectionStartNodeId) return;
    const svg = document.getElementById("connectionsSvg");
    const startNode = document.querySelector(`[data-node-id="${state.connectionStartNodeId}"]`);
    const startPort = startNode?.querySelector(".output-port");
    if (!svg || !startPort) return;

    if (state.tempLine) {
        state.tempLine.remove();
        state.tempLine = null;
    }

    const svgRect = svg.getBoundingClientRect();
    const startRect = startPort.getBoundingClientRect();
    const x1 = startRect.left + startRect.width / 2 - svgRect.left;
    const y1 = startRect.top + startRect.height / 2 - svgRect.top;
    const x2 = event.clientX - svgRect.left;
    const y2 = event.clientY - svgRect.top;
    const curve = `M ${x1} ${y1} C ${x1 + 90} ${y1}, ${x2 - 90} ${y2}, ${x2} ${y2}`;

    state.tempLine = document.createElementNS("http://www.w3.org/2000/svg", "path");
    state.tempLine.setAttribute("d", curve);
    state.tempLine.setAttribute("class", "edge-path");
    state.tempLine.setAttribute("opacity", "0.45");
    svg.appendChild(state.tempLine);
}

function handleConnectionMouseUp(event) {
    if (!state.isConnecting) return;
    const target = event.target;
    if (target.classList.contains("node-port") && target.dataset.port === "input") {
        const targetNodeId = target.closest(".workflow-node")?.dataset.nodeId;
        if (targetNodeId && targetNodeId !== state.connectionStartNodeId) {
            createEdge(state.connectionStartNodeId, targetNodeId);
        }
    }

    state.tempLine?.remove();
    state.tempLine = null;
    state.isConnecting = false;
    state.connectionStartNodeId = null;
    document.removeEventListener("mousemove", handleConnectionMouseMove);
    document.removeEventListener("mouseup", handleConnectionMouseUp);
}

function createEdge(sourceId, targetId) {
    const existing = state.workflow.edges.find((edge) => edge.source === sourceId && edge.target === targetId);
    if (existing) {
        selectEdge(existing.id);
        return;
    }

    const edge = {
        id: generateId("edge"),
        source: sourceId,
        target: targetId,
        label: suggestEdgeLabel(sourceId),
        condition: "",
    };

    state.workflow.edges.push(edge);
    selectEdge(edge.id);
    markWorkflowDirty();
    renderAll();
}

function suggestEdgeLabel(sourceId) {
    const sourceNode = getNode(sourceId);
    if (!sourceNode || sourceNode.type !== "condition") return "";
    const outgoing = state.workflow.edges.filter((edge) => edge.source === sourceId).map((edge) => edge.label);
    if (!outgoing.includes("true")) return "true";
    if (!outgoing.includes("false")) return "false";
    return "";
}

function handleCanvasClick(event) {
    if (event.target.id === "canvas" || event.target.id === "canvasContent") {
        closeConfigPanel();
    }
}

function selectNode(nodeId) {
    state.selectedNodeId = nodeId;
    state.selectedEdgeId = null;
    renderWorkflow();
    renderSelectionPanel();
    renderWorkflowOutline();
    const node = getNode(nodeId);
    if (node?.type === "llm") {
        openLLMConfigModal(nodeId);
        return;
    }
    closeLLMConfigModal();
}

function selectEdge(edgeId) {
    state.selectedEdgeId = edgeId;
    state.selectedNodeId = null;
    closeLLMConfigModal();
    renderWorkflow();
    renderSelectionPanel();
    renderWorkflowOutline();
}

function closeConfigPanel() {
    state.selectedNodeId = null;
    state.selectedEdgeId = null;
    closeLLMConfigModal();
    renderWorkflow();
    renderSelectionPanel();
    renderWorkflowOutline();
}

function updateNodeLabel(nodeId, label) {
    const node = getNode(nodeId);
    if (!node) return;
    node.label = label;
    markWorkflowDirty();
    renderAll();
    if (state.llmModalNodeId === nodeId) {
        renderLLMModal();
    }
}

function updateNodeConfig(nodeId, key, value) {
    const node = getNode(nodeId);
    if (!node) return;
    const field = (state.nodeTypeMap[node.type]?.fields || []).find((item) => item.key === key);
    if (field?.type === "number") {
        node.config[key] = value === "" ? "" : Number(value);
    } else {
        node.config[key] = value;
    }
    markWorkflowDirty();
    renderAll();
    if (state.llmModalNodeId === nodeId) {
        renderLLMModal();
    }
}

function updateNodeCheckbox(nodeId, key, value) {
    const node = getNode(nodeId);
    if (!node) return;
    node.config[key] = Boolean(value);
    markWorkflowDirty();
    renderAll();
    if (state.llmModalNodeId === nodeId) {
        renderLLMModal();
    }
}

function setNodeEditorTab(nodeId, tabKey) {
    state.editorTabs[nodeId] = tabKey;
    renderSelectionPanel();
    if (state.llmModalNodeId === nodeId) {
        renderLLMModal();
    }
}

function handleConfigFocusIn(event) {
    const target = event.target;
    const nodeId = target.dataset?.nodeId;
    const fieldKey = target.dataset?.fieldKey;
    if (!nodeId || !fieldKey) return;
    state.focusedConfigField = { nodeId, fieldKey };
}

function insertVariableToken(nodeId, fieldKey, tokenValue) {
    const element = document.querySelector(`[data-node-id="${nodeId}"][data-field-key="${fieldKey}"]`);
    const node = getNode(nodeId);
    if (!node) return;

    if (element && typeof element.selectionStart === "number") {
        const start = element.selectionStart;
        const end = element.selectionEnd;
        const current = element.value || "";
        const next = `${current.slice(0, start)}${tokenValue}${current.slice(end)}`;
        element.value = next;
        updateNodeConfig(nodeId, fieldKey, next);
        const cursor = start + tokenValue.length;
        element.focus();
        element.setSelectionRange(cursor, cursor);
        return;
    }

    const currentValue = String(node.config?.[fieldKey] ?? "");
    const nextValue = `${currentValue}${currentValue ? " " : ""}${tokenValue}`;
    updateNodeConfig(nodeId, fieldKey, nextValue);
}

function openLLMConfigModal(nodeId) {
    const node = getNode(nodeId);
    if (!node || node.type !== "llm") return;
    state.llmModalNodeId = nodeId;
    renderLLMModal();
}

function closeLLMConfigModal() {
    state.llmModalNodeId = null;
    renderLLMModal();
}

function handleLLMModalBackdropClick(event) {
    if (event.target.id === "llmConfigModal") {
        closeLLMConfigModal();
    }
}

function focusCurrentLLMNode() {
    if (state.llmModalNodeId) {
        focusNodeInCanvas(state.llmModalNodeId);
    }
}

function renderLLMModal() {
    const modal = document.getElementById("llmConfigModal");
    const body = document.getElementById("llmModalBody");
    const title = document.getElementById("llmModalTitle");
    const subtitle = document.getElementById("llmModalSubtitle");
    if (!modal || !body || !title || !subtitle) return;

    const node = state.llmModalNodeId ? getNode(state.llmModalNodeId) : null;
    if (!node || node.type !== "llm") {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        body.innerHTML = "";
        return;
    }

    const typeInfo = state.nodeTypeMap[node.type] || {};
    const fields = Array.isArray(typeInfo.fields) ? typeInfo.fields : [];
    const groupedFields = fields.reduce((acc, field) => {
        const group = field.group || "节点参数";
        if (!acc[group]) acc[group] = [];
        acc[group].push(field);
        return acc;
    }, {});
    const tabs = getNodeEditorTabs(node, groupedFields);
    const activeTab = tabs.length ? (state.editorTabs[node.id] || tabs[0].key) : "";
    const activeGroups = tabs.length
        ? tabs.find((tab) => tab.key === activeTab)?.groups || []
        : Object.keys(groupedFields);
    const bindingLabel = node.config?.endpoint_id
        ? `${node.config.endpoint_id}${node.config?.base_url ? ` · ${node.config.base_url}` : ""}`
        : (node.config?.base_url || "还没有绑定已部署模型");

    title.textContent = `${node.label || "LLM"} 参数配置`;
    subtitle.textContent = `当前节点：${node.config?.provider || "openai"} / ${node.config?.model || "未选择模型"}${node.config?.endpoint_id ? ` · 已绑定 ${node.config.endpoint_id}` : " · 可从左侧已部署 LLM 直接切换"}。`;
    body.innerHTML = `
        <div class="llm-modal-grid">
            <div class="llm-modal-main">
                <div class="llm-modal-card">
                    <h4>节点基础</h4>
                    <div class="field-grid">
                        <div class="form-group">
                            <label class="form-label">节点名称</label>
                            <input class="form-input" value="${escapeHtml(node.label || "")}" onchange="updateNodeLabel('${node.id}', this.value)">
                        </div>
                        <div class="form-group">
                            <label class="form-label">绑定部署</label>
                            <input class="form-input" value="${escapeHtml(bindingLabel)}" disabled>
                        </div>
                    </div>
                </div>
                <div class="llm-modal-card">
                    <h4>参数分栏</h4>
                    <div class="config-tabs">
                        ${tabs.map((tab) => `
                            <button class="config-tab ${tab.key === activeTab ? "is-active" : ""}" type="button" onclick="setNodeEditorTab('${node.id}', '${tab.key}')">
                                ${escapeHtml(tab.label)}
                            </button>
                        `).join("")}
                    </div>
                    ${Object.entries(groupedFields)
                        .filter(([groupName]) => !tabs.length || activeGroups.includes(groupName))
                        .map(([groupName, items]) => `
                            <div class="config-group">
                                <div class="config-group-head">
                                    <strong>${escapeHtml(groupName)}</strong>
                                </div>
                                <div class="field-grid">
                                    ${items.map((field) => renderNodeField(node, field)).join("")}
                                </div>
                            </div>
                        `).join("")}
                </div>
            </div>
            <div class="llm-modal-side">
                <div class="llm-modal-card">
                    <h4>Prompt 预览</h4>
                    <p>直接查看当前 Prompt 模板，改完参数不用切回右侧再找。</p>
                    <div class="llm-modal-preview">${escapeHtml(node.config?.prompt || "")}</div>
                </div>
                <div class="llm-modal-card">
                    <h4>配置摘要</h4>
                    <p>模型、采样和输出控制集中展示。</p>
                    <div class="overview-grid">
                        <div class="overview-card">
                            <strong>部署接入</strong>
                            <p>${escapeHtml(node.config?.endpoint_id || "未绑定部署")} · ${escapeHtml(node.config?.base_url || "可从左侧已部署 LLM 直接选择")}</p>
                        </div>
                        <div class="overview-card">
                            <strong>模型</strong>
                            <p>${escapeHtml(node.config?.provider || "openai")} / ${escapeHtml(node.config?.model || "未选择")}</p>
                        </div>
                        <div class="overview-card">
                            <strong>采样</strong>
                            <p>Temp ${escapeHtml(node.config?.temperature ?? 0.7)} · Top P ${escapeHtml(node.config?.top_p ?? 1)} · Max ${escapeHtml(node.config?.max_tokens ?? 1500)}</p>
                        </div>
                        <div class="overview-card">
                            <strong>输出</strong>
                            <p>${escapeHtml(node.config?.response_format || "text")} · ${escapeHtml(node.config?.output_var || "llm_result")}</p>
                        </div>
                    </div>
                </div>
                <div class="llm-modal-card">
                    <h4>参数预设</h4>
                    <p>点一下就切换整组采样参数和输出格式，适合快速试验不同风格。</p>
                    <div class="llm-preset-list">
                        ${llmPresets.map((preset) => `
                            <div class="llm-preset-item">
                                <div class="llm-preset-head">
                                    <div>
                                        <div class="llm-preset-title">${escapeHtml(preset.name)}</div>
                                        <div class="llm-preset-copy">${escapeHtml(preset.description)}</div>
                                    </div>
                                    <button class="btn btn-ghost" type="button" onclick="applyLLMPreset('${node.id}', '${preset.id}')">
                                        <i class="fas fa-bolt"></i> 套用
                                    </button>
                                </div>
                                <div class="helper-chip-row">
                                    <span class="helper-chip">Temp ${escapeHtml(String(preset.config.temperature ?? "-"))}</span>
                                    <span class="helper-chip">Top P ${escapeHtml(String(preset.config.top_p ?? "-"))}</span>
                                    <span class="helper-chip">${escapeHtml(preset.config.response_format || "text")}</span>
                                </div>
                            </div>
                        `).join("")}
                    </div>
                </div>
            </div>
        </div>
    `;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
}

function analyzeWorkflow() {
    const nodes = state.workflow.nodes || [];
    const edges = state.workflow.edges || [];
    const variableEntries = getVariableEntries();
    const issues = getLocalValidation();
    const typeCounts = {};
    const referencedVariables = new Set();
    let configuredNodeCount = 0;
    let branchCount = 0;
    let llmCount = 0;
    let edgeLabelCount = 0;

    nodes.forEach((node) => {
        typeCounts[node.type] = (typeCounts[node.type] || 0) + 1;
        if (node.type === "condition") branchCount += 1;
        if (node.type === "llm") llmCount += 1;
        const config = node.config || {};
        const nonEmptyConfigKeys = Object.entries(config).filter(([, value]) => value !== "" && value !== null && value !== undefined && value !== false);
        if (nonEmptyConfigKeys.length >= 2) configuredNodeCount += 1;
        Object.values(config).forEach((value) => {
            extractTokensFromValue(value).forEach((token) => referencedVariables.add(token));
        });
        (node.inputs || []).forEach((name) => referencedVariables.add(name));
        (node.outputs || []).forEach((name) => referencedVariables.add(name));
    });

    edges.forEach((edge) => {
        if (edge.label || edge.condition) edgeLabelCount += 1;
    });

    const nodeCount = nodes.length;
    const variableCount = variableEntries.length;
    const referencedVariableCount = Array.from(referencedVariables).filter((token) => variableEntries.some((entry) => entry.name === token)).length;
    const complexityScore = clampPercentage(
        (nodeCount * 10) +
        (edges.length * 6) +
        (branchCount * 12) +
        (llmCount * 10) +
        (typeCounts.api ? 10 : 0) +
        (typeCounts.merge ? 8 : 0)
    );
    const structureScore = clampPercentage(Math.round(((configuredNodeCount + edgeLabelCount) / Math.max(nodeCount + branchCount, 1)) * 100));
    const variableCoverage = clampPercentage(variableCount ? Math.round((referencedVariableCount / variableCount) * 100) : (nodeCount ? 60 : 0));
    const releaseReadiness = clampPercentage(Math.round(
        (complexityScore * 0.22) +
        (structureScore * 0.38) +
        (variableCoverage * 0.18) +
        ((issues.length ? Math.max(0, 100 - issues.length * 18) : 100) * 0.22)
    ));

    return {
        nodeCount,
        edgeCount: edges.length,
        variableCount,
        llmCount,
        branchCount,
        configuredNodeCount,
        referencedVariableCount,
        typeCounts,
        issues,
        complexityScore,
        structureScore,
        variableCoverage,
        releaseReadiness,
    };
}

function buildRouteSummaries() {
    const nodes = state.workflow.nodes || [];
    const edges = state.workflow.edges || [];
    if (!nodes.length) return [];
    const outgoing = new Map();
    edges.forEach((edge) => {
        if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
        outgoing.get(edge.source).push(edge);
    });
    const starts = nodes.filter((node) => node.type === "start" || !edges.some((edge) => edge.target === node.id));
    const routes = [];
    const walk = (nodeId, trail, depth) => {
        if (depth > 8) {
            routes.push({ kind: "截断", summary: `${trail.join(" → ")} → ...` });
            return;
        }
        const node = getNode(nodeId);
        if (!node) return;
        const nextTrail = [...trail, node.label || node.type];
        const nextEdges = outgoing.get(nodeId) || [];
        if (!nextEdges.length) {
            routes.push({ kind: node.type === "end" ? "闭环完成" : "未收口", summary: nextTrail.join(" → ") });
            return;
        }
        nextEdges.forEach((edge) => {
            const suffix = edge.label ? `(${edge.label})` : edge.condition ? `(${edge.condition})` : "";
            const target = getNode(edge.target);
            if (!target) return;
            walk(edge.target, suffix ? [...nextTrail, suffix] : nextTrail, depth + 1);
        });
    };
    starts.forEach((node) => walk(node.id, [], 0));
    return routes.slice(0, 6);
}

function buildNextSteps() {
    const analysis = analyzeWorkflow();
    const steps = [];
    if (!analysis.nodeCount) {
        steps.push({ title: "先拉一条主链路", copy: "建议从开始、LLM 或 Agent、结束三个节点起步，再逐步补条件和 API。" });
        steps.push({ title: "加一个复杂 Demo", copy: "左侧复杂 Demo 已经准备好，可以直接拉一条完整场景进画布。" });
        return steps;
    }
    if (analysis.issues.length) {
        analysis.issues.slice(0, 3).forEach((issue) => {
            steps.push({ title: "先修结构阻塞", copy: issue });
        });
    }
    if (analysis.variableCount === 0) {
        steps.push({ title: "补全局变量", copy: "把 user_query、kb_scope、response_policy 这类变量提到全局，后续节点复用会更稳。" });
    }
    if (!analysis.llmCount) {
        steps.push({ title: "补推理节点", copy: "当前还没有 LLM 节点，复杂编排通常需要至少一个模型节点承担分析或生成。" });
    }
    if (!analysis.branchCount && analysis.nodeCount >= 4) {
        steps.push({ title: "增加分支控制", copy: "节点数量已经上来，但还没有条件分支，可以补一层判断节点控制不同路径。" });
    }
    if (!steps.length) {
        steps.push({ title: "试一轮运行场景", copy: "当前结构已经比较完整，建议直接套用一条 demo 输入看执行链路和输出格式。" });
        steps.push({ title: "细化输出结构", copy: "如果要接到其他页面或下游链路，建议把结束节点输出模版改成稳定 JSON。" });
        steps.push({ title: "为关键节点套用预设", copy: "LLM 节点已经支持一键参数预设，可以再调一轮模型表现。" });
    }
    return steps.slice(0, 4);
}

function buildNodeInventory() {
    const analysis = analyzeWorkflow();
    const typeLabelMap = Object.fromEntries(state.nodeTypes.map((item) => [item.type, item.label]));
    const entries = Object.entries(analysis.typeCounts).sort((a, b) => b[1] - a[1]);
    return entries.map(([type, count]) => ({
        label: typeLabelMap[type] || type,
        count,
        copy: type === "llm"
            ? "负责核心生成与推理，建议重点调模型参数。"
            : type === "condition"
                ? "负责链路路由和分支控制。"
                : type === "api"
                    ? "负责外部系统集成与实时数据接入。"
                    : type === "merge"
                        ? "负责多路结果收敛。"
                        : "当前流程中的基础组成部分。"
    }));
}

function getCurrentRunPresets() {
    const scenario = workflowScenarios.find((item) => item.id === state.currentScenarioId);
    if (scenario?.runPresets?.length) return scenario.runPresets;
    const variableBasedPreset = buildVariableBackedPreset();
    return variableBasedPreset ? [variableBasedPreset] : [];
}

function buildVariableBackedPreset() {
    const variables = normalizeVariables(state.workflow.variables);
    const keys = Object.keys(variables);
    if (!keys.length) return null;
    const input = {};
    keys.slice(0, 8).forEach((key) => {
        input[key] = variables[key]?.value ?? "";
    });
    return {
        id: "workflow_variables",
        name: "按流程变量生成",
        description: "把当前流程变量直接带进测试输入。",
        input,
    };
}

function extractTokensFromValue(value) {
    const text = typeof value === "string" ? value : JSON.stringify(value || "");
    const matches = [...String(text).matchAll(/\{([a-zA-Z0-9_]+)\}/g)];
    return [...new Set(matches.map((match) => match[1]))];
}

function clampPercentage(value) {
    return Math.max(0, Math.min(Math.round(value), 100));
}

function updateNodeIO(nodeId, direction, value) {
    const node = getNode(nodeId);
    if (!node) return;
    node[direction] = splitList(value);
    markWorkflowDirty();
    renderAll();
}

function duplicateNode(nodeId) {
    const node = getNode(nodeId);
    if (!node) return;
    const copy = deepClone(node);
    copy.id = generateId("node");
    copy.label = `${node.label || state.nodeTypeMap[node.type]?.label || node.type} 副本`;
    copy.position = {
        x: node.position.x + 40,
        y: node.position.y + 40,
    };
    state.workflow.nodes.push(copy);
    selectNode(copy.id);
    markWorkflowDirty();
    renderAll();
}

function deleteNode(nodeId) {
    state.workflow.nodes = state.workflow.nodes.filter((node) => node.id !== nodeId);
    state.workflow.edges = state.workflow.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId);
    if (state.selectedNodeId === nodeId) state.selectedNodeId = null;
    if (state.llmModalNodeId === nodeId) state.llmModalNodeId = null;
    markWorkflowDirty();
    renderAll();
}

function updateEdgeField(edgeId, key, value) {
    const edge = getEdge(edgeId);
    if (!edge) return;
    edge[key] = value;
    markWorkflowDirty();
    renderAll();
}

function deleteEdge(edgeId) {
    state.workflow.edges = state.workflow.edges.filter((edge) => edge.id !== edgeId);
    if (state.selectedEdgeId === edgeId) state.selectedEdgeId = null;
    markWorkflowDirty();
    renderAll();
}

function handleWorkflowSettingsInput(event) {
    const target = event.target;
    const index = Number(target.dataset.variableIndex);
    const field = target.dataset.field;
    if (Number.isNaN(index) || !field) return;
    updateVariableField(index, field, target.value);
}

function handleWorkflowSettingsClick(event) {
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (!action) return;
    if (action === "add-variable") {
        addWorkflowVariable();
    }
    if (action === "remove-variable") {
        const index = Number(event.target.closest("[data-variable-index]")?.dataset.variableIndex || event.target.dataset.variableIndex);
        removeWorkflowVariable(index);
    }
}

function handleKeydown(event) {
    const tagName = event.target?.tagName;
    const isTyping = tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT";
    if (event.key === "Escape" && state.llmModalNodeId) {
        event.preventDefault();
        closeLLMConfigModal();
        return;
    }
    if (isTyping) return;

    if ((event.key === "Delete" || event.key === "Backspace") && state.selectedNodeId) {
        event.preventDefault();
        deleteNode(state.selectedNodeId);
        return;
    }
    if ((event.key === "Delete" || event.key === "Backspace") && state.selectedEdgeId) {
        event.preventDefault();
        deleteEdge(state.selectedEdgeId);
        return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d" && state.selectedNodeId) {
        event.preventDefault();
        duplicateNode(state.selectedNodeId);
    }
}

function getVariableEntries() {
    return Object.entries(normalizeVariables(state.workflow.variables)).map(([name, meta]) => ({ name, meta }));
}

function normalizeVariables(variables) {
    const normalized = {};
    Object.entries(variables || {}).forEach(([key, value]) => {
        if (value && typeof value === "object" && !Array.isArray(value) && ("value" in value || "description" in value || "type" in value)) {
            normalized[key] = {
                value: value.value ?? "",
                description: value.description ?? "",
                type: value.type || inferVariableType(value.value),
            };
        } else {
            normalized[key] = {
                value,
                description: "",
                type: inferVariableType(value),
            };
        }
    });
    return normalized;
}

function addWorkflowVariable() {
    const variables = normalizeVariables(state.workflow.variables);
    let index = Object.keys(variables).length + 1;
    let name = `var_${index}`;
    while (variables[name]) {
        index += 1;
        name = `var_${index}`;
    }
    variables[name] = { value: "", description: "", type: "string" };
    state.workflow.variables = variables;
    markWorkflowDirty();
    renderAll();
}

function removeWorkflowVariable(index) {
    const entries = getVariableEntries();
    const current = entries[index];
    if (!current) return;
    const variables = normalizeVariables(state.workflow.variables);
    delete variables[current.name];
    state.workflow.variables = variables;
    markWorkflowDirty();
    renderAll();
}

function updateVariableField(index, field, value) {
    const entries = getVariableEntries();
    const current = entries[index];
    if (!current) return;
    const variables = normalizeVariables(state.workflow.variables);

    if (field === "name") {
        const nextName = (value || "").trim();
        if (!nextName || nextName === current.name) return;
        if (variables[nextName]) return;
        variables[nextName] = variables[current.name];
        delete variables[current.name];
        state.workflow.variables = variables;
    } else {
        variables[current.name][field] = field === "value" ? parseVariableValue(value, variables[current.name].type) : value;
        state.workflow.variables = variables;
    }

    markWorkflowDirty();
    renderAll();
}

function parseVariableValue(value, type) {
    if (type === "number") return value === "" ? "" : Number(value);
    if (type === "boolean") return value === "true" || value === true;
    if (type === "object" || type === "array") {
        try {
            return JSON.parse(value || (type === "array" ? "[]" : "{}"));
        } catch (_error) {
            return value;
        }
    }
    return value;
}

function inferVariableType(value) {
    if (Array.isArray(value)) return "array";
    if (value && typeof value === "object") return "object";
    if (typeof value === "number") return "number";
    if (typeof value === "boolean") return "boolean";
    return "string";
}

function stringifyVariableValue(value) {
    if (value && typeof value === "object") {
        try {
            return JSON.stringify(value);
        } catch (_error) {
            return String(value);
        }
    }
    return value == null ? "" : String(value);
}

function updateCanvasGuide() {
    const guide = document.getElementById("canvasGuide");
    if (guide) guide.hidden = state.workflow.nodes.length > 0;
}

function updateWorkflowMeta(statusText) {
    const nodeCount = document.getElementById("nodeCount");
    const edgeCount = document.getElementById("edgeCount");
    const saveState = document.getElementById("saveState");
    if (nodeCount) nodeCount.textContent = String(state.workflow.nodes.length);
    if (edgeCount) edgeCount.textContent = String(state.workflow.edges.length);
    if (saveState) {
        if (statusText) {
            saveState.textContent = statusText;
        } else if (state.workflowDirty) {
            saveState.textContent = "未保存变更";
        } else if (state.workflow.id) {
            saveState.textContent = "已保存";
        } else {
            saveState.textContent = "未保存";
        }
    }
    updateSelectionState();
}

function updateSelectionState() {
    const selectionState = document.getElementById("selectionState");
    if (!selectionState) return;
    if (state.selectedNodeId) {
        const node = getNode(state.selectedNodeId);
        selectionState.textContent = node ? `节点 · ${node.label}` : "未选中对象";
        return;
    }
    if (state.selectedEdgeId) {
        const edge = getEdge(state.selectedEdgeId);
        selectionState.textContent = edge ? `连线 · ${edge.label || "未命名分支"}` : "未选中对象";
        return;
    }
    selectionState.textContent = "未选中对象";
}

function updateStructureSummary() {
    const summary = document.getElementById("structureSummary");
    if (!summary) return;
    if (!state.workflow.nodes.length) {
        summary.textContent = "画布还是空的，可以从模板或节点库开始。";
        return;
    }
    const startCount = state.workflow.nodes.filter((node) => node.type === "start").length;
    const endCount = state.workflow.nodes.filter((node) => node.type === "end").length;
    const variableCount = Object.keys(state.workflow.variables || {}).length;
    summary.textContent = `起点 ${startCount} · 终点 ${endCount} · 全局变量 ${variableCount} · 已配置 ${state.workflow.edges.length} 条连接。`;
}

function markWorkflowDirty() {
    state.workflowDirty = true;
    updateWorkflowMeta("未保存变更");
}

function clearCanvas() {
    if (!window.confirm("确定要清空整张画布吗？当前编排内容会被移除。")) return;
    state.workflow = createEmptyWorkflow();
    state.currentScenarioId = "";
    state.selectedRunPresetId = "";
    state.workflowDirty = false;
    closeConfigPanel();
    renderRunResult("还没有运行结果。", []);
    renderAll();
    updateWorkflowMeta("画布已清空");
}

function newWorkflow() {
    if (state.workflowDirty && !window.confirm("当前有未保存变更，仍然新建空白流程吗？")) return;
    state.workflow = createEmptyWorkflow();
    state.currentScenarioId = "";
    state.selectedRunPresetId = "";
    state.workflowDirty = false;
    closeConfigPanel();
    renderRunResult("还没有运行结果。", []);
    renderAll();
    updateWorkflowMeta("新建空白流程");
}

function loadStarterFlow() {
    const template = state.templates.find((item) => item.id === "simple") || state.templates[0];
    if (template) {
        state.currentScenarioId = "";
        state.selectedRunPresetId = "";
        applyTemplate(template);
    }
}

function loadTemplateById(templateId) {
    const template = state.templates.find((item) => item.id === templateId);
    if (!template) return;
    state.currentScenarioId = "";
    state.selectedRunPresetId = "";
    applyTemplate(template);
}

function loadWorkflowScenario(scenarioId) {
    const scenario = workflowScenarios.find((item) => item.id === scenarioId);
    if (!scenario) return;
    state.currentScenarioId = scenario.id;
    state.selectedRunPresetId = scenario.runPresets?.[0]?.id || "";
    applyTemplate(scenario.workflow);
    if (scenario.runPresets?.length) {
        setRunInputValue(scenario.runPresets[0].input);
    }
    renderWorkflowLab();
    updateWorkflowMeta(`已载入 Demo：${scenario.name}`);
}

function applyTemplate(template) {
    const idMap = {};
    const nodes = (template.nodes || []).map((node) => {
        const nextId = generateId("node");
        idMap[node.id] = nextId;
        return normalizeNode({
            ...node,
            id: nextId,
        });
    });
    const edges = (template.edges || []).map((edge) => normalizeEdge({
        ...edge,
        id: generateId("edge"),
        source: idMap[edge.source],
        target: idMap[edge.target],
    }));

    state.workflow = {
        id: null,
        name: template.name || "",
        description: template.description || "",
        nodes,
        edges,
        variables: normalizeVariables(template.variables || {}),
    };
    state.workflowDirty = true;
    closeConfigPanel();
    renderRunResult("还没有运行结果。", []);
    renderAll();
    updateWorkflowMeta("未保存变更");
}

async function openWorkflow(workflowId) {
    try {
        const response = await fetch(`/api/visual-workflow/workflows/${workflowId}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "加载流程失败");
        state.workflow = normalizeWorkflow(data);
        state.currentScenarioId = "";
        state.selectedRunPresetId = "";
        state.workflowDirty = false;
        closeConfigPanel();
        renderRunResult("还没有运行结果。", []);
        renderAll();
        updateWorkflowMeta("已载入");
    } catch (error) {
        alert(`加载流程失败: ${error.message || error}`);
    }
}

async function removeWorkflowFromLibrary(workflowId) {
    if (!window.confirm("确定删除这条已保存流程吗？")) return;
    try {
        const response = await fetch(`/api/visual-workflow/workflows/${workflowId}`, { method: "DELETE" });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) throw new Error(data.error || "删除失败");
        if (state.workflow.id === workflowId) {
            state.workflow = createEmptyWorkflow();
            state.workflowDirty = false;
            closeConfigPanel();
            renderAll();
        }
        await loadWorkflowLibrary();
    } catch (error) {
        alert(`删除流程失败: ${error.message || error}`);
    }
}

function triggerImportWorkflow() {
    const input = document.getElementById("workflowImportInput");
    if (!input) return;
    input.value = "";
    input.click();
}

async function handleWorkflowImport(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
        const text = await file.text();
        const data = JSON.parse(text);
        state.workflow = normalizeWorkflow(data);
        state.workflow.id = null;
        state.currentScenarioId = "";
        state.selectedRunPresetId = "";
        state.workflowDirty = true;
        closeConfigPanel();
        renderRunResult("已导入流程 JSON，当前是未保存草稿。", []);
        renderAll();
        updateWorkflowMeta("已导入未保存草稿");
    } catch (error) {
        alert(`导入失败: ${error.message || error}`);
    }
}

function exportWorkflow() {
    const payload = {
        id: state.workflow.id,
        name: state.workflow.name,
        description: state.workflow.description,
        nodes: state.workflow.nodes,
        edges: state.workflow.edges,
        variables: state.workflow.variables,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${(state.workflow.name || "workflow").replace(/\s+/g, "_")}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function applyRunPreset(presetId) {
    const preset = getCurrentRunPresets().find((item) => item.id === presetId);
    if (!preset) return;
    state.selectedRunPresetId = presetId;
    setRunInputValue(preset.input || {});
    renderWorkflowLab();
    updateWorkflowMeta(`已载入测试场景：${preset.name}`);
}

function autoLayout() {
    if (!state.workflow.nodes.length) return;
    const levels = buildNodeLevels();
    const groups = new Map();
    state.workflow.nodes.forEach((node) => {
        const level = levels[node.id] ?? 0;
        if (!groups.has(level)) groups.set(level, []);
        groups.get(level).push(node);
    });

    Array.from(groups.keys()).sort((a, b) => a - b).forEach((level) => {
        groups.get(level).forEach((node, index) => {
            node.position.x = 80 + level * 260;
            node.position.y = 80 + index * 170;
        });
    });

    markWorkflowDirty();
    renderAll();
}

function buildNodeLevels() {
    const levels = {};
    const incoming = {};
    state.workflow.nodes.forEach((node) => {
        incoming[node.id] = 0;
    });
    state.workflow.edges.forEach((edge) => {
        incoming[edge.target] = (incoming[edge.target] || 0) + 1;
    });

    const queue = state.workflow.nodes
        .filter((node) => node.type === "start" || incoming[node.id] === 0)
        .map((node) => ({ id: node.id, level: 0 }));

    while (queue.length) {
        const current = queue.shift();
        levels[current.id] = Math.max(levels[current.id] || 0, current.level);
        state.workflow.edges
            .filter((edge) => edge.source === current.id)
            .forEach((edge) => queue.push({ id: edge.target, level: current.level + 1 }));
    }

    return levels;
}

function focusNodeInCanvas(nodeId) {
    const nodeEl = document.querySelector(`[data-node-id="${nodeId}"]`);
    nodeEl?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
}

function setRunInputValue(value) {
    const input = document.getElementById("runInput");
    if (!input) return;
    input.value = JSON.stringify(value || {}, null, 2);
}

function getLocalValidation() {
    const issues = [];
    const startCount = state.workflow.nodes.filter((node) => node.type === "start").length;
    const endCount = state.workflow.nodes.filter((node) => node.type === "end").length;
    if (!startCount) issues.push("缺少开始节点");
    if (!endCount) issues.push("缺少结束节点");

    const nodeIds = new Set(state.workflow.nodes.map((node) => node.id));
    state.workflow.edges.forEach((edge) => {
        if (!nodeIds.has(edge.source)) issues.push(`连线源节点不存在: ${edge.source}`);
        if (!nodeIds.has(edge.target)) issues.push(`连线目标节点不存在: ${edge.target}`);
    });

    state.workflow.nodes.forEach((node) => {
        if (node.type === "llm" && !node.config?.prompt) issues.push(`LLM 节点「${node.label}」缺少提示模板`);
        if (node.type === "agent" && !node.config?.prompt) issues.push(`Agent 节点「${node.label}」缺少提示模板`);
        if (node.type === "condition" && !node.config?.condition) issues.push(`条件节点「${node.label}」缺少条件表达式`);
        if (node.type === "api" && !node.config?.url) issues.push(`API 节点「${node.label}」缺少请求地址`);
        if (node.type === "merge" && !node.config?.source_vars) issues.push(`合流节点「${node.label}」缺少来源变量`);
    });

    return issues;
}

async function validateWorkflow() {
    const localIssues = getLocalValidation();
    if (localIssues.length) {
        renderRunResult(`检查未通过\n\n${localIssues.map((item) => `- ${item}`).join("\n")}`, localIssues.map((item) => ({
            title: "本地检查",
            detail: item,
        })));
        updateWorkflowMeta("检查未通过");
        alert(`流程检查未通过:\n${localIssues.join("\n")}`);
        return;
    }

    if (!state.workflow.id) {
        renderRunResult("本地检查通过。当前流程还没保存，可以先继续编辑，也可以直接保存后再跑服务端校验。", [{
            title: "本地检查",
            detail: "结构完整，起点、终点、关键字段都已满足最低要求。",
        }]);
        updateWorkflowMeta("本地检查通过");
        alert("✓ 本地检查通过，可以继续保存或执行");
        return;
    }

    try {
        const response = await fetch(`/api/visual-workflow/workflows/${state.workflow.id}/validate`, { method: "POST" });
        const data = await response.json();
        if (data.valid) {
            renderRunResult("服务端校验通过。", [{
                title: "服务端检查",
                detail: data.message || "验证通过",
            }]);
            updateWorkflowMeta("检查通过");
            alert("✓ 流程检查通过");
        } else {
            renderRunResult(`服务端校验未通过：${data.message}`, [{
                title: "服务端检查",
                detail: data.message || "验证未通过",
            }]);
            updateWorkflowMeta("检查未通过");
            alert(`✗ 流程检查未通过: ${data.message}`);
        }
    } catch (error) {
        updateWorkflowMeta("检查失败");
        alert(`流程检查失败: ${error.message || error}`);
    }
}

async function saveWorkflow() {
    state.workflow.name = document.getElementById("workflowName")?.value || "未命名流程";
    state.workflow.description = document.getElementById("workflowDescription")?.value || "";

    try {
        const method = state.workflow.id ? "PUT" : "POST";
        const url = state.workflow.id
            ? `/api/visual-workflow/workflows/${state.workflow.id}`
            : "/api/visual-workflow/workflows";

        const response = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: state.workflow.name,
                description: state.workflow.description,
                nodes: state.workflow.nodes,
                edges: state.workflow.edges,
                variables: state.workflow.variables,
            }),
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "保存失败");
        state.workflow = normalizeWorkflow(data);
        state.workflowDirty = false;
        updateWorkflowMeta("已保存");
        renderAll();
        await loadWorkflowLibrary();
        alert("✓ 编排已保存");
    } catch (error) {
        updateWorkflowMeta("保存失败");
        alert(`保存编排失败: ${error.message || error}`);
    }
}

async function executeWorkflow() {
    const inputRaw = document.getElementById("runInput")?.value || "{}";
    let inputData;
    try {
        inputData = JSON.parse(inputRaw);
    } catch (error) {
        alert("测试输入不是合法 JSON");
        return;
    }

    if (!state.workflow.id) {
        await saveWorkflow();
        if (!state.workflow.id) return;
    }

    try {
        updateWorkflowMeta("执行中");
        const response = await fetch(`/api/visual-workflow/workflows/${state.workflow.id}/execute`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ input: inputData }),
        });
        const result = await response.json();
        if (result.success) {
            renderRunResult(JSON.stringify(result.context, null, 2), (result.log || []).map((item) => ({
                title: item.node_label || item.node_type || "节点执行",
                detail: `${item.timestamp || ""} · ${item.node_type || ""}`.trim(),
            })));
            updateWorkflowMeta("执行完成");
        } else {
            renderRunResult(`执行失败\n\n${result.error || "未知错误"}`, (result.log || []).map((item) => ({
                title: item.node_label || item.node_type || "节点执行",
                detail: `${item.timestamp || ""} · ${item.node_type || ""}`.trim(),
            })));
            updateWorkflowMeta("执行失败");
        }
    } catch (error) {
        updateWorkflowMeta("执行失败");
        renderRunResult(`执行失败\n\n${error.message || error}`, []);
        alert(`流程执行失败: ${error.message || error}`);
    }
}

function renderRunResult(outputText, logs) {
    const output = document.getElementById("runOutput");
    const logList = document.getElementById("runLog");
    if (output) output.textContent = outputText;
    if (logList) {
        logList.innerHTML = logs.length
            ? logs.map((log) => `
                <div class="test-log-item">
                    <strong>${escapeHtml(log.title || "执行事件")}</strong>
                    <p>${escapeHtml(log.detail || "")}</p>
                </div>
            `).join("")
            : '<div class="config-empty"><strong>还没有执行日志。</strong><span>运行一次流程后，这里会按节点顺序显示事件轨迹。</span></div>';
    }
}

function normalizeDeployedModels(endpoints) {
    return (Array.isArray(endpoints) ? endpoints : [])
        .filter((endpoint) => endpoint && String(endpoint.endpoint_type || "chat") === "chat")
        .filter((endpoint) => ["running", "starting"].includes(String(endpoint.status || "").toLowerCase()))
        .map((endpoint) => {
            const model = String(endpoint.model_name || endpoint.model_uid || endpoint.endpoint_id || "未命名模型");
            const provider = detectProviderFromDeployment(endpoint);
            return {
                id: String(endpoint.endpoint_id || generateId("deployment")),
                endpointId: String(endpoint.endpoint_id || ""),
                model,
                label: model,
                modelUid: String(endpoint.model_uid || ""),
                provider,
                providerLabel: provider === "azure-openai" ? "Azure OpenAI" : provider === "qwen" ? "Qwen" : provider === "deepseek" ? "DeepSeek" : provider === "anthropic" ? "Anthropic" : provider === "custom" ? "自定义端点" : "OpenAI Compatible",
                baseUrl: String(endpoint.base_url || ""),
                apiKey: String(endpoint.api_key || ""),
                backend: String(endpoint.backend || "manual"),
                backendLabel: endpoint.backend === "vllm" ? "vLLM" : endpoint.backend === "xinference" ? "Xinference" : "OpenAI Compatible",
                status: String(endpoint.status || "unknown"),
                statusLabel: endpoint.status === "running" ? "运行中" : endpoint.status === "starting" ? "启动中" : endpoint.status === "error" ? "异常" : "未知状态",
            };
        })
        .sort((a, b) => {
            const rank = (item) => (item.status === "running" ? 0 : item.status === "starting" ? 1 : 2);
            return rank(a) - rank(b) || a.label.localeCompare(b.label, "zh-CN");
        });
}

function detectProviderFromDeployment(endpoint) {
    const raw = `${endpoint.model_name || ""} ${endpoint.model_uid || ""} ${endpoint.base_url || ""} ${endpoint.backend || ""}`.toLowerCase();
    if (raw.includes("azure")) return "azure-openai";
    if (raw.includes("anthropic") || raw.includes("claude")) return "anthropic";
    if (raw.includes("deepseek")) return "deepseek";
    if (raw.includes("qwen") || raw.includes("tongyi")) return "qwen";
    if (raw.includes("openai") || raw.includes("/v1") || endpoint.backend === "vllm" || endpoint.backend === "xinference") return "openai";
    return "custom";
}

function getEditableLLMNode() {
    const current = state.llmModalNodeId || state.selectedNodeId;
    const node = current ? getNode(current) : null;
    return node?.type === "llm" ? node : null;
}

function createLLMNodeAtCanvasCenter() {
    const typeInfo = state.nodeTypeMap.llm || {};
    const canvas = document.getElementById("canvas");
    const width = canvas?.clientWidth || 960;
    const height = canvas?.clientHeight || 640;
    const defaultConfig = deepClone(typeInfo.default_config || {});
    const outputVar = String(defaultConfig.output_var || "llm_result");
    const node = {
        id: generateId("node"),
        type: "llm",
        label: typeInfo.label || "LLM",
        position: {
            x: Math.max(36, Math.round(width / 2 - 120)),
            y: Math.max(36, Math.round(height / 2 - 78)),
        },
        config: defaultConfig,
        inputs: ["user_query"],
        outputs: [outputVar, `${outputVar}_text`],
    };
    state.workflow.nodes.push(node);
    return node;
}

function applyDeploymentToNode(node, deployment) {
    if (!node || !deployment) return;
    const baseLabel = state.nodeTypeMap.llm?.label || "LLM";
    if (!node.label || node.label === baseLabel || node.label === "LLM") {
        node.label = deployment.label;
    }
    node.config.provider = deployment.provider;
    node.config.model = deployment.model;
    node.config.endpoint_id = deployment.endpointId;
    node.config.base_url = deployment.baseUrl;
    node.config.api_key = deployment.apiKey || node.config.api_key || "";
    node.config.model_uid = deployment.modelUid || "";
    node.config.completion_mode = node.config.completion_mode || "chat";
    if (!Array.isArray(node.inputs) || !node.inputs.length) {
        node.inputs = ["user_query"];
    }
    const outputVar = String(node.config.output_var || "llm_result");
    node.outputs = Array.from(new Set([...(Array.isArray(node.outputs) ? node.outputs : []), outputVar, `${outputVar}_text`]));
}

function activateDeployedLLM(deploymentId) {
    const deployment = state.deployedModels.find((item) => item.id === deploymentId);
    if (!deployment) return;
    const node = getEditableLLMNode() || createLLMNodeAtCanvasCenter();
    applyDeploymentToNode(node, deployment);
    state.selectedNodeId = node.id;
    state.selectedEdgeId = null;
    state.llmModalNodeId = node.id;
    state.editorTabs[node.id] = state.editorTabs[node.id] || "deployment";
    markWorkflowDirty();
    renderAll();
    focusNodeInCanvas(node.id);
    updateWorkflowMeta(`已绑定 ${deployment.label}`);
}

function applyLLMPreset(nodeId, presetId) {
    const node = getNode(nodeId);
    const preset = llmPresets.find((item) => item.id === presetId);
    if (!node || node.type !== "llm" || !preset) return;
    Object.assign(node.config, preset.config);
    if (preset.config.response_format !== "json" && !node.config.json_schema) {
        node.config.json_schema = "";
    }
    markWorkflowDirty();
    renderAll();
    updateWorkflowMeta(`已套用 ${preset.name}`);
}

function normalizeWorkflow(raw) {
    return {
        id: raw.id || null,
        name: raw.name || "",
        description: raw.description || "",
        nodes: Array.isArray(raw.nodes) ? raw.nodes.map(normalizeNode) : [],
        edges: Array.isArray(raw.edges) ? raw.edges.map(normalizeEdge) : [],
        variables: normalizeVariables(raw.variables || {}),
    };
}

function normalizeNode(node) {
    const typeInfo = state.nodeTypeMap[node.type] || {};
    return {
        id: node.id || generateId("node"),
        type: node.type,
        label: node.label || typeInfo.label || node.type,
        position: {
            x: Number(node.position?.x || 80),
            y: Number(node.position?.y || 80),
        },
        config: {
            ...deepClone(typeInfo.default_config || {}),
            ...(node.config || {}),
        },
        inputs: Array.isArray(node.inputs) ? node.inputs : [],
        outputs: Array.isArray(node.outputs) ? node.outputs : [],
    };
}

function normalizeEdge(edge) {
    return {
        id: edge.id || generateId("edge"),
        source: edge.source,
        target: edge.target,
        label: edge.label || "",
        condition: edge.condition || "",
    };
}

function getNode(nodeId) {
    return state.workflow.nodes.find((node) => node.id === nodeId);
}

function getEdge(edgeId) {
    return state.workflow.edges.find((edge) => edge.id === edgeId);
}

function splitList(value) {
    return String(value || "")
        .split(/[,\n]/)
        .map((item) => item.trim())
        .filter(Boolean);
}

function deepClone(value) {
    return JSON.parse(JSON.stringify(value));
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function generateId(prefix) {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

window.loadTemplateById = loadTemplateById;
window.clearCanvas = clearCanvas;
window.newWorkflow = newWorkflow;
window.autoLayout = autoLayout;
window.saveWorkflow = saveWorkflow;
window.executeWorkflow = executeWorkflow;
window.validateWorkflow = validateWorkflow;
window.closeConfigPanel = closeConfigPanel;
window.updateNodeLabel = updateNodeLabel;
window.updateNodeConfig = updateNodeConfig;
window.updateNodeCheckbox = updateNodeCheckbox;
window.setNodeEditorTab = setNodeEditorTab;
window.insertVariableToken = insertVariableToken;
window.openLLMConfigModal = openLLMConfigModal;
window.closeLLMConfigModal = closeLLMConfigModal;
window.focusCurrentLLMNode = focusCurrentLLMNode;
window.updateNodeIO = updateNodeIO;
window.deleteNode = deleteNode;
window.duplicateNode = duplicateNode;
window.focusNodeInCanvas = focusNodeInCanvas;
window.updateEdgeField = updateEdgeField;
window.deleteEdge = deleteEdge;
window.selectNode = selectNode;
window.selectEdge = selectEdge;
window.openWorkflow = openWorkflow;
window.removeWorkflowFromLibrary = removeWorkflowFromLibrary;
window.loadStarterFlow = loadStarterFlow;
window.loadWorkflowScenario = loadWorkflowScenario;
window.triggerImportWorkflow = triggerImportWorkflow;
window.exportWorkflow = exportWorkflow;
window.applyRunPreset = applyRunPreset;
window.activateDeployedLLM = activateDeployedLLM;
window.applyLLMPreset = applyLLMPreset;
