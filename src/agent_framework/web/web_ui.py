"""
Web UI - Agent Framework 交互式界面
基于 Flask + WebSocket 实现实时流式输出
"""

import asyncio
import logging
import threading
import uuid
import urllib.request
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, send_from_directory, Response
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
        "name": "风场选址",
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

MODULE_WORKSPACE_DETAILS = {
    "weather-siting": {
        "workspace_kpis": [
            {"icon": "forest", "value": "18→6→2", "label": "候选收敛"},
            {"icon": "radar", "value": "91%", "label": "测风覆盖"},
            {"icon": "power", "value": "3条", "label": "接入走廊"},
            {"icon": "warning", "value": "2项", "label": "待踏勘约束"},
            {"icon": "schedule", "value": "72h", "label": "决策窗口"},
        ],
        "overview_cards": [
            {"kicker": "当前重点", "title": "先把候选区缩到可研级名单", "desc": "这一页先服务站址收敛，不做泛化展示。优选、备选和观察池必须被清楚分开。"},
            {"kicker": "推进重点", "title": "资源、工程、并网三面并排", "desc": "风速不是唯一主线，工程可实施性和接入距离必须一起参与排序。"},
            {"kicker": "协同接口", "title": "把未闭合约束直接转成动作", "desc": "生态、道路、吊装和送出距离中的未决项，直接下发到踏勘或外部确认，不留模糊结论。"},
            {"kicker": "输出要求", "title": "结论要能直接进入投前评审", "desc": "工作台要给出管理层能读懂的排序、风险和下一步动作，而不是一堆原始分析截图。"},
        ],
        "operating_kicker": "业务主线",
        "operating_title": "风场选址工作台的三段收敛链",
        "operating_sections": [
            {
                "label": "资源筛选",
                "title": "先把风资源和硬约束拉平",
                "desc": "先统一测风样本、机型边界和收益底线，再做红线筛除，避免候选区从一开始就跑偏。",
                "bullets": [
                    "统一容量、机型与收益基线。",
                    "先剔除生态、噪声和运输硬冲突。",
                    "测风缺口直接转补数动作。",
                ],
            },
            {
                "label": "工程复筛",
                "title": "工程可实施性不能后置",
                "desc": "道路、吊装、坡度和施工窗口要和资源面同步看，不能等到结论出来再返工。",
                "bullets": [
                    "同步比对道路可达和吊装平台条件。",
                    "长送出方案直接给经济性提醒。",
                    "丘陵区单独做微地形修正提示。",
                ],
            },
            {
                "label": "决策输出",
                "title": "结论直接指向优选、备选、踏勘",
                "desc": "站址不是只给排序，必须明确哪些进入可研、哪些保留、哪些必须先踏勘。",
                "bullets": [
                    "输出优选、备选、观察池三档名单。",
                    "把外部确认项从结论里拆出去。",
                    "形成可直接汇报的投前口径。",
                ],
            },
        ],
        "capability_title": "风场选址工作台能力栈",
        "board_kicker": "工作看板",
        "board_title": "本轮选址推进通道",
        "board_cards": [
            {"kicker": "主流程", "title": "候选区漏斗收敛", "desc": "从资源筛选到工程复筛再到管理结论，主链路必须压缩轮次。"},
            {"kicker": "关键卡点", "title": "道路与接入双复核", "desc": "真正会拖慢评审的，不是风速高低，而是道路吊装和接入距离没有闭合。"},
            {"kicker": "协同动作", "title": "踏勘与并网同步推进", "desc": "工程设计与并网专责要同时收到优选点位，避免一边先走一边等数据。"},
            {"kicker": "交付形态", "title": "管理层可读结论包", "desc": "输出排序、风险、敏感性和下一步动作，不把业务决策留给用户自己拼。"},
        ],
        "timeline_kicker": "近期节奏",
        "timeline_title": "风场选址最近动作",
        "timeline_steps": [
            {"tone": "success", "title": "沿海北段已锁定进入优选名单", "time": "8 分钟前", "desc": "风资源、接入距离和施工条件三面表现均衡，已进入可研候选。"},
            {"tone": "primary", "title": "接入走廊方案更新至三条可行路径", "time": "26 分钟前", "desc": "并网专责已回传新口径，长距离送出方案被降级为备选。"},
            {"tone": "warn", "title": "丘陵西侧仍需补踏勘与高程校核", "time": "52 分钟前", "desc": "当前 DEM 修正后仍存在不确定性，禁止直接进入结论名单。"},
            {"tone": "success", "title": "投前汇报模板已自动预填", "time": "今天 09:10", "desc": "优选、备选和观察池结构已经同步到管理汇报模板。"},
        ],
    },
    "smart-workorder": {
        "workspace_kpis": [
            {"icon": "assignment", "value": "21", "label": "今日受理"},
            {"icon": "crisis_alert", "value": "4", "label": "超时风险"},
            {"icon": "build_circle", "value": "6", "label": "待验收"},
            {"icon": "inventory_2", "value": "84%", "label": "备件命中"},
            {"icon": "task_alt", "value": "93%", "label": "闭环率"},
        ],
        "overview_cards": [
            {"kicker": "当前重点", "title": "把待验收当主瓶颈来处理", "desc": "工单模块最大的问题不是建单速度，而是执行后回执和验收排队导致闭环失真。"},
            {"kicker": "派单原则", "title": "责任、技能、位置和备件一起看", "desc": "高优先级工单不能只推给空闲人，必须同时看资源匹配和备件可达性。"},
            {"kicker": "现场要求", "title": "现场留痕要进入主链路", "desc": "照片、措施、工时和材料使用必须被当作闭环的一部分，而不是附属上传。"},
            {"kicker": "沉淀目标", "title": "把返工原因沉淀成模板", "desc": "重复故障和高频返工项应继续回流到模板建单和 SOP 中。"},
        ],
        "operating_kicker": "业务主线",
        "operating_title": "智能工单工作台的闭环组织方式",
        "operating_sections": [
            {
                "label": "受理",
                "title": "先把故障对象写清楚",
                "desc": "设备、等级、影响面和临时措施如果不规范，后面所有派单和复核都会反复返工。",
                "bullets": [
                    "受理时统一设备、站点和等级字段。",
                    "临时措施与剩余风险必须入单。",
                    "重复故障优先复用模板建单。",
                ],
            },
            {
                "label": "派单执行",
                "title": "派单和资源调度放在一起",
                "desc": "高优先级工单的真正难点不在分配动作本身，而在能否一次匹配到正确班组和备件。",
                "bullets": [
                    "高优先级直接进入值长裁决链。",
                    "班组、技能、位置和备件联合推荐。",
                    "现场处理全程记录措施和照片。",
                ],
            },
            {
                "label": "验收沉淀",
                "title": "闭环要带着回执和复盘一起结束",
                "desc": "如果只是把状态改成完成，工单价值就丢了一半，验收结论和经验沉淀必须进入终态。",
                "bullets": [
                    "待验收队列单独暴露出来。",
                    "回执缺口直接提示责任节点。",
                    "返工原因回流模板和 SOP。",
                ],
            },
        ],
        "capability_title": "工单闭环工作台能力栈",
        "board_kicker": "工作看板",
        "board_title": "工单队列推进通道",
        "board_cards": [
            {"kicker": "主流程", "title": "受理到验收一条链", "desc": "不再只是把工单推出去，而是把执行和验收继续拉回主链路。"},
            {"kicker": "关键卡点", "title": "复核排队与回执缺口", "desc": "当前节奏真正卡在验收席位和现场留痕不完整，不在建单按钮本身。"},
            {"kicker": "协同动作", "title": "值长、班组、质检同屏", "desc": "高优先级工单必须在同一视图下看到归口、执行和复核的责任切换。"},
            {"kicker": "交付形态", "title": "闭环结果可直接归档", "desc": "完成后的工单应自带回执、返工分析和经验沉淀去向。"},
        ],
        "timeline_kicker": "近期节奏",
        "timeline_title": "智能工单最近动作",
        "timeline_steps": [
            {"tone": "success", "title": "WO-240312 已完成现场检修并进入复核", "time": "3 分钟前", "desc": "现场班组已补齐措施与照片，当前只待质检回执。"},
            {"tone": "primary", "title": "AI 为 3 张新单生成责任人建议", "time": "14 分钟前", "desc": "已结合站点位置、技能标签和班次负载完成首轮推荐。"},
            {"tone": "warn", "title": "升压站保护工单超过建议派单时限", "time": "29 分钟前", "desc": "需值长直接裁决资源占用，避免继续转派。"},
            {"tone": "success", "title": "备件锁库状态已同步到工单面板", "time": "今天 10:05", "desc": "箱变温控相关材料已完成可发放校核。"},
        ],
    },
    "power-trading": {
        "workspace_kpis": [
            {"icon": "monitoring", "value": "428.5", "label": "实时均价"},
            {"icon": "schedule", "value": "16:30", "label": "报价锁窗"},
            {"icon": "show_chart", "value": "±6.8%", "label": "波动区间"},
            {"icon": "flash_on", "value": "12MW", "label": "偏差敞口"},
            {"icon": "paid", "value": "+18.6万", "label": "测算收益"},
        ],
        "overview_cards": [
            {"kicker": "当前重点", "title": "先把盘面结构看清，再谈报价", "desc": "交易工作台不应该一上来就是报价按钮，而是先让盘面、价差和负荷变化被看懂。"},
            {"kicker": "策略原则", "title": "主策略和备用策略并排", "desc": "高波动日不能只输出一条报价建议，必须保留切换条件和执行边界。"},
            {"kicker": "风险控制", "title": "收益和止损必须同屏", "desc": "偏差敞口、履约约束和异常盘面止损线必须在同一页上被前置展示。"},
            {"kicker": "复盘目标", "title": "盘后结果回流次日策略", "desc": "工作台不止服务盘中动作，还要把盘后复盘沉淀成第二天的基线。"},
        ],
        "operating_kicker": "业务主线",
        "operating_title": "电力交易工作台的三层组织方式",
        "operating_sections": [
            {
                "label": "市场层",
                "title": "先判断价差和盘面方向",
                "desc": "日前、现货和中长期必须在同一视图里看价差结构，交易员先看市场，不先看结论。",
                "bullets": [
                    "盘前预判与盘中修正保持同一链路。",
                    "晚高峰价格和负荷误差单独看。",
                    "异常盘面优先进入观察位。",
                ],
            },
            {
                "label": "策略层",
                "title": "把可执行策略而不是单点报价放中间",
                "desc": "工作台中心应该是主策略、备用策略和切换条件，而不是孤立的一组数值。",
                "bullets": [
                    "稳健、平衡、进取三套口径并排。",
                    "高价段保留上浮空间提示。",
                    "切换条件直接给到交易席位。",
                ],
            },
            {
                "label": "风控层",
                "title": "偏差敞口和止损线前置",
                "desc": "真正防止策略失真的不是预测准确率本身，而是偏差敞口和止损边界是否持续可见。",
                "bullets": [
                    "偏差敞口持续更新。",
                    "合约履约约束单独提示。",
                    "盘后复盘回流策略基线。",
                ],
            },
        ],
        "capability_title": "交易决策工作台能力栈",
        "board_kicker": "工作看板",
        "board_title": "交易策略推进通道",
        "board_cards": [
            {"kicker": "主流程", "title": "盘前建模到盘后复盘闭环", "desc": "报价动作只是中间一环，真正的工作台应该覆盖建模、确认、执行和复盘全链路。"},
            {"kicker": "关键卡点", "title": "晚高峰决策与偏差控制", "desc": "今天的风险重点不在全天均值，而在高价时段和预测误差同时放大。"},
            {"kicker": "协同动作", "title": "交易员与风控并排决策", "desc": "策略确认不能脱离风控审核，收益口径和止损边界必须同时确认。"},
            {"kicker": "交付形态", "title": "直接可执行的策略带", "desc": "输出结果应直接包含报价带、观察位、备用策略和复盘口径。"},
        ],
        "timeline_kicker": "近期节奏",
        "timeline_title": "电力交易最近动作",
        "timeline_steps": [
            {"tone": "success", "title": "V3 报价策略已生成并进入人工确认", "time": "2 分钟前", "desc": "主策略与两套保守方案已经完成初步对比。"},
            {"tone": "primary", "title": "晚高峰价格预测上调 3.2%", "time": "11 分钟前", "desc": "午后盘面走强，18:00 后策略需保留额外上浮空间。"},
            {"tone": "warn", "title": "18:00 后负荷误差区间扩大", "time": "24 分钟前", "desc": "偏差成本有吞噬收益的风险，风控边界需要同步收紧。"},
            {"tone": "success", "title": "中长期与现货价差图已更新", "time": "今天 09:40", "desc": "套利机会窗口已重新标注到策略台面。"},
        ],
    },
    "smart-office": {
        "workspace_kpis": [
            {"icon": "groups", "value": "17项", "label": "待认领事项"},
            {"icon": "description", "value": "5份", "label": "纪要草稿"},
            {"icon": "fact_check", "value": "6项", "label": "待确认项"},
            {"icon": "menu_book", "value": "12条", "label": "知识候选"},
            {"icon": "hub", "value": "高", "label": "协同热度"},
        ],
        "overview_cards": [
            {"kicker": "当前重点", "title": "把会后动作真正收口", "desc": "办公工作台不能只会生成纪要，重点是把 owner、deadline 和依赖关系一起拉出来。"},
            {"kicker": "整理原则", "title": "先提炼结论，再展开正文", "desc": "高层和跨部门场景都更需要快速看结论、争议点和待确认项，而不是先读流水账。"},
            {"kicker": "协同接口", "title": "把碎片动作回收到统一任务视图", "desc": "聊天、文档和邮件里的后续动作都要重新收口，不能继续分散漂流。"},
            {"kicker": "沉淀目标", "title": "高频场景要转成模板和知识", "desc": "经营会、周例会、复盘会适合继续沉淀模板，降低综合部重复劳动。"},
        ],
        "operating_kicker": "业务主线",
        "operating_title": "智慧办公工作台的三段闭环",
        "operating_sections": [
            {
                "label": "纪要",
                "title": "先抽决策，再写正文",
                "desc": "办公模块的第一层不是排版，而是把结论、争议点和待确认项抽出来，形成可执行摘要。",
                "bullets": [
                    "会议结论和争议点优先前置。",
                    "需上报事项单独标出。",
                    "高层场景保留快速阅读层。",
                ],
            },
            {
                "label": "任务",
                "title": "从纪要直接拆 owner 与时间",
                "desc": "会后动作不能靠人工二次整理，工作台要直接生成任务、责任边界和回执节点。",
                "bullets": [
                    "纪要直接拆出 owner 和 deadline。",
                    "跨部门事项统一收口到同一页。",
                    "待确认与已认领状态分层显示。",
                ],
            },
            {
                "label": "知识",
                "title": "把可复用内容继续沉淀",
                "desc": "会议结束只是第一步，复盘、周报和专题经验要继续进入模板库和知识库。",
                "bullets": [
                    "纪要、模板、知识条目分层归档。",
                    "高频会议优先模板化。",
                    "知识管理员只接可复用结论。",
                ],
            },
        ],
        "capability_title": "办公协同工作台能力栈",
        "board_kicker": "工作看板",
        "board_title": "会后协同推进通道",
        "board_cards": [
            {"kicker": "主流程", "title": "会中抽取到会后推进闭环", "desc": "从纪要初稿、任务认领到知识归档，整个会后推进过程应保持一条链。"},
            {"kicker": "关键卡点", "title": "跨部门确认和 owner 缺口", "desc": "现在真正拖慢推进的，是任务边界不清和待确认项长期悬空。"},
            {"kicker": "协同动作", "title": "综合部与业务部门同屏协作", "desc": "综合部负责口径和结构，各业务部门负责认领和时限，两类动作必须同步可见。"},
            {"kicker": "交付形态", "title": "纪要、任务、知识三分流", "desc": "页面输出应明确哪些进入纪要、哪些进入任务、哪些进入知识沉淀。"},
        ],
        "timeline_kicker": "近期节奏",
        "timeline_title": "智慧办公最近动作",
        "timeline_steps": [
            {"tone": "success", "title": "经营例会纪要已完成结构化整理", "time": "5 分钟前", "desc": "关键结论、争议点和待确认项已经抽出，等待最终口径确认。"},
            {"tone": "primary", "title": "3 个跨部门事项已自动分配 owner", "time": "16 分钟前", "desc": "当前任务链已经同步到协同视图，等待各部门确认时限。"},
            {"tone": "warn", "title": "交易策略文档仍缺 2 个责任确认", "time": "31 分钟前", "desc": "若今天内不回执，纪要和任务的推进口径都会继续分裂。"},
            {"tone": "success", "title": "运维月报模板已更新到团队知识库", "time": "今天 08:50", "desc": "本周复用频次高的模板已进入公共知识空间。"},
        ],
    },
}


