"""
统一配置系统 —— 集中管理平台配置

优先级：环境变量 > config.yaml > 默认值

用法：
    from agent_framework.core.config import get_config

    cfg = get_config()
    print(cfg.llm.api_key)
    print(cfg.server.port)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

# ─── 配置数据类 ──────────────────────────────────────────────────────────────


@dataclass
class LLMConfig:
    provider: str = "openai-compatible"
    api_key: str = ""
    model: str = "Qwen/Qwen3-VL-32B-Instruct"
    base_url: str = "https://api.siliconflow.cn/v1"
    timeout: int = 120


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    secret_key: str = "agent-framework-secret-key-change-in-production"
    max_upload_mb: int = 100
    cors_allowed_origins: list[str] = field(default_factory=list)


@dataclass
class AgentDefaults:
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.95
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    max_rounds: int = 15
    stream: bool = True


@dataclass
class DataConfig:
    data_dir: str = "./data"
    workflow_dir: str = "./data/workflows"


@dataclass
class GatewayConfig:
    namespace: str = "/gateway"
    db_path: str = "./data/gateway.db"
    allow_user_id_fallback: bool = False


@dataclass
class WebSearchConfig:
    provider: str = "searxng"
    base_url: str = "http://localhost:8888"
    timeout: int = 10
    max_results: int = 5
    language: str = ""          # 空=auto, 或 zh-CN, en-US
    safesearch: int = 0         # 0=off, 1=moderate, 2=strict
    enabled: bool = True


@dataclass
class WeatherConfig:
    provider: str = "openweathermap"
    api_key: str = ""
    base_url: str = "https://api.openweathermap.org/data/2.5"
    timeout: int = 10
    units: str = "metric"       # metric / imperial / standard
    language: str = "zh_cn"     # API 返回语言
    enabled: bool = True


@dataclass
class TravelConfig:
    provider: str = "amap"      # amap（高德）
    api_key: str = ""
    base_url: str = "https://restapi.amap.com/v3"
    timeout: int = 10
    enabled: bool = True


@dataclass
class ToolsEnabledConfig:
    """统一工具开关 —— 按工具名控制是否注册（默认全部启用）"""
    calculate: bool = True
    get_datetime: bool = True
    sum_numbers: bool = True
    score_grade: bool = True
    to_uppercase: bool = True   # 同时控制 text_utils 所有子工具
    create_todo_list: bool = True
    analyze_causal_chain: bool = True  # 同时控制因果推理所有子工具


@dataclass
class PlatformConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    agent: AgentDefaults = field(default_factory=AgentDefaults)
    data: DataConfig = field(default_factory=DataConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    travel: TravelConfig = field(default_factory=TravelConfig)
    tools_enabled: ToolsEnabledConfig = field(default_factory=ToolsEnabledConfig)


# ─── 加载逻辑 ────────────────────────────────────────────────────────────────

_PACKAGE_CONFIG_FILE = Path(__file__).with_name("config.yaml")
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PROJECT_CONFIG_FILE = _PROJECT_ROOT / "config.yaml"
_CONFIG_ENV_VAR = "AGENT_FRAMEWORK_CONFIG"
_cached: PlatformConfig | None = None
_dotenv_loaded = False


def _ensure_dotenv_loaded() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    if load_dotenv is not None:
        load_dotenv()
    _dotenv_loaded = True


def _load_yaml(path: Path) -> dict[str, Any]:
    """加载 YAML 配置文件（可选依赖）"""
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _first_env(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key)
        if value not in (None, ""):
            return value
    return default


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _resolve_config_file(yaml_path: Path | None = None) -> Path:
    if yaml_path is not None:
        return Path(yaml_path)

    env_path = os.getenv(_CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path)

    if _PROJECT_CONFIG_FILE.exists():
        return _PROJECT_CONFIG_FILE

    return _PACKAGE_CONFIG_FILE


def load_config(yaml_path: Path | None = None) -> PlatformConfig:
    _ensure_dotenv_loaded()
    """加载配置：YAML → 环境变量覆盖 → 默认值"""
    raw = _load_yaml(_resolve_config_file(yaml_path))
    llm_raw = raw.get("llm", {})
    srv_raw = raw.get("server", {})
    agt_raw = raw.get("agent", {})
    dat_raw = raw.get("data", {})
    gtw_raw = raw.get("gateway", {})
    ws_raw = raw.get("web_search", {})
    wth_raw = raw.get("weather", {})
    trv_raw = raw.get("travel", {})
    te_raw = raw.get("tools_enabled", {})

    cfg = PlatformConfig(
        llm=LLMConfig(
            provider=_env("LLM_PROVIDER", llm_raw.get("provider", LLMConfig.provider)),
            api_key=_first_env(
                "LLM_API_KEY",
                "XINFERENCE_API_KEY",
                "VLLM_API_KEY",
                "SILICONFLOW_API_KEY",
                "OPENAI_API_KEY",
                default=llm_raw.get("api_key", ""),
            ),
            model=_first_env(
                "LLM_MODEL",
                "XINFERENCE_MODEL",
                "VLLM_MODEL",
                "DEFAULT_MODEL",
                default=llm_raw.get("model", LLMConfig.model),
            ),
            base_url=_first_env(
                "LLM_BASE_URL",
                "XINFERENCE_BASE_URL",
                "VLLM_BASE_URL",
                "BASE_URL",
                default=llm_raw.get("base_url", LLMConfig.base_url),
            ),
            timeout=int(_env("LLM_TIMEOUT", str(llm_raw.get("timeout", LLMConfig.timeout)))),
        ),
        server=ServerConfig(
            host=_env("HOST", srv_raw.get("host", ServerConfig.host)),
            port=int(_env("PORT", str(srv_raw.get("port", ServerConfig.port)))),
            debug=_env("DEBUG", str(srv_raw.get("debug", False))).lower() in ("true", "1"),
            secret_key=_env("SECRET_KEY", srv_raw.get("secret_key", ServerConfig.secret_key)),
            max_upload_mb=int(srv_raw.get("max_upload_mb", ServerConfig.max_upload_mb)),
            cors_allowed_origins=_split_csv(
                _env(
                    "CORS_ALLOWED_ORIGINS",
                    ",".join(srv_raw.get("cors_allowed_origins", [])),
                )
            ),
        ),
        agent=AgentDefaults(
            temperature=float(agt_raw.get("temperature", AgentDefaults.temperature)),
            max_tokens=int(agt_raw.get("max_tokens", AgentDefaults.max_tokens)),
            top_p=float(agt_raw.get("top_p", AgentDefaults.top_p)),
            frequency_penalty=float(agt_raw.get("frequency_penalty", AgentDefaults.frequency_penalty)),
            presence_penalty=float(agt_raw.get("presence_penalty", AgentDefaults.presence_penalty)),
            max_rounds=int(agt_raw.get("max_rounds", AgentDefaults.max_rounds)),
            stream=bool(agt_raw.get("stream", AgentDefaults.stream)),
        ),
        data=DataConfig(
            data_dir=_env("DATA_DIR", dat_raw.get("data_dir", DataConfig.data_dir)),
            workflow_dir=dat_raw.get("workflow_dir", DataConfig.workflow_dir),
        ),
        gateway=GatewayConfig(
            namespace=_env("GATEWAY_NAMESPACE", gtw_raw.get("namespace", GatewayConfig.namespace)),
            db_path=_env("GATEWAY_DB_PATH", gtw_raw.get("db_path", GatewayConfig.db_path)),
            allow_user_id_fallback=_env(
                "GATEWAY_ALLOW_USER_ID_FALLBACK",
                str(gtw_raw.get("allow_user_id_fallback", GatewayConfig.allow_user_id_fallback)),
            ).lower() in ("true", "1"),
        ),
        web_search=WebSearchConfig(
            provider=ws_raw.get("provider", WebSearchConfig.provider),
            base_url=_env("SEARXNG_BASE_URL", ws_raw.get("base_url", WebSearchConfig.base_url)),
            timeout=int(_env("WEB_SEARCH_TIMEOUT", str(ws_raw.get("timeout", WebSearchConfig.timeout)))),
            max_results=int(ws_raw.get("max_results", WebSearchConfig.max_results)),
            language=ws_raw.get("language", WebSearchConfig.language),
            safesearch=int(ws_raw.get("safesearch", WebSearchConfig.safesearch)),
            enabled=_env("WEB_SEARCH_ENABLED", str(ws_raw.get("enabled", True))).lower() in ("true", "1"),
        ),
        weather=WeatherConfig(
            provider=wth_raw.get("provider", WeatherConfig.provider),
            api_key=_env("WEATHER_API_KEY", wth_raw.get("api_key", "")),
            base_url=_env("WEATHER_BASE_URL", wth_raw.get("base_url", WeatherConfig.base_url)),
            timeout=int(wth_raw.get("timeout", WeatherConfig.timeout)),
            units=wth_raw.get("units", WeatherConfig.units),
            language=wth_raw.get("language", WeatherConfig.language),
            enabled=_env("WEATHER_ENABLED", str(wth_raw.get("enabled", True))).lower() in ("true", "1"),
        ),
        travel=TravelConfig(
            provider=trv_raw.get("provider", TravelConfig.provider),
            api_key=_env("AMAP_API_KEY", trv_raw.get("api_key", "")),
            base_url=_env("AMAP_BASE_URL", trv_raw.get("base_url", TravelConfig.base_url)),
            timeout=int(trv_raw.get("timeout", TravelConfig.timeout)),
            enabled=_env("TRAVEL_ENABLED", str(trv_raw.get("enabled", True))).lower() in ("true", "1"),
        ),
        tools_enabled=ToolsEnabledConfig(
            **{k: _env(f"TOOL_{k.upper()}_ENABLED", str(te_raw.get(k, True))).lower() in ("true", "1")
               for k in ToolsEnabledConfig.__dataclass_fields__},
        ),
    )
    return cfg


def get_config() -> PlatformConfig:
    """获取全局配置单例"""
    global _cached
    if _cached is None:
        _cached = load_config()
    return _cached


def reload_config() -> PlatformConfig:
    """重新加载配置"""
    global _cached
    _cached = load_config()
    return _cached
