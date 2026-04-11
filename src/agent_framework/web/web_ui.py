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
from urllib.parse import urlparse

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
        "tagline": "风资源评估与智能选址决策",
        "description": "基于气象数据、地形地貌、电网接入条件的综合分析，提供科学的风电场选址建议和风资源评估报告。",
        "status": "模块工作台",
        "primary_label": "进入知识与数据",
        "primary_href": "/knowledge",
        "secondary_label": "查看分析面板",
        "secondary_href": "/analytics",
        "scenes": [
            "风资源数据分析",
            "地形地貌评估",
            "候选站址筛选",
            "接入条件核查",
            "选址报告生成",
        ],
        "capabilities": [
            {"title": "数据整合", "desc": "整合测风塔数据、气象观测、卫星遥感和历史发电数据。"},
            {"title": "智能分析", "desc": "基于风速、风向、湍流强度、地形坡度等多维度智能评估。"},
            {"title": "选址优化", "desc": "综合考虑风资源、道路交通、电网接入和环境约束条件。"},
        ],
    },
    "smart-workorder": {
        "slug": "smart-workorder",
        "index": "02",
        "name": "智能工单",
        "tagline": "智能派单与全流程闭环管理",
        "description": "从缺陷识别、工单生成、智能派单到执行追踪、闭环归档，实现设备维护全流程数字化管理。",
        "status": "在线业务模块",
        "primary_label": "进入工单处理台",
        "primary_href": "/workflow",
        "secondary_label": "查看工单日志",
        "secondary_href": "/logs",
        "scenes": [
            "智能建单",
            "自动派单",
            "执行追踪",
            "质量复核",
            "闭环归档",
        ],
        "capabilities": [
            {"title": "智能建单", "desc": "基于设备告警、巡检发现自动生成工单，支持批量建单。"},
            {"title": "流程编排", "desc": "可配置审批流、派单规则、超时提醒和升级机制。"},
            {"title": "全程追踪", "desc": "实时查看工单状态、处理进度、现场照片和验收结果。"},
        ],
    },
    "guide-assistant": {
        "slug": "guide-assistant",
        "index": "03",
        "name": "智导助手",
        "tagline": "智能故障诊断与现场辅助决策",
        "description": "基于知识图谱和专家经验的智能问答系统，提供故障诊断、操作指导、应急预案和决策建议。",
        "status": "已接入现有能力",
        "primary_label": "进入业务助手",
        "primary_href": "/maintenance-assistant",
        "secondary_label": "进入开发版助手",
        "secondary_href": "/developer/assistant",
        "scenes": [
            "故障智能诊断",
            "操作步骤指导",
            "应急预案推荐",
            "知识检索增强",
            "经验案例复用",
        ],
        "capabilities": [
            {"title": "智能问答", "desc": "结合知识库、历史案例和实时数据的多轮对话问答。"},
            {"title": "故障诊断", "desc": "基于症状描述和设备数据，快速定位故障原因和解决方案。"},
            {"title": "决策支持", "desc": "提供操作建议、风险评估和应急处置方案。"},
        ],
    },
    "smart-guard": {
        "slug": "smart-guard",
        "index": "04",
        "name": "智能值守",
        "tagline": "全天候智能监控与告警联动",
        "description": "实时监控设备运行状态、智能告警分级处理、巡检任务管理，打造无人值守的智能运维中心。",
        "status": "模块工作台",
        "primary_label": "进入值守大屏",
        "primary_href": "/data-platform",
        "secondary_label": "查看性能监控",
        "secondary_href": "/performance",
        "scenes": [
            "实时监控大屏",
            "智能告警分级",
            "巡检任务调度",
            "异常态势分析",
            "值班日志记录",
        ],
        "capabilities": [
            {"title": "态势感知", "desc": "多维度展示设备状态、告警分布、巡检进度和关键指标。"},
            {"title": "智能告警", "desc": "告警自动分级、关联分析、处置建议和升级提醒。"},
            {"title": "巡检管理", "desc": "巡检路线规划、任务分配、完成度追踪和异常上报。"},
        ],
    },
    "power-trading": {
        "slug": "power-trading",
        "index": "05",
        "name": "电力交易",
        "tagline": "智能报价与市场分析",
        "description": "实时市场监控、智能报价建议、风险评估与收益优化，为电力交易决策提供全方位数据支持和AI辅助分析。",
        "status": "在线业务模块",
        "primary_label": "进入交易分析台",
        "primary_href": "/analytics",
        "secondary_label": "查看市场动态",
        "secondary_href": "/system-status",
        "scenes": [
            "实时市场监控",
            "智能报价优化",
            "风险评估分析",
            "收益预测建模",
            "历史数据对比",
            "市场趋势研判",
        ],
        "capabilities": [
            {"title": "实时行情", "desc": "多市场价格监控、负荷预测和成交数据实时更新。"},
            {"title": "智能报价", "desc": "基于历史数据和AI模型生成最优报价策略建议。"},
            {"title": "风险管控", "desc": "识别价格波动风险、负荷偏差和市场异常情况。"},
            {"title": "收益分析", "desc": "交易收益追踪、成本分析和经营指标可视化。"},
        ],
    },
    "smart-office": {
        "slug": "smart-office",
        "index": "06",
        "name": "智慧办公",
        "tagline": "AI 赋能的协同办公平台",
        "description": "智能文档处理、会议纪要生成、任务协同管理，让 AI 成为办公场景的得力助手。",
        "status": "模块工作台",
        "primary_label": "进入应用中心",
        "primary_href": "/apps",
        "secondary_label": "查看代码片段",
        "secondary_href": "/code-snippets",
        "scenes": [
            "智能文档处理",
            "会议纪要生成",
            "任务协同管理",
            "知识沉淀整理",
            "部门助手定制",
        ],
        "capabilities": [
            {"title": "文档智能", "desc": "文档摘要、信息抽取、格式转换和智能生成。"},
            {"title": "协同办公", "desc": "待办提醒、任务分配、进度追踪和团队协作。"},
            {"title": "知识管理", "desc": "会议纪要、经验总结、知识库构建和智能检索。"},
        ],
    },
}


