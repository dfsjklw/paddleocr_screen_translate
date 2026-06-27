"""
overlay/overlay.py — 覆盖层模块

使用 wxPython 创建透明覆盖窗口，在屏幕上绘制翻译文本。
通过 Win32 API SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)
使覆盖层对 DXGI 捕获不可见，防止递归翻译。

线程安全设计：
- 所有公共方法均可从任意线程安全调用
- 内部通过 wx.CallAfter 将 GUI 操作派发到主线程
- set_items() 原子性地替换全部覆盖项，避免 clear+update 的双重刷新

渲染方式：
- 使用 UpdateLayeredWindow + 32 位 per-pixel alpha 位图
- 文字背景使用半透明黑色，文字区域外完全透明
"""
import sys
import ctypes
import ctypes.wintypes
import numpy as np
import wx
from dataclasses import dataclass
from typing import Optional

from ..config.settings import OverlayConfig


# Win32 常量
WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
ULW_ALPHA = 0x00000002

_user32 = ctypes.windll.user32 if sys.platform == "win32" else None
_gdi32 = ctypes.windll.gdi32 if sys.platform == "win32" else None

# 设置 Win32 API 的 argtypes，确保 64 位句柄正确传递
if _gdi32:
    _gdi32.CreateCompatibleDC.argtypes = [ctypes.wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = ctypes.wintypes.HDC
    _gdi32.CreateDIBSection.argtypes = [
        ctypes.wintypes.HDC, ctypes.c_void_p, ctypes.wintypes.UINT,
        ctypes.c_void_p, ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD,
    ]
    _gdi32.CreateDIBSection.restype = ctypes.wintypes.HBITMAP
    _gdi32.SelectObject.argtypes = [ctypes.wintypes.HDC, ctypes.wintypes.HGDIOBJ]
    _gdi32.SelectObject.restype = ctypes.wintypes.HGDIOBJ
    _gdi32.DeleteObject.argtypes = [ctypes.wintypes.HGDIOBJ]
    _gdi32.DeleteObject.restype = ctypes.wintypes.BOOL
    _gdi32.DeleteDC.argtypes = [ctypes.wintypes.HDC]
    _gdi32.DeleteDC.restype = ctypes.wintypes.BOOL
if _user32:
    _user32.UpdateLayeredWindow.argtypes = [
        ctypes.wintypes.HWND, ctypes.wintypes.HDC, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.wintypes.HDC, ctypes.c_void_p,
        ctypes.wintypes.COLORREF, ctypes.c_void_p, ctypes.wintypes.DWORD,
    ]
    _user32.UpdateLayeredWindow.restype = ctypes.wintypes.BOOL


# ── Win32 结构体（模块级别，避免重复定义）──

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.wintypes.DWORD),
        ("biWidth", ctypes.wintypes.LONG),
        ("biHeight", ctypes.wintypes.LONG),
        ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD),
        ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.wintypes.BYTE),
        ("BlendFlags", ctypes.wintypes.BYTE),
        ("SourceConstantAlpha", ctypes.wintypes.BYTE),
        ("AlphaFormat", ctypes.wintypes.BYTE),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.wintypes.LONG),
        ("y", ctypes.wintypes.LONG),
    ]


class _SIZE(ctypes.Structure):
    _fields_ = [
        ("cx", ctypes.wintypes.LONG),
        ("cy", ctypes.wintypes.LONG),
    ]


def _parse_hex_color(hex_str: str) -> wx.Colour:
    """解析 #RRGGBB 格式的十六进制颜色"""
    hex_str = hex_str.lstrip("#")
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return wx.Colour(r, g, b)


@dataclass
class OverlayItem:
    """单个覆盖项"""
    x: int
    y: int
    w: int
    h: int
    text: str
    original_text: str = ""


