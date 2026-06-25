"""Export PP-OCRv5_mobile_det PIR model to ONNX.

Works around two issues:
1. paddle2onnx hard-blocks paddle 3.0.0 on Windows (monkey-patched)
2. paddle2onnx_cpp2py_export.pyd depends on libpaddle.pyd/common.dll/mkldnn.dll/phi.dll
   which are in paddle/base/ and paddle/libs/, not on the standard DLL search path.
   We pre-load these dependencies with ctypes before importing paddle2onnx.
"""

import importlib.metadata
import sys
import os
import ctypes

# ── Locate paddle directories ───────────────────────────────────
_PADDLE_BASE = (
    r"C:\Users\lol\AppData\Local\Programs\Python\Python312"
    r"\Lib\site-packages\paddle"
)
_LIBS = os.path.join(_PADDLE_BASE, "libs")
_BASE = os.path.join(_PADDLE_BASE, "base")

# Register DLL directories (for Python 3.8+ DLL loading)
for _d in (_LIBS, _BASE, _PADDLE_BASE):
    if os.path.isdir(_d):
        try:
            os.add_dll_directory(_d)
            print(f"[DLL dir] {_d}")
        except OSError:
            pass

# ── Pre-load dependent DLLs in correct order ────────────────────
# paddle2onnx_cpp2py_export.pyd depends on:
#   libpaddle.pyd -> phi.dll, common.dll, mkldnn.dll
# We load leaf dependencies first, then libpaddle, then paddle2onnx

print("[Preload] Loading leaf DLLs from paddle/libs ...")
for _name in ["mkldnn.dll", "phi.dll", "common.dll"]:
    _path = os.path.join(_LIBS, _name)
    if os.path.isfile(_path):
        try:
            ctypes.CDLL(_path)
            print(f"  OK: {_name}")
        except Exception as _e:
            print(f"  FAIL: {_name} -> {_e}")

print("[Preload] Loading libpaddle.pyd from paddle/base ...")
_libpaddle_path = os.path.join(_BASE, "libpaddle.pyd")
if os.path.isfile(_libpaddle_path):
    try:
        ctypes.CDLL(_libpaddle_path)
        print(f"  OK: libpaddle.pyd")
    except Exception as _e:
        print(f"  FAIL: libpaddle.pyd -> {_e}")
else:
    print(f"  NOT FOUND: {_libpaddle_path}")

# ── Monkey-patch version check ──────────────────────────────────
_original_version = importlib.metadata.version

def _patched_version(package_name):
    v = _original_version(package_name)
    if package_name in ("paddlepaddle", "paddlepaddle-gpu") and v == "3.0.0":
        return "3.0.0.post0"
    return v

importlib.metadata.version = _patched_version

# ── Now import paddle and paddle2onnx ───────────────────────────
import paddle
print(f"paddle: {paddle.__version__}")

import paddle2onnx
print(f"paddle2onnx: {paddle2onnx.__version__}")

# ── Load model and export ───────────────────────────────────────
model_dir = r"C:\Software\screen_translate\PP-OCRv5_mobile_det_infer"
model = paddle.jit.load(os.path.join(model_dir, "inference"))

input_spec = paddle.static.InputSpec(
    shape=[-1, 3, -1, -1], dtype="float32", name="x"
)

output_path = r"C:\Software\PP-OCRv5_mobile_det.onnx"
paddle.onnx.export(
    model,
    output_path,
    input_spec=[input_spec],
    opset_version=7,
)

size_mb = os.path.getsize(output_path) / (1024 * 1024)
print(f"Done: {output_path} ({size_mb:.1f} MB)")
