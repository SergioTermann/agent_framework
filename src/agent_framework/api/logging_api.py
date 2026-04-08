"""
日志管理 API
提供日志查询、统计和管理的 REST API
"""

from flask import Blueprint, jsonify, request
from agent_framework.core.unified_logging import get_unified_logger, LogLevel
from datetime import datetime, timedelta
import time

logging_bp = Blueprint('logging', __name__, url_prefix='/api/logs')


@logging_bp.route('/query', methods=['GET'])
def query_logs():
    """
    查询日志

    参数:
    - level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    - logger: 日志器名称
    - start_time: 开始时间 (ISO格式或时间戳)
    - end_time: 结束时间 (ISO格式或时间戳)
    - keyword: 关键词搜索
    - limit: 返回数量 (默认100)
    - offset: 偏移量 (默认0)
    """
    level = request.args.get('level')
    logger = request.args.get('logger')
    keyword = request.args.get('keyword')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    # 解析时间
    start_time = None
    end_time = None

    start_time_str = request.args.get('start_time')
    if start_time_str:
        try:
            # 尝试解析 ISO 格式
            dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            start_time = dt.timestamp()
        except:
            # 尝试解析时间戳
            try:
                start_time = float(start_time_str)
            except:
                pass

    end_time_str = request.args.get('end_time')
    if end_time_str:
        try:
            dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            end_time = dt.timestamp()
        except:
            try:
                end_time = float(end_time_str)
            except:
                pass

    # 查询日志
    unified_logger = get_unified_logger()
    entries = unified_logger.query(
        level=level,
        logger=logger,
        start_time=start_time,
        end_time=end_time,
        keyword=keyword,
        limit=limit,
        offset=offset
    )

    # 统计总数
    total = unified_logger.count(
        level=level,
        logger=logger,
        start_time=start_time,
        end_time=end_time
    )

    return jsonify({
        'logs': [entry.to_dict() for entry in entries],
        'total': total,
        'limit': limit,
        'offset': offset
    })


@logging_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """
    获取日志统计信息

    参数:
    - hours: 统计时间范围（小时，默认24）
    """
    hours = request.args.get('hours', 24, type=int)

    unified_logger = get_unified_logger()
    stats = unified_logger.get_statistics(hours=hours)

    return jsonify(stats)


@logging_bp.route('/levels', methods=['GET'])
def get_levels():
    """获取所有日志级别"""
    return jsonify({
        'levels': [level.value for level in LogLevel]
    })


@logging_bp.route('/loggers', methods=['GET'])
def get_loggers():
    """获取所有日志器"""
    unified_logger = get_unified_logger()

    # 获取最近24小时的日志器
    start_time = time.time() - 86400
    entries = unified_logger.query(start_time=start_time, limit=1000)

    # 提取唯一的日志器名称
    loggers = list(set(entry.logger for entry in entries))
    loggers.sort()

    return jsonify({
        'loggers': loggers,
        'count': len(loggers)
    })


@logging_bp.route('/recent', methods=['GET'])
def get_recent_logs():
    """
    获取最近的日志

    参数:
    - minutes: 最近多少分钟（默认10）
    - level: 日志级别过滤
    - limit: 返回数量（默认50）
    """
    minutes = request.args.get('minutes', 10, type=int)
    level = request.args.get('level')
    limit = request.args.get('limit', 50, type=int)

    start_time = time.time() - (minutes * 60)

    unified_logger = get_unified_logger()
    entries = unified_logger.query(
        level=level,
        start_time=start_time,
        limit=limit
    )

    return jsonify({
        'logs': [entry.to_dict() for entry in entries],
        'count': len(entries)
    })


@logging_bp.route('/errors', methods=['GET'])
def get_errors():
    """
    获取错误日志

    参数:
    - hours: 时间范围（小时，默认24）
    - limit: 返回数量（默认100）
    """
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 100, type=int)

    start_time = time.time() - (hours * 3600)

    unified_logger = get_unified_logger()
    entries = unified_logger.query(
        level='ERROR',
        start_time=start_time,
        limit=limit
    )

    return jsonify({
        'errors': [entry.to_dict() for entry in entries],
        'count': len(entries)
    })


