from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import resilient_fetch as subject


def make_result(**overrides: Any) -> subject.FetchResult:
    values: dict[str, Any] = {
        "engine": "scrapling",
        "url": "https://example.com",
        "final_url": "https://example.com/",
        "status": 200,
        "html": "<html><title>Example</title><body>expected</body></html>",
        "elapsed_sec": 1.25,
        "title": "Example",
        "block_reasons": [],
        "versions": {"scrapling": "test"},
    }
    values.update(overrides)
    return subject.FetchResult(**values)


AUTO_LEVELS = ("static", "playwright", "scrapling", "cloak-cdp")


def stub_availability(
    monkeypatch: pytest.MonkeyPatch, installed: tuple[str, ...] | None = None
) -> None:
    """Pin engine probing so unit tests never depend on the host environment."""

    names = AUTO_LEVELS if installed is None else installed
    monkeypatch.setattr(
        subject,
        "engine_availability",
        lambda name: subject.EngineAvailability(name in names, "stub"),
    )
    monkeypatch.setattr(
        subject, "available_engines", lambda: tuple(name for name in AUTO_LEVELS if name in names)
    )


@pytest.mark.parametrize(
    ("proxy", "endpoint"),
    [
        ("http://127.0.0.1:18080", ("127.0.0.1", 18080)),
        ("socks5://user:pass@example.com:1080", ("example.com", 1080)),
        ("https://[::1]:8443", ("::1", 8443)),
    ],
)
def test_parse_proxy_endpoint(proxy: str, endpoint: tuple[str, int]) -> None:
    assert subject.parse_proxy_endpoint(proxy) == endpoint


@pytest.mark.parametrize("proxy", ["127.0.0.1:18080", "ftp://host:21", "http://host"])
def test_parse_proxy_endpoint_rejects_invalid_values(proxy: str) -> None:
    with pytest.raises(ValueError):
        subject.parse_proxy_endpoint(proxy)


def test_redact_proxy_hides_credentials() -> None:
    assert (
        subject.redact_proxy("http://alice:secret@127.0.0.1:18080")
        == "http://***:***@127.0.0.1:18080"
    )
    assert subject.redact_proxy("http://127.0.0.1:18080") == "http://127.0.0.1:18080"
    assert subject.redact_proxy(None) is None


def test_discover_local_proxy_uses_first_reachable_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_ports: list[int] = []
    candidates = ("http://127.0.0.1:18081", "http://127.0.0.1:18082")

    class Connection:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: Any) -> None:
            return None

    def connect(endpoint: tuple[str, int], timeout: float) -> Connection:
        attempted_ports.append(endpoint[1])
        if endpoint[1] != 18082:
            raise OSError("closed")
        return Connection()

    monkeypatch.setattr(subject.socket, "create_connection", connect)
    assert subject.discover_local_proxy(candidates) == "http://127.0.0.1:18082"
    assert attempted_ports == [18081, 18082]


