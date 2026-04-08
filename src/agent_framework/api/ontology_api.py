#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本体论因果推理 API
"""

from flask import Blueprint, jsonify, request
from agent_framework.causal.ontology_causal_engine import (
    Ontology, ObjectType, LinkType, PropertyDefinition,
    PropertyType, CausalStrength
)

ontology_api = Blueprint('ontology_api', __name__)

# 全局本体论实例
ontology = Ontology()


@ontology_api.route('/api/ontology/types', methods=['GET'])
def get_types():
    """获取所有类型"""
    return jsonify({
        'object_types': {
            type_id: {
                'id': obj_type.id,
                'name': obj_type.name,
                'description': obj_type.description,
                'icon': obj_type.icon,
                'color': obj_type.color
            }
            for type_id, obj_type in ontology.object_types.items()
        },
        'link_types': {
            type_id: {
                'id': link_type.id,
                'name': link_type.name,
                'description': link_type.description,
                'causal_strength': link_type.causal_strength.label if link_type.causal_strength else None
            }
            for type_id, link_type in ontology.link_types.items()
        }
    })


@ontology_api.route('/api/ontology/objects', methods=['GET'])
def get_objects():
    """获取所有对象"""
    return jsonify({
        'objects': [obj.to_dict() for obj in ontology.objects.values()]
    })


@ontology_api.route('/api/ontology/objects', methods=['POST'])
def create_object():
    """创建对象"""
    data = request.json
    obj = ontology.create_object(
        type_id=data['type_id'],
        properties=data.get('properties', {}),
        object_id=data.get('object_id')
    )
    if obj:
        return jsonify(obj.to_dict())
    return jsonify({'error': '创建失败'}), 400


@ontology_api.route('/api/ontology/links', methods=['GET'])
def get_links():
    """获取所有链接"""
    return jsonify({
        'links': [link.to_dict() for link in ontology.links.values()]
    })


@ontology_api.route('/api/ontology/links', methods=['POST'])
def create_link():
    """创建链接"""
    data = request.json
    link = ontology.create_link(
        type_id=data['type_id'],
        source_id=data['source_id'],
        target_id=data['target_id'],
        properties=data.get('properties', {}),
        confidence=data.get('confidence', 0.8)
    )
    if link:
        return jsonify(link.to_dict())
    return jsonify({'error': '创建失败'}), 400


@ontology_api.route('/api/ontology/causal_chain', methods=['POST'])
def get_causal_chain():
    """获取因果链"""
    data = request.json
    chains = ontology.get_causal_chain(
        start_id=data['start_id'],
        end_id=data['end_id'],
        max_depth=data.get('max_depth', 5)
    )
    return jsonify({'chains': chains})


@ontology_api.route('/api/ontology/causal_impact/<object_id>', methods=['GET'])
def get_causal_impact(object_id):
    """获取因果影响分析"""
    impact = ontology.analyze_causal_impact(object_id)
    return jsonify(impact)


@ontology_api.route('/api/ontology/graph', methods=['GET'])
def get_graph():
    """获取完整图谱数据"""
    nodes = []
    links = []

    for obj_id, obj in ontology.objects.items():
        obj_type = ontology.object_types.get(obj.type_id)
        nodes.append({
            'id': obj_id,
            'type': obj.type_id,
            'label': obj.properties.get('name', obj_id),
            'icon': obj_type.icon if obj_type else '📦',
            'color': obj_type.color if obj_type else '#3498db',
            'properties': obj.properties
        })

    for link_id, link in ontology.links.items():
        link_type = ontology.link_types.get(link.type_id)
        links.append({
            'id': link_id,
            'source': link.source_id,
            'target': link.target_id,
            'type': link.type_id,
            'label': link_type.name if link_type else '',
            'confidence': link.confidence,
            'strength': link_type.causal_strength.label if link_type and link_type.causal_strength else '未知'
        })

    return jsonify({
        'nodes': nodes,
        'links': links,
        'stats': {
            'total_objects': len(nodes),
            'total_links': len(links),
            'object_types': len(ontology.object_types),
            'link_types': len(ontology.link_types)
        }
    })


@ontology_api.route('/api/ontology/demo', methods=['POST'])
def create_demo_data():
    """创建演示数据（简单示例）"""
    # 注册对象类型
    person_type = ObjectType(
        id='person',
        name='人员',
        description='人员对象类型',
        icon='👤',
        color='#3498db',
        properties={
            'name': PropertyDefinition(
                id='name',
                name='姓名',
                property_type=PropertyType.STRING,
                required=True
            )
        }
    )
    ontology.register_object_type(person_type)

    event_type = ObjectType(
        id='event',
        name='事件',
        description='事件对象类型',
        icon='⚡',
        color='#e74c3c',
        properties={
            'name': PropertyDefinition(
                id='name',
                name='事件名称',
                property_type=PropertyType.STRING,
                required=True
            )
        }
    )
    ontology.register_object_type(event_type)

    # 注册链接类型
    causes_link = LinkType(
        id='causes',
        name='导致',
        description='因果关系',
        source_types=['person', 'event'],
        target_types=['person', 'event'],
        causal_strength=CausalStrength.STRONG
    )
    ontology.register_link_type(causes_link)

    influences_link = LinkType(
        id='influences',
        name='影响',
        description='影响关系',
        source_types=['person', 'event'],
        target_types=['person', 'event'],
        causal_strength=CausalStrength.MODERATE
    )
    ontology.register_link_type(influences_link)

    # 创建对象
    p1 = ontology.create_object('person', {'name': '张三'})
    p2 = ontology.create_object('person', {'name': '李四'})
    p3 = ontology.create_object('person', {'name': '王五'})
    e1 = ontology.create_object('event', {'name': '项目启动'})
    e2 = ontology.create_object('event', {'name': '需求变更'})
    e3 = ontology.create_object('event', {'name': '项目延期'})

    # 创建链接
    ontology.create_link('causes', p1.id, e1.id, confidence=0.9)
    ontology.create_link('influences', e1.id, p2.id, confidence=0.7)
    ontology.create_link('causes', e2.id, e3.id, confidence=0.85)
    ontology.create_link('influences', p2.id, e2.id, confidence=0.6)
    ontology.create_link('causes', p3.id, e2.id, confidence=0.75)

    return jsonify({'message': '演示数据创建成功'})


@ontology_api.route('/api/ontology/demo/complex', methods=['POST'])
def create_complex_demo_data():
    """创建复杂演示数据 - 软件系统故障分析场景"""
    
    # ═══════════════════════════════════════════════════════════════
    # 1. 注册对象类型（多层次类型系统）
    # ═══════════════════════════════════════════════════════════════
    
    # 系统组件类型
    server_type = ObjectType(
        id='server',
        name='服务器',
        description='物理或虚拟服务器',
        icon='🖥️',
        color='#3498db',
        properties={
            'name': PropertyDefinition(id='name', name='名称', property_type=PropertyType.STRING, required=True),
            'ip': PropertyDefinition(id='ip', name='IP地址', property_type=PropertyType.STRING),
            'cpu_usage': PropertyDefinition(id='cpu_usage', name='CPU使用率', property_type=PropertyType.FLOAT),
            'memory_usage': PropertyDefinition(id='memory_usage', name='内存使用率', property_type=PropertyType.FLOAT)
        }
    )
    ontology.register_object_type(server_type)
    
    database_type = ObjectType(
        id='database',
        name='数据库',
        description='数据库服务',
        icon='🗄️',
        color='#9b59b6',
        properties={
            'name': PropertyDefinition(id='name', name='名称', property_type=PropertyType.STRING, required=True),
            'type': PropertyDefinition(id='type', name='类型', property_type=PropertyType.STRING),
            'connections': PropertyDefinition(id='connections', name='连接数', property_type=PropertyType.INTEGER),
            'query_time': PropertyDefinition(id='query_time', name='查询时间(ms)', property_type=PropertyType.FLOAT)
        }
    )
    ontology.register_object_type(database_type)
    
    service_type = ObjectType(
        id='service',
        name='微服务',
        description='微服务应用',
        icon='⚙️',
        color='#e67e22',
        properties={
            'name': PropertyDefinition(id='name', name='服务名', property_type=PropertyType.STRING, required=True),
            'version': PropertyDefinition(id='version', name='版本', property_type=PropertyType.STRING),
            'status': PropertyDefinition(id='status', name='状态', property_type=PropertyType.STRING),
            'response_time': PropertyDefinition(id='response_time', name='响应时间(ms)', property_type=PropertyType.FLOAT)
        }
    )
    ontology.register_object_type(service_type)
    
    # 事件类型
    incident_type = ObjectType(
        id='incident',
        name='故障事件',
        description='系统故障事件',
        icon='🚨',
        color='#e74c3c',
        properties={
            'name': PropertyDefinition(id='name', name='事件名', property_type=PropertyType.STRING, required=True),
            'severity': PropertyDefinition(id='severity', name='严重程度', property_type=PropertyType.STRING),
            'timestamp': PropertyDefinition(id='timestamp', name='发生时间', property_type=PropertyType.STRING)
        }
    )
    ontology.register_object_type(incident_type)
    
    metric_type = ObjectType(
        id='metric',
        name='性能指标',
        description='系统性能指标',
        icon='📊',
        color='#2ecc71',
        properties={
            'name': PropertyDefinition(id='name', name='指标名', property_type=PropertyType.STRING, required=True),
            'value': PropertyDefinition(id='value', name='当前值', property_type=PropertyType.FLOAT),
            'threshold': PropertyDefinition(id='threshold', name='阈值', property_type=PropertyType.FLOAT),
            'unit': PropertyDefinition(id='unit', name='单位', property_type=PropertyType.STRING)
        }
    )
    ontology.register_object_type(metric_type)
    
    action_type = ObjectType(
        id='action',
        name='处理动作',
        description='故障处理动作',
        icon='🔧',
        color='#f39c12',
        properties={
            'name': PropertyDefinition(id='name', name='动作名', property_type=PropertyType.STRING, required=True),
            'executor': PropertyDefinition(id='executor', name='执行者', property_type=PropertyType.STRING),
            'result': PropertyDefinition(id='result', name='结果', property_type=PropertyType.STRING)
        }
    )
    ontology.register_object_type(action_type)
    
    # ═══════════════════════════════════════════════════════════════
    # 2. 注册链接类型（多种因果关系强度）
    # ═══════════════════════════════════════════════════════════════
    
    causes_deterministic = LinkType(
        id='causes_deterministic',
        name='必然导致',
        description='确定性因果关系',
        source_types=['server', 'database', 'service', 'incident', 'metric'],
        target_types=['server', 'database', 'service', 'incident', 'metric'],
        causal_strength=CausalStrength.DETERMINISTIC
    )
    ontology.register_link_type(causes_deterministic)
    
    causes_strong = LinkType(
        id='causes_strong',
        name='强导致',
        description='强因果关系',
        source_types=['server', 'database', 'service', 'incident', 'metric'],
        target_types=['server', 'database', 'service', 'incident', 'metric'],
        causal_strength=CausalStrength.STRONG
    )
    ontology.register_link_type(causes_strong)
    
    causes_moderate = LinkType(
        id='causes_moderate',
        name='可能导致',
        description='中等因果关系',
        source_types=['server', 'database', 'service', 'incident', 'metric'],
        target_types=['server', 'database', 'service', 'incident', 'metric'],
        causal_strength=CausalStrength.MODERATE
    )
    ontology.register_link_type(causes_moderate)
    
    causes_weak = LinkType(
        id='causes_weak',
        name='可能影响',
        description='弱因果关系',
        source_types=['server', 'database', 'service', 'incident', 'metric'],
        target_types=['server', 'database', 'service', 'incident', 'metric'],
        causal_strength=CausalStrength.WEAK
    )
    ontology.register_link_type(causes_weak)
    
    depends_on = LinkType(
        id='depends_on',
        name='依赖',
        description='服务依赖关系',
        source_types=['service', 'database'],
        target_types=['service', 'database', 'server'],
        causal_strength=CausalStrength.STRONG
    )
    ontology.register_link_type(depends_on)
    
    triggers = LinkType(
        id='triggers',
        name='触发',
        description='触发告警或事件',
        source_types=['metric', 'incident'],
        target_types=['incident', 'action'],
        causal_strength=CausalStrength.MODERATE
    )
    ontology.register_link_type(triggers)
    
    mitigates = LinkType(
        id='mitigates',
        name='缓解',
        description='缓解故障影响',
        source_types=['action'],
        target_types=['incident', 'metric'],
        causal_strength=CausalStrength.MODERATE
    )
    ontology.register_link_type(mitigates)
    
    # ═══════════════════════════════════════════════════════════════
    # 3. 创建对象实例（复杂系统架构）
    # ═══════════════════════════════════════════════════════════════
    
    # 服务器
    app_server = ontology.create_object('server', {
        'name': '应用服务器-01',
        'ip': '192.168.1.101',
        'cpu_usage': 85.5,
        'memory_usage': 78.2
    })
    
    db_server = ontology.create_object('server', {
        'name': '数据库服务器-01',
        'ip': '192.168.1.102',
        'cpu_usage': 92.3,
        'memory_usage': 88.7
    })
    
    cache_server = ontology.create_object('server', {
        'name': '缓存服务器-01',
        'ip': '192.168.1.103',
        'cpu_usage': 45.2,
        'memory_usage': 65.4
    })
    
    # 数据库
    primary_db = ontology.create_object('database', {
        'name': '主数据库',
        'type': 'MySQL',
        'connections': 450,
        'query_time': 2500
    })
    
    replica_db = ontology.create_object('database', {
        'name': '从数据库',
        'type': 'MySQL',
        'connections': 200,
        'query_time': 1800
    })
    
    # 微服务
    api_gateway = ontology.create_object('service', {
        'name': 'API网关服务',
        'version': 'v2.3.1',
        'status': 'degraded',
        'response_time': 3500
    })
    
    user_service = ontology.create_object('service', {
        'name': '用户服务',
        'version': 'v1.8.5',
        'status': 'critical',
        'response_time': 5200
    })
    
    order_service = ontology.create_object('service', {
        'name': '订单服务',
        'version': 'v3.2.0',
        'status': 'down',
        'response_time': 9999
    })
    
    payment_service = ontology.create_object('service', {
        'name': '支付服务',
        'version': 'v2.1.3',
        'status': 'degraded',
        'response_time': 4200
    })
    
    notification_service = ontology.create_object('service', {
        'name': '通知服务',
        'version': 'v1.5.2',
        'status': 'normal',
        'response_time': 150
    })
    
    # 性能指标
    cpu_metric = ontology.create_object('metric', {
        'name': 'CPU使用率',
        'value': 92.3,
        'threshold': 80.0,
        'unit': '%'
    })
    
    memory_metric = ontology.create_object('metric', {
        'name': '内存使用率',
        'value': 88.7,
        'threshold': 85.0,
        'unit': '%'
    })
    
    connection_metric = ontology.create_object('metric', {
        'name': '数据库连接数',
        'value': 450,
        'threshold': 400,
        'unit': '个'
    })
    
    response_time_metric = ontology.create_object('metric', {
        'name': '响应时间',
        'value': 5200,
        'threshold': 1000,
        'unit': 'ms'
    })
    
    error_rate_metric = ontology.create_object('metric', {
        'name': '错误率',
        'value': 15.8,
        'threshold': 5.0,
        'unit': '%'
    })
    
    # 故障事件
    db_slow_query = ontology.create_object('incident', {
        'name': '数据库慢查询',
        'severity': 'high',
        'timestamp': '2024-01-15 14:30:00'
    })
    
    connection_pool_exhausted = ontology.create_object('incident', {
        'name': '连接池耗尽',
        'severity': 'critical',
        'timestamp': '2024-01-15 14:35:00'
    })
    
    service_timeout = ontology.create_object('incident', {
        'name': '服务超时',
        'severity': 'critical',
        'timestamp': '2024-01-15 14:40:00'
    })
    
    system_overload = ontology.create_object('incident', {
        'name': '系统过载',
        'severity': 'critical',
        'timestamp': '2024-01-15 14:45:00'
    })
    
    user_complaint = ontology.create_object('incident', {
        'name': '用户投诉激增',
        'severity': 'high',
        'timestamp': '2024-01-15 15:00:00'
    })
    
    # 处理动作
    scale_db = ontology.create_object('action', {
        'name': '扩容数据库',
        'executor': '运维团队',
        'result': '进行中'
    })
    
    restart_service = ontology.create_object('action', {
        'name': '重启服务',
        'executor': '自动化系统',
        'result': '已完成'
    })
    
    optimize_query = ontology.create_object('action', {
        'name': '优化SQL查询',
        'executor': 'DBA团队',
        'result': '待执行'
    })
    
    enable_cache = ontology.create_object('action', {
        'name': '启用缓存',
        'executor': '开发团队',
        'result': '已完成'
    })
    
    # ═══════════════════════════════════════════════════════════════
    # 4. 创建因果关系链（多层次的复杂因果网络）
    # ═══════════════════════════════════════════════════════════════
    
    # 基础设施层因果关系
    ontology.create_link('causes_strong', db_server.id, cpu_metric.id, confidence=0.95)
    ontology.create_link('causes_strong', db_server.id, memory_metric.id, confidence=0.92)
    ontology.create_link('causes_strong', primary_db.id, connection_metric.id, confidence=0.88)
    
    # 指标异常触发事件
    ontology.create_link('triggers', cpu_metric.id, system_overload.id, confidence=0.85)
    ontology.create_link('triggers', memory_metric.id, system_overload.id, confidence=0.82)
    ontology.create_link('triggers', connection_metric.id, connection_pool_exhausted.id, confidence=0.90)
    ontology.create_link('triggers', response_time_metric.id, service_timeout.id, confidence=0.88)
    ontology.create_link('triggers', error_rate_metric.id, user_complaint.id, confidence=0.75)
    
    # 服务依赖关系
    ontology.create_link('depends_on', api_gateway.id, user_service.id, confidence=0.95)
    ontology.create_link('depends_on', api_gateway.id, order_service.id, confidence=0.95)
    ontology.create_link('depends_on', user_service.id, primary_db.id, confidence=0.90)
    ontology.create_link('depends_on', order_service.id, primary_db.id, confidence=0.92)
    ontology.create_link('depends_on', order_service.id, payment_service.id, confidence=0.88)
    ontology.create_link('depends_on', payment_service.id, primary_db.id, confidence=0.85)
    
    # 数据库问题导致服务异常
    ontology.create_link('causes_strong', db_slow_query.id, user_service.id, confidence=0.92)
    ontology.create_link('causes_strong', connection_pool_exhausted.id, order_service.id, confidence=0.95)
    ontology.create_link('causes_moderate', db_slow_query.id, payment_service.id, confidence=0.70)
    
    # 服务故障传播
    ontology.create_link('causes_strong', user_service.id, api_gateway.id, confidence=0.88)
    ontology.create_link('causes_deterministic', order_service.id, api_gateway.id, confidence=0.95)
    ontology.create_link('causes_moderate', payment_service.id, api_gateway.id, confidence=0.75)
    
    # 故障事件链
    ontology.create_link('causes_strong', system_overload.id, db_slow_query.id, confidence=0.85)
    ontology.create_link('causes_strong', db_slow_query.id, connection_pool_exhausted.id, confidence=0.90)
    ontology.create_link('causes_deterministic', connection_pool_exhausted.id, service_timeout.id, confidence=0.95)
    ontology.create_link('causes_strong', service_timeout.id, user_complaint.id, confidence=0.80)
    
    # 处理动作的影响
    ontology.create_link('mitigates', scale_db.id, connection_pool_exhausted.id, confidence=0.85)
    ontology.create_link('mitigates', restart_service.id, service_timeout.id, confidence=0.75)
    ontology.create_link('mitigates', optimize_query.id, db_slow_query.id, confidence=0.90)
    ontology.create_link('mitigates', enable_cache.id, response_time_metric.id, confidence=0.80)
    
    # 次要影响关系
    ontology.create_link('causes_weak', cache_server.id, api_gateway.id, confidence=0.60)
    ontology.create_link('causes_moderate', notification_service.id, user_complaint.id, confidence=0.65)
    
    # 跨层级复杂因果关系
    ontology.create_link('causes_moderate', cpu_metric.id, db_slow_query.id, confidence=0.78)
    ontology.create_link('causes_moderate', memory_metric.id, connection_pool_exhausted.id, confidence=0.82)
    
    return jsonify({
        'message': '复杂演示数据创建成功',
        'stats': {
            'object_types': len(ontology.object_types),
            'link_types': len(ontology.link_types),
            'objects': len(ontology.objects),
            'links': len(ontology.links)
        }
    })


