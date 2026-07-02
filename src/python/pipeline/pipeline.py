"""
pipeline/pipeline.py — 核心翻译流水线调度

完整流程：采集帧 → OCR 识别 → 翻译 → 清除旧覆盖 → 覆盖新文本
支持：暂停/继续、差异检测跳过、周期计时
"""
import threading
import time
import numpy as np
import cv2
from typing import Optional, Callable

from ..config.settings import AppConfig
from ..capture.capture import CaptureBackend, create_capture
from ..ocr import OcrEngine, OcrOutput, TextBox, create_ocr_engine
from ..translator.translator import TranslatorBackend, create_translator, TranslationResult
from ..overlay.overlay import OverlayWindow, OverlayItem
from ..logger.cycle_logger import CycleLogger, CycleLog, TextBoxLog, Timer


class Pipeline:
    """
    翻译流水线管理器

    在独立线程中运行，执行周期性翻译流程。
    通过回调函数与 GUI 通信。
    """

    def __init__(
        self,
        config: AppConfig,
        overlay: OverlayWindow,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_cycle_complete: Optional[Callable[[CycleLog], None]] = None,
        on_ocr_result: Optional[Callable[[int, list, float, float], None]] = None,
        on_translation_result: Optional[Callable[[int, list, float], None]] = None,
    ):
        self._config = config
        self._overlay = overlay
        self._on_status = on_status_change or (lambda s: None)
        self._on_cycle = on_cycle_complete or (lambda c: None)
        self._on_ocr = on_ocr_result or (lambda cid, boxes, det_ms, rec_ms: None)
        self._on_trans = on_translation_result or (lambda cid, pairs, ms: None)

        # 模块
        self._capture: Optional[CaptureBackend] = None
        self._ocr: Optional[OcrEngine] = None
        self._translator: Optional[TranslatorBackend] = None
        self._logger: Optional[CycleLogger] = None

        # 状态
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 翻译结果缓存 (原文 → 译文)
        self._translation_cache: dict[str, str] = {}

    def init(self, skip_capture: bool = False) -> bool:
        """初始化所有子模块

        Args:
            skip_capture: 若为 True，跳过摄像头初始化（用于截屏式单次翻译/区域翻译）
        """
        self._on_status("Initializing...")

        # 捕获 — 可选（单次/区域翻译使用传入截图帧时跳过）
        if not skip_capture:
            try:
                self._capture = create_capture(self._config.capture)
                if not self._capture.open():
                    self._on_status("Error: Camera open failed")
                    return False
            except Exception as e:
                self._on_status(f"Error: {e}")
                return False
        else:
            self._capture = None

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

    def start(self):
        """启动流水线线程"""
        if self._running:
            return
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._on_status("Running")

    def stop(self):
        """停止流水线并清除覆盖层"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._overlay.hide_overlay()
        self._on_status("Stopped")

    def toggle_pause(self):
        """切换暂停/继续"""
        self._paused = not self._paused
        if self._paused:
            self._overlay.hide_overlay()
        status = "Paused" if self._paused else "Running"
        self._on_status(status)

    def run_once(self, on_start=None, on_done=None):
        """执行单次翻译（在后台线程中运行）

        Args:
            on_start: 开始单次翻译时的回调
            on_done: 单次翻译完成时的回调
        """
        if not hasattr(self, '_single_shot_running'):
            self._single_shot_running = False

        if self._single_shot_running:
            return  # 单次翻译已在执行中

        def _single_shot():
            self._single_shot_running = True
            if on_start:
                on_start()
            try:
                # 始终重新初始化以应用最新的配置（包括 OCR 引擎切换）
                self._on_status("Single: initializing...")
                if not self.init():
                    self._on_status("Single: init failed")
                    return
                self._on_status("Single: capturing...")
                self._execute_cycle()
                self._on_status("Single: done")
            except Exception as e:
                self._on_status(f"Single: error: {e}")
            finally:
                self._single_shot_running = False
                if on_done:
                    on_done()

        threading.Thread(target=_single_shot, daemon=True).start()

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
        if not hasattr(self, '_region_translate_running'):
            self._region_translate_running = False

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

    def run_fullscreen_translate(
        self, frame: np.ndarray,
        on_start=None, on_done=None,
    ):
        """执行单次全屏翻译（使用预截取的全屏截图帧）

        复用 region 翻译的 OCR → 翻译 → 覆盖路径，
        区域偏移为 (0, 0)，即使用全屏绝对坐标。
        初始化流水线时跳过摄像头采集。

        Args:
            frame: BGR numpy array — 全屏截图
            on_start: 开始回调（在后台线程中调用）
            on_done: 完成回调（在后台线程中调用）
        """
        if not hasattr(self, '_single_shot_running'):
            self._single_shot_running = False

        if self._single_shot_running:
            return  # 单次翻译已在执行中

        def _fullscreen_shot():
            self._single_shot_running = True
            if on_start:
                on_start()
            try:
                self._on_status("Single: initializing...")
                if not self.init(skip_capture=True):
                    self._on_status("Single: init failed")
                    return
                self._on_status("Single: capturing...")
                # _execute_region_cycle 内部加锁，region 偏移为 (0,0)
                # 即 OCR 返回的坐标直接作为全屏绝对坐标
                self._execute_region_cycle(frame, 0, 0)
                self._on_status("Single: done")
            except Exception as e:
                self._on_status(f"Single: error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self._single_shot_running = False
                if on_done:
                    on_done()

        threading.Thread(target=_fullscreen_shot, daemon=True).start()

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_running(self) -> bool:
        return self._running

    def shutdown(self):
        """释放所有资源"""
        self.stop()
        if self._capture:
            self._capture.close()
        if self._ocr:
            self._ocr.shutdown()
        if self._logger:
            self._logger.close()
        self._overlay.set_items([])

    def _run_loop(self):
        """主循环"""
        interval = self._config.pipeline.cycle_interval

        while self._running:
            if self._paused:
                time.sleep(0.1)
                continue

            cycle_start = time.perf_counter()
            self._execute_cycle()

            # 等待剩余时间以维持周期
            elapsed = time.perf_counter() - cycle_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _execute_cycle(self):
        """执行一个完整的翻译周期（线程安全）"""
        with self._lock:
            self._execute_cycle_impl()

    def _execute_cycle_impl(self):
        """执行一个完整的翻译周期（内部实现，调用方负责加锁）"""
        cycle_log = self._logger.new_cycle()
        timer = Timer()

        # ── 1. 采集帧 ──
        timer.start()
        frame = self._capture.read_frame()
        cycle_log.capture_ms = timer.elapsed_ms()

        if frame is None:
            cycle_log.skipped = True
            cycle_log.skip_reason = "no_frame"
            self._logger.write_cycle(cycle_log)
            return

        # ── 2. OCR ──
        timer.start()
        # 记录原始尺寸（用于后续坐标恢复）
        orig_h, orig_w = frame.shape[:2]

        # 小图放大预处理（如果宽或高 < 300px，等比例放大 3x）
        frame, upscale_factor = self._maybe_upscale(frame)

        scale_factor = 1.0
        max_size = self._config.pipeline.downscale_max_size
        if max_size > 0 and max(orig_w, orig_h) > max_size:
            scale_factor = max_size / max(orig_w, orig_h)
            new_w = int(orig_w * scale_factor)
            new_h = int(orig_h * scale_factor)
            ocr_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            ocr_frame = frame

        ocr_result = self._ocr.process(ocr_frame) if self._ocr else OcrOutput(boxes=[])
        ocr_total_ms = timer.elapsed_ms()
        # PaddleOCR predict() 是单一调用，无法分离 det/rec 耗时；
        # 使用总耗时作为 det_time，rec 置 0
        cycle_log.ocr_det_ms = ocr_total_ms
        cycle_log.ocr_rec_ms = 0.0

        boxes = ocr_result.boxes

        # 如果做了下采样，将 OCR 返回的坐标还原到原始图像空间
        if scale_factor < 1.0:
            inv_scale = 1.0 / scale_factor
            for box in boxes:
                box.points = [
                    (p[0] * inv_scale, p[1] * inv_scale) for p in box.points
                ]

        # 如果做了小图放大但未做下采样，将 OCR 坐标还原到原始图像空间
        if upscale_factor > 1.0 and scale_factor >= 1.0:
            inv_upscale = 1.0 / upscale_factor
            for box in boxes:
                box.points = [
                    (p[0] * inv_upscale, p[1] * inv_upscale) for p in box.points
                ]

        # 过滤无意义的文本片段
        boxes = self._filter_meaningless_boxes(boxes)

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

        # ── 4. 翻译 ──
        timer.start()
        texts = [tb.text for tb in boxes]
        # 使用缓存
        to_translate = []
        cache_hits = {}
        for i, text in enumerate(texts):
            if text in self._translation_cache:
                cache_hits[i] = self._translation_cache[text]
            else:
                to_translate.append((i, text))

        translations: list[TranslationResult] = [None] * len(texts)

        # 并行翻译未缓存的文本
        if to_translate:
            batch_texts = [t for _, t in to_translate]
            batch_results = self._translator.translate_batch(
                batch_texts,
                parallel=self._config.translator.llama.parallel_requests,
            )
            for j, (orig_idx, orig_text) in enumerate(to_translate):
                translations[orig_idx] = batch_results[j]
                if batch_results[j].status == "ok":
                    self._translation_cache[orig_text] = batch_results[j].text

        # 填充缓存命中
        for i, cached_text in cache_hits.items():
            translations[i] = TranslationResult(
                text=cached_text, original=texts[i], status="ok",
            )

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

        # ── 5. 覆盖层 ──
        timer.start()

        overlay_items = []
        for i, (tb, trans_result) in enumerate(zip(boxes, translations)):
            x, y, w, h = tb.bounding_rect
            translated_text = trans_result.text if trans_result else tb.text
            status = trans_result.status if trans_result else "error"

            overlay_items.append(OverlayItem(
                x=x, y=y, w=w, h=h,
                text=translated_text,
                original_text=tb.text,
            ))

            cycle_log.text_boxes.append(TextBoxLog(
                original=tb.text,
                translated=translated_text,
                bbox=[x, y, w, h],
                det_score=tb.det_score,
                rec_score=tb.rec_score,
                translate_status=status,
            ))

        # 原子替换覆盖项 + 显示（线程安全，单次 wx.CallAfter）
        self._overlay.set_items(overlay_items)
        cycle_log.overlay_ms = timer.elapsed_ms()

        # ── 6. 日志 ─
        cycle_log.total_ms = (
            cycle_log.capture_ms + cycle_log.ocr_det_ms +
            cycle_log.ocr_rec_ms + cycle_log.translate_ms +
            cycle_log.overlay_ms
        )
        self._logger.write_cycle(cycle_log)
        self._on_cycle(cycle_log)

    def _execute_region_cycle(self, frame: np.ndarray, region_left: int, region_top: int):
        """执行划屏翻译周期 — 对屏幕截取的区域进行 OCR + 翻译 + 原位覆盖

        与 _execute_cycle_impl 的区别：
        - 跳过摄像头采集步骤，直接使用传入的截屏帧
        - 覆盖层坐标 = region_offset + 文本框在区域内的相对坐标
        - 不进行差异检测
        """
        with self._lock:
            self._execute_region_cycle_impl(frame, region_left, region_top)

    def _execute_region_cycle_impl(self, frame: np.ndarray, region_left: int, region_top: int):
        """划屏翻译周期内部实现（调用方负责加锁）"""
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
        orig_h, orig_w = frame.shape[:2]

        # 小图放大预处理（如果宽或高 < 300px，等比例放大 3x）
        frame, upscale_factor = self._maybe_upscale(frame)

        scale_factor = 1.0
        max_size = self._config.pipeline.downscale_max_size
        if max_size > 0 and max(orig_w, orig_h) > max_size:
            scale_factor = max_size / max(orig_w, orig_h)
            new_w = int(orig_w * scale_factor)
            new_h = int(orig_h * scale_factor)
            ocr_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            ocr_frame = frame

        ocr_result = self._ocr.process(ocr_frame) if self._ocr else OcrOutput(boxes=[])
        ocr_total_ms = timer.elapsed_ms()
        cycle_log.ocr_det_ms = ocr_total_ms
        cycle_log.ocr_rec_ms = 0.0

        boxes = ocr_result.boxes

        # 将 OCR 坐标还原到原始图像空间
        if scale_factor < 1.0:
            inv_scale = 1.0 / scale_factor
            for box in boxes:
                box.points = [
                    (p[0] * inv_scale, p[1] * inv_scale) for p in box.points
                ]

        # 如果做了小图放大但未做下采样，将 OCR 坐标还原到原始图像空间
        if upscale_factor > 1.0 and scale_factor >= 1.0:
            inv_upscale = 1.0 / upscale_factor
            for box in boxes:
                box.points = [
                    (p[0] * inv_upscale, p[1] * inv_upscale) for p in box.points
                ]

        # 过滤无意义的文本片段
        boxes = self._filter_meaningless_boxes(boxes)

        if self._logger:
            self._logger.write_ocr_result(
                cycle_log.cycle_id, boxes, ocr_total_ms, 0.0,
            )
        self._on_ocr(cycle_log.cycle_id, boxes, ocr_total_ms, 0.0)

        if not boxes:
            cycle_log.skipped = True
            cycle_log.skip_reason = "no_text"
            self._overlay.set_items([])
            self._logger.write_cycle(cycle_log)
            return

        # ── 2. 翻译 ──
        timer.start()
        texts = [tb.text for tb in boxes]
        to_translate = []
        cache_hits = {}
        for i, text in enumerate(texts):
            if text in self._translation_cache:
                cache_hits[i] = self._translation_cache[text]
            else:
                to_translate.append((i, text))

        translations: list[TranslationResult] = [None] * len(texts)

        if to_translate:
            batch_texts = [t for _, t in to_translate]
            batch_results = self._translator.translate_batch(
                batch_texts,
                parallel=self._config.translator.llama.parallel_requests,
            )
            for j, (orig_idx, orig_text) in enumerate(to_translate):
                translations[orig_idx] = batch_results[j]
                if batch_results[j].status == "ok":
                    self._translation_cache[orig_text] = batch_results[j].text

        for i, cached_text in cache_hits.items():
            translations[i] = TranslationResult(
                text=cached_text, original=texts[i], status="ok",
            )

        cycle_log.translate_ms = timer.elapsed_ms()

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
        cycle_log.overlay_ms = timer.elapsed_ms()

        # ── 4. 日志 ──
        cycle_log.total_ms = (
            cycle_log.capture_ms + cycle_log.ocr_det_ms +
            cycle_log.ocr_rec_ms + cycle_log.translate_ms +
            cycle_log.overlay_ms
        )
        self._logger.write_cycle(cycle_log)
        self._on_cycle(cycle_log)

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

    def _maybe_upscale(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        """
        小图放大预处理。

        如果 upscale_small_image 开启且图像的宽或高小于 300 像素，
        则将其等比例放大 3 倍，以提高 OCR 识别小尺寸文本的成功率。

        Args:
            frame: BGR 输入图像 (numpy array)

        Returns:
            (放大后的图像, 放大倍数) — 未放大时倍数为 1.0
        """
        if not self._config.pipeline.upscale_small_image:
            return frame, 1.0

        h, w = frame.shape[:2]
        if w >= 300 and h >= 300:
            return frame, 1.0

        scale = 3.0
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        upscaled = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        print(f"[Pipeline] Upscaled small image {w}x{h} → {new_w}x{new_h}")
        return upscaled, scale

    def _merge_adjacent_boxes(self, boxes: list[TextBox]) -> list[TextBox]:
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
