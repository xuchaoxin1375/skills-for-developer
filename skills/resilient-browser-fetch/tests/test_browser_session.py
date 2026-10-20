"""Cover the layer-1 browser batch session: warmup, tabs, validation, lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any

import browser_session as subject
import pytest
from site_session import PageRejectedError, SiteRequest


class FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status


class FakePage:
    def __init__(self, context: FakeContext, url: str) -> None:
        self._context = context
        self.url = url
        self.closed = False
        self.waits: list[int] = []
        self.screenshot_paths: list[str] = []
        self.dead = False

    async def goto(self, url: str, **_kwargs: Any) -> FakeResponse:
        # 让出事件循环, 否则所有任务一路跑完，观察不到真实的 tab 并发
        await asyncio.sleep(0.01)
        self.url = url
        entry = self._context.routes.get(url)
        if entry is None:
            self.dead = True
            raise RuntimeError(f"unknown route in fake browser: {url}")
        status, html, poll_until = entry
        self._html = html
        self._poll_until = poll_until
        self._polls = 0
        return FakeResponse(status)

    async def wait_for_load_state(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)

    async def wait_for_selector(self, selector: str, **_kwargs: Any) -> None:
        if selector not in self._context.selectors.get(self.url, set()):
            raise RuntimeError(f"selector not found: {selector}")

    async def query_selector(self, selector: str) -> Any:
        return object() if selector in self._context.selectors.get(self.url, set()) else None

    async def screenshot(self, *, path: str, **_kwargs: Any) -> None:
        self.screenshot_paths.append(path)

    async def content(self) -> str:
        self._polls += 1
        if self._polls <= self._poll_until:
            return "<html><head><title>Just a moment...</title></head><body>/cdn-cgi/challenge-platform</body></html>"
        return self._html

    async def close(self) -> None:
        self.closed = True
        self._context.live_pages.discard(self)


def article(title: str, body: str = "业务正文内容足够长可以被识别为有效页面。") -> str:
    return f"<!doctype html><html><head><title>{title}</title></head><body><article><h1>{title}</h1><p>{body * 5}</p></article></body></html>"


class FakeContext:
    def __init__(self, routes: dict[str, tuple[int, str, int]]) -> None:
        self.routes = routes
        self.selectors: dict[str, set[str]] = {}
        self.live_pages: set[FakePage] = set()
        self.max_live = 0
        self.closed = False

    async def new_page(self) -> FakePage:
        page = FakePage(self, "")
        self.live_pages.add(page)
        self.max_live = max(self.max_live, len(self.live_pages))
        return page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self._context = context
        self.closed = False

    async def new_context(self, **_kwargs: Any) -> FakeContext:
        return self._context

    async def close(self) -> None:
        self.closed = True


class FakePlaywright:
    def __init__(self, context: FakeContext) -> None:
        self.chromium = self
        self._context = context
        self.launch_kwargs: dict[str, Any] = {}
        self.stopped = False

    async def launch(self, **kwargs: Any) -> FakeBrowser:
        self.launch_kwargs = kwargs
        return FakeBrowser(self._context)

    async def launch_persistent_context(self, path: str, **kwargs: Any) -> FakeContext:
        self.launch_kwargs = kwargs
        self.persistent_path = path
        return self._context

    async def stop(self) -> None:
        self.stopped = True


class FakeStarter:
    def __init__(self, playwright: FakePlaywright) -> None:
        self._playwright = playwright

    async def start(self) -> FakePlaywright:
        return self._playwright


def install_fake(monkeypatch: pytest.MonkeyPatch, routes: dict[str, tuple[int, str, int]]) -> FakePlaywright:
    context = FakeContext(routes)
    playwright = FakePlaywright(context)
    monkeypatch.setattr(subject, "load_async_playwright", lambda: (lambda: FakeStarter(playwright)))
    monkeypatch.setattr(subject, "wait_for_proxy", lambda proxy, *a, **k: True)
    monkeypatch.setattr(subject, "discover_local_proxy", lambda *a, **k: None)
    return playwright


def options(base: str, **overrides: Any) -> subject.BrowserSessionOptions:
    values: dict[str, Any] = {
        "home_url": f"{base}/",
        "max_pages": 8,
        "concurrency": 2,
        "timeout_ms": 5_000,
        "wall_timeout_ms": 10_000,
        "min_bytes": 1,
    }
    values.update(overrides)
    return subject.BrowserSessionOptions(**values)


@pytest.mark.asyncio
async def test_warmup_is_singleflight_and_reuses_one_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake(monkeypatch, {"https://site.test/": (200, article("Home"), 0)})
    session = subject.BrowserBatchSession(options("https://site.test"))
    async with session:
        first, second = await asyncio.gather(session.warmup(), session.warmup())
        assert first.elapsed_sec >= 0
        assert second is first, "预热单飞，第二次直接复用结果"
        assert session.state is subject.BrowserSessionState.READY
    assert fake.stopped is True, "退出上下文后停止 playwright"
    assert fake._context.closed is True


@pytest.mark.asyncio
async def test_fetch_many_limits_open_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {
        "https://site.test/": (200, article("Home"), 0),
        "https://site.test/a": (200, article("A"), 0),
        "https://site.test/b": (200, article("B"), 0),
        "https://site.test/c": (200, article("C"), 0),
    }
    install_fake(monkeypatch, routes)
    async with subject.BrowserBatchSession(options("https://site.test", concurrency=2)) as session:
        results = await session.fetch_many(
            ["https://site.test/a", "https://site.test/b", "https://site.test/c"]
        )
        assert [item.title for item in results] == ["A", "B", "C"]
        assert all(item.engine == "playwright" for item in results)
        context = session._context
    assert context.max_live <= 2, "并发不超过 tab 上限"
    assert context.max_live >= 2, "确实同时开了多个 tab"


@pytest.mark.asyncio
async def test_challenge_page_is_rejected_with_escalation_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = "<html><head><title>Just a moment...</title></head><body>/cdn-cgi/challenge-platform</body></html>"
    install_fake(
        monkeypatch,
        {"https://site.test/": (200, article("Home"), 0), "https://site.test/cf": (403, challenge, 0)},
    )
    async with subject.BrowserBatchSession(options("https://site.test")) as session:
        with pytest.raises(PageRejectedError) as captured:
            await session.fetch("https://site.test/cf")
    assert any(reason.startswith("http_status:403") for reason in captured.value.reasons)
    assert captured.value.result.block_reasons, "挑战特征带在结果里供调用方决定升档"


@pytest.mark.asyncio
async def test_warmup_failure_returns_session_to_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake(monkeypatch, {"https://site.test/": (403, article("Blocked"), 0)})
    async with subject.BrowserBatchSession(options("https://site.test")) as session:
        with pytest.raises(subject.WarmupError):
            await session.warmup()
        assert session.state is subject.BrowserSessionState.IDLE


@pytest.mark.asyncio
async def test_dom_expectations_are_checked_on_layer_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake(
        monkeypatch,
        {"https://site.test/": (200, article("Home"), 0), "https://site.test/a": (200, article("A"), 0)},
    )
    context = fake._context
    async with subject.BrowserBatchSession(options("https://site.test")) as session:
        with pytest.raises(PageRejectedError) as missing_selector:
            await session.fetch(
                SiteRequest("https://site.test/a", expected_selector="#missing")
            )
        assert "missing_expected_selector:#missing" in missing_selector.value.reasons

        with pytest.raises(PageRejectedError) as missing_wait:
            await session.fetch(SiteRequest("https://site.test/a", wait_selector="#later"))
        assert "missing_wait_selector:#later" in missing_wait.value.reasons

        context.selectors = {
            "https://site.test/a": {"#main", "#later"},
            "https://site.test/": {"#main"},
        }
        result = await session.fetch(
            SiteRequest("https://site.test/a", expected_selector="#main", wait_selector="#later")
        )
    assert "A" == result.title


@pytest.mark.asyncio
async def test_headful_challenge_wait_lets_a_human_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routes = {
        "https://site.test/": (200, article("Home"), 0),
        "https://site.test/cf": (200, article("CF 之后"), 2),
    }
    install_fake(monkeypatch, routes)
    monkeypatch.setattr(subject, "wait_for_manual_verification_async", _fake_wait)
    session = subject.BrowserBatchSession(
        options("https://site.test", headless=False, challenge_wait_ms=5_000)
    )
    async with session:
        result = await session.fetch("https://site.test/cf")
    assert "CF 之后" in result.html, "人工过完验证后保存真实页面"
    assert session.state is subject.BrowserSessionState.CLOSED


async def _fake_wait(read_html: Any, wait_ms: int, **_kwargs: Any) -> tuple[bool, float]:
    """Stand-in for the real poller: consume the challenge polls, then report clear."""

    from resilient_fetch import block_reasons

    for _ in range(5):
        html = await read_html()
        if not block_reasons(html):
            return True, 0.1
    return False, float(wait_ms) / 1000


def test_challenge_wait_requires_headful() -> None:
    with pytest.raises(ValueError):
        subject.BrowserSessionOptions(home_url="https://site.test/", challenge_wait_ms=5_000)


def test_cross_origin_and_validation_guards() -> None:
    with pytest.raises(ValueError):
        subject.BrowserSessionOptions(home_url="https://site.test/", concurrency=9, max_pages=4)
    with pytest.raises(ValueError):
        subject.BrowserSessionOptions(home_url="https://site.test/", timeout_ms=10, wall_timeout_ms=10)
    with pytest.raises(ValueError):
        subject.BrowserSessionOptions(home_url="ftp://site.test/")
    with pytest.raises(ValueError):
        subject.BrowserSessionOptions(home_url="https://site.test/", post_wait_ms=-1)


@pytest.mark.asyncio
async def test_lifecycle_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake(monkeypatch, {"https://site.test/": (200, article("Home"), 0)})
    session = subject.BrowserBatchSession(options("https://site.test"))
    with pytest.raises(subject.SiteSessionError):
        await session.fetch("https://site.test/")
    await session.start()
    with pytest.raises(subject.SiteSessionError):
        await session.start()
    with pytest.raises(ValueError):
        await session.fetch("https://other.test/x")
    await session.close()
    with pytest.raises(subject.SiteSessionError):
        await session.fetch("https://site.test/")


@pytest.mark.asyncio
async def test_missing_playwright_maps_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "resolve_playwright_api", lambda *_args: None)
    session = subject.BrowserBatchSession(options("https://site.test"))
    async with session:
        with pytest.raises(subject.EngineUnavailableError):
            await session.warmup()


@pytest.mark.asyncio
async def test_transient_navigation_error_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake(monkeypatch, {"https://site.test/": (200, article("Home"), 0)})
    calls = {"n": 0}
    original = subject.BrowserBatchSession._render_once

    async def flaky(self: Any, request: SiteRequest) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise subject.FetchError(f"页面渲染失败 {request.url}: 瞬时错误")
        return await original(self, request)

    monkeypatch.setattr(subject.BrowserBatchSession, "_render_once", flaky)
    async with subject.BrowserBatchSession(
        options("https://site.test", retries=2, retry_delay=0)
    ) as session:
        result = await session.fetch("https://site.test/")
    assert result.status == 200
    assert calls["n"] == 3, "第二次失败后重试成功(预热 + 首次失败 + 重试)"


def test_screenshot_slug_is_filesystem_safe() -> None:
    slug = subject.request_slug("https://site.test/a/b?c=1#d")
    assert slug == "site.test_a_b"
    assert subject.request_slug("https://site.test/") == "site.test_index"


def test_browser_session_applies_identity_headers() -> None:
    session = subject.BrowserBatchSession(
        subject.BrowserSessionOptions(
            home_url="https://site.test/",
            user_agent="ProbeUA/1.0",
            referer="https://example.org/from",
        )
    )

    assert session._context_kwargs() == {"user_agent": "ProbeUA/1.0"}, "UA 走 context"

    with pytest.raises(ValueError, match="referer"):
        subject.BrowserSessionOptions(home_url="https://site.test/", referer="example.org/from")
    with pytest.raises(ValueError, match="user_agent"):
        subject.BrowserSessionOptions(home_url="https://site.test/", user_agent="bad\nua")
