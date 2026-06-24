# Screen Translate — 架构设计文档

> 更新日期：2026-06-24

## 1. 项目概览

**目标**：实时屏幕翻译系统，Windows优先、跨平台可移植。

**核心流程**（一次完整周期）：
```
OBS虚拟摄像头 → OpenCV采集帧 → 720p下采样(可选) → OCR识别 → 坐标还原 → llama.cpp翻译 → 覆盖层显示
```

**技术栈**：纯 Python（OCR 使用 `paddleocr` 库 + `easyocr` 库，无需 C++ 编译）

---

## 2. 模块架构

```
┌─────────────────────────────────────────────────────────────┐
│                      main.py (入口)                         │
│                  wx.App → App.OnInit()                      │
├─────────────────────────────────────────────────────────────┤
│                    MainWindow (GUI)                         │
│  按钮: Start | Single | Pause/Resume | Stop                │
│  切换: Diff Detection | 720p Downscale                     │
│  语言切换: 中/EN                                           │
│  配置: URL, 语言, 间隔, OCR引擎, 预处理开关                 │
│  状态显示 + 实时OCR/翻译结果                                │
├─────────────────────────────────────────────────────────────┤
│                    Pipeline (调度核心)                       │
│  线程安全, 暂停/继续, 差异检测跳过, 720p下采样              │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Capture  │  │   OCR    │  │Translator│  │ Overlay  │   │
│  │ (采集)   │  │ (识别)   │  │ (翻译)   │  │ (覆盖层) │   │
│  ├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤   │
│  │OpenCV    │  │双引擎:   │  │HTTP API  │  │wxPython  │   │
│  │DirectShow│  │PaddleOCR │  │llama.cpp │  │透明窗口  │   │
│  │OBS虚拟   │  │EasyOCR   │  │/v1/chat/ │  │WDA_EXCL  │   │
│  │摄像头    │  │本地模型  │  │completions│  │64-bit HDC│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │  Logger  │  │  Config  │  │   i18n   │                 │
│  │ (日志)   │  │ (配置)   │  │ (国际化) │                 │
│  ├──────────┤  ├──────────┤  ├──────────┤                 │
│  │JSONL格式 │  │YAML解析  │  │中英文切换│                 │
│  │周期记录  │  │dataclass │  │80+字符串 │                 │
│  │OCR+翻译  │  │路径解析  │  │即时刷新  │                 │
│  └──────────┘  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 模块详解

| 模块 | 文件 | 职责 | 解耦方式 |
|------|------|------|----------|
| **Capture** | `capture/capture.py` | 从OBS虚拟摄像头或屏幕直接读取帧（BGR numpy数组） | 抽象基类 `CaptureBackend`，工厂函数 `create_capture()` |
| **OCR** | `ocr/paddle_ocr_engine.py` + `ocr/easy_ocr_engine.py` | 双引擎检测+识别，统一返回带位置的文本 | 统一接口 `TextBox/OcrOutput`，工厂 `create_ocr_engine()` |
| **Translator** | `translator/translator.py` | 调用 llama.cpp HTTP API 翻译 | 抽象基类 `TranslatorBackend`，工厂函数 `create_translator()` |
| **Overlay** | `overlay/overlay.py` | 透明窗口覆盖翻译文本，64-bit HDC 兼容 | 通过 `OverlayItem` 数据类与 Pipeline 通信 |
| **GUI** | `gui/main_window.py` | 控制面板 + 托盘 + 快捷键 + 语言切换 + 引擎切换 | 通过回调函数与 Pipeline 通信 |
| **Logger** | `logger/cycle_logger.py` | JSONL 周期日志 + 人类可读 OCR/翻译日志 | 独立模块，`CycleLogger` 通过 `write_cycle()` 接口 |
| **Config** | `config/settings.py` | YAML→dataclass 配置解析 | 纯数据类，无行为依赖 |
| **Pipeline** | `pipeline/pipeline.py` | 编排完整流程，720p下采样+坐标还原 | 依赖注入：各模块通过构造函数传入 |
| **i18n** | `i18n/` | 中英文 UI 文本管理 | `LocaleManager` 单例 + `tr()` 函数，订阅/通知模式 |

---

## 3. 数据流

```
config.yaml ──→ AppConfig (dataclass)
                    │
                    ▼
              Pipeline.__init__(config, overlay, callbacks)
                    │
                    ▼ (线程循环, 每 cycle_interval 秒)
     ┌──────────────────────────────────────────┐
     │  1. Capture.read_frame() → np.ndarray    │
     │  2. 差异检测 (与上一帧对比)                │
     │     ├─ 无变化 → 复用上次结果, skip         │
     │     └─ 有变化 ↓                           │
     │  3. 720p下采样 (长边>720 → 等比缩放)       │
     │  4. OCR.process(scaled_frame) → OcrOutput  │
     │     └─ [TextBox(points, text, scores)...] │
     │  5. 坐标还原 (除以缩放比例)                 │
     │  6. Translator.translate_batch(texts)      │
     │     └─ [TranslationResult(text)...]        │
     │  7. Overlay.set_items() → show_overlay()   │
     │     └─ [OverlayItem(x,y,w,h,text)...]     │
     │  8. Logger.write_cycle(CycleLog)           │
     └──────────────────────────────────────────┘
                    │
                    ▼
              GUI 更新 (线程安全, wx.CallAfter)
              on_status_change() / on_cycle_complete()
              on_ocr_result() / on_translation_result()
