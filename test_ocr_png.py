# test_ocr_png.py
"""
test_ocr_png.py — PNG文件OCR识别测试脚本

用法:
    python test_ocr_png.py <image_path>

示例:
    python test_ocr_png.png test_image.png
"""
import sys
import os
import cv2
import numpy as np
from pathlib import Path
from typing import Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.python.config.settings import load_config
from src.python.ocr.paddle_ocr_engine import create_ocr_engine


def main():
    """主函数"""
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("Usage: python test_ocr_png.py <image_path>")
        print("\nExample:")
        print("  python test_ocr_png.py test_image.png")
        print("  python test_ocr_png.py screenshot.jpg")
        sys.exit(1)

    image_path = sys.argv[1]

    # 验证文件存在
    if not os.path.exists(image_path):
        print(f"ERROR: File not found: {image_path}")
        sys.exit(1)

    print("=" * 80)
    print("PNG File OCR Test")
    print("=" * 80)
    print(f"Image: {image_path}")
    print()

    # 加载配置
    print("[1/3] Loading configuration...")
    config = load_config()
    print(f"      Detection model: {config.ocr.det_model_dir}")
    print(f"      Recognition model: {config.ocr.rec_model_dir}")
    print(f"      Min confidence: {config.ocr.min_confidence}")
    print(f"      Preprocessing: invert={config.ocr.det_invert_dark}, "
          f"denoise={config.ocr.det_denoise}, enhance={config.ocr.rec_enhance}")
    print()

    # 创建OCR引擎
    print("[2/3] Initializing OCR engine...")
    engine = create_ocr_engine(config)
    if engine is None:
        print("ERROR: Failed to initialize OCR engine")
        sys.exit(1)
    print("      OCR engine ready")
    print()

    # 执行OCR
    print("[3/3] Performing OCR...")
    result = engine.process_file(image_path)

    # 显示结果
    print()
    print("=" * 80)
    print("OCR Results")
    print("=" * 80)
    print(f"Total time: {result.total_time_ms:.2f} ms")
    print(f"Detection time: {result.det_time_ms:.2f} ms")
    print(f"Recognition time: {result.rec_time_ms:.2f} ms")
    print(f"Text boxes found: {len(result.boxes)}")
    print("-" * 80)

    if not result.boxes:
        print("No text detected!")
    else:
        # 按Y坐标排序（从上到下）
        sorted_boxes = sorted(result.boxes, key=lambda b: min(p[1] for p in b.points))

        for i, box in enumerate(sorted_boxes, 1):
            x, y, w, h = box.bounding_rect
            print(f"[{i:2d}] Text: \"{box.text}\"")
            print(f"      BBox: ({x},{y},{w},{h})")
            print(f"      Confidence: det={box.det_score:.3f}, rec={box.rec_score:.3f}")
            print()

    # 生成可视化图像
    output_image = visualize_ocr_result(image_path, result)
    if output_image:
        print(f"Visualization saved to: {output_image}")

    # 清理资源
    engine.shutdown()

    print()
    print("=" * 80)
    print("Test completed successfully!")
    print("=" * 80)


def visualize_ocr_result(image_path: str, result) -> Optional[str]:
    """
    可视化OCR结果

    Args:
        image_path: 原始图像路径
        result: OCR结果

    Returns:
        可视化图像保存路径
    """
    try:
        # 读取原始图像
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            return None

        # 绘制文本框
        for box in result.boxes:
            # 绘制多边形
            points = np.array(box.points, dtype=np.int32)
            cv2.polylines(img, [points], True, (0, 255, 0), 2)

            # 绘制文本和置信度
            x, y, w, h = box.bounding_rect
            label = f"{box.text} ({box.rec_score:.2f})"
            cv2.putText(img, label, (x, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # 保存可视化图像
        base_name = Path(image_path).stem
        output_path = f"ocr_result_{base_name}.png"
        cv2.imwrite(output_path, img)

        return output_path

    except Exception as e:
        print(f"Warning: Failed to visualize OCR result: {e}")
        return None


if __name__ == "__main__":
    main()

