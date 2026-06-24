# Screen Translate

> 实时屏幕翻译工具 — 截图 → OCR 识别 → 翻译 → 覆盖显示，全流程自动化

基于 PaddleOCR / EasyOCR 进行光学字符识别，llama.cpp 提供本地大模型翻译，wxPython 构建桌面 GUI。支持双引擎 OCR、实时与单次翻译、差异检测跳过、中英文 UI 切换。

---

## 功能特性

- **实时翻译** — 周期性捕获屏幕/摄像头帧，自动 OCR + 翻译 + 覆盖
- **单次翻译** — 支持快捷键一键触发单帧翻译，无需启动实时流水线
- **双 OCR 引擎** — PaddleOCR (PP-OCRv5_mobile) + EasyOCR (CRAFT)，运行时热切换
- **本地大模型翻译** — 通过 llama.cpp HTTP API 调用本地 LLM 翻译
- **差异检测** — 帧内容无变化时自动跳过 OCR/翻译，降低 CPU 负载
- **720p 缩放** — 可选将长边缩放至 720px 后再 OCR，提升速度
- **图像预处理** — 深色背景自动反色、高斯去噪、CLAHE 对比度增强
- **覆盖层防污染** — `WDA_EXCLUDEFROMCAPTURE` 使覆盖层对 DXGI 捕获不可见
- **i18n 国际化** — 中英文 UI 一键切换
- **系统托盘** — 最小化到托盘，支持快捷键全局操控
- **离线运行** — 所有模型文件本地存储，无需联网

---