MODULE_FRONTENDS = {
    "weather-siting": {
        "route": "/modules/weather-siting/app",
        "headline": "气象选址智能分析平台",
        "summary": "整合风资源数据、地形地貌、电网接入条件，提供科学的选址决策支持和风资源评估报告。",
        "metrics": [
            {"label": "候选区域", "value": "12", "note": "待评估地块"},
            {"label": "优选站址", "value": "4", "note": "推荐方案"},
            {"label": "测风数据", "value": "18 组", "note": "已接入分析"},
        ],
        "fields": [
            {"label": "项目名称", "type": "text", "name": "project", "placeholder": "例如：华北沿海风电场一期"},
            {"label": "区域范围", "type": "text", "name": "region", "placeholder": "例如：河北沿海 80km 半径范围"},
            {"label": "分析需求", "type": "textarea", "name": "goal", "placeholder": "描述选址目标、容量规划、重点关注因素（如风速要求、接入距离等）"},
        ],
        "quick_actions": ["风资源评估", "地形分析", "接入条件核查"],
        "result_title": "选址分析结果",
        "result_lines": [
            "综合评估年平均风速、风功率密度、湍流强度和极端气象条件。",
            "分析地形坡度、海拔高度、地表粗糙度对风资源的影响。",
            "核查道路交通、电网接入距离、环境保护区等约束条件。",
            "生成候选站址清单，标注优先级和关键风险点。",
        ],
        "board_title": "候选站址评估清单",
        "board_columns": ["站址编号", "区域位置", "风速等级", "综合评价"],
        "board_rows": [
            ["WS-A01", "沿海北段", "7.2 m/s", "优选 - 风资源优异，接入条件良好"],
            ["WS-A02", "沿海中段", "6.8 m/s", "推荐 - 测风数据完整，道路可达"],
            ["WS-B01", "丘陵西侧", "6.5 m/s", "备选 - 风速稳定，地形需详细勘察"],
            ["WS-B02", "平原东部", "6.2 m/s", "观察 - 接入距离较远，经济性待评估"],
        ],
    },
    "smart-workorder": {
        "route": "/modules/smart-workorder/app",
        "headline": "智能工单管理系统",
        "summary": "从缺陷识别到闭环归档的全流程数字化管理，支持智能派单、进度追踪和质量验收。",
        "metrics": [
            {"label": "待处理", "value": "9", "note": "需要派单"},
            {"label": "处理中", "value": "14", "note": "现场执行"},
            {"label": "已完成", "value": "126", "note": "本月累计"},
        ],
        "fields": [
            {"label": "设备名称", "type": "text", "name": "asset", "placeholder": "例如：3# 风机变桨系统"},
            {"label": "故障等级", "type": "text", "name": "severity", "placeholder": "紧急 / 重要 / 一般 / 计划"},
            {"label": "问题描述", "type": "textarea", "name": "issue", "placeholder": "详细描述故障现象、影响范围、已采取措施和处理需求"},
        ],
        "quick_actions": ["生成工单", "智能派单", "查看历史"],
        "result_title": "工单处理方案",
        "result_lines": [
            "基于故障描述自动生成工单标题、优先级和处理建议。",
            "智能匹配责任人、预估处理时长和所需备件。",
            "自动关联历史相似工单和处理经验。",
            "支持审批流程配置、超时提醒和自动升级。",
        ],
        "board_title": "工单处理队列",
        "board_columns": ["工单编号", "设备名称", "状态", "负责人"],
        "board_rows": [
            ["WO-240315", "3# 风机变桨", "待派单", "待分配"],
            ["WO-240312", "升压站保护", "处理中", "王工 - 预计今日完成"],
            ["WO-240308", "箱变温控", "待验收", "李工 - 等待复核"],
            ["WO-240305", "SCADA通讯", "已完成", "张工 - 已闭环归档"],
        ],
    },
    "smart-guard": {
        "route": "/data-platform",
        "headline": "智能值守监控中心",
        "summary": "实时监控设备运行状态，智能告警分级处理，巡检任务全程管理，打造无人值守运维体系。",
        "metrics": [
            {"label": "实时告警", "value": "6", "note": "需重点关注"},
            {"label": "巡检任务", "value": "11", "note": "本班次待完成"},
            {"label": "设备在线", "value": "98.2%", "note": "运行正常"},
        ],
        "fields": [
            {"label": "值班班次", "type": "text", "name": "shift", "placeholder": "例如：早班 / 中班 / 夜班"},
            {"label": "监控区域", "type": "text", "name": "area", "placeholder": "例如：1# 风场 / 升压站 / 全场"},
            {"label": "关注重点", "type": "textarea", "name": "focus", "placeholder": "描述本班次重点关注的设备、告警类型或特殊事项"},
        ],
        "quick_actions": ["告警处理", "巡检记录", "交接班"],
        "result_title": "值守态势分析",
        "result_lines": [
            "实时展示设备运行状态、告警分布和巡检完成情况。",
            "智能识别高优先级告警，推荐处置方案和联动操作。",
            "自动生成巡检路线，记录巡检发现和异常上报。",
            "支持值班日志自动生成和交接班信息推送。",
        ],
        "board_title": "告警处理清单",
        "board_columns": ["告警时间", "设备名称", "告警等级", "处理状态"],
        "board_rows": [
            ["14:23", "5# 风机齿轮箱", "紧急", "处理中 - 已派单"],
            ["13:45", "箱变温度异常", "重要", "已确认 - 持续观察"],
            ["12:10", "SCADA通讯中断", "一般", "已恢复 - 待归档"],
            ["11:30", "测风仪数据缺失", "提示", "已记录 - 计划检修"],
        ],
    },
    "power-trading": {
        "route": "/modules/power-trading/app",
        "headline": "电力交易智能分析台",
        "summary": "实时监控多市场行情动态，AI驱动的智能报价建议，风险预警与收益优化分析，为交易决策提供全方位数据支持。",
        "metrics": [
            {"label": "实时均价", "value": "428.5", "note": "元/MWh"},
            {"label": "负荷预测", "value": "92.3%", "note": "准确率"},
            {"label": "今日收益", "value": "+18.6", "note": "万元"},
            {"label": "风险等级", "value": "中", "note": "可控范围"},
        ],
        "fields": [
            {"label": "交易时段", "type": "text", "name": "period", "placeholder": "例如：明日日前 / 本周现货 / 月度中长期"},
            {"label": "目标市场", "type": "text", "name": "market", "placeholder": "例如：华北现货 / 华东日前 / 南方电网"},
            {"label": "交易容量", "type": "text", "name": "capacity", "placeholder": "例如：500 MW / 全部可用容量"},
            {"label": "分析目标", "type": "textarea", "name": "goal", "placeholder": "描述报价策略、风险偏好、收益目标或市场研判需求"},
        ],
        "quick_actions": [
            "生成智能报价方案",
            "分析市场价格趋势",
            "评估交易风险等级",
            "优化收益策略",
            "对比历史同期数据",
            "预测负荷曲线"
        ],
        "result_title": "AI交易分析报告",
        "result_lines": [
            "基于实时市场数据和历史模式，AI模型已生成最优报价建议。",
            "当前市场波动处于正常范围，建议采用稳健型报价策略。",
            "负荷预测准确率达92.3%，可信度较高，建议参考执行。",
            "已识别3个潜在风险点和2个套利机会，详见风险评估面板。",
        ],
        "board_title": "实时交易看板",
        "board_columns": ["市场/时段", "当前价格", "预测趋势", "建议操作"],
        "board_rows": [
            ["日前市场 08:00-12:00", "¥435/MWh", "↗ 上涨5%", "适度增加报量"],
            ["日前市场 12:00-18:00", "¥520/MWh", "→ 平稳", "按计划执行"],
            ["日前市场 18:00-22:00", "¥680/MWh", "↗ 峰值", "优先高价时段"],
            ["现货市场 实时", "¥428/MWh", "↘ 回落3%", "观察后续走势"],
            ["中长期合约", "¥395/MWh", "→ 稳定", "按合约履约"],
        ],
    },
    "smart-office": {
        "route": "/modules/smart-office/app",
        "headline": "智慧办公协同平台",
        "summary": "AI 驱动的文档处理、会议纪要生成、任务协同管理，让办公更高效智能。",
        "metrics": [
            {"label": "待办任务", "value": "17", "note": "今日需处理"},
            {"label": "会议纪要", "value": "5", "note": "待生成"},
            {"label": "协同事项", "value": "8", "note": "跨部门"},
        ],
        "fields": [
            {"label": "办公场景", "type": "text", "name": "topic", "placeholder": "例如：周例会 / 项目协同 / 文档整理"},
            {"label": "参与部门", "type": "text", "name": "team", "placeholder": "例如：运维部、交易部、综合部"},
            {"label": "处理需求", "type": "textarea", "name": "goal", "placeholder": "描述会议纪要生成、任务分配、文档摘要或知识整理需求"},
        ],
        "quick_actions": ["生成会议纪要", "任务分配", "文档摘要"],
        "result_title": "智能办公助手",
        "result_lines": [
            "自动提取会议关键信息，生成结构化纪要和待办清单。",
            "智能识别任务优先级，推荐责任人和完成时限。",
            "文档智能摘要、信息抽取和格式转换。",
            "支持知识沉淀、经验总结和团队协作。",
        ],
        "board_title": "办公任务看板",
        "board_columns": ["任务名称", "负责部门", "状态", "截止时间"],
        "board_rows": [
            ["周例会纪要整理", "综合部", "进行中", "今日 16:00"],
            ["运维月报生成", "运维部", "待开始", "本周五"],
            ["交易策略文档", "交易部", "待审核", "明日 10:00"],
            ["知识库更新", "技术部", "已完成", "已归档"],
        ],
    },
}