```

---

## 4. OCR 双引擎架构

### 4.1 引擎选择

```
config.ocr.engine ──→ create_ocr_engine(config)
                      ├─ "paddle"  → PaddleOcrEngine
                      └─ "easyocr" → EasyOcrEngine
```

### 4.2 引擎切换

GUI 下拉菜单 → 更新 config → 自动停止+重启流水线 (wx.CallLater 600ms)

pipeline.init() 中先 shutdown 旧引擎再创建新引擎，防止资源泄漏。

### 4.3 PaddleOCR 纯 Python + 本地模型方案

```
PaddleOcrEngine.__init__(config)    →    PaddleOCR(
    ├─ resolve_path(det_model_dir)           text_detection_model_name='PP-OCRv5_mobile_det',
    ├─ resolve_path(rec_model_dir)           text_detection_model_dir=...,
    ├─ 验证本地模型目录存在                   text_recognition_model_name='PP-OCRv5_mobile_rec',
    └─ cpu_threads, thresholds               text_recognition_model_dir=...,
                                         )
PaddleOcrEngine.process(img)        →    ocr.predict(rgb_img)
    ├─ _preprocess_image()               → 返回 OCRResult
    │   ├─ detect_invert_dark             ├─ rec_texts: 识别文本
    │   ├─ Gaussian denoise              ├─ rec_scores: 置信度
    │   └─ CLAHE enhance                 └─ dt_polys: 检测多边形
    └─ 解析 → [TextBox, ...]
```

### 4.4 EasyOCR 备选引擎

```
EasyOcrEngine.__init__(config)      →    easyocr.Reader(languages, model_storage_directory)
EasyOcrEngine.process(img)          →    reader.readtext(img)
    ├─ _preprocess_image()               → [(bbox, text, confidence), ...]
    └─ 解析 → [TextBox, ...]
```

---

## 5. 720p 图像下采样

```
原始帧 (e.g. 1920×1080)
  ↓
max(w,h) > 720 ?
  ├─ YES → scale = 720/max(w,h)   # e.g. 0.375
  │        ocr_frame = cv2.resize(frame, 720×405)
  │        OCR.process(ocr_frame)
  │        boxes.points *= 1/scale  # 坐标还原
  └─ NO  → 直接 OCR
  ↓
overlay 使用原始坐标放置译文
```

配置: `pipeline.downscale_max_size: 720` (0 = 不限制)

---

## 6. 翻译 HTTP API 协议

```
POST http://{url}/v1/chat/completions
{
  "messages": [
    {"role": "system", "content": "You are a professional translator..."},
    {"role": "user", "content": "将以下文本翻译为中文...\n\n{text}"}
  ],
  "temperature": 0.7, "n_predict": 512, "stream": false
}
```

---

## 7. 覆盖层防污染机制

Windows 10 2004+ `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` 使覆盖窗口对 DXGI 不可见。

渲染: UpdateLayeredWindow + 32-bit per-pixel alpha 位图 (GDI+)。

**64-bit 兼容**: ctypes Win32 API 函数设置了正确的 argtypes (wintypes.HDC 等)，避免 64-bit 句柄溢出。

---

## 8. i18n 国际化

```
LocaleManager (单例)
├─ lang: "en" | "zh"
├─ toggle() → 切换语言 + 通知订阅者
├─ tr(key, **kwargs) → 翻译字符串
└─ subscribe(cb) / unsubscribe(cb)

MainWindow 订阅 LocaleManager
├─ _on_language_changed() → _refresh_ui_texts()
└─ 刷新所有控件: 标题/按钮/标签/复选框/静态框/提示
```

字符串定义在 `i18n/strings.py`，支持 `{name}` 插值。

---

## 9. 部署结构

```
screen_translate/
├── main.py                     # 入口
├── config.yaml                 # 用户可编辑配置
├── requirements.txt            # pip依赖
├── test_e2e.py                 # 完整流水线测试
├── test_focused.py             # OCR切换+覆盖层+下采样测试
├── PP-OCRv5_mobile_det_infer/  # 本地检测模型
├── PP-OCRv5_mobile_rec_infer/  # 本地识别模型
├── PP-LCNet_x1_0_doc_ori/      # 文档方向分类 (自动发现)
├── PP-LCNet_x1_0_textline_ori/ # 文本行方向分类 (自动发现)
├── UVDoc/                      # 文档畸变矫正 (自动发现)
├── easyocr_models/             # EasyOCR 本地模型
├── src/
│   └── python/
│       ├── capture/            # 采集模块
│       ├── ocr/                # OCR模块 (双引擎)
│       ├── translator/         # 翻译模块
│       ├── overlay/            # 覆盖层模块
│       ├── gui/                # GUI模块
│       ├── logger/             # 日志模块
│       ├── pipeline/           # 流水线调度
│       ├── config/             # 配置解析
│       └── i18n/               # 国际化
├── logs/                       # 运行日志
└── build_windows.bat           # 启动脚本
```

---

## 10. 性能目标

| 阶段 | 目标耗时 | 实测 (1080p→720p, CPU) |
|------|---------|------------------------|
| Capture | < 50ms | ~30ms |
| OCR (PaddleOCR) | < 5000ms | ~13,000ms (含 JIT) |
| OCR (EasyOCR) | < 20000ms | ~21,000ms |
| Translate | < 3000ms | ~200ms (单条) / ~2000ms (批量21条) |
| Overlay | < 50ms | ~10ms |
| **总计 (含翻译)** | **< 25000ms** | **~15,000ms** |
