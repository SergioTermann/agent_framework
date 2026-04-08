/**
 * 可视化工作流编排 JavaScript
 */

// 全局状态
let workflow = {
    id: null,
    name: '',
    nodes: [],
    edges: [],
    variables: {}
};

let selectedNode = null;
let isDragging = false;
let dragOffset = { x: 0, y: 0 };
let isConnecting = false;
let connectionStart = null;
let tempLine = null;
let nodeTypes = [];

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    loadNodeTypes();
    loadTemplates();
    initCanvas();
    initPalette();
});

// 加载节点类型
async function loadNodeTypes() {
    try {
        const response = await fetch('/api/visual-workflow/node-types');
        const data = await response.json();
        nodeTypes = data.node_types;
        renderNodePalette();
    } catch (error) {
        console.error('加载节点类型失败:', error);
    }
}

// 渲染节点面板
function renderNodePalette() {
    const palette = document.getElementById('nodePalette');
    palette.innerHTML = '';

    nodeTypes.forEach(type => {
        const item = document.createElement('div');
        item.className = 'node-item';
        item.draggable = true;
        item.dataset.nodeType = type.type;
        item.innerHTML = `
            <div class="node-icon">${type.icon}</div>
            <div>${type.label}</div>
        `;

        item.addEventListener('dragstart', handlePaletteDragStart);
        palette.appendChild(item);
    });
}

// 加载模板
async function loadTemplates() {
    try {
        const response = await fetch('/api/visual-workflow/templates');
        const data = await response.json();
        renderTemplates(data.templates);
    } catch (error) {
        console.error('加载模板失败:', error);
    }
}

