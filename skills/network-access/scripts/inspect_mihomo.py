#!/usr/bin/env python3
"""检查本机 mihomo / Clash 系客户端的配置、节点与分组，输出概述报告（默认只读）。

做什么
    1. 定位客户端：先按内核进程的 `-d`/`--directory` 与 `-f`/`--config`（Windows 查 CIM
       命令行，Linux 读 /proc，macOS 用 ps），再退回候选目录扫描，最后才要 `--config`。
       从运行时配置里取 external-controller 与 secret。
    2. 只读 GET Clash 兼容 API：/version、/configs、/proxies、/providers/proxies、
       /rules、/connections。
    3. 汇总为报告：可用配置、运行时状态、节点池、分组与当前选中、订阅状态、规则面、
       以及按场景给出的提示（含空组、混入 DIRECT、信息节点、策略选择）。
    4. --delay 追加一次有界延迟测速（默认逐叶子节点，真实出网）。
    5. --list-instances 只枚举本机实例（PID、-d/-f、mixed、controller、listeners、策略），
       不查 API；多实例再逐个用 --config/--controller 检查。

不做什么
    - 不发 PUT/PATCH：不切节点、不改模式、不写代理登记文件。
    - 不凭节点名判断地区或真实出口：需要逐节点出口必须切节点，属写操作，另需授权。
    - 不把 load-balance 的 round-robin 当成缺陷：轮换出口对无登录公开页爬虫是有效策略，
      对带会话的站点才是风险，报告按场景提示。
    - 不把单实例报告当整机：默认只检查一个实例；发现多个代理相关进程时只提示，
      完整清单用 --list-instances。

用法
    python -X utf8 scripts/inspect_mihomo.py
    python -X utf8 scripts/inspect_mihomo.py --list-instances
    python -X utf8 scripts/inspect_mihomo.py --list-instances --json
    python -X utf8 scripts/inspect_mihomo.py --json
    python -X utf8 scripts/inspect_mihomo.py --process
    python -X utf8 scripts/inspect_mihomo.py --config <path> --controller <host>:<port>
    python -X utf8 scripts/inspect_mihomo.py --delay
    python -X utf8 scripts/inspect_mihomo.py --delay --group PROXY --test-url <url>
    python -X utf8 scripts/inspect_mihomo.py --report <path>          # 另存 Markdown

    --delay 会真实出网（每个目标节点一次请求），不加则只读本机配置与回环 API。

退出码：0 报告完整；1 找到配置但控制 API 不可用（只输出配置部分）；2 没有找到配置。
仅标准库。
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse as urlparse
from urllib import request as urlreq

UA = "inspect-mihomo/0.1"
DEFAULT_TEST_URL = "http://www.gstatic.com/generate_204"
DEFAULT_DELAY_TIMEOUT = 5000
DEFAULT_DELAY_LIMIT = 120
API_TIMEOUT = 8.0
GROUP_TYPES = {"Selector", "URLTest", "Fallback", "LoadBalance", "Relay", "Compatible"}
SPECIAL_PROXIES = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "PASS-RULE", "COMPATIBLE", "GLOBAL"}
SPECIAL_TYPES = {"Direct", "Reject", "RejectDrop", "Pass", "PassRule", "Compatible", "Dns"}
JUNK_NAME_RE = re.compile(r"官网|官方|剩余|到期|过期|套餐|重置|流量|试用|expire|traffic|official", re.I)
PROCESS_HINT_RE = re.compile(r"mihomo|clash|verge|flclash|mihomo-party|hiddify|karing", re.I)
ROUND_ROBIN_TYPES = {"round-robin"}

# 客户端配置根目录：只作候选，不假设文件名；命中后按 external-controller 是否可解析挑选。
CLIENT_ROOTS = (
    ("Clash Verge Rev", "%APPDATA%/io.github.clash-verge-rev.clash-verge-rev"),
    ("Clash Verge", "%APPDATA%/clash-verge"),
    ("mihomo-party", "%APPDATA%/mihomo-party"),
    ("FlClash", "%APPDATA%/FlClash"),
    ("FlClash", "%APPDATA%/com.follow.clash"),
    ("Clash Verge Rev", "%LOCALAPPDATA%/io.github.clash-verge-rev.clash-verge-rev"),
    ("mihomo", "~/.config/mihomo"),
    ("clash", "~/.config/clash"),
    ("mihomo-party", "~/.config/mihomo-party"),
    ("FlClash", "~/.config/FlClash"),
    ("mihomo-party", "~/Library/Application Support/mihomo-party"),
    ("Clash Verge Rev", "~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev"),
)

KEY_RE = re.compile(
    r"^(external-controller|secret|mixed-port|port|socks-port|allow-lan|mode|log-level|"
    r"ipv6|unified-delay|external-ui)\s*:\s*(.*)$"
)


def expand(path: str) -> Path:
    for var in ("APPDATA", "LOCALAPPDATA"):
        if f"%{var}%" in path:
            value = os.environ.get(var)
            if not value:
                return Path("")  # 该平台没有这个变量：跳过候选
            path = path.replace(f"%{var}%", value)
    return Path(os.path.expanduser(path))


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def strip_comment(value: str) -> str:
    """去掉 YAML 行尾注释，但不碰引号里的 # 与正则里的 #。"""
    out, quote = [], ""
    for ch in value:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            continue
        if ch == "#" and (not out or out[-1] in " \t"):
            break
        out.append(ch)
    return "".join(out).strip()


def host_only(url: str) -> str:
    try:
        u = urlparse.urlsplit(url if "://" in url else f"http://{url}")
        return u.hostname or "<unparsable>"
    except ValueError:
        return "<unparsable>"


def parse_config_text(text: str) -> dict:
    """从运行时配置里取少量标量与 tun 开关；不做完整 YAML 解析。"""
    result = {"keys": {}, "tun": {}}
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not line or line.lstrip().startswith("#"):
            continue
        m = KEY_RE.match(line)
        if m:
            key, raw = m.group(1), strip_comment(m.group(2))
            if key == "secret":
                result["keys"]["secret"] = unquote(raw)
            else:
                result["keys"][key] = unquote(raw)
        if re.match(r"^tun\s*:\s*$", line):
            for follow in lines[idx + 1 :]:
                if follow and not follow.startswith((" ", "\t", "#")):
                    break
                tm = re.match(r"^\s+(enable|stack|device|auto-route|auto-detect-interface)\s*:\s*(\S*)", follow)
                if tm:
                    result["tun"][tm.group(1)] = unquote(strip_comment(tm.group(2)))
    return result


def parse_profile_chain(text: str) -> dict:
    """解析 Verge profiles.yaml：当前 uid 与各 profile 的摘要（URL 只留主机）。"""
    current = None
    items, item = [], None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cm = re.match(r"^current\s*:\s*(\S+)", line)
        if cm:
            current = unquote(cm.group(1))
            continue
        im = re.match(r"^-\s+uid\s*:\s*(.+)$", line)
        if im:
            if item:
                items.append(item)
            item = {"uid": unquote(im.group(1))}
            continue
        if item is None:
            continue
        if re.match(r"^\S", line):  # 回到顶层
            items.append(item)
            item = None
            continue
        fm = re.match(r"^\s{2}(type|name|file|desc|url|updated|expire)\s*:\s*(.*)$", line)
        if fm:
            key, raw_val = fm.group(1), strip_comment(fm.group(2))
            if key == "url" and raw_val:
                item["urlHost"] = host_only(unquote(raw_val))
                item["url"] = "<masked>"
            elif key == "updated":
                item["updated"] = unquote(raw_val)
            else:
                item[key] = unquote(raw_val)
    if item:
        items.append(item)
    return {"current": current, "items": items}


def parse_group_defs(text: str) -> list[dict]:
    """从运行时配置读 proxy-groups 的策略与筛选条件（成员以 API 为准）。"""
    groups, group = [], None
    in_section = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if re.match(r"^proxy-groups\s*:", line):
            in_section = True
            continue
        if in_section and re.match(r"^[A-Za-z][\w-]*\s*:", line):
            break
        if not in_section:
            continue
        nm = re.match(r"^\s*-\s+name\s*:\s*(.+)$", line)
        if nm:
            if group:
                groups.append(group)
            group = {"name": unquote(strip_comment(nm.group(1))), "use": [], "filters": []}
            continue
        if group is None:
            continue
        sm = re.match(r"^\s{2}(type|strategy|filter|exclude-filter|include-all|include-all-proxies)\s*:\s*(.*)$", line)
        if sm:
            key, value = sm.group(1), unquote(strip_comment(sm.group(2)))
            if key in {"filter", "exclude-filter"}:
                group["filters"].append({"key": key, "value": value})
            elif key.startswith("include-all"):
                group[key] = value
            else:
                group[key] = value
            continue
        um = re.match(r"^\s{2}-\s+(.+)$", line)
        if um and group.get("_in_use"):
            group["use"].append(unquote(strip_comment(um.group(1))))
            continue
        if re.match(r"^\s{2}use\s*:\s*$", line):
            group["_in_use"] = True
            continue
        if re.match(r"^\s{2}\S", line):
            group.pop("_in_use", None)
    if group:
        groups.append(group)
    for g in groups:
        g.pop("_in_use", None)
    return groups


