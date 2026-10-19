"""Cover the layer-0 static batch session: warmup, concurrency, validation, lifecycle."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
import static_session as subject


@contextmanager
def local_server(
    routes: dict[str, tuple[int, bytes, dict[str, str]]],
    *,
    stats: dict[str, int] | None = None,
    delay: float = 0.0,
) -> Iterator[str]:
    """Serve fixed bodies from 127.0.0.1 and optionally track concurrency."""

    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            status, body, headers = routes.get(self.path, (404, b"missing", {}))
            if stats is not None:
                with lock:
                    stats["active"] = stats.get("active", 0) + 1
                    stats["max_active"] = max(stats.get("max_active", 0), stats["active"])
                    stats["total"] = stats.get("total", 0) + 1
                time.sleep(delay)
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            if stats is not None:
                with lock:
                    stats["active"] -= 1

        def log_message(self, format: str, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def page(title: str, extra: str = "") -> bytes:
    return (
        f"<!doctype html><html><head><title>{title}</title></head>"
        f"<body><article><p>{extra or '正文内容足够长可以被识别为业务主体。' * 5}</p></article></body></html>"
    ).encode()


def options(base: str, **overrides: Any) -> subject.StaticSessionOptions:
    values: dict[str, Any] = {
        "home_url": f"{base}/",
        "max_pages": 8,
        "concurrency": 2,
        "timeout_ms": 5_000,
        "wall_timeout_ms": 10_000,
        "min_bytes": 1,
    }
    values.update(overrides)
    return subject.StaticSessionOptions(**values)


@pytest.mark.asyncio
async def test_fetch_many_warms_once_and_limits_concurrency() -> None:
    stats: dict[str, int] = {}
    routes = {
        "/": (200, page("Home"), {"Content-Type": "text/html; charset=utf-8"}),
        "/a": (200, page("A"), {"Content-Type": "text/html; charset=utf-8"}),
        "/b": (200, page("B"), {"Content-Type": "text/html; charset=utf-8"}),
        "/c": (200, page("C"), {"Content-Type": "text/html; charset=utf-8"}),
    }
    with local_server(routes, stats=stats, delay=0.15) as base:
        async with subject.StaticBatchSession(options(base)) as session:
            results = await session.fetch_many([f"{base}/a", f"{base}/b", f"{base}/c"])
            assert [item.title for item in results] == ["A", "B", "C"]
            assert session.state is subject.StaticSessionState.READY

    assert stats["total"] == 4, "首页只预热一次，不随页数重复请求"
    assert stats["max_active"] <= 2, "并发不超过 concurrency"
    assert stats["max_active"] >= 2, "确实并发执行"


@pytest.mark.asyncio
async def test_expected_text_failure_raises_structured_error() -> None:
    routes = {
        "/": (200, page("Home"), {"Content-Type": "text/html"}),
        "/a": (200, page("A"), {"Content-Type": "text/html"}),
    }
    with local_server(routes) as base:
        async with subject.StaticBatchSession(options(base)) as session:
            with pytest.raises(subject.PageRejectedError) as captured:
                await session.fetch(subject.SiteRequest(f"{base}/a", expected_texts=("不存在",)))
    assert "missing_expected_text:不存在" in captured.value.reasons


@pytest.mark.asyncio
async def test_challenge_page_is_reported_not_solved() -> None:
    challenge = b"<html><head><title>Just a moment...</title></head><body>cf-error-details</body></html>"
    routes = {
        "/": (200, page("Home"), {"Content-Type": "text/html"}),
        "/blocked": (403, challenge, {"Content-Type": "text/html"}),
    }
    with local_server(routes) as base:
        async with subject.StaticBatchSession(options(base)) as session:
            with pytest.raises(subject.PageRejectedError) as captured:
                await session.fetch(f"{base}/blocked")
    assert any(reason.startswith("http_status:403") for reason in captured.value.reasons)
    assert captured.value.result.block_reasons, "挑战特征要带在结果里，供调用方决定升档"


@pytest.mark.asyncio
async def test_warmup_failure_returns_session_to_idle() -> None:
    routes = {"/": (403, b"<html><body>blocked</body></html>", {"Content-Type": "text/html"})}
    with local_server(routes) as base:
        async with subject.StaticBatchSession(options(base)) as session:
            with pytest.raises(subject.WarmupError):
                await session.warmup()
            assert session.state is subject.StaticSessionState.IDLE


@pytest.mark.asyncio
async def test_cross_origin_and_unsupported_checks() -> None:
    routes = {"/": (200, page("Home"), {"Content-Type": "text/html"})}
    with local_server(routes) as base:
        async with subject.StaticBatchSession(
            options(base, expected_home_texts=("正文",))
        ) as session:
            with pytest.raises(ValueError):
                await session.fetch("https://example.com/other")
            with pytest.raises(ValueError) as selector_error:
                await session.fetch(subject.SiteRequest(f"{base}/", expected_selector="#main"))
    assert "expected_selector" in str(selector_error.value)


@pytest.mark.asyncio
async def test_lifecycle_guards() -> None:
    routes = {"/": (200, page("Home"), {"Content-Type": "text/html"})}
    with local_server(routes) as base:
        session = subject.StaticBatchSession(options(base))
        with pytest.raises(subject.SiteSessionError):
            await session.fetch(f"{base}/")
        await session.start()
        with pytest.raises(subject.SiteSessionError):
            await session.start()
        await session.close()
        with pytest.raises(subject.SiteSessionError):
            await session.fetch(f"{base}/")


@pytest.mark.asyncio
async def test_network_error_names_the_page_and_retry_default_is_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_on_page(config: dict[str, Any]) -> Any:
        if config["url"].endswith("/flaky"):
            raise subject.FetchError(f"static 抓取失败(2 次尝试): {config['url']} <urlopen error EOF>")
        return subject.FetchResult(
            engine="static",
            url=config["url"],
            final_url=config["url"],
            status=200,
            html="<html><title>OK</title><body>正文内容足够长可以被识别为业务主体。</body></html>",
            elapsed_sec=0.0,
        )

    assert subject.StaticSessionOptions(home_url="http://127.0.0.1:1/").retries == 2, (
        "静态批量默认重试一次，抵消并发握手的瞬时错误"
    )
    monkeypatch.setattr(subject, "fetch_with_static", fail_on_page)
    # 单页内部重试由 resilient_fetch 负责；这里只覆盖会话层把 URL 带进错误消息。
    options = subject.StaticSessionOptions(
        home_url="http://127.0.0.1:1/",
        retries=2,
        retry_delay=0.0,
        min_bytes=1,
        timeout_ms=2_000,
        wall_timeout_ms=5_000,
    )
    async with subject.StaticBatchSession(options) as session:
        with pytest.raises(subject.FetchError) as captured:
            await session.fetch("http://127.0.0.1:1/flaky")
    assert "http://127.0.0.1:1/flaky" in str(captured.value)


@pytest.mark.asyncio
async def test_wall_timeout_is_enforced_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_fetch(config: dict[str, Any]) -> Any:
        if config["url"].endswith("/slow"):
            time.sleep(3)
        return subject.FetchResult(
            engine="static",
            url=config["url"],
            final_url=config["url"],
            status=200,
            html="<html><title>OK</title><body>正文内容足够长可以被识别为业务主体。</body></html>",
            elapsed_sec=0.0,
        )

    monkeypatch.setattr(subject, "fetch_with_static", slow_fetch)
    session_options = subject.StaticSessionOptions(
        home_url="http://127.0.0.1:1/",
        timeout_ms=2_000,
        wall_timeout_ms=2_000,
        min_bytes=1,
    )
    async with subject.StaticBatchSession(session_options) as session:
        with pytest.raises(subject.PageTimeoutError):
            await session.fetch("http://127.0.0.1:1/slow")


@pytest.mark.asyncio
async def test_proxy_resolution_prefers_explicit_and_can_forbid_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "wait_for_proxy", lambda proxy, *args, **kwargs: True)
    monkeypatch.setattr(subject, "discover_local_proxy", lambda candidates=None: None)

    explicit = subject.StaticBatchSession(
        subject.StaticSessionOptions(home_url="http://127.0.0.1:1/", proxy="http://127.0.0.1:7897")
    )
    await explicit.start()
    assert explicit.effective_proxy == "http://127.0.0.1:7897"

    discovered_missing = subject.StaticBatchSession(
        subject.StaticSessionOptions(home_url="http://127.0.0.1:1/", discover_proxy=True)
    )
    with pytest.raises(subject.ProxyUnavailableError):
        await discovered_missing.start()

    allowed_direct = subject.StaticBatchSession(
        subject.StaticSessionOptions(home_url="http://127.0.0.1:1/", discover_proxy=True, allow_direct=True)
    )
    await allowed_direct.start()
    assert allowed_direct.effective_proxy is None


@pytest.mark.asyncio
async def test_fetch_many_cancels_remaining_pages_on_failure() -> None:
    routes = {
        "/": (200, page("Home"), {"Content-Type": "text/html"}),
        "/a": (200, page("A"), {"Content-Type": "text/html"}),
        "/b": (500, b"<html><body>boom</body></html>", {"Content-Type": "text/html"}),
    }
    with local_server(routes) as base:
        async with subject.StaticBatchSession(options(base)) as session:
            with pytest.raises(subject.PageRejectedError):
                await session.fetch_many([f"{base}/a", f"{base}/b"])
            pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
            assert not [task for task in pending if not task.done()]


def test_options_validate_impersonate_target(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str | None] = []
    monkeypatch.setattr(subject, "validate_impersonate", lambda target: calls.append(target))

    subject.StaticSessionOptions(home_url="http://127.0.0.1:1/", impersonate="chrome124")

    assert calls == ["chrome124"], "批量静态会话复用层 0 的 impersonate 校验"


def test_fetch_blocking_passes_impersonate_to_static_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    def fake_fetch(config: dict[str, Any]) -> Any:
        seen.append(config)
        return subject.FetchResult(
            engine="static",
            url=config["url"],
            final_url=config["url"],
            status=200,
            html="<html><title>OK</title><body>正文内容足够长可以被识别为业务主体。</body></html>",
            elapsed_sec=0.0,
        )

    monkeypatch.setattr(subject, "fetch_with_static", fake_fetch)
    session = subject.StaticBatchSession(
        subject.StaticSessionOptions(home_url="http://127.0.0.1:1/", impersonate="chrome124")
    )

    session._fetch_blocking(subject.SiteRequest("http://127.0.0.1:1/page"))

    assert seen and seen[0]["impersonate"] == "chrome124"
