"""Inline a saved page's external assets so the HTML opens offline."""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import logging
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

from resilient_fetch import (
    FetchOptions,
    ProxyUnavailableError,
    atomic_write_text,
    resolve_proxy,
    setup_logging,
)

DEFAULT_ASSET_TIMEOUT_MS = 20_000
DEFAULT_MAX_ASSET_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 30 * 1024 * 1024
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
UNFETCHABLE_PREFIXES = (
    "data:",
    "blob:",
    "javascript:",
    "about:",
    "mailto:",
    "tel:",
    "#",
)
CSS_URL_RE = re.compile(
    r"""url\(\s*(?P<quote>['"]?)(?P<url>[^'")\s]+)(?P=quote)\s*\)""",
    re.IGNORECASE,
)
CSS_IMPORT_RE = re.compile(
    r"""@import\s+(?:url\(\s*)?['"]?(?P<url>[^'")\s;]+)""",
    re.IGNORECASE,
)


class AssetFetchError(RuntimeError):
    """Raised when a single asset cannot be retrieved."""


@dataclass(frozen=True)
class Cookie:
    """Hold one cookie parsed from a Netscape cookie jar."""

    domain: str
    path: str
    secure: bool
    expires: float
    name: str
    value: str
    http_only: bool


@dataclass(frozen=True)
class InlineOptions:
    """Configure base URL, network access, and volume limits for inlining."""

    base_url: str | None = None
    proxy: str | None = None
    user_agent: str | None = None
    cookies: tuple[Cookie, ...] = ()
    timeout_ms: int = DEFAULT_ASSET_TIMEOUT_MS
    max_asset_bytes: int = DEFAULT_MAX_ASSET_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    inline_images: bool = True
    inline_fonts: bool = True


@dataclass
class InlineResult:
    """Record what was embedded and what was left as an online reference."""

    inlined: dict[str, int] = field(
        default_factory=lambda: {"stylesheet": 0, "image": 0, "font": 0, "other": 0}
    )
    total_asset_bytes: int = 0
    dropped_srcsets: int = 0
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def inlined_total(self) -> int:
        """Return how many distinct assets were embedded."""
        return sum(self.inlined.values())

    def note_skip(self, url: str, kind: str, reason: str) -> None:
        """Record one reference left external and why."""
        self.skipped.append({"url": url, "kind": kind, "reason": reason})


AssetFetcher = Callable[[str], tuple[bytes, str]]


@dataclass(frozen=True)
class _Asset:
    """Hold one downloaded asset and its normalized media type."""

    url: str
    payload: bytes
    mime: str


@dataclass(frozen=True)
class _StylesheetRef:
    """Hold one stylesheet link tag and its target."""

    raw: str
    href: str
    media: str | None


@dataclass(frozen=True)
class _SrcsetRef:
    """Hold one srcset value and whether its tag also has a src attribute."""

    value: str
    has_src: bool


class _AssetScanner(HTMLParser):
    """Collect asset references from saved HTML without rewriting markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stylesheets: list[_StylesheetRef] = []
        self.image_urls: list[str] = []
        self.srcsets: list[_SrcsetRef] = []
        self.style_values: list[str] = []
        self.base_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record asset-bearing tags and the references they carry."""
        values = {name.lower(): (value or "") for name, value in attrs}
        if tag == "base" and values.get("href") and self.base_href is None:
            self.base_href = values["href"]
        rel = values.get("rel", "").lower()
        is_css_link = "stylesheet" in rel or values.get("type", "").lower() == "text/css"
        if tag == "link" and is_css_link and values.get("href"):
            raw = self.get_starttag_text() or ""
            self.stylesheets.append(
                _StylesheetRef(raw=raw, href=values["href"], media=values.get("media"))
            )
        if tag in {"img", "source"}:
            has_src = bool(values.get("src"))
            if has_src:
                self.image_urls.append(values["src"])
            if values.get("srcset"):
                self.srcsets.append(_SrcsetRef(value=values["srcset"], has_src=has_src))
        if values.get("style"):
            self.style_values.append(values["style"])


