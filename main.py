"""
Screen Translate — 主入口

启动 GUI 控制窗口和翻译流水线。
"""
import sys
import os

# 确保项目根目录在 sys.path 中
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

# 将 PaddleX 缓存目录重定向到项目本地，避免写入用户文件夹 (~/.paddlex/)
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", os.path.join(_BASE_DIR, ".paddlex_cache"))

import wx
from src.python.config.settings import load_config, AppConfig
from src.python.gui.main_window import MainWindow, TrayIcon
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

        # 主窗口（先创建，以便 pipeline 可以回调它的方法）
        self._window = MainWindow(
            config,
            on_toggle_pause=self._toggle_pause,
            on_start=self._start_pipeline,
            on_stop=self._stop_pipeline,
            on_single_translate=self._single_translate,
            on_single_start=self._on_single_start,
            on_single_done=self._on_single_done,
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
            on_cycle_complete=self._on_cycle,
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

    def _start_pipeline(self):
        """初始化并启动流水线"""
        if not self._pipeline.is_running:
            # 先将 GUI 上所有参数写回 config
            if self._window:
                self._window.sync_config_from_gui()
            if not self._pipeline.init():
                wx.MessageBox("Pipeline init failed. Check logs.", "Error",
                              wx.OK | wx.ICON_ERROR)
                return
            self._pipeline.start()

    def _single_translate(self):
        """执行单次翻译"""
        if self._window:
            self._window.sync_config_from_gui()
        self._pipeline.run_once(
            on_start=self._on_single_start,
            on_done=self._on_single_done,
        )

    def _on_single_start(self):
        """单次翻译开始"""
        if self._window:
            self._window._single_in_progress = True
            wx.CallAfter(lambda: self._window._btn_single.Enable(False))

    def _on_single_done(self):
        """单次翻译完成"""
        if self._window:
            self._window._single_in_progress = False
            wx.CallAfter(lambda: self._window._btn_single.Enable(True))

    def _toggle_pause(self):
        if self._pipeline.is_running:
            self._pipeline.toggle_pause()

    def _stop_pipeline(self):
        self._pipeline.stop()

    def _on_status(self, status: str):
        if self._window:
            self._window.update_status(status)

    def _on_cycle(self, cycle):
        if self._window:
            self._window.update_cycle_info(cycle)

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
    print(f"[Main] Cycle interval: {config.pipeline.cycle_interval}s")
    print(f"[Main] UI language: {config.gui.ui_language}")

    # 启动应用
    app = App(config)
    app.MainLoop()


if __name__ == "__main__":
    main()
