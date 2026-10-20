"""Tests for offline asset inlining of saved pages."""

from __future__ import annotations

from inline_page import (
    AssetFetchError,
    InlineOptions,
    inline_html,
    load_snapshot,
    normalize_mime,
    resolve_asset_url,
)

ASSETS = {
    "https://cdn.example/site.css": (
        b'body{background:url("/img/bg.png")} @font-face{src:url(fonts/a.woff2)}',
        "text/css",
    ),
    "https://cdn.example/img/bg.png": (b"BG", "image/png"),
    "https://cdn.example/img/logo.png": (b"LOGO", "image/png"),
    "https://cdn.example/fonts/a.woff2": (b"WOFF", "font/woff2"),
}


class Recorder:
    """Serve canned assets while recording every requested URL."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[bytes, str]:
        self.calls.append(url)
        if url in ASSETS:
            return ASSETS[url]
        raise AssetFetchError("HTTP 404")


def test_inlines_stylesheet_and_its_assets() -> None:
    html = (
        '<html><head><link href="https://cdn.example/site.css" '
        'rel="stylesheet" media="screen"></head><body></body></html>'
    )

    out, result = inline_html(html, InlineOptions(), Recorder())

    assert '<style media="screen">' in out
    assert "cdn.example/site.css" not in out
    assert "data:image/png;base64," in out
    assert "data:font/woff2;base64," in out
    assert result.inlined["stylesheet"] == 1
    assert result.inlined["image"] == 1
    assert result.inlined["font"] == 1


def test_inlines_img_and_drops_srcset() -> None:
    html = (
        '<img src="https://cdn.example/img/logo.png" '
        'srcset="https://cdn.example/img/logo.png 1x, https://cdn.example/img/big.png 2x">'
    )

    out, result = inline_html(html, InlineOptions(), Recorder())

    assert 'src="data:image/png;base64,' in out
    assert 'srcset=""' in out
    assert result.dropped_srcsets == 1


def test_failed_asset_keeps_original_url() -> None:
    html = '<img src="https://cdn.example/img/missing.png">'

    out, result = inline_html(html, InlineOptions(), Recorder())

    assert "https://cdn.example/img/missing.png" in out
    assert result.skipped[0]["reason"].startswith("fetch_failed")


def test_asset_size_cap_keeps_url() -> None:
    html = '<img src="https://cdn.example/img/logo.png">'

    out, result = inline_html(html, InlineOptions(max_asset_bytes=2), Recorder())

    assert "cdn.example/img/logo.png" in out
    assert result.skipped[0]["reason"] == "asset_too_large"


def test_total_limit_stops_further_assets() -> None:
    html = (
        '<img src="https://cdn.example/img/bg.png">'
        '<img src="https://cdn.example/img/logo.png">'
    )

    out, result = inline_html(html, InlineOptions(max_total_bytes=3), Recorder())

    assert "data:image/png;base64," in out
    assert result.skipped[-1]["reason"] == "total_limit"


def test_relative_asset_without_base_is_untouched() -> None:
    recorder = Recorder()

    out, result = inline_html('<img src="/img/logo.png">', InlineOptions(), recorder)

    assert recorder.calls == []
    assert "/img/logo.png" in out
    assert result.inlined_total == 0


def test_base_href_is_used_for_relative_assets() -> None:
    html = '<head><base href="https://cdn.example/"></head><img src="img/logo.png">'

    out, _ = inline_html(html, InlineOptions(), Recorder())

    assert "data:image/png;base64," in out


def test_same_asset_is_fetched_once() -> None:
    recorder = Recorder()
    html = (
        '<img src="https://cdn.example/img/logo.png">'
        '<img src="https://cdn.example/img/logo.png">'
    )

    inline_html(html, InlineOptions(), recorder)

    assert recorder.calls.count("https://cdn.example/img/logo.png") == 1


def test_inlines_style_attribute_background() -> None:
    html = '<div style="background:url(https://cdn.example/img/bg.png)"></div>'

    out, _ = inline_html(html, InlineOptions(), Recorder())

    assert "data:image/png;base64," in out
    assert "cdn.example/img/bg.png" not in out


def test_existing_data_uri_is_untouched() -> None:
    html = '<img src="data:image/png;base64,AAAA">'

    out, _ = inline_html(html, InlineOptions(), Recorder())

    assert out == html


def test_css_import_is_reported_not_inlined() -> None:
    def fetcher(url: str) -> tuple[bytes, str]:
        if url.endswith("import.css"):
            return (b'@import "https://cdn.example/other.css"; body{}', "text/css")
        raise AssetFetchError("HTTP 404")

    html = '<link rel="stylesheet" href="https://cdn.example/import.css">'

    out, result = inline_html(html, InlineOptions(), fetcher)

    assert "import_not_inlined" in [item["reason"] for item in result.skipped]
    assert "<style>" in out


def test_srcset_without_src_is_reported() -> None:
    html = '<img srcset="https://cdn.example/img/big.png 2x">'

    out, result = inline_html(html, InlineOptions(), Recorder())

    assert 'srcset="https://cdn.example/img/big.png 2x"' in out
    assert result.skipped[0]["reason"] == "srcset_without_src"


def test_normalize_mime_falls_back_to_extension() -> None:
    assert normalize_mime("application/octet-stream", "https://x.example/a.css") == "text/css"


def test_css_link_without_rel_is_inlined() -> None:
    html = '<link type="text/css" href="https://cdn.example/site.css">'

    out, _ = inline_html(html, InlineOptions(), Recorder())

    assert "<style>" in out
    assert "cdn.example/site.css" not in out


def test_resolve_asset_url_rejects_non_http_schemes() -> None:
    assert resolve_asset_url("data:image/png;base64,AAAA", "https://x.example/") is None
    assert resolve_asset_url("#top", "https://x.example/") is None
    assert resolve_asset_url("./a.png", "https://x.example/post") == "https://x.example/a.png"


MHTML_FIXTURE = (
    "From: <Saved by Blink>\r\n"
    "MIME-Version: 1.0\r\n"
    'Content-Type: multipart/related; type="text/html"; boundary="BOUND"\r\n'
    "\r\n"
    "--BOUND\r\n"
    "Content-Type: text/html\r\n"
    "Content-Transfer-Encoding: quoted-printable\r\n"
    "Content-Location: https://example.com/post\r\n"
    "\r\n"
    '<html><img src=3D"https://cdn.example/img/logo.png"></html>\r\n'
    "--BOUND\r\n"
    "Content-Type: image/png\r\n"
    "Content-Transfer-Encoding: base64\r\n"
    "Content-Location: https://cdn.example/img/logo.png\r\n"
    "\r\n"
    "TE9HTw==\r\n"
    "--BOUND--\r\n"
)


def test_mhtml_snapshot_supplies_assets(tmp_path) -> None:
    snapshot_path = tmp_path / "page.mhtml"
    snapshot_path.write_text(MHTML_FIXTURE, encoding="utf-8", newline="")

    assets = load_snapshot(snapshot_path)
    out, result = inline_html(
        '<img src="https://cdn.example/img/logo.png">', InlineOptions(), snapshot=assets
    )

    assert "https://cdn.example/img/logo.png" in assets
    assert "data:image/png;base64," in out
    assert result.inlined["image"] == 1


def test_snapshot_miss_falls_back_to_network() -> None:
    recorder = Recorder()
    assets = {"https://cdn.example/unused.css": (b"body{}", "text/css")}

    out, _ = inline_html(
        '<img src="https://cdn.example/img/logo.png">',
        InlineOptions(),
        recorder,
        snapshot=assets,
    )

    assert recorder.calls == ["https://cdn.example/img/logo.png"]
    assert "data:image/png;base64," in out