def test_discover_local_proxy_reads_registry_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = tmp_path / "proxy-resources.json"
    registry.write_text(
        json.dumps(
            {
                "default": "second",
                "proxies": [
                    {"name": "first", "url": "http://127.0.0.1:18081"},
                    {"name": "second", "url": "http://127.0.0.1:18082"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(subject, "PROXY_REGISTRY_PATH", registry)

    class Connection:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(
        subject.socket,
        "create_connection",
        lambda endpoint, timeout: Connection(),
    )
    assert subject.discover_local_proxy() == "http://127.0.0.1:18082"


def test_discover_local_proxy_without_registry_finds_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subject, "PROXY_REGISTRY_PATH", tmp_path / "missing.json")
    assert subject.discover_local_proxy() is None


def test_extract_title_decodes_entities_and_whitespace() -> None:
    page = "<html><head><title> A &amp;\n B </title></head></html>"
    assert subject.extract_title(page) == "A & B"
    assert subject.extract_title("<html></html>") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap_index.xml?part=1",
        "https://example.com/news-sitemap/1.xml",
    ],
)
def test_is_sitemap_url(url: str) -> None:
    assert subject.is_sitemap_url(url)


def test_is_sitemap_url_rejects_normal_page() -> None:
    assert not subject.is_sitemap_url("https://example.com/products/map.html")


def test_block_reasons_detects_multilingual_cloudflare_interstitial() -> None:
    page = (
        "<title>请稍候…</title><meta name='robots' content='noindex,nofollow'>"
        "<script src='https://challenges.cloudflare.com/widget.js'></script>"
    )
    assert "cloudflare_interstitial" in subject.block_reasons(page)


def test_block_reasons_does_not_reject_normal_cloudflare_assets() -> None:
    page = "<title>Shop</title><script>window.cloudflareAnalytics = true</script>"
    assert subject.block_reasons(page) == []


def test_validation_reasons_combines_content_expectations_and_status() -> None:
    result = make_result(status=403, html="short", block_reasons=["cloudflare_interstitial"])
    assert subject.validation_reasons(result, 100, ["missing"]) == [
        "cloudflare_interstitial",
        "content_too_short:5",
        "missing_expected_text:missing",
        "http_status:403",
    ]


def full_page(marker: str) -> str:
    """Build a page comfortably above the content-based acceptance floor."""

    return f"<html><title>Shop</title><body>{marker}{'x' * 20_000}</body></html>"


def test_validation_reasons_accepts_403_whose_body_is_verified_content() -> None:
    result = make_result(status=403, html=full_page("Ricambi"), title="Shop")
    reasons = subject.validation_reasons(result, 300, ["Ricambi"])
    assert reasons == []
    assert result.notes == ["http_status:403:accepted_by_content"]


def test_validation_reasons_keeps_403_without_caller_expectations() -> None:
    result = make_result(status=403, html=full_page("Ricambi"), title="Shop")
    assert subject.validation_reasons(result, 300, []) == ["http_status:403"]
    assert result.notes == [], "没有调用方断言时不得静默接受错误状态码的正文"


def test_validation_reasons_keeps_403_for_small_or_titleless_bodies() -> None:
    small = make_result(status=403, html="<html><title>Shop</title><body>Ricambi</body></html>")
    assert subject.validation_reasons(small, 1, ["Ricambi"]) == ["http_status:403"]
    titleless = make_result(status=403, html=f"<html><body>Ricambi{'x' * 20_000}</body></html>")
    assert subject.validation_reasons(titleless, 1, ["Ricambi"]) == ["http_status:403"]


def test_validation_reasons_only_relaxes_403() -> None:
    result = make_result(status=404, html=full_page("Ricambi"), title="Shop")
    assert subject.validation_reasons(result, 300, ["Ricambi"]) == ["http_status:404"]


def test_fetch_page_returns_structured_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_availability(monkeypatch)
    monkeypatch.setattr(subject, "run_isolated_engine", lambda *args: make_result())
    outcome = subject.fetch_page(
        subject.FetchOptions(
            url="https://example.com",
            engine="scrapling",
            timeout_ms=60_000,
            expected_texts=("expected",),
            min_bytes=1,
        )
    )
    assert outcome.result.title == "Example"
    assert outcome.proxy is None
    assert len(outcome.attempts) == 1
    assert outcome.attempts[0].ok
    assert outcome.attempts[0].kind == subject.KIND_OK


def test_fetch_page_falls_back_after_rejected_content(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_availability(monkeypatch, ("scrapling", "cloak-cdp"))
    results = iter(
        [
            make_result(status=403, html="challenge", block_reasons=["cloudflare_interstitial"]),
            make_result(engine="cloak-cdp"),
        ]
    )
    monkeypatch.setattr(subject, "run_isolated_engine", lambda *args: next(results))
    outcome = subject.fetch_page(
        subject.FetchOptions(url="https://example.com", timeout_ms=60_000, min_bytes=1)
    )
    assert outcome.result.engine == "cloak-cdp"
    assert [attempt.ok for attempt in outcome.attempts] == [False, True]
    assert outcome.attempts[0].rejected_html == "challenge"
    assert outcome.attempts[0].kind == subject.KIND_BLOCKED


def test_fetch_page_raises_structured_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_availability(monkeypatch)
    monkeypatch.setattr(
        subject,
        "run_isolated_engine",
        lambda *args: make_result(status=403, html="blocked"),
    )
    with pytest.raises(subject.FetchFailed) as captured:
        subject.fetch_page(
            subject.FetchOptions(url="https://example.com", engine="scrapling", timeout_ms=60_000)
        )
    assert captured.value.url == "https://example.com"
    assert captured.value.attempts[0].status == 403
    assert captured.value.blocked_engines == ("scrapling",)


def test_fetch_page_records_missing_engines_without_running_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_availability(monkeypatch, ())
    monkeypatch.setattr(
        subject,
        "run_isolated_engine",
        lambda *args: pytest.fail("缺件引擎不应启动 worker"),
    )
    with pytest.raises(subject.FetchFailed) as captured:
        subject.fetch_page(subject.FetchOptions(url="https://example.com"))
    assert captured.value.unavailable_engines == AUTO_LEVELS
    assert all(item.kind == subject.KIND_UNAVAILABLE for item in captured.value.attempts)
    assert "缺件" in captured.value.describe()


def test_fetch_page_reports_explicit_missing_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_availability(monkeypatch, ())
    monkeypatch.setattr(
        subject, "run_isolated_engine", lambda *args: pytest.fail("缺件引擎不应启动 worker")
    )
    with pytest.raises(subject.FetchFailed) as captured:
        subject.fetch_page(
            subject.FetchOptions(url="https://example.com", engine="scrapling", timeout_ms=60_000)
        )
    assert captured.value.unavailable_engines == ("scrapling",)
    assert captured.value.attempts[0].kind == subject.KIND_UNAVAILABLE


def test_save_page_uses_fetch_api_and_writes_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = make_result()
    outcome = subject.FetchOutcome(
        result=result,
        attempts=(subject.FetchAttempt("scrapling", True, 1.25, status=200),),
        proxy=None,
    )
    monkeypatch.setattr(subject, "fetch_page", lambda _options: outcome)
    output = tmp_path / "module-page.html"
    returned = subject.save_page(
        subject.FetchOptions(url="https://example.com", timeout_ms=60_000), output
    )
    assert returned is outcome
    assert output.read_text(encoding="utf-8") == result.html
    metadata = json.loads((tmp_path / "module-page.html.meta.json").read_text(encoding="utf-8"))
    assert metadata["attempts"][0]["engine"] == "scrapling"


def test_save_success_writes_html_and_metadata(tmp_path: Path) -> None:
    result = make_result()
    output = tmp_path / "page.html"
    attempts = [{"engine": "scrapling", "ok": True}]

    subject.save_success(result, output, attempts)

    assert output.read_text(encoding="utf-8") == result.html
    metadata = json.loads((tmp_path / "page.html.meta.json").read_text(encoding="utf-8"))
    encoded = result.html.encode()
    assert metadata["bytes_utf8"] == len(encoded)
    assert metadata["sha256"] == hashlib.sha256(encoded).hexdigest()
    assert metadata["attempts"] == attempts
    assert "html" not in metadata


def test_worker_main_serializes_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"url": "https://example.com"}), encoding="utf-8")
    monkeypatch.setattr(subject, "fetch_with_scrapling", lambda config: make_result())

    assert subject.worker_main("scrapling", config_path, tmp_path) == 0
    assert (tmp_path / "page.html").exists()
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))["status"] == 200


