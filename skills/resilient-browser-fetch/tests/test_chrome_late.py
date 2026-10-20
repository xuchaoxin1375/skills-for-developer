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


def test_akamai_bot_page_is_detected_as_blocked() -> None:
    html = (
        "<html><head><title></title></head><body>"
        "<div>Powered and protected by</div><script>var chlgeId='';</script>"
        "</body></html>"
    )
    assert "akamai_bot_page" in engine_subject.block_reasons(html)


def test_chrome_late_engine_is_registered_but_not_in_auto() -> None:
    spec = engine_subject.ENGINES["chrome-late"]
    assert spec.in_auto is False
    assert "chrome-late" in engine_subject.ENGINE_CHOICES
    assert engine_subject.CAP_LATE_CDP in spec.capabilities


def test_worker_config_carries_settle_window() -> None:
    options = engine_subject.FetchOptions(url="https://example.com/", settle_ms=9000)
    config = engine_subject.build_worker_config(options, None)
    assert config["settle_ms"] == 9000
