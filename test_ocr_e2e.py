"""End-to-end test for PaddleOCR 3.0+ migration.

Creates a synthetic image with known English text, runs OCR,
and verifies correct detection.
"""
import sys
import os
import warnings

# Capture warnings to verify no deprecation/user warnings
_warnings_captured = []


def _capture_warning(message, category, *args, **kwargs):
    """Track all captured warnings for later assertion."""
    if issubclass(category, (DeprecationWarning, UserWarning)):
        _warnings_captured.append((category.__name__, str(message)))


warnings.showwarning = _capture_warning

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.python.config.settings import load_config
from src.python.ocr import PaddleOcrEngine, OcrOutput


def create_test_image(text="Hello World", size=(400, 100)):
    """Create a white image with black text."""
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Try to use a common font, fallback to default
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except (OSError, IOError):
        font = ImageFont.load_default()
    # Draw text centered
    draw.text((20, 30), text, fill=(0, 0, 0), font=font)
    return img


def main():
    print("=" * 60)
    print("PaddleOCR 3.0+ End-to-End Test")
    print("=" * 60)

    # We manually set the env before importing paddleocr
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", os.path.join(BASE_DIR, ".paddlex_cache"))

    # 1. Create test image
    test_text = "Hello World Test"
    print(f"\n[1/4] Creating test image with text: '{test_text}'")
    pil_img = create_test_image(test_text)
    # Convert PIL to BGR numpy array (as pipeline would provide)
    img_np = np.array(pil_img)
    img_bgr = img_np[:, :, ::-1].copy()  # RGB -> BGR
    print(f"       Image size: {img_bgr.shape[1]}x{img_bgr.shape[0]}")

    # 2. Load config and create engine
    print("\n[2/4] Initializing PaddleOCR engine...")
    cfg = load_config()
    engine = PaddleOcrEngine(cfg)
    success = engine.init()
    if not success:
        print("FATAL: Engine initialization failed!")
        return 1
    print("       Engine initialized successfully.")

    # 3. Run OCR
    print("\n[3/4] Running OCR on test image...")
    result: OcrOutput = engine.process(img_bgr)

    print(f"       Detected {len(result.boxes)} text box(es)")
    print(f"       Detection time: {result.det_time_ms:.1f}ms")
    print(f"       Total time: {result.total_time_ms:.1f}ms")

    for i, box in enumerate(result.boxes, 1):
        x, y, w, h = box.bounding_rect
        print(f"       [{i}] \"{box.text}\" (det={box.det_score:.2f}, rec={box.rec_score:.2f}) "
              f"bbox=({x},{y},{w},{h})")

    # 4. Cleanup
    print("\n[4/4] Shutting down engine...")
    engine.shutdown()

    errors = []

    # Check: at least one text box detected
    if len(result.boxes) == 0:
        errors.append("No text boxes detected!")
    else:
        # Check: at least one box contains something resembling "Hello"
        all_text = " ".join(b.text for b in result.boxes).lower()
        if "hello" not in all_text:
            errors.append(f"Expected 'hello' in OCR result, got: '{all_text}'")

    # Check: no deprecation or user warnings from paddleocr
    relevant_warnings = [
        (cat, msg) for cat, msg in _warnings_captured
        if "paddleocr" in msg.lower() or "paddle" in msg.lower() or "lang" in msg.lower()
    ]
    if relevant_warnings:
        for cat, msg in relevant_warnings:
            errors.append(f"Unwanted {cat}: {msg}")

    print("\n" + "=" * 60)
    if errors:
        print("TEST FAILED")
        for e in errors:
            print(f"  [FAIL] {e}")
        return 1
    else:
        print("TEST PASSED -- PaddleOCR 3.0+ migration successful!")
        print(f"  [OK] Text detected: {len(result.boxes)} box(es)")
        print(f"  [OK] No deprecation/user warnings")
        return 0


if __name__ == "__main__":
    sys.exit(main())
