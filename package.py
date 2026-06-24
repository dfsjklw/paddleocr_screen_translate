"""
package.py — 打包脚本

将项目打包为可部署的 zip 文件（不含 llama.cpp 和 OBS）。
"""
import os
import shutil
import zipfile
from datetime import datetime

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DIST_DIR = os.path.join(_BASE_DIR, "dist")

# 要包含的文件/目录
_INCLUDE = [
    "main.py",
    "config.yaml",
    "requirements.txt",
    "src/",
    "build/bin/",            # 编译后的 DLL
    "PP-OCRv5_mobile_det_infer/",
    "PP-OCRv5_mobile_rec_infer/",
]

# 排除的模式
_EXCLUDE = [
    "__pycache__",
    ".pyc",
    ".git",
    ".idea",
    ".venv",
    "opencv/",
    "paddle_inference/",
    "llama/",
    "logs/",
    "build/CMake",
    "build/Release",
    "build/Debug",
]


def should_include(path: str) -> bool:
    for ex in _EXCLUDE:
        if ex in path:
            return False
    return True


def package():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"screen_translate_{timestamp}.zip"
    zip_path = os.path.join(_DIST_DIR, zip_name)

    os.makedirs(_DIST_DIR, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pattern in _INCLUDE:
            full_path = os.path.join(_BASE_DIR, pattern)

            if os.path.isfile(full_path):
                arc_name = os.path.join("screen_translate", pattern)
                if should_include(full_path):
                    zf.write(full_path, arc_name)
                    print(f"  + {pattern}")

            elif os.path.isdir(full_path):
                for root, dirs, files in os.walk(full_path):
                    # 过滤目录
                    dirs[:] = [d for d in dirs if should_include(d)]
                    for f in files:
                        file_path = os.path.join(root, f)
                        rel_path = os.path.relpath(file_path, _BASE_DIR)
                        if should_include(rel_path):
                            arc_name = os.path.join("screen_translate", rel_path)
                            zf.write(file_path, arc_name)

        # 添加启动脚本
        start_bat = "screen_translate_start.bat"
        bat_content = (
            "@echo off\r\n"
            "REM Screen Translate Launcher\r\n"
            "echo Starting Screen Translate...\r\n"
            "echo.\r\n"
            "echo Make sure llama.cpp server is running!\r\n"
            "echo.\r\n"
            "python main.py\r\n"
            "pause\r\n"
        )
        zf.writestr(os.path.join("screen_translate", start_bat), bat_content)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"\nPackage created: {zip_path}")
    print(f"Size: {size_mb:.1f} MB")
    print("\nNOTE: User must provide their own:")
    print("  - llama.cpp (llama-server.exe)")
    print("  - Translation model (.gguf)")
    print("  - OBS (if using virtual camera mode)")


if __name__ == "__main__":
    package()
