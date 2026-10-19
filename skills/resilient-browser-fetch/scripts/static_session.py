"""Batch-fetch same-origin pages with the layer-0 (stdlib HTTP) engine.

Use this when a multi-page job only needs static HTML: no browser, no third-party
package (install the recommended ``curl_cffi`` and set ``impersonate`` when the site
checks TLS/client fingerprints), no Cloudflare求解. For JS-rendered or challenge-protected batches use
``site_session.SiteSessionManager`` (layer 2+, with warmup barrier and manual
verification), and let the two share the same ``SiteRequest``/``FetchResult``
contracts so a caller can swap them.

Differences from the browser session, deliberately:

- no challenge solving and no revalidation loop; a challenge page raises
  ``PageRejectedError`` so the caller can decide to升档;
- no CSS-selector checks (no DOM engine): ``expected_selector`` is rejected,
  ``wait_selector`` is ignored with a warning. Use ``expected_texts`` instead;
- concurrency is bounded by a semaphore over worker threads, and each page keeps
  its own hard wall timeout.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from types import TracebackType

from resilient_fetch import (
    FetchError,
    FetchResult,
    ProxyUnavailableError,
    discover_local_proxy,
    fetch_with_static,
    redact_proxy,
    validate_identity_headers,
    validate_impersonate,
    validation_reasons,
    wait_for_proxy,
)
from site_session import (
    PageRejectedError,
    PageTimeoutError,
    SiteRequest,
    SiteSessionError,
    WarmupError,
    _normalized_path,  # 与浏览器会话共用同一 URL 语义，避免两套实现漂移
    _origin,
    _validate_http_url,
)

__all__ = ["StaticBatchSession", "StaticSessionOptions", "StaticSessionState"]


class StaticSessionState(str, Enum):
    """Describe the lifecycle of a static batch session."""

    NEW = "new"
    IDLE = "idle"
    WARMING = "warming"
    READY = "ready"
    CLOSED = "closed"


@dataclass(frozen=True)
class StaticSessionOptions:
    """Configure one proxy and identity shared by every page of a static batch."""

    home_url: str
    proxy: str | None = None
    discover_proxy: bool = False
    allow_direct: bool = False
    max_pages: int = 8
    concurrency: int = 4
    timeout_ms: int = 30_000
    wall_timeout_ms: int = 60_000
    retries: int = 2
    retry_delay: float = 1.0
    min_bytes: int = 300
    expected_home_texts: tuple[str, ...] = ()
    locale: str | None = None
    user_agent: str | None = None
    referer: str | None = None
    impersonate: str | None = None

    def __post_init__(self) -> None:
        """Validate settings that protect a shared static batch."""

        _validate_http_url(self.home_url)
        if self.max_pages < 1:
            raise ValueError("max_pages 必须大于 0。")
        if not 1 <= self.concurrency <= self.max_pages:
            raise ValueError("concurrency 必须在 1 和 max_pages 之间。")
        if self.timeout_ms < 1_000:
            raise ValueError("timeout_ms 不得低于 1000。")
        if self.wall_timeout_ms < self.timeout_ms:
            raise ValueError("wall_timeout_ms 不得小于 timeout_ms。")
        if not 1 <= self.retries <= 3:
            raise ValueError("retries 必须在 1 到 3 之间。")
        if self.retry_delay < 0:
            raise ValueError("retry_delay 不得为负数。")
        if self.min_bytes < 1:
            raise ValueError("min_bytes 必须大于 0。")
        validate_impersonate(self.impersonate)
        validate_identity_headers(self.user_agent, self.referer)


class StaticBatchSession:
    """Warm one homepage over HTTP, then fetch same-origin pages with bounded concurrency."""

    def __init__(self, options: StaticSessionOptions) -> None:
        """Store configuration without touching the network or writing files."""

        self.options = options
        self._state = StaticSessionState.NEW
        self._ready = asyncio.Event()
        self._warmup_lock = asyncio.Lock()
        self._page_slots = asyncio.Semaphore(options.concurrency)
        self._warmup_result: FetchResult | None = None
        self._effective_proxy: str | None = None

    @property
    def state(self) -> StaticSessionState:
        """Return the current batch-session state."""

        return self._state

    @property
    def effective_proxy(self) -> str | None:
        """Return the proxy selected when the session started."""

        return self._effective_proxy

    async def __aenter__(self) -> StaticBatchSession:
        """Start the session and return this object."""

        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the session after all callers leave the context."""

        await self.close()

    async def start(self) -> None:
        """Resolve the proxy once; no browser or profile is involved."""

        if self._state is not StaticSessionState.NEW:
            raise SiteSessionError("站点会话只能启动一次。")
        self._effective_proxy = self._resolve_proxy()
        self._state = StaticSessionState.IDLE
        logging.info("启动静态批量会话，代理=%s", redact_proxy(self._effective_proxy) or "直连")

    async def close(self) -> None:
        """Mark the session closed; nothing else holds resources."""

        if self._state is StaticSessionState.CLOSED:
            return
        self._ready.clear()
        self._state = StaticSessionState.CLOSED

    async def warmup(self, *, force: bool = False) -> FetchResult:
        """Fetch the homepage once (single-flight) to validate route and content."""

        self._ensure_started()
        async with self._warmup_lock:
            if not force and self._ready.is_set() and self._warmup_result is not None:
                return self._warmup_result
            self._ready.clear()
            self._state = StaticSessionState.WARMING
            request = SiteRequest(
                self.options.home_url,
                expected_texts=self.options.expected_home_texts,
                min_bytes=self.options.min_bytes,
            )
            try:
                result = await self._fetch_timed(request)
                reasons = self._validation_reasons(request, result)
                if reasons:
                    raise WarmupError(request, result, reasons)
            except BaseException:
                self._ready.clear()
                if self._state is not StaticSessionState.CLOSED:
                    self._state = StaticSessionState.IDLE
                raise
            self._warmup_result = result
            self._ready.set()
            self._state = StaticSessionState.READY
            logging.info("首页静态预热完成: %s", result.final_url or request.url)
            return result

    async def fetch(self, request: SiteRequest | str) -> FetchResult:
        """Fetch one same-origin page after warmup; challenges are reported, not solved."""

        self._ensure_started()
        normalized = request if isinstance(request, SiteRequest) else SiteRequest(request)
        self._ensure_same_origin(normalized.url)
        self._ensure_supported(normalized)
        await self.warmup()
        await self._ready.wait()

        async with self._page_slots:
            result = await self._fetch_timed(normalized)

        reasons = self._validation_reasons(normalized, result)
        if reasons:
            if result.block_reasons:
                logging.warning(
                    "静态会话疑似遇到挑战页，建议升档到 site_session.SiteSessionManager 或 --engine auto: %s",
                    normalized.url,
                )
            raise PageRejectedError(normalized, result, reasons)
        return result

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

    async def _fetch_timed(self, request: SiteRequest) -> FetchResult:
        """Run one blocking HTTP fetch off the event loop under a hard wall timeout."""

        # 超时后工作线程仍会跑完它自己的 socket 超时(timeout_ms)，因此不会永久占用线程。
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_blocking, request),
                timeout=self.options.wall_timeout_ms / 1000,
            )
        except asyncio.TimeoutError as exc:
            raise PageTimeoutError(
                f"页面超过硬超时 {self.options.wall_timeout_ms} ms: {request.url}"
            ) from exc

    def _fetch_blocking(self, request: SiteRequest) -> FetchResult:
        try:
            return fetch_with_static(
                {
                    "url": request.url,
                    "proxy": self._effective_proxy,
                    "timeout_ms": self.options.timeout_ms,
                    "retries": self.options.retries,
                    "retry_delay": self.options.retry_delay,
                    "locale": self.options.locale,
                    "user_agent": self.options.user_agent,
                    "referer": self.options.referer,
                    "impersonate": self.options.impersonate,
                }
            )
        except FetchError as exc:
            # 批量下并发握手更容易遇到瞬时 TLS/连接错误；错误里带上 URL 才能定位是哪个页面。
            raise FetchError(f"静态抓取失败 {request.url}: {exc}") from exc

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
        if self._state in {StaticSessionState.NEW, StaticSessionState.CLOSED}:
            raise SiteSessionError("请先通过 async with 或 start() 启动站点会话。")

    def _ensure_same_origin(self, url: str) -> None:
        if _origin(url) != _origin(self.options.home_url):
            raise ValueError(f"批量会话只接受与首页同源的 URL: {url}")

    @staticmethod
    def _ensure_supported(request: SiteRequest) -> None:
        if request.expected_selector:
            raise ValueError(
                f"层 0 静态会话不支持 expected_selector(没有 DOM 引擎): {request.expected_selector}"
                "；请改用 expected_texts，或换用 site_session.SiteSessionManager。"
            )
        if request.wait_selector:
            logging.warning("层 0 静态会话不执行 JS，已忽略 wait_selector: %s", request.url)

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
