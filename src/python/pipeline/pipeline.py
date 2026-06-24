"""
pipeline/pipeline.py — 核心翻译流水线调度

完整流程：OCR 识别 → 合并相邻文本框 → 翻译 → 覆盖层显示
支持：划屏翻译（区域选择后原位覆盖）
"""
import threading
import time
import numpy as np
from typing import Optional, Callable

from ..config.settings import AppConfig
from ..ocr import OcrEngine, OcrOutput, TextBox, create_ocr_engine
from ..translator.translator import TranslatorBackend, create_translator, TranslationResult
from ..overlay.overlay import OverlayWindow, OverlayItem
from ..logger.cycle_logger import CycleLogger, CycleLog, TextBoxLog, Timer


class Pipeline:
    """
    翻译流水线管理器

    在独立线程中运行划屏翻译流程。
    通过回调函数与 GUI 通信。
    """

    def __init__(
        self,
        config: AppConfig,
        overlay: OverlayWindow,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_ocr_result: Optional[Callable[[int, list, float, float], None]] = None,
        on_translation_result: Optional[Callable[[int, list, float], None]] = None,
    ):
        self._config = config
        self._overlay = overlay
        self._on_status = on_status_change or (lambda s: None)
        self._on_ocr = on_ocr_result or (lambda cid, boxes, det_ms, rec_ms: None)
        self._on_trans = on_translation_result or (lambda cid, pairs, ms: None)

        # 模块
        self._ocr: Optional[OcrEngine] = None
        self._translator: Optional[TranslatorBackend] = None
        self._logger: Optional[CycleLogger] = None

        # 划屏翻译状态
        self._region_translate_running = False

    def init(self) -> bool:
        """初始化所有子模块"""
        self._on_status("Initializing...")

        # 先关闭旧的 OCR 引擎（如果有），再创建新的
        if self._ocr is not None:
            try:
                self._ocr.shutdown()
            except Exception:
                pass
            self._ocr = None

        # OCR（通过工厂函数选择引擎）
        engine_name = self._config.ocr.engine if hasattr(self._config.ocr, 'engine') else "paddle"
        print(f"[Pipeline] Creating OCR engine: {engine_name}")
        import sys; sys.stdout.flush()
        self._ocr = create_ocr_engine(self._config)
        if self._ocr is None:
            self._on_status("Warning: OCR init failed")
            print("[Pipeline] OCR engine creation returned None")
            import sys; sys.stdout.flush()
            return False
        print(f"[Pipeline] OCR engine created: {type(self._ocr).__name__}")
        import sys; sys.stdout.flush()

        # 翻译器
        try:
            self._translator = create_translator(self._config)
        except Exception as e:
            self._on_status(f"Error: Translator init failed: {e}")
            return False

        # 日志
        self._logger = CycleLogger(self._config)

        self._on_status("Ready")
        return True

    def run_region_translate(
        self, frame: np.ndarray, region_left: int, region_top: int,
        on_start=None, on_done=None,
    ):
        """执行划屏翻译（在后台线程中运行）

        使用屏幕截图代替摄像头帧，OCR + 翻译后将结果
        覆盖回原始屏幕区域。

        Args:
            frame: BGR numpy array — 从屏幕截取的区域图像
            region_left: 截图区域在屏幕上的左边界 x 坐标
            region_top: 截图区域在屏幕上的上边界 y 坐标
            on_start: 开始时的回调
            on_done: 完成时的回调
        """
        if self._region_translate_running:
            return  # 划屏翻译已在执行中

        def _region_shot():
            self._region_translate_running = True
            if on_start:
                on_start()
            try:
                self._on_status("Region: initializing...")
                if not self.init():
                    self._on_status("Region: init failed")
                    return
                self._on_status("Region: capturing...")
                self._execute_region_cycle(frame, region_left, region_top)
                self._on_status("Region: done")
            except Exception as e:
                self._on_status(f"Region: error: {e}")
            finally:
                self._region_translate_running = False
                if on_done:
                    on_done()

        threading.Thread(target=_region_shot, daemon=True).start()

    def shutdown(self):
        """释放所有资源"""
        if self._ocr:
            self._ocr.shutdown()
        if self._logger:
            self._logger.close()
        self._overlay.set_items([])

    def _execute_region_cycle(self, frame: np.ndarray, region_left: int, region_top: int):
        """执行划屏翻译周期 — 对屏幕截取的区域进行 OCR + 翻译 + 原位覆盖

        与简化前版本的区别：
        - 不进行图像下采样
        - 不进行翻译缓存
        - 添加相邻文本框合并
        """
        self._execute_region_cycle_impl(frame, region_left, region_top)

    def _execute_region_cycle_impl(self, frame: np.ndarray, region_left: int, region_top: int):
        """划屏翻译周期内部实现"""
        cycle_log = self._logger.new_cycle()
        timer = Timer()
        cycle_log.capture_ms = 0.0  # 区域截图在上层完成

        if frame is None:
            cycle_log.skipped = True
            cycle_log.skip_reason = "no_frame"
            self._logger.write_cycle(cycle_log)
            return

        # ── 1. OCR ──
        timer.start()
        ocr_result = self._ocr.process(frame) if self._ocr else OcrOutput(boxes=[])
        ocr_total_ms = timer.elapsed_ms()
        cycle_log.ocr_det_ms = ocr_total_ms
        cycle_log.ocr_rec_ms = 0.0

        boxes = ocr_result.boxes[:self._config.pipeline.max_text_boxes]

        # 过滤无意义的文本片段
        boxes = self._filter_meaningless_boxes(boxes)

        # 合并空间上相邻的文本框
        boxes = self._merge_adjacent_boxes(boxes)

        # 记录 OCR 结果到日志文件（含耗时）+ 通知 GUI
        if self._logger:
            self._logger.write_ocr_result(
                cycle_log.cycle_id, boxes,
                ocr_total_ms, 0.0,
            )
        self._on_ocr(cycle_log.cycle_id, boxes, ocr_total_ms, 0.0)

        if not boxes:
            cycle_log.skipped = True
            cycle_log.skip_reason = "no_text"
            self._overlay.set_items([])  # 原子清除（线程安全）
            self._logger.write_cycle(cycle_log)
            return

        # ── 2. 翻译 ──
        timer.start()
        texts = [tb.text for tb in boxes]

        translations: list[TranslationResult] = [None] * len(texts)

        # 并行翻译所有文本
        batch_results = self._translator.translate_batch(
            texts,
            self._config.source_lang,
            self._config.target_lang,
            parallel=self._config.translator.llama.parallel_requests,
        )
        for i in range(len(texts)):
            translations[i] = batch_results[i]

        cycle_log.translate_ms = timer.elapsed_ms()

        # 记录翻译结果到日志文件 + 通知 GUI
        if self._logger:
            trans_pairs = [
                (tb.text, (translations[i].text if translations[i] else ""),
                 (translations[i].status if translations[i] else "error"))
                for i, tb in enumerate(boxes)
            ]
            self._logger.write_translation_result(
                cycle_log.cycle_id, trans_pairs, cycle_log.translate_ms,
            )
        trans_pairs_gui = [
            (tb.text, (translations[i].text if translations[i] else ""),
             (translations[i].status if translations[i] else "error"))
            for i, tb in enumerate(boxes)
        ]
        self._on_trans(cycle_log.cycle_id, trans_pairs_gui, cycle_log.translate_ms)

        # ── 3. 覆盖层 — 坐标加上区域在屏幕上的偏移量 ──
        timer.start()

        overlay_items = []
        for i, (tb, trans_result) in enumerate(zip(boxes, translations)):
            x, y, w, h = tb.bounding_rect
            translated_text = trans_result.text if trans_result else tb.text
            status = trans_result.status if trans_result else "error"

            # 关键：覆盖层坐标 = 区域原点 + 文本框在区域内的相对坐标
            overlay_items.append(OverlayItem(
                x=region_left + x,
                y=region_top + y,
                w=w, h=h,
                text=translated_text,
                original_text=tb.text,
            ))

            cycle_log.text_boxes.append(TextBoxLog(
                original=tb.text,
                translated=translated_text,
                bbox=[region_left + x, region_top + y, w, h],
                det_score=tb.det_score,
                rec_score=tb.rec_score,
                translate_status=status,
            ))

        self._overlay.set_items(overlay_items)
        self._overlay.show_overlay()
        cycle_log.overlay_ms = timer.elapsed_ms()

        # ── 4. 日志 ──
        cycle_log.total_ms = (
            cycle_log.capture_ms + cycle_log.ocr_det_ms +
            cycle_log.ocr_rec_ms + cycle_log.translate_ms +
            cycle_log.overlay_ms
        )
        self._logger.write_cycle(cycle_log)

    @staticmethod
    def _filter_meaningless_boxes(boxes: list[TextBox]) -> list[TextBox]:
        """
        过滤无意义的文本片段

        规则：
        1. 长度小于2且不含字母的片段（如单个标点、数字）
        2. 纯标点符号
        3. 纯数字（除非包含特殊符号如$、%等）
        """
        meaningful_boxes = []
        for box in boxes:
            text = box.text.strip()

            # 空文本直接跳过
            if not text:
                continue

            # 长度>=2的保留
            if len(text) >= 2:
                meaningful_boxes.append(box)
                continue

            # 长度为1的情况
            if len(text) == 1:
                char = text[0]
                # 保留字母
                if char.isalpha():
                    meaningful_boxes.append(box)
                # 保留特殊符号（可能在上下文中重要）
                elif char in "$€£¥%°±×÷":
                    meaningful_boxes.append(box)
                # 其他单字符（标点、数字等）跳过
                else:
                    continue

        return meaningful_boxes

    @staticmethod
    def _merge_adjacent_boxes(boxes: list[TextBox]) -> list[TextBox]:
        """
        合并空间上相邻的文本框

        策略：
        1. 按Y坐标分组（同一行）
        2. 在同一行内，按X坐标排序
        3. 合并水平距离较近的文本框
        """
        if not boxes:
            return []

        # 按Y坐标分组（允许一定误差）
        y_tolerance = 10  # Y坐标容差
        rows = {}
        for box in boxes:
            y_center = (box.points[0][1] + box.points[2][1]) / 2
            row_key = round(y_center / y_tolerance) * y_tolerance

            if row_key not in rows:
                rows[row_key] = []
            rows[row_key].append(box)

        merged_boxes = []
        for row_key, row_boxes in rows.items():
            # 按X坐标排序
            row_boxes.sort(key=lambda b: b.points[0][0])

            # 合并相邻的文本框
            current_group = [row_boxes[0]]
            for box in row_boxes[1:]:
                last_box = current_group[-1]

                # 计算水平距离
                last_x_end = max(p[0] for p in last_box.points)
                curr_x_start = min(p[0] for p in box.points)
                gap = curr_x_start - last_x_end

                # 如果距离小于阈值，合并
                if gap < 30:  # 30像素以内的视为相邻
                    # 合并文本
                    merged_text = last_box.text + (" " if gap > 5 else "") + box.text

                    # 创建新的合并文本框
                    all_points = last_box.points + box.points
                    xs = [p[0] for p in all_points]
                    ys = [p[1] for p in all_points]

                    # 计算包围框
                    x_min, y_min = min(xs), min(ys)
                    x_max, y_max = max(xs), max(ys)

                    new_box = TextBox(
                        points=[
                            (x_min, y_min),
                            (x_max, y_min),
                            (x_max, y_max),
                            (x_min, y_max)
                        ],
                        text=merged_text,
                        det_score=min(last_box.det_score, box.det_score),
                        rec_score=min(last_box.rec_score, box.rec_score)
                    )
                    current_group[-1] = new_box
                else:
                    # 距离太远，开始新组
                    merged_boxes.extend(current_group)
                    current_group = [box]

            merged_boxes.extend(current_group)

        # 过滤掉太短的文本（可能是噪声）
        filtered_boxes = [
            box for box in merged_boxes
            if len(box.text.strip()) >= 2 or any(c.isalpha() for c in box.text)
        ]

        return filtered_boxes
