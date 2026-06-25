@echo off
C:\Users\lol\AppData\Local\Programs\Python\Python312\python.exe -m pip install paddlepaddle==3.0.0
if %ERRORLEVEL% EQU 0 (
    echo.
    echo === SUCCESS: paddle 3.0.0 installed ===
    echo Now run: C:\Users\lol\AppData\Local\Programs\Python\Python312\python.exe -c "import paddle2onnx; print(paddle2onnx.__version__)"
) else (
    echo === FAILED with exit code %ERRORLEVEL% ===
)
pause
