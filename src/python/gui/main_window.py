"""
gui/main_window.py — wxPython GUI 主窗口

提供控制面板界面：
- 开始/暂停翻译按钮
- 状态显示
- 配置编辑（llama URL 等）
- 快捷键绑定
- 全部优化选项开关
- 中英文语言切换
- 单次翻译（独立可用，无需先启动实时翻译）
"""
import wx
import wx.adv
import sys
from typing import Optional, Callable

from ..config.settings import AppConfig
from ..logger.cycle_logger import CycleLog
from ..i18n import tr, get_locale, LocaleManager


# ── 辅助控件工厂 ────────────────────────────────────────────────

def _make_labeled_input(parent, label: str, value: str, size=(80, -1),
                        cb=None) -> tuple[wx.TextCtrl, wx.BoxSizer]:
    """创建 Label | TextCtrl 的水平布局，返回 (input, sizer)"""
    sz = wx.BoxSizer(wx.HORIZONTAL)
    sz.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
    ctrl = wx.TextCtrl(parent, value=value, size=size)
    sz.Add(ctrl, 0, wx.LEFT, 5)
    return ctrl, sz


def _make_float_input(parent, label: str, value: float, size=(65, -1),
                      cb=None) -> tuple[wx.TextCtrl, wx.BoxSizer]:
    """创建浮点数输入行"""
    return _make_labeled_input(parent, label, f"{value:.4g}", size, cb)


def _make_int_input(parent, label: str, value: int, size=(65, -1),
                    cb=None) -> tuple[wx.TextCtrl, wx.BoxSizer]:
    """创建整数输入行"""
    return _make_labeled_input(parent, label, str(value), size, cb)


