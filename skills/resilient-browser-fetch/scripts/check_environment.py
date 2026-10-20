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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from resilient_fetch import (
    ENGINE_CHOICES,
    ENGINES,
    engine_availability,
    parse_proxy_endpoint,
    reset_availability_cache,
    resolve_playwright_api,
    wait_for_proxy,
)

MAX_INTERPRETER_CANDIDATES = 12
PROBE_TIMEOUT_SEC = 30


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


def playwright_cache_root() -> Path:
    """Return the Playwright/patchright browser cache root for this platform."""

    custom = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if custom:
        return Path(custom).expanduser()
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def playwright_browsers() -> list[Path]:
    """List installed full Chromium builds; headless shells cannot serve layer 1 headful."""

    root = playwright_cache_root()
    if not root.is_dir():
        return []
    # Playwright 的新旧布局并存(chrome-win64 取代了 chrome-win，mac/linux 同理)。
    layouts = (
        ("chrome-win64", "chrome.exe"),
        ("chrome-win", "chrome.exe"),
        ("chrome-mac-arm64", "Chromium.app", "Contents", "MacOS", "Chromium"),
        ("chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
        ("chrome-linux64", "chrome"),
        ("chrome-linux", "chrome"),
    )
    found: list[Path] = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir() or not entry.name.startswith("chromium-"):
            continue
        for relative in layouts:
            candidate = entry.joinpath(*relative)
            if candidate.exists():
                found.append(candidate)
                break
    return found


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
    """Describe the active interpreter and the manager (conda/venv) that owns it."""

    prefix = Path(sys.prefix)
    manager = environment_manager(prefix)
    if manager == "system":
        # 未 activate 时直接调用某个环境的解释器时, CONDA_PREFIX 为空，只能靠环境变量兜底。
        conda_prefix = os.getenv("CONDA_PREFIX")
        if conda_prefix and Path(conda_prefix).resolve() == prefix.resolve():
            manager = f"conda:{os.getenv('CONDA_DEFAULT_ENV') or prefix.name}"
        elif sys.prefix != sys.base_prefix:
            manager = "venv"
    return f"{platform.python_version()} ({manager}, {sys.executable})"


def environment_manager(prefix: Path) -> str:
    """Name what owns an environment prefix: ``conda:<env>``, ``venv``, ``venv(uv)``, ``system``.

    只看前缀目录特征，不依赖已激活的环境变量: 直接调用 ``<env>\\python.exe`` 时
    ``CONDA_PREFIX``/``VIRTUAL_ENV`` 都是空的，仅靠环境变量会把 conda 环境误报为 system。
    """

    if (prefix / "conda-meta").is_dir():
        # conda 根环境的前缀名常是版本号(miniforge/26.3.2-2)，且根下自带 envs。
        if (prefix / "envs").is_dir():
            return "conda:base"
        return f"conda:{prefix.name}"
    configuration = prefix / "pyvenv.cfg"
    if configuration.is_file():
        try:
            text = configuration.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for line in text.splitlines():
            key, separator, _ = line.partition("=")
            if separator and key.strip().lower() == "uv":
                return "venv(uv)"
        return "venv"
    return "system"


def interpreter_in(prefix: Path) -> Path | None:
    """Return the interpreter that lives in an environment prefix, if it exists."""

    for relative in (
        ("Scripts", "python.exe"),
        ("bin", "python"),
        ("python.exe",),
        ("python",),
    ):
        candidate = prefix.joinpath(*relative)
        if candidate.is_file():
            return candidate
    return None


def conda_env_prefixes() -> list[Path]:
    """List conda prefixes from environment variables, the registry file, and common roots."""

    prefixes: list[Path] = []
    for value in (os.getenv("CONDA_PREFIX"), os.getenv("CONDA_DEFAULT_ENV")):
        if value and Path(value).is_dir():
            prefixes.append(Path(value))
    conda_exe = os.getenv("CONDA_EXE")
    if conda_exe:
        # <conda root>\Scripts\conda.exe 或 <conda root>/bin/conda
        prefixes.append(Path(conda_exe).parent.parent)
    roots = [Path(value) for value in (os.getenv("CONDA_ROOT"), os.getenv("MAMBA_ROOT_PREFIX")) if value]
    registry = Path.home() / ".conda" / "environments.txt"
    if registry.is_file():
        try:
            for line in registry.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    prefixes.append(Path(line.strip()))
        except OSError:
            pass
    for root in (
        *roots,
        Path.home() / "miniforge3",
        Path.home() / "miniconda3",
        Path.home() / "anaconda3",
        Path.home() / ".conda",
    ):
        prefixes.append(root)
        envs = root / "envs"
        if envs.is_dir():
            try:
                prefixes.extend(sorted(entry for entry in envs.iterdir() if entry.is_dir()))
            except OSError:
                pass
    return prefixes


def virtualenv_prefixes() -> list[Path]:
    """List venv/virtualenv/uv-managed prefixes from common locations."""

    prefixes: list[Path] = [Path.cwd() / ".venv"]
    for value in (os.getenv("VIRTUAL_ENV"), os.getenv("WORKON_HOME")):
        if value:
            prefixes.append(Path(value))
    roots = [
        Path.home() / ".virtualenvs",
        Path.home() / ".local" / "share" / "virtualenvs",
        Path.home() / ".venv",
        Path.home() / ".local" / "share" / "uv" / "python",
        Path.home() / ".local" / "share" / "uv" / "venvs",
        Path.home() / "AppData" / "Roaming" / "uv" / "python",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        if root.name in {"virtualenvs", "venvs", "python"}:
            try:
                prefixes.extend(sorted(entry for entry in root.iterdir() if entry.is_dir()))
                continue
            except OSError:
                pass
        prefixes.append(root)
    return prefixes


def launcher_pythons() -> list[Path]:
    """Ask the Windows ``py`` launcher for every registered interpreter."""

    if os.name != "nt":
        return []
    launcher = shutil.which("py")
    if not launcher:
        return []
    try:
        process = subprocess.run(
            [launcher, "-0p"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    found: list[Path] = []
    for line in (process.stdout or "").splitlines():
        value = line.strip()
        if value.lower().endswith("python.exe") and Path(value).is_file():
            found.append(Path(value))
    return found


def interpreter_candidates() -> list[dict[str, str]]:
    """Collect interpreters that could own the dependency layers, without activating anything."""

    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(path: Path | None, source: str) -> None:
        if path is None or not path.is_file():
            return
        try:
            key = str(path.resolve())
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        found.append({"path": key, "source": source})

    add(Path(sys.executable), "current")
    for variable, source in (("VIRTUAL_ENV", "env:VIRTUAL_ENV"), ("CONDA_PREFIX", "env:CONDA_PREFIX")):
        value = os.getenv(variable)
        if value:
            add(interpreter_in(Path(value)), source)
    for name in ("python", "python3", *(f"python3.{minor}" for minor in range(10, 15))):
        located = shutil.which(name)
        if located:
            add(Path(located), "PATH")
    for path in launcher_pythons():
        add(path, "py -0p")
    for prefix in conda_env_prefixes():
        add(interpreter_in(prefix), "conda-envs")
    for prefix in virtualenv_prefixes():
        add(interpreter_in(prefix), "venv-dirs")
    return found[:MAX_INTERPRETER_CANDIDATES]


PROBE_PROGRAM = "\n".join(
    (
        "import importlib.metadata as md, json, sys",
        "payload = {'executable': sys.executable, 'prefix': sys.prefix,",
        "           'version': '%d.%d.%d' % sys.version_info[:3]}",
        "packages = {}",
        "for name in ('playwright', 'patchright', 'scrapling', 'cloakbrowser', 'curl_cffi'):",
        "    try:",
        "        packages[name] = md.version(name)",
        "    except Exception:",
        "        packages[name] = None",
        "payload['packages'] = packages",
        "try:",
        "    sys.path.insert(0, sys.argv[1])",
        "    import resilient_fetch as rf",
        "    payload['engines'] = [name for name in rf.available_engines()]",
        "except Exception as exc:",
        "    payload['engines'] = []",
        "    payload['probe_error'] = f'{type(exc).__name__}: {exc}'",
        "print(json.dumps(payload, ensure_ascii=False))",
    )
)


def probe_interpreter(path: str, scripts_dir: Path) -> dict[str, Any]:
    """Ask one interpreter which layers it can run; never raises."""

    try:
        process = subprocess.run(
            [path, "-X", "utf8", "-c", PROBE_PROGRAM, str(scripts_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"path": path, "ok": False, "detail": f"无法运行: {exc}"}
    if process.returncode != 0:
        detail = (process.stderr or "").strip().splitlines()
        return {
            "path": path,
            "ok": False,
            "detail": f"退出码 {process.returncode}: {detail[-1][:200] if detail else '无输出'}",
        }
    lines = [line for line in (process.stdout or "").splitlines() if line.strip()]
    if not lines:
        return {"path": path, "ok": False, "detail": "无输出"}
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"path": path, "ok": False, "detail": "输出不是 JSON"}
    payload["path"] = path
    payload["ok"] = True
    return payload


def engine_levels(engines: list[str]) -> list[int]:
    """Map engine names reported by an interpreter to their layer levels."""

    return sorted({ENGINES[name].level for name in engines if name in ENGINES})


def scan_environments(required: tuple[str, ...], scripts_dir: Path) -> list[dict[str, Any]]:
    """Probe every candidate interpreter and rank it by the layers it can actually run."""

    candidates = interpreter_candidates()
    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
        probed = list(pool.map(lambda item: probe_interpreter(item["path"], scripts_dir), candidates))
    for entry, candidate in zip(probed, candidates, strict=True):
        entry["source"] = candidate["source"]
        prefix = Path(str(entry.get("prefix") or "")) if entry.get("prefix") else Path(candidate["path"]).parent
        entry["manager"] = environment_manager(prefix)
        engines = [str(name) for name in entry.get("engines", [])]
        entry["engines"] = engines
        entry["levels"] = engine_levels(engines)
        entry["satisfies"] = [name for name in required if name not in engines]
    probed.sort(
        key=lambda entry: (
            bool(entry["satisfies"]),
            -max(entry["levels"] or [0]),
            -len(entry["engines"]),
            str(entry["path"]),
        )
    )
    return probed


def format_environment_report(
    environments: list[dict[str, Any]], required: tuple[str, ...]
) -> list[str]:
    """Render the interpreter scan as human-readable lines, including ready-to-run commands."""

    lines = [f"解释器扫描: {len(environments)} 个候选(按可运行层数排序)"]
    for entry in environments:
        if not entry["ok"]:
            lines.append(f"[--] 无法探测  {entry['path']}  ({entry.get('detail', '')})")
            continue
        state = "OK" if not entry["satisfies"] else "WARN"
        mark = f"[{state}]" if required else "[  ]"
        levels = "/".join(str(level) for level in entry["levels"]) or "无"
        lines.append(f"{mark} {entry['manager']:<18} {entry['path']}  (来源: {entry['source']})")
        lines.append(f"     Python {entry.get('version', '?')}  层 {levels}  引擎: {', '.join(entry['engines']) or '无'}")
        installed = [
            f"{name} {version}" for name, version in entry.get("packages", {}).items() if version
        ]
        if installed:
            lines.append(f"     包: {', '.join(installed)}")
        missing = [name for name in entry["satisfies"]]
        if missing:
            lines.append(f"     缺: {', '.join(missing)}")
        if entry.get("probe_error"):
            lines.append(f"     探测异常: {entry['probe_error']}")
    usable = [entry for entry in environments if entry["ok"] and not entry["satisfies"]]
    if not required:
        return lines
    if usable:
        best = usable[0]
        lines.append(f"建议解释器(满足 {', '.join(required)}): {best['path']}")
        lines.append(f"   直接调用: & \"{best['path']}\" -X utf8 <scripts>/resilient_fetch.py --url <URL>")
        if best["manager"].startswith("conda:"):
            name = best["manager"].split(":", 1)[1]
            lines.append(
                "   conda:    conda run -n "
                f"{name} --no-capture-output python -X utf8 <scripts>/resilient_fetch.py --url <URL>"
            )
    else:
        lines.append(
            f"没有解释器同时具备 {', '.join(required)}；按缺失项安装后重跑本命令。"
        )
    return lines


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
    parser.add_argument(
        "--require-nodriver",
        action="store_true",
        help="把 nodriver(显式/有头后备的直接 CDP 引擎)标为必需；需要系统 Chrome。",
    )
    parser.add_argument(
        "--require-stealth",
        action="store_true",
        help="把 scrapling[fetchers](层 2 及挑战求解)标为必需。",
    )
    parser.add_argument(
        "--require-playwright",
        action="store_true",
        help="把 playwright/patchright 与浏览器二进制(层 1)标为必需。",
    )
    parser.add_argument("--headful", action="store_true")
    parser.add_argument(
        "--list-envs",
        action="store_true",
        help="扫描本机候选解释器(conda/venv/uv/PATH/py 启动器)，报告各自可运行的引擎层，并给出建议命令。",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    required_engines = tuple(
        name
        for name, enabled in (
            ("playwright", args.require_playwright),
            ("scrapling", args.require_stealth),
            ("cloak-cdp", args.require_cloak),
            ("nodriver", args.require_nodriver),
        )
        if enabled
    )

    if args.list_envs:
        environments = scan_environments(required_engines, Path(__file__).resolve().parent)
        satisfied = [entry for entry in environments if entry["ok"] and not entry["satisfies"]]
        if args.json:
            print(
                json.dumps(
                    {
                        "required": list(required_engines),
                        "environments": environments,
                        "recommended": satisfied[0]["path"] if satisfied else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            for line in format_environment_report(environments, required_engines):
                print(line)
        return 1 if required_engines and not satisfied else 0

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

    curl_cffi = package_version("curl_cffi")
    add_check(
        checks,
        "curl_cffi",
        curl_cffi is not None,
        curl_cffi or "未安装；层 0 仍可用，但推荐安装以启用 socks 代理与 --impersonate 的 TLS/HTTP2 伪装",
        required=False,
    )

    playwright_apis = {
        name: package_version(name)
        for name in ("patchright", "playwright")
        if package_version(name) is not None
    }
    resolved_api = resolve_playwright_api()
    if playwright_apis:
        playwright_detail = ", ".join(
            f"{name} {version}" for name, version in playwright_apis.items()
        )
        playwright_detail += f"；auto 解析为 {resolved_api}"
    else:
        playwright_detail = "未安装(层 1 不可用)"
    add_check(
        checks,
        "playwright",
        bool(playwright_apis),
        playwright_detail,
        required=args.require_playwright,
    )
    browsers = playwright_browsers()
    add_check(
        checks,
        "playwright-browsers",
        bool(browsers),
        str(browsers[0]) if browsers else "未发现完整 Chromium；层 1 需 `playwright install chromium`",
        required=args.require_playwright,
    )

    scrapling = package_version("scrapling")
    add_check(checks, "scrapling", scrapling is not None, scrapling or "未安装", args.require_stealth)
    try:
        from scrapling.fetchers import StealthyFetcher  # noqa: F401

        fetcher_ok, fetcher_detail = True, "StealthyFetcher 可导入"
    except Exception as exc:
        fetcher_ok, fetcher_detail = False, str(exc)
    add_check(checks, "scrapling-fetchers", fetcher_ok, fetcher_detail, args.require_stealth)
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
        str(browsers[0]) if browsers else "未发现；--real-chrome 与 nodriver 需要",
        required=False,
    )
    nodriver = package_version("nodriver")
    add_check(
        checks,
        "nodriver",
        nodriver is not None,
        nodriver or "未安装(可选，AGPL-3.0；直接 CDP，不下载浏览器)",
        required=args.require_nodriver,
    )
    if nodriver:
        add_check(
            checks,
            "nodriver-chrome",
            bool(browsers),
            str(browsers[0]) if browsers else "未发现系统 Chrome；nodriver 无法启动",
            required=args.require_nodriver,
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

    reset_availability_cache()
    engines = [
        {
            "name": name,
            "level": ENGINES[name].level,
            "order": ENGINES[name].order or ENGINES[name].level * 10,
            "in_auto": ENGINES[name].in_auto,
            "auto_requires_headful": ENGINES[name].auto_requires_headful,
            "ok": engine_availability(name).ok,
            "detail": engine_availability(name).reason(),
        }
        for name in ENGINE_CHOICES
        if name != "auto"
    ]
    usable = [item["name"] for item in engines if item["ok"] and item["in_auto"]]
    headful_only = [
        item["name"]
        for item in engines
        if item["ok"] and item["in_auto"] and item["auto_requires_headful"]
    ]

    payload = {
        "platform": platform.platform(),
        "engines": engines,
        "usable_engines": usable,
        "headful_only_engines": headful_only,
        "checks": checks,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"平台: {payload['platform']}")
        for check in checks:
            state = "OK" if check["ok"] else ("FAIL" if check["required"] else "WARN")
            print(f"[{state}] {check['name']}: {check['detail']}")
        engine_line = "可用引擎(auto 顺序): " + (
            ", ".join(usable) if usable else "无(缺件明细见上)"
        )
        if headful_only:
            engine_line += "；仅有头加入 auto: " + ", ".join(headful_only)
        print(engine_line)

    return 1 if any(check["required"] and not check["ok"] for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
