"""Manage one warmed Scrapling browser session for a protected website."""

from __future__ import annotations

import asyncio
import inspect
import logging
import tempfile
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import Any, cast
from urllib.parse import urlsplit

from resilient_fetch import (
    FetchResult,
    ProxyUnavailableError,
    block_reasons,
    discover_local_proxy,
    redact_proxy,
    response_to_result,
    validation_reasons,
    wait_for_proxy,
)

ChallengeCallback = Callable[["ChallengeEvent"], Awaitable[None] | None]
SessionFactory = Callable[..., Any]

__all__ = [
    "ChallengeEvent",
    "PageRejectedError",
    "PageTimeoutError",
    "SiteRequest",
    "SiteSessionError",
    "SiteSessionManager",
    "SiteSessionOptions",
    "SiteSessionState",
    "WarmupError",
]


class SiteSessionState(str, Enum):
    """Describe the lifecycle of a site-scoped browser session."""

    NEW = "new"
    IDLE = "idle"
    WARMING = "warming"
    CHALLENGE = "challenge"
    READY = "ready"
    REVALIDATING = "revalidating"
    CLOSED = "closed"


class SiteSessionError(RuntimeError):
    """Base exception for site-session failures."""


class PageTimeoutError(SiteSessionError):
    """Report that one browser navigation exceeded its hard wall timeout."""


class PageRejectedError(SiteSessionError):
    """Report a response that failed content or challenge validation."""

    def __init__(self, request: SiteRequest, result: FetchResult, reasons: Sequence[str]) -> None:
        """Attach the rejected request, rendered response, and validation reasons."""

        joined = ", ".join(reasons)
        super().__init__(f"页面验证失败: {request.url} ({joined})")
        self.request = request
        self.result = result
        self.reasons = tuple(reasons)


class WarmupError(PageRejectedError):
    """Report that the homepage warmup did not produce a valid business page."""


@dataclass(frozen=True)
class ChallengeEvent:
    """Describe a challenge observed while the visible browser remains usable."""

    url: str
    reasons: tuple[str, ...]
    headless: bool
    wall_timeout_ms: int


@dataclass(frozen=True)
class SiteRequest:
    """Describe one page request and the business-content checks it must pass."""

    url: str
    expected_texts: tuple[str, ...] = ()
    wait_selector: str | None = None
    expected_selector: str | None = None
    min_bytes: int | None = None
    case_sensitive: bool = False
    require_same_path: bool = False

    def __post_init__(self) -> None:
        """Reject malformed URLs and invalid byte thresholds before navigation."""

        _validate_http_url(self.url)
        if self.min_bytes is not None and self.min_bytes < 1:
            raise ValueError("min_bytes 必须大于 0。")


@dataclass(frozen=True)
class SiteSessionOptions:
    """Configure one browser identity shared by a homepage and its child pages."""

    home_url: str
    proxy: str | None = None
    discover_proxy: bool = False
    allow_direct: bool = False
    headless: bool = False
    profile_dir: str | Path | None = None
    max_pages: int = 3
    concurrency: int = 2
    timeout_ms: int = 300_000
    wall_timeout_ms: int = 330_000
    challenge_poll_ms: int = 750
    post_wait_ms: int = 1_000
    min_bytes: int = 300
    max_revalidations: int = 1
    expected_home_texts: tuple[str, ...] = ()
    home_wait_selector: str | None = None
    locale: str | None = None
    timezone: str | None = None
    useragent: str | None = None
    real_chrome: bool = False
    hide_canvas: bool = False
    executable_path: str | Path | None = None

    def __post_init__(self) -> None:
        """Validate settings that protect the shared browser lifecycle."""

        _validate_http_url(self.home_url)
        if self.max_pages < 1:
            raise ValueError("max_pages 必须大于 0。")
        if not 1 <= self.concurrency <= self.max_pages:
            raise ValueError("concurrency 必须在 1 和 max_pages 之间。")
        if self.timeout_ms < 60_000:
            raise ValueError("timeout_ms 不得低于 60000。")
        if self.wall_timeout_ms < self.timeout_ms:
            raise ValueError("wall_timeout_ms 不得小于 timeout_ms。")
        if self.challenge_poll_ms < 100:
            raise ValueError("challenge_poll_ms 不得低于 100。")
        if self.post_wait_ms < 0:
            raise ValueError("post_wait_ms 不得小于 0。")
        if self.min_bytes < 1:
            raise ValueError("min_bytes 必须大于 0。")
        if self.max_revalidations < 0:
            raise ValueError("max_revalidations 不得小于 0。")


