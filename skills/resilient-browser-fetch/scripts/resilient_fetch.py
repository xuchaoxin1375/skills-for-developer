"""Orchestrate reliable, isolated browser fetches for protected web pages.

This module adds process isolation, proxy safety, engine fallback, content
validation, and normalized diagnostics around Scrapling and CloakBrowser.
It is intentionally optimized for reliable single-page jobs; callers that
need a continuous batch should reuse an ``AsyncStealthySession`` instead.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html as html_module
import importlib.metadata
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlsplit, urlunsplit
from urllib.request import ProxyHandler, build_opener

DEFAULT_TIMEOUT_MS = 300_000
MIN_SOLVER_TIMEOUT_MS = 60_000
LOCAL_PROXY_CANDIDATES = (
    "http://127.0.0.1:7897",
    "http://127.0.0.1:7890",
    "socks5://127.0.0.1:10808",
)
BLOCK_HINTS = (
    "access denied",
    "attention required",
    "error 1020",
    "error 1015",
    "sorry, you have been blocked",
    "cf-error-details",
)

__all__ = [
    "FetchAttempt",
    "FetchError",
    "FetchFailed",
    "FetchOptions",
    "FetchOutcome",
    "FetchResult",
    "ProxyUnavailableError",
    "fetch_page",
    "save_page",
]


class FetchError(RuntimeError):
    """Base exception for reusable fetch API failures."""

    pass


class ProxyUnavailableError(FetchError):
    """Indicate that a required proxy could not be discovered or reached."""

    pass


@dataclass
class FetchResult:
    """Represent one engine's normalized page response and rendered HTML."""

    engine: str
    url: str
    final_url: str | None
    status: int | None
    html: str
    elapsed_sec: float
    title: str | None = None
    block_reasons: list[str] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FetchOptions:
    """Configure one isolated page-fetch operation without CLI-specific state."""

    url: str
    proxy: str | None = None
    discover_proxy: bool = False
    engine: str = "auto"
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    wall_timeout_ms: int | None = None
    retries: int = 1
    retry_delay: float = 2.0
    headful: bool = False
    wait_selector: str | None = None
    expected_texts: tuple[str, ...] = ()
    post_wait_ms: int = 1000
    challenge_wait_ms: int = 0
    min_bytes: int = 300
    locale: str | None = None
    timezone: str | None = None
    geoip: bool = False
    humanize: bool = False
    hide_canvas: bool = False
    real_chrome: bool = False
    profile_dir: str | Path | None = None
    executable_path: str | Path | None = None
    network_idle: bool = False
    screenshot: str | Path | None = None
    allow_direct: bool = False


@dataclass
class FetchAttempt:
    """Describe one engine attempt, including rejection or runtime failure details."""

    engine: str
    ok: bool
    elapsed_sec: float
    status: int | None = None
    reasons: tuple[str, ...] = ()
    error: str | None = None
    rejected_html: str | None = field(default=None, repr=False)

    def as_metadata(self) -> dict[str, Any]:
        """Return a JSON-serializable summary without embedding rejected HTML."""

        metadata: dict[str, Any] = {
            "engine": self.engine,
            "ok": self.ok,
            "elapsed_sec": self.elapsed_sec,
        }
        if self.status is not None:
            metadata["status"] = self.status
        if self.reasons:
            metadata["reasons"] = list(self.reasons)
        if self.error:
            metadata["error"] = self.error
        return metadata


@dataclass
class FetchOutcome:
    """Return the accepted result, attempt history, and effective proxy."""

    result: FetchResult
    attempts: tuple[FetchAttempt, ...]
    proxy: str | None


class FetchFailed(FetchError):
    """Report that every configured engine failed or returned invalid content."""

    def __init__(self, url: str, attempts: tuple[FetchAttempt, ...]) -> None:
        """Attach the target URL and structured engine attempts to the failure."""

        super().__init__(f"所有引擎均无法获取有效页面: {url}")
        self.url = url
        self.attempts = attempts


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_proxy_endpoint(proxy: str) -> tuple[str, int]:
    parsed = urlparse(proxy)
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
        raise ValueError("代理协议必须为 http、https、socks5 或 socks5h。")
    if not parsed.hostname or not parsed.port:
        raise ValueError("代理格式不完整；请使用 scheme://[user:pass@]host:port。")
    return parsed.hostname, int(parsed.port)


