"""
性能监控 API
提供性能数据的 REST API 接口
"""

from flask import Blueprint, jsonify, request
from agent_framework.infra.performance_monitor import get_performance_monitor, PerformanceAnalyzer
from datetime import datetime

performance_bp = Blueprint('performance', __name__, url_prefix='/api/performance')


@performance_bp.route('/stats', methods=['GET'])
def get_stats():
    """获取性能统计"""
    monitor = get_performance_monitor()
    function_name = request.args.get('function')

    if function_name:
        # 获取特定函数的统计
        stats = monitor.get_stats(function_name)
        if not stats:
            return jsonify({'error': '函数不存在'}), 404

        return jsonify({
            'function': function_name,
            'stats': stats
        })
    else:
        # 获取所有函数的统计
        all_stats = monitor.get_stats()
        return jsonify({
            'functions': all_stats,
            'total_functions': len(all_stats)
        })


@performance_bp.route('/analysis', methods=['GET'])
def get_analysis():
    """获取性能分析"""
    monitor = get_performance_monitor()
    analyzer = PerformanceAnalyzer(monitor)

    analysis = analyzer.analyze()

    return jsonify(analysis)


@performance_bp.route('/suggestions', methods=['GET'])
def get_suggestions():
    """获取优化建议"""
    monitor = get_performance_monitor()
    analyzer = PerformanceAnalyzer(monitor)

    suggestions = analyzer.get_optimization_suggestions()

    return jsonify({
        'suggestions': suggestions,
        'count': len(suggestions)
    })


@performance_bp.route('/slow-queries', methods=['GET'])
def get_slow_queries():
    """获取慢查询"""
    monitor = get_performance_monitor()

    threshold = request.args.get('threshold', 1.0, type=float)
    limit = request.args.get('limit', 10, type=int)

    slow_queries = monitor.get_slow_queries(threshold, limit)

    return jsonify({
        'slow_queries': [
            {
                'name': q.name,
                'duration': q.duration,
                'timestamp': datetime.fromtimestamp(q.timestamp).isoformat(),
                'success': q.success,
                'error': q.error
            }
            for q in slow_queries
        ],
        'count': len(slow_queries)
    })


@performance_bp.route('/error-rate', methods=['GET'])
def get_error_rate():
    """获取错误率"""
    monitor = get_performance_monitor()
    function_name = request.args.get('function')

    error_rate = monitor.get_error_rate(function_name)

    return jsonify({
        'function': function_name or 'all',
        'error_rate': error_rate,
        'error_percentage': f"{error_rate:.2%}"
    })


@performance_bp.route('/clear', methods=['POST'])
def clear_metrics():
    """清空性能指标"""
    monitor = get_performance_monitor()
    monitor.clear()

    return jsonify({
        'success': True,
        'message': '性能指标已清空'
    })


@performance_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    """获取性能监控仪表板数据"""
    monitor = get_performance_monitor()
    analyzer = PerformanceAnalyzer(monitor)

    # 获取所有数据
    all_stats = monitor.get_stats()
    analysis = analyzer.analyze()
    suggestions = analyzer.get_optimization_suggestions()
    slow_queries = monitor.get_slow_queries(threshold=0.5, limit=10)

    # 计算总体指标
    total_calls = sum(s.get('count', 0) for s in all_stats.values())
    total_time = sum(s.get('total_time', 0) for s in all_stats.values())
    avg_time = total_time / total_calls if total_calls > 0 else 0

    # 找出最慢的函数
    slowest = max(all_stats.items(), key=lambda x: x[1].get('avg_time', 0)) if all_stats else None

    # 找出调用最多的函数
    most_called = max(all_stats.items(), key=lambda x: x[1].get('count', 0)) if all_stats else None

    return jsonify({
        'overview': {
            'total_functions': len(all_stats),
            'total_calls': total_calls,
            'total_time': total_time,
            'avg_time': avg_time,
            'error_rate': monitor.get_error_rate(),
            'slow_queries_count': len(slow_queries)
        },
        'slowest_function': {
            'name': slowest[0] if slowest else None,
            'avg_time': slowest[1].get('avg_time', 0) if slowest else 0
        } if slowest else None,
        'most_called_function': {
            'name': most_called[0] if most_called else None,
            'count': most_called[1].get('count', 0) if most_called else 0
        } if most_called else None,
        'top_functions': {
            'slowest': analysis['slowest_functions'][:5],
            'most_called': analysis['most_called'][:5],
            'most_time_consuming': analysis['most_time_consuming'][:5]
        },
        'slow_queries': [
            {
                'name': q.name,
                'duration': q.duration,
                'timestamp': datetime.fromtimestamp(q.timestamp).isoformat()
            }
            for q in slow_queries[:5]
        ],
        'suggestions': suggestions,
        'timestamp': datetime.now().isoformat()
    })


@performance_bp.route('/metrics/export', methods=['GET'])
def export_metrics():
    """导出性能指标（CSV格式）"""
    monitor = get_performance_monitor()

    # 获取所有指标
    metrics = monitor.metrics

    # 生成 CSV
    csv_lines = ['name,duration,timestamp,success,error']
    for metric in metrics:
        csv_lines.append(
            f"{metric.name},{metric.duration},{metric.timestamp},"
            f"{metric.success},{metric.error or ''}"
        )

    csv_content = '\n'.join(csv_lines)

    return csv_content, 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename=performance_metrics.csv'
    }


@performance_bp.route('/functions', methods=['GET'])
def list_functions():
    """列出所有被监控的函数"""
    monitor = get_performance_monitor()
    all_stats = monitor.get_stats()

    functions = [
        {
            'name': name,
            'count': stats.get('count', 0),
            'avg_time': stats.get('avg_time', 0),
            'total_time': stats.get('total_time', 0)
        }
        for name, stats in all_stats.items()
    ]

    # 按总耗时排序
    functions.sort(key=lambda x: x['total_time'], reverse=True)

    return jsonify({
        'functions': functions,
        'count': len(functions)
    })


@performance_bp.route('/compare', methods=['POST'])
def compare_functions():
    """对比多个函数的性能"""
    data = request.json
    function_names = data.get('functions', [])

    if not function_names:
        return jsonify({'error': '请提供要对比的函数名'}), 400

    monitor = get_performance_monitor()

    comparison = []
    for name in function_names:
        stats = monitor.get_stats(name)
        if stats:
            comparison.append({
                'name': name,
                'stats': stats
            })

    return jsonify({
        'comparison': comparison,
        'count': len(comparison)
    })
