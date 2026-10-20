#!/usr/bin/env python3
"""inventory.py - 汇总本机可用资源，供安装、选型或排障前先读一次报告。

用法:
    python inventory.py                  # 人类可读报告（默认不联网）
    python inventory.py --json           # 机器可读 JSON
    python inventory.py --project .      # 追加项目级资源探测（可重复）
    python inventory.py --probe-proxy    # 追加代理活体探测（会出网）

各组实际检测逻辑属于对应 skill：Python 环境见 resilient-browser-fetch 的
check_environment.py，浏览器见 browser-automation 的 browser_discovery.py，
代理见 network-access 的 probe_local_proxies.py。本脚本只聚合，不重写它们的规则。
"""

from __future__ import annotations

import argparse
import importlib
import json
import locale
import logging
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("inventory")

SKILL_NAME = "resource-inventory"
DEFAULT_TIMEOUT = 30.0
SCAN_TIMEOUT = 120.0
PROBE_TIMEOUT = 60.0
PROJECT_TIMEOUT = 20.0
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# 运行时探测表：(报告名, 命令)。版本取命令输出的第一行，不解析具体格式。
TOOL_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("python", "--version")),
    ("python3", ("python3", "--version")),
    ("conda", ("conda", "--version")),
    ("uv", ("uv", "--version")),
    ("node", ("node", "--version")),
    ("npm", ("npm", "--version")),
    ("pnpm", ("pnpm", "--version")),
    ("yarn", ("yarn", "--version")),
    ("corepack", ("corepack", "--version")),
    ("bun", ("bun", "--version")),
    ("deno", ("deno", "--version")),
    ("pwsh", ("pwsh", "--version")),
    ("git", ("git", "--version")),
    ("go", ("go", "version")),
    ("rustc", ("rustc", "--version")),
    ("cargo", ("cargo", "--version")),
    ("ffmpeg", ("ffmpeg", "-version")),
)

# 项目级测试工具识别：package.json 依赖名 → 报告中的框架名。
TEST_DEPS: dict[str, str] = {
    "playwright": "playwright",
    "@playwright/test": "playwright",
    "vitest": "vitest",
    "jest": "jest",
    "cypress": "cypress",
    "mocha": "mocha",
    "ava": "ava",
    "pytest": "pytest",
}

# 项目级配置文件识别（相对项目根目录的 glob）。
TEST_CONFIG_GLOBS: tuple[str, ...] = (
    "playwright.config.*",
    "vitest.config.*",
    "jest.config.*",
    "cypress.config.*",
    "karma.conf.*",
    "pytest.ini",
    "tox.ini",
    "noxfile.py",
    "conftest.py",
    "pyproject.toml",
    "setup.cfg",
)

LOCKFILE_MANAGERS: dict[str, str] = {
    "pnpm-lock.yaml": "pnpm",
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "bun.lockb": "bun",
    "bun.lock": "bun",
    "poetry.lock": "poetry",
    "uv.lock": "uv",
    "Pipfile.lock": "pipenv",
    "Cargo.lock": "cargo",
}

# 当前会话语境：说明"我现在在哪个环境里"，避免把全局工具当成项目环境里的。
ENV_HINTS: tuple[str, ...] = (
    "VIRTUAL_ENV",
    "CONDA_DEFAULT_ENV",
    "CONDA_PREFIX",
    "PLAYWRIGHT_BROWSERS_PATH",
    "HTMLMINI_PYTHON",
    "HTMLMINI_ENV_SCAN",
    "UV_PYTHON",
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
    "NPM_CONFIG_REGISTRY",
)

# 代理相关环境变量：会影响子进程抓取，和登记文件分开报告。
PROXY_VARS: tuple[str, ...] = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")

# 项目内已安装证据：node_modules/.bin 下的测试与构建入口；不执行、不触发下载。
NODE_BIN_HINTS: tuple[str, ...] = (
    "playwright",
    "vitest",
    "jest",
    "cypress",
    "mocha",
    "ava",
    "tsc",
    "eslint",
    "vite",
)

# 项目内虚拟环境的解释器候选（Windows / POSIX 布局）。
VENV_PYTHON_CANDIDATES: tuple[str, ...] = (
    ".venv/Scripts/python.exe",
    ".venv/bin/python",
    "venv/Scripts/python.exe",
    "venv/bin/python",
)

