"""
配置热重载系统
支持配置文件变更自动重载，无需重启服务
"""

from __future__ import annotations

import os
import time
import threading
import yaml
from typing import Any, Callable, Dict, Optional
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent


class ConfigReloader:
    """配置重载器"""

    def __init__(self, config_path: str, reload_callback: Optional[Callable] = None):
        """
        初始化配置重载器

        Args:
            config_path: 配置文件路径
            reload_callback: 配置重载后的回调函数
        """
        self.config_path = Path(config_path)
        self.reload_callback = reload_callback
        self.config: Dict[str, Any] = {}
        self.last_modified = 0
        self._lock = threading.RLock()
        self._observer = None
        self._running = False

        # 加载初始配置
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        with self._lock:
            try:
                if not self.config_path.exists():
                    print(f"配置文件不存在: {self.config_path}")
                    return {}

                with open(self.config_path, 'r', encoding='utf-8') as f:
                    if self.config_path.suffix in ['.yaml', '.yml']:
                        self.config = yaml.safe_load(f) or {}
                    elif self.config_path.suffix == '.json':
                        import json
                        self.config = json.load(f)
                    else:
                        print(f"不支持的配置文件格式: {self.config_path.suffix}")
                        return {}

                self.last_modified = self.config_path.stat().st_mtime
                print(f"配置已加载: {self.config_path}")

                return self.config

            except Exception as e:
                print(f"加载配置失败: {e}")
                return {}

    def reload_config(self):
        """重新加载配置"""
        print(f"重新加载配置: {self.config_path}")
        old_config = self.config.copy()
        new_config = self.load_config()

        # 检查配置是否有变化
        if old_config != new_config:
            print("配置已更新")

            # 调用回调函数
            if self.reload_callback:
                try:
                    self.reload_callback(old_config, new_config)
                except Exception as e:
                    print(f"配置重载回调失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._lock:
            keys = key.split('.')
            value = self.config

            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default

                if value is None:
                    return default

            return value

    def set(self, key: str, value: Any):
        """设置配置值（仅内存）"""
        with self._lock:
            keys = key.split('.')
            config = self.config

            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]

            config[keys[-1]] = value

    def save_config(self):
        """保存配置到文件"""
        with self._lock:
            try:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    if self.config_path.suffix in ['.yaml', '.yml']:
                        yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
                    elif self.config_path.suffix == '.json':
                        import json
                        json.dump(self.config, f, indent=2, ensure_ascii=False)

                print(f"配置已保存: {self.config_path}")

            except Exception as e:
                print(f"保存配置失败: {e}")

    def start_watching(self):
        """启动配置文件监控"""
        if self._running:
            return

        self._running = True

        class ConfigFileHandler(FileSystemEventHandler):
            def __init__(self, reloader: ConfigReloader):
                self.reloader = reloader

            def on_modified(self, event):
                if isinstance(event, FileModifiedEvent):
                    if Path(event.src_path) == self.reloader.config_path:
                        # 防止重复触发
                        current_mtime = self.reloader.config_path.stat().st_mtime
                        if current_mtime > self.reloader.last_modified:
                            time.sleep(0.1)  # 等待文件写入完成
                            self.reloader.reload_config()

        event_handler = ConfigFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(
            event_handler,
            str(self.config_path.parent),
            recursive=False
        )
        self._observer.start()

        print(f"开始监控配置文件: {self.config_path}")

    def stop_watching(self):
        """停止配置文件监控"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._running = False
            print("停止监控配置文件")


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self.reloaders: Dict[str, ConfigReloader] = {}
        self._callbacks: Dict[str, list] = {}

    def register(
        self,
        name: str,
        config_path: str,
        auto_reload: bool = True,
        callback: Optional[Callable] = None
    ) -> ConfigReloader:
        """
        注册配置文件

        Args:
            name: 配置名称
            config_path: 配置文件路径
            auto_reload: 是否自动重载
            callback: 重载回调函数
        """
        reloader = ConfigReloader(config_path, callback)
        self.reloaders[name] = reloader

        if auto_reload:
            reloader.start_watching()

        return reloader

    def get_reloader(self, name: str) -> Optional[ConfigReloader]:
        """获取配置重载器"""
        return self.reloaders.get(name)

    def get(self, name: str, key: str, default: Any = None) -> Any:
        """获取配置值"""
        reloader = self.reloaders.get(name)
        if reloader:
            return reloader.get(key, default)
        return default

    def reload_all(self):
        """重载所有配置"""
        for reloader in self.reloaders.values():
            reloader.reload_config()

    def stop_all(self):
        """停止所有监控"""
        for reloader in self.reloaders.values():
            reloader.stop_watching()


# 全局配置管理器
_global_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器"""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager()
    return _global_config_manager


# ═══════════════════════════════════════════════════════════════════════════════
# 使用示例
# ═══════════════════════════════════════════════════════════════════════════════

"""
# 注册配置文件
config_manager = get_config_manager()

def on_config_reload(old_config, new_config):
    print("配置已更新")
    # 重新初始化服务
    reinitialize_services(new_config)

config_manager.register(
    name="app",
    config_path="config.yaml",
    auto_reload=True,
    callback=on_config_reload
)

# 获取配置
api_key = config_manager.get("app", "llm.api_key")
model = config_manager.get("app", "llm.model", default="gpt-4")

# 修改配置（仅内存）
reloader = config_manager.get_reloader("app")
reloader.set("llm.temperature", 0.8)

# 保存配置
reloader.save_config()

# 手动重载
reloader.reload_config()

# 停止监控
config_manager.stop_all()
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 简化版（不依赖 watchdog）
# ═══════════════════════════════════════════════════════════════════════════════

class SimpleConfigReloader:
    """简化版配置重载器（轮询方式）"""

    def __init__(self, config_path: str, check_interval: int = 5):
        self.config_path = Path(config_path)
        self.check_interval = check_interval
        self.config: Dict[str, Any] = {}
        self.last_modified = 0
        self._running = False
        self._thread = None

        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            if not self.config_path.exists():
                return {}

            with open(self.config_path, 'r', encoding='utf-8') as f:
                if self.config_path.suffix in ['.yaml', '.yml']:
                    self.config = yaml.safe_load(f) or {}
                elif self.config_path.suffix == '.json':
                    import json
                    self.config = json.load(f)

            self.last_modified = self.config_path.stat().st_mtime
            return self.config

        except Exception as e:
            print(f"加载配置失败: {e}")
            return {}

    def start_watching(self):
        """启动监控（轮询方式）"""
        if self._running:
            return

        self._running = True

        def check_loop():
            while self._running:
                try:
                    if self.config_path.exists():
                        current_mtime = self.config_path.stat().st_mtime
                        if current_mtime > self.last_modified:
                            print("检测到配置文件变更，重新加载...")
                            self.load_config()
                except Exception as e:
                    print(f"检查配置文件失败: {e}")

                time.sleep(self.check_interval)

        self._thread = threading.Thread(target=check_loop, daemon=True)
        self._thread.start()

    def stop_watching(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.check_interval + 1)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

            if value is None:
                return default

        return value
