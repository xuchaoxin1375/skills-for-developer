"""晚接入引擎的实现: 先让站点的挑战流程跑完，再接入调试器读取已渲染 DOM。

为什么需要它: 不少 WAF(如 Akamai Bot Manager 防护的电商站)会在第一个文档请求
时先下发挑战页, 挑战在页面加载早期(约 0-10 秒)采集环境与驱动会话。这个窗口里
暴露了自动化痕迹就判失败, 落到 Access Denied; 没暴露就自己重载正文。所以要做的
不是"晚一点接入"本身, 而是**别在挑战决策窗口里出现**。

工程约束:

- 只启动**自己**的浏览器进程，并在任何退出路径(成功、异常、超时)上回收它；
  回收按进程所有权执行，不按进程名批量结束别人的浏览器。
- 用自己的临时 profile，用完删除；不复制、不读取用户的个人 profile。
- 就绪判定只读 DevTools 的 HTTP 端点(不建立调试会话)，避免过早接入。
- 读正文前区分四种页面状态: 正文 / 挑战进行中 / 已被拒绝 / 空。
  把"挑战进行中"当"被拒绝"会丢掉本来能拿到的正文。
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

DEFAULT_SETTLE_MS = 5_000
READY_POLL_INTERVAL_SEC = 0.4
RENDER_POLL_INTERVAL_SEC = 0.8
DEFAULT_RENDER_TIMEOUT_MS = 15_000
# DOM 体积相对变化小于这个比例才算"渲染稳定"
RENDER_STABLE_RATIO = 0.02
DEVTOOLS_HOST = "127.0.0.1"
PROFILE_DIR_PREFIX = "chrome-late-"
# 超过这个年龄的 profile 目录视为上一轮被强杀留下的遗留;一轮正常采集只需十几秒,
# 留出足够余量避免误删仍在使用的目录。
STALE_PROFILE_AGE_SEC = 600

# 页面状态: 正文 / 挑战进行中 / 已被拒绝 / 空
STATE_CONTENT = "content"
STATE_CHALLENGE = "challenge"
STATE_BLOCKED = "blocked"
STATE_EMPTY = "empty"

# 挑战页的共同特征。多数 WAF 挑战页没有 <title>, 但也有站点会写 "Just a moment...";
# 命中任一特征只说明"站点还没放行", 不等于"被拒绝"。
CHALLENGE_MARKERS = (
    "sec-if-cpt-container",
    "behavioral-content",
    "sec-bc-tile-container",
    "powered and protected by",
    "/cdn-cgi/challenge-platform",
    "cf-chl-",
    "checking your browser",
    "enable javascript and cookies to continue",
)
# 标题里出现这些词, 说明服务端已经明确拒绝, 再等也不会变好。
BLOCKED_TITLE_HINTS = (
    "access denied",
    "error 1020",
    "error 1015",
    "reference #",
    "forbidden",
    "unusual traffic",
    "site can't be reached",
    "无法访问",
)
# 标题里出现这些词, 说明挑战还在跑, 继续等。
PENDING_TITLE_HINTS = (
    "just a moment",
    "attention required",
    "checking your browser",
    "one more step",
    "verifying you are human",
    "please wait",
)


class ChromeLateError(RuntimeError):
    """Indicate that the late-attach engine cannot run in this environment."""


def find_system_browser(explicit: str | None = None) -> str | None:
    """Locate a local Chrome/Chromium/Edge binary, preferring the explicit path."""

    if explicit:
        candidate = Path(explicit).expanduser()
        return str(candidate) if candidate.is_file() else None

    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    user_profile = os.environ.get("USERPROFILE")
    if os.name == "nt":
        if local_app_data:
            candidates += [
                Path(local_app_data) / "Google/Chrome/Application/chrome.exe",
                Path(local_app_data) / "Microsoft/Edge/Application/msedge.exe",
            ]
        if program_files:
            candidates += [
                Path(program_files) / "Google/Chrome/Application/chrome.exe",
                Path(program_files) / "Microsoft/Edge/Application/msedge.exe",
            ]
        if program_files_x86:
            candidates += [
                Path(program_files_x86) / "Google/Chrome/Application/chrome.exe",
                Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe",
            ]
        if user_profile:
            for app in ("chrome", "chrome-portable", "chromium"):
                candidates.append(Path(user_profile) / f"scoop/apps/{app}/current/chrome.exe")
                candidates.append(Path(user_profile) / f"scoop/apps/{app}/current/chromium.exe")
    elif os.name == "darwin":
        candidates += [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def proxy_server_value(proxy: str | None) -> str | None:
    """Translate a proxy URL into a Chrome --proxy-server value."""

    if not proxy:
        return None
    if "://" not in proxy:
        raise ChromeLateError(f"代理格式无法解析: {proxy}")
    scheme, _, rest = proxy.partition("://")
    if "@" in rest.split("/")[0]:
        raise ChromeLateError("chrome-late 不支持带凭据的代理；请改用无凭据代理或换其他引擎。")
    return f"{scheme}://{rest}"


def build_launch_args(
    *,
    executable: str,
    port: int,
    user_data_dir: str,
    url: str,
    proxy: str | None = None,
) -> list[str]:
    """Build the command line that opens the URL before any debugger attaches."""

    args = [
        executable,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1400,900",
    ]
    if proxy:
        args.append(f"--proxy-server={proxy}")
    args.append(url)
    return args


def looks_like_url_text(text: str | None) -> bool:
    """Tell a not-yet-titled tab (Chrome shows the bare URL) from a real page title."""

    value = (text or "").strip()
    if not value:
        return True
    if "://" in value:
        return True
    head = value.split("/", 1)[0]
    return "." in head and " " not in head


def classify_page_state(title: str, html: str) -> str:
    """Tell real content, a running challenge, a block page, and an empty page apart.

    A challenge page is not a block: the browser may still solve it and reload the
    real document. Treating "challenge" as "blocked" throws away pages that were
    one wait away from success.
    """

    lowered_title = (title or "").strip().lower()
    if any(hint in lowered_title for hint in BLOCKED_TITLE_HINTS):
        return STATE_BLOCKED
    sample = (html or "")[:300_000].lower()
    if any(marker in sample for marker in CHALLENGE_MARKERS):
        return STATE_CHALLENGE
    if any(hint in lowered_title for hint in PENDING_TITLE_HINTS):
        return STATE_CHALLENGE
    if not sample.strip():
        return STATE_EMPTY
    return STATE_CONTENT


def title_state(title: str) -> str:
    """Classify a tab from its title alone, before any debugger attaches."""

    lowered = (title or "").strip().lower()
    if any(hint in lowered for hint in BLOCKED_TITLE_HINTS):
        return STATE_BLOCKED
    if any(hint in lowered for hint in PENDING_TITLE_HINTS):
        return STATE_CHALLENGE
    if looks_like_url_text(title):
        return STATE_EMPTY
    return STATE_CONTENT


def read_page_targets(port: int, timeout_sec: float = 5.0) -> list[dict[str, Any]]:
    """Read tab metadata from the DevTools HTTP endpoint.

    Reading this endpoint does not create a debugger session, so it is safe to poll
    it while the page is still loading — that is exactly when attaching would be
    detected.
    """

    opener = build_opener(ProxyHandler({}))
    with opener.open(f"http://{DEVTOOLS_HOST}:{port}/json", timeout=timeout_sec) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [item for item in payload if isinstance(item, dict)]


def pick_page_target(targets: list[dict[str, Any]], target_url: str) -> dict[str, Any] | None:
    """Choose the tab that matches the requested URL, else the first http page."""

    pages = [item for item in targets if item.get("type") == "page"]
    http_pages = [item for item in pages if str(item.get("url", "")).startswith("http")]
    if not http_pages:
        return None
    for item in http_pages:
        if str(item.get("url", "")).startswith(target_url):
            return item
    return http_pages[0]


def pick_rendered_page(pages: list[Any], target_url: str) -> Any | None:
    """Choose the open tab that belongs to the requested URL.

    Reading the wrong tab is worse than reading nothing, so when several tabs
    are open and none of them matches, this returns None instead of guessing.
    A redirect changes the URL, so a same-host tab still counts as a match.
    """

    candidates = [
        page
        for page in pages
        if str(getattr(page, "url", "")).startswith(("http://", "https://"))
    ]
    if not candidates:
        return None
    for page in candidates:
        if str(page.url).startswith(target_url):
            return page
    host = urlsplit(target_url).netloc
    same_host = [
        page for page in candidates if urlsplit(str(page.url)).netloc == host
    ]
    if len(same_host) == 1:
        return same_host[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


@dataclass(frozen=True)
class ReadySignal:
    """Describe how the page looked when the engine decided to attach."""

    ready: bool
    title: str
    waited_ms: int
    state: str = STATE_CONTENT


def wait_for_page_ready(
    port: int,
    *,
    target_url: str,
    min_settle_ms: int = DEFAULT_SETTLE_MS,
    max_wait_ms: int = 60_000,
) -> ReadySignal:
    """Wait until the page has a real title, without attaching a debugger.

    A WAF challenge page usually has no title, so "the title is a real title" is
    also the signal that the challenge finished and the real document replaced
    it. A title that says the request was refused ends the wait immediately
    instead of burning the whole budget.
    """

    started = time.monotonic()
    deadline = started + max_wait_ms / 1000
    settle_at = started + min_settle_ms / 1000
    title = ""
    state = STATE_EMPTY
    while time.monotonic() < deadline:
        try:
            targets = read_page_targets(port)
        except Exception:  # 浏览器未就绪时继续等待
            time.sleep(READY_POLL_INTERVAL_SEC)
            continue
        target = pick_page_target(targets, target_url)
        if target is not None:
            title = str(target.get("title") or "")
            state = title_state(title)
            if state == STATE_BLOCKED:
                return ReadySignal(
                    False, title, int((time.monotonic() - started) * 1000), STATE_BLOCKED
                )
            if state == STATE_CONTENT and time.monotonic() >= settle_at:
                return ReadySignal(
                    True, title, int((time.monotonic() - started) * 1000), STATE_CONTENT
                )
        time.sleep(READY_POLL_INTERVAL_SEC)
    return ReadySignal(
        False, title, int((time.monotonic() - started) * 1000), state or STATE_EMPTY
    )


@dataclass(frozen=True)
class RenderSignal:
    """Hold the rendered document and how the page looked when it was read."""

    html: str
    title: str
    state: str
    waited_ms: int
    ready_state: str = ""


def wait_for_rendered_page(
    page: Any,
    *,
    budget_ms: int = DEFAULT_RENDER_TIMEOUT_MS,
    poll_ms: float = RENDER_POLL_INTERVAL_SEC,
) -> RenderSignal:
    """Read the DOM once the page has actually finished rendering.

    The tab title appears when the head is parsed, long before the body is
    built, so reading at that moment returns a half-rendered page. Wait until
    the DOM stops growing before reading; document.readyState has to reach
    "interactive" or better, because a page that keeps a long-lived connection
    open never reaches "complete" and would otherwise burn the whole budget.
    A challenge that is still running is waited out too: it reloads the
    document when it succeeds.
    """

    started = time.monotonic()
    deadline = started + budget_ms / 1000
    previous_size = 0
    stable_samples = 0
    html = ""
    title = ""
    ready_state = ""
    state = STATE_EMPTY
    while True:
        try:
            snapshot = page.evaluate(
                "() => ({html: document.documentElement.outerHTML,"
                " title: document.title, ready: document.readyState})"
            )
            html = str(snapshot.get("html") or "")
            title = str(snapshot.get("title") or "")
            ready_state = str(snapshot.get("ready") or "")
        except Exception:
            # The document may be replaced while the challenge reloads it.
            html, title, ready_state = "", "", ""
        state = classify_page_state(title, html)
        if state == STATE_BLOCKED:
            break
        size = len(html)
        if state == STATE_CONTENT and ready_state in ("interactive", "complete"):
            if previous_size and abs(size - previous_size) <= max(
                2048, int(previous_size * RENDER_STABLE_RATIO)
            ):
                stable_samples += 1
                if stable_samples >= 2:
                    break
            else:
                stable_samples = 0
        previous_size = size
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_ms)
    return RenderSignal(
        html, title, state, int((time.monotonic() - started) * 1000), ready_state
    )


def terminate_owned_tree(process: subprocess.Popen[str]) -> None:
    """Terminate the browser process tree this engine started, and nothing else."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(process.pid), 15)
        process.wait(timeout=5)
    except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
        try:
            os.killpg(os.getpgid(process.pid), 9)
        except (ProcessLookupError, PermissionError):
            pass


