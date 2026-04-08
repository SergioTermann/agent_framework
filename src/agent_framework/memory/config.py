"""
记忆系统配置文件
"""

import copy
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


_dotenv_loaded = False


def _ensure_dotenv_loaded() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    if load_dotenv is not None:
        load_dotenv()
    _dotenv_loaded = True


def _first_env(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return ''

# 基础配置
MEMORY_CONFIG = {
    'backend': {
        'provider': 'local',
        'fallback_to_local': True,
        'reme': {
            'enabled': False,
            'sidecar': {
                'enabled': True,
                'auto_start': True,
                'llm_provider': '',
                'base_url': 'http://127.0.0.1:8765',
                'host': '127.0.0.1',
                'port': 8765,
                'venv_dir': '.venv_reme_memory',
                'working_dir': '.reme-sidecar',
                'start_timeout': 45,
                'request_timeout': 10,
                'embedding_dimensions': None,
                'llm_api_key': '',
                'llm_base_url': '',
                'embedding_api_key': '',
                'embedding_base_url': '',
            },
        },
        'viking': {
            'enabled': False,
            'host': 'api-knowledgebase.mlp.cn-beijing.volces.com',
            'region': 'cn-beijing',
            'access_key': '',
            'secret_key': '',
            'scheme': 'http',
            'timeout': 30,
        },
    },

    # 数据库配置
    'database': {
        'path': 'data/memory.db',
        'backup_interval': 3600,  # 备份间隔（秒）
        'max_backup_files': 10
    },

    # 向量编码配置
    'encoder': {
        'model_name': 'all-MiniLM-L6-v2',
        'dimension': 384,
        'batch_size': 32,
        'cache_embeddings': True
    },

    # 记忆管理配置
    'memory_management': {
        'max_working_memory': 50,
        'importance_decay_rate': 0.1,
        'consolidation_interval': 86400,  # 24小时
        'similarity_threshold': 0.3,
        'max_search_results': 20
    },

    # 自动记忆配置
    'auto_memory': {
        'enabled': True,
        'min_content_length': 10,
        'importance_threshold': 0.3,
        'record_api_calls': True,
        'record_conversations': True,
        'record_errors': True
    },

    # 记忆类型权重
    'memory_weights': {
        'episodic': 0.5,    # 情节记忆
        'semantic': 0.8,    # 语义记忆
        'procedural': 0.9,  # 程序性记忆
        'working': 0.3      # 工作记忆
    },

    # 上下文增强配置
    'context_enhancement': {
        'max_context_memories': 5,
        'memory_summary_length': 200,
        'include_memory_metadata': True
    },

    # 性能配置
    'performance': {
        'enable_caching': True,
        'cache_size': 1000,
        'parallel_search': True,
        'max_concurrent_operations': 4
    },

    # 安全配置
    'security': {
        'encrypt_sensitive_data': False,
        'anonymize_personal_info': True,
        'data_retention_days': 365,
        'audit_log_enabled': True
    },

    # ── 三层记忆架构配置 ────────────────────────────────────────────────

    # 文件记忆层（每日笔记 + MEMORY.md）
    'file_memory': {
        'enabled': True,
        'base_dir': 'data/memory',
        'daily_notes_load_days': 2,
        'memory_md_max_size_kb': 50,
    },

    # 自动刷写（上下文压缩前保存重要信息）
    'auto_flush': {
        'enabled': True,
        'event_threshold': 30,      # 事件数达到此值时触发刷写
    },

    # 自动回忆（LLM 调用前检索相关记忆注入上下文）
    'auto_recall': {
        'enabled': True,
        'max_injected_memories': 3,
        'similarity_threshold': 0.4,
    },

    # 自动捕获（每轮对话后自动提取关键信息）
    'auto_capture': {
        'enabled': True,
        'min_content_length': 20,
        'save_to_daily_notes': True,
        'save_to_sqlite': True,
    },
}

# 环境变量覆盖
def load_config():
    """加载配置，支持环境变量覆盖"""
    _ensure_dotenv_loaded()
    config = copy.deepcopy(MEMORY_CONFIG)

    if os.getenv('MEMORY_BACKEND'):
        config['backend']['provider'] = os.getenv('MEMORY_BACKEND').strip().lower()
    if os.getenv('MEMORY_BACKEND_FALLBACK'):
        config['backend']['fallback_to_local'] = os.getenv('MEMORY_BACKEND_FALLBACK').lower() == 'true'
    if os.getenv('REME_ENABLED'):
        config['backend']['reme']['enabled'] = os.getenv('REME_ENABLED').lower() == 'true'
    if os.getenv('REME_SIDECAR_ENABLED'):
        config['backend']['reme']['sidecar']['enabled'] = os.getenv('REME_SIDECAR_ENABLED').lower() == 'true'
    if os.getenv('REME_SIDECAR_AUTO_START'):
        config['backend']['reme']['sidecar']['auto_start'] = os.getenv('REME_SIDECAR_AUTO_START').lower() == 'true'
    if os.getenv('LLM_PROVIDER'):
        config['backend']['reme']['sidecar']['llm_provider'] = os.getenv('LLM_PROVIDER').strip().lower()
    if os.getenv('REME_SIDECAR_BASE_URL'):
        config['backend']['reme']['sidecar']['base_url'] = os.getenv('REME_SIDECAR_BASE_URL')
    if os.getenv('REME_SIDECAR_HOST'):
        config['backend']['reme']['sidecar']['host'] = os.getenv('REME_SIDECAR_HOST')
    if os.getenv('REME_SIDECAR_PORT'):
        config['backend']['reme']['sidecar']['port'] = int(os.getenv('REME_SIDECAR_PORT'))
    if os.getenv('REME_SIDECAR_VENV'):
        config['backend']['reme']['sidecar']['venv_dir'] = os.getenv('REME_SIDECAR_VENV')
    if os.getenv('REME_SIDECAR_WORKDIR'):
        config['backend']['reme']['sidecar']['working_dir'] = os.getenv('REME_SIDECAR_WORKDIR')
    if os.getenv('REME_SIDECAR_TIMEOUT'):
        config['backend']['reme']['sidecar']['start_timeout'] = int(os.getenv('REME_SIDECAR_TIMEOUT'))
    if os.getenv('REME_SIDECAR_REQUEST_TIMEOUT'):
        config['backend']['reme']['sidecar']['request_timeout'] = int(os.getenv('REME_SIDECAR_REQUEST_TIMEOUT'))
    if os.getenv('REME_EMBEDDING_DIMENSIONS'):
        config['backend']['reme']['sidecar']['embedding_dimensions'] = int(os.getenv('REME_EMBEDDING_DIMENSIONS'))
    if os.getenv('REME_LLM_API_KEY'):
        config['backend']['reme']['sidecar']['llm_api_key'] = os.getenv('REME_LLM_API_KEY')
    if os.getenv('REME_LLM_BASE_URL'):
        config['backend']['reme']['sidecar']['llm_base_url'] = os.getenv('REME_LLM_BASE_URL')
    if os.getenv('REME_EMBEDDING_API_KEY'):
        config['backend']['reme']['sidecar']['embedding_api_key'] = os.getenv('REME_EMBEDDING_API_KEY')
    if os.getenv('REME_EMBEDDING_BASE_URL'):
        config['backend']['reme']['sidecar']['embedding_base_url'] = os.getenv('REME_EMBEDDING_BASE_URL')
    sidecar = config['backend']['reme']['sidecar']
    if not sidecar['llm_api_key']:
        sidecar['llm_api_key'] = _first_env('LLM_API_KEY', 'OPENAI_API_KEY', 'SILICONFLOW_API_KEY')
    if not sidecar['llm_base_url']:
        sidecar['llm_base_url'] = _first_env('LLM_BASE_URL', 'BASE_URL')
    if not sidecar['embedding_api_key']:
        sidecar['embedding_api_key'] = _first_env('EMBEDDING_API_KEY')
    if not sidecar['embedding_base_url']:
        sidecar['embedding_base_url'] = _first_env('EMBEDDING_BASE_URL')
    if not sidecar['embedding_api_key']:
        if sidecar['llm_provider'] != 'vllm':
            sidecar['embedding_api_key'] = _first_env('REME_LLM_API_KEY', 'LLM_API_KEY', 'OPENAI_API_KEY', 'SILICONFLOW_API_KEY')
    if not sidecar['embedding_base_url']:
        if sidecar['llm_provider'] != 'vllm':
            sidecar['embedding_base_url'] = _first_env('REME_LLM_BASE_URL', 'LLM_BASE_URL', 'BASE_URL')
    if os.getenv('VIKING_ENABLED'):
        config['backend']['viking']['enabled'] = os.getenv('VIKING_ENABLED').lower() == 'true'
    if os.getenv('VIKING_HOST'):
        config['backend']['viking']['host'] = os.getenv('VIKING_HOST')
    if os.getenv('VIKING_REGION'):
        config['backend']['viking']['region'] = os.getenv('VIKING_REGION')
    if os.getenv('VIKING_ACCESS_KEY'):
        config['backend']['viking']['access_key'] = os.getenv('VIKING_ACCESS_KEY')
    if os.getenv('VIKING_SECRET_KEY'):
        config['backend']['viking']['secret_key'] = os.getenv('VIKING_SECRET_KEY')
    if os.getenv('VIKING_SCHEME'):
        config['backend']['viking']['scheme'] = os.getenv('VIKING_SCHEME')
    if os.getenv('VIKING_TIMEOUT'):
        config['backend']['viking']['timeout'] = int(os.getenv('VIKING_TIMEOUT'))

    # 数据库路径
    if os.getenv('MEMORY_DB_PATH'):
        config['database']['path'] = os.getenv('MEMORY_DB_PATH')

    # 编码器模型
    if os.getenv('MEMORY_ENCODER_MODEL'):
        config['encoder']['model_name'] = os.getenv('MEMORY_ENCODER_MODEL')

    # 自动记忆开关
    if os.getenv('MEMORY_AUTO_ENABLED'):
        config['auto_memory']['enabled'] = os.getenv('MEMORY_AUTO_ENABLED').lower() == 'true'

    # 相似度阈值
    if os.getenv('MEMORY_SIMILARITY_THRESHOLD'):
        config['memory_management']['similarity_threshold'] = float(os.getenv('MEMORY_SIMILARITY_THRESHOLD'))

    # 文件记忆层
    if os.getenv('MEMORY_FILE_ENABLED'):
        config['file_memory']['enabled'] = os.getenv('MEMORY_FILE_ENABLED').lower() == 'true'
    if os.getenv('MEMORY_FILE_BASE_DIR'):
        config['file_memory']['base_dir'] = os.getenv('MEMORY_FILE_BASE_DIR')
    if os.getenv('MEMORY_DAILY_NOTES_DAYS'):
        config['file_memory']['daily_notes_load_days'] = int(os.getenv('MEMORY_DAILY_NOTES_DAYS'))

    # 自动刷写
    if os.getenv('MEMORY_AUTO_FLUSH_ENABLED'):
        config['auto_flush']['enabled'] = os.getenv('MEMORY_AUTO_FLUSH_ENABLED').lower() == 'true'
    if os.getenv('MEMORY_AUTO_FLUSH_THRESHOLD'):
        config['auto_flush']['event_threshold'] = int(os.getenv('MEMORY_AUTO_FLUSH_THRESHOLD'))

    # 自动回忆
    if os.getenv('MEMORY_AUTO_RECALL_ENABLED'):
        config['auto_recall']['enabled'] = os.getenv('MEMORY_AUTO_RECALL_ENABLED').lower() == 'true'
    if os.getenv('MEMORY_AUTO_RECALL_MAX'):
        config['auto_recall']['max_injected_memories'] = int(os.getenv('MEMORY_AUTO_RECALL_MAX'))
    if os.getenv('MEMORY_AUTO_RECALL_THRESHOLD'):
        config['auto_recall']['similarity_threshold'] = float(os.getenv('MEMORY_AUTO_RECALL_THRESHOLD'))

    # 自动捕获
    if os.getenv('MEMORY_AUTO_CAPTURE_ENABLED'):
        config['auto_capture']['enabled'] = os.getenv('MEMORY_AUTO_CAPTURE_ENABLED').lower() == 'true'

    return config

# 记忆类型定义
MEMORY_TYPES = {
    'episodic': {
        'name': '情节记忆',
        'description': '记录特定时间和地点发生的事件',
        'default_importance': 0.5,
        'retention_days': 90,
        'auto_consolidate': True
    },
    'semantic': {
        'name': '语义记忆',
        'description': '存储概念、事实和知识',
        'default_importance': 0.8,
        'retention_days': 365,
        'auto_consolidate': False
    },
    'procedural': {
        'name': '程序性记忆',
        'description': '记录如何执行任务的知识',
        'default_importance': 0.9,
        'retention_days': 180,
        'auto_consolidate': False
    },
    'working': {
        'name': '工作记忆',
        'description': '临时存储当前任务相关信息',
        'default_importance': 0.3,
        'retention_days': 7,
        'auto_consolidate': True
    }
}

# 重要性计算规则
IMPORTANCE_RULES = {
    'keywords': {
        'high': ['错误', '问题', '解决', '重要', '关键', '紧急', '配置', '部署'],
        'medium': ['优化', '改进', '建议', '方案', '策略', '分析'],
        'low': ['你好', '谢谢', '再见', '测试', '示例']
    },
    'length_weights': {
        'short': (0, 50, 0.2),      # 0-50字符，权重0.2
        'medium': (51, 200, 0.5),   # 51-200字符，权重0.5
        'long': (201, 1000, 0.8),   # 201-1000字符，权重0.8
        'very_long': (1001, float('inf'), 1.0)  # 1000+字符，权重1.0
    },
    'context_weights': {
        'api_call': 0.6,
        'error_handling': 0.9,
        'user_feedback': 0.7,
        'system_event': 0.4,
        'manual_input': 0.8
    }
}

# 标签系统
TAG_CATEGORIES = {
    'source': ['manual_input', 'api_call', 'auto_generated', 'imported'],
    'type': ['question', 'answer', 'error', 'solution', 'configuration'],
    'domain': ['technical', 'business', 'personal', 'system'],
    'priority': ['high', 'medium', 'low', 'critical'],
    'status': ['active', 'archived', 'deprecated', 'pending']
}

# 搜索配置
SEARCH_CONFIG = {
    'default_limit': 10,
    'max_limit': 100,
    'similarity_algorithms': ['cosine', 'euclidean', 'dot_product'],
    'ranking_factors': {
        'similarity_score': 0.4,
        'importance': 0.3,
        'recency': 0.2,
        'access_frequency': 0.1
    },
    'filters': {
        'memory_type': ['episodic', 'semantic', 'procedural', 'working'],
        'date_range': True,
        'importance_range': True,
        'tags': True
    }
}

# 导出/导入配置
EXPORT_CONFIG = {
    'formats': ['json', 'csv', 'xml'],
    'compression': True,
    'include_embeddings': False,
    'batch_size': 1000,
    'max_file_size': 100 * 1024 * 1024  # 100MB
}

# 监控和日志配置
MONITORING_CONFIG = {
    'metrics': {
        'memory_count_by_type': True,
        'search_performance': True,
        'storage_usage': True,
        'api_response_times': True
    },
    'alerts': {
        'storage_threshold': 0.9,  # 90%存储使用率
        'search_latency_threshold': 1000,  # 1秒
        'error_rate_threshold': 0.05  # 5%错误率
    },
    'logging': {
        'level': 'INFO',
        'file': 'logs/memory_system.log',
        'max_size': 10 * 1024 * 1024,  # 10MB
        'backup_count': 5
    }
}

def get_config():
    """获取完整配置"""
    return {
        'memory': load_config(),
        'types': MEMORY_TYPES,
        'importance': IMPORTANCE_RULES,
        'tags': TAG_CATEGORIES,
        'search': SEARCH_CONFIG,
        'export': EXPORT_CONFIG,
        'monitoring': MONITORING_CONFIG
    }
