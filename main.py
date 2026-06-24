"""
Screen Translate — 主入口

启动 GUI 控制窗口和翻译流水线。
"""
import sys
import os

# 确保项目根目录在 sys.path 中
# 兼容 PyInstaller 打包：frozen 时用 sys._MEIPASS，否则用 __file__
if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

# 将 PaddleX 缓存目录重定向到项目本地，避免写入用户文件夹 (~/.paddlex/)
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", os.path.join(_BASE_DIR, ".paddlex_cache"))

import wx
from src.python.config.settings import load_config, AppConfig
from src.python.gui.main_window import MainWindow, TrayIcon
from src.python.gui.region_selector import RegionSelector
from src.python.overlay.overlay import OverlayWindow
from src.python.pipeline.pipeline import Pipeline
from src.python.i18n import init_locale


class App(wx.App):
    def __init__(self, config: AppConfig):
        self._config = config
        self._pipeline: Pipeline = None
        self._overlay: OverlayWindow = None
        self._tray: TrayIcon = None
        self._window: MainWindow = None
        super().__init__(redirect=False)

    def OnInit(self):
        config = self._config

        # 初始化国际化
        init_locale(config)

        # 覆盖层窗口
        self._overlay = OverlayWindow(config.overlay)

        # 主窗口
        self._window = MainWindow(
            config,
            on_region_translate=self._region_translate,
            on_clear_overlay=self._clear_overlay,
            on_region_start=self._on_region_start,
            on_region_done=self._on_region_done,
        )

        # 设置 OCR 和翻译结果回调
        def on_ocr_result(cid, boxes, dms, rms):
            if self._window:
                self._window.update_ocr_result(cid, boxes, dms, rms)

        def on_translation_result(cid, pairs, tms):
            if self._window:
                self._window.update_translation_result(cid, pairs, tms)

        # 主流水线
        self._pipeline = Pipeline(
            config,
            overlay=self._overlay,
            on_status_change=self._on_status,
            on_ocr_result=on_ocr_result,
            on_translation_result=on_translation_result,
        )

        self._window.Show(True)
        self.SetTopWindow(self._window)

        # 系统托盘
        self._tray = TrayIcon(self._window)

        # 窗口关闭事件
        self._window.Bind(wx.EVT_CLOSE, self._on_close)

        return True

    def _region_translate(self):
        """执行划屏翻译 — 清除覆盖层，让用户选择屏幕区域"""
        # 1. 清除屏幕上的所有覆盖层
        self._overlay.clear()
        self._on_status("Overlay cleared")

        # 2. 隐藏主窗口以便选择屏幕区域
        if self._window and self._window.IsShown():
            self._window.Hide()

        # 3. 短暂延迟让覆盖层清除和窗口隐藏生效
        wx.CallLater(200, self._show_region_selector)

    def _show_region_selector(self):
        """显示区域选择器"""
        self._on_status("Region: selecting")
        RegionSelector(
            on_region_selected=self._on_region_selected,
            on_cancel=self._on_region_cancelled,
        )

    def _on_region_selected(self, left: int, top: int, width: int, height: int, frame):
        """用户完成区域选择"""
        # 恢复主窗口
        if self._window:
            self._window.Show()
            self._window.Raise()
            self._window.sync_config_from_gui()

        # 在后台线程中运行 OCR + 翻译 + 覆盖
        self._pipeline.run_region_translate(
            frame=frame,
            region_left=left,
            region_top=top,
            on_start=self._on_region_start,
            on_done=self._on_region_done,
        )

    def _on_region_cancelled(self):
        """用户取消区域选择"""
        if self._window:
            self._window.Show()
            self._window.Raise()
        self._on_status("Ready")

    def _clear_overlay(self):
        """一键清除屏幕覆盖层"""
        self._overlay.clear()
        self._on_status("Overlay cleared")

    def _on_region_start(self):
        """划屏翻译开始"""
        if self._window:
            self._window._region_in_progress = True
            wx.CallAfter(lambda: self._window._btn_region.Enable(False))

    def _on_region_done(self):
        """划屏翻译完成"""
        if self._window:
            self._window._region_in_progress = False
            wx.CallAfter(lambda: self._window._btn_region.Enable(True))

    def _on_status(self, status: str):
        if self._window:
            self._window.update_status(status)

    def _on_close(self, event):
        """清理并退出"""
        self._pipeline.shutdown()
        if self._tray:
            self._tray.RemoveIcon()
            self._tray.Destroy()
        event.Skip()


def main():
    # DPI 感知 (Win10+)
    if sys.platform == "win32":
        try:
            import ctypes
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except Exception:
            pass

    # 加载配置
    config_path = os.path.join(_BASE_DIR, "config.yaml")
    config = load_config(config_path)
    print(f"[Main] Config loaded: source={config.source_lang}, target={config.target_lang}")
    print(f"[Main] Translator: {config.translator.backend} @ {config.translator.llama.url}")
    print(f"[Main] UI language: {config.gui.ui_language}")

    # 启动应用
    app = App(config)
    app.MainLoop()


if __name__ == "__main__":
    main()
