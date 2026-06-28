# Screen Translate

> 实时屏幕翻译工具 — 截图 → OCR 识别 → 翻译 → 覆盖显示，全流程自动化

基于 **PP-OCRv6 ONNX Runtime** 进行光学字符识别，llama.cpp 提供本地大模型翻译，wxPython 构建桌面 GUI。支持实时与单次翻译、划屏翻译、差异检测跳过、中英文 UI 切换。

---

## 功能特性

- **实时翻译** — 周期性捕获屏幕/摄像头帧，自动 OCR + 翻译 + 覆盖
- **单次翻译** — 支持快捷键一键触发单帧翻译，无需启动实时流水线
- **划屏翻译** — 选择屏幕区域，对该区域进行 OCR + 翻译 + 原位覆盖
- **OCR 引擎** — PP-OCRv6 ONNX Runtime 推理，检测+识别全流程加速
- **DirectML GPU 加速** — 可选启用 ONNX DirectML GPU 推理 (Windows 10+)，显著提升 OCR 速度
- **本地大模型翻译** — 通过 llama.cpp HTTP API 调用本地 LLM 翻译
- **差异检测** — 帧内容无变化时自动跳过 OCR/翻译，降低 CPU 负载
- **720p 缩放** — 可选（默认关闭），将长边缩放至 720px 后再 OCR，平衡速度与精度
- **覆盖层防污染** — `WDA_EXCLUDEFROMCAPTURE` 使覆盖层对 DXGI 捕获不可见
- **覆盖层按需显示** — 仅在翻译内容到达时显示覆盖窗口，空时自动隐藏，避免干扰任务栏
- **i18n 国际化** — 中英文 UI 一键切换
- **系统托盘** — 最小化到托盘，支持快捷键全局操控
- **离线运行** — 所有模型文件本地存储，无需联网

---

## 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| **GUI 框架** | [wxPython 4.2+](https://wxpython.org/) | 跨平台桌面界面，现代扁平风格 |
| **OCR 引擎** | PP-OCRv6 + ONNX Runtime | 端到端文本检测+识别，可选 DirectML GPU 加速 |
| **GPU 加速** | ONNX DirectML (`onnxruntime-directml`) | 可选 GPU 推理加速，需 `use_directml: true` |
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
    │   ├── __init__.py             # OCR 模块入口 + 工厂函数
    │   ├── types.py                # TextBox / OcrOutput 数据类型
    │   ├── directml.py             # ONNX DirectML 辅助模块 (GPU 加速)
    │   └── ppocr_onnx_engine.py    # PP-OCRv6 ONNX Runtime 引擎
    ├── translator/translator.py    # llama.cpp /v1/chat/completions HTTP 翻译
    ├── overlay/overlay.py          # wxPython 透明覆盖窗口 (按需显示，per-pixel alpha + WDA)
    ├── pipeline/pipeline.py        # 核心流水线调度器 (采集→OCR→翻译→覆盖)
    ├── gui/
    │   ├── main_window.py          # 主控制面板 (选项卡布局 + 自定义 ToggleSwitch + 托盘图标)
    │   └── region_selector.py      # 划屏翻译区域选择器
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
  DirectShow      PP-OCRv6 ONNX     llama.cpp HTTP    Per-pixel Alpha
  摄像头帧         Runtime 推理      本地 LLM          WDA_EXCLUDED
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

### OCR 模型 (ONNX)

| 变体 | 检测模型 | 识别模型 | 大小 (检测+识别) | 说明 |
|---|---|---|---|---|
| **tiny** | `PP-OCRv6_tiny_det_onnx/` | `PP-OCRv6_tiny_rec_onnx/` | ~1.7 MB + ~4.3 MB | 轻量快速，适合低配设备 |
| **small** | `PP-OCRv6_small_det_onnx/` | `PP-OCRv6_small_rec_onnx/` | ~9.4 MB + ~20.2 MB | 高精度（默认） |
| **medium** | `PP-OCRv6_medium_det_onnx/` | `PP-OCRv6_medium_rec_onnx/` | — | 精度/速度平衡（需自行下载） |

