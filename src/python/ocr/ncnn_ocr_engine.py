"""
ncnn_ocr_engine.py — 基于 screen_transalate_ocr.exe 的 OCR 引擎

调用编译好的 ncnn PaddleOCRv5 命令行工具进行文字检测与识别。
输出 TextBox / OcrOutput 格式，接口与原 Python OCR 引擎完全兼容。
"""
import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import numpy as np
import cv2
from typing import Optional, List, Tuple
from dataclasses import dataclass


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


class NcnnOcrEngine:
    """
    NCNN OCR 引擎：通过 subprocess 调用 screen_transalate_ocr.exe

    优势：
    - 无需 Python OCR 库依赖（paddleocr / easyocr）
    - 使用 ncnn 高性能推理框架
    - 模型编译为独立可执行文件，部署简单
    """

    def __init__(self, config):
        """
        初始化 OCR 引擎

        Args:
            config: AppConfig 实例，包含 OCR 配置
        """
        self._config = config
        self._ocr_cfg = config.ocr

        # 解析 exe 路径
        exe_path = config.resolve_path(self._ocr_cfg.exe_path)
        self._exe_path = exe_path
        self._exe_dir = os.path.dirname(os.path.abspath(exe_path))

        # 置信度阈值
        self._min_confidence = self._ocr_cfg.min_confidence

        # 检测参数
        self._det_box_thresh = getattr(self._ocr_cfg, 'det_box_thresh', 0.6)
        self._det_binary_thresh = getattr(self._ocr_cfg, 'det_binary_thresh', 0.3)

        # 识别过滤参数
        self._rec_char_thresh = getattr(self._ocr_cfg, 'rec_char_thresh', 0.0)
        self._rec_block_thresh = getattr(self._ocr_cfg, 'rec_block_thresh', 0.0)

        # 字典
        self._dict_name = getattr(self._ocr_cfg, 'dict_name', 'zh_dict.txt')

        # 超时
        self._timeout = getattr(self._ocr_cfg, 'timeout', 30)
        if self._timeout <= 0:
            self._timeout = 30

        self._initialized = False

    def init(self) -> bool:
        """
        验证 exe 和模型文件存在

        Returns:
            bool: 是否初始化成功
        """
        # 验证 exe 存在
        if not os.path.isfile(self._exe_path):
            print(f"[OCR] ERROR: OCR executable not found: {self._exe_path}")
            import sys; sys.stdout.flush()
            return False

        # 验证 weights 目录存在
        weights_dir = os.path.join(self._exe_dir, "weights")
        if not os.path.isdir(weights_dir):
            print(f"[OCR] ERROR: Weights directory not found: {weights_dir}")
            import sys; sys.stdout.flush()
            return False

        # 检查必要的模型文件
        required_files = [
            "PP_OCRv5_mobile_det.ncnn.param",
            "PP_OCRv5_mobile_det.ncnn.bin",
            "PP_OCRv5_mobile_rec.ncnn.param",
            "PP_OCRv5_mobile_rec.ncnn.bin",
        ]
        for fname in required_files:
            fpath = os.path.join(weights_dir, fname)
            if not os.path.isfile(fpath):
                print(f"[OCR] ERROR: Model file not found: {fpath}")
                import sys; sys.stdout.flush()
                return False

        self._initialized = True
        print(f"[OCR] NCNN OCR engine ready: {self._exe_path}")
        print(f"[OCR]   Weights: {weights_dir}")
        import sys; sys.stdout.flush()
        return True

    def process(self, img: np.ndarray) -> OcrOutput:
        """
        对输入图像执行完整 OCR 流水线

        将 numpy 数组写入临时 PNG 文件，调用 screen_transalate_ocr.exe
        进行处理，解析 JSON 输出。

        Args:
            img: BGR 图像 (numpy array, HWC)

        Returns:
            OcrOutput: 包含所有检测到的文本框
        """
        if not self._initialized:
            print("[OCR] ERROR: Engine not initialized. Call init() first.")
            return OcrOutput(boxes=[])

        start_time = time.perf_counter()
        temp_path = None

        try:
            # 1. 写入临时 PNG 文件
            fd, temp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            if not cv2.imwrite(temp_path, img):
                print("[OCR] ERROR: Failed to write temp image")
                return OcrOutput(boxes=[])

            # 2. 清除之前的 output/ 目录（确保没有残留结果）
            output_dir = os.path.join(self._exe_dir, "output")
            if os.path.isdir(output_dir):
                shutil.rmtree(output_dir, ignore_errors=True)

            # 3. 调用 screen_transalate_ocr.exe（带参数）
            cmd = [self._exe_path, "single", temp_path]

            # 检测参数
            cmd.extend(["--box-thresh", str(self._det_box_thresh)])
            cmd.extend(["--binary-thresh", str(self._det_binary_thresh)])

            # 识别过滤参数
            if self._rec_char_thresh > 0.0:
                cmd.extend(["--char-thresh", str(self._rec_char_thresh)])
            if self._rec_block_thresh > 0.0:
                cmd.extend(["--block-thresh", str(self._rec_block_thresh)])

            # 字典
            dict_path = os.path.join(self._exe_dir, "weights", self._dict_name)
            if os.path.isfile(dict_path):
                cmd.extend(["--dict", dict_path])
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self._exe_dir,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                )
                if result.returncode != 0:
                    print(f"[OCR] ERROR: OCR exe returned code {result.returncode}")
                    if result.stderr:
                        print(f"[OCR]   stderr: {result.stderr.strip()}")
                    import sys; sys.stdout.flush()
                    return OcrOutput(boxes=[])
            except subprocess.TimeoutExpired:
                print(f"[OCR] ERROR: OCR exe timed out after {self._timeout}s")
                import sys; sys.stdout.flush()
                return OcrOutput(boxes=[])
            except FileNotFoundError:
                print(f"[OCR] ERROR: OCR exe not found at {self._exe_path}")
                import sys; sys.stdout.flush()
                return OcrOutput(boxes=[])

            # 4. 读取输出 JSON
            output_json = os.path.join(output_dir, "output.json")
            if not os.path.isfile(output_json):
                print("[OCR] ERROR: output.json not found after OCR run")
                if result.stdout:
                    print(f"[OCR]   stdout: {result.stdout.strip()}")
                if result.stderr:
                    print(f"[OCR]   stderr: {result.stderr.strip()}")
                import sys; sys.stdout.flush()
                return OcrOutput(boxes=[])

            with open(output_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 5. 解析结果
            dt_polys = data.get("dt_polys", [])
            rec_texts = data.get("rec_texts", [])
            rec_scores = data.get("rec_scores", [])
            rec_char_avg_scores = data.get("rec_char_avg_scores", [])
            rec_polys = data.get("rec_polys", [])

            boxes = []
            for i, text in enumerate(rec_texts):
                if not text or not text.strip():
                    continue

                # 识别置信度 (优先用 rec_char_avg_scores — 即字符平均置信度)
                if rec_char_avg_scores and i < len(rec_char_avg_scores):
                    rec_conf = rec_char_avg_scores[i]
                elif rec_scores and i < len(rec_scores):
                    rec_conf = rec_scores[i]
                else:
                    rec_conf = 0.0

                # Python 侧二次过滤低置信度
                if rec_conf < self._min_confidence:
                    continue

                # 获取多边形坐标（优先 rec_polys，回退 dt_polys）
                if rec_polys and i < len(rec_polys):
                    poly = rec_polys[i]
                elif dt_polys and i < len(dt_polys):
                    poly = dt_polys[i]
                else:
                    # 没有位置信息，跳过
                    continue

                # 转换为 [(float, float), ...] 格式
                if isinstance(poly, np.ndarray):
                    points_list = [(float(p[0]), float(p[1])) for p in poly.reshape(-1, 2)]
                else:
                    points_list = [(float(p[0]), float(p[1])) for p in poly]

                boxes.append(TextBox(
                    points=points_list,
                    text=text.strip(),
                    det_score=rec_conf,  # exe 不分 det/rec 分数，统一用 rec_score
                    rec_score=rec_conf,
                ))

            total_time = (time.perf_counter() - start_time) * 1000

            return OcrOutput(
                boxes=boxes,
                det_time_ms=total_time,  # 无法分离 det/rec 耗时
                rec_time_ms=0.0,
                total_time_ms=total_time,
            )

        except json.JSONDecodeError as e:
            print(f"[OCR] ERROR: Failed to parse output.json: {e}")
            import sys; sys.stdout.flush()
            return OcrOutput(boxes=[], total_time_ms=(time.perf_counter() - start_time) * 1000)
        except Exception as e:
            print(f"[OCR] ERROR during OCR processing: {e}")
            import traceback
            traceback.print_exc()
            import sys; sys.stdout.flush()
            return OcrOutput(boxes=[], total_time_ms=(time.perf_counter() - start_time) * 1000)
        finally:
            # 6. 清理临时文件
            if temp_path and os.path.isfile(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def process_file(self, image_path: str) -> OcrOutput:
        """
        直接从文件路径执行 OCR

        Args:
            image_path: 图像文件路径（PNG/JPG/BMP等）

        Returns:
            OcrOutput: OCR 结果
        """
        if not os.path.exists(image_path):
            print(f"[OCR] ERROR: File not found: {image_path}")
            return OcrOutput(boxes=[])

        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"[OCR] ERROR: Failed to read image: {image_path}")
            return OcrOutput(boxes=[])

        print(f"[OCR] Processing file: {image_path} ({img.shape[1]}x{img.shape[0]})")
        return self.process(img)

    def shutdown(self):
        """释放资源（无操作，exe 由 OS 管理）"""
        self._initialized = False
        print("[OCR] Engine shutdown")


# 向后兼容别名
OcrEngine = NcnnOcrEngine
