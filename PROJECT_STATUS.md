# Screen Translate — 项目状态报告

> 更新日期：2026-06-24

---

## 🟢 已完成 (Ready)

### 1. 项目骨架 & 模块结构
- [x] 模块目录结构完整 (`capture/`, `ocr/`, `translator/`, `overlay/`, `gui/`, `logger/`, `pipeline/`, `config/`, `i18n/`)
- [x] 各模块通过抽象基类/回调/数据类实现高度解耦
- [x] `main.py` 入口 + `wx.App` 生命周期管理
- [x] `package.py` 打包脚本（排除 llama.cpp / OBS / paddle SDK 源码）

### 2. Capture 采集模块
- [x] `DirectShowCapture` — OpenCV `CAP_DSHOW` 读取 OBS 虚拟摄像头
- [x] `ScreenCapture` — mss/PIL 屏幕直接捕获（支持全屏/区域）
- [x] 返回 BGR numpy 数组，支持分辨率/FPS 配置
- [x] `CaptureBackend` 抽象基类（为 DXGI 等后端预留）

### 3. OCR 模块 (双引擎: PaddleOCR + EasyOCR)
- [x] `paddle_ocr_engine.py` — 基于 `paddleocr` 库的纯 Python OCR 引擎
- [x] `easy_ocr_engine.py` — EasyOCR 备选引擎，支持 80+ 语言，GPU 加速
- [x] 统一接口 `TextBox` / `OcrOutput` / 工厂函数 `create_ocr_engine()`
- [x] GUI 切换引擎自动重启流水线（`wx.CallLater` 延迟重启）
- [x] `pipeline.init()` 自动 shutdown 旧引擎再创建新引擎，防资源泄漏
- [x] PaddleOCR: PP-OCRv5_mobile 本地模型（det ~4.7MB + rec ~16.5MB）
- [x] EasyOCR: 本地模型存储在 `easyocr_models/`
- [x] 图像预处理: 深色背景自动反色、Gaussian 去噪、CLAHE 对比度增强
- [x] 无需 C++ DLL 依赖，完全 Python 实现

### 4. Translator 翻译模块
- [x] `LlamaCppTranslator` — llama.cpp HTTP API (OpenAI 兼容 `/v1/chat/completions`)
- [x] 翻译 prompt 模板（中英文）
- [x] 并行翻译: `ThreadPoolExecutor` + `translate_batch()`
- [x] 重试机制: 指数退避 (1s, 2s)
- [x] `TranslatorBackend` 抽象基类（为 Deepl 预留）

### 5. Overlay 覆盖层模块
- [x] `OverlayWindow` — wxPython 全屏透明覆盖窗口
- [x] Win32 扩展样式: `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW`
- [x] `WDA_EXCLUDEFROMCAPTURE` 防捕获污染
- [x] UpdateLayeredWindow + per-pixel alpha 渲染
- [x] **64-bit HDC 兼容**: 正确设置 ctypes argtypes (`wintypes.HDC`)，修复 OverflowError
- [x] `set_items()` / `show_overlay()` / `hide_overlay()` 线程安全（wx.CallAfter）

### 6. GUI 模块
- [x] `MainWindow` — 控制面板 (480x780px)
- [x] Start / Single / Pause(Resume) / Stop 按钮 + 状态联动
- [x] **单次翻译独立可用** — 无需先启动实时翻译，按钮始终可点击
- [x] 单次翻译执行中按钮自动禁用，完成后恢复
- [x] **中英文语言切换** — 标题栏 "中/EN" 按钮，即时切换全部 UI 文本
- [x] `i18n/` 模块 — `LocaleManager` 单例 + 80+ 字符串键
- [x] Diff Detection 快速切换按钮
- [x] **720p Downscale 快速切换按钮** — ON(720) / OFF(0)
- [x] URL 连通性测试按钮
- [x] OCR 引擎选择 (PaddleOCR / EasyOCR) + 切换自动重启流水线
- [x] 可编辑配置: llama URL, 源语言, 目标语言, 周期间隔
- [x] OCR 预处理开关 (反色/去噪/增强)
- [x] EasyOCR 语言输入 (仅在 easyocr 模式下显示)
- [x] 实时 OCR + 翻译结果显示面板
- [x] `TrayIcon` — 系统托盘 + 右键菜单（支持中英文）
- [x] 全局快捷键: F8 单次翻译, F9 暂停, F10 退出 (keyboard 库)
- [x] 快捷键可自定义并热更新