def redact_proxy(proxy: str | None) -> str | None:
    if not proxy:
        return proxy
    parsed = urlsplit(proxy)
    if parsed.username is None:
        return proxy
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit(
        (parsed.scheme, f"***:***@{host}", parsed.path, parsed.query, parsed.fragment)
    )


def wait_for_proxy(proxy: str | None, attempts: int = 3, delay: float = 1.0) -> bool:
    if not proxy:
        return True
    host, port = parse_proxy_endpoint(proxy)
    for attempt in range(1, attempts + 1):
        try:
            with socket.create_connection((host, port), timeout=3):
                logging.info("代理端口可连通: %s:%s", host, port)
                return True
        except OSError as exc:
            logging.warning("代理连通性检查失败 %s/%s: %s", attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(delay)
    return False


def discover_local_proxy(
    candidates: tuple[str, ...] = LOCAL_PROXY_CANDIDATES, timeout: float = 0.75
) -> str | None:
    for candidate in candidates:
        host, port = parse_proxy_endpoint(candidate)
        try:
            with socket.create_connection((host, port), timeout=timeout):
                logging.info("发现本地代理候选: %s", candidate)
                return candidate
        except OSError:
            continue
    return None


def extract_title(page_html: str) -> str | None:
    match = re.search(r"<title\b[^>]*>(.*?)</title>", page_html, re.I | re.S)
    if not match:
        return None
    title = re.sub(r"\s+", " ", html_module.unescape(match.group(1))).strip()
    return title or None


def is_sitemap_url(url: str) -> bool:
    return "sitemap" in urlparse(url).path.lower()


def block_reasons(page_html: str) -> list[str]:
    """Detect challenge and block pages without rejecting normal Cloudflare assets."""

    sample = page_html[:500_000].lower()
    reasons = [f"hint:{hint}" for hint in BLOCK_HINTS if hint in sample]
    title = (extract_title(page_html) or "").lower()
    if "just a moment" in title and "/cdn-cgi/challenge-platform" in sample:
        reasons.append("cloudflare_interstitial")
    if "cf-chl-" in sample and "/cdn-cgi/challenge-platform" in sample:
        reasons.append("cloudflare_challenge_markers")
    if "challenges.cloudflare.com" in sample and "noindex,nofollow" in sample:
        reasons.append("cloudflare_interstitial")
    return sorted(set(reasons))


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp"
    ) as handle:
        handle.write(content)
        temporary = handle.name
    os.replace(temporary, path)


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("scrapling", "cloakbrowser", "playwright", "patchright"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def extract_html(response: Any) -> str:
    for attr in ("html_content", "text", "html", "content", "body"):
        value = getattr(response, attr, None)
        if value is None:
            continue
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            return value
    rendered = str(response)
    if rendered:
        return rendered
    raise FetchError("无法从 Scrapling Response 对象提取 HTML。")


def integer_attr(obj: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(obj, name, None)
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
        if isinstance(value, int):
            return value
    return None


def string_attr(obj: Any, *names: str) -> str | None:
    for name in names:
        value = getattr(obj, name, None)
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
        if value:
            return str(value)
    return None


def response_to_result(engine: str, url: str, response: Any, started: float) -> FetchResult:
    page_html = extract_html(response)
    return FetchResult(
        engine=engine,
        url=url,
        final_url=string_attr(response, "url"),
        status=integer_attr(response, "status", "status_code"),
        html=page_html,
        elapsed_sec=round(time.perf_counter() - started, 3),
        title=extract_title(page_html),
        block_reasons=block_reasons(page_html),
        versions=package_versions(),
    )


def scrapling_kwargs(config: dict[str, Any], *, cdp_url: str | None = None) -> dict[str, Any]:
    """Translate normalized worker configuration into Scrapling session options."""

    kwargs: dict[str, Any] = {
        "solve_cloudflare": True,
        "timeout": config["timeout_ms"],
        "retries": config["retries"],
        "retry_delay": config["retry_delay"],
        "load_dom": True,
        "network_idle": config["network_idle"],
        "disable_resources": False,
    }
    if config.get("wait_selector"):
        kwargs["wait_selector"] = config["wait_selector"]
        kwargs["wait_selector_state"] = "visible"
    if config.get("post_wait_ms"):
        kwargs["wait"] = config["post_wait_ms"]

    screenshot = config.get("screenshot")
    challenge_wait_ms = config.get("challenge_wait_ms", 0)
    if screenshot or challenge_wait_ms:
        if cdp_url:

            async def after_solver_async(page: Any) -> None:
                deadline = time.monotonic() + challenge_wait_ms / 1000
                while challenge_wait_ms and time.monotonic() < deadline:
                    if not block_reasons(await page.content()):
                        break
                    await asyncio.sleep(1)
                if screenshot:
                    await page.screenshot(path=screenshot, full_page=True)

            kwargs["page_action"] = after_solver_async
        else:

            def after_solver_sync(page: Any) -> None:
                deadline = time.monotonic() + challenge_wait_ms / 1000
                while challenge_wait_ms and time.monotonic() < deadline:
                    if not block_reasons(page.content()):
                        break
                    time.sleep(1)
                if screenshot:
                    page.screenshot(path=screenshot, full_page=True)

            kwargs["page_action"] = after_solver_sync

    if cdp_url:
        kwargs["cdp_url"] = cdp_url
        return kwargs

    kwargs.update(
        {
            "headless": not config["headful"],
            "block_webrtc": bool(config.get("proxy")),
            "hide_canvas": config["hide_canvas"],
            "real_chrome": config["real_chrome"],
        }
    )
    for source, target in (
        ("proxy", "proxy"),
        ("locale", "locale"),
        ("timezone", "timezone_id"),
        ("executable_path", "executable_path"),
    ):
        if config.get(source):
            kwargs[target] = config[source]
    if config.get("profile_dir"):
        kwargs["user_data_dir"] = str(Path(config["profile_dir"]) / "scrapling")
    return kwargs


def fetch_with_scrapling(config: dict[str, Any]) -> FetchResult:
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception as exc:
        raise FetchError(
            "无法导入 StealthyFetcher；请安装 requirements.txt 并运行 `scrapling install`。"
        ) from exc
    started = time.perf_counter()
    logging.info("使用 Scrapling Python API，代理=%s", redact_proxy(config.get("proxy")))
    response = StealthyFetcher.fetch(config["url"], **scrapling_kwargs(config))
    return response_to_result("scrapling", config["url"], response, started)


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_cdp_websocket(port: int, timeout_sec: float = 30.0) -> str:
    """Read a local Chromium CDP endpoint while explicitly bypassing external proxies."""

    endpoint = f"http://127.0.0.1:{port}/json/version"
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout_sec
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with opener.open(endpoint, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            websocket = payload.get("webSocketDebuggerUrl")
            if isinstance(websocket, str) and websocket.startswith(("ws://", "wss://")):
                return websocket
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    raise FetchError(f"CloakBrowser CDP 端点未就绪: {last_error}")


async def fetch_with_cloak_cdp_async(config: dict[str, Any]) -> FetchResult:
    try:
        from cloakbrowser import launch_async, launch_persistent_context_async
        from scrapling.fetchers import StealthyFetcher
    except Exception as exc:
        raise FetchError(
            "Cloak CDP 回退不可用；请安装 requirements-cloak.txt 并运行 `python -m cloakbrowser install`。"
        ) from exc

    started = time.perf_counter()
    port = free_local_port()
    launch_kwargs: dict[str, Any] = {
        "headless": not config["headful"],
        "proxy": config.get("proxy"),
        "args": [
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
        ],
        "geoip": config["geoip"],
        "humanize": config["humanize"],
    }
    if config.get("locale"):
        launch_kwargs["locale"] = config["locale"]
    if config.get("timezone"):
        launch_kwargs["timezone"] = config["timezone"]

    logging.info("启动 CloakBrowser 并通过本机 CDP 交给 Scrapling。")
    if config.get("profile_dir"):
        browser = await launch_persistent_context_async(
            str(Path(config["profile_dir"]) / "cloak"), **launch_kwargs
        )
    else:
        browser = await launch_async(**launch_kwargs)
    try:
        websocket = await asyncio.to_thread(read_cdp_websocket, port)
        response = await StealthyFetcher.async_fetch(
            config["url"], **scrapling_kwargs(config, cdp_url=websocket)
        )
        return response_to_result("cloak-cdp", config["url"], response, started)
    finally:
        try:
            await asyncio.wait_for(browser.close(), timeout=15)
        except Exception as exc:
            logging.warning("CloakBrowser 关闭阶段异常: %s", exc)


def fetch_with_cloak_cdp(config: dict[str, Any]) -> FetchResult:
    return asyncio.run(fetch_with_cloak_cdp_async(config))


def fetch_with_scrapling_cli(config: dict[str, Any], worker_dir: Path) -> FetchResult:
    executable = shutil.which("scrapling")
    if not executable:
        raise FetchError("未找到 scrapling CLI。")
    started = time.perf_counter()
    output = worker_dir / "cli.html"
    command = [
        executable,
        "extract",
        "stealthy-fetch",
        "--solve-cloudflare",
        "--timeout",
        str(config["timeout_ms"]),
    ]
    command.append("--no-headless" if config["headful"] else "--headless")
    if config.get("proxy"):
        command.extend(["--proxy", config["proxy"]])
    if config.get("wait_selector"):
        command.extend(["--wait-selector", config["wait_selector"]])
    if config.get("locale"):
        command.extend(["--locale", config["locale"]])
    if config["real_chrome"]:
        command.append("--real-chrome")
    if config.get("executable_path"):
        command.extend(["--executable-path", config["executable_path"]])
    command.extend([config["url"], str(output)])
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=config["timeout_ms"] / 1000 + 45,
    )
    if process.returncode != 0:
        sanitized = process.stdout.replace(
            config.get("proxy") or "\0", redact_proxy(config.get("proxy")) or ""
        )
        raise FetchError(f"Scrapling CLI exit={process.returncode}: {sanitized[-4000:]}")
    if not output.exists():
        raise FetchError("Scrapling CLI 未生成输出文件。")
    page_html = output.read_text(encoding="utf-8", errors="replace")
    return FetchResult(
        engine="scrapling-cli",
        url=config["url"],
        final_url=None,
        status=None,
        html=page_html,
        elapsed_sec=round(time.perf_counter() - started, 3),
        title=extract_title(page_html),
        block_reasons=block_reasons(page_html),
        versions=package_versions(),
    )


def write_worker_result(worker_dir: Path, result: FetchResult) -> None:
    atomic_write_text(worker_dir / "page.html", result.html)
    metadata = asdict(result)
    metadata.pop("html")
    atomic_write_text(
        worker_dir / "result.json", json.dumps(metadata, ensure_ascii=False, indent=2)
    )


def worker_main(engine: str, config_path: Path, worker_dir: Path) -> int:
    worker_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        if engine == "scrapling":
            result = fetch_with_scrapling(config)
        elif engine == "cloak-cdp":
            result = fetch_with_cloak_cdp(config)
        elif engine == "scrapling-cli":
            result = fetch_with_scrapling_cli(config, worker_dir)
        else:
            raise FetchError(f"未知引擎: {engine}")
        write_worker_result(worker_dir, result)
        return 0
    except Exception as exc:
        atomic_write_text(
            worker_dir / "error.json",
            json.dumps(
                {"engine": engine, "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            ),
        )
        logging.exception("%s 失败", engine)
        return 1


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate a timed-out worker and every browser process it spawned."""

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
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_isolated_engine(engine: str, config: dict[str, Any], wall_timeout_ms: int) -> FetchResult:
    """Run one engine in a subprocess so its hard timeout is enforceable."""

    with tempfile.TemporaryDirectory(prefix=f"resilient-fetch-{engine}-") as temporary:
        worker_dir = Path(temporary)
        config_path = worker_dir / "config.json"
        atomic_write_text(config_path, json.dumps(config, ensure_ascii=False))
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker-engine",
            engine,
            "--worker-config",
            str(config_path),
            "--worker-dir",
            str(worker_dir),
        ]
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **popen_kwargs)
        try:
            stdout, _ = process.communicate(timeout=wall_timeout_ms / 1000)
        except subprocess.TimeoutExpired as exc:
            terminate_process_tree(process)
            raise FetchError(
                f"{engine} 超过硬超时 {wall_timeout_ms}ms，已终止浏览器进程树。"
            ) from exc

        result_path = worker_dir / "result.json"
        if process.returncode != 0 or not result_path.exists():
            error_path = worker_dir / "error.json"
            error = "worker 未返回错误详情"
            if error_path.exists():
                error = json.loads(error_path.read_text(encoding="utf-8")).get("error", error)
            sanitized = stdout.replace(
                config.get("proxy") or "\0", redact_proxy(config.get("proxy")) or ""
            )
            if sanitized.strip():
                logging.debug("%s worker 输出:\n%s", engine, sanitized[-6000:])
            raise FetchError(f"{engine}: {error}")

        metadata = json.loads(result_path.read_text(encoding="utf-8"))
        page_html = (worker_dir / "page.html").read_text(encoding="utf-8", errors="replace")
        return FetchResult(html=page_html, **metadata)


def save_success(result: FetchResult, out: Path, attempts: list[dict[str, Any]]) -> None:
    atomic_write_text(out, result.html)
    encoded = result.html.encode("utf-8", errors="replace")
    metadata = asdict(result)
    metadata.pop("html")
    metadata.update(
        {
            "saved_to": str(out.resolve()),
            "bytes_utf8": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "attempts": attempts,
        }
    )
    atomic_write_text(
        out.with_suffix(out.suffix + ".meta.json"),
        json.dumps(metadata, ensure_ascii=False, indent=2),
    )


def engine_order(selected: str) -> list[str]:
    if selected == "auto":
        return ["scrapling", "cloak-cdp"]
    return [selected]


def validation_reasons(result: FetchResult, min_bytes: int, expected_texts: list[str]) -> list[str]:
    reasons = list(result.block_reasons)
    byte_count = len(result.html.encode("utf-8", errors="replace"))
    if byte_count < min_bytes:
        reasons.append(f"content_too_short:{byte_count}")
    for expected in expected_texts:
        if expected not in result.html:
            reasons.append(f"missing_expected_text:{expected}")
    if result.status is not None and result.status >= 400:
        reasons.append(f"http_status:{result.status}")
    return reasons


def validate_options(options: FetchOptions) -> None:
    parsed = urlparse(options.url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url 必须是完整的 HTTP(S) URL。")
    if options.engine not in {"auto", "scrapling", "cloak-cdp", "scrapling-cli"}:
        raise ValueError(f"未知 engine: {options.engine}")
    if options.timeout_ms < MIN_SOLVER_TIMEOUT_MS:
        raise ValueError(f"启用 Cloudflare 求解时 timeout_ms 不得低于 {MIN_SOLVER_TIMEOUT_MS}。")
    if options.retries not in range(1, 4):
        raise ValueError("retries 必须在 1 到 3 之间。")
    if options.retry_delay < 0:
        raise ValueError("retry_delay 不得为负数。")
    if options.post_wait_ms < 0 or options.challenge_wait_ms < 0 or options.min_bytes < 1:
        raise ValueError("等待时间与 min_bytes 必须为非负/正整数。")
    minimum_wall_timeout = options.timeout_ms + options.challenge_wait_ms
    if options.wall_timeout_ms is not None and options.wall_timeout_ms < minimum_wall_timeout:
        raise ValueError("wall_timeout_ms 不得小于 timeout_ms 与 challenge_wait_ms 之和。")


def resolve_proxy(options: FetchOptions) -> str | None:
    proxy = options.proxy.strip() if options.proxy else None
    if not proxy and options.discover_proxy:
        proxy = discover_local_proxy()
        if not proxy:
            raise ProxyUnavailableError("未在本机 7897、7890 或 10808 端口发现可用代理。")
    if not proxy:
        return None
    try:
        reachable = wait_for_proxy(proxy)
    except ValueError as exc:
        raise ProxyUnavailableError(str(exc)) from exc
    if reachable:
        return proxy
    if options.allow_direct:
        logging.warning("代理不可用，按 allow_direct 改为直连。")
        return None
    raise ProxyUnavailableError("代理不可用，且未允许直连。")


def build_worker_config(options: FetchOptions, proxy: str | None) -> dict[str, Any]:
    return {
        "url": options.url.strip(),
        "proxy": proxy,
        "timeout_ms": options.timeout_ms,
        "retries": options.retries,
        "retry_delay": options.retry_delay,
        "headful": options.headful,
        "wait_selector": options.wait_selector,
        "post_wait_ms": options.post_wait_ms,
        "challenge_wait_ms": options.challenge_wait_ms,
        "locale": options.locale,
        "timezone": options.timezone,
        "geoip": options.geoip,
        "humanize": options.humanize,
        "hide_canvas": options.hide_canvas,
        "real_chrome": options.real_chrome,
        "profile_dir": str(Path(options.profile_dir).expanduser().resolve())
        if options.profile_dir
        else None,
        "executable_path": str(Path(options.executable_path).expanduser().resolve())
        if options.executable_path
        else None,
        "network_idle": options.network_idle,
        "screenshot": str(Path(options.screenshot).expanduser().resolve())
        if options.screenshot
        else None,
    }


def fetch_page(options: FetchOptions) -> FetchOutcome:
    """Fetch one page without writing HTML, metadata, or diagnostics to output files.

    Engines run sequentially in isolated subprocesses. A response is accepted only
    after transport status, challenge markers, size, and caller expectations pass.
    """
    validate_options(options)
    url = options.url.strip()
    if is_sitemap_url(url):
        logging.warning(
            "正在直接访问 sitemap。批量任务应先在同一浏览器会话访问站点首页并通过验证，"
            "再复用该窗口请求 sitemap。"
        )
    if options.profile_dir:
        logging.info(
            "持久 profile 适合跨进程复用，但可能持续增长并占用较多磁盘；"
            "连续批量任务优先复用同一浏览器窗口。"
        )

    proxy = resolve_proxy(options)
    config = build_worker_config(options, proxy)
    wall_timeout_ms = (
        options.wall_timeout_ms or options.timeout_ms + options.challenge_wait_ms + 90_000
    )
    attempts: list[FetchAttempt] = []

    for engine in engine_order(options.engine):
        started = time.perf_counter()
        try:
            logging.info("开始引擎: %s", engine)
            result = run_isolated_engine(engine, config, wall_timeout_ms)
            reasons = validation_reasons(result, options.min_bytes, list(options.expected_texts))
            attempt = FetchAttempt(
                engine=engine,
                ok=not reasons,
                status=result.status,
                elapsed_sec=result.elapsed_sec,
                reasons=tuple(reasons),
                rejected_html=result.html if reasons else None,
            )
            attempts.append(attempt)
            if reasons:
                continue
            return FetchOutcome(result=result, attempts=tuple(attempts), proxy=proxy)
        except Exception as exc:
            attempts.append(
                FetchAttempt(
                    engine=engine,
                    ok=False,
                    elapsed_sec=round(time.perf_counter() - started, 3),
                    error=str(exc),
                )
            )
            logging.warning("%s 失败: %s", engine, exc)

    raise FetchFailed(url, tuple(attempts))


def write_attempt_diagnostics(attempts: tuple[FetchAttempt, ...], out: Path) -> None:
    for attempt in attempts:
        if not attempt.rejected_html:
            continue
        diagnostic = out.with_suffix(out.suffix + f".{attempt.engine}.blocked.html")
        atomic_write_text(diagnostic, attempt.rejected_html)
        logging.warning(
            "%s 未通过内容验证: %s；诊断文件: %s",
            attempt.engine,
            ", ".join(attempt.reasons),
            diagnostic,
        )


def save_page(options: FetchOptions, out: str | Path) -> FetchOutcome:
    """Fetch one page and atomically save HTML, metadata, and failure diagnostics."""
    output = Path(out).expanduser().resolve()
    try:
        outcome = fetch_page(options)
    except FetchFailed as exc:
        write_attempt_diagnostics(exc.attempts, output)
        attempts_path = output.with_suffix(output.suffix + ".attempts.json")
        atomic_write_text(
            attempts_path,
            json.dumps(
                {"url": exc.url, "attempts": [attempt.as_metadata() for attempt in exc.attempts]},
                ensure_ascii=False,
                indent=2,
            ),
        )
        logging.error("所有引擎均失败；尝试记录: %s", attempts_path)
        raise

    write_attempt_diagnostics(outcome.attempts, output)
    save_success(
        outcome.result,
        output,
        [attempt.as_metadata() for attempt in outcome.attempts],
    )
    logging.info(
        "成功保存: %s | engine=%s | status=%s | bytes=%s | elapsed=%ss",
        output,
        outcome.result.engine,
        outcome.result.status,
        len(outcome.result.html.encode("utf-8", errors="replace")),
        outcome.result.elapsed_sec,
    )
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="通过 Scrapling/CloakBrowser 保存受保护页面的渲染后 HTML。"
    )
    parser.add_argument("--url", help="目标 HTTP(S) URL。")
    parser.add_argument("--out", default="page.html", help="成功页面的输出路径。")
    parser.add_argument(
        "--proxy", default=os.getenv("SCRAPE_PROXY"), help="代理 URL；也可设置 SCRAPE_PROXY。"
    )
    parser.add_argument(
        "--discover-proxy",
        action="store_true",
        help="未指定代理时依次探测本机 7897、7890 和 SOCKS5 10808 端口。",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "scrapling", "cloak-cdp", "scrapling-cli"),
        default="auto",
        help="auto 依次尝试 Scrapling API 和 CloakBrowser CDP；CLI 仅用于诊断。",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=DEFAULT_TIMEOUT_MS,
        help="每个浏览器操作超时，默认 300000。",
    )
    parser.add_argument(
        "--wall-timeout-ms",
        type=int,
        help="每个引擎的硬超时；默认 timeout + challenge wait + 90000。",
    )
    parser.add_argument(
        "--retries",
        type=int,
        choices=range(1, 4),
        default=1,
        help="导航或代理错误重试次数；不限制 Scrapling 内部 Cloudflare 求解轮次。",
    )
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument(
        "--headful", action="store_true", help="使用有头模式；Linux 服务器需 DISPLAY/Xvfb。"
    )
    parser.add_argument("--wait-selector", help="验证通过后必须出现的 CSS 选择器。")
    parser.add_argument(
        "--expect-text", action="append", default=[], help="成功 HTML 必须包含的文本，可重复。"
    )
    parser.add_argument("--post-wait-ms", type=int, default=1000, help="内容加载后额外等待时间。")
    parser.add_argument(
        "--challenge-wait-ms",
        type=int,
        default=0,
        help="求解器返回后若仍为挑战页，继续等待；有头模式下可用于人工接管。",
    )
    parser.add_argument("--min-bytes", type=int, default=300)
    parser.add_argument("--locale", help="BCP 47 locale，例如 en-US。")
    parser.add_argument("--timezone", help="IANA 时区，例如 America/New_York。")
    parser.add_argument(
        "--geoip",
        action="store_true",
        help="CloakBrowser 按代理出口推导地区；需要 cloakbrowser[geoip]。",
    )
    parser.add_argument("--humanize", action="store_true", help="CloakBrowser 使用人类化输入行为。")
    parser.add_argument("--hide-canvas", action="store_true")
    parser.add_argument("--real-chrome", action="store_true", help="Scrapling 使用系统 Chrome。")
    parser.add_argument("--profile-dir", help="持久配置根目录，用于复用 cookie/localStorage。")
    parser.add_argument("--executable-path", help="Scrapling 自定义 Chromium/Chrome 绝对路径。")
    parser.add_argument(
        "--network-idle", action="store_true", help="等待 networkidle；长连接页面可能不适用。"
    )
    parser.add_argument("--screenshot", help="验证完成后保存全页截图。")
    parser.add_argument("--allow-direct", action="store_true", help="代理不可达时允许直连。")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--worker-engine",
        choices=("scrapling", "cloak-cdp", "scrapling-cli"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--worker-config", help=argparse.SUPPRESS)
    parser.add_argument("--worker-dir", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    if args.worker_engine:
        if not args.worker_config or not args.worker_dir:
            parser.error("worker 参数不完整。")
        return worker_main(args.worker_engine, Path(args.worker_config), Path(args.worker_dir))

    if not args.url:
        parser.error("必须提供 --url。")
    options = FetchOptions(
        url=args.url,
        proxy=args.proxy,
        discover_proxy=args.discover_proxy,
        engine=args.engine,
        timeout_ms=args.timeout_ms,
        wall_timeout_ms=args.wall_timeout_ms,
        retries=args.retries,
        retry_delay=args.retry_delay,
        headful=args.headful,
        wait_selector=args.wait_selector,
        expected_texts=tuple(args.expect_text),
        post_wait_ms=args.post_wait_ms,
        challenge_wait_ms=args.challenge_wait_ms,
        min_bytes=args.min_bytes,
        locale=args.locale,
        timezone=args.timezone,
        geoip=args.geoip,
        humanize=args.humanize,
        hide_canvas=args.hide_canvas,
        real_chrome=args.real_chrome,
        profile_dir=args.profile_dir,
        executable_path=args.executable_path,
        network_idle=args.network_idle,
        screenshot=args.screenshot,
        allow_direct=args.allow_direct,
    )
    try:
        save_page(options, args.out)
    except ValueError as exc:
        parser.error(str(exc))
    except ProxyUnavailableError as exc:
        logging.error("%s", exc)
        return 2
    except FetchFailed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