# 项目虚拟环境里值得确认的包：装过就不必重复安装。
VENV_PROBE_PACKAGES: tuple[str, ...] = ("pytest", "playwright", "scrapling", "ruff", "mypy")


def mask_url(value: str) -> str:
    """隐藏 URL 里的账号口令，只保留主机与端口。"""
    return re.sub(r"(?<=//)[^/@\s]+@", "***@", value)


def get_env(name: str) -> str | None:
    """读取环境变量，兼容大小写（Windows 不区分，POSIX 常写大写）。"""
    if name in os.environ:
        return os.environ[name]
    lower = os.getenv(name.lower())
    if lower is not None:
        return lower
    upper = os.getenv(name.upper())
    return upper


def parse_only(value: str) -> set[str]:
    """校验 --only 的分组名（逗号分隔）。"""
    allowed = {"host", "runtimes", "python-envs", "browsers", "proxies", "projects"}
    names = {part.strip() for part in value.split(",") if part.strip()}
    unknown = names - allowed
    if unknown:
        raise argparse.ArgumentTypeError(f"未知分组: {', '.join(sorted(unknown))}；可选 {', '.join(sorted(allowed))}")
    if not names:
        raise argparse.ArgumentTypeError("--only 至少给一个分组")
    return names


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析命令行参数（含 --help 与基本校验）。"""
    parser = argparse.ArgumentParser(
        description="汇总本机可用资源：运行时、Python 环境与引擎层、浏览器、代理入口、项目已有工具。",
        epilog=(
            "示例:\n"
            "  python inventory.py --json --project .\n"
            "  python inventory.py --only proxies --probe-proxy\n"
            "  python inventory.py --skills-root <多个 skill 所在目录>"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（默认输出表格）")
    parser.add_argument(
        "--only",
        type=parse_only,
        default=None,
        metavar="LIST",
        help="只跑指定分组，逗号分隔：host,runtimes,python-envs,browsers,proxies,projects（默认全部）",
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        metavar="PATH",
        help="追加项目级探测；可重复。默认不探测任何项目",
    )
    parser.add_argument(
        "--skills-root",
        default=None,
        metavar="PATH",
        help="skill 所在目录（含 resilient-browser-fetch 等兄弟 skill）；默认从本脚本位置推导",
    )
    parser.add_argument(
        "--registry",
        default=None,
        metavar="PATH",
        help="代理登记文件；默认 ~/.config/proxy-resources.json（env: RESOURCE_INVENTORY_PROXY_REGISTRY）",
    )
    parser.add_argument(
        "--probe-proxy",
        action="store_true",
        help="对代理入口做活体探测并出网（默认只读登记，不联网）",
    )
    parser.add_argument("--probe-budget", type=float, default=15.0, help="代理活体探测总预算秒数（默认 15）")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单个本机命令超时秒数（默认 30）")
    parser.add_argument("--verbose", action="store_true", help="打印解析与降级细节到 stderr")
    return parser.parse_args(argv)


def decode_output(raw: bytes | None) -> str:
    """按 UTF-8 解码子进程输出，失败才回落到系统编码（中文 Windows 为 GBK）。"""
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), errors="replace")


def run_command(args: Sequence[str], timeout: float) -> tuple[int | None, str, str]:
    """执行外部命令，返回 (退出码, stdout, stderr)；超时与缺命令不抛异常。"""
    argv = list(args)
    executable = shutil.which(argv[0]) or argv[0]
    if os.name == "nt" and Path(executable).suffix.lower() in {".bat", ".cmd"}:
        argv = ["cmd", "/c", *argv]
    env = {**os.environ, "PYTHONUTF8": "1"}
    try:
        proc = subprocess.run(  # noqa: S603 - 参数为内部常量，非用户输入拼接
            argv,
            capture_output=True,
            timeout=timeout,
            env=env,
            creationflags=NO_WINDOW,
            check=False,
        )
    except FileNotFoundError:
        return None, "", f"command not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return None, "", f"timeout after {timeout:.0f}s: {' '.join(argv)}"
    except OSError as error:
        return None, "", f"{type(error).__name__}: {error}"
    return proc.returncode, decode_output(proc.stdout), decode_output(proc.stderr)


def first_line(text: str, limit: int = 120) -> str:
    """取非空首行并截断，用于版本号展示。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:limit]
    return ""


