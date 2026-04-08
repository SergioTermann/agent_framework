"""
Web UI - Agent Framework 交互式界面
基于 Flask + WebSocket 实现实时流式输出
"""

import asyncio
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, send_from_directory
from flask_socketio import SocketIO, emit

from agent_framework.agent import AgentBuilder
from agent_framework.agent.session import AgentSession as _BaseAgentSession
from agent_framework.agent.thread import latest_assistant_message
from agent_framework.core.harness_health import (
    build_liveness_report,
    build_readiness_report,
    readiness_http_status,
)
from agent_framework.memory.tools import MemoryToolsRegistry
from agent_framework.memory.system import get_memory_manager, get_file_memory_layer
from agent_framework.core.openapi_docs import register_openapi_routes
from agent_framework.core.system_status import collect_system_status
from agent_framework.platform.extension_system import get_extension_system

# API Blueprints
from agent_framework.api.conversation_api import conversation_bp
from agent_framework.api.api_key_api import api_key_bp
from agent_framework.api.monitoring_api import monitoring_bp
from agent_framework.api.auth_api import auth_bp, user_bp, org_bp
from agent_framework.api.application_api import app_bp
from agent_framework.api.prompt_api import prompt_bp
from agent_framework.api.document_api import document_bp
from agent_framework.api.publish_api import publish_bp
from agent_framework.api.finetune_api import finetune_bp
from agent_framework.api.unified_chat_api import unified_bp
from agent_framework.api.causal_chain_api import causal_chain_bp
from agent_framework.api.causal_reasoning_api import causal_reasoning_bp
from agent_framework.api.config_presets_api import config_presets_bp
from agent_framework.api.memory_api import memory_bp, register_memory_system
from agent_framework.api.advanced_reasoning_api import reasoning_bp
from agent_framework.api.extension_api import extension_bp
from agent_framework.api.multi_agent_api import multi_agent_bp
from agent_framework.api.visual_workflow_api import visual_workflow_bp
from agent_framework.api.knowledge_api import knowledge_bp
from agent_framework.api.plugin_market_api import plugin_market_bp
from agent_framework.api.multimodal_api import multimodal_bp
from agent_framework.api.collaboration_api import collaboration_bp, register_collaboration_events
from agent_framework.api.ab_testing_api import ab_testing_bp
from agent_framework.api.workflow_advanced_api import workflow_advanced_bp
from agent_framework.api.performance_api import performance_bp
from agent_framework.api.async_task_api import async_task_bp
from agent_framework.api.logging_api import logging_bp
from agent_framework.api.webhook_api import webhook_bp, create_webhook_receiver
from agent_framework.api.http_request_api import http_request_bp
from agent_framework.api.code_snippet_api import snippet_bp
from agent_framework.api.ontology_api import ontology_api
from agent_framework.api.rl_api import rl_bp
from agent_framework.api.llm_rlhf_api import llm_rlhf_bp
from agent_framework.api.pipeline_api import pipeline_bp
from agent_framework.api.tool_api import tool_bp
from agent_framework.api.skill_creator_api import skill_creator_bp
from agent_framework.gateway import gateway_bp, register_gateway_socketio
from agent_framework.infra.monitoring import MonitoringManager, MonitoringStorage
from agent_framework.tools import TOOLSET_PRESETS, discover_tools
from agent_framework.vector_db.knowledge_base import knowledge_manager

# 统一配置
import os as _os
from agent_framework.core.config import get_config as _get_platform_config
_platform_cfg = _get_platform_config()

# When running behind Go Gateway, INTERNAL_PORT overrides the configured port
# so Flask listens on a different port (default 5001) while Go handles :5000.
_internal_port = _os.environ.get("INTERNAL_PORT")
if _internal_port:
    _platform_cfg.server.port = int(_internal_port)

logger = logging.getLogger(__name__)

