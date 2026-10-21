"""Example: fetch a protected page through the reusable API and save its source."""

from __future__ import annotations

import argparse
import logging
import os

from resilient_fetch import (
    DEFAULT_PLAYWRIGHT_API,
    DEFAULT_RENDER_TIMEOUT_MS,
    DEFAULT_SETTLE_MS,
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
        settle_ms=getattr(args, "settle_ms", DEFAULT_SETTLE_MS),
        render_timeout_ms=getattr(args, "render_timeout_ms", DEFAULT_RENDER_TIMEOUT_MS),
        cdp_url=getattr(args, "cdp_url", None),
        cdp_navigate=bool(getattr(args, "cdp_navigate", False)),
        executable_path=getattr(args, "executable_path", None),
        browser_brand=getattr(args, "browser_brand", None),
    )


def main(argv: list[str] | None = None) -> int:
    """Parse example arguments, save the page, and map structured failures to exit codes."""

    parser = argparse.ArgumentParser(description="保存一个网页的浏览器渲染后源码。")
    parser.add_argument("url")
    parser.add_argument("-o", "--out", default="page.html")
    parser.add_argument("-p", "--proxy", default=os.getenv("SCRAPE_PROXY"))
    parser.add_argument("--discover-proxy", action="store_true")
    parser.add_argument("-e", "--engine", choices=ENGINE_CHOICES, default="auto")
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
        "--settle-ms",
        type=int,
        default=DEFAULT_SETTLE_MS,
        help="chrome-late 的最小静默窗口: 这期间不接调试器。",
    )
    parser.add_argument(
        "--render-timeout-ms",
        type=int,
        default=DEFAULT_RENDER_TIMEOUT_MS,
        help="chrome-late 接入后等待渲染完成的上限(客户端渲染的应用要调大)。",
    )
    parser.add_argument(
        "--cdp-url",
        help=(
            "接管已开着的浏览器(如 --remote-debugging-port 启动的 Chrome/Edge),"
            "复用它自己的 profile/cookie/放行凭据;只读已渲染 DOM,不会关闭它。"
        ),
    )
    parser.add_argument(
        "--cdp-navigate",
        action="store_true",
        help="接管的浏览器里没有目标页时,让它导航到目标 URL(挑战窗口里会带着调试会话)。",
    )
    parser.add_argument(
        "--save-cookies",
        help="保存浏览器 cookie (Netscape 格式，可能含会话 cookie) 供后续 HTTP 复用。",
    )
    parser.add_argument(
        "--save-snapshot",
        help="保存 MHTML 快照 (页面与已加载资源)，供受保护站点的离线内联使用。",
    )
    parser.add_argument(
        "--executable-path",
        help=(
            "自定义浏览器可执行文件绝对路径(chrome-late 晚接入引擎用)。"
            "WAF 可能按客户端品牌判负: 同一出口 Chrome 被拒、Edge 放行时用它换品牌。"
        ),
    )
    parser.add_argument(
        "-b",
        "--browser-brand",
        choices=("auto", "chrome", "edge", "chromium"),
        help=(
            "系统浏览器品牌偏好(chrome-late 的浏览器发现、层 1 的 channel):"
            "auto(默认 Chrome→Edge→Chromium)、chrome、edge、chromium;"
            "也可用环境变量 RESILIENT_BROWSER。"
        ),
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