def resolve_asset_url(url: str, base_url: str | None) -> str | None:
    """Resolve a reference to an absolute http(s) URL, or None when unfetchable."""
    candidate = url.strip()
    if not candidate or candidate.lower().startswith(UNFETCHABLE_PREFIXES):
        return None
    absolute = urllib.parse.urljoin(base_url or "", candidate)
    parts = urllib.parse.urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return urllib.parse.urldefrag(absolute)[0]


def load_cookie_jar(path: Path) -> tuple[list[Cookie], str | None]:
    """Parse a Netscape cookie jar and the User-Agent line exported beside it."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise AssetFetchError(f"cookie 文件读取失败: {exc}") from exc
    cookies: list[Cookie] = []
    user_agent: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_") :]
            http_only = True
        elif line.startswith("#"):
            if line.lower().startswith("# user-agent:"):
                user_agent = line.split(":", 1)[1].strip()
            continue
        else:
            http_only = False
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        domain, _flag, cookie_path, secure, expires, name, value = fields[:7]
        try:
            expires_at = float(expires)
        except ValueError:
            expires_at = 0.0
        cookies.append(
            Cookie(
                domain=domain,
                path=cookie_path or "/",
                secure=secure.strip().upper() == "TRUE",
                expires=expires_at,
                name=name,
                value=value,
                http_only=http_only,
            )
        )
    return cookies, user_agent


def cookie_header_for(
    url: str, cookies: Iterable[Cookie], now: float | None = None
) -> str | None:
    """Build the Cookie header for one URL from the jar entries that match it."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host:
        return None
    scheme = parts.scheme.lower()
    path = parts.path or "/"
    current = time.time() if now is None else now
    matched = [item for item in cookies if _cookie_matches(item, host, path, scheme, current)]
    if not matched:
        return None
    matched.sort(key=lambda item: len(item.path), reverse=True)
    return "; ".join(f"{item.name}={item.value}" for item in matched)


def _cookie_matches(cookie: Cookie, host: str, path: str, scheme: str, now: float) -> bool:
    """Apply RFC 6265 domain, path, secure, and expiry rules to one request."""
    domain = cookie.domain.lstrip(".").lower()
    if host != domain and not host.endswith("." + domain):
        return False
    if cookie.secure and scheme != "https":
        return False
    if cookie.expires and cookie.expires < now:
        return False
    cookie_path = cookie.path or "/"
    prefix = cookie_path if cookie_path.endswith("/") else cookie_path + "/"
    return path == cookie_path or path.startswith(prefix)


def normalize_mime(content_type: str, url: str) -> str:
    """Pick the most specific media type available for a data URI."""
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime and mime not in {"application/octet-stream", "binary/octet-stream", "text/plain"}:
        return mime
    guessed, _ = mimetypes.guess_type(url)
    return guessed or "application/octet-stream"


def asset_bucket(mime: str) -> str:
    """Group a media type into the counters reported by InlineResult."""
    if mime == "text/css":
        return "stylesheet"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("font/") or mime in {"application/font-woff", "application/vnd.ms-fontobject"}:
        return "font"
    return "other"


def to_data_uri(payload: bytes, mime: str) -> str:
    """Encode bytes as a base64 data URI."""
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


