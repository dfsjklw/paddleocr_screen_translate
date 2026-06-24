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
    "btn.test": {
        "en": "Test",
        "zh": "测试",
    },
    "btn.apply_hotkeys": {
        "en": "Apply Hotkeys",
        "zh": "应用快捷键",
    },
    "btn.region_translate": {
        "en": "Region",
        "zh": "划屏翻译",
    },
    "btn.clear_overlay": {
        "en": "Clear",
        "zh": "清除覆盖层",
    },
    "btn.lang_toggle": {
        "en": "中",
        "zh": "EN",
    },

    # ── 状态 ──
    "status.ready": {
        "en": "Ready",
        "zh": "就绪",
    },
    "status.initializing": {
        "en": "Initializing...",
        "zh": "初始化中…",
    },
    "status.region_init": {
        "en": "Region: initializing...",
        "zh": "划屏: 初始化中…",
    },
    "status.region_capturing": {
        "en": "Region: capturing...",
        "zh": "划屏: 截图中…",
    },
    "status.region_done": {
        "en": "Region: done",
        "zh": "划屏: 完成",
    },
    "status.region_error": {
        "en": "Region: error: {error}",
        "zh": "划屏: 错误: {error}",
    },
    "status.region_init_failed": {
        "en": "Region: init failed",
        "zh": "划屏: 初始化失败",
    },
    "status.region_selecting": {
        "en": "Region: drag to select area (ESC to cancel)",
        "zh": "划屏: 拖动选择区域 (ESC 取消)",
    },
    "status.overlay_cleared": {
        "en": "Overlay cleared",
        "zh": "覆盖层已清除",
    },
    "status.error": {
        "en": "Error: {error}",
        "zh": "错误: {error}",
    },
    "status.warning_ocr": {
        "en": "Warning: OCR init failed",
        "zh": "警告: OCR 初始化失败",
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
    "field.hotkey_region": {
        "en": "Region Trans:",
        "zh": "划屏翻译:",
    },
    "field.hotkey_clear": {
        "en": "Clear Overlay:",
        "zh": "清除覆盖层:",
    },
    "field.hotkey_quit": {
        "en": "Quit:",
        "zh": "退出:",
    },

    # ── 复选框 ──
    "cb.logging": {
        "en": "Enable cycle logging",
        "zh": "启用周期日志",
    },

    # ── 工具提示 ──
    "tooltip.region": {
        "en": "Region translation — drag to select screen area, OCR, translate, overlay at original position",
        "zh": "划屏翻译 — 拖动选择屏幕区域 → OCR → 翻译 → 原位覆盖显示",
    },
    "tooltip.clear_overlay": {
        "en": "Clear all overlay text from the screen",
        "zh": "清除屏幕上所有覆盖层文字",
    },

    # ── 快捷键提示 ──
    "hotkey.label": {
        "en": "Hotkeys: {region} = Region, {clear} = Clear, {quit} = Quit",
        "zh": "快捷键: {region} = 划屏翻译, {clear} = 清除覆盖层, {quit} = 退出",
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

    # ── 选项卡标签 ──
    "tab.control": {
        "en": "🎛  Control",
        "zh": "🎛  控制",
    },
    "tab.ocr": {
        "en": "🔍  OCR",
        "zh": "🔍  OCR",
    },
    "tab.translator": {
        "en": "🌐  Translator",
        "zh": "🌐  翻译器",
    },
    "tab.overlay": {
        "en": "🖼  Overlay",
        "zh": "🖼  覆盖层",
    },
    "tab.hotkeys": {
        "en": "⌨  Hotkeys",
        "zh": "⌨  快捷键",
    },
    "tab.logging": {
        "en": "📋  Logging",
        "zh": "📋  日志",
    },
    "tab.result": {
        "en": "📊  Results",
        "zh": "📊  结果",
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

    # ── 划屏翻译区域选择器 ──
    "region.instructions": {
        "en": "Click and drag to select a region for translation\nPress ESC or right-click to cancel",
        "zh": "点击并拖动选择要翻译的区域\n按 ESC 或右键取消",
    },
    "region.dimensions": {
        "en": "{w} x {h}",
        "zh": "{w} x {h}",
    },
}
