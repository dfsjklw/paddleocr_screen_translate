"""
ocr/__init__.py — OCR 模块入口

支持双引擎：
- PaddleOCR (PP-OCRv5_mobile, 本地模型)
- EasyOCR (多语言, GPU加速)

导出 TextBox、OcrOutput、两个引擎类以及工厂函数。
"""
from .paddle_ocr_engine import (
    PaddleOcrEngine,
    TextBox,
    OcrOutput,
)

from .easy_ocr_engine import (
    EasyOcrEngine,
)

# 向后兼容别名：OcrEngine 默认指向 PaddleOcrEngine
# 新代码应优先使用 create_ocr_engine() 工厂函数
OcrEngine = PaddleOcrEngine


def create_ocr_engine(config):
    """
    工厂函数：根据配置创建并初始化OCR引擎

    根据 config.ocr.engine 选择：
    - "paddle" → PaddleOcrEngine
    - "easyocr" → EasyOcrEngine

    Args:
        config: AppConfig实例

    Returns:
        初始化的引擎实例，或None（初始化失败时）
    """
    engine_name = config.ocr.engine.lower() if hasattr(config.ocr, 'engine') else "paddle"

    if engine_name == "easyocr":
        print("[OCR] Creating EasyOCR engine...")
        import sys; sys.stdout.flush()
        engine = EasyOcrEngine(config)
    else:
        print("[OCR] Creating PaddleOCR engine...")
        import sys; sys.stdout.flush()
        engine = PaddleOcrEngine(config)

    if not engine.init():
        print("[OCR] Engine init failed")
        import sys; sys.stdout.flush()
        return None
    print(f"[OCR] Engine ready: {type(engine).__name__}")
    import sys; sys.stdout.flush()
    return engine


__all__ = [
    "PaddleOcrEngine",
    "EasyOcrEngine",
    "OcrEngine",
    "TextBox",
    "OcrOutput",
    "create_ocr_engine",
]