MODULE_WORKSPACES = {
    "weather-siting": {
        "slug": "weather-siting",
        "index": "01",
        "name": "气象选址",
        "tagline": "风资源评估与候选站址筛选",
        "description": "面向风资源分析、测风数据整理、候选区域初筛和选址建议输出，先把气象与地理信息拉到一个统一工作台。",
        "status": "模块工作台",
        "primary_label": "进入知识与数据",
        "primary_href": "/knowledge",
        "secondary_label": "查看分析面板",
        "secondary_href": "/analytics",
        "scenes": [
            "风资源数据汇总",
            "候选站址初筛",
            "测风资料比对",
            "选址建议输出",
        ],
        "capabilities": [
            {"title": "数据接入", "desc": "整合气象观测、测风塔、历史功率和外部资料。"},
            {"title": "选址分析", "desc": "围绕风速、地形、道路和接入条件进行站址筛选。"},
            {"title": "报告输出", "desc": "把阶段性分析沉淀成评估摘要与选址建议。"},
        ],
    },
    "smart-workorder": {
        "slug": "smart-workorder",
        "index": "02",
        "name": "智能工单",
        "tagline": "工单生成、流转与闭环追踪",
        "description": "面向缺陷上报、派单执行、处理回执和闭环追踪，集中处理工单创建、流转和闭环记录。",
        "status": "在线业务模块",
        "primary_label": "进入工单处理台",
        "primary_href": "/workflow",
        "secondary_label": "查看工单日志",
        "secondary_href": "/logs",
        "scenes": [
            "异常自动建单",
            "处理流程分派",
            "执行进度追踪",
            "工单闭环归档",
        ],
        "capabilities": [
            {"title": "建单入口", "desc": "按设备异常、人工上报或批量任务创建工单。"},
            {"title": "流程编排", "desc": "把派单、审批、复核和归档串成标准流程。"},
            {"title": "工单视图", "desc": "在统一面板里查看状态、负责人和处理结果。"},
        ],
    },
    "guide-assistant": {
        "slug": "guide-assistant",
        "index": "03",
        "name": "智导助手",
        "tagline": "故障问答与现场辅助决策",
        "description": "这是主业务入口，围绕知识问答、故障诊断、操作引导和经验复用展开。",
        "status": "已接入现有能力",
        "primary_label": "进入业务助手",
        "primary_href": "/maintenance-assistant",
        "secondary_label": "进入开发版助手",
        "secondary_href": "/developer/assistant",
        "scenes": [
            "故障诊断问答",
            "现场处置建议",
            "知识增强检索",
            "辅助决策输出",
        ],
        "capabilities": [
            {"title": "对话入口", "desc": "直接进入现有智导助手页面发起问题。"},
            {"title": "知识增强", "desc": "结合知识库与记忆系统提升回答质量。"},
            {"title": "开发调试", "desc": "需要调 prompt 和参数时切到开发版助手。"},
        ],
    },
    "smart-guard": {
        "slug": "smart-guard",
        "index": "04",
        "name": "智能值守",
        "tagline": "告警联动与运行监测",
        "description": "面向值班巡检、告警汇总、异常态势和重点设备监控，把值守信息聚合成统一面板。",
        "status": "模块工作台",
        "primary_label": "进入平台总览",
        "primary_href": "/dashboard",
        "secondary_label": "查看性能监控",
        "secondary_href": "/performance",
        "scenes": [
            "值班态势总览",
            "告警分级处理",
            "巡检任务跟踪",
            "重点设备监控",
        ],
        "capabilities": [
            {"title": "值守面板", "desc": "按班次、区域和设备维度查看当前值守态势。"},
            {"title": "告警联动", "desc": "把告警汇总、排序和处置建议放在同一界面。"},
            {"title": "巡检跟踪", "desc": "把巡检任务、完成度和异常记录集中呈现。"},
        ],
    },
    "power-trading": {
        "slug": "power-trading",
        "index": "05",
        "name": "电力交易",
        "tagline": "报价分析与交易辅助",
        "description": "面向交易数据分析、报价建议、市场研判和经营辅助，集中查看行情、报价和经营指标。",
        "status": "在线业务模块",
        "primary_label": "进入交易分析台",
        "primary_href": "/analytics",
        "secondary_label": "查看运行状态",
        "secondary_href": "/system-status",
        "scenes": [
            "交易数据汇总",
            "报价辅助分析",
            "市场趋势判断",
            "经营指标跟踪",
        ],
        "capabilities": [
            {"title": "交易总览", "desc": "把价格、负荷和成交数据集中到业务入口。"},
            {"title": "报价建议", "desc": "围绕历史数据和当前状态生成分析建议。"},
            {"title": "经营视图", "desc": "为交易、运营和管理层提供统一的观察口。"},
        ],
    },
    "smart-office": {
        "slug": "smart-office",
        "index": "06",
        "name": "智慧办公",
        "tagline": "协同办公与通用助手",
        "description": "面向流程协同、文档整理、通用事务和部门办公助手，让办公场景也有独立模块入口。",
        "status": "模块工作台",
        "primary_label": "进入应用中心",
        "primary_href": "/apps",
        "secondary_label": "查看代码片段",
        "secondary_href": "/code-snippets",
        "scenes": [
            "会议纪要整理",
            "待办任务汇总",
            "文档抽取生成",
            "部门协同助手",
        ],
        "capabilities": [
            {"title": "办公入口", "desc": "收纳日常办公场景下的通用 AI 助手能力。"},
            {"title": "应用连接", "desc": "通过应用中心接入更多办公型工具和页面。"},
            {"title": "文档处理", "desc": "围绕摘要、整理和知识沉淀做统一入口。"},
        ],
    },
}