def _create_kill_on_close_job() -> int | None:
    """Create a Windows job object that kills its members when the handle closes."""

    if os.name != "nt":
        return None

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_ulong),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_ulong),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_ulong),
            ("SchedulingClass", ctypes.c_ulong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        limits = ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        )  # JobObjectExtendedLimitInformation
        if not ok:
            kernel32.CloseHandle(job)
            return None
        return int(job)
    except Exception:  # job object 只是加固手段, 失败则退回常规回收
        return None


def wait_for_pages_ready(
    port: int,
    *,
    target_urls: list[str],
    min_settle_ms: int = DEFAULT_SETTLE_MS,
    max_wait_ms: int = 60_000,
) -> dict[str, ReadySignal]:
    """Wait until every requested tab has a real title, without attaching.

    Several tabs can be opened in one browser launch; each keeps its own load
    cycle, so all of them stay outside the debug session until the quiet window
    closes.
    """

    started = time.monotonic()
    deadline = started + max_wait_ms / 1000
    settle_at = started + min_settle_ms / 1000
    signals: dict[str, ReadySignal] = {}
    while time.monotonic() < deadline:
        try:
            targets = read_page_targets(port)
        except Exception:  # 浏览器未就绪时继续等待
            time.sleep(READY_POLL_INTERVAL_SEC)
            continue
        for target_url in target_urls:
            if target_url in signals:
                continue
            target = pick_page_target(targets, target_url)
            if target is None:
                continue
            title = str(target.get("title") or "")
            if not looks_like_url_text(title) and time.monotonic() >= settle_at:
                signals[target_url] = ReadySignal(
                    True, title, int((time.monotonic() - started) * 1000)
                )
        if len(signals) == len(target_urls):
            break
        time.sleep(READY_POLL_INTERVAL_SEC)
    for target_url in target_urls:
        signals.setdefault(
            target_url,
            ReadySignal(False, "", int((time.monotonic() - started) * 1000)),
        )
    return signals


