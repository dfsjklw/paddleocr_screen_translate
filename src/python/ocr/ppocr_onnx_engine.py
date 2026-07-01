"""
ppocr_onnx_engine.py — 基于 ONNX Runtime 的 PP-OCRv6 引擎

直接加载 PP-OCRv6_small_det_onnx / PP-OCRv6_small_rec_onnx 目录下的
ONNX 模型进行文字检测与识别。

接口规范：TextBox / OcrOutput / init / process。
"""
import os
import time
import math
import numpy as np
import cv2
from typing import Optional, List, Tuple

from .types import TextBox, OcrOutput
from .directml import get_providers, create_dml_session_options


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _get_rotate_crop_image(img: np.ndarray, points: np.ndarray) -> np.ndarray:
    """对检测框做透视变换，得到矫正后的文本框图像"""
    box = np.array(points, dtype=np.float32)
    # 计算目标宽高
    w = int(max(
        np.linalg.norm(box[0] - box[1]),
        np.linalg.norm(box[2] - box[3]),
    ))
    h = int(max(
        np.linalg.norm(box[0] - box[3]),
        np.linalg.norm(box[1] - box[2]),
    ))
    if w < 1 or h < 1:
        return None
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(box, dst)
    warped = cv2.warpPerspective(img, M, (w, h), borderValue=0)
    return warped


def _sorted_4_points(box: np.ndarray) -> np.ndarray:
    """将 4 个点按 (tl, tr, br, bl) 顺时针排序"""
    # 按 x 排序
    sorted_x = box[np.argsort(box[:, 0]), :]
    # 左半: 按 y 升序 → tl, bl
    left = sorted_x[:2, :]
    left = left[np.argsort(left[:, 1]), :]
    # 右半: 按 y 升序 → tr, br
    right = sorted_x[2:, :]
    right = right[np.argsort(right[:, 1]), :]
    return np.array([left[0], right[0], right[1], left[1]], dtype=np.float32)


def _box_score_fast(prob_map: np.ndarray, poly: np.ndarray) -> float:
    """计算多边形区域内概率图的平均分"""
    h, w = prob_map.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [poly.astype(np.int32).reshape(-1, 1, 2)], 1)
    return float(np.mean(prob_map[mask > 0]))


def _unclip(poly: np.ndarray, unclip_ratio: float) -> np.ndarray:
    """用 pyclipper 对多边形做膨胀（pyclipper 要求 Python int）"""
    import pyclipper
    area = cv2.contourArea(poly)
    peri = cv2.arcLength(poly, True)
    distance = area * unclip_ratio / peri if peri > 0 else 0
    offset = pyclipper.PyclipperOffset()
    offset.AddPath(
        [[int(p[0]), int(p[1])] for p in poly],  # pyclipper needs native int
        pyclipper.JT_ROUND,
        pyclipper.ET_CLOSEDPOLYGON,
    )
    expanded = offset.Execute(distance)
    if not expanded:
        return poly
    return np.array(expanded[0], dtype=np.float32).reshape(-1, 2)


def _db_postprocess(
    prob_map: np.ndarray,
    ori_h: int,
    ori_w: int,
    box_thresh: float = 0.4,
    binary_thresh: float = 0.2,
    unclip_ratio: float = 1.4,
    max_candidates: int = 3000,
) -> Tuple[List[np.ndarray], List[float]]:
    """DB 后处理：概率图 -> 多边形框"""
    pred = prob_map.squeeze()  # [H, W]
    h, w = pred.shape

    # 二值化
    bitmap = (pred > binary_thresh).astype(np.uint8) * 255

    # 找轮廓
    contours, _ = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:max_candidates]

    boxes = []
    scores = []
    for contour in contours:
        # 用 minAreaRect 得到最小外接矩形 → 4 点
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)  # [4, 2]
        box = np.array(box, dtype=np.float32)

        # 较短边 < 3px 跳过
        sside = min(rect[1])
        if sside < 3:
            continue

        # 计算分数
        score = _box_score_fast(pred, box)
        if score < box_thresh:
            continue

        # unclip 膨胀
        new_poly = _unclip(box, unclip_ratio)
        if len(new_poly) < 4:
            continue

        # 膨胀后再取 minAreaRect
        rect2 = cv2.minAreaRect(new_poly.astype(np.int32).reshape(-1, 1, 2))
        final_box = cv2.boxPoints(rect2)

        # 排序
        final_box = _sorted_4_points(final_box)

        # 裁剪到图像边界
        final_box[:, 0] = np.clip(final_box[:, 0], 0, w - 1)
        final_box[:, 1] = np.clip(final_box[:, 1], 0, h - 1)

        # 缩放到原图尺寸
        final_box[:, 0] = final_box[:, 0] / w * ori_w
        final_box[:, 1] = final_box[:, 1] / h * ori_h

        boxes.append(final_box)
        scores.append(score)

    return boxes, scores