MODULE_FRONTENDS = {
    "weather-siting": {
        "route": "/modules/weather-siting/app",
        "headline": "风场选址决策工作台",
        "summary": "把风资源、硬约束、接入走廊和投前经济性放进同一张工作台，直接收敛优选、备选和待踏勘站址。",
        "metrics": [
            {"label": "候选风区", "value": "18", "note": "已纳入首轮比选"},
            {"label": "红线图层", "value": "27", "note": "生态、噪声、运输同步校核"},
            {"label": "接入走廊", "value": "3条", "note": "正在并网方案收敛"},
            {"label": "优选站址", "value": "2个", "note": "具备进入可研条件"},
        ],
        "fields": [
            {"label": "项目名称", "type": "text", "name": "project", "placeholder": "例如：华北沿海风电场一期"},
            {"label": "区域范围", "type": "text", "name": "region", "placeholder": "例如：河北沿海北段 + 中段 80km 走廊"},
            {"label": "容量与机型边界", "type": "text", "name": "capacity", "placeholder": "例如：300MW / 8.5MW 机型 / 轮毂高度 140m"},
            {"label": "比选目标", "type": "textarea", "name": "goal", "placeholder": "描述本轮要收敛的候选区、红线限制、接入距离阈值、收益底线和是否输出踏勘清单"},
        ],
        "quick_actions": ["生成候选区漏斗", "比对接入走廊", "输出踏勘红线", "锁定优选/备选"],
        "result_title": "选址分析结果",
        "result_lines": [
            "先对风资源、接入走廊和生态红线做硬筛，再把候选区分成优选、备选和观察池。",
            "同步给出道路吊装、微地形修正和并网距离对收益的影响，避免只看风速高低。",
            "对于仍未闭合的约束项，直接标记成踏勘或外部确认动作，而不是留在结论里模糊处理。",
            "最终输出可直接进入投前评审或现场踏勘安排的站址清单。",
        ],
        "board_title": "候选风区收敛看板",
        "board_columns": ["候选区", "资源面", "工程面", "并网面", "当前结论"],
        "board_rows": [
            ["WS-A01 沿海北段", "7.2m/s，湍流稳", "道路与吊装已闭合", "送出 31km，可接入 220kV", "优选 - 进入可研口径"],
            ["WS-A02 沿海中段", "6.9m/s，样本完整", "场内道路可达", "送出 36km，方案可行", "备选 - 保持并网复核"],
            ["WS-B01 丘陵西侧", "6.6m/s，微地形敏感", "吊装道路待核验", "送出 28km，站址需重排", "观察 - 先安排踏勘"],
            ["WS-B02 平原东部", "6.3m/s，稳定一般", "施工友好", "送出 49km，经济性承压", "剔除边缘 - 仅保留兜底"],
        ],
    },
    "smart-workorder": {
        "route": "/modules/smart-workorder/app",
        "headline": "智能工单闭环指挥台",
        "summary": "把受理分级、责任派发、现场留痕、备件依赖和验收归档连成一条工单闭环主链，不再只是列表式派单。",
        "metrics": [
            {"label": "待分派", "value": "9", "note": "需在 SLA 内完成归口"},
            {"label": "超时风险", "value": "4", "note": "集中在升压站与保护类"},
            {"label": "待验收", "value": "6", "note": "执行完成待复核"},
            {"label": "备件锁定", "value": "13项", "note": "已联动仓储校验"},
        ],
        "fields": [
            {"label": "所属站点", "type": "text", "name": "site", "placeholder": "例如：北段风场 / 升压站 / 35kV 集电线"},
            {"label": "设备名称", "type": "text", "name": "asset", "placeholder": "例如：3# 风机变桨系统"},
            {"label": "SLA 等级", "type": "text", "name": "severity", "placeholder": "紧急 / 重要 / 一般 / 计划"},
            {"label": "故障与处置背景", "type": "textarea", "name": "issue", "placeholder": "描述故障现象、影响范围、已做临时措施、所需备件和希望达到的闭环状态"},
        ],
        "quick_actions": ["生成标准工单", "拉起智能派单", "检查备件依赖", "推进验收闭环"],
        "result_title": "工单处理方案",
        "result_lines": [
            "系统会先把故障描述拆成设备、等级、影响范围和临时措施，再决定是否升级到值长裁决。",
            "派单建议会同时匹配责任班组、技能标签、地理位置和备件可用性，减少重复转派。",
            "执行过程中自动收集照片、工时和材料消耗，为验收与返工分析保留证据链。",
            "闭环输出不是简单完结，而是带着验收结果、超时原因和经验沉淀一起归档。",
        ],
        "board_title": "工单闭环队列",
        "board_columns": ["工单", "当前环节", "SLA", "阻塞点", "下一动作"],
        "board_rows": [
            ["WO-240315 3# 变桨", "待分级/待派单", "15 分钟内", "现场影响范围未写清", "补故障等级后自动派单"],
            ["WO-240312 升压站保护", "执行中", "当班闭环", "高级工程师占用中", "值长保留优先资源"],
            ["WO-240308 箱变温控", "待验收", "18:00 前回执", "照片与回执缺 1 项", "质检复核后归档"],
            ["WO-240305 SCADA 通讯", "复盘归档", "已满足", "重复故障原因待沉淀", "沉淀模板建单规则"],
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
        "headline": "电力交易策略指挥台",
        "summary": "把盘前建模、盘中修正、报价锁窗、偏差风控和盘后复盘压进同一个策略台面，让交易动作可切换、可解释、可追责。",
        "metrics": [
            {"label": "实时均价", "value": "428.5", "note": "元/MWh"},
            {"label": "报价窗口", "value": "16:30", "note": "距锁窗剩余 3 小时"},
            {"label": "偏差敞口", "value": "12MW", "note": "晚高峰仍需压降"},
            {"label": "今日收益", "value": "+18.6", "note": "万元，按平衡策略测算"},
        ],
        "fields": [
            {"label": "交易时段", "type": "text", "name": "period", "placeholder": "例如：明日日前 / 本周现货 / 月度中长期"},
            {"label": "目标市场", "type": "text", "name": "market", "placeholder": "例如：华北现货 / 华东日前 / 南方电网"},
            {"label": "组合仓位", "type": "text", "name": "portfolio", "placeholder": "例如：现货 320MW / 合约 180MW / 可调余量 40MW"},
            {"label": "风险边界", "type": "text", "name": "capacity", "placeholder": "例如：偏差不超过 12MW / 保底收益 15 万"},
            {"label": "策略目标", "type": "textarea", "name": "goal", "placeholder": "描述本轮希望锁定的报价带、风险偏好、偏差边界、套利关注点和是否输出备用策略"},
        ],
        "quick_actions": [
            "生成主/备报价带",
            "重算晚高峰策略",
            "检查偏差敞口",
            "对比合约与现货",
            "输出风控止损线",
            "生成盘后复盘"
        ],
        "result_title": "AI交易分析报告",
        "result_lines": [
            "系统会先拉齐市场窗口、仓位结构和风险边界，再同时生成主策略和备用策略，而不是只给一个报价数。",
            "报价建议会结合实时行情、历史同期和负荷预测，对高价时段单独给出上浮或保守处理建议。",
            "偏差敞口、履约约束和异常行情止损线会与收益机会同屏展示，避免只追求高价。",
            "最终输出可直接给交易员执行的报价带、观察位和盘后复盘口径。",
        ],
        "board_title": "盘中策略执行看板",
        "board_columns": ["交易窗", "当前价格", "价差判断", "风险位", "建议动作"],
        "board_rows": [
            ["日前 08:00-12:00", "¥435/MWh", "↗ 价差扩大", "低", "适度增加报量"],
            ["日前 12:00-18:00", "¥520/MWh", "→ 平衡区", "中", "按主策略执行"],
            ["日前 18:00-22:00", "¥680/MWh", "↗ 峰段走强", "中高", "保留上浮空间"],
            ["现货实时", "¥428/MWh", "↘ 回落 3%", "中", "观察敞口再调仓"],
            ["中长期履约", "¥395/MWh", "→ 稳定", "低", "按合约兑现"],
        ],
    },
    "smart-office": {
        "route": "/modules/smart-office/app",
        "headline": "智慧办公协同工作台",
        "summary": "把会议结论、任务拆解、跨部门确认和知识沉淀放进一条办公闭环，页面中心不再只是纪要生成器，而是协同调度台。",
        "metrics": [
            {"label": "待认领事项", "value": "17", "note": "跨部门动作偏多"},
            {"label": "纪要草稿", "value": "5", "note": "待确认口径"},
            {"label": "决策待确认", "value": "6", "note": "需 owner 回执"},
            {"label": "知识候选", "value": "12", "note": "本周待归档"},
        ],
        "fields": [
            {"label": "办公场景", "type": "text", "name": "topic", "placeholder": "例如：经营例会 / 项目协同 / 专题复盘"},
            {"label": "会议或项目主题", "type": "text", "name": "subject", "placeholder": "例如：二季度交易经营复盘 / 海上项目推进会"},
            {"label": "协同部门", "type": "text", "name": "team", "placeholder": "例如：综合部、运维部、交易部、工程部"},
            {"label": "处理目标", "type": "textarea", "name": "goal", "placeholder": "描述需要生成的纪要口径、任务拆解方式、责任边界、截止时间和是否沉淀到知识库"},
        ],
        "quick_actions": ["生成决策纪要", "拆解跨部门任务", "汇总待确认项", "沉淀知识条目"],
        "result_title": "智能办公助手",
        "result_lines": [
            "系统会先抽取决策、争议点和待确认项，再生成纪要正文，避免输出一段无法执行的流水账。",
            "会后动作会直接拆成 owner、deadline、依赖关系和回执节点，减少综合部二次整理。",
            "跨部门事项统一进入同一跟踪视图，文档、聊天和邮件里的碎片动作会被回收到任务主线。",
            "可复用内容会自动区分为纪要、模板和知识条目三类归档去向。",
        ],
        "board_title": "会后协同推进看板",
        "board_columns": ["事项", "来源", "责任人", "状态", "沉淀去向"],
        "board_rows": [
            ["经营例会纪要", "经营会录音 + PPT", "综合部", "待高层口径确认", "管理复盘库"],
            ["交易策略跟进", "会议决议", "交易部", "待 owner 回执", "专题知识页"],
            ["运维月报整编", "周报素材池", "运维部", "进行中", "月报模板库"],
            ["项目推进清单", "跨部门协同会", "工程部", "已拆任务", "项目知识空间"],
        ],
    },
}

MODULE_FRONTEND_DETAILS = {
    "weather-siting": {
        "command_deck": [
            {"label": "决策窗口", "value": "72h", "note": "本轮站址比选将在 72 小时内完成首轮收敛。", "meta": "需同步设计院与接入评审"},
            {"label": "测风覆盖", "value": "91%", "note": "候选区域已有观测、遥感与历史模型覆盖。", "meta": "缺口集中在丘陵西侧"},
            {"label": "接入半径", "value": "38km", "note": "当前优选方案平均接入距离维持在经济区间。", "meta": "超过 45km 需单独立项论证"},
            {"label": "约束项", "value": "5项", "note": "生态红线、道路运输、噪声敏感点已纳入筛查。", "meta": "其中 2 项需补现场踏勘"},
        ],
        "pipeline_steps": [
            {"label": "资源拼图", "state": "done"},
            {"label": "硬约束筛除", "state": "done"},
            {"label": "接入比选", "state": "active"},
            {"label": "踏勘校核", "state": "pending"},
            {"label": "投前结论", "state": "pending"},
        ],
        "story_kicker": "场景剖面",
        "story_title": "风场选址决策分层",
        "story_blocks": [
            {"label": "资源面", "title": "风速与湍流双校核", "desc": "把年平均风速、湍流强度和极端天气一起纳入同一评价面。", "meta": "先看稳定性，再看峰值收益"},
            {"label": "工程面", "title": "道路与吊装约束", "desc": "不只看风资源，必须同步考虑运输半径、道路坡度和场内施工。", "meta": "工程可实施性决定能否进可研"},
            {"label": "并网面", "title": "送出距离与消纳", "desc": "将接入系统方案、线路长度和消纳压力一并并入经济性判断。", "meta": "接入不是附属项，是主变量"},
            {"label": "投资面", "title": "收益与风险并排", "desc": "把收益弹性、审批风险和地面约束同时放在管理层口径里。", "meta": "适合直接进入投前评审"},
        ],
        "timeline_kicker": "推进节奏",
        "timeline_title": "本轮站址收敛路径",
        "timeline_steps": [
            {"title": "候选区拉齐", "when": "T+0", "desc": "统一容量假设、机型边界和基础测风样本，避免前提条件不一致。"},
            {"title": "优先级排序", "when": "T+1", "desc": "按资源、接入、工程三类权重形成初步排序，锁定领先梯队。"},
            {"title": "风险剔除", "when": "T+2", "desc": "把生态红线、道路冲突和长送出方案作为硬约束复核。"},
            {"title": "输出结论", "when": "T+3", "desc": "形成优选、备选和观察项三档结论，进入投资评审材料。"},
        ],
        "matrix_kicker": "约束矩阵",
        "matrix_title": "站址硬约束对照",
        "matrix_columns": ["约束项", "A01", "A02", "B01"],
        "matrix_rows": [
            ["接入距离", "优", "良", "中"],
            ["道路可达", "优", "良", "待核验"],
            ["生态边界", "已核", "已核", "待终审"],
            ["施工难度", "中", "中", "偏高"],
        ],
        "workspace_cards": [
            {"label": "主线目标", "value": "压缩比选轮次", "note": "优先形成 2 个可研级候选点，减少反复拉通。"},
            {"label": "当前瓶颈", "value": "地形核验", "note": "坡度与吊装道路冲突仍需工程组二次确认。"},
            {"label": "交付节点", "value": "周五 18:00", "note": "输出站址排序、关键风险和接入边界说明。"},
        ],
        "intake_checklist": [
            "明确项目容量、机型边界和最低风速收益线，避免分析目标过宽。",
            "补齐区域坐标、测风周期和已知限制条件，减少 AI 推断偏差。",
            "如果已做过现场踏勘，录入道路、地质和红线反馈，结果会更稳定。",
            "需要报告时，优先说明是投前筛选、可研深化还是业主汇报场景。",
        ],
        "delivery_tracks": [
            {"badge": "勘测", "title": "地理与道路核验", "desc": "把优选站址同步给工程勘测，确认坡度、运输和施工可达性。"},
            {"badge": "接入", "title": "电网接入复核", "desc": "对优选点位做接入距离、升压站方案和消纳约束复核。"},
            {"badge": "汇报", "title": "投资决策材料", "desc": "整理站址排序、收益敏感性和约束清单，形成管理层汇报稿。"},
        ],
        "ai_recommendations": [
            {"tag": "优先级", "title": "先锁定沿海北段与中段", "desc": "两处风资源和接入条件最均衡，适合作为首轮主推方案。"},
            {"tag": "补数", "title": "丘陵西侧补一轮高程校核", "desc": "当前模型对微地形影响的误差较大，建议补 DEM 与现场踏勘。"},
            {"tag": "风控", "title": "提前拉通生态红线", "desc": "后置处理生态约束会直接拖慢可研节奏，建议前置排查。"},
        ],
        "collab_items": [
            {"role": "投资分析", "task": "核对容量边界、IRR 下限和优选站址收益敏感性。", "eta": "今天 15:00"},
            {"role": "工程设计", "task": "复核道路运输、场内道路与吊装平台可实施性。", "eta": "今天 18:30"},
            {"role": "并网专责", "task": "确认接入系统方案和远距离送出约束。", "eta": "明天 10:00"},
        ],
        "health_rings": [
            {"label": "数据完备", "value": 96, "color": "var(--primary)"},
            {"label": "模型稳定", "value": 89, "color": "var(--primary-soft)"},
            {"label": "现场同步", "value": 76, "color": "#d97706"},
        ],
        "health_bars": [
            {"label": "栅格生成", "width": "44%", "value": "4.8m", "tone": "normal"},
            {"label": "约束校验", "width": "62%", "value": "12项", "tone": "warn"},
        ],
        "activity_feed": [
            {"tone": "success", "title": "沿海北段新增测风样本已合并入当前模型", "time": "3 分钟前"},
            {"tone": "primary", "title": "AI 已重算候选站址收益敏感性区间", "time": "11 分钟前"},
            {"tone": "warn", "title": "丘陵西侧运输条件存在二次核验提醒", "time": "22 分钟前"},
            {"tone": "success", "title": "接入距离约束已同步更新到优选排序", "time": "39 分钟前"},
            {"tone": "primary", "title": "可研资料包已推送至项目共享空间", "time": "1 小时前"},
        ],
        "risk_items": [
            {"level": "P1", "title": "接入距离拉长", "desc": "B02 站址如果沿现有接入方案推进，经济性边际会明显收窄。"},
            {"level": "P1", "title": "生态范围未终审", "desc": "当前保护区边界来自历史版本，需与地方最新图层复核。"},
            {"level": "P2", "title": "丘陵微地形误差", "desc": "风速外推结果偏乐观，建议补充高程和湍流修正。"},
        ],
        "resource_cards": [
            {"label": "分析席位", "value": "3/4", "note": "尚可并行处理 1 个候选区"},
            {"label": "踏勘窗口", "value": "2天", "note": "本周仍可安排一次现场核验"},
            {"label": "评审槽位", "value": "周五", "note": "管理层评审会已预留 30 分钟"},
        ],
        "board_kpis": [
            {"label": "优选命中率", "value": "67%", "note": "与历史投产项目相似度较高"},
            {"label": "收益弹性", "value": "+8.4%", "note": "优选站址对电价波动更稳健"},
            {"label": "约束闭合", "value": "13/16", "note": "剩余 3 项待外部确认"},
            {"label": "资料齐套", "value": "82%", "note": "报告可先出预审版"},
        ],
        "board_briefs": [
            "A01 和 A02 已形成明显领先梯队，适合进入下一轮工程深化。",
            "B01 风速稳定但施工条件不明朗，建议保留为成本受限场景备选。",
            "B02 的核心问题不是风资源，而是接入距离带来的整体经济性压力。",
        ],
        "next_actions": [
            {"badge": "立即", "title": "锁定优选站址名单", "desc": "以 A01、A02 为主推，B01 作为补位方案进入汇报稿。"},
            {"badge": "今日", "title": "同步设计与接入团队", "desc": "要求两侧在今天内反馈工程可行性与并网边界。"},
            {"badge": "本周", "title": "输出投前比选结论", "desc": "形成可直接进入投资评审的简版结论与风险提示。"},
        ],
    },
    "smart-workorder": {
        "command_deck": [
            {"label": "待分派", "value": "9单", "note": "紧急与重要工单集中在升压站和主机系统。", "meta": "2 单超过建议受理时限"},
            {"label": "闭环率", "value": "93%", "note": "本月闭环率保持高位，但质检返工略有上升。", "meta": "返工主要来自记录不完整"},
            {"label": "平均处理", "value": "5.6h", "note": "现场执行速度稳定，验收等待是主要耗时点。", "meta": "比上周缩短 0.8h"},
            {"label": "备件命中", "value": "84%", "note": "常用件满足率较高，特殊备件仍需提前锁库。", "meta": "本周 3 单存在缺件风险"},
        ],
        "pipeline_steps": [
            {"label": "受理分级", "state": "done"},
            {"label": "责任派发", "state": "done"},
            {"label": "现场执行", "state": "active"},
            {"label": "验收回执", "state": "pending"},
            {"label": "归档复盘", "state": "pending"},
        ],
        "story_kicker": "闭环地图",
        "story_title": "工单主链路拆解",
        "story_blocks": [
            {"label": "受理", "title": "故障信息标准化", "desc": "先把设备、等级、影响范围和临时措施收敛成统一受理结构。", "meta": "减少后续重复沟通"},
            {"label": "派单", "title": "责任与资源匹配", "desc": "依据班次、技能、位置和备件情况自动推荐最合适执行人。", "meta": "避免高优先级工单被转派"},
            {"label": "执行", "title": "现场动作可追溯", "desc": "照片、备件、时长和措施都纳入同一时间线，便于复核。", "meta": "现场留痕决定闭环质量"},
            {"label": "验收", "title": "结果回执与沉淀", "desc": "不只验是否修好，还要沉淀返工原因和可复用经验。", "meta": "直接影响月度闭环口径"},
        ],
        "timeline_kicker": "闭环时序",
        "timeline_title": "高优先级工单推进节奏",
        "timeline_steps": [
            {"title": "5 分钟内分级", "when": "受理后", "desc": "完成故障定级和停机影响判断，决定是否进入升级池。"},
            {"title": "15 分钟内派单", "when": "值长确认", "desc": "锁定责任班组、备件清单和现场响应时间。"},
            {"title": "执行中留痕", "when": "现场处理", "desc": "同步记录措施、照片与材料使用，支撑后续质量复核。"},
            {"title": "当班前闭环", "when": "班末前", "desc": "高优先级工单必须进入验收或明确延迟原因。"},
        ],
        "matrix_kicker": "工单矩阵",
        "matrix_title": "优先级与处理策略",
        "matrix_columns": ["等级", "派单时限", "响应方式", "升级条件"],
        "matrix_rows": [
            ["紧急", "5 分钟", "值长直派", "停机扩大/保护动作"],
            ["重要", "15 分钟", "智能派单", "影响产能超过阈值"],
            ["一般", "30 分钟", "班组池分配", "连续重复发生"],
            ["计划", "当日排程", "统一编排", "窗口被压缩"],
        ],
        "workspace_cards": [
            {"label": "主线目标", "value": "提升一次闭环", "note": "减少返工和补录，把工单从执行拉到真正闭环。"},
            {"label": "当前瓶颈", "value": "验收排队", "note": "复核和回执不及时，影响整体节奏和统计口径。"},
            {"label": "交付节点", "value": "今日班末", "note": "高优先级工单需全部进入执行或验收状态。"},
        ],
        "intake_checklist": [
            "先写清设备、故障等级、影响范围和当前状态，避免系统生成过泛的工单。",
            "如果现场已做过临时处置，请录入措施和剩余风险，方便派单和验收判断。",
            "涉及备件时尽量补型号、数量和仓储信息，可直接联动备件校核。",
            "如果希望自动派单，请明确站点、班组和可用资源边界。",
        ],
        "delivery_tracks": [
            {"badge": "派单", "title": "责任人与班组匹配", "desc": "根据技能、位置和班次自动推荐责任人，避免重复转派。"},
            {"badge": "执行", "title": "现场处理与留痕", "desc": "同步照片、措施、备件和时间线，保证后续复核可追溯。"},
            {"badge": "验收", "title": "质量复核与归档", "desc": "按工艺要求完成验收结论、回执和经验沉淀。"},
        ],
        "ai_recommendations": [
            {"tag": "优先", "title": "升压站保护类工单前置处理", "desc": "该类故障影响范围大，建议直接占用高级工程师资源。"},
            {"tag": "优化", "title": "对重复故障启用模板建单", "desc": "变桨、温控、通讯类问题可以统一字段模板，提高受理速度。"},
            {"tag": "质控", "title": "执行环节增加照片校验", "desc": "本月返工多来自现场记录不足，建议在提交前做必填校验。"},
        ],
        "collab_items": [
            {"role": "值长", "task": "确认高优先级工单排序与资源占用，决定是否升级。", "eta": "实时"},
            {"role": "现场班组", "task": "接收派单后补齐处理措施、备件使用和照片回传。", "eta": "30 分钟"},
            {"role": "质检复核", "task": "针对待验收工单完成回执判定和经验归档。", "eta": "今天 17:30"},
        ],
        "health_rings": [
            {"label": "受理效率", "value": 92, "color": "var(--primary)"},
            {"label": "执行到位", "value": 86, "color": "var(--primary-soft)"},
            {"label": "复核负载", "value": 71, "color": "#d97706"},
        ],
        "health_bars": [
            {"label": "平均响应", "width": "39%", "value": "18m", "tone": "normal"},
            {"label": "超时风险", "width": "57%", "value": "4单", "tone": "warn"},
        ],
        "activity_feed": [
            {"tone": "success", "title": "WO-240312 已完成现场检修并提交复核", "time": "2 分钟前"},
            {"tone": "primary", "title": "AI 已为 3 张新工单生成责任人建议", "time": "9 分钟前"},
            {"tone": "warn", "title": "升压站保护工单超过建议派单时限", "time": "17 分钟前"},
            {"tone": "success", "title": "备件库已确认箱变温控所需材料可发放", "time": "33 分钟前"},
            {"tone": "primary", "title": "返工分析清单同步至班组长工作台", "time": "52 分钟前"},
        ],
        "risk_items": [
            {"level": "P1", "title": "待验收堆积", "desc": "如果复核继续排队，已完成工单无法及时闭环，月度口径会失真。"},
            {"level": "P1", "title": "高优先级转派", "desc": "频繁转派会放大故障停机时间，需值长直接裁决责任归口。"},
            {"level": "P2", "title": "备件记录不全", "desc": "材料去向无法回溯，后续可能影响成本归集与经验复盘。"},
        ],
        "resource_cards": [
            {"label": "现场班组", "value": "6组", "note": "其中 2 组正在升压站区域"},
            {"label": "复核席位", "value": "2席", "note": "下午高峰前建议不要再压单"},
            {"label": "备件状态", "value": "稳", "note": "常用件满足率高于 80%"},
        ],
        "board_kpis": [
            {"label": "今日受理", "value": "21", "note": "较昨日增加 4 单"},
            {"label": "一次通过", "value": "88%", "note": "返工率仍有优化空间"},
            {"label": "升级工单", "value": "3", "note": "均为停机影响项"},
            {"label": "归档完整", "value": "91%", "note": "照片与回执缺口持续收敛"},
        ],
        "board_briefs": [
            "当前队列的真实瓶颈在验收，不在新建工单数量本身。",
            "升压站和通讯类问题影响面更大，适合保持单独优先级池。",
            "模板建单和照片校验能直接改善返工与统计质量。 ",
        ],
        "next_actions": [
            {"badge": "立即", "title": "清理超时待派单", "desc": "优先处理停机影响与保护动作相关工单，避免二次升级。"},
            {"badge": "今天", "title": "拉平复核负载", "desc": "把待验收队列分配给两名复核席位并设回执时限。"},
            {"badge": "本周", "title": "固化模板建单规则", "desc": "对高频故障沉淀字段模板和推荐处理路径。"},
        ],
    },
    "smart-guard": {
        "command_deck": [
            {"label": "告警池", "value": "6条", "note": "紧急和重要告警都已挂接处置动作。", "meta": "夜班接手前需清零紧急项"},
            {"label": "巡检进度", "value": "73%", "note": "本班次巡检路线已跑完大部分核心点位。", "meta": "升压站仍有 2 处待复看"},
            {"label": "在线率", "value": "98.2%", "note": "绝大多数设备运行稳定，通讯链路整体正常。", "meta": "个别边缘点位数据抖动"},
            {"label": "联动动作", "value": "14次", "note": "本班次已触发告警确认、派单和广播联动。", "meta": "2 次由人工接管"},
        ],
        "workspace_cards": [
            {"label": "主线目标", "value": "告警压降", "note": "先让紧急告警进入受控状态，再安排巡检补位。"},
            {"label": "当前瓶颈", "value": "跨班交接", "note": "交接信息不完整会造成同一告警重复研判。"},
            {"label": "交付节点", "value": "换班前", "note": "需要留下清晰的异常清单和持续观察项。"},
        ],
        "intake_checklist": [
            "录入当前班次、监控区域和重点设备，方便系统收敛告警优先级。",
            "如果已有人工处置动作，请补充结果和剩余观察时间窗。",
            "涉及多点位异常时，建议写明是否存在共因或通讯异常怀疑。",
            "交接班场景下优先保留仍在观察中的事项和下一班动作。",
        ],
        "delivery_tracks": [
            {"badge": "联动", "title": "告警自动分级", "desc": "按严重度分发给工单、广播和值长席位。"},
            {"badge": "巡检", "title": "巡检路线重排", "desc": "把持续观察点位自动插入下一轮巡检路径。"},
            {"badge": "交班", "title": "日志与交接纪要", "desc": "自动沉淀班次关注点、处置动作和未闭合事项。"},
        ],
        "ai_recommendations": [
            {"tag": "处置", "title": "齿轮箱紧急告警保持单独观察窗", "desc": "避免被普通温度告警淹没，需持续跟踪振动与温升联动。"},
            {"tag": "路线", "title": "优先巡检升压站与 5# 风机", "desc": "当前风险集中在这两处，适合插队进入下轮巡检。"},
            {"tag": "交接", "title": "夜班前固化观察项", "desc": "把持续观察告警和已做动作写入交接模板，减少重复研判。"},
        ],
        "collab_items": [
            {"role": "值长席位", "task": "确认紧急告警处置级别和是否直接升级工单。", "eta": "实时"},
            {"role": "巡检班组", "task": "对重点点位补拍现场状态并回传确认结果。", "eta": "45 分钟"},
            {"role": "交接班", "task": "汇总观察项、处置链路和下一班次动作建议。", "eta": "换班前"},
        ],
        "health_rings": [
            {"label": "设备在线", "value": 98, "color": "var(--primary)"},
            {"label": "告警确认", "value": 88, "color": "var(--primary-soft)"},
            {"label": "班次负载", "value": 74, "color": "#d97706"},
        ],
        "health_bars": [
            {"label": "联动耗时", "width": "34%", "value": "11s", "tone": "normal"},
            {"label": "告警积压", "width": "51%", "value": "2条", "tone": "warn"},
        ],
        "activity_feed": [
            {"tone": "success", "title": "5# 风机齿轮箱告警已联动至工单中心", "time": "1 分钟前"},
            {"tone": "primary", "title": "巡检路线已按当前风险重排", "time": "6 分钟前"},
            {"tone": "warn", "title": "箱变温度异常持续观察未结束", "time": "14 分钟前"},
            {"tone": "success", "title": "SCADA 通讯中断已恢复并完成确认", "time": "28 分钟前"},
            {"tone": "primary", "title": "交接班草稿已生成并等待值长确认", "time": "43 分钟前"},
        ],
        "risk_items": [
            {"level": "P1", "title": "跨班信息断层", "desc": "观察项如果不写清动作边界，下一班会重复排查。"},
            {"level": "P1", "title": "齿轮箱告警持续", "desc": "虽然已派单，但若温升继续扩大需要直接升级现场响应。"},
            {"level": "P2", "title": "边缘点位数据抖动", "desc": "可能掩盖真实异常，建议同时看视频与历史趋势。"},
        ],
        "resource_cards": [
            {"label": "值守席位", "value": "2席", "note": "主值守与联动审核都在线"},
            {"label": "巡检车辆", "value": "3台", "note": "可再插入 1 条补巡路线"},
            {"label": "换班倒计时", "value": "2h", "note": "需在交班前清理高优先级事项"},
        ],
        "board_kpis": [
            {"label": "本班告警", "value": "18", "note": "高于昨日同期 2 条"},
            {"label": "已联动", "value": "14", "note": "联动占比保持高位"},
            {"label": "巡检完成", "value": "8/11", "note": "剩余任务集中在重点区域"},
            {"label": "交接待办", "value": "4", "note": "均已形成草稿"},
        ],
        "board_briefs": [
            "当前告警数量不算高，关键在于少数高优先级项要持续盯住。",
            "巡检任务基本可控，问题更多出在交接信息是否完整。",
            "边缘点位的通讯抖动建议和实际异常分开跟踪，避免误判。",
        ],
        "next_actions": [
            {"badge": "立即", "title": "继续跟踪齿轮箱告警", "desc": "把振动、温度和派单动作保持在同一观察视图中。"},
            {"badge": "本班", "title": "完成升压站补巡", "desc": "补齐照片和确认结果，降低交班后续追问成本。"},
            {"badge": "换班前", "title": "确认交接纪要", "desc": "把未闭合事项、责任人和下一班动作一次写清。"},
        ],
    },
    "power-trading": {
        "command_deck": [
            {"label": "报价窗口", "value": "16:30", "note": "明日日前报价剩余 3 个小时，需完成策略确认。", "meta": "当前建议偏稳健报价"},
            {"label": "波动区间", "value": "±6.8%", "note": "午后尖峰价格弹性增强，套利窗口仍在。", "meta": "晚高峰风险也同步抬升"},
            {"label": "偏差敞口", "value": "12MW", "note": "负荷预测与现货执行之间仍有可压降空间。", "meta": "重点看 18:00 后负荷波动"},
            {"label": "策略版本", "value": "V3", "note": "综合历史同期、实时行情与风险偏好生成。", "meta": "已对比 2 套保守方案"},
        ],
        "pipeline_steps": [
            {"label": "盘前建模", "state": "done"},
            {"label": "盘中修正", "state": "done"},
            {"label": "报价锁窗", "state": "active"},
            {"label": "执行盯盘", "state": "pending"},
            {"label": "盘后复盘", "state": "pending"},
        ],
        "story_kicker": "策略栈",
        "story_title": "交易决策三层结构",
        "story_blocks": [
            {"label": "行情层", "title": "实时价差盯盘", "desc": "把现货、日前和中长期价差放在同一视图，先识别有没有结构性机会。", "meta": "不做脱离市场的静态报价"},
            {"label": "预测层", "title": "负荷与价格联判", "desc": "负荷预测不是孤立指标，而是直接影响偏差成本和执行空间。", "meta": "晚高峰尤其关键"},
            {"label": "策略层", "title": "稳健与进取并行", "desc": "同时给出主策略和备用策略，便于交易员根据盘中变化切换。", "meta": "策略不是单一结论"},
            {"label": "风控层", "title": "收益与止损同屏", "desc": "把收益机会和偏差止损边界一起输出，避免只追高价。", "meta": "先活下来，再多赚"},
        ],
        "timeline_kicker": "交易时序",
        "timeline_title": "从盘前到盘后的一轮动作",
        "timeline_steps": [
            {"title": "盘前预判", "when": "09:00", "desc": "生成初版价格带、负荷曲线和风险假设。"},
            {"title": "午后修正", "when": "13:30", "desc": "结合实时行情和偏差变化，重算晚高峰执行区间。"},
            {"title": "报价确认", "when": "16:00", "desc": "交易员与风控共同确认主策略和备用策略。"},
            {"title": "盘后复盘", "when": "收市后", "desc": "核对策略命中、偏差成本和套利兑现情况，形成次日参考。"},
        ],
        "matrix_kicker": "策略对照",
        "matrix_title": "报价模式选择表",
        "matrix_columns": ["模式", "适用场景", "收益倾向", "风险敞口"],
        "matrix_rows": [
            ["稳健", "高波动日", "中", "低"],
            ["平衡", "常规行情", "中高", "中"],
            ["进取", "趋势明确", "高", "高"],
            ["应急", "异常盘面", "保底", "可控"],
        ],
        "workspace_cards": [
            {"label": "主线目标", "value": "稳收益控偏差", "note": "不追逐短期极值，先保证可执行性与收益质量。"},
            {"label": "当前瓶颈", "value": "尖峰决策", "note": "晚高峰价格可能继续走高，但偏差成本也同步放大。"},
            {"label": "交付节点", "value": "收市前", "note": "需要输出报价、风险区间和备用应对策略。"},
        ],
        "intake_checklist": [
            "先写清交易时段、目标市场和交易容量，否则策略建议会过泛。",
            "如果存在风险偏好、保底收益或偏差约束，请在分析目标里明确写出。",
            "涉及多市场对比时，建议说明主市场和备用市场，便于生成优先级。",
            "需要管理层汇报时，额外写明是否要套利机会、风险说明或执行建议。",
        ],
        "delivery_tracks": [
            {"badge": "策略", "title": "报价策略生成", "desc": "基于负荷预测、历史成交和价格区间生成可执行报价带。"},
            {"badge": "风险", "title": "偏差与波动评估", "desc": "同时评估价格波动、预测误差和履约风险。"},
            {"badge": "执行", "title": "下游交易动作", "desc": "输出报量、调仓、观察位和复盘口径，便于交易员直接接单。"},
        ],
        "ai_recommendations": [
            {"tag": "窗口", "title": "18:00-22:00 保留上浮空间", "desc": "该时段仍有上涨动能，但不建议过度追价。"},
            {"tag": "风控", "title": "把偏差控制放在第一优先级", "desc": "当前负荷预测虽准，但尾段误差仍可能吞掉部分收益。"},
            {"tag": "套利", "title": "关注中长期与现货价差", "desc": "价差仍有利用空间，可做结构性优化而不是全面加仓。"},
        ],
        "collab_items": [
            {"role": "交易员", "task": "根据 AI 策略带完成最终报价确认与报量决策。", "eta": "16:00 前"},
            {"role": "风控岗", "task": "审核价格波动、偏差敞口和异常情景下的止损边界。", "eta": "16:10"},
            {"role": "经营分析", "task": "同步收益影响和管理层关注口径，用于会后复盘。", "eta": "16:30"},
        ],
        "health_rings": [
            {"label": "行情接入", "value": 97, "color": "var(--primary)"},
            {"label": "预测可信", "value": 92, "color": "var(--primary-soft)"},
            {"label": "风险张力", "value": 69, "color": "#d97706"},
        ],
        "health_bars": [
            {"label": "数据延迟", "width": "28%", "value": "4s", "tone": "normal"},
            {"label": "敞口占比", "width": "63%", "value": "中", "tone": "warn"},
        ],
        "activity_feed": [
            {"tone": "success", "title": "V3 报价策略已生成并进入人工确认", "time": "2 分钟前"},
            {"tone": "primary", "title": "晚高峰价格预测上调 3.2%", "time": "7 分钟前"},
            {"tone": "warn", "title": "18:00 后负荷误差区间有所放大", "time": "16 分钟前"},
            {"tone": "success", "title": "中长期与现货价差对比图已更新", "time": "27 分钟前"},
            {"tone": "primary", "title": "今日收益复盘模板已自动填充", "time": "41 分钟前"},
        ],
        "risk_items": [
            {"level": "P1", "title": "晚高峰偏差风险", "desc": "价格上涨虽有利，但预测误差也在扩大，需留安全边界。"},
            {"level": "P1", "title": "市场情绪过热", "desc": "实时现货情绪偏强，盲目追价可能导致报价和执行脱节。"},
            {"level": "P2", "title": "合约履约挤压", "desc": "若临时上调报量，需同时核对中长期履约约束。"},
        ],
        "resource_cards": [
            {"label": "策略版本", "value": "3套", "note": "稳健、平衡、进取均已生成"},
            {"label": "复盘样本", "value": "180天", "note": "已接入历史同期成交数据"},
            {"label": "交易席位", "value": "在线", "note": "人工确认链路保持可用"},
        ],
        "board_kpis": [
            {"label": "尖峰收益", "value": "+6.2%", "note": "按平衡策略测算"},
            {"label": "偏差成本", "value": "-1.4%", "note": "较昨日进一步压降"},
            {"label": "套利机会", "value": "2处", "note": "需风控确认后执行"},
            {"label": "策略一致", "value": "84%", "note": "AI 与人工判断整体收敛"},
        ],
        "board_briefs": [
            "当前市场并非单边激进做多环境，平衡策略更适合今天的风险结构。",
            "真正决定收益质量的不是报价高低，而是高价时段的执行准确度。",
            "V3 已经把历史同期和实时行情融合，适合作为本轮主策略基线。",
        ],
        "next_actions": [
            {"badge": "立即", "title": "确认 V3 报价带", "desc": "将晚高峰保留上浮空间，同时保住整体偏差边界。"},
            {"badge": "收市前", "title": "同步风控止损口径", "desc": "给交易员明确异常价格和负荷偏差的处理规则。"},
            {"badge": "盘后", "title": "沉淀今日复盘", "desc": "记录策略命中、偏差成本和套利机会兑现情况。"},
        ],
    },
    "smart-office": {
        "command_deck": [
            {"label": "待办池", "value": "17项", "note": "跨部门事项占比高，需要明确责任和时间窗。", "meta": "其中 5 项今天必须推进"},
            {"label": "纪要草稿", "value": "5份", "note": "会议纪要已预生成，待补关键结论和责任人。", "meta": "2 份需要高层口径审阅"},
            {"label": "知识沉淀", "value": "12条", "note": "本周新增经验与模板已进入待归档队列。", "meta": "优先归整交易与运维专题"},
            {"label": "协同热度", "value": "高", "note": "跨部门任务密集，适合用统一任务视图收敛。", "meta": "沟通碎片明显偏多"},
        ],
        "pipeline_steps": [
            {"label": "会议抽取", "state": "done"},
            {"label": "决议整理", "state": "done"},
            {"label": "任务拆分", "state": "active"},
            {"label": "跨部确认", "state": "pending"},
            {"label": "知识归档", "state": "pending"},
        ],
        "story_kicker": "办公主线",
        "story_title": "会议到任务再到知识的闭环",
        "story_blocks": [
            {"label": "会议", "title": "结论先于正文", "desc": "纪要优先抽出结论、争议点和需上报事项，不再只是流水账。", "meta": "适合高层快速过目"},
            {"label": "任务", "title": "从纪要直接拆待办", "desc": "把会议结论直接转成 owner、deadline 和依赖关系，避免二次整理。", "meta": "纪要不是终点"},
            {"label": "协同", "title": "跨部门动作归一", "desc": "把聊天、文档和邮件里的碎片动作收回到统一任务视图。", "meta": "减少责任漂移"},
            {"label": "知识", "title": "高频场景模板化", "desc": "复盘、周报、经营会等内容沉淀成模板，降低重复劳动。", "meta": "沉淀后才能复用"},
        ],
        "timeline_kicker": "办公节奏",
        "timeline_title": "一场会议后的标准推进链",
        "timeline_steps": [
            {"title": "会中抽取", "when": "实时", "desc": "记录关键决策、分歧和需要继续确认的问题。"},
            {"title": "会后 10 分钟", "when": "纪要初稿", "desc": "自动生成纪要与待办草稿，先供组织者确认口径。"},
            {"title": "会后 30 分钟", "when": "任务认领", "desc": "各部门完成 owner、deadline 和依赖条件确认。"},
            {"title": "当日归档", "when": "班末前", "desc": "将可复用结论沉淀到模板或知识条目中。"},
        ],
        "matrix_kicker": "协同矩阵",
        "matrix_title": "办公场景与输出物",
        "matrix_columns": ["场景", "核心输出", "主要角色", "沉淀去向"],
        "matrix_rows": [
            ["经营会", "决策纪要", "综合部/经营分析", "管理复盘库"],
            ["项目协同", "任务清单", "各业务部门", "项目知识页"],
            ["专题复盘", "经验条目", "专题 owner", "专题模板库"],
            ["日常周例会", "跟进清单", "部门经理", "周报模板"],
        ],
        "workspace_cards": [
            {"label": "主线目标", "value": "把会后动作收口", "note": "不是只生成纪要，而是把责任和截止时间真正落地。"},
            {"label": "当前瓶颈", "value": "跨部门确认", "note": "任务分散在聊天和文档里，责任边界不清晰。"},
            {"label": "交付节点", "value": "今天下班前", "note": "要完成纪要、任务拆分和知识归档三个动作。"},
        ],
        "intake_checklist": [
            "输入办公场景、参与部门和处理需求，系统会据此切换生成模板。",
            "如果是会议纪要，尽量补关键决策、争议点和待确认事项。",
            "如果要做任务分配，建议写明 deadline、owner 候选和协同部门。",
            "希望沉淀到知识库时，补一句适用范围和后续复用场景。",
        ],
        "delivery_tracks": [
            {"badge": "纪要", "title": "会议内容结构化", "desc": "自动拆出结论、待办、风险和需上报信息。"},
            {"badge": "协同", "title": "任务分配与提醒", "desc": "将事项拆给责任部门并附上截止时间和依赖说明。"},
            {"badge": "知识", "title": "经验沉淀归档", "desc": "把复用价值高的内容转成知识条目或模板。"},
        ],
        "ai_recommendations": [
            {"tag": "整理", "title": "先收口跨部门动作", "desc": "本页最适合先把责任人、截止时间和依赖关系写透。"},
            {"tag": "复用", "title": "把高频会议模板沉淀下来", "desc": "周例会、经营会、复盘会应直接复用模板减少重复整理。"},
            {"tag": "知识", "title": "把结论和经验分层归档", "desc": "纪要保留时序，经验条目提炼规则，便于后续检索。"},
        ],
        "collab_items": [
            {"role": "综合部", "task": "校对纪要口径，确认会议结论和上报版本。", "eta": "今天 14:30"},
            {"role": "各业务部门", "task": "认领任务、补充完成时限与依赖前置条件。", "eta": "今天 17:00"},
            {"role": "知识管理员", "task": "筛选适合沉淀的内容并入库到知识模块。", "eta": "明天上午"},
        ],
        "health_rings": [
            {"label": "任务清晰", "value": 90, "color": "var(--primary)"},
            {"label": "纪要完整", "value": 85, "color": "var(--primary-soft)"},
            {"label": "协同负载", "value": 73, "color": "#d97706"},
        ],
        "health_bars": [
            {"label": "生成耗时", "width": "31%", "value": "9s", "tone": "normal"},
            {"label": "待确认项", "width": "58%", "value": "6项", "tone": "warn"},
        ],
        "activity_feed": [
            {"tone": "success", "title": "经营例会纪要已完成结构化整理", "time": "4 分钟前"},
            {"tone": "primary", "title": "3 个跨部门任务已自动分配 owner", "time": "10 分钟前"},
            {"tone": "warn", "title": "交易策略文档仍缺 2 个责任确认", "time": "19 分钟前"},
            {"tone": "success", "title": "运维月报模板已更新到团队知识库", "time": "31 分钟前"},
            {"tone": "primary", "title": "本周沉淀清单已同步至知识管理员", "time": "47 分钟前"},
        ],
        "risk_items": [
            {"level": "P1", "title": "任务责任模糊", "desc": "如果 owner 不明确，纪要生成再完整也难以推进执行。"},
            {"level": "P1", "title": "跨部门确认滞后", "desc": "当前多个事项卡在确认链路，建议设置统一回执时间。"},
            {"level": "P2", "title": "知识归档滞后", "desc": "会议内容容易沉没在聊天和文档里，复用价值被浪费。"},
        ],
        "resource_cards": [
            {"label": "模板库", "value": "28份", "note": "覆盖会议、周报、复盘等高频场景"},
            {"label": "协同事项", "value": "8项", "note": "跨部门动作需要统一追踪"},
            {"label": "知识队列", "value": "12条", "note": "可在本周内批量归档"},
        ],
        "board_kpis": [
            {"label": "今日纪要", "value": "5", "note": "2 份待高层口径确认"},
            {"label": "任务认领", "value": "76%", "note": "仍需补足 owner 信息"},
            {"label": "文档摘要", "value": "14份", "note": "已形成可复用结论"},
            {"label": "知识入库", "value": "9条", "note": "本周累计更新"},
        ],
        "board_briefs": [
            "办公模块的关键不是多生成内容，而是把动作、责任和沉淀打通。",
            "目前跨部门事项较多，统一任务视图比单纯发纪要更有价值。",
            "高频场景模板化后，综合部的整理成本还可以继续下降。",
        ],
        "next_actions": [
            {"badge": "立即", "title": "确认 owner 和 deadline", "desc": "优先把跨部门事项的责任边界写清。"},
            {"badge": "今天", "title": "完成纪要与任务联动", "desc": "从纪要直接生成待办，不再手工二次拆分。"},
            {"badge": "本周", "title": "沉淀模板与知识条目", "desc": "将高频会议与复盘场景转成可复用模板。"},
        ],
    },
}

MODULE_FRONTEND_STRUCTURE = {
    "weather-siting": {
        "operating_kicker": "业务主线",
        "operating_title": "风场选址不是一张地图，而是三段式决策收敛",
        "operating_sections": [
            {
                "label": "第一段",
                "title": "先做资源与红线初筛",
                "desc": "先把测风覆盖、极端天气和生态硬约束拉到同一张筛选面，避免候选区从一开始就方向偏掉。",
                "bullets": [
                    "统一容量假设、机型边界和收益底线。",
                    "先剔除生态、噪声和运输明显冲突区域。",
                    "把测风缺口单独标为补数动作，不混进结论。",
                ],
            },
            {
                "label": "第二段",
                "title": "再做工程与并网复筛",
                "desc": "真正拉开候选点差距的，往往不是风速本身，而是道路吊装、接入距离和消纳条件的组合约束。",
                "bullets": [
                    "把接入半径、升压站方案和送出距离一起比。",
                    "同步核验道路坡度、吊装平台和施工窗口。",
                    "对长距离送出方案直接做经济性敏感提示。",
                ],
            },
            {
                "label": "第三段",
                "title": "最后输出优选、备选与踏勘清单",
                "desc": "结论不只写排名，而是明确哪些可以进可研、哪些保留、哪些必须先踏勘或外部确认。",
                "bullets": [
                    "形成优选、备选、观察池三档清单。",
                    "把未闭合约束拆成踏勘项和外部确认项。",
                    "直接给出可进入投前评审的管理口径。",
                ],
            },
        ],
    },
    "smart-workorder": {
        "operating_kicker": "业务主线",
        "operating_title": "智能工单的核心不是派出去，而是闭回来",
        "operating_sections": [
            {
                "label": "受理段",
                "title": "故障信息先标准化",
                "desc": "工单质量从第一步就决定了后续效率，设备对象、等级、影响面和临时措施必须一次收清。",
                "bullets": [
                    "先明确设备、站点、等级和影响范围。",
                    "把临时处置和剩余风险写进受理结构。",
                    "对重复故障优先复用模板建单。",
                ],
            },
            {
                "label": "执行段",
                "title": "责任、资源和备件一起调度",
                "desc": "派单不能只看人名，必须同时考虑班次、技能、位置和备件命中，否则高优先级工单还是会反复转派。",
                "bullets": [
                    "高优先级工单直接走值长裁决链。",
                    "智能推荐责任班组并联动备件校核。",
                    "执行过程统一留痕照片、工时和材料使用。",
                ],
            },
            {
                "label": "闭环段",
                "title": "验收与复盘进入同一口径",
                "desc": "页面结构要把待验收、返工原因和经验沉淀放在主链路里，而不是完成执行后就结束。",
                "bullets": [
                    "把验收排队视为主瓶颈而不是附属动作。",
                    "回执缺口直接提示到责任节点。",
                    "把返工原因沉淀为模板和标准 SOP。",
                ],
            },
        ],
    },
    "power-trading": {
        "operating_kicker": "业务主线",
        "operating_title": "电力交易页面要围绕市场、策略、风控三层展开",
        "operating_sections": [
            {
                "label": "市场层",
                "title": "先判断盘面和价差结构",
                "desc": "交易员需要先看到市场窗口、价格带和负荷变化，不是先看到一个结论性的报价数字。",
                "bullets": [
                    "把日前、现货和中长期放进同一观察面。",
                    "晚高峰单独看价格弹性和负荷误差。",
                    "用盘前预判和盘中修正形成同一条链路。",
                ],
            },
            {
                "label": "策略层",
                "title": "主策略与备用策略并排",
                "desc": "报价建议应保留切换空间，尤其在价格走强但预测误差放大的时段，不能只给单一路径。",
                "bullets": [
                    "输出稳健、平衡、进取三类策略口径。",
                    "把高价时段单列成独立处理建议。",
                    "给交易员明确观察位与切换条件。",
                ],
            },
            {
                "label": "风控层",
                "title": "收益机会与止损边界同屏",
                "desc": "真正好的交易页面要让偏差敞口、履约约束和异常行情止损一起出现，避免只追收益曲线。",
                "bullets": [
                    "偏差敞口单列并持续更新。",
                    "把异常盘面和止损口径前置展示。",
                    "盘后复盘直接回流到次日策略基线。",
                ],
            },
        ],
    },
    "smart-office": {
        "operating_kicker": "业务主线",
        "operating_title": "智慧办公应该围绕纪要、任务、知识三段闭环组织",
        "operating_sections": [
            {
                "label": "纪要段",
                "title": "先抽决策，再写正文",
                "desc": "办公场景最怕纪要写得很多但无法执行，所以第一层必须先把结论、争议点和待确认项抽出来。",
                "bullets": [
                    "把会议结论、争议点和需上报项前置。",
                    "纪要正文服务于确认口径，而不是堆材料。",
                    "对高层场景保留快速过目的摘要层。",
                ],
            },
            {
                "label": "任务段",
                "title": "从纪要直接拆责任与时间",
                "desc": "页面中心要承接会后推进，把 owner、deadline 和依赖条件收口，而不是让用户再去聊天软件里补动作。",
                "bullets": [
                    "会后动作直接拆成 owner 和截止时间。",
                    "跨部门事项统一放进同一跟踪视图。",
                    "待确认项和已认领项要分层显示。",
                ],
            },
            {
                "label": "知识段",
                "title": "把可复用内容沉淀成模板",
                "desc": "会议结束不等于流程结束，复盘、周报和专题经验要继续回流到模板库和知识条目。",
                "bullets": [
                    "把纪要、模板、知识条目分开归档。",
                    "高频会议优先沉淀为标准模板。",
                    "知识管理员只接可复用内容，不接原始碎片。",
                ],
            },
        ],
    },
}

MODULE_ENTRY_CONFIG = {
    "weather-siting": {
        "tone": "flow",
        "icon": "air",
        "home_description": "风场选址决策台。",
        "footer": "资源筛选 / 工程复筛 / 优选备选",
        "portal_summary": "资源筛选、工程复筛、投前定版。",
        "highlights": ["资源筛选", "工程复筛", "优选/备选/踏勘"],
    },
    "smart-workorder": {
        "tone": "collab",
        "icon": "assignment",
        "home_description": "现场工单指挥台。",
        "footer": "受理 / 派单 / 验收沉淀",
        "portal_summary": "受理派单、现场执行、验收归档。",
        "highlights": ["受理分级", "责任派单", "验收沉淀"],
    },
    "power-trading": {
        "tone": "publish",
        "icon": "query_stats",
        "home_description": "电力交易策略台。",
        "footer": "盘前建模 / 主备策略 / 偏差风控",
        "portal_summary": "盘前建模、交易执行、偏差风控。",
        "highlights": ["盘前建模", "主/备策略", "偏差风控"],
    },
    "smart-office": {
        "tone": "capability",
        "icon": "workspaces",
        "home_description": "经营协同办公台。",
        "footer": "纪要 / 任务认领 / 知识归档",
        "portal_summary": "纪要生成、任务推进、知识归档。",
        "highlights": ["会议纪要", "任务认领", "知识归档"],
    },
}

for _slug, _module in MODULE_WORKSPACES.items():
    _module.update(MODULE_WORKSPACE_DETAILS.get(_slug, {}))

for _slug, _page in MODULE_FRONTENDS.items():
    _page.update(MODULE_FRONTEND_DETAILS.get(_slug, {}))
    _page.update(MODULE_FRONTEND_STRUCTURE.get(_slug, {}))
    if _slug in MODULE_WORKSPACES:
        MODULE_WORKSPACES[_slug]["primary_href"] = _page["route"]


def _entry_metrics_from_workspace(module: dict) -> list[str]:
    metrics = module.get("workspace_kpis") or []
    return [f"{item['value']} {item['label']}" for item in metrics[:3]]


def _build_module_snapshot(slug: str) -> dict | None:
    workspace = MODULE_WORKSPACES.get(slug)
    frontend = MODULE_FRONTENDS.get(slug)
    if workspace is None:
        return None

    workspace_copy = deepcopy(workspace)
    frontend_copy = deepcopy(frontend) if frontend is not None else None
    entry_cfg = MODULE_ENTRY_CONFIG.get(slug, {})
    entry_metrics = _entry_metrics_from_workspace(workspace_copy)

    entry = {
        "slug": slug,
        "name": workspace_copy["name"],
        "index": workspace_copy["index"],
        "tone": entry_cfg.get("tone", "flow"),
        "icon": entry_cfg.get("icon", "dashboard"),
        "description": entry_cfg.get("home_description", workspace_copy.get("description", "")),
        "footer": entry_cfg.get("footer", workspace_copy.get("tagline", "")),
        "pills": entry_metrics,
        "highlights": deepcopy(entry_cfg.get("highlights", workspace_copy.get("scenes", [])[:3])),
        "app_href": frontend_copy["route"] if frontend_copy is not None else workspace_copy["primary_href"],
        "workbench_href": f"/modules/{slug}",
        "secondary_href": workspace_copy["secondary_href"],
        "secondary_label": workspace_copy["secondary_label"],
        "portal_summary": entry_cfg.get("portal_summary", workspace_copy.get("description", "")),
        "metrics": entry_metrics,
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workspace": workspace_copy,
        "frontend": frontend_copy,
        "entry": entry,
    }


def _build_home_business_modules() -> list[dict]:
    modules: list[dict] = []
    for slug in ("weather-siting", "smart-workorder", "power-trading", "smart-office"):
        snapshot = _build_module_snapshot(slug)
        if snapshot is not None:
            modules.append(snapshot["entry"])
    return modules


PORTAL_SECTIONS = [
    {
        "title": "业务模块",
        "summary": "风场经营主入口。",
        "items": [
            {"name": "风场选址", "href": "/modules/weather-siting/app", "summary": "资源筛选、工程复筛、投前定版。"},
            {"name": "智能工单", "href": "/modules/smart-workorder/app", "summary": "受理派单、现场执行、验收归档。"},
            {"name": "智能值守", "href": "/data-platform", "summary": "监控总览、告警联动、巡检交接。"},
            {"name": "电力交易", "href": "/modules/power-trading/app", "summary": "盘前建模、交易执行、偏差风控。"},
            {"name": "智慧办公", "href": "/modules/smart-office/app", "summary": "纪要生成、任务推进、知识归档。"},
        ],
    },
    {
        "title": "AI 助手",
        "summary": "助手与协作入口。",
        "items": [
            {"name": "智能运维助手", "href": "/maintenance-assistant", "summary": "统一问答、诊断和运维建议入口。"},
            {"name": "开发版助手", "href": "/dev/assistant", "summary": "可编辑配置的开发版助手。"},
            {"name": "简易对话", "href": "/chat", "summary": "轻量聊天页。"},
            {"name": "多智能体协作", "href": "/multi-agent", "summary": "多智能体协同工作入口。"},
        ],
    },
    {
        "title": "知识与流程",
        "summary": "知识与编排入口。",
        "items": [
            {"name": "知识库", "href": "/knowledge", "summary": "知识库管理与检索。"},
            {"name": "本体可视化", "href": "/ontology", "summary": "本体与关系结构展示。"},
            {"name": "插件市场", "href": "/plugins", "summary": "插件浏览与管理。"},
            {"name": "应用中心", "href": "/apps", "summary": "平台应用与工具入口。"},
            {"name": "技能创建器", "href": "/skill-creator", "summary": "快速创建技能配置。"},
            {"name": "可视化工作流", "href": "/workflow", "summary": "工作流编排与流程搭建。"},
            {"name": "协作管理", "href": "/collaboration", "summary": "团队协作与流程管理。"},
        ],
    },
    {
        "title": "分析与运营",
        "summary": "分析与运营入口。",
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
            {"name": "回调管理", "href": "/webhooks", "summary": "回调配置与查看。"},
            {"name": "网络调试", "href": "/http-tools", "summary": "网络请求调试与测试。"},
        ],
    },
    {
        "title": "模型与实验",
        "summary": "训练与实验入口。",
        "items": [
            {"name": "因果推理", "href": "/causal-reasoning", "summary": "因果推理引擎页面。"},
            {"name": "因果链", "href": "/causal-chain", "summary": "因果链路分析。"},
            {"name": "因果树", "href": "/causal-tree", "summary": "因果树实验与示例。"},
            {"name": "高级推理", "href": "/reasoning", "summary": "推理实验页面。"},
            {"name": "模型微调", "href": "/finetune", "summary": "微调任务配置页面。"},
            {"name": "对比实验", "href": "/ab-testing", "summary": "实验对比和评估。"},
            {"name": "模型强化学习", "href": "/llm-rl", "summary": "强化学习与对齐实验入口。"},
            {"name": "训练流水线", "href": "/pipeline", "summary": "SFT 到 RLHF 流水线。"},
            {"name": "多模态", "href": "/multimodal", "summary": "多模态能力页面。"},
            {"name": "记忆系统", "href": "/memory", "summary": "持久化记忆与观察面板。"},
            {"name": "发布管理", "href": "/publish", "summary": "发布与交付入口。"},
            {"name": "配置预设", "href": "/config-presets", "summary": "配置模板与预设管理。"},
        ],
    },
    {
        "title": "平台与账号",
        "summary": "平台与账号入口。",
        "items": [
            {"name": "开发控制台", "href": "/dev", "summary": "平台开发总入口。"},
            {"name": "设置", "href": "/settings", "summary": "平台设置页面。"},
            {"name": "接口密钥", "href": "/api-keys", "summary": "平台接口密钥管理。"},
            {"name": "扩展管理", "href": "/extensions", "summary": "扩展与能力管理。"},
            {"name": "登录", "href": "/login", "summary": "用户登录页面。"},
            {"name": "注册", "href": "/register", "summary": "用户注册页面。"},
            {"name": "个人中心", "href": "/profile", "summary": "个人资料与账号信息。"},
        ],
    },
]


