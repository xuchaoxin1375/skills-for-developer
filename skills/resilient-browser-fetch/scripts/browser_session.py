"""Batch-fetch same-origin pages in one layer-1 browser (no challenge solving).

Use this when the pages need rendering (JS) but not challenge solving, and the
machine only has layer 1 (``playwright``/``patchright``). It keeps **one browser
and one context** alive and opens one tab per page under a concurrency limit, so
cookies/verification state from the warmed homepage are reused instead of paying
a browser launch per URL.

Deliberately different from the other two sessions:

- vs ``site_session.SiteSessionManager`` (layer 2+): no Cloudflare solving, no
  revalidation barrier; a challenge page raises ``PageRejectedError`` so the
  caller decides to升档. It also does not need scrapling at all.
- vs ``static_session.StaticBatchSession`` (layer 0): real DOM, so
  ``expected_selector``/``wait_selector`` are supported and ``--headful`` +
  ``challenge_wait_ms`` can wait for a human to finish a verification.

The public surface mirrors the other sessions (``start``/``close``/``warmup``/
``fetch``/``fetch_many`` and the same ``SiteRequest``/``FetchResult`` contracts),
so callers can swap implementations by capability.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import urlparse, urlsplit

from resilient_fetch import (
    EngineUnavailableError,
    FetchError,
    FetchResult,
    ProxyUnavailableError,
    block_reasons,
    discover_local_proxy,
    extract_title,
    package_versions,
    playwright_api_name,
    redact_proxy,
    validate_identity_headers,
    validation_reasons,
    wait_for_manual_verification_async,
    wait_for_proxy,
)
from site_session import (
    PageRejectedError,
    PageTimeoutError,
    SiteRequest,
    SiteSessionError,
    WarmupError,
    _normalized_path,  # 与其它会话共用同一 URL 语义，避免多套实现漂移
    _origin,
    _validate_http_url,
)

__all__ = ["BrowserBatchSession", "BrowserSessionOptions", "BrowserSessionState"]


class BrowserSessionState(str, Enum):
    """Describe the lifecycle of a layer-1 browser batch session."""

    NEW = "new"
    IDLE = "idle"
    WARMING = "warming"
    READY = "ready"
    CLOSED = "closed"


@dataclass(frozen=True)
class BrowserSessionOptions:
    """Configure the shared browser, proxy, identity, and page limits of a batch."""

    home_url: str
    proxy: str | None = None
    discover_proxy: bool = False
    allow_direct: bool = False
    max_pages: int = 8
    concurrency: int = 4
    timeout_ms: int = 60_000
    wall_timeout_ms: int = 120_000
    retries: int = 1
    retry_delay: float = 1.0
    post_wait_ms: int = 0
    min_bytes: int = 300
    expected_home_texts: tuple[str, ...] = ()
    home_wait_selector: str | None = None
    locale: str | None = None
    timezone: str | None = None
    user_agent: str | None = None
    referer: str | None = None
    headless: bool = True
    challenge_wait_ms: int = 0
    network_idle: bool = False
    real_chrome: bool = False
    executable_path: str | None = None
    profile_dir: str | None = None
    screenshot_dir: str | None = None

    def __post_init__(self) -> None:
        """Validate the settings that protect a shared browser session."""

        _validate_http_url(self.home_url)
        if self.max_pages < 1:
            raise ValueError("max_pages 必须大于 0。")
        if not 1 <= self.concurrency <= self.max_pages:
            raise ValueError("concurrency 必须在 1 和 max_pages 之间。")
        if self.timeout_ms < 1_000:
            raise ValueError("timeout_ms 至少为 1000。")
        if self.wall_timeout_ms < self.timeout_ms:
            raise ValueError("wall_timeout_ms 不得小于 timeout_ms。")
        if not 1 <= self.retries <= 3:
            raise ValueError("retries 必须在 1 到 3 之间。")
        if self.retry_delay < 0:
            raise ValueError("retry_delay 不得为负数。")
        if self.min_bytes < 1:
            raise ValueError("min_bytes 必须大于 0。")
        if self.challenge_wait_ms < 0:
            raise ValueError("challenge_wait_ms 不得为负数。")
        if self.challenge_wait_ms and self.headless:
            raise ValueError("challenge_wait_ms 需要 headless=False 才能人工过验证，无头模式下无意义。")
        if self.post_wait_ms < 0:
            raise ValueError("post_wait_ms 不得为负数。")
        validate_identity_headers(self.user_agent, self.referer)


class BrowserBatchSession:
    """Keep one layer-1 browser/context warm, then render same-origin pages in tabs."""

    def __init__(self, options: BrowserSessionOptions) -> None:
        """Store configuration without launching a browser or writing files."""

        self.options = options
        self._state = BrowserSessionState.NEW
        self._ready = asyncio.Event()
        self._warmup_lock = asyncio.Lock()
        self._tab_slots = asyncio.Semaphore(options.concurrency)
        self._warmup_result: FetchResult | None = None
        self._effective_proxy: str | None = None
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    @property
    def state(self) -> BrowserSessionState:
        """Return the current batch-session state."""

        return self._state

    @property
    def effective_proxy(self) -> str | None:
        """Return the proxy selected when the session started."""

        return self._effective_proxy

    async def __aenter__(self) -> BrowserBatchSession:
        """Start the session and return this object."""

        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the browser and drop the profile after all callers leave the context."""

        await self.close()

    async def start(self) -> None:
        """Resolve the proxy; the browser itself starts lazily on first use."""

        if self._state is not BrowserSessionState.NEW:
            raise SiteSessionError("站点会话只能启动一次。")
        self._effective_proxy = self._resolve_proxy()
        self._state = BrowserSessionState.IDLE
        logging.info(
            "启动层 1 批量会话(%s)，代理=%s",
            "无头" if self.options.headless else "有头",
            redact_proxy(self._effective_proxy) or "直连",
        )

    async def close(self) -> None:
        """Close context/browser/playwright; a caller-supplied profile_dir is left on disk."""

        if self._state is BrowserSessionState.CLOSED:
            return
        self._ready.clear()
        self._state = BrowserSessionState.CLOSED
        for closer in (self._context, self._browser):
            if closer is None:
                continue
            try:
                await closer.close()
            except Exception as exc:  # 关闭阶段的异常不应掩盖业务错误
                logging.warning("关闭浏览器资源失败: %s", exc)
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logging.warning("停止 playwright 失败: %s", exc)
        self._context = None
        self._browser = None
        self._playwright = None

    async def warmup(self, *, force: bool = False) -> FetchResult:
        """Render the homepage once (single-flight) to validate route and content."""

        self._ensure_started()
        async with self._warmup_lock:
            if not force and self._ready.is_set() and self._warmup_result is not None:
                return self._warmup_result
            self._ready.clear()
            self._state = BrowserSessionState.WARMING
            request = SiteRequest(
                self.options.home_url,
                expected_texts=self.options.expected_home_texts,
                wait_selector=self.options.home_wait_selector,
                min_bytes=self.options.min_bytes,
            )
            try:
                result = await self._render_once(request)
                reasons = self._validation_reasons(request, result)
                if reasons:
                    raise WarmupError(request, result, reasons)
            except BaseException:
                self._ready.clear()
                if self._state is not BrowserSessionState.CLOSED:
                    self._state = BrowserSessionState.IDLE
                raise
            self._warmup_result = result
            self._ready.set()
            self._state = BrowserSessionState.READY
            logging.info(
                "首页渲染预热完成: %s (%s ms)", result.final_url or request.url, result.elapsed_sec * 1000
            )
            return result

    async def fetch(self, request: SiteRequest | str) -> FetchResult:
        """Render one same-origin page in its own tab; challenges are reported, not solved."""

        self._ensure_started()
        normalized = request if isinstance(request, SiteRequest) else SiteRequest(request)
        self._ensure_same_origin(normalized.url)
        await self.warmup()
        await self._ready.wait()

        async with self._tab_slots:
            result = await self._render_with_retries(normalized)

        reasons = self._validation_reasons(normalized, result)
        if reasons:
            if result.block_reasons:
                logging.warning(
                    "层 1 会话遇到挑战页(无求解能力)，建议升档到 site_session.SiteSessionManager、"
                    "改用 --headful 人工验证，或安装层 2: %s",
                    normalized.url,
                )
            raise PageRejectedError(normalized, result, reasons)
        return result

    async def fetch_many(self, requests: Sequence[SiteRequest | str]) -> list[FetchResult]:
        """Warm once, then render pages concurrently within the configured tab limit."""

        await self.warmup()
        tasks = [asyncio.create_task(self.fetch(request)) for request in requests]
        try:
            return list(await asyncio.gather(*tasks))
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    # ---- 内部实现 ----

    async def _render_with_retries(self, request: SiteRequest) -> FetchResult:
        """Render one page, retrying transient navigation errors within the wall budget."""

        attempts = max(1, self.options.retries)
        last: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.wait_for(
                    self._render_once(request), timeout=self.options.wall_timeout_ms / 1000
                )
            except asyncio.TimeoutError as exc:
                raise PageTimeoutError(
                    f"页面超过硬超时 {self.options.wall_timeout_ms} ms: {request.url}"
                ) from exc
            except (PageRejectedError, PageTimeoutError, EngineUnavailableError):
                raise
            except FetchError as exc:
                last = exc
                if attempt >= attempts:
                    break
                logging.warning("页面渲染失败 %s/%s: %s", attempt, attempts, exc)
                await asyncio.sleep(self.options.retry_delay)
        raise last if last is not None else FetchError(f"页面渲染失败: {request.url}")

    async def _render_once(self, request: SiteRequest) -> FetchResult:
        """Open a tab, navigate, wait as requested, and return the rendered HTML."""

        context = await self._ensure_context()
        started = time.perf_counter()
        page = await context.new_page()
        try:
            try:
                goto_kwargs: dict[str, Any] = {
                    "timeout": self.options.timeout_ms,
                    "wait_until": "load",
                }
                if self.options.referer:
                    goto_kwargs["referer"] = self.options.referer
                response = await page.goto(request.url, **goto_kwargs)
            except Exception as exc:
                raise self._as_fetch_error(request.url, exc) from exc
            if self.options.network_idle:
                await self._wait_for_network_idle(page)
            if self.options.challenge_wait_ms and not self.options.headless:
                cleared, _waited = await wait_for_manual_verification_async(
                    lambda: page.content(),
                    self.options.challenge_wait_ms,
                    label=request.url,
                    headful=True,
                )
                if cleared:
                    await page.wait_for_timeout(1_500)
            await self._check_dom_expectations(request, page, started)
            if self.options.post_wait_ms:
                await page.wait_for_timeout(self.options.post_wait_ms)
            page_html = await page.content()
            status = getattr(response, "status", None)
            result = self._result(request, page_html, status, page, started)
            await self._maybe_screenshot(page, request.url)
            return result
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def _check_dom_expectations(
        self, request: SiteRequest, page: Any, started: float
    ) -> None:
        """Fail fast on a missing selector: layer 1 has a DOM, so both are checkable."""

        if request.wait_selector:
            try:
                await page.wait_for_selector(
                    request.wait_selector, state="visible", timeout=self.options.timeout_ms
                )
            except Exception as exc:
                raise PageRejectedError(
                    request,
                    self._result(request, "", None, page, started),
                    [f"missing_wait_selector:{request.wait_selector}"],
                ) from exc
        if request.expected_selector:
            try:
                element = await page.query_selector(request.expected_selector)
            except Exception as exc:
                raise PageRejectedError(
                    request,
                    self._result(request, "", None, page, started),
                    [f"invalid_expected_selector:{request.expected_selector}"],
                ) from exc
            if element is None:
                raise PageRejectedError(
                    request,
                    self._result(request, "", None, page, started),
                    [f"missing_expected_selector:{request.expected_selector}"],
                )

    def _result(
        self, request: SiteRequest, page_html: str, status: int | None, page: Any, started: float
    ) -> FetchResult:
        return FetchResult(
            engine="playwright",
            url=request.url,
            final_url=str(getattr(page, "url", request.url) or request.url),
            status=status,
            html=page_html,
            elapsed_sec=round(time.perf_counter() - started, 3),
            title=extract_title(page_html),
            block_reasons=block_reasons(page_html),
            versions=package_versions(),
        )

    async def _maybe_screenshot(self, page: Any, url: str) -> None:
        if not self.options.screenshot_dir:
            return
        directory = Path(self.options.screenshot_dir)
        directory.mkdir(parents=True, exist_ok=True)
        name = request_slug(url) + ".png"
        try:
            await page.screenshot(path=str(directory / name), full_page=True)
        except Exception as exc:
            logging.warning("截图失败 %s: %s", url, exc)

    async def _wait_for_network_idle(self, page: Any) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=self.options.timeout_ms)
        except Exception:
            logging.debug("等待 networkidle 超时，按当前页面继续。")

    async def _ensure_context(self) -> Any:
        """Launch the browser and context once, reusing the warmed session state."""

        if self._context is not None:
            return self._context
        factory = load_async_playwright()
        self._playwright = await factory().start()
        launch_kwargs: dict[str, Any] = {"headless": self.options.headless}
        if self.options.executable_path:
            launch_kwargs["executable_path"] = self.options.executable_path
        elif self.options.real_chrome:
            launch_kwargs["channel"] = "chrome"
        proxy = playwright_proxy_config(self._effective_proxy)
        if proxy:
            launch_kwargs["proxy"] = proxy
        if self.options.profile_dir:
            self._context = await self._playwright.chromium.launch_persistent_context(
                self.options.profile_dir, **launch_kwargs, **self._context_kwargs()
            )
        else:
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            self._context = await self._browser.new_context(**self._context_kwargs())
        logging.info("层 1 浏览器就绪: 并发上限 %s", self.options.concurrency)
        return self._context

    def _context_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self.options.locale:
            kwargs["locale"] = self.options.locale
        if self.options.timezone:
            kwargs["timezone_id"] = self.options.timezone
        if self.options.user_agent:
            kwargs["user_agent"] = self.options.user_agent
        return kwargs

    def _validation_reasons(self, request: SiteRequest, result: FetchResult) -> list[str]:
        min_bytes = request.min_bytes or self.options.min_bytes
        reasons = validation_reasons(result, min_bytes, [])
        page_html = result.html if request.case_sensitive else result.html.casefold()
        missing = [
            expected
            for expected in request.expected_texts
            if (expected if request.case_sensitive else expected.casefold()) not in page_html
        ]
        status_reasons = [reason for reason in reasons if reason.startswith("http_status:")]
        content_reasons = [reason for reason in reasons if not reason.startswith("http_status:")]
        if result.final_url and _origin(result.final_url) != _origin(request.url):
            content_reasons.append(f"final_origin_mismatch:{result.final_url}")
        elif (
            request.require_same_path
            and result.final_url
            and _normalized_path(result.final_url) != _normalized_path(request.url)
        ):
            content_reasons.append(f"final_path_mismatch:{result.final_url}")
        return (
            content_reasons
            + [f"missing_expected_text:{expected}" for expected in missing]
            + status_reasons
        )

    def _ensure_started(self) -> None:
        if self._state in {BrowserSessionState.NEW, BrowserSessionState.CLOSED}:
            raise SiteSessionError("请先通过 async with 或 start() 启动站点会话。")

    def _ensure_same_origin(self, url: str) -> None:
        if _origin(url) != _origin(self.options.home_url):
            raise ValueError(f"批量会话只接受与首页同源的 URL: {url}")

    def _resolve_proxy(self) -> str | None:
        if self.options.proxy:
            if not wait_for_proxy(self.options.proxy):
                raise ProxyUnavailableError(f"代理不可达: {redact_proxy(self.options.proxy)}")
            return self.options.proxy
        if not self.options.discover_proxy:
            return None
        discovered = discover_local_proxy()
        if discovered:
            return discovered
        if self.options.allow_direct:
            logging.warning("未发现本地代理，已按显式配置允许直连。")
            return None
        raise ProxyUnavailableError("未发现可用本地代理，且未允许直连。")

    @staticmethod
    def _as_fetch_error(url: str, exc: Exception) -> BaseException:
        message = str(exc)
        if "Timeout" in type(exc).__name__ or "Timeout" in message:
            return PageTimeoutError(f"页面渲染超时: {url} ({message})")
        if "Executable doesn't exist" in message or "playwright install" in message:
            return EngineUnavailableError(
                f"未找到浏览器二进制；请运行 `playwright install chromium`，"
                f"或用 real_chrome/executable_path 指定系统浏览器。原始信息: {message}"
            )
        return FetchError(f"页面渲染失败 {url}: {message}")


