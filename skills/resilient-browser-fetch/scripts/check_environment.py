"""Perform read-only dependency, browser, proxy, and platform diagnostics."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from resilient_fetch import parse_proxy_endpoint, wait_for_proxy


def add_check(
    checks: list[dict[str, Any]], name: str, ok: bool, detail: str, required: bool = True
) -> None:
    """Append one normalized diagnostic record to the output collection."""

    checks.append({"name": name, "ok": ok, "required": required, "detail": detail})


def package_version(name: str) -> str | None:
    """Return an installed distribution version without importing the package."""

    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def chrome_candidates() -> list[Path]:
    """Return existing Chrome or Chromium executables from common locations."""

    candidates: list[Path] = []
    for executable in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        found = shutil.which(executable)
        if found:
            candidates.append(Path(found))
    if os.name == "nt":
        for root in (
            os.getenv("PROGRAMFILES"),
            os.getenv("PROGRAMFILES(X86)"),
            os.getenv("LOCALAPPDATA"),
        ):
            if root:
                candidates.append(Path(root) / "Google/Chrome/Application/chrome.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    return [path for path in candidates if path.exists()]


def executable_version(name: str) -> str | None:
    """Return a command's version output, executable path, or ``None`` if missing."""

    executable = shutil.which(name)
    if not executable:
        return None
    try:
        process = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except OSError:
        return executable
    return process.stdout.strip() or process.stderr.strip() or executable


def environment_executable(name: str) -> Path | None:
    """Find a console script beside the Python interpreter running this check."""

    suffix = ".exe" if os.name == "nt" else ""
    candidate = Path(sys.executable).parent / f"{name}{suffix}"
    return candidate if candidate.exists() else None


def python_environment_detail() -> str:
    """Describe the active interpreter and whether Conda or venv owns it."""

    prefix = Path(sys.prefix).resolve()
    conda_prefix = os.getenv("CONDA_PREFIX")
    if conda_prefix and prefix == Path(conda_prefix).resolve():
        manager = f"conda:{os.getenv('CONDA_DEFAULT_ENV') or prefix.name}"
    elif sys.prefix != sys.base_prefix:
        manager = "venv"
    else:
        manager = "system"
    return f"{platform.python_version()} ({manager}, {sys.executable})"


def configure_utf8_output() -> None:
    """Use UTF-8 for redirected diagnostics on platforms with legacy code pages."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    """Run environment checks and return nonzero only for required failures."""

    configure_utf8_output()
    parser = argparse.ArgumentParser(description="检查 resilient-browser-fetch 的只读运行环境。")
    parser.add_argument("--proxy", default=os.getenv("SCRAPE_PROXY"))
    parser.add_argument("--require-cloak", action="store_true")
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    add_check(checks, "python", sys.version_info >= (3, 10), python_environment_detail())
    uv_version = executable_version("uv")
    add_check(
        checks,
        "uv",
        uv_version is not None,
        uv_version or "未安装，将回退到 python -m pip",
        required=False,
    )

    scrapling = package_version("scrapling")
    add_check(checks, "scrapling", scrapling is not None, scrapling or "未安装")
    try:
        from scrapling.fetchers import StealthyFetcher  # noqa: F401

        fetcher_ok, fetcher_detail = True, "StealthyFetcher 可导入"
    except Exception as exc:
        fetcher_ok, fetcher_detail = False, str(exc)
    add_check(checks, "scrapling-fetchers", fetcher_ok, fetcher_detail)
    cli = environment_executable("scrapling")
    path_cli = shutil.which("scrapling")
    if cli:
        cli_detail = f"当前环境: {cli}"
    elif path_cli:
        cli_detail = f"当前环境缺少；PATH 指向其他环境: {path_cli}"
    else:
        cli_detail = "当前环境和 PATH 均未找到"
    add_check(checks, "scrapling-cli", cli is not None, cli_detail, required=False)

    cloak = package_version("cloakbrowser")
    add_check(
        checks, "cloakbrowser", cloak is not None, cloak or "未安装", required=args.require_cloak
    )
    if cloak:
        try:
            from cloakbrowser import binary_info

            info = binary_info()
            add_check(
                checks,
                "cloak-binary",
                bool(info.get("installed")),
                json.dumps(
                    {key: info.get(key) for key in ("version", "tier", "platform", "binary_path")},
                    ensure_ascii=False,
                ),
                required=args.require_cloak,
            )
        except Exception as exc:
            add_check(checks, "cloak-binary", False, str(exc), required=args.require_cloak)

    browsers = chrome_candidates()
    add_check(
        checks,
        "system-chrome",
        bool(browsers),
        str(browsers[0]) if browsers else "未发现；仅 --real-chrome 需要",
        required=False,
    )

    if args.proxy:
        try:
            host, port = parse_proxy_endpoint(args.proxy)
            reachable = wait_for_proxy(args.proxy, attempts=1)
            add_check(checks, "proxy-port", reachable, f"{host}:{port}")
        except Exception as exc:
            add_check(checks, "proxy-port", False, str(exc))

    if args.headful and sys.platform.startswith("linux"):
        display = os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")
        add_check(
            checks, "linux-display", bool(display), display or "未设置 DISPLAY/WAYLAND_DISPLAY"
        )

    payload = {"platform": platform.platform(), "checks": checks}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"平台: {payload['platform']}")
        for check in checks:
            state = "OK" if check["ok"] else ("FAIL" if check["required"] else "WARN")
            print(f"[{state}] {check['name']}: {check['detail']}")

    return 1 if any(check["required"] and not check["ok"] for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
