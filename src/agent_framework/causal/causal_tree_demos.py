#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因果推理树演示案例集
提供多个预设的演示场景
"""

DEMO_CASES = [
    {
        "id": "tech_innovation",
        "title": "科技创新影响",
        "cause": "公司发布革命性AI产品",
        "effect": "行业格局重塑",
        "context": "在竞争激烈的科技行业，新技术可能带来连锁反应",
        "tree": {
            "id": "root",
            "content": "公司发布革命性AI产品",
            "type": "cause",
            "confidence": 1.0,
            "children": [
                {
                    "id": "market_1",
                    "content": "市场关注度激增",
                    "type": "effect",
                    "confidence": 0.95,
                    "relation": "直接导致",
                    "children": [
                        {
                            "id": "media_1",
                            "content": "媒体大量报道",
                            "type": "effect",
                            "confidence": 0.9,
                            "relation": "引发",
                            "children": []
                        },
                        {
                            "id": "investor_1",
                            "content": "投资者信心增强",
                            "type": "effect",
                            "confidence": 0.85,
                            "relation": "带动",
                            "children": [
                                {
                                    "id": "stock_1",
                                    "content": "股价上涨",
                                    "type": "effect",
                                    "confidence": 0.8,
                                    "relation": "推动",
                                    "children": []
                                }
                            ]
                        }
                    ]
                },
                {
                    "id": "competitor_1",
                    "content": "竞争对手压力增大",
                    "type": "effect",
                    "confidence": 0.9,
                    "relation": "施加压力",
                    "children": [
                        {
                            "id": "strategy_1",
                            "content": "竞品加速研发",
                            "type": "effect",
                            "confidence": 0.85,
                            "relation": "迫使",
                            "children": []
                        },
                        {
                            "id": "market_share_1",
                            "content": "市场份额重新分配",
                            "type": "effect",
                            "confidence": 0.75,
                            "relation": "触发",
                            "children": []
                        }
                    ]
                },
                {
                    "id": "customer_1",
                    "content": "用户需求升级",
                    "type": "effect",
                    "confidence": 0.88,
                    "relation": "刺激",
                    "children": [
                        {
                            "id": "expectation_1",
                            "content": "行业标准提高",
                            "type": "effect",
                            "confidence": 0.82,
                            "relation": "推动",
                            "children": [
                                {
                                    "id": "industry_1",
                                    "content": "行业格局重塑",
                                    "type": "effect",
                                    "confidence": 0.78,
                                    "relation": "最终导致",
                                    "children": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    },
    {
        "id": "climate_change",
        "title": "气候变化影响",
        "cause": "全球气温持续上升",
        "effect": "生态系统崩溃",
        "context": "气候变化是一个复杂的全球性问题，影响多个领域",
        "tree": {
            "id": "root",
            "content": "全球气温持续上升",
            "type": "cause",
            "confidence": 1.0,
            "children": [
                {
                    "id": "ice_1",
                    "content": "极地冰川融化",
                    "type": "effect",
                    "confidence": 0.95,
                    "relation": "直接导致",
                    "children": [
                        {
                            "id": "sea_level_1",
                            "content": "海平面上升",
                            "type": "effect",
                            "confidence": 0.92,
                            "relation": "引发",
                            "children": [
                                {
                                    "id": "coastal_1",
                                    "content": "沿海城市被淹没",
                                    "type": "effect",
                                    "confidence": 0.85,
                                    "relation": "造成",
                                    "children": []
                                }
                            ]
                        }
                    ]
                },
                {
                    "id": "weather_1",
                    "content": "极端天气频发",
                    "type": "effect",
                    "confidence": 0.9,
                    "relation": "触发",
                    "children": [
                        {
                            "id": "disaster_1",
                            "content": "自然灾害增多",
                            "type": "effect",
                            "confidence": 0.88,
                            "relation": "带来",
                            "children": [
                                {
                                    "id": "economy_1",
                                    "content": "经济损失加剧",
                                    "type": "effect",
                                    "confidence": 0.8,
                                    "relation": "导致",
                                    "children": []
                                }
                            ]
                        },
                        {
                            "id": "agriculture_1",
                            "content": "农业生产受影响",
                            "type": "effect",
                            "confidence": 0.85,
                            "relation": "影响",
                            "children": [
                                {
                                    "id": "food_1",
                                    "content": "粮食危机",
                                    "type": "effect",
                                    "confidence": 0.75,
                                    "relation": "引发",
                                    "children": []
                                }
                            ]
                        }
                    ]
                },
                {
                    "id": "ecosystem_1",
                    "content": "生物多样性减少",
                    "type": "effect",
                    "confidence": 0.87,
                    "relation": "破坏",
                    "children": [
                        {
                            "id": "species_1",
                            "content": "物种灭绝加速",
                            "type": "effect",
                            "confidence": 0.82,
                            "relation": "加速",
                            "children": [
                                {
                                    "id": "collapse_1",
                                    "content": "生态系统崩溃",
                                    "type": "effect",
                                    "confidence": 0.7,
                                    "relation": "最终导致",
                                    "children": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    },
    {
        "id": "education_reform",
        "title": "教育改革影响",
        "cause": "实施素质教育改革",
        "effect": "人才培养模式转变",
        "context": "教育改革涉及学生、教师、家长等多方利益",
        "tree": {
            "id": "root",
            "content": "实施素质教育改革",
            "type": "cause",
            "confidence": 1.0,
            "children": [
                {
                    "id": "student_1",
                    "content": "学生学习方式改变",
                    "type": "effect",
                    "confidence": 0.92,
                    "relation": "促使",
                    "children": [
                        {
                            "id": "creativity_1",
                            "content": "创造力提升",
                            "type": "effect",
                            "confidence": 0.85,
                            "relation": "培养",
                            "children": [
                                {
                                    "id": "innovation_1",
                                    "content": "创新能力增强",
                                    "type": "effect",
                                    "confidence": 0.8,
                                    "relation": "提升",
                                    "children": []
                                }
                            ]
                        },
                        {
                            "id": "pressure_1",
                            "content": "应试压力减轻",
                            "type": "effect",
                            "confidence": 0.75,
                            "relation": "缓解",
                            "children": []
                        }
                    ]
                },
                {
                    "id": "teacher_1",
                    "content": "教师角色转变",
                    "type": "effect",
                    "confidence": 0.88,
                    "relation": "推动",
                    "children": [
                        {
                            "id": "method_1",
                            "content": "教学方法创新",
                            "type": "effect",
                            "confidence": 0.82,
                            "relation": "激发",
                            "children": []
                        },
                        {
                            "id": "training_1",
                            "content": "需要重新培训",
                            "type": "effect",
                            "confidence": 0.9,
                            "relation": "要求",
                            "children": []
                        }
                    ]
                },
                {
                    "id": "society_1",
                    "content": "社会评价体系变化",
                    "type": "effect",
                    "confidence": 0.8,
                    "relation": "影响",
                    "children": [
                        {
                            "id": "talent_1",
                            "content": "人才评价标准多元化",
                            "type": "effect",
                            "confidence": 0.78,
                            "relation": "促进",
                            "children": [
                                {
                                    "id": "model_1",
                                    "content": "人才培养模式转变",
                                    "type": "effect",
                                    "confidence": 0.75,
                                    "relation": "最终实现",
                                    "children": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    },
    {
        "id": "pandemic_impact",
        "title": "疫情影响分析",
        "cause": "全球疫情爆发",
        "effect": "社会运行模式改变",
        "context": "疫情对经济、社会、生活方式产生深远影响",
        "tree": {
            "id": "root",
            "content": "全球疫情爆发",
            "type": "cause",
            "confidence": 1.0,
            "children": [
                {
                    "id": "health_1",
                    "content": "公共卫生系统压力",
                    "type": "effect",
                    "confidence": 0.95,
                    "relation": "施加压力",
                    "children": [
                        {
                            "id": "medical_1",
                            "content": "医疗资源紧张",
                            "type": "effect",
                            "confidence": 0.9,
                            "relation": "导致",
                            "children": [
                                {
                                    "id": "reform_1",
                                    "content": "医疗体系改革",
                                    "type": "effect",
                                    "confidence": 0.8,
                                    "relation": "推动",
                                    "children": []
                                }
                            ]
                        }
                    ]
                },
                {
                    "id": "economy_1",
                    "content": "经济活动受限",
                    "type": "effect",
                    "confidence": 0.93,
                    "relation": "限制",
                    "children": [
                        {
                            "id": "business_1",
                            "content": "企业经营困难",
                            "type": "effect",
                            "confidence": 0.88,
                            "relation": "造成",
                            "children": [
                                {
                                    "id": "unemployment_1",
                                    "content": "失业率上升",
                                    "type": "effect",
                                    "confidence": 0.85,
                                    "relation": "引发",
                                    "children": []
                                }
                            ]
                        },
                        {
                            "id": "digital_1",
                            "content": "数字化转型加速",
                            "type": "effect",
                            "confidence": 0.9,
                            "relation": "促进",
                            "children": []
                        }
                    ]
                },
                {
                    "id": "lifestyle_1",
                    "content": "生活方式改变",
                    "type": "effect",
                    "confidence": 0.92,
                    "relation": "改变",
                    "children": [
                        {
                            "id": "remote_1",
                            "content": "远程办公普及",
                            "type": "effect",
                            "confidence": 0.88,
                            "relation": "推广",
                            "children": [
                                {
                                    "id": "work_model_1",
                                    "content": "工作模式重塑",
                                    "type": "effect",
                                    "confidence": 0.82,
                                    "relation": "重塑",
                                    "children": []
                                }
                            ]
                        },
                        {
                            "id": "social_1",
                            "content": "社交方式转变",
                            "type": "effect",
                            "confidence": 0.85,
                            "relation": "转变",
                            "children": [
                                {
                                    "id": "society_model_1",
                                    "content": "社会运行模式改变",
                                    "type": "effect",
                                    "confidence": 0.78,
                                    "relation": "最终导致",
                                    "children": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    },
    {
        "id": "ai_development",
        "title": "AI技术发展",
        "cause": "通用人工智能突破",
        "effect": "人类社会变革",
        "context": "AI技术的快速发展可能带来深刻的社会变革",
        "tree": {
            "id": "root",
            "content": "通用人工智能突破",
            "type": "cause",
            "confidence": 1.0,
            "children": [
                {
                    "id": "automation_1",
                    "content": "自动化水平提升",
                    "type": "effect",
                    "confidence": 0.95,
                    "relation": "提升",
                    "children": [
                        {
                            "id": "job_1",
                            "content": "传统岗位被替代",
                            "type": "effect",
                            "confidence": 0.88,
                            "relation": "替代",
                            "children": [
                                {
                                    "id": "employment_1",
                                    "content": "就业结构调整",
                                    "type": "effect",
                                    "confidence": 0.82,
                                    "relation": "调整",
                                    "children": []
                                }
                            ]
                        },
                        {
                            "id": "productivity_1",
                            "content": "生产效率大幅提高",
                            "type": "effect",
                            "confidence": 0.92,
                            "relation": "提高",
                            "children": []
                        }
                    ]
                },
                {
                    "id": "decision_1",
                    "content": "决策辅助能力增强",
                    "type": "effect",
                    "confidence": 0.9,
                    "relation": "增强",
                    "children": [
                        {
                            "id": "management_1",
                            "content": "管理模式革新",
                            "type": "effect",
                            "confidence": 0.85,
                            "relation": "革新",
                            "children": [
                                {
                                    "id": "organization_1",
                                    "content": "组织结构扁平化",
                                    "type": "effect",
                                    "confidence": 0.78,
                                    "relation": "推动",
                                    "children": []
                                }
                            ]
                        }
                    ]
                },
                {
                    "id": "ethics_1",
                    "content": "伦理问题凸显",
                    "type": "effect",
                    "confidence": 0.87,
                    "relation": "引发",
                    "children": [
                        {
                            "id": "regulation_1",
                            "content": "监管政策出台",
                            "type": "effect",
                            "confidence": 0.8,
                            "relation": "促使",
                            "children": [
                                {
                                    "id": "society_1",
                                    "content": "社会治理模式变革",
                                    "type": "effect",
                                    "confidence": 0.75,
                                    "relation": "带来",
                                    "children": []
                                }
                            ]
                        },
                        {
                            "id": "human_1",
                            "content": "人机关系重新定义",
                            "type": "effect",
                            "confidence": 0.82,
                            "relation": "重新定义",
                            "children": [
                                {
                                    "id": "transformation_1",
                                    "content": "人类社会变革",
                                    "type": "effect",
                                    "confidence": 0.7,
                                    "relation": "最终实现",
                                    "children": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    },
    {
        "id": "urbanization",
        "title": "城市化进程",
        "cause": "大规模城市化",
        "effect": "城乡结构重塑",
        "context": "快速城市化带来机遇和挑战",
        "tree": {
            "id": "root",
            "content": "大规模城市化",
            "type": "cause",
            "confidence": 1.0,
            "children": [
                {
                    "id": "population_1",
                    "content": "人口向城市集中",
                    "type": "effect",
                    "confidence": 0.95,
                    "relation": "驱动",
                    "children": [
                        {
                            "id": "housing_1",
                            "content": "住房需求激增",
                            "type": "effect",
                            "confidence": 0.9,
                            "relation": "引发",
                            "children": [
                                {
                                    "id": "price_1",
                                    "content": "房价上涨",
                                    "type": "effect",
                                    "confidence": 0.85,
                                    "relation": "推高",
                                    "children": []
                                }
                            ]
                        },
                        {
                            "id": "infrastructure_1",
                            "content": "基础设施压力",
                            "type": "effect",
                            "confidence": 0.88,
                            "relation": "施加压力",
                            "children": []
                        }
                    ]
                },
                {
                    "id": "rural_1",
                    "content": "农村人口减少",
                    "type": "effect",
                    "confidence": 0.92,
                    "relation": "导致",
                    "children": [
                        {
                            "id": "agriculture_1",
                            "content": "农业劳动力短缺",
                            "type": "effect",
                            "confidence": 0.85,
                            "relation": "造成",
                            "children": [
                                {
                                    "id": "modernization_1",
                                    "content": "农业现代化加速",
                                    "type": "effect",
                                    "confidence": 0.8,
                                    "relation": "促进",
                                    "children": []
                                }
                            ]
                        },
                        {
                            "id": "village_1",
                            "content": "乡村空心化",
                            "type": "effect",
                            "confidence": 0.82,
                            "relation": "形成",
                            "children": []
                        }
                    ]
                },
                {
                    "id": "economy_1",
                    "content": "经济结构转型",
                    "type": "effect",
                    "confidence": 0.9,
                    "relation": "推动",
                    "children": [
                        {
                            "id": "service_1",
                            "content": "服务业比重上升",
                            "type": "effect",
                            "confidence": 0.87,
                            "relation": "提升",
                            "children": [
                                {
                                    "id": "structure_1",
                                    "content": "城乡结构重塑",
                                    "type": "effect",
                                    "confidence": 0.78,
                                    "relation": "最终重塑",
                                    "children": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }
]


def get_demo_by_id(demo_id):
    """根据ID获取演示案例"""
    for demo in DEMO_CASES:
        if demo['id'] == demo_id:
            return demo
    return None


def get_all_demos():
    """获取所有演示案例"""
    return DEMO_CASES


def get_demo_list():
    """获取演示案例列表（不包含树数据）"""
    return [
        {
            'id': demo['id'],
            'title': demo['title'],
            'cause': demo['cause'],
            'effect': demo['effect'],
            'context': demo['context']
        }
        for demo in DEMO_CASES
    ]
