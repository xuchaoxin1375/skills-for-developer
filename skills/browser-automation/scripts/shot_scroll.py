"""Managed viewport screenshots: one browser, one or more scroll positions.

Examples:
  python -X utf8 shot_scroll.py --url https://example.com --out page.png
  python -X utf8 shot_scroll.py --url https://example.com --screens 2 --channel msedge
  python -X utf8 shot_scroll.py --url https://example.com --to-bottom --out last.png

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

from browser_discovery import discover_browsers, native_binary, select_browser
from managed_browser import USER_TEMP_ROOT, TaskError, run_managed

PROXY_REGISTRY_PATH = Path.home() / ".config" / "proxy-resources.json"

BOTTOM_MAX_STEPS = 60
BOTTOM_STABLE_CHECKS = 3


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


def page_metrics(page: Any) -> dict[str, int]:
    """Read the values that decide whether the real bottom is reached."""
    return page.evaluate(
        "() => ({y: Math.round(window.scrollY), h: window.innerHeight,"
        " d: Math.max(document.body.scrollHeight,"
        " document.documentElement.scrollHeight)})"
    )


def settle_to_bottom(page: Any, config: dict[str, Any]) -> dict[str, int]:
    """Walk down one viewport at a time until the bottom holds still.

    Content created on scroll (lazy sections, infinite feeds) only exists after
    being seen, so jumping to the document height renders a blank, too-short
    page instead of the last screen.
    """
    height = page_metrics(page)["d"]
    stable = 0
    for _ in range(BOTTOM_MAX_STEPS):
        metrics = page_metrics(page)
        if metrics["y"] + metrics["h"] >= metrics["d"] - 4 and metrics["d"] == height:
            stable += 1
            if stable >= BOTTOM_STABLE_CHECKS:
                break
        else:
            stable = 0
        height = metrics["d"]
        page.evaluate("() => window.scrollTo(0, window.scrollY + window.innerHeight)")
        page.wait_for_timeout(config["step_wait_ms"])
    else:
        raise TaskError(
            "未能确认页面底部：高度持续变化或页面无限滚动；请改用 --screens 指定屏数。",
            1,
        )
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(config["step_wait_ms"])
    return page_metrics(page)


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
            version = browser.version
            context = browser.new_context(
                viewport={"width": config["width"], "height": config["height"]}
            )
            try:
                context.set_default_timeout(config["timeout_ms"])
                page = context.new_page()
                page.goto(config["url"], wait_until="domcontentloaded")
                page.wait_for_timeout(config["settle_ms"])
                bottom: dict[str, int] | None = None
                if config.get("to_bottom"):
                    bottom = settle_to_bottom(page, config)
                    page.screenshot(
                        path=str(shots_dir / "0.png"), full_page=False
                    )
                else:
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
    result: dict[str, Any] = {
        "code": 0,
        "browser_version": version,
        "artifacts": artifacts(config),
    }
    if bottom is not None:
        result["page"] = bottom
    return result


def artifacts(config: dict[str, Any]) -> list[dict[str, str]]:
    """Map this round's shot files onto the requested destinations."""
    return [
        {"source": f"shots/{index}.png", "destination": target}
        for index, target in enumerate(config["outputs"])
    ]


def light_capture(config: dict[str, Any]) -> dict[str, Any]:
    """Worker-only light engine: one installed browser, no Playwright package."""
    import light_browser

    shots_dir = Path(config["workspace"]) / "shots"
    shots_dir.mkdir()
    version = light_browser.capture(config, shots_dir)
    return {"code": 0, "browser_version": version, "artifacts": artifacts(config)}


def engine_capture(config: dict[str, Any]) -> dict[str, Any]:
    """Dispatch by engine so the worker imports only what that engine needs."""
    if config["engine"] == "playwright":
        return capture(config)
    return light_capture(config)


def worker_main() -> int:
    """Wait for containment assignment before importing or launching anything."""
    line = sys.stdin.buffer.readline()
    if not line:
        return 130
    config = json.loads(line)
    try:
        result = engine_capture(config)
    except TaskError as exc:
        # Engine messages are bounded and deliberately free of page details.
        result = {"code": exc.code, "error": str(exc)}
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


def native_ok(path: str) -> bool:
    """Read-only format check for a candidate browser file."""
    try:
        return native_binary(Path(path), sys.platform)
    except (OSError, RuntimeError):
        return False


def doctor_report(args: argparse.Namespace) -> dict[str, Any]:
    """Report engine choices without starting a guardian or launching a browser."""
    import importlib.util

    package = "installed" if importlib.util.find_spec("playwright") else "missing"
    candidates = discover_browsers()
    selected: dict[str, Any] | None = None
    if args.executable_path:
        selected = {
            "browser": "explicit",
            "path": args.executable_path,
            "source": "explicit",
            "reason": "由 --executable-path 指定",
        }
    else:
        candidate = select_browser(candidates=candidates)
        if candidate is not None:
            selected = candidate.as_dict()
    if selected is not None:
        selected["launch"] = "not-probed"
        if args.probe_launch:
            import light_browser

            try:
                version = light_browser.probe_launch(selected["path"], args.timeout_ms)
                selected["launch"] = f"ok:{version}"
            except TaskError as exc:
                selected["launch"] = f"failed:{exc}"
    if package == "installed":
        recommended = {
            "engine": "playwright",
            "reason": "目标环境已有 Playwright 包，沿用默认制品与默认协议",
        }
    elif selected is not None:
        recommended = {
            "engine": "cdp",
            "reason": "缺少 Playwright 包；显式 --engine cdp 加真实浏览器可保留滚动语义",
        }
    else:
        recommended = {
            "engine": "none",
            "reason": "既缺 Playwright 包，也未发现可用的本机原生浏览器",
        }
    return {
        "platform": sys.platform,
        "playwright": {
            "package": package,
            "browsers_path": os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or None,
        },
        "candidates": [item.as_dict() for item in candidates],
        "selected": selected,
        "recommended": recommended,
        "note": "只读体检：不启动 guardian、不启动浏览器；--probe-launch 会实际探一次启动。",
    }