def _live_portal_sections() -> list[dict]:
    sections = deepcopy(PORTAL_SECTIONS)
    for section in sections:
        if section["title"] != "业务模块":
            continue
        live_items = []
        for slug in ("weather-siting", "smart-workorder", "power-trading", "smart-office"):
            snapshot = _build_module_snapshot(slug)
            if snapshot is not None:
                entry = snapshot["entry"]
                live_items.append(
                    {
                        "name": entry["name"],
                        "href": entry["app_href"],
                        "summary": entry["portal_summary"],
                        "tone": entry["tone"],
                        "icon": entry["icon"],
                        "footer": entry["footer"],
                        "pills": entry["pills"],
                        "highlights": entry["highlights"],
                        "metrics": entry["metrics"],
                        "workbench_href": entry["workbench_href"],
                        "secondary_href": entry["secondary_href"],
                        "secondary_label": entry["secondary_label"],
                        "primary_label": MODULE_WORKSPACES[slug]["primary_label"],
                    }
                )
        live_items.insert(
            2,
            {
                "name": "智能值守",
                "href": "/data-platform",
                "summary": "监控总览、告警联动、巡检交接。",
                "tone": "observe",
                "icon": "monitoring",
                "footer": "监控 / 告警 / 巡检 / 交接",
                "pills": ["18 条 告警", "8/11 巡检", "2h 换班窗口"],
                "metrics": ["18 条 告警", "8/11 巡检", "2h 换班窗口"],
                "highlights": ["监控总览", "联动处置", "交接班跟踪"],
                "secondary_href": "/monitoring",
                "secondary_label": "监控面板",
                "primary_label": "进入值守大屏",
            },
        )
        section["items"] = live_items
        break
    return sections