def load_async_playwright() -> Any:
    """Return the async playwright factory from the preferred installed package."""

    name = playwright_api_name()
    if name is None:
        raise EngineUnavailableError(
            "未安装 playwright/patchright；请安装后运行 `playwright install chromium`，"
            "或用 real_chrome/executable_path 指向系统浏览器。"
        )
    module = importlib.import_module(f"{name}.async_api")
    factory = getattr(module, "async_playwright", None)
    if factory is None:
        raise EngineUnavailableError(f"{name}.async_api 缺少 async_playwright。")
    return factory


def playwright_proxy_config(proxy: str | None) -> dict[str, Any] | None:
    """Translate a proxy URL into Chromium launch options, mirroring layer 1."""

    if not proxy:
        return None
    parsed = urlparse(proxy)
    server = f"{parsed.scheme}://{parsed.hostname or ''}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    entry: dict[str, Any] = {"server": server}
    if parsed.username:
        if parsed.scheme.lower().startswith("socks"):
            raise FetchError("playwright 不支持带凭据的 socks 代理；请改用 http 代理或层 2/3。")
        entry["username"] = parsed.username
        entry["password"] = parsed.password or ""
    return entry


def request_slug(url: str) -> str:
    """Build a filesystem-safe file name stem from a page URL."""

    parsed = urlsplit(url)
    path = (parsed.path or "/").strip("/").replace("/", "_") or "index"
    return f"{parsed.netloc}_{path}"[:120]
