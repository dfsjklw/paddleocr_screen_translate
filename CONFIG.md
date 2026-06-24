# Screen Translate — 配置参考文档

> 更新日期：2026-06-24

本文档覆盖 `config.yaml` 全部配置项的说明、默认值、取值范围及注意事项。

---

## 目录

1. [配置文件位置](#1-配置文件位置)
2. [OCR 模型配置（本地 PP-OCRv5_mobile）](#2-ocr-模型配置)
3. [Capture 采集配置](#3-capture-采集配置)
4. [OCR 识别参数配置](#4-ocr-识别参数配置)
5. [Translator 翻译配置](#5-translator-翻译配置)
6. [Overlay 覆盖层配置](#6-overlay-覆盖层配置)
7. [Pipeline 流水线配置](#7-pipeline-流水线配置)
8. [GUI 配置](#8-gui-配置)
9. [语言配置](#9-语言配置)
10. [Logging 日志配置](#10-logging-日志配置)
11. [完整配置示例](#11-完整配置示例)

---

## 1. 配置文件位置

| 项目 | 说明 |
|------|------|
| **路径** | `<项目根目录>/config.yaml` |
| **格式** | YAML 1.1 |
| **编码** | UTF-8 |
| **解析** | `src/python/config/settings.py` → `AppConfig` dataclass |
| **路径解析** | 所有相对路径相对于 `config.yaml` 所在目录（项目根目录） |

配置加载优先级：
1. 如果 `config.yaml` 存在 → 读取并合并到默认值
2. 如果 `config.yaml` 不存在 → 使用全部默认值（并打印警告）

---

## 2. OCR 模型配置

### 2.1 本地模型目录（核心配置）

这是最重要的配置项 — 项目使用 **PP-OCRv5_mobile 本地模型**，模型文件存放在项目目录内，无需联网下载。

```yaml
ocr:
  # [必填] PP-OCRv5 检测模型目录
  # 目录内应包含: inference.yml + inference.json + inference.pdiparams
  det_model_dir: "./PP-OCRv5_mobile_det_infer"

  # [必填] PP-OCRv5 识别模型目录
  # 目录内应包含: inference.yml + inference.json + inference.pdiparams
  rec_model_dir: "./PP-OCRv5_mobile_rec_infer"
```

### 2.2 模型目录结构

```
PP-OCRv5_mobile_det_infer/        # 检测模型 (~4.7 MB)
├── inference.yml                 # 模型配置: model_name='PP-OCRv5_mobile_det'
├── inference.json                # 模型元信息
└── inference.pdiparams           # 模型权重参数

PP-OCRv5_mobile_rec_infer/        # 识别模型 (~16.5 MB)
├── inference.yml                 # 模型配置: model_name='PP-OCRv5_mobile_rec'
├── inference.json                # 模型元信息
└── inference.pdiparams           # 模型权重参数

PP-LCNet_x1_0_textline_ori/       # 文本行方向分类模型 (~0.96 MB)
├── inference.yml                 # 模型配置: model_name='PP-LCNet_x1_0_textline_ori'
├── inference.json                # 模型元信息
├── inference.pdiparams           # 模型权重参数
└── config.json                   # 预处理/后处理配置

PP-LCNet_x1_0_doc_ori/            # 文档方向分类模型 (~7 MB)
├── inference.yml                 # 模型配置: model_name='PP-LCNet_x1_0_doc_ori'
├── inference.json                # 模型元信息
├── inference.pdiparams           # 模型权重参数
└── config.json                   # 预处理/后处理配置

UVDoc/                            # 文档畸变矫正模型
├── inference.yml                 # 模型配置: model_name='UVDoc'
├── inference.json                # 模型元信息
├── inference.pdiparams           # 模型权重参数
└── config.json                   # 预处理/后处理配置

easyocr_models/                   # EasyOCR 备选引擎模型 (~97 MB)
├── craft_mlt_25k.pth             # CRAFT 文本检测模型 (~79 MB)
└── english_g2.pth                # 英文识别模型 (~14 MB)
```

### 2.3 本地模型自动发现

项目中的所有模型均从项目本地目录加载，无需联网下载：

| 引擎 | 模型目录 | 加载方式 |
|------|----------|----------|
| PaddleOCR | `PP-OCRv5_mobile_det_infer/` | `config.yaml` 显式指定 |
| PaddleOCR | `PP-OCRv5_mobile_rec_infer/` | `config.yaml` 显式指定 |
| PaddleX | `PP-LCNet_x1_0_textline_ori/` | PaddleX 自动发现 (cwd) |
| PaddleX | `PP-LCNet_x1_0_doc_ori/` | PaddleX 自动发现 (cwd) |
| PaddleX | `UVDoc/` | PaddleX 自动发现 (cwd) |
| EasyOCR | `easyocr_models/` | `easy_ocr_engine.py` 显式指定 |

**辅助模型说明**：
- **PP-LCNet_x1_0_textline_ori**: 文本行方向分类 (0°/180°)，用于纠正倒置文本行
- **PP-LCNet_x1_0_doc_ori**: 文档方向分类 (0°/90°/180°/270°)，用于纠正文档旋转
- **UVDoc**: 文档畸变矫正，用于纠正拍照/扫描产生的几何变形
- **easyocr_models/**: EasyOCR 备选引擎的 CRAFT 检测 + 英文识别模型

**PaddleX 自动发现机制**：PaddleX 的模型管理器（`official_models.py`）已被修改，在检查默认缓存目录（`~/.paddlex/official_models/`）之前，会**优先搜索当前工作目录**（即项目根目录）下的同名文件夹。因此只要从项目根目录运行程序，上述 PaddleX 模型会自动从本地加载。

也可以通过环境变量 `PADDLE_PDX_LOCAL_MODEL_DIRS` 指定额外的搜索目录（分号分隔，Windows 用 `;`，Linux/Mac 用 `:`）：
```bash
# Windows
set PADDLE_PDX_LOCAL_MODEL_DIRS=C:\models\ocr;D:\backup\models
# Linux/Mac
export PADDLE_PDX_LOCAL_MODEL_DIRS=/home/user/models:/opt/models
```

### 2.4 模型选择原理

代码中通过 `PaddleOCR` 构造函数同时指定 **模型名称** 和 **模型目录** 来加载本地模型：

```python
# src/python/ocr/paddle_ocr_engine.py:115-120
self._ocr = PaddleOCR(
    text_detection_model_name='PP-OCRv5_mobile_det',    # 必须与 inference.yml 中一致
    text_detection_model_dir=det_model_dir,              # 本地绝对路径
    text_recognition_model_name='PP-OCRv5_mobile_rec',   # 必须与 inference.yml 中一致
    text_recognition_model_dir=rec_model_dir,             # 本地绝对路径
    ...
)
```

**重要**：如果不指定 `text_detection_model_name` / `text_recognition_model_name`，PaddleOCR 默认使用 v6 模型名，与本地 v5 模型目录中的 `inference.yml` 冲突，导致 `ValueError: Model name mismatch`。

### 2.5 更换模型

如需更换为其他 PP-OCR 版本的模型（如 v4_mobile、v5_server 等）：

1. 将新模型文件放入项目目录（例如 `PP-OCRv4_mobile_det_infer/`）
2. 修改 `config.yaml` 中的 `det_model_dir` 和 `rec_model_dir`
3. 修改 `paddle_ocr_engine.py` 中 `text_detection_model_name` 和 `text_recognition_model_name` 为对应的模型名称
4. 确保 `inference.yml` 中的 `model_name` 与代码中指定的名称一致

---

## 3. Capture 采集配置

```yaml
capture:
  # 采集后端: "directshow" (摄像头) | "screen" (屏幕直接截取)
  backend: "directshow"

  # DirectShow 模式: 摄像头设备索引 (0=默认摄像头)
  camera_index: 0

  # 采集帧率
  fps: 30

  # screen 模式: 显示器索引 (1=主显示器)
  monitor: 1

  # screen 模式: 截取区域 [x, y, w, h]，null 表示全屏
  region: null
```

| 参数 | 默认值 | 取值范围 | 说明 |
|------|--------|----------|------|
| `backend` | `"directshow"` | `"directshow"` / `"screen"` | OBS虚拟摄像头用 directshow |
| `camera_index` | `0` | 0~N | DirectShow 设备编号 |
| `fps` | `30` | 1~60 | 目标帧率，实际取决于摄像头 |
| `monitor` | `1` | 1~N | 仅在 screen 模式下使用 |
| `region` | `null` | `[x, y, w, h]` 或 `null` | 截取区域，null=全屏 |

---

## 4. OCR 引擎选择 (NEW)

```yaml
ocr:
  # OCR 引擎: "paddle" (PaddleOCR) | "easyocr" (EasyOCR)
  engine: "paddle"

  # EasyOCR 语言列表 (仅 easyocr 模式)
  easyocr_languages:
    - "en"
    # - "ch_sim"
    # - "ja"
```

| 参数 | 默认值 | 取值范围 | 说明 |
|------|--------|----------|------|
| `engine` | `"paddle"` | `"paddle"` / `"easyocr"` | OCR 引擎选择 |
| `easyocr_languages` | `["en"]` | 语言代码列表 | EasyOCR 识别语言，逗号分隔 |

EasyOCR 支持语言代码: `en` (英文), `ch_sim` (简体中文), `ja` (日文), `ko` (韩文), `fr` (法文), `de` (德文) 等 80+ 语言。

GUI 切换引擎后会自动重启流水线以应用新引擎。

---

## 5. OCR 识别参数配置

```yaml
ocr:
  # CPU 推理线程数
  cpu_threads: 4

  # 检测置信度阈值 (DB 后处理)
  det_threshold: 0.3

  # 文本框置信度阈值
  box_threshold: 0.6

  # 最小综合置信度 (低于此值丢弃)
  min_confidence: 0.5

  # 检测输入长边尺寸 (px)
  det_resize_long: 960

  # ── 图像预处理开关 ──
  # 深色背景自动反色 (白字/黑底场景)
  det_invert_dark: true

  # 检测前 Gaussian 去噪
  det_denoise: false

  # 识别前 CLAHE 对比度增强
  rec_enhance: false
```

| 参数 | 默认值 | 取值范围 | 说明 |
|------|--------|----------|------|
| `cpu_threads` | `4` | 1~CPU核心数 | PaddlePaddle CPU 推理线程数 |
| `det_threshold` | `0.3` | 0.0~1.0 | DB 检测后处理阈值，越低检出越敏感 |
| `box_threshold` | `0.6` | 0.0~1.0 | 文本框筛选阈值 |
| `min_confidence` | `0.5` | 0.0~1.0 | 识别结果最低置信度，低于此值丢弃 |
| `det_resize_long` | `960` | 320~4000 | 检测前将图像长边缩放到的尺寸 (影响速度/精度) |
| `det_invert_dark` | `true` | `true` / `false` | 检测到深色背景（亮度<100）时自动反色 |
| `det_denoise` | `false` | `true` / `false` | 检测前 3x3 Gaussian Blur |
| `rec_enhance` | `false` | `true` / `false` | 识别前 CLAHE 对比度增强 |

### 预处理选择建议

| 场景 | 建议配置 |
|------|----------|
| 浅色背景深色文字 (正常场景) | `det_invert_dark: true`, 其他 false |
| 游戏/深色模式 UI | `det_invert_dark: true`, `rec_enhance: true` |
| 低对比度文本 | `det_invert_dark: true`, `rec_enhance: true` |
| 高噪点图像 | `det_denoise: true` |

---

## 5. Translator 翻译配置

```yaml
translator:
  # 翻译后端: llama (本地大模型)
  backend: "llama"

  llama:
    # llama.cpp server 地址 (OpenAI 兼容 API)
    url: "http://127.0.0.1:8080"

    # 请求超时 (秒)
    timeout: 30

    # 最大重试次数
    max_retries: 2

    # 并行翻译请求数
    parallel_requests: 4

    # 推理参数
    inference_params:
      temperature: 0.7
      top_k: 20
      top_p: 0.6
      repeat_penalty: 1.05
      n_predict: 512
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `backend` | `"llama"` | 翻译后端选择 |
| `llama.url` | `"http://127.0.0.1:8080"` | llama.cpp server 地址 |
| `llama.timeout` | `30` | 请求超时秒数 |
| `llama.max_retries` | `2` | 失败重试次数 |
| `llama.parallel_requests` | `4` | 并发翻译数（提升批量翻译速度） |
| `llama.inference_params.temperature` | `0.7` | 翻译多样性（越低越确定） |
| `llama.inference_params.n_predict` | `512` | 单次最大生成 token 数 |

---

## 6. Overlay 覆盖层配置

```yaml
overlay:
  # 覆盖层后端: wxpython (跨平台透明窗口)
  backend: "wxpython"

  # 字体大小 (px)
  font_size: 16

  # 字体族
  font_family: "Microsoft YaHei"

  # 背景不透明度 (0.0=完全透明, 1.0=完全不透明)
  background_opacity: 0.7

  # 文本颜色 (十六进制)
  text_color: "#FFFFFF"

  # 是否启用 WDA_EXCLUDEFROMCAPTURE (防止覆盖层被再次采集)
  exclude_from_capture: true
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `font_size` | `16` | 覆盖层文字大小 |
| `font_family` | `"Microsoft YaHei"` | 字体（需系统已安装） |
| `background_opacity` | `0.7` | 覆盖层背景不透明度 |
| `text_color` | `"#FFFFFF"` | 覆盖层文字颜色 |
| `exclude_from_capture` | `true` | Win10 2004+ 防捕获特性 |

---

## 8. Pipeline 流水线配置

```yaml
pipeline:
  # 目标周期 (秒) — 每隔多久执行一次 OCR+翻译
  cycle_interval: 5.0

  # 是否启用帧差异检测
  diff_detection: false

  # 差异检测阈值 (0~1, 低于此值跳过 OCR)
  diff_threshold: 0.95

  # 单帧最大文本框数
  max_text_boxes: 50

  # OCR前图像长边最大像素 (超过此值等比缩小, 0=不限制)
  downscale_max_size: 720
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `cycle_interval` | `5.0` | 周期间隔秒数，越短响应越快但 CPU 占用越高 |
| `diff_detection` | `false` | 开启后画面无变化时跳过 OCR，节省算力 |
| `diff_threshold` | `0.95` | 差异检测灵敏度（更高=更容易跳过） |
| `max_text_boxes` | `50` | 单帧最大检测框数，防止异常场景 |
| `downscale_max_size` | `720` | OCR前将长边>此值的图像等比缩放，OCR后坐标自动还原。0=不限制 |

---

## 9. GUI 配置

```yaml
gui:
  # UI 语言: "en" (English) 或 "zh" (中文)
  ui_language: "en"

  # 暂停/继续快捷键
  hotkey_pause: "F9"

  # 退出快捷键
  hotkey_quit: "F10"

  # 单次翻译快捷键
  hotkey_single_translate: "F8"
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ui_language` | `"en"` | UI 显示语言，"en"=英文, "zh"=中文。GUI 标题栏有快捷切换按钮 |
| `hotkey_pause` | `"F9"` | 暂停/继续翻译流水线 |
| `hotkey_quit` | `"F10"` | 退出程序 |
| `hotkey_single_translate` | `"F8"` | 执行单次翻译（采集一帧并翻译） |

热键格式遵循 `keyboard` 库的命名规范。

---

## 9. 语言配置

```yaml
# 源语言
source_lang: "en"

# 目标语言
target_lang: "zh"
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `source_lang` | `"en"` | OCR 主要识别语言 + 翻译源语言 |
| `target_lang` | `"zh"` | 翻译目标语言 |

> **注意**：OCR 识别语言由 PaddleOCR 的 `lang` 参数控制（当前硬编码为 `'en'`），
> `source_lang` 目前仅用于翻译 prompt 模板。

---

## 11. Logging 日志配置

```yaml
logging:
  # 是否启用日志
  enabled: true

  # 日志文件路径 (JSONL 格式)
  path: "./logs/cycles.jsonl"

  # 是否记录耗时
  include_timing: true
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `true` | 开启/关闭日志 |
| `path` | `"./logs/cycles.jsonl"` | 日志文件路径 |
| `include_timing` | `true` | 是否记录各阶段耗时 |

日志格式为 JSONL（每行一个完整周期的 JSON 对象），便于程序化分析。

---

## 12. 完整配置示例

```yaml
# Screen Translate — 完整配置文件
# 所有路径均相对于本文件所在目录
#
# ── 模型目录结构 ──
# 项目内置以下本地模型（均位于项目根目录）：
#   PP-OCRv5_mobile_det_infer/  ← 检测模型 (det_model_dir)
#   PP-OCRv5_mobile_rec_infer/  ← 识别模型 (rec_model_dir)
#   PP-LCNet_x1_0_textline_ori/ ← 文本行方向分类 (自动发现)
#   PP-LCNet_x1_0_doc_ori/      ← 文档方向分类 (自动发现)
#   UVDoc/                      ← 文档畸变矫正 (自动发现)
#   easyocr_models/             ← EasyOCR 本地模型
# 后三个模型由 PaddleX 自动从当前目录加载，无需在 config.yaml 中额外配置。

capture:
  backend: "directshow"
  camera_index: 0
  fps: 30
  monitor: 1
  region: null

ocr:
  engine: "paddle"                        # OCR引擎: "paddle" | "easyocr"
  easyocr_languages: ["en"]               # EasyOCR 语言列表
  # PP-OCRv5 本地模型目录 (PaddleOCR 专用)
  det_model_dir: "./PP-OCRv5_mobile_det_infer"
  rec_model_dir: "./PP-OCRv5_mobile_rec_infer"
  # 推理参数
  cpu_threads: 4
  det_threshold: 0.3
  box_threshold: 0.6
  min_confidence: 0.5
  det_resize_long: 960
  # 预处理开关
  det_invert_dark: true
  det_denoise: false
  rec_enhance: false

translator:
  backend: "llama"
  llama:
    url: "http://127.0.0.1:8080"
    timeout: 30
    max_retries: 2
    parallel_requests: 4
    inference_params:
      temperature: 0.7
      top_k: 20
      top_p: 0.6
      repeat_penalty: 1.05
      n_predict: 512

source_lang: "en"
target_lang: "zh"

overlay:
  backend: "wxpython"
  font_size: 16
  font_family: "Microsoft YaHei"
  background_opacity: 0.7
  text_color: "#FFFFFF"
  exclude_from_capture: true

pipeline:
  cycle_interval: 5.0
  diff_detection: false
  diff_threshold: 0.95
  max_text_boxes: 50
  downscale_max_size: 720               # OCR前图像缩小阈值 (0=不限制)

gui:
  ui_language: "en"                      # UI语言: "en" | "zh"
  hotkey_pause: "F9"
  hotkey_quit: "F10"
  hotkey_single_translate: "F8"

logging:
  enabled: true
  path: "./logs/cycles.jsonl"
  include_timing: true
```

---

## 常见问题

### Q: 如何验证本地模型目录配置正确？

检查模型目录下的 `inference.yml` 文件，确认 `model_name` 字段：

```bash
# 检测模型名称应为:
grep model_name PP-OCRv5_mobile_det_infer/inference.yml
# → model_name: PP-OCRv5_mobile_det

# 识别模型名称应为:
grep model_name PP-OCRv5_mobile_rec_infer/inference.yml
# → model_name: PP-OCRv5_mobile_rec

# 辅助模型名称:
grep model_name PP-LCNet_x1_0_textline_ori/inference.yml
# → model_name: PP-LCNet_x1_0_textline_ori

grep model_name PP-LCNet_x1_0_doc_ori/inference.yml
# → model_name: PP-LCNet_x1_0_doc_ori

grep model_name UVDoc/inference.yml
# → model_name: UVDoc

# EasyOCR 模型文件:
ls easyocr_models/
# → craft_mlt_25k.pth  english_g2.pth
```

### Q: 模型目录找不到怎么办？

确保 `config.yaml` 中的路径相对于项目根目录：
- `./PP-OCRv5_mobile_det_infer` = `<项目根>/PP-OCRv5_mobile_det_infer`
- 也可以使用绝对路径: `C:/Software/screen_translate/PP-OCRv5_mobile_det_infer`

对于辅助模型（PP-LCNet_x1_0_textline_ori、PP-LCNet_x1_0_doc_ori、UVDoc），只需确保从项目根目录运行程序，PaddleX 会自动从当前目录加载。也可以设置 `PADDLE_PDX_LOCAL_MODEL_DIRS` 环境变量指向模型所在目录。

### Q: 如何降低 OCR CPU 占用？

1. 减少 `cpu_threads` (如 4 → 2)
2. 减小 `det_resize_long` (如 960 → 640)
3. 增大 `cycle_interval` (如 5s → 10s)
4. 启用 `diff_detection: true` 跳过无变化帧
