"""
A/B 测试 API
提供 A/B 测试管理接口
"""

from flask import Blueprint, request, jsonify
from agent_framework.infra.ab_testing import get_ab_test_manager, TestStatus

ab_testing_bp = Blueprint('ab_testing', __name__, url_prefix='/api/ab-testing')


@ab_testing_bp.route('/tests', methods=['POST'])
def create_test():
    """创建 A/B 测试"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        variants = data.get('variants', [])

        if not name or not variants:
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400

        manager = get_ab_test_manager()
        test = manager.create_test(name, description, variants)

        return jsonify({
            'success': True,
            'test': {
                'test_id': test.test_id,
                'name': test.name,
                'description': test.description,
                'status': test.status.value,
                'variants': [
                    {
                        'variant_id': v.variant_id,
                        'name': v.name,
                        'workflow_id': v.workflow_id,
                        'traffic_percentage': v.traffic_percentage
                    }
                    for v in test.variants
                ],
                'created_at': test.created_at
            }
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ab_testing_bp.route('/tests', methods=['GET'])
def list_tests():
    """列出所有测试"""
    try:
        status = request.args.get('status')
        test_status = TestStatus(status) if status else None

        manager = get_ab_test_manager()
        tests = manager.list_tests(test_status)

        return jsonify({
            'success': True,
            'tests': [
                {
                    'test_id': test.test_id,
                    'name': test.name,
                    'description': test.description,
                    'status': test.status.value,
                    'total_requests': test.total_requests,
                    'created_at': test.created_at,
                    'started_at': test.started_at,
                    'ended_at': test.ended_at
                }
                for test in tests
            ]
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ab_testing_bp.route('/tests/<test_id>', methods=['GET'])
def get_test(test_id: str):
    """获取测试详情"""
    try:
        manager = get_ab_test_manager()
        test = manager.get_test(test_id)

        if not test:
            return jsonify({
                'success': False,
                'error': '测试不存在'
            }), 404

        return jsonify({
            'success': True,
            'test': {
                'test_id': test.test_id,
                'name': test.name,
                'description': test.description,
                'status': test.status.value,
                'variants': [
                    {
                        'variant_id': v.variant_id,
                        'name': v.name,
                        'workflow_id': v.workflow_id,
                        'traffic_percentage': v.traffic_percentage,
                        'description': v.description
                    }
                    for v in test.variants
                ],
                'total_requests': test.total_requests,
                'created_at': test.created_at,
                'started_at': test.started_at,
                'ended_at': test.ended_at
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ab_testing_bp.route('/tests/<test_id>/start', methods=['POST'])
def start_test(test_id: str):
    """开始测试"""
    try:
        manager = get_ab_test_manager()
        success = manager.start_test(test_id)

        if success:
            return jsonify({
                'success': True,
                'message': '测试已开始'
            })
        else:
            return jsonify({
                'success': False,
                'error': '无法开始测试'
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ab_testing_bp.route('/tests/<test_id>/stop', methods=['POST'])
def stop_test(test_id: str):
    """停止测试"""
    try:
        manager = get_ab_test_manager()
        success = manager.stop_test(test_id)

        if success:
            return jsonify({
                'success': True,
                'message': '测试已停止'
            })
        else:
            return jsonify({
                'success': False,
                'error': '无法停止测试'
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ab_testing_bp.route('/tests/<test_id>/select', methods=['GET'])
def select_variant(test_id: str):
    """选择变体"""
    try:
        manager = get_ab_test_manager()
        variant = manager.select_variant(test_id)

        if variant:
            return jsonify({
                'success': True,
                'variant': {
                    'variant_id': variant.variant_id,
                    'name': variant.name,
                    'workflow_id': variant.workflow_id
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': '无法选择变体'
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ab_testing_bp.route('/tests/<test_id>/results', methods=['POST'])
def record_result(test_id: str):
    """记录测试结果"""
    try:
        data = request.json
        variant_id = data.get('variant_id')
        success = data.get('success', True)
        duration = data.get('duration', 0)
        metrics = data.get('metrics', {})

        manager = get_ab_test_manager()
        manager.record_result(test_id, variant_id, success, duration, metrics)

        return jsonify({
            'success': True,
            'message': '结果已记录'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ab_testing_bp.route('/tests/<test_id>/results', methods=['GET'])
def get_results(test_id: str):
    """获取测试结果"""
    try:
        manager = get_ab_test_manager()
        results = manager.get_results(test_id)

        return jsonify({
            'success': True,
            'results': [
                {
                    'variant_id': r.variant_id,
                    'request_count': r.request_count,
                    'success_count': r.success_count,
                    'error_count': r.error_count,
                    'success_rate': r.success_count / r.request_count if r.request_count > 0 else 0,
                    'avg_duration': r.avg_duration,
                    'metrics': r.metrics
                }
                for r in results
            ]
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ab_testing_bp.route('/tests/<test_id>/winner', methods=['GET'])
def get_winner(test_id: str):
    """获取获胜变体"""
    try:
        metric = request.args.get('metric', 'success_rate')

        manager = get_ab_test_manager()
        winner_id = manager.get_winner(test_id, metric)

        if winner_id:
            return jsonify({
                'success': True,
                'winner_id': winner_id,
                'metric': metric
            })
        else:
            return jsonify({
                'success': False,
                'error': '无法确定获胜者'
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
