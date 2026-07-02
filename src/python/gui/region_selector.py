"""
gui/region_selector.py — Screen region selector for 划屏翻译

Fullscreen overlay that lets the user drag-select a screen region.
Uses pure Win32 GDI API (BitBlt) for screen capture — no PIL dependency.
Returns the selected region coordinates + BGR frame for OCR + translation.
"""
import sys
import numpy as np
import wx
from typing import Optional, Callable

from ..capture.screenshot import capture_screen_region, get_screen_size
from ..i18n import tr


def _win32_capture_full_screen_to_bitmap() -> wx.Bitmap:
    """
    Capture the entire primary screen as a wx.Bitmap using Win32 GDI.

    Returns a 32-bit RGB wx.Bitmap suitable for GDI+ rendering.
    """
    w, h = get_screen_size()

    # Capture using Win32 GDI via screenshot module
    bgr = capture_screen_region(0, 0, w, h)

    # BGR → RGB for wx.Bitmap
    rgb = bgr[:, :, ::-1].copy()
    bmp = wx.Bitmap.FromBuffer(w, h, rgb)
    return bmp


# ═══════════════════════════════════════════════════════════════════
#  RegionSelector
# ═══════════════════════════════════════════════════════════════════

class RegionSelector(wx.Frame):
    """
    Fullscreen region selection window.

    Uses Win32 GDI (BitBlt + GetDIBits) for all screen capture operations.
    No PIL / mss dependency for capture.

    Flow:
    1. Capture full screen via BitBlt → wx.Bitmap background
    2. Display as fullscreen window with dim overlay
    3. User drags to select a clear region
    4. On release: hide, BitBlt the region, invoke callback(x, y, w, h, bgr_frame)
    5. ESC / right-click: cancel, invoke on_cancel()
    """

    DIM_ALPHA = 140
    BORDER_COLOR = wx.Colour(0x25, 0x63, 0xEB)  # #2563EB
    BORDER_WIDTH = 2

    def __init__(
        self,
        on_region_selected: Callable[[int, int, int, int, np.ndarray], None],
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        self._on_region_selected = on_region_selected
        self._on_cancel = on_cancel

        # Capture full screen as wx.Bitmap using Win32 GDI
        self._screenshot_bmp: Optional[wx.Bitmap] = None
        try:
            self._screenshot_bmp = _win32_capture_full_screen_to_bitmap()
        except Exception as e:
            print(f"[RegionSelector] Win32 full-screen capture failed: {e}")

        # Screen dimensions
        self._screen_w, self._screen_h = get_screen_size()

        # Selection state
        self._start_x: int = -1
        self._start_y: int = -1
        self._end_x: int = -1
        self._end_y: int = -1
        self._dragging: bool = False

        # Create fullscreen frame
        style = wx.NO_BORDER | wx.STAY_ON_TOP | wx.FRAME_NO_TASKBAR
        super().__init__(None, title="Region Selector", style=style)
        self.SetSize((self._screen_w, self._screen_h))
        self.SetPosition((0, 0))

        # Main panel
        panel = wx.Panel(self, size=(self._screen_w, self._screen_h))
        panel.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        # Bind events
        panel.Bind(wx.EVT_PAINT, self._on_paint)
        panel.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        panel.Bind(wx.EVT_MOTION, self._on_motion)
        panel.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        panel.Bind(wx.EVT_RIGHT_DOWN, self._on_cancel_event)
        panel.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        panel.SetFocus()
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_down)

        self.Show(True)
        self.Raise()
        self.SetFocus()

    # ── Event Handlers ────────────────────────────────────────────

    def _on_paint(self, event):
        """Paint the dimmed screenshot with clear selection rectangle."""
        dc = wx.AutoBufferedPaintDC(self.GetChildren()[0])
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        w, h = self._screen_w, self._screen_h

        # 1. Draw the original screenshot
        if self._screenshot_bmp and self._screenshot_bmp.IsOk():
            gc.DrawBitmap(self._screenshot_bmp, 0, 0, w, h)

        # 2. Draw dim overlay — skip selection rectangle to show original
        dim_color = wx.Colour(0, 0, 0, self.DIM_ALPHA)
        brush = gc.CreateBrush(wx.Brush(dim_color))
        gc.SetBrush(brush)
        gc.SetPen(wx.TRANSPARENT_PEN)

        if self._dragging and self._start_x >= 0 and self._end_x >= 0:
            rx, ry, rw, rh = self._get_selection_rect()
            if rw > 0 and rh > 0:
                # Top
                if ry > 0:
                    gc.DrawRectangle(0, 0, w, ry)
                # Bottom
                if ry + rh < h:
                    gc.DrawRectangle(0, ry + rh, w, h - ry - rh)
                # Left
                if rx > 0:
                    gc.DrawRectangle(0, ry, rx, rh)
                # Right
                if rx + rw < w:
                    gc.DrawRectangle(rx + rw, ry, w - rx - rw, rh)

                # Selection border
                pen = wx.Pen(self.BORDER_COLOR, self.BORDER_WIDTH)
                gc.SetPen(pen)
                gc.SetBrush(wx.TRANSPARENT_BRUSH)
                gc.DrawRectangle(rx, ry, rw, rh)

                # Size label
                size_text = tr("region.dimensions", w=rw, h=rh)
                font = wx.Font(11, wx.FONTFAMILY_DEFAULT,
                              wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
                gc.SetFont(font, wx.Colour(255, 255, 255))
                tw, th, _, _ = gc.GetFullTextExtent(size_text)
                label_x = rx + max(0, (rw - tw) // 2)
                label_y = ry + rh + 4 if ry + rh + th + 8 < h else ry - th - 4
                if label_y < 0:
                    label_y = ry + 4
                gc.SetBrush(gc.CreateBrush(wx.Brush(wx.Colour(0, 0, 0, 180))))
                gc.SetPen(wx.TRANSPARENT_PEN)
                gc.DrawRectangle(label_x - 4, label_y - 2, tw + 8, th + 4)
                gc.SetFont(font, wx.Colour(255, 255, 255))
                gc.DrawText(size_text, label_x, label_y)
        else:
            gc.DrawRectangle(0, 0, w, h)

        # 3. Instructions if not dragging
        if not self._dragging:
            instr = tr("region.instructions")
            lines = instr.split("\n")
            font = wx.Font(14, wx.FONTFAMILY_DEFAULT,
                          wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
            gc.SetFont(font, wx.Colour(255, 255, 255, 230))

            line_data = []
            for line in lines:
                tw, th, _, _ = gc.GetFullTextExtent(line)
                line_data.append((line, tw, th))

            total_h = sum(th for _, _, th in line_data) + (len(lines) - 1) * 6
            start_y = (h - total_h) // 2
            for line, tw, th in line_data:
                x = (w - tw) // 2
                gc.SetBrush(gc.CreateBrush(wx.Brush(wx.Colour(0, 0, 0, 160))))
                gc.SetPen(wx.TRANSPARENT_PEN)
                gc.DrawRectangle(x - 8, start_y - 4, tw + 16, th + 8)
                gc.SetFont(font, wx.Colour(255, 255, 255, 230))
                gc.DrawText(line, x, start_y)
                start_y += th + 6

        del gc

    def _on_left_down(self, event):
        self._start_x = event.GetX()
        self._start_y = event.GetY()
        self._end_x = self._start_x
        self._end_y = self._start_y
        self._dragging = True
        self.Refresh()

    def _on_motion(self, event):
        if self._dragging and event.Dragging():
            self._end_x = max(0, min(event.GetX(), self._screen_w - 1))
            self._end_y = max(0, min(event.GetY(), self._screen_h - 1))
            self.Refresh()

    def _on_left_up(self, event):
        if not self._dragging:
            return

        self._end_x = max(0, min(event.GetX(), self._screen_w - 1))
        self._end_y = max(0, min(event.GetY(), self._screen_h - 1))
        self._dragging = False

        rx, ry, rw, rh = self._get_selection_rect()

        if rw < 10 or rh < 10:
            print(f"[RegionSelector] Selection too small ({rw}x{rh}), cancelling")
            self._do_cancel()
            return

        # Hide ourselves so we don't appear in the capture
        self.Hide()

        # Capture the selected region using Win32 GDI (BitBlt)
        try:
            frame = capture_screen_region(rx, ry, rw, rh)
        except Exception as e:
            print(f"[RegionSelector] Win32 region capture failed: {e}")
            self._do_cancel()
            return

        print(f"[RegionSelector] Region selected: ({rx}, {ry}, {rw}, {rh}) "
              f"via Win32 GDI BitBlt")
        self._on_region_selected(rx, ry, rw, rh, frame)
        self.Close()

    def _on_cancel_event(self, event):
        self._do_cancel()

    def _on_key_down(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self._do_cancel()
        else:
            event.Skip()

    def _do_cancel(self):
        print("[RegionSelector] Selection cancelled")
        self.Hide()
        if self._on_cancel:
            self._on_cancel()
        self.Close()

    # ── Helpers ───────────────────────────────────────────────────

    def _get_selection_rect(self) -> tuple[int, int, int, int]:
        """Get normalized selection rectangle (x, y, w, h)."""
        x1, y1 = self._start_x, self._start_y
        x2, y2 = self._end_x, self._end_y
        return (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