class _AssetStore:
    """Fetch each asset once and enforce the per-asset and total byte caps."""

    def __init__(self, options: InlineOptions, fetcher: AssetFetcher, result: InlineResult) -> None:
        self.options = options
        self.fetcher = fetcher
        self.result = result
        self.cache: dict[str, _Asset | None] = {}

    def fetch(self, url: str, base_url: str | None, kind: str = "other") -> _Asset | None:
        """Return one downloaded asset, or None when it stays external."""
        absolute = resolve_asset_url(url, base_url)
        if absolute is None:
            return None
        if absolute in self.cache:
            return self.cache[absolute]
        if kind == "image" and not self.options.inline_images:
            return None
        if self.result.total_asset_bytes >= self.options.max_total_bytes:
            self.result.note_skip(absolute, kind, "total_limit")
            return None
        try:
            payload, content_type = self.fetcher(absolute)
        except AssetFetchError as exc:
            self.result.note_skip(absolute, kind, f"fetch_failed: {exc}")
            self.cache[absolute] = None
            return None
        if len(payload) > self.options.max_asset_bytes:
            self.result.note_skip(absolute, kind, "asset_too_large")
            self.cache[absolute] = None
            return None
        if self.result.total_asset_bytes + len(payload) > self.options.max_total_bytes:
            self.result.note_skip(absolute, kind, "total_limit")
            self.cache[absolute] = None
            return None
        mime = normalize_mime(content_type, absolute)
        bucket = asset_bucket(mime)
        if bucket == "image" and not self.options.inline_images:
            self.result.note_skip(absolute, kind, "images_disabled")
            self.cache[absolute] = None
            return None
        if bucket == "font" and not self.options.inline_fonts:
            self.result.note_skip(absolute, kind, "fonts_disabled")
            self.cache[absolute] = None
            return None
        asset = _Asset(url=absolute, payload=payload, mime=mime)
        self.cache[absolute] = asset
        self.result.total_asset_bytes += len(payload)
        self.result.inlined[bucket] += 1
        return asset

    def data_uri(self, url: str, base_url: str | None, kind: str = "other") -> str | None:
        """Return a data URI for one reference, or None when it stays external."""
        asset = self.fetch(url, base_url, kind)
        if asset is None:
            return None
        return to_data_uri(asset.payload, asset.mime)


def _inline_css_urls(css: str, css_base: str | None, store: _AssetStore) -> str:
    """Replace url() references inside CSS with data URIs where allowed."""

    def replace(match: re.Match[str]) -> str:
        uri = store.data_uri(match.group("url"), css_base, "css_asset")
        return f'url("{uri}")' if uri else match.group(0)

    return CSS_URL_RE.sub(replace, css)


def _inline_stylesheets(
    html: str, refs: list[_StylesheetRef], store: _AssetStore, base_url: str | None
) -> str:
    """Replace stylesheet links with inline style blocks."""
    for ref in refs:
        asset = store.fetch(ref.href, base_url, "stylesheet")
        if asset is None:
            continue
        css = asset.payload.decode("utf-8", errors="replace")
        for match in CSS_IMPORT_RE.finditer(css):
            store.result.note_skip(match.group("url"), "stylesheet", "import_not_inlined")
        css = _inline_css_urls(css, asset.url, store)
        media = f' media="{ref.media}"' if ref.media else ""
        html = html.replace(ref.raw, f"<style{media}>\n{css}\n</style>", 1)
    return html


def _replace_attribute(html: str, attribute: str, old: str, new: str) -> str:
    """Swap one quoted attribute value in every tag that carries it."""
    for quote in ('"', "'"):
        html = html.replace(
            f"{attribute}={quote}{old}{quote}", f"{attribute}={quote}{new}{quote}"
        )
    return html


def _inline_images(
    html: str, scan: _AssetScanner, store: _AssetStore, base_url: str | None
) -> str:
    """Embed image sources and drop srcset, whose comma syntax rejects data URIs."""
    for url in scan.image_urls:
        uri = store.data_uri(url, base_url, "image")
        if uri:
            html = _replace_attribute(html, "src", url, uri)
    for ref in scan.srcsets:
        if not ref.has_src:
            first = ref.value.split(",", 1)[0].strip().split(None, 1)[0]
            store.result.note_skip(first, "image", "srcset_without_src")
            continue
        store.result.dropped_srcsets += 1
        for quote in ('"', "'"):
            html = html.replace(f"srcset={quote}{ref.value}{quote}", f"srcset={quote}{quote}", 1)
    return html


def _inline_style_attributes(
    html: str, values: list[str], store: _AssetStore, base_url: str | None
) -> str:
    """Inline url() references inside style attributes."""
    for value in values:
        rewritten = _inline_css_urls(value, base_url, store)
        if rewritten != value:
            html = html.replace(value, rewritten, 1)
    return html