## 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| **GUI 框架** | [wxPython 4.2.5](https://wxpython.org/) + wxWidgets 3.2.9 | 跨平台桌面界面，现代扁平风格 |
| **OCR 引擎** | [PaddleOCR 2.7+](https://github.com/PaddlePaddle/PaddleOCR) | 默认引擎，PP-OCRv5_mobile 本地模型 |
| **OCR 备选** | [EasyOCR](https://github.com/JaidedAI/EasyOCR) | 备选引擎，CRAFT 检测 + CRNN 识别 |
| **翻译后端** | [llama.cpp](https://github.com/ggerganov/llama.cpp) | 本地大模型 HTTP API，支持任意 GGUF 模型 |
| **图像处理** | OpenCV, NumPy, Pillow, scikit-image | 帧采集、预处理、颜色转换 |
| **配置系统** | YAML + Python dataclass | 类型安全配置，自动验证与路径解析 |
| **构建打包** | PyInstaller | 一键打包为独立 .exe |

---

## 架构

```
Screen Translate
├── main.py                         # 应用入口，DPI 初始化，启动 wx.App
└── src/python/
    ├── config/settings.py          # YAML 配置加载 → AppConfig dataclass
    ├── capture/capture.py          # 图像采集层 (DirectShow 摄像头 / 屏幕截图)
    ├── ocr/
    │   ├── paddle_ocr_engine.py    # PaddleOCR 封装 (PP-OCRv5_mobile 本地模型)
    │   └── easy_ocr_engine.py      # EasyOCR 封装 (CRAFT 检测 + 英文识别)
    ├── translator/translator.py    # llama.cpp /v1/chat/completions HTTP 翻译
    ├── overlay/overlay.py          # wxPython 透明覆盖窗口 (per-pixel alpha + WDA)
    ├── pipeline/pipeline.py        # 核心流水线调度器 (采集→OCR→翻译→覆盖)
    ├── gui/main_window.py          # 主控制面板 (选项卡布局 + 自定义 ToggleSwitch)
    ├── i18n/
    │   ├── __init__.py             # LocaleManager 单例，回调通知机制
    │   └── strings.py              # 全部 UI 文本 (中/英文)
    └── logger/cycle_logger.py      # 周期日志记录 (JSONL 格式)
```

### 数据流

```
┌──────────┐    ┌───────────┐    ┌────────────┐    ┌──────────┐    ┌──────────┐
│  Capture  │───→│    OCR    │───→│ Translator  │───→│ Overlay  │───→│  Screen  │
│  (帧采集)  │    │ (文本识别) │    │  (翻译)     │    │ (覆盖层)  │    │  (显示)  │
└──────────┘    └───────────┘    └────────────┘    └──────────┘    └──────────┘
       │                │                │                │
       ▼                ▼                ▼                ▼
  DirectShow     PP-OCRv5_mobile   llama.cpp HTTP    Per-pixel Alpha
  摄像头帧        EasyOCR (备选)    本地 LLM          WDA_EXCLUDED
```

### 线程模型

```
Main Thread (wx.App.MainLoop)
  ├── GUI 渲染 & 事件处理
  └── wx.CallAfter() 接收后台线程结果

Pipeline Thread (daemon)
  ├── 周期定时器 (cycle_interval)
  ├── Capture → OCR → Translator → Overlay
  └── 通过回调将结果推送到 GUI 线程
```

---

## 模型文件

### 本地模型清单

| 模型 | 目录 | 大小 | 用途 |
|---|---|---|---|
| PP-OCRv5_mobile_det | `PP-OCRv5_mobile_det_infer/` | ~4.7 MB | 文本检测 |
| PP-OCRv5_mobile_rec | `PP-OCRv5_mobile_rec_infer/` | ~16.5 MB | 文本识别 |
| PP-LCNet_x1_0_textline_ori | `PP-LCNet_x1_0_textline_ori/` | ~0.96 MB | 文本行方向分类 |
| PP-LCNet_x1_0_doc_ori | `PP-LCNet_x1_0_doc_ori/` | ~7 MB | 文档方向分类 |
| UVDoc | `UVDoc/` | — | 文档畸变矫正 |
| EasyOCR (备选) | `easyocr_models/` | ~93 MB | CRAFT 检测 + 英文识别 |

所有模型均本地存储于项目目录，无需联网下载。PaddleX 缓存目录通过 `PADDLE_PDX_CACHE_HOME` 环境变量重定向到 `.paddlex_cache/`，不会写入用户文件夹。

### 翻译模型 (llama.cpp)

翻译需要单独启动 llama.cpp server。推荐使用 Qwen2.5 系列 GGUF 模型：

```bash
# 下载模型（示例）
# https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF

# 启动 llama.cpp server
llama-server -m models/qwen2.5-7b-instruct-q4_k_m.gguf --port 8080
```

---

## 快速开始

### 前置条件

- Python 3.12+
- llama.cpp server (翻译后端)
- Windows 10 2004+ (WDA_EXCLUDEFROMCAPTURE 需要)

### 安装

```bash
# 1. 克隆仓库
git clone <repo-url>
cd screen_translate

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. 安装依赖
pip install -r requirements.txt

# 4. 下载模型文件（需要单独获取，见下方说明）
# 将 PP-OCRv5_mobile_det_infer/、PP-OCRv5_mobile_rec_infer/ 等放入项目根目录
# 将 EasyOCR 模型 (craft_mlt_25k.pth, english_g2.pth) 放入 easyocr_models/

# 5. 启动 llama.cpp server（翻译后端）
llama-server -m <your-model>.gguf --port 8080

# 6. 运行
python main.py
```

### 配置

编辑 `config.yaml` 进行配置。所有相对路径相对于项目根目录。详细说明见 [CONFIG.md](CONFIG.md)。

关键配置项：

```yaml
ocr:
  engine: "paddle"                     # paddle 或 easyocr
  det_model_dir: "./PP-OCRv5_mobile_det_infer"
  rec_model_dir: "./PP-OCRv5_mobile_rec_infer"

translator:
  backend: "llama"
  llama:
    url: "http://127.0.0.1:8080"

source_lang: "en"
target_lang: "zh"
```

### 快捷键

| 快捷键 | 功能 |
|---|---|
| `F8` | 单次翻译 |
| `F9` | 暂停/继续 |
| `F10` | 退出 |

快捷键可在 GUI 的 Hotkeys 选项卡中自定义。

---

## 项目结构

```
screen_translate/
├── main.py                              # 应用入口
├── config.yaml                          # 用户配置文件
├── requirements.txt                     # Python 依赖
├── package.py                           # PyInstaller 打包脚本
├── CONFIG.md                            # 配置参考文档
├── .gitignore
│
├── src/python/
│   ├── capture/capture.py               # 图像采集 (DirectShow)
│   ├── config/settings.py               # 配置数据模型 + 加载器
│   ├── gui/main_window.py               # 主窗口 (选项卡片 + ToggleSwitch + 状态栏)
│   ├── i18n/                            # 国际化 (中/英文)
│   │   ├── __init__.py                  # LocaleManager
│   │   └── strings.py                  # UI 文本定义
│   ├── logger/cycle_logger.py           # JSONL 周期日志
│   ├── ocr/
│   │   ├── paddle_ocr_engine.py         # PaddleOCR 引擎
│   │   └── easy_ocr_engine.py           # EasyOCR 引擎 (备选)
│   ├── overlay/overlay.py               # 透明覆盖窗口 (UpdateLayeredWindow)
│   ├── pipeline/pipeline.py             # 翻译流水线调度
│   └── translator/translator.py         # llama.cpp HTTP 客户端
│
├── PP-OCRv5_mobile_det_infer/           # 检测模型 (需单独下载)
├── PP-OCRv5_mobile_rec_infer/           # 识别模型 (需单独下载)
├── PP-LCNet_x1_0_doc_ori/               # 文档方向模型 (需单独下载)
├── PP-LCNet_x1_0_textline_ori/          # 文本行方向模型 (需单独下载)
├── UVDoc/                               # 畸变矫正模型 (需单独下载)
└── easyocr_models/                      # EasyOCR 模型 (需单独下载)
    ├── craft_mlt_25k.pth
    └── english_g2.pth
```

---

## 打包

使用 PyInstaller 打包为独立 .exe（无需 Python 环境）：

```bash
python package.py --name ScreenTranslate
# 输出: dist/ScreenTranslate.exe
```

打包时自动收集 PaddleOCR / Paddle / EasyOCR 模型资源文件。

---

## 开发工具脚本

| 脚本 | 用途 |
|---|---|
| `test_ocr_png.py` | 测试 OCR 引擎对单张图片的识别效果 |
| `test_e2e.py` | 端到端测试 (capture → OCR → 输出) |
| `test_focused.py` | 针对性调试脚本 |
| `debug_ocr.py` | OCR 调试辅助 |
| `count_chars.py` | 字符统计工具 |