for _slug, _page in MODULE_FRONTENDS.items():
    if _slug in MODULE_WORKSPACES:
        MODULE_WORKSPACES[_slug]["primary_href"] = _page["route"]


PORTAL_SECTIONS = [
    {
        "title": "AI 助手",
        "summary": "对话、诊断、协作和开发版助手入口。",
        "items": [
            {"name": "智能运维助手", "href": "/maintenance-assistant", "summary": "统一问答、诊断和运维建议入口。"},
            {"name": "助手视图", "href": "/user", "summary": "面向使用者的助手界面。"},
            {"name": "开发版助手", "href": "/dev/assistant", "summary": "可编辑配置的开发版助手。"},
            {"name": "简易对话", "href": "/chat", "summary": "轻量聊天页。"},
            {"name": "多 Agent 协作", "href": "/multi-agent", "summary": "多智能体协同工作入口。"},
        ],
    },
    {
        "title": "业务模块",
        "summary": "已有业务场景页面，直接打开，不再经首页中转。",
        "items": [
            {"name": "风场选址", "href": "/modules/weather-siting/app", "summary": "气象与选址分析模块。"},
            {"name": "智能工单", "href": "/modules/smart-workorder/app", "summary": "工单生成、派发和闭环处理。"},
            {"name": "智能值守", "href": "/data-platform", "summary": "监控大屏和值守场景。"},
            {"name": "电力交易", "href": "/modules/power-trading/app", "summary": "交易分析与策略支持。"},
            {"name": "智慧办公", "href": "/modules/smart-office/app", "summary": "办公协同和知识整理场景。"},
        ],
    },
    {
        "title": "知识与流程",
        "summary": "知识库、插件、工作流和应用能力。",
        "items": [
            {"name": "知识库", "href": "/knowledge", "summary": "知识库管理与检索。"},
            {"name": "本体可视化", "href": "/ontology", "summary": "本体与关系结构展示。"},
            {"name": "插件市场", "href": "/plugins", "summary": "插件浏览与管理。"},
            {"name": "应用中心", "href": "/apps", "summary": "平台应用与工具入口。"},
            {"name": "技能创建器", "href": "/skill-creator", "summary": "快速创建技能配置。"},
            {"name": "可视化工作流", "href": "/workflow", "summary": "统一工作流编排入口，覆盖可视化与复杂流程配置。"},
            {"name": "协作管理", "href": "/collaboration", "summary": "团队协作与流程管理。"},
        ],
    },
    {
        "title": "分析与运营",
        "summary": "监控、分析、日志、任务和文档类页面。",
        "items": [
            {"name": "分析面板", "href": "/analytics", "summary": "分析看板与业务数据汇总。"},
            {"name": "管理后台", "href": "/dashboard", "summary": "后台管理总览。"},
            {"name": "行业知识", "href": "/industry-knowledge", "summary": "行业知识内容入口。"},
            {"name": "性能监控", "href": "/performance", "summary": "性能指标和状态跟踪。"},
            {"name": "系统状态", "href": "/system-status", "summary": "运行状态与健康展示。"},
            {"name": "监控面板", "href": "/monitoring", "summary": "平台监控页面。"},
            {"name": "异步任务", "href": "/async-tasks", "summary": "异步任务执行与管理。"},
            {"name": "日志中心", "href": "/logs", "summary": "日志查看与筛选。"},
            {"name": "文档中心", "href": "/documents", "summary": "文档与资料管理。"},
            {"name": "代码片段", "href": "/code-snippets", "summary": "代码片段存取与复用。"},
            {"name": "提示词库", "href": "/prompts", "summary": "提示词管理入口。"},
            {"name": "Webhook 管理", "href": "/webhooks", "summary": "Webhook 配置与查看。"},
            {"name": "HTTP 工具", "href": "/http-tools", "summary": "HTTP 请求调试与测试。"},
        ],
    },
    {
        "title": "模型与实验",
        "summary": "推理、微调、训练和实验相关页面。",
        "items": [
            {"name": "因果推理", "href": "/causal-reasoning", "summary": "因果推理引擎页面。"},
            {"name": "因果链", "href": "/causal-chain", "summary": "因果链路分析。"},
            {"name": "因果树", "href": "/causal-tree", "summary": "因果树实验与示例。"},
            {"name": "高级推理", "href": "/reasoning", "summary": "推理实验页面。"},
            {"name": "模型微调", "href": "/finetune", "summary": "微调任务配置页面。"},
            {"name": "A/B 测试", "href": "/ab-testing", "summary": "实验对比和评估。"},
            {"name": "LLM 强化学习", "href": "/llm-rl", "summary": "RLHF / LLM-RL 入口。"},
            {"name": "训练流水线", "href": "/pipeline", "summary": "SFT 到 RLHF 的统一流水线。"},
            {"name": "多模态", "href": "/multimodal", "summary": "多模态能力页面。"},
            {"name": "记忆系统", "href": "/memory", "summary": "持久化记忆与观察面板。"},
            {"name": "发布管理", "href": "/publish", "summary": "发布与交付入口。"},
            {"name": "配置预设", "href": "/config-presets", "summary": "配置模板与预设管理。"},
        ],
    },
    {
        "title": "平台与账号",
        "summary": "开发控制台、系统设置与账号页面。",
        "items": [
            {"name": "开发控制台", "href": "/dev", "summary": "平台开发总入口。"},
            {"name": "设置", "href": "/settings", "summary": "平台设置页面。"},
            {"name": "API Keys", "href": "/api-keys", "summary": "API 密钥管理。"},
            {"name": "扩展管理", "href": "/extensions", "summary": "扩展与能力管理。"},
            {"name": "登录", "href": "/login", "summary": "用户登录页面。"},
            {"name": "注册", "href": "/register", "summary": "用户注册页面。"},
            {"name": "个人中心", "href": "/profile", "summary": "个人资料与账号信息。"},
        ],
    },
]