ONNX 模型可直接使用 ONNX Runtime 推理，无需安装 PaddlePaddle 框架。

**切换模型**：编辑 `config.yaml`，修改 `det_model_dir` 和 `rec_model_dir` 为对应目录路径即可：

```yaml
# 使用 tiny 轻量模型
ocr:
  det_model_dir: "./PP-OCRv6_tiny_det_onnx"
  rec_model_dir: "./PP-OCRv6_tiny_rec_onnx"

# 使用 small 高精度模型
ocr:
  det_model_dir: "./PP-OCRv6_small_det_onnx"
  rec_model_dir: "./PP-OCRv6_small_rec_onnx"
```

重启应用后生效。可在 GUI 的 OCR 选项卡中查看当前加载的模型名称。

### 旧版模型 (PaddleOCR / PaddleX)

| 模型 | 目录 | 说明 |
|---|---|---|
| PP-OCRv5_mobile_det | `PP-OCRv5_mobile_det_infer/` | PaddleOCR v5 检测（兼容旧版） |
| PP-OCRv5_mobile_rec | `PP-OCRv5_mobile_rec_infer/` | PaddleOCR v5 识别（兼容旧版） |
| PP-LCNet 系列 | `PP-LCNet_*/` | 方向分类/文本行方向 |
| UVDoc | `UVDoc/` | 文档畸变矫正 |
| EasyOCR (备选) | `easyocr_models/` | CRAFT 检测 + CRNN 识别（备选） |

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
- ONNX Runtime（依赖已包含在 requirements.txt 中）
- llama.cpp server (翻译后端)
- Windows 10 2004+ (WDA_EXCLUDEFROMCAPTURE 需要)
- （可选）DirectML GPU 加速：需 Windows 10+ 且 GPU 支持 DirectX 12

### 安装

```bash
# 1. 克隆仓库
git clone <repo-url>
cd screen_translate

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate    # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. （可选）安装 DirectML GPU 加速支持
# pip install onnxruntime-directml

# 5. 下载模型文件
# 将 PP-OCRv6_small_det_onnx/、PP-OCRv6_small_rec_onnx/ 放入项目根目录

# 6. 启动 llama.cpp server（翻译后端）
llama-server -m <your-model>.gguf --port 8080

# 7. 运行
python main.py
```

### 配置

编辑 `config.yaml` 进行配置。所有相对路径相对于项目根目录。

关键配置项：

```yaml
ocr:
  engine: "onnx"                          # ONNX Runtime 引擎
  det_model_dir: "./PP-OCRv6_small_det_onnx"  # 可换为 tiny_det_onnx
  rec_model_dir: "./PP-OCRv6_small_rec_onnx"  # 可换为 tiny_rec_onnx
  use_directml: false                     # 启用 DirectML GPU 加速 (需 pip install onnxruntime-directml)

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
├── .gitignore
│
├── src/python/
│   ├── capture/capture.py               # 图像采集 (DirectShow)
│   ├── config/settings.py               # 配置数据模型 + 加载器
│   ├── gui/
│   │   ├── main_window.py               # 主窗口 (选项卡片 + ToggleSwitch + 状态栏 + 托盘)
│   │   └── region_selector.py           # 划屏翻译区域选择窗口
│   ├── i18n/                            # 国际化 (中/英文)
│   │   ├── __init__.py                  # LocaleManager
│   │   └── strings.py                   # UI 文本定义
│   ├── logger/cycle_logger.py           # JSONL 周期日志
│   ├── ocr/
│   │   ├── __init__.py                  # OCR 模块入口 + 工厂函数
│   │   ├── types.py                     # TextBox / OcrOutput 数据类型
│   │   ├── directml.py                  # ONNX DirectML 辅助模块
│   │   └── ppocr_onnx_engine.py         # PP-OCRv6 ONNX Runtime 引擎
│   ├── overlay/overlay.py               # 透明覆盖窗口 (按需显示，UpdateLayeredWindow)
│   ├── pipeline/pipeline.py             # 翻译流水线调度
│   └── translator/translator.py         # llama.cpp HTTP 客户端
│
├── PP-OCRv6_small_det_onnx/              # OCRv6 检测模型 (ONNX)
├── PP-OCRv6_small_rec_onnx/              # OCRv6 识别模型 (ONNX)
├── config.yaml                          # 用户配置
└── README.md
```

