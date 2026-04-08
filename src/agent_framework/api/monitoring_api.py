"""
监控和分析 API
提供实时监控、性能分析、成本统计接口
"""

from flask import Blueprint, request, jsonify
from agent_framework.infra.monitoring import (
    MonitoringManager,
    MonitoringStorage,
    AlertManager,
    AlertRule,
    CostCalculator,
    MetricType,
)
from datetime import datetime


# 创建 Blueprint
monitoring_bp = Blueprint('monitoring', __name__, url_prefix='/api/monitoring')

# 初始化存储和管理器
storage = MonitoringStorage()
manager = MonitoringManager(storage)
alert_manager = AlertManager()


# ─── 仪表板 ───────────────────────────────────────────────────────────────────

@monitoring_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    """获取仪表板数据"""
    try:
        time_range = request.args.get('time_range', '24h')
        data = manager.get_dashboard_data(time_range)

        return jsonify({
            "success": True,
            "data": data,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 指标 ─────────────────────────────────────────────────────────────────────

@monitoring_bp.route('/metrics', methods=['POST'])
def record_metric():
    """记录指标"""
    try:
        data = request.json
        name = data.get('name')
        value = data.get('value')
        type_str = data.get('type', 'gauge')
        tags = data.get('tags', {})

        if not name or value is None:
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        metric_type = MetricType(type_str)
        manager.record_metric(name, value, metric_type, tags)

        return jsonify({
            "success": True,
            "message": "指标已记录",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@monitoring_bp.route('/metrics/<metric_name>', methods=['GET'])
def get_metrics(metric_name: str):
    """获取指标历史"""
    try:
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        limit = int(request.args.get('limit', 1000))

        metrics = storage.get_metrics(
            name=metric_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

        return jsonify({
            "success": True,
            "data": [
                {
                    "metric_id": m.metric_id,
                    "name": m.name,
                    "type": m.type.value,
                    "value": m.value,
                    "timestamp": m.timestamp,
                    "tags": m.tags,
                }
                for m in metrics
            ],
            "total": len(metrics),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@monitoring_bp.route('/metrics/<metric_name>/timeseries', methods=['GET'])
def get_time_series(metric_name: str):
    """获取时间序列数据"""
    try:
        time_range = request.args.get('time_range', '24h')
        interval = request.args.get('interval', '1h')

        data = manager.get_time_series(metric_name, time_range, interval)

        return jsonify({
            "success": True,
            "data": data,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 性能 ─────────────────────────────────────────────────────────────────────

@monitoring_bp.route('/performance', methods=['POST'])
def record_performance():
    """记录性能"""
    try:
        data = request.json
        operation = data.get('operation')
        duration = data.get('duration')
        success = data.get('success', True)
        error = data.get('error')
        metadata = data.get('metadata', {})

        if not operation or duration is None:
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        manager.record_performance(operation, duration, success, error, metadata)

        return jsonify({
            "success": True,
            "message": "性能记录已保存",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@monitoring_bp.route('/performance/stats', methods=['GET'])
def get_performance_stats():
    """获取性能统计"""
    try:
        operation = request.args.get('operation')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')

        stats = storage.get_performance_stats(
            operation=operation,
            start_time=start_time,
            end_time=end_time,
        )

        return jsonify({
            "success": True,
            "data": stats,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 成本 ─────────────────────────────────────────────────────────────────────

@monitoring_bp.route('/cost', methods=['POST'])
def record_cost():
    """记录成本"""
    try:
        data = request.json
        model = data.get('model')
        input_tokens = data.get('input_tokens')
        output_tokens = data.get('output_tokens')
        metadata = data.get('metadata', {})

        if not model or input_tokens is None or output_tokens is None:
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        # 计算成本
        cost = CostCalculator.calculate_cost(model, input_tokens, output_tokens)

        manager.record_cost(model, input_tokens, output_tokens, cost, metadata)

        return jsonify({
            "success": True,
            "data": {
                "cost": round(cost, 4),
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@monitoring_bp.route('/cost/stats', methods=['GET'])
def get_cost_stats():
    """获取成本统计"""
    try:
        model = request.args.get('model')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')

        stats = storage.get_cost_stats(
            model=model,
            start_time=start_time,
            end_time=end_time,
        )

        return jsonify({
            "success": True,
            "data": stats,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@monitoring_bp.route('/cost/estimate', methods=['POST'])
def estimate_cost():
    """估算成本"""
    try:
        data = request.json
        model = data.get('model')
        daily_requests = data.get('daily_requests')
        avg_input_tokens = data.get('avg_input_tokens')
        avg_output_tokens = data.get('avg_output_tokens')

        if not all([model, daily_requests, avg_input_tokens, avg_output_tokens]):
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        estimate = CostCalculator.estimate_monthly_cost(
            model,
            daily_requests,
            avg_input_tokens,
            avg_output_tokens,
        )

        return jsonify({
            "success": True,
            "data": estimate,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@monitoring_bp.route('/cost/pricing', methods=['GET'])
def get_pricing():
    """获取模型定价"""
    try:
        return jsonify({
            "success": True,
            "data": CostCalculator.PRICING,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 告警 ─────────────────────────────────────────────────────────────────────

@monitoring_bp.route('/alerts', methods=['GET'])
def get_alerts():
    """获取告警列表"""
    try:
        limit = int(request.args.get('limit', 100))
        alerts = alert_manager.get_alerts(limit)

        return jsonify({
            "success": True,
            "data": alerts,
            "total": len(alerts),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@monitoring_bp.route('/alerts/rules', methods=['POST'])
def add_alert_rule():
    """添加告警规则"""
    try:
        data = request.json
        name = data.get('name')
        metric_name = data.get('metric_name')
        condition = data.get('condition')
        threshold = data.get('threshold')
        duration = data.get('duration', 60)

        if not all([name, metric_name, condition, threshold]):
            return jsonify({
                "success": False,
                "error": "缺少必要参数",
            }), 400

        rule = AlertRule(
            name=name,
            metric_name=metric_name,
            condition=condition,
            threshold=threshold,
            duration=duration,
        )

        alert_manager.add_rule(rule)

        return jsonify({
            "success": True,
            "message": "告警规则已添加",
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ─── 健康检查 ─────────────────────────────────────────────────────────────────

@monitoring_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    try:
        # 检查数据库连接
        storage.get_metrics(limit=1)

        return jsonify({
            "success": True,
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }), 503
