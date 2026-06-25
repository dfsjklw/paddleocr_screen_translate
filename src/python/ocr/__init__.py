"""
ocr/__init__.py — OCR 模块入口

使用 NCNN PaddleOCRv5 引擎（screen_transalate_ocr.exe）。
输出 TextBox、OcrOutput 数据类以及工厂函数。
"""
from .ncnn_ocr_engine import (
    NcnnOcrEngine,
    TextBox,
    OcrOutput,
)

# 向后兼容别名：OcrEngine 默认指向 NcnnOcrEngine
OcrEngine = NcnnOcrEngine


def create_ocr_engine(config):
    """
    工厂函数：创建并初始化 OCR 引擎

    Args:
        config: AppConfig 实例

    Returns:
        NcnnOcrEngine 实例，或 None（初始化失败时）
    """
    print("[OCR] Creating NCNN OCR engine...")
    import sys; sys.stdout.flush()
    engine = NcnnOcrEngine(config)
    if not engine.init():
        print("[OCR] Engine init failed")
        import sys; sys.stdout.flush()
        return None
    print(f"[OCR] Engine ready: {type(engine).__name__}")
    import sys; sys.stdout.flush()
    return engine


__all__ = [
    "NcnnOcrEngine",
    "OcrEngine",
    "TextBox",
    "OcrOutput",
    "create_ocr_engine",
]