def inline_html(
    html: str,
    options: InlineOptions | None = None,
    fetcher: AssetFetcher | None = None,
    snapshot: dict[str, tuple[bytes, str]] | None = None,
) -> tuple[str, InlineResult]:
    """Embed stylesheets, images, and fonts referenced by saved HTML."""
    settings = options or InlineOptions()
    result = InlineResult()
    scan = _AssetScanner()
    scan.feed(html)
    scan.close()
    base_url = settings.base_url or scan.base_href
    network = fetcher or http_fetcher(settings, base_url)
    asset_fetcher = chain_fetchers(snapshot_fetcher(snapshot), network) if snapshot else network
    store = _AssetStore(settings, asset_fetcher, result)
    output = _inline_stylesheets(html, scan.stylesheets, store, base_url)
    if settings.inline_images:
        output = _inline_images(output, scan, store, base_url)
    output = _inline_style_attributes(output, scan.style_values, store, base_url)
    return output, result


def load_snapshot(snapshot: Path) -> dict[str, tuple[bytes, str]]:
    """Parse an MHTML snapshot into a URL to (payload, media type) map."""
    try:
        raw = snapshot.read_bytes()
    except OSError as exc:
        raise AssetFetchError(f"快照读取失败: {exc}") from exc
    message = BytesParser(policy=policy.default).parsebytes(raw)
    assets: dict[str, tuple[bytes, str]] = {}
    for part in message.walk():
        location = part.get("Content-Location")
        if not location:
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        assets[urllib.parse.urldefrag(str(location))[0]] = (payload, part.get_content_type())
    return assets


def snapshot_fetcher(assets: dict[str, tuple[bytes, str]]) -> AssetFetcher:
    """Serve asset bytes captured in the browser snapshot without new requests."""

    def fetch(url: str) -> tuple[bytes, str]:
        try:
            return assets[url]
        except KeyError:
            raise AssetFetchError("快照中没有该资源") from None

    return fetch


def chain_fetchers(primary: AssetFetcher, fallback: AssetFetcher) -> AssetFetcher:
    """Try the snapshot first, then the network for resources it lacks."""

    def fetch(url: str) -> tuple[bytes, str]:
        try:
            return primary(url)
        except AssetFetchError:
            return fallback(url)

    return fetch