def _portal_allowed_targets() -> set[str]:
    return {
        item["href"]
        for section in _live_portal_sections()
        for item in section["items"]
    }


def _portal_iframe_src(href: str) -> str:
    if href == "/data-platform":
        return "/data-platform/?embed=1"
    if href.startswith("/"):
        separator = "&" if "?" in href else "?"
        return f"{href}{separator}embed=1"
    if href.startswith("/modules/") and href.endswith("/app"):
        return f"{href}?embed=1"
    return href


def _build_portal_sections(current_target: str | None = None) -> list[dict]:
    sections: list[dict] = []
    for section in _live_portal_sections():
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
    for section in _live_portal_sections():
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
    if current_target:
        return redirect(current_target)
    portal_sections = _build_portal_sections()
    total_features = sum(len(section["items"]) for section in portal_sections)
    return render_template(
        'portal.html',
        portal_sections=portal_sections,
        portal_total_features=total_features,
    )


@app.route('/simple')
def simple_home():
    """简洁主页 - 左侧功能导航，右侧对话界面"""
    return render_template('simple_home.html')


@app.route('/user')
def user_home():
    """兼容旧地址，跳转到风电运维智导助手"""
    return redirect(url_for('maintenance_assistant', **request.args))


@app.route('/developer')
@app.route('/dev')
def developer_home():
    """开发版 - 平台总入口"""
    return render_template('index.html', home_business_modules=_build_home_business_modules())


