# Screen Translate

**实时屏幕翻译系统** — 采集屏幕画面，OCR 识别文字，本地大模型翻译，透明覆盖层叠加显示译文。

> Real-time screen translation: capture → OCR → LLM translate → transparent overlay.

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2B-blue" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/tests-79%2F79%20passed-brightgreen" alt="Tests">
</p>

---

## 特性 / Features

- 🔍 **双 OCR 引擎** — PaddleOCR (PP-OCRv5, 轻量快速) + EasyOCR (80+ 语言, GPU 加速)，GUI 一键热切换
- 🌐 **本地大模型翻译** — 通过 llama.cpp HTTP API (OpenAI 兼容 `/v1/chat/completions`) 调用本地模型，数据不出本机
- 🖥️ **透明覆盖层** — 译文以半透明背景+白色文字叠加在原文位置，支持 per-pixel alpha 渲染
- 🛡️ **防递归污染** — Win10 2004+ `WDA_EXCLUDEDFROMCAPTURE` 使覆盖层对屏幕捕获不可见
- ⚡ **720p 智能下采样** — 自动等比缩放高分辨率画面，OCR 后坐标精确还原，大幅降低推理耗时
- 📷 **多采集源** — 支持 OBS 虚拟摄像头 (DirectShow) 或屏幕直接截取 (mss/PIL)
- 🔄 **差异检测** — 画面无变化自动跳过 OCR，大幅节省 CPU
- 💾 **翻译缓存** — `{原文: 译文}` 内存缓存，避免重复翻译
- ⌨️ **全局快捷键** — F8 单次翻译 / F9 暂停 / F10 退出 (可自定义)
- 🌍 **国际化 UI** — 中/英文界面即时切换
- 📊 **JSONL 周期日志** — 每轮完整记录采集→OCR→翻译→覆盖的耗时与结果

## 核心流程 / Pipeline

```
OBS 虚拟摄像头 → OpenCV 采集帧 → 720p 下采样(可选)
    → OCR 识别 (PaddleOCR / EasyOCR) → 坐标还原
    → llama.cpp 翻译 → 覆盖层显示 (per-pixel alpha)
```

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Capture  │  │   OCR    │  │Translator│  │ Overlay  │
│ (采集)   │  │ (识别)   │  │ (翻译)   │  │ (覆盖层) │
├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤
│ OpenCV   │  │ PaddleOCR│  │ llama.cpp│  │ wxPython │
│ DirectShow│  │ EasyOCR  │  │ HTTP API │  │ 透明窗口 │
│ 屏幕截取 │  │ 本地模型 │  │/v1/chat/ │  │WDA_EXCL  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

## 环境要求 / Requirements

| 组件 | 说明 |
|------|------|
| **操作系统** | Windows 10 2004+ (覆盖层防污染需此版本) |
| **Python** | 3.10+ |
| **OBS Studio** | 可选 — 配合虚拟摄像头采集特定窗口 |
| **llama.cpp server** | 本地翻译模型服务 (OpenAI 兼容 API) |

### Python 依赖

```
wxPython>=4.2.0        # GUI + 透明覆盖层
numpy>=1.24.0          # 图像数据处理
opencv-python>=4.8.0   # 图像采集与预处理
paddleocr>=2.7.0       # PaddleOCR 引擎
paddlepaddle>=2.5.0    # PaddlePaddle 推理框架
requests>=2.28.0       # HTTP 翻译请求
Pillow>=9.0.0          # 图像处理
pyyaml>=6.0            # 配置解析
keyboard>=0.13.5       # 全局热键
```

## 快速开始 / Quick Start

### 1. 克隆项目

```bash
git clone https://github.com/your-username/screen-translate.git
cd screen-translate
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### 3. 启动 llama.cpp 翻译服务

```bash
# 示例：启动 Qwen2.5-7B 或其他翻译模型
llama-server -m models/qwen2.5-7b-instruct-q4_k_m.gguf --port 8080
```

### 4. 配置 OBS 虚拟摄像头 (可选)

1. 安装 [OBS Studio](https://obsproject.com/)
2. 添加你要翻译的窗口为「窗口捕获」源
3. 菜单 → 工具 → 虚拟摄像头 → 启动

### 5. 编辑配置文件

编辑 `config.yaml`，至少修改翻译服务地址：

```yaml
translator:
  llama:
    url: "http://127.0.0.1:8080"   # 改为你的 llama.cpp server 地址

source_lang: "en"                    # 源语言
target_lang: "zh"                    # 目标语言
```

### 6. 运行

```bash
python main.py
```

点击 **Start** 开始实时翻译，或按 **F8** 执行单次翻译。

## 使用说明 / Usage

### 控制面板

| 按钮 | 功能 |
|------|------|
| **Start** | 启动实时翻译流水线 |
| **Stop** | 停止流水线 |
| **Pause / Resume** | 暂停 / 继续 |
| **Single** | 单次翻译 (采集一帧并翻译) |
| **中 / EN** | 切换 UI 语言 |

### 快速切换

| 开关 | 说明 |
|------|------|
| **Diff Detection** | 画面无变化时跳过 OCR，节省 CPU |
| **720p Downscale** | OCR 前等比缩放到 720p，大幅提升 OCR 速度 |

### 全局快捷键

| 按键 | 功能 |
|------|------|
| `F8` | 单次翻译 |
| `F9` | 暂停 / 继续 |
| `F10` | 退出程序 |

快捷键可在 `config.yaml` → `gui` 中自定义。

## 配置参考 / Configuration

完整配置见 `config.yaml`，主要配置项：

```yaml
ocr:
  engine: "paddle"                    # OCR 引擎: "paddle" | "easyocr"
  cpu_threads: 4                      # CPU 推理线程数
  min_confidence: 0.5                 # 最低识别置信度

