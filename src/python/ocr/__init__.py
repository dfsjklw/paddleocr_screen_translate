"""
ocr/__init__.py — OCR 模块入口

使用 PP-OCRv6 ONNX Runtime 引擎进行文字检测与识别。
"""
from .types import TextBox, OcrOutput
from .ppocr_onnx_engine import PpOcrOnnxEngine

# 向后兼容别名
OcrEngine = PpOcrOnnxEngine


def create_ocr_engine(config):
    """
    工厂函数：创建 ONNX OCR 引擎

    Args:
        config: AppConfig 实例

    Returns:
        引擎实例，或 None（初始化失败时）
    """
    print("[OCR] Creating PP-OCRv6 ONNX engine...")
    engine = PpOcrOnnxEngine(config)

    import sys
    sys.stdout.flush()

    if not engine.init():
        print("[OCR] Engine init failed")
        sys.stdout.flush()
        return None

    print(f"[OCR] Engine ready: {type(engine).__name__}")
    sys.stdout.flush()
    return engine


__all__ = [
    "PpOcrOnnxEngine",
    "OcrEngine",
    "TextBox",
    "OcrOutput",
    "create_ocr_engine",
]
