"""
多模态 API
提供图片、音频、视频处理接口
"""

from flask import Blueprint, request, jsonify, send_file
from agent_framework.web.multimodal_processor import get_multimodal_processor
from werkzeug.utils import secure_filename
import os
import tempfile

multimodal_bp = Blueprint('multimodal', __name__, url_prefix='/api/multimodal')

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'flac'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}


def allowed_file(filename, extensions):
    """检查文件扩展名"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in extensions


@multimodal_bp.route('/image/upload', methods=['POST'])
def upload_image():
    """上传图片"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "没有文件"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "文件名为空"}), 400

        if not allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            return jsonify({"error": "不支持的文件格式"}), 400

        # 保存文件
        filename = secure_filename(file.filename)
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(temp_path)

        return jsonify({
            "success": True,
            "file_path": temp_path,
            "filename": filename
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@multimodal_bp.route('/image/process', methods=['POST'])
def process_image():
    """处理图片"""
    try:
        data = request.json
        image_path = data.get('image_path')
        task = data.get('task', 'describe')  # describe, ocr, detect, classify

        if not image_path or not os.path.exists(image_path):
            return jsonify({"error": "图片不存在"}), 400

        processor = get_multimodal_processor()
        result = processor.process_image(image_path, task)

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@multimodal_bp.route('/audio/upload', methods=['POST'])
def upload_audio():
    """上传音频"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "没有文件"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "文件名为空"}), 400

        if not allowed_file(file.filename, ALLOWED_AUDIO_EXTENSIONS):
            return jsonify({"error": "不支持的文件格式"}), 400

        filename = secure_filename(file.filename)
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(temp_path)

        return jsonify({
            "success": True,
            "file_path": temp_path,
            "filename": filename
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@multimodal_bp.route('/audio/transcribe', methods=['POST'])
def transcribe_audio():
    """语音转文字"""
    try:
        data = request.json
        audio_path = data.get('audio_path')

        if not audio_path or not os.path.exists(audio_path):
            return jsonify({"error": "音频文件不存在"}), 400

        processor = get_multimodal_processor()
        result = processor.process_audio(audio_path, task='transcribe')

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@multimodal_bp.route('/audio/tts', methods=['POST'])
def text_to_speech():
    """文字转语音"""
    try:
        data = request.json
        text = data.get('text')
        voice = data.get('voice', 'alloy')

        if not text:
            return jsonify({"error": "文本不能为空"}), 400

        processor = get_multimodal_processor()
        audio_data = processor.text_to_speech(text, voice)

        # 保存到临时文件
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        temp_file.write(audio_data)
        temp_file.close()

        return send_file(
            temp_file.name,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name='speech.mp3'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@multimodal_bp.route('/video/upload', methods=['POST'])
def upload_video():
    """上传视频"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "没有文件"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "文件名为空"}), 400

        if not allowed_file(file.filename, ALLOWED_VIDEO_EXTENSIONS):
            return jsonify({"error": "不支持的文件格式"}), 400

        filename = secure_filename(file.filename)
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(temp_path)

        return jsonify({
            "success": True,
            "file_path": temp_path,
            "filename": filename
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@multimodal_bp.route('/video/process', methods=['POST'])
def process_video():
    """处理视频"""
    try:
        data = request.json
        video_path = data.get('video_path')
        task = data.get('task', 'analyze')  # analyze, extract_frames, generate_subtitles

        if not video_path or not os.path.exists(video_path):
            return jsonify({"error": "视频文件不存在"}), 400

        processor = get_multimodal_processor()
        result = processor.process_video(video_path, task)

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@multimodal_bp.route('/capabilities', methods=['GET'])
def get_capabilities():
    """???????"""
    processor = get_multimodal_processor()
    runtime = processor.get_runtime_capabilities()
    capabilities = {
        "image": {
            "formats": list(ALLOWED_IMAGE_EXTENSIONS),
            "tasks": ["describe", "ocr", "detect", "classify"],
            "runtime": runtime["capabilities"]["image"],
        },
        "audio": {
            "formats": list(ALLOWED_AUDIO_EXTENSIONS),
            "tasks": ["transcribe", "translate", "analyze"],
            "runtime": runtime["capabilities"]["audio"],
        },
        "video": {
            "formats": list(ALLOWED_VIDEO_EXTENSIONS),
            "tasks": ["analyze", "extract_frames", "generate_subtitles"]
        },
        "tts": {
            "voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
            "runtime": runtime["capabilities"]["tts"],
        }
    }

    return jsonify({
        "success": True,
        "capabilities": capabilities,
        "runtime": runtime,
    })
