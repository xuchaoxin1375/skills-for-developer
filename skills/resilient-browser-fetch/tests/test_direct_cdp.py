"""Cover direct-CDP engine selection, Playwright API choice, and nodriver wiring."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import resilient_fetch as subject


class FakeCdp:
    """Minimal CDP namespace used by the nodriver engine."""

    class page:
        @staticmethod
        def capture_snapshot(**kwargs: Any) -> str:
            assert kwargs.get("format_") == "mhtml"
            return "<html>mhtml</html>"

    class emulation:
        @staticmethod
        async def set_locale_override(**_kwargs: Any) -> None:
            return None

        @staticmethod
        async def set_timezone_override(**_kwargs: Any) -> None:
            return None


class FakeTab:
    """Fake nodriver tab with the few methods the engine calls."""

    def __init__(self, html: str, url: str = "https://example.com/") -> None:
        self._html = html
        self.target = SimpleNamespace(url=url)
        self.screenshots: list[str] = []
        self.selected: list[str] = []
        self.sent: list[Any] = []

    async def evaluate(self, expression: str) -> str:
        if expression == "document.readyState":
            return "complete"
        return "FakeUA/1.0"

    async def get_content(self) -> str:
        return self._html

    async def select(self, selector: str, **_kwargs: Any) -> Any:
        self.selected.append(selector)
        return object()

    async def save_screenshot(self, path: str, **_kwargs: Any) -> None:
        self.screenshots.append(path)

    async def send(self, command: Any) -> Any:
        self.sent.append(command)
        return command


class FakeBrowser:
    """Fake nodriver browser that records launch and context choices."""

    def __init__(self, tab: FakeTab) -> None:
        self.tab = tab
        self.context_kwargs: dict[str, Any] | None = None
        self.get_urls: list[str] = []
        self.stopped = False
        self.cookies = self

    async def get(self, url: str) -> FakeTab:
        self.get_urls.append(url)
        return self.tab

    async def create_context(self, **kwargs: Any) -> FakeTab:
        self.context_kwargs = kwargs
        return self.tab

    async def get_all(self) -> list[Any]:
        return [
            SimpleNamespace(
                name="session",
                value="abc",
                domain=".example.com",
                path="/",
                expires=123,
                secure=True,
                http_only=True,
            )
        ]

    def stop(self) -> None:
        self.stopped = True


def install_fake_nodriver(
    monkeypatch: pytest.MonkeyPatch, tab: FakeTab
) -> tuple[FakeBrowser, dict[str, Any]]:
    """Install a fake ``nodriver`` module and return the browser/launch kwargs."""

    browser = FakeBrowser(tab)
    seen: dict[str, Any] = {}

    async def start(**kwargs: Any) -> FakeBrowser:
        seen.update(kwargs)
        return browser

    module = types.ModuleType("nodriver")
    module.start = start  # type: ignore[attr-defined]
    module.cdp = FakeCdp  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nodriver", module)
    return browser, seen


def nodriver_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "url": "https://example.com/",
        "proxy": None,
        "timeout_ms": 5_000,
        "wait_until": "load",
        "wait_selector": None,
        "post_wait_ms": 0,
        "challenge_wait_ms": 0,
        "headful": True,
        "locale": None,
        "timezone": None,
        "user_agent": None,
        "profile_dir": None,
        "executable_path": None,
        "screenshot": None,
        "save_snapshot": None,
        "save_cookies": None,
    }
    config.update(overrides)
    return config


@pytest.mark.asyncio
async def test_nodriver_engine_uses_system_chrome_and_records_direct_cdp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tab = FakeTab("<html><title>OK</title><body>content</body></html>")
    browser, launch = install_fake_nodriver(monkeypatch, tab)

    result = await subject.fetch_with_nodriver_async(nodriver_config())

    assert result.engine == "nodriver"
    assert result.status is None
    assert "control_plane:direct-cdp" in result.notes
    assert "browser_channel:system-chrome" in result.notes
    assert "headless:false" in result.notes
    assert launch["headless"] is False
    assert browser.get_urls == ["https://example.com/"]
    assert browser.stopped is True


@pytest.mark.asyncio
async def test_nodriver_engine_uses_proxy_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tab = FakeTab("<html><title>OK</title><body>content</body></html>")
    browser, _launch = install_fake_nodriver(monkeypatch, tab)

    await subject.fetch_with_nodriver_async(
        nodriver_config(proxy="http://user:pass@127.0.0.1:7897")
    )

    assert browser.context_kwargs is not None
    assert browser.context_kwargs["proxy_server"] == "http://user:pass@127.0.0.1:7897"
    assert browser.context_kwargs["new_window"] is True
    assert "new_tab" not in browser.context_kwargs
    assert browser.get_urls == [], "有代理时应通过 create_context 而不是默认 tab 导航"


@pytest.mark.asyncio
async def test_nodriver_engine_writes_snapshot_and_cookie_jar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tab = FakeTab("<html><title>OK</title><body>content</body></html>")
    install_fake_nodriver(monkeypatch, tab)
    snapshot = tmp_path / "page.mhtml"
    cookies = tmp_path / "cookies.txt"
    screenshot = tmp_path / "shot.png"

    await subject.fetch_with_nodriver_async(
        nodriver_config(
            save_snapshot=str(snapshot),
            save_cookies=str(cookies),
            screenshot=str(screenshot),
            headful=False,
        )
    )

    assert snapshot.read_text(encoding="utf-8") == "<html>mhtml</html>"
    assert tab.screenshots == [str(screenshot)]
    jar = cookies.read_text(encoding="utf-8")
    assert "session" in jar and "abc" in jar
    assert "#HttpOnly_.example.com" in jar


def test_nodriver_launch_kwargs_keep_system_chrome_and_profile(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "chrome.exe"
    kwargs = subject.nodriver_launch_kwargs(
        nodriver_config(
            headful=False,
            user_agent="ProbeUA/1.0",
            locale="zh-CN",
            profile_dir=str(tmp_path / "profiles"),
            executable_path=str(executable),
        )
    )
    assert kwargs["headless"] is True
    assert kwargs["browser_executable_path"] == str(executable)
    assert kwargs["user_data_dir"] == str(tmp_path / "profiles" / "nodriver")
    assert "--user-agent=ProbeUA/1.0" in kwargs["browser_args"]
    assert "--lang=zh-CN" in kwargs["browser_args"]


def test_engine_order_keeps_nodriver_out_of_headless_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "available_engines",
        lambda: ("static", "playwright", "scrapling", "cloak-cdp", "nodriver"),
    )
    monkeypatch.setattr(
        subject, "engine_availability", lambda _name: subject.EngineAvailability(True, "stub")
    )

    assert "nodriver" not in subject.engine_order("auto")
    assert "nodriver" in subject.engine_order("auto", headful=True)


def test_resolve_playwright_api_honours_explicit_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = importlib.util.find_spec
    monkeypatch.setattr(
        subject.importlib.util,
        "find_spec",
        lambda name: object()
        if name == "playwright"
        else (None if name == "patchright" else original(name)),
    )
    monkeypatch.setattr(subject, "playwright_api_name", lambda: "patchright")

    assert subject.resolve_playwright_api("auto") == "patchright"
    assert subject.resolve_playwright_api("playwright") == "playwright"
    assert subject.resolve_playwright_api("patchright") is None
    with pytest.raises(ValueError, match="playwright_api"):
        subject.resolve_playwright_api("bogus")


def test_validate_options_rejects_missing_explicit_playwright_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "resolve_playwright_api", lambda _requested: None)
    with pytest.raises(ValueError, match="未安装 patchright"):
        subject.validate_options(
            subject.FetchOptions(
                url="https://example.com",
                engine="playwright",
                playwright_api="patchright",
            )
        )


def test_browser_session_options_record_api_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import browser_session

    monkeypatch.setattr(browser_session, "resolve_playwright_api", lambda _api: "playwright")
    options = browser_session.BrowserSessionOptions(
        home_url="https://example.com",
        playwright_api="playwright",
    )
    assert options.playwright_api == "playwright"


def test_nodriver_probe_reports_missing_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = importlib.util.find_spec
    monkeypatch.setattr(
        subject.importlib.util,
        "find_spec",
        lambda name: None if name == "nodriver" else original(name),
    )
    availability = subject.probe_nodriver()
    assert availability.ok is False
    assert "AGPL" in availability.reason()


def test_nodriver_is_registered_but_ordered_after_other_engines() -> None:
    spec = subject.ENGINES["nodriver"]
    assert spec.level == 1
    assert spec.order > subject.ENGINES["cloak-cdp"].level * 10
    assert spec.auto_requires_headful is True
    assert subject.CAP_DIRECT_CDP in spec.capabilities


def test_nodriver_validation_warns_for_unsupported_flags(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        subject, "engine_availability", lambda _name: subject.EngineAvailability(True, "stub")
    )
    with caplog.at_level("WARNING"):
        subject.validate_options(
            subject.FetchOptions(
                url="https://example.com",
                engine="nodriver",
                headful=False,
                humanize=True,
                geoip=True,
                network_idle=True,
                wait_until="networkidle",
                referer="https://example.org/from",
            )
        )
    assert "nodriver" in caplog.text
    assert "--headful" in caplog.text
    assert "--humanize" in caplog.text
    assert "--referer" in caplog.text


def test_fetch_with_playwright_records_api_and_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "render_with_playwright",
        lambda _config: ("<html><title>OK</title><body>content</body></html>", 200, "https://example.com/"),
    )
    monkeypatch.setattr(subject, "resolve_playwright_api", lambda _api: "patchright")

    result = subject.fetch_with_playwright(
        {
            "url": "https://example.com/",
            "playwright_api": "patchright",
            "headful": True,
            "real_chrome": True,
        }
    )

    assert "control_plane:patchright" in result.notes
    assert "playwright_api:patchright" in result.notes
    assert "browser_channel:system-chrome" in result.notes
    assert "headless:false" in result.notes


def test_build_worker_config_carries_playwright_api() -> None:
    config = subject.build_worker_config(
        subject.FetchOptions(url="https://example.com", playwright_api="playwright"),
        None,
    )
    assert config["playwright_api"] == "playwright"
    assert "nodriver" in subject.WORKER_ENGINE_CHOICES
