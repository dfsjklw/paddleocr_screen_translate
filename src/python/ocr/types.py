"""
ocr/types.py — OCR 数据类型定义

被 ppocr_onnx_engine 和 ocr/__init__.py 共同使用。
"""
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TextBox:
    """文本框数据结构"""
    points: List[Tuple[float, float]]  # [(x1,y1),(x2,y2),(x3,y3),(x4,y4)]
    text: str
    det_score: float
    rec_score: float

    @property
    def bounding_rect(self) -> Tuple[int, int, int, int]:
        """返回 (x, y, w, h) 的轴对齐包围框"""
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        x_min, y_min = int(min(xs)), int(min(ys))
        return (x_min, y_min, int(max(xs)) - x_min, int(max(ys)) - y_min)


@dataclass
class OcrOutput:
    """OCR输出结果"""
    boxes: List[TextBox]
    det_time_ms: float = 0.0
    rec_time_ms: float = 0.0
    total_time_ms: float = 0.0


__all__ = [
    "TextBox",
    "OcrOutput",
]