def _portal_allowed_targets() -> set[str]:
    return {
        item["href"]
        for section in PORTAL_SECTIONS
        for item in section["items"]
    }


def _portal_iframe_src(href: str) -> str:
    if href.startswith("/"):
        separator = "&" if "?" in href else "?"
        return f"{href}{separator}embed=1"
    if href.startswith("/modules/") and href.endswith("/app"):
        return f"{href}?embed=1"
    return href


def _build_portal_sections(current_target: str | None = None) -> list[dict]:
    sections: list[dict] = []
    for section in PORTAL_SECTIONS:
        items = []
        for item in section["items"]:
            item_copy = dict(item)
            item_copy["shell_href"] = url_for("portal_home", target=item["href"])
            item_copy["iframe_src"] = _portal_iframe_src(item["href"])
            item_copy["active"] = item["href"] == current_target
            items.append(item_copy)
        section_copy = dict(section)
        section_copy["items"] = items
        section_copy["active"] = any(item["active"] for item in items)
        sections.append(section_copy)
    return sections


def _resolve_portal_target(raw_target: str | None) -> str | None:
    if not raw_target:
        return None
    target = raw_target.strip()
    if not target or not target.startswith("/"):
        return None
    parsed = urlparse(target)
    normalized = parsed.path
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    if normalized not in _portal_allowed_targets():
        return None
    return normalized


