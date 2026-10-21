"""Tests for the cdp-attach engine: attach to a browser the caller already started."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
import resilient_fetch as subject

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def _find_browser() -> str | None:
    for candidate in CHROME_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_devtools(port: int, timeout: float = 30.0) -> str:
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=3) as response:
                return json.loads(response.read().decode("utf-8")).get("webSocketDebuggerUrl", "")
        except Exception:
            time.sleep(0.4)
    raise RuntimeError("Chrome 调试端口未就绪")


def test_cdp_attach_requires_an_endpoint() -> None:
    with pytest.raises(subject.FetchError):
        subject.fetch_with_cdp_attach({"url": "https://example.com/", "timeout_ms": 5_000})


def test_cdp_url_conflicts_with_an_explicit_engine() -> None:
    with pytest.raises(ValueError):
        subject.validate_options(
            subject.FetchOptions(url="https://example.com/", cdp_url="http://127.0.0.1:9222", engine="static")
        )


def test_cdp_attach_is_not_in_the_auto_ladder() -> None:
    assert subject.ENGINES["cdp-attach"].in_auto is False
    assert "cdp-attach" not in subject.engine_order("auto")


def _serve_local_page(body: str) -> tuple[str, Any]:
    """Serve one page on 127.0.0.1 and return (url, server)."""

    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_address[1]}/target", server


def test_cdp_attach_reads_an_open_tab_without_closing_the_browser() -> None:
    browser = _find_browser()
    if browser is None:
        pytest.skip("本机没有 Chrome/Edge 可用于接管测试")
    url, server = _serve_local_page("<title>Attach Test</title><h1>hello from the user browser</h1>")
    port = _free_port()
    profile = Path(tempfile.mkdtemp(prefix="cdp-attach-test-"))
    args: list[str] = [
        cast(str, browser),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_devtools(port)
        result = subject.fetch_with_cdp_attach(
            {
                "url": url,
                "timeout_ms": 30_000,
                "render_timeout_ms": 8_000,
                "cdp_url": f"http://127.0.0.1:{port}",
                "playwright_api": "playwright",
            }
        )
        assert "hello from the user browser" in result.html
        assert result.engine == "cdp-attach"
        assert "browser_owned:false" in result.notes
        assert any(note.startswith("control_plane:cdp-attach") for note in result.notes)
        # 用户的浏览器不是我们的: 接管读完之后它必须还活着。
        assert process.poll() is None, "接管不应关闭用户的浏览器"
    finally:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        shutil.rmtree(profile, ignore_errors=True)
        server.shutdown()


def test_cdp_attach_reports_a_missing_tab() -> None:
    browser = _find_browser()
    if browser is None:
        pytest.skip("本机没有 Chrome/Edge 可用于接管测试")
    port = _free_port()
    profile = Path(tempfile.mkdtemp(prefix="cdp-attach-empty-"))
    args: list[str] = [
        cast(str, browser),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "data:text/html,<title>Other</title>",
    ]
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_devtools(port)
        with pytest.raises(subject.FetchError) as captured:
            subject.fetch_with_cdp_attach(
                {
                    "url": "https://example.com/not-opened",
                    "timeout_ms": 30_000,
                    "cdp_url": f"http://127.0.0.1:{port}",
                    "playwright_api": "playwright",
                }
            )
        assert "cdp-attach" in str(captured.value)
    finally:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        shutil.rmtree(profile, ignore_errors=True)


def test_local_cdp_env_restores_the_environment() -> None:
    saved = {key: os.environ.get(key) for key in ("NO_PROXY", "no_proxy")}
    os.environ.pop("NO_PROXY", None)
    os.environ.pop("no_proxy", None)
    try:
        with subject.local_cdp_env():
            assert "127.0.0.1" in (os.environ.get("NO_PROXY") or "")
        assert os.environ.get("NO_PROXY") is None
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