MODULE_FRONTENDS = {
    "weather-siting": {
        "route": "/modules/weather-siting/app",
        "headline": "气象选址前端工作台",
        "summary": "把风资源、候选区域和接入条件收进一个前端页面，先完成选址分析入口、结果面板和候选站址清单。",
        "metrics": [
            {"label": "候选区域", "value": "12", "note": "待评估地块"},
            {"label": "已筛站址", "value": "4", "note": "进入复核"},
            {"label": "气象数据", "value": "18 份", "note": "已接入资料"},
        ],
        "fields": [
            {"label": "项目名称", "type": "text", "name": "project", "placeholder": "例如：华北沿海风场一期"},
            {"label": "区域范围", "type": "text", "name": "region", "placeholder": "例如：河北沿海 80km 范围"},
            {"label": "分析目标", "type": "textarea", "name": "goal", "placeholder": "说明本次要完成的选址判断、对比或报告任务"},
        ],
        "quick_actions": ["风资源初筛", "候选站址对比", "接入条件核查"],
        "result_title": "选址分析输出",
        "result_lines": [
            "优先关注年平均风速、极端天气和道路接入约束。",
            "适合先形成候选站址清单，再进入人工复核。",
            "结果页后续可继续接地图、测风和外部数据接口。",
        ],
        "board_title": "候选站址清单",
        "board_columns": ["站址", "区域", "状态", "说明"],
        "board_rows": [
            ["A-01", "沿海北段", "待复核", "风资源好，接入条件待确认"],
            ["A-02", "沿海中段", "推荐", "道路条件较好，测风资料完整"],
            ["B-01", "丘陵西侧", "观察", "风速稳定，但地形复杂"],
        ],
    },
    "smart-workorder": {
        "route": "/modules/smart-workorder/app",
        "headline": "智能工单处理台",
        "summary": "集中完成建单、派单、处理和闭环追踪，页面内直接查看工单状态、处理进度和记录列表。",
        "metrics": [
            {"label": "待处理工单", "value": "9", "note": "需要分派"},
            {"label": "处理中", "value": "14", "note": "现场执行中"},
            {"label": "已闭环", "value": "126", "note": "本月累计"},
        ],
        "fields": [
            {"label": "设备名称", "type": "text", "name": "asset", "placeholder": "例如：3# 风机变桨系统"},
            {"label": "异常级别", "type": "text", "name": "severity", "placeholder": "例如：高 / 中 / 低"},
            {"label": "问题描述", "type": "textarea", "name": "issue", "placeholder": "描述故障现象、影响范围和当前处理诉求"},
        ],
        "quick_actions": ["生成处理工单", "派发检修任务", "查看闭环记录"],
        "result_title": "工单处理建议",
        "result_lines": [
            "支持根据异常描述生成工单标题、处理建议和派单信息。",
            "可继续补充责任人、审批节点和消息通知等流程配置。",
            "页面内已经保留工单录入、状态查看和闭环跟踪入口。",
        ],
        "board_title": "工单队列",
        "board_columns": ["工单号", "设备", "状态", "负责人"],
        "board_rows": [
            ["WO-24031", "3# 风机", "待派单", "未分配"],
            ["WO-24028", "升压站保护柜", "处理中", "王工"],
            ["WO-24015", "箱变温控", "待复核", "李工"],
        ],
    },
    "smart-guard": {
        "route": "/modules/smart-guard/app",
        "headline": "智能值守前端工作台",
        "summary": "把值守态势、告警优先级和巡检任务集中成统一值班面板，先补值守前端页面和告警看板。",
        "metrics": [
            {"label": "实时告警", "value": "6", "note": "需重点关注"},
            {"label": "待巡检点位", "value": "11", "note": "本班次"},
            {"label": "在线设备", "value": "98%", "note": "设备在线率"},
        ],
        "fields": [
            {"label": "值守班次", "type": "text", "name": "shift", "placeholder": "例如：白班 / 夜班"},
            {"label": "关注设备", "type": "text", "name": "focus", "placeholder": "例如：升压站、风机群、箱变"},
            {"label": "值守目标", "type": "textarea", "name": "goal", "placeholder": "输入本班次重点关注问题、告警或巡检安排"},
        ],
        "quick_actions": ["汇总当前告警", "生成值守摘要", "安排巡检任务"],
        "result_title": "值守建议输出",
        "result_lines": [
            "优先按影响范围和设备等级给告警排序。",
            "适合把值守摘要、巡检计划和处置记录放在一页。",
            "后续可继续接系统状态和实时告警接口。",
        ],
        "board_title": "值守看板",
        "board_columns": ["对象", "告警", "状态", "动作"],
        "board_rows": [
            ["1# 风机群", "偏航异常", "关注", "安排现场巡检"],
            ["升压站", "温度波动", "处理中", "等待复测"],
            ["箱变区", "通信抖动", "观察", "继续监视"],
        ],
    },
    "power-trading": {
        "route": "/modules/power-trading/app",
        "headline": "电力交易分析台",
        "summary": "集中查看交易分析入口、报价建议面板和经营数据看板，用一页完成主要交易判断。",
        "metrics": [
            {"label": "今日均价", "value": "428", "note": "元/MWh"},
            {"label": "预测负荷", "value": "86%", "note": "达成率"},
            {"label": "报价方案", "value": "3", "note": "待选择"},
        ],
        "fields": [
            {"label": "交易周期", "type": "text", "name": "period", "placeholder": "例如：明日现货 / 本周中长期"},
            {"label": "关注市场", "type": "text", "name": "market", "placeholder": "例如：华北现货市场"},
            {"label": "分析需求", "type": "textarea", "name": "goal", "placeholder": "输入报价、趋势、风险或收益分析需求"},
        ],
        "quick_actions": ["生成报价建议", "查看市场趋势", "汇总经营指标"],
        "result_title": "交易分析建议",
        "result_lines": [
            "适合集中查看报价建议、风险提示和市场摘要。",
            "可继续接入实时行情、成交结果和负荷预测数据。",
            "页面内已预留交易输入、结果摘要和经营看板区域。",
        ],
        "board_title": "交易看板",
        "board_columns": ["市场", "指标", "状态", "说明"],
        "board_rows": [
            ["日前交易", "价格波动", "关注", "建议观察午后区间"],
            ["现货交易", "负荷偏差", "处理中", "需要修正预测"],
            ["中长期", "合约收益", "稳定", "按计划执行"],
        ],
    },
    "smart-office": {
        "route": "/modules/smart-office/app",
        "headline": "智慧办公前端工作台",
        "summary": "把会议纪要、待办汇总、文档处理和协同事务做成一个统一办公入口，先补齐前端页面。",
        "metrics": [
            {"label": "今日待办", "value": "17", "note": "待整理事项"},
            {"label": "会议纪要", "value": "5", "note": "待生成摘要"},
            {"label": "协同任务", "value": "8", "note": "跨部门事项"},
        ],
        "fields": [
            {"label": "办公主题", "type": "text", "name": "topic", "placeholder": "例如：周例会整理 / 任务分派"},
            {"label": "参与部门", "type": "text", "name": "team", "placeholder": "例如：运维部、交易部、综合部"},
            {"label": "处理需求", "type": "textarea", "name": "goal", "placeholder": "输入纪要整理、任务提炼或文档生成需求"},
        ],
        "quick_actions": ["生成会议纪要", "整理待办事项", "汇总部门协同"],
        "result_title": "办公助手输出",
        "result_lines": [
            "适合沉淀会议纪要、待办清单和协同记录。",
            "后续可继续连接知识库、应用中心和文档接口。",
            "当前先完成独立办公前端入口。",
        ],
        "board_title": "办公面板",
        "board_columns": ["事项", "部门", "状态", "说明"],
        "board_rows": [
            ["周例会纪要", "综合部", "待整理", "下午 4 点前完成"],
            ["运维待办汇总", "运维部", "处理中", "需补充责任人"],
            ["交易简报", "交易部", "待确认", "等待最新数据"],
        ],
    },
}