def find_skills_root(explicit: str | None) -> Path | None:
    """定位兄弟 skill 所在目录：显式参数 → 环境变量 → 从脚本位置向上推导。"""
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_root = (os.getenv("RESOURCE_INVENTORY_SKILLS") or "").strip()
    if env_root:
        candidates.append(env_root)
    for raw in candidates:
        path = Path(raw).expanduser()
        if path.is_dir():
            return path.resolve()
        logger.warning("skills-root 不是目录: %s", raw)
    here = Path(__file__).resolve()
    for parent in list(here.parents)[:4]:
        if (parent / SKILL_NAME).is_dir() and any(
            (parent / sibling).is_dir() for sibling in ("resilient-browser-fetch", "browser-automation", "network-access")
        ):
            return parent
    return None


def section_host() -> dict[str, Any]:
    """运行环境标识：谁在跑这份报告，以及当前会话在哪个环境里。"""
    environment = {}
    for name in ENV_HINTS:
        value = get_env(name)
        if value:
            environment[name] = mask_url(value) if "://" in value else value
    return {
        "available": True,
        "owner": "resource-inventory",
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "python_path": sys.executable,
        "cwd": str(Path.cwd()),
        "environment": environment,
    }


def section_runtimes(timeout: float) -> dict[str, Any]:
    """PATH 上常见运行时的版本与路径。"""
    found: list[dict[str, Any]] = []
    missing: list[str] = []
    for name, argv in TOOL_SPECS:
        located = shutil.which(argv[0])
        if not located:
            missing.append(name)
            continue
        code, stdout, stderr = run_command(argv, timeout)
        version = first_line(stdout) or first_line(stderr)
        if code != 0 and not version:
            version = f"exit={code}"
        found.append({"name": name, "path": located, "version": version, "exit": code})
    return {
        "available": True,
        "owner": "resource-inventory",
        "source": "PATH 探测（shutil.which + 各工具 --version）",
        "tools": found,
        "missing": missing,
    }


def section_python_envs(skills_root: Path | None, timeout: float) -> dict[str, Any]:
    """Python 解释器与可运行引擎层：委派 resilient-browser-fetch 的 check_environment.py。"""
    base = {"available": False, "owner": "resilient-browser-fetch"}
    if skills_root is None:
        return {**base, "reason": "未定位到 skill 目录，用 --skills-root 指定"}
    script = skills_root / "resilient-browser-fetch" / "scripts" / "check_environment.py"
    if not script.is_file():
        return {**base, "reason": f"缺少 {script}（sibling skill 可能未链接到同一目录）"}
    code, stdout, stderr = run_command(
        [sys.executable, "-X", "utf8", str(script), "--list-envs", "--json"],
        max(timeout, SCAN_TIMEOUT),
    )
    if code != 0 or not stdout.strip():
        return {**base, "reason": f"扫描失败（exit={code}）: {first_line(stderr)}"}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as error:
        return {**base, "reason": f"扫描输出无法解析: {error}"}
    environments = []
    for entry in data.get("environments", []):
        packages = {name: version for name, version in (entry.get("packages") or {}).items() if version}
        environments.append(
            {
                "path": entry.get("path"),
                "version": entry.get("version"),
                "manager": entry.get("manager"),
                "source": entry.get("source"),
                "levels": entry.get("levels") or [],
                "engines": entry.get("engines") or [],
                "packages": packages,
                "ok": entry.get("ok"),
            }
        )
    recommended = next((e["path"] for e in environments if max(e["levels"] or [0]) >= 1), None)
    return {
        **base,
        "available": True,
        "source": str(script),
        "environments": environments,
        "recommended": recommended,
    }