@app.route('/developer/assistant')
@app.route('/dev/assistant')
def developer_assistant():
    """开发版 - 可编辑的风电运维智导助手"""
    embedded = request.args.get("embed") == "1"
    return render_template('maintenance_assistant_dev.html', embedded=embedded, **_get_agent_tool_ui_options())


@app.route('/modules/<slug>')
def module_workspace(slug: str):
    """业务模块工作台。"""
    snapshot = _build_module_snapshot(slug)
    if snapshot is None:
        return redirect(url_for('portal_home'))
    embedded = request.args.get("embed") == "1"
    return render_template('module_workspace.html', module=snapshot["workspace"], embedded=embedded)


@app.route('/modules/<slug>/app')
def module_frontend(slug: str):
    """业务模块前端页面。"""
    snapshot = _build_module_snapshot(slug)
    if snapshot is None or snapshot["frontend"] is None:
        return redirect(url_for('portal_home'))
    embedded = request.args.get("embed") == "1"
    return render_template('module_frontend.html', module=snapshot["workspace"], page=snapshot["frontend"], embedded=embedded)


@app.route('/api/modules/<slug>/snapshot')
def module_snapshot_api(slug: str):
    """业务模块统一快照。"""
    snapshot = _build_module_snapshot(slug)
    if snapshot is None:
        return jsonify({"error": "module_not_found", "slug": slug}), 404
    return jsonify(snapshot)


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


