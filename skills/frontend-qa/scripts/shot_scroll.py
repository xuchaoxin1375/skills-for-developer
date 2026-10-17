"""多屏滚动截图：一次 Playwright 会话连拍 N 个视口。

shot-quick.ps1 只拍首屏；需要第二屏及以下时用本脚本，避免为每屏各起一次浏览器。
代理契约与 resilient_fetch.py 一致：--proxy / SCRAPE_PROXY 优先，
--discover-proxy 时再读机外登记（~/.config/proxy-resources.json）并做有界 TCP 探测；
无代理参数且未要求发现时即直连，只有 --discover-proxy 要求代理却无可用候选时
才报错退出（exit 2），不猜端口、不静默降级。

示例：
  python -X utf8 shot_scroll.py --url 'https://example.com/page' --screens 2
  python -X utf8 shot_scroll.py --url 'https://example.com/page' --screens 2 --discover-proxy
  python -X utf8 shot_scroll.py --url 'https://example.com/page' --proxy 'http://127.0.0.1:<port>'
  python -X utf8 shot_scroll.py --url 'https://example.com/page' --screens 2 --channel msedge

本机装有 Chrome/Edge 时加 --channel 直用本机浏览器，免下载；--channel 与
--executable-path 互斥，后者指向任意位置的浏览器可执行文件。

成功打印 SHOT 行并 exit 0；失败 exit 1；代理不可用 exit 2。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

PROXY_REGISTRY_PATH = Path.home() / ".config" / "proxy-resources.json"
WIDTHS = (390, 1440)


class ProxyUnavailableError(RuntimeError):
    """要求代理但无可用候选。"""


def slugify(url: str) -> str:
    """由 URL 派生文件名别名（与 shot-quick.ps1 同规则）。"""
    slug = re.sub(r"^https?://", "", url.strip().lower())
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug[:60] or "page"


def registry_default_proxy(registry_path: Path | None = None) -> str | None:
    """读机外登记，默认条目优先；文件缺失/损坏/无条目返回 None。"""
    try:
        data = json.loads(Path(registry_path or PROXY_REGISTRY_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("proxies"), list):
        return None
    proxies = [e for e in data["proxies"] if isinstance(e, dict) and e.get("url")]
    if not proxies:
        return None
    default = data.get("default")
    for entry in proxies:
        if entry.get("name") == default:
            return entry["url"]
    return proxies[0]["url"]


def tcp_reachable(proxy_url: str, timeout: float = 1.0) -> bool:
    """对代理端点做一次有界 TCP 探测（只判监听，不验证协议与出口）。"""
    try:
        parsed = urlparse(proxy_url)
        host, port = parsed.hostname, parsed.port
    except ValueError:
        return False
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def resolve_proxy(
    explicit: str | None, *, discover: bool
) -> tuple[str | None, str]:
    """按 显式参数 → SCRAPE_PROXY →（discover 时）登记 → 直连 解析代理。"""
    if explicit:
        return explicit, "explicit"
    env = os.getenv("SCRAPE_PROXY")
    if env:
        return env, "env:SCRAPE_PROXY"
    if not discover:
        return None, "direct"
    candidate = registry_default_proxy()
    if candidate and tcp_reachable(candidate):
        return candidate, "registry"
    raise ProxyUnavailableError(
        "要求代理但未找到可用候选（登记缺失或候选不可达）。"
        "请用 --proxy 指定代理 URL，或设置 SCRAPE_PROXY，或先登记可用代理后重试。"
    )


def capture(
    url: str,
    *,
    out_dir: Path,
    width: int,
    height: int,
    screens: int,
    proxy: str | None,
    timeout_ms: int,
    settle_ms: int,
    step_wait_ms: int,
    channel: str | None = None,
    executable_path: str | None = None,
) -> list[Path]:
    """一次会话连拍：首屏 + 每次下滚一视口。返回截图路径列表。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("缺少 playwright：请先安装 Playwright Python 包与浏览器。") from exc
    slug = slugify(url)
    out_dir.mkdir(parents=True, exist_ok=True)
    shots: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy={"server": proxy} if proxy else None,
            channel=channel,
            executable_path=executable_path,
        )
        try:
            page = browser.new_context(
                viewport={"width": width, "height": height}
            ).new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(15000, timeout_ms))
            except Exception:
                pass  # 重 JS 页网络难静默，固定等待后继续，不阻塞后续屏
            page.wait_for_timeout(settle_ms)
            for i in range(1, screens + 1):
                shot = out_dir / f"{slug}-s{i}-{width}.png"
                page.screenshot(path=str(shot))
                shots.append(shot)
                if i < screens:
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(step_wait_ms)
        finally:
            browser.close()
    return shots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一次 Playwright 会话连拍 N 个视口（首屏+滚动屏）。")
    parser.add_argument("--url", required=True, help="目标 HTTP(S) URL。")
    parser.add_argument("--out-dir", default="", help="输出目录，缺省为系统临时目录下 shot-scroll/。")
    parser.add_argument("--width", type=int, choices=list(WIDTHS), default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--screens", type=int, default=2, help="连拍屏数，首屏为 s1。")
    parser.add_argument("--proxy", default=os.getenv("SCRAPE_PROXY"), help="代理 URL；也可设置 SCRAPE_PROXY。")
    parser.add_argument("--discover-proxy", action="store_true", help="未指定代理时读本机登记并探测可用候选。")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--settle-ms", type=int, default=4000, help="首屏渲染固定等待。")
    parser.add_argument("--step-wait-ms", type=int, default=1500, help="每次滚动后固定等待。")
    local_browser = parser.add_mutually_exclusive_group()
    local_browser.add_argument(
        "--channel",
        choices=["chrome", "msedge"],
        default=None,
        help="直用本机安装的 Chrome/Edge，免下载浏览器。",
    )
    local_browser.add_argument(
        "--executable-path",
        default=None,
        help="直用指定路径的浏览器可执行文件（适用于上述通道之外的位置）。",
    )
    args = parser.parse_args(argv)

    if not re.match(r"^https?://", args.url):
        print(f"Url 须为 http(s) 地址：{args.url}", file=sys.stderr)
        return 1
    if args.screens < 1:
        print("--screens 须 >= 1", file=sys.stderr)
        return 1
    try:
        proxy, source = resolve_proxy(args.proxy or None, discover=args.discover_proxy)
    except ProxyUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.gettempdir()) / "opencode" / "shot-scroll"
    print(f"PROXY source={source}")
    try:
        shots = capture(
            args.url,
            out_dir=out_dir,
            width=args.width,
            height=args.height,
            screens=args.screens,
            proxy=proxy,
            timeout_ms=args.timeout_ms,
            settle_ms=args.settle_ms,
            step_wait_ms=args.step_wait_ms,
            channel=args.channel,
            executable_path=args.executable_path,
        )
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    for shot in shots:
        print(f"SHOT {shot} ({round(shot.stat().st_size / 1024)}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
