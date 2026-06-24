"""
capture/capture.py — 图像采集模块

支持多种后端：
- directshow: OBS 虚拟摄像头 / 普通摄像头 (OpenCV CAP_DSHOW)
- screen: 直接屏幕捕获 (PIL ImageGrab / mss)
- dxgi: DXGI Desktop Duplication (未来)
"""
import cv2
import numpy as np
from typing import Optional

from ..config.settings import CaptureConfig


class CaptureBackend:
    """图像采集后端抽象基类"""

    def open(self) -> bool:
        raise NotImplementedError

    def read_frame(self) -> Optional[np.ndarray]:
        """读取一帧，返回 BGR numpy 数组；失败返回 None"""
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    @property
    def is_opened(self) -> bool:
        raise NotImplementedError


class DirectShowCapture(CaptureBackend):
    """
    DirectShow 采集后端
    通过 OpenCV VideoCapture + CAP_DSHOW 读取 OBS 虚拟摄像头或普通摄像头
    """

    def __init__(self, config: CaptureConfig):
        self._camera_index = config.camera_index
        self._fps = config.fps
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            print(f"[Capture] Failed to open camera index {self._camera_index} via DirectShow")
            return False
        self._cap.set(cv2.CAP_PROP_FPS, self._fps)
        # 尽量提高分辨率
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        print(f"[Capture] Opened camera {self._camera_index}, "
              f"resolution={int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
              f"{int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}, "
              f"fps={self._cap.get(cv2.CAP_PROP_FPS):.1f}")
        return True

    def read_frame(self) -> Optional[np.ndarray]:
        if self._cap is None or not self._cap.isOpened():
            return None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return None
        return frame

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()


class ScreenCapture(CaptureBackend):
    """
    屏幕捕获后端
    直接截取桌面画面，不依赖摄像头。
    支持全屏或指定区域捕获。

    后端选择：优先 mss（高性能），回退 PIL ImageGrab。
    """

    def __init__(self, config: CaptureConfig):
        self._fps = config.fps
        self._monitor: int = getattr(config, 'monitor', 0)  # 0=全屏, 1=主显示器
        self._region: Optional[tuple[int, int, int, int]] = getattr(config, 'region', None)
        self._backend: str = "mss"  # mss | pil
        self._sct = None

    def open(self) -> bool:
        # 尝试 mss
        try:
            import mss
            self._sct = mss.mss()
            monitor = self._sct.monitors[self._monitor] if self._monitor < len(self._sct.monitors) else self._sct.monitors[1]
            print(f"[Capture] Screen capture (mss): {monitor['width']}x{monitor['height']}")
            self._backend = "mss"
            return True
        except ImportError:
            pass

        # 回退 PIL
        try:
            from PIL import ImageGrab
            bbox = ImageGrab.grab().size
            print(f"[Capture] Screen capture (PIL): {bbox[0]}x{bbox[1]}")
            self._backend = "pil"
            return True
        except ImportError:
            print("[Capture] Neither mss nor PIL available. Install: pip install mss pillow")
            return False

    def read_frame(self) -> Optional[np.ndarray]:
        if self._backend == "mss" and self._sct is not None:
            try:
                import mss
                monitor = self._sct.monitors[self._monitor] if self._monitor < len(self._sct.monitors) else self._sct.monitors[1]
                if self._region:
                    region = {
                        "left": self._region[0], "top": self._region[1],
                        "width": self._region[2], "height": self._region[3],
                    }
                else:
                    region = monitor
                img = self._sct.grab(region)
                # BGRA → BGR
                frame = np.array(img, dtype=np.uint8)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                return frame
            except Exception as e:
                print(f"[Capture] mss grab error: {e}")
                return None

        elif self._backend == "pil":
            try:
                from PIL import ImageGrab
                bbox = self._region if self._region else None
                img = ImageGrab.grab(bbox=bbox)
                # PIL returns RGB
                frame = np.array(img, dtype=np.uint8)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                return frame
            except Exception as e:
                print(f"[Capture] PIL grab error: {e}")
                return None

        return None

    def close(self):
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None

    @property
    def is_opened(self) -> bool:
        return self._sct is not None or self._backend == "pil"


def create_capture(config: CaptureConfig) -> CaptureBackend:
    """工厂函数：根据配置创建采集后端"""
    if config.backend == "directshow":
        return DirectShowCapture(config)
    elif config.backend == "screen":
        return ScreenCapture(config)
    raise ValueError(f"Unknown capture backend: {config.backend}")
