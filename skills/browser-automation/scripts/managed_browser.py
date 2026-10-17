"""Run a browser worker under a separate guardian with a caller lifeline.

The worker reads one JSON line from stdin before starting, writes result.json in
its workspace, and stores temporary browser state under workspace/tmp. Only the
guardian owns the worker's Windows Job Object or POSIX process group. This module
does not launch anything on import. See references/screenshot-workflow.md.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, cast

CLEANUP_SECONDS = 8.0
POLL_SECONDS = 0.05
USER_TEMP_ROOT = Path(tempfile.gettempdir()) / (
    "opencode" if os.name == "nt" else f"opencode-{os.getuid()}"
)
STATE_ROOT = USER_TEMP_ROOT / "browser-tasks"


class TaskError(RuntimeError):
    """A failed task with a stable CLI exit status."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class TaskLock:
    """Cross-process lock; a process crash releases the operating-system lock."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.file = (root / "active.lock").open("a+b")
        try:
            self.file.seek(0, 2)
            if self.file.tell() == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise TaskError("截图任务正在运行；等待其收尾后再试。", 3) from exc

    def close(self) -> None:
        """Release the lock only after cleanup has completed."""
        self.file.close()


class ProcessScope:
    """Contain a gated worker; never select processes by name or a saved PID."""

    def __init__(self) -> None:
        self.job: Any = None
        self.kernel: Any = None
        self.process: subprocess.Popen[bytes] | None = None
        if os.name == "nt":
            self._create_job()
        elif sys.platform.startswith("linux"):
            if not hasattr(os, "pidfd_open") or not hasattr(
                signal, "pidfd_send_signal"
            ):
                raise TaskError(
                    "Linux 托管需要 pidfd 支持；当前环境不能保证后代回收。", 2
                )
            descriptor = os.pidfd_open(os.getpid())
            os.close(descriptor)
            # Reap orphaned grandchildren so empty checks include zombies.
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
                raise OSError(ctypes.get_errno(), "cannot become child subreaper")
        else:
            raise TaskError(
                "当前托管器支持 Windows Job Object 与 Linux pidfd/subreaper；其他平台请用项目受管 runner。",
                2,
            )

    def _create_job(self) -> None:
        from ctypes import wintypes as w

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("ProcessTime", ctypes.c_int64),
                ("JobTime", ctypes.c_int64),
                ("Flags", w.DWORD),
                ("MinWorkingSet", ctypes.c_size_t),
                ("MaxWorkingSet", ctypes.c_size_t),
                ("ActiveLimit", w.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("Priority", w.DWORD),
                ("Scheduling", w.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOps",
                    "WriteOps",
                    "OtherOps",
                    "ReadBytes",
                    "WriteBytes",
                    "OtherBytes",
                )
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("Basic", BasicLimits),
                ("Io", IoCounters),
                ("ProcessMemory", ctypes.c_size_t),
                ("JobMemory", ctypes.c_size_t),
                ("PeakProcessMemory", ctypes.c_size_t),
                ("PeakJobMemory", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            w.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            w.DWORD,
        ]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        kernel.TerminateJobObject.restype = w.BOOL
        kernel.QueryInformationJobObject.argtypes = [
            w.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            w.DWORD,
            ctypes.c_void_p,
        ]
        kernel.QueryInformationJobObject.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle.restype = w.BOOL
        self.kernel = kernel
        self.job = kernel.CreateJobObjectW(None, None)
        if not self.job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(
            self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            kernel.CloseHandle(self.job)
            self.job = None
            raise error

    def start(
        self, command: list[str], payload: dict[str, Any], workspace: Path
    ) -> None:
        """Assign the process before sending its start gate and configuration."""
        env = os.environ.copy()
        env.update(
            PYTHONUTF8="1",
            TMP=str(workspace / "tmp"),
            TEMP=str(workspace / "tmp"),
            TMPDIR=str(workspace / "tmp"),
        )
        options: dict[str, Any] = (
            {"creationflags": subprocess.CREATE_NO_WINDOW}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        process = cast(
            subprocess.Popen[bytes],
            subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                **options,
            ),
        )
        self.process = process
        if os.name == "nt":
            if not self.kernel.AssignProcessToJobObject(
                self.job, int(getattr(process, "_handle"))
            ):
                process.kill()
                process.wait(timeout=CLEANUP_SECONDS)
                raise ctypes.WinError(ctypes.get_last_error())
        assert self.process.stdin is not None
        self.process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        self.process.stdin.close()

    def _empty(self) -> bool:
        if os.name == "nt":
            # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four int64, four DWORD.
            accounting = ctypes.create_string_buffer(48)
            if not self.kernel.QueryInformationJobObject(
                self.job, 1, accounting, 48, None
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return int.from_bytes(accounting.raw[40:44], "little") == 0
        if sys.platform.startswith("linux"):
            while True:
                try:
                    if os.waitpid(-1, os.WNOHANG)[0] == 0:
                        break
                except ChildProcessError:
                    break
            # Playwright can launch Chrome in another session. Subreaper adoption
            # and pidfds also cover descendants that escaped the original group.
            children = (
                Path(f"/proc/self/task/{os.getpid()}/children")
                .read_text(encoding="ascii")
                .split()
            )
            for child in children:
                try:
                    descriptor = os.pidfd_open(int(child))
                except ProcessLookupError:
                    continue
                try:
                    status = Path(f"/proc/{child}/stat").read_text(encoding="ascii")
                    parent = int(status.rsplit(")", 1)[1].split()[1])
                    if parent != os.getpid():
                        raise TaskError("后代进程身份无法确认。", 4)
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                except (ProcessLookupError, FileNotFoundError):
                    pass
                finally:
                    os.close(descriptor)
            if children:
                return False
        return True

    def close(self) -> None:
        """Remove residual children even after worker success; verify emptiness."""
        deadline = time.monotonic() + CLEANUP_SECONDS - 2
        try:
            if self.process is None:
                return
            if os.name == "nt":
                if not self.kernel.TerminateJobObject(self.job, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                self.process.terminate()
            # Reap the direct child before reaping adopted children on Linux.
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    self.process.kill()
                self.process.wait(timeout=max(0.01, deadline - time.monotonic()))
            while not self._empty():
                if time.monotonic() >= deadline:
                    raise TaskError("本轮浏览器进程未确认全部释放。", 4)
                time.sleep(POLL_SECONDS)
        finally:
            if self.process is not None and self.process.stdin is not None:
                self.process.stdin.close()
            if self.job:
                self.kernel.CloseHandle(self.job)
                self.job = None


def _lifeline_closed(event: threading.Event) -> None:
    """EOF also arrives when the CLI is forcibly terminated."""
    os.read(sys.stdin.fileno(), 1)
    event.set()


def _publish(workspace: Path, response: dict[str, Any]) -> None:
    """Publish verified PNGs only after the browser scope is empty."""
    for artifact in response.get("artifacts", []):
        source = (workspace / artifact["source"]).resolve()
        if not source.is_relative_to(workspace.resolve()):
            raise ValueError("artifact escaped workspace")
        with source.open("rb") as image:
            if image.read(8) != b"\x89PNG\r\n\x1a\n":
                raise ValueError("worker did not produce a PNG")
        destination = Path(artifact["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".shot-", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as output, source.open("rb") as data:
                shutil.copyfileobj(data, output)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _remove_workspace(workspace: Path) -> None:
    """Windows can briefly retain file handles after job accounting reaches zero."""
    deadline = time.monotonic() + 2
    while workspace.exists():
        try:
            shutil.rmtree(workspace)
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(POLL_SECONDS)


def _guard(request: dict[str, Any], cancelled: threading.Event) -> dict[str, Any]:
    root = Path(request["state_root"])
    lock = TaskLock(root)
    workspace: Path | None = None
    scope: ProcessScope | None = None
    response: dict[str, Any] = {"code": 1, "error": "worker 未完成"}
    try:
        if (root / "cleanup-failed.json").exists():
            raise TaskError(
                f"上一轮清理未确认，请先检查 {root / 'cleanup-failed.json'}。", 4
            )
        if any(root.glob("run-*")):
            raise TaskError(f"发现未收尾的任务目录，请先检查 {root}；停止重试。", 4)
        if cancelled.is_set():
            raise TaskError("调用端已退出，任务已取消。", 130)
        workspace = Path(tempfile.mkdtemp(prefix="run-", dir=root))
        (workspace / "tmp").mkdir()
        logging.info("RUN %s", workspace.name)
        scope = ProcessScope()
        payload = dict(request["payload"], workspace=str(workspace))
        deadline = time.monotonic() + request["wall_timeout_ms"] / 1000
        scope.start(request["command"], payload, workspace)
        assert scope.process is not None
        while scope.process.poll() is None:
            if cancelled.wait(POLL_SECONDS):
                raise TaskError("调用端已退出，任务已取消。", 130)
            if time.monotonic() >= deadline:
                raise TaskError("截图超过任务总期限。", 124)
        if time.monotonic() >= deadline:
            raise TaskError("截图超过任务总期限。", 124)
        result_path = workspace / "result.json"
        if result_path.exists():
            response = json.loads(result_path.read_text(encoding="utf-8"))
        if scope.process.returncode != 0 and response.get("code") == 0:
            raise TaskError("截图 worker 异常退出。")
    except TaskError as exc:
        response = {"code": exc.code, "error": str(exc)}
    except Exception as exc:
        # Do not echo worker stderr or configuration: they can contain credentials.
        response = {"code": 1, "error": f"截图执行失败：{type(exc).__name__}"}
    finally:
        try:
            if scope is not None:
                scope.close()
            if workspace is not None:
                if cancelled.is_set():
                    response = {"code": 130, "error": "调用端已退出，任务已取消。"}
                if response.get("code") == 0:
                    try:
                        _publish(workspace, response)
                    except (OSError, ValueError) as exc:
                        response = {
                            "code": 1,
                            "error": f"截图写入失败：{type(exc).__name__}。",
                        }
                _remove_workspace(workspace)
        except Exception as exc:
            detail = f"{type(exc).__name__} (errno={getattr(exc, 'errno', None)}, winerror={getattr(exc, 'winerror', None)})"
            response = {"code": 4, "error": f"资源清理失败：{detail}；停止重试。"}
            (root / "cleanup-failed.json").write_text(
                json.dumps({"workspace": str(workspace), "error": response["error"]}),
                encoding="utf-8",
            )
        finally:
            lock.close()
    return response


def guardian_main() -> int:
    """Private guardian protocol; stdin must remain open for the task lifetime."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    request = json.loads(sys.stdin.buffer.readline())
    cancelled = threading.Event()
    threading.Thread(target=_lifeline_closed, args=(cancelled,), daemon=True).start()
    try:
        response = _guard(request, cancelled)
    except TaskError as exc:
        response = {"code": exc.code, "error": str(exc)}
    try:
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        # Caller death is expected; resource cleanup has already finished.
        return 130
    return 0