class MainWindow(wx.Frame):
    """主控制窗口"""

    def __init__(
        self,
        config: AppConfig,
        on_toggle_pause: Callable[[], None],
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_single_translate: Optional[Callable[[], None]] = None,
        on_single_start: Optional[Callable[[], None]] = None,
        on_single_done: Optional[Callable[[], None]] = None,
        on_ocr_result: Optional[Callable[[int, list, float, float], None]] = None,
        on_translation_result: Optional[Callable[[int, list, float], None]] = None,
    ):
        super().__init__(None, title=tr("app.title"), size=(480, 780))
        self._config = config
        self._on_toggle = on_toggle_pause
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_single = on_single_translate
        self._on_single_start = on_single_start
        self._on_single_done = on_single_done
        self._on_ocr = on_ocr_result
        self._on_trans = on_translation_result

        # 单次翻译状态
        self._single_in_progress = False
        # 实时翻译是否在运行
        self._pipeline_running = False

        # 存放所有需要动态更新的控件引用
        self._dynamic_labels: list[tuple[wx.Control, str, dict]] = []
        # 存放所有静态框引用（用于更新标题）
        self._static_boxes: dict[str, wx.StaticBox] = {}

        self._locale = get_locale()
        self._locale.subscribe(self._on_language_changed)

        self._create_ui()
        self._setup_hotkeys()
        self.Center()

    # ── 语言切换 ─────────────────────────────────────────────────

    def _on_language_changed(self):
        """语言变更回调 — 刷新所有 UI 文本"""
        self._refresh_ui_texts()

    def _on_lang_button(self, event):
        """点击语言切换按钮"""
        self._locale.toggle()
        # 保存到 config
        self._config.gui.ui_language = self._locale.lang
        # 刷新按钮自身
        self._btn_lang.SetLabel(tr("btn.lang_toggle"))

    def _refresh_ui_texts(self):
        """刷新所有可动态更新的 UI 文本"""
        # 窗口标题
        self.SetTitle(tr("app.title"))
        # 语言按钮
        self._btn_lang.SetLabel(tr("btn.lang_toggle"))
        # 核心按钮
        self._btn_start.SetLabel(tr("btn.start"))
        self._btn_single.SetLabel(tr("btn.single"))
        self._btn_single.SetToolTip(tr("tooltip.single"))
        # Pause/Resume 根据当前状态
        if self._btn_pause.IsEnabled() and self._btn_pause.GetLabel() == tr("btn.resume"):
            self._btn_pause.SetLabel(tr("btn.resume"))
        else:
            self._btn_pause.SetLabel(tr("btn.pause"))
        self._btn_stop.SetLabel(tr("btn.stop"))
        self._btn_test_url.SetLabel(tr("btn.test"))
        self._btn_apply_hotkeys.SetLabel(tr("btn.apply_hotkeys"))
        # 差异检测按钮
        self._update_diff_button_label()
        # 720p 下采样按钮
        self._update_downscale_button_label()
        # 刷新所有已注册的动态标签
        for ctrl, key, kwargs in self._dynamic_labels:
            if isinstance(ctrl, wx.StaticText):
                ctrl.SetLabel(tr(key, **kwargs))
            elif isinstance(ctrl, wx.Button):
                ctrl.SetLabel(tr(key, **kwargs))
        # 刷新静态框标题
        for name, box in self._static_boxes.items():
            if name == "ocr":
                engine = self._config.ocr.engine
                box.SetLabel(tr("section.ocr", engine=engine))
            else:
                box.SetLabel(tr(f"section.{name}"))
        # 刷新复选框标签
        self._diff_detection_cb.SetLabel(tr("cb.diff_detection"))
        self._det_invert_cb.SetLabel(tr("cb.invert_dark"))
        self._det_denoise_cb.SetLabel(tr("cb.denoise"))
        self._rec_enhance_cb.SetLabel(tr("cb.enhance"))
        self._exclude_cap_cb.SetLabel(tr("cb.exclude_capture"))
        self._log_enabled_cb.SetLabel(tr("cb.logging"))
        # 刷新 OCR engine choice 的标签
        engine_idx = 0 if self._config.ocr.engine == "paddle" else 1
        self._ocr_engine_choice.SetItems([tr("ocr.paddle_label"), tr("ocr.easyocr_label")])
        self._ocr_engine_choice.SetSelection(engine_idx)
        # 刷新 EasyOCR 提示
        self._easyocr_hint.SetLabel(tr("field.easyocr_hint"))
        # 刷新快捷键提示
        self._refresh_hotkey_label()
        # 刷新当前状态
        self._status_label.SetLabel(tr("status.label", status=tr("status.ready")))
        # 布局更新
        self.GetSizer().Layout()

    def _update_diff_button_label(self):
        """更新差异检测按钮标签"""
        if self._config.pipeline.diff_detection:
            self._btn_diff.SetLabel(tr("diff.on"))
        else:
            self._btn_diff.SetLabel(tr("diff.off"))

    # ── UI 构建 ─────────────────────────────────────────────────

    def _create_ui(self):
        """创建全部 UI 控件（可滚动）"""
        # 使用 ScrolledWindow 容纳全部设置项
        sw = wx.ScrolledWindow(self, style=wx.VSCROLL)
        sw.SetScrollRate(10, 10)
        panel = sw
        vbox = wx.BoxSizer(wx.VERTICAL)

        cfg = self._config  # 短别名

        # ── 标题行（含语言切换按钮）──
        title_row = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(panel, label=tr("app.title"))
        title_font = title.GetFont()
        title_font.SetPointSize(16)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        title_row.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        title_row.AddStretchSpacer(1)
        self._btn_lang = wx.Button(panel, label=tr("btn.lang_toggle"), size=(48, 30))
        self._btn_lang.SetToolTip("Switch UI language / 切换界面语言")
        self._btn_lang.Bind(wx.EVT_BUTTON, self._on_lang_button)
        title_row.Add(self._btn_lang, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        vbox.Add(title_row, 0, wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT, 12)

        # ── 状态 ──
        self._status_label = wx.StaticText(panel, label=tr("status.label", status=tr("status.ready")))
        self._status_label.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT,
                                           wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        vbox.Add(self._status_label, 0, wx.ALIGN_CENTER | wx.TOP, 8)

        vbox.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 8)

        # ══════════════════════════════════════════════════════════
        # ▸ 核心工作流按钮
        # ══════════════════════════════════════════════════════════
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_start = wx.Button(panel, label=tr("btn.start"), size=(100, 42))
        self._btn_start.Bind(wx.EVT_BUTTON, lambda e: self._on_start())
        btn_sizer.Add(self._btn_start, 0, wx.RIGHT, 3)

        self._btn_single = wx.Button(panel, label=tr("btn.single"), size=(100, 42))
        self._btn_single.SetToolTip(tr("tooltip.single"))
        self._btn_single.Bind(wx.EVT_BUTTON, lambda e: self._on_single() if self._on_single else None)
        # 单次翻译按钮默认启用（不再需要先启动实时翻译）
        btn_sizer.Add(self._btn_single, 0, wx.RIGHT, 3)

        self._btn_pause = wx.Button(panel, label=tr("btn.pause"), size=(100, 42))
        self._btn_pause.Bind(wx.EVT_BUTTON, lambda e: self._on_toggle())
        self._btn_pause.Enable(False)
        btn_sizer.Add(self._btn_pause, 0, wx.RIGHT, 3)

        self._btn_stop = wx.Button(panel, label=tr("btn.stop"), size=(100, 42))
        self._btn_stop.Bind(wx.EVT_BUTTON, lambda e: self._on_stop())
        self._btn_stop.Enable(False)
        btn_sizer.Add(self._btn_stop, 0)
        vbox.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP, 4)

        # ▸ 差异检测快速开关按钮
        diff_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        diff_on = cfg.pipeline.diff_detection
        self._btn_diff = wx.Button(panel, label=tr("diff.on") if diff_on else tr("diff.off"), size=(220, 38))
        self._btn_diff.Bind(wx.EVT_BUTTON, lambda e: self._on_diff_detection_button())
        diff_btn_sizer.Add(self._btn_diff, 0)
        vbox.Add(diff_btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP, 4)

        # ▸ 720p 下采样快速开关按钮
        downscale_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        downscale_on = cfg.pipeline.downscale_max_size > 0
        self._btn_downscale = wx.Button(panel, label=tr("downscale.on") if downscale_on else tr("downscale.off"), size=(220, 38))
        self._btn_downscale.Bind(wx.EVT_BUTTON, lambda e: self._on_downscale_button())
        downscale_btn_sizer.Add(self._btn_downscale, 0)
        vbox.Add(downscale_btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP, 4)

        vbox.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 8)

        # ══════════════════════════════════════════════════════════
        # ▸ 基础配置
        # ══════════════════════════════════════════════════════════
        basic_box = wx.StaticBox(panel, label=tr("section.basic"))
        self._static_boxes["basic"] = basic_box
        basic_sz = wx.StaticBoxSizer(basic_box, wx.VERTICAL)

        # Llama URL
        url_sizer = wx.BoxSizer(wx.HORIZONTAL)
        url_sizer.Add(wx.StaticText(panel, label=tr("field.llama_url")), 0, wx.ALIGN_CENTER_VERTICAL)
        self._url_input = wx.TextCtrl(panel, value=cfg.translator.llama.url, size=(200, -1))
        url_sizer.Add(self._url_input, 1, wx.LEFT, 5)
        self._btn_test_url = wx.Button(panel, label=tr("btn.test"), size=(60, -1))
        self._btn_test_url.Bind(wx.EVT_BUTTON, self._on_test_url)
        url_sizer.Add(self._btn_test_url, 0, wx.LEFT, 5)
        basic_sz.Add(url_sizer, 0, wx.EXPAND | wx.ALL, 4)

        # 源语言 / 目标语言
        lang_sz = wx.BoxSizer(wx.HORIZONTAL)
        lang_sz.Add(wx.StaticText(panel, label=tr("field.source_lang")), 0, wx.ALIGN_CENTER_VERTICAL)
        self._src_lang = wx.TextCtrl(panel, value=cfg.source_lang, size=(60, -1))
        lang_sz.Add(self._src_lang, 0, wx.LEFT, 5)
        lang_sz.Add(wx.StaticText(panel, label=tr("field.target_lang")), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 15)
        self._tgt_lang = wx.TextCtrl(panel, value=cfg.target_lang, size=(60, -1))
        lang_sz.Add(self._tgt_lang, 0, wx.LEFT, 5)
        basic_sz.Add(lang_sz, 0, wx.EXPAND | wx.ALL, 4)

        # 周期间隔 + Diff 检测阈值 + 最大文本框
        pipeline_sz1 = wx.BoxSizer(wx.HORIZONTAL)
        self._interval_input, isz = _make_float_input(panel, tr("field.cycle_interval"), cfg.pipeline.cycle_interval)
        pipeline_sz1.Add(isz, 0, wx.RIGHT, 20)
        self._diff_thresh_input, dsz = _make_float_input(panel, tr("field.diff_threshold"), cfg.pipeline.diff_threshold)
        pipeline_sz1.Add(dsz, 0)
        basic_sz.Add(pipeline_sz1, 0, wx.EXPAND | wx.ALL, 4)

        pipeline_sz2 = wx.BoxSizer(wx.HORIZONTAL)
        self._max_boxes_input, msz = _make_int_input(panel, tr("field.max_text_boxes"), cfg.pipeline.max_text_boxes)
        pipeline_sz2.Add(msz, 0)
        basic_sz.Add(pipeline_sz2, 0, wx.EXPAND | wx.ALL, 4)

        # Diff detection 复选框
        self._diff_detection_cb = wx.CheckBox(panel, label=tr("cb.diff_detection"))
        self._diff_detection_cb.SetValue(cfg.pipeline.diff_detection)
        self._diff_detection_cb.Bind(wx.EVT_CHECKBOX, self._on_diff_detection_toggle)
        basic_sz.Add(self._diff_detection_cb, 0, wx.EXPAND | wx.ALL, 4)

        vbox.Add(basic_sz, 0, wx.EXPAND | wx.ALL, 4)

        # ══════════════════════════════════════════════════════════
        # ▸ OCR 参数
        # ══════════════════════════════════════════════════════════
        ocr_box = wx.StaticBox(panel, label=tr("section.ocr", engine=cfg.ocr.engine))
        self._static_boxes["ocr"] = ocr_box
        ocr_sz = wx.StaticBoxSizer(ocr_box, wx.VERTICAL)
        self._ocr_box = ocr_box  # 保存引用以便后续更新标题

        # ─ OCR 引擎选择 ─
        engine_sz = wx.BoxSizer(wx.HORIZONTAL)
        engine_sz.Add(wx.StaticText(panel, label=tr("field.ocr_engine")), 0, wx.ALIGN_CENTER_VERTICAL)
        self._ocr_engine_choice = wx.Choice(
            panel,
            choices=[tr("ocr.paddle_label"), tr("ocr.easyocr_label")],
        )
        engine_idx = 0 if cfg.ocr.engine == "paddle" else 1
        self._ocr_engine_choice.SetSelection(engine_idx)
        self._ocr_engine_choice.Bind(wx.EVT_CHOICE, self._on_ocr_engine_changed)
        engine_sz.Add(self._ocr_engine_choice, 0, wx.LEFT, 5)
        ocr_sz.Add(engine_sz, 0, wx.EXPAND | wx.ALL, 4)

        # ─ EasyOCR 语言输入（仅在easyocr模式下显示）──
        easy_lang_sz = wx.BoxSizer(wx.HORIZONTAL)
        easy_lang_str = ",".join(cfg.ocr.easyocr_languages) if cfg.ocr.easyocr_languages else "en"
        self._easyocr_lang_input, el_sz = _make_labeled_input(
            panel, tr("field.easyocr_langs"), easy_lang_str, size=(120, -1)
        )
        easy_lang_sz.Add(el_sz, 0)
        # 提示标签
        self._easyocr_hint = wx.StaticText(panel, label=tr("field.easyocr_hint"))
        self._easyocr_hint.SetFont(wx.Font(7, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
        self._easyocr_hint.SetForegroundColour(wx.Colour(128, 128, 128))
        easy_lang_sz.Add(self._easyocr_hint, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        ocr_sz.Add(easy_lang_sz, 0, wx.EXPAND | wx.ALL, 4)
        # 仅在easyocr模式下显示语言输入
        self._easyocr_lang_sizer = easy_lang_sz
        if cfg.ocr.engine != "easyocr":
            easy_lang_sz.ShowItems(False)

        # ─ PaddleOCR 专用参数 ─
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._cpu_threads_input, csz = _make_int_input(panel, tr("field.cpu_threads"), cfg.ocr.cpu_threads)
        row1.Add(csz, 0, wx.RIGHT, 20)
        self._det_resize_long_input, rsz = _make_int_input(panel, tr("field.resize_long"), cfg.ocr.det_resize_long)
        row1.Add(rsz, 0)
        ocr_sz.Add(row1, 0, wx.EXPAND | wx.ALL, 4)

        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self._det_thresh_input, dts = _make_float_input(panel, tr("field.det_threshold"), cfg.ocr.det_threshold)
        row2.Add(dts, 0, wx.RIGHT, 20)
        self._box_thresh_input, bts = _make_float_input(panel, tr("field.box_threshold"), cfg.ocr.box_threshold)
        row2.Add(bts, 0, wx.RIGHT, 20)
        self._min_conf_input, mcs = _make_float_input(panel, tr("field.min_confidence"), cfg.ocr.min_confidence)
        row2.Add(mcs, 0)
        ocr_sz.Add(row2, 0, wx.EXPAND | wx.ALL, 4)

        # 预处理开关
        self._det_invert_cb = wx.CheckBox(panel, label=tr("cb.invert_dark"))
        self._det_invert_cb.SetValue(cfg.ocr.det_invert_dark)
        self._det_invert_cb.Bind(wx.EVT_CHECKBOX, self._on_ocr_preproc_toggle)
        ocr_sz.Add(self._det_invert_cb, 0, wx.EXPAND | wx.ALL, 4)

        self._det_denoise_cb = wx.CheckBox(panel, label=tr("cb.denoise"))
        self._det_denoise_cb.SetValue(cfg.ocr.det_denoise)
        self._det_denoise_cb.Bind(wx.EVT_CHECKBOX, self._on_ocr_preproc_toggle)
        ocr_sz.Add(self._det_denoise_cb, 0, wx.EXPAND | wx.ALL, 4)

        self._rec_enhance_cb = wx.CheckBox(panel, label=tr("cb.enhance"))
        self._rec_enhance_cb.SetValue(cfg.ocr.rec_enhance)
        self._rec_enhance_cb.Bind(wx.EVT_CHECKBOX, self._on_ocr_preproc_toggle)
        ocr_sz.Add(self._rec_enhance_cb, 0, wx.EXPAND | wx.ALL, 4)

        vbox.Add(ocr_sz, 0, wx.EXPAND | wx.ALL, 4)

        # ══════════════════════════════════════════════════════════
        # ▸ 翻译器参数
        # ══════════════════════════════════════════════════════════
        trans_box = wx.StaticBox(panel, label=tr("section.translator"))
        self._static_boxes["translator"] = trans_box
        trans_sz = wx.StaticBoxSizer(trans_box, wx.VERTICAL)

        ll = cfg.translator.llama
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._timeout_input, tos = _make_int_input(panel, tr("field.timeout"), ll.timeout)
        row1.Add(tos, 0, wx.RIGHT, 20)
        self._max_retries_input, mrs = _make_int_input(panel, tr("field.max_retries"), ll.max_retries)
        row1.Add(mrs, 0, wx.RIGHT, 20)
        self._parallel_input, prs = _make_int_input(panel, tr("field.parallel"), ll.parallel_requests)
        row1.Add(prs, 0)
        trans_sz.Add(row1, 0, wx.EXPAND | wx.ALL, 4)

        ip = ll.inference_params
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self._temp_input, tms = _make_float_input(panel, tr("field.temperature"), ip["temperature"])
        row2.Add(tms, 0, wx.RIGHT, 20)
        self._topk_input, tks = _make_int_input(panel, tr("field.top_k"), ip["top_k"])
        row2.Add(tks, 0, wx.RIGHT, 20)
        self._topp_input, tps = _make_float_input(panel, tr("field.top_p"), ip["top_p"])
        row2.Add(tps, 0)
        trans_sz.Add(row2, 0, wx.EXPAND | wx.ALL, 4)

        row3 = wx.BoxSizer(wx.HORIZONTAL)
        self._rpen_input, rps = _make_float_input(panel, tr("field.repeat_penalty"), ip["repeat_penalty"])
        row3.Add(rps, 0, wx.RIGHT, 20)
        self._npredict_input, nps = _make_int_input(panel, tr("field.n_predict"), ip["n_predict"])
        row3.Add(nps, 0)
        trans_sz.Add(row3, 0, wx.EXPAND | wx.ALL, 4)

        vbox.Add(trans_sz, 0, wx.EXPAND | wx.ALL, 4)

        # ══════════════════════════════════════════════════════════
        # ▸ 覆盖层参数
        # ══════════════════════════════════════════════════════════
        ovl_box = wx.StaticBox(panel, label=tr("section.overlay"))
        self._static_boxes["overlay"] = ovl_box
        ovl_sz = wx.StaticBoxSizer(ovl_box, wx.VERTICAL)

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._font_size_input, fss = _make_int_input(panel, tr("field.font_size"), cfg.overlay.font_size)
        row1.Add(fss, 0, wx.RIGHT, 20)
        self._bg_opacity_input, bos = _make_float_input(panel, tr("field.bg_opacity"), cfg.overlay.background_opacity)
        row1.Add(bos, 0)
        ovl_sz.Add(row1, 0, wx.EXPAND | wx.ALL, 4)

        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self._font_family_input, ffs = _make_labeled_input(panel, tr("field.font_family"), cfg.overlay.font_family, size=(140, -1))
        row2.Add(ffs, 0, wx.RIGHT, 20)
        self._text_color_input, tcs = _make_labeled_input(panel, tr("field.text_color"), cfg.overlay.text_color, size=(70, -1))
        row2.Add(tcs, 0)
        ovl_sz.Add(row2, 0, wx.EXPAND | wx.ALL, 4)

        # 是否启用 WDA_EXCLUDEFROMCAPTURE
        self._exclude_cap_cb = wx.CheckBox(panel, label=tr("cb.exclude_capture"))
        self._exclude_cap_cb.SetValue(cfg.overlay.exclude_from_capture)
        self._exclude_cap_cb.Bind(wx.EVT_CHECKBOX, self._on_exclude_cap_toggle)
        ovl_sz.Add(self._exclude_cap_cb, 0, wx.EXPAND | wx.ALL, 4)

        vbox.Add(ovl_sz, 0, wx.EXPAND | wx.ALL, 4)

        # ══════════════════════════════════════════════════════════
        # ▸ 采集参数
        # ══════════════════════════════════════════════════════════
        cap_box = wx.StaticBox(panel, label=tr("section.capture"))
        self._static_boxes["capture"] = cap_box
        cap_sz = wx.StaticBoxSizer(cap_box, wx.VERTICAL)

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._backend_input, bes = _make_labeled_input(panel, tr("field.backend"), cfg.capture.backend, size=(90, -1))
        row1.Add(bes, 0, wx.RIGHT, 20)
        self._cam_index_input, cis = _make_int_input(panel, tr("field.camera_index"), cfg.capture.camera_index)
        row1.Add(cis, 0, wx.RIGHT, 20)
        self._fps_input, fps = _make_int_input(panel, tr("field.fps"), cfg.capture.fps)
        row1.Add(fps, 0)
        cap_sz.Add(row1, 0, wx.EXPAND | wx.ALL, 4)

        vbox.Add(cap_sz, 0, wx.EXPAND | wx.ALL, 4)

        # ══════════════════════════════════════════════════════════
        # ▸ 快捷键自定义
        # ══════════════════════════════════════════════════════════
        hotkey_box = wx.StaticBox(panel, label=tr("section.hotkeys"))
        self._static_boxes["hotkeys"] = hotkey_box
        hotkey_sz = wx.StaticBoxSizer(hotkey_box, wx.VERTICAL)

        hk_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self._hotkey_single_input, hss = _make_labeled_input(
            panel, tr("field.hotkey_single"), cfg.gui.hotkey_single_translate, size=(80, -1))
        hk_row1.Add(hss, 0, wx.RIGHT, 15)
        self._hotkey_pause_input, hps = _make_labeled_input(
            panel, tr("field.hotkey_pause"), cfg.gui.hotkey_pause, size=(80, -1))
        hk_row1.Add(hps, 0, wx.RIGHT, 15)
        self._hotkey_quit_input, hqs = _make_labeled_input(
            panel, tr("field.hotkey_quit"), cfg.gui.hotkey_quit, size=(80, -1))
        hk_row1.Add(hqs, 0)
        hotkey_sz.Add(hk_row1, 0, wx.EXPAND | wx.ALL, 4)

        hk_row2 = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_apply_hotkeys = wx.Button(panel, label=tr("btn.apply_hotkeys"), size=(140, 32))
        self._btn_apply_hotkeys.Bind(wx.EVT_BUTTON, lambda e: self._apply_hotkeys())
        hk_row2.Add(self._btn_apply_hotkeys, 0)
        hk_row2.AddStretchSpacer(1)
        hotkey_sz.Add(hk_row2, 0, wx.EXPAND | wx.ALL, 4)

        vbox.Add(hotkey_sz, 0, wx.EXPAND | wx.ALL, 4)

        # ══════════════════════════════════════════════════════════
        # ▸ 日志
        # ══════════════════════════════════════════════════════════
        log_box = wx.StaticBox(panel, label=tr("section.logging"))
        self._static_boxes["logging"] = log_box
        log_sz = wx.StaticBoxSizer(log_box, wx.VERTICAL)
        self._log_enabled_cb = wx.CheckBox(panel, label=tr("cb.logging"))
        self._log_enabled_cb.SetValue(cfg.logging.enabled)
        self._log_enabled_cb.Bind(wx.EVT_CHECKBOX, self._on_logging_toggle)
        log_sz.Add(self._log_enabled_cb, 0, wx.EXPAND | wx.ALL, 4)
        vbox.Add(log_sz, 0, wx.EXPAND | wx.ALL, 4)

        # ══════════════════════════════════════════════════════════
        # ▸ 实时结果区域（占据剩余空间）
        # ══════════════════════════════════════════════════════════
        result_box = wx.StaticBox(panel, label=tr("section.live_result"))
        self._static_boxes["live_result"] = result_box
        result_sz = wx.StaticBoxSizer(result_box, wx.VERTICAL)

        self._result_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.TE_RICH2,
        )
        self._result_text.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE,
                                           wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        result_sz.Add(self._result_text, 1, wx.EXPAND | wx.ALL, 5)
        vbox.Add(result_sz, 1, wx.EXPAND | wx.ALL, 4)

        # ── 快捷键提示 ──
        self._hotkey_label = wx.StaticText(panel, label=self._make_hotkey_label_text())
        self._hotkey_label.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT,
                                           wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
        vbox.Add(self._hotkey_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)

        sw.SetSizer(vbox)

    def _make_hotkey_label_text(self) -> str:
        """生成快捷键提示文本"""
        cfg = self._config.gui
        return tr("hotkey.label",
                  single=cfg.hotkey_single_translate,
                  pause=cfg.hotkey_pause,
                  quit=cfg.hotkey_quit)

    def _refresh_hotkey_label(self):
        """刷新快捷键提示标签"""
        self._hotkey_label.SetLabel(self._make_hotkey_label_text())

    # ── 快捷键 ───────────────────────────────────────────────────

    def _setup_hotkeys(self):
        """初始化快捷键（首次注册）"""
        self._hotkey_handlers = []
        self._register_hotkeys()

    def _register_hotkeys(self):
        """注册所有快捷键，保存 handler 以便后续解绑"""
        try:
            import keyboard
            cfg = self._config.gui
            # 按顺序注册并存储 handler
            for hotkey_str, callback in [
                (cfg.hotkey_pause, lambda: wx.CallAfter(self._on_toggle)),
                (cfg.hotkey_quit, lambda: wx.CallAfter(self._on_stop)),
                (cfg.hotkey_single_translate,
                 lambda: wx.CallAfter(self._on_single) if self._on_single else None),
            ]:
                handler = keyboard.add_hotkey(hotkey_str, callback, suppress=True)
                self._hotkey_handlers.append(handler)
        except Exception as e:
            print(f"[GUI] Hotkey registration failed: {e}")

    def _unbind_hotkeys(self):
        """解绑所有已注册的快捷键"""
        for handler in self._hotkey_handlers:
            try:
                handler()
            except Exception:
                pass
        self._hotkey_handlers.clear()

    def _apply_hotkeys(self):
        """应用 GUI 中修改的快捷键：读取输入 → 解绑旧键 → 注册新键 → 更新提示"""
        new_single = self._hotkey_single_input.GetValue().strip()
        new_pause = self._hotkey_pause_input.GetValue().strip()
        new_quit = self._hotkey_quit_input.GetValue().strip()

        # 基础校验
        if not new_single or not new_pause or not new_quit:
            wx.MessageBox(tr("dlg.hotkey_empty"), tr("dlg.hotkey_invalid_title"),
                          wx.OK | wx.ICON_WARNING)
            return
        if len({new_single, new_pause, new_quit}) < 3:
            wx.MessageBox(tr("dlg.hotkey_duplicate"), tr("dlg.hotkey_invalid_title"),
                          wx.OK | wx.ICON_WARNING)
            return

        # 更新 config
        cfg = self._config.gui
        cfg.hotkey_single_translate = new_single
        cfg.hotkey_pause = new_pause
        cfg.hotkey_quit = new_quit

        # 解绑旧键 → 注册新键
        self._unbind_hotkeys()
        self._register_hotkeys()

        # 更新快捷键提示文本
        self._refresh_hotkey_label()

        print(f"[GUI] Hotkeys applied: single={new_single}, pause={new_pause}, quit={new_quit}")

    # ── URL 测试 ─────────────────────────────────────────────────

    def _on_test_url(self, event):
        """测试 llama.cpp URL 连通性"""
        import requests
        url = self._url_input.GetValue().strip()
        if not url:
            wx.MessageBox(tr("dlg.enter_url"), tr("dlg.warning_title"), wx.OK | wx.ICON_WARNING)
            return

        self._btn_test_url.Enable(False)
        self._btn_test_url.SetLabel("...")
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
                wx.CallAfter(self._show_test_result, False,
                             tr("dlg.connection_failed"))
            except requests.exceptions.Timeout:
                wx.CallAfter(self._show_test_result, False,
                             tr("dlg.connection_timeout"))
            except Exception as e:
                wx.CallAfter(self._show_test_result, False,
                             tr("dlg.test_error", error_type=type(e).__name__, error_msg=e))

        threading.Thread(target=test_connection, daemon=True).start()

    def _show_test_result(self, success: bool, message: str):
        """在主线程中显示测试结果"""
        self._btn_test_url.Enable(True)
        self._btn_test_url.SetLabel(tr("btn.test"))
        if success:
            wx.MessageBox(message, tr("dlg.test_ok_title"), wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox(message, tr("dlg.test_failed_title"), wx.OK | wx.ICON_ERROR)

    # ── 状态更新（线程安全）──────────────────────────────────────

    # 结果文本最大字符数，防止 TextCtrl 无限增长导致渲染变慢
    _MAX_RESULT_CHARS = 8000

    def update_status(self, status: str):
        """更新状态显示（线程安全，单次 CallAfter）

        status 为英文状态字符串（如 "Ready", "Running", "Paused", "Stopped"），
        显示时会被翻译为当前语言。
        """
        def _update():
            # 翻译常用状态
            status_map = {
                "Ready": tr("status.ready"),
                "Running": tr("status.running"),
                "Paused": tr("status.paused"),
                "Stopped": tr("status.stopped"),
                "Initializing...": tr("status.initializing"),
            }
            # 处理单次翻译状态
            if status.startswith("Single:"):
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
                self._status_label.SetLabel(tr("status.label", status=disp))
            elif status.startswith("Error:"):
                error = status[len("Error:"):].strip()
                disp = tr("status.error", error=error)
                self._status_label.SetLabel(tr("status.label", status=disp))
            elif status.startswith("Warning:"):
                self._status_label.SetLabel(tr("status.label", status=status))
            elif status in status_map:
                self._status_label.SetLabel(tr("status.label", status=status_map[status]))
            else:
                self._status_label.SetLabel(tr("status.label", status=status))

            is_running = status in ("Running", "Paused")
            self._pipeline_running = is_running
            self._btn_start.Enable(not is_running)
            self._btn_pause.Enable(is_running)
            self._btn_stop.Enable(is_running)
            if status == "Paused":
                self._btn_pause.SetLabel(tr("btn.resume"))
            else:
                self._btn_pause.SetLabel(tr("btn.pause"))

            # Single 按钮：仅在单次翻译执行中禁用，其他时间均可使用
            self._btn_single.Enable(not self._single_in_progress)
        wx.CallAfter(_update)

    def update_ocr_result(self, cycle_id: int, boxes: list,
                           det_ms: float = 0.0, rec_ms: float = 0.0):
        """实时显示 OCR 识别结果（线程安全），含耗时统计"""
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
                    self._result_text.AppendText(
                        f"  [{i}] \"{tb.text}\"\n"
                    )
                self._result_text.AppendText("\n")
                self._trim_result_text()
                self._result_text.ShowPosition(self._result_text.GetLastPosition())
            finally:
                self._result_text.Thaw()
        wx.CallAfter(_update)

    def update_translation_result(self, cycle_id: int, pairs: list, total_ms: float):
        """实时显示翻译结果（线程安全），含耗时统计"""
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
        """更新最近周期摘要信息"""
        if cycle.skipped:
            info = f"Cycle #{cycle.cycle_id}: SKIPPED ({cycle.skip_reason})"
        else:
            info = (
                f"Cycle #{cycle.cycle_id}: {len(cycle.text_boxes)} boxes, "
                f"Total: {cycle.total_ms:.0f}ms | "
                f"Cap: {cycle.capture_ms:.0f}ms | "
                f"OCR: {cycle.ocr_det_ms + cycle.ocr_rec_ms:.0f}ms | "
                f"Trans: {cycle.translate_ms:.0f}ms"
            )
        wx.CallAfter(self._status_label.SetLabel, f"Status: {info}")

    def _trim_result_text(self):
        """
        裁剪结果文本框内容，防止无限增长导致 TextCtrl 渲染变慢。

        当字符数超过 MAX_RESULT_CHARS 时，从头部删除旧内容。
        """
        text = self._result_text.GetValue()
        if len(text) > self._MAX_RESULT_CHARS:
            # 从头部截断：找到第一个换行后的截断点
            trim_at = len(text) - self._MAX_RESULT_CHARS
            # 对齐到下一个换行符，避免裁出半行
            nl_pos = text.find("\n", trim_at)
            if nl_pos >= 0:
                trim_at = nl_pos + 1
            self._result_text.Remove(0, trim_at)
            # 添加截断标记
            self._result_text.SetValue(
                f"... (older results trimmed) ...\n{self._result_text.GetValue()}"
            )

    # ── 读取当前 GUI 值 ──────────────────────────────────────────

    def sync_config_from_gui(self):
        """将所有 GUI 控件值写回 self._config（在 pipeline 启动前调用）"""
        cfg = self._config

        # URL & languages (existing getters already use live values)
        cfg.source_lang = self._src_lang.GetValue().strip()
        cfg.target_lang = self._tgt_lang.GetValue().strip()
        cfg.translator.llama.url = self._url_input.GetValue().strip()

        # Pipeline
        try:
            cfg.pipeline.cycle_interval = float(self._interval_input.GetValue())
        except ValueError:
            pass
        try:
            cfg.pipeline.diff_threshold = float(self._diff_thresh_input.GetValue())
        except ValueError:
            pass
        try:
            cfg.pipeline.max_text_boxes = int(self._max_boxes_input.GetValue())
        except ValueError:
            pass

        # OCR
        cfg.ocr.engine = self._ocr_engine_from_selection()
        # EasyOCR 语言
        lang_str = self._easyocr_lang_input.GetValue().strip()
        if lang_str:
            cfg.ocr.easyocr_languages = [l.strip() for l in lang_str.split(",") if l.strip()]
        else:
            cfg.ocr.easyocr_languages = ["en"]
        try:
            cfg.ocr.cpu_threads = int(self._cpu_threads_input.GetValue())
        except ValueError:
            pass
        try:
            cfg.ocr.det_resize_long = int(self._det_resize_long_input.GetValue())
        except ValueError:
            pass
        try:
            cfg.ocr.det_threshold = float(self._det_thresh_input.GetValue())
        except ValueError:
            pass
        try:
            cfg.ocr.box_threshold = float(self._box_thresh_input.GetValue())
        except ValueError:
            pass
        try:
            cfg.ocr.min_confidence = float(self._min_conf_input.GetValue())
        except ValueError:
            pass
        # 预处理开关
        cfg.ocr.det_invert_dark = self._det_invert_cb.GetValue()
        cfg.ocr.det_denoise = self._det_denoise_cb.GetValue()
        cfg.ocr.rec_enhance = self._rec_enhance_cb.GetValue()

        # Translator
        ll = cfg.translator.llama
        try:
            ll.timeout = int(self._timeout_input.GetValue())
        except ValueError:
            pass
        try:
            ll.max_retries = int(self._max_retries_input.GetValue())
        except ValueError:
            pass
        try:
            ll.parallel_requests = int(self._parallel_input.GetValue())
        except ValueError:
            pass
        try:
            ll.inference_params["temperature"] = float(self._temp_input.GetValue())
        except ValueError:
            pass
        try:
            ll.inference_params["top_k"] = int(self._topk_input.GetValue())
        except ValueError:
            pass
        try:
            ll.inference_params["top_p"] = float(self._topp_input.GetValue())
        except ValueError:
            pass
        try:
            ll.inference_params["repeat_penalty"] = float(self._rpen_input.GetValue())
        except ValueError:
            pass
        try:
            ll.inference_params["n_predict"] = int(self._npredict_input.GetValue())
        except ValueError:
            pass

        # Overlay
        try:
            cfg.overlay.font_size = int(self._font_size_input.GetValue())
        except ValueError:
            pass
        cfg.overlay.font_family = self._font_family_input.GetValue().strip()
        cfg.overlay.text_color = self._text_color_input.GetValue().strip()
        try:
            cfg.overlay.background_opacity = float(self._bg_opacity_input.GetValue())
        except ValueError:
            pass

        # Capture
        cfg.capture.backend = self._backend_input.GetValue().strip()
        try:
            cfg.capture.camera_index = int(self._cam_index_input.GetValue())
        except ValueError:
            pass
        try:
            cfg.capture.fps = int(self._fps_input.GetValue())
        except ValueError:
            pass

        # Hotkeys
        if hasattr(self, '_hotkey_single_input'):
            cfg.gui.hotkey_single_translate = self._hotkey_single_input.GetValue().strip()
            cfg.gui.hotkey_pause = self._hotkey_pause_input.GetValue().strip()
            cfg.gui.hotkey_quit = self._hotkey_quit_input.GetValue().strip()

        # UI language
        cfg.gui.ui_language = self._locale.lang

    # ── 原有 getter ──────────────────────────────────────────────

    def get_url(self) -> str:
        return self._url_input.GetValue()

    def get_langs(self) -> tuple[str, str]:
        return self._src_lang.GetValue(), self._tgt_lang.GetValue()

    def get_interval(self) -> float:
        try:
            return float(self._interval_input.GetValue())
        except ValueError:
            return 5.0

    # ── 开关回调 ─────────────────────────────────────────────────

    def _on_diff_detection_button(self):
        """差异检测按钮回调 — 切换开关状态"""
        current = self._config.pipeline.diff_detection
        new_state = not current
        self._config.pipeline.diff_detection = new_state
        self._diff_detection_cb.SetValue(new_state)
        self._update_diff_button_label()

    def _on_diff_detection_toggle(self, event):
        """差异检测复选框回调"""
        self._config.pipeline.diff_detection = self._diff_detection_cb.GetValue()
        self._update_diff_button_label()

    def _on_downscale_button(self):
        """720p 下采样按钮回调 — 切换开关状态"""
        current = self._config.pipeline.downscale_max_size > 0
        new_state = not current
        self._config.pipeline.downscale_max_size = 720 if new_state else 0
        self._update_downscale_button_label()

    def _update_downscale_button_label(self):
        """更新下采样按钮标签"""
        if self._config.pipeline.downscale_max_size > 0:
            self._btn_downscale.SetLabel(tr("downscale.on"))
        else:
            self._btn_downscale.SetLabel(tr("downscale.off"))

    def _on_exclude_cap_toggle(self, event):
        """Exclude from capture 复选框回调"""
        self._config.overlay.exclude_from_capture = self._exclude_cap_cb.GetValue()

    def _on_logging_toggle(self, event):
        """日志开关回调"""
        self._config.logging.enabled = self._log_enabled_cb.GetValue()

    def _on_ocr_preproc_toggle(self, event):
        """OCR 预处理开关回调"""
        cfg = self._config.ocr
        cfg.det_invert_dark = self._det_invert_cb.GetValue()
        cfg.det_denoise = self._det_denoise_cb.GetValue()
        cfg.rec_enhance = self._rec_enhance_cb.GetValue()

    def _ocr_engine_from_selection(self) -> str:
        """将选择索引映射为引擎标识符"""
        idx = self._ocr_engine_choice.GetSelection()
        return "paddle" if idx == 0 else "easyocr"

    def _on_ocr_engine_changed(self, event):
        """OCR 引擎切换回调 — 自动重启流水线以应用新引擎"""
        engine = self._ocr_engine_from_selection()
        old_engine = self._config.ocr.engine
        self._config.ocr.engine = engine

        # 更新 OCR Group Box 标题
        self._ocr_box.SetLabel(tr("section.ocr", engine=engine))

        # 显示/隐藏 EasyOCR 语言输入
        if engine == "easyocr":
            self._easyocr_lang_sizer.ShowItems(True)
        else:
            self._easyocr_lang_sizer.ShowItems(False)

        # 刷新布局
        self._ocr_box.GetContainingSizer().Layout()

        # 如果引擎实际变更，自动重启以应用新引擎
        if engine != old_engine:
            if self._pipeline_running:
                # 流水线正在运行：先停止再重启
                self._on_stop()
                print(f"[GUI] Pipeline restarting with engine: {engine}")
                wx.CallLater(600, self._on_start)
            else:
                # 流水线未运行：启动后立即停止，确保引擎被正确初始化
                print(f"[GUI] Initializing engine: {engine} (pipeline not running)")
                self._on_start()
                wx.CallLater(400, self._on_stop)


class TrayIcon(wx.adv.TaskBarIcon):
    """系统托盘图标"""

    def __init__(self, frame: MainWindow):
        super().__init__()
        self._frame = frame
        self.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16))),
                     "Screen Translate")
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
