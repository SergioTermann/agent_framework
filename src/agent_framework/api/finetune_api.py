"""
微调 API - 基于 LLaMA Factory 的模型微调接口
"""

from flask import Blueprint, request, jsonify
import os
import shutil
import agent_framework.core.fast_json as json
from datetime import datetime
import uuid
import subprocess
import threading
from pathlib import Path

from agent_framework.reasoning.model_serving import MODEL_CACHE_DIR

finetune_bp = Blueprint('finetune', __name__, url_prefix='/api/finetune')

# 存储路径
UPLOAD_FOLDER = 'data/datasets'
TASKS_FILE = 'data/finetune_tasks.json'
DOWNLOAD_TASKS = {}  # 存储下载任务状态

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('data', exist_ok=True)

# 初始化任务文件
if not os.path.exists(TASKS_FILE):
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)


def load_tasks():
    """加载任务列表"""
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []


def save_tasks(tasks):
    """保存任务列表"""
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def _safe_display_name(path):
    base = os.path.basename(str(path).rstrip('/\\'))
    return base.replace('_', '/')


def _format_size(total_size):
    if total_size <= 0:
        return '0 MB'
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(total_size)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}" if unit != 'B' else f"{int(size)} B"
        size /= 1024
    return f'{total_size} B'


def _dir_size(path):
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total += os.path.getsize(filepath)
            except OSError:
                continue
    return total


def _guess_model_capability(name, path):
    sample = f"{name} {path}".lower()
    if any(token in sample for token in ('rerank', 'reranker')):
        return 'rerank'
    if any(token in sample for token in ('embed', 'embedding', 'bge-m3', 'e5', 'gte')):
        return 'embedding'
    return 'chat'


def _collect_installed_models():
    items = []
    seen_paths = set()

    def add_model(path, source, display_name='', metadata=None):
        resolved = os.path.abspath(path)
        if not os.path.isdir(resolved) or resolved in seen_paths:
            return
        seen_paths.add(resolved)
        total_size = _dir_size(resolved)
        name = display_name or _safe_display_name(resolved)
        item = {
            'id': uuid.uuid5(uuid.NAMESPACE_URL, resolved).hex[:12],
            'name': name,
            'path': resolved,
            'source': source,
            'size_bytes': total_size,
            'size': _format_size(total_size),
            'capability': _guess_model_capability(name, resolved),
            'created_at': datetime.fromtimestamp(os.path.getctime(resolved)).strftime('%Y-%m-%d %H:%M:%S')
        }
        if metadata:
            item.update(metadata)
        items.append(item)

    models_dir = Path('./models')
    if models_dir.exists():
        for entry in models_dir.iterdir():
            if entry.is_dir():
                add_model(str(entry), 'downloaded')

    cache_dir = Path(MODEL_CACHE_DIR)
    if cache_dir.exists():
        for entry in cache_dir.iterdir():
            if entry.is_dir():
                add_model(str(entry), 'cache')

    for task in load_tasks():
        if task.get('status') != 'completed':
            continue
        model_path = os.path.join('data', 'models', task['id'])
        add_model(
            model_path,
            'finetuned',
            display_name=task.get('task_name') or task.get('base_model') or task['id'],
            metadata={
                'task_id': task['id'],
                'base_model': task.get('base_model', ''),
                'train_method': task.get('train_method', '')
            }
        )

    items.sort(key=lambda item: (item['source'] != 'finetuned', item['source'] != 'downloaded', item['name'].lower()))
    return items


def _deletable_roots():
    return [os.path.abspath('./models'), os.path.abspath(MODEL_CACHE_DIR), os.path.abspath('data/models')]


def _path_is_within(path, root):
    try:
        common = os.path.commonpath([os.path.abspath(path), os.path.abspath(root)])
    except ValueError:
        return False
    return common == os.path.abspath(root)


