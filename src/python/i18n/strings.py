"""
i18n/strings.py — 全部 UI 文本字符串（中英文）

每个 key 对应的 dict 必须包含 "en" 和 "zh" 两个键。
"""

STRINGS: dict[str, dict[str, str]] = {
    # ── 窗口标题 ──
    "app.title": {
        "en": "Screen Translate",
        "zh": "屏幕翻译",
    },

    # ── 按钮 ──
    "btn.start": {
        "en": "Start",
        "zh": "开始",
    },
    "btn.single": {
        "en": "Single",
        "zh": "单次翻译",
    },
    "btn.pause": {
        "en": "Pause",
        "zh": "暂停",
    },
    "btn.resume": {
        "en": "Resume",
        "zh": "继续",
    },
    "btn.stop": {
        "en": "Stop",
        "zh": "停止",
    },
    "btn.test": {
        "en": "Test",
        "zh": "测试",
    },
    "btn.apply_hotkeys": {
        "en": "Apply Hotkeys",
        "zh": "应用快捷键",
    },
    "btn.lang_toggle": {
        "en": "中",
        "zh": "EN",
    },

    # ── 差异检测按钮 ──
    "diff.on": {
        "en": "Diff Detection: ON",
        "zh": "差异检测: 开",
    },
    "diff.off": {
        "en": "Diff Detection: OFF",
        "zh": "差异检测: 关",
    },
    "downscale.on": {
        "en": "720p Downscale: ON",
        "zh": "720p 缩放: 开",
    },
    "downscale.off": {
        "en": "720p Downscale: OFF",
        "zh": "720p 缩放: 关",
    },

    # ── 状态 ──
    "status.ready": {
        "en": "Ready",
        "zh": "就绪",
    },
    "status.running": {
        "en": "Running",
        "zh": "运行中",
    },
    "status.paused": {
        "en": "Paused",
        "zh": "已暂停",
    },
    "status.stopped": {
        "en": "Stopped",
        "zh": "已停止",
    },
    "status.initializing": {
        "en": "Initializing...",
        "zh": "初始化中…",
    },
    "status.single_init": {
        "en": "Single: initializing...",
        "zh": "单次: 初始化中…",
    },
    "status.single_capturing": {
        "en": "Single: capturing...",
        "zh": "单次: 截图中…",
    },
    "status.single_done": {
        "en": "Single: done",
        "zh": "单次: 完成",
    },
    "status.single_error": {
        "en": "Single: error: {error}",
        "zh": "单次: 错误: {error}",
    },
    "status.single_init_failed": {
        "en": "Single: init failed",
        "zh": "单次: 初始化失败",
    },
    "status.error": {
        "en": "Error: {error}",
        "zh": "错误: {error}",
    },
    "status.warning_ocr": {
        "en": "Warning: OCR init failed",
        "zh": "警告: OCR 初始化失败",
    },
    "status.label": {
        "en": "Status: {status}",
        "zh": "状态: {status}",
    },

    # ── 区块标题 ──
    "section.basic": {
        "en": "Basic",
        "zh": "基础设置",
    },
    "section.ocr": {
        "en": "OCR ({engine})",
        "zh": "OCR ({engine})",
    },
    "section.translator": {
        "en": "Translator (llama.cpp)",
        "zh": "翻译器 (llama.cpp)",
    },
    "section.overlay": {
        "en": "Overlay",
        "zh": "覆盖层",
    },
    "section.capture": {
        "en": "Capture",
        "zh": "采集",
    },
    "section.hotkeys": {
        "en": "Hotkeys",
        "zh": "快捷键",
    },
    "section.logging": {
        "en": "Logging",
        "zh": "日志",
    },
    "section.live_result": {
        "en": "Live OCR & Translation",
        "zh": "实时识别与翻译",
    },

    # ── 字段标签 ──
    "field.llama_url": {
        "en": "llama.cpp URL:",
        "zh": "llama.cpp 地址:",
    },
    "field.source_lang": {
        "en": "Source:",
        "zh": "源语言:",
    },
    "field.target_lang": {
        "en": "Target:",
        "zh": "目标语言:",
    },
    "field.cycle_interval": {
        "en": "Cycle interval (s):",
        "zh": "周期间隔 (秒):",
    },
    "field.diff_threshold": {
        "en": "Diff threshold:",
        "zh": "差异阈值:",
    },
    "field.max_text_boxes": {
        "en": "Max text boxes:",
        "zh": "最大文本框:",
    },
    "field.ocr_engine": {
        "en": "OCR Engine:",
        "zh": "OCR 引擎:",
    },
    "field.easyocr_langs": {
        "en": "EasyOCR langs:",
        "zh": "EasyOCR 语言:",
    },
    "field.easyocr_hint": {
        "en": "(comma-separated, e.g. en,ch_sim,ja)",
        "zh": "(逗号分隔，如 en,ch_sim,ja)",
    },
    "field.cpu_threads": {
        "en": "CPU threads:",
        "zh": "CPU 线程:",
    },
    "field.resize_long": {
        "en": "Resize long:",
        "zh": "长边缩放:",
    },
    "field.det_threshold": {
        "en": "Det threshold:",
        "zh": "检测阈值:",
    },
    "field.box_threshold": {
        "en": "Box threshold:",
        "zh": "框阈值:",
    },
    "field.min_confidence": {
        "en": "Min confidence:",
        "zh": "最小置信度:",
    },
    "field.timeout": {
        "en": "Timeout (s):",
        "zh": "超时 (秒):",
    },
    "field.max_retries": {
        "en": "Max retries:",
        "zh": "最大重试:",
    },
    "field.parallel": {
        "en": "Parallel:",
        "zh": "并行数:",
    },
    "field.temperature": {
        "en": "Temperature:",
        "zh": "温度:",
    },
    "field.top_k": {
        "en": "Top-K:",
        "zh": "Top-K:",
    },
    "field.top_p": {
        "en": "Top-P:",
        "zh": "Top-P:",
    },
    "field.repeat_penalty": {
        "en": "Repeat penalty:",
        "zh": "重复惩罚:",
    },
    "field.n_predict": {
        "en": "N predict:",
        "zh": "预测长度:",
    },
    "field.font_size": {
        "en": "Font size:",
        "zh": "字体大小:",
    },
    "field.bg_opacity": {
        "en": "BG opacity:",
        "zh": "背景透明度:",
    },
    "field.font_family": {
        "en": "Font family:",
        "zh": "字体:",
    },
    "field.text_color": {
        "en": "Text color:",
        "zh": "文字颜色:",
    },
    "field.backend": {
        "en": "Backend:",
        "zh": "采集端:",
    },
    "field.camera_index": {
        "en": "Camera index:",
        "zh": "摄像头索引:",
    },
    "field.fps": {
        "en": "FPS:",
        "zh": "帧率:",
    },
    "field.hotkey_single": {
        "en": "Single Shot:",
        "zh": "单次翻译:",
    },
    "field.hotkey_pause": {
        "en": "Pause/Resume:",
        "zh": "暂停/继续:",
    },
    "field.hotkey_quit": {
        "en": "Quit:",
        "zh": "退出:",
    },

    # ── 复选框 ──
    "cb.diff_detection": {
        "en": "Enable frame diff detection (skip unchanged frames)",
        "zh": "启用帧差异检测 (跳过无变化帧)",
    },
    "cb.invert_dark": {
        "en": "Auto-invert dark backgrounds",
        "zh": "深色背景自动反色",
    },
    "cb.denoise": {
        "en": "Denoise before detection (Gaussian blur)",
        "zh": "检测前去噪 (高斯模糊)",
    },
    "cb.enhance": {
        "en": "Enhance before recognition (CLAHE)",
        "zh": "识别前增强 (CLAHE)",
    },
    "cb.exclude_capture": {
        "en": "Exclude overlay from capture (anti-pollution)",
        "zh": "从采集中排除覆盖层 (防污染)",
    },
    "cb.logging": {
        "en": "Enable cycle logging",
        "zh": "启用周期日志",
    },

    # ── 工具提示 ──
    "tooltip.single": {
        "en": "Single-shot translation (capture one frame, OCR, translate, overlay)",
        "zh": "单次翻译 (截取一帧 → OCR → 翻译 → 覆盖显示)",
    },

    # ── 快捷键提示 ──
    "hotkey.label": {
        "en": "Hotkeys: {single} = Single Shot, {pause} = Pause/Resume, {quit} = Quit",
        "zh": "快捷键: {single} = 单次翻译, {pause} = 暂停/继续, {quit} = 退出",
    },

    # ── 对话框消息 ──
    "dlg.init_failed": {
        "en": "Pipeline init failed. Check logs.",
        "zh": "流水线初始化失败，请检查日志。",
    },
    "dlg.error_title": {
        "en": "Error",
        "zh": "错误",
    },
    "dlg.warning_title": {
        "en": "Warning",
        "zh": "警告",
    },
    "dlg.enter_url": {
        "en": "Please enter a URL first.",
        "zh": "请先输入 URL。",
    },
    "dlg.hotkey_empty": {
        "en": "All hotkey fields must be non-empty.",
        "zh": "所有快捷键字段不能为空。",
    },
    "dlg.hotkey_duplicate": {
        "en": "Hotkeys must be unique (no duplicates).",
        "zh": "快捷键必须唯一（不能重复）。",
    },
    "dlg.hotkey_invalid_title": {
        "en": "Invalid Hotkey",
        "zh": "无效快捷键",
    },
    "dlg.test_ok_title": {
        "en": "Test OK",
        "zh": "测试成功",
    },
    "dlg.test_failed_title": {
        "en": "Test Failed",
        "zh": "测试失败",
    },
    "dlg.connection_success": {
        "en": "Connection successful!\n\nServer response:\n{data}",
        "zh": "连接成功！\n\n服务器响应:\n{data}",
    },
    "dlg.connection_unexpected": {
        "en": "Server responded but status is unexpected:\n{data}",
        "zh": "服务器有响应但状态异常:\n{data}",
    },
    "dlg.connection_failed": {
        "en": "Connection failed: Cannot reach the server.\n\nPlease check:\n• The URL is correct\n• llama.cpp server is running\n• No firewall is blocking the connection",
        "zh": "连接失败: 无法访问服务器。\n\n请检查:\n• URL 是否正确\n• llama.cpp 服务是否在运行\n• 防火墙是否阻止了连接",
    },
    "dlg.connection_timeout": {
        "en": "Connection timed out.\n\nThe server did not respond within 5 seconds.",
        "zh": "连接超时。\n\n服务器在 5 秒内未响应。",
    },
    "dlg.test_error": {
        "en": "Test failed with error:\n{error_type}: {error_msg}",
        "zh": "测试失败，错误信息:\n{error_type}: {error_msg}",
    },

    # ── 托盘菜单 ──
    "tray.show_hide": {
        "en": "Show/Hide",
        "zh": "显示/隐藏",
    },
    "tray.quit": {
        "en": "Quit",
        "zh": "退出",
    },

    # ── OCR 引擎名 ──
    "ocr.paddle_label": {
        "en": "PaddleOCR",
        "zh": "PaddleOCR",
    },
    "ocr.easyocr_label": {
        "en": "EasyOCR",
        "zh": "EasyOCR",
    },

    # ── 结果区域占位 ──
    "result.cycle_header": {
        "en": "Cycle #{id} — OCR ({count} boxes) | Det: {det}ms  Rec: {rec}ms  Total: {total}ms",
        "zh": "周期 #{id} — OCR ({count} 框) | 检测: {det}ms  识别: {rec}ms  总计: {total}ms",
    },
    "result.trans_header": {
        "en": "Cycle #{id} — Translation ({count} items) | Total: {total}ms",
        "zh": "周期 #{id} — 翻译 ({count} 项) | 总计: {total}ms",
    },
}