for _slug, _page in MODULE_FRONTENDS.items():
    if _slug in MODULE_WORKSPACES:
        MODULE_WORKSPACES[_slug]["primary_href"] = _page["route"]


def _socketio_kwargs() -> dict:
    kwargs = {}
    if _platform_cfg.server.cors_allowed_origins:
        kwargs["cors_allowed_origins"] = _platform_cfg.server.cors_allowed_origins
    return kwargs

_PKG_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PKG_ROOT.parent.parent
_ENTRY_WEB_HTML = _REPO_ROOT / "web.html"


def _get_knowledge_base_examples():
    try:
        return [
            {"id": kb.id, "name": kb.name or kb.id}
            for kb in knowledge_manager.list_knowledge_bases()
        ]
    except Exception:
        return []


def _get_agent_tool_ui_options():
    try:
        toolset_presets = list(TOOLSET_PRESETS.keys())
    except Exception:
        toolset_presets = []
    try:
        available_tool_names = sorted({spec.name for spec in discover_tools()})
    except Exception:
        available_tool_names = []
    return {
        "toolset_presets": toolset_presets,
        "available_tool_names": available_tool_names,
    }

# 批量注册 API Blueprints
BLUEPRINTS = [
    conversation_bp, api_key_bp, monitoring_bp,
    auth_bp, user_bp, org_bp, app_bp, prompt_bp, document_bp, publish_bp,
    finetune_bp, causal_chain_bp, causal_reasoning_bp, config_presets_bp,
    reasoning_bp, extension_bp, multi_agent_bp, visual_workflow_bp,
    knowledge_bp, plugin_market_bp, multimodal_bp, collaboration_bp,
    ab_testing_bp, workflow_advanced_bp, performance_bp, async_task_bp,
    logging_bp, webhook_bp, http_request_bp, snippet_bp, ontology_api,
    rl_bp,
    llm_rlhf_bp,
    pipeline_bp,
    tool_bp,
    gateway_bp,
    skill_creator_bp,
]


def create_app() -> tuple[Flask, SocketIO]:
    app = Flask(
        __name__,
        template_folder=str(_PKG_ROOT / "templates"),
        static_folder=str(_PKG_ROOT / "static"),
    )
    app.config['SECRET_KEY'] = _platform_cfg.server.secret_key
    app.config['MAX_CONTENT_LENGTH'] = _platform_cfg.server.max_upload_mb * 1024 * 1024
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    app.jinja_env.auto_reload = True
    app.jinja_env.cache = {}

    socketio = SocketIO(app, **_socketio_kwargs())
    register_gateway_socketio(socketio)

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    app.register_blueprint(unified_bp, url_prefix='/api/unified')
    register_memory_system(app)
    register_collaboration_events(socketio)
    create_webhook_receiver(app)
    register_openapi_routes(app)
    return app, socketio


app, socketio = create_app()

# 全局配置（从统一配置系统获取）
MODEL = _platform_cfg.llm.model
monitoring_manager = MonitoringManager(MonitoringStorage())

# 存储活动的 Agent 会话
active_sessions = {}
active_sessions_lock = threading.RLock()


def _set_active_session(session_id: str, session: "AgentSession") -> None:
    with active_sessions_lock:
        active_sessions[session_id] = session


def _discard_active_session(session_id: str) -> None:
    with active_sessions_lock:
        active_sessions.pop(session_id, None)


def _socket_payload(data):
    """标准化 Socket 事件载荷。"""
    return data or {}


def _emit_socket_error(event_name: str, prefix: str, exc: Exception | None = None):
    """统一记录并发送 Socket 错误事件。"""
    message = prefix if exc is None else f"{prefix}: {exc}"
    if exc is None:
        logger.error(message)
    else:
        logger.exception(message)
    emit(event_name, {'error': message})