def run_managed(
    command: list[str],
    payload: dict[str, Any],
    wall_timeout_ms: int,
    *,
    state_root: Path = STATE_ROOT,
) -> dict[str, Any]:
    """Run one gated worker; keep the guardian alive through CLI cancellation."""
    if not command or wall_timeout_ms <= 0:
        raise TaskError("需要 worker 命令及正数总期限。", 2)
    options: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--guardian"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        **options,
    )
    assert process.stdin is not None and process.stdout is not None
    request = {
        "command": command,
        "payload": payload,
        "wall_timeout_ms": wall_timeout_ms,
        "state_root": str(state_root.resolve()),
    }
    interrupted = False
    try:
        process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
        process.stdin.flush()
        deadline = time.monotonic() + wall_timeout_ms / 1000 + CLEANUP_SECONDS + 5
        while process.poll() is None:
            try:
                if time.monotonic() >= deadline:
                    raise TaskError("守护进程未按期返回；停止重试并检查资源。", 4)
                time.sleep(POLL_SECONDS)
            except KeyboardInterrupt:
                if not interrupted:
                    interrupted = True
                    process.stdin.close()
        output = process.stdout.read()
        if not output:
            raise TaskError("守护进程异常退出；停止重试并检查资源。", 4)
        result = json.loads(output)
        if result["code"]:
            raise TaskError(result["error"], result["code"])
        if interrupted:
            raise TaskError("截图已取消。", 130)
        return result
    finally:
        process.stdin.close()
        process.stdout.close()


if __name__ == "__main__":
    if sys.argv[1:] != ["--guardian"]:
        raise SystemExit("Internal guardian; use shot_scroll.py --help.")
    raise SystemExit(guardian_main())
