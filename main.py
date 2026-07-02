"""
Screen Translate — 主入口

启动 GUI 控制窗口和翻译流水线。
"""
import sys
import os

# 确保项目根目录在 sys.path 中
# 兼容 PyInstaller 打包：frozen 时用 sys._MEIPASS，否则用 __file__
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)  # 打包后 config.yaml / 模型目录在 EXE 同级
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

import wx
from src.python.config.settings import load_config, AppConfig
from src.python.gui.main_window import MainWindow, TrayIcon
from src.python.gui.region_selector import RegionSelector
from src.python.capture.screenshot import capture_fullscreen
from src.python.overlay.overlay import OverlayWindow
from src.python.pipeline.pipeline import Pipeline
from src.python.i18n import init_locale, tr


class App(wx.App):
    def __init__(self, config: AppConfig, console_logger=None):
        self._config = config
        self._console_logger = console_logger
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
            console_log_dir=self._console_logger.log_dir if self._console_logger else None,
            on_stop=self._stop_pipeline,
            on_single_translate=self._single_translate,
            on_single_start=self._on_single_start,
            on_single_done=self._on_single_done,
            on_region_translate=self._region_translate,
            on_clear_overlay=self._clear_overlay,
            on_hold_hide_press=self._on_hold_hide_press,
            on_hold_hide_release=self._on_hold_hide_release,
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
                wx.MessageBox(tr("dlg.init_failed"), tr("dlg.error_title"),
                              wx.OK | wx.ICON_ERROR)
                return
            self._pipeline.start()

    def _single_translate(self):
        """执行单次翻译 — 使用全屏截图（Win32 GDI BitBlt）替代 OBS 虚拟摄像头"""
        if getattr(self, '_single_capture_in_progress', False):
            return
        self._single_capture_in_progress = True

        if self._window:
            self._window.sync_config_from_gui()

        # 清除覆盖层，防止截图包含已翻译的文本
        self._overlay.clear()
        self._on_status("Overlay cleared")

        # 隐藏主窗口，避免截图包含 GUI 自身
        if self._window and self._window.IsShown():
            self._window.Hide()

        # 延迟 200ms 让窗口隐藏生效，然后截取全屏
        wx.CallLater(200, self._do_single_capture)

    def _do_single_capture(self):
        """截取全屏并启动翻译流水线"""
        try:
            frame = capture_fullscreen()
        except Exception as e:
            print(f"[Main] Fullscreen screenshot failed: {e}")
            self._on_status(f"Single: screenshot failed: {e}")
            if self._window:
                self._window.Show()
                self._window.Raise()
            self._single_capture_in_progress = False
            return

        # 恢复主窗口
        if self._window:
            self._window.Show()
            self._window.Raise()

        # 在后台线程中运行 OCR + 翻译 + 覆盖
        self._pipeline.run_fullscreen_translate(
            frame=frame,
            on_start=self._on_single_start,
            on_done=self._on_single_done,
        )

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
        import numpy as np

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
        """一键清除屏幕覆盖层（流水线继续运行，下一周期自动重绘）"""
        self._overlay.clear()
        self._on_status("Overlay cleared")

    def _on_hold_hide_press(self):
        """按住隐藏覆盖层（热键按下 / 按钮按下）"""
        self._overlay.push_to_hide()

    def _on_hold_hide_release(self):
        """松开恢复覆盖层（热键松开 / 按钮松开）"""
        self._overlay.release_show()

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

    def _on_single_start(self):
        """单次翻译开始"""
        if self._window:
            self._window._single_in_progress = True
            wx.CallAfter(lambda: self._window._btn_single.Enable(False))

    def _on_single_done(self):
        """单次翻译完成"""
        self._single_capture_in_progress = False
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

        # 清理键盘全局钩子 & 线程
        if self._window:
            self._window._unbind_hotkeys()
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass

        # 销毁覆盖层窗口（必须显式销毁，否则 wx.App 主循环不会退出）
        if self._overlay:
            self._overlay.hide_overlay()
            self._overlay.Destroy()
            self._overlay = None

        # 销毁系统托盘
        if self._tray:
            self._tray.RemoveIcon()
            self._tray.Destroy()

        # 强制退出主循环（确保进程完全退出）
        wx.CallAfter(self.ExitMainLoop)
        event.Skip()


def main():
    # ── 控制台日志捕获（必须在任何 print 之前启动） ──
    _console_logger = None
    try:
        config_path = os.path.join(_BASE_DIR, "config.yaml")
        config = load_config(config_path)

        if config.console_logging.enabled:
            from src.python.logger.console_logger import ConsoleLogger
            # ConsoleLogger 使用内置路径解析，正确处理打包后 EXE 目录
            _console_logger = ConsoleLogger(max_days=config.console_logging.max_days)
            _console_logger.start()
    except Exception as e:
        print(f"[Main] ConsoleLogger init failed: {e}", file=sys.__stderr__)
        config_path = os.path.join(_BASE_DIR, "config.yaml")
        config = load_config(config_path)

    # DPI 感知 (Win10+)
    if sys.platform == "win32":
        try:
            import ctypes
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except Exception:
            pass

    print(f"[Main] Config loaded: source={config.source_lang}, target={config.target_lang}")
    print(f"[Main] Translator: {config.translator.backend} @ {config.translator.llama.url}")
    print(f"[Main] Cycle interval: {config.pipeline.cycle_interval}s")
    print(f"[Main] UI language: {config.gui.ui_language}")

    # 启动应用
    app = App(config, console_logger=_console_logger)
    app.MainLoop()


if __name__ == "__main__":
    main()