class AgentSession(_BaseAgentSession):
    """Web UI 版 AgentSession —— 增加记忆系统集成"""

    def __init__(self, session_id: str, config: dict, user_id: str | None = None, emit_fn=None):
        super().__init__(session_id, config, user_id=user_id, emit_fn=emit_fn or socketio.emit)
        self.memory_manager = get_memory_manager()
        self.file_memory = get_file_memory_layer()

    def create_agent(self):
        """创建 Agent（继承自动工具发现，额外注册记忆工具）"""
        cfg = _platform_cfg

        def stream_callback(chunk: str):
            self._emit('stream_chunk', {'session_id': self.session_id, 'chunk': chunk})

        builder = (
            AgentBuilder()
            .with_openai(
                api_key=cfg.llm.api_key,
                model=self.config.get('model', cfg.llm.model),
                base_url=cfg.llm.base_url,
            )
            .with_agent_backend(self.config.get('agent_backend', 'auto'))
            .with_temperature(self.config.get('temperature', cfg.agent.temperature))
            .with_max_tokens(self.config.get('max_tokens', cfg.agent.max_tokens))
            .with_top_p(self.config.get('top_p', cfg.agent.top_p))
            .with_frequency_penalty(self.config.get('frequency_penalty', cfg.agent.frequency_penalty))
            .with_presence_penalty(self.config.get('presence_penalty', cfg.agent.presence_penalty))
            .with_stream(self.config.get('stream', cfg.agent.stream), on_chunk=stream_callback)
            .with_callbacks(self.callbacks)
            .with_max_rounds(self.config.get('max_rounds', cfg.agent.max_rounds))
            .with_tool_permission_rules(self.config.get("tool_permission_rules"))
            .with_tool_result_limit(int(self.config.get("max_tool_result_chars", 4000) or 4000))
        )

        from agent_framework.tools import register_selected_tools
        register_selected_tools(
            builder,
            allowed_tools=self.config.get("allowed_tools"),
            blocked_tools=self.config.get("blocked_tools"),
            toolsets=self.config.get("toolsets") or self.config.get("toolset"),
            include_plugin_tools=bool(self.config.get("include_plugin_tools", True)),
        )

        # 注册记忆工具
        builder = MemoryToolsRegistry.register_memory_tools(builder)

        return builder.build()

    def run(self, user_input: str):
        """运行 Agent"""
        try:
            super().run(user_input)

            # 自动保存重要交互到记忆
            if self.thread:
                final_result = latest_assistant_message(self.thread)
                self._auto_save_memory(user_input, final_result)

            # 兼容旧平台入口的性能记录
            if self.user_id and self.thread:
                try:
                    monitoring_manager.record_performance(
                        user_id=self.user_id,
                        model=self.config.get('model', MODEL),
                        input_tokens=self.token_counter.total_input_tokens,
                        output_tokens=self.token_counter.total_output_tokens,
                        latency=self.perf_monitor.total_time,
                    )
                except Exception:
                    pass
        finally:
            # 清理已完成的会话
            _discard_active_session(self.session_id)

    def _auto_save_memory(self, user_input: str, final_result: str):
        """自动保存交互到记忆系统（三层架构：SQLite + 每日笔记）"""
        try:
            # 过滤无效输入
            if len(user_input) < 10 or len(final_result) < 20:
                return

            greetings = ['你好', 'hello', 'hi', '谢谢', 'thank you']
            if any(greeting in user_input.lower() for greeting in greetings):
                return

            # 统一截断逻辑
            def truncate(text: str, max_len: int) -> str:
                return text[:max_len] + "..." if len(text) > max_len else text

            # Layer 1: 写入每日笔记
            try:
                self.file_memory.append_daily_note(f"用户: {truncate(user_input, 150)}")
                self.file_memory.append_daily_note(f"助手: {truncate(final_result, 150)}")
            except Exception as e:
                logger.warning("写入每日笔记失败: %s", e)

            # Layer 2: 写入 SQLite
            timestamp = datetime.now().isoformat()
            base_context = {
                'session_id': self.session_id,
                'timestamp': timestamp,
                'source': 'web_ui'
            }

            self.memory_manager.add_episodic_memory(
                content=f"用户提问: {user_input}",
                context={**base_context, 'type': 'user_input'},
                importance=self._calculate_importance(user_input),
                tags=['user_input', 'conversation', 'web_ui']
            )

            self.memory_manager.add_procedural_memory(
                content=f"Agent回答: {truncate(final_result, 800)}",
                context={**base_context, 'type': 'agent_response', 'user_input': user_input},
                importance=self._calculate_importance(final_result),
                tags=['agent_response', 'conversation', 'web_ui']
            )
        except Exception as e:
            logger.warning("自动保存记忆失败: %s", e)

    def _calculate_importance(self, text: str) -> float:
        """计算文本重要性分数"""
        base_score = min(len(text) / 300, 0.5)

        important_keywords = {
            '重要', '关键', '问题', '错误', '解决', '方案', '配置', '设置',
            '部署', '优化', '性能', '如何', '怎么', '为什么', '什么是'
        }
        keyword_score = sum(0.1 for kw in important_keywords if kw in text)

        return min(base_score + keyword_score, 1.0)


@app.route('/')
def root_home():
    """默认首页跳转到开发工具主页。"""
    if _ENTRY_WEB_HTML.exists():
        return send_file(_ENTRY_WEB_HTML)
    return redirect(url_for('portal_home'))


@app.route('/portal')
def portal_home():
    """前端门户首页。"""
    return render_template('portal.html')


@app.route('/user')
def user_home():
    """用户版 - 风电运维智导助手"""
    return render_template(
        'maintenance_assistant.html',
        knowledge_base_examples=_get_knowledge_base_examples(),
        **_get_agent_tool_ui_options(),
    )


@app.route('/developer')
@app.route('/dev')
def developer_home():
    """开发版 - 平台总入口"""
    return render_template('index.html')


@app.route('/developer/assistant')
@app.route('/dev/assistant')
def developer_assistant():
    """开发版 - 可编辑的风电运维智导助手"""
    return render_template('maintenance_assistant_dev.html', **_get_agent_tool_ui_options())


@app.route('/modules/<slug>')
def module_workspace(slug: str):
    """业务模块工作台。"""
    module = MODULE_WORKSPACES.get(slug)
    if module is None:
        return redirect(url_for('portal_home'))
    return render_template('module_workspace.html', module=module)