def section_browsers(skills_root: Path | None) -> dict[str, Any]:
    """浏览器候选：委派 browser-automation 的 browser_discovery.py（模块 API）。"""
    base = {"available": False, "owner": "browser-automation"}
    if skills_root is None:
        return {**base, "reason": "未定位到 skill 目录，用 --skills-root 指定"}
    module_dir = skills_root / "browser-automation" / "scripts"
    if not (module_dir / "browser_discovery.py").is_file():
        return {**base, "reason": f"缺少 {module_dir / 'browser_discovery.py'}（sibling skill 可能未链接到同一目录）"}
    sys.path.insert(0, str(module_dir))
    try:
        module = importlib.import_module("browser_discovery")
        candidates = [item.as_dict() for item in module.discover_browsers()]
    except Exception as error:  # noqa: BLE001 - 发现失败只降级该组，不中断其它组
        return {**base, "reason": f"{type(error).__name__}: {error}"}
    return {
        **base,
        "available": True,
        "source": str(module_dir / "browser_discovery.py"),
        "candidates": candidates,
    }


def read_proxy_registry(registry: Path) -> dict[str, Any]:
    """读取代理登记文件的结构化内容。"""
    if not registry.is_file():
        return {"available": False, "reason": f"无登记文件: {registry}"}
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"available": False, "reason": f"登记文件无法解析: {error}"}
    entries = [
        {
            "name": item.get("name"),
            "type": item.get("type"),
            "url": item.get("url"),
            "source": item.get("source"),
            "verified": item.get("verified"),
            "notes": item.get("notes"),
        }
        for item in data.get("proxies", [])
    ]
    return {
        "available": True,
        "path": str(registry),
        "updated": data.get("updated"),
        "default": data.get("default"),
        "entries": entries,
    }


def section_proxies(
    registry_path: Path,
    skills_root: Path | None,
    probe: bool,
    probe_budget: float,
) -> dict[str, Any]:
    """代理入口：环境变量、登记文件、（可选）活体探测。登记条目只说明上次核验，不等于现在可用。"""
    environment = {name: mask_url(value) for name in PROXY_VARS if (value := get_env(name))}
    report: dict[str, Any] = {
        "owner": "network-access",
        "env": environment,
        "registry": read_proxy_registry(registry_path),
    }
    if not probe:
        report["probe"] = {"ran": False, "reason": "默认不联网；需要可用性结论时加 --probe-proxy"}
        return report
    if skills_root is None:
        report["probe"] = {"ran": False, "reason": "未定位到 skill 目录，用 --skills-root 指定"}
        return report
    script = skills_root / "network-access" / "scripts" / "probe_local_proxies.py"
    if not script.is_file():
        report["probe"] = {"ran": False, "reason": f"缺少 {script}"}
        return report
    code, stdout, stderr = run_command(
        [sys.executable, "-X", "utf8", str(script), "--json", "--budget", str(probe_budget)],
        max(PROBE_TIMEOUT, probe_budget + 30.0),
    )
    if code != 0 or not stdout.strip():
        report["probe"] = {"ran": True, "ok": False, "reason": f"探测失败（exit={code}）: {first_line(stderr)}"}
        return report
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as error:
        report["probe"] = {"ran": True, "ok": False, "reason": f"探测输出无法解析: {error}"}
        return report
    report["probe"] = {
        "ran": True,
        "ok": True,
        "source": str(script),
        "target": data.get("url"),
        "direct": data.get("direct"),
        "usable": data.get("usable", []),
        "summary": data.get("summary", {}),
        "blindSpots": data.get("blindSpots", []),
    }
    return report


