"""
多模态处理系统
支持图片、音频、视频的处理和分析
"""

import base64
import io
import os
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from agent_framework.core.config import get_config

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class MediaType(str, Enum):
    """媒体类型"""
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TEXT = "text"


@dataclass
class MediaFile:
    """媒体文件"""
    file_path: str
    media_type: MediaType
    mime_type: str
    size: int
    metadata: Dict[str, Any]


class MultimodalProcessor:
    """多模态处理器"""

    # 支持的格式
    supported_image_formats = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp']
    supported_audio_formats = ['mp3', 'wav', 'ogg', 'm4a', 'flac']
    supported_video_formats = ['mp4', 'avi', 'mov', 'mkv', 'webm']

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        chat_model: Optional[str] = None,
        audio_model: Optional[str] = None,
        tts_model: Optional[str] = None,
        chat_base_url: Optional[str] = None,
        audio_base_url: Optional[str] = None,
        tts_base_url: Optional[str] = None,
        chat_api_key: Optional[str] = None,
        audio_api_key: Optional[str] = None,
        tts_api_key: Optional[str] = None,
    ):
        cfg = get_config()
        default_api_key = (
            api_key
            if api_key is not None
            else os.getenv("MULTIMODAL_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or cfg.llm.api_key
        ) or ""
        self.api_key = default_api_key.strip()
        default_base_url = (
            base_url
            or os.getenv("MULTIMODAL_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or cfg.llm.base_url
            or "https://api.openai.com/v1"
        ).strip().rstrip("/")
        self.base_url = default_base_url
        self.chat_base_url = (chat_base_url or os.getenv("MULTIMODAL_CHAT_BASE_URL") or default_base_url).strip().rstrip("/")
        self.audio_base_url = (audio_base_url or os.getenv("MULTIMODAL_AUDIO_BASE_URL") or default_base_url).strip().rstrip("/")
        self.tts_base_url = (tts_base_url or os.getenv("MULTIMODAL_TTS_BASE_URL") or default_base_url).strip().rstrip("/")
        self.chat_model = (
            chat_model
            or os.getenv("MULTIMODAL_CHAT_MODEL")
            or os.getenv("LLM_MODEL")
            or cfg.llm.model
            or "gpt-4o"
        ).strip()
        self.audio_model = (
            audio_model
            or os.getenv("MULTIMODAL_AUDIO_MODEL")
            or "whisper-1"
        ).strip()
        self.tts_model = (
            tts_model
            or os.getenv("MULTIMODAL_TTS_MODEL")
            or "tts-1"
        ).strip()
        self.chat_api_key = ((chat_api_key or os.getenv("MULTIMODAL_CHAT_API_KEY") or default_api_key) or "").strip()
        self.audio_api_key = ((audio_api_key or os.getenv("MULTIMODAL_AUDIO_API_KEY") or default_api_key) or "").strip()
        self.tts_api_key = ((tts_api_key or os.getenv("MULTIMODAL_TTS_API_KEY") or default_api_key) or "").strip()

    def _headers(self, capability: str = "chat", *, json_content: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        api_key = self._api_key_for(capability)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    def _api_key_for(self, capability: str) -> str:
        if capability == "audio":
            return self.audio_api_key or self.api_key
        if capability == "tts":
            return self.tts_api_key or self.api_key
        return self.chat_api_key or self.api_key

    def _base_url_for(self, capability: str) -> str:
        if capability == "audio":
            return self.audio_base_url or self.base_url
        if capability == "tts":
            return self.tts_base_url or self.base_url
        return self.chat_base_url or self.base_url

    @staticmethod
    def _looks_local(base_url: str) -> bool:
        try:
            host = (urlparse(base_url).hostname or "").lower()
        except Exception:
            return False
        return host in {"127.0.0.1", "0.0.0.0", "localhost", "::1"}

    @staticmethod
    def _env_flag(name: str) -> Optional[bool]:
        value = os.getenv(name)
        if value is None:
            return None
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _probe_models(self, capability: str) -> Dict[str, Any]:
        import requests

        base_url = self._base_url_for(capability)
        try:
            response = requests.get(
                f"{base_url}/models",
                headers=self._headers(capability),
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            models = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(models, list):
                models = []
            return {
                "ok": True,
                "status_code": response.status_code,
                "model_ids": [
                    str(item.get("id") or item.get("model_name") or "").strip()
                    for item in models
                    if isinstance(item, dict)
                ],
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

    def get_runtime_capabilities(self) -> Dict[str, Any]:
        checks = OrderedDict()
        checks["chat"] = self._probe_models("chat")
        if self.audio_base_url != self.chat_base_url or self.audio_api_key != self.chat_api_key:
            checks["audio"] = self._probe_models("audio")
        else:
            checks["audio"] = checks["chat"]
        if self.tts_base_url != self.chat_base_url or self.tts_api_key != self.chat_api_key:
            checks["tts"] = self._probe_models("tts")
        else:
            checks["tts"] = checks["chat"]

        model_name = self.chat_model.lower()
        heuristic_vision = any(token in model_name for token in (
            "vl", "vision", "llava", "minicpm-v", "internvl", "gpt-4o", "omni", "qvq"
        ))
        vision_override = self._env_flag("MULTIMODAL_VISION_ENABLED")
        audio_override = self._env_flag("MULTIMODAL_AUDIO_ENABLED")
        tts_override = self._env_flag("MULTIMODAL_TTS_ENABLED")

        return {
            "configured": {
                "chat": {
                    "base_url": self.chat_base_url,
                    "model": self.chat_model,
                    "api_key_configured": bool(self._api_key_for("chat")),
                    "local_endpoint": self._looks_local(self.chat_base_url),
                },
                "audio": {
                    "base_url": self.audio_base_url,
                    "model": self.audio_model,
                    "api_key_configured": bool(self._api_key_for("audio")),
                    "local_endpoint": self._looks_local(self.audio_base_url),
                },
                "tts": {
                    "base_url": self.tts_base_url,
                    "model": self.tts_model,
                    "api_key_configured": bool(self._api_key_for("tts")),
                    "local_endpoint": self._looks_local(self.tts_base_url),
                },
            },
            "checks": checks,
            "capabilities": {
                "image": {
                    "describe": {"configured": bool(self.chat_model), "verified": bool(checks["chat"].get("ok"))},
                    "ocr": {"configured": bool(self.chat_model), "verified": bool(checks["chat"].get("ok"))},
                    "detect": {"configured": bool(self.chat_model), "verified": bool(checks["chat"].get("ok"))},
                    "classify": {"configured": bool(self.chat_model), "verified": bool(checks["chat"].get("ok"))},
                    "vision_model_likely": vision_override if vision_override is not None else heuristic_vision,
                },
                "audio": {
                    "transcribe": {
                        "configured": bool(self.audio_model),
                        "verified": audio_override if audio_override is not None else bool(checks["audio"].get("ok")),
                    },
                    "translate": {
                        "configured": bool(self.audio_model and self.chat_model),
                        "verified": (
                            audio_override if audio_override is not None else bool(checks["audio"].get("ok"))
                        ) and bool(checks["chat"].get("ok")),
                    },
                    "analyze": {
                        "configured": bool(self.audio_model and self.chat_model),
                        "verified": (
                            audio_override if audio_override is not None else bool(checks["audio"].get("ok"))
                        ) and bool(checks["chat"].get("ok")),
                    },
                },
                "tts": {
                    "speech": {
                        "configured": bool(self.tts_model),
                        "verified": tts_override if tts_override is not None else bool(checks["tts"].get("ok")),
                    }
                },
            },
        }

    def process_image(self, image_path: str, task: str = "describe") -> Dict[str, Any]:
        """
        处理图片

        Args:
            image_path: 图片路径
            task: 任务类型 (describe, ocr, detect, classify)

        Returns:
            处理结果
        """
        if not PIL_AVAILABLE:
            return {
                "success": False,
                "error": "PIL 未安装，请运行: pip install Pillow"
            }

        try:
            # 加载图片
            image = Image.open(image_path)

            # 获取图片信息
            width, height = image.size
            format_name = image.format
            mode = image.mode

            # 转换为 base64
            buffered = io.BytesIO()
            image.save(buffered, format=format_name or 'PNG')
            img_base64 = base64.b64encode(buffered.getvalue()).decode()

            result = {
                "success": True,
                "image_info": {
                    "width": width,
                    "height": height,
                    "format": format_name,
                    "mode": mode,
                    "size": os.path.getsize(image_path)
                },
                "base64": img_base64
            }

            # 根据任务类型处理
            if task == "describe":
                result["description"] = self._describe_image(img_base64)
            elif task == "ocr":
                result["text"] = self._extract_text(img_base64)
            elif task == "detect":
                result["objects"] = self._detect_objects(img_base64)
            elif task == "classify":
                result["categories"] = self._classify_image(img_base64)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _describe_image(self, image_base64: str) -> str:
        """描述图片内容（使用 Vision API）"""
        try:
            import requests

            headers = self._headers("chat")

            payload = {
                "model": self.chat_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请详细描述这张图片的内容"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500
            }

            response = requests.post(
                f"{self._base_url_for('chat')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                return f"API 调用失败: {response.status_code}"

        except Exception as e:
            return f"图片描述失败: {str(e)}"

    def _extract_text(self, image_base64: str) -> str:
        """从图片中提取文字（OCR）"""
        try:
            # 尝试使用 pytesseract
            import pytesseract
            from PIL import Image
            import base64
            import io

            # 解码 base64 图片
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))

            # 执行 OCR
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            return text.strip()

        except ImportError:
            # pytesseract 未安装，尝试使用 OpenAI Vision API
            try:
                import requests

                headers = self._headers("chat")

                payload = {
                    "model": self.chat_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "请提取图片中的所有文字内容，保持原有格式。"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1000
                }

                response = requests.post(
                    f"{self._base_url_for('chat')}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30
                )

                if response.status_code == 200:
                    return response.json()['choices'][0]['message']['content']
                else:
                    return f"OCR 失败: {response.status_code}"

            except Exception as e:
                return f"OCR 功能需要安装 pytesseract 或配置兼容的多模态端点: {str(e)}"

        except Exception as e:
            return f"OCR 失败: {str(e)}"

    def _detect_objects(self, image_base64: str) -> List[Dict]:
        """检测图片中的物体"""
        try:
            # 使用 OpenAI Vision API 进行物体检测
            import requests

            headers = self._headers("chat")

            payload = {
                "model": self.chat_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请识别图片中的所有物体，以 JSON 格式返回，格式为: [{\"object\": \"物体名称\", \"confidence\": 0.95}]"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500
            }

            response = requests.post(
                f"{self._base_url_for('chat')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content']
                # 尝试解析 JSON
                import json
                try:
                    return json.loads(content)
                except:
                    return [{"object": content, "confidence": 0.8}]
            else:
                return []

        except Exception as e:
            return [{"error": f"物体检测失败: {str(e)}"}]

    def _classify_image(self, image_base64: str) -> List[str]:
        """分类图片"""
        try:
            # 使用 OpenAI Vision API 进行图片分类
            import requests

            headers = self._headers("chat")

            payload = {
                "model": self.chat_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请对这张图片进行分类，返回最相关的 3-5 个类别标签。"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 200
            }

            response = requests.post(
                f"{self._base_url_for('chat')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content']
                # 简单解析标签
                tags = [tag.strip() for tag in content.split(',')]
                return tags[:5]
            else:
                return []

        except Exception as e:
            return [f"分类失败: {str(e)}"]

    def process_audio(self, audio_path: str, task: str = "transcribe") -> Dict[str, Any]:
        """
        处理音频

        Args:
            audio_path: 音频路径
            task: 任务类型 (transcribe, translate, analyze)

        Returns:
            处理结果
        """
        try:
            # 获取音频信息
            file_size = os.path.getsize(audio_path)
            file_ext = Path(audio_path).suffix

            result = {
                "success": True,
                "audio_info": {
                    "size": file_size,
                    "format": file_ext
                }
            }

            # 根据任务类型处理
            if task == "transcribe":
                result["text"] = self._transcribe_audio(audio_path)
            elif task == "translate":
                result["translation"] = self._translate_audio(audio_path)
            elif task == "analyze":
                result["analysis"] = self._analyze_audio(audio_path)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _transcribe_audio(self, audio_path: str) -> str:
        """语音转文字（使用 Whisper API）"""
        try:
            import requests

            headers = self._headers("audio", json_content=False)

            with open(audio_path, 'rb') as audio_file:
                files = {
                    'file': audio_file,
                    'model': (None, self.audio_model)
                }

                response = requests.post(
                    f"{self._base_url_for('audio')}/audio/transcriptions",
                    headers=headers,
                    files=files,
                    timeout=60
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('text', '')
                else:
                    return f"API 调用失败: {response.status_code}"

        except Exception as e:
            return f"语音转文字失败: {str(e)}"

    def _translate_audio(self, audio_path: str) -> str:
        """翻译音频"""
        try:
            # 先转录音频
            transcription = self._transcribe_audio(audio_path)

            if not transcription or transcription.startswith("语音转文字失败"):
                return transcription

            # 使用 LLM 翻译文本
            import requests

            headers = self._headers("chat")

            payload = {
                "model": self.chat_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的翻译助手，请将以下文本翻译成中文。"
                    },
                    {
                        "role": "user",
                        "content": transcription
                    }
                ],
                "temperature": 0.3
            }

            response = requests.post(
                f"{self._base_url_for('chat')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                translation = response.json()['choices'][0]['message']['content']
                return translation
            else:
                return f"翻译失败: {response.status_code}"

        except Exception as e:
            return f"音频翻译失败: {str(e)}"

    def _analyze_audio(self, audio_path: str) -> Dict:
        """分析音频（情感、说话人等）"""
        try:
            # 先转录音频
            transcription = self._transcribe_audio(audio_path)

            if not transcription or transcription.startswith("语音转文字失败"):
                return {"error": transcription}

            # 使用 LLM 分析情感和内容
            import requests

            headers = self._headers("chat")

            payload = {
                "model": self.chat_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "请分析以下文本的情感倾向、主题和关键信息，以 JSON 格式返回。"
                    },
                    {
                        "role": "user",
                        "content": transcription
                    }
                ],
                "temperature": 0.3
            }

            response = requests.post(
                f"{self._base_url_for('chat')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                analysis = response.json()['choices'][0]['message']['content']
                return {
                    "transcription": transcription,
                    "analysis": analysis
                }
            else:
                return {"error": f"分析失败: {response.status_code}"}

        except Exception as e:
            return {"error": f"音频分析失败: {str(e)}"}

    def process_video(self, video_path: str, task: str = "analyze") -> Dict[str, Any]:
        """
        处理视频

        Args:
            video_path: 视频路径
            task: 任务类型 (analyze, extract_frames, generate_subtitles)

        Returns:
            处理结果
        """
        try:
            # 获取视频信息
            file_size = os.path.getsize(video_path)
            file_ext = Path(video_path).suffix

            result = {
                "success": True,
                "video_info": {
                    "size": file_size,
                    "format": file_ext
                }
            }

            # 根据任务类型处理
            if task == "analyze":
                result["analysis"] = self._analyze_video(video_path)
            elif task == "extract_frames":
                result["frames"] = self._extract_frames(video_path)
            elif task == "generate_subtitles":
                result["subtitles"] = self._generate_subtitles(video_path)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _analyze_video(self, video_path: str) -> Dict:
        """分析视频内容"""
        try:
            # 提取关键帧
            frames = self._extract_frames(video_path, interval=5)

            if not frames:
                return {"error": "无法提取视频帧"}

            # 分析第一帧作为示例
            first_frame = frames[0] if frames else None

            if first_frame:
                # 使用图片分析功能
                frame_analysis = self.process_image(first_frame, task="describe")

                return {
                    "frame_count": len(frames),
                    "sample_frame_analysis": frame_analysis.get("description", ""),
                    "message": "视频分析基于关键帧采样"
                }
            else:
                return {"error": "无法分析视频"}

        except Exception as e:
            return {"error": f"视频分析失败: {str(e)}"}

    def _extract_frames(self, video_path: str, interval: int = 1) -> List[str]:
        """提取视频帧"""
        try:
            import cv2
            import tempfile

            # 打开视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return []

            frames = []
            frame_count = 0
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_interval = int(fps * interval)  # 每 interval 秒提取一帧

            temp_dir = tempfile.mkdtemp()

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_count % frame_interval == 0:
                    # 保存帧
                    frame_path = f"{temp_dir}/frame_{frame_count}.jpg"
                    cv2.imwrite(frame_path, frame)
                    frames.append(frame_path)

                frame_count += 1

            cap.release()
            return frames

        except ImportError:
            return []  # OpenCV 未安装
        except Exception as e:
            return []

    def _generate_subtitles(self, video_path: str) -> str:
        """生成字幕"""
        try:
            # 1. 提取音频
            import subprocess
            import tempfile

            temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            audio_path = temp_audio.name
            temp_audio.close()

            # 使用 ffmpeg 提取音频
            try:
                subprocess.run(
                    ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'mp3', audio_path],
                    capture_output=True,
                    check=True
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                return "需要安装 ffmpeg 来提取视频音频"

            # 2. 语音识别
            transcription = self._transcribe_audio(audio_path)

            # 3. 清理临时文件
            os.unlink(audio_path)

            # 4. 生成 SRT 格式字幕（简化版）
            if transcription and not transcription.startswith("语音转文字失败"):
                # 简单分段，实际应该根据时间戳
                lines = transcription.split('。')
                srt_content = ""

                for i, line in enumerate(lines):
                    if line.strip():
                        start_time = f"00:00:{i*5:02d},000"
                        end_time = f"00:00:{(i+1)*5:02d},000"
                        srt_content += f"{i+1}\n{start_time} --> {end_time}\n{line.strip()}\n\n"

                return srt_content
            else:
                return transcription

        except Exception as e:
            return f"字幕生成失败: {str(e)}"

    def text_to_speech(self, text: str, voice: str = "alloy") -> bytes:
        """
        文字转语音（TTS）

        Args:
            text: 要转换的文字
            voice: 声音类型 (alloy, echo, fable, onyx, nova, shimmer)

        Returns:
            音频数据（bytes）
        """
        try:
            import requests

            headers = self._headers("tts")

            payload = {
                "model": self.tts_model,
                "input": text,
                "voice": voice
            }

            response = requests.post(
                f"{self._base_url_for('tts')}/audio/speech",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                return response.content
            else:
                raise Exception(f"TTS API 调用失败: {response.status_code}")

        except Exception as e:
            raise Exception(f"文字转语音失败: {str(e)}")


# 全局实例
_processor = None


def get_multimodal_processor() -> MultimodalProcessor:
    """获取多模态处理器实例"""
    global _processor
    if _processor is None:
        _processor = MultimodalProcessor()
    return _processor
