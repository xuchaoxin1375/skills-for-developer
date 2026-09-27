"""Example: fetch a protected page through the reusable API and save its source."""

from __future__ import annotations

import argparse
import logging
import os

from resilient_fetch import (
    DEFAULT_TIMEOUT_MS,
    FetchFailed,
    FetchOptions,
    ProxyUnavailableError,
    save_page,
    setup_logging,
)


def build_fetch_options(args: argparse.Namespace) -> FetchOptions:
    """Translate example CLI arguments into the reusable module options."""

    return FetchOptions(
        url=args.url,
        proxy=args.proxy,
        discover_proxy=args.discover_proxy,
        engine=args.engine,
        timeout_ms=args.timeout_ms,
        wall_timeout_ms=args.wall_timeout_ms,
        headful=args.headful,
        expected_texts=tuple(args.expect_text),
    )


def main(argv: list[str] | None = None) -> int:
    """Parse example arguments, save the page, and map structured failures to exit codes."""

    parser = argparse.ArgumentParser(description="保存一个网页的浏览器渲染后源码。")
    parser.add_argument("url")
    parser.add_argument("--out", default="page.html")
    parser.add_argument("--proxy", default=os.getenv("SCRAPE_PROXY"))
    parser.add_argument("--discover-proxy", action="store_true")
    parser.add_argument("--engine", choices=("auto", "scrapling", "cloak-cdp"), default="auto")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--wall-timeout-ms", type=int)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--expect-text", action="append", default=[])
    args = parser.parse_args(argv)
    setup_logging(False)
    try:
        save_page(build_fetch_options(args), args.out)
    except ProxyUnavailableError as exc:
        logging.error("%s", exc)
        return 2
    except FetchFailed as exc:
        logging.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