// 渲染模板列表
function renderTemplates(templates) {
    const list = document.getElementById('templateList');
    list.innerHTML = '';

    templates.forEach(template => {
        const item = document.createElement('div');
        item.className = 'node-item';
        item.style.gridColumn = '1 / -1';
        item.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 4px;">${template.name}</div>
            <div style="font-size: 10px; color: #7f8c8d;">${template.description}</div>
        `;
        item.onclick = () => loadTemplate(template);
        list.appendChild(item);
    });
}

// 加载模板
function loadTemplate(template) {
    workflow.nodes = template.nodes.map(n => ({...n, id: generateId()}));
    workflow.edges = template.edges.map(e => ({
        ...e,
        id: generateId(),
        source: workflow.nodes.find((_, i) => i === template.nodes.findIndex(n => n.id === e.source))?.id,
        target: workflow.nodes.find((_, i) => i === template.nodes.findIndex(n => n.id === e.target))?.id
    }));
    renderWorkflow();
}

// 初始化画布
function initCanvas() {
    const canvas = document.getElementById('canvas');

    canvas.addEventListener('dragover', handleCanvasDragOver);
    canvas.addEventListener('drop', handleCanvasDrop);
    canvas.addEventListener('click', handleCanvasClick);
}

// 初始化节点面板拖拽
function initPalette() {
    const items = document.querySelectorAll('.node-item');
    items.forEach(item => {
        item.addEventListener('dragstart', handlePaletteDragStart);
    });
}

// 面板拖拽开始
function handlePaletteDragStart(e) {
    e.dataTransfer.setData('nodeType', e.currentTarget.dataset.nodeType);
}

// 画布拖拽悬停
function handleCanvasDragOver(e) {
    e.preventDefault();
}

// 画布放置
function handleCanvasDrop(e) {
    e.preventDefault();
    const nodeType = e.dataTransfer.getData('nodeType');
    if (!nodeType) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    createNode(nodeType, x, y);
}

// 创建节点
function createNode(type, x, y) {
    const typeInfo = nodeTypes.find(t => t.type === type);
    if (!typeInfo) return;

    const node = {
        id: generateId(),
        type: type,
        label: typeInfo.label,
        position: { x, y },
        config: {},
        inputs: [],
        outputs: []
    };

    workflow.nodes.push(node);
    renderWorkflow();
}

// 渲染工作流
function renderWorkflow() {
    const content = document.getElementById('canvasContent');
    content.innerHTML = '';

    // 渲染节点
    workflow.nodes.forEach(node => {
        const nodeEl = createNodeElement(node);
        content.appendChild(nodeEl);
    });

    // 渲染连接线
    renderConnections();
}

// 创建节点元素
function createNodeElement(node) {
    const typeInfo = nodeTypes.find(t => t.type === node.type);
    const div = document.createElement('div');
    div.className = 'workflow-node';
    div.dataset.nodeId = node.id;
    div.style.left = node.position.x + 'px';
    div.style.top = node.position.y + 'px';

    div.innerHTML = `
        <div class="node-header">
            <div class="node-icon-large">${typeInfo?.icon || '📦'}</div>
            <div>
                <div class="node-label">${node.label}</div>
                <div class="node-type">${typeInfo?.label || node.type}</div>
            </div>
        </div>
        <div class="node-ports">
            <div class="node-port input-port" data-port="input"></div>
            <div class="node-port output-port" data-port="output"></div>
        </div>
    `;

    // 节点拖拽
    div.addEventListener('mousedown', (e) => handleNodeMouseDown(e, node));

    // 节点点击
    div.addEventListener('click', (e) => {
        e.stopPropagation();
        selectNode(node);
    });

    // 端口连接
    const ports = div.querySelectorAll('.node-port');
    ports.forEach(port => {
        port.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            handlePortMouseDown(e, node, port.dataset.port);
        });
    });

    return div;
}

// 节点鼠标按下
function handleNodeMouseDown(e, node) {
    if (e.target.classList.contains('node-port')) return;

    isDragging = true;
    selectedNode = node;

    const nodeEl = e.currentTarget;
    const rect = nodeEl.getBoundingClientRect();
    dragOffset.x = e.clientX - rect.left;
    dragOffset.y = e.clientY - rect.top;

    document.addEventListener('mousemove', handleNodeMouseMove);
    document.addEventListener('mouseup', handleNodeMouseUp);
}

// 节点鼠标移动
function handleNodeMouseMove(e) {
    if (!isDragging || !selectedNode) return;

    const canvas = document.getElementById('canvas');
    const rect = canvas.getBoundingClientRect();

    selectedNode.position.x = e.clientX - rect.left - dragOffset.x;
    selectedNode.position.y = e.clientY - rect.top - dragOffset.y;

    renderWorkflow();
}

// 节点鼠标释放
function handleNodeMouseUp() {
    isDragging = false;
    document.removeEventListener('mousemove', handleNodeMouseMove);
    document.removeEventListener('mouseup', handleNodeMouseUp);
}

// 端口鼠标按下
function handlePortMouseDown(e, node, portType) {
    if (portType === 'input') return; // 只能从输出端口开始连接

    isConnecting = true;
    connectionStart = { node, port: portType };

    document.addEventListener('mousemove', handleConnectionMouseMove);
    document.addEventListener('mouseup', handleConnectionMouseUp);
}

// 连接鼠标移动
function handleConnectionMouseMove(e) {
    if (!isConnecting) return;

    const svg = document.getElementById('connectionsSvg');
    const rect = svg.getBoundingClientRect();

    // 移除临时线
    if (tempLine) {
        tempLine.remove();
    }

    // 创建临时线
    const startNode = document.querySelector(`[data-node-id="${connectionStart.node.id}"]`);
    const startPort = startNode.querySelector('.output-port');
    const startRect = startPort.getBoundingClientRect();

    const startX = startRect.left + startRect.width / 2 - rect.left;
    const startY = startRect.top + startRect.height / 2 - rect.top;
    const endX = e.clientX - rect.left;
    const endY = e.clientY - rect.top;

    tempLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    tempLine.setAttribute('x1', startX);
    tempLine.setAttribute('y1', startY);
    tempLine.setAttribute('x2', endX);
    tempLine.setAttribute('y2', endY);
    tempLine.setAttribute('stroke', '#58a6ff');
    tempLine.setAttribute('stroke-width', '2');
    tempLine.setAttribute('opacity', '0.5');

    svg.appendChild(tempLine);
}

// 连接鼠标释放
function handleConnectionMouseUp(e) {
    if (!isConnecting) return;

    // 检查是否释放在输入端口上
    const target = e.target;
    if (target.classList.contains('node-port') && target.dataset.port === 'input') {
        const targetNodeEl = target.closest('.workflow-node');
        const targetNode = workflow.nodes.find(n => n.id === targetNodeEl.dataset.nodeId);

        if (targetNode && targetNode.id !== connectionStart.node.id) {
            createEdge(connectionStart.node.id, targetNode.id);
        }
    }

    // 清理
    if (tempLine) {
        tempLine.remove();
        tempLine = null;
    }

    isConnecting = false;
    connectionStart = null;

    document.removeEventListener('mousemove', handleConnectionMouseMove);
    document.removeEventListener('mouseup', handleConnectionMouseUp);
}

// 创建连接
function createEdge(sourceId, targetId) {
    const edge = {
        id: generateId(),
        source: sourceId,
        target: targetId,
        label: ''
    };

    workflow.edges.push(edge);
    renderWorkflow();
}

// 渲染连接线
function renderConnections() {
    const svg = document.getElementById('connectionsSvg');
    svg.innerHTML = '';

    workflow.edges.forEach(edge => {
        const sourceNode = document.querySelector(`[data-node-id="${edge.source}"]`);
        const targetNode = document.querySelector(`[data-node-id="${edge.target}"]`);

        if (!sourceNode || !targetNode) return;

        const sourcePort = sourceNode.querySelector('.output-port');
        const targetPort = targetNode.querySelector('.input-port');

        const svgRect = svg.getBoundingClientRect();
        const sourceRect = sourcePort.getBoundingClientRect();
        const targetRect = targetPort.getBoundingClientRect();

        const x1 = sourceRect.left + sourceRect.width / 2 - svgRect.left;
        const y1 = sourceRect.top + sourceRect.height / 2 - svgRect.top;
        const x2 = targetRect.left + targetRect.width / 2 - svgRect.left;
        const y2 = targetRect.top + targetRect.height / 2 - svgRect.top;

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('stroke', '#58a6ff');
        line.setAttribute('stroke-width', '2');

        svg.appendChild(line);
    });
}

// 选择节点
function selectNode(node) {
    selectedNode = node;

    // 更新UI
    document.querySelectorAll('.workflow-node').forEach(el => {
        el.classList.remove('selected');
    });
    document.querySelector(`[data-node-id="${node.id}"]`)?.classList.add('selected');

    // 显示配置面板
    showConfigPanel(node);
}

// 显示配置面板
function showConfigPanel(node) {
    const panel = document.getElementById('configPanel');
    const content = document.getElementById('configContent');

    const typeInfo = nodeTypes.find(t => t.type === node.type);

    let html = `
        <div class="form-group">
            <label class="form-label">节点名称</label>
            <input type="text" class="form-input" value="${node.label}"
                   onchange="updateNodeLabel('${node.id}', this.value)">
        </div>
    `;

    // 根据节点类型添加配置项
    if (node.type === 'agent') {
        html += `
            <div class="form-group">
                <label class="form-label">Agent 类型</label>
                <select class="form-input" onchange="updateNodeConfig('${node.id}', 'agent_type', this.value)">
                    <option value="general" ${node.config.agent_type === 'general' ? 'selected' : ''}>通用</option>
                    <option value="code" ${node.config.agent_type === 'code' ? 'selected' : ''}>代码</option>
                    <option value="analysis" ${node.config.agent_type === 'analysis' ? 'selected' : ''}>分析</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">提示词</label>
                <textarea class="form-input form-textarea"
                          onchange="updateNodeConfig('${node.id}', 'prompt', this.value)">${node.config.prompt || ''}</textarea>
            </div>
            <div class="form-group">
                <label class="form-label">输出变量</label>
                <input type="text" class="form-input" value="${node.config.output_var || 'result'}"
                       onchange="updateNodeConfig('${node.id}', 'output_var', this.value)">
            </div>
        `;
    } else if (node.type === 'condition') {
        html += `
            <div class="form-group">
                <label class="form-label">条件表达式</label>
                <input type="text" class="form-input" value="${node.config.condition || ''}"
                       onchange="updateNodeConfig('${node.id}', 'condition', this.value)">
            </div>
        `;
    }

    html += `
        <div class="form-group">
            <button class="btn" style="width: 100%; background: rgba(239, 68, 68, 0.2); border-color: rgba(239, 68, 68, 0.5);"
                    onclick="deleteNode('${node.id}')">
                <i class="fas fa-trash"></i> 移除这个节点
            </button>
        </div>
    `;

    content.innerHTML = html;
    panel.classList.add('active');
}

// 关闭配置面板
function closeConfigPanel() {
    document.getElementById('configPanel').classList.remove('active');
    selectedNode = null;
    document.querySelectorAll('.workflow-node').forEach(el => {
        el.classList.remove('selected');
    });
}

// 更新节点标签
function updateNodeLabel(nodeId, label) {
    const node = workflow.nodes.find(n => n.id === nodeId);
    if (node) {
        node.label = label;
        renderWorkflow();
    }
}

// 更新节点配置
function updateNodeConfig(nodeId, key, value) {
    const node = workflow.nodes.find(n => n.id === nodeId);
    if (node) {
        node.config[key] = value;
    }
}

// 删除节点
function deleteNode(nodeId) {
    workflow.nodes = workflow.nodes.filter(n => n.id !== nodeId);
    workflow.edges = workflow.edges.filter(e => e.source !== nodeId && e.target !== nodeId);
    closeConfigPanel();
    renderWorkflow();
}

// 画布点击
function handleCanvasClick(e) {
    if (e.target.id === 'canvas' || e.target.id === 'canvasContent') {
        closeConfigPanel();
    }
}

// 清空画布
function clearCanvas() {
    if (confirm('确定要清空整张画布吗？当前编排内容会被移除。')) {
        workflow.nodes = [];
        workflow.edges = [];
        renderWorkflow();
    }
}

// 验证工作流
async function validateWorkflow() {
    if (!workflow.id) {
        alert('先保存这条流程，再做检查');
        return;
    }

    try {
        const response = await fetch(`/api/visual-workflow/workflows/${workflow.id}/validate`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.valid) {
            alert('✓ 流程检查通过，可以继续执行或复用');
        } else {
            alert('✗ 流程检查未通过: ' + data.message);
        }
    } catch (error) {
        alert('流程检查失败: ' + error.message);
    }
}

// 保存工作流
async function saveWorkflow() {
    const name = document.getElementById('workflowName').value || '未命名流程';

    try {
        const method = workflow.id ? 'PUT' : 'POST';
        const url = workflow.id
            ? `/api/visual-workflow/workflows/${workflow.id}`
            : '/api/visual-workflow/workflows';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                nodes: workflow.nodes,
                edges: workflow.edges,
                variables: workflow.variables
            })
        });

        const data = await response.json();
        workflow.id = data.id;

        alert('✓ 编排已保存，可以继续补节点或直接运行');
    } catch (error) {
        alert('保存编排失败: ' + error.message);
    }
}

// 执行工作流
async function executeWorkflow() {
    if (!workflow.id) {
        alert('先保存这条流程，再执行');
        return;
    }

    const input = prompt('输入这次运行要用的初始数据（JSON 格式）:', '{}');
    if (!input) return;

    try {
        const inputData = JSON.parse(input);

        const response = await fetch(`/api/visual-workflow/workflows/${workflow.id}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input: inputData })
        });

        const result = await response.json();

        if (result.success) {
            alert('✓ 流程运行完成\n\n结果: ' + JSON.stringify(result.context, null, 2));
        } else {
            alert('✗ 流程运行失败: ' + result.error);
        }
    } catch (error) {
        alert('流程执行失败: ' + error.message);
    }
}

// 生成ID
function generateId() {
    return 'node_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}
