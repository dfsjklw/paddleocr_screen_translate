# src/python/ocr/easy_ocr_engine.py
"""
easy_ocr_engine.py — 基于EasyOCR的OCR引擎

作为PaddleOCR的备选方案，支持多语言OCR识别。
接口与PaddleOcrEngine保持一致，可无缝切换。
"""
import os
import numpy as np
import cv2
from typing import Optional, List, Tuple
from dataclasses import dataclass
import time

try:
    import easyocr
    _HAS_EASYOCR = True
except ImportError:
    _HAS_EASYOCR = False
    print("[WARN] easyocr not installed. Run: pip install easyocr")

from .paddle_ocr_engine import TextBox, OcrOutput


class EasyOcrEngine:
    """
    EasyOCR引擎：封装EasyOCR调用

    特性：
    - 支持80+语言识别
    - 自动GPU加速（如果可用）
    - 支持PNG/JPG/BMP等图像格式
    - 与PaddleOcrEngine接口兼容
    """

    def __init__(self, config):
        """
        初始化EasyOCR引擎

        Args:
            config: AppConfig实例，包含OCR配置
        """
        self._config = config
        self._ocr_cfg = config.ocr

        # 置信度阈值
        self._min_confidence = config.ocr.min_confidence

        # 语言列表
        self._languages = config.ocr.easyocr_languages
        if isinstance(self._languages, str):
            self._languages = [self._languages]

        # EasyOCR Reader实例
        self._reader: Optional[easyocr.Reader] = None
        self._initialized = False

    def init(self) -> bool:
        """
        初始化EasyOCR Reader

        Returns:
            bool: 是否初始化成功
        """
        if not _HAS_EASYOCR:
            print("[EasyOCR] ERROR: easyocr not installed")
            print("[EasyOCR] Please run: pip install easyocr")
            import sys; sys.stdout.flush()
            return False

        try:
            lang_list = self._languages if self._languages else ["en"]
            print(f"[EasyOCR] Initializing EasyOCR (languages: {lang_list})...")
            import sys; sys.stdout.flush()

            # 模型存储目录指向项目本地目录
            model_dir = self._config.resolve_path("./easyocr_models")
            os.makedirs(model_dir, exist_ok=True)

            self._reader = easyocr.Reader(
                lang_list=lang_list,
                gpu=False,  # 自动检测GPU，不可用时回退CPU
                model_storage_directory=model_dir,
                download_enabled=False,  # 禁用自动下载，使用本地模型
                verbose=True,
            )

            self._initialized = True
            print("[EasyOCR] EasyOCR initialized successfully")
            import sys; sys.stdout.flush()
            return True

        except Exception as e:
            print(f"[EasyOCR] ERROR: Failed to initialize EasyOCR: {e}")
            import traceback
            traceback.print_exc()
            import sys; sys.stdout.flush()
            return False

    def process(self, img: np.ndarray) -> OcrOutput:
        """
        对输入图像执行完整OCR流水线

        Args:
            img: BGR图像 (numpy array, HWC)

        Returns:
            OcrOutput: 包含所有检测到的文本框
        """
        if not self._initialized or self._reader is None:
            print("[EasyOCR] ERROR: Engine not initialized. Call init() first.")
            return OcrOutput(boxes=[])

        start_time = time.perf_counter()

        # 执行OCR
        try:
            # EasyOCR期望RGB图像
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # 调用EasyOCR readtext()
            predict_start = time.perf_counter()
            results = self._reader.readtext(rgb_img)
            predict_ms = (time.perf_counter() - predict_start) * 1000

            # EasyOCR返回: [(bbox, text, confidence), ...]
            # bbox格式: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] (四个角点)
            boxes = []
            det_time = predict_ms
            rec_time = 0.0

            for bbox, text, confidence in results:
                if not text or not text.strip():
                    continue

                # 过滤低置信度
                if confidence < self._min_confidence:
                    continue

                # 转换bbox格式为 [(x1,y1),(x2,y2),(x3,y3),(x4,y4)]
                if isinstance(bbox, np.ndarray):
                    points_list = [(float(p[0]), float(p[1])) for p in bbox]
                else:
                    points_list = [(float(p[0]), float(p[1])) for p in bbox]

                boxes.append(TextBox(
                    points=points_list,
                    text=text.strip(),
                    det_score=confidence,
                    rec_score=confidence,
                ))

            total_time = (time.perf_counter() - start_time) * 1000

            return OcrOutput(
                boxes=boxes,
                det_time_ms=det_time,
                rec_time_ms=rec_time,
                total_time_ms=total_time
            )

        except Exception as e:
            print(f"[EasyOCR] ERROR during OCR processing: {e}")
            import traceback
            traceback.print_exc()
            return OcrOutput(boxes=[], total_time_ms=(time.perf_counter() - start_time) * 1000)

    def process_file(self, image_path: str) -> OcrOutput:
        """
        直接从文件路径执行OCR

        Args:
            image_path: 图像文件路径（PNG/JPG/BMP等）

        Returns:
            OcrOutput: OCR结果
        """
        if not os.path.exists(image_path):
            print(f"[EasyOCR] ERROR: File not found: {image_path}")
            return OcrOutput(boxes=[])

        # 读取图像
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"[EasyOCR] ERROR: Failed to read image: {image_path}")
            return OcrOutput(boxes=[])

        print(f"[EasyOCR] Processing file: {image_path} ({img.shape[1]}x{img.shape[0]})")

        # 执行OCR
        return self.process(img)

    def shutdown(self):
        """释放资源"""
        self._reader = None
        self._initialized = False
        print("[EasyOCR] Engine shutdown")