---

## 打包

使用 PyInstaller 打包为独立 .exe（无需 Python 环境）：

```bash
# 1. 安装 PyInstaller
pip install pyinstaller

# 2. 运行打包脚本（自动收集依赖、复制模型文件）
python package.py

# 输出: dist/ScreenTranslate/ScreenTranslate.exe
```

打包完成后，输出目录结构：

```
dist/ScreenTranslate/
├── ScreenTranslate.exe          # 主程序
├── config.yaml                  # 配置文件（可编辑）
├── PP-OCRv6_small_det_onnx/     # 检测模型
├── PP-OCRv6_small_rec_onnx/     # 识别模型
├── PP-OCRv6_tiny_det_onnx/      # 轻量检测模型（可选）
├── PP-OCRv6_tiny_rec_onnx/      # 轻量识别模型（可选）
└── ...  (运行时库文件)
```

**注意事项：**
- 模型文件不嵌入 exe 内部，而是复制到 exe 同目录，方便切换模型变体
- 可直接编辑 `dist/ScreenTranslate/config.yaml` 切换模型或修改参数
- 如需重新打包，运行 `python package.py` 即可

### 手动打包（不依赖 package.py）

如需要自定义打包参数，也可直接调用 PyInstaller：

```bash
pyinstaller --noconfirm --clean --name ScreenTranslate --noconsole ^
  --add-data "config.yaml;." ^
  --hidden-import yaml --hidden-import onnxruntime --hidden-import pyclipper ^
  --hidden-import keyboard --hidden-import PIL --hidden-import PIL.ImageGrab ^
  main.py
```

---

## 常见问题

### 任务栏消失

**原因**：覆盖层窗口 (`OverlayWindow`) 在全屏置顶状态下持续显示，Windows 误认为有全屏应用在运行，从而自动隐藏任务栏。

**解决方案**：当前版本已修复 — 覆盖层仅在翻译内容到达时才显示，内容清空后自动隐藏。如仍遇到问题，请检查是否开启了 Windows "自动隐藏任务栏" 设置。

### 翻译速度慢

- 启用 DirectML GPU 加速（`config.yaml` 中设置 `use_directml: true`，需安装 `onnxruntime-directml`）
- 启用 720p 缩放（控制面板点击 "Downscale: OFF" 切换为 "Downscale: 720p"）
- 使用更小的 LLM 模型（如 Qwen2.5-1.5B-Instruct）
- 调整 `cycle_interval` 增加采集间隔

### DirectML GPU 加速不生效

- 确保已安装 `onnxruntime-directml`：`pip install onnxruntime-directml`
- 确认显卡支持 DirectX 12 (Windows 10+)
- 检查启动日志中 `[DirectML]` 输出：应显示 "DmlExecutionProvider is available"
- 如果仍在使用 CPU，日志会显示 "DML requested but unavailable — falling back to CPU"
- 注意：DirectML 配置项 `use_directml` 仅在 `config.yaml` 中设置，不在 GUI 中显示

---

## 开发工具脚本

| 脚本 | 用途 |
|---|---|
| `test_ocr_png.py` | 测试 OCR 引擎对单张图片的识别效果 |
| `test_e2e.py` | 端到端测试 (capture → OCR → 输出) |
| `test_focused.py` | 针对性调试脚本 |
| `debug_ocr.py` | OCR 调试辅助 |
| `count_chars.py` | 字符统计工具 |