@app.route('/modules/<slug>/app')
def module_frontend(slug: str):
    """业务模块前端页面。"""
    module = MODULE_WORKSPACES.get(slug)
    page = MODULE_FRONTENDS.get(slug)
    if module is None or page is None:
        return redirect(url_for('portal_home'))
    return render_template('module_frontend.html', module=module, page=page)


@app.route('/gateway-demo')
def gateway_demo():
    """Gateway + WebSocket 联调页"""
    return render_template('gateway_demo.html')


@app.route('/home')
def home():
    """首页别名"""
    return redirect(url_for('portal_home'))


@app.route('/maintenance-assistant')
def maintenance_assistant():
    """风电运维智导助手"""
    return render_template(
        'maintenance_assistant.html',
        knowledge_base_examples=_get_knowledge_base_examples(),
        **_get_agent_tool_ui_options(),
    )


@app.route('/chat')
def chat():
    """简单对话助手"""
    return render_template('chat.html')


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """对话API"""
    try:
        data = request.get_json()
        message = data.get('message', '')

        if not message:
            return jsonify({'error': '消息不能为空'}), 400

        # 这里可以接入实际的AI模型
        # 暂时返回简单的回复
        response = f"收到您的消息：{message}\n\n这是一个简单的回复示例。您可以在这里接入实际的AI模型来生成更智能的回复。"

        return jsonify({'response': response})
    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/multi-agent')
def multi_agent():
    """多 Agent 协作"""
    return render_template('multi_agent.html')



@app.route('/visual-workflow')
@app.route('/workflow')
def visual_workflow():
    """可视化工作流编排"""
    return render_template('visual_workflow.html')


@app.route('/test-visual-workflow')
def test_visual_workflow():
    """兼容旧测试入口，跳转到正式工作流页面"""
    return redirect(url_for('visual_workflow'))


@app.route('/knowledge')
def knowledge():
    """知识库管理"""
    return render_template('knowledge.html')


@app.route('/ontology')
def ontology_visualization():
    """本体论可视化"""
    return render_template('ontology_visualization.html')


@app.route('/plugins')
def plugins():
    """插件市场"""
    return render_template('plugin_market.html')


@app.route('/causal_chain_viz')
def causal_chain_viz():
    """因果链路可视化"""
    import json
    from urllib.parse import unquote
    from agent_framework.causal.causal_visualization import CausalVisualizer

    # 获取数据
    data_str = request.args.get('data', '{}')
    data = json.loads(unquote(data_str))

    # 生成可视化
    visualizer = CausalVisualizer()
    causal_structure = data.get('causal_structure', {})

    if causal_structure:
        html = visualizer.visualize_causal_chain(causal_structure, format='html')
        return html
    else:
        return "<html><body><h2>暂无因果链路数据</h2></body></html>"


@app.route('/apps')
def apps():
    """应用管理"""
    return render_template('apps.html')


@app.route('/tools')
def tools():
    """工具中心"""
    return redirect(url_for('apps'))


@app.route('/settings')
def settings():
    """系统设置"""
    return render_template('settings.html')


@app.route('/api-keys')
def api_keys():
    """API 密钥管理"""
    return render_template('api_keys.html')


@app.route('/data-platform')
@app.route('/data-platform/')
def data_platform_home():
    """数据平台 - 风机监控可视化"""
    return send_file(_PKG_ROOT / 'static' / 'data_platform' / 'index.html')


@app.route('/data-platform/<path:filename>')
def data_platform_static(filename):
    """数据平台静态资源"""
    return send_from_directory(_PKG_ROOT / 'static' / 'data_platform', filename)


@app.route('/skill-creator')
def skill_creator():
    """技能创建器"""
    return render_template('skill_creator.html')


@app.route('/login')
def login():
    """用户登录"""
    return render_template('login.html')


@app.route('/register')
def register():
    """用户注册"""
    return render_template('register.html')


@app.route('/profile')
def profile():
    """个人中心"""
    return render_template('profile.html')


@app.route('/finetune')
def finetune():
    """模型微调"""
    return render_template('finetune.html')


@app.route('/causal-reasoning')
def causal_reasoning():
    """因果推理引擎"""
    return render_template('causal_reasoning.html')


@app.route('/causal-chain')
def causal_chain():
    """因果推理链"""
    return render_template('causal_chain.html')


@app.route('/causal-tree')
def causal_tree():
    """因果推理树"""
    import json as _json
    from agent_framework.causal.causal_tree_demos import get_demo_list, get_demo_by_id
    demos = get_demo_list()
    # 若 URL 携带 ?demo=xxx，直接将完整 demo 数据注入页面，无需前端再 fetch
    demo_id = request.args.get('demo', '')
    preload_demo = get_demo_by_id(demo_id) if demo_id else None
    preload_json = _json.dumps(preload_demo, ensure_ascii=False) if preload_demo else 'null'
    # 把 cause/effect/context 也直接注入表单 value（服务端渲染，无需 JS）
    preload_cause   = preload_demo.get('cause', '')   if preload_demo else ''
    preload_effect  = preload_demo.get('effect', '')  if preload_demo else ''
    preload_context = preload_demo.get('context', '') if preload_demo else ''
    return render_template('causal_tree.html', demos=demos,
                           preload_json=preload_json, selected_demo_id=demo_id,
                           preload_cause=preload_cause, preload_effect=preload_effect,
                           preload_context=preload_context)


