#!/bin/bash
# Step 1: Install paddle 3.0.0 in Python 3.12
/c/Users/lol/AppData/Local/Programs/Python/Python312/python.exe -m pip install paddlepaddle==3.0.0

# Step 2: Verify paddle2onnx works
/c/Users/lol/AppData/Local/Programs/Python/Python312/python.exe -c "import paddle2onnx; print('paddle2onnx:', paddle2onnx.__version__)"

# Step 3: Export ONNX
/c/Users/lol/AppData/Local/Programs/Python/Python312/python.exe -c "
import paddle, os
model = paddle.jit.load(r'C:\Software\screen_translate\PP-OCRv5_mobile_det_infer\inference')
input_spec = paddle.static.InputSpec(shape=[-1, 3, -1, -1], dtype='float32', name='x')
paddle.onnx.export(model, r'C:\Software\PP-OCRv5_mobile_det.onnx', input_spec=[input_spec], opset_version=7)
print(f'Done: {os.path.getsize(r\"C:\\Software\\PP-OCRv5_mobile_det.onnx\")} bytes')
"
