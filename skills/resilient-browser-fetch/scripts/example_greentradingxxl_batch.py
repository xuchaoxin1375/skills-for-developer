"""Warm GreenTradingXXL once, then save three product pages from one browser."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from resilient_fetch import FetchResult, atomic_write_text
from site_session import ChallengeEvent, SiteRequest, SiteSessionManager, SiteSessionOptions

HOME_URL = "https://www.greentradingxxl.com/"
PRODUCT_REQUESTS = (
    SiteRequest(
        "https://www.greentradingxxl.com/produkt/opticlimate-6000-pro3-watergekoelde-airco/"
    ),
    SiteRequest("https://www.greentradingxxl.com/produkt/luftfilterbox-mit-vliesfilter-250mm/"),
    SiteRequest(
        "https://www.greentradingxxl.com/produkt/ocr-clip-fan-ec-motor-o-152-cm-manuell-neigbar/"
    ),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for the concrete batch example."""

    parser = argparse.ArgumentParser(
        description=(
            "先在有界面 Scrapling 会话中预热 GreenTradingXXL 首页，再复用同一窗口抓取商品页。"
        )
    )
    parser.add_argument("--proxy", default=os.environ.get("SCRAPE_PROXY"))
    parser.add_argument(
        "--discover-proxy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="未显式提供代理时探测本机 7897、7890、10808 (默认启用)。",
    )
    parser.add_argument(
        "--allow-direct",
        action="store_true",
        help="本地代理发现失败时允许直连；默认安全退出。",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="隐藏浏览器；默认显示窗口，以便首次验证时人工完成。",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        help="可选持久 profile；连续单次批量不设置即可，跨重启复用时再设置。",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("greentradingxxl-pages"))
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout-ms", type=int, default=300_000)
    parser.add_argument("--wall-timeout-ms", type=int, default=330_000)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="额外检查首页品牌文本、商品页 h1 和最终路径；默认仅做基础检查。",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def build_options(args: argparse.Namespace) -> SiteSessionOptions:
    """Translate CLI arguments into reusable site-session options."""

    return SiteSessionOptions(
        home_url=HOME_URL,
        proxy=args.proxy,
        discover_proxy=args.discover_proxy,
        allow_direct=args.allow_direct,
        headless=args.headless,
        profile_dir=args.profile_dir,
        max_pages=max(3, args.concurrency),
        concurrency=args.concurrency,
        timeout_ms=args.timeout_ms,
        wall_timeout_ms=args.wall_timeout_ms,
        expected_home_texts=("Green Trading XXL",) if args.strict else (),
        home_wait_selector="body",
    )


def build_product_requests(strict: bool) -> tuple[SiteRequest, ...]:
    """Add business assertions only when the caller explicitly requests them."""

    if not strict:
        return PRODUCT_REQUESTS
    return tuple(
        SiteRequest(request.url, expected_selector="h1", require_same_path=True)
        for request in PRODUCT_REQUESTS
    )


def product_name(page_html: str, url: str) -> str | None:
    """Extract a product heading with Scrapling's parser without another request."""

    from scrapling import Selector

    document = Selector(page_html, url=url)
    for selector in ("h1.product_title::text", "h1.entry-title::text", "h1::text"):
        value = document.css(selector).get()
        if value:
            return " ".join(str(value).split())
    return None


def output_name(url: str) -> str:
    """Create a stable HTML filename from the final URL path."""

    slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return f"{slug or 'index'}.html"


def save_result(result: FetchResult, output_dir: Path) -> dict[str, Any]:
    """Save rendered HTML and return its compact metadata record."""

    output = output_dir / output_name(result.url)
    atomic_write_text(output, result.html)
    encoded = result.html.encode("utf-8")
    return {
        "url": result.url,
        "final_url": result.final_url,
        "status": result.status,
        "title": result.title,
        "product_name": product_name(result.html, result.final_url or result.url),
        "bytes_utf8": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "html_file": str(output.resolve()),
    }


def report_challenge(event: ChallengeEvent) -> None:
    """Tell the operator when the visible browser needs manual attention."""

    if event.headless:
        logging.warning("无头浏览器检测到验证，无法人工接管: %s", event.url)
        return
    logging.warning(
        "请在已打开的浏览器窗口中完成人工验证；程序会自动继续，最长等待 %.1f 秒。",
        event.wall_timeout_ms / 1000,
    )


def configure_utf8_output() -> None:
    """Use UTF-8 when Windows redirects output through a legacy code page."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Execute homepage warmup and bounded product-page collection."""

    options = build_options(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    async with SiteSessionManager(options, on_challenge=report_challenge) as site:
        await site.warmup()
        results = await site.fetch_many(build_product_requests(args.strict))
        records = [save_result(result, args.output_dir) for result in results]

    summary = args.output_dir / "summary.json"
    atomic_write_text(summary, json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    return records


def main(argv: list[str] | None = None) -> int:
    """Run the example and print machine-readable result metadata."""

    configure_utf8_output()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        records = asyncio.run(run(args))
    except (OSError, RuntimeError, ValueError) as exc:
        logging.error("批量采集失败: %s", exc)
        return 1
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
