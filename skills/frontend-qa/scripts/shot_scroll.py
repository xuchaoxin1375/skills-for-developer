"""Managed viewport screenshots: one browser, one or more scroll positions.

Examples:
  python -X utf8 shot_scroll.py --url https://example.com --out page.png
  python -X utf8 shot_scroll.py --url https://example.com --screens 2 --channel msedge

The CLI starts a guardian, not a persistent browser service. See --help and
references/screenshot-workflow.md for lifecycle guarantees and exit statuses.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
from typing import Any
from urllib.parse import urlparse
import uuid

from managed_browser import USER_TEMP_ROOT, TaskError, run_managed

PROXY_REGISTRY_PATH = Path.home() / ".config" / "proxy-resources.json"


def registry_default_proxy(registry_path: Path | None = None) -> str | None:
    """Return the registered default without guessing local proxy ports."""
    try:
        data = json.loads(
            (registry_path or PROXY_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("proxies"), list):
        return None
    proxies = [
        entry
        for entry in data["proxies"]
        if isinstance(entry, dict) and isinstance(entry.get("url"), str)
    ]
    default = next(
        (entry for entry in proxies if entry.get("name") == data.get("default")), None
    )
    return (default or proxies[0])["url"] if proxies else None


def tcp_reachable(proxy: str) -> bool:
    """Check only the registered endpoint's listener, with a bounded wait."""
    try:
        parsed = urlparse(proxy)
        if not parsed.hostname or not parsed.port:
            return False
        with socket.create_connection((parsed.hostname, parsed.port), timeout=1):
            return True
    except (OSError, ValueError):
        return False


def resolve_proxy(explicit: str | None, *, discover: bool) -> tuple[str | None, str]:
    """Explicit -> environment -> optional registry -> direct."""
    if explicit:
        return explicit, "explicit"
    if os.getenv("SCRAPE_PROXY"):
        return os.environ["SCRAPE_PROXY"], "env:SCRAPE_PROXY"
    if not discover:
        return None, "direct"
    candidate = registry_default_proxy()
    if candidate and tcp_reachable(candidate):
        return candidate, "registry"
    raise TaskError("未找到可用的登记代理，请传 --proxy 或设置 SCRAPE_PROXY。", 2)


def capture(config: dict[str, Any]) -> dict[str, Any]:
    """Worker-only Playwright session; the guardian owns its hard deadline."""
    from playwright.sync_api import sync_playwright

    workspace = Path(config["workspace"])
    shots_dir = workspace / "shots"
    shots_dir.mkdir()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            timeout=config["timeout_ms"],
            channel=config["channel"],
            executable_path=config["executable_path"],
            proxy={"server": config["proxy"]} if config["proxy"] else None,
        )
        try:
            context = browser.new_context(
                viewport={"width": config["width"], "height": config["height"]}
            )
            try:
                context.set_default_timeout(config["timeout_ms"])
                page = context.new_page()
                page.goto(config["url"], wait_until="domcontentloaded")
                page.wait_for_timeout(config["settle_ms"])
                for index in range(config["screens"]):
                    page.screenshot(
                        path=str(shots_dir / f"{index}.png"), full_page=False
                    )
                    if index + 1 < config["screens"]:
                        page.evaluate("window.scrollBy(0, window.innerHeight)")
                        page.wait_for_timeout(config["step_wait_ms"])
            finally:
                context.close()
        finally:
            browser.close()
    return {
        "code": 0,
        "artifacts": [
            {"source": f"shots/{index}.png", "destination": target}
            for index, target in enumerate(config["outputs"])
        ],
    }


def worker_main() -> int:
    """Wait for containment assignment before importing or launching Playwright."""
    line = sys.stdin.buffer.readline()
    if not line:
        return 130
    config = json.loads(line)
    try:
        result = capture(config)
    except Exception as exc:
        # Browser exception strings may contain URLs or proxy credentials.
        hint = (
            "缺少 Playwright，请在目标 Python 环境安装该包。"
            if isinstance(exc, ImportError)
            else "请检查浏览器安装、目标页面与代理。"
        )
        result = {"code": 1, "error": f"截图失败：{type(exc).__name__}；{hint}"}
    (Path(config["workspace"]) / "result.json").write_text(
        json.dumps(result), encoding="utf-8"
    )
    return result["code"]