def parse_listener_defs(text: str) -> list[dict]:
    """从运行时配置读 listeners 的 name/port/type/proxy；只取报告字段，不展开锚点。

    listeners 是同一实例的额外入站端口（常见于按国家/worker 分流），
    与 mixed-port、external-controller 是不同用途；报告要把它们分开。
    """
    listeners, item = [], None
    in_section = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if re.match(r"^listeners\s*:\s*$", line):
            in_section = True
            continue
        if in_section and re.match(r"^[A-Za-z][\w-]*\s*:", line):
            break
        if not in_section:
            continue
        nm = re.match(r"^\s*-\s+name\s*:\s*(.+)$", line)
        if nm:
            if item:
                listeners.append(item)
            item = {"name": unquote(strip_comment(nm.group(1)))}
            continue
        if item is None:
            continue
        m = re.match(r"^\s+(port|type|proxy|listen)\s*:\s*(.*)$", line)
        if m:
            key, value = m.group(1), unquote(strip_comment(m.group(2)))
            if key == "port":
                try:
                    item["port"] = int(value)
                except ValueError:
                    item["port"] = value
            else:
                item[key] = value
    if item:
        listeners.append(item)
    return listeners


def parse_provider_defs(text: str) -> dict[tuple[str, str], dict]:
    """解析 proxy-providers / rule-providers 的块状写法（type/url/path/interval）。

    只取报告需要的字段；流式写法与锚点不展开，解析不到时按"未解析"处理。
    """
    defs: dict[tuple[str, str], dict] = {}
    section = ""
    kind = ""
    provider_indent = -1
    field_indent = -1
    current: dict | None = None
    in_health = False

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()

        if indent == 0:
            provider_indent = -1
            field_indent = -1
            current = None
            match = re.match(r"^(proxy-providers|rule-providers)\s*:\s*$", stripped)
            section = match.group(1) if match else ""
            kind = "proxy" if section == "proxy-providers" else "rule"
            continue
        if not section:
            continue
        if provider_indent < 0:
            provider_indent = indent

        if indent == provider_indent:
            current = None
            in_health = False
            field_indent = -1
            match = re.match(r"""^("[^"]+"|'[^']+'|[^:#]+):\s*(.*)$""", stripped)
            if not match:
                continue
            name = unquote(match.group(1))
            if not name:
                continue
            current = {"name": name, "kind": kind, "type": "", "path": "", "url": "",
                       "interval": None, "healthCheckInterval": None}
            defs[(kind, name)] = current
            continue

        if current is None:
            continue
        if field_indent < 0:
            field_indent = indent
        if indent > field_indent:
            if in_health and stripped.startswith("interval:"):
                current["healthCheckInterval"] = parse_seconds(stripped.split(":", 1)[1])
            continue
        if indent < field_indent:
            continue

        key, _, value = stripped.partition(":")
        key = key.strip().lower()
        value = strip_comment(value)
        if key == "health-check":
            in_health = True
            continue
        in_health = False
        if key == "type":
            current["type"] = unquote(value).lower()
        elif key == "path":
            current["path"] = unquote(value)
        elif key == "url":
            current["url"] = unquote(value)
        elif key == "interval":
            current["interval"] = parse_seconds(value)
    return defs


def parse_seconds(value: str) -> int | None:
    raw = unquote(strip_comment(value))
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def resolve_provider_path(entry: dict, home_dir: str | None) -> str | None:
    """缓存文件：显式 path 优先；http 未写 path 时按 URL 的 MD5 落在 proxies/ 或 rules/。"""
    if not entry or entry.get("type") == "inline":
        return None
    path = entry.get("path") or ""
    if path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            if not home_dir:
                return None
            candidate = Path(home_dir) / candidate
        return str(candidate)
    if entry.get("type") == "http" and entry.get("url") and home_dir:
        digest = hashlib.md5(entry["url"].encode("utf-8")).hexdigest()
        bucket = "rules" if entry.get("kind") == "rule" else "proxies"
        return str(Path(home_dir) / bucket / digest)
    return None


def iter_yaml(root: Path, max_depth: int = 3, limit: int = 80):
    skip = {"node_modules", ".git", "logs", "cache", "update_cache"}
    root = root.resolve()
    for base, dirs, files in os.walk(root):
        depth = len(Path(base).relative_to(root).parts)
        if depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d not in skip]
        for name in files:
            if name.lower().endswith((".yaml", ".yml")):
                path = Path(base) / name
                try:
                    if 0 < path.stat().st_size <= 8 * 1024 * 1024:
                        yield path
                except OSError:
                    continue
                limit -= 1
                if limit <= 0:
                    return


def _clean_arg(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    if value.startswith("\\\\?\\"):
        value = value[4:]
    return value


def parse_process_paths(cmdline: str, posix: bool | None = None) -> dict:
    """从内核进程命令行里取 -d/--directory、-f/--config、-ext-ctl 与 -secret。

    先用正则按“值到下一个 -flag 为止”提取，保证含空格的路径（如 macOS
    `Application Support`）不被截断；再补齐 `=` 形式与引号包裹的值。
    """
    raw = cmdline or ""
    dirs, files = [], []
    result = {"dirs": dirs, "files": files, "controller": None, "secret": None}

    # 正则：匹配 `-flag value`，value 延伸到下一个 ` -` 标志或行尾，保留内部空格。
    flag_re = re.compile(r"(?:^|\s)(-d|--directory|-home|-f|--config|-ext-ctl|--ext-ctl|-ext-ctl-unix|--ext-ctl-unix|-secret)\s+(.+?)(?=\s-[A-Za-z]|\s--[A-Za-z]|$)")
    for match in flag_re.finditer(raw):
        flag = match.group(1).lower()
        value = _clean_arg(match.group(2).strip())
        if not value:
            continue
        if flag in ("-d", "--directory", "-home"):
            dirs.append(value)
        elif flag in ("-f", "--config"):
            files.append(value)
        elif flag in ("-ext-ctl", "--ext-ctl"):
            result["controller"] = value
        elif flag in ("-ext-ctl-unix", "--ext-ctl-unix"):
            result["controller"] = "unix:" + value
        elif flag == "-secret":
            result["secret"] = value

    # 补齐 `--flag=value` 形式（正则上面只覆盖空格分隔形式）。
    if posix is None:
        posix = os.name != "nt"
    for arg in re.split(r"\s+", raw):
        if "=" not in arg or not arg.startswith("-"):
            continue
        key, _, val = arg.partition("=")
        low = key.lower()
        val = _clean_arg(val)
        if not val:
            continue
        if low in ("--directory", "-home") and val not in dirs:
            dirs.append(val)
        elif low in ("--config",) and val not in files:
            files.append(val)
        elif low in ("--ext-ctl",) and not result["controller"]:
            result["controller"] = val
        elif low in ("--ext-ctl-unix",) and not result["controller"]:
            result["controller"] = "unix:" + val
        elif low == "--secret" and not result["secret"]:
            result["secret"] = val

    return result


def is_mihomo_core(name: str) -> bool:
    """进程名是否像 mihomo/Clash 内核，而不是 GUI 外壳。

    多实例提示只数内核；把 GUI 进程算进去会让正常的“GUI + 一个内核”误报成多实例。
    """
    low = (name or "").lower()
    if any(hint in low for hint in ("clash-verge", "mihomo-party", "flclash")):
        return False
    return bool(re.search(r"mihomo|clash", low))


def client_label(name: str, home_dir: Path | str | None = None) -> str:
    """进程/目录对应的客户端名。

    `verge-mihomo.exe` 同时被 GUI 与独立实例使用，不能只看进程名：
    只有进程名或 `-d` 落在 Clash Verge 的目录下才标成 GUI，其余标为独立 mihomo。
    """
    low = (name or "").lower()
    home = str(home_dir or "").lower()
    if "party" in low:
        return "mihomo-party"
    if "flclash" in low:
        return "FlClash"
    if "verge" in low or "clash-verge" in low:
        if "clash-verge" in low or "clash-verge" in home:
            return "Clash Verge Rev"
        return "mihomo (standalone)"
    return "mihomo"


def list_proxy_processes() -> list[dict]:
    """枚举代理内核进程（pid/name/exe/cmdline）。失败返回空表，不阻塞报告。"""
    proc_root = Path("/proc")
    if os.name != "nt" and proc_root.is_dir():
        out = []
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                name = (entry / "comm").read_text(errors="replace").strip()
                raw = (entry / "cmdline").read_bytes()
                args = [chunk.decode("utf-8", "replace") for chunk in raw.split(b"\0") if chunk]
                exe = os.readlink(entry / "exe") if (entry / "exe").exists() else ""
            except OSError:
                continue
            if PROCESS_HINT_RE.search(name) or PROCESS_HINT_RE.search(" ".join(args)):
                out.append({"pid": int(entry.name), "name": name, "exe": exe, "cmdline": " ".join(args)})
        return out

    if os.name == "nt":
        script = (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
            "Get-CimInstance Win32_Process -Filter \"Name LIKE '%mihomo%' OR Name LIKE '%clash%' "
            "OR Name LIKE '%verge%' OR Name LIKE '%flclash%'\" | "
            "Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
        )
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script]
    else:
        command = ["ps", "-axo", "pid=,comm=,args="]

    try:
        proc = subprocess.run(command, capture_output=True, timeout=12)
    except (OSError, subprocess.SubprocessError):
        return []
    raw = proc.stdout.decode("utf-8", errors="replace").strip()
    if not raw:
        return []

    if os.name == "nt":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        rows = data if isinstance(data, list) else [data]
        return [
            {
                "pid": row.get("ProcessId"),
                "name": row.get("Name") or "",
                "exe": row.get("ExecutablePath") or "",
                "cmdline": row.get("CommandLine") or "",
            }
            for row in rows
            if PROCESS_HINT_RE.search(row.get("Name") or "")
        ]

    rows = []
    for line in raw.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            rows.append({"pid": int(parts[0]), "name": parts[1], "exe": parts[1], "cmdline": parts[2]})
    return [row for row in rows if PROCESS_HINT_RE.search(row["name"]) or PROCESS_HINT_RE.search(row["cmdline"])]


