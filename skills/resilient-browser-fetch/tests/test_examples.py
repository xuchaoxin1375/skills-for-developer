from __future__ import annotations

import argparse

import example_extract_page_info as extract_example
import example_greentradingxxl_batch as batch_example
import example_save_page as save_example
import resilient_fetch as core


def test_save_example_builds_module_options() -> None:
    args = argparse.Namespace(
        url="https://example.com",
        out="page.html",
        proxy=None,
        discover_proxy=True,
        engine="auto",
        timeout_ms=300_000,
        wall_timeout_ms=600_000,
        headful=False,
        expect_text=["Example"],
    )
    options = save_example.build_fetch_options(args)
    assert options.discover_proxy
    assert options.expected_texts == ("Example",)
    assert options.wall_timeout_ms == 600_000


def test_extract_visible_text_ignores_scripts_and_styles() -> None:
    page = "<title>Example</title><style>hidden</style><body>Hello <b>world</b></body>"
    assert extract_example.extract_visible_text(page) == "Example Hello world"


def test_fetch_page_info_returns_structured_data(monkeypatch) -> None:
    html = "<html><title>Example</title><body>Useful content</body></html>"
    result = core.FetchResult(
        engine="scrapling",
        url="https://example.com",
        final_url="https://example.com/",
        status=200,
        html=html,
        elapsed_sec=1.0,
    )
    outcome = core.FetchOutcome(
        result=result,
        attempts=(core.FetchAttempt("scrapling", True, 1.0, status=200),),
        proxy=None,
    )
    monkeypatch.setattr(extract_example, "fetch_page", lambda _options: outcome)
    info = extract_example.fetch_page_info("https://example.com", preview_chars=20)
    assert info == {
        "url": "https://example.com",
        "final_url": "https://example.com/",
        "status": 200,
        "title": "Example",
        "engine": "scrapling",
        "bytes_utf8": 62,
        "text_preview": "Example Useful conte",
    }


def test_greentradingxxl_example_defaults_to_visible_shared_session() -> None:
    args = batch_example.build_parser().parse_args([])
    options = batch_example.build_options(args)

    assert options.home_url == "https://www.greentradingxxl.com/"
    assert options.discover_proxy
    assert not options.headless
    assert options.concurrency == 2
    assert options.wall_timeout_ms == 330_000
    assert not options.expected_home_texts
    assert all(not request.expected_texts for request in batch_example.PRODUCT_REQUESTS)
    assert all(request.expected_selector is None for request in batch_example.PRODUCT_REQUESTS)


def test_greentradingxxl_strict_mode_adds_business_assertions() -> None:
    args = batch_example.build_parser().parse_args(["--strict"])
    options = batch_example.build_options(args)
    requests = batch_example.build_product_requests(args.strict)

    assert options.expected_home_texts == ("Green Trading XXL",)
    assert all(request.expected_selector == "h1" for request in requests)
    assert all(request.require_same_path for request in requests)


def test_greentradingxxl_product_name_uses_rendered_html() -> None:
    page = '<html><h1 class="product_title">  Example Product  </h1></html>'
    assert (
        batch_example.product_name(page, "https://www.greentradingxxl.com/produkt/example/")
        == "Example Product"
    )