def positive_int(value: str) -> int:
    """Reject invalid budgets before starting a guardian."""
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return number


def nonnegative_int(value: str) -> int:
    """Allow an explicit zero render wait."""
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("不能为负数")
    return number


def build_parser() -> argparse.ArgumentParser:
    """Expose one interface for first-viewport and scrolling screenshots."""
    parser = argparse.ArgumentParser(
        description="托管截图：首屏或滚动多屏，自动回收浏览器。",
        epilog="示例：--url https://example.com --out page.png；多屏加 --screens 2。\n"
        "退出码：0 成功；1 截图失败；2 参数/代理错误；3 忙；4 清理未确认；124 总超时；130 取消。",
    )
    parser.add_argument("--url", required=True, help="目标 HTTP(S) URL")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--out", help="首屏 PNG 文件（仅 --screens 1）")
    output.add_argument("--out-dir", help="截图目录；默认临时目录中的独立运行目录")
    parser.add_argument(
        "--screens", type=positive_int, default=1, help="视口屏数，1–20，默认 1"
    )
    parser.add_argument(
        "--width", type=positive_int, default=1440, help="CSS 像素宽，最大 8192"
    )
    parser.add_argument(
        "--height", type=positive_int, default=900, help="CSS 像素高，最大 8192"
    )
    parser.add_argument(
        "--timeout-ms", type=positive_int, default=30_000, help="单次浏览器操作超时"
    )
    parser.add_argument(
        "--wall-timeout-ms",
        type=positive_int,
        default=60_000,
        help="整个 worker 的总期限；收尾另留最多约 8 秒",
    )
    parser.add_argument(
        "--settle-ms", type=nonnegative_int, default=500, help="首屏渲染等待，默认 500"
    )
    parser.add_argument(
        "--step-wait-ms", type=nonnegative_int, default=500, help="滚动后等待，默认 500"
    )
    parser.add_argument("--proxy", help="运行时代理；缺省读取 SCRAPE_PROXY")
    parser.add_argument(
        "--discover-proxy", action="store_true", help="无显式/环境代理时读登记并探测"
    )
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument(
        "--channel", choices=["chrome", "msedge"], help="使用本机浏览器，免下载制品"
    )
    browser.add_argument(
        "--executable-path", help="指定真实浏览器二进制；不接受包装器/垫片"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate input, start a managed task, print only committed screenshots."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        parsed = urlparse(args.url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            parser.error("--url 需要不含凭据的 HTTP(S) 地址")
        if args.screens > 20 or args.width > 8192 or args.height > 8192:
            parser.error("最多 20 屏，视口宽高各不超过 8192")
        if args.out and (args.screens != 1 or Path(args.out).suffix.lower() != ".png"):
            parser.error("--out 仅接受单屏 PNG 文件")
        if args.executable_path and (
            not Path(args.executable_path).is_file()
            or Path(args.executable_path).suffix.lower() in (".cmd", ".bat", ".ps1")
            or Path(args.executable_path).with_suffix(".shim").exists()
        ):
            parser.error("--executable-path 需要真实浏览器文件")
        proxy, source = resolve_proxy(args.proxy, discover=args.discover_proxy)
        logging.info("PROXY source=%s", source)
        slug = (
            re.sub(r"[^a-z0-9]+", "-", (parsed.hostname + parsed.path).lower()).strip(
                "-"
            )[:60]
            or "page"
        )
        out_dir = (
            Path(args.out_dir)
            if args.out_dir
            else USER_TEMP_ROOT / "shots" / uuid.uuid4().hex
        )
        outputs = (
            [str(Path(args.out).resolve())]
            if args.out
            else [
                str((out_dir / f"{slug}-s{index + 1}-{args.width}.png").resolve())
                for index in range(args.screens)
            ]
        )
        config = vars(args) | {"proxy": proxy, "outputs": outputs}
        result = run_managed(
            [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--worker"],
            config,
            args.wall_timeout_ms,
        )
        for artifact in result["artifacts"]:
            path = Path(artifact["destination"])
            print(f"SHOT {path} ({path.stat().st_size} bytes)")
        logging.info("CLEANUP verified")
        return 0
    except TaskError as exc:
        logging.error("FAIL %s", exc)
        return exc.code
    except (OSError, ValueError) as exc:
        logging.error("FAIL %s", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(worker_main() if sys.argv[1:] == ["--worker"] else main())
