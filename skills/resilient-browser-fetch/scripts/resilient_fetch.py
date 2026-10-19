"""Orchestrate reliable, isolated browser fetches for protected web pages.

This module adds process isolation, proxy safety, engine fallback, content
validation, and normalized diagnostics around a layered engine set:

- level 0 ``static``: stdlib HTTP, no third-party dependency;
- level 1 ``playwright``: plain headless rendering, no challenge solving;
- level 2 ``scrapling``: anti-detect rendering with Cloudflare solving;
- level 3 ``cloak-cdp``: CloakBrowser fingerprint base driven through Scrapling.

``auto`` tries only the engines that are actually installed, from the lowest
level up, so a missing enhancement package downgrades the run instead of
failing it. It is intentionally optimized for reliable single-page jobs;
callers that need a continuous batch should reuse a session manager instead.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import html as html_module
import importlib.metadata
import importlib.util
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
import zlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse, urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener

DEFAULT_TIMEOUT_MS = 300_000
MIN_SOLVER_TIMEOUT_MS = 60_000
CHALLENGE_POLL_INTERVAL_SEC = 1.0
CHALLENGE_LOG_EVERY_SEC = 15.0
CHALLENGE_SETTLE_MS = 1_500
PROXY_REGISTRY_PATH = Path.home() / ".config" / "proxy-resources.json"
BLOCK_HINTS = (
    "access denied",
    "attention required",
    "error 1020",
    "error 1015",
    "sorry, you have been blocked",
    "cf-error-details",
)
# 部分站点(WAF)对可疑请求回 403，却仍下发完整正文；这类响应正文侧没有任何拦截信号。
# 只有调用方显式断言过正文、且正文达到正常页面量级时才按可用内容接受，
# 以免把 404/401/429/5xx，或品牌化的小体积拦截页当成正文。
SOFT_STATUS_CODES = frozenset({403})
SOFT_STATUS_MIN_BYTES = 20_000
# 服务端明确声明资源不存在时，换更高层引擎只会重复请求同一不可用资源，
# 不能把 404/410 当挑战页升档；挑战特征命中时仍按拦截页处理。
TERMINAL_STATUS_CODES = frozenset({404, 410})

# 页面"加载完成"的判定条件，决定取源码与关闭窗口的时机(层 1/2/3；层 0 无浏览器，忽略)。
WAIT_UNTIL_CHOICES = ("commit", "domcontentloaded", "load", "networkidle")
DEFAULT_WAIT_UNTIL = "load"

# 层 0 的 TLS/HTTP2 客户端伪装(需 curl_cffi)。默认写具体版本而不是 "chrome" 这类滚动别名:
# 别名指向的 Chrome 版本会随 curl_cffi 升级漂移(实测 JA4 第三段不同: chrome vs chrome124)，
# 固定版本才能复现与对照。
DEFAULT_IMPERSONATE_TARGET = "chrome124"

# ---- 引擎能力分层 ----
# 层 0 零第三方依赖，层 1 只需 playwright/patchright，层 2 起才需要 scrapling。
# auto 只升档到"已安装"的引擎，缺件记 unavailable 而不算失败。
CAP_HTTP = "http"
CAP_RENDER = "render"
CAP_SOLVE = "solve-challenge"
CAP_CDP = "cdp"

# 尝试结果分类:调用方据此区分"该装依赖"与"该换路线"。
KIND_OK = "ok"
KIND_UNAVAILABLE = "unavailable"
KIND_BLOCKED = "blocked"
KIND_EMPTY = "blocked_or_empty"
KIND_RUNTIME = "runtime_error"

# worker 把引擎缺件写成 EngineUnavailableError，父进程按此标记回判分类。
UNAVAILABLE_ERROR_MARKER = "EngineUnavailableError"

__all__ = [
    "ENGINES",
    "ENGINE_CHOICES",
    "EngineAvailability",
    "EngineSpec",
    "EngineUnavailableError",
    "FetchAttempt",
    "FetchError",
    "FetchFailed",
    "FetchOptions",
    "FetchOutcome",
    "FetchResult",
    "ProxyUnavailableError",
    "available_engines",
    "curl_cffi_available",
    "curl_cffi_impersonate_targets",
    "default_impersonate_target",
    "engine_availability",
    "engine_order",
    "fetch_page",
    "fetch_with_static",
    "playwright_api_name",
    "reset_availability_cache",
    "save_page",
    "validate_identity_headers",
    "validate_impersonate",
]


class FetchError(RuntimeError):
    """Base exception for reusable fetch API failures."""

    pass


class ProxyUnavailableError(FetchError):
    """Indicate that a required proxy could not be discovered or reached."""

    pass


class EngineUnavailableError(FetchError):
    """Indicate that an engine's own dependencies are missing in this environment."""

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
    notes: list[str] = field(default_factory=list)
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
    wait_until: str = DEFAULT_WAIT_UNTIL
    expected_texts: tuple[str, ...] = ()
    post_wait_ms: int = 1000
    challenge_wait_ms: int = 0
    min_bytes: int = 300
    locale: str | None = None
    timezone: str | None = None
    user_agent: str | None = None
    referer: str | None = None
    geoip: bool = False
    humanize: bool = False
    hide_canvas: bool = False
    real_chrome: bool = False
    profile_dir: str | Path | None = None
    executable_path: str | Path | None = None
    network_idle: bool = False
    impersonate: str | None = None
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
    kind: str = KIND_OK
    rejected_html: str | None = field(default=None, repr=False)

    def as_metadata(self) -> dict[str, Any]:
        """Return a JSON-serializable summary without embedding rejected HTML."""

        metadata: dict[str, Any] = {
            "engine": self.engine,
            "ok": self.ok,
            "kind": self.kind,
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

    @property
    def unavailable_engines(self) -> tuple[str, ...]:
        """Name the engines that could not even start for missing dependencies."""

        return tuple(item.engine for item in self.attempts if item.kind == KIND_UNAVAILABLE)

    @property
    def blocked_engines(self) -> tuple[str, ...]:
        """Name the engines that ran but were rejected as challenge or empty pages."""

        return tuple(
            item.engine for item in self.attempts if item.kind in (KIND_BLOCKED, KIND_EMPTY)
        )

    def describe(self) -> str:
        """Summarize the failure for logs and calling agents."""

        if self.attempts and len(self.unavailable_engines) == len(self.attempts):
            missing = sorted({item.error for item in self.attempts if item.error})
            detail = "；".join(item for item in missing if item)
            return (
                f"没有可用引擎(缺件: {detail or '见 attempts.json'})；"
                "若依赖装在别的 Python 环境，请改用该环境的解释器运行"
                "(如 conda run -n <env> --no-capture-output python ...)，"
                "或用 check_environment.py --list-envs 查看哪个环境具备所需层"
            )
        if self.attempts and len(self.blocked_engines) == len(self.attempts):
            return "所有已尝试引擎都返回挑战页或空内容；请升档、换代理或改用有头人工验证"
        return f"所有引擎均无法获取有效页面(尝试 {len(self.attempts)} 个)"


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


def registry_proxy_candidates() -> tuple[str, ...]:
    """Return proxy URLs from the machine-local registry, default entry first.

    The registry lives outside this repo (one file per machine); an absent or
    unparsable registry simply yields no candidates instead of guessing ports.
    """

    try:
        data = json.loads(PROXY_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(data, dict) or not isinstance(data.get("proxies"), list):
        return ()
    ordered: list[str] = []
    default = data.get("default")
    if isinstance(default, str):
        for entry in data["proxies"]:
            if (
                isinstance(entry, dict)
                and entry.get("name") == default
                and isinstance(entry.get("url"), str)
                and entry["url"]
            ):
                ordered.append(entry["url"])
    for entry in data["proxies"]:
        if isinstance(entry, dict) and isinstance(entry.get("url"), str) and entry["url"]:
            if entry["url"] not in ordered:
                ordered.append(entry["url"])
    return tuple(ordered)


def discover_local_proxy(
    candidates: tuple[str, ...] | None = None, timeout: float = 0.75
) -> str | None:
    if candidates is None:
        candidates = registry_proxy_candidates()
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


def log_manual_verification_hint(wait_ms: int, *, headful: bool) -> None:
    """Tell the operator what to do when a headful run may hit a challenge."""

    if not headful:
        return
    if wait_ms > 0:
        logging.info(
            "有头模式: 若窗口中出现人机验证，请在窗口内完成；脚本会在 %.0f 秒内轮询页面，"
            "验证通过后立即保存并关闭窗口。",
            wait_ms / 1000,
        )
    else:
        logging.info(
            "有头模式: 若窗口中出现人机验证，请完成它；当前 --challenge-wait-ms 为 0，"
            "脚本不会等待，建议设为 300000 给人工留出时间。"
        )


def wait_for_manual_verification(
    read_html: Callable[[], str],
    wait_ms: int,
    *,
    label: str = "页面",
    headful: bool = False,
) -> tuple[bool, float]:
    """Poll a page until block markers clear or the wait budget runs out.

    Returns ``(cleared, waited_sec)``。有头模式下会打印人工指引与进度，
    这样操作者知道窗口在等他点验证，而不是以为脚本卡住了。
    """

    started = time.monotonic()
    budget = max(0, int(wait_ms)) / 1000
    if budget <= 0:
        return (not block_reasons(read_html()), 0.0)
    next_log = 0.0
    while True:
        elapsed = time.monotonic() - started
        if not block_reasons(read_html()):
            if elapsed >= CHALLENGE_POLL_INTERVAL_SEC:
                logging.info("验证已通过(等待 %.0f 秒)，继续抓取。", elapsed)
            return True, elapsed
        if elapsed >= budget:
            logging.warning("%s 在 %.0f 秒内未通过验证，按当前页面继续。", label, budget)
            return False, elapsed
        if elapsed >= next_log:
            next_log = elapsed + CHALLENGE_LOG_EVERY_SEC
            logging.info(
                "%s 仍在等待验证: 已等 %.0f/%.0f 秒%s",
                label,
                elapsed,
                budget,
                "，请在有头窗口内完成人机验证"
                if headful
                else "，无头模式请改用 --headful 人工验证或层 2/3 求解",
            )
        time.sleep(CHALLENGE_POLL_INTERVAL_SEC)


async def wait_for_manual_verification_async(
    read_html: Callable[[], Awaitable[str]],
    wait_ms: int,
    *,
    label: str = "页面",
    headful: bool = False,
) -> tuple[bool, float]:
    """Async twin of :func:`wait_for_manual_verification` for CDP sessions."""

    started = time.monotonic()
    budget = max(0, int(wait_ms)) / 1000
    if budget <= 0:
        return (not block_reasons(await read_html()), 0.0)
    next_log = 0.0
    while True:
        elapsed = time.monotonic() - started
        if not block_reasons(await read_html()):
            if elapsed >= CHALLENGE_POLL_INTERVAL_SEC:
                logging.info("验证已通过(等待 %.0f 秒)，继续抓取。", elapsed)
            return True, elapsed
        if elapsed >= budget:
            logging.warning("%s 在 %.0f 秒内未通过验证，按当前页面继续。", label, budget)
            return False, elapsed
        if elapsed >= next_log:
            next_log = elapsed + CHALLENGE_LOG_EVERY_SEC
            logging.info(
                "%s 仍在等待验证: 已等 %.0f/%.0f 秒%s",
                label,
                elapsed,
                budget,
                "，请在有头窗口内完成人机验证"
                if headful
                else "，无头模式请改用 --headful 人工验证或层 2/3 求解",
            )
        await asyncio.sleep(CHALLENGE_POLL_INTERVAL_SEC)


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
    for package in ("scrapling", "cloakbrowser", "playwright", "patchright", "curl_cffi"):
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


# ---- 层 0:stdlib HTTP(零第三方依赖)----
STATIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
STATIC_HEADERS = {
    "User-Agent": STATIC_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}


def decode_static_body(
    payload: bytes, content_type: str | None, content_encoding: str | None
) -> str:
    """Decode a static body from transport headers, then sniffed, then fallback charsets."""

    encoding = (content_encoding or "").strip().lower()
    if encoding == "gzip":
        payload = gzip.decompress(payload)
    elif encoding == "deflate":
        try:
            payload = zlib.decompress(payload)
        except zlib.error:
            payload = zlib.decompress(payload, -zlib.MAX_WBITS)

    candidates: list[str] = []
    if content_type:
        declared = re.search(r"charset=[\"']?([\w\-]+)", content_type, re.I)
        if declared:
            candidates.append(declared.group(1))
    sniffed = re.search(rb"charset=[\"']?([\w\-]+)", payload[:2048], re.I)
    if sniffed:
        candidates.append(sniffed.group(1).decode("ascii", errors="replace"))
    candidates.extend(("utf-8", "gb18030"))

    for candidate in candidates:
        try:
            return payload.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def static_proxy_map(proxy: str | None) -> dict[str, str]:
    """Map one proxy URL onto urllib's per-scheme proxy dictionary."""

    return {"http": proxy, "https": proxy} if proxy else {}


def curl_cffi_get(config: dict[str, Any], target: str) -> Any:
    """Perform one curl_cffi request with the requested TLS/HTTP2 fingerprint.

    只覆盖调用方显式指定的头: UA 交给 impersonate 目标决定, 避免 TLS 说 Chrome136、UA 说
    Chrome124 的自相矛盾; Referer 仅在给出时附加。
    """

    from curl_cffi import requests as curl_requests

    headers: dict[str, str] = {}
    if config.get("user_agent"):
        headers["User-Agent"] = str(config["user_agent"])
    if config.get("locale"):
        headers["Accept-Language"] = str(config["locale"])
    if config.get("referer"):
        headers["Referer"] = str(config["referer"])
    proxy = config.get("proxy")
    return curl_requests.get(
        config["url"],
        headers=headers or None,
        proxies={"http": proxy, "https": proxy} if proxy else None,
        timeout=max(config["timeout_ms"] / 1000, 1.0),
        # curl_cffi 的 stubs 把 impersonate 收窄为字面量联合；目标在构造选项时已校验。
        impersonate=cast(Any, target),
    )


def fetch_with_static_curl_cffi(config: dict[str, Any], started: float) -> FetchResult:
    """Fetch through curl_cffi when the caller asked for TLS disguise or the proxy scheme needs it."""

    if not curl_cffi_available():
        raise EngineUnavailableError(
            "static 引擎需要 curl_cffi 才能做 TLS/HTTP2 伪装或走该代理；"
            "请安装 curl_cffi，或改用 http(s) 代理并去掉 --impersonate。"
        )
    target = config.get("impersonate") or default_impersonate_target()
    last_error: Exception | None = None
    for attempt in range(1, config["retries"] + 1):
        try:
            response = curl_cffi_get(config, target)
        except Exception as exc:
            # 经代理的 TLS 握手偶发 "OPENSSL_internal:invalid library" 一类瞬时失败(实测)，
            # 与 stdlib 路径一样按 retries 重试，避免把可恢复的握手失败报成引擎故障。
            last_error = exc
            if attempt < config["retries"]:
                logging.warning(
                    "static(curl_cffi) 抓取失败 %s/%s: %s", attempt, config["retries"], exc
                )
                time.sleep(config["retry_delay"])
            continue
        page_html = response.text
        logging.info("static 走 curl_cffi: impersonate=%s", target)
        return FetchResult(
            engine="static",
            url=config["url"],
            final_url=str(response.url),
            status=int(response.status_code),
            html=page_html,
            elapsed_sec=round(time.perf_counter() - started, 3),
            title=extract_title(page_html),
            block_reasons=block_reasons(page_html),
            notes=[f"impersonate:{target}"],
            versions=package_versions(),
        )
    raise FetchError(
        f"static(curl_cffi, impersonate={target}) 抓取失败({config['retries']} 次尝试): {last_error}"
    )


def static_request(
    opener: Any, url: str, headers: dict[str, str], timeout: float
) -> tuple[int, str, bytes, str | None, str | None]:
    """Perform one stdlib request, returning transport details instead of raising on 4xx/5xx."""

    request = Request(url, headers=headers)
    try:
        with opener.open(request, timeout=timeout) as response:
            return (
                int(getattr(response, "status", 200) or 200),
                response.geturl(),
                response.read(),
                response.headers.get("Content-Type"),
                response.headers.get("Content-Encoding"),
            )
    except HTTPError as exc:
        # 4xx/5xx 按"拿到了内容"返回，交给内容校验判定是拦截还是正常错误页。
        with exc:
            return (
                int(exc.code),
                exc.geturl(),
                exc.read() or b"",
                exc.headers.get("Content-Type") if exc.headers else None,
                exc.headers.get("Content-Encoding") if exc.headers else None,
            )


def fetch_with_static(config: dict[str, Any]) -> FetchResult:
    """Fetch the page over HTTP only; never launches a browser."""

    proxy = config.get("proxy")
    scheme = urlparse(proxy).scheme.lower() if proxy else ""
    started = time.perf_counter()
    if config.get("impersonate"):
        if not curl_cffi_available():
            raise EngineUnavailableError(
                "static 引擎的 --impersonate 需要 curl_cffi；请安装 curl_cffi(推荐)，"
                "或去掉该参数改用浏览器引擎。"
            )
        return fetch_with_static_curl_cffi(config, started)
    if scheme in {"socks5", "socks5h"} or (scheme and scheme not in {"http", "https"}):
        if not curl_cffi_available():
            raise EngineUnavailableError(
                f"static 引擎不支持 {scheme or '该'} 代理且未安装 curl_cffi；"
                "请安装 curl_cffi，或改用 http(s) 代理，或升档到浏览器引擎。"
            )
        return fetch_with_static_curl_cffi(config, started)

    headers = dict(STATIC_HEADERS)
    if config.get("user_agent"):
        headers["User-Agent"] = str(config["user_agent"])
    if config.get("locale"):
        headers["Accept-Language"] = str(config["locale"])
    if config.get("referer"):
        headers["Referer"] = str(config["referer"])
    opener = build_opener(ProxyHandler(static_proxy_map(proxy)))
    timeout = max(config["timeout_ms"] / 1000, 1.0)
    last_error: Exception | None = None
    for attempt in range(1, config["retries"] + 1):
        try:
            status, final_url, body, content_type, content_encoding = static_request(
                opener, config["url"], headers, timeout
            )
        except (URLError, OSError, ValueError) as exc:
            last_error = exc
            if attempt < config["retries"]:
                logging.warning("static 抓取失败 %s/%s: %s", attempt, config["retries"], exc)
                time.sleep(config["retry_delay"])
            continue
        page_html = decode_static_body(body, content_type, content_encoding)
        return FetchResult(
            engine="static",
            url=config["url"],
            final_url=final_url,
            status=status,
            html=page_html,
            elapsed_sec=round(time.perf_counter() - started, 3),
            title=extract_title(page_html),
            block_reasons=block_reasons(page_html),
            versions=package_versions(),
        )
    raise FetchError(f"static 抓取失败({config['retries']} 次尝试): {last_error}")


# ---- 层 1:playwright/patchright 渲染(无挑战求解)----
def load_playwright_factory() -> Any:
    """Import the sync API of patchright when present, else of plain Playwright."""

    name = playwright_api_name()
    if name is None:
        raise EngineUnavailableError(
            "未安装 playwright/patchright；请安装后运行 `playwright install chromium`，"
            "或用 --real-chrome/--executable-path 指向系统浏览器。"
        )
    module = importlib.import_module(f"{name}.sync_api")
    factory = getattr(module, "sync_playwright", None)
    if factory is None:
        raise EngineUnavailableError(f"{name}.sync_api 缺少 sync_playwright。")
    return factory


def playwright_launch_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    """Translate normalized config into Chromium launch options."""

    kwargs: dict[str, Any] = {"headless": not config["headful"]}
    proxy = config.get("proxy")
    if proxy:
        parsed = urlparse(proxy)
        server = f"{parsed.scheme}://{parsed.hostname or ''}"
        if parsed.port:
            server = f"{server}:{parsed.port}"
        credentials = bool(parsed.username)
        if credentials and parsed.scheme.lower().startswith("socks"):
            raise FetchError("playwright 不支持带凭据的 socks 代理；请改用 http 代理或层 2/3。")
        entry: dict[str, Any] = {"server": server}
        if credentials:
            entry["username"] = unquote(parsed.username or "")
            entry["password"] = unquote(parsed.password or "")
        kwargs["proxy"] = entry
    if config.get("executable_path"):
        kwargs["executable_path"] = config["executable_path"]
    elif config.get("real_chrome"):
        kwargs["channel"] = "chrome"
    return kwargs


def render_with_playwright(config: dict[str, Any]) -> tuple[str, int | None, str]:
    """Open the URL in a plain browser context and return (html, status, final_url)."""

    factory = load_playwright_factory()
    timeout_ms = int(config["timeout_ms"])
    launch_kwargs = playwright_launch_kwargs(config)
    context_kwargs: dict[str, Any] = {}
    if config.get("locale"):
        context_kwargs["locale"] = config["locale"]
    if config.get("timezone"):
        context_kwargs["timezone_id"] = config["timezone"]
    if config.get("user_agent"):
        context_kwargs["user_agent"] = str(config["user_agent"])
    profile_dir = Path(config["profile_dir"]) / "playwright" if config.get("profile_dir") else None
    screenshot = Path(config["screenshot"]) if config.get("screenshot") else None
    if screenshot:
        screenshot.parent.mkdir(parents=True, exist_ok=True)

    with factory() as playwright:
        browser = None
        if profile_dir:
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir), **launch_kwargs, **context_kwargs
            )
        else:
            browser = playwright.chromium.launch(**launch_kwargs)
            context = browser.new_context(**context_kwargs)
        try:
            page = context.new_page()
            wait_until = config.get("wait_until") or DEFAULT_WAIT_UNTIL
            goto_kwargs: dict[str, Any] = {"timeout": timeout_ms, "wait_until": wait_until}
            if config.get("referer"):
                goto_kwargs["referer"] = str(config["referer"])
            response = page.goto(config["url"], **goto_kwargs)
            if config.get("network_idle") and wait_until != "networkidle":
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            # 层 1 没有求解器，但有人: 有头模式先给人时间过验证，再等选择器/截图/取源码，
            # 否则 --wait-selector 会先在挑战页上超时，人工验证永远等不到。
            manual_wait_ms = int(config.get("challenge_wait_ms") or 0)
            if config.get("headful") and manual_wait_ms > 0:
                cleared, _waited = wait_for_manual_verification(
                    lambda: page.content(),
                    manual_wait_ms,
                    label=config["url"],
                    headful=True,
                )
                if cleared:
                    # 验证后页面通常还会再跳一次，给它一点稳定时间。
                    page.wait_for_timeout(CHALLENGE_SETTLE_MS)
            if config.get("wait_selector"):
                page.wait_for_selector(
                    config["wait_selector"], state="visible", timeout=timeout_ms
                )
            if config.get("post_wait_ms"):
                page.wait_for_timeout(int(config["post_wait_ms"]))
            if screenshot:
                page.screenshot(path=str(screenshot), full_page=True)
            page_html = page.content()
            final_url = page.url
            status = response.status if response is not None else None
        finally:
            try:
                context.close()
            finally:
                if browser is not None:
                    browser.close()
    return page_html, status, final_url


