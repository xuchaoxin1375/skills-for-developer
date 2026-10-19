"""Cover the layered engine set: layer 0 static, layer 1 playwright, and their gating."""

from __future__ import annotations

import gzip
import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import resilient_fetch as subject


def make_result(**overrides: Any) -> subject.FetchResult:
    values: dict[str, Any] = {
        "engine": "static",
        "url": "https://example.com",
        "final_url": "https://example.com/",
        "status": 200,
        "html": "<html><title>Example</title><body>expected</body></html>",
        "elapsed_sec": 0.1,
        "title": "Example",
        "block_reasons": [],
        "versions": {},
    }
    values.update(overrides)
    return subject.FetchResult(**values)


@contextmanager
def local_server(
    routes: dict[str, tuple[int, bytes, dict[str, str]]],
) -> Iterator[str]:
    """Serve fixed bodies from 127.0.0.1 so layer 0 tests never touch the network."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            status, body, headers = routes.get(self.path, (404, b"missing", {}))
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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


def static_config(url: str, **overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "url": url,
        "proxy": None,
        "timeout_ms": 10_000,
        "retries": 1,
        "retry_delay": 0.0,
        "locale": None,
    }
    config.update(overrides)
    return config


# ---- 层 0:static ----


def test_static_engine_fetches_without_any_third_party_package() -> None:
    body = b"<html><title>Local</title><body>hello</body></html>"
    routes = {"/": (200, body, {"Content-Type": "text/html; charset=utf-8"})}
    with local_server(routes) as base:
        result = subject.fetch_with_static(static_config(f"{base}/"))

    assert result.engine == "static"
    assert result.status == 200
    assert result.title == "Local"
    assert "hello" in result.html
    assert result.final_url == f"{base}/"


def test_static_engine_returns_error_body_for_content_validation() -> None:
    body = b"<html><title>Just a moment</title><body>blocked</body></html>"
    routes = {"/": (403, body, {"Content-Type": "text/html"})}
    with local_server(routes) as base:
        result = subject.fetch_with_static(static_config(f"{base}/"))

    reasons = subject.validation_reasons(result, 1, [])
    assert result.status == 403
    assert "http_status:403" in reasons
    assert subject.attempt_kind(reasons, None) == subject.KIND_BLOCKED


def test_static_engine_decodes_gzip_bodies() -> None:
    body = gzip.compress(b"<html><title>Gzip</title></html>")
    routes = {
        "/": (
            200,
            body,
            {"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip"},
        )
    }
    with local_server(routes) as base:
        result = subject.fetch_with_static(static_config(f"{base}/"))

    assert result.title == "Gzip"


def test_decode_static_body_honours_header_charset() -> None:
    payload = "<html><title>中文</title></html>".encode("gbk")
    assert "中文" in subject.decode_static_body(payload, "text/html; charset=GBK", None)


def test_decode_static_body_sniffs_meta_charset_without_header() -> None:
    payload = '<html><head><meta charset="gbk"></head><title>中文</title></html>'.encode("gbk")
    assert "中文" in subject.decode_static_body(payload, None, None)


def test_decode_static_body_falls_back_to_gb18030() -> None:
    payload = "<html><title>中文</title></html>".encode("gb18030")
    decoded = subject.decode_static_body(payload, "text/html", None)
    assert "中文" in decoded


def test_static_engine_requires_curl_cffi_for_socks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "curl_cffi_available", lambda: False)
    with pytest.raises(subject.EngineUnavailableError):
        subject.fetch_with_static(
            static_config("http://example.com/", proxy="socks5://127.0.0.1:1080")
        )


def test_static_proxy_map_is_empty_without_proxy() -> None:
    assert subject.static_proxy_map(None) == {}
    assert subject.static_proxy_map("http://127.0.0.1:7897") == {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897",
    }


def test_static_engine_uses_curl_cffi_when_impersonate_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    def fake_curl_cffi(config: dict[str, Any], started: float) -> subject.FetchResult:
        seen.append(config)
        return make_result(notes=[f"impersonate:{config['impersonate']}"])

    monkeypatch.setattr(subject, "curl_cffi_available", lambda: True)
    monkeypatch.setattr(subject, "fetch_with_static_curl_cffi", fake_curl_cffi)

    result = subject.fetch_with_static(
        static_config("http://example.com/", impersonate="chrome124")
    )

    assert seen and seen[0]["impersonate"] == "chrome124"
    assert result.notes == ["impersonate:chrome124"]


def test_static_engine_impersonate_without_curl_cffi_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "curl_cffi_available", lambda: False)
    with pytest.raises(subject.EngineUnavailableError, match="impersonate"):
        subject.fetch_with_static(
            static_config("http://example.com/", impersonate="chrome124")
        )


def test_static_curl_cffi_path_retries_transient_tls_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeResponse:
        status_code = 200
        url = "https://example.com/"
        text = "<html><title>伪装</title><body>ok</body></html>"

    def flaky(config: dict[str, Any], target: str) -> Any:
        calls.append(target)
        if len(calls) == 1:
            raise RuntimeError("TLS connect error: OPENSSL_internal:invalid library")
        return FakeResponse()

    monkeypatch.setattr(subject, "curl_cffi_available", lambda: True)
    monkeypatch.setattr(subject, "curl_cffi_get", flaky)

    result = subject.fetch_with_static_curl_cffi(
        static_config("https://example.com/", impersonate="chrome124", retries=2, retry_delay=0.0),
        0.0,
    )

    assert calls == ["chrome124", "chrome124"], "经代理的瞬时握手失败按 retries 重试"
    assert result.status == 200
    assert result.notes == ["impersonate:chrome124"]


def test_static_curl_cffi_path_reports_last_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_fail(config: dict[str, Any], target: str) -> Any:
        raise RuntimeError("TLS connect error")

    monkeypatch.setattr(subject, "curl_cffi_available", lambda: True)
    monkeypatch.setattr(subject, "curl_cffi_get", always_fail)

    with pytest.raises(subject.FetchError, match="curl_cffi"):
        subject.fetch_with_static_curl_cffi(
            static_config(
                "https://example.com/", impersonate="chrome124", retries=2, retry_delay=0.0
            ),
            0.0,
        )


def test_impersonate_validation_rejects_missing_dependency_and_unknown_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "curl_cffi_available", lambda: False)
    with pytest.raises(ValueError, match="curl_cffi"):
        subject.validate_impersonate("chrome124")

    monkeypatch.setattr(subject, "curl_cffi_available", lambda: True)
    monkeypatch.setattr(
        subject, "curl_cffi_impersonate_targets", lambda: ("chrome124", "chrome136")
    )
    subject.validate_impersonate("chrome136")
    subject.validate_impersonate(None)
    with pytest.raises(ValueError, match="chrome124"):
        subject.validate_impersonate("chrome999")


def test_default_impersonate_target_prefers_documented_then_newest_chrome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "curl_cffi_impersonate_targets", lambda: ())
    assert subject.default_impersonate_target() == subject.DEFAULT_IMPERSONATE_TARGET

    monkeypatch.setattr(
        subject, "curl_cffi_impersonate_targets", lambda: ("chrome99", "chrome136", "safari184")
    )
    assert subject.default_impersonate_target() == "chrome136"

    monkeypatch.setattr(
        subject,
        "curl_cffi_impersonate_targets",
        lambda: ("chrome99", "chrome124", "chrome136"),
    )
    assert subject.default_impersonate_target() == subject.DEFAULT_IMPERSONATE_TARGET


def test_impersonate_is_carried_into_worker_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "curl_cffi_available", lambda: True)
    monkeypatch.setattr(subject, "curl_cffi_impersonate_targets", lambda: ("chrome124",))

    config = subject.build_worker_config(
        subject.FetchOptions(url="https://example.com", impersonate="chrome124"), None
    )
    assert config["impersonate"] == "chrome124"
    subject.validate_options(
        subject.FetchOptions(url="https://example.com", impersonate="chrome124")
    )


def test_impersonate_warns_on_browser_layers(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(subject, "curl_cffi_available", lambda: True)
    monkeypatch.setattr(subject, "curl_cffi_impersonate_targets", lambda: ("chrome124",))

    with caplog.at_level(logging.WARNING):
        subject.validate_options(
            subject.FetchOptions(
                url="https://example.com", engine="playwright", impersonate="chrome124"
            )
        )

    assert "--impersonate" in caplog.text and "层 0" in caplog.text


# ---- 层 1:playwright ----


def test_playwright_launch_kwargs_maps_proxy_credentials() -> None:
    kwargs = subject.playwright_launch_kwargs(
        {"headful": False, "proxy": "http://user:p%40ss@127.0.0.1:7897"}
    )
    assert kwargs["headless"] is True
    assert kwargs["proxy"] == {
        "server": "http://127.0.0.1:7897",
        "username": "user",
        "password": "p@ss",
    }


def test_playwright_launch_kwargs_rejects_socks_credentials() -> None:
    with pytest.raises(subject.FetchError):
        subject.playwright_launch_kwargs({"headful": False, "proxy": "socks5://u:p@127.0.0.1:1080"})


def test_playwright_launch_kwargs_supports_real_chrome_and_explicit_binary() -> None:
    headful = subject.playwright_launch_kwargs(
        {"headful": True, "proxy": None, "real_chrome": True}
    )
    assert headful["headless"] is False
    assert headful["channel"] == "chrome"
    explicit = subject.playwright_launch_kwargs(
        {"headful": True, "proxy": None, "executable_path": "C:/chrome/chrome.exe"}
    )
    assert explicit["executable_path"] == "C:/chrome/chrome.exe"


def test_fetch_with_playwright_reports_missing_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "playwright_api_name", lambda: None)
    with pytest.raises(subject.EngineUnavailableError):
        subject.fetch_with_playwright(
            {"url": "https://example.com", "timeout_ms": 5_000, "headful": False, "proxy": None}
        )


# ---- 人工验证等待: 有头窗口轮询与指引 ----


class FakePlaywrightPage:
    """Fake sync page that clears its challenge after N polls."""

    def __init__(self, *, clear_after: int = 0, url: str = "https://example.com/app") -> None:
        self.polls = 0
        self.clear_after = clear_after
        self.url = url
        self.selector_waited = False
        self.screenshot_paths: list[str] = []
        self.waits: list[int] = []
        self.goto_kwargs: dict[str, Any] = {}
        self.load_states: list[str] = []

    def goto(self, _url: str, **kwargs: Any) -> Any:
        class Response:
            status = 200

        self.goto_kwargs = kwargs
        return Response()

    def wait_for_load_state(self, state: str, **_kwargs: Any) -> None:
        self.load_states.append(state)
        return None

    def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)

    def wait_for_selector(self, *_args: Any, **_kwargs: Any) -> None:
        self.selector_waited = True

    def screenshot(self, *, path: str, **_kwargs: Any) -> None:
        self.screenshot_paths.append(path)

    def content(self) -> str:
        self.polls += 1
        if self.polls <= self.clear_after:
            return "<html><head><title>Just a moment...</title></head><body>/cdn-cgi/challenge-platform</body></html>"
        return "<html><head><title>正文</title></head><body>真实内容</body></html>"


def fake_playwright_factory(page: FakePlaywrightPage) -> Any:
    class Context:
        def new_page(self) -> FakePlaywrightPage:
            return page

        def close(self) -> None:
            return None

    class Browser:
        def new_context(self, **_kwargs: Any) -> Context:
            return Context()

        def close(self) -> None:
            return None

    class Chromium:
        def launch(self, **_kwargs: Any) -> Browser:
            return Browser()

    class Manager:
        def __enter__(self) -> Manager:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        chromium = Chromium()

    return lambda: Manager()


def test_wait_for_manual_verification_clears_and_reports_elapsed() -> None:
    polls = {"n": 0}

    def read_html() -> str:
        polls["n"] += 1
        if polls["n"] < 3:
            return "<html><head><title>Just a moment...</title></head><body>/cdn-cgi/challenge-platform</body></html>"
        return "<html><body>ok</body></html>"

    cleared, elapsed = subject.wait_for_manual_verification(
        read_html, 10_000, label="https://example.com", headful=True
    )

    assert cleared is True
    assert elapsed >= 0
    assert polls["n"] == 3


def test_wait_for_manual_verification_gives_up_at_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "CHALLENGE_POLL_INTERVAL_SEC", 0.0)

    def read_html() -> str:
        return "<html><head><title>Just a moment...</title></head><body>/cdn-cgi/challenge-platform</body></html>"

    cleared, _elapsed = subject.wait_for_manual_verification(read_html, 0, headful=True)

    assert cleared is False, "预算为 0 时不等待，按当前页面继续"


def test_wait_for_manual_verification_skips_wait_without_budget() -> None:
    calls = {"n": 0}

    def read_html() -> str:
        calls["n"] += 1
        return "<html><head><title>Just a moment...</title></head><body>/cdn-cgi/challenge-platform</body></html>"

    assert subject.wait_for_manual_verification(read_html, 0)[0] is False
    assert calls["n"] == 1, "没有预算时只探一次，不做轮询"


@pytest.mark.asyncio
async def test_async_manual_verification_polls_until_clear() -> None:
    polls = {"n": 0}

    async def read_html() -> str:
        polls["n"] += 1
        if polls["n"] < 2:
            return "<html><head><title>Just a moment...</title></head><body>/cdn-cgi/challenge-platform</body></html>"
        return "<html><body>ok</body></html>"

    cleared, _elapsed = await subject.wait_for_manual_verification_async(
        read_html, 5_000, label="session", headful=True
    )

    assert cleared is True
    assert polls["n"] == 2


def test_manual_verification_hint_mentions_window_and_budget(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        subject.log_manual_verification_hint(300_000, headful=True)
    assert "请在窗口内完成" in caplog.text
    assert "300 秒" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO):
        subject.log_manual_verification_hint(0, headful=True)
    assert "--challenge-wait-ms" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO):
        subject.log_manual_verification_hint(300_000, headful=False)
    assert caplog.text == "", "无头模式不打印人工指引"


def test_playwright_headful_waits_for_manual_verification_before_selector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = FakePlaywrightPage(clear_after=2)
    monkeypatch.setattr(subject, "playwright_api_name", lambda: "playwright")
    monkeypatch.setattr(subject, "load_playwright_factory", lambda: fake_playwright_factory(page))
    monkeypatch.setattr(subject, "CHALLENGE_POLL_INTERVAL_SEC", 0.0)
    screenshot = tmp_path / "shot.png"

    html, status, _final = subject.render_with_playwright(
        {
            "url": "https://example.com/app",
            "timeout_ms": 5_000,
            "headful": True,
            "proxy": None,
            "challenge_wait_ms": 5_000,
            "wait_selector": "#main",
            "screenshot": str(screenshot),
        }
    )

    assert "真实内容" in html, "保存的是人工验证之后的页面"
    assert status == 200
    assert page.polls >= 3, "轮询到挑战标记消失"
    assert page.selector_waited is True, "验证通过后仍执行 wait_selector"
    assert page.screenshot_paths == [str(screenshot)]
    assert subject.CHALLENGE_SETTLE_MS in page.waits, "验证通过后给页面稳定时间"


def test_playwright_headless_does_not_wait_for_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePlaywrightPage(clear_after=99)
    monkeypatch.setattr(subject, "playwright_api_name", lambda: "playwright")
    monkeypatch.setattr(subject, "load_playwright_factory", lambda: fake_playwright_factory(page))

    html, _status, _final = subject.render_with_playwright(
        {
            "url": "https://example.com/app",
            "timeout_ms": 5_000,
            "headful": False,
            "proxy": None,
            "challenge_wait_ms": 5_000,
        }
    )

    assert "Just a moment" in html, "无头模式不等人，直接按当前页面返回"
    assert page.polls == 1


def test_playwright_wait_until_controls_when_page_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePlaywrightPage()
    monkeypatch.setattr(subject, "playwright_api_name", lambda: "playwright")
    monkeypatch.setattr(subject, "load_playwright_factory", lambda: fake_playwright_factory(page))

    subject.render_with_playwright(
        {
            "url": "https://example.com/app",
            "timeout_ms": 5_000,
            "headful": False,
            "proxy": None,
            "wait_until": "domcontentloaded",
            "post_wait_ms": 700,
        }
    )

    assert page.goto_kwargs["wait_until"] == "domcontentloaded"
    assert page.load_states == [], "未请求 networkidle 时不应额外等待"
    assert page.waits == [700]

    monkeypatch.setattr(subject, "load_playwright_factory", lambda: fake_playwright_factory(page))
    subject.render_with_playwright(
        {
            "url": "https://example.com/app",
            "timeout_ms": 5_000,
            "headful": False,
            "proxy": None,
            "wait_until": "networkidle",
            "network_idle": True,
        }
    )
    assert page.goto_kwargs["wait_until"] == "networkidle"
    assert "networkidle" not in page.load_states, "goto 已等 networkidle，不再重复等待"


def test_playwright_defaults_to_load_until_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePlaywrightPage()
    monkeypatch.setattr(subject, "playwright_api_name", lambda: "playwright")
    monkeypatch.setattr(subject, "load_playwright_factory", lambda: fake_playwright_factory(page))

    subject.render_with_playwright(
        {"url": "https://example.com/app", "timeout_ms": 5_000, "headful": False, "proxy": None}
    )

    assert page.goto_kwargs["wait_until"] == "load"


def test_scrapling_wait_kwargs_maps_each_wait_condition() -> None:
    assert subject.scrapling_wait_kwargs("networkidle") == {"network_idle": True, "load_dom": True}
    assert subject.scrapling_wait_kwargs("load") == {"network_idle": False, "load_dom": True}
    for condition in ("commit", "domcontentloaded"):
        assert subject.scrapling_wait_kwargs(condition) == {
            "network_idle": False,
            "load_dom": False,
        }


def test_scrapling_kwargs_keeps_legacy_network_idle_flag() -> None:
    config = {
        "url": "https://example.com/",
        "timeout_ms": 60_000,
        "retries": 1,
        "retry_delay": 2.0,
        "headful": False,
        "proxy": None,
        "hide_canvas": False,
        "real_chrome": False,
        "network_idle": True,
        "wait_until": "domcontentloaded",
    }
    assert subject.scrapling_kwargs(config)["network_idle"] is True, "--network-idle 仍是显式开关"


def test_wait_until_is_validated_and_carried_into_worker_config() -> None:
    with pytest.raises(ValueError, match="wait_until"):
        subject.validate_options(
            subject.FetchOptions(url="https://example.com", wait_until="bogus")
        )

    config = subject.build_worker_config(
        subject.FetchOptions(url="https://example.com", wait_until="networkidle"), None
    )
    assert config["wait_until"] == "networkidle"


def test_static_engine_warns_about_browser_only_wait_options(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        subject.validate_options(
            subject.FetchOptions(
                url="https://example.com", engine="static", wait_until="domcontentloaded"
            )
        )
    assert "--wait-until" in caplog.text


def test_fetch_with_playwright_maps_missing_browser_to_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_config: dict[str, Any]) -> tuple[str, int | None, str]:
        raise RuntimeError("Executable doesn't exist at /ms-playwright/chromium-1243/chrome.exe")

    monkeypatch.setattr(subject, "render_with_playwright", boom)
    with pytest.raises(subject.EngineUnavailableError):
        subject.fetch_with_playwright(
            {"url": "https://example.com", "timeout_ms": 5_000, "headful": False, "proxy": None}
        )


def test_fetch_with_playwright_keeps_other_errors_as_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_config: dict[str, Any]) -> tuple[str, int | None, str]:
        raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")

    monkeypatch.setattr(subject, "render_with_playwright", boom)
    with pytest.raises(subject.FetchError) as captured:
        subject.fetch_with_playwright(
            {"url": "https://example.com", "timeout_ms": 5_000, "headful": False, "proxy": None}
        )
    assert not isinstance(captured.value, subject.EngineUnavailableError)


# ---- 能力分层与参数校验 ----


def test_engine_capabilities_marks_solver_only_for_layers_two_and_three() -> None:
    assert subject.engine_capabilities("static") == frozenset({subject.CAP_HTTP})
    assert subject.CAP_SOLVE not in subject.engine_capabilities("playwright")
    assert subject.CAP_SOLVE in subject.engine_capabilities("scrapling")


def test_validate_options_allows_small_timeout_below_the_solver_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject, "engine_availability", lambda name: subject.EngineAvailability(name == "static", "s")
    )
    monkeypatch.setattr(subject, "available_engines", lambda: ("static",))
    subject.validate_options(subject.FetchOptions(url="https://example.com", timeout_ms=3_000))


def test_validate_options_keeps_solver_timeout_floor() -> None:
    with pytest.raises(ValueError):
        subject.validate_options(
            subject.FetchOptions(url="https://example.com", engine="scrapling", timeout_ms=50_000)
        )


def test_validate_options_rejects_headful_static() -> None:
    with pytest.raises(ValueError):
        subject.validate_options(
            subject.FetchOptions(url="https://example.com", engine="static", headful=True)
        )


def test_validate_options_rejects_unknown_engine() -> None:
    with pytest.raises(ValueError):
        subject.validate_options(subject.FetchOptions(url="https://example.com", engine="nope"))


def test_probes_report_missing_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "playwright_api_name", lambda: None)
    unavailable = subject.probe_playwright()
    assert unavailable.ok is False
    assert "playwright" in unavailable.missing
    assert "缺失" in unavailable.reason()


# ---- 调度与 worker 协议 ----


def test_run_engine_dispatches_layer_zero_and_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_static(_config: dict[str, Any]) -> subject.FetchResult:
        calls.append("static")
        return make_result()

    def fake_playwright(_config: dict[str, Any]) -> subject.FetchResult:
        calls.append("playwright")
        return make_result(engine="playwright")

    monkeypatch.setattr(subject, "fetch_with_static", fake_static)
    monkeypatch.setattr(subject, "fetch_with_playwright", fake_playwright)

    assert subject.run_engine("static", {"url": "https://example.com"}, tmp_path).engine == "static"
    assert subject.run_engine("playwright", {"url": "https://example.com"}, tmp_path).engine == (
        "playwright"
    )
    assert calls == ["static", "playwright"]


def test_run_engine_rejects_unknown_engine(tmp_path: Path) -> None:
    with pytest.raises(subject.FetchError):
        subject.run_engine("nope", {"url": "https://example.com"}, tmp_path)


def test_worker_main_serializes_static_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"url": "https://example.com"}), encoding="utf-8")
    monkeypatch.setattr(subject, "fetch_with_static", lambda _config: make_result())

    assert subject.worker_main("static", config_path, tmp_path) == 0
    assert (tmp_path / "page.html").exists()


def test_worker_main_marks_missing_engine_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"url": "https://example.com"}), encoding="utf-8")

    def fail(_config: dict[str, Any]) -> subject.FetchResult:
        raise subject.EngineUnavailableError("未安装 playwright/patchright")

    monkeypatch.setattr(subject, "fetch_with_playwright", fail)

    assert subject.worker_main("playwright", config_path, tmp_path) == 1
    error = json.loads((tmp_path / "error.json").read_text(encoding="utf-8"))
    assert error["error"].startswith("EngineUnavailableError")
    assert subject.attempt_kind((), error["error"]) == subject.KIND_UNAVAILABLE


def test_fetch_page_classifies_stale_probe_failure_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject, "engine_availability", lambda name: subject.EngineAvailability(True, "stub")
    )
    monkeypatch.setattr(subject, "available_engines", lambda: ("scrapling",))
    monkeypatch.setattr(
        subject,
        "run_isolated_engine",
        lambda *args: (_ for _ in ()).throw(
            subject.FetchError("scrapling: EngineUnavailableError: 未安装 scrapling")
        ),
    )
    with pytest.raises(subject.FetchFailed) as captured:
        subject.fetch_page(
            subject.FetchOptions(url="https://example.com", engine="scrapling", timeout_ms=60_000)
        )
    assert captured.value.attempts[0].kind == subject.KIND_UNAVAILABLE
    assert captured.value.unavailable_engines == ("scrapling",)
