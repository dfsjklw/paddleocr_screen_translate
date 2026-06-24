"""
i18n/__init__.py — 国际化模块

提供 UI 文本的中英文切换。
用法:
    from ..i18n import tr, LocaleManager
    label = tr("btn.start")  # 根据当前语言返回 "Start" 或 "开始"
"""

from .strings import STRINGS
from ..config.settings import AppConfig


class LocaleManager:
    """语言管理器 — 单例，持有当前语言并支持回调通知"""

    _instance = None
    _listeners: list = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lang = "en"
        return cls._instance

    @property
    def lang(self) -> str:
        return self._lang

    @lang.setter
    def lang(self, value: str):
        if value not in ("en", "zh"):
            raise ValueError(f"Unsupported language: {value}")
        old = self._lang
        self._lang = value
        if value != old:
            self._notify()

    def tr(self, key: str, **kwargs) -> str:
        """翻译单个 key，支持 {name} 插值"""
        try:
            text = STRINGS[key][self._lang]
        except KeyError:
            return key  # fallback: 返回 key 本身
        if kwargs:
            text = text.format(**kwargs)
        return text

    def toggle(self):
        """切换中英文"""
        self.lang = "zh" if self._lang == "en" else "en"

    def subscribe(self, callback):
        """订阅语言变更通知；callback 无参数"""
        self._listeners.append(callback)

    def unsubscribe(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self):
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                pass


# 全局实例
_locale = LocaleManager()


def init_locale(config: AppConfig):
    """根据配置初始化语言"""
    lang = getattr(config.gui, "ui_language", "en")
    if lang in ("en", "zh"):
        _locale.lang = lang


def tr(key: str, **kwargs) -> str:
    """快捷翻译函数"""
    return _locale.tr(key, **kwargs)


def get_locale() -> LocaleManager:
    return _locale
