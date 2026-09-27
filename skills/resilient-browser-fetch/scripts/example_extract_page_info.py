"""Example: fetch a protected page and return compact structured information."""

from __future__ import annotations

import argparse
import json
import logging
import os
from html.parser import HTMLParser

from resilient_fetch import (
    DEFAULT_TIMEOUT_MS,
    FetchFailed,
    FetchOptions,
    ProxyUnavailableError,
    extract_title,
    fetch_page,
    setup_logging,
)


class VisibleTextParser(HTMLParser):
    """Collect visible text while excluding script and style containers."""

    def __init__(self) -> None:
        """Initialize parser state for nested ignored elements."""

        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Enter containers whose data should not appear in the text preview."""

        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Leave an ignored container while tolerating malformed nesting."""

        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        """Normalize and collect visible character data."""

        text = " ".join(data.split())
        if text and not self._ignored_depth:
            self.parts.append(text)


def extract_visible_text(page_html: str) -> str:
    """Extract normalized visible text from rendered HTML."""

    parser = VisibleTextParser()
    parser.feed(page_html)
    return " ".join(parser.parts)


def fetch_page_info(
    url: str,
    *,
    proxy: str | None = None,
    discover_proxy: bool = False,
    engine: str = "auto",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    wall_timeout_ms: int | None = None,
    preview_chars: int = 500,
) -> dict[str, object]:
    """Fetch one page without output files and return fields suitable for JSON."""

    outcome = fetch_page(
        FetchOptions(
            url=url,
            proxy=proxy,
            discover_proxy=discover_proxy,
            engine=engine,
            timeout_ms=timeout_ms,
            wall_timeout_ms=wall_timeout_ms,
        )
    )
    result = outcome.result
    visible_text = extract_visible_text(result.html)
    return {
        "url": url,
        "final_url": result.final_url,
        "status": result.status,
        "title": extract_title(result.html),
        "engine": result.engine,
        "bytes_utf8": len(result.html.encode("utf-8", errors="replace")),
        "text_preview": visible_text[:preview_chars],
    }


def main(argv: list[str] | None = None) -> int:
    """Print page information as JSON while keeping operational logs on stderr."""

    parser = argparse.ArgumentParser(description="获取网页并打印标题等结构化信息。")
    parser.add_argument("url")
    parser.add_argument("--proxy", default=os.getenv("SCRAPE_PROXY"))
    parser.add_argument("--discover-proxy", action="store_true")
    parser.add_argument("--engine", choices=("auto", "scrapling", "cloak-cdp"), default="auto")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--wall-timeout-ms", type=int)
    parser.add_argument("--preview-chars", type=int, default=500)
    args = parser.parse_args(argv)
    setup_logging(False)
    try:
        info = fetch_page_info(
            args.url,
            proxy=args.proxy,
            discover_proxy=args.discover_proxy,
            engine=args.engine,
            timeout_ms=args.timeout_ms,
            wall_timeout_ms=args.wall_timeout_ms,
            preview_chars=args.preview_chars,
        )
    except ProxyUnavailableError as exc:
        logging.error("%s", exc)
        return 2
    except FetchFailed as exc:
        logging.error("%s", exc)
        return 1
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
