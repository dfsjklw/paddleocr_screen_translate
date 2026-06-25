@echo off
echo ==========================================
echo  PP-OCRv5 Mobile Det -> ONNX export
echo ==========================================
echo.

REM Use the standalone paddle2onnx CLI
C:\Users\lol\AppData\Local\Programs\Python\Python312\Scripts\paddle2onnx.exe ^
  --model_dir "C:\Software\screen_translate\PP-OCRv5_mobile_det_infer" ^
  --model_filename inference.json ^
  --params_filename inference.pdiparams ^
  --save_file "C:\Software\PP-OCRv5_mobile_det.onnx" ^
  --opset_version 7

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ==========================================
    echo  SUCCESS
    echo ==========================================
    dir "C:\Software\PP-OCRv5_mobile_det.onnx"
) else (
    echo.
    echo ==========================================
    echo  FAILED (exit code: %ERRORLEVEL%)
    echo ==========================================
    echo.
    echo If it failed with "version should not be less than 3.0.0.dev20250426",
    echo try running: export_onnx_fallback.cmd
)
pause