def http_fetcher(options: InlineOptions, referer: str | None) -> AssetFetcher:
    """Build a fetcher that retrieves assets over HTTP through the configured proxy."""
    handlers: list[urllib.request.BaseHandler] = []
    if options.proxy:
        handlers.append(
            urllib.request.ProxyHandler({"http": options.proxy, "https": options.proxy})
        )
    opener = urllib.request.build_opener(*handlers)
    timeout = max(options.timeout_ms, 1000) / 1000
    user_agent = options.user_agent or DEFAULT_USER_AGENT

    def fetch(url: str) -> tuple[bytes, str]:
        headers = {"User-Agent": user_agent, "Accept": "*/*"}
        cookie_header = cookie_header_for(url, options.cookies)
        if cookie_header:
            headers["Cookie"] = cookie_header
        request = urllib.request.Request(url, headers=headers)
        if referer:
            request.add_header("Referer", referer)
        try:
            with opener.open(request, timeout=timeout) as response:
                payload = response.read(options.max_asset_bytes + 1)
                content_type = response.headers.get("Content-Type", "")
                encoding = response.headers.get("Content-Encoding", "")
        except urllib.error.HTTPError as exc:
            raise AssetFetchError(f"HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AssetFetchError(str(exc)) from exc
        if encoding.lower() == "gzip":
            try:
                payload = gzip.decompress(payload)
            except OSError as exc:
                raise AssetFetchError("gzip inflated failed") from exc
        return payload, content_type

    return fetch


def metadata_base_url(source: Path) -> str | None:
    """Recover the page URL recorded by save_page in the sibling meta file."""
    meta = source.with_name(source.name + ".meta.json")
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    final_url = data.get("final_url") or data.get("url")
    return final_url if isinstance(final_url, str) else None


def _format_counts(counts: dict[str, int]) -> str:
    """Render the per-kind counters for logs."""
    return ", ".join(f"{kind}={count}" for kind, count in counts.items() if count)


def main(argv: list[str] | None = None) -> int:
    """Run the inliner CLI and report what was embedded."""
    parser = argparse.ArgumentParser(
        description="把已保存页面的外链样式、图片与字体内联成单个 HTML 文件。"
    )
    parser.add_argument("input")
    parser.add_argument("-o", "--out")
    parser.add_argument("--base-url")
    parser.add_argument("--proxy", default=os.getenv("SCRAPE_PROXY"))
    parser.add_argument("--discover-proxy", action="store_true")
    parser.add_argument("--cookies", help="Netscape 格式 cookie 文件，用于受保护的站内资源。")
    parser.add_argument("--user-agent", help="覆盖 cookie 文件里导出的 User-Agent。")
    parser.add_argument("--mhtml", help="浏览器会话导出的 MHTML 快照，优先从其中取资源。")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_ASSET_TIMEOUT_MS)
    parser.add_argument("--max-asset-bytes", type=int, default=DEFAULT_MAX_ASSET_BYTES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--no-images", action="store_true")
    parser.add_argument("--no-fonts", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    source = Path(args.input)
    try:
        html = source.read_text(encoding="utf-8")
    except OSError as exc:
        logging.error("读取失败: %s", exc)
        return 1
    base_url = args.base_url or metadata_base_url(source)
    cookies: tuple[Cookie, ...] = ()
    jar_user_agent: str | None = None
    if args.cookies:
        try:
            loaded, jar_user_agent = load_cookie_jar(Path(args.cookies))
        except AssetFetchError as exc:
            logging.error("%s", exc)
            return 1
        cookies = tuple(loaded)
        logging.info("已加载 %d 个 cookie (来源 %s)", len(cookies), args.cookies)
    snapshot_assets: dict[str, tuple[bytes, str]] | None = None
    if args.mhtml:
        try:
            snapshot_assets = load_snapshot(Path(args.mhtml))
        except AssetFetchError as exc:
            logging.error("%s", exc)
            return 1
        logging.info("已加载快照 %d 个资源 (来源 %s)", len(snapshot_assets), args.mhtml)
    options = InlineOptions(
        base_url=base_url,
        proxy=args.proxy,
        user_agent=args.user_agent or jar_user_agent,
        cookies=cookies,
        timeout_ms=args.timeout_ms,
        max_asset_bytes=args.max_asset_bytes,
        max_total_bytes=args.max_total_bytes,
        inline_images=not args.no_images,
        inline_fonts=not args.no_fonts,
    )
    if args.discover_proxy and not options.proxy:
        try:
            discovered = resolve_proxy(FetchOptions(url=base_url or args.input, discover_proxy=True))
        except ProxyUnavailableError as exc:
            logging.error("%s", exc)
            return 2
        options = replace(options, proxy=discovered)

    output, result = inline_html(html, options, snapshot=snapshot_assets)
    target = Path(args.out) if args.out else source.with_suffix(".offline.html")
    atomic_write_text(target, output)
    logging.info(
        "已写出 %s | 内联 %d 项 (%s) | 资产 %.1f KiB | 丢弃 srcset %d",
        target,
        result.inlined_total,
        _format_counts(result.inlined) or "无",
        result.total_asset_bytes / 1024,
        result.dropped_srcsets,
    )
    if result.skipped:
        logging.warning(
            "未内联 %d 项，保留原链接；原因分布: %s",
            len(result.skipped),
            json.dumps(
                {
                    reason: sum(1 for item in result.skipped if item["reason"] == reason)
                    for reason in {item["reason"] for item in result.skipped}
                },
                ensure_ascii=False,
            ),
        )
    if args.json:
        print(
            json.dumps(
                {
                    "input": str(source),
                    "output": str(target),
                    "output_bytes": len(output.encode("utf-8")),
                    "inlined": result.inlined,
                    "total_asset_bytes": result.total_asset_bytes,
                    "dropped_srcsets": result.dropped_srcsets,
                    "skipped": result.skipped,
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
