"""Tests for cookie export and reuse between the fetcher and the inliner."""

from __future__ import annotations

import http.server
import threading
from pathlib import Path

import pytest
from archive_page import (
    ArchiveOptions,
    Cookie,
    cookie_header_for,
    http_fetcher,
    load_cookie_jar,
)
from resilient_fetch import export_cookies, write_cookie_jar


def test_write_cookie_jar_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "cookies.txt"
    count = write_cookie_jar(
        path,
        [
            {
                "name": "cf_clearance",
                "value": "v1",
                "domain": ".linux.do",
                "path": "/",
                "expires": 1893456000,
                "secure": True,
                "httpOnly": True,
            },
            {
                "name": "session",
                "value": "s",
                "domain": "linux.do",
                "path": "/t/",
                "expires": -1,
                "secure": False,
                "httpOnly": False,
            },
        ],
        user_agent="UA/1",
    )

    assert count == 2
    text = path.read_text(encoding="utf-8")
    assert "# User-Agent: UA/1" in text
    assert "#HttpOnly_.linux.do\tTRUE\t/\tTRUE\t1893456000\tcf_clearance\tv1" in text

    cookies, user_agent = load_cookie_jar(path)
    assert user_agent == "UA/1"
    assert [item.name for item in cookies] == ["cf_clearance", "session"]
    assert cookies[0].http_only is True
    assert cookies[1].expires == 0


def test_export_cookies_skips_without_target(tmp_path: Path) -> None:
    export_cookies({}, [{"name": "a", "value": "b", "domain": "example.com"}])

    assert list(tmp_path.iterdir()) == []


def test_export_cookies_writes_when_target_set(tmp_path: Path) -> None:
    target = tmp_path / "jar.txt"

    export_cookies({"save_cookies": str(target)}, [{"name": "a", "value": "b", "domain": "x.dev"}])

    assert "x.dev" in target.read_text(encoding="utf-8")


def _cookie(name: str, domain: str, path: str = "/", secure: bool = False, expires: float = 0.0) -> Cookie:
    return Cookie(
        domain=domain,
        path=path,
        secure=secure,
        expires=expires,
        name=name,
        value="v",
        http_only=False,
    )


def test_cookie_header_matches_domain_path_and_scheme() -> None:
    cookies = (
        _cookie("root", ".example.com"),
        _cookie("scoped", "example.com", path="/assets"),
        _cookie("secure_only", ".example.com", secure=True),
        _cookie("expired", ".example.com", expires=1000.0),
        _cookie("other", ".other.com"),
    )

    header = cookie_header_for("https://cdn.example.com/assets/a.png", cookies, now=2000.0)

    assert header == "scoped=v; root=v; secure_only=v"
    assert cookie_header_for("http://cdn.example.com/other.png", cookies, now=2000.0) == "root=v"
    assert cookie_header_for("https://cdn.example.com/other.png", cookies, now=3000.0) == (
        "root=v; secure_only=v"
    )


SEEN: list[str] = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        SEEN.append(self.headers.get("Cookie", ""))
        body = b"body{}"
        self.send_response(200)
        self.send_header("Content-Type", "text/css")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_http_fetcher_sends_exported_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    SEEN.clear()
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        options = ArchiveOptions(
            cookies=(_cookie("sid", "127.0.0.1"),),
            user_agent="UA/test",
            timeout_ms=5000,
        )
        payload, content_type = http_fetcher(options, None)(f"http://127.0.0.1:{port}/a.css")
    finally:
        server.shutdown()
        server.server_close()

    assert payload == b"body{}"
    assert content_type.startswith("text/css")
    assert SEEN == ["sid=v"]