def _entry_from_file(path: Path, client: str, root: Path, source: str, process: dict | None = None,
                     home_dir: Path | None = None) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    keys = parse_config_text(text)["keys"]
    if "external-controller" not in keys and "mixed-port" not in keys:
        return None
    profiles = root / "profiles.yaml"
    return {
        "client": client,
        "root": str(root),
        "home_dir": str(home_dir or root),
        "runtime_config": str(path),
        "profiles_file": str(profiles) if profiles.is_file() else None,
        "candidates": [str(path)],
        "discovery": source,
        "process": {"name": process.get("name"), "pid": process.get("pid")} if process else None,
        "controller_override": (process or {}).get("controller"),
        "secret_override": (process or {}).get("secret"),
        "_text": text,
    }


def score_entry(entry: dict) -> tuple:
    """运行时配置通常最完整也最新：优先带控制口和 groups/rules 的那份，再按时间。"""
    body = entry["_text"]
    keys = parse_config_text(body)["keys"]
    rich = bool(re.search(r"^(proxy-groups|proxy-providers|rules)\s*:", body, re.M))
    try:
        stat = Path(entry["runtime_config"]).stat()
        mtime, size = stat.st_mtime, stat.st_size
    except OSError:
        mtime, size = 0.0, 0
    return (1 if keys.get("external-controller") else 0, 1 if rich else 0, mtime, size)


def best_entry_in_dir(directory: Path, client: str, source: str, process: dict | None = None,
                      max_depth: int = 1, limit: int = 20, home_dir: Path | None = None) -> dict | None:
    entries = []
    if not directory.is_dir():
        return None
    for path in iter_yaml(directory, max_depth=max_depth, limit=limit):
        entry = _entry_from_file(path, client, directory, source, process, home_dir=home_dir)
        if entry:
            entries.append(entry)
    if not entries:
        return None
    entries.sort(key=score_entry, reverse=True)
    return entries[0]


def process_entries(processes: list[dict]) -> list[dict]:
    entries: list[dict] = []
    for proc in processes or []:
        paths = parse_process_paths(proc.get("cmdline") or "")
        context = {**proc, "controller": paths["controller"], "secret": paths["secret"]}
        home = Path(paths["dirs"][0]) if paths["dirs"] else None
        client = client_label(proc.get("name") or "", home)
        found = False
        for file in paths["files"]:
            path = Path(file)
            if path.is_file():
                entry = _entry_from_file(path, client, path.parent, "process", context,
                                         home_dir=home or path.parent)
                if entry:
                    entries.append(entry)
                    found = True
        for directory in paths["dirs"]:
            entry = best_entry_in_dir(Path(directory), client, "process", context, home_dir=Path(directory))
            if entry:
                entries.append(entry)
                found = True
        if not found and proc.get("exe"):
            exe_dir = Path(proc["exe"]).parent
            entry = best_entry_in_dir(exe_dir, client, "process", context, home_dir=exe_dir)
            if entry:
                entries.append(entry)
    return dedupe_entries(entries)


def dedupe_entries(entries: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for entry in entries:
        key = os.path.normcase(os.path.abspath(entry["runtime_config"]))
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


def pick_entry(entries: list[dict]) -> dict | None:
    """多个候选时先按分数排，再对带控制口的候选做一次短探测，能响应的优先。"""
    unique = dedupe_entries(entries)
    if not unique:
        return None
    unique.sort(key=score_entry, reverse=True)
    if len(unique) == 1:
        return unique[0]
    for entry in unique[:4]:
        keys = parse_config_text(entry["_text"])["keys"]
        controller = keys.get("external-controller")
        if not controller:
            continue
        base = controller if controller.startswith(("http://", "https://")) else f"http://{controller}"
        try:
            api_get(base, keys.get("secret") or "", "/version", timeout=1.5)
            return entry
        except Exception:  # noqa: BLE001
            continue
    return unique[0]


def static_entries() -> list[dict]:
    entries = []
    for label, raw in CLIENT_ROOTS:
        root = expand(raw)
        if not root.is_dir():
            continue
        entry = best_entry_in_dir(root, label, "scan", max_depth=3, limit=80, home_dir=root)
        if entry:
            entries.append(entry)
    return entries


def entry_from_explicit(path: Path) -> dict | None:
    """把 --config 指定的运行时文件包装成统一 entry，供单实例与实例清单复用。"""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "client": "explicit",
        "root": str(path.parent),
        "home_dir": str(path.parent),
        "runtime_config": str(path),
        "profiles_file": None,
        "candidates": [str(path)],
        "discovery": "explicit",
        "process": None,
        "controller_override": None,
        "secret_override": None,
        "_text": text,
    }


def find_client(
    explicit: Path | None,
    processes: list[dict] | None = None,
    prefer_process: bool = False,
    use_process: bool = True,
) -> dict | None:
    """返回 {client, root, runtime_config, profiles_file, candidates, discovery, process}。"""
    if explicit:
        return entry_from_explicit(explicit)

    if processes is not None:
        prefer_process = True
    scanned = static_entries()

    if use_process and (prefer_process or os.name != "nt"):
        procs = processes if processes is not None else list_proxy_processes()
        picked = pick_entry(process_entries(procs) + scanned)
        if picked:
            return picked
        return pick_entry(scanned)

    # Windows 单客户端快路径：目录扫描约 0.1 秒，进程查询要起 PowerShell/CIM，约 0.3 秒。
    if len(scanned) == 1:
        return scanned[0]
    if use_process and (not scanned or len(scanned) >= 2):
        procs = processes if processes is not None else list_proxy_processes()
        return pick_entry(process_entries(procs) + scanned)
    return pick_entry(scanned)


def proxy_process_count() -> int:
    """轻量计数代理内核进程，只用于提示"是否可能有多个实例"。

    Windows 用 tasklist（比 CIM 便宜），其他平台直接枚举进程。
    计数失败返回 0，不阻塞单实例报告。
    """
    if os.name != "nt":
        return sum(1 for item in list_proxy_processes() if is_mihomo_core(item.get("name") or ""))
    try:
        proc = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    count = 0
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        name = line.split(",", 1)[0].strip().strip('"')
        if name and is_mihomo_core(name):
            count += 1
    return count


