#!/usr/bin/env python3
"""check_network_env.py - 盘点本机开发环境的源、镜像与代理配置，并做可选的有界探测。

用法:
    python check_network_env.py                  # 只读配置，不联网
    python check_network_env.py --probe          # 追加有界可达性探测（会出网）
    python check_network_env.py --json           # 机器可读 JSON
    python check_network_env.py --project .      # 追加项目级源配置与锁文件来源
    python check_network_env.py --only python,node

默认只读环境变量、系统代理、工具配置与登记文件；--probe 才对 GitHub、npm registry、
PyPI 索引各做一次有界请求。代理入口本身的可达性用 probe_local_proxies.py，
浏览器制品的 revision 覆盖用 playwright install --dry-run 核验。
"""

from __future__ import annotations

import argparse
import configparser
import json
import locale
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from urllib import error as urlerror
from urllib import request as urlreq
from urllib.parse import urlsplit

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 没有 tomllib，项目级 TOML 直接标记未解析
    tomllib = None  # type: ignore[assignment]

logger = logging.getLogger("check_network_env")

SKILL_NAME = "check_network_env"
UA = "check-network-env/1.0"
DEFAULT_TIMEOUT = 8.0
DEFAULT_BUDGET = 30.0
LOCAL_TIMEOUT = 30.0
LOCKFILE_MAX_BYTES = 512 * 1024
LOCKFILE_MAX_HOSTS = 12
DEFAULT_PROXY_REGISTRY = Path.home() / ".config" / "proxy-resources.json"
PYPI_DEFAULT = "https://pypi.org/simple"
NPM_DEFAULT = "https://registry.npmjs.org"
GITHUB_GIT_URL = "https://github.com/octocat/Hello-World.git"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/octocat/Hello-World/master/README"
PROBE_PACKAGE = "is-number"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

GROUPS = ("route", "python", "node", "conda", "git", "artifacts", "projects")
LOCKFILES = (
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
)
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
PIP_ENV_VARS = (
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
    "PIP_TRUSTED_HOST",
    "PIP_PROXY",
)
UV_ENV_VARS = (
    "UV_CONFIG_FILE",
    "UV_DEFAULT_INDEX",
    "UV_INDEX",
    "UV_INDEX_URL",
    "UV_PYTHON_INSTALL_MIRROR",
)
NPM_KEYS = (
    "registry",
    "proxy",
    "https-proxy",
    "noproxy",
    "strict-ssl",
    "fetch-timeout",
    "fetch-retries",
    "userconfig",
    "globalconfig",
    "prefix",
    "cafile",
)
NPMRC_KEYS = {"registry", "proxy", "https-proxy", "noproxy", "strict-ssl"}
PIP_KEYS = {"index-url", "extra-index-url", "trusted-host", "proxy", "cert", "client-cert"}
YARN_MODERN_KEYS = ("npmRegistryServer", "httpProxy", "httpsProxy", "httpsCaFilePath")
YARN_CLASSIC_KEYS = ("registry", "proxy", "https-proxy")
CONDA_KEYS = (
    "channels",
    "default_channels",
    "custom_channels",
    "channel_alias",
    "show_channel_urls",
    "ssl_verify",
    "proxy_servers",
    "remote_read_timeout_secs",
    "remote_connect_timeout_secs",
    "remote_max_retries",
)
ARTIFACT_VARS = (
    "PLAYWRIGHT_DOWNLOAD_HOST",
    "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST",
    "PLAYWRIGHT_FIREFOX_DOWNLOAD_HOST",
    "PLAYWRIGHT_WEBKIT_DOWNLOAD_HOST",
    "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT",
)

URL_RE = re.compile(r"https?://([^/\s\"'<>]+)", re.IGNORECASE)