def fetch_with_playwright(config: dict[str, Any]) -> FetchResult:
    """Render with a plain browser: fast, dependency-light, no challenge solving."""

    started = time.perf_counter()
    try:
        page_html, status, final_url = render_with_playwright(config)
    except (EngineUnavailableError, FetchError):
        raise
    except Exception as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message:
            raise EngineUnavailableError(
                f"未找到浏览器二进制；请运行 `playwright install chromium`，"
                f"或用 --real-chrome/--executable-path 指定系统浏览器。原始信息: {message}"
            ) from exc
        raise FetchError(f"playwright 渲染失败: {message}") from exc
    return FetchResult(
        engine="playwright",
        url=config["url"],
        final_url=final_url,
        status=status,
        html=page_html,
        elapsed_sec=round(time.perf_counter() - started, 3),
        title=extract_title(page_html),
        block_reasons=block_reasons(page_html),
        versions=package_versions(),
    )


def scrapling_wait_kwargs(wait_until: str) -> dict[str, Any]:
    """Map the normalized wait condition onto Scrapling's own loading options.

    Scrapling 没有 `wait_until`: `networkidle` 用它的 `network_idle` 表达; `commit` 与
    `domcontentloaded` 都用 `load_dom=False` 近似, 即不等页面脚本执行完再取源码.
    """

    if wait_until == "networkidle":
        return {"network_idle": True, "load_dom": True}
    if wait_until in {"commit", "domcontentloaded"}:
        return {"network_idle": False, "load_dom": False}
    return {"network_idle": False, "load_dom": True}


