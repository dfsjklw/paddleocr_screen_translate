"""
capture/screenshot.py — 全屏截图工具（纯 Win32 GDI）

使用 Win32 GDI BitBlt + GetDIBits 实现屏幕截图，无需 PIL / mss 依赖。
返回 BGR numpy 数组，与 OpenCV / 流水线格式兼容。

从 gui/region_selector.py 提取的独立模块。
"""
import ctypes
import ctypes.wintypes
import numpy as np
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
#  Win32 GDI constants
# ═══════════════════════════════════════════════════════════════════

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0

# GDI function prototypes
_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

_gdi32.CreateCompatibleDC.argtypes = [ctypes.wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = ctypes.wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [ctypes.wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = ctypes.wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [ctypes.wintypes.HDC, ctypes.wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = ctypes.wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = [ctypes.wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = ctypes.wintypes.BOOL
_gdi32.DeleteDC.argtypes = [ctypes.wintypes.HDC]
_gdi32.DeleteDC.restype = ctypes.wintypes.BOOL
_gdi32.BitBlt.argtypes = [
    ctypes.wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.wintypes.DWORD,
]
_gdi32.BitBlt.restype = ctypes.wintypes.BOOL
_gdi32.GetDIBits.argtypes = [
    ctypes.wintypes.HDC, ctypes.wintypes.HBITMAP, ctypes.wintypes.UINT,
    ctypes.wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, ctypes.wintypes.UINT,
]
_gdi32.GetDIBits.restype = ctypes.c_int
_gdi32.CreateDCW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p]
_gdi32.CreateDCW.restype = ctypes.wintypes.HDC

_user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int
_user32.GetDC.argtypes = [ctypes.wintypes.HWND]
_user32.GetDC.restype = ctypes.wintypes.HDC
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]
_user32.GetSystemMetrics.restype = ctypes.c_int


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


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════

SM_CXSCREEN = 0
SM_CYSCREEN = 1


def get_screen_size() -> tuple[int, int]:
    """获取主显示器尺寸（物理像素）。"""
    w = _user32.GetSystemMetrics(SM_CXSCREEN)
    h = _user32.GetSystemMetrics(SM_CYSCREEN)
    return w, h


def capture_screen_region(x: int, y: int, w: int, h: int) -> np.ndarray:
    """
    使用 Win32 GDI（BitBlt + GetDIBits）截取屏幕区域。

    Args:
        x, y: 区域左上角屏幕坐标
        w, h: 区域宽高

    Returns:
        BGR numpy array, shape=(h, w, 3), dtype=np.uint8

    Raises:
        OSError: GDI 操作失败
    """
    hdc_screen = _gdi32.CreateDCW("DISPLAY", None, None, None)
    if not hdc_screen:
        raise OSError("CreateDCW('DISPLAY') failed")

    try:
        hdc_mem = _gdi32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            raise OSError("CreateCompatibleDC failed")

        try:
            hbmp = _gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            if not hbmp:
                raise OSError("CreateCompatibleBitmap failed")

            try:
                old_bmp = _gdi32.SelectObject(hdc_mem, hbmp)

                ok = _gdi32.BitBlt(hdc_mem, 0, 0, w, h,
                                   hdc_screen, x, y, SRCCOPY)
                if not ok:
                    raise OSError(f"BitBlt failed (err={ctypes.get_last_error()})")

                bi = _BITMAPINFOHEADER()
                bi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
                bi.biWidth = w
                bi.biHeight = -h  # negative = top-down DIB
                bi.biPlanes = 1
                bi.biBitCount = 32
                bi.biCompression = BI_RGB

                buf_size = w * h * 4
                buf = (ctypes.c_ubyte * buf_size)()

                lines = _gdi32.GetDIBits(
                    hdc_mem, hbmp, 0, h,
                    ctypes.byref(buf), ctypes.byref(bi), DIB_RGB_COLORS,
                )
                if lines == 0:
                    raise OSError(f"GetDIBits failed (err={ctypes.get_last_error()})")

                # BGRA byte buffer → numpy BGR
                bgra = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4)
                bgr = bgra[:, :, :3][:, :, ::-1].copy()
                return bgr

            finally:
                _gdi32.SelectObject(hdc_mem, old_bmp)
                _gdi32.DeleteObject(hbmp)
        finally:
            _gdi32.DeleteDC(hdc_mem)
    finally:
        _gdi32.DeleteDC(hdc_screen)


def capture_fullscreen() -> np.ndarray:
    """截取全屏画面，返回 BGR numpy array。"""
    w, h = get_screen_size()
    return capture_screen_region(0, 0, w, h)