@app.route('/demo-gallery')
def demo_gallery():
    """演示案例库"""
    return render_template('demo_gallery.html')


@app.route('/test_demos_simple')
def test_demos_simple():
    """兼容旧测试入口，跳转到演示案例页"""
    return redirect(url_for('demo_gallery'))


@app.route('/memory')
def memory_dashboard():
    """永久记忆系统"""
    return render_template('memory_dashboard.html')


@app.route('/dashboard')
def dashboard():
    """管理后台"""
    return render_template('dashboard.html')


@app.route('/analytics')
def analytics_dashboard():
    """数据分析面板"""
    return render_template('analytics_dashboard.html')







@app.route('/simple_test')
def simple_test():
    """兼容旧测试入口，跳转到健康检查"""
    return redirect(url_for('health'))



@app.route('/industry-knowledge')
def industry_knowledge():
    """行业智库"""
    return render_template('industry_knowledge.html')




@app.route('/performance')
def performance_dashboard():
    """性能监控仪表板"""
    return render_template('performance_dashboard.html')


@app.route('/system-status')
def system_status_page():
    """系统状态页面"""
    return render_template('system_status.html')


@app.route('/async-tasks')
def async_tasks_dashboard():
    """异步任务管理"""
    return render_template('async_tasks.html')


@app.route('/rl')
def rl_dashboard():
    """兼容旧入口：统一跳转到面向大模型的 RLHF / LLM-RL 页面"""
    return redirect(url_for('llm_rl_dashboard'))


@app.route('/llm-rl')
def llm_rl_dashboard():
    """LLM 强化学习平台"""
    return render_template('llm_rlhf_dashboard.html')


@app.route('/pipeline')
def pipeline_dashboard():
    """SFT -> RLHF 统一训练流水线"""
    return render_template('pipeline_dashboard.html')


@app.route('/logs')
def logs_dashboard():
    """日志管理"""
    return render_template('logs.html')


@app.route('/webhooks')
def webhooks_dashboard():
    """Webhook 管理"""
    return render_template('webhooks.html')


@app.route('/code-snippets')
def code_snippets():
    """代码片段管理"""
    return render_template('code_snippets.html')


@app.route('/health')
def health():
    """健康检查"""
    return jsonify(build_liveness_report())


@app.route('/health/live')
def health_live():
    """Liveness probe."""
    return jsonify(build_liveness_report())


@app.route('/health/ready')
def health_ready():
    """Readiness probe."""
    report = build_readiness_report(app)
    return jsonify(report), readiness_http_status(report)


@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    logger.info("Client connected: %s", request.sid)
    emit('connected', {'status': 'ok'})


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    logger.info("Client disconnected: %s", request.sid)


@socketio.on('start_agent')
def handle_start_agent(data):
    """启动 Agent"""
    data = _socket_payload(data)
    session_id = str(uuid.uuid4())
    user_input = data.get('input', '')
    config = data.get('config', {})
    user_id = data.get('user_id')

    # 创建会话
    session = AgentSession(session_id, config, user_id=user_id)
    _set_active_session(session_id, session)

    # 发送会话 ID
    emit('session_created', {
        'session_id': session_id,
        'task': user_input,
        'status': 'queued'
    })

    # 在后台线程运行 Agent
    thread = threading.Thread(target=session.run, args=(user_input,))
    thread.daemon = True
    thread.start()