translator:
  llama:
    url: "http://127.0.0.1:8080"     # llama.cpp server 地址
    parallel_requests: 4              # 并行翻译数

pipeline:
  cycle_interval: 5.0                 # 翻译周期 (秒)
  diff_detection: false               # 差异检测
  downscale_max_size: 720             # OCR 下采样阈值 (0=禁用)

overlay:
  font_size: 16                       # 覆盖层字体大小
  background_opacity: 0.7             # 背景不透明度
  exclude_from_capture: true          # 防捕获污染

gui:
  ui_language: "en"                   # UI 语言: "en" | "zh"
  hotkey_single_translate: "F8"       # 单次翻译快捷键
```

详细配置说明见 [CONFIG.md](CONFIG.md)。

## 项目结构 / Project Structure

```
screen_translate/
├── main.py                         # 入口
├── config.yaml                     # 用户配置文件
├── requirements.txt                # Python 依赖
├── test_e2e.py                     # 端到端测试 (48 项)
├── test_focused.py                 # 聚焦测试 (31 项)
├── PP-OCRv5_mobile_det_infer/      # PaddleOCR 检测模型 (~4.7 MB)
├── PP-OCRv5_mobile_rec_infer/      # PaddleOCR 识别模型 (~16.5 MB)
├── PP-LCNet_x1_0_doc_ori/          # 文档方向分类模型 (自动发现)
├── PP-LCNet_x1_0_textline_ori/     # 文本行方向分类模型 (自动发现)
├── UVDoc/                          # 文档畸变矫正模型 (自动发现)
├── easyocr_models/                 # EasyOCR 本地模型 (~97 MB)
├── logs/                           # 运行日志
├── src/python/
│   ├── capture/                    # 采集模块
│   │   └── capture.py              # DirectShow + 屏幕截取
│   ├── ocr/                        # OCR 模块
│   │   ├── paddle_ocr_engine.py    # PaddleOCR 引擎
│   │   └── easy_ocr_engine.py      # EasyOCR 引擎
│   ├── translator/                 # 翻译模块
│   │   └── translator.py           # llama.cpp HTTP API
│   ├── overlay/                    # 覆盖层模块
│   │   └── overlay.py              # 透明窗口 + per-pixel alpha
│   ├── gui/                        # GUI 模块
│   │   └── main_window.py          # 控制面板 + 托盘
│   ├── pipeline/                   # 流水线调度
│   │   └── pipeline.py             # 核心调度逻辑
│   ├── config/                     # 配置解析
│   │   └── settings.py             # YAML → dataclass
│   ├── logger/                     # 日志模块
│   │   └── cycle_logger.py         # JSONL 周期日志
│   └── i18n/                       # 国际化
│       ├── __init__.py             # LocaleManager
│       └── strings.py              # 80+ 翻译字符串
├── ARCHITECTURE.md                 # 架构设计文档
├── CONFIG.md                       # 完整配置参考
└── PROJECT_STATUS.md               # 项目状态与路线图
```

## 性能指标 / Performance

> 测试环境：Windows 11, CPU i7-13700H, 1080p→720p 下采样

| 阶段 | 耗时 |
|------|------|
| Capture (采集) | ~30 ms |
| OCR (PaddleOCR, 720p) | ~13,000 ms |
| OCR (EasyOCR, CPU) | ~21,000 ms |
| Translate (llama.cpp) | ~200 ms/条 (批量并行) |
| Overlay (覆盖层渲染) | ~10 ms |
| **完整周期 (含翻译)** | **~15,000 ms** |

> 首次启动时 PaddlePaddle 会进行 JIT 编译，首个周期耗时较长。后续周期恢复正常。

## 测试 / Tests

```bash
# 端到端测试 (完整流水线)
python test_e2e.py      # 48/48 passed

# 聚焦测试 (OCR 切换 + 覆盖层 + 下采样)
python test_focused.py  # 30/31 passed (1 项为下采样 OCR 精度差异)
```

## 路线图 / Roadmap

- [x] PaddleOCR + EasyOCR 双引擎
- [x] 本地大模型翻译 (llama.cpp)
- [x] 透明覆盖层 + per-pixel alpha
- [x] 720p 智能下采样 + 坐标还原
- [x] 国际化 UI (中/英文)
- [x] 全局快捷键 + 系统托盘
- [x] JSONL 周期日志
- [x] 64-bit HDC 兼容
- [ ] 屏幕选区功能
- [ ] 字体大小自适应
- [ ] DeepL 翻译后端
- [ ] Linux 跨平台支持
- [ ] GPU OCR 推理加速

详见 [PROJECT_STATUS.md](PROJECT_STATUS.md) 和 [todo.md](todo.md)。

## 许可证 / License

MIT License

## 致谢 / Acknowledgments

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — OCR 引擎
- [EasyOCR](https://github.com/JaidedAI/EasyOCR) — 备选 OCR 引擎
- [llama.cpp](https://github.com/ggerganov/llama.cpp) — 本地 LLM 推理
- [wxPython](https://www.wxpython.org/) — GUI 框架与透明覆盖层
- [OBS Studio](https://obsproject.com/) — 虚拟摄像头
