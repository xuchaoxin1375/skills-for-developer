"""Cover the late-attach engine: browser discovery, readiness, and resource reclaim."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import chrome_late as subject
import pytest
import resilient_fetch as engine_subject


def test_find_system_browser_prefers_explicit_existing_file(tmp_path: Path) -> None:
    binary = tmp_path / "chrome.exe"
    binary.write_bytes(b"stub")
    assert subject.find_system_browser(str(binary)) == str(binary)
    assert subject.find_system_browser(str(tmp_path / "missing.exe")) is None


def test_build_launch_args_carries_port_profile_url_and_proxy() -> None:
    args = subject.build_launch_args(
        executable="C:/chrome.exe",
        port=9333,
        user_data_dir="C:/tmp/profile",
        url="https://example.com/p",
        proxy="socks5://127.0.0.1:10808",
    )
    assert "--remote-debugging-port=9333" in args
    assert "--user-data-dir=C:/tmp/profile" in args
    assert "--proxy-server=socks5://127.0.0.1:10808" in args
    assert args[-1] == "https://example.com/p"


def test_proxy_server_value_rejects_credentials_and_bare_host() -> None:
    assert subject.proxy_server_value(None) is None
    assert subject.proxy_server_value("http://127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert subject.proxy_server_value("socks5://127.0.0.1:10808") == "socks5://127.0.0.1:10808"
    with pytest.raises(subject.ChromeLateError):
        subject.proxy_server_value("http://user:pass@127.0.0.1:7890")
    with pytest.raises(subject.ChromeLateError):
        subject.proxy_server_value("127.0.0.1:7890")


def test_looks_like_url_text_tells_bare_url_from_page_title() -> None:
    assert subject.looks_like_url_text("") is True
    assert subject.looks_like_url_text("https://example.com/x") is True
    assert subject.looks_like_url_text("example.com/Bedding-Bath/410-Thread") is True
    assert subject.looks_like_url_text("Pointehaven 410 Thread Count Set - Bed Bath & Beyond") is False


def test_pick_page_target_prefers_the_requested_url() -> None:
    targets = [
        {"type": "page", "url": "https://other.example/", "title": "Other"},
        {"type": "page", "url": "https://example.com/p", "title": "Target"},
        {"type": "background_page", "url": "https://example.com/p", "title": "Bg"},
    ]
    picked = subject.pick_page_target(targets, "https://example.com/p")
    assert picked is not None
    assert picked["title"] == "Target"
    assert subject.pick_page_target([{"type": "service_worker", "url": "x"}], "https://example.com/p") is None


def test_wait_for_page_ready_reports_ready_when_title_appears() -> None:
    payload = [
        {"type": "page", "url": "https://example.com/p", "title": "example.com/p"},
        {"type": "page", "url": "https://example.com/p", "title": "Real Page Title"},
    ]
    state = {"index": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps([payload[state["index"]]]).encode("utf-8")
            state["index"] = min(state["index"] + 1, len(payload) - 1)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        signal = subject.wait_for_page_ready(
            port, target_url="https://example.com/p", min_settle_ms=0, max_wait_ms=5000
        )
    finally:
        server.shutdown()
        server.server_close()
    assert signal.ready is True
    assert signal.title == "Real Page Title"


def test_site_error_shell_is_detected_as_blocked() -> None:
    html = (
        "<html><head><title>Bed Bath & Beyond | The Best Deals Online</title></head>"
        "<body><div>There was an error processing your request.</div></body></html>"
    )
    assert "site_error_shell" in engine_subject.block_reasons(html)


def test_failure_message_points_at_the_late_attach_route() -> None:
    attempt = engine_subject.FetchAttempt(
        engine="playwright",
        ok=False,
        elapsed_sec=1.0,
        reasons=("site_error_shell",),
        kind=engine_subject.KIND_BLOCKED,
    )
    failure = engine_subject.FetchFailed("https://example.com/", (attempt,))
    assert "chrome-late" in failure.describe()


def test_bulk_readiness_waits_for_every_target() -> None:
    payload = [
        {"type": "page", "url": "https://example.com/a", "title": "Page A"},
        {"type": "page", "url": "https://example.com/b", "title": "example.com/b"},
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        signals = subject.wait_for_pages_ready(
            port,
            target_urls=["https://example.com/a", "https://example.com/b"],
            min_settle_ms=0,
            max_wait_ms=1500,
        )
    finally:
        server.shutdown()
        server.server_close()
    assert signals["https://example.com/a"].ready is True
    assert signals["https://example.com/b"].ready is False, "标题仍是 URL 时不算就绪"


def test_batch_helper_flags_block_pages() -> None:
    import example_late_batch

    assert example_late_batch.looks_blocked("Access Denied", "<html></html>") is True
    assert example_late_batch.looks_blocked("Access Denied", "x") is True
    assert example_late_batch.looks_blocked("正常标题", "<html>正文</html>") is False
    assert example_late_batch.slugify("Bed Bath & Beyond | 12269546", "page") == (
        "Bed-Bath-Beyond-12269546"
    )


def test_unhydrated_shell_is_not_accepted_as_rendered() -> None:
    shell = f'<html><body data-filler="{"x" * 8000}"><div id="app"></div></body></html>'
    assert subject.looks_like_app_shell(shell) is True
    hydrated = f'<html><body data-filler="{"x" * 8000}"><p>{"正文内容" * 100}</p></body></html>'
    assert subject.looks_like_app_shell(hydrated) is False


def test_site_error_state_is_told_apart_from_content() -> None:
    error_text = "Something went wrong. Something isn't right and an error has occurred."
    assert subject.looks_like_render_error(error_text) is True
    assert subject.looks_like_render_error("Unable to connect to the Internet") is True
    # 正文长、只是提到错误机制的文章不算错误态
    assert subject.looks_like_render_error("教程正文。" * 300 + "unable to connect") is False
    assert subject.looks_like_soft_error(error_text) is True
    # 通用说法不单独成立: 前端 bundle 里也常见
    assert subject.looks_like_soft_error("Something went wrong") is False


def test_soft_error_page_is_flagged_but_a_long_article_is_not() -> None:
    error_page = (
        "<html><body><h1>La Bonita Supermarkets</h1>"
        "<p>Unable to connect to the Internet</p></body></html>"
    )
    assert "site_error_shell" in engine_subject.block_reasons(error_page)
    article = (
        "<html><body><article><p>" + ("排障教程正文。" * 500) +
        "unable to connect to the internet</p></article></body></html>"
    )
    assert "site_error_shell" not in engine_subject.block_reasons(article)


def test_product_page_with_a_transient_error_banner_is_not_an_error() -> None:
    # 商品页上挂着一块瞬时错误横幅是常见情况, 不能因此把整页判成失败。
    product = (
        "<html><head><title>Catering Package 20-25 Person</title></head><body>"
        "<h1>Catering Package 20-25 Person</h1><p>Unable to connect to the Internet</p>"
        "<p>" + ("套餐包含米饭、豆类、酱料与玉米饼。" * 60) + "</p></body></html>"
    )
    assert "site_error_shell" not in engine_subject.block_reasons(product)
    assert subject.soft_error_phrase(product) is None


def test_render_wait_keeps_waiting_on_a_shell_until_the_budget() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.calls = 0

        def evaluate(self, script: str) -> dict:
            self.calls += 1
            return {
                "html": "<html><body>" + ("x" * 8000) + "<div id=app></div></body></html>",
                "title": "商店",
                "ready": "complete",
                "text": "Loading…",
                "textLen": 9,
            }

    page = FakePage()
    render = subject.wait_for_rendered_page(page, budget_ms=300, poll_ms=0.05)
    assert render.state == subject.STATE_SHELL, "稳定但没水合的空壳不能当成正文"
    assert page.calls >= 3, "空壳应被继续观察而不是立刻接受"


def test_render_wait_reports_the_site_error_state() -> None:
    class FakePage:
        def evaluate(self, script: str) -> dict:
            return {
                "html": "<html><body><p>Unable to connect to the Internet</p></body></html>",
                "title": "商店",
                "ready": "complete",
                "text": "Unable to connect to the Internet",
                "textLen": 38,
            }

    render = subject.wait_for_rendered_page(FakePage(), budget_ms=200, poll_ms=0.05)
    assert render.state == subject.STATE_ERROR


def test_sweep_stale_profiles_removes_only_old_leftovers(tmp_path: Path) -> None:
    old = tmp_path / f"{subject.PROFILE_DIR_PREFIX}old"
    old.mkdir()
    fresh = tmp_path / f"{subject.PROFILE_DIR_PREFIX}fresh"
    fresh.mkdir()
    stale_time = time.time() - subject.STALE_PROFILE_AGE_SEC - 60
    os.utime(old, (stale_time, stale_time))
    removed = subject.sweep_stale_profiles(root=tmp_path)
    assert str(old) in removed
    assert not old.exists()
    assert fresh.exists(), "仍在使用或较新的目录不能被清理"


def test_owned_browser_process_terminates_only_what_it_started() -> None:
    marker = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    owned = subject.OwnedBrowserProcess.launch(
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    try:
        assert owned.pid != marker.pid
        assert owned.process.poll() is None
    finally:
        owned.close()
    deadline = time.monotonic() + 10
    while owned.process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    assert owned.process.poll() is not None, "自有浏览器进程必须被回收"
    assert marker.poll() is None, "不得结束不属于本引擎的进程"
    marker.terminate()
    marker.wait(timeout=10)
    owned.close()  # 幂等: 重复回收不应报错


def test_akamai_challenge_page_is_detected_as_blocked() -> None:
    html = (
        "<html><head><title></title></head><body>"
        "<div>Powered and protected by</div><script>var chlgeId='';</script>"
        "</body></html>"
    )
    assert "akamai_challenge" in engine_subject.block_reasons(html)


def test_challenge_page_is_a_pending_state_not_a_refusal() -> None:
    interstitial = (
        '<html><head><title></title></head><body>'
        '<div id="sec-if-cpt-container"><div class="behavioral-content">'
        "<p>Powered and protected by</p></div></div></body></html>"
    )
    assert subject.classify_page_state("", interstitial) == subject.STATE_CHALLENGE
    assert subject.classify_page_state("Just a moment...", "<html>x</html>") == (
        subject.STATE_CHALLENGE
    )
    assert subject.classify_page_state("Access Denied", "<html>x</html>") == (
        subject.STATE_BLOCKED
    )
    assert subject.classify_page_state("商品标题", "<html>正文</html>") == (
        subject.STATE_CONTENT
    )


def test_browser_network_error_page_is_not_content() -> None:
    html = (
        "<html><head><title>example.com</title></head>"
        "<body>ERR_NAME_NOT_RESOLVED</body></html>"
    )
    assert "browser_error_page" in engine_subject.block_reasons(html)


def test_pick_rendered_page_matches_the_requested_tab() -> None:
    class Tab:
        def __init__(self, url: str) -> None:
            self.url = url

    wanted = Tab("https://example.com/product")
    other = Tab("https://other.example/")
    assert (
        subject.pick_rendered_page([other, wanted], "https://example.com/product") is wanted
    )
    # 重定向换了路径但同源, 仍然算命中
    redirected = Tab("https://example.com/new-path")
    assert (
        subject.pick_rendered_page([other, redirected], "https://example.com/product")
        is redirected
    )
    # 多个标签都对不上时宁可读不到, 也不要读错页面
    assert (
        subject.pick_rendered_page(
            [other, Tab("https://third.example/")], "https://example.com/p"
        )
        is None
    )
    assert subject.pick_rendered_page([other], "https://example.com/p") is other


def test_wait_for_page_ready_stops_at_a_refused_title() -> None:
    payload = [{"type": "page", "url": "https://example.com/p", "title": "Access Denied"}]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        signal = subject.wait_for_page_ready(
            port, target_url="https://example.com/p", min_settle_ms=0, max_wait_ms=30_000
        )
    finally:
        server.shutdown()
        server.server_close()
    assert signal.state == subject.STATE_BLOCKED
    assert signal.ready is False
    assert signal.waited_ms < 5_000, "标题已表明被拒时不该继续等满预算"


def test_wait_for_rendered_page_waits_until_the_dom_stops_growing() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.calls = 0

        def evaluate(self, script: str) -> dict:
            self.calls += 1
            if self.calls < 3:
                size = 1000 * self.calls
                ready = "loading"
            else:
                size = 3000
                ready = "complete"
            return {
                "html": "<html><body>" + ("x" * size) + "</body></html>",
                "title": "商品标题",
                "ready": ready,
            }

    page = FakePage()
    render = subject.wait_for_rendered_page(page, budget_ms=5000, poll_ms=0.01)
    assert render.state == subject.STATE_CONTENT
    assert render.ready_state == "complete"
    assert page.calls >= 3, "DOM 还在增长时不该读取"
    assert render.html.count("x") == 3000


def test_chrome_late_engine_is_registered_but_not_in_auto() -> None:
    spec = engine_subject.ENGINES["chrome-late"]
    assert spec.in_auto is False
    assert "chrome-late" in engine_subject.ENGINE_CHOICES
    assert engine_subject.CAP_LATE_CDP in spec.capabilities


def test_worker_config_carries_settle_window() -> None:
    options = engine_subject.FetchOptions(url="https://example.com/", settle_ms=9000)
    config = engine_subject.build_worker_config(options, None)
    assert config["settle_ms"] == 9000
