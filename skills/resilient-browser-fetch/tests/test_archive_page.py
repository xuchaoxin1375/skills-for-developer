"""Tests for offline page archiving, in split and single-file modes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from archive_page import (
    ArchiveOptions,
    AssetFetchError,
    archive_html,
    asset_filename,
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
    "https://cdn.example/img/big.png": (b"BIG", "image/png"),
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


def split_options(tmp_path: Path, **overrides: object) -> ArchiveOptions:
    """Build split-mode options that write into a temporary asset directory."""
    values: dict[str, object] = {"asset_dir": tmp_path / "page_files"}
    values.update(overrides)
    return ArchiveOptions(**values)  # type: ignore[arg-type]


def test_split_writes_stylesheet_and_assets(tmp_path: Path) -> None:
    html = (
        '<html><head><link href="https://cdn.example/site.css" rel="stylesheet"></head>'
        '<body><img src="https://cdn.example/img/logo.png"></body></html>'
    )

    out, result = archive_html(html, split_options(tmp_path), Recorder())

    css_name = asset_filename("https://cdn.example/site.css", "text/css")
    logo_name = asset_filename("https://cdn.example/img/logo.png", "image/png")
    bg_name = asset_filename("https://cdn.example/img/bg.png", "image/png")
    font_name = asset_filename("https://cdn.example/fonts/a.woff2", "font/woff2")
    asset_dir = tmp_path / "page_files"

    assert result.mode == "split"
    assert f'href="page_files/{css_name}"' in out
    assert f'src="page_files/{logo_name}"' in out
    assert (asset_dir / logo_name).read_bytes() == b"LOGO"
    assert f'url("{bg_name}")' in (asset_dir / css_name).read_text(encoding="utf-8")
    assert f'url("{font_name}")' in (asset_dir / css_name).read_text(encoding="utf-8")
    assert result.assets == {"stylesheet": 1, "image": 2, "font": 1, "other": 0}


def test_split_keeps_srcset_with_local_files(tmp_path: Path) -> None:
    html = (
        '<img src="https://cdn.example/img/logo.png" '
        'srcset="https://cdn.example/img/logo.png 1x, https://cdn.example/img/big.png 2x">'
    )

    out, result = archive_html(html, split_options(tmp_path), Recorder())

    logo_name = asset_filename("https://cdn.example/img/logo.png", "image/png")
    big_name = asset_filename("https://cdn.example/img/big.png", "image/png")
    assert f'srcset="page_files/{logo_name} 1x, page_files/{big_name} 2x"' in out
    assert result.dropped_srcsets == 0
    assert (tmp_path / "page_files" / big_name).read_bytes() == b"BIG"


def test_split_writes_manifest(tmp_path: Path) -> None:
    html = '<img src="https://cdn.example/img/logo.png">'

    archive_html(html, split_options(tmp_path), Recorder())

    manifest = json.loads((tmp_path / "page_files" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "split"
    assert manifest["assets"][0]["url"] == "https://cdn.example/img/logo.png"
    assert manifest["assets"][0]["bytes"] == 4


def test_split_requires_asset_dir() -> None:
    with pytest.raises(ValueError):
        archive_html("<img src='https://cdn.example/img/logo.png'>", ArchiveOptions())


def test_single_file_inlines_stylesheet_and_assets() -> None:
    html = (
        '<html><head><link href="https://cdn.example/site.css" '
        'rel="stylesheet" media="screen"></head><body></body></html>'
    )

    out, result = archive_html(html, ArchiveOptions(single_file=True), Recorder())

    assert '<style media="screen">' in out
    assert "cdn.example/site.css" not in out
    assert "data:image/png;base64," in out
    assert "data:font/woff2;base64," in out
    assert result.mode == "single"
    assert result.files == []


def test_single_file_drops_srcset() -> None:
    html = (
        '<img src="https://cdn.example/img/logo.png" '
        'srcset="https://cdn.example/img/logo.png 1x, https://cdn.example/img/big.png 2x">'
    )

    out, result = archive_html(html, ArchiveOptions(single_file=True), Recorder())

    assert 'src="data:image/png;base64,' in out
    assert 'srcset=""' in out
    assert result.dropped_srcsets == 1


def test_failed_asset_keeps_original_url(tmp_path: Path) -> None:
    html = '<img src="https://cdn.example/img/missing.png">'

    out, result = archive_html(html, split_options(tmp_path), Recorder())

    assert "https://cdn.example/img/missing.png" in out
    assert result.skipped[0]["reason"].startswith("fetch_failed")


def test_asset_size_cap_keeps_url(tmp_path: Path) -> None:
    html = '<img src="https://cdn.example/img/logo.png">'

    out, result = archive_html(html, split_options(tmp_path, max_asset_bytes=2), Recorder())

    assert "cdn.example/img/logo.png" in out
    assert result.skipped[0]["reason"] == "asset_too_large"


def test_total_limit_stops_further_assets(tmp_path: Path) -> None:
    html = (
        '<img src="https://cdn.example/img/bg.png">'
        '<img src="https://cdn.example/img/logo.png">'
    )

    out, result = archive_html(html, split_options(tmp_path, max_total_bytes=3), Recorder())

    assert f'src="page_files/{asset_filename("https://cdn.example/img/bg.png", "image/png")}"' in out
    assert result.skipped[-1]["reason"] == "total_limit"


def test_relative_asset_without_base_is_untouched(tmp_path: Path) -> None:
    recorder = Recorder()

    out, result = archive_html('<img src="/img/logo.png">', split_options(tmp_path), recorder)

    assert recorder.calls == []
    assert "/img/logo.png" in out
    assert result.asset_total == 0


def test_base_href_is_used_for_relative_assets(tmp_path: Path) -> None:
    html = '<head><base href="https://cdn.example/"></head><img src="img/logo.png">'

    out, _ = archive_html(html, split_options(tmp_path), Recorder())

    assert f'src="page_files/{asset_filename("https://cdn.example/img/logo.png", "image/png")}"' in out


def test_same_asset_is_written_once(tmp_path: Path) -> None:
    recorder = Recorder()
    html = (
        '<img src="https://cdn.example/img/logo.png">'
        '<img src="https://cdn.example/img/logo.png">'
    )

    _, result = archive_html(html, split_options(tmp_path), recorder)

    assert recorder.calls.count("https://cdn.example/img/logo.png") == 1
    assert len(result.files) == 1


def test_localizes_style_attribute_background(tmp_path: Path) -> None:
    html = '<div style="background:url(https://cdn.example/img/bg.png)"></div>'

    out, _ = archive_html(html, split_options(tmp_path), Recorder())

    assert f'url("page_files/{asset_filename("https://cdn.example/img/bg.png", "image/png")}")' in out


def test_srcset_inside_script_payload_is_not_rewritten(tmp_path: Path) -> None:
    srcset = "https://cdn.example/img/logo.png 1x, https://cdn.example/img/big.png 2x"
    payload = json.dumps(
        {"cooked": f'<img src="https://cdn.example/img/logo.png" srcset="{srcset}">'}
    )
    html = (
        f'<script type="application/json">{payload}</script>'
        f'<img src="https://cdn.example/img/logo.png" srcset="{srcset}">'
    )

    out, _ = archive_html(html, split_options(tmp_path), Recorder())

    logo_name = asset_filename("https://cdn.example/img/logo.png", "image/png")
    big_name = asset_filename("https://cdn.example/img/big.png", "image/png")
    assert f'srcset="page_files/{logo_name} 1x, page_files/{big_name} 2x"' in out
    assert f'srcset=\\"{srcset}' in out


def test_existing_data_uri_is_untouched(tmp_path: Path) -> None:
    html = '<img src="data:image/png;base64,AAAA">'

    out, _ = archive_html(html, split_options(tmp_path), Recorder())

    assert out == html


def test_css_import_is_reported_not_localized(tmp_path: Path) -> None:
    def fetcher(url: str) -> tuple[bytes, str]:
        if url.endswith("import.css"):
            return (b'@import "https://cdn.example/other.css"; body{}', "text/css")
        raise AssetFetchError("HTTP 404")

    html = '<link rel="stylesheet" href="https://cdn.example/import.css">'

    _, result = archive_html(html, split_options(tmp_path), fetcher)

    assert "import_not_inlined" in [item["reason"] for item in result.skipped]


def test_css_link_without_rel_is_localized(tmp_path: Path) -> None:
    html = '<link type="text/css" href="https://cdn.example/site.css">'

    out, _ = archive_html(html, split_options(tmp_path), Recorder())

    assert f'href="page_files/{asset_filename("https://cdn.example/site.css", "text/css")}"' in out


def test_resolve_asset_url_rejects_non_http_schemes() -> None:
    assert resolve_asset_url("data:image/png;base64,AAAA", "https://x.example/") is None
    assert resolve_asset_url("#top", "https://x.example/") is None
    assert resolve_asset_url("./a.png", "https://x.example/post") == "https://x.example/a.png"


def test_normalize_mime_falls_back_to_extension() -> None:
    assert normalize_mime("application/octet-stream", "https://x.example/a.css") == "text/css"


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


def test_mhtml_snapshot_supplies_assets(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "page.mhtml"
    snapshot_path.write_text(MHTML_FIXTURE, encoding="utf-8", newline="")

    assets = load_snapshot(snapshot_path)
    out, result = archive_html(
        '<img src="https://cdn.example/img/logo.png">',
        ArchiveOptions(single_file=True),
        snapshot=assets,
    )

    assert "https://cdn.example/img/logo.png" in assets
    assert "data:image/png;base64," in out
    assert result.assets["image"] == 1


def test_snapshot_miss_falls_back_to_network(tmp_path: Path) -> None:
    recorder = Recorder()
    assets = {"https://cdn.example/unused.css": (b"body{}", "text/css")}

    out, _ = archive_html(
        '<img src="https://cdn.example/img/logo.png">',
        split_options(tmp_path),
        recorder,
        snapshot=assets,
    )

    assert recorder.calls == ["https://cdn.example/img/logo.png"]
    assert f'src="page_files/{asset_filename("https://cdn.example/img/logo.png", "image/png")}"' in out