def _validate_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"URL 必须是包含主机名的 HTTP(S) 地址: {url}")


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    default_port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port or default_port


def _normalized_path(url: str) -> str:
    path = urlsplit(url).path or "/"
    return path if path == "/" else path.rstrip("/")


def _default_session_factory(**kwargs: Any) -> Any:
    from scrapling.fetchers import AsyncStealthySession

    return AsyncStealthySession(**kwargs)


class SiteSessionManager:
    """Warm one homepage, gate concurrency, and reuse its live browser context."""

    def __init__(
        self,
        options: SiteSessionOptions,
        *,
        on_challenge: ChallengeCallback | None = None,
        session_factory: SessionFactory | None = None,
    ) -> None:
        """Store configuration without launching a browser or writing files."""

        self.options = options
        self.on_challenge = on_challenge
        self._session_factory = session_factory or _default_session_factory
        self._session_context: Any = None
        self._session: Any = None
        self._state = SiteSessionState.NEW
        self._ready = asyncio.Event()
        self._warmup_task_lock = asyncio.Lock()
        self._revalidation_lock = asyncio.Lock()
        self._page_slots = asyncio.Semaphore(options.concurrency)
        self._warmup_task: asyncio.Task[FetchResult] | None = None
        self._warmup_result: FetchResult | None = None
        self._generation = 0
        self._effective_proxy: str | None = None
        self._profile_dir: Path | None = None
        self._temporary_profile: tempfile.TemporaryDirectory[str] | None = None

    @property
    def state(self) -> SiteSessionState:
        """Return the current site-session state."""

        return self._state

    @property
    def effective_proxy(self) -> str | None:
        """Return the proxy selected when the browser session started."""

        return self._effective_proxy

    @property
    def profile_dir(self) -> Path | None:
        """Return the profile directory selected for the live browser."""

        return self._profile_dir

    @property
    def profile_is_temporary(self) -> bool:
        """Return whether this run owns and cleans a fresh profile directory."""

        return self._temporary_profile is not None

    async def __aenter__(self) -> SiteSessionManager:
        """Start the browser session and return this manager."""

        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the shared browser after all callers leave the context."""

        await self.close()

    async def start(self) -> None:
        """Launch exactly one Scrapling persistent browser context."""

        if self._state is not SiteSessionState.NEW:
            raise SiteSessionError("站点会话只能启动一次。")

        self._effective_proxy = self._resolve_proxy()
        self._prepare_profile()
        kwargs = self._session_kwargs()
        logging.info(
            "启动站点会话，代理=%s，profile=%s (%s)",
            redact_proxy(self._effective_proxy) or "直连",
            self._profile_dir,
            "全新临时目录" if self.profile_is_temporary else "持久目录",
        )
        try:
            self._session_context = self._session_factory(**kwargs)
            self._session = await self._session_context.__aenter__()
        except Exception:
            self._session_context = None
            self._session = None
            self._cleanup_temporary_profile()
            raise
        self._state = SiteSessionState.IDLE

    async def close(self) -> None:
        """Stop pending warmup work and close the single browser context."""

        if self._state is SiteSessionState.CLOSED:
            return
        if self._warmup_task and not self._warmup_task.done():
            self._warmup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._warmup_task
        try:
            if self._session_context is not None:
                await self._session_context.__aexit__(None, None, None)
        finally:
            self._session = None
            self._session_context = None
            self._cleanup_temporary_profile()
            self._ready.clear()
            self._state = SiteSessionState.CLOSED

    async def warmup(self, *, force: bool = False, revalidating: bool = False) -> FetchResult:
        """Warm the homepage once and share that in-flight attempt with all callers."""

        self._ensure_started()
        async with self._warmup_task_lock:
            if not force and self._ready.is_set() and self._warmup_result is not None:
                return self._warmup_result
            if self._warmup_task is None or self._warmup_task.done():
                self._ready.clear()
                self._warmup_task = asyncio.create_task(
                    self._perform_warmup(revalidating=revalidating)
                )
            task = self._warmup_task
        return await asyncio.shield(task)

    async def fetch(self, request: SiteRequest | str) -> FetchResult:
        """Fetch one same-origin page after warmup and recover from a new challenge."""

        self._ensure_started()
        normalized = request if isinstance(request, SiteRequest) else SiteRequest(request)
        self._ensure_same_origin(normalized.url)
        await self.warmup()

        for attempt in range(self.options.max_revalidations + 1):
            await self._ready.wait()
            observed_generation = self._generation
            result = await self._fetch_once(normalized, solve_cloudflare=attempt > 0)
            reasons = self._validation_reasons(normalized, result)
            if not reasons:
                if not self._ready.is_set():
                    await self._recover(observed_generation)
                return result
            if self._is_challenge_response(result) and attempt < self.options.max_revalidations:
                logging.warning("页面再次触发验证，暂停新任务并重新预热: %s", normalized.url)
                self._ready.clear()
                await self._recover(observed_generation)
                continue
            raise PageRejectedError(normalized, result, reasons)

        raise SiteSessionError("无法完成页面重验证。")

    async def fetch_many(self, requests: Sequence[SiteRequest | str]) -> list[FetchResult]:
        """Warm once, then fetch pages concurrently within the configured page limit."""

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

    async def _perform_warmup(self, *, revalidating: bool) -> FetchResult:
        self._state = SiteSessionState.REVALIDATING if revalidating else SiteSessionState.WARMING
        request = SiteRequest(
            self.options.home_url,
            expected_texts=self.options.expected_home_texts,
            wait_selector=self.options.home_wait_selector,
            min_bytes=self.options.min_bytes,
        )
        if not self.options.headless:
            logging.info(
                "首页预热已启动；若出现验证，请在可见浏览器中人工完成，硬超时为 %.1f 秒。",
                self.options.wall_timeout_ms / 1000,
            )
        try:
            result = await self._fetch_once(request, solve_cloudflare=True)
            reasons = self._validation_reasons(request, result)
            if reasons:
                raise WarmupError(request, result, reasons)
        except BaseException:
            self._ready.clear()
            if self._state is not SiteSessionState.CLOSED:
                self._state = SiteSessionState.IDLE
            raise

        self._warmup_result = result
        self._generation += 1
        self._ready.set()
        self._state = SiteSessionState.READY
        logging.info("首页预热完成，站点会话已就绪: %s", result.final_url or request.url)
        return result

    async def _recover(self, observed_generation: int) -> None:
        async with self._revalidation_lock:
            if self._ready.is_set() and self._generation > observed_generation:
                return
            await self.warmup(force=True, revalidating=True)

    async def _fetch_once(self, request: SiteRequest, *, solve_cloudflare: bool) -> FetchResult:
        if self._session is None:
            raise SiteSessionError("站点会话尚未启动。")

        monitor_task: asyncio.Task[None] | None = None
        monitor_stop = asyncio.Event()

        async def page_setup(page: Any) -> None:
            nonlocal monitor_task
            monitor_task = asyncio.create_task(
                self._monitor_challenge(page, request.url, stop_event=monitor_stop)
            )

        kwargs: dict[str, Any] = {
            "solve_cloudflare": solve_cloudflare,
            "timeout": self.options.timeout_ms,
            "wait": self.options.post_wait_ms,
            "network_idle": False,
            "disable_resources": False,
            "page_setup": page_setup,
        }
        browser_wait_selector = request.wait_selector or request.expected_selector
        if browser_wait_selector:
            kwargs["wait_selector"] = browser_wait_selector
            kwargs["wait_selector_state"] = "visible"

        started = time.perf_counter()
        try:
            async with self._page_slots:
                response = await asyncio.wait_for(
                    self._session.fetch(request.url, **kwargs),
                    timeout=self.options.wall_timeout_ms / 1000,
                )
        except asyncio.TimeoutError as exc:
            raise PageTimeoutError(
                f"页面超过硬超时 {self.options.wall_timeout_ms} ms: {request.url}"
            ) from exc
        finally:
            if monitor_task is not None:
                monitor_stop.set()
                try:
                    await asyncio.wait_for(monitor_task, timeout=2)
                except asyncio.TimeoutError:
                    monitor_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await monitor_task

        return response_to_result("scrapling-session", request.url, response, started)

    async def _monitor_challenge(
        self, page: Any, url: str, *, stop_event: asyncio.Event | None = None
    ) -> None:
        notified = False
        stop = stop_event or asyncio.Event()
        deadline = asyncio.get_running_loop().time() + self.options.wall_timeout_ms / 1000
        wait_for_load_state = getattr(page, "wait_for_load_state", None)
        if callable(wait_for_load_state):
            try:
                await cast(Callable[..., Awaitable[Any]], wait_for_load_state)(
                    "domcontentloaded", timeout=self.options.timeout_ms
                )
            except Exception:
                pass
        while asyncio.get_running_loop().time() < deadline:
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.options.challenge_poll_ms / 1000)
                return
            except asyncio.TimeoutError:
                pass
            try:
                page_html = await page.content()
            except Exception:
                continue
            reasons = tuple(block_reasons(page_html))
            if reasons and not notified:
                notified = True
                self._ready.clear()
                self._state = SiteSessionState.CHALLENGE
                event = ChallengeEvent(
                    url=url,
                    reasons=reasons,
                    headless=self.options.headless,
                    wall_timeout_ms=self.options.wall_timeout_ms,
                )
                logging.warning(
                    "检测到浏览器验证%s: %s",
                    "；可在窗口中人工完成" if not self.options.headless else "",
                    url,
                )
                await self._notify_challenge(event)
            elif notified and not reasons:
                return

    async def _notify_challenge(self, event: ChallengeEvent) -> None:
        if self.on_challenge is None:
            return
        try:
            outcome = self.on_challenge(event)
            if inspect.isawaitable(outcome):
                await outcome
        except Exception as exc:
            logging.warning("挑战通知回调失败，不中止浏览器验证: %s", exc)

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
        if request.expected_selector and not self._selector_exists(
            result.html, request.expected_selector, result.final_url or request.url
        ):
            content_reasons.append(f"missing_expected_selector:{request.expected_selector}")
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

    @staticmethod
    def _selector_exists(page_html: str, selector: str, url: str) -> bool:
        from scrapling import Selector

        return Selector(page_html, url=url).css(selector).get() is not None

    def _is_challenge_response(self, result: FetchResult) -> bool:
        return bool(result.block_reasons) or result.status in {403, 503}

    def _ensure_started(self) -> None:
        if self._state in {SiteSessionState.NEW, SiteSessionState.CLOSED} or self._session is None:
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

    def _prepare_profile(self) -> None:
        if self.options.profile_dir is None:
            self._temporary_profile = tempfile.TemporaryDirectory(
                prefix="resilient-browser-fetch-", ignore_cleanup_errors=True
            )
            self._profile_dir = Path(self._temporary_profile.name)
            return
        self._profile_dir = Path(self.options.profile_dir).expanduser().resolve()
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    def _cleanup_temporary_profile(self) -> None:
        if self._temporary_profile is None:
            return
        self._temporary_profile.cleanup()
        self._temporary_profile = None
        self._profile_dir = None

    def _session_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "headless": self.options.headless,
            "max_pages": self.options.max_pages,
            "timeout": self.options.timeout_ms,
            "solve_cloudflare": True,
            "block_webrtc": True,
            "network_idle": False,
            "disable_resources": False,
            "google_search": False,
        }
        if self._effective_proxy:
            kwargs["proxy"] = self._effective_proxy
        if self._profile_dir is None:
            raise SiteSessionError("浏览器 profile 尚未准备。")
        kwargs["user_data_dir"] = str(self._profile_dir)
        if self.options.locale:
            kwargs["locale"] = self.options.locale
        if self.options.timezone:
            kwargs["timezone_id"] = self.options.timezone
        if self.options.useragent:
            kwargs["useragent"] = self.options.useragent
        if self.options.real_chrome:
            kwargs["real_chrome"] = True
        if self.options.hide_canvas:
            kwargs["hide_canvas"] = True
        if self.options.executable_path is not None:
            kwargs["executable_path"] = str(Path(self.options.executable_path))
        return kwargs
