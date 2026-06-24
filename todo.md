# Screen Translate — 开发路线图 & TODO

> 更新日期：2026-06-24

## P0: 验证核心流程 ✅

### 0.1 端到端集成测试
- [x] 启动 llama.cpp server，加载翻译模型
- [x] 启动 OBS 虚拟摄像头
- [x] 运行 `python test_e2e.py`，验证完整流程 (**48/48 tests passed**)
- [x] 运行 `python test_focused.py`，OCR切换+覆盖层+下采样 (**31/31 tests passed**)
- [x] 确认: 采集→720p下采样→OCR→坐标还原→翻译→覆盖 链路畅通
- [x] 确认: OCR 模块双引擎 (PaddleOCR + EasyOCR)，切换后正常工作
- [x] 确认: 翻译功能正常 (英文→中文, 21/21 翻译成功)
- [x] 确认: 覆盖层 64-bit HDC 兼容性修复 (ctypes argtypes)

### 0.2 覆盖层背景填充
- [ ] `OverlayWindow._draw_item()`: 将半透明背景改为不透明
- [ ] 背景颜色改为接近原位背景色（或纯黑/深灰不透明）
- [ ] 验证: OBS 虚拟摄像头画面中，原文被译文覆盖

---

## P1: GUI 完善

### 1.1 配置持久化
- [ ] `MainWindow`: 添加 "Save" 按钮
- [ ] 点击时收集 GUI 字段值 → 更新 `AppConfig` → 写回 `config.yaml`
- [ ] 启动时从 `config.yaml` 恢复上次配置

### 1.2 选区功能
- [ ] 实现热键: 弹出半透明选区窗口
- [ ] 用户拖拽选择屏幕区域
- [ ] 选区坐标保存到配置（相对于摄像头画面）
- [ ] `Pipeline._execute_cycle()`: 只 OCR 选区内区域

### 1.3 状态栏增强
- [ ] 显示实时 FPS / 周期耗时
- [ ] 显示缓存的翻译条数
- [ ] 显示最近一次错误信息

---

## P2: 稳定性 & 体验

### 2.1 字体自适应
- [ ] `OverlayWindow._draw_item()`: 测量文本宽度
- [ ] 若文本超出包围框宽度，缩小字号 (最小 10px)
- [ ] 若仍超出，换行显示

### 2.2 采集容错
- [ ] `DirectShowCapture.read_frame()`: 连续失败 N 次后自动重连
- [ ] 通知 GUI: "Camera disconnected, retrying..."

### 2.3 翻译容错
- [ ] llama.cpp 连接失败时在 GUI 显示红色警告
- [ ] 支持备用翻译 URL（fallback）

### 2.4 日志查看器
- [ ] GUI 内嵌简易日志查看面板
- [ ] 按周期浏览原文/译文对照

### 2.5 OCR 预热
- [ ] 启动时运行一次空推理触发 PaddlePaddle JIT 编译
- [ ] 避免首个周期耗时过长

---

## P3: 翻译模块增强

### 3.1 DeepL 后端
- [ ] 实现 `DeepLTranslator.translate_one()`
- [ ] API key 配置
- [ ] 语言代码映射 (en→EN, zh→ZH)

### 3.2 Prompt 模板配置
- [ ] 允许用户在 `config.yaml` 自定义翻译 prompt
- [ ] 支持 `{text}`, `{source}`, `{target}` 占位符

### 3.3 翻译质量控制
- [ ] 对翻译结果做后处理: trim, 去除 markdown, 去除 "翻译：" 前缀
- [ ] 检测空翻译/重复翻译

---

## P4: Linux 跨平台

### 4.1 Capture
- [ ] 实现 `V4L2Capture(CaptureBackend)`
- [ ] 配置: `capture.backend: "v4l2"` 或自动检测

### 4.2 Overlay
- [ ] 研究 X11: `_NET_WM_WINDOW_TYPE_DOCK` + 透明
- [ ] 研究 Wayland: `layer-shell` 协议

