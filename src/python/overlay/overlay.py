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
    font_size: int | None = None  # None = 使用全局配置字号


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
        self._user_hidden = False           # 用户按住隐藏键时跳过显示
        self._font_size = config.font_size
        self._font_family = config.font_family
        self._bg_opacity = int(config.background_opacity * 255)
        self._bg_color = _parse_hex_color(config.background_color)
        self._text_color = _parse_hex_color(config.text_color)
        self._exclude_capture = config.exclude_from_capture
        self._min_font_size = getattr(config, 'min_font_size', 8)
        self._stack_shrink = getattr(config, 'stack_shrink', True)

        # 缓存字体对象
        self._cached_font: Optional[wx.Font] = None
        # 字号→字体映射缓存（用于堆叠缩小）
        self._font_cache: dict[int, wx.Font] = {}

        # 获取工作区尺寸（排除任务栏区域，防止全屏置顶窗口导致任务栏自动隐藏）
        if wx.Display.GetCount() > 0:
            work_area = wx.Display(0).GetClientArea()
            screen_w = work_area.GetWidth()
            screen_h = work_area.GetHeight()
            screen_x = work_area.GetX()
            screen_y = work_area.GetY()
        else:
            screen_w, screen_h = 1920, 1080
            screen_x, screen_y = 0, 0
        self._screen_w = screen_w
        self._screen_h = screen_h

        # 创建工作区大小的无边框窗口
        super().__init__(
            None,
            title="ScreenTranslate Overlay",
            pos=(screen_x, screen_y),
            size=(screen_w, screen_h),
            style=wx.NO_BORDER | wx.STAY_ON_TOP | wx.FRAME_NO_TASKBAR,
        )

        # 设置窗口扩展样式
        self._setup_window()

        # 窗口不立即显示，由 pipeline 生命周期控制显示时机

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

    def push_to_hide(self):
        """（用户按住隐藏键时）隐藏窗口但保留内容。线程安全。"""
        wx.CallAfter(self._push_to_hide_impl)

    def release_show(self):
        """（用户松开隐藏键时）恢复窗口显示。线程安全。"""
        wx.CallAfter(self._release_show_impl)

    # ── 主线程实现 ──────────────────────────────────────────────────

    def _set_items_impl(self, items: list[OverlayItem]):
        """（主线程）原子替换覆盖项并重绘"""
        self._items = items
        # 用户正在按住隐藏键 → 只存不显示
        if self._user_hidden:
            return
        if not self.IsShown():
            if items:
                self.Show(True)
            else:
                return  # 窗口未显示且无内容，无需操作
        # 窗口已显示：有内容时绘制，无内容时渲染透明覆盖层
        self.Raise()
        self._render_to_layered_window()

    def _clear_impl(self):
        """（主线程）清除覆盖项 — 渲染透明覆盖层而非隐藏窗口"""
        self._items = []
        self._user_hidden = False  # 清除时自动解除隐藏状态
        if self.IsShown():
            # 渲染全透明覆盖层，避免隐藏/显示窗口触发 Windows 任务栏逻辑
            self._render_to_layered_window()

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

    def _push_to_hide_impl(self):
        """（主线程）按住隐藏 — 隐藏窗口但保留内容"""
        self._user_hidden = True
        if self.IsShown():
            self.Show(False)

    def _release_show_impl(self):
        """（主线程）松开恢复 — 如果之前有内容则重新显示"""
        if not self._user_hidden:
            return
        self._user_hidden = False
        if self._items:
            self.Show(True)
            self.Raise()
            self._render_to_layered_window()

    # ── 运行时配置更新 ─────────────────────────────────────────────

    def apply_config(self, config: OverlayConfig):
        """运行时更新覆盖层渲染参数。线程安全。"""
        wx.CallAfter(self._apply_config_impl, config)

    def _apply_config_impl(self, config: OverlayConfig):
        """（主线程）更新渲染参数并触发重绘"""
        self._config = config
        self._font_size = config.font_size
        self._font_family = config.font_family
        self._bg_opacity = int(config.background_opacity * 255)
        self._bg_color = _parse_hex_color(config.background_color)
        self._text_color = _parse_hex_color(config.text_color)
        self._min_font_size = config.min_font_size
        self._stack_shrink = config.stack_shrink
        # 清空字体缓存，下次渲染时重建
        self._cached_font = None
        self._font_cache.clear()
        # 如果当前有内容则立即重绘
        if self._items and self.IsShown():
            self._render_to_layered_window()

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

        # 堆叠检测缩小：计算重叠组的缩小字号（结果写入 item.font_size）
        self._compute_shrink_font_sizes(gc)

        # 绘制所有文本项
        font = self._get_font()
        gc.SetFont(font, self._text_color)
        for item in self._items:
            self._draw_item(gc, item)

        # 重置 item.font_size（避免影响下次渲染）
        for item in self._items:
            item.font_size = None

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
            if not src_dc:
                print("[Overlay] CreateCompatibleDC failed — GDI resource exhausted")
                sys.stdout.flush()
                return

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
            if not h_bmp:
                print("[Overlay] CreateDIBSection failed — GDI resource exhausted")
                sys.stdout.flush()
                _gdi32.DeleteDC(src_dc)
                return
            if not ppv_bits:
                print("[Overlay] CreateDIBSection returned null bits")
                sys.stdout.flush()
                _gdi32.DeleteObject(h_bmp)
                _gdi32.DeleteDC(src_dc)
                return

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

    def _get_font_for_size(self, size: int) -> wx.Font:
        """获取或创建指定字号的字体（缓存复用）

        限制字号最小为 1，防止无效字体导致的 GDI+ 崩溃。
        """
        size = max(1, size)
        if size not in self._font_cache:
            self._font_cache[size] = wx.Font(
                size, wx.FONTFAMILY_DEFAULT,
                wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL,
                faceName=self._font_family,
            )
        return self._font_cache[size]

    @staticmethod
    def _rects_overlap(
        r1: tuple[int, int, int, int],
        r2: tuple[int, int, int, int],
    ) -> bool:
        """AABB 矩形相交测试"""
        x1, y1, w1, h1 = r1
        x2, y2, w2, h2 = r2
        return not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)

    def _measure_text_extent(
        self, gc: wx.GraphicsContext, text: str, font_size: int,
    ) -> tuple[int, int]:
        """测量文本在指定字号下的像素宽高，不修改 GC 的永久状态

        返回 (width, height)，即使 GDI+ 调用失败也返回安全默认值。
        """
        try:
            font = self._get_font_for_size(font_size)
            gc.SetFont(font, self._text_color)
            tw, th, _, _ = gc.GetFullTextExtent(text)
            return tw, th
        except Exception as e:
            print(f"[Overlay] _measure_text_extent error: {e}")
            sys.stdout.flush()
            # 返回基于字号的安全默认值
            return font_size * len(text), font_size + 4

    def _compute_item_rect(
        self, gc: wx.GraphicsContext, item: OverlayItem, font_size: int,
    ) -> tuple[int, int, int, int]:
        """计算 item 在给定字号下的背景矩形坐标 (x, y, w, h)

        逻辑与 _draw_item 完全一致，用于堆叠检测中的尺寸测量。
        """
        padding = 4
        margin = 2
        x = item.x - margin
        y = item.y - margin
        if item.text:
            tw, th = self._measure_text_extent(gc, item.text, font_size)
            rect_w = tw + padding * 2
            rect_h = th + padding * 2
        else:
            rect_w = item.w + margin * 2
            rect_h = item.h + margin * 2
        return (x, y, rect_w, rect_h)

    def _compute_shrink_font_sizes(self, gc: wx.GraphicsContext):
        """检测堆叠重叠并计算每个 item 的缩小字号

        流程：
        1. 计算所有 item 在配置字号下的背景矩形
        2. 两两检测相交 → 构建无向图（邻接表）
        3. BFS 查找连通分量（重叠组）
        4. 对每组从配置字号向下迭代，直到组内无重叠或达到最小字号
        5. 将结果字号写入 item.font_size

        整段包裹 try-except 防止 GDI+ 原生崩溃导致进程退出。
        """
        if not self._stack_shrink:
            return
        n = len(self._items)
        if n <= 1:
            return

        try:
            # Step 1: 计算初始矩形
            rects = [self._compute_item_rect(gc, item, self._font_size) for item in self._items]

            # Step 2: 构建重叠邻接表（仅含文本的 item 参与重叠检测）
            adj = [set() for _ in range(n)]
            for i in range(n):
                if not self._items[i].text:
                    continue
                for j in range(i + 1, n):
                    if not self._items[j].text:
                        continue
                    if self._rects_overlap(rects[i], rects[j]):
                        adj[i].add(j)
                        adj[j].add(i)

            # Step 3: BFS 找连通分量
            visited = [False] * n
            groups: list[list[int]] = []
            for i in range(n):
                if not visited[i] and self._items[i].text and adj[i]:
                    group = []
                    stack = [i]
                    visited[i] = True
                    while stack:
                        v = stack.pop()
                        group.append(v)
                        for u in adj[v]:
                            if not visited[u]:
                                visited[u] = True
                                stack.append(u)
                    groups.append(group)

            # Step 4: 对每个重叠组迭代缩小字号
            for group in groups:
                current = self._font_size
                while current > self._min_font_size:
                    group_rects = {}
                    for idx in group:
                        group_rects[idx] = self._compute_item_rect(
                            gc, self._items[idx], current,
                        )
                    # 检查组内是否有重叠
                    has_overlap = False
                    for a in range(len(group)):
                        for b in range(a + 1, len(group)):
                            if self._rects_overlap(
                                group_rects[group[a]], group_rects[group[b]],
                            ):
                                has_overlap = True
                                break
                        if has_overlap:
                            break
                    if not has_overlap:
                        break
                    current -= 1

                # 将最终字号赋给组内所有 item
                for idx in group:
                    self._items[idx].font_size = current
        except Exception as e:
            print(f"[Overlay] _compute_shrink_font_sizes error: {e}")
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            # 出错时不做任何缩小，保持原样

    def _draw_item(self, gc: wx.GraphicsContext, item: OverlayItem):
        """绘制单个文本项：先填充不透明背景遮盖原文，再绘制译文

        即使译文为空，也绘制背景矩形以遮盖原文区域。
        支持 item 级别的字号覆盖（堆叠检测缩小用）。
        """
        padding = 4
        margin = 2
        x, y = item.x - margin, item.y - margin

        # 计算背景矩形尺寸：有文本时匹配文本大小，无文本时覆盖原始文本框
        if item.text:
            font_size = item.font_size if item.font_size is not None else self._font_size
            font = self._get_font_for_size(font_size)
            gc.SetFont(font, self._text_color)
            try:
                tw, th, _, _ = gc.GetFullTextExtent(item.text)
            except Exception:
                # GetFullTextExtent 失败时使用保守估计
                tw, th = font_size * len(item.text), font_size + 4
            rect_w = tw + padding * 2
            rect_h = th + padding * 2
        else:
            rect_w = item.w + margin * 2
            rect_h = item.h + margin * 2

        # 1. 先绘制高不透明度背景，遮盖原文（总是绘制，即使译文为空）
        bg_color = wx.Colour(self._bg_color.Red(), self._bg_color.Green(), self._bg_color.Blue(), self._bg_opacity)
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