def probe_venv_packages(venv_python: Path, timeout: float) -> dict[str, bool] | None:
    """在项目虚拟环境里检查关键包是否已安装；只做 import 探测，不安装任何东西。"""
    program = (
        "import importlib.util, json\n"
        f"names = {list(VENV_PROBE_PACKAGES)!r}\n"
        "print(json.dumps({name: importlib.util.find_spec(name) is not None for name in names}))\n"
    )
    code, stdout, _stderr = run_command([str(venv_python), "-X", "utf8", "-c", program], timeout)
    if code != 0 or not stdout.strip():
        return None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def section_project(raw_path: str) -> dict[str, Any]:
    """项目级资源：包管理器、脚本、测试工具与已安装证据，避免重复安装与现读配置猜测。"""
    root = Path(raw_path).expanduser()
    report: dict[str, Any] = {"owner": "web-app-testing", "root": str(root)}
    if not root.is_dir():
        return {**report, "available": False, "reason": f"目录不存在: {root}"}
    lockfiles = [name for name in LOCKFILE_MANAGERS if (root / name).is_file()]
    report["lockfiles"] = lockfiles
    report["packageManager"] = next((LOCKFILE_MANAGERS[name] for name in lockfiles), None)
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            manifest = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            report["packageJson"] = {"error": f"无法解析: {error}"}
        else:
            scripts = manifest.get("scripts") or {}
            deps = {**(manifest.get("dependencies") or {}), **(manifest.get("devDependencies") or {})}
            frameworks = sorted({TEST_DEPS[name] for name in deps if name in TEST_DEPS})
            report["packageJson"] = {
                "name": manifest.get("name"),
                "packageManager": manifest.get("packageManager"),
                "scripts": sorted(scripts),
                "testFrameworks": frameworks,
            }
    configs = sorted(
        str(match.relative_to(root)) for pattern in TEST_CONFIG_GLOBS for match in root.glob(pattern)
    )
    report["configFiles"] = configs
    report["virtualenvs"] = [name for name in (".venv", "venv", ".conda") if (root / name).is_dir()]
    bins_dir = root / "node_modules" / ".bin"
    installed: dict[str, Any] = {
        "nodeModulesBins": sorted(
            name
            for name in NODE_BIN_HINTS
            if any((bins_dir / f"{name}{suffix}").exists() for suffix in ("", ".cmd", ".ps1"))
        )
    }
    venv_python = next((root / rel for rel in VENV_PYTHON_CANDIDATES if (root / rel).is_file()), None)
    if venv_python:
        installed["venvPython"] = str(venv_python)
        packages = probe_venv_packages(venv_python, PROJECT_TIMEOUT)
        if packages is not None:
            installed["pythonPackages"] = packages
    report["installed"] = installed
    report["available"] = True
    return report


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    """组装报告；单组失败只标记该组，不中断其余探测。--only 决定跑哪些组。"""
    selected = args.only or {"host", "runtimes", "python-envs", "browsers", "proxies", "projects"}
    skills_root = find_skills_root(args.skills_root)
    if skills_root is None and selected & {"python-envs", "browsers", "proxies"}:
        logger.warning("未定位到 skill 目录；Python 环境、浏览器、代理活体探测将标记为不可用")
    elif skills_root:
        logger.debug("skills root: %s", skills_root)
    if args.project and "projects" not in selected:
        logger.warning("--project 已给出，但 --only 未包含 projects，忽略项目探测")
    registry = Path(
        args.registry
        or (os.getenv("RESOURCE_INVENTORY_PROXY_REGISTRY") or "").strip()
        or (Path.home() / ".config" / "proxy-resources.json")
    ).expanduser()
    report: dict[str, Any] = {
        "tool": SKILL_NAME,
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "skillsRoot": str(skills_root) if skills_root else None,
    }
    if "host" in selected:
        report["host"] = section_host()
    if "runtimes" in selected:
        report["runtimes"] = section_runtimes(args.timeout)
    if "python-envs" in selected:
        report["pythonEnvs"] = section_python_envs(skills_root, args.timeout)
    if "browsers" in selected:
        report["browsers"] = section_browsers(skills_root)
    if "proxies" in selected:
        report["proxies"] = section_proxies(registry, skills_root, args.probe_proxy, args.probe_budget)
    if "projects" in selected:
        report["projects"] = [section_project(path) for path in args.project]
    return report


