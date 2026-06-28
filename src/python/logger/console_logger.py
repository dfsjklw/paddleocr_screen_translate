"""
logger/console_logger.py — 控制台日志捕获模块

在打包为 EXE（--noconsole）时，所有 print() 输出和异常追踪对用户不可见。
此模块将 stdout/stderr 重定向到本地日志文件，方便排查运行时错误。

功能：
    - 捕获 sys.stdout / sys.stderr（所有 print 输出）
    - 捕获未处理异常（sys.excepthook）
    - 每个运行实例一个独立日志文件，文件名带时间戳
    - 自动清理超过保留天数的旧日志
    - 同时保持输出到原始终端（开发时仍然可见）

用法：
    from src.python.logger.console_logger import ConsoleLogger

    logger = ConsoleLogger()
    logger.start()          # 开始捕获
    # ... 程序运行 ...
    logger.stop()           # 恢复原始流（程序退出时自动）
"""

import io
import os
import sys
import time
import glob
import atexit
import threading
from datetime import datetime


# ── 路径解析（兼容 PyInstaller 打包）───────────────────────────────

def _get_log_base_dir() -> str:
    """获取日志存储的根目录

    - 打包 EXE 时: 以 ScreenTranslate.exe 所在目录为基准
    - 开发时: 以项目根目录为基准（main.py 所在目录）
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        # console_logger.py 位于 src/python/logger/ 下，向上 4 层到项目根
        return os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ))


_LOG_BASE = _get_log_base_dir()
_DEFAULT_LOG_DIR = os.path.join(_LOG_BASE, "logs")
_DEFAULT_MAX_DAYS = 7


def get_default_log_dir() -> str:
    """获取默认日志目录（供外部模块获取路径）"""
    return _DEFAULT_LOG_DIR


# ═══════════════════════════════════════════════════════════════════
#  ConsoleLogger
# ═══════════════════════════════════════════════════════════════════

class ConsoleLogger:
    """控制台日志捕获器

    start() 后所有 print() / 异常追踪将被同时写入日志文件和原始终端。
    """

    def __init__(self, log_dir: str | None = None, max_days: int = 7):
        """
        Args:
            log_dir: 日志目录，默认 <项目根>/logs/
            max_days: 旧日志保留天数，默认 7
        """
        self._log_dir = log_dir or _DEFAULT_LOG_DIR
        self._max_days = max(max_days, 1)

        self._original_stdout: io.TextIOWrapper | None = None
        self._original_stderr: io.TextIOWrapper | None = None
        self._original_excepthook: object | None = None
        self._log_file: io.TextIOWrapper | None = None
        self._log_path: str | None = None
        self._started: bool = False
        self._lock = threading.Lock()

    # ── 属性 ──────────────────────────────────────────────────────

    @property
    def log_dir(self) -> str:
        """日志目录路径"""
        return self._log_dir

    @property
    def log_path(self) -> str | None:
        """当前运行实例的日志文件路径（未启动时为 None）"""
        return self._log_path

    # ── 生命周期 ──────────────────────────────────────────────────

    def start(self):
        """开始捕获控制台输出

        必须在程序最早期调用，建议放在 main() 第一行。
        会自动注册 atexit 清理。
        """
        if self._started:
            return

        # 确保日志目录存在
        try:
            os.makedirs(self._log_dir, exist_ok=True)
        except OSError as e:
            print(f"[ConsoleLogger] Failed to create log dir {self._log_dir}: {e}", file=sys.__stderr__)
            return

        # 打开日志文件（时间戳命名）
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path = os.path.join(self._log_dir, f"console_{timestamp}.log")
        try:
            self._log_file = open(self._log_path, "w", encoding="utf-8", buffering=1)
        except OSError as e:
            print(f"[ConsoleLogger] Failed to open log file: {e}", file=sys.__stderr__)
            return

        # 写入文件头
        self._write_header()

        # ── 重定向 stdout/stderr ──
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = _TeeWriter(self._log_file, self._original_stdout, sys.stdout, "STDOUT")
        sys.stderr = _TeeWriter(self._log_file, self._original_stderr, sys.stderr, "STDERR")

        # ── 安装未处理异常钩子 ──
        self._original_excepthook = sys.excepthook
        sys.excepthook = self._exception_hook  # type: ignore[assignment]

        self._started = True

        # 注册退出清理
        atexit.register(self.stop)

        # 清理旧日志
        self._cleanup_old_logs()

        # 启动确认（此时已重定向 stdout）
        print(f"[ConsoleLogger] Log started: {self._log_path}")

    def stop(self):
        """恢复原始输出流，关闭日志文件

        可通过 atexit 自动调用，也可以手动调用。
        多次调用安全。
        """
        if not self._started:
            return
        self._started = False

        # 写一条结束标记
        if self._log_file:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self._log_file.write(f"\n[{ts}] [ConsoleLogger] Log stopped.\n")
            self._log_file.write(f"{'─' * 50}\n")

        # 恢复异常钩子
        if self._original_excepthook is not None:
            sys.excepthook = self._original_excepthook  # type: ignore[assignment]

        # 恢复 stdout/stderr（必须先恢复，再关闭文件，避免 TeeWriter 写已关文件）
        if self._original_stdout is not None:
            sys.stdout = self._original_stdout
        if self._original_stderr is not None:
            sys.stderr = self._original_stderr

        # 关闭日志文件
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    # ── 内部方法 ──────────────────────────────────────────────────

    def _write_header(self):
        """写入日志文件头信息"""
        if not self._log_file:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log_file.write(f"{'=' * 60}\n")
        self._log_file.write(f" ScreenTranslate Console Log\n")
        self._log_file.write(f" Started  : {now}\n")
        self._log_file.write(f" PID      : {os.getpid()}\n")
        self._log_file.write(f" Frozen   : {getattr(sys, 'frozen', False)}\n")
        self._log_file.write(f" Executable: {sys.executable}\n")
        self._log_file.write(f"{'=' * 60}\n\n")
        self._log_file.flush()

    def _cleanup_old_logs(self):
        """删除超过保留天数的旧日志文件"""
        try:
            pattern = os.path.join(self._log_dir, "console_*.log")
            now = time.time()
            cutoff = now - self._max_days * 86400
            for fpath in glob.glob(pattern):
                try:
                    mtime = os.path.getmtime(fpath)
                    if mtime < cutoff:
                        os.remove(fpath)
                except OSError:
                    pass
        except Exception:
            pass  # 清理失败不应影响主程序

    def _exception_hook(self, exc_type, exc_value, exc_tb):
        """捕获未处理异常

        写入日志文件后，再调用原始的 excepthook（显示在原始终端）。
        """
        if self._log_file:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self._log_file.write(f"\n[{ts}] [FATAL] Unhandled exception:\n")
            import traceback
            traceback.print_exception(exc_type, exc_value, exc_tb, file=self._log_file)
            self._log_file.write("\n")
            self._log_file.flush()

        # 调用原始钩子（确保终端也显示）
        if self._original_excepthook is not None:
            self._original_excepthook(exc_type, exc_value, exc_tb)


# ═══════════════════════════════════════════════════════════════════
#  _TeeWriter — 同时写入日志文件和原始流
# ═══════════════════════════════════════════════════════════════════

class _TeeWriter(io.TextIOBase):
    """双向输出流：将写入内容同时发送到日志文件和原始终端。

    替换 sys.stdout / sys.stderr，保证：
    - 所有输出写入日志文件（带时间戳和流标记）
    - 原始终端仍然可以收到输出
    - 每次写入立即 flush，崩溃时不丢失
    """

    def __init__(self, log_file: io.TextIOWrapper, original: io.TextIOWrapper | None,
                 fallback: object, stream_name: str):
        super().__init__()
        self._log_file = log_file
        self._original = original
        self._fallback = fallback  # sys.stdout/sys.stderr 自身（避免递归）
        self._stream_name = stream_name
        self._line_buffer = ""

    def write(self, s: str) -> int:
        if not s:
            return 0

        # ── 写入日志文件（带时间戳） ──
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            # 对每一行添加时间戳和流标记
            for line in s.splitlines(True):
                if line == "\n":
                    # 保持空行的完整性
                    self._log_file.write("\n")
                else:
                    self._log_file.write(f"[{ts}] [{self._stream_name}] {line}")
                    if not line.endswith("\n"):
                        # 行末无换行时补充，确保格式整齐
                        pass
            self._log_file.flush()
        except (OSError, ValueError, AttributeError):
            pass

        # ── 写入原始终端 ──
        if self._original is not None:
            try:
                self._original.write(s)
                self._original.flush()
            except (OSError, ValueError, AttributeError):
                pass

        return len(s)

    def flush(self):
        try:
            self._log_file.flush()
        except (OSError, ValueError, AttributeError):
            pass
        if self._original is not None:
            try:
                self._original.flush()
            except (OSError, ValueError, AttributeError):
                pass

    def isatty(self) -> bool:
        return False

    def fileno(self):
        """部分场景需要 fileno（如某些 C 扩展）"""
        if self._original is not None and hasattr(self._original, "fileno"):
            try:
                return self._original.fileno()
            except OSError:
                pass
        raise OSError("TeeWriter has no fileno")

    def close(self):
        """不要关闭底层流 — 它们不属于 TeeWriter"""
        pass

    @property
    def encoding(self):
        if self._original is not None and hasattr(self._original, "encoding"):
            return self._original.encoding
        return "utf-8"
