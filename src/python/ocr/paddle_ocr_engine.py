# src/python/ocr/paddle_ocr_engine.py
"""
paddle_ocr_engine.py — 基于PaddleOCR的纯Python OCR引擎

支持PNG/JPG等图像文件的OCR识别，使用PP-OCRv5_mobile模型（本地部署）。
无需C++ DLL依赖，完全Python实现。
"""
import os
import sys
import numpy as np
import cv2
from typing import Optional, List, Tuple
from dataclasses import dataclass
import time

try:
    from paddleocr import PaddleOCR
    _HAS_PADDLEOCR = True
except ImportError:
    _HAS_PADDLEOCR = False
    print("[WARN] paddleocr not installed. Run: pip install paddleocr paddlepaddle")


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


class PaddleOcrEngine:
    """
    PaddleOCR引擎：封装PaddleOCR调用

    特性：
    - 支持PNG/JPG/BMP等图像格式
    - 自动处理深色背景反色
    - 可选的图像预处理（去噪、增强）
    - 完整的检测+识别流水线
    """

    def __init__(self, config):
        """
        初始化OCR引擎

        Args:
            config: AppConfig实例，包含OCR配置
        """
        self._config = config
        self._ocr_cfg = config.ocr

        # 预处理开关
        self._det_invert_dark = config.ocr.det_invert_dark
        self._det_denoise = config.ocr.det_denoise
        self._rec_enhance = config.ocr.rec_enhance

        # 置信度阈值
        self._min_confidence = config.ocr.min_confidence

        # PaddleOCR实例
        self._ocr: Optional[PaddleOCR] = None
        self._initialized = False

    def init(self) -> bool:
        """
        初始化PaddleOCR模型

        Returns:
            bool: 是否初始化成功
        """
        if not _HAS_PADDLEOCR:
            print("[OCR] ERROR: paddleocr not installed")
            print("[OCR] Please run: pip install paddleocr paddlepaddle")
            import sys; sys.stdout.flush()
            return False

        try:
            # 解析模型路径（相对于项目根目录）
            det_model_dir = self._config.resolve_path(self._ocr_cfg.det_model_dir)
            rec_model_dir = self._config.resolve_path(self._ocr_cfg.rec_model_dir)

            # 验证本地模型目录存在
            if not os.path.isdir(det_model_dir):
                print(f"[OCR] ERROR: Detection model directory not found: {det_model_dir}")
                import sys; sys.stdout.flush()
                return False
            if not os.path.isdir(rec_model_dir):
                print(f"[OCR] ERROR: Recognition model directory not found: {rec_model_dir}")
                import sys; sys.stdout.flush()
                return False

            print(f"[OCR] Initializing PaddleOCR (PP-OCRv5_mobile, local models)...")
            print(f"[OCR]   Det model: {det_model_dir}")
            print(f"[OCR]   Rec model: {rec_model_dir}")
            import sys; sys.stdout.flush()

            # 初始化PaddleOCR（使用本地PP-OCRv5_mobile模型）
            # 必须同时指定 model_name 和 model_dir，否则 PaddleOCR 默认使用 v6 名称
            # enable_mkldnn=False 避免某些CPU上的ONEDNN PIR兼容性问题
            self._ocr = PaddleOCR(
                text_detection_model_name='PP-OCRv5_mobile_det',
                text_detection_model_dir=det_model_dir,
                text_recognition_model_name='PP-OCRv5_mobile_rec',
                text_recognition_model_dir=rec_model_dir,
                use_doc_orientation_classify=False,   # 屏幕截屏无需文档方向分类
                use_doc_unwarping=False,              # 屏幕截屏无需文档展平
                use_textline_orientation=False,        # 屏幕截屏文本方向固定
                enable_mkldnn=False,    # 禁用MKLDNN以兼容当前Paddle版本
                cpu_threads=self._ocr_cfg.cpu_threads,
                text_det_thresh=self._ocr_cfg.det_threshold,
                text_det_box_thresh=self._ocr_cfg.box_threshold,
                text_rec_score_thresh=self._ocr_cfg.min_confidence,
                text_det_limit_side_len=self._ocr_cfg.det_resize_long,
            )

            self._initialized = True
            print("[OCR] PaddleOCR initialized successfully")
            import sys; sys.stdout.flush()
            return True

        except Exception as e:
            print(f"[OCR] ERROR: Failed to initialize PaddleOCR: {e}")
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
        if not self._initialized or self._ocr is None:
            print("[OCR] ERROR: Engine not initialized. Call init() first.")
            return OcrOutput(boxes=[])

        start_time = time.perf_counter()

        # 图像预处理
        processed_img = self._preprocess_image(img)

        # 执行OCR
        try:
            # PaddleOCR期望RGB图像
            rgb_img = cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB)

            # 调用PaddleOCR predict()（新版API）—— 计时
            predict_start = time.perf_counter()
            results = self._ocr.predict(rgb_img)
            predict_ms = (time.perf_counter() - predict_start) * 1000

            # 解析结果（新版返回OCRResult对象列表）
            boxes = []
            # predict() 是单一调用，无法分离 det/rec —— 全部计入 det_time
            det_time = predict_ms
            rec_time = 0.0

            if results:
                for page_result in results:
                    # page_result 是 OCRResult 对象
                    dt_polys = page_result.get("dt_polys", [])
                    rec_texts = page_result.get("rec_texts", [])
                    rec_scores = page_result.get("rec_scores", [])
                    rec_boxes = page_result.get("rec_boxes", None)
                    rec_polys = page_result.get("rec_polys", [])

                    if not rec_texts:
                        continue

                    for i, text in enumerate(rec_texts):
                        if not text or not text.strip():
                            continue

                        # 识别置信度
                        rec_conf = rec_scores[i] if i < len(rec_scores) else 0.0

                        # 过滤低置信度
                        if rec_conf < self._min_confidence:
                            continue

                        # 获取检测多边形（用于定位）
                        if rec_polys and i < len(rec_polys):
                            poly = rec_polys[i]
                            if isinstance(poly, np.ndarray):
                                points_list = [(float(p[0]), float(p[1])) for p in poly.reshape(-1, 2)]
                            else:
                                points_list = [(float(p[0]), float(p[1])) for p in poly]
                        elif dt_polys and i < len(dt_polys):
                            poly = dt_polys[i]
                            if isinstance(poly, np.ndarray):
                                points_list = [(float(p[0]), float(p[1])) for p in poly.reshape(-1, 2)]
                            else:
                                points_list = [(float(p[0]), float(p[1])) for p in poly]
                        elif rec_boxes is not None and i < len(rec_boxes):
                            # 使用识别框作为回退
                            box = rec_boxes[i]
                            x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
                            points_list = [
                                (float(x1), float(y1)),
                                (float(x2), float(y1)),
                                (float(x2), float(y2)),
                                (float(x1), float(y2)),
                            ]
                        else:
                            # 没有位置信息，跳过
                            continue

                        # 使用识别分数同时作为检测分数（新API不分离两者）
                        det_conf = rec_conf

                        boxes.append(TextBox(
                            points=points_list,
                            text=text.strip(),
                            det_score=det_conf,
                            rec_score=rec_conf,
                        ))

            total_time = (time.perf_counter() - start_time) * 1000

            return OcrOutput(
                boxes=boxes,
                det_time_ms=det_time,
                rec_time_ms=rec_time,
                total_time_ms=total_time
            )

        except Exception as e:
            print(f"[OCR] ERROR during OCR processing: {e}")
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
            print(f"[OCR] ERROR: File not found: {image_path}")
            return OcrOutput(boxes=[])

        # 读取图像
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"[OCR] ERROR: Failed to read image: {image_path}")
            return OcrOutput(boxes=[])

        print(f"[OCR] Processing file: {image_path} ({img.shape[1]}x{img.shape[0]})")

        # 执行OCR
        return self.process(img)

    def _preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """
        图像预处理

        Args:
            img: 原始BGR图像

        Returns:
            预处理后的图像
        """
        processed = img.copy()

        # 可选：深色背景反色
        if self._det_invert_dark:
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
            mean_brightness = np.mean(gray)
            if mean_brightness < 100:
                processed = cv2.bitwise_not(processed)
                print(f"[OCR] Dark background detected (brightness={mean_brightness:.1f}), inverting colors")

        # 可选：去噪
        if self._det_denoise:
            processed = cv2.GaussianBlur(processed, (3, 3), 0)

        # 可选：CLAHE对比度增强
        if self._rec_enhance:
            lab = cv2.cvtColor(processed, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            processed = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

        return processed

    def shutdown(self):
        """释放资源"""
        if self._ocr is not None and hasattr(self._ocr, 'close'):
            self._ocr.close()
        self._ocr = None
        self._initialized = False
        print("[OCR] Engine shutdown")


# 向后兼容别名
OcrEngine = PaddleOcrEngine


def create_ocr_engine(config) -> Optional[PaddleOcrEngine]:
    """
    工厂函数：创建并初始化OCR引擎

    Args:
        config: AppConfig实例

    Returns:
        PaddleOcrEngine实例或None
    """
    engine = PaddleOcrEngine(config)
    if not engine.init():
        return None
    return engine
