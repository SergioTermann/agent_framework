"""
国际化（i18n）系统
支持多语言切换
"""

import agent_framework.core.fast_json as json
import os
from pathlib import Path
from typing import Dict, Optional
from flask import request, session


class I18n:
    """国际化管理器"""

    def __init__(self, locales_dir: str | Path | None = None, default_locale: str = "zh-CN"):
        self.locales_dir = Path(locales_dir) if locales_dir is not None else Path(__file__).resolve().parent.parent / "locales"
        self.default_locale = default_locale
        self.translations: Dict[str, Dict] = {}
        self.load_translations()

    def load_translations(self):
        """加载所有翻译文件"""
        if not self.locales_dir.exists():
            os.makedirs(self.locales_dir, exist_ok=True)
            return

        for file_path in self.locales_dir.glob("*.json"):
            locale = file_path.stem
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.translations[locale] = json.load(f)
            except Exception as e:
                print(f"加载翻译文件失败 {file_path}: {e}")

    def get_locale(self) -> str:
        """获取当前语言"""
        # 1. 从 session 获取
        if 'locale' in session:
            return session['locale']

        # 2. 从请求头获取
        accept_language = request.headers.get('Accept-Language', '')
        if accept_language:
            # 解析 Accept-Language 头
            languages = []
            for lang in accept_language.split(','):
                parts = lang.strip().split(';')
                locale = parts[0]
                quality = 1.0
                if len(parts) > 1 and parts[1].startswith('q='):
                    try:
                        quality = float(parts[1][2:])
                    except ValueError:
                        pass
                languages.append((locale, quality))

            # 按质量排序
            languages.sort(key=lambda x: x[1], reverse=True)

            # 查找支持的语言
            for locale, _ in languages:
                # 精确匹配
                if locale in self.translations:
                    return locale
                # 语言匹配（如 zh-CN -> zh）
                lang = locale.split('-')[0]
                for supported_locale in self.translations.keys():
                    if supported_locale.startswith(lang):
                        return supported_locale

        # 3. 返回默认语言
        return self.default_locale

    def set_locale(self, locale: str):
        """设置当前语言"""
        if locale in self.translations:
            session['locale'] = locale
            return True
        return False

    def translate(self, key: str, locale: Optional[str] = None, **kwargs) -> str:
        """
        翻译文本

        Args:
            key: 翻译键（支持点号分隔，如 'auth.login'）
            locale: 语言代码（如果不指定则使用当前语言）
            **kwargs: 格式化参数

        Returns:
            翻译后的文本
        """
        if locale is None:
            locale = self.get_locale()

        # 获取翻译字典
        translations = self.translations.get(locale, self.translations.get(self.default_locale, {}))

        # 解析键路径
        keys = key.split('.')
        value = translations
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                value = None
                break

        # 如果没找到翻译，返回键本身
        if value is None:
            return key

        # 格式化
        if kwargs:
            try:
                return value.format(**kwargs)
            except (KeyError, ValueError):
                return value

        return value

    def get_available_locales(self) -> Dict[str, str]:
        """获取可用的语言列表"""
        locale_names = {
            'zh-CN': '简体中文',
            'zh-TW': '繁體中文',
            'en-US': 'English',
            'ja-JP': '日本語',
            'ko-KR': '한국어',
            'fr-FR': 'Français',
            'de-DE': 'Deutsch',
            'es-ES': 'Español',
            'ru-RU': 'Русский',
            'ar-SA': 'العربية'
        }

        return {
            locale: locale_names.get(locale, locale)
            for locale in self.translations.keys()
        }

    def get_supported_locales(self) -> list:
        """获取支持的语言代码列表"""
        return list(self.translations.keys())


# 全局实例
_i18n = None


def get_i18n() -> I18n:
    """获取国际化实例"""
    global _i18n
    if _i18n is None:
        _i18n = I18n()
    return _i18n


def t(key: str, **kwargs) -> str:
    """翻译快捷函数"""
    return get_i18n().translate(key, **kwargs)


# Flask 模板过滤器
def init_i18n(app):
    """初始化国际化系统"""
    i18n = get_i18n()

    @app.context_processor
    def inject_i18n():
        """注入翻译函数到模板"""
        return {
            't': t,
            'current_locale': i18n.get_locale(),
            'available_locales': i18n.get_available_locales()
        }

    @app.route('/api/i18n/locale', methods=['GET'])
    def get_current_locale():
        """获取当前语言"""
        return {
            'locale': i18n.get_locale(),
            'available': i18n.get_available_locales()
        }

    @app.route('/api/i18n/locale', methods=['POST'])
    def set_current_locale():
        """设置当前语言"""
        data = request.json
        locale = data.get('locale')

        if i18n.set_locale(locale):
            return {'success': True, 'locale': locale}
        else:
            return {'success': False, 'error': '不支持的语言'}, 400

    @app.route('/api/i18n/translations/<locale>', methods=['GET'])
    def get_translations(locale: str):
        """获取指定语言的所有翻译"""
        translations = i18n.translations.get(locale, {})
        return {'locale': locale, 'translations': translations}
