"""
package.py — PyInstaller 打包脚本

构建独立的 ScreenTranslate.exe（Windows GUI 应用）。
模型文件和配置文件放置在 exe 同目录，方便用户编辑和切换模型变体。

用法:
    pip install pyinstaller
    python package.py

输出:
    dist/ScreenTranslate/
        ScreenTranslate.exe      # 主程序
        config.yaml              # 配置文件（用户可编辑）
        PP-OCRv6_small_det_onnx/ # 模型目录（用户可增删/切换）
        PP-OCRv6_small_rec_onnx/
        PP-OCRv6_tiny_det_onnx/
        PP-OCRv6_tiny_rec_onnx/
"""
import os
import sys
import shutil
import subprocess
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent.resolve()
DIST_DIR = ROOT_DIR / "dist" / "ScreenTranslate"
TEMP_DIR = ROOT_DIR / "dist_temp"


def find_pyinstaller() -> str:
    """查找 pyinstaller 可执行文件路径"""
    scripts_dir = Path(sys.executable).parent
    pip_installed = scripts_dir / "pyinstaller.exe"
    if pip_installed.exists():
        return str(pip_installed)
    return f"{sys.executable} -m PyInstaller"


def remove_path(p: Path, label: str = ""):
    """尝试删除文件或目录，Windows 文件锁时等一会儿重试"""
    if not p.exists():
        return
    for attempt in range(3):
        try:
            if p.is_dir():
                shutil.rmtree(p, onexc=lambda *a: None)
            else:
                p.unlink()
            print(f"  [Clean] Removed {label}{p.name}")
            return
        except PermissionError:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  [Clean] Skipped (locked): {label}{p.name}")


def clean_artifacts():
    """清理上次构建的残留文件"""
    print("[Clean] Cleaning previous build artifacts...")
    remove_path(ROOT_DIR / "build", "build/")
    remove_path(ROOT_DIR / "ScreenTranslate.spec")
    # dist 可能被 Windows Defender 锁定，不强求删除
    if (ROOT_DIR / "dist").exists():
        remove_path(ROOT_DIR / "dist")
    # temp 目录总是可删
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, onexc=lambda *a: None)
        print(f"  [Clean] Removed {TEMP_DIR.name}/")


def get_model_dirs() -> list[Path]:
    """扫描项目根目录下的 PP-OCRv6 模型目录"""
    return sorted([
        d for d in ROOT_DIR.iterdir()
        if d.is_dir()
        and d.name.startswith("PP-OCRv6_")
        and d.name.endswith("_onnx")
        and (d / "inference.onnx").exists()
    ])


def build_exe():
    """执行 PyInstaller 打包到临时目录"""
    pyinst = find_pyinstaller()

    cmd = [
        pyinst,
        "--noconfirm",
        "--clean",
        "--name", "ScreenTranslate",
        "--noconsole",
        "--onedir",
        f"--distpath={TEMP_DIR}",
        f"--workpath={ROOT_DIR / 'build'}",
        "--exclude-module", "tkinter",
        # 配置文件
        "--add-data", f"config.yaml{os.pathsep}.",
        # 隐式导入
        "--hidden-import", "yaml",
        "--hidden-import", "onnxruntime",
        "--hidden-import", "pyclipper",
        "--hidden-import", "keyboard",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.ImageGrab",
        "--hidden-import", "wx",
        "--hidden-import", "wx.adv",
        "--hidden-import", "wx.html2",
        str(ROOT_DIR / "main.py"),
    ]

    print(f"[Build] Running PyInstaller...")
    sys.stdout.flush()
    subprocess.check_call(cmd, cwd=ROOT_DIR)
    print("[Build] PyInstaller completed successfully.")
    sys.stdout.flush()


def copy_model_dirs(target_dir: Path):
    """将模型目录复制到目标目录"""
    model_dirs = get_model_dirs()
    if not model_dirs:
        print("[Warn] No PP-OCRv6 model directories found.")
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    for src in model_dirs:
        dst = target_dir / src.name
        if dst.exists():
            shutil.rmtree(dst)
        print(f"  [Copy] {src.name}/")
        shutil.copytree(src, dst)

    # 也复制 config.yaml
    shutil.copy2(ROOT_DIR / "config.yaml", target_dir / "config.yaml")
    print(f"  [Copy] config.yaml")

    print(f"  [Copy] Copied {len(model_dirs)} model directories.")


def finalize_output():
    """将临时目录移动到最终 dist 目录"""
    temp_out = TEMP_DIR / "ScreenTranslate"
    if not temp_out.exists():
        print(f"[Error] Build output not found at {temp_out}")
        sys.exit(1)

    # 复制模型到临时输出
    copy_model_dirs(temp_out)

    # 尝试替换最终 dist 目录
    if DIST_DIR.exists():
        print("[Finalize] Replacing old dist/ScreenTranslate/ ...")
        try:
            shutil.rmtree(DIST_DIR, onexc=lambda *a: None)
        except PermissionError:
            print("[Finalize] Old dist is locked — leaving output at dist_temp/")
            print(f"[Finalize] Output: {temp_out}")
            return
        time.sleep(1)

    # rename temp → final
    (ROOT_DIR / "dist").mkdir(parents=True, exist_ok=True)
    temp_out.rename(DIST_DIR)
    print(f"[Finalize] Output moved to {DIST_DIR}")


def print_summary():
    """打印打包结果"""
    exe = DIST_DIR / "ScreenTranslate.exe"
    if not exe.exists():
        exe = TEMP_DIR / "ScreenTranslate" / "ScreenTranslate.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        parent = exe.parent
        model_count = len(list(parent.glob("PP-OCRv6_*_onnx")))
        print(f"\n{'='*60}")
        print(f"  Package complete!")
        print(f"  EXE:  {exe}")
        print(f"  Size: {size_mb:.1f} MB")
        print(f"  Dir:  {parent}")
        print(f"  Config: {parent / 'config.yaml'}")
        print(f"  Models: {model_count} dir(s)")
        print(f"{'='*60}")
    else:
        print(f"\n[Error] ScreenTranslate.exe not found — build may have failed.")
        sys.exit(1)


def main():
    print("=" * 60)
    print("  Screen Translate — PyInstaller Packager")
    print("=" * 60)

    clean_artifacts()
    build_exe()
    finalize_output()
    print_summary()


if __name__ == "__main__":
    main()