def scrapling_kwargs(config: dict[str, Any], *, cdp_url: str | None = None) -> dict[str, Any]:
    """Translate normalized worker configuration into Scrapling session options."""

    kwargs: dict[str, Any] = {
        "solve_cloudflare": True,
        "timeout": config["timeout_ms"],
        "retries": config["retries"],
        "retry_delay": config["retry_delay"],
        "disable_resources": False,
        **scrapling_wait_kwargs(config.get("wait_until") or DEFAULT_WAIT_UNTIL),
    }
    if config.get("network_idle"):
        kwargs["network_idle"] = True
    if config.get("user_agent"):
        kwargs["useragent"] = str(config["user_agent"])
    referer = config.get("referer")
    if referer:
        # 实测 extra_headers 的 Referer 会覆盖 google_search 带来的 Google referer。
        kwargs["extra_headers"] = {"Referer": str(referer)}
    elif referer == "":
        # 显式不发 Referer: 必须关掉 google_search, 否则会静默带上 Google referer。
        kwargs["google_search"] = False
    if config.get("wait_selector"):
        kwargs["wait_selector"] = config["wait_selector"]
        kwargs["wait_selector_state"] = "visible"
    if config.get("post_wait_ms"):
        kwargs["wait"] = config["post_wait_ms"]

    screenshot = config.get("screenshot")
    challenge_wait_ms = config.get("challenge_wait_ms", 0)
    headful = bool(config.get("headful"))
    if screenshot or challenge_wait_ms:
        if cdp_url:

            async def after_solver_async(page: Any) -> None:
                await wait_for_manual_verification_async(
                    lambda: page.content(),
                    challenge_wait_ms,
                    label=config["url"],
                    headful=headful,
                )
                if screenshot:
                    await page.screenshot(path=screenshot, full_page=True)

            kwargs["page_action"] = after_solver_async
        else:

            def after_solver_sync(page: Any) -> None:
                wait_for_manual_verification(
                    lambda: page.content(),
                    challenge_wait_ms,
                    label=config["url"],
                    headful=headful,
                )
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
        raise EngineUnavailableError(
            "未安装 scrapling[fetchers]；请安装 requirements-stealth.txt 并运行 `scrapling install`。"
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
        raise EngineUnavailableError(
            "层 3 不可用:需要层 2 的 scrapling[fetchers] 与 cloakbrowser；"
            "请安装 requirements-cloak.txt 并运行 `python -m cloakbrowser install`。"
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
        raise EngineUnavailableError("未找到 scrapling CLI；该引擎仅用于排障。")
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


def run_engine(
    engine: str, config: dict[str, Any], worker_dir: Path
) -> FetchResult:
    """Dispatch one engine by name inside its isolated worker process."""

    if engine == "static":
        return fetch_with_static(config)
    if engine == "playwright":
        return fetch_with_playwright(config)
    if engine == "scrapling":
        return fetch_with_scrapling(config)
    if engine == "cloak-cdp":
        return fetch_with_cloak_cdp(config)
    if engine == "scrapling-cli":
        return fetch_with_scrapling_cli(config, worker_dir)
    raise FetchError(f"未知引擎: {engine}")


def worker_main(engine: str, config_path: Path, worker_dir: Path) -> int:
    worker_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        result = run_engine(engine, config, worker_dir)
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


@dataclass(frozen=True)
class EngineAvailability:
    """Describe whether one engine can run in the current interpreter environment."""

    ok: bool
    detail: str
    missing: tuple[str, ...] = ()

    def reason(self) -> str:
        """Render a human-readable explanation including missing dependencies."""

        if self.missing:
            return f"{self.detail}(缺失: {', '.join(self.missing)})"
        return self.detail


@dataclass(frozen=True)
class EngineSpec:
    """Declare one engine's capability level and its dependency probe."""

    name: str
    level: int
    capabilities: frozenset[str]
    requires: tuple[str, ...]
    probe: Callable[[], EngineAvailability]
    in_auto: bool = True


def curl_cffi_available() -> bool:
    """Report whether the recommended layer-0 enhancement (socks proxy and TLS disguise) is installed."""

    return importlib.util.find_spec("curl_cffi") is not None


def curl_cffi_impersonate_targets() -> tuple[str, ...]:
    """Return the impersonate targets this curl_cffi offers, or empty when unavailable."""

    if not curl_cffi_available():
        return ()
    try:
        from curl_cffi import requests as curl_requests
    except Exception:
        return ()
    try:
        return tuple(sorted(item.value for item in curl_requests.BrowserType))
    except Exception:
        return ()


def default_impersonate_target() -> str:
    """Prefer the documented target, else the newest chrome profile this curl_cffi offers."""

    targets = curl_cffi_impersonate_targets()
    if not targets or DEFAULT_IMPERSONATE_TARGET in targets:
        return DEFAULT_IMPERSONATE_TARGET
    chrome = [name for name in targets if re.fullmatch(r"chrome\d+", name)]
    if not chrome:
        return DEFAULT_IMPERSONATE_TARGET
    return max(chrome, key=lambda name: int(name.removeprefix("chrome")))


def validate_impersonate(target: str | None) -> None:
    """Reject a TLS-disguise request this interpreter cannot honour."""

    if not target:
        return
    if not curl_cffi_available():
        raise ValueError(
            f"--impersonate {target} 需要 curl_cffi(层 0 的 TLS/HTTP2 伪装)；"
            "请安装 curl_cffi(推荐)，或去掉该参数改用浏览器引擎。"
        )
    known = curl_cffi_impersonate_targets()
    if known and target not in known:
        preview = ", ".join(known[:6])
        raise ValueError(
            f"未知 impersonate 目标: {target}；本机 curl_cffi 可用目标示例: {preview} …"
        )


def validate_identity_headers(user_agent: str | None, referer: str | None) -> None:
    """Reject identity header values that are malformed or could inject extra headers."""

    if user_agent is not None and (not user_agent.strip() or "\n" in user_agent or "\r" in user_agent):
        raise ValueError("user_agent 不能为空或包含换行符。")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("referer 必须是完整的 http(s) URL；要显式不发 Referer 请传空串。")


def probe_static() -> EngineAvailability:
    """Report the stdlib HTTP engine, which works without any third-party package."""

    optional = (
        ""
        if curl_cffi_available()
        else "；未安装 curl_cffi(推荐: socks5 代理与 --impersonate 的 TLS/HTTP2 伪装不可用)"
    )
    return EngineAvailability(True, f"stdlib HTTP 直连可用{optional}")


def playwright_api_name() -> str | None:
    """Return the stealth-flavoured fork when present, else plain Playwright."""

    for name in ("patchright", "playwright"):
        if importlib.util.find_spec(name) is not None:
            return name
    return None


def probe_playwright() -> EngineAvailability:
    """Report the plain rendering engine, which deliberately has no solver."""

    name = playwright_api_name()
    if name is None:
        return EngineAvailability(False, "未安装 playwright/patchright", ("playwright", "patchright"))
    return EngineAvailability(True, f"{name} 已安装(仅渲染，不求解挑战)")


def probe_scrapling() -> EngineAvailability:
    """Report the anti-detect engine that solves Cloudflare/Turnstile challenges."""

    if importlib.util.find_spec("scrapling") is None:
        return EngineAvailability(False, "未安装 scrapling", ("scrapling[fetchers]",))
    try:
        from scrapling.fetchers import StealthyFetcher  # noqa: F401
    except Exception as exc:
        return EngineAvailability(False, f"StealthyFetcher 不可导入: {exc}", ("scrapling[fetchers]",))
    return EngineAvailability(True, "StealthyFetcher 可导入")


def probe_cloak_cdp() -> EngineAvailability:
    """Report the CloakBrowser fingerprint base, which still needs layer 2 to drive pages."""

    layer_two = probe_scrapling()
    if not layer_two.ok:
        return EngineAvailability(False, f"层 2 未就绪: {layer_two.detail}", ("scrapling[fetchers]",))
    if importlib.util.find_spec("cloakbrowser") is None:
        return EngineAvailability(False, "未安装 cloakbrowser", ("cloakbrowser",))
    return EngineAvailability(True, "cloakbrowser + StealthyFetcher 就绪")


def probe_scrapling_cli() -> EngineAvailability:
    """Report the CLI entry point, which only exists for PATH/安装排障."""

    executable = shutil.which("scrapling")
    if not executable:
        return EngineAvailability(False, "未在 PATH 找到 scrapling CLI", ("scrapling 命令",))
    return EngineAvailability(True, executable)


ENGINES: dict[str, EngineSpec] = {
    spec.name: spec
    for spec in (
        EngineSpec("static", 0, frozenset({CAP_HTTP}), (), probe_static),
        EngineSpec(
            "playwright",
            1,
            frozenset({CAP_HTTP, CAP_RENDER}),
            ("playwright|patchright",),
            probe_playwright,
        ),
        EngineSpec(
            "scrapling", 2, frozenset({CAP_RENDER, CAP_SOLVE}), ("scrapling[fetchers]",), probe_scrapling
        ),
        EngineSpec(
            "cloak-cdp",
            3,
            frozenset({CAP_RENDER, CAP_SOLVE, CAP_CDP}),
            ("cloakbrowser",),
            probe_cloak_cdp,
        ),
        EngineSpec(
            "scrapling-cli",
            3,
            frozenset({CAP_RENDER, CAP_SOLVE}),
            ("scrapling 命令",),
            probe_scrapling_cli,
            in_auto=False,
        ),
    )
}

ENGINE_CHOICES = ("auto", "static", "playwright", "scrapling", "cloak-cdp", "scrapling-cli")
WORKER_ENGINE_CHOICES = tuple(name for name in ENGINE_CHOICES if name != "auto")

_AVAILABILITY_CACHE: dict[str, EngineAvailability] = {}


def engine_availability(name: str) -> EngineAvailability:
    """Probe one engine once per process; probing never raises."""

    if name not in ENGINES:
        raise ValueError(f"未知引擎: {name}")
    cached = _AVAILABILITY_CACHE.get(name)
    if cached is None:
        try:
            cached = ENGINES[name].probe()
        except Exception as exc:  # 探测失败按不可用处理，不中断升档
            cached = EngineAvailability(False, f"探测失败: {exc}", ())
        _AVAILABILITY_CACHE[name] = cached
    return cached


def reset_availability_cache() -> None:
    """Forget cached probe results (tests and long-lived callers)."""

    _AVAILABILITY_CACHE.clear()


def engine_capabilities(selected: str) -> frozenset[str]:
    """Return the capability union an explicit engine or an ``auto`` run can reach."""

    if selected != "auto":
        return ENGINES[selected].capabilities
    reachable = [name for name in available_engines() if ENGINES[name].in_auto]
    if not reachable:  # 无可用引擎时按全部声明能力校验，保持旧告警口径
        reachable = [spec.name for spec in ENGINES.values() if spec.in_auto]
    capabilities: set[str] = set()
    for name in reachable:
        capabilities |= ENGINES[name].capabilities
    return frozenset(capabilities)


def engine_order(selected: str) -> list[str]:
    """List engines to try: explicit selection stays strict, ``auto`` upgrades by level."""

    if selected != "auto":
        return [selected]
    return [name for name in available_engines() if ENGINES[name].in_auto]


def available_engines() -> tuple[str, ...]:
    """List installed engines from the lowest capability level up."""

    return tuple(
        spec.name
        for spec in sorted(ENGINES.values(), key=lambda item: (item.level, item.name))
        if engine_availability(spec.name).ok
    )


def attempt_kind(reasons: Sequence[str], error: str | None) -> str:
    """Classify a failed attempt so callers can tell missing deps from real blocks."""

    if error is not None:
        return KIND_UNAVAILABLE if UNAVAILABLE_ERROR_MARKER in error else KIND_RUNTIME
    blockers = [reason for reason in reasons if not reason.startswith("content_too_short")]
    return KIND_BLOCKED if blockers else KIND_EMPTY


def stops_auto_escalation(result: FetchResult) -> bool:
    """Tell whether a server status makes further engine upgrades pointless.

    404/410 是资源级结论，换浏览器或换指纹不会改变服务端答案；但正文若仍带
    挑战特征，说明这次状态码可能来自拦截层，仍应继续升档。
    """

    return result.status in TERMINAL_STATUS_CODES and not result.block_reasons


def accepts_by_content(result: FetchResult, byte_count: int, expected_texts: list[str]) -> bool:
    """Tell whether a 4xx response may be accepted because its body is verified content.

    站点用 403 拒绝可疑请求却仍下发完整正文时，正文侧不会有任何拦截信号；这时只有调用方
    自己断言过正文、且正文达到正常页面量级，才把状态码当作告警而不是失败。
    """

    return (
        result.status in SOFT_STATUS_CODES
        and bool(expected_texts)
        and byte_count >= SOFT_STATUS_MIN_BYTES
        and extract_title(result.html) is not None
    )


def validation_reasons(result: FetchResult, min_bytes: int, expected_texts: list[str]) -> list[str]:
    reasons = list(result.block_reasons)
    byte_count = len(result.html.encode("utf-8", errors="replace"))
    if byte_count < min_bytes:
        reasons.append(f"content_too_short:{byte_count}")
    for expected in expected_texts:
        if expected not in result.html:
            reasons.append(f"missing_expected_text:{expected}")
    if result.status is None or result.status < 400:
        return reasons
    if not reasons and accepts_by_content(result, byte_count, expected_texts):
        note = f"http_status:{result.status}:accepted_by_content"
        if note not in result.notes:
            result.notes.append(note)
        logging.warning(
            "HTTP %s 但正文通过内容校验(%s 字节，期望文本全部命中): 站点可能对可疑请求回错误状态码"
            "却仍下发正文，按可用内容接受，不再为此升档；状态码保留在 meta 的 status/notes。"
            "这类正文可能尚未水合(样式/懒加载图片未就绪)，需要完整客户端渲染时显式指定更高层引擎。",
            result.status,
            byte_count,
        )
        return []
    return [*reasons, f"http_status:{result.status}"]


def validate_options(options: FetchOptions) -> None:
    parsed = urlparse(options.url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url 必须是完整的 HTTP(S) URL。")
    if options.engine not in ENGINE_CHOICES:
        raise ValueError(f"未知 engine: {options.engine} (可选: {', '.join(ENGINE_CHOICES)})")
    if options.wait_until not in WAIT_UNTIL_CHOICES:
        raise ValueError(
            f"未知 wait_until: {options.wait_until} (可选: {', '.join(WAIT_UNTIL_CHOICES)})"
        )
    validate_impersonate(options.impersonate)
    validate_identity_headers(options.user_agent, options.referer)
    if options.impersonate and options.engine not in {"auto", "static"}:
        logging.warning(
            "--impersonate 只作用于层 0(static)；%s 由浏览器自己完成 TLS 指纹，已忽略该参数。",
            options.engine,
        )
    capabilities = engine_capabilities(options.engine)
    if CAP_SOLVE in capabilities:
        if options.timeout_ms < MIN_SOLVER_TIMEOUT_MS:
            raise ValueError(
                f"启用 Cloudflare 求解时 timeout_ms 不得低于 {MIN_SOLVER_TIMEOUT_MS}。"
            )
    elif options.timeout_ms < 1_000:
        raise ValueError("timeout_ms 至少为 1000。")
    if options.engine == "static":
        if options.headful:
            raise ValueError("static 引擎不启动浏览器，--headful 无意义；请改用 playwright 及以上层。")
        skipped = [
            flag
            for flag, enabled in (
                ("--real-chrome", options.real_chrome),
                ("--geoip", options.geoip),
                ("--humanize", options.humanize),
                ("--hide-canvas", options.hide_canvas),
                ("--network-idle", options.network_idle),
                ("--wait-until", options.wait_until != DEFAULT_WAIT_UNTIL),
                ("--screenshot", bool(options.screenshot)),
            )
            if enabled
        ]
        if skipped:
            logging.warning("static 引擎忽略浏览器专属参数: %s", ", ".join(skipped))
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
            raise ProxyUnavailableError(
                "未发现可用本地代理 (已按本机登记候选探测)。"
                "请用 --proxy 指定代理 URL，或设置 SCRAPE_PROXY，或先登记可用代理后重试。"
            )
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
        "wait_until": options.wait_until,
        "post_wait_ms": options.post_wait_ms,
        "challenge_wait_ms": options.challenge_wait_ms,
        "locale": options.locale,
        "timezone": options.timezone,
        "user_agent": options.user_agent,
        "referer": options.referer,
        "geoip": options.geoip,
        "humanize": options.humanize,
        "hide_canvas": options.hide_canvas,
        "impersonate": options.impersonate,
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
    order = engine_order(options.engine)
    skipped = (
        [
            name
            for name, spec in sorted(ENGINES.items(), key=lambda item: item[1].level)
            if spec.in_auto and name not in order
        ]
        if options.engine == "auto"
        else []
    )
    if options.headful:
        log_manual_verification_hint(options.challenge_wait_ms, headful=True)
    if skipped:
        logging.info(
            "缺件或未启用，已跳过: %s",
            ", ".join(f"{name}({engine_availability(name).reason()})" for name in skipped),
        )
        if any(engine_availability(name).ok is False for name in skipped):
            logging.info(
                "依赖可能装在别的 Python 环境: 请改用该环境的解释器运行本脚本，"
                "或用 check_environment.py --list-envs 查看哪个环境具备所需层。"
            )
    if not order:
        for name in skipped:
            availability = engine_availability(name)
            attempts.append(
                FetchAttempt(
                    engine=name,
                    ok=False,
                    elapsed_sec=0.0,
                    kind=KIND_UNAVAILABLE,
                    error=f"引擎不可用: {availability.reason()}",
                )
            )
        raise FetchFailed(url, tuple(attempts))

    for engine in order:
        started = time.perf_counter()
        availability = engine_availability(engine)
        if not availability.ok:
            attempts.append(
                FetchAttempt(
                    engine=engine,
                    ok=False,
                    elapsed_sec=0.0,
                    kind=KIND_UNAVAILABLE,
                    error=f"引擎不可用: {availability.reason()}",
                )
            )
            logging.warning("跳过 %s: %s", engine, availability.reason())
            continue
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
                kind=KIND_OK if not reasons else attempt_kind(reasons, None),
                rejected_html=result.html if reasons else None,
            )
            attempts.append(attempt)
            if reasons:
                if options.engine == "auto" and stops_auto_escalation(result):
                    logging.warning(
                        "站点返回 HTTP %s；auto 停止升档，避免用更高层引擎重复请求同一不可用资源。"
                        "如需确认是否为站点可见性问题，可在同一会话中用对照页或公开接口核对，"
                        "不要为单个 404/410 另起浏览器。",
                        result.status,
                    )
                    break
                continue
            return FetchOutcome(result=result, attempts=tuple(attempts), proxy=proxy)
        except Exception as exc:
            message = str(exc)
            attempts.append(
                FetchAttempt(
                    engine=engine,
                    ok=False,
                    elapsed_sec=round(time.perf_counter() - started, 3),
                    error=message,
                    kind=attempt_kind((), message),
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
                {
                    "url": exc.url,
                    "schema_version": 2,
                    "summary": exc.describe(),
                    "attempts": [attempt.as_metadata() for attempt in exc.attempts],
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        logging.error("所有引擎均失败:%s；尝试记录: %s", exc.describe(), attempts_path)
        raise

    write_attempt_diagnostics(outcome.attempts, output)
    save_success(
        outcome.result,
        output,
        [attempt.as_metadata() for attempt in outcome.attempts],
    )
    notes = f" | notes={','.join(outcome.result.notes)}" if outcome.result.notes else ""
    logging.info(
        "成功保存: %s | engine=%s | status=%s | bytes=%s | elapsed=%ss%s",
        output,
        outcome.result.engine,
        outcome.result.status,
        len(outcome.result.html.encode("utf-8", errors="replace")),
        outcome.result.elapsed_sec,
        notes,
    )
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="按能力分层抓取页面并保存渲染后 HTML(static → playwright → scrapling → cloak-cdp)。"
    )
    parser.add_argument("--url", help="目标 HTTP(S) URL。")
    parser.add_argument("--out", default="page.html", help="成功页面的输出路径。")
    parser.add_argument(
        "--proxy", default=os.getenv("SCRAPE_PROXY"), help="代理 URL；也可设置 SCRAPE_PROXY。"
    )
    parser.add_argument(
        "--discover-proxy",
        action="store_true",
        help="未指定代理时按本机登记文件 (~/.config/proxy-resources.json) 中的候选依次探测。",
    )
    parser.add_argument(
        "--engine",
        choices=ENGINE_CHOICES,
        default="auto",
        help=(
            "auto 按可用层从低到高尝试:static → playwright → scrapling → cloak-cdp；"
            "显式指定某个引擎时缺件会直接失败。"
        ),
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=DEFAULT_TIMEOUT_MS,
        help="每个引擎的操作超时，默认 300000；层 0/1 可用更小值。",
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
        "--wait-until",
        choices=WAIT_UNTIL_CHOICES,
        default=DEFAULT_WAIT_UNTIL,
        help=(
            "判定页面加载完成并取源码的条件(层 1/2/3, 层 0 忽略): commit | domcontentloaded | "
            "load | networkidle，默认 load；长连接/轮询站点用完 networkidle 可能一直不空闲时，"
            "改用 load 或 domcontentloaded 配合 --post-wait-ms/--wait-selector。"
        ),
    )
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
    parser.add_argument(
        "--real-chrome", action="store_true", help="层 1/2 使用系统 Chrome 而非安装的浏览器。"
    )
    parser.add_argument(
        "--profile-dir",
        help="持久配置根目录，用于复用 cookie/localStorage；按引擎分子目录(playwright/scrapling/cloak)。",
    )
    parser.add_argument(
        "--executable-path", help="自定义 Chromium/Chrome 绝对路径(层 1/2 可用)。"
    )
    parser.add_argument(
        "--network-idle", action="store_true", help="等待 networkidle；长连接页面可能不适用。"
    )
    parser.add_argument(
        "--impersonate",
        help=(
            "层 0(static) 用 curl_cffi 做 TLS/HTTP2 客户端伪装(需安装 curl_cffi):"
            "如 chrome124、chrome136、safari184；可过部分站点的 TLS/客户端指纹检查，"
            "但不解 JS 挑战。浏览器层自带指纹，会告警忽略。"
        ),
    )
    parser.add_argument(
        "--user-agent",
        help=(
            "覆盖各层默认 User-Agent。默认: 层 0 用固定 Chrome/124 串、层 1 用浏览器真实 UA"
            "(无头会带 HeadlessChrome 标记)、层 2/3 由 Scrapling 生成；与 --impersonate 同用时"
            "以本参数为准，否则层 0 让 impersonate 目标决定 UA，避免版本自相矛盾。"
        ),
    )
    referer_group = parser.add_mutually_exclusive_group()
    referer_group.add_argument(
        "--referer",
        help=(
            "发送指定 Referer(完整 http(s) URL)。层 0 加请求头、层 1 为导航带 referer、"
            "层 2/3 走 extra_headers 并覆盖 Scrapling 默认的 Google referer。"
        ),
    )
    referer_group.add_argument(
        "--no-referer",
        action="store_true",
        help="显式不发送 Referer；层 2/3 会同时关掉 Scrapling 默认的 Google referer。",
    )
    parser.add_argument("--screenshot", help="验证完成后保存全页截图。")
    parser.add_argument("--allow-direct", action="store_true", help="代理不可达时允许直连。")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--worker-engine",
        choices=WORKER_ENGINE_CHOICES,
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
        wait_until=args.wait_until,
        expected_texts=tuple(args.expect_text),
        post_wait_ms=args.post_wait_ms,
        challenge_wait_ms=args.challenge_wait_ms,
        min_bytes=args.min_bytes,
        locale=args.locale,
        timezone=args.timezone,
        user_agent=args.user_agent,
        referer="" if args.no_referer else args.referer,
        geoip=args.geoip,
        humanize=args.humanize,
        hide_canvas=args.hide_canvas,
        real_chrome=args.real_chrome,
        profile_dir=args.profile_dir,
        executable_path=args.executable_path,
        network_idle=args.network_idle,
        impersonate=args.impersonate,
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