@logging_bp.route('/cleanup', methods=['POST'])
def cleanup_logs():
    """
    清理旧日志

    请求体:
    {
        "days": 30  # 保留最近多少天的日志
    }
    """
    data = request.json or {}
    days = data.get('days', 30)

    if days < 1:
        return jsonify({'error': '保留天数必须大于0'}), 400

    unified_logger = get_unified_logger()
    deleted = unified_logger.cleanup(days=days)

    return jsonify({
        'deleted': deleted,
        'message': f'已清理 {deleted} 条日志'
    })


@logging_bp.route('/export', methods=['GET'])
def export_logs():
    """
    导出日志（CSV格式）

    参数:
    - level: 日志级别
    - logger: 日志器名称
    - start_time: 开始时间
    - end_time: 结束时间
    - limit: 导出数量（默认1000）
    """
    level = request.args.get('level')
    logger = request.args.get('logger')
    limit = request.args.get('limit', 1000, type=int)

    # 解析时间
    start_time = None
    end_time = None

    start_time_str = request.args.get('start_time')
    if start_time_str:
        try:
            dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            start_time = dt.timestamp()
        except:
            try:
                start_time = float(start_time_str)
            except:
                pass

    end_time_str = request.args.get('end_time')
    if end_time_str:
        try:
            dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            end_time = dt.timestamp()
        except:
            try:
                end_time = float(end_time_str)
            except:
                pass

    # 查询日志
    unified_logger = get_unified_logger()
    entries = unified_logger.query(
        level=level,
        logger=logger,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )

    # 生成 CSV
    csv_lines = ['timestamp,level,logger,message,module,function,line_number']

    for entry in entries:
        timestamp = datetime.fromtimestamp(entry.timestamp).isoformat()
        message = entry.message.replace(',', ';').replace('\n', ' ')
        csv_lines.append(
            f'"{timestamp}","{entry.level}","{entry.logger}","{message}",'
            f'"{entry.module}","{entry.function}",{entry.line_number}'
        )

    csv_content = '\n'.join(csv_lines)

    return csv_content, 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename=logs.csv'
    }


@logging_bp.route('/search', methods=['POST'])
def search_logs():
    """
    高级日志搜索

    请求体:
    {
        "query": "关键词",
        "filters": {
            "level": "ERROR",
            "logger": "app",
            "start_time": "2026-03-17T00:00:00",
            "end_time": "2026-03-17T23:59:59"
        },
        "limit": 100,
        "offset": 0
    }
    """
    data = request.json or {}

    query = data.get('query', '')
    filters = data.get('filters', {})
    limit = data.get('limit', 100)
    offset = data.get('offset', 0)

    # 解析过滤器
    level = filters.get('level')
    logger = filters.get('logger')

    start_time = None
    if filters.get('start_time'):
        try:
            dt = datetime.fromisoformat(filters['start_time'].replace('Z', '+00:00'))
            start_time = dt.timestamp()
        except:
            pass

    end_time = None
    if filters.get('end_time'):
        try:
            dt = datetime.fromisoformat(filters['end_time'].replace('Z', '+00:00'))
            end_time = dt.timestamp()
        except:
            pass

    # 搜索日志
    unified_logger = get_unified_logger()
    entries = unified_logger.query(
        level=level,
        logger=logger,
        start_time=start_time,
        end_time=end_time,
        keyword=query,
        limit=limit,
        offset=offset
    )

    total = unified_logger.count(
        level=level,
        logger=logger,
        start_time=start_time,
        end_time=end_time
    )

    return jsonify({
        'logs': [entry.to_dict() for entry in entries],
        'total': total,
        'query': query,
        'filters': filters
    })