def render_human(report: dict[str, Any]) -> str:
    """把报告渲染成便于人读的表格文本；--only 未选的分组不输出。"""
    lines: list[str] = [f"本机资源体检 {report['generated']}  (skills root: {report['skillsRoot'] or '未定位'})"]

    host = report.get("host")
    if host:
        env = host.get("environment") or {}
        lines.append(f"\n[会话环境] {host['platform']}  python {host['python']}")
        if env:
            for name, value in env.items():
                lines.append(f"  {name}={value}")
        else:
            lines.append("  未检测到虚拟环境/镜像相关变量")

    runtimes = report.get("runtimes")
    if runtimes:
        lines.append(f"\n[运行时] PATH 上找到 {len(runtimes['tools'])} 个")
        for tool in runtimes["tools"]:
            lines.append(f"  {tool['name']:<9} {tool['version'][:60]:<62} {tool['path']}")
        if runtimes["missing"]:
            lines.append(f"  缺失: {', '.join(runtimes['missing'])}")

    envs = report.get("pythonEnvs")
    if envs:
        if envs["available"]:
            lines.append(f"\n[Python 环境与引擎层] {len(envs['environments'])} 个候选（owner: {envs['owner']}）")
            for entry in envs["environments"]:
                levels = "/".join(str(level) for level in entry["levels"]) or "无"
                packages = ", ".join(f"{k} {v}" for k, v in entry["packages"].items()) or "无第三方包"
                lines.append(f"  层 {levels:<8} {entry['manager'] or '?':<20} {entry['path']}")
                lines.append(f"  {'':10} {entry['engines'] and ', '.join(entry['engines']) or '无'} | {packages}")
            if envs["recommended"]:
                lines.append(f"  建议（层 >= 1）: {envs['recommended']}")
        else:
            lines.append(f"\n[Python 环境与引擎层] 不可用: {envs['reason']}")

    browsers = report.get("browsers")
    if browsers:
        if browsers["available"]:
            lines.append(f"\n[浏览器] {len(browsers['candidates'])} 个候选（owner: {browsers['owner']}）")
            for item in browsers["candidates"]:
                mark = "可用" if item.get("eligible") else "不可用"
                lines.append(f"  [{mark}] {item.get('browser'):<9} {item.get('path')}  ({item.get('source')})")
        else:
            lines.append(f"\n[浏览器] 不可用: {browsers['reason']}")

    proxies = report.get("proxies")
    if proxies:
        registry = proxies["registry"]
        lines.append(f"\n[代理] owner: {proxies['owner']}")
        env = proxies.get("env") or {}
        if env:
            for name, value in env.items():
                lines.append(f"  环境变量 {name}={value}")
        else:
            lines.append("  环境变量: 未设置 HTTP(S)_PROXY/ALL_PROXY/NO_PROXY")
        if registry.get("available"):
            lines.append(f"  登记: {registry['path']}（updated {registry.get('updated')}，默认 {registry.get('default')}）")
            for entry in registry["entries"]:
                lines.append(f"  {entry['name']}  {entry['url']}  verified {entry['verified']}")
        else:
            lines.append(f"  登记不可用: {registry['reason']}")
        probe = proxies["probe"]
        if not probe.get("ran"):
            lines.append(f"  活体探测: 未运行（{probe['reason']}）")
        elif probe.get("ok"):
            lines.append(f"  活体探测: 可用入口 {len(probe['usable'])} 个，出口 {probe.get('direct')}")
        else:
            lines.append(f"  活体探测失败: {probe.get('reason')}")

    for project in report.get("projects", []):
        if not project.get("available"):
            lines.append(f"\n[项目 {project['root']}] 不可用: {project['reason']}")
            continue
        lines.append(f"\n[项目 {project['root']}] owner: {project['owner']}")
        lines.append(f"  包管理器: {project['packageManager'] or '未从 lockfile 判定'}  锁文件: {', '.join(project['lockfiles']) or '无'}")
        manifest = project.get("packageJson") or {}
        if manifest:
            lines.append(f"  脚本: {', '.join(manifest.get('scripts') or []) or '无'}")
            lines.append(f"  测试框架: {', '.join(manifest.get('testFrameworks') or []) or '未从依赖判定'}")
        lines.append(f"  配置文件: {', '.join(project['configFiles']) or '无'}")
        installed = project.get("installed") or {}
        if installed.get("nodeModulesBins"):
            lines.append(f"  已装 node_modules 入口: {', '.join(installed['nodeModulesBins'])}")
        if installed.get("pythonPackages"):
            found = [name for name, ok in installed["pythonPackages"].items() if ok]
            lines.append(f"  项目虚拟环境已装: {', '.join(found) or '无'}")
        if project["virtualenvs"]:
            lines.append(f"  项目内虚拟环境: {', '.join(project['virtualenvs'])}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """入口函数：返回进程退出码。"""
    logging.basicConfig(
        level=logging.DEBUG if "--verbose" in (argv or sys.argv) else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
    args = parse_args(argv)
    try:
        report = build_report(args)
    except Exception:  # noqa: BLE001 - 顶层兜底：失败要带堆栈退出，不静默
        logger.exception("资源体检失败")
        return 1
    if args.json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(render_human(report) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