def build_parser() -> argparse.ArgumentParser:
    """Expose one interface for first-viewport and scrolling screenshots."""
    parser = argparse.ArgumentParser(
        description="托管截图：首屏、滚动多屏或末屏，自动回收浏览器。",
        epilog="示例：--url https://example.com --out page.png；多屏加 --screens 2；末屏加 --to-bottom。\n"
        "退出码：0 成功；1 截图失败；2 参数/代理错误；3 忙；4 清理未确认；124 总超时；130 取消。",
    )
    parser.add_argument("--url", help="目标 HTTP(S) URL；只列浏览器时不需要")
    parser.add_argument(
        "--list-browsers",
        action="store_true",
        help="只读列出本机浏览器 JSON，不启动、不安装",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--out", help="单张 PNG 文件（首屏或 --to-bottom 末屏）")
    output.add_argument("--out-dir", help="截图目录；默认临时目录中的独立运行目录")
    parser.add_argument(
        "--screens", type=positive_int, default=1, help="视口屏数，1–20，默认 1"
    )
    parser.add_argument(
        "--to-bottom",
        action="store_true",
        help="逐屏滚到底后只拍末屏视口；与 --screens 互斥，仅默认 Playwright 引擎",
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
    browser.add_argument(
        "--discover-browser",
        action="store_true",
        help="从常见安装位置选择本机浏览器；不下载、不失败换浏览器",
    )
    parser.add_argument(
        "--engine",
        choices=("playwright", "oneshot", "cdp"),
        default="playwright",
        help="采集引擎；oneshot/cdp 为轻量引擎，须显式指定真实浏览器",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="只读体检：报告可用引擎与选中的浏览器，不启动 guardian 或浏览器",
    )
    parser.add_argument(
        "--probe-launch",
        action="store_true",
        help="配合 --doctor 实际探一次候选启动；不探不得声称可启动",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate input, start a managed task, print only committed screenshots."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.probe_launch and not args.doctor:
            parser.error("--probe-launch 需要与 --doctor 一起使用")
        if args.doctor:
            if args.url or args.out or args.out_dir or args.list_browsers:
                parser.error("--doctor 单独使用，不与截图或候选列出参数组合")
            if args.channel:
                parser.error(
                    "--doctor 不解析 Playwright channel；用 --executable-path 指定本机浏览器"
                )
            if args.executable_path and not native_ok(args.executable_path):
                parser.error("--executable-path 需要可读的原生浏览器文件")
            print(json.dumps(doctor_report(args), ensure_ascii=False, indent=2))
            return 0
        if args.list_browsers:
            if (
                args.url
                or args.channel
                or args.executable_path
                or args.discover_browser
            ):
                parser.error("--list-browsers 单独使用，不与截图或浏览器选择参数组合")
            print(
                json.dumps(
                    {
                        "platform": sys.platform,
                        "candidates": [item.as_dict() for item in discover_browsers()],
                        "note": "只读路径/格式检查；不证明可启动、可信或与项目兼容。"
                        "source=playwright-cache 的条目仅为信息，不参与自动选择。",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if not args.url:
            parser.error("截图需要 --url；只读查找使用 --list-browsers")
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
        if args.to_bottom and args.screens != 1:
            parser.error("--to-bottom 与 --screens 互斥：末屏为一张视口")
        if args.out and (args.screens != 1 or Path(args.out).suffix.lower() != ".png"):
            parser.error("--out 仅接受单屏 PNG 文件")
        if args.engine != "playwright":
            if args.channel:
                parser.error(
                    "--engine oneshot/cdp 不接受 --channel；"
                    "请用 --executable-path 或 --discover-browser"
                )
            if not (args.executable_path or args.discover_browser):
                parser.error(
                    "--engine oneshot/cdp 需要显式指定真实浏览器：轻量引擎不是默认回退"
                )
            if args.to_bottom:
                parser.error(
                    "--to-bottom 需要默认 Playwright 引擎："
                    "轻量引擎按整块画布切片，不确认底部"
                )
        if args.executable_path and not native_ok(args.executable_path):
            parser.error("--executable-path 需要可读的原生浏览器文件")
        if args.discover_browser:
            candidate = select_browser(candidates=discover_browsers())
            if candidate is None:
                raise TaskError(
                    "常见位置未找到原生浏览器；用 --list-browsers 查看候选，或显式指定 --channel/--executable-path。",
                    2,
                )
            args.executable_path = candidate.path
            logging.info(
                "BROWSER discovered=%s source=%s path=%s",
                candidate.browser,
                candidate.source,
                candidate.path,
            )
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
        if args.out:
            outputs = [str(Path(args.out).resolve())]
        elif args.to_bottom:
            outputs = [str((out_dir / f"{slug}-bottom-{args.width}.png").resolve())]
        else:
            outputs = [
                str((out_dir / f"{slug}-s{index + 1}-{args.width}.png").resolve())
                for index in range(args.screens)
            ]
        config = vars(args) | {"proxy": proxy, "outputs": outputs}
        result = run_managed(
            [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--worker"],
            config,
            args.wall_timeout_ms,
        )
        logging.info("BROWSER version=%s", result.get("browser_version", "unknown"))
        if result.get("page"):
            logging.info("PAGE metrics=%s", json.dumps(result["page"]))
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
