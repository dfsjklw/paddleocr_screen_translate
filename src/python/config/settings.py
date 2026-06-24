"""
config/settings.py — YAML 配置加载与验证模块
"""
import os
import yaml
from dataclasses import dataclass, field
from typing import Any

# settings.py → config → python → src → project_root
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
    engine: str = "paddle"          # OCR引擎: "paddle" 或 "easyocr"
    # PaddleOCR 专用配置
    det_model_dir: str = "./PP-OCRv5_mobile_det_infer"
    rec_model_dir: str = "./PP-OCRv5_mobile_rec_infer"
    cpu_threads: int = 4
    det_threshold: float = 0.3
    box_threshold: float = 0.6
    min_confidence: float = 0.5
    det_resize_long: int = 960
    # 图像预处理开关
    det_invert_dark: bool = True    # 深色背景自动反色
    det_denoise: bool = False       # 检测前去噪 (Gaussian blur)
    rec_enhance: bool = False       # 识别前增强 (CLAHE)
    # EasyOCR 专用配置
    easyocr_languages: list = field(default_factory=lambda: ["en"])  # EasyOCR 语言列表


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
    text_color: str = "#FFFFFF"
    exclude_from_capture: bool = True


@dataclass
class PipelineConfig:
    cycle_interval: float = 5.0
    diff_detection: bool = False
    diff_threshold: float = 0.95
    max_text_boxes: int = 50
    downscale_max_size: int = 720   # OCR前将长边>此值的图像等比缩至此值; 0=不缩放


@dataclass
class GuiConfig:
    ui_language: str = "en"           # UI语言: "en" 或 "zh"
    hotkey_pause: str = "F9"
    hotkey_quit: str = "F10"
    hotkey_single_translate: str = "F8"


@dataclass
class LoggingConfig:
    enabled: bool = True
    path: str = "./logs/cycles.jsonl"
    include_timing: bool = True


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