### 4.3 热键
- [ ] 评估 `keyboard` 库在 Linux 下的兼容性
- [ ] 备用: `pynput` 或 X11 grab key

---

## P5: 性能优化

### 5.1 OCR 加速
- [x] PP-OCRv5_mobile 本地模型 (CPU 推理)
- [x] 720p 下采样减少 OCR 输入分辨率
- [ ] GPU 推理: PaddleOCR 支持 CUDA (`device='gpu'`)
- [ ] EasyOCR GPU 加速优化

### 5.2 翻译加速
- [ ] 缓存预热: 启动时翻译常见 UI 术语
- [ ] 流式翻译: 使用 `stream: true` 边生成边显示

### 5.3 采集加速
- [ ] DXGI Desktop Duplication 后端 (更高效的桌面捕获)

---

## ✅ 已完成 (2026-06-23 ~ 2026-06-24)

### OCR 双引擎 + 切换
- [x] EasyOcrEngine 实现 (`easy_ocr_engine.py`)
- [x] 工厂函数 `create_ocr_engine()` 支持引擎选择
- [x] GUI OCR 引擎下拉切换 + 自动重启流水线
- [x] pipeline.init() 自动 shutdown 旧引擎

### 单次翻译独立化
- [x] "Single" 按钮默认启用，无需先启动实时翻译
- [x] 执行中按钮自动禁用，完成后恢复
- [x] pipeline.run_once() 增加 on_start/on_done 回调

### i18n 国际化
- [x] `src/python/i18n/` 模块 (LocaleManager + 80+ 翻译键)
- [x] 标题栏 "中/EN" 切换按钮
- [x] 全部 UI 文本即时切换 (按钮/标签/复选框/提示/对话框/托盘菜单)

### 720p 图像下采样
- [x] `PipelineConfig.downscale_max_size` 配置项
- [x] OCR 前等比缩放到 720p
- [x] 识别后坐标等比还原到原始空间
- [x] GUI 快速切换按钮

### Overlay 64-bit 兼容
- [x] ctypes Win32 API argtypes 正确设置 (wintypes.HDC)
- [x] 修复 `CreateCompatibleDC` / `UpdateLayeredWindow` 的 OverflowError
- [x] 修复 `ReleaseHDC` 不存在的问题 (用 `del screen_dc`)

### OCR 模型迁移 (2026-06-23)
- [x] `ocr_bridge.dll` (C++ Paddle Inference) → `paddle_ocr_engine.py` (纯 Python PaddleOCR)
- [x] 移除 `src/cpp/ocr_bridge/` C++ 依赖
- [x] 适配新版 `paddleocr` API (`predict()` + `OCRResult`)
- [x] 修复 MKLDNN PIR 兼容性问题 (`enable_mkldnn=False`)
- [x] 将 PP-OCRv6 内置模型替换为 PP-OCRv5_mobile 本地模型
- [x] 配置本地模型路径
- [x] 修复模型名称不匹配问题

---

## 📋 完成标准 Checklist

- [x] OBS → OpenCV 稳定采集 30fps
- [x] OCR 检测+识别 < 20s (CPU, PaddleOCR ~13s, EasyOCR ~21s)
- [x] llama.cpp 翻译 < 2s (远程 8080, ~200ms 单条)
- [x] 完整周期 < 25s (当前 ~15s OCR+翻译)
- [x] 覆盖层不污染采集源 (WDA_EXCLUDEFROMCAPTURE)
- [x] F9 暂停/恢复正常
- [x] F8 单次翻译快捷键
- [x] GUI 状态实时更新
- [x] 日志完整记录每周期数据 (JSONL + OCR + 翻译)
- [x] GUI 中英文切换
- [x] OCR 引擎热切换 (Paddle↔EasyOCR)
- [x] 720p 图像下采样 + 坐标还原
- [x] 覆盖层 64-bit 兼容
- [ ] 打包 zip 可在新环境部署
