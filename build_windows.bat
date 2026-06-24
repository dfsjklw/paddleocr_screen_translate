@echo off
REM Screen Translate — Windows 构建脚本
REM 编译 OCR Bridge C++ DLL

setlocal enabledelayedexpansion

echo ==========================================
echo   Screen Translate Build Script
echo ==========================================

REM 检查 CMake
where cmake >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] CMake not found. Please install CMake 3.16+
    exit /b 1
)

REM 定位 vswhere
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"

REM 检查 MSVC 编译器
where cl >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] MSVC cl.exe not in PATH, trying to find Visual Studio...

    if not exist "!VSWHERE!" (
        echo [ERROR] Visual Studio not found. Please run from a Developer Command Prompt.
        exit /b 1
    )

    for /f "usebackq tokens=*" %%i in (`"!VSWHERE!" -latest -property installationPath`) do (
        set "VS_PATH=%%i"
    )

    if not defined VS_PATH (
        echo [ERROR] Visual Studio installation not found.
        exit /b 1
    )

    echo [INFO] Found Visual Studio at: !VS_PATH!
    call "!VS_PATH!\VC\Auxiliary\Build\vcvars64.bat"
)

REM 自动检测 Visual Studio 版本
if not exist "!VSWHERE!" (
    echo [WARN] vswhere not found, defaulting to Visual Studio 17 2022
    set "CMAKE_GENERATOR=Visual Studio 17 2022"
) else (
    for /f "delims=. tokens=1" %%a in ('"!VSWHERE!" -latest -property installationVersion') do (
        set "VS_MAJOR=%%a"
    )

    if "!VS_MAJOR!"=="18" (
        set "CMAKE_GENERATOR=Visual Studio 18 2026"
    ) else if "!VS_MAJOR!"=="17" (
        set "CMAKE_GENERATOR=Visual Studio 17 2022"
    ) else (
        echo [WARN] Unknown VS version !VS_MAJOR!, defaulting to Visual Studio 17 2022
        set "CMAKE_GENERATOR=Visual Studio 17 2022"
    )
)
echo [INFO] Using CMake generator: !CMAKE_GENERATOR!

echo.
echo [BUILD] Configuring CMake...
echo.

REM 创建 build 目录
if not exist build mkdir build
cd build

REM 清理旧的 CMake 缓存（生成器可能不匹配）
if exist CMakeCache.txt (
    findstr /C:"!CMAKE_GENERATOR!" CMakeCache.txt >nul 2>nul
    if errorlevel 1 (
        echo [INFO] Cleaning stale CMake cache ^(generator mismatch^)...
        del /q CMakeCache.txt >nul 2>nul
        if exist CMakeFiles rmdir /s /q CMakeFiles >nul 2>nul
    )
)

REM CMake 配置
cmake .. -G "!CMAKE_GENERATOR!" -A x64 -DCMAKE_BUILD_TYPE=Release

if %errorlevel% neq 0 (
    echo [ERROR] CMake configuration failed.
    cd ..
    exit /b 1
)

echo.
echo [BUILD] Building...
echo.

REM 编译
cmake --build . --config Release --parallel

if %errorlevel% neq 0 (
    echo [ERROR] Build failed.
    cd ..
    exit /b 1
)

cd ..

echo.
echo ==========================================
echo   Build successful!
echo   Output: build\bin\ocr_bridge.dll
echo ==========================================

REM 显示输出文件
if exist build\bin\ocr_bridge.dll (
    echo.
    echo Files in build\bin\:
    dir build\bin\*.dll /b
)

endlocal
