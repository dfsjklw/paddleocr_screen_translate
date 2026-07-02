"""
gui/main_window.py — wxPython GUI 主窗口 (Modern UI)

Modern flat-design control panel with:
- Tabbed notebook layout (Control / OCR / Translator / Overlay / Capture / Hotkeys / Logging / Results)
- Unicode icon buttons with colored accents
- Custom ToggleSwitch widgets
- Dark-themed live result panel
- Persistent status bar

All public API and business logic preserved from the original implementation.
"""
import wx
import wx.adv
import sys
import os
from typing import Optional, Callable

from ..config.settings import AppConfig
from ..logger.cycle_logger import CycleLog
from ..i18n import tr, get_locale, LocaleManager


# ═══════════════════════════════════════════════════════════════════
#  Color Scheme
# ═══════════════════════════════════════════════════════════════════

PRIMARY    = wx.Colour(0x25, 0x63, 0xEB)  # #2563EB blue accent
PRIMARY_HV = wx.Colour(0x1D, 0x4E, 0xD8)  # hover
SUCCESS    = wx.Colour(0x10, 0xB9, 0x81)  # #10B981 green
DANGER     = wx.Colour(0xEF, 0x44, 0x44)  # #EF4444 red
WARNING_   = wx.Colour(0xF5, 0x9E, 0x0B)  # #F59E0B amber
BG_PAGE    = wx.Colour(0xF8, 0xFA, 0xFC)  # #F8FAFC page bg
BG_CARD    = wx.Colour(0xFF, 0xFF, 0xFF)  # white cards
BG_DARK    = wx.Colour(0x1E, 0x1E, 0x1E)  # dark result panel
TEXT_MAIN  = wx.Colour(0x1E, 0x29, 0x3B)  # #1E293B dark slate
TEXT_MUTED = wx.Colour(0x94, 0xA3, 0xB8)  # #94A3B8 muted
TEXT_DARK  = wx.Colour(0xD4, 0xD4, 0xD4)  # light on dark
BORDER     = wx.Colour(0xE2, 0xE8, 0xF0)  # #E2E8F0
WHITE      = wx.Colour(0xFF, 0xFF, 0xFF)
TOGGLE_ON  = PRIMARY
TOGGLE_OFF = wx.Colour(0xCB, 0xD5, 0xE1)  # #CBD5E1
BTN_DEFAULT = wx.Colour(0xF1, 0xF5, 0xF9)  # #F1F5F9

# ═══════════════════════════════════════════════════════════════════
#  Custom Toggle Switch
# ═══════════════════════════════════════════════════════════════════

class _PillTrack(wx.Panel):
    """The actual painted pill toggle — only the track + knob, no text."""

    TRACK_W = 44
    TRACK_H = 24
    KNOB_R = 10

    def __init__(self, parent):
        super().__init__(parent, size=(self.TRACK_W, self.TRACK_H))
        self._value = False
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((self.TRACK_W, self.TRACK_H))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_click)

    def GetValue(self) -> bool:
        return self._value

    def SetValue(self, val: bool):
        if val != self._value:
            self._value = val
            self.Refresh()

    def _on_click(self, event):
        self._value = not self._value
        self.Refresh()
        # Propagate the click to the parent ToggleSwitch
        evt = wx.CommandEvent(wx.EVT_CHECKBOX.typeId, self.GetParent().GetId())
        evt.SetEventObject(self.GetParent())
        evt.SetInt(int(self._value))
        self.GetParent().GetEventHandler().ProcessEvent(evt)

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)

        track_w, track_h = self.TRACK_W, self.TRACK_H
        knob_d = self.KNOB_R * 2

        if self._value:
            track_color = TOGGLE_ON
            knob_x = track_w - knob_d - 2
        else:
            track_color = TOGGLE_OFF
            knob_x = 2

        # Track
        gc.SetBrush(gc.CreateBrush(wx.Brush(track_color)))
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.DrawRoundedRectangle(0, 0, track_w, track_h, 12)

        # Knob
        gc.SetBrush(gc.CreateBrush(wx.Brush(WHITE)))
        gc.DrawEllipse(knob_x, 2, knob_d, knob_d)

        del gc


