"""
logger/cycle_logger.py — JSONL 周期日志模块

记录每个翻译周期的详细数据：
- 原文/译文对照
- 各阶段耗时
- 文本框位置
"""
import json
import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

from ..config.settings import LoggingConfig, AppConfig


@dataclass
class TextBoxLog:
    original: str
    translated: str
    bbox: list[int]           # [x, y, w, h]
    det_score: float = 0.0
    rec_score: float = 0.0
    translate_status: str = "ok"  # ok | error | skipped


@dataclass
class CycleLog:
    cycle_id: int
    timestamp: str = ""
    capture_ms: float = 0.0
    ocr_det_ms: float = 0.0
    ocr_rec_ms: float = 0.0
    translate_ms: float = 0.0
    overlay_ms: float = 0.0
    total_ms: float = 0.0
    text_boxes: list[TextBoxLog] = field(default_factory=list)
    skipped: bool = False
    skip_reason: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "capture_ms": round(self.capture_ms, 2),
            "ocr_det_ms": round(self.ocr_det_ms, 2),
            "ocr_rec_ms": round(self.ocr_rec_ms, 2),
            "translate_ms": round(self.translate_ms, 2),
            "overlay_ms": round(self.overlay_ms, 2),
            "total_ms": round(self.total_ms, 2),
            "text_boxes": [
                {
                    "original": tb.original,
                    "translated": tb.translated,
                    "bbox": tb.bbox,
                    "det_score": round(tb.det_score, 4),
                    "rec_score": round(tb.rec_score, 4),
                    "translate_status": tb.translate_status,
                }
                for tb in self.text_boxes
            ],
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }
        return d


class CycleLogger:
    """管理翻译周期日志的写入（JSONL + 人类可读文本日志）"""

    def __init__(self, config: AppConfig):
        self._enabled = config.logging.enabled
        self._include_timing = config.logging.include_timing
        self._path = config.resolve_path(config.logging.path)

        # 确保日志目录存在
        log_dir = os.path.dirname(self._path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        self._cycle_id = 0
        self._file = None
        self._ocr_file = None
        self._trans_file = None

        if self._enabled:
            self._file = open(self._path, "a", encoding="utf-8")
            # 人类可读 OCR 日志
            ocr_log_path = os.path.join(log_dir, "ocr_results.txt")
            self._ocr_file = open(ocr_log_path, "a", encoding="utf-8")
            # 人类可读翻译日志
            trans_log_path = os.path.join(log_dir, "translation_results.txt")
            self._trans_file = open(trans_log_path, "a", encoding="utf-8")

    def new_cycle(self) -> CycleLog:
        """创建一个新周期的日志对象"""
        self._cycle_id += 1
        return CycleLog(
            cycle_id=self._cycle_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def write_cycle(self, cycle: CycleLog):
        """将周期日志写入 JSONL 文件"""
        if not self._enabled or self._file is None:
            return
        line = json.dumps(cycle.to_dict(), ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()

    def write_ocr_result(self, cycle_id: int, boxes: list, det_ms: float, rec_ms: float):
        """将 OCR 结果写入人类可读文本日志"""
        if not self._enabled or self._ocr_file is None:
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._ocr_file.write(f"{'='*60}\n")
        self._ocr_file.write(f"Cycle #{cycle_id}  |  {ts}\n")
        ocr_total = det_ms + rec_ms
        self._ocr_file.write(f"OCR total: {ocr_total:.1f}ms  (det+rec: {det_ms:.1f}ms + {rec_ms:.1f}ms)\n")
        self._ocr_file.write(f"Boxes found: {len(boxes)}\n")
        self._ocr_file.write(f"{'-'*60}\n")
        for i, tb in enumerate(boxes, 1):
            x, y, w, h = tb.bounding_rect
            self._ocr_file.write(
                f"  [{i}] text=\"{tb.text}\"  "
                f"bbox=({x},{y},{w},{h})  "
                f"det={tb.det_score:.3f}  rec={tb.rec_score:.3f}\n"
            )
        self._ocr_file.write("\n")
        self._ocr_file.flush()

    def write_translation_result(self, cycle_id: int, pairs: list[tuple[str, str, str]], total_ms: float):
        """将翻译结果写入人类可读文本日志

        Args:
            cycle_id: 周期编号
            pairs: [(原文, 译文, 状态), ...]
            total_ms: 翻译阶段总耗时
        """
        if not self._enabled or self._trans_file is None:
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._trans_file.write(f"{'='*60}\n")
        self._trans_file.write(f"Cycle #{cycle_id}  |  {ts}\n")
        self._trans_file.write(f"Translation time: {total_ms:.1f}ms  |  Items: {len(pairs)}\n")
        self._trans_file.write(f"{'-'*60}\n")
        for i, (original, translated, status) in enumerate(pairs, 1):
            status_icon = "✓" if status == "ok" else "✗"
            self._trans_file.write(f"  [{i}] {status_icon} \"{original}\"\n")
            self._trans_file.write(f"       → \"{translated}\"\n")
        self._trans_file.write("\n")
        self._trans_file.flush()

    def close(self):
        if self._file:
            self._file.close()
            self._file = None
        if self._ocr_file:
            self._ocr_file.close()
            self._ocr_file = None
        if self._trans_file:
            self._trans_file.close()
            self._trans_file = None


class Timer:
    """简单计时器，用于测量各阶段耗时"""

    def __init__(self):
        self._start: float = 0.0

    def start(self):
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0
