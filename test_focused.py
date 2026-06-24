"""
Focused end-to-end test: OCR engine switching + Overlay rendering

Usage: python test_focused.py
"""
import sys
import os
import time

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

import numpy as np
import cv2
import wx

from src.python.config.settings import load_config
from src.python.capture.capture import create_capture
from src.python.ocr import create_ocr_engine, PaddleOcrEngine, EasyOcrEngine
from src.python.overlay.overlay import OverlayWindow, OverlayItem


def run_tests():
    config_path = os.path.join(_BASE_DIR, "config.yaml")
    config = load_config(config_path)

    total = 0; passed = 0; failed = 0

    def check(name, condition, detail=""):
        nonlocal total, passed, failed
        total += 1
        status = "PASS" if condition else "FAIL"
        msg = f"  [{status}] {name}"
        if detail and not condition:
            msg += f" -- {detail}"
        print(msg)
        if condition: passed += 1
        else: failed += 1
        return condition

    print("=" * 60)
    print("  Focused Test: OCR Switching + Overlay")
    print("=" * 60)

    # ── Setup: wx App (required for overlay) ──
    app = wx.App(redirect=False)

    # ── Setup: capture a test frame ──
    print("\n-- 0. Setup: Capture test frame --")
    capture = create_capture(config.capture)
    check("Capture created", capture is not None)
    check("Camera opened", capture.open())
    frame = None
    for _ in range(5):
        frame = capture.read_frame()
    check("Test frame captured", frame is not None)
    if frame is not None:
        h, w = frame.shape[:2]
        print(f"    Resolution: {w}x{h}")

    # ==============================================================
    # 1. OCR ENGINE SWITCHING TESTS
    # ==============================================================
    print("\n" + "=" * 60)
    print("  1. OCR Engine Switching Tests")
    print("=" * 60)

    # 1a. Create PaddleOCR, run, shutdown
    print("\n-- 1a. PaddleOCR -> process -> shutdown --")
    config.ocr.engine = "paddle"
    paddle = create_ocr_engine(config)
    check("PaddleOCR created", paddle is not None)
    check("PaddleOCR is PaddleOcrEngine", isinstance(paddle, PaddleOcrEngine))

    if paddle and frame is not None:
        t0 = time.perf_counter()
        result_paddle = paddle.process(frame)
        t_paddle = (time.perf_counter() - t0) * 1000
        boxes_p = len(result_paddle.boxes)
        print(f"    PaddleOCR: {boxes_p} boxes in {t_paddle:.0f}ms")
        check("PaddleOCR found text", boxes_p > 0)

    paddle.shutdown()
    check("PaddleOCR shutdown OK", True)
    print("    PaddleOCR shutdown complete")

    # 1b. Switch to EasyOCR, run
    print("\n-- 1b. Switch -> EasyOCR -> process --")
    config.ocr.engine = "easyocr"
    config.ocr.easyocr_languages = ["en"]
    easy = create_ocr_engine(config)
    check("EasyOCR created", easy is not None)
    check("EasyOCR is EasyOcrEngine", isinstance(easy, EasyOcrEngine))

    if easy and frame is not None:
        t0 = time.perf_counter()
        result_easy = easy.process(frame)
        t_easy = (time.perf_counter() - t0) * 1000
        boxes_e = len(result_easy.boxes)
        print(f"    EasyOCR: {boxes_e} boxes in {t_easy:.0f}ms")
        check("EasyOCR found text", boxes_e > 0)

        # Show comparison
        print(f"\n    Comparison:")
        print(f"      PaddleOCR: {boxes_p} boxes, {t_paddle:.0f}ms")
        print(f"      EasyOCR:   {boxes_e} boxes, {t_easy:.0f}ms")

    # 1c. Switch back to PaddleOCR (re-init test)
    print("\n-- 1c. Switch back -> PaddleOCR (re-init) --")
    easy.shutdown()
    config.ocr.engine = "paddle"
    paddle2 = create_ocr_engine(config)
    check("PaddleOCR re-created after EasyOCR", paddle2 is not None)
    check("PaddleOCR is PaddleOcrEngine", isinstance(paddle2, PaddleOcrEngine))

    if paddle2 and frame is not None:
        t0 = time.perf_counter()
        result_paddle2 = paddle2.process(frame)
        t_paddle2 = (time.perf_counter() - t0) * 1000
        boxes_p2 = len(result_paddle2.boxes)
        print(f"    PaddleOCR (re-init): {boxes_p2} boxes in {t_paddle2:.0f}ms")
        check("PaddleOCR re-init found text", boxes_p2 > 0)
        # Results should be similar to first run
        check("PaddleOCR re-init consistent box count",
              abs(boxes_p2 - boxes_p) <= max(3, boxes_p * 0.3),
              f"first={boxes_p}, reinit={boxes_p2}")

    paddle2.shutdown()

    # 1d. Multiple rapid switches
    print("\n-- 1d. Rapid engine switching (3x) --")
    switches_ok = True
    for i in range(3):
        for eng_name in ["paddle", "easyocr"]:
            config.ocr.engine = eng_name
            eng = create_ocr_engine(config)
            if eng is None:
                switches_ok = False
                print(f"    FAIL: switch #{i+1} {eng_name} returned None")
                break
            if eng and frame is not None:
                result = eng.process(frame)
                if len(result.boxes) == 0:
                    switches_ok = False
                    print(f"    FAIL: switch #{i+1} {eng_name} found 0 boxes")
            eng.shutdown()
        if not switches_ok:
            break
    check("Rapid switching (3x paddle<->easyocr) all OK", switches_ok)

    # ==============================================================
    # 2. 720P DOWNSCALE + COORDINATE RECOVERY TEST
    # ==============================================================
    print("\n" + "=" * 60)
    print("  2. 720p Downscale + Coordinate Recovery")
    print("=" * 60)

    if frame is not None:
        orig_h, orig_w = frame.shape[:2]
        max_size = 720
        scale_factor = 1.0
        if max(orig_w, orig_h) > max_size:
            scale_factor = max_size / max(orig_w, orig_h)

        check("Downscale triggered for >720p frame", scale_factor < 1.0,
              f"{orig_w}x{orig_h} -> scale={scale_factor:.3f}")

        if scale_factor < 1.0:
            new_w = int(orig_w * scale_factor)
            new_h = int(orig_h * scale_factor)
            scaled_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            check(f"Frame scaled: {orig_w}x{orig_h} -> {new_w}x{new_h}", True)

            # Run OCR on scaled frame
            config.ocr.engine = "paddle"
            paddle3 = create_ocr_engine(config)
            result_scaled = paddle3.process(scaled_frame)
            scaled_boxes = len(result_scaled.boxes)

            # Scale coordinates back
            inv_scale = 1.0 / scale_factor
            for box in result_scaled.boxes:
                box.points = [(p[0] * inv_scale, p[1] * inv_scale) for p in box.points]

            # Verify coordinates are in original space
            all_in_bounds = True
            for box in result_scaled.boxes:
                x, y, bw, bh = box.bounding_rect
                if x < 0 or y < 0 or x + bw > orig_w or y + bh > orig_h:
                    all_in_bounds = False
                    print(f"    OUT OF BOUNDS: bbox=({x},{y},{bw},{bh}), frame={orig_w}x{orig_h}")
                    break

            check("All scaled-back boxes within original frame bounds", all_in_bounds)
            check("Scaled+recovered found same text count as full-res",
                  abs(scaled_boxes - boxes_p) <= max(3, boxes_p * 0.3),
                  f"full={boxes_p}, scaled+recovered={scaled_boxes}")

            paddle3.shutdown()

    # ==============================================================
    # 3. OVERLAY RENDERING TEST
    # ==============================================================
    print("\n" + "=" * 60)
    print("  3. Overlay Rendering Test")
    print("=" * 60)

    overlay = OverlayWindow(config.overlay)
    check("Overlay created", overlay is not None)

    # Create test items
    items = [
        OverlayItem(x=100, y=100, w=300, h=40, text="Hello World", original_text="Hello"),
        OverlayItem(x=100, y=160, w=300, h=40, text="你好世界", original_text="你好"),
        OverlayItem(x=100, y=220, w=400, h=40, text="Test 测试 テスト", original_text="Test"),
    ]

    # Test set_items (triggers render)
    try:
        overlay.set_items(items)
        time.sleep(0.3)  # Let wx process CallAfter
        wx.Yield()
        check("Overlay set_items() no crash", True)
    except Exception as e:
        check("Overlay set_items() no crash", False, str(e))

    # Test show_overlay
    try:
        overlay.show_overlay()
        time.sleep(0.3)
        wx.Yield()
        check("Overlay show_overlay() no crash", True)
    except Exception as e:
        check("Overlay show_overlay() no crash", False, str(e))

    # Test clear
    try:
        overlay.set_items([])
        time.sleep(0.2)
        wx.Yield()
        check("Overlay clear (empty items) no crash", True)
    except Exception as e:
        check("Overlay clear no crash", False, str(e))

    # Test hide
    try:
        overlay.hide_overlay()
        time.sleep(0.2)
        wx.Yield()
        check("Overlay hide_overlay() no crash", True)
    except Exception as e:
        check("Overlay hide_overlay() no crash", False, str(e))

    # Test re-show after hide
    try:
        overlay.set_items(items)
        overlay.show_overlay()
        time.sleep(0.3)
        wx.Yield()
        check("Overlay re-show after hide no crash", True)
    except Exception as e:
        check("Overlay re-show after hide no crash", False, str(e))

    # ==============================================================
    # 4. DOWNSCALE TOGGLE CONFIG TEST
    # ==============================================================
    print("\n" + "=" * 60)
    print("  4. Downscale Toggle Config")
    print("=" * 60)

    check("downscale_max_size in config", hasattr(config.pipeline, 'downscale_max_size'),
          f"value={getattr(config.pipeline, 'downscale_max_size', 'MISSING')}")

    ds = config.pipeline.downscale_max_size
    check("downscale_max_size default is 720", ds == 720, f"got {ds}")

    # Toggle off
    config.pipeline.downscale_max_size = 0
    check("Toggle OFF: value=0", config.pipeline.downscale_max_size == 0)

    # Toggle on
    config.pipeline.downscale_max_size = 720
    check("Toggle ON: value=720", config.pipeline.downscale_max_size == 720)

    # ==============================================================
    # 5. OCR SWITCHING + OVERLAY INTEGRATION
    # ==============================================================
    print("\n" + "=" * 60)
    print("  5. OCR Switch + Overlay Integration")
    print("=" * 60)

    # Simulate: PaddleOCR -> overlay with results
    config.ocr.engine = "paddle"
    paddle_i = create_ocr_engine(config)
    result_i = paddle_i.process(frame)
    boxes_i = result_i.boxes[:5]

    overlay_items = []
    for box in boxes_i:
        x, y, w_box, h_box = box.bounding_rect
        overlay_items.append(OverlayItem(
            x=x, y=y, w=w_box, h=h_box,
            text=box.text, original_text=box.text,
        ))

    try:
        overlay.set_items(overlay_items)
        overlay.show_overlay()
        time.sleep(0.3)
        wx.Yield()
        check("PaddleOCR results -> overlay render OK", True)
    except Exception as e:
        check("PaddleOCR results -> overlay render OK", False, str(e))

    paddle_i.shutdown()

    # Switch to EasyOCR -> overlay with new results
    config.ocr.engine = "easyocr"
    config.ocr.easyocr_languages = ["en"]
    easy_i = create_ocr_engine(config)
    result_e = easy_i.process(frame)
    boxes_e = result_e.boxes[:5]

    overlay_items2 = []
    for box in boxes_e:
        x, y, w_box, h_box = box.bounding_rect
        overlay_items2.append(OverlayItem(
            x=x, y=y, w=w_box, h=h_box,
            text=box.text, original_text=box.text,
        ))

    try:
        overlay.set_items(overlay_items2)
        overlay.show_overlay()
        time.sleep(0.3)
        wx.Yield()
        check("EasyOCR results -> overlay render OK", True)
    except Exception as e:
        check("EasyOCR results -> overlay render OK", False, str(e))

    easy_i.shutdown()

    # Cleanup
    overlay.hide_overlay()
    overlay.set_items([])
    capture.close()
    app.Destroy()

    # ── Summary ──
    print("\n" + "=" * 60)
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("  *** ALL TESTS PASSED ***")
    else:
        print(f"  *** {failed} TEST(S) FAILED ***")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