class ToggleSwitch(wx.Panel):
    """Modern pill-shaped toggle switch replacing wx.CheckBox.

    Composite widget:
        [_PillTrack]  [wx.StaticText label]

    Usage identical to wx.CheckBox:
        ts = ToggleSwitch(parent, label="Enable feature")
        ts.SetValue(True)
        ts.Bind(wx.EVT_CHECKBOX, handler)
        val = ts.GetValue()
    """

    def __init__(self, parent, label="", size=None):
        super().__init__(parent, size=size or (-1, 28))

        # Inherit parent background so we blend into the card background
        self.SetBackgroundColour(parent.GetBackgroundColour())

        # Horizontal layout: pill track + label
        row = wx.BoxSizer(wx.HORIZONTAL)

        self._pill = _PillTrack(self)
        row.Add(self._pill, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self._label_ctrl = wx.StaticText(self, label=label)
        self._label_ctrl.SetForegroundColour(TEXT_MAIN)
        row.Add(self._label_ctrl, 0, wx.ALIGN_CENTER_VERTICAL)

        self.SetSizer(row)

        # Click on label area also toggles (pill handles its own clicks)
        self._label_ctrl.Bind(wx.EVT_LEFT_DOWN, self._on_label_click)

    def GetValue(self) -> bool:
        return self._pill.GetValue()

    def SetValue(self, val: bool):
        self._pill.SetValue(val)

    def SetLabel(self, label: str):
        self._label_ctrl.SetLabel(label)

    def _on_label_click(self, event):
        """Toggle when the label text is clicked."""
        self._pill._on_click(event)


# ═══════════════════════════════════════════════════════════════════
#  Helper: Styled Button
# ═══════════════════════════════════════════════════════════════════

def _make_btn(parent, label: str, color=None, size=(-1, 36), bold=False) -> wx.Button:
    """Create a modern flat button with custom colors."""
    btn = wx.Button(parent, label=label, size=size)
    if color:
        btn.SetBackgroundColour(color)
        btn.SetForegroundColour(WHITE)
    else:
        btn.SetBackgroundColour(BTN_DEFAULT)
        btn.SetForegroundColour(TEXT_MAIN)
    if bold:
        f = btn.GetFont()
        f.SetWeight(wx.FONTWEIGHT_BOLD)
        btn.SetFont(f)
    btn.SetWindowStyleFlag(wx.BORDER_NONE)
    return btn


# ═══════════════════════════════════════════════════════════════════
#  Helper: Labeled Input Row
# ═══════════════════════════════════════════════════════════════════

def _make_labeled_input(parent, label: str, value: str, size=(80, -1),
                        cb=None) -> tuple[wx.TextCtrl, wx.StaticText, wx.BoxSizer]:
    """Create Label | TextCtrl horizontal row. Returns (ctrl, label_widget, sizer)."""
    sz = wx.BoxSizer(wx.HORIZONTAL)
    lbl = wx.StaticText(parent, label=label)
    lbl.SetForegroundColour(TEXT_MAIN)
    sz.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
    ctrl = wx.TextCtrl(parent, value=value, size=size)
    sz.Add(ctrl, 0, wx.LEFT, 5)
    return ctrl, lbl, sz


def _make_float_input(parent, label: str, value: float, size=(65, -1),
                      cb=None) -> tuple[wx.TextCtrl, wx.StaticText, wx.BoxSizer]:
    return _make_labeled_input(parent, label, f"{value:.4g}", size, cb)


def _make_int_input(parent, label: str, value: int, size=(65, -1),
                    cb=None) -> tuple[wx.TextCtrl, wx.StaticText, wx.BoxSizer]:
    return _make_labeled_input(parent, label, str(value), size, cb)


def _section_label(parent, text: str) -> wx.StaticText:
    """Create a bold section heading."""
    st = wx.StaticText(parent, label=text)
    f = st.GetFont()
    f.SetWeight(wx.FONTWEIGHT_BOLD)
    f.SetPointSize(f.GetPointSize() + 1)
    st.SetFont(f)
    st.SetForegroundColour(TEXT_MAIN)
    return st


def _hint_label(parent, text: str) -> wx.StaticText:
    """Create a small muted hint label."""
    st = wx.StaticText(parent, label=text)
    f = st.GetFont()
    f.SetPointSize(max(7, f.GetPointSize() - 2))
    st.SetFont(f)
    st.SetForegroundColour(TEXT_MUTED)
    return st


# ═══════════════════════════════════════════════════════════════════
#  MainWindow
# ═══════════════════════════════════════════════════════════════════

class MainWindow(wx.Frame):
    """Modern main control window with tabbed layout."""

    _MAX_RESULT_CHARS = 8000

    def __init__(
        self,
        config: AppConfig,
        on_toggle_pause: Callable[[], None],
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        console_log_dir: str | None = None,
        on_single_translate: Optional[Callable[[], None]] = None,
        on_single_start: Optional[Callable[[], None]] = None,
        on_single_done: Optional[Callable[[], None]] = None,
        on_ocr_result: Optional[Callable[[int, list, float, float], None]] = None,
        on_translation_result: Optional[Callable[[int, list, float], None]] = None,
        on_region_translate: Optional[Callable[[], None]] = None,
        on_clear_overlay: Optional[Callable[[], None]] = None,
        on_hold_hide_press: Optional[Callable[[], None]] = None,
        on_hold_hide_release: Optional[Callable[[], None]] = None,
        on_region_start: Optional[Callable[[], None]] = None,
        on_region_done: Optional[Callable[[], None]] = None,
    ):
        super().__init__(None, title=tr("app.title"), size=(520, 660))
        self._config = config
        self._console_log_dir = console_log_dir
        self._on_toggle = on_toggle_pause
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_single = on_single_translate
        self._on_single_start = on_single_start
        self._on_single_done = on_single_done
        self._on_ocr = on_ocr_result
        self._on_trans = on_translation_result
        self._on_region = on_region_translate
        self._on_clear = on_clear_overlay
        self._on_hold_hide_press = on_hold_hide_press
        self._on_hold_hide_release = on_hold_hide_release
        self._on_region_start = on_region_start
        self._on_region_done = on_region_done

        # State
        self._single_in_progress = False
        self._region_in_progress = False
        self._pipeline_running = False
        self._paused = False
        self._hold_hide_active = False      # 按住隐藏按钮状态

        # Dynamic labels registry (for language switching)
        self._dynamic_labels: list[tuple[wx.Control, str, dict]] = []
        # Toggle switches (needs special handling for labels)
        self._toggles: list[ToggleSwitch] = []

        # Locale
        self._locale = get_locale()
        self._locale.subscribe(self._on_language_changed)

        # Build UI
        self._create_ui()
        self._setup_hotkeys()
        self.SetBackgroundColour(BG_PAGE)
        self.Center()

    # ── Language Switching ─────────────────────────────────────────

    def _on_language_changed(self):
        self._refresh_ui_texts()

    def _on_lang_button(self, event):
        self._locale.toggle()
        self._config.gui.ui_language = self._locale.lang
        self._btn_lang.SetLabel(tr("btn.lang_toggle"))

    def _refresh_ui_texts(self):
        """Refresh all UI texts after language change."""
        self.SetTitle(tr("app.title"))
        self._btn_lang.SetLabel(tr("btn.lang_toggle"))
        self._btn_lang.SetToolTip(tr("btn.lang_toggle_tooltip"))

        # Tab labels
        for i, key in enumerate(["tab.control", "tab.ocr", "tab.translator",
                                  "tab.overlay", "tab.capture", "tab.hotkeys",
                                  "tab.logging", "tab.result"]):
            if i < self._notebook.GetPageCount():
                self._notebook.SetPageText(i, tr(key))

        # Core buttons
        self._btn_start.SetLabel(tr("btn.start"))
        self._btn_single.SetLabel(tr("btn.single"))
        self._btn_single.SetToolTip(tr("tooltip.single"))
        self._btn_region.SetLabel(tr("btn.region_translate"))
        self._btn_region.SetToolTip(tr("tooltip.region"))
        self._btn_clear.SetLabel(tr("btn.clear_overlay"))
        self._btn_clear.SetToolTip(tr("tooltip.clear_overlay"))
        self._btn_hold_hide.SetLabel(
            tr("btn.hold_hide_release") if self._hold_hide_active else tr("btn.hold_hide")
        )
        self._btn_hold_hide.SetToolTip(tr("tooltip.hold_hide"))
        if self._paused:
            self._btn_pause.SetLabel(tr("btn.resume"))
        else:
            self._btn_pause.SetLabel(tr("btn.pause"))
        self._btn_stop.SetLabel(tr("btn.stop"))
        self._btn_test_url.SetLabel(tr("btn.test"))
        self._btn_apply_hotkeys.SetLabel(tr("btn.apply_hotkeys"))

        # Toggle labels
        self._tb_exclude.SetLabel(tr("cb.exclude_capture"))
        self._tb_log.SetLabel(tr("cb.logging"))
        self._tb_console_log.SetLabel(tr("cb.console_logging"))
        self._tb_stack_shrink.SetLabel(tr("field.stack_shrink"))

        # Downscale button
        self._update_downscale_button_label()

        # Upscale button
        self._update_upscale_button_label()

        # Dynamic labels
        for ctrl, key, kwargs in self._dynamic_labels:
            if isinstance(ctrl, wx.StaticText):
                ctrl.SetLabel(tr(key, **kwargs))
            elif isinstance(ctrl, wx.Button):
                ctrl.SetLabel(tr(key, **kwargs))

        # Console log labels
        log_dir = self._console_log_dir or self._config.resolve_path(self._config.console_logging.log_dir)
        self._console_log_path_label.SetLabel(tr("label.console_log_path", path=log_dir))
        self._console_log_hint_label.SetLabel(tr("label.console_log_hint"))
        self._btn_open_log_folder.SetLabel(tr("btn.open_log_folder"))

        # Hotkey hint
        self._refresh_hotkey_label()

        # Status bar — 保留流水线运行状态
        if self._pipeline_running:
            if self._paused:
                self._status_dot.SetState("paused")
                self._status_text.SetLabel(tr("status.paused"))
            else:
                self._status_dot.SetState("running")
                self._status_text.SetLabel(tr("status.running"))
        else:
            self._status_dot.SetState("stopped")
            self._status_text.SetLabel(tr("status.ready"))
        self.Layout()

    def _update_downscale_button_label(self):
        if self._config.pipeline.downscale_max_size > 0:
            self._btn_downscale.SetLabel(tr("downscale.on"))
        else:
            self._btn_downscale.SetLabel(tr("downscale.off"))

    def _update_upscale_button_label(self):
        if self._config.pipeline.upscale_small_image:
            self._btn_upscale.SetLabel(tr("upscale.on"))
        else:
            self._btn_upscale.SetLabel(tr("upscale.off"))

    # ── UI Construction ────────────────────────────────────────────

    def _create_ui(self):
        """Build the complete modern tabbed UI."""
        cfg = self._config

        # ── Main vertical layout ──
        main_vbox = wx.BoxSizer(wx.VERTICAL)

        # ── Header bar ──
        header = wx.Panel(self, size=(-1, 48))
        header.SetBackgroundColour(WHITE)
        header_sz = wx.BoxSizer(wx.HORIZONTAL)

        self._header_title = wx.StaticText(header, label=tr("app.title"))
        self._dynamic_labels.append((self._header_title, "app.title", {}))
        title_font = self._header_title.GetFont()
        title_font.SetPointSize(14)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._header_title.SetFont(title_font)
        self._header_title.SetForegroundColour(TEXT_MAIN)
        header_sz.Add(self._header_title, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 14)

        header_sz.AddStretchSpacer(1)

        self._btn_lang = wx.Button(header, label=tr("btn.lang_toggle"),
                                    size=(42, 28))
        self._btn_lang.SetBackgroundColour(BTN_DEFAULT)
        self._btn_lang.SetForegroundColour(TEXT_MAIN)
        self._btn_lang.SetWindowStyleFlag(wx.BORDER_NONE)
        self._btn_lang.SetToolTip(tr("btn.lang_toggle_tooltip"))
        self._btn_lang.Bind(wx.EVT_BUTTON, self._on_lang_button)
        header_sz.Add(self._btn_lang, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        header.SetSizer(header_sz)
        main_vbox.Add(header, 0, wx.EXPAND)

        # Separator line
        sep = wx.Panel(self, size=(-1, 1))
        sep.SetBackgroundColour(BORDER)
        main_vbox.Add(sep, 0, wx.EXPAND)

        # ── Notebook (tabs) ──
        self._notebook = wx.Notebook(self, style=wx.NB_TOP)
        self._notebook.SetBackgroundColour(BG_PAGE)

        # Build each tab page
        self._build_control_tab(cfg)
        self._build_ocr_tab(cfg)
        self._build_translator_tab(cfg)
        self._build_overlay_tab(cfg)
        self._build_capture_tab(cfg)
        self._build_hotkeys_tab(cfg)
        self._build_logging_tab(cfg)
        self._build_result_tab()

        main_vbox.Add(self._notebook, 1, wx.EXPAND | wx.ALL, 0)

        # ── Status Bar ──
        self._build_status_bar(main_vbox)

        self.SetSizer(main_vbox)

    def _page_panel(self):
        """Create a standard tab page panel with card-like padding."""
        panel = wx.Panel(self._notebook)
        panel.SetBackgroundColour(BG_PAGE)
        return panel

    def _card_sizer(self, parent_sz):
        """Add a white card to a sizer. Returns the card's inner sizer."""
        # We approximate cards with a white-background panel and border
        card_sz = wx.BoxSizer(wx.VERTICAL)
        parent_sz.Add(card_sz, 0, wx.EXPAND | wx.ALL, 8)
        return card_sz

    def _card_sep(self, sizer):
        """Add a light separator line between card rows."""
        line = wx.Panel(sizer.GetContainingWindow(), size=(-1, 1))
        line.SetBackgroundColour(BORDER)
        sizer.Add(line, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)

    # ── Tab: Control ───────────────────────────────────────────────

    def _build_control_tab(self, cfg):
        page = wx.Panel(self._notebook)
        page.SetBackgroundColour(BG_PAGE)
        self._notebook.AddPage(page, tr("tab.control"))

        sz = wx.BoxSizer(wx.VERTICAL)
        outer_pad = 12

        # ── Action Buttons ──
        btn_card = wx.Panel(page)
        btn_card.SetBackgroundColour(WHITE)
        btn_sz = wx.BoxSizer(wx.HORIZONTAL)

        self._btn_start = _make_btn(btn_card, tr("btn.start"), PRIMARY, (95, 38))
        self._btn_start.Bind(wx.EVT_BUTTON, lambda e: self._on_start())
        btn_sz.Add(self._btn_start, 0, wx.RIGHT, 5)

        self._btn_single = _make_btn(btn_card, tr("btn.single"), size=(95, 38))
        self._btn_single.SetToolTip(tr("tooltip.single"))
        self._btn_single.Bind(wx.EVT_BUTTON, lambda e: self._on_single() if self._on_single else None)
        btn_sz.Add(self._btn_single, 0, wx.RIGHT, 5)

        self._btn_pause = _make_btn(btn_card, tr("btn.pause"), size=(95, 38))
        self._btn_pause.Bind(wx.EVT_BUTTON, lambda e: self._on_toggle())
        self._btn_pause.Enable(False)
        btn_sz.Add(self._btn_pause, 0, wx.RIGHT, 5)

        self._btn_stop = _make_btn(btn_card, tr("btn.stop"), DANGER, (95, 38))
        self._btn_stop.Bind(wx.EVT_BUTTON, lambda e: self._on_stop())
        self._btn_stop.Enable(False)
        btn_sz.Add(self._btn_stop, 0)

        btn_card.SetSizer(wx.BoxSizer(wx.VERTICAL))
        btn_card.GetSizer().Add(btn_sz, 0, wx.ALL, 12)
        sz.Add(btn_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, outer_pad)
        sz.AddSpacer(8)

        # ── Region & Clear Buttons ──
        rc_card = wx.Panel(page)
        rc_card.SetBackgroundColour(WHITE)
        rc_btn_sz = wx.BoxSizer(wx.HORIZONTAL)

        self._btn_region = _make_btn(rc_card, tr("btn.region_translate"), PRIMARY, (130, 38))
        self._btn_region.SetToolTip(tr("tooltip.region"))
        self._btn_region.Bind(wx.EVT_BUTTON, lambda e: self._on_region() if self._on_region else None)
        rc_btn_sz.Add(self._btn_region, 0, wx.RIGHT, 8)

        self._btn_clear = _make_btn(rc_card, tr("btn.clear_overlay"), size=(130, 38))
        self._btn_clear.SetToolTip(tr("tooltip.clear_overlay"))
        self._btn_clear.Bind(wx.EVT_BUTTON, lambda e: self._on_clear() if self._on_clear else None)
        rc_btn_sz.Add(self._btn_clear, 0, wx.RIGHT, 8)

        # Peek 按钮 — 按住隐藏覆盖层
        self._btn_hold_hide = _make_btn(rc_card, tr("btn.hold_hide"), WARNING_, (130, 38))
        self._btn_hold_hide.SetToolTip(tr("tooltip.hold_hide"))
        self._btn_hold_hide.Bind(wx.EVT_LEFT_DOWN, self._on_hold_hide_down)
        self._btn_hold_hide.Bind(wx.EVT_LEFT_UP, self._on_hold_hide_up)
        rc_btn_sz.Add(self._btn_hold_hide, 0)

        rc_card.SetSizer(wx.BoxSizer(wx.VERTICAL))
        rc_card.GetSizer().Add(rc_btn_sz, 0, wx.ALL, 12)
        sz.Add(rc_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, outer_pad)
        sz.AddSpacer(8)

        # ── Quick Toggles Card ──
        toggle_card = wx.Panel(page)
        toggle_card.SetBackgroundColour(WHITE)
        tc_sz = wx.BoxSizer(wx.VERTICAL)

        downscale_on = cfg.pipeline.downscale_max_size > 0
        self._btn_downscale = wx.Button(toggle_card,
                                         label=tr("downscale.on") if downscale_on else tr("downscale.off"),
                                         size=(-1, 34))
        self._btn_downscale.SetBackgroundColour(BTN_DEFAULT)
        self._btn_downscale.SetForegroundColour(TEXT_MAIN)
        self._btn_downscale.SetWindowStyleFlag(wx.BORDER_NONE)
        self._btn_downscale.Bind(wx.EVT_BUTTON, lambda e: self._on_downscale_button())
        tc_sz.Add(self._btn_downscale, 0, wx.EXPAND | wx.ALL, 6)

        # 小图放大按钮
        upscale_on = cfg.pipeline.upscale_small_image
        self._btn_upscale = wx.Button(toggle_card,
                                       label=tr("upscale.on") if upscale_on else tr("upscale.off"),
                                       size=(-1, 34))
        self._btn_upscale.SetBackgroundColour(BTN_DEFAULT)
        self._btn_upscale.SetForegroundColour(TEXT_MAIN)
        self._btn_upscale.SetWindowStyleFlag(wx.BORDER_NONE)
        self._btn_upscale.Bind(wx.EVT_BUTTON, lambda e: self._on_upscale_button())
        tc_sz.Add(self._btn_upscale, 0, wx.EXPAND | wx.ALL, 6)

        toggle_card.SetSizer(tc_sz)
        sz.Add(toggle_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, outer_pad)
        sz.AddSpacer(8)

        # ── Settings Card ──
        set_card = wx.Panel(page)
        set_card.SetBackgroundColour(WHITE)
        sc_sz = wx.BoxSizer(wx.VERTICAL)

        # Llama URL
        self._url_label = wx.StaticText(set_card, label=tr("field.llama_url"))
        self._dynamic_labels.append((self._url_label, "field.llama_url", {}))
        self._url_label.SetForegroundColour(TEXT_MAIN)
        sc_sz.Add(self._url_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        url_row = wx.BoxSizer(wx.HORIZONTAL)
        self._url_input = wx.TextCtrl(set_card, value=cfg.translator.llama.url, size=(200, -1))
        url_row.Add(self._url_input, 1, wx.RIGHT, 5)
        self._btn_test_url = _make_btn(set_card, tr("btn.test"), size=(60, 32))
        self._btn_test_url.Bind(wx.EVT_BUTTON, self._on_test_url)
        url_row.Add(self._btn_test_url, 0)
        sc_sz.Add(url_row, 0, wx.EXPAND | wx.ALL, 10)

        # Source / Target lang
        lang_row = wx.BoxSizer(wx.HORIZONTAL)
        self._src_lang_label = wx.StaticText(set_card, label=tr("field.source_lang"))
        self._dynamic_labels.append((self._src_lang_label, "field.source_lang", {}))
        lang_row.Add(self._src_lang_label, 0, wx.ALIGN_CENTER_VERTICAL)
        self._src_lang = wx.TextCtrl(set_card, value=cfg.source_lang, size=(60, -1))
        lang_row.Add(self._src_lang, 0, wx.LEFT, 5)
        self._tgt_lang_label = wx.StaticText(set_card, label=tr("field.target_lang"))
        self._dynamic_labels.append((self._tgt_lang_label, "field.target_lang", {}))
        lang_row.Add(self._tgt_lang_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 15)
        self._tgt_lang = wx.TextCtrl(set_card, value=cfg.target_lang, size=(60, -1))
        lang_row.Add(self._tgt_lang, 0, wx.LEFT, 5)
        sc_sz.Add(lang_row, 0, wx.ALL, 10)

        # Pipeline params
        pipe_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._interval_input, _interval_lbl, isz = _make_float_input(set_card, tr("field.cycle_interval"), cfg.pipeline.cycle_interval)
        self._dynamic_labels.append((_interval_lbl, "field.cycle_interval", {}))
        pipe_row1.Add(isz, 0)
        sc_sz.Add(pipe_row1, 0, wx.ALL, 10)

        set_card.SetSizer(sc_sz)
        sz.Add(set_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, outer_pad)
        sz.AddSpacer(8)

        page.SetSizer(sz)

    # ── Tab: OCR ───────────────────────────────────────────────────

    def _build_ocr_tab(self, cfg):
        page = wx.Panel(self._notebook)
        page.SetBackgroundColour(BG_PAGE)
        self._notebook.AddPage(page, tr("tab.ocr"))

        sz = wx.BoxSizer(wx.VERTICAL)
        outer_pad = 12

        # Card
        card = wx.Panel(page)
        card.SetBackgroundColour(WHITE)
        cs = wx.BoxSizer(wx.VERTICAL)

        # Engine info
        self._ocr_info_label = wx.StaticText(card, label=tr("engine.info"))
        self._dynamic_labels.append((self._ocr_info_label, "engine.info", {}))
        info_font = self._ocr_info_label.GetFont()
        info_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._ocr_info_label.SetFont(info_font)
        self._ocr_info_label.SetForegroundColour(TEXT_MAIN)
        cs.Add(self._ocr_info_label, 0, wx.ALL, 10)

        # 动态显示实际加载的模型路径（来自配置文件）
        det_name = os.path.basename(cfg.ocr.det_model_dir.rstrip("/\\"))
        rec_name = os.path.basename(cfg.ocr.rec_model_dir.rstrip("/\\"))
        self._ocr_hint_label = _hint_label(card, tr("engine.model_hint", det=det_name, rec=rec_name))
        self._dynamic_labels.append((self._ocr_hint_label, "engine.model_hint", {"det": det_name, "rec": rec_name}))
        cs.Add(self._ocr_hint_label, 0, wx.LEFT | wx.RIGHT, 10)

        cs.Add(wx.StaticLine(card), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── Detection params ──
        self._ocr_det_label = wx.StaticText(card, label=tr("section.detection"))
        self._dynamic_labels.append((self._ocr_det_label, "section.detection", {}))
        self._ocr_det_label.SetForegroundColour(TEXT_MUTED)
        cs.Add(self._ocr_det_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        det_row = wx.BoxSizer(wx.HORIZONTAL)
        self._det_box_thresh_input, _det_box_thresh_lbl, dbs = _make_float_input(card, tr("field.det_box_thresh"), cfg.ocr.det_box_thresh)
        self._dynamic_labels.append((_det_box_thresh_lbl, "field.det_box_thresh", {}))
        det_row.Add(dbs, 0, wx.RIGHT, 16)
        self._det_binary_thresh_input, _det_binary_thresh_lbl, dns = _make_float_input(card, tr("field.det_binary_thresh"), cfg.ocr.det_binary_thresh)
        self._dynamic_labels.append((_det_binary_thresh_lbl, "field.det_binary_thresh", {}))
        det_row.Add(dns, 0)
        cs.Add(det_row, 0, wx.ALL, 10)

        cs.Add(wx.StaticLine(card), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── Recognition ──
        self._ocr_rec_label = wx.StaticText(card, label=tr("section.recognition"))
        self._dynamic_labels.append((self._ocr_rec_label, "section.recognition", {}))
        self._ocr_rec_label.SetForegroundColour(TEXT_MUTED)
        cs.Add(self._ocr_rec_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        rec_row = wx.BoxSizer(wx.HORIZONTAL)
        self._min_conf_input, _min_conf_lbl, mcs = _make_float_input(card, tr("field.min_confidence"), cfg.ocr.min_confidence)
        self._dynamic_labels.append((_min_conf_lbl, "field.min_confidence", {}))
        rec_row.Add(mcs, 0)
        cs.Add(rec_row, 0, wx.ALL, 10)

        card.SetSizer(cs)
        sz.Add(card, 0, wx.EXPAND | wx.ALL, outer_pad)
        page.SetSizer(sz)

    # ── Tab: Translator ────────────────────────────────────────────

    def _build_translator_tab(self, cfg):
        page = wx.Panel(self._notebook)
        page.SetBackgroundColour(BG_PAGE)
        self._notebook.AddPage(page, tr("tab.translator"))

        sz = wx.BoxSizer(wx.VERTICAL)
        outer_pad = 12

        card = wx.Panel(page)
        card.SetBackgroundColour(WHITE)
        cs = wx.BoxSizer(wx.VERTICAL)
        ll = cfg.translator.llama

        # Connection params
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._timeout_input, _timeout_lbl, tos = _make_int_input(card, tr("field.timeout"), ll.timeout)
        self._dynamic_labels.append((_timeout_lbl, "field.timeout", {}))
        row1.Add(tos, 0, wx.RIGHT, 16)
        self._max_retries_input, _max_retries_lbl, mrs = _make_int_input(card, tr("field.max_retries"), ll.max_retries)
        self._dynamic_labels.append((_max_retries_lbl, "field.max_retries", {}))
        row1.Add(mrs, 0, wx.RIGHT, 16)
        self._parallel_input, _parallel_lbl, prs = _make_int_input(card, tr("field.parallel"), ll.parallel_requests)
        self._dynamic_labels.append((_parallel_lbl, "field.parallel", {}))
        row1.Add(prs, 0)
        cs.Add(row1, 0, wx.ALL, 10)

        cs.Add(wx.StaticLine(card), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Inference params
        ip = ll.inference_params
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self._temp_input, _temp_lbl, tms = _make_float_input(card, tr("field.temperature"), ip["temperature"])
        self._dynamic_labels.append((_temp_lbl, "field.temperature", {}))
        row2.Add(tms, 0, wx.RIGHT, 16)
        self._topk_input, _topk_lbl, tks = _make_int_input(card, tr("field.top_k"), ip["top_k"])
        self._dynamic_labels.append((_topk_lbl, "field.top_k", {}))
        row2.Add(tks, 0, wx.RIGHT, 16)
        self._topp_input, _topp_lbl, tps = _make_float_input(card, tr("field.top_p"), ip["top_p"])
        self._dynamic_labels.append((_topp_lbl, "field.top_p", {}))
        row2.Add(tps, 0)
        cs.Add(row2, 0, wx.ALL, 10)

        row3 = wx.BoxSizer(wx.HORIZONTAL)
        self._rpen_input, _rpen_lbl, rps = _make_float_input(card, tr("field.repeat_penalty"), ip["repeat_penalty"])
        self._dynamic_labels.append((_rpen_lbl, "field.repeat_penalty", {}))
        row3.Add(rps, 0, wx.RIGHT, 16)
        self._npredict_input, _npredict_lbl, nps = _make_int_input(card, tr("field.n_predict"), ip["n_predict"])
        self._dynamic_labels.append((_npredict_lbl, "field.n_predict", {}))
        row3.Add(nps, 0)
        cs.Add(row3, 0, wx.ALL, 10)

        card.SetSizer(cs)
        sz.Add(card, 0, wx.EXPAND | wx.ALL, outer_pad)
        page.SetSizer(sz)

    # ── Tab: Overlay ───────────────────────────────────────────────

    def _build_overlay_tab(self, cfg):
        page = wx.Panel(self._notebook)
        page.SetBackgroundColour(BG_PAGE)
        self._notebook.AddPage(page, tr("tab.overlay"))

        sz = wx.BoxSizer(wx.VERTICAL)
        outer_pad = 12

        card = wx.Panel(page)
        card.SetBackgroundColour(WHITE)
        cs = wx.BoxSizer(wx.VERTICAL)

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._font_size_input, _font_size_lbl, fss = _make_int_input(card, tr("field.font_size"), cfg.overlay.font_size)
        self._dynamic_labels.append((_font_size_lbl, "field.font_size", {}))
        row1.Add(fss, 0, wx.RIGHT, 16)
        self._min_font_size_input, _min_font_size_lbl, mfs = _make_int_input(card, tr("field.min_font_size"), cfg.overlay.min_font_size)
        self._dynamic_labels.append((_min_font_size_lbl, "field.min_font_size", {}))
        row1.Add(mfs, 0, wx.RIGHT, 16)
        self._bg_opacity_input, _bg_opacity_lbl, bos = _make_float_input(card, tr("field.bg_opacity"), cfg.overlay.background_opacity)
        self._dynamic_labels.append((_bg_opacity_lbl, "field.bg_opacity", {}))
        row1.Add(bos, 0)
        cs.Add(row1, 0, wx.ALL, 10)

        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self._font_family_input, _font_family_lbl, ffs = _make_labeled_input(card, tr("field.font_family"), cfg.overlay.font_family, size=(140, -1))
        self._dynamic_labels.append((_font_family_lbl, "field.font_family", {}))
        row2.Add(ffs, 0, wx.RIGHT, 16)
        self._text_color_input, _text_color_lbl, tcs = _make_labeled_input(card, tr("field.text_color"), cfg.overlay.text_color, size=(70, -1))
        self._dynamic_labels.append((_text_color_lbl, "field.text_color", {}))
        row2.Add(tcs, 0)
        cs.Add(row2, 0, wx.ALL, 10)

        self._tb_exclude = ToggleSwitch(card, label=tr("cb.exclude_capture"))
        self._tb_exclude.SetValue(cfg.overlay.exclude_from_capture)
        self._tb_exclude.Bind(wx.EVT_CHECKBOX, self._on_exclude_cap_toggle)
        self._toggles.append(self._tb_exclude)
        cs.Add(self._tb_exclude, 0, wx.ALL, 10)

        self._tb_stack_shrink = ToggleSwitch(card, label=tr("field.stack_shrink"))
        self._tb_stack_shrink.SetValue(cfg.overlay.stack_shrink)
        self._toggles.append(self._tb_stack_shrink)
        cs.Add(self._tb_stack_shrink, 0, wx.ALL, 10)

        card.SetSizer(cs)
        sz.Add(card, 0, wx.EXPAND | wx.ALL, outer_pad)
        page.SetSizer(sz)

    # ── Tab: Capture ───────────────────────────────────────────────

    def _build_capture_tab(self, cfg):
        page = wx.Panel(self._notebook)
        page.SetBackgroundColour(BG_PAGE)
        self._notebook.AddPage(page, tr("tab.capture"))

        sz = wx.BoxSizer(wx.VERTICAL)
        outer_pad = 12

        card = wx.Panel(page)
        card.SetBackgroundColour(WHITE)
        cs = wx.BoxSizer(wx.VERTICAL)

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._backend_input, _backend_lbl, bes = _make_labeled_input(card, tr("field.backend"), cfg.capture.backend, size=(90, -1))
        self._dynamic_labels.append((_backend_lbl, "field.backend", {}))
        row1.Add(bes, 0, wx.RIGHT, 16)
        self._cam_index_input, _cam_index_lbl, cis = _make_int_input(card, tr("field.camera_index"), cfg.capture.camera_index)
        self._dynamic_labels.append((_cam_index_lbl, "field.camera_index", {}))
        row1.Add(cis, 0, wx.RIGHT, 16)
        self._fps_input, _fps_lbl, fps = _make_int_input(card, tr("field.fps"), cfg.capture.fps)
        self._dynamic_labels.append((_fps_lbl, "field.fps", {}))
        row1.Add(fps, 0)
        cs.Add(row1, 0, wx.ALL, 10)

        card.SetSizer(cs)
        sz.Add(card, 0, wx.EXPAND | wx.ALL, outer_pad)
        page.SetSizer(sz)

    # ── Tab: Hotkeys ───────────────────────────────────────────────

    def _build_hotkeys_tab(self, cfg):
        page = wx.Panel(self._notebook)
        page.SetBackgroundColour(BG_PAGE)
        self._notebook.AddPage(page, tr("tab.hotkeys"))

        sz = wx.BoxSizer(wx.VERTICAL)
        outer_pad = 12

        card = wx.Panel(page)
        card.SetBackgroundColour(WHITE)
        cs = wx.BoxSizer(wx.VERTICAL)

        # Row 1: Single, Pause, Quit
        hk_row = wx.BoxSizer(wx.HORIZONTAL)
        self._hotkey_single_input, _hotkey_single_lbl, hss = _make_labeled_input(card, tr("field.hotkey_single"),
                                                              cfg.gui.hotkey_single_translate, size=(70, -1))
        self._dynamic_labels.append((_hotkey_single_lbl, "field.hotkey_single", {}))
        hk_row.Add(hss, 0, wx.RIGHT, 10)
        self._hotkey_pause_input, _hotkey_pause_lbl, hps = _make_labeled_input(card, tr("field.hotkey_pause"),
                                                             cfg.gui.hotkey_pause, size=(70, -1))
        self._dynamic_labels.append((_hotkey_pause_lbl, "field.hotkey_pause", {}))
        hk_row.Add(hps, 0, wx.RIGHT, 10)
        self._hotkey_quit_input, _hotkey_quit_lbl, hqs = _make_labeled_input(card, tr("field.hotkey_quit"),
                                                            cfg.gui.hotkey_quit, size=(70, -1))
        self._dynamic_labels.append((_hotkey_quit_lbl, "field.hotkey_quit", {}))
        hk_row.Add(hqs, 0)
        cs.Add(hk_row, 0, wx.ALL, 10)

        # Row 2: Region Translate, Clear Overlay
        hk_row2 = wx.BoxSizer(wx.HORIZONTAL)
        self._hotkey_region_input, _hotkey_region_lbl, hrs = _make_labeled_input(card, tr("field.hotkey_region"),
                                                              cfg.gui.hotkey_region_translate, size=(70, -1))
        self._dynamic_labels.append((_hotkey_region_lbl, "field.hotkey_region", {}))
        hk_row2.Add(hrs, 0, wx.RIGHT, 10)
        self._hotkey_clear_input, _hotkey_clear_lbl, hcs = _make_labeled_input(card, tr("field.hotkey_clear"),
                                                             cfg.gui.hotkey_clear_overlay, size=(70, -1))
        self._dynamic_labels.append((_hotkey_clear_lbl, "field.hotkey_clear", {}))
        hk_row2.Add(hcs, 0)
        cs.Add(hk_row2, 0, wx.ALL, 10)

        # Row 3: Hold Hide hotkey
        hk_row3 = wx.BoxSizer(wx.HORIZONTAL)
        self._hotkey_hold_hide_input, _hotkey_hold_hide_lbl, hhs = _make_labeled_input(card, tr("field.hotkey_hold_hide"),
                                                                  cfg.gui.hotkey_hold_hide, size=(70, -1))
        self._dynamic_labels.append((_hotkey_hold_hide_lbl, "field.hotkey_hold_hide", {}))
        hk_row3.Add(hhs, 0)
        cs.Add(hk_row3, 0, wx.ALL, 10)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_apply_hotkeys = _make_btn(card, tr("btn.apply_hotkeys"), PRIMARY, (130, 32))
        self._btn_apply_hotkeys.Bind(wx.EVT_BUTTON, lambda e: self._apply_hotkeys())
        btn_row.Add(self._btn_apply_hotkeys, 0)
        btn_row.AddStretchSpacer(1)
        cs.Add(btn_row, 0, wx.ALL, 10)

        self._hotkey_label = _hint_label(card, self._make_hotkey_label_text())
        cs.Add(self._hotkey_label, 0, wx.ALL, 10)

        card.SetSizer(cs)
        sz.Add(card, 0, wx.EXPAND | wx.ALL, outer_pad)
        page.SetSizer(sz)

    # ── Tab: Logging ───────────────────────────────────────────────

    def _build_logging_tab(self, cfg):
        page = wx.Panel(self._notebook)
        page.SetBackgroundColour(BG_PAGE)
        self._notebook.AddPage(page, tr("tab.logging"))

        sz = wx.BoxSizer(wx.VERTICAL)
        outer_pad = 12

        # ── Card 1: Cycle Logging ──
        card1 = wx.Panel(page)
        card1.SetBackgroundColour(WHITE)
        cs1 = wx.BoxSizer(wx.VERTICAL)

        self._tb_log = ToggleSwitch(card1, label=tr("cb.logging"))
        self._tb_log.SetValue(cfg.logging.enabled)
        self._tb_log.Bind(wx.EVT_CHECKBOX, self._on_logging_toggle)
        self._toggles.append(self._tb_log)
        cs1.Add(self._tb_log, 0, wx.ALL, 10)

        card1.SetSizer(cs1)
        sz.Add(card1, 0, wx.EXPAND | wx.ALL, outer_pad)
        sz.AddSpacer(4)

        # ── Card 2: Console Logging ──
        card2 = wx.Panel(page)
        card2.SetBackgroundColour(WHITE)
        cs2 = wx.BoxSizer(wx.VERTICAL)

        self._tb_console_log = ToggleSwitch(card2, label=tr("cb.console_logging"))
        self._tb_console_log.SetValue(cfg.console_logging.enabled)
        self._tb_console_log.Bind(wx.EVT_CHECKBOX, self._on_console_logging_toggle)
        self._toggles.append(self._tb_console_log)
        cs2.Add(self._tb_console_log, 0, wx.ALL, 10)

        # 日志路径信息
        log_dir = self._console_log_dir or cfg.resolve_path(cfg.console_logging.log_dir)
        self._console_log_path_label = _hint_label(
            card2, tr("label.console_log_path", path=log_dir)
        )
        cs2.Add(self._console_log_path_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # 功能说明
        self._console_log_hint_label = _hint_label(card2, tr("label.console_log_hint"))
        cs2.Add(self._console_log_hint_label, 0, wx.LEFT | wx.RIGHT, 10)

        # 打开文件夹按钮
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_row.AddStretchSpacer(1)
        self._btn_open_log_folder = _make_btn(card2, tr("btn.open_log_folder"), size=(150, 32))
        self._btn_open_log_folder.Bind(wx.EVT_BUTTON, self._on_open_log_folder)
        btn_row.Add(self._btn_open_log_folder, 0, wx.ALL, 5)
        btn_row.AddStretchSpacer(1)
        cs2.Add(btn_row, 0, wx.EXPAND | wx.ALL, 10)

        card2.SetSizer(cs2)
        sz.Add(card2, 0, wx.EXPAND | wx.ALL, outer_pad)

        page.SetSizer(sz)

    # ── Tab: Results ───────────────────────────────────────────────

    def _build_result_tab(self):
        page = wx.Panel(self._notebook)
        page.SetBackgroundColour(BG_DARK)
        self._notebook.AddPage(page, tr("tab.result"))

        sz = wx.BoxSizer(wx.VERTICAL)

        self._result_text = wx.TextCtrl(
            page,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.TE_RICH2 | wx.BORDER_NONE,
        )
        self._result_text.SetBackgroundColour(BG_DARK)
        self._result_text.SetForegroundColour(TEXT_DARK)
        self._result_text.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE,
                                           wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        sz.Add(self._result_text, 1, wx.EXPAND | wx.ALL, 4)

        page.SetSizer(sz)

    # ── Status Bar ─────────────────────────────────────────────────

    def _build_status_bar(self, main_vbox):
        bar = wx.Panel(self, size=(-1, 30))
        bar.SetBackgroundColour(WHITE)
        bar_sz = wx.BoxSizer(wx.HORIZONTAL)

        self._status_dot = _StatusDot(bar, 8)
        bar_sz.Add(self._status_dot, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 8)

        self._status_text = wx.StaticText(bar, label=tr("status.ready"))
        self._status_text.SetForegroundColour(TEXT_MUTED)
        bar_sz.Add(self._status_text, 0, wx.ALIGN_CENTER_VERTICAL)

        bar_sz.AddStretchSpacer(1)

        self._cycle_info_label = wx.StaticText(bar, label="")
        self._cycle_info_label.SetForegroundColour(TEXT_MUTED)
        bar_sz.Add(self._cycle_info_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        bar.SetSizer(bar_sz)
        main_vbox.Add(bar, 0, wx.EXPAND)

    # ── Hotkey Helpers ─────────────────────────────────────────────

    def _make_hotkey_label_text(self) -> str:
        cfg = self._config.gui
        return tr("hotkey.label",
                  single=cfg.hotkey_single_translate,
                  region=cfg.hotkey_region_translate,
                  clear=cfg.hotkey_clear_overlay,
                  pause=cfg.hotkey_pause,
                  holdhide=cfg.hotkey_hold_hide,
                  quit=cfg.hotkey_quit)

    def _refresh_hotkey_label(self):
        self._hotkey_label.SetLabel(self._make_hotkey_label_text())

    # ── Hotkeys ────────────────────────────────────────────────────

    def _setup_hotkeys(self):
        self._hotkey_handlers = []
        self._register_hotkeys()

    def _register_hotkeys(self):
        try:
            import keyboard
            cfg = self._config.gui
            for hotkey_str, callback in [
                (cfg.hotkey_pause, lambda: wx.CallAfter(self._on_toggle)),
                (cfg.hotkey_quit, lambda: wx.CallAfter(self._on_stop)),
                (cfg.hotkey_single_translate,
                 lambda: wx.CallAfter(self._on_single) if self._on_single else None),
                (cfg.hotkey_region_translate,
                 lambda: wx.CallAfter(self._on_region) if self._on_region else None),
                (cfg.hotkey_clear_overlay,
                 lambda: wx.CallAfter(self._on_clear) if self._on_clear else None),
            ]:
                handler = keyboard.add_hotkey(hotkey_str, callback, suppress=True)
                self._hotkey_handlers.append(handler)

            # 按住隐藏热键 — 按下时隐藏，松开后恢复
            if self._on_hold_hide_press:
                handler = keyboard.add_hotkey(
                    cfg.hotkey_hold_hide,
                    lambda: wx.CallAfter(self._on_hold_hide_press),
                    suppress=True,
                )
                self._hotkey_handlers.append(handler)
            if self._on_hold_hide_release:
                handler = keyboard.add_hotkey(
                    cfg.hotkey_hold_hide,
                    lambda: wx.CallAfter(self._on_hold_hide_release),
                    suppress=True,
                    trigger_on_release=True,
                )
                self._hotkey_handlers.append(handler)
        except Exception as e:
            print(f"[GUI] Hotkey registration failed: {e}")

    def _unbind_hotkeys(self):
        for handler in self._hotkey_handlers:
            try:
                handler()
            except Exception:
                pass
        self._hotkey_handlers.clear()

    def _apply_hotkeys(self):
        new_single = self._hotkey_single_input.GetValue().strip()
        new_pause = self._hotkey_pause_input.GetValue().strip()
        new_quit = self._hotkey_quit_input.GetValue().strip()
        new_region = self._hotkey_region_input.GetValue().strip()
        new_clear = self._hotkey_clear_input.GetValue().strip()
        new_hold_hide = self._hotkey_hold_hide_input.GetValue().strip()

        if not all([new_single, new_pause, new_quit, new_region, new_clear, new_hold_hide]):
            wx.MessageBox(tr("dlg.hotkey_empty"), tr("dlg.hotkey_invalid_title"),
                          wx.OK | wx.ICON_WARNING)
            return
        if len({new_single, new_pause, new_quit, new_region, new_clear, new_hold_hide}) < 6:
            wx.MessageBox(tr("dlg.hotkey_duplicate"), tr("dlg.hotkey_invalid_title"),
                          wx.OK | wx.ICON_WARNING)
            return

        cfg = self._config.gui
        cfg.hotkey_single_translate = new_single
        cfg.hotkey_pause = new_pause
        cfg.hotkey_quit = new_quit
        cfg.hotkey_region_translate = new_region
        cfg.hotkey_clear_overlay = new_clear
        cfg.hotkey_hold_hide = new_hold_hide

        self._unbind_hotkeys()
        self._register_hotkeys()
        self._refresh_hotkey_label()
        print(f"[GUI] Hotkeys applied: single={new_single}, pause={new_pause}, "
              f"quit={new_quit}, region={new_region}, clear={new_clear}, hold_hide={new_hold_hide}")

    # ── URL Test ───────────────────────────────────────────────────

    def _on_test_url(self, event):
        import requests
        url = self._url_input.GetValue().strip()
        if not url:
            wx.MessageBox(tr("dlg.enter_url"), tr("dlg.warning_title"), wx.OK | wx.ICON_WARNING)
            return

        self._btn_test_url.Enable(False)
        self._btn_test_url.SetLabel(tr("test.connecting"))
        wx.GetApp().Yield()

        import threading

        def test_connection():
            try:
                health_url = url.rstrip("/") + "/health"
                resp = requests.get(health_url, timeout=(3, 5))
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "ok" or resp.status_code == 200:
                    wx.CallAfter(self._show_test_result, True,
                                 tr("dlg.connection_success", data=data))
                else:
                    wx.CallAfter(self._show_test_result, False,
                                 tr("dlg.connection_unexpected", data=data))
            except requests.exceptions.ConnectionError:
                wx.CallAfter(self._show_test_result, False, tr("dlg.connection_failed"))
            except requests.exceptions.Timeout:
                wx.CallAfter(self._show_test_result, False, tr("dlg.connection_timeout"))
            except Exception as e:
                wx.CallAfter(self._show_test_result, False,
                             tr("dlg.test_error", error_type=type(e).__name__, error_msg=e))

        threading.Thread(target=test_connection, daemon=True).start()

    def _show_test_result(self, success: bool, message: str):
        self._btn_test_url.Enable(True)
        self._btn_test_url.SetLabel(tr("btn.test"))
        if success:
            wx.MessageBox(message, tr("dlg.test_ok_title"), wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox(message, tr("dlg.test_failed_title"), wx.OK | wx.ICON_ERROR)

    # ── Status Updates (thread-safe) ───────────────────────────────

    def update_status(self, status: str):
        CORE_STATES = ("Running", "Paused", "Stopped", "Ready", "Initializing...")

        def _update():
            status_map = {
                "Ready": tr("status.ready"),
                "Running": tr("status.running"),
                "Paused": tr("status.paused"),
                "Stopped": tr("status.stopped"),
                "Initializing...": tr("status.initializing"),
            }

            # ═══ 显示文本逻辑（所有状态都更新显示文本）═══
            if status in status_map:
                disp = status_map[status]
            elif status.startswith("Single:"):
                if status == "Single: initializing...":
                    disp = tr("status.single_init")
                elif status == "Single: capturing...":
                    disp = tr("status.single_capturing")
                elif status == "Single: done":
                    disp = tr("status.single_done")
                    self._single_in_progress = False
                elif status.startswith("Single: error:"):
                    error = status[len("Single: error:"):].strip()
                    disp = tr("status.single_error", error=error)
                    self._single_in_progress = False
                elif status == "Single: init failed":
                    disp = tr("status.single_init_failed")
                    self._single_in_progress = False
                else:
                    disp = status
            elif status.startswith("Region:"):
                if status == "Region: initializing...":
                    disp = tr("status.region_init")
                elif status == "Region: capturing...":
                    disp = tr("status.region_capturing")
                elif status == "Region: done":
                    disp = tr("status.region_done")
                    self._region_in_progress = False
                elif status.startswith("Region: error:"):
                    error = status[len("Region: error:"):].strip()
                    disp = tr("status.region_error", error=error)
                    self._region_in_progress = False
                elif status == "Region: init failed":
                    disp = tr("status.region_init_failed")
                    self._region_in_progress = False
                elif status == "Region: selecting":
                    disp = tr("status.region_selecting")
                else:
                    disp = status
            elif status == "Overlay cleared":
                disp = tr("status.overlay_cleared")
            elif status.startswith("Error:"):
                error = status[len("Error:"):].strip()
                disp = tr("status.error", error=error)
            elif status.startswith("Warning:"):
                disp = status
            else:
                disp = status

            self._status_text.SetLabel(disp)

            # ═══ 流水线状态管理（只在核心状态时更新按钮和状态点）═══
            if status in CORE_STATES:
                is_running = status in ("Running", "Paused")
                self._pipeline_running = is_running
                self._paused = (status == "Paused")
                self._btn_start.Enable(not is_running)
                self._btn_pause.Enable(is_running)
                self._btn_stop.Enable(is_running)
                if status == "Paused":
                    self._btn_pause.SetLabel(tr("btn.resume"))
                    self._status_dot.SetState("paused")
                elif status == "Running":
                    self._btn_pause.SetLabel(tr("btn.pause"))
                    self._status_dot.SetState("running")
                else:
                    self._status_dot.SetState("stopped")

            self._btn_single.Enable(not self._single_in_progress)
            self._btn_region.Enable(not self._region_in_progress)
        wx.CallAfter(_update)

    def update_ocr_result(self, cycle_id: int, boxes: list,
                           det_ms: float = 0.0, rec_ms: float = 0.0):
        ocr_total = det_ms + rec_ms
        def _update():
            self._result_text.Freeze()
            try:
                self._result_text.AppendText(
                    f"{'─'*55}\n"
                    f"{tr('result.cycle_header', id=cycle_id, count=len(boxes), det=f'{det_ms:.0f}', rec=f'{rec_ms:.0f}', total=f'{ocr_total:.0f}')}\n"
                    f"{'─'*55}\n"
                )
                for i, tb in enumerate(boxes, 1):
                    self._result_text.AppendText(f"  [{i}] \"{tb.text}\"\n")
                self._result_text.AppendText("\n")
                self._trim_result_text()
                self._result_text.ShowPosition(self._result_text.GetLastPosition())
            finally:
                self._result_text.Thaw()
        wx.CallAfter(_update)

    def update_translation_result(self, cycle_id: int, pairs: list, total_ms: float):
        def _update():
            self._result_text.Freeze()
            try:
                self._result_text.AppendText(
                    f"{'─'*55}\n"
                    f"{tr('result.trans_header', id=cycle_id, count=len(pairs), total=f'{total_ms:.0f}')}\n"
                    f"{'─'*55}\n"
                )
                for i, (original, translated, status) in enumerate(pairs, 1):
                    status_icon = "✓" if status == "ok" else "✗"
                    self._result_text.AppendText(f"  [{i}] {status_icon} \"{original}\"\n")
                    self._result_text.AppendText(f"       → \"{translated}\"\n")
                self._result_text.AppendText("\n")
                self._trim_result_text()
                self._result_text.ShowPosition(self._result_text.GetLastPosition())
            finally:
                self._result_text.Thaw()
        wx.CallAfter(_update)

    def update_cycle_info(self, cycle: CycleLog):
        if cycle.skipped:
            info = tr("cycle.skipped", id=cycle.cycle_id, reason=cycle.skip_reason or "unknown")
        else:
            ocr_ms = cycle.ocr_det_ms + cycle.ocr_rec_ms
            info = tr("cycle.info",
                      id=cycle.cycle_id,
                      count=len(cycle.text_boxes),
                      total=f"{cycle.total_ms:.0f}",
                      cap=f"{cycle.capture_ms:.0f}",
                      ocr=f"{ocr_ms:.0f}",
                      trans=f"{cycle.translate_ms:.0f}")
        wx.CallAfter(self._cycle_info_label.SetLabel, info)

    def _trim_result_text(self):
        text = self._result_text.GetValue()
        if len(text) > self._MAX_RESULT_CHARS:
            trim_at = len(text) - self._MAX_RESULT_CHARS
            nl_pos = text.find("\n", trim_at)
            if nl_pos >= 0:
                trim_at = nl_pos + 1
            self._result_text.Remove(0, trim_at)
            self._result_text.SetValue(
                f"{tr('result.trimmed')}\n{self._result_text.GetValue()}"
            )

    # ── Sync Config from GUI ───────────────────────────────────────

    def sync_config_from_gui(self):
        cfg = self._config

        cfg.source_lang = self._src_lang.GetValue().strip()
        cfg.target_lang = self._tgt_lang.GetValue().strip()
        cfg.translator.llama.url = self._url_input.GetValue().strip()

        try: cfg.pipeline.cycle_interval = float(self._interval_input.GetValue())
        except ValueError: pass

        try: cfg.ocr.det_box_thresh = float(self._det_box_thresh_input.GetValue())
        except ValueError: pass
        try: cfg.ocr.det_binary_thresh = float(self._det_binary_thresh_input.GetValue())
        except ValueError: pass
        try: cfg.ocr.min_confidence = float(self._min_conf_input.GetValue())
        except ValueError: pass

        ll = cfg.translator.llama
        try: ll.timeout = int(self._timeout_input.GetValue())
        except ValueError: pass
        try: ll.max_retries = int(self._max_retries_input.GetValue())
        except ValueError: pass
        try: ll.parallel_requests = int(self._parallel_input.GetValue())
        except ValueError: pass
        try: ll.inference_params["temperature"] = float(self._temp_input.GetValue())
        except ValueError: pass
        try: ll.inference_params["top_k"] = int(self._topk_input.GetValue())
        except ValueError: pass
        try: ll.inference_params["top_p"] = float(self._topp_input.GetValue())
        except ValueError: pass
        try: ll.inference_params["repeat_penalty"] = float(self._rpen_input.GetValue())
        except ValueError: pass
        try: ll.inference_params["n_predict"] = int(self._npredict_input.GetValue())
        except ValueError: pass

        try: cfg.overlay.font_size = int(self._font_size_input.GetValue())
        except ValueError: pass
        try: cfg.overlay.min_font_size = int(self._min_font_size_input.GetValue())
        except ValueError: pass
        cfg.overlay.font_family = self._font_family_input.GetValue().strip()
        cfg.overlay.text_color = self._text_color_input.GetValue().strip()
        try: cfg.overlay.background_opacity = float(self._bg_opacity_input.GetValue())
        except ValueError: pass
        cfg.overlay.exclude_from_capture = self._tb_exclude.GetValue()
        cfg.overlay.stack_shrink = self._tb_stack_shrink.GetValue()

        cfg.capture.backend = self._backend_input.GetValue().strip()
        try: cfg.capture.camera_index = int(self._cam_index_input.GetValue())
        except ValueError: pass
        try: cfg.capture.fps = int(self._fps_input.GetValue())
        except ValueError: pass

        if hasattr(self, '_hotkey_single_input'):
            cfg.gui.hotkey_single_translate = self._hotkey_single_input.GetValue().strip()
            cfg.gui.hotkey_pause = self._hotkey_pause_input.GetValue().strip()
            cfg.gui.hotkey_quit = self._hotkey_quit_input.GetValue().strip()
            cfg.gui.hotkey_region_translate = self._hotkey_region_input.GetValue().strip()
            cfg.gui.hotkey_clear_overlay = self._hotkey_clear_input.GetValue().strip()
            cfg.gui.hotkey_hold_hide = self._hotkey_hold_hide_input.GetValue().strip()

        cfg.console_logging.enabled = self._tb_console_log.GetValue()
        cfg.gui.ui_language = self._locale.lang

    # ── Public Getters ─────────────────────────────────────────────

    def get_url(self) -> str:
        return self._url_input.GetValue()

    def get_langs(self) -> tuple[str, str]:
        return self._src_lang.GetValue(), self._tgt_lang.GetValue()

    def get_interval(self) -> float:
        try: return float(self._interval_input.GetValue())
        except ValueError: return 5.0

    # ── Toggle / Checkbox Callbacks ────────────────────────────────

    def _on_downscale_button(self):
        current = self._config.pipeline.downscale_max_size > 0
        new_state = not current
        self._config.pipeline.downscale_max_size = 720 if new_state else 0
        self._update_downscale_button_label()

    def _on_upscale_button(self):
        current = self._config.pipeline.upscale_small_image
        self._config.pipeline.upscale_small_image = not current
        self._update_upscale_button_label()

    # ── Hold-Hide 按钮 ─────────────────────────────────────────

    def _on_hold_hide_down(self, event):
        """Peek 按钮按下 → 隐藏覆盖层"""
        if self._on_hold_hide_press:
            self._on_hold_hide_press()
        self._hold_hide_active = True
        self._btn_hold_hide.SetLabel(tr("btn.hold_hide_release"))
        event.Skip()

    def _on_hold_hide_up(self, event):
        """Peek 按钮松开 → 恢复覆盖层"""
        if self._on_hold_hide_release:
            self._on_hold_hide_release()
        self._hold_hide_active = False
        self._btn_hold_hide.SetLabel(tr("btn.hold_hide"))
        event.Skip()

    def _on_exclude_cap_toggle(self, event):
        self._config.overlay.exclude_from_capture = self._tb_exclude.GetValue()

    def _on_logging_toggle(self, event):
        self._config.logging.enabled = self._tb_log.GetValue()

    def _on_console_logging_toggle(self, event):
        self._config.console_logging.enabled = self._tb_console_log.GetValue()

    def _on_open_log_folder(self, event):
        """在资源管理器中打开日志文件夹"""
        log_dir = self._console_log_dir or self._config.resolve_path(self._config.console_logging.log_dir)
        try:
            import os
            if os.path.isdir(log_dir):
                os.startfile(log_dir)
            else:
                wx.MessageBox(
                    tr("dlg.log_dir_not_found", path=log_dir),
                    tr("dlg.warning_title"),
                    wx.OK | wx.ICON_WARNING,
                )
        except Exception as e:
            wx.MessageBox(
                tr("dlg.open_folder_error", error=e),
                tr("dlg.error_title"),
                wx.OK | wx.ICON_ERROR,
            )


# ═══════════════════════════════════════════════════════════════════
#  Status Dot widget
# ═══════════════════════════════════════════════════════════════════

class _StatusDot(wx.Panel):
    """Small colored circle indicating pipeline status."""

    def __init__(self, parent, radius=8):
        size = radius * 2 + 4
        super().__init__(parent, size=(size, size))
        self._radius = radius
        self._state = "stopped"  # stopped | running | paused
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def SetState(self, state: str):
        self._state = state
        self.Refresh()

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)

        w, h = self.GetSize()
        cx, cy = w // 2, h // 2

        colors = {
            "running": SUCCESS,
            "paused": WARNING_,
            "stopped": TEXT_MUTED,
        }
        color = colors.get(self._state, TEXT_MUTED)

        gc.SetBrush(gc.CreateBrush(wx.Brush(color)))
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.DrawEllipse(cx - self._radius, cy - self._radius,
                       self._radius * 2, self._radius * 2)
        del gc


# ═══════════════════════════════════════════════════════════════════
#  TrayIcon (unchanged from original)
# ═══════════════════════════════════════════════════════════════════

class TrayIcon(wx.adv.TaskBarIcon):
    """System tray icon."""

    def __init__(self, frame: MainWindow):
        super().__init__()
        self._frame = frame
        self.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16))),
                     tr("tray.tooltip"))
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self._on_left_dclick)

    def _on_left_dclick(self, event):
        if self._frame.IsShown():
            self._frame.Hide()
        else:
            self._frame.Show()
            self._frame.Raise()

    def CreatePopupMenu(self):
        menu = wx.Menu()
        show_item = menu.Append(wx.ID_ANY, tr("tray.show_hide"))
        quit_item = menu.Append(wx.ID_EXIT, tr("tray.quit"))
        self.Bind(wx.EVT_MENU, lambda e: self._on_left_dclick(None), show_item)
        self.Bind(wx.EVT_MENU, lambda e: self._frame.Close(), quit_item)
        return menu
