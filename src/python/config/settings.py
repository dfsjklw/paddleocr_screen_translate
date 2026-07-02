"""
config/settings.py — YAML 配置加载与验证模块
"""
import os
import sys
import yaml
from dataclasses import dataclass, field
from typing import Any

# settings.py → config → python → src → project_root
# 兼容 PyInstaller 打包：frozen 时用 sys._MEIPASS，否则基于 __file__ 推算
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)  # 打包后路径相对于 EXE 目录（模型、config.yaml 都在此处）
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@dataclass
class LlamaConfig:
    url: str = "http://127.0.0.1:8080"
    timeout: int = 30
    max_retries: int = 2
    parallel_requests: int = 4
    inference_params: dict = field(default_factory=lambda: {
        "temperature": 0.7, "top_k": 20, "top_p": 0.6,
        "repeat_penalty": 1.05, "n_predict": 512,
    })



@dataclass
class TranslatorConfig:
    backend: str = "llama"
    llama: LlamaConfig = field(default_factory=LlamaConfig)


@dataclass
class OcrConfig:
    engine: str = "onnx"                        # OCR 引擎: 当前仅支持 "onnx" (PP-OCRv6)

    # ── ONNX 引擎参数 ──
    det_model_dir: str = "./PP-OCRv6_small_det_onnx"
    rec_model_dir: str = "./PP-OCRv6_small_rec_onnx"
    det_limit_side: int = 960                   # 检测前长边缩放上限
    det_unclip_ratio: float = 1.4               # DB 后处理 unclip 系数
    use_directml: bool = False                  # 启用 ONNX DirectML GPU 加速 (Windows 10+)
    rec_batch_size: int = 0                     # 识别 batch 大小: 0=全部打包, 1=逐张, N=每N个一组

    # ── 通用参数 ──
    min_confidence: float = 0.5                 # 最小识别置信度 (Python 侧二次过滤)
    det_box_thresh: float = 0.4                 # 检测框分数阈值
    det_binary_thresh: float = 0.2              # 概率图二值化阈值


@dataclass
class CaptureConfig:
    backend: str = "directshow"
    camera_index: int = 0
    fps: int = 30
    monitor: int = 1          # screen后端: 显示器索引 (1=主显示器)
    region: list | None = None  # screen后端: [x, y, w, h] 或 null=全屏


@dataclass
class OverlayConfig:
    font_size: int = 16
    font_family: str = "Microsoft YaHei"
    background_opacity: float = 0.92   # 背景不透明度 (0~1)，越高越能遮盖原文
    background_color: str = "#000000"  # 背景颜色 (十六进制)
    text_color: str = "#FFFFFF"
    exclude_from_capture: bool = True
    min_font_size: int = 8             # 堆叠检测缩小下限
    stack_shrink: bool = True          # 堆叠检测缩小总开关


@dataclass
class PipelineConfig:
    cycle_interval: float = 5.0
    downscale_max_size: int = 0     # OCR前将长边>此值的图像等比缩至此值; 0=不缩放（默认关闭）
    upscale_small_image: bool = True  # 小图预处理: <300px时放大3x; 默认开启


@dataclass
class GuiConfig:
    ui_language: str = "en"           # UI语言: "en" 或 "zh"
    hotkey_pause: str = "F9"
    hotkey_quit: str = "F10"
    hotkey_single_translate: str = "F8"
    hotkey_region_translate: str = "F7"
    hotkey_clear_overlay: str = "F6"
    hotkey_hold_hide: str = "F5"


@dataclass
class LoggingConfig:
    enabled: bool = True
    path: str = "./logs/cycles.jsonl"
    include_timing: bool = True


@dataclass
class ConsoleLoggingConfig:
    enabled: bool = True
    log_dir: str = "./logs"
    max_days: int = 7


@dataclass
class AppConfig:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    source_lang: str = "en"
    target_lang: str = "zh"
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    console_logging: ConsoleLoggingConfig = field(default_factory=ConsoleLoggingConfig)

    def resolve_path(self, path: str) -> str:
        """将相对路径解析为绝对路径（相对于项目根目录）"""
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(_BASE_DIR, path))


def _deep_update(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _dict_to_dataclass(cls, data: dict):
    """递归将 dict 转为 dataclass 实例"""
    if data is None:
        return cls()
    fieldtypes = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for key, val in data.items():
        if key in fieldtypes:
            ft = fieldtypes[key]
            # 处理嵌套 dataclass
            if isinstance(ft, type) and hasattr(ft, '__dataclass_fields__'):
                kwargs[key] = _dict_to_dataclass(ft, val)
            else:
                kwargs[key] = val
    return cls(**kwargs)


def load_config(config_path: str | None = None) -> AppConfig:
    """加载配置文件，返回 AppConfig 实例"""
    if config_path is None:
        config_path = os.path.join(_BASE_DIR, "config.yaml")

    if not os.path.exists(config_path):
        print(f"[WARN] config.yaml not found at {config_path}, using defaults")
        return AppConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return _dict_to_dataclass(AppConfig, raw)