### 7. Pipeline 调度核心
- [x] 独立线程运行，支持 Start/Stop/TogglePause
- [x] 完整周期: 采集→差异检测→720p下采样→OCR→坐标还原→翻译→缓存→覆盖→日志
- [x] **720p 图像等比缩放**: 长边 >720px 自动缩放，OCR 后坐标等比还原
- [x] 帧差异检测: 灰度降采样 (160x90) + 均值差
- [x] 无变化帧跳过（复用上次覆盖层）
- [x] 翻译缓存: `{original_text: translated_text}` 避免重复翻译
- [x] 无意义文本片段过滤（单标点/纯数字等）
- [x] 周期剩余时间 sleep 维持固定频率
- [x] 线程安全: `threading.Lock` 保护临界区
- [x] GUI 回调: `on_status_change`, `on_cycle_complete`, `on_ocr_result`, `on_translation_result`
- [x] `run_once()` 接受 `on_start`/`on_done` 回调，支持 GUI 按钮状态联动

### 8. Logger 日志模块
- [x] JSONL 格式 (`logs/cycles.jsonl`)，每行一个完整周期
- [x] 人类可读 OCR 日志 (`logs/ocr_results.txt`)
- [x] 人类可读翻译日志 (`logs/translation_results.txt`)
- [x] `CycleLog` — 记录所有阶段耗时 + 每框原文/译文/位置/置信度
- [x] `Timer` 工具类
- [x] UTC 时间戳

### 9. Config 配置模块
- [x] YAML → 嵌套 dataclass 解析 (`AppConfig`)
- [x] `resolve_path()` 相对路径→绝对路径
- [x] 完整的 `config.yaml` 含所有模块配置
- [x] `GuiConfig.ui_language` — UI 语言持久化 ("en"/"zh")
- [x] `PipelineConfig.downscale_max_size` — 720p 下采样开关
- [x] `OcrConfig.engine` + `OcrConfig.easyocr_languages` — 双引擎配置
- [x] **`CONFIG.md`** — 完整的配置参考文档

### 10. i18n 国际化模块
- [x] `src/python/i18n/__init__.py` — `LocaleManager` 单例 + `tr()` 快捷函数
- [x] `src/python/i18n/strings.py` — 80+ 字符串键，中英文全覆盖
- [x] 语言变更通知机制 (`subscribe`/`unsubscribe`)，即时刷新全部 UI
- [x] 支持 `{name}` 插值变量

### 11. 测试
- [x] `test_e2e.py` — 完整流水线测试: **48/48 passed** (含翻译)
- [x] `test_focused.py` — OCR 切换 + 覆盖层 + 下采样测试: **31/31 passed**
- [x] **合计 79/79 测试全部通过**

---

## 🟡 部分完成 / 需要完善

### 12. Overlay 覆盖效果
- ⚠️ **覆盖不完整**: 当前仅绘制半透明背景+文本，未彻底遮盖原文区域

### 13. GUI 配置持久化
- ⚠️ GUI 中修改的部分配置（URL/语言/间隔等）未自动写回 `config.yaml`
- ✅ 语言选择和下采样开关已通过 config 属性内存持久化
  - 建议: 添加 "Save Settings" 按钮 / 自动保存

---

## 🔴 未完成

### 14. 选区功能 (Region Selection)
- [ ] `config.yaml` 中已定义 `hotkey_select_region: "F8"`，但无实现

### 15. Linux 支持
- [ ] Capture: v4l2loopback 后端未实现
- [ ] Overlay: X11/Wayland 覆盖层未实现

### 16. 字体大小自适应
- [ ] 翻译后文本长度可能与原文差异大，未做字体缩放适配包围框

### 17. 错误恢复
- [ ] 连续采集失败时的自动重连
- [ ] llama.cpp 服务断连时的通知

### 18. DeepL 后端
- [ ] `DeepLTranslator` 仅有存根，未实现

---

## 📊 代码量统计

| 语言 | 文件 | 行数 |
|------|------|------|
| Python | 11 个模块 | ~2,800 行 |
| YAML | 1 个 | 97 行 |
| Markdown | 4 个 | ARCHITECTURE, PROJECT_STATUS, todo, CONFIG |
| 模型文件 | 8 个 | PP-OCRv5_mobile + PaddleX + EasyOCR |
| **总计** | | **~2,900 行代码 + 文档** |

---

## 🎯 下一步建议优先级

| 优先级 | 任务 | 原因 |
|--------|------|------|
| **P0** | 完善覆盖层背景填充 | 影响翻译可读性 |
| **P1** | GUI 配置保存 | 用户体验 |
| **P1** | 选区功能实现 | 减少不必要的 OCR 区域 |
| **P2** | 字体大小自适应 | 长文本显示 |
| **P2** | 错误恢复（重连/通知） | 稳定性 |
| **P3** | Linux 支持 | 跨平台 |
| **P3** | DeepL 后端 | 多后端 |