def summarize_instance(entry: dict) -> dict:
    """把一个 entry 压成实例清单的一行；不查 API、不输出 secret。"""
    text = entry.get("_text") or ""
    keys = parse_config_text(text)["keys"]
    listeners = parse_listener_defs(text)
    strategies: list[str] = []
    # 策略可能写在 proxy-groups 的锚点里，parse_group_defs 不展开锚点；
    # 实例清单只做概览，按文件里出现的 strategy 值去重列出。
    for match in re.finditer(r"^\s*strategy\s*:\s*(\S+)", text, re.M):
        strategy = unquote(strip_comment(match.group(1)))
        if strategy and strategy not in strategies:
            strategies.append(strategy)
    proc = entry.get("process") or {}
    return {
        "client": entry.get("client"),
        "pid": proc.get("pid"),
        "process": proc.get("name"),
        "home": entry.get("home_dir") or entry.get("root"),
        "runtimeConfig": entry.get("runtime_config"),
        "profilesFile": entry.get("profiles_file"),
        "controller": entry.get("controller_override") or keys.get("external-controller") or "",
        "mixedPort": keys.get("mixed-port") or "",
        "listeners": listeners,
        "strategies": strategies,
        "discovery": entry.get("discovery"),
    }


def discover_instances(explicit: Path | None = None, processes: list[dict] | None = None) -> list[dict]:
    """枚举本机所有可发现的实例：显式配置 + 进程 -d/-f + 客户端目录扫描。"""
    entries: list[dict] = []
    if explicit:
        entry = entry_from_explicit(explicit)
        if entry:
            entries.append(entry)
    procs = processes if processes is not None else list_proxy_processes()
    entries.extend(process_entries(procs))
    entries.extend(static_entries())
    return dedupe_entries(entries)


