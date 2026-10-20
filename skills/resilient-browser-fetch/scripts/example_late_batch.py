"""示例: 一次浏览器启动、多个标签页、各自跑完挑战后统一晚接入读取。

适合"同站多页、每页都要渲染"的场景: 普通做法是每页一次启动与静默等待,
这里只付一次启动与一次静默窗口的代价。

每个标签页各自经历站点的挑战流程, 标题变成真实标题即挑战已过; 最后统一
接入, 等 DOM 渲染稳定后逐页读取落盘。每页在 batch.json 里标 state:
content(真正文) / challenge(挑战未完成) / blocked(被拒) / missing(没找到标签)。

用法: 

```bash
python example_late_batch.py \
  --url 'https://example.com/a' --url 'https://example.com/b' \
  --out-dir './late-batch' --settle-ms 5000
```

每个页面落盘为 <out-dir>/<序号>-<标题片段>.html，并写一份 batch.json 汇总。
浏览器由本脚本启动、由本脚本回收(进程树 + 临时 profile)，异常路径同样回收。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from chrome_late import (
    DEFAULT_SETTLE_MS,
    OwnedBrowserProcess,
    build_launch_args,
    classify_page_state,
    find_system_browser,
    pick_rendered_page,
    proxy_server_value,
    sweep_stale_profiles,
    wait_for_pages_ready,
    wait_for_rendered_page,
)


def slugify(title: str, fallback: str) -> str:
    """Turn a page title into a safe file name fragment."""

    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", title).strip("-")
    return (cleaned[:60] or fallback)


BLOCK_TITLE_HINTS = (
    "access denied",
    "just a moment",
    "attention required",
    "error 1020",
    "error 1015",
)


def looks_blocked(title: str, html: str) -> bool:
    """Tell a refused page apart from real content.

    A challenge page is not refused: the browser may still solve it and reload
    the real document, so it must not be reported as a finished result.
    """

    return classify_page_state(title, html) == "blocked"


def main(argv: list[str] | None = None) -> int:
    """Fetch several pages in one late-attach session and save each one."""

    parser = argparse.ArgumentParser(description="一次启动、多个标签页的晚接入批量采集")
    parser.add_argument("--url", action="append", required=True, help="目标 URL，可重复")
    parser.add_argument("--out-dir", required=True, help="落盘目录")
    parser.add_argument("--settle-ms", type=int, default=DEFAULT_SETTLE_MS, help="最小静默窗口")
    parser.add_argument(
        "--render-timeout-ms",
        type=int,
        default=15_000,
        help="接入后等待渲染完成的上限",
    )
    parser.add_argument("--timeout-ms", type=int, default=90_000, help="等待页面上限")
    parser.add_argument("--proxy", help="代理 URL，例如 http://127.0.0.1:7890 或 socks5://127.0.0.1:10808")
    parser.add_argument("--allow-direct", action="store_true", help="允许直连(未给代理时)")
    args = parser.parse_args(argv)

    urls = [item.strip() for item in args.url if item.strip()]
    if not urls:
        print("至少要一个 --url", file=sys.stderr)
        return 2

    executable = find_system_browser()
    if not executable:
        print("未找到系统 Chrome/Chromium/Edge；请安装浏览器后重试。", file=sys.stderr)
        return 2
    try:
        proxy = proxy_server_value(args.proxy)
    except Exception as exc:  # 参数错误直接报出
        print(str(exc), file=sys.stderr)
        return 2
    if not proxy and not args.allow_direct:
        print("未给 --proxy；确需直连请显式加 --allow-direct。", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(tempfile.mkdtemp(prefix="chrome-late-"))
    port = _free_port()
    browser = None
    summary: list[dict[str, Any]] = []
    try:
        stale = sweep_stale_profiles()
        if stale:
            print(f"清理遗留 profile: {len(stale)} 个")
        browser = OwnedBrowserProcess.launch(
            build_launch_args(
                executable=executable,
                port=port,
                user_data_dir=str(profile_dir),
                url=urls[0],
                proxy=proxy,
            )
            + urls[1:]
        )
        signals = wait_for_pages_ready(
            port,
            target_urls=urls,
            min_settle_ms=args.settle_ms,
            max_wait_ms=args.timeout_ms,
        )
        pages = _read_pages(port, urls, render_timeout_ms=args.render_timeout_ms)
        for index, url in enumerate(urls, start=1):
            title, html, state, waited_ms = pages.get(url, ("", "", "missing", 0))
            signal = signals.get(url)
            blocked = state == "blocked"
            challenge = state == "challenge"
            name = f"{index:02d}-{slugify(title, 'page')}.html"
            target = out_dir / name
            target.write_text(html, encoding="utf-8")
            summary.append(
                {
                    "url": url,
                    "file": str(target),
                    "title": title,
                    "bytes": len(html.encode("utf-8")),
                    "ready": bool(signal.ready) if signal else False,
                    "waited_ms": signal.waited_ms if signal else 0,
                    "state": state,
                    "blocked": blocked,
                    "challenge": challenge,
                    "render_wait_ms": waited_ms,
                }
            )
            mark = ""
            if blocked:
                mark = " [被拒绝]"
            elif challenge:
                mark = " [挑战未完成, 站点还没放行]"
            elif state == "missing":
                mark = " [没找到对应标签页]"
            print(
                f"{url} -> {name} ({len(html.encode('utf-8'))} B, "
                f"ready={summary[-1]['ready']}, state={state}){mark}"
            )
    finally:
        if browser is not None:
            browser.close()
        shutil.rmtree(profile_dir, ignore_errors=True)
    (out_dir / "batch.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


def _free_port() -> int:
    """Pick a free loopback port for the debugging endpoint."""

    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_pages(
    port: int, urls: list[str], *, render_timeout_ms: int = 15_000
) -> dict[str, tuple[str, str, str, int]]:
    """Attach once and read every tab's rendered DOM.

    Results are keyed by the requested URL, not by the URL the browser ended
    up on: a redirect must not turn a successful page into an empty file.
    """

    from resilient_fetch import load_playwright_factory

    factory = load_playwright_factory("auto")
    result: dict[str, tuple[str, str, str, int]] = {}
    with factory() as driver:
        browser = driver.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            pages = [page for context in browser.contexts for page in context.pages]
            for url in urls:
                page = pick_rendered_page(pages, url)
                if page is None:
                    result[url] = ("", "", "missing", 0)
                    continue
                render = wait_for_rendered_page(page, budget_ms=render_timeout_ms)
                result[url] = (render.title, render.html, render.state, render.waited_ms)
        finally:
            browser.close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