# ──────────────────────────────────────────────
# 主引擎
# ──────────────────────────────────────────────

class PpOcrOnnxEngine:
    """
    PP-OCRv6 ONNX 引擎：通过 onnxruntime 直接运行检测+识别模型
    """

    def __init__(self, config):
        self._config = config
        self._ocr_cfg = config.ocr

        # 模型目录
        self._det_model_dir = config.resolve_path(
            getattr(self._ocr_cfg, 'det_model_dir', './PP-OCRv6_small_det_onnx')
        )
        self._rec_model_dir = config.resolve_path(
            getattr(self._ocr_cfg, 'rec_model_dir', './PP-OCRv6_small_rec_onnx')
        )

        # 参数
        self._min_confidence = self._ocr_cfg.min_confidence
        self._det_box_thresh = getattr(self._ocr_cfg, 'det_box_thresh', 0.4)
        self._det_binary_thresh = getattr(self._ocr_cfg, 'det_binary_thresh', 0.2)
        self._det_unclip_ratio = getattr(self._ocr_cfg, 'det_unclip_ratio', 1.4)
        self._det_limit_side = getattr(self._ocr_cfg, 'det_limit_side', 960)
        self._use_directml = getattr(self._ocr_cfg, 'use_directml', False)

        # 运行时
        self._det_session = None
        self._rec_session = None
        self._character_map = []          # idx -> char
        self._blank_id = 0
        self._initialized = False

        # 识别批量推理参数
        self._rec_batch_size = getattr(self._ocr_cfg, 'rec_batch_size', 0)
        self._rec_downsample_ratio = 4.0   # 将在 init() 中通过 dummy 推理校准

    # ── 初始化 ──────────────────────────────

    def init(self) -> bool:
        """加载 ONNX 模型 + 字符表，创建推理会话"""
        import yaml

        det_onnx = os.path.join(self._det_model_dir, "inference.onnx")
        rec_onnx = os.path.join(self._rec_model_dir, "inference.onnx")
        rec_yml = os.path.join(self._rec_model_dir, "inference.yml")

        # 检查文件
        for path, desc in [(det_onnx, "detection onnx"), (rec_onnx, "recognition onnx")]:
            if not os.path.isfile(path):
                print(f"[OCR] ERROR: {desc} not found: {path}")
                return False

        # 加载字符表
        if not os.path.isfile(rec_yml):
            print(f"[OCR] ERROR: rec inference.yml not found: {rec_yml}")
            return False
        with open(rec_yml, "r", encoding="utf-8") as f:
            rec_cfg = yaml.safe_load(f)
        char_dict = rec_cfg.get("PostProcess", {}).get("character_dict", [])
        if not char_dict:
            print("[OCR] ERROR: character_dict is empty in inference.yml")
            return False
        # 构建字符映射
        # 模型的输出维度 = 6906 = 1 (blank) + 6904 (char_dict) + 1 (space)
        # 即: [blank, char0, char1, ..., charN, space]
        self._character_map = [''] + char_dict + [' ']
        self._blank_id = 0

        # 创建 ONNX Runtime 会话
        try:
            import onnxruntime as ort
        except ImportError:
            print("[OCR] ERROR: onnxruntime not installed. Run: pip install onnxruntime")
            return False

        # 选择 providers (可通过 DirectML 模块配置 GPU 加速)
        providers = get_providers(self._use_directml)

        try:
            so = create_dml_session_options(intra_op_threads=2)
            self._det_session = ort.InferenceSession(det_onnx, so, providers=providers)
            self._rec_session = ort.InferenceSession(rec_onnx, so, providers=providers)
        except Exception as e:
            print(f"[OCR] ERROR: Failed to create ONNX session: {e}")
            return False

        # 校验模型输出维度与字符表匹配
        rec_out_shape = self._rec_session.get_outputs()[0].shape
        if len(rec_out_shape) == 3:
            model_out_dim = rec_out_shape[2]
            if isinstance(model_out_dim, int) and model_out_dim > 0:
                if model_out_dim != len(self._character_map):
                    print(f"[OCR] WARN: model output dim={model_out_dim}, "
                          f"char_map len={len(self._character_map)}. "
                          f"Using standard mapping (blank at 0, space at 1).")

        self._initialized = True
        print(f"[OCR] PpOcrOnnx engine ready")
        print(f"[OCR]   Det model: {det_onnx}")
        print(f"[OCR]   Rec model: {rec_onnx}")
        print(f"[OCR]   Char dict size: {len(char_dict)}")
        print(f"[OCR]   GPU DirectML: {'enabled' if self._use_directml else 'disabled (CPU)'}")
        print(f"[OCR]   Rec batch size: {self._rec_batch_size} (0 = all)")

        # ── 用 dummy 推理校准下采样比率 ──
        try:
            dummy = np.zeros((1, 3, 48, 16), dtype=np.float32)
            out = self._rec_session.run(
                [self._rec_session.get_outputs()[0].name],
                {self._rec_session.get_inputs()[0].name: dummy}
            )[0]
            self._rec_downsample_ratio = 16.0 / out.shape[1]
            print(f"[OCR]   Rec downsample ratio: {self._rec_downsample_ratio:.2f}")
        except Exception as e:
            print(f"[OCR]   WARN: downsample ratio calc failed, using default 4.0 — {e}")

        return True

    # ── 主 OCR 方法 ─────────────────────────

    def process(self, img: np.ndarray) -> OcrOutput:
        """对输入图像执行完整 OCR 流水线"""
        if not self._initialized:
            print("[OCR] ERROR: Engine not initialized. Call init() first.")
            return OcrOutput(boxes=[])

        start_time = time.perf_counter()
        try:
            # 1. 检测阶段
            t0 = time.perf_counter()
            det_boxes = self._detect(img)
            det_time = (time.perf_counter() - t0) * 1000

            if not det_boxes:
                total = (time.perf_counter() - start_time) * 1000
                return OcrOutput(boxes=[], det_time_ms=det_time,
                                 rec_time_ms=0, total_time_ms=total)

            # 2. 识别阶段
            t0 = time.perf_counter()
            rec_results = self._recognize_batch(img, [b[0] for b in det_boxes])
            rec_time = (time.perf_counter() - t0) * 1000

            # 3. 组装结果
            boxes = []
            for (poly, det_score), (text, rec_score) in zip(det_boxes, rec_results):
                if not text or not text.strip():
                    continue
                if rec_score < self._min_confidence:
                    continue
                points = [(float(p[0]), float(p[1])) for p in poly]
                boxes.append(TextBox(
                    points=points,
                    text=text.strip(),
                    det_score=det_score,
                    rec_score=rec_score,
                ))

            total = (time.perf_counter() - start_time) * 1000
            return OcrOutput(
                boxes=boxes,
                det_time_ms=det_time,
                rec_time_ms=rec_time,
                total_time_ms=total,
            )

        except Exception as e:
            print(f"[OCR] ERROR during processing: {e}")
            import traceback
            traceback.print_exc()
            total = (time.perf_counter() - start_time) * 1000
            return OcrOutput(boxes=[], total_time_ms=total)

    # ── 检测 ────────────────────────────────

    def _detect(self, img: np.ndarray) -> List[Tuple[np.ndarray, float]]:
        """
        文字检测
        Returns: [(poly_4points, score), ...]
        """
        ori_h, ori_w = img.shape[:2]

        # 1. 预处理
        resized, scale_ratio = self._det_preprocess(img)

        # 2. 推理
        input_name = self._det_session.get_inputs()[0].name
        output_name = self._det_session.get_outputs()[0].name
        prob_map = self._det_session.run([output_name], {input_name: resized})[0]

        # 3. 后处理
        boxes, scores = _db_postprocess(
            prob_map[0],  # [1, 1, H, W] -> [H, W]
            ori_h,
            ori_w,
            box_thresh=self._det_box_thresh,
            binary_thresh=self._det_binary_thresh,
            unclip_ratio=self._det_unclip_ratio,
        )

        # 按分数降序排列
        idx = np.argsort(scores)[::-1]
        return [(boxes[i], scores[i]) for i in idx]

    def _det_preprocess(self, img: np.ndarray) -> Tuple[np.ndarray, float]:
        """检测模型预处理：resize + 归一化 + CHW"""
        h, w = img.shape[:2]

        # 等比缩放，长边 <= limit
        ratio = self._det_limit_side / max(h, w)
        if ratio < 1.0:
            new_h, new_w = int(h * ratio), int(w * ratio)
        else:
            new_h, new_w = h, w
            ratio = 1.0

        # padding 到 32 的倍数
        pad_h = math.ceil(new_h / 32) * 32
        pad_w = math.ceil(new_w / 32) * 32

        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # 创建 canvas 并贴图
        canvas = np.zeros((pad_h, pad_w, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized

        # 归一化 (BGR HWC -> CHW, float32, normalized)
        canvas = canvas.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        canvas = (canvas - mean) / std

        # HWC -> CHW
        canvas = canvas.transpose(2, 0, 1)  # [3, H, W]

        # batch dim
        canvas = np.expand_dims(canvas, axis=0)  # [1, 3, H, W]
        return canvas, ratio

    # ── 识别 ────────────────────────────────

    def _recognize_batch(
        self, img: np.ndarray, polys: List[np.ndarray]
    ) -> List[Tuple[str, float]]:
        """
        批量识别文本框（支持真 batch 推理）

        流程：全部 crop 预处理 → 按 rec_batch_size 分组 →
              每组 pad 到相同宽度 → 一次 session.run() → 按实际宽度截断解码

        Returns: [(text, confidence), ...]
        """
        if not polys:
            return []

        # ── 1. 预处理所有有效 crop ──
        valid = []  # [(orig_index, tensor), ...]
        for i, poly in enumerate(polys):
            crop = _get_rotate_crop_image(img, poly)
            if crop is None or crop.shape[0] < 2 or crop.shape[1] < 2:
                continue
            tensor = self._rec_preprocess(crop)  # [1, 3, 48, W]
            valid.append((i, tensor))

        results = [("", 0.0)] * len(polys)
        if not valid:
            return results

        # ── 2. 按配置确定每组大小 ──
        # rec_batch_size: 0 = 全部打包, 1 = 逐张, N = 每 N 个一组
        group_size = self._rec_batch_size
        if group_size <= 0:
            group_size = len(valid)

        # ── 3. 逐组 batch 推理 ──
        input_name = self._rec_session.get_inputs()[0].name
        output_name = self._rec_session.get_outputs()[0].name

        for start in range(0, len(valid), group_size):
            group = valid[start:start + group_size]
            indices, tensors = zip(*group)

            # 各 tensor 宽度及对应预期输出长度
            widths = [t.shape[3] for t in tensors]
            expected_lens = [int(w / self._rec_downsample_ratio) for w in widths]
            max_w = max(widths)

            # Padding 到组内最大宽度 → 拼接为真 batch
            batch_parts = []
            for t in tensors:
                if t.shape[3] < max_w:
                    pad_w = max_w - t.shape[3]
                    t = np.pad(t, ((0,0), (0,0), (0,0), (0, pad_w)),
                               mode='constant', constant_values=0)
                batch_parts.append(t)
            batched = np.concatenate(batch_parts, axis=0)  # [N, 3, 48, max_w]

            # 一次推理
            preds = self._rec_session.run([output_name], {input_name: batched})[0]
            # preds shape: [N, max_seq_len, num_classes]

            # 解码，每个按实际宽度截断
            for j, orig_idx in enumerate(indices):
                raw = preds[j]
                # 截断到预期长度，去除 padding 区域可能的 RNN 状态泄露
                seq = raw[:expected_lens[j]]
                text, conf = self._ctc_decode(seq)
                results[orig_idx] = (text, conf)

        return results

    def _rec_preprocess(self, crop: np.ndarray) -> np.ndarray:
        """识别模型预处理：resize 到高=48，归一化"""
        h, w = crop.shape[:2]
        target_h = 48
        ratio = target_h / h
        target_w = max(int(w * ratio), 16)  # 最小宽度 16

        resized = cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        # 归一化到 [0, 1]
        tensor = resized.astype(np.float32) / 255.0

        # HWC -> CHW
        tensor = tensor.transpose(2, 0, 1)  # [3, 48, W]
        tensor = np.expand_dims(tensor, axis=0)  # [1, 3, 48, W]
        return tensor

    def _ctc_decode(self, pred: np.ndarray) -> Tuple[str, float]:
        """CTC argmax 解码（batch / single 共用）"""
        pred_idx = pred.argmax(axis=1)  # [seq_len]
        pred_prob = pred.max(axis=1)    # [seq_len]

        max_idx = len(self._character_map) - 1

        # 去重 + 去空白
        decoded = []
        confs = []
        prev = self._blank_id
        for idx, prob in zip(pred_idx, pred_prob):
            c = int(idx)
            if c > max_idx:
                continue  # 越界保护
            if c != self._blank_id and c != prev:
                decoded.append(self._character_map[c])
                confs.append(float(prob))
            prev = c

        text = "".join(decoded)
        avg_conf = float(np.mean(confs)) if confs else 0.0
        return text, avg_conf

    def _rec_infer_single(self, tensor: np.ndarray) -> Tuple[str, float]:
        """单个 crop 的识别推理"""
        input_name = self._rec_session.get_inputs()[0].name
        output_name = self._rec_session.get_outputs()[0].name
        pred = self._rec_session.run([output_name], {input_name: tensor})[0]
        # pred shape: [1, seq_len, num_classes]
        return self._ctc_decode(pred[0])

    # ── 辅助方法 ────────────────────────────

    def process_file(self, image_path: str) -> OcrOutput:
        """从文件路径执行 OCR"""
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
        """释放资源"""
        self._det_session = None
        self._rec_session = None
        self._initialized = False
        print("[OCR] PpOcrOnnx engine shutdown")