def _find_portal_item(target: str | None) -> dict | None:
    if target is None:
        return None
    for section in PORTAL_SECTIONS:
        for item in section["items"]:
            if item["href"] == target:
                item_copy = dict(item)
                item_copy["iframe_src"] = _portal_iframe_src(item["href"])
                return item_copy
    return None


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
    current_target = _resolve_portal_target(request.args.get("target"))
    current_item = _find_portal_item(current_target)
    portal_sections = _build_portal_sections(current_target)
    total_features = sum(len(section["items"]) for section in PORTAL_SECTIONS)
    return render_template(
        'portal.html',
        portal_sections=portal_sections,
        portal_total_features=total_features,
        current_target=current_target,
        current_item=current_item,
    )


@app.route('/user')
def user_home():
    """用户版 - 风电运维智导助手"""
    embedded = request.args.get("embed") == "1"
    return render_template(
        'maintenance_assistant.html',
        knowledge_base_examples=_get_knowledge_base_examples(),
        embedded=embedded,
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
    embedded = request.args.get("embed") == "1"
    return render_template('maintenance_assistant_dev.html', embedded=embedded, **_get_agent_tool_ui_options())


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
    embedded = request.args.get("embed") == "1"
    return render_template('module_frontend.html', module=module, page=page, embedded=embedded)


@app.route('/home')
def home():
    """首页别名"""
    return redirect(url_for('portal_home'))


@app.route('/maintenance-assistant')
def maintenance_assistant():
    """风电运维智导助手"""
    embedded = request.args.get("embed") == "1"
    return render_template(
        'maintenance_assistant.html',
        knowledge_base_examples=_get_knowledge_base_examples(),
        embedded=embedded,
        **_get_agent_tool_ui_options(),
    )


@app.route('/chat')
def chat():
    """简单对话助手"""
    embedded = request.args.get("embed") == "1"
    return render_template('chat.html', embedded=embedded)


@app.route('/chat-interface')
def chat_interface_redirect():
    return redirect(url_for('chat'))


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
    embedded = request.args.get("embed") == "1"
    return render_template('visual_workflow.html', embedded=embedded)


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
    embedded = request.args.get("embed") == "1"
    return render_template('plugin_market.html', embedded=embedded)


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
    embedded = request.args.get("embed") == "1"
    return render_template('settings.html', embedded=embedded)


@app.route('/api-keys')
def api_keys():
    """API 密钥管理"""
    embedded = request.args.get("embed") == "1"
    return render_template('api_keys.html', embedded=embedded)


@app.route('/data-platform')
@app.route('/data-platform/')
def data_platform_home():
    """数据平台 - 风机监控可视化"""
    response = send_file(_PKG_ROOT / 'static' / 'data_platform' / 'index.html')
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route('/data-platform/<path:filename>')
def data_platform_static(filename):
    """数据平台静态资源"""
    response = send_from_directory(_PKG_ROOT / 'static' / 'data_platform', filename)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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
    embedded = request.args.get("embed") == "1"
    return render_template('finetune.html', embedded=embedded)


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
    embedded = request.args.get("embed") == "1"
    return render_template('dashboard.html', embedded=embedded)


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
    embedded = request.args.get("embed") == "1"
    return render_template('industry_knowledge.html', embedded=embedded)




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


@app.route('/prompts')
def prompts_page():
    """提示词库管理"""
    return render_template('prompts.html')


@app.route('/documents')
def documents_page():
    """文档中心"""
    return render_template('documents.html')


@app.route('/ab-testing')
def ab_testing_page():
    """A/B 测试平台"""
    return render_template('ab_testing.html')


@app.route('/reasoning')
def reasoning_page():
    """高级推理实验室"""
    return render_template('reasoning.html')


@app.route('/publish')
def publish_page():
    """发布管理"""
    return render_template('publish.html')


@app.route('/config-presets')
def config_presets_page():
    """配置预设管理"""
    return render_template('config_presets.html')


@app.route('/http-tools')
def http_tools_page():
    """HTTP 请求工具"""
    return render_template('http_tools.html')


@app.route('/workflow-advanced')
def workflow_advanced_page():
    """兼容旧高级工作流入口，统一回到工作流页"""
    return redirect(url_for('visual_workflow'))


@app.route('/collaboration')
def collaboration_page():
    """协作管理"""
    return render_template('collaboration.html')


@app.route('/monitoring')
def monitoring_page():
    """监控面板"""
    return render_template('monitoring.html')


@app.route('/multimodal')
def multimodal_page():
    """多模态处理"""
    return render_template('multimodal.html')


@app.route('/extensions')
def extensions_page():
    """扩展管理"""
    return render_template('extensions.html')


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