def list_instances(explicit: Path | None, as_json: bool) -> int:
    """只读列出实例清单；完整检查仍按实例分别 --config/--controller。"""
    entries = discover_instances(explicit)
    if not entries:
        print("没有发现 mihomo/Clash 实例；用 --config 指定运行时配置。", file=sys.stderr)
        return 2
    summaries = [summarize_instance(entry) for entry in entries]
    summaries.sort(key=lambda item: (item["pid"] is None, item["pid"] or 0, item["runtimeConfig"] or ""))

    if as_json:
        print(json.dumps({"count": len(summaries), "instances": summaries}, ensure_ascii=False, indent=2))
        return 0

    print(f"mihomo 实例 {len(summaries)} 个：")
    print("")
    print("| PID | 客户端 | 工作目录 (-d) | mixed | controller | listeners | 策略 | 配置 (-f) |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for item in summaries:
        listeners = item["listeners"]
        if listeners:
            shown = ", ".join(f"{one.get('name')}:{one.get('port')}" for one in listeners[:3])
            if len(listeners) > 3:
                shown += f" … 共 {len(listeners)} 个"
        else:
            shown = "-"
        print(
            f"| {item['pid'] or '-'} | {item['client'] or '-'} | `{item['home'] or '-'}` | "
            f"{item['mixedPort'] or '-'} | {item['controller'] or '-'} | {shown} | "
            f"{', '.join(item['strategies']) or '-'} | `{item['runtimeConfig']}` |"
        )
    print("")
    print("逐个检查：`--config <runtime> --controller <host:port>`；控制口不可达时用 `--process` 或 `--no-process` 重试。")
    return 0


def _is_unix_socket(controller: str) -> bool:
    """控制口是 Unix socket 路径（不是 host:port 的 HTTP 控制口）。"""
    if not controller:
        return False
    if controller.startswith(("http://", "https://")):
        return False
    if controller.startswith("unix:"):
        return True
    # 绝对路径或以 ./ 开头的相对路径，且不是 host:port（含冒号端口）
    if controller.startswith(("/", "./", "../")):
        return True
    # 含 / 且无端口冒号，通常是 socket 路径
    if "/" in controller and not re.match(r"^\[?[^\s/]+\]?:\d+$", controller):
        return True
    return False


def _unix_socket_path(controller: str) -> str:
    if controller.startswith("unix:"):
        return controller[len("unix:"):]
    return controller


class _UnixHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection 走 AF_UNIX，跳过 TCP_NODELAY 等 TCP 专属设置。"""

    def __init__(self, socket_path: str, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self):  # noqa: D401
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._socket_path)
        self.sock = s


def api_get(base: str, secret: str, path: str, timeout: float = API_TIMEOUT,
            unix_socket: str | None = None):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    if unix_socket:
        conn = _UnixHTTPConnection(unix_socket, timeout)
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
    else:
        req = urlreq.Request(base + path, headers=headers)
        opener = urlreq.build_opener(urlreq.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
    if raw[:1] in (b"{", b"["):
        return json.loads(raw)
    return raw.decode("utf-8", "replace")


def delay_one(base: str, secret: str, name: str, test_url: str, timeout_ms: int,
              unix_socket: str | None = None):
    path = "/proxies/{}/delay?{}".format(
        urlparse.quote(name, safe=""),
        urlparse.urlencode({"url": test_url, "timeout": timeout_ms}),
    )
    try:
        data = api_get(base, secret, path, timeout=timeout_ms / 1000 + 3, unix_socket=unix_socket)
        return name, data.get("delay"), None
    except Exception as exc:  # noqa: BLE001
        return name, None, f"{type(exc).__name__}: {exc}"


def delay_group_targets(base: str, secret: str, targets: list[str], proxies: dict,
                        test_url: str, timeout_ms: int, preferred: list[str] | None = None,
                        unix_socket: str | None = None) -> dict:
    """对不在 /proxies 里的 provider 节点，按其所属分组整组测速并取回成员结果。

    先测显式指定的组，再按覆盖人数从大到小测，避免同一批节点被多个小组重复测速。
    """
    pending = set(targets)
    results: dict[str, int] = {}
    tested: set[str] = set()
    ordered = [name for name in (preferred or []) if name in proxies and name != "GLOBAL"]
    rest = [
        name for name, p in proxies.items()
        if p.get("type") in GROUP_TYPES and name not in SPECIAL_PROXIES
        and name not in ordered and name != "GLOBAL"
    ]
    rest.sort(key=lambda name: -len(group_leaf_members(name, proxies)))
    for name in ordered + rest:
        if not pending:
            break
        members = proxies[name].get("all") or []
        if any((proxies.get(m) or {}).get("type") in GROUP_TYPES for m in members):
            continue  # 嵌套组的 delay 返回的是子组而不是叶子，跳过
        leaves = {m for m in members if m not in SPECIAL_PROXIES}
        if not ((leaves & pending) - tested):
            continue
        path = "/group/{}/delay?{}".format(
            urlparse.quote(name, safe=""),
            urlparse.urlencode({"url": test_url, "timeout": timeout_ms}),
        )
        try:
            data = api_get(base, secret, path, timeout=timeout_ms / 1000 + 15, unix_socket=unix_socket)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict) or not data:
            continue  # 空响应不参与判定，换下一个组
        if not (leaves & set(data)):
            continue  # 返回的是子组或其它成员，不消费待测节点
        tested |= leaves
        for member in leaves & pending:
            if isinstance(data.get(member), int):
                results[member] = data[member]
            pending.discard(member)
    return results


def fetch_subscription(url: str, proxy_url: str | None = None, timeout: float = 20.0) -> str:
    """只读 GET 订阅地址，UA 与内核一致；不打印 URL 与凭据。"""
    handlers = [urlreq.ProxyHandler({"http": proxy_url, "https": proxy_url} if proxy_url else {})]
    opener = urlreq.build_opener(*handlers)
    req = urlreq.Request(
        url,
        headers={"User-Agent": "clash.meta", "Accept": "*/*", "Accept-Encoding": "identity"},
    )
    with opener.open(req, timeout=timeout) as resp:
        return resp.read(2_000_000).decode("utf-8", "replace")


def parse_subscription_names(text: str) -> list[str]:
    """从 Clash 配置响应的 proxies 段取节点名，兼容 flow 与 block 写法。"""
    names: list[str] = []
    in_section = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t", "-")):
            in_section = bool(re.match(r"^proxies\s*:", raw))
            if in_section and "[" in raw:
                for match in re.finditer(r"\{[^{}]*?\bname:\s*['\"]?([^,'\"}]+)", raw):
                    names.append(match.group(1).strip())
            continue
        if not in_section:
            continue
        flow = re.match(r"^\s*-\s*\{.*?\bname:\s*['\"]?([^,'\"}]+)", raw)
        if flow:
            names.append(flow.group(1).strip())
            continue
        block = re.match(r"^\s*-\s+name\s*:\s*(.+)$", raw)
        if block:
            names.append(unquote(strip_comment(block.group(1))).strip())
    return list(dict.fromkeys(name for name in names if name))


def compare_subscriptions(defs: dict, proxy_api: dict, proxy_url: str | None, timeout: float = 20.0) -> list[dict]:
    """对比本地 provider 节点与订阅当前返回的节点名；只读 GET，不改配置。"""
    rows = []
    for (kind, name), entry in defs.items():
        if kind != "proxy" or str(entry.get("type")).lower() != "http" or not entry.get("url"):
            continue
        local = [
            node.get("name")
            for node in ((proxy_api.get(name) or {}).get("proxies") or [])
            if node.get("name")
        ]
        row = {
            "name": name,
            "host": host_only(entry["url"]),
            "localCount": len(local),
            "remoteCount": None,
            "added": [],
            "removed": [],
            "error": None,
        }
        attempts = [proxy_url, None] if proxy_url else [None]
        last_error = None
        for attempt in attempts:
            try:
                remote = parse_subscription_names(fetch_subscription(entry["url"], attempt, timeout))
                if not remote:
                    last_error = "响应里没有解析到 proxies（可能不是 Clash 配置）"
                    continue
                row.update(
                    remoteCount=len(remote),
                    added=[n for n in remote if n not in local],
                    removed=[n for n in local if n not in remote],
                )
                row["addedReal"] = [n for n in row["added"] if not JUNK_NAME_RE.search(n)]
                row["addedInfo"] = [n for n in row["added"] if JUNK_NAME_RE.search(n)]
                row["removedReal"] = [n for n in row["removed"] if not JUNK_NAME_RE.search(n)]
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
        row["error"] = last_error
        rows.append(row)
    return rows


def leaf_names(proxies: dict) -> list[str]:
    return [
        n
        for n, p in proxies.items()
        if p.get("type") not in GROUP_TYPES
        and p.get("type") not in SPECIAL_TYPES
        and n not in SPECIAL_PROXIES
    ]


def merge_nodes(proxies: dict, providers: dict) -> dict:
    """合并节点来源：新版内核的 provider 节点可能只出现在 /providers/proxies。"""
    merged = dict(proxies)
    for provider in (providers or {}).values():
        for node in provider.get("proxies") or []:
            name = node.get("name")
            if name and name not in merged:
                merged[name] = node
    return merged


def group_leaf_members(name: str, proxies: dict, seen: set | None = None) -> list[str]:
    seen = seen or set()
    if name in seen or name not in proxies:
        return []
    seen.add(name)
    out = []
    for member in proxies[name].get("all") or []:
        if member in SPECIAL_PROXIES:
            continue
        if (proxies.get(member) or {}).get("type") in GROUP_TYPES:
            out.extend(group_leaf_members(member, proxies, seen))
        else:
            out.append(member)
    return out


def parse_timestamp(ts) -> datetime | None:
    if not ts or str(ts).startswith("0001"):
        return None
    if isinstance(ts, str) and ts.strip().isdigit():
        ts = int(ts.strip())
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        dt = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", str(ts).replace("Z", "+00:00")))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def human_age(ts) -> str:
    dt = parse_timestamp(ts)
    if dt is None:
        return "未记录"
    secs = int((datetime.now(timezone.utc) - dt).total_seconds())
    if secs < 0:
        return f"{-secs}s 后（时钟偏差）"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    return f"{secs // 86400} 天前"


def human_interval(seconds) -> str:
    if not seconds:
        return "未设置"
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "未设置"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def build_providers(proxy_api: dict, rule_api: dict, defs: dict, home_dir: str | None) -> list[dict]:
    """合并 API 状态与配置里的 interval/path，算缓存位置与是否超过更新周期。"""
    rows = []
    now = datetime.now(timezone.utc)
    for kind, source in (("proxy", proxy_api), ("rule", rule_api)):
        for name, provider in (source or {}).items():
            sub = provider.get("subscriptionInfo") or {}
            used = (sub.get("Upload") or 0) + (sub.get("Download") or 0)
            total = sub.get("Total") or 0
            updated = parse_timestamp(provider.get("updatedAt"))
            age_sec = int((now - updated).total_seconds()) if updated else None
            entry = defs.get((kind, name)) or {}
            interval = entry.get("interval")
            vehicle = provider.get("vehicleType") or entry.get("type") or ""
            cache_path = resolve_provider_path(entry, home_dir)
            cache_exists = bool(cache_path) and Path(cache_path).is_file()
            cache_age = human_age(Path(cache_path).stat().st_mtime) if cache_exists else None
            stale = bool(
                str(vehicle).upper() == "HTTP"
                and interval
                and age_sec is not None
                and age_sec > interval * 1.5
            )
            note = ""
            if str(vehicle).lower() == "compatible":
                note = "内置兼容 provider，非订阅"
            elif str(vehicle).lower() == "file":
                note = "本地文件监听，不自动下载"
            elif str(vehicle).upper() == "HTTP" and not interval:
                note = "未设置 interval，只在启动时拉一次"
            if stale:
                note = f"{note}；超过更新周期" if note else "超过更新周期"
            rows.append(
                {
                    "kind": kind,
                    "name": name,
                    "vehicle": vehicle,
                    "count": provider.get("ruleCount") if kind == "rule" else len(provider.get("proxies") or []),
                    "updatedAt": updated.strftime("%Y-%m-%d %H:%M") if updated else None,
                    "age": human_age(provider.get("updatedAt")),
                    "ageSeconds": age_sec,
                    "interval": interval,
                    "stale": stale,
                    "cachePath": cache_path,
                    "cacheExists": cache_exists,
                    "cacheAge": cache_age,
                    "note": note,
                    "expire": sub.get("Expire"),
                    "usedGB": round(used / 1024**3, 2),
                    "totalGB": round(total / 1024**3, 2) if total else None,
                }
            )
    rows.sort(key=lambda row: (row["kind"], row["name"]))
    return rows


def build_model(ctx: dict, api: dict, delay: dict | None, subscriptions: list[dict] | None = None) -> dict:
    text = ctx["_text"]
    cfg = parse_config_text(text)
    chain = parse_profile_chain(
        Path(ctx["profiles_file"]).read_text(encoding="utf-8", errors="replace")
        if ctx.get("profiles_file")
        else ""
    )
    group_defs = {g["name"]: g for g in parse_group_defs(text)}

    version = api.get("version") or {}
    configs = api.get("configs") or {}
    proxies = (api.get("proxies") or {}).get("proxies") or {}
    providers = (api.get("providers") or {}).get("providers") or {}
    rule_providers = (api.get("rules_providers") or {}).get("providers") or {}
    proxies = merge_nodes(proxies, providers)
    rules = (api.get("rules") or {}).get("rules") or []
    conns = api.get("connections") or {}

    counts: dict[str, int] = {}
    for name in leaf_names(proxies):
        t = proxies[name].get("type", "?")
        counts[t] = counts.get(t, 0) + 1

    leaves = []
    for name in leaf_names(proxies):
        p = proxies[name]
        hist = p.get("history") or []
        last = hist[-1] if hist else {}
        leaves.append(
            {
                "name": name,
                "type": p.get("type"),
                "alive": p.get("alive"),
                "lastDelay": last.get("delay"),
                "historyCount": len(hist),
                "provider": p.get("provider") or p.get("provider-name") or None,
            }
        )

    groups = []
    for name, p in sorted(proxies.items()):
        if p.get("type") not in GROUP_TYPES or name in SPECIAL_PROXIES:
            continue
        members = p.get("all") or []
        nested = [
            m for m in members
            if m not in SPECIAL_PROXIES and (proxies.get(m) or {}).get("type") in GROUP_TYPES
        ]
        leafs = [m for m in members if m not in SPECIAL_PROXIES and m not in nested]
        d = group_defs.get(name, {})
        groups.append(
            {
                "name": name,
                "type": p.get("type"),
                "now": p.get("now"),
                "members": len(members),
                "leaves": len(leafs),
                "nested": len(nested),
                "hasDirect": "DIRECT" in members,
                "hasReject": "REJECT" in members or "REJECT-DROP" in members,
                "strategy": d.get("strategy"),
                "use": d.get("use") or [],
                "filters": d.get("filters") or [],
                "includeAll": d.get("include-all") or d.get("include-all-proxies"),
            }
        )

    provs = build_providers(
        providers,
        rule_providers,
        parse_provider_defs(text),
        ctx.get("home_dir"),
    )

    rule_types: dict[str, int] = {}
    for r in rules:
        rule_types[r.get("type", "?")] = rule_types.get(r.get("type", "?"), 0) + 1
    final_rule = rules[-1] if rules else {}

    chains: dict[str, int] = {}
    for c in conns.get("connections") or []:
        key = " > ".join(c.get("chains") or [])
        chains[key] = chains.get(key, 0) + 1

    secret = cfg["keys"].get("secret") or ""
    model = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "client": {
            "name": ctx["client"],
            "root": ctx["root"],
            "homeDir": ctx.get("home_dir"),
            "runtimeConfig": ctx["runtime_config"],
            "profilesFile": ctx.get("profiles_file"),
            "candidates": ctx.get("candidates") or [],
            "discovery": ctx.get("discovery") or "scan",
            "process": ctx.get("process"),
        },
        "config": {
            "controller": cfg["keys"].get("external-controller"),
            "secretSet": bool(secret),
            "secretLen": len(secret),
            "mixedPort": cfg["keys"].get("mixed-port"),
            "httpPort": cfg["keys"].get("port"),
            "socksPort": cfg["keys"].get("socks-port"),
            "mode": cfg["keys"].get("mode"),
            "allowLan": cfg["keys"].get("allow-lan"),
            "ipv6": cfg["keys"].get("ipv6"),
            "unifiedDelay": cfg["keys"].get("unified-delay"),
            "tunEnabled": cfg["tun"].get("enable"),
            "tunStack": cfg["tun"].get("stack"),
        },
        "profiles": chain,
        "runtime": {
            "version": version.get("version"),
            "meta": version.get("meta"),
            "mode": configs.get("mode"),
            "mixedPort": configs.get("mixed-port"),
            "httpPort": configs.get("port"),
            "socksPort": configs.get("socks-port"),
            "allowLan": configs.get("allow-lan"),
            "ipv6": configs.get("ipv6"),
            "tun": configs.get("tun"),
            "tunEnabled": (configs.get("tun") or {}).get("enable"),
            "error": api.get("error"),
        },
        "nodes": {
            "leafTotal": len(leaves),
            "byType": counts,
            "leaves": leaves,
            "groups": groups,
        },
        "providers": provs,
        "subscriptions": subscriptions,
        "rules": {
            "count": len(rules),
            "types": rule_types,
            "final": {"type": final_rule.get("type"), "proxy": final_rule.get("proxy")},
            "all": [{"type": r.get("type"), "payload": r.get("payload"), "proxy": r.get("proxy")} for r in rules],
        },
        "connections": {
            "open": len(conns.get("connections") or []),
            "topChains": sorted(chains.items(), key=lambda kv: -kv[1])[:8],
        },
        "delay": delay or {"ran": False},
        "findings": [],
        "blindSpots": [
            "延迟只代表测试 URL，不代表目标站可达或能过风控",
            "节点名里的地区不可信；逐节点真实出口需要切节点（写操作），本脚本不做",
            "只覆盖 Clash 兼容控制 API；sing-box / xray 的本地接口不在本轮范围",
        ],
    }
    model["findings"] = findings(model, proxies)
    return model


def findings(model: dict, proxies: dict) -> list[dict]:
    out: list[dict] = []

    def add(level: str, title: str, detail: str) -> None:
        out.append({"level": level, "title": title, "detail": detail})

    cfg = model["config"]
    groups = model["nodes"]["groups"]
    leaves = model["nodes"]["leaves"]
    tun_on = model["runtime"].get("tunEnabled")
    if tun_on is None:
        tun_on = cfg.get("tunEnabled")

    if str(tun_on).lower() not in ("true", "1") and cfg["controller"]:
        add(
            "info",
            "系统级接管未开启",
            "TUN 关闭时只有显式走 mixed 端口的进程受这套配置影响；新终端或工具不设代理变量就是直连。",
        )
    if cfg["secretSet"] and cfg["secretLen"] <= 4:
        add(
            "info",
            "控制口 secret 很短",
            "只绑定回环时风险有限，但本机任意进程都能读取节点列表与切换节点。",
        )

    empty = [g["name"] for g in groups if g["leaves"] == 0 and g["nested"] == 0]
    if empty:
        add("warn", "存在空分组", f"{', '.join(empty)} 没有可用的成员；选中它们等于放弃代理（常见于 provider 为空）。")

    risky = [g["name"] for g in groups if g["type"] == "Selector" and (g["hasDirect"] or g["hasReject"])]
    if risky:
        add(
            "warn",
            "主选择组混入直连/拒绝项",
            f"{', '.join(risky)} 含 DIRECT/REJECT；误选一次就是整机直连或全阻断，且不会报错。",
        )

    rotating = [g["name"] for g in groups if g["strategy"] in ROUND_ROBIN_TYPES]
    if rotating:
        add(
            "info",
            "轮换出口的分组",
            f"{', '.join(rotating)} 使用 round-robin（按连接轮换）。适合无登录公开页面爬虫分散出口；"
            "带登录态、会话绑定或需要 IP 一致的站点应改用 consistent-hashing / sticky-sessions，"
            "或换成固定单节点的选择组。",
        )

    junk_in_pool = []
    for leaf in leaves:
        if JUNK_NAME_RE.search(leaf["name"]):
            junk_in_pool.append(leaf["name"])
    if junk_in_pool:
        add(
            "info",
            "订阅自带信息节点",
            f"{len(junk_in_pool)} 个节点名字像流量/到期提示；它们可能被 exclude-filter 挡住，"
            "但仍在 provider 里参与健康检查，建议确认过滤规则是否覆盖。",
        )

    reachable: set[str] = set()
    for g in groups:
        reachable.update(group_leaf_members(g["name"], proxies))
    unreachable = [leaf["name"] for leaf in leaves if leaf["name"] not in reachable]
    if unreachable:
        sample = "、".join(unreachable[:3]) + ("…" if len(unreachable) > 3 else "")
        add(
            "info",
            "有节点不在任何分组里",
            f"{len(unreachable)} 个（如 {sample}）在 provider 里但没进任何组，可能是 filter/exclude-filter "
            "挡掉的；它们选不到，却仍参与 provider 健康检查。",
        )

    final = model["rules"]["final"]
    target = final.get("proxy")
    if target and target in proxies:
        path, cur, seen = [target], proxies[target].get("now"), {target}
        while cur and cur in proxies and cur not in seen:
            path.append(cur)
            seen.add(cur)
            cur = (proxies.get(cur) or {}).get("now")
        if len(path) > 1:
            add(
                "info",
                "默认出口链路",
                "MATCH -> " + " -> ".join(path) + "；未命中规则的流量都走这条链，"
                "其他分组只在对应规则命中时才生效。",
            )

    weak_provs = [
        p["name"] for p in model["providers"]
        if str(p.get("vehicle")).lower() == "file" and not p.get("count")
    ]
    if weak_provs:
        add("warn", "空的 file provider", f"{', '.join(weak_provs)} 没有节点；引用它们的组会退化成空组。")

    stale = [p["name"] for p in model["providers"] if p.get("stale")]
    if stale:
        add(
            "warn",
            "超过更新周期的 provider",
            f"{', '.join(stale)} 的更新时间已超过自身 interval 的 1.5 倍；可能是订阅不可达或更新失败，"
            "但重启后 updatedAt 会被重置为缓存 mtime，先对照缓存文件时间再下结论。",
        )

    missing_cache = [
        p["name"] for p in model["providers"]
        if str(p.get("vehicle")).upper() == "http" and p.get("cachePath") and not p.get("cacheExists")
    ]
    if missing_cache:
        add(
            "warn",
            "provider 缓存文件缺失",
            f"{', '.join(missing_cache)} 按配置推出的缓存路径不存在；首次拉取、换 URL 后未更新，"
            "或 `path` 与实际写法不一致都可能造成，确认前不要当成已加载。",
        )

    no_interval = [
        p["name"] for p in model["providers"]
        if str(p.get("vehicle")).upper() == "http" and not p.get("interval")
    ]
    if no_interval:
        add(
            "info",
            "provider 未设置更新周期",
            f"{', '.join(no_interval)} 没有写 interval，按内核语义视为 0：只在启动时拉一次，之后不轮询。",
        )

    for row in model.get("subscriptions") or []:
        if row.get("error"):
            add("info", "订阅内容对比失败", f"{row['name']}（{row.get('host')}）：{row['error']}")
            continue
        if row.get("addedReal"):
            sample = "、".join(row["addedReal"][:5]) + ("…" if len(row["addedReal"]) > 5 else "")
            add(
                "warn",
                "订阅有新增节点但本地 provider 没有",
                f"{row['name']}：{sample}。本地缓存可能早于订阅变更；先触发 provider 更新，再查分组过滤。",
            )
        if row.get("removedReal"):
            sample = "、".join(row["removedReal"][:5]) + ("…" if len(row["removedReal"]) > 5 else "")
            add(
                "info",
                "线上已移除的节点仍在本地",
                f"{row['name']}：{sample}。可能是缓存未更新，或显式 path 固定了旧文件。",
            )

    if not any(r.get("type") == "Match" for r in model["rules"]["all"]):
        add("warn", "缺少兜底规则", "没有 MATCH/FINAL 规则时，未命中的流量行为取决于内核默认值。")

    dead = [leaf["name"] for leaf in leaves if leaf["alive"] is False or leaf["lastDelay"] == 0]
    if dead:
        add(
            "info",
            "历史记录里不可用的节点",
            f"{len(dead)} 个节点 alive 为 false 或最近延迟为 0；这些是历史记录，"
            "是否仍不可用要用 --delay 复测。",
        )

    final = model["rules"]["final"]
    if final.get("type") == "Match" and final.get("proxy") in {"DIRECT", "REJECT"}:
        add("warn", "兜底走直连/拒绝", f"MATCH -> {final.get('proxy')}，未命中的流量不会走代理。")

    return out


def render(model: dict) -> str:
    cfg = model["config"]
    rt = model["runtime"]
    nodes = model["nodes"]
    lines: list[str] = []
    add = lines.append

    add("# mihomo 环境检查报告")
    add("")
    add(f"- 生成时间：{model['generated']}")
    add(f"- 客户端：{model['client']['name']}（{model['client']['root']}）")
    add(f"- 运行时配置：`{model['client']['runtimeConfig']}`")
    if model["client"].get("homeDir"):
        add(f"- 工作目录（-d）：`{model['client']['homeDir']}`")
    discovery = model["client"].get("discovery")
    proc = model["client"].get("process") or {}
    if discovery == "process":
        add(f"- 发现方式：内核进程 `{proc.get('name')}`（pid {proc.get('pid')}）的 `-d`/`-f`")
    elif discovery == "explicit":
        add("- 发现方式：`--config` 显式指定")
    else:
        add("- 发现方式：候选目录扫描")
    if rt.get("error"):
        add(f"- 控制 API：不可用（{rt['error']}）")
    else:
        add(f"- 控制 API：`{cfg['controller']}` 可用，内核 {rt.get('version') or '?'}")
    add("")

    add("## 运行时")
    add("")
    add("| 项 | 值 |")
    add("| --- | --- |")
    add(f"| 模式 | {rt.get('mode') or cfg.get('mode')} |")
    add(f"| 入口 | mixed `{rt.get('mixedPort') if rt.get('mixedPort') is not None else cfg.get('mixedPort')}`"
        f"；http `{rt.get('httpPort')}`；socks `{rt.get('socksPort')}` |")
    tun_on = rt.get("tunEnabled")
    if tun_on is None:
        tun_on = cfg.get("tunEnabled")
    stack = cfg.get("tunStack") or (rt.get("tun") or {}).get("stack")
    add(f"| TUN | {'开启' if str(tun_on).lower() in ('true', '1') else '关闭'}（stack {stack}） |")
    add(f"| allow-lan / IPv6 | {rt.get('allowLan') if rt.get('allowLan') is not None else cfg.get('allowLan')}"
        f" / {rt.get('ipv6') if rt.get('ipv6') is not None else cfg.get('ipv6')} |")
    secret_note = "已设置" if cfg["secretSet"] else "未设置"
    if cfg["secretSet"]:
        secret_note += f"（长度 {cfg['secretLen']}）"
    add(f"| 控制口 secret | {secret_note} |")
    add("")

    prof = model["profiles"]
    if prof.get("items"):
        add("## 可用配置")
        add("")
        add("| profile | 类型 | 状态 | 更新时间 | 备注 |")
        add("| --- | --- | --- | --- | --- |")
        for item in prof["items"]:
            if item.get("type") in {"merge", "script", "rules", "proxies", "groups"}:
                continue
            active = "当前生效" if item.get("uid") == prof.get("current") else "未启用"
            note = item.get("urlHost") or item.get("desc") or ""
            add(f"| `{item.get('name') or item.get('uid')}` | {item.get('type')} | {active} | {human_age(item.get('updated'))} | {note} |")
        add("")

    add("## 节点池")
    add("")
    if rt.get("error"):
        add(f"> ⚠️ 控制 API 不可用（{rt['error']}），以下节点数来自静态配置解析，**不代表内核运行时的真实节点池**；"
            "真实节点、分组与选中项需控制 API 可用后才能确认。若内核用 Unix socket / 命名管道控制口"
            "（如 `-ext-ctl-unix`），用 `--controller unix:/path/to/socket` 或 `--controller /path/to/socket` 重试。")
        add("")
    add(f"叶子节点 {nodes['leafTotal']} 个：" + "、".join(f"{k} {v}" for k, v in sorted(nodes["byType"].items(), key=lambda kv: -kv[1])))
    add("")
    if model["providers"]:
        add("## 订阅与规则集")
        add("")
        add("| 名称 | 种类 | 条目 | 更新 | 周期 | 缓存/文件 | 用量/判定 |")
        add("| --- | --- | --- | --- | --- | --- | --- |")
        for p in model["providers"]:
            kind = "节点" if p["kind"] == "proxy" else "规则"
            cache = "缺失" if p.get("cachePath") and not p.get("cacheExists") else (
                f"存在（{p['cacheAge']}）" if p.get("cacheExists") else "未解析"
            )
            tail = p.get("note") or "正常"
            if p["kind"] == "proxy" and p.get("totalGB"):
                tail = f"{p['usedGB']} GB / {p['totalGB']} GB；{tail}"
            add(f"| `{p['name']}` | {kind} | {p['count']} | {p['age']} | "
                f"{'—' if str(p['vehicle']).lower() == 'compatible' else human_interval(p.get('interval'))} | "
                f"{cache} | {tail} |")
        add("")
        add("`updatedAt` 在内核内存里，重启后会等于缓存文件 mtime；\"多久没更新\"要结合缓存文件时间看。"
            "未写 `path` 的 HTTP provider 缓存按 URL 的 MD5 落在 `<HomeDir>/proxies/`（规则集在 `rules/`）。")
        add("")

    if model.get("subscriptions") is not None:
        add("## 订阅内容对比")
        add("")
        if not model["subscriptions"]:
            add("没有可对比的 HTTP provider。")
        else:
            add("| provider | 本地 | 订阅当前 | 本地缺失 | 线上已移除 |")
            add("| --- | --- | --- | --- | --- |")
            for row in model["subscriptions"]:
                if row.get("error"):
                    add(f"| `{row['name']}` | {row['localCount']} | — | — | {row['error']} |")
                else:
                    added = "、".join((row.get("addedReal") or [])[:6]) or "—"
                    if row.get("addedInfo"):
                        added += f"（另有 {len(row['addedInfo'])} 个信息节点）"
                    removed = "、".join((row.get("removedReal") or [])[:6]) or "—"
                    add(f"| `{row['name']}` | {row['localCount']} | {row['remoteCount']} | {added} | {removed} |")
            add("")
            add("对比是主动 GET 订阅 URL，会计入订阅流量；它不更新配置，也不写缓存。")
        add("")

    add("## 分组与当前选中")
    add("")
    add("| 分组 | 类型 | 成员 | 当前选中 | 策略/条件 |")
    add("| --- | --- | --- | --- | --- |")
    for g in nodes["groups"]:
        extra = g["strategy"] or ""
        if g["includeAll"]:
            extra = "include-all"
        if g["hasDirect"] or g["hasReject"]:
            extra = (extra + " 含直连/拒绝").strip()
        add(f"| `{g['name']}` | {g['type']} | {g['members']} | {g['now'] or '—'} | {extra} |")
    add("")

    if model["rules"]["count"]:
        add("## 规则面")
        add("")
        add(f"共 {model['rules']['count']} 条，类型分布：" +
            "、".join(f"{k} {v}" for k, v in sorted(model["rules"]["types"].items(), key=lambda kv: -kv[1])))
        final = model["rules"]["final"]
        add(f"兜底：{final.get('type')} -> {final.get('proxy')}")
        add("")

    if model["delay"].get("ran"):
        d = model["delay"]
        add("## 延迟测速")
        add("")
        add(f"测试 URL：`{d['testUrl']}`，上限 {d['timeoutMs']}ms，目标 {d['targets']} 个。")
        add("")
        if d.get("mode") in ("group", "mixed"):
            add("provider 节点在新版内核里没有单节点测速接口，这部分结果来自整组测速。")
            add("")
        ok = [x for x in d["results"] if isinstance(x.get("delay"), int) and x["delay"] > 0]
        bad = [x for x in d["results"] if x.get("delay") is None or x.get("error")]
        add(f"有响应 {len(ok)} 个，无响应 {len(bad)} 个。")
        add("")
        if ok:
            ok.sort(key=lambda x: x["delay"])
            add("最快的 5 个：" + "、".join(f"{x['name']} {x['delay']}ms" for x in ok[:5]))
            add("")
            if len(ok) > 5:
                add("最慢的 5 个：" + "、".join(f"{x['name']} {x['delay']}ms" for x in ok[-5:]))
                add("")
        if bad:
            add("无响应：" + "、".join(x["name"] for x in bad[:20]) + ("…" if len(bad) > 20 else ""))
            add("")

    add("## 提示与风险")
    add("")
    if model["findings"]:
        for f in model["findings"]:
            add(f"- **[{f['level']}] {f['title']}**：{f['detail']}")
    else:
        add("- 未发现结构性异常；节点可用性仍需按 --delay 复测。")
    add("")

    add("## 盲区")
    add("")
    for item in model["blindSpots"]:
        add(f"- {item}")
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="检查本机 mihomo/Clash 系客户端的配置、节点与分组（默认只读，不发写请求）。",
        epilog="示例：python -X utf8 scripts/inspect_mihomo.py --delay --group PROXY",
    )
    parser.add_argument("--config", help="显式指定运行时配置文件，跳过自动发现")
    parser.add_argument("--process", action="store_true", help="先按内核进程的 -d/-f 定位，再退回目录扫描")
    parser.add_argument("--no-process", action="store_true", help="不查进程信息，只用候选目录与 --config")
    parser.add_argument("--list-instances", action="store_true",
                        help="只列出本机 mihomo/Clash 实例（PID、-d/-f、mixed/controller、listeners、策略），不查 API")
    parser.add_argument("--controller", help="覆盖 external-controller，如 <host>:<port>")
    parser.add_argument("--secret", help="覆盖 secret；默认从配置读取，不落盘不回显")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（stdout 只留 JSON）")
    parser.add_argument("--report", metavar="PATH", help="把 Markdown 报告另存到文件")
    parser.add_argument("--delay", action="store_true", help="追加延迟测速（会真实出网）")
    parser.add_argument("--compare-subscriptions", action="store_true",
                        help="主动 GET 订阅 URL，对比当前节点与本地 provider（会计入订阅流量）")
    parser.add_argument("--subscription-proxy", default="auto",
                        help="对比订阅时的路线：auto（用 mixed 端口）/ direct / <proxy-url>")
    parser.add_argument("--group", action="append", default=[], help="只测指定分组的叶子成员，可重复")
    parser.add_argument("--test-url", default=DEFAULT_TEST_URL, help=f"延迟测试 URL（默认 {DEFAULT_TEST_URL}）")
    parser.add_argument("--delay-timeout", type=int, default=DEFAULT_DELAY_TIMEOUT, help="单节点超时毫秒数")
    parser.add_argument("--delay-limit", type=int, default=DEFAULT_DELAY_LIMIT, help="单次最多测多少节点")
    parser.add_argument("--workers", type=int, default=8, help="测速并发数")
    args = parser.parse_args(argv)

    if args.list_instances:
        explicit = Path(args.config).expanduser().resolve() if args.config else None
        return list_instances(explicit, args.json)

    ctx = find_client(
        Path(args.config).expanduser().resolve() if args.config else None,
        prefer_process=args.process,
        use_process=not args.no_process,
    )
    if not ctx:
        print("没有找到 mihomo/Clash 系运行时配置；用 --config 指定，或用 probe_local_proxies.py 先找端口。", file=sys.stderr)
        return 2
    if not args.config and not args.no_process:
        count = proxy_process_count()
        if count > 1:
            proc = ctx.get("process") or {}
            pid_note = f"（pid {proc.get('pid')}）" if proc.get("pid") else ""
            print(
                f"inspect: 发现 {count} 个代理相关进程，本次只检查 {ctx.get('runtime_config')}{pid_note}；"
                "用 --list-instances 查看全部，或 --config/--controller 指定实例。",
                file=sys.stderr,
            )

    text = ctx["_text"]
    cfg = parse_config_text(text)["keys"]
    override = (ctx.get("controller_override") or "").strip()
    if override and not override.startswith(("http://", "https://", "unix:")) \
            and not re.match(r"^\[?[^\\/\s]+\]?:\d+$", override) \
            and not _is_unix_socket(override):
        override = ""  # 无法识别的控制口（既非 HTTP、host:port，也非 Unix socket 路径）
    controller = args.controller or override or cfg.get("external-controller")
    if args.secret is not None:
        secret = args.secret
    elif ctx.get("secret_override") is not None:
        secret = ctx["secret_override"]
    else:
        secret = cfg.get("secret") or ""

    api: dict = {}
    api_ok = False
    if controller:
        unix_socket = _unix_socket_path(controller) if _is_unix_socket(controller) else None
        base = controller if controller.startswith(("http://", "https://")) else f"http://{controller}"
        endpoints = {
            "version": "/version",
            "configs": "/configs",
            "proxies": "/proxies",
            "providers": "/providers/proxies",
            "rules_providers": "/providers/rules",
            "rules": "/rules",
            "connections": "/connections",
        }
        errors = []
        try:
            api["version"] = api_get(base, secret, "/version", timeout=3, unix_socket=unix_socket)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"version: {type(exc).__name__}")
            api["error"] = "控制 API 不可用（" + "; ".join(errors) + "）"
        else:
            for key, path in endpoints.items():
                if key == "version":
                    continue
                try:
                    api[key] = api_get(base, secret, path, unix_socket=unix_socket)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{key}: {type(exc).__name__}")
            api_ok = "proxies" in api
            if not api_ok:
                api["error"] = "控制 API 不完整（" + "; ".join(errors) + "）"
    else:
        unix_socket = None
        api["error"] = "配置里没有 external-controller"

    subscriptions = None
    if args.compare_subscriptions and api_ok:
        mixed_port = (api.get("configs") or {}).get("mixed-port")
        route = (args.subscription_proxy or "auto").strip()
        if route.lower() == "direct":
            proxy_url = None
        elif route.lower() == "auto":
            proxy_url = f"http://127.0.0.1:{mixed_port}" if mixed_port else None
        else:
            proxy_url = route
        subscriptions = compare_subscriptions(
            parse_provider_defs(text),
            (api.get("providers") or {}).get("providers") or {},
            proxy_url,
        )

    delay = None
    if args.delay and api_ok:
        raw_proxies = api["proxies"].get("proxies") or {}
        proxies = merge_nodes(raw_proxies, (api.get("providers") or {}).get("providers") or {})
        if args.group:
            targets: list[str] = []
            for g in args.group:
                targets.extend(group_leaf_members(g, proxies))
        else:
            targets = leaf_names(proxies)
        targets = list(dict.fromkeys(targets))[: max(1, args.delay_limit)]
        base = controller if controller.startswith(("http://", "https://")) else f"http://{controller}"
        results = []

        # 新版内核的 provider 节点不在 /proxies 里，单节点测速会 404，只能整组测。
        node_targets = [name for name in targets if name in raw_proxies]
        group_targets = [name for name in targets if name not in raw_proxies]
        mode = "node"
        if node_targets and group_targets:
            mode = "mixed"
        elif group_targets:
            mode = "group"

        with cf.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = [
                pool.submit(delay_one, base, secret, name, args.test_url, args.delay_timeout, unix_socket)
                for name in node_targets
            ]
            for fut in cf.as_completed(futures):
                name, delay_ms, error = fut.result()
                if delay_ms is not None:
                    results.append({"name": name, "delay": delay_ms})
                else:
                    results.append({"name": name, "delay": None, "error": error or "no response"})

        if group_targets:
            group_results = delay_group_targets(
                base, secret, group_targets, proxies, args.test_url, args.delay_timeout, preferred=args.group,
                unix_socket=unix_socket
            )
            for name in group_targets:
                delay_ms = group_results.get(name)
                if delay_ms is not None:
                    results.append({"name": name, "delay": delay_ms})
                else:
                    results.append({"name": name, "delay": None, "error": "整组测速未返回该节点"})

        delay = {
            "ran": True,
            "mode": mode,
            "testUrl": args.test_url,
            "timeoutMs": args.delay_timeout,
            "targets": len(targets),
            "results": sorted(results, key=lambda x: (x["delay"] is None, x["delay"] or 0)),
        }

    model = build_model(ctx, api, delay, subscriptions)
    model["apiOk"] = api_ok
    model["config"]["controller"] = controller
    report = render(model)

    if args.report:
        Path(args.report).expanduser().write_text(report, encoding="utf-8")
    if args.json:
        print(json.dumps(model, ensure_ascii=False, indent=2))
    else:
        print(report)
    return 0 if api_ok else 1


if __name__ == "__main__":
    sys.exit(main())