@app.route('/api/dify/chat-messages', methods=['POST'])
def dify_proxy():
    """代理转发 Dify API，避免前端直连 localhost"""
    try:
        import http.client
        import json as _json

        req_data = request.get_data()
        conn = http.client.HTTPConnection('localhost', 3080, timeout=120)
        conn.request(
            'POST',
            '/v1/chat-messages',
            body=req_data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': request.headers.get('Authorization', ''),
            },
        )
        resp = conn.getresponse()

        def generate():
            try:
                while True:
                    chunk = resp.read(256)
                    if not chunk:
                        break
                    yield chunk
            finally:
                conn.close()

        return Response(
            generate(),
            status=resp.status,
            content_type=resp.getheader('Content-Type', 'text/event-stream'),
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            },
        )
    except Exception as e:
        logger.error(f"Dify proxy error: {e}")
        return jsonify({'error': str(e)}), 502


@app.route('/multi-agent')
def multi_agent():
    """多 Agent 协作"""
    embedded = request.args.get("embed") == "1"
    return render_template('multi_agent.html', embedded=embedded)



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
    embedded = request.args.get("embed") == "1"
    return render_template('knowledge.html', embedded=embedded)


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
def data_platform_home():
    """数据平台 - 风机监控可视化"""
    query = request.query_string.decode("utf-8")
    target = "/data-platform/"
    if query:
        target = f"{target}?{query}"
    return redirect(target)


@app.route('/data-platform/')
def data_platform_home_with_slash():
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
    embedded = request.args.get("embed") == "1"
    return render_template('collaboration.html', embedded=embedded)


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