def first_line(text: str, limit: int = 160) -> str:
    """取非空首行并截断，用于错误摘要。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:limit]
    return ""


def decode_output(raw: bytes | None) -> str:
    """按 UTF-8 解码子进程输出，失败才回落到系统编码（中文 Windows 为 GBK）。"""
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), errors="replace")


def run_command(
    args: Sequence[str],
    timeout: float,
    extra_env: dict[str, str] | None = None,
) -> tuple[int | None, str, str]:
    """执行外部命令，返回 (退出码, stdout, stderr)；超时与缺命令不抛异常。"""
    argv = list(args)
    executable = shutil.which(argv[0]) or argv[0]
    if os.name == "nt" and Path(executable).suffix.lower() in {".bat", ".cmd"}:
        argv = ["cmd", "/c", *argv]
    env = {**os.environ, "PYTHONUTF8": "1", **(extra_env or {})}
    try:
        proc = subprocess.run(  # noqa: S603 - 参数来自本脚本常量与用户显式输入
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


def get_env(name: str) -> str | None:
    """读取环境变量，兼容大小写（Windows 不区分，POSIX 常写大写）。"""
    if name in os.environ:
        return os.environ[name]
    lower = os.getenv(name.lower())
    if lower is not None:
        return lower
    return os.getenv(name.upper())


def env_values(names: Sequence[str]) -> dict[str, str]:
    """按给定名单读取环境变量；URL 值脱敏后返回。"""
    values: dict[str, str] = {}
    for name in names:
        value = get_env(name)
        if value:
            values[name] = mask_value(value)
    return values


def mask_url(value: str) -> str:
    """隐藏 URL 里的账号口令，只保留主机与端口。"""
    return re.sub(r"(?<=//)[^/@\s]+@", "***@", value)


def mask_value(value: str) -> str:
    """对 URL 做凭据脱敏；普通文本原样返回。"""
    return mask_url(value) if "://" in value else value


def mask_proxy_server(value: str) -> str:
    """脱敏 ProxyServer 这类 `scheme=user:pass@host:port` 文本。"""
    return re.sub(r"[^=/@\s;]+(?=@)", "***", value)


def parse_json_output(text: str) -> Any:
    """解析工具输出的 JSON；允许前面有少量警告文本。"""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def read_text(path: Path) -> str | None:
    """读取 UTF-8 文本；不存在或无法解码时返回 None。"""
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def read_ini(path: Path, keys: set[str]) -> dict[str, str]:
    """读取 INI 配置中关心的键；结构异常时返回空字典。"""
    parser = configparser.RawConfigParser()
    try:
        with path.open(encoding="utf-8-sig") as handle:
            parser.read_file(handle)
    except (OSError, UnicodeDecodeError, configparser.Error):
        return {}
    values: dict[str, str] = {}
    for section in parser.sections():
        for key, value in parser.items(section):
            if key.lower() in keys and value.strip():
                values[f"{section}.{key}"] = mask_value(value.strip())
    return values


def read_npmrc(path: Path) -> dict[str, str]:
    """读取 .npmrc 的白名单键，不输出 token 与认证相关行。"""
    text = read_text(path)
    if text is None:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")) or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if key in NPMRC_KEYS and value:
            values[key] = mask_value(value)
    return values


def read_yarnrc_yml(path: Path) -> dict[str, str]:
    """读取现代 Yarn 顶层配置中的 registry/proxy 键，忽略认证字段。"""
    text = read_text(path)
    if text is None:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if key in YARN_MODERN_KEYS and value:
            values[key] = mask_value(value)
    return values


def read_yarnrc_classic(path: Path) -> dict[str, str]:
    """读取 Yarn Classic 的 registry/proxy 行。"""
    text = read_text(path)
    if text is None:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) == 2 and parts[0] in YARN_CLASSIC_KEYS:
            values[parts[0]] = mask_value(parts[1].strip().strip("'\""))
    return values


def parse_key_value_lines(text: str) -> dict[str, str]:
    """解析 `key=value` 形式的工具输出，去掉值两侧的引号。"""
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value:
            values[key] = value
    return values


def pick_prefixed(config: dict[str, str], key: str) -> str | None:
    """按 pip 的来源前缀优先级取有效值。"""
    for prefix in (":env:.", "global.", "user.", "site.", "install."):
        value = config.get(prefix + key)
        if value:
            return value
    for name, value in config.items():
        if name.endswith("." + key) and value:
            return value
    return None


def pip_config_candidates() -> list[Path]:
    """列出当前平台的 pip 配置文件候选位置。"""
    home = Path.home()
    paths: list[Path] = []
    if os.name == "nt":
        if appdata := os.getenv("APPDATA"):
            paths.append(Path(appdata) / "pip" / "pip.ini")
        if programdata := os.getenv("PROGRAMDATA"):
            paths.append(Path(programdata) / "pip" / "pip.ini")
        paths.append(home / "pip" / "pip.ini")
    else:
        paths.extend(
            (
                Path("/etc/pip.conf"),
                home / ".config" / "pip" / "pip.conf",
                home / ".pip" / "pip.conf",
            )
        )
    if venv := os.getenv("VIRTUAL_ENV"):
        paths.append(Path(venv) / ("pip.ini" if os.name == "nt" else "pip.conf"))
    seen: set[str] = set()
    return [path for path in paths if not (str(path) in seen or seen.add(str(path)))]


def pip_info(timeout: float) -> dict[str, Any]:
    """当前解释器的 pip 有效配置与来源。"""
    code, stdout, stderr = run_command(
        [sys.executable, "-m", "pip", "config", "list"],
        timeout,
        {"PIP_DISABLE_PIP_VERSION_CHECK": "1"},
    )
    info: dict[str, Any] = {
        "available": code == 0,
        "interpreter": sys.executable,
        "env": env_values(PIP_ENV_VARS),
    }
    config_files = []
    for path in pip_config_candidates():
        if path.is_file():
            keys = read_ini(path, PIP_KEYS)
            config_files.append({"path": str(path), "keys": keys})
    info["configFiles"] = config_files
    if code != 0:
        info["reason"] = f"pip 不可用（exit={code}）: {first_line(stderr)}"
        return info
    parsed = parse_key_value_lines(stdout)
    effective = {
        key: mask_value(value)
        for key, value in parsed.items()
        if key.rsplit(".", 1)[-1].lower() in PIP_KEYS
    }
    info["effective"] = effective
    info["indexUrl"] = mask_value(pick_prefixed(effective, "index-url") or PYPI_DEFAULT)
    info["extraIndexUrls"] = [
        mask_value(item)
        for item in (pick_prefixed(effective, "extra-index-url") or "").split()
        if item
    ]
    if any(key.startswith(":env:") for key in effective):
        info["source"] = "env"
    elif config_files:
        info["source"] = "config"
    else:
        info["source"] = "default"
    info["defaultIndex"] = PYPI_DEFAULT
    info["note"] = "pip 配置按解释器生效；这里只检查当前脚本使用的 Python。"
    return info


def uv_config_candidates(platform_name: str | None = None) -> list[Path]:
    """列出 uv 用户级配置文件候选位置。"""
    platform_name = platform_name or os.name
    paths: list[Path] = []
    if config_file := os.getenv("UV_CONFIG_FILE"):
        paths.append(Path(config_file))
    if platform_name == "nt":
        if appdata := os.getenv("APPDATA"):
            paths.append(Path(appdata) / "uv" / "uv.toml")
    else:
        if config_home := os.getenv("XDG_CONFIG_HOME"):
            paths.append(Path(config_home) / "uv" / "uv.toml")
        else:
            paths.append(Path.home() / ".config" / "uv" / "uv.toml")
    seen: set[str] = set()
    return [path for path in paths if not (str(path) in seen or seen.add(str(path)))]


def read_uv_config(path: Path, is_pyproject: bool) -> dict[str, Any]:
    """读取 pyproject.toml/uv.toml 中的 uv 索引配置。"""
    text = read_text(path)
    if text is None:
        return {"path": str(path), "error": "无法读取"}
    if tomllib is None:
        return {"path": str(path), "error": "需要 Python 3.11+ 的 tomllib；可改用 uv 自身帮助核对"}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return {"path": str(path), "error": f"TOML 解析失败: {error}"}
    section = data.get("tool", {}).get("uv", {}) if is_pyproject else data
    if not isinstance(section, dict):
        return {"path": str(path), "error": "uv 配置段不是对象"}
    indexes = []
    for item in section.get("index") or []:
        if isinstance(item, dict):
            indexes.append(
                {
                    "name": item.get("name"),
                    "url": mask_value(str(item.get("url"))) if item.get("url") else None,
                    "default": item.get("default"),
                }
            )
    result: dict[str, Any] = {
        "path": str(path),
        "defaultIndex": mask_value(str(section["default-index"]))
        if section.get("default-index")
        else None,
        "indexUrl": mask_value(str(section["index-url"])) if section.get("index-url") else None,
        "indexes": indexes,
    }
    if not any((result["defaultIndex"], result["indexUrl"], indexes)):
        result["configured"] = False
    return result


def uv_info(
    project_roots: Sequence[Path], platform_name: str | None = None
) -> dict[str, Any]:
    """uv 的环境变量与用户级/项目级索引；uv 不读取 pip 的配置。"""
    configs = []
    seen: set[str] = set()

    def add_config(path: Path, is_pyproject: bool, scope: str) -> None:
        key = str(path)
        if key in seen or not path.is_file():
            return
        seen.add(key)
        item = read_uv_config(path, is_pyproject)
        item["scope"] = scope
        configs.append(item)

    for path in uv_config_candidates(platform_name):
        add_config(path, False, "user")
    for root in project_roots:
        for name, is_pyproject in (("pyproject.toml", True), ("uv.toml", False)):
            add_config(root / name, is_pyproject, "project")
    return {
        "available": shutil.which("uv") is not None,
        "env": env_values(UV_ENV_VARS),
        "configFiles": configs,
        "note": "uv 不读取 pip.conf/PIP_INDEX_URL；用户级、项目级与环境变量都未配置时使用官方索引。",
    }


def section_python(project_roots: Sequence[Path], timeout: float) -> dict[str, Any]:
    """Python 侧：pip 与 uv 的源配置。"""
    return {
        "owner": "network-access",
        "pip": pip_info(timeout),
        "uv": uv_info(project_roots),
    }


def filter_npm_config(raw: Any) -> dict[str, Any]:
    """只保留 npm 网络相关键，认证 token 等字段一律不进入报告。"""
    effective: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return effective
    for key in NPM_KEYS:
        value = raw.get(key)
        if isinstance(value, str):
            effective[key] = mask_value(value)
        elif isinstance(value, (bool, int, float)):
            effective[key] = value
    return effective


def npm_info(project_roots: Sequence[Path], timeout: float) -> dict[str, Any]:
    """npm 的有效 registry/proxy 与配置文件来源。"""
    npm_path = shutil.which("npm")
    code, stdout, stderr = run_command(
        ["npm", "config", "list", "--json"],
        timeout,
        {"npm_config_update_notifier": "false", "NO_UPDATE_NOTIFIER": "1"},
    )
    effective: dict[str, Any] = {}
    reason = ""
    if code == 0 and stdout.strip():
        try:
            raw = parse_json_output(stdout)
        except json.JSONDecodeError as error:
            reason = f"npm 配置输出无法解析: {error}"
        else:
            effective = filter_npm_config(raw)
    else:
        reason = f"npm 不可用（exit={code}）: {first_line(stderr)}"

    config_files: list[dict[str, Any]] = []
    candidates: list[Path] = [root / ".npmrc" for root in project_roots]
    if isinstance(effective.get("userconfig"), str):
        candidates.append(Path(str(effective["userconfig"])))
    if isinstance(effective.get("globalconfig"), str):
        candidates.append(Path(str(effective["globalconfig"])))
    candidates.append(Path.home() / ".npmrc")
    seen: set[str] = set()
    for path in candidates:
        text_path = str(path)
        if text_path in seen or not path.is_file():
            continue
        seen.add(text_path)
        keys = read_npmrc(path)
        config_files.append({"path": text_path, "keys": keys})

    env_registry = get_env("NPM_CONFIG_REGISTRY") or get_env("npm_config_registry")
    registry = effective.get("registry") or (mask_value(env_registry) if env_registry else None)
    userconfig = str(effective.get("userconfig") or "")
    globalconfig = str(effective.get("globalconfig") or "")
    if env_registry:
        source = "env"
    elif any(
        (root / ".npmrc").is_file() and read_npmrc(root / ".npmrc").get("registry")
        for root in project_roots
    ):
        source = "project"
    elif any(item["path"] == userconfig and item["keys"].get("registry") for item in config_files):
        source = "user"
    elif any(item["path"] == globalconfig and item["keys"].get("registry") for item in config_files):
        source = "global"
    elif any(item["keys"].get("registry") for item in config_files):
        source = "config"
    else:
        source = "default"
    info: dict[str, Any] = {
        "available": npm_path is not None and code == 0,
        "path": npm_path,
        "effective": effective,
        "registry": registry or NPM_DEFAULT,
        "source": source,
        "configFiles": config_files,
        "env": env_values(
            (
                "NPM_CONFIG_REGISTRY",
                "npm_config_registry",
                "NPM_CONFIG_PROXY",
                "npm_config_proxy",
                "NPM_CONFIG_HTTPS_PROXY",
                "npm_config_https_proxy",
                "NPM_CONFIG_NOPROXY",
                "npm_config_noproxy",
            )
        ),
        "defaultRegistry": NPM_DEFAULT,
    }
    if reason:
        info["reason"] = reason
    return info


def pnpm_info() -> dict[str, Any]:
    """pnpm 的配置继承关系；不执行 pnpm，避免 corepack 首次下载。"""
    return {
        "available": shutil.which("pnpm") is not None,
        "executed": False,
        "inheritsNpm": True,
        "note": "pnpm 默认复用 npm 的 .npmrc；为避免 corepack 首次下载，本报告不执行 pnpm。项目级设置按版本文档核对。",
    }


def yarn_info(project_roots: Sequence[Path]) -> dict[str, Any]:
    """Yarn 配置：只读文件与环境变量，不执行可能触发下载的 shim。"""
    home = Path.home()
    modern_files = [*[root / ".yarnrc.yml" for root in project_roots], home / ".yarnrc.yml"]
    classic_files = [*[root / ".yarnrc" for root in project_roots], home / ".yarnrc"]
    config_files = []
    for path in modern_files:
        if path.is_file():
            scope = "user" if path == home / ".yarnrc.yml" else "project"
            config_files.append(
                {"path": str(path), "kind": "modern", "scope": scope, "keys": read_yarnrc_yml(path)}
            )
    for path in classic_files:
        if path.is_file():
            scope = "user" if path == home / ".yarnrc" else "project"
            config_files.append(
                {"path": str(path), "kind": "classic", "scope": scope, "keys": read_yarnrc_classic(path)}
            )

    env = env_values(("YARN_NPM_REGISTRY_SERVER", "YARN_HTTP_PROXY", "YARN_HTTPS_PROXY"))
    registry = env.get("YARN_NPM_REGISTRY_SERVER")
    source = "env" if registry else None
    if not registry:
        for item in config_files:
            value = item["keys"].get("npmRegistryServer") or item["keys"].get("registry")
            if value:
                registry, source = value, item["scope"]
                break
    return {
        "available": shutil.which("yarn") is not None,
        "executed": False,
        "effective": {"registry": registry} if registry else {},
        "source": source or "default",
        "configFiles": config_files,
        "env": env,
        "note": "现代 Yarn 不读 .npmrc 的 registry；Classic 会读。多份配置的合并顺序按 Yarn 版本文档核对。",
    }


def sanitize_conda_value(value: Any) -> Any:
    """递归脱敏 conda 配置中的 URL。"""
    if isinstance(value, str):
        return mask_value(value)
    if isinstance(value, list):
        return [sanitize_conda_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_conda_value(item) for key, item in value.items()}
    return value


def conda_info(timeout: float) -> dict[str, Any]:
    """conda 的有效 channels 与来源文件；只保留网络相关键。"""
    if shutil.which("conda") is None:
        return {"available": False, "reason": "PATH 上无 conda"}
    code, stdout, stderr = run_command(
        ["conda", "config", "--show", "channels", "--json"],
        timeout,
        {"CONDA_NO_PLUGINS": "true"},
    )
    channels: list[str] = []
    if code == 0 and stdout.strip():
        try:
            data = parse_json_output(stdout)
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            channels = [str(item) for item in data.get("channels") or []]
    code_sources, stdout_sources, stderr_sources = run_command(
        ["conda", "config", "--show-sources", "--json"],
        timeout,
        {"CONDA_NO_PLUGINS": "true"},
    )
    sources: list[dict[str, Any]] = []
    if code_sources == 0 and stdout_sources.strip():
        try:
            data_sources = parse_json_output(stdout_sources)
        except json.JSONDecodeError:
            data_sources = {}
        if isinstance(data_sources, dict):
            for path, item in data_sources.items():
                if path in ("cmd_line", "envvars") or not isinstance(item, dict):
                    continue
                keys = {key: sanitize_conda_value(item[key]) for key in CONDA_KEYS if key in item}
                if keys:
                    sources.append({"path": path, "keys": keys})
    info: dict[str, Any] = {
        "available": code == 0,
        "channels": channels,
        "configFiles": sources,
        "env": env_values(("CONDA_CHANNELS",)),
        "note": "channels 是名称；custom_channels 才是名称到 URL 的映射，不能按普通 URL 替换理解。",
    }
    if code != 0:
        info["reason"] = f"conda 配置读取失败（exit={code}）: {first_line(stderr)}"
    elif code_sources != 0:
        info["sourcesReason"] = f"来源读取失败（exit={code_sources}）: {first_line(stderr_sources)}"
    return info


GIT_PATTERN = r"^(http|https)\.(proxy|sslverify)$|^url\..*\.insteadof$"


def parse_git_config_output(text: str, scope: str) -> list[dict[str, str]]:
    """解析 git --show-origin --get-regexp 的输出。"""
    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        if "\t" not in line:
            continue
        origin, rest = line.split("\t", 1)
        parts = rest.split(None, 1)
        if len(parts) != 2:
            continue
        key, value = parts[0], parts[1]
        entries.append(
            {
                "scope": scope,
                "origin": origin.strip().strip('"'),
                "key": key,
                "value": mask_value(value.strip()),
            }
        )
    return entries


def git_info(project_roots: Sequence[Path], timeout: float) -> dict[str, Any]:
    """Git 的 URL 改写与代理配置；私有凭据不输出。"""
    if shutil.which("git") is None:
        return {"available": False, "reason": "PATH 上无 git"}
    entries: list[dict[str, str]] = []
    scopes = (("system", ["--system"]), ("global", ["--global"]))
    for scope, prefix in scopes:
        code, stdout, _stderr = run_command(
            ["git", *prefix, "--show-origin", "--get-regexp", GIT_PATTERN],
            timeout,
        )
        if code == 0:
            entries.extend(parse_git_config_output(stdout, scope))
    local_entries: list[dict[str, str]] = []
    for root in project_roots:
        if not (root / ".git").exists():
            continue
        code, stdout, _stderr = run_command(
            ["git", "-C", str(root), "--local", "--show-origin", "--get-regexp", GIT_PATTERN],
            timeout,
        )
        if code == 0:
            local_entries.extend(parse_git_config_output(stdout, "local"))
    entries.extend(local_entries)
    instead_of = [item for item in entries if item["key"].lower().endswith(".insteadof")]
    proxies = [
        item for item in entries if item["key"].lower() in ("http.proxy", "https.proxy")
    ]
    ssl_verify = [item for item in entries if item["key"].lower().endswith(".sslverify")]
    return {
        "available": True,
        "insteadOf": instead_of,
        "proxies": proxies,
        "sslVerify": ssl_verify,
        "note": "insteadOf 会把一个 URL 前缀改写到另一主机；换源或排障前先看这里。",
    }


def read_registry(path: Path) -> dict[str, Any]:
    """读取代理登记文件；只返回概要与制品镜像，不复制完整登记。"""
    if not path.is_file():
        return {"available": False, "reason": f"无登记文件: {path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        return {"available": False, "reason": f"登记文件无法解析: {error}"}
    if not isinstance(data, dict):
        return {"available": False, "reason": "登记文件顶层不是对象"}
    proxies = []
    raw_proxies = data.get("proxies")
    if isinstance(raw_proxies, list):
        for item in raw_proxies:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            proxies.append(
                {
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "url": mask_url(str(url)) if url else None,
                    "verified": item.get("verified"),
                }
            )
    artifacts = []
    raw_artifacts = data.get("artifact_mirrors")
    if isinstance(raw_artifacts, list):
        for item in raw_artifacts:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            artifacts.append(
                {
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "url": mask_url(str(url)) if url else None,
                    "source": item.get("source"),
                    "verified": item.get("verified"),
                    "notes": mask_value(str(item.get("notes"))) if item.get("notes") else None,
                }
            )
    return {
        "available": True,
        "path": str(path),
        "updated": data.get("updated"),
        "default": data.get("default"),
        "proxies": proxies,
        "artifactMirrors": artifacts,
    }


SYSTEM_PROXY_TIMEOUT = 3.0


def truthy(value: Any) -> bool:
    """把注册表/DWORD/scutil 的 0/1、true/false 统一成布尔值。"""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_proxy_server(value: str) -> dict[str, str]:
    """解析 Windows ProxyServer：host:port 或 http=...;https=...;socks=...。"""
    parsed: dict[str, str] = {}
    for part in (value or "").split(";"):
        item = part.strip()
        if not item:
            continue
        if "=" in item:
            scheme, address = item.split("=", 1)
            scheme = scheme.strip().lower()
            address = address.strip()
            if not address:
                continue
            if scheme.startswith("socks"):
                parsed["socks"] = address
            elif scheme in ("http", "https"):
                parsed[scheme] = address
            continue
        parsed.setdefault("http", item)
        parsed.setdefault("https", item)
    return parsed


def endpoint_url(scheme: str, address: str) -> str:
    """补全 scheme 并脱敏；输入已是 URL 时只脱敏。"""
    if "://" in address:
        return mask_url(address)
    prefix = "socks5" if scheme == "socks" else scheme
    return mask_url(f"{prefix}://{address}")


def windows_system_proxy() -> dict[str, Any]:
    """只读 HKCU Internet Settings，取得系统代理、PAC 与绕过列表。"""
    try:
        import winreg
    except ImportError:
        return {
            "available": False,
            "source": "windows-registry",
            "reason": "当前解释器没有 winreg",
        }
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            def read(name: str) -> Any:
                try:
                    return winreg.QueryValueEx(key, name)[0]
                except OSError:
                    return None

            enable = read("ProxyEnable")
            server = read("ProxyServer") or ""
            override = read("ProxyOverride") or ""
            pac = read("AutoConfigURL") or ""
            auto_detect = read("AutoDetect")
    except OSError as error:
        return {
            "available": False,
            "source": "windows-registry",
            "reason": f"读取 Internet Settings 失败: {error}",
        }

    parsed = parse_proxy_server(str(server))
    auto = truthy(auto_detect)
    enabled = truthy(enable)
    info: dict[str, Any] = {
        "available": True,
        "source": "HKCU Internet Settings",
        "enabled": enabled or bool(pac) or auto,
        "autoDetect": auto,
    }
    if enabled:
        for scheme in ("http", "https", "socks"):
            address = parsed.get(scheme)
            if address:
                info[scheme] = endpoint_url(scheme, address)
    elif server:
        info["configuredServer"] = mask_proxy_server(str(server))
    if pac:
        info["pac"] = mask_value(str(pac))
    if override:
        info["bypass"] = str(override)
    return info


def parse_scutil_proxy(text: str) -> dict[str, Any]:
    """解析 macOS `scutil --proxy` 的字典输出。"""
    values: dict[str, str] = {}
    bypass: list[str] = []
    in_exceptions = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("ExceptionsList"):
            in_exceptions = True
            continue
        if in_exceptions:
            if line.startswith("}"):
                in_exceptions = False
                continue
            match = re.match(r"^\d+\s*:\s*(.+)$", line)
            if match:
                bypass.append(match.group(1).strip())
                continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9]*)\s*:\s*(.+)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip()

    def address(prefix: str) -> str | None:
        if not truthy(values.get(f"{prefix}Enable")):
            return None
        host = values.get(f"{prefix}Proxy")
        port = values.get(f"{prefix}Port")
        if not host:
            return None
        if port and ":" not in host:
            host = f"{host}:{port}"
        return host

    info: dict[str, Any] = {
        "available": True,
        "source": "scutil --proxy",
        "enabled": False,
    }
    for scheme in ("http", "https", "socks"):
        found = address(scheme.upper())
        if found:
            info[scheme] = endpoint_url(scheme, found)
    pac = (
        values.get("ProxyAutoConfigURLString")
        if truthy(values.get("ProxyAutoConfigEnable"))
        else None
    )
    auto = truthy(values.get("ProxyAutoDiscoveryEnable"))
    if pac:
        info["pac"] = mask_value(pac)
    if auto:
        info["autoDetect"] = True
    if bypass:
        info["bypass"] = ", ".join(bypass)
    info["enabled"] = bool(info.get("http") or info.get("https") or info.get("socks") or pac or auto)
    return info


def macos_system_proxy() -> dict[str, Any]:
    """调用只读的 `scutil --proxy`；失败时返回原因而不是抛异常。"""
    code, stdout, stderr = run_command(["scutil", "--proxy"], SYSTEM_PROXY_TIMEOUT)
    if code != 0:
        return {
            "available": False,
            "source": "scutil --proxy",
            "reason": stderr.strip() or f"scutil 退出码 {code}",
        }
    return parse_scutil_proxy(stdout)


def linux_system_proxy() -> dict[str, Any]:
    """读取 GNOME/`gsettings` 的系统代理；非 GNOME 桌面明确报未知。"""
    if not shutil.which("gsettings"):
        return {
            "available": False,
            "source": "gsettings",
            "reason": "未找到 gsettings（非 GNOME 桌面或未安装）",
        }

    def get(schema: str, key: str) -> str:
        code, stdout, stderr = run_command(
            ["gsettings", "get", schema, key], SYSTEM_PROXY_TIMEOUT
        )
        if code != 0:
            logger.debug("gsettings %s %s 失败: %s", schema, key, stderr.strip())
            return ""
        return stdout.strip().strip("'\"")

    mode = get("org.gnome.system.proxy", "mode")
    if not mode:
        return {
            "available": False,
            "source": "gsettings",
            "reason": "读取 org.gnome.system.proxy 失败",
        }
    info: dict[str, Any] = {
        "available": True,
        "source": "gsettings",
        "enabled": mode in ("manual", "auto"),
        "mode": mode,
    }
    if mode == "manual":
        for scheme, schema in (
            ("http", "org.gnome.system.proxy.http"),
            ("https", "org.gnome.system.proxy.https"),
            ("socks", "org.gnome.system.proxy.socks"),
        ):
            host = get(schema, "host")
            port = get(schema, "port")
            if host:
                info[scheme] = endpoint_url(scheme, f"{host}:{port}" if port else host)
    elif mode == "auto":
        pac = get("org.gnome.system.proxy", "autoconfig-url")
        if pac:
            info["pac"] = mask_value(pac)
    bypass = get("org.gnome.system.proxy", "ignore-hosts")
    if bypass:
        info["bypass"] = bypass
    return info


def system_proxy_info() -> dict[str, Any]:
    """按平台读取系统代理设置；只读，失败返回 available=False。"""
    if os.name == "nt":
        return windows_system_proxy()
    if sys.platform == "darwin":
        return macos_system_proxy()
    return linux_system_proxy()


def section_route(registry_path: Path) -> dict[str, Any]:
    """代理环境变量、系统代理与登记摘要；入口可用性仍在 probe_local_proxies.py。"""
    registry = read_registry(registry_path)
    if registry.get("available"):
        registry["artifactCount"] = len(registry.get("artifactMirrors") or [])
        registry.pop("artifactMirrors", None)
    return {
        "env": env_values(PROXY_VARS),
        "system": system_proxy_info(),
        "registry": registry,
        "note": (
            "系统代理只说明系统设置，不证明终端或当前进程会使用它；"
            "登记是线索，不是当前可用性。源站可达性用本脚本 --probe，"
            "代理入口用 probe_local_proxies.py。"
        ),
    }


def section_artifacts(registry_path: Path) -> dict[str, Any]:
    """浏览器制品下载相关变量与已登记制品镜像。"""
    registry = read_registry(registry_path)
    mirrors = (registry.get("artifactMirrors") or []) if registry.get("available") else []
    return {
        "env": env_values(ARTIFACT_VARS),
        "artifactMirrors": mirrors,
        "note": "制品镜像是否覆盖当前 Playwright 版本，要用 install --dry-run 对齐 revision 后再判定。",
    }


def lockfile_hosts(path: Path) -> dict[str, Any]:
    """有界扫描锁文件里出现的下载主机，避免整份读取大锁文件。"""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            raw = handle.read(LOCKFILE_MAX_BYTES)
    except OSError as error:
        return {"path": str(path), "error": f"{type(error).__name__}: {error}"}
    text = raw.decode("utf-8", errors="replace")
    hosts: list[str] = []
    for match in URL_RE.finditer(text):
        host = match.group(1).split("@")[-1].lower().rstrip("),]")
        if host and host not in hosts:
            hosts.append(host)
        if len(hosts) >= LOCKFILE_MAX_HOSTS:
            break
    return {"path": str(path), "hosts": hosts, "truncated": size > LOCKFILE_MAX_BYTES}


def project_info(raw_path: str) -> dict[str, Any]:
    """单个项目的源配置、包管理器声明与锁文件下载主机。"""
    root = Path(raw_path).expanduser()
    report: dict[str, Any] = {"root": str(root)}
    if not root.is_dir():
        return {**report, "available": False, "reason": f"目录不存在: {root}"}
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            manifest = json.loads(package_json.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            report["packageJson"] = {"error": f"无法解析: {error}"}
        else:
            report["packageJson"] = {
                "name": manifest.get("name"),
                "packageManager": manifest.get("packageManager"),
            }
    report["npmrc"] = read_npmrc(root / ".npmrc") if (root / ".npmrc").is_file() else {}
    yarnrc = {}
    if (root / ".yarnrc.yml").is_file():
        yarnrc = read_yarnrc_yml(root / ".yarnrc.yml")
    elif (root / ".yarnrc").is_file():
        yarnrc = read_yarnrc_classic(root / ".yarnrc")
    report["yarnrc"] = yarnrc
    uv_configs = []
    for name, is_pyproject in (("pyproject.toml", True), ("uv.toml", False)):
        path = root / name
        if path.is_file():
            uv_configs.append(read_uv_config(path, is_pyproject))
    report["uv"] = uv_configs
    report["lockfiles"] = [
        lockfile_hosts(root / name) for name in LOCKFILES if (root / name).is_file()
    ]
    report["available"] = True
    return report


def build_opener(proxy: str | None, direct: bool) -> urlreq.OpenerDirector:
    """按显式代理/直连参数构造 opener；默认沿用进程环境。"""
    if direct:
        return urlreq.build_opener(urlreq.ProxyHandler({}))
    if proxy:
        return urlreq.build_opener(urlreq.ProxyHandler({"http": proxy, "https": proxy}))
    return urlreq.build_opener()


def classify_status(status: int) -> str:
    """把 HTTP 状态码归入可操作的类别。"""
    if status in (401, 403):
        return "auth-or-blocked"
    if status == 429:
        return "rate-limited"
    if status == 404:
        return "not-found"
    if 500 <= status < 600:
        return "server-error"
    return "http-error"


def probe_http(url: str, timeout: float, proxy: str | None, direct: bool) -> dict[str, Any]:
    """一次有界 HTTP 请求；只读少量字节，不重试。"""
    start = time.monotonic()
    request = urlreq.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with build_opener(proxy, direct).open(request, timeout=timeout) as response:
            response.read(4096)
            return {
                "ok": True,
                "status": getattr(response, "status", None),
                "finalUrl": mask_url(response.geturl()),
                "seconds": round(time.monotonic() - start, 3),
                "verdict": "ok",
                "error": None,
            }
    except urlerror.HTTPError as error:
        return {
            "ok": False,
            "status": error.code,
            "seconds": round(time.monotonic() - start, 3),
            "verdict": classify_status(error.code),
            "error": mask_url(f"HTTP {error.code}"),
        }
    except (urlerror.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        timed_out = isinstance(reason, TimeoutError) or "timed out" in str(reason).lower()
        return {
            "ok": False,
            "status": None,
            "seconds": round(time.monotonic() - start, 3),
            "verdict": "timeout" if timed_out else "unreachable",
            "error": mask_url(f"{type(reason).__name__}: {reason}"),
        }
    except ValueError as error:
        return {
            "ok": False,
            "status": None,
            "seconds": round(time.monotonic() - start, 3),
            "verdict": "invalid-request",
            "error": mask_url(f"{type(error).__name__}: {error}"),
        }


def probe_git(url: str, timeout: float, proxy: str | None, direct: bool) -> dict[str, Any]:
    """一次有界的 git ls-remote；代理走子进程环境，避免凭据出现在命令行。"""
    start = time.monotonic()
    config: list[str] = []
    extra_env: dict[str, str] = {}
    if direct:
        config = ["-c", "http.proxy=", "-c", "https.proxy="]
        extra_env = {"HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "", "NO_PROXY": "*"}
    elif proxy:
        extra_env = {"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy, "NO_PROXY": ""}
    code, stdout, stderr = run_command(
        ["git", *config, "ls-remote", "--exit-code", url, "HEAD"],
        timeout,
        extra_env,
    )
    ok = code == 0 and bool(stdout.strip())
    return {
        "ok": ok,
        "status": None,
        "seconds": round(time.monotonic() - start, 3),
        "verdict": "ok" if ok else ("timeout" if code is None else "unreachable"),
        "error": None if ok else mask_url(first_line(stderr) or f"exit={code}"),
    }


def join_url(base: str, path: str) -> str:
    """拼接 URL 路径，保留 base 的查询串之外的结构。"""
    return base.rstrip("/") + "/" + path.lstrip("/")


def http_probe_spec(target: str, url: str) -> dict[str, str]:
    """构造 HTTP 探测条目。"""
    return {"target": target, "url": url, "kind": "http"}


def build_probe_specs(report: dict[str, Any]) -> list[dict[str, str]]:
    """按报告里实际生效的源生成探测目标，避免探测未使用的生态。"""
    specs: list[dict[str, str]] = []
    git = report.get("git") or {}
    if "git" in report:
        if git.get("available"):
            specs.append({"target": "github-git", "url": GITHUB_GIT_URL, "kind": "git"})
        specs.append(http_probe_spec("github-raw", GITHUB_RAW_URL))

    node = report.get("node") or {}
    npm = node.get("npm") or {}
    if npm.get("available"):
        registry = str(npm.get("registry") or NPM_DEFAULT)
        if urlsplit(registry).scheme in ("http", "https") and "***@" not in registry:
            specs.append(http_probe_spec("npm-registry", join_url(registry, f"{PROBE_PACKAGE}/latest")))

    python = report.get("python") or {}
    pip = python.get("pip") or {}
    uv = python.get("uv") or {}
    indexes: list[tuple[str, str]] = []
    if "python" in report and pip.get("available"):
        indexes.append(("pypi-index", str(pip.get("indexUrl") or PYPI_DEFAULT)))
        for item in pip.get("extraIndexUrls") or []:
            indexes.append(("pypi-extra", str(item)))
    if "python" in report and uv.get("available"):
        if not pip.get("available"):
            indexes.append(("pypi-uv", PYPI_DEFAULT))
        for item in uv.get("configFiles") or []:
            for index in item.get("indexes") or []:
                if index.get("url"):
                    indexes.append(("pypi-uv", str(index["url"])))
            if item.get("indexUrl"):
                indexes.append(("pypi-uv", str(item["indexUrl"])))
    seen: set[str] = set()
    for target, index in indexes:
        if index in seen or "***@" in index or urlsplit(index).scheme not in ("http", "https"):
            continue
        seen.add(index)
        specs.append(http_probe_spec(target, join_url(index, f"{PROBE_PACKAGE}/")))
    if len(specs) > 6:
        specs = specs[:6]
    return specs


def run_probes(
    specs: Sequence[dict[str, str]],
    timeout: float,
    budget: float,
    proxy: str | None,
    direct: bool,
    route: str,
) -> dict[str, Any]:
    """并发执行有界探测；每个目标一次请求，失败不重试。"""
    if not specs:
        return {"ran": True, "results": [], "reason": "没有可探测的目标"}
    deadline = time.monotonic() + budget
    results: list[dict[str, Any]] = []
    logger.info("probe: %d 个目标，timeout=%ss，budget=%ss，route=%s", len(specs), timeout, budget, route)

    def execute(spec: dict[str, str]) -> dict[str, Any]:
        remaining = max(0.1, min(timeout, deadline - time.monotonic()))
        logger.info("probe start: %s %s", spec["target"], spec["url"])
        if spec["kind"] == "git":
            result = probe_git(spec["url"], remaining, proxy, direct)
        else:
            result = probe_http(spec["url"], remaining, proxy, direct)
        logger.info(
            "probe done: %s verdict=%s seconds=%s",
            spec["target"],
            result.get("verdict"),
            result.get("seconds"),
        )
        return {"target": spec["target"], "url": spec["url"], "route": route, **result}

    with ThreadPoolExecutor(max_workers=min(4, len(specs))) as pool:
        futures = [(spec, pool.submit(execute, spec)) for spec in specs]
        for spec, future in futures:
            try:
                results.append(future.result())
            except Exception as error:  # noqa: BLE001 - 单个探测失败不中断其余目标
                results.append(
                    {
                        "target": spec["target"],
                        "url": spec["url"],
                        "route": route,
                        "ok": False,
                        "status": None,
                        "seconds": None,
                        "verdict": "error",
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
    return {
        "ran": True,
        "route": route,
        "timeout": timeout,
        "budget": budget,
        "results": results,
        "reason": None if results else "没有可探测的目标",
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    """组装报告；单个生态失败只影响该组，不中断其余检查。"""
    selected = set(args.only) if args.only else (set(GROUPS) - {"projects"})
    if args.project and not args.only:
        selected.add("projects")
    elif args.project and "projects" not in selected:
        logger.warning("--project 已给出，但 --only 未包含 projects，忽略项目检查")
    project_roots = [Path(item).expanduser() for item in args.project]
    registry_path = Path(args.registry).expanduser() if args.registry else DEFAULT_PROXY_REGISTRY
    report: dict[str, Any] = {
        "tool": SKILL_NAME,
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": sys.platform,
        "mode": "probe" if args.probe else "offline",
        "notes": [
            "配置只说明本机当前设置，不证明镜像当前可用；目标包与文件仍需实测。",
            "默认不联网；--probe 对每个目标最多请求一次，不重试、不轮换出口。",
            "探测超时按单次连接/读取操作计，慢握手可能略超 --budget；结果以实际耗时为准。",
            "代理登记是线索；入口可用性用 probe_local_proxies.py，本脚本不扫描端口。",
            "GitHub 加速候选不在这里自动选择；直连失败时用 check_github_mirrors.py 核验镜像前缀。",
            "锁文件可能固定 tarball 或索引主机，换源后仍可能访问旧主机。",
        ],
    }
    if "route" in selected:
        report["route"] = section_route(registry_path)
    if "python" in selected:
        report["python"] = section_python(project_roots, LOCAL_TIMEOUT)
    if "node" in selected:
        report["node"] = {
            "owner": "network-access",
            "npm": npm_info(project_roots, LOCAL_TIMEOUT),
            "pnpm": pnpm_info(),
            "yarn": yarn_info(project_roots),
            "corepack": {"env": env_values(("COREPACK_NPM_REGISTRY",))},
        }
    if "conda" in selected:
        report["conda"] = conda_info(LOCAL_TIMEOUT)
    if "git" in selected:
        report["git"] = git_info(project_roots, LOCAL_TIMEOUT)
    if "artifacts" in selected:
        report["artifacts"] = section_artifacts(registry_path)
    if "projects" in selected:
        report["projects"] = [project_info(item) for item in args.project]

    proxy_env = [name for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY") if get_env(name)]
    system = (report.get("route") or {}).get("system") or {}
    system_route = (
        bool(system.get("enabled"))
        and any(system.get(key) for key in ("http", "https", "socks"))
        and (os.name == "nt" or sys.platform == "darwin")
    )
    route_label = "direct" if args.direct else (
        "proxy" if args.proxy else (
            "env" if proxy_env else ("system" if system_route else "default")
        )
    )
    if args.probe:
        specs = build_probe_specs(report)
        report["probe"] = run_probes(
            specs,
            args.timeout,
            args.budget,
            args.proxy,
            args.direct,
            route_label,
        )
    else:
        report["probe"] = {"ran": False, "reason": "默认不联网；需要可达性结论时加 --probe"}
    return report


def render_probe(report: dict[str, Any]) -> list[str]:
    """渲染探测结果摘要。"""
    probe = report.get("probe") or {}
    lines: list[str] = []
    if not probe.get("ran"):
        lines.append(f"[探测] 未运行（{probe.get('reason')}）")
        return lines
    results = probe.get("results") or []
    ok = sum(1 for item in results if item.get("ok"))
    lines.append(
        f"[探测] {len(results)} 项，成功 {ok} / 失败 {len(results) - ok}"
        f"，route={probe.get('route')}，timeout={probe.get('timeout')}s"
    )
    for item in results:
        mark = "ok" if item.get("ok") else item.get("verdict")
        status = f" HTTP {item['status']}" if item.get("status") else ""
        seconds = f" {item['seconds']}s" if item.get("seconds") is not None else ""
        error = f"  {item['error']}" if item.get("error") else ""
        lines.append(f"  [{mark}]{status}{seconds} {item.get('target')} {item.get('url')}{error}")
    return lines


def render_human(report: dict[str, Any]) -> str:
    """把报告渲染成便于人读的分段文本。"""
    mode = "只读配置（未出网）" if report["mode"] == "offline" else "配置 + 有界探测"
    lines = [f"网络与镜像体检 {report['generated']}  ({mode})"]

    route = report.get("route")
    if route:
        lines.append("\n[代理与登记]")
        env = route.get("env") or {}
        if env:
            lines.append("  " + "  ".join(f"{key}={value}" for key, value in env.items()))
        else:
            lines.append("  环境变量: 未设置 HTTP(S)_PROXY/ALL_PROXY/NO_PROXY")
        system = route.get("system") or {}
        if system.get("available"):
            if system.get("enabled"):
                parts = []
                for key in ("http", "https", "socks"):
                    if system.get(key):
                        parts.append(f"{key}={system[key]}")
                if system.get("pac"):
                    parts.append(f"pac={system['pac']}")
                if system.get("autoDetect"):
                    parts.append("auto-detect=on")
                lines.append("  系统代理: " + ("  ".join(parts) or "已开启（未解析到地址）"))
                if system.get("bypass"):
                    lines.append(f"    绕过: {system['bypass']}")
            else:
                detail = ""
                if system.get("configuredServer"):
                    detail = f"（已配置 {system['configuredServer']}，但未启用）"
                lines.append(f"  系统代理: 关闭{detail}")
        else:
            lines.append(f"  系统代理: 未知（{system.get('reason') or '未检测'}）")
        proxy_env = {
            key: value
            for key, value in env.items()
            if key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
        }
        if system.get("available") and system.get("enabled") and not proxy_env:
            lines.append(
                "  说明: 系统代理已开但环境变量未设；终端与多数 CLI 不会自动跟随，"
                "需显式设 HTTP(S)_PROXY 或使用 TUN。"
            )
        elif system.get("available") and not system.get("enabled") and proxy_env:
            lines.append(
                "  说明: 只有环境变量生效；新终端和 GUI 应用未设变量时仍直连。"
            )
        registry = route.get("registry") or {}
        if registry.get("available"):
            lines.append(
                f"  登记: {registry.get('path')}（updated {registry.get('updated') or '?'}"
                f"，default {registry.get('default') or '?'}，条目 {len(registry.get('proxies') or [])}）"
            )
        else:
            lines.append(f"  登记不可用: {registry.get('reason')}")

    python = report.get("python")
    if python:
        pip = python.get("pip") or {}
        lines.append(f"\n[Python] 解释器: {python.get('pip', {}).get('interpreter')}")
        if pip.get("available"):
            effective = pip.get("effective") or {}
            lines.append(
                f"  pip: index-url={pip.get('indexUrl')}"
                f"（source={pip.get('source')}，extra={len(pip.get('extraIndexUrls') or [])}）"
            )
            for key, value in effective.items():
                if key.rsplit(".", 1)[-1] not in ("index-url", "extra-index-url"):
                    lines.append(f"    {key}={value}")
            for item in pip.get("configFiles") or []:
                lines.append(f"    配置: {item['path']} {item.get('keys') or ''}")
        else:
            lines.append(f"  pip 不可用: {pip.get('reason')}")
        uv = python.get("uv") or {}
        lines.append(f"  uv: {'已安装' if uv.get('available') else '未检测到'}；{uv.get('note')}")
        if uv.get("env"):
            lines.append("    " + "  ".join(f"{key}={value}" for key, value in uv["env"].items()))
        for item in uv.get("configFiles") or []:
            label = "用户配置" if item.get("scope") == "user" else "项目配置"
            lines.append(
                f"    {label}: {item.get('path')} {item.get('indexes') or item.get('error') or ''}"
            )

    node = report.get("node")
    if node:
        npm = node.get("npm") or {}
        lines.append("\n[Node.js]")
        if npm.get("available"):
            lines.append(
                f"  npm: registry={npm.get('registry')}（source={npm.get('source')}）"
            )
            for key, value in (npm.get("effective") or {}).items():
                if key != "registry":
                    lines.append(f"    {key}={value}")
            for item in npm.get("configFiles") or []:
                if item.get("keys"):
                    lines.append(f"    配置: {item['path']} {item['keys']}")
        else:
            lines.append(f"  npm 不可用: {npm.get('reason')}")
        pnpm = node.get("pnpm") or {}
        lines.append(f"  pnpm: {'检测到' if pnpm.get('available') else '未检测到'}；{pnpm.get('note')}")
        yarn = node.get("yarn") or {}
        lines.append(
            f"  yarn: {'检测到' if yarn.get('available') else '未检测到'}"
            f"；registry={yarn.get('effective', {}).get('registry') or '未配置'}"
        )
        if node.get("corepack", {}).get("env"):
            lines.append(f"  corepack: {node['corepack']['env']}")

    conda = report.get("conda")
    if conda:
        lines.append("\n[conda]")
        if conda.get("available"):
            lines.append(f"  channels: {', '.join(conda.get('channels') or []) or '未配置'}")
            for item in conda.get("configFiles") or []:
                if item.get("keys"):
                    lines.append(f"    来源: {item['path']} {item['keys']}")
            lines.append(f"  说明: {conda.get('note')}")
        else:
            lines.append(f"  不可用: {conda.get('reason')}")

    git = report.get("git")
    if git:
        lines.append("\n[Git]")
        if git.get("available"):
            instead = git.get("insteadOf") or []
            lines.append(f"  insteadOf: {len(instead)} 条")
            for item in instead:
                lines.append(f"    {item['key']} = {item['value']} ({item['scope']}, {item['origin']})")
            proxies = git.get("proxies") or []
            lines.append(f"  代理: {', '.join(item['key'] + '=' + item['value'] for item in proxies) or '未配置'}")
            lines.append(f"  说明: {git.get('note')}")
        else:
            lines.append(f"  不可用: {git.get('reason')}")

    artifacts = report.get("artifacts")
    if artifacts:
        lines.append("\n[浏览器制品]")
        env = artifacts.get("env") or {}
        if env:
            lines.append("  " + "  ".join(f"{key}={value}" for key, value in env.items()))
        else:
            lines.append("  未配置 PLAYWRIGHT_DOWNLOAD_HOST 等制品变量")
        for item in artifacts.get("artifactMirrors") or []:
            lines.append(f"  登记镜像: {item.get('name')} {item.get('url')}（verified {item.get('verified') or '未知'}）")
        lines.append(f"  说明: {artifacts.get('note')}")

    if "projects" in report and not report["projects"]:
        lines.append("\n[项目] 未提供 --project")
    for project in report.get("projects") or []:
        lines.append(f"\n[项目 {project['root']}]")
        if not project.get("available"):
            lines.append(f"  不可用: {project.get('reason')}")
            continue
        if project.get("npmrc"):
            lines.append(f"  .npmrc: {project['npmrc']}")
        if project.get("yarnrc"):
            lines.append(f"  Yarn 配置: {project['yarnrc']}")
        for item in project.get("uv") or []:
            lines.append(f"  uv: {item.get('path')} {item.get('indexes') or item.get('error') or ''}")
        for item in project.get("lockfiles") or []:
            lines.append(
                f"  锁文件 {Path(str(item.get('path'))).name}: {', '.join(item.get('hosts') or []) or '未发现 URL'}"
                f"{'（已截断）' if item.get('truncated') else ''}"
            )
        if not any((project.get("npmrc"), project.get("yarnrc"), project.get("uv"), project.get("lockfiles"))):
            lines.append("  未发现 .npmrc/.yarnrc/pyproject.toml/uv.toml/常见锁文件")

    lines.append("")
    lines.extend(render_probe(report))
    lines.append("\n[说明]")
    for note in report.get("notes") or []:
        lines.append(f"  - {note}")
    return "\n".join(lines)


def parse_only(value: str) -> set[str]:
    """校验 --only 的分组名（逗号分隔）。"""
    names = {part.strip() for part in value.split(",") if part.strip()}
    unknown = names - set(GROUPS)
    if unknown:
        raise argparse.ArgumentTypeError(
            f"未知分组: {', '.join(sorted(unknown))}；可选 {', '.join(GROUPS)}"
        )
    if not names:
        raise argparse.ArgumentTypeError("--only 至少给一个分组")
    return names


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析命令行参数（含 --help 与基本校验）。"""
    parser = argparse.ArgumentParser(
        description="盘点本机开发环境的源、镜像、系统代理与环境变量；默认只读，--probe 才做有界探测。",
        epilog=(
            "示例:\n"
            "  python check_network_env.py\n"
            "  python check_network_env.py --json --project .\n"
            "  python check_network_env.py --probe --timeout 5\n"
            "  python check_network_env.py --only python,node"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（默认输出分段文本）")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="对 GitHub、npm registry、PyPI 索引做一次有界探测（会出网；默认不联网）",
    )
    parser.add_argument(
        "--only",
        type=parse_only,
        default=None,
        metavar="LIST",
        help=f"只跑指定分组，逗号分隔：{','.join(GROUPS)}（默认除 projects 外全部）",
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        metavar="PATH",
        help="追加项目级源配置与锁文件检查；可重复",
    )
    parser.add_argument(
        "--registry",
        default=None,
        metavar="PATH",
        help="代理登记文件；默认 ~/.config/proxy-resources.json",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="单次连接/读取操作的 socket 超时秒数（默认 8；总耗时还受 --budget 约束）",
    )
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help="探测总预算秒数（默认 30）")
    parser.add_argument(
        "--proxy",
        metavar="URL",
        help="探测时显式使用该代理（默认沿用进程环境；HTTP 探测只支持 http(s) 代理，SOCKS 仅 git 探测可用）",
    )
    parser.add_argument("--direct", action="store_true", help="探测时绕过环境代理")
    parser.add_argument("--verbose", action="store_true", help="把进度与降级细节打到 stderr")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout 必须为正数")
    if args.budget <= 0:
        parser.error("--budget 必须为正数")
    if args.proxy and args.direct:
        parser.error("--proxy 与 --direct 只能选一个")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """入口函数：返回进程退出码。"""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if (args.verbose or (args.probe and not args.json)) else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
    try:
        report = build_report(args)
    except Exception:  # noqa: BLE001 - 顶层兜底：失败要带堆栈退出，不静默
        logger.exception("网络与镜像体检失败")
        return 1
    if args.json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(render_human(report) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