def sweep_stale_profiles(
    root: Path | None = None, age_sec: float = STALE_PROFILE_AGE_SEC
) -> list[str]:
    """Remove profile directories left behind by runs that were force-killed.

    A caller that is killed outright never runs its own cleanup, so the browser
    is reclaimed by the job object while the temporary profile stays on disk.
    The next run sweeps those leftovers instead of letting them accumulate.
    """

    base = root or Path(tempfile.gettempdir())
    now = time.time()
    removed: list[str] = []
    for entry in base.glob(f"{PROFILE_DIR_PREFIX}*"):
        if not entry.is_dir():
            continue
        try:
            if now - entry.stat().st_mtime < age_sec:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            removed.append(str(entry))
        except OSError:
            continue
    return removed


class OwnedBrowserProcess:
    """Own one launched browser and guarantee it is reclaimed on every exit path."""

    def __init__(self, process: subprocess.Popen[str], job_handle: int | None = None) -> None:
        """Bind an already launched browser process to this owner."""

        self.process = process
        self.job_handle = job_handle
        self._closed = False

    @classmethod
    def launch(cls, args: list[str]) -> OwnedBrowserProcess:
        """Start the browser and bind it to a kill-on-close job where supported."""

        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "text": True,
        }
        if os.name != "nt":
            # 独立进程组: worker 被结束时，浏览器随组一起回收
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(args, **popen_kwargs)
        job_handle = _create_kill_on_close_job()
        if job_handle is not None and os.name == "nt":
            try:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                assigned = kernel32.AssignProcessToJobObject(job_handle, process._handle)  # type: ignore[attr-defined]
                if not assigned:
                    kernel32.CloseHandle(job_handle)
                    job_handle = None
            except Exception:
                job_handle = None
        return cls(process, job_handle)

    @property
    def pid(self) -> int:
        """Return the launched browser's process id."""

        return self.process.pid

    def close(self) -> None:
        """Reclaim the browser process tree and release the job handle."""

        if self._closed:
            return
        self._closed = True
        try:
            terminate_owned_tree(self.process)
        finally:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            if self.job_handle is not None and os.name == "nt":
                try:
                    ctypes.WinDLL("kernel32").CloseHandle(self.job_handle)  # type: ignore[attr-defined]
                except Exception:
                    pass
                self.job_handle = None
