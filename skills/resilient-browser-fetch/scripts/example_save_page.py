"""Example: fetch a protected page through the reusable API and save its source."""

from __future__ import annotations

import argparse
import logging
import os

from resilient_fetch import (
    DEFAULT_PLAYWRIGHT_API,
    DEFAULT_TIMEOUT_MS,
    ENGINE_CHOICES,
    PLAYWRIGHT_API_CHOICES,
    WALL_TIMEOUT_HELP,
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
        playwright_api=getattr(args, "playwright_api", DEFAULT_PLAYWRIGHT_API),
        timeout_ms=args.timeout_ms,
        wall_timeout_ms=args.wall_timeout_ms,
        headful=args.headful,
        expected_texts=tuple(args.expect_text),
        save_cookies=args.save_cookies,
        save_snapshot=args.save_snapshot,
    )


def main(argv: list[str] | None = None) -> int:
    """Parse example arguments, save the page, and map structured failures to exit codes."""

    parser = argparse.ArgumentParser(description="保存一个网页的浏览器渲染后源码。")
    parser.add_argument("url")
    parser.add_argument("--out", default="page.html")
    parser.add_argument("--proxy", default=os.getenv("SCRAPE_PROXY"))
    parser.add_argument("--discover-proxy", action="store_true")
    parser.add_argument("--engine", choices=ENGINE_CHOICES, default="auto")
    parser.add_argument(
        "--playwright-api",
        choices=PLAYWRIGHT_API_CHOICES,
        default=DEFAULT_PLAYWRIGHT_API,
        help="层 1 使用 auto/playwright/patchright；默认 auto (Patchright 优先)。",
    )
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--wall-timeout-ms", type=int, help=WALL_TIMEOUT_HELP)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--expect-text", action="append", default=[])
    parser.add_argument(
        "--save-cookies",
        help="保存浏览器 cookie (Netscape 格式，可能含会话 cookie) 供后续 HTTP 复用。",
    )
    parser.add_argument(
        "--save-snapshot",
        help="保存 MHTML 快照 (页面与已加载资源)，供受保护站点的离线内联使用。",
    )
    args = parser.parse_args(argv)
    setup_logging(False)
    try:
        save_page(build_fetch_options(args), args.out)
    except ValueError as exc:
        parser.error(str(exc))
    except ProxyUnavailableError as exc:
        logging.error("%s", exc)
        return 2
    except FetchFailed as exc:
        logging.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
