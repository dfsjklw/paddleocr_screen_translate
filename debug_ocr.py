"""Test OCR with PaddleOCR engine"""
import sys
sys.path.insert(0, '.')

import cv2
from src.python.config.settings import load_config
from src.python.ocr import PaddleOcrEngine, TextBox, OcrOutput

cfg = load_config()
engine = PaddleOcrEngine(cfg)
if not engine.init():
    print("Failed to initialize OCR engine")
    sys.exit(1)

img = cv2.imread("debug_doc_test.png")
if img is None:
    # Try alternate test image
    img = cv2.imread("test_ocr_png.png")
if img is None:
    print("No test image found (tried debug_doc_test.png, test_ocr_png.png)")
    sys.exit(1)

print(f"Image: {img.shape}")

# Run OCR
result: OcrOutput = engine.process(img)

print(f"\nDetected {len(result.boxes)} text boxes:")
print(f"  Detection time: {result.det_time_ms:.1f}ms")
print(f"  Recognition time: {result.rec_time_ms:.1f}ms")
print(f"  Total time: {result.total_time_ms:.1f}ms")

for i, box in enumerate(result.boxes, 1):
    x, y, w, h = box.bounding_rect
    print(f"  [{i}] \"{box.text}\" (det={box.det_score:.2f}, rec={box.rec_score:.2f}) "
          f"bbox=({x},{y},{w},{h})")

engine.shutdown()