@socketio.on('assistant_message')
def handle_assistant_message(data):
    """处理助手消息（支持多种 Agent 类型）"""
    try:
        data = _socket_payload(data)
        logger.debug("assistant_message payload: %s", data)
        message = data.get('message', '')
        model = data.get('model', MODEL)
        agent_type = data.get('agent_type', 'general')

        if not message:
            _emit_socket_error('assistant_error', '消息不能为空')
            return

        # 创建 LLM Provider
        from agent_framework.agent.llm import OpenAICompatibleProvider
        llm_provider = OpenAICompatibleProvider(
            api_key=_platform_cfg.llm.api_key,
            model=model,
            base_url=_platform_cfg.llm.base_url,
            timeout=120
        )
        logger.debug("LLM provider created for agent_type=%s model=%s", agent_type, model)

        # 根据 Agent 类型构建系统提示词
        agent_prompts = {
            'general': """你是一个通用智能助手,可以回答各种问题并提供帮助。
你的回答应该:
- 清晰、准确、易懂
- 结构化组织信息
- 提供实用的建议和见解""",

            'code': """你是一个专业的代码助手,擅长:
- 编写高质量、可维护的代码
- 代码审查和优化建议
- 调试和修复bug
- 解释代码逻辑和算法
- 提供编程最佳实践建议

回答代码问题时,请:
1. 提供完整、可运行的代码示例
2. 添加清晰的注释说明
3. 解释关键逻辑和设计思路
4. 指出潜在的问题和优化方向""",

            'causal': """你是一个因果推理专家,擅长:
- 分析事件之间的因果关系
- 识别因果链条和影响路径
- 评估因果关系的强度和可信度
- 提供因果推理的可视化建议

进行因果推理时,请:
1. 明确识别原因和结果
2. 分析中间影响机制
3. 评估因果关系的强度
4. 考虑其他可能的影响因素
5. 提供结构化的因果分析""",

            'data': """你是一个数据分析专家,擅长:
- 数据清洗和预处理
- 统计分析和可视化
- 数据洞察和趋势分析
- 提供数据驱动的建议

进行数据分析时,请:
1. 明确分析目标和指标
2. 选择合适的分析方法
3. 解释数据背后的含义
4. 提供可视化建议
5. 给出可执行的行动建议"""
        }

        system_prompt = agent_prompts.get(agent_type, agent_prompts['general'])

        if agent_type == 'causal':
            # 因果推理 Agent
            logger.debug("Using causal agent")
            from agent_framework.causal.causal_cot_integration_v2 import get_causal_integration, analyze_causal_response
            integration = get_causal_integration()
            messages, metadata = integration.create_prompt(message)

            try:
                logger.debug("Calling LLM for causal agent")
                response = llm_provider.chat(messages, model=model)
                response_content = response.content if hasattr(response, 'content') else str(response)
                logger.debug("Causal LLM response preview: %s", response_content[:100])

                analysis_result = analyze_causal_response(
                    query=message,
                    llm_response=response_content,
                    mode=metadata.get('detected_mode'),
                    confidence=metadata.get('confidence', 0.0)
                )

                logger.debug("Sending causal response to client")
                emit('assistant_response', {
                    'message': response_content,
                    'metadata': {
                        'agent_type': 'causal',
                        'causal_analysis': {
                            'mode': analysis_result.mode.value if analysis_result.mode else '自动检测',
                            'confidence': analysis_result.confidence,
                            'quality_score': analysis_result.quality_score,
                            'links_count': len(analysis_result.causal_structure.get('links', [])),
                            'hypotheses_count': len(analysis_result.causal_structure.get('hypotheses', [])),
                            'causal_structure': analysis_result.causal_structure
                        }
                    }
                })
            except Exception as e:
                _emit_socket_error('assistant_error', '因果推理失败', e)

        else:
            # 其他 Agent 类型（通用、代码、数据分析）
            logger.debug("Using agent type=%s", agent_type)
            try:
                logger.debug("Calling LLM with streaming")
                messages = [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': message}
                ]

                # 流式回调函数
                def stream_callback(chunk):
                    emit('assistant_stream', {'chunk': chunk})

                response = llm_provider.chat(
                    messages,
                    model=model,
                    stream=True,
                    stream_callback=stream_callback
                )
                response_content = response.content if hasattr(response, 'content') else str(response)
                logger.debug("Streaming LLM response completed")
                emit('assistant_complete', {
                    'message': response_content,
                    'metadata': {'agent_type': agent_type}
                })
            except Exception as e:
                _emit_socket_error('assistant_error', 'LLM 调用失败', e)

    except Exception as e:
        _emit_socket_error('assistant_error', '处理消息时出错', e)


@socketio.on('multi_agent_execute')
def handle_multi_agent_execute(data):
    """处理多 Agent 协作任务"""
    try:
        data = _socket_payload(data)
        logger.debug("multi_agent_execute payload: %s", data)
        query = data.get('query', '')

        if not query:
            _emit_socket_error('multi_agent_error', '查询不能为空')
            return

        # 获取协调器
        from agent_framework.api.multi_agent_api import get_coordinator
        coordinator = get_coordinator()

        # 执行协作任务,带回调
        def progress_callback(event):
            logger.debug("multi agent event: %s", event['type'])
            emit('multi_agent_progress', event)

        result = coordinator.execute_collaborative_task(query, progress_callback)

        logger.debug("multi agent task completed")
        emit('multi_agent_complete', result)

    except Exception as e:
        _emit_socket_error('multi_agent_error', '多 Agent 任务失败', e)


@app.route('/api/config', methods=['GET'])
def get_config():
    """获取默认配置"""
    return jsonify({
        # 基础模型参数
        'model': MODEL,
        'temperature': 0.7,
        'max_tokens': 2048,
        'top_p': 0.95,
        'frequency_penalty': 0.0,
        'presence_penalty': 0.0,

        # 提示词配置
        'system_prompt': '',
        'stop_sequences': '',

        # 输出控制
        'stream': True,
        'response_format': 'text',

        # 执行控制
        'max_rounds': 15,
        'timeout': 60,

        # 重试策略
        'max_retries': 3,
        'retry_delay': 2,

        # 日志配置
        'log_level': 'info',
    })


@app.route('/api/system/status', methods=['GET'])
def get_system_status():
    """Return a live system status snapshot."""
    return jsonify(collect_system_status(app))


@app.route('/api/system/readiness', methods=['GET'])
def get_system_readiness():
    """Return readiness checks for the running harness."""
    report = build_readiness_report(app)
    return jsonify(report), readiness_http_status(report)


def initialize_extension_system():
    """初始化扩展系统。"""
    logger.info("正在初始化扩展系统...")
    try:
        extension_system = get_extension_system()
        asyncio.run(extension_system.initialize())
        logger.info("扩展系统初始化成功")
    except Exception as e:
        logger.exception("扩展系统初始化失败: %s", e)


def run_server():
    """统一的服务启动入口，供兼容入口复用。"""
    import sys
    import io

    # 设置 UTF-8 编码
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 80)
    print("Agent Framework - 智能体系统")
    print("=" * 80)
    print()
    print("功能特性:")
    print("  - 实时流式输出")
    print("  - 多工具协作")
    print("  - 性能监控")
    print("  - 参数可调")
    print()
    print(f"访问地址: http://localhost:{_platform_cfg.server.port}")
    print()

    initialize_extension_system()

    print("=" * 80)
    print()
    print("按 Ctrl+C 停止服务器")
    print("=" * 80)

    socketio.run(
        app,
        host=_platform_cfg.server.host,
        port=_platform_cfg.server.port,
        debug=_platform_cfg.server.debug,
        allow_unsafe_werkzeug=True,
    )


if __name__ == '__main__':
    run_server()