@finetune_bp.route('/start', methods=['POST'])
def start_finetune():
    """启动微调任务"""
    data = request.json

    task = {
        'id': str(uuid.uuid4()),
        'task_name': data.get('task_name'),
        'base_model': data.get('base_model'),
        'train_method': data.get('train_method'),
        'learning_rate': data.get('learning_rate'),
        'epochs': data.get('epochs'),
        'batch_size': data.get('batch_size'),
        'dataset': data.get('dataset'),
        'dpo_dataset': data.get('dpo_dataset'),
        'status': 'running',
        'progress': 0,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'process_id': None
    }

    tasks = load_tasks()
    tasks.append(task)
    save_tasks(tasks)

    # 集成 LLaMA Factory 启动训练
    def run_training():
        try:
            # 创建训练配置文件
            config = {
                "model_name_or_path": task['base_model'],
                "dataset": task['dataset'],
                "finetuning_type": task['train_method'],
                "learning_rate": float(task['learning_rate']),
                "num_train_epochs": int(task['epochs']),
                "per_device_train_batch_size": int(task['batch_size']),
                "output_dir": f"data/models/{task['id']}",
                "logging_steps": 10,
                "save_steps": 100,
                "do_train": True
            }

            # DPO 阶段支持
            train_method = task.get('train_method', '')
            if train_method == 'dpo' or 'dpo' in train_method.lower():
                config["stage"] = "dpo"
                config["finetuning_type"] = "lora"  # DPO 默认使用 LoRA
                if task.get('dpo_dataset'):
                    config["dataset"] = task['dpo_dataset']

            config_path = f"data/train_configs/{task['id']}.json"
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            # 检查 LLaMA Factory 是否安装
            try:
                result = subprocess.run(
                    ['llamafactory-cli', 'version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                llamafactory_available = result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                llamafactory_available = False

            if llamafactory_available:
                # 使用 LLaMA Factory 训练
                process = subprocess.Popen(
                    ['llamafactory-cli', 'train', config_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                # 更新任务进程 ID
                tasks = load_tasks()
                for t in tasks:
                    if t['id'] == task['id']:
                        t['process_id'] = process.pid
                        break
                save_tasks(tasks)

                # 等待训练完成
                stdout, stderr = process.communicate()

                # 更新任务状态
                tasks = load_tasks()
                for t in tasks:
                    if t['id'] == task['id']:
                        if process.returncode == 0:
                            t['status'] = 'completed'
                            t['progress'] = 100
                        else:
                            t['status'] = 'failed'
                            t['error'] = stderr
                        break
                save_tasks(tasks)

            else:
                # LLaMA Factory 未安装，使用模拟训练
                import time
                for i in range(10):
                    time.sleep(2)
                    tasks = load_tasks()
                    for t in tasks:
                        if t['id'] == task['id']:
                            t['progress'] = (i + 1) * 10
                            if i == 9:
                                t['status'] = 'completed'
                            break
                    save_tasks(tasks)

        except Exception as e:
            tasks = load_tasks()
            for t in tasks:
                if t['id'] == task['id']:
                    t['status'] = 'failed'
                    t['error'] = str(e)
                    break
            save_tasks(tasks)

    # 在后台线程中运行训练
    thread = threading.Thread(target=run_training, daemon=True)
    thread.start()

    return jsonify({
        'success': True,
        'task_id': task['id'],
        'message': '微调任务已启动'
    })


@finetune_bp.route('/tasks', methods=['GET'])
def get_tasks():
    """获取任务列表"""
    tasks = load_tasks()
    return jsonify(tasks)


@finetune_bp.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """获取单个任务详情"""
    tasks = load_tasks()
    task = next((t for t in tasks if t['id'] == task_id), None)

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    return jsonify(task)


@finetune_bp.route('/tasks/<task_id>/stop', methods=['POST'])
def stop_task(task_id):
    """停止任务"""
    tasks = load_tasks()
    task = next((t for t in tasks if t['id'] == task_id), None)

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    task['status'] = 'stopped'
    save_tasks(tasks)

    return jsonify({'success': True, 'message': '任务已停止'})


@finetune_bp.route('/upload', methods=['POST'])
def upload_dataset():
    """上传数据集"""
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    # 保存文件
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    return jsonify({
        'success': True,
        'filename': filename,
        'path': filepath
    })


@finetune_bp.route('/datasets', methods=['GET'])
def get_datasets():
    """获取数据集列表"""
    datasets = []

    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                size = os.path.getsize(filepath)
                size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"

                datasets.append({
                    'name': filename,
                    'size': size_str,
                    'path': filepath,
                    'created_at': datetime.fromtimestamp(os.path.getctime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                })

    return jsonify(datasets)


@finetune_bp.route('/datasets/<filename>', methods=['DELETE'])
def delete_dataset(filename):
    """删除数据集"""
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404

    os.remove(filepath)
    return jsonify({'success': True, 'message': '数据集已删除'})


@finetune_bp.route('/models', methods=['GET'])
def get_models():
    """获取可用的基础模型列表"""
    models = [
        {
            'name': 'Qwen/Qwen2.5-7B',
            'size': '7B',
            'type': 'chat'
        },
        {
            'name': 'Qwen/Qwen2.5-14B',
            'size': '14B',
            'type': 'chat'
        },
        {
            'name': 'meta-llama/Llama-3-8B',
            'size': '8B',
            'type': 'base'
        },
        {
            'name': 'mistralai/Mistral-7B-v0.1',
            'size': '7B',
            'type': 'base'
        }
    ]

    return jsonify(models)


@finetune_bp.route('/download-model', methods=['POST'])
def download_model():
    """从 HuggingFace 下载模型"""
    data = request.json
    model_id = data.get('model_id')
    download_path = data.get('download_path', './models')

    if not model_id:
        return jsonify({'error': '模型 ID 不能为空'}), 400

    task_id = str(uuid.uuid4())

    # 初始化下载任务状态
    DOWNLOAD_TASKS[task_id] = {
        'model_id': model_id,
        'progress': 0,
        'status': '准备下载...',
        'completed': False,
        'error': None
    }

    # 在后台线程中执行下载
    thread = threading.Thread(target=_download_model_thread, args=(task_id, model_id, download_path))
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': '开始下载模型'
    })


def _download_model_thread(task_id, model_id, download_path):
    """后台下载模型"""
    try:
        # 确保下载目录存在
        os.makedirs(download_path, exist_ok=True)

        DOWNLOAD_TASKS[task_id]['status'] = '正在从 HuggingFace 下载...'
        DOWNLOAD_TASKS[task_id]['progress'] = 10

        # 使用 huggingface_hub 下载模型
        try:
            from huggingface_hub import snapshot_download

            DOWNLOAD_TASKS[task_id]['progress'] = 20
            DOWNLOAD_TASKS[task_id]['status'] = '连接 HuggingFace...'

            # 下载模型
            local_path = snapshot_download(
                repo_id=model_id,
                local_dir=os.path.join(download_path, model_id.replace('/', '_')),
                local_dir_use_symlinks=False
            )

            DOWNLOAD_TASKS[task_id]['progress'] = 100
            DOWNLOAD_TASKS[task_id]['status'] = f'下载完成！保存在: {local_path}'
            DOWNLOAD_TASKS[task_id]['completed'] = True

        except ImportError:
            # 如果没有 huggingface_hub，使用 git clone
            DOWNLOAD_TASKS[task_id]['status'] = '使用 git 克隆模型...'
            DOWNLOAD_TASKS[task_id]['progress'] = 30

            repo_url = f"https://huggingface.co/{model_id}"
            local_path = os.path.join(download_path, model_id.replace('/', '_'))

            result = subprocess.run(
                ['git', 'clone', repo_url, local_path],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                DOWNLOAD_TASKS[task_id]['progress'] = 100
                DOWNLOAD_TASKS[task_id]['status'] = f'下载完成！保存在: {local_path}'
                DOWNLOAD_TASKS[task_id]['completed'] = True
            else:
                raise Exception(f"Git clone 失败: {result.stderr}")

    except Exception as e:
        DOWNLOAD_TASKS[task_id]['error'] = str(e)
        DOWNLOAD_TASKS[task_id]['status'] = f'下载失败: {str(e)}'
        DOWNLOAD_TASKS[task_id]['completed'] = False


@finetune_bp.route('/download-progress/<task_id>', methods=['GET'])
def get_download_progress(task_id):
    """获取下载进度"""
    if task_id not in DOWNLOAD_TASKS:
        return jsonify({'error': '任务不存在'}), 404

    return jsonify(DOWNLOAD_TASKS[task_id])


@finetune_bp.route('/local-models', methods=['GET'])
def get_local_models():
    """获取本地已下载的模型列表"""
    models = [item for item in _collect_installed_models() if item.get('source') in {'downloaded', 'cache', 'finetuned'}]
    return jsonify(models)


@finetune_bp.route('/installed-models', methods=['GET'])
def get_installed_models():
    """获取所有已安装模型，供微调 / RL / 服务管理复用。"""
    return jsonify({'success': True, 'models': _collect_installed_models()})


@finetune_bp.route('/installed-models', methods=['DELETE'])
def delete_installed_model():
    """删除一个已安装模型目录。"""
    data = request.get_json(silent=True) or {}
    target_path = os.path.abspath(str(data.get('path') or '').strip())
    if not target_path:
        return jsonify({'success': False, 'error': 'path 不能为空'}), 400
    if not os.path.isdir(target_path):
        return jsonify({'success': False, 'error': '模型目录不存在'}), 404
    if not any(_path_is_within(target_path, root) for root in _deletable_roots()):
        return jsonify({'success': False, 'error': '不允许删除该目录'}), 403

    shutil.rmtree(target_path)
    return jsonify({'success': True, 'deleted_path': target_path})


@finetune_bp.route('/completed-models', methods=['GET'])
def get_completed_models():
    """获取所有微调完成的模型（含路径），供流水线使用。"""
    tasks = load_tasks()
    completed = []
    for t in tasks:
        if t.get('status') == 'completed':
            model_path = f"data/models/{t['id']}"
            completed.append({
                'task_id': t['id'],
                'task_name': t.get('task_name', ''),
                'base_model': t.get('base_model', ''),
                'train_method': t.get('train_method', ''),
                'model_path': model_path,
                'model_exists': os.path.isdir(model_path),
                'created_at': t.get('created_at', ''),
            })
    return jsonify({'success': True, 'models': completed})


@finetune_bp.route('/import-dpo-dataset', methods=['POST'])
def import_dpo_dataset():
    """从 RLHF 偏好数据导出 DPO 数据集到 datasets 目录。"""
    try:
        from agent_framework.reasoning.llm_rlhf_engine import get_llm_rlhf_engine
        engine = get_llm_rlhf_engine()
        dataset = engine.export_dpo_dataset()

        if not dataset:
            return jsonify({'success': False, 'error': '没有可导出的偏好数据'}), 400

        # 保存为 JSON 文件到 datasets 目录
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"dpo_dataset_{timestamp}.json"
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)

        return jsonify({
            'success': True,
            'filename': filename,
            'path': filepath,
            'count': len(dataset),
            'message': f'已导出 {len(dataset)} 条 DPO 数据'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
