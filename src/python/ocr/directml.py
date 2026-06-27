"""
ocr/directml.py — ONNX DirectML Execution Provider 模块

提供 DirectML (GPU) 加速推理所需的辅助函数：
- 检测 DML 执行提供程序可用性
- 创建带 DML 的 InferenceSession 配置（含设备选择和内存限制）
- 自动回退到 CPU（日志记录原因）

在 config.yaml 中通过 ocr.use_directml 开启，不在 GUI 中显示。
"""

import sys
from typing import Optional


def is_directml_available() -> bool:
    """检查 onnxruntime 是否支持 DirectML 执行提供程序"""
    try:
        import onnxruntime as ort
        available = 'DmlExecutionProvider' in ort.get_available_providers()
        if available:
            print("[DirectML] DmlExecutionProvider is available")
        else:
            print("[DirectML] DmlExecutionProvider NOT available — will use CPU")
        sys.stdout.flush()
        return available
    except ImportError:
        print("[DirectML] onnxruntime not installed")
        return False
    except Exception as e:
        print(f"[DirectML] Error checking DML availability: {e}")
        return False


def get_providers(use_directml: bool) -> list[str]:
    """返回供 onnxruntime InferenceSession 使用的 providers 列表。

    当 use_directml=True 且 DML 可用时，优先使用 DmlExecutionProvider。
    否则仅使用 CPUExecutionProvider。
    """
    if use_directml and is_directml_available():
        print("[DirectML] Using DmlExecutionProvider + CPUExecutionProvider fallback")
        sys.stdout.flush()
        return ['DmlExecutionProvider', 'CPUExecutionProvider']

    if use_directml:
        print("[DirectML] DML requested but unavailable — falling back to CPU")
        sys.stdout.flush()

    return ['CPUExecutionProvider']


def create_dml_session_options(
    intra_op_threads: int = 2,
    enable_all_optimization: bool = True,
) -> 'onnxruntime.SessionOptions':
    """创建适用于 DML/CPU 的 SessionOptions。

    Args:
        intra_op_threads: 内部操作线程数（DML 下主要影响 CPU 辅助操作）
        enable_all_optimization: 是否启用全部图优化

    Returns:
        配置好的 SessionOptions 实例
    """
    import onnxruntime as ort

    so = ort.SessionOptions()
    if enable_all_optimization:
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = intra_op_threads

    # DML 特定选项：将所有可能算子分配到 GPU
    so.add_session_config_entry("session.set_denormal_as_zero", "1")

    return so