def test_worker_main_serializes_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"url": "https://example.com"}), encoding="utf-8")

    def fail(_config: dict[str, Any]) -> subject.FetchResult:
        raise subject.FetchError("failed safely")

    monkeypatch.setattr(subject, "fetch_with_scrapling", fail)

    assert subject.worker_main("scrapling", config_path, tmp_path) == 1
    error = json.loads((tmp_path / "error.json").read_text(encoding="utf-8"))
    assert error == {"engine": "scrapling", "error": "FetchError: failed safely"}


@pytest.mark.parametrize("selected", ["static", "playwright", "scrapling", "cloak-cdp", "scrapling-cli"])
def test_engine_order_keeps_explicit_selection_strict(selected: str) -> None:
    assert subject.engine_order(selected) == [selected]


def test_engine_order_auto_upgrades_by_level(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_availability(monkeypatch, ("scrapling", "cloak-cdp"))
    assert subject.engine_order("auto") == ["scrapling", "cloak-cdp"]


def test_engine_order_auto_uses_only_installed_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_availability(monkeypatch, ("static", "playwright"))
    assert subject.engine_order("auto") == ["static", "playwright"]


def test_engine_order_auto_never_includes_diagnostic_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_availability(monkeypatch, AUTO_LEVELS)
    assert "scrapling-cli" not in subject.engine_order("auto")


def test_attempt_kind_separates_missing_deps_from_blocks() -> None:
    assert subject.attempt_kind(("cloudflare_interstitial",), None) == subject.KIND_BLOCKED
    assert subject.attempt_kind(("http_status:403",), None) == subject.KIND_BLOCKED
    assert subject.attempt_kind(("content_too_short:12",), None) == subject.KIND_EMPTY
    assert subject.attempt_kind((), "scrapling: FetchError: boom") == subject.KIND_RUNTIME
    assert (
        subject.attempt_kind((), "scrapling: EngineUnavailableError: 未安装 scrapling")
        == subject.KIND_UNAVAILABLE
    )


def test_attempt_metadata_reports_kind() -> None:
    attempt = subject.FetchAttempt(
        "scrapling", False, 0.0, error="引擎不可用", kind=subject.KIND_UNAVAILABLE
    )
    assert attempt.as_metadata()["kind"] == subject.KIND_UNAVAILABLE
    assert attempt.as_metadata()["engine"] == "scrapling"