class OverlayWindow(wx.Frame):
    """
    透明覆盖窗口

    特性：
    - 全屏大小，透明背景
    - 置顶显示 (WS_EX_TOPMOST)
    - 鼠标穿透 (WS_EX_TRANSPARENT)
    - 对 DXGI 不可见 (WDA_EXCLUDEFROMCAPTURE)
    - 线程安全：所有公开方法可通过 wx.CallAfter 从任意线程调用
    - 使用 UpdateLayeredWindow 实现 per-pixel alpha 渲染
    """

    def __init__(self, config: OverlayConfig):
        self._config = config
        self._items: list[OverlayItem] = []
        self._font_size = config.font_size
        self._font_family = config.font_family
        self._bg_opacity = int(config.background_opacity * 255)
        self._text_color = _parse_hex_color(config.text_color)
        self._exclude_capture = config.exclude_from_capture

        # 缓存字体对象
        self._cached_font: Optional[wx.Font] = None

        # 获取屏幕尺寸
        screen_w = wx.Display(0).GetGeometry().GetWidth() if wx.Display.GetCount() > 0 else 1920
        screen_h = wx.Display(0).GetGeometry().GetHeight() if wx.Display.GetCount() > 0 else 1080
        self._screen_w = screen_w
        self._screen_h = screen_h

        # 创建全屏无边框窗口
        super().__init__(
            None,
            title="ScreenTranslate Overlay",
            pos=(0, 0),
            size=(screen_w, screen_h),
            style=wx.NO_BORDER | wx.STAY_ON_TOP | wx.FRAME_NO_TASKBAR,
        )

        # 设置窗口扩展样式
        self._setup_window()

        # 注意：不立即显示窗口，以免全屏置顶窗口覆盖任务栏区域导致 Windows 任务栏消失。
        # 窗口仅在 set_items() 收到有效内容时才自动显示。

    def _setup_window(self):
        """设置窗口扩展样式"""
        if sys.platform != "win32":
            return

        hwnd = self.GetHandle()

        ex_style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_ex = ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex)

        # WDA_EXCLUDEFROMCAPTURE: 使覆盖层对屏幕捕获不可见
        if self._exclude_capture:
            ret = _user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if ret:
                print("[Overlay] WDA_EXCLUDEFROMCAPTURE enabled")
                sys.stdout.flush()
            else:
                print("[Overlay] WDA_EXCLUDEFROMCAPTURE failed (requires Win10 2004+)")
                sys.stdout.flush()

    # ── 线程安全的公开 API ──────────────────────────────────────────

    def set_items(self, items: list[OverlayItem]):
        """原子性地替换所有覆盖项。线程安全。"""
        wx.CallAfter(self._set_items_impl, items)

    def clear(self):
        """清除所有覆盖项。线程安全。"""
        wx.CallAfter(self._clear_impl)

    def show_overlay(self):
        """显示并提升覆盖层。线程安全。"""
        wx.CallAfter(self._show_impl)

    def hide_overlay(self):
        """隐藏覆盖层。线程安全。"""
        wx.CallAfter(self._hide_impl)

    # ── 主线程实现 ──────────────────────────────────────────────────

    def _set_items_impl(self, items: list[OverlayItem]):
        """（主线程）原子替换覆盖项并重绘"""
        self._items = items
        if items and not self.IsShown():
            self.Show(True)
        elif not items and self.IsShown():
            self.Show(False)
            return
        self._render_to_layered_window()

    def _clear_impl(self):
        """（主线程）清除覆盖项并重绘"""
        self._items = []
        if self.IsShown():
            self.Show(False)

    def _show_impl(self):
        """（主线程）显示覆盖层"""
        if not self.IsShown():
            self.Show(True)
        self.Raise()
        if self._items:
            self._render_to_layered_window()

    def _hide_impl(self):
        """（主线程）隐藏覆盖层"""
        if self.IsShown():
            self.Show(False)

    # ── Per-pixel Alpha 渲染 ───────────────────────────────────────

    def _render_to_layered_window(self):
        """
        将覆盖项渲染到 32 位 per-pixel alpha 位图，通过 UpdateLayeredWindow 显示。

        流程：
        1. 创建 32 位 RGBA 位图并用 GDI+ 绘制
        2. 使用 numpy 高效转换为 BGRA 格式
        3. 调用 UpdateLayeredWindow 将位图合成到屏幕
        """
        if sys.platform != "win32" or not self.IsShown():
            return

        w, h = self._screen_w, self._screen_h

        # 创建 32 位 RGBA 位图 — 使用 wx.Image 确保 alpha 通道被正确初始化
        image = wx.Image(w, h)
        image.InitAlpha()
        # 显式将 RGB 和 alpha 数据置零，使位图初始为全透明。
        # GDI+ 默认 SourceOver 混合模式下，用透明画刷绘制不会改变目标像素，
        # 因此不能依赖 GDI+ 来清除背景，必须直接在位图数据中清零。
        image.SetData(b'\x00' * (w * h * 3))
        image.SetAlpha(b'\x00' * (w * h))
        bitmap = wx.Bitmap(image, 32)
        if not bitmap.IsOk():
            print("[Overlay] Failed to create 32-bit bitmap")
            sys.stdout.flush()
            return

        # 在 memory DC 上使用 GDI+ 绘制
        mdc = wx.MemoryDC()
        mdc.SelectObject(bitmap)

        gc = wx.GraphicsContext.Create(mdc)
        if gc is None:
            mdc.SelectObject(wx.NullBitmap)
            print("[Overlay] Failed to create GraphicsContext")
            return

        # 全透明清除
        gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))
        gc.SetPen(wx.Pen(wx.Colour(0, 0, 0, 0)))
        gc.DrawRectangle(0, 0, w, h)

        # 绘制所有文本项
        font = self._get_font()
        gc.SetFont(font, self._text_color)
        for item in self._items:
            self._draw_item(gc, item)

        del gc
        mdc.SelectObject(wx.NullBitmap)

        # 使用 numpy 高效转换像素格式
        try:
            img = bitmap.ConvertToImage()
            rgb = np.frombuffer(img.GetData(), dtype=np.uint8).reshape(h, w, 3)
            alpha = np.frombuffer(img.GetAlpha(), dtype=np.uint8).reshape(h, w, 1)

            # RGB -> BGRA (numpy 向量化，比 Python 循环快 ~1000x)
            bgra = np.dstack([
                rgb[:, :, 2],   # B
                rgb[:, :, 1],   # G
                rgb[:, :, 0],   # R
                alpha[:, :, 0], # A
            ]).tobytes()
        except Exception as e:
            print(f"[Overlay] Pixel conversion error: {e}")
            return

        # 调用 UpdateLayeredWindow
        hwnd = self.GetHandle()
        screen_dc = wx.ScreenDC()
        hdc_screen = screen_dc.GetHDC()
        # GetHDC() 返回原始 GDI HDC（虽然标记为 deprecated，但
        # GetHandle() 返回的不是 HDC 而是 wx 内部句柄，无法用于 GDI API）
        # ctypes argtypes 已设为 wintypes.HDC，64 位句柄可安全传递

        try:
            src_dc = _gdi32.CreateCompatibleDC(hdc_screen)

            bi = _BITMAPINFOHEADER()
            bi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bi.biWidth = w
            bi.biHeight = -h  # top-down
            bi.biPlanes = 1
            bi.biBitCount = 32
            bi.biCompression = 0  # BI_RGB

            ppv_bits = ctypes.c_void_p()
            h_bmp = _gdi32.CreateDIBSection(
                src_dc, ctypes.byref(bi), 0,
                ctypes.byref(ppv_bits), None, 0,
            )

            ctypes.memmove(ppv_bits, bgra, len(bgra))
            old_bmp = _gdi32.SelectObject(src_dc, h_bmp)

            blend = _BLENDFUNCTION()
            blend.BlendOp = 0   # AC_SRC_OVER
            blend.BlendFlags = 0
            blend.SourceConstantAlpha = 255
            blend.AlphaFormat = 1  # AC_SRC_ALPHA

            pt_dst = _POINT(0, 0)
            src_size = _SIZE(w, h)
            pt_src = _POINT(0, 0)

            result = _user32.UpdateLayeredWindow(
                hwnd,
                hdc_screen,
                ctypes.byref(pt_dst),
                ctypes.byref(src_size),
                src_dc,
                ctypes.byref(pt_src),
                0,
                ctypes.byref(blend),
                ULW_ALPHA,
            )

            if not result:
                err = ctypes.get_last_error()
                print(f"[Overlay] UpdateLayeredWindow failed, error={err}")
                sys.stdout.flush()

            _gdi32.SelectObject(src_dc, old_bmp)
            _gdi32.DeleteObject(h_bmp)
            _gdi32.DeleteDC(src_dc)

        except Exception as e:
            print(f"[Overlay] Render error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # ScreenDC 在 wxPython 4.2+ 中无 ReleaseHDC，
            # HDC 随 ScreenDC 对象销毁自动释放
            del screen_dc

    # ── 绘制 ────────────────────────────────────────────────────────

    def _get_font(self) -> wx.Font:
        """获取缓存字体"""
        if self._cached_font is None:
            self._cached_font = wx.Font(
                self._font_size, wx.FONTFAMILY_DEFAULT,
                wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL,
                faceName=self._font_family,
            )
        return self._cached_font

    def _draw_item(self, gc: wx.GraphicsContext, item: OverlayItem):
        """绘制单个文本项：先填充不透明背景遮盖原文，再绘制译文

        即使译文为空，也绘制背景矩形以遮盖原文区域。
        """
        padding = 4
        margin = 2
        x, y = item.x - margin, item.y - margin

        # 计算背景矩形尺寸：有文本时匹配文本大小，无文本时覆盖原始文本框
        if item.text:
            tw, th, _, _ = gc.GetFullTextExtent(item.text)
            rect_w = tw + padding * 2
            rect_h = th + padding * 2
        else:
            rect_w = item.w + margin * 2
            rect_h = item.h + margin * 2

        # 1. 先绘制高不透明度背景，遮盖原文（总是绘制，即使译文为空）
        bg_color = wx.Colour(0, 0, 0, self._bg_opacity)
        gc.SetBrush(wx.Brush(bg_color))
        gc.SetPen(wx.Pen(wx.Colour(0, 0, 0, 0)))
        gc.DrawRectangle(x, y, rect_w, rect_h)

        # 2. 再在背景上绘制译文（仅当有文本时）
        if item.text:
            text_x = item.x + padding
            text_y = item.y + padding
            gc.DrawText(item.text, text_x, text_y)

    # ── 向后兼容 ────────────────────────────────────────────────────

    def update_items(self, items: list[OverlayItem]):
        """更新覆盖层显示的文本项（向后兼容）"""
        self.set_items(items)
