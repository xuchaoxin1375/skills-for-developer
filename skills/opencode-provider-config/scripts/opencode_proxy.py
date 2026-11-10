#!/usr/bin/env python3
"""opencode_proxy.py — 检查、设置、移除 OpenCode V2 后台服务的代理环境变量。

做什么
    1. 三层对照：服务端存储（service.json 的 env 块）、live 服务进程实际继承的环境、
       当前 shell 的环境；三者对不上时点名是哪一层缺。
    2. 变量名审计：内置 `opencode service set env` 接受任意名字，写错（如 HPPTS_PROXY）
       也会成功落盘并出现在进程里，但没有任何 HTTP 客户端会读取，表现为"配了代理却全程直连"。
    3. NO_PROXY 检查：逗号分隔、回环地址是否存在。
    4. 连通性探测：对已配置的代理做一次有界 TCP 探活。
    5. 一次写盘：set/unset 直接读写 service.json（原子替换 + 备份），只需重启一次服务，
       不逐个 `service set env`（内置命令每次都会重启）。

不做什么
    - 不推测代理端口，不扫描端口段；URL 由使用者给出。
    - 不替代 `opencode service` 命令；存储格式不受支持时按退出码 3 拒绝写入并要求改用内置命令。
    - 不读取、不打印非代理类 env 的值（只报数量），避免密钥进入终端与日志。

用法
    python3 opencode_proxy.py status                       # 默认做 TCP 探活
    python3 opencode_proxy.py status --json --no-probe     # 机器可读、不出网
    python3 opencode_proxy.py set http://127.0.0.1:<port>   # 写 HTTP(S)_PROXY，合并 NO_PROXY，重启并核验
    python3 opencode_proxy.py set http://127.0.0.1:<port> --no-restart
    python3 opencode_proxy.py unset                        # 清代理变量，保留 NO_PROXY
    python3 opencode_proxy.py unset --all                  # 连 NO_PROXY 一起清

退出码
    0 正常；1 发现问题或核验未通过；2 用法/IO 错误；3 service.json 的 env 格式不受支持。

注意
    set/unset 默认重启后台服务，正在执行的会话内命令可能被打断（这是重启行为，不是失败）。
    在 OpenCode 会话内执行时建议加 --no-restart，另开会话外终端重启并复核。
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

SKILL_NAME = "opencode-provider-config"
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
CANONICAL = PROXY_VARS + ("NO_PROXY",)
LOOPBACK = ("localhost", "127.0.0.1", "::1")
FORMAT_OBJECT = "object"
FORMAT_STRING = "string"
FORMAT_MISSING = "missing"

EXIT_OK = 0
EXIT_PROBLEM = 1
EXIT_USAGE = 2
EXIT_FORMAT = 3

RESTART_TIMEOUT = 120.0
POLL_INTERVAL = 2.0
PROBE_TIMEOUT = 2.0
CMD_TIMEOUT = 15.0

ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)


class ServiceFormatError(RuntimeError):
    """service.json 的 env 块既不是对象也不是可解析的映射字符串。"""


# ---------------------------------------------------------------- 基础命令


def opencode_bin() -> str:
    return os.environ.get("OPENCODE_BIN") or shutil.which("opencode") or "opencode"


def run(cmd: list[str], timeout: float = CMD_TIMEOUT) -> str:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} 退出码 {proc.returncode}: {proc.stderr.strip()[:200]}")
    return proc.stdout


def resolve_service_json(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env_path = os.environ.get("OPENCODE_SERVICE_JSON")
    if env_path:
        return Path(env_path).expanduser()
    try:
        for line in run([opencode_bin(), "debug", "paths"]).splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "config":
                return Path(parts[1]).expanduser() / "service.json"
    except Exception:  # noqa: BLE001 - 拿不到路径就回落到平台默认位置
        pass
    candidates: list[Path] = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "opencode" / "service.json")
    candidates.append(Path.home() / ".config" / "opencode" / "service.json")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


# ---------------------------------------------------------------- 存储层读写


def load_service(path: Path) -> tuple[dict, dict[str, str], str]:
    """返回 (整个 service.json, env 映射, 原始格式标记)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    env = data.get("env")
    if env is None:
        return data, {}, FORMAT_MISSING
    if isinstance(env, dict):
        return data, {str(k): str(v) for k, v in env.items()}, FORMAT_OBJECT
    if isinstance(env, str):
        try:
            parsed = ast.literal_eval(env.strip())
        except (ValueError, SyntaxError) as exc:
            raise ServiceFormatError(
                f"{path} 的 env 是字符串且无法解析（{exc}）；请用 `opencode service set env` 重写后再运行本脚本"
            ) from exc
        if not isinstance(parsed, dict):
            raise ServiceFormatError(f"{path} 的 env 字符串解析结果不是映射：{type(parsed).__name__}")
        return data, {str(k): str(v) for k, v in parsed.items()}, FORMAT_STRING
    raise ServiceFormatError(f"{path} 的 env 类型不受支持：{type(env).__name__}")


def write_service(path: Path, data: dict, env: dict[str, str]) -> Path:
    """原子写入标准对象形式，返回备份文件路径。"""
    backup = path.with_name(f"{path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    payload = dict(data)
    payload["env"] = env
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".service.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return backup


# ---------------------------------------------------------------- 纯逻辑（可测）


def fold(env: dict[str, str]) -> dict[str, tuple[str, str]]:
    """按大写名归类，返回 {大写名: (原始名, 值)}；同名大小写并存时大写优先。"""
    folded: dict[str, tuple[str, str]] = {}
    for name, value in env.items():
        key = name.upper()
        if key not in folded or name == key:
            folded[key] = (name, value)
    return folded


def proxy_entries(env: dict[str, str]) -> dict[str, str]:
    folded = fold(env)
    return {key: folded[key][1] for key in PROXY_VARS if key in folded}


def audit_names(env: dict[str, str]) -> list[dict[str, str]]:
    """找出疑似拼错的代理变量名。"""
    issues: list[dict[str, str]] = []
    for name in env:
        upper = name.upper()
        if upper in CANONICAL:
            continue
        if not (upper.endswith("_PROXY") or upper == "PROXY"):
            continue
        match = difflib.get_close_matches(upper, list(CANONICAL), n=1, cutoff=0.6)
        issues.append({"name": name, "suggest": match[0] if match else ""})
    return issues


def no_proxy_value(env: dict[str, str]) -> str:
    folded = fold(env)
    return folded.get("NO_PROXY", ("", ""))[1]


def merge_no_proxy(existing: str, extra: tuple[str, ...] = LOOPBACK) -> str:
    """保持既有顺序、去重、补上默认项；空格分隔按逗号归一。"""
    items: list[str] = []
    seen: set[str] = set()
    for raw in existing.replace(" ", ",").split(","):
        item = raw.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    for item in extra:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            items.append(item)
    return ",".join(items)


def check_no_proxy(env: dict[str, str], proxy_configured: bool) -> list[str]:
    value = no_proxy_value(env)
    if not value:
        return ["未设置 NO_PROXY：本地回环请求也会走代理" ] if proxy_configured else []
    problems: list[str] = []
    if "," not in value and " " in value:
        problems.append("NO_PROXY 用空格分隔，部分客户端无法解析；应为逗号分隔")
    entries = [item.strip().lower() for item in value.split(",") if item.strip()]
    if proxy_configured and not any(item in LOOPBACK for item in entries):
        problems.append("NO_PROXY 未包含回环地址（localhost/127.0.0.1/::1）")
    return problems


def parse_proxy(url: str) -> dict[str, object]:
    raw = url or ""
    if not raw.strip():
        raise ValueError("代理 URL 不能为空")
    if raw != raw.strip() or any(ch.isspace() for ch in raw):
        raise ValueError("代理 URL 不能含空白字符")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"代理 URL 端口非法：{exc}") from exc
    if parts.scheme not in ("http", "https"):
        raise ValueError("仅支持 http/https 代理 URL（环境变量方式不适用于 socks 直写）")
    if not parts.hostname:
        raise ValueError("代理 URL 缺少主机名")
    return {
        "url": raw,
        "scheme": parts.scheme,
        "host": parts.hostname,
        "port": port or (443 if parts.scheme == "https" else 80),
        "auth": bool(parts.username or parts.password),
    }


def probe_tcp(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def evaluate(
    storage_env: dict[str, str],
    live_env: dict[str, str] | None,
    live_error: str | None,
) -> tuple[list[str], list[str]]:
    """返回 (problems, notes)。"""
    problems: list[str] = []
    notes: list[str] = []
    stored = proxy_entries(storage_env)
    live = proxy_entries(live_env or {})

    for issue in audit_names(storage_env):
        hint = f"，应为 {issue['suggest']}" if issue["suggest"] else ""
        problems.append(f"{issue['name']} 疑似拼写错误{hint}；HTTP 客户端不会读取该变量")
    problems.extend(check_no_proxy(storage_env, bool(stored) or bool(live)))

    if stored and live_env is None:
        notes.append(f"无法读取 live 进程环境（{live_error}），未能核验是否生效")
    if stored and live_env is not None:
        missing = [key for key in stored if live.get(key) != stored[key]]
        if missing:
            problems.append(
                "live 进程未加载或取值不同：" + "、".join(missing) + "（存储层已写入，需重启服务）"
            )
    if not stored and live:
        problems.append(
            "存储层没有代理变量，但 live 进程有：" + "、".join(sorted(live)) + "（重启后会丢失，请补写存储层）"
        )
    if not stored and not live:
        notes.append("未配置服务端代理，当前走直连")
    return problems, notes


# ---------------------------------------------------------------- live 侧观测


def service_pid() -> int | None:
    try:
        payload = json.loads(run([opencode_bin(), "api", "get", "/api/info"]))
        return int(payload["pid"])
    except Exception:  # noqa: BLE001 - 服务未运行或接口不可用都属于未取到
        return None


def process_start_time(pid: int) -> str:
    if os.name == "nt":
        try:
            out = run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Process -Id {pid}).StartTime.ToString('yyyy-MM-dd HH:mm:ss')",
                ]
            )
            return out.strip()
        except Exception:  # noqa: BLE001
            return "未知"
    try:
        return run(["ps", "-o", "lstart=", "-p", str(pid)]).strip()
    except Exception:  # noqa: BLE001
        return "未知"


def read_live_env(pid: int | None) -> tuple[dict[str, str] | None, str | None]:
    if not pid:
        return None, "服务未运行"
    if os.name == "nt":
        return None, "Windows 无受支持方式读取其他进程的环境变量"
    proc = Path(f"/proc/{pid}/environ")
    try:
        if proc.exists():
            raw = proc.read_bytes().decode("utf-8", "replace")
            pairs = {}
            for item in raw.split("\0"):
                if "=" in item:
                    key, value = item.split("=", 1)
                    pairs.setdefault(key, value)
            return (pairs or None), None
        out = run(["ps", "eww", "-p", str(pid)])
    except Exception as exc:  # noqa: BLE001
        return None, f"读取失败：{type(exc).__name__}: {exc}"
    pairs = {}
    for token in out.split():
        match = ENV_LINE.match(token)
        if match:
            pairs.setdefault(match.group(1), match.group(2))
    if not pairs:
        return None, "ps 未能读出环境变量（权限或平台限制）"
    return pairs, None


# ---------------------------------------------------------------- 输出


def render_status(report: dict) -> str:
    lines: list[str] = []
    storage = report["storage"]
    lines.append("OpenCode 代理状态")
    lines.append("")
    lines.append(f"存储层  {report['service_json']}  （env 格式：{storage['format']}）")
    if storage["proxy"]:
        for key in PROXY_VARS:
            if key in storage["proxy"]:
                lines.append(f"  {key:<12}{storage['proxy'][key]}")
        lines.append(f"  {'NO_PROXY':<12}{storage['no_proxy'] or '(未设置)'}")
    else:
        lines.append("  (无可识别的代理变量)")
    if storage["hidden"]:
        lines.append(f"  其他 env 变量 {storage['hidden']} 个（值已隐藏）")

    live = report["live"]
    lines.append("")
    if live["pid"]:
        lines.append(f"live 进程  pid {live['pid']}，启动 {live['started']}")
    else:
        lines.append("live 进程  (未运行)")
    if not live["known"]:
        lines.append(f"  无法读取：{live['error']}")
    elif live["proxy"]:
        for key in PROXY_VARS:
            if key in live["proxy"]:
                lines.append(f"  {key:<12}{live['proxy'][key]}")
        lines.append(f"  {'NO_PROXY':<12}{live['no_proxy'] or '(未设置)'}")
    else:
        lines.append("  (无代理变量)")

    shell = report["shell"]
    lines.append("")
    lines.append("当前 shell")
    if shell["proxy"]:
        for key in PROXY_VARS:
            if key in shell["proxy"]:
                lines.append(f"  {key:<12}{shell['proxy'][key]}")
    else:
        lines.append("  (无代理变量：--standalone / 前台 serve 不读服务端 env)")

    lines.append("")
    lines.append("NO_PROXY 检查")
    lines.append(f"  {report['no_proxy_value'] or '(未设置)'}")

    if report["probes"]:
        lines.append("")
        lines.append("代理可达性")
        for item in report["probes"]:
            mark = "可连" if item["ok"] else f"不可连（{item['error']}）"
            lines.append(f"  {item['url']} → TCP {mark}")

    audit = report["audit"]
    if audit:
        lines.append("")
        lines.append("变量名审计")
        for item in audit:
            hint = f" → 应为 {item['suggest']}" if item["suggest"] else ""
            lines.append(f"  {item['name']}{hint}")

    problems = report["problems"]
    notes = report["notes"]
    lines.append("")
    lines.append("结论")
    if problems:
        for item in problems:
            lines.append(f"  ✗ {item}")
    else:
        lines.append("  ✓ 未发现代理配置问题")
    for item in notes:
        lines.append(f"  · {item}")
    if problems:
        lines.append("")
        lines.append("修复：python3 opencode_proxy.py set <代理URL>（或按上方提示改用内置命令）")
    return "\n".join(lines)


# ---------------------------------------------------------------- 子命令


def cmd_status(args: argparse.Namespace) -> int:
    path = resolve_service_json(args.service_json)
    if not path.exists():
        print(f"找不到 {path}；确认 OpenCode 已初始化并至少启动过一次服务", file=sys.stderr)
        return EXIT_USAGE
    try:
        data, env, fmt = load_service(path)
    except ServiceFormatError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FORMAT
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取 {path} 失败：{exc}", file=sys.stderr)
        return EXIT_USAGE

    pid = service_pid()
    live_env, live_error = read_live_env(pid)
    problems, notes = evaluate(env, live_env, live_error)

    probes = []
    if not args.no_probe:
        urls = set(proxy_entries(env).values()) | set(proxy_entries(live_env or {}).values())
        for url in sorted(urls):
            try:
                info = parse_proxy(url)
            except ValueError as exc:
                problems.append(f"代理 URL 不合法：{url}（{exc}）")
                continue
            ok, error = probe_tcp(str(info["host"]), int(info["port"]), args.timeout)
            probes.append({"url": url, "ok": ok, "error": error})
            if not ok:
                problems.append(f"代理不可达：{url}（{error}）")

    audit = audit_names(env)
    report = {
        "service_json": str(path),
        "storage": {
            "format": fmt,
            "proxy": proxy_entries(env),
            "no_proxy": no_proxy_value(env),
            "hidden": max(0, len(env) - len(proxy_entries(env)) - (1 if no_proxy_value(env) else 0)),
        },
        "live": {
            "pid": pid,
            "started": process_start_time(pid) if pid else "",
            "known": live_env is not None,
            "proxy": proxy_entries(live_env or {}),
            "no_proxy": no_proxy_value(live_env or {}),
            "error": live_error,
        },
        "shell": {
            "proxy": proxy_entries({k: v for k, v in os.environ.items() if k.upper() in CANONICAL}),
        },
        "no_proxy_value": no_proxy_value(env),
        "probes": probes,
        "audit": audit,
        "problems": problems,
        "notes": notes,
        "ok": not problems,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_status(report))
    return EXIT_OK if not problems else EXIT_PROBLEM


def restart_and_verify(
    expect_present: tuple[str, ...], expect_absent: tuple[str, ...], timeout: float
) -> tuple[bool, list[str]]:
    old_pid = service_pid()
    log_path = Path(tempfile.gettempdir()) / "opencode-proxy-restart.log"
    kwargs: dict[str, object] = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    with open(log_path, "ab") as handle:
        subprocess.Popen([opencode_bin(), "service", "restart"], stdout=handle, stderr=handle, **kwargs)

    deadline = time.time() + timeout
    new_pid = None
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        new_pid = service_pid()
        if new_pid and new_pid != old_pid:
            break
    messages: list[str] = []
    if not new_pid or new_pid == old_pid:
        messages.append(f"等待 {timeout:.0f}s 仍未观察到新服务进程；重启日志见 {log_path}")
        return False, messages

    live_env, error = read_live_env(new_pid)
    if live_env is None:
        messages.append(f"新进程 pid {new_pid} 已就绪，但无法核验其环境变量（{error}）")
        return False, messages
    folded = fold(live_env)
    missing = [name for name in expect_present if name not in folded]
    leftover = [name for name in expect_absent if name in folded]
    if missing:
        messages.append("新进程缺少变量：" + "、".join(missing))
    if leftover:
        messages.append("新进程仍有变量：" + "、".join(leftover))
    return (not missing and not leftover), messages


def cmd_set(args: argparse.Namespace) -> int:
    path = resolve_service_json(args.service_json)
    if not path.exists():
        print(f"找不到 {path}；确认 OpenCode 已初始化", file=sys.stderr)
        return EXIT_USAGE
    try:
        data, env, fmt = load_service(path)
        info = parse_proxy(args.url)
    except ServiceFormatError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FORMAT
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return EXIT_USAGE

    target = str(info["url"])
    dropped = sorted(issue["name"] for issue in audit_names(env))
    for name in dropped:
        env.pop(name, None)
    for key in ("HTTP_PROXY", "HTTPS_PROXY"):
        env[key] = target
        if key.lower() in env:
            env[key.lower()] = target
    existing = no_proxy_value(env)
    extra = tuple(item.strip() for item in (args.no_proxy or "").split(",") if item.strip())
    merged = merge_no_proxy(existing, LOOPBACK + extra)
    env["NO_PROXY"] = merged
    if "no_proxy" in env:
        env["no_proxy"] = merged

    backup = write_service(path, data, env)
    result: dict[str, object] = {
        "service_json": str(path),
        "backup": str(backup),
        "migrated_format": fmt == FORMAT_STRING,
        "dropped_typos": dropped,
        "written": {"HTTP_PROXY": target, "HTTPS_PROXY": target, "NO_PROXY": merged},
        "restarted": False,
        "verified": False,
    }
    messages: list[str] = []
    if args.no_restart:
        messages.append("已写入存储层，未重启；重启后生效")
    else:
        ok, details = restart_and_verify(("HTTP_PROXY", "HTTPS_PROXY"), (), args.timeout)
        result["restarted"] = True
        result["verified"] = ok
        messages.extend(details)
        if not ok:
            messages.append("存储层已写入，但新进程未通过核验；按详情排查后重试")

    if args.json:
        result["messages"] = messages
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"已写入 {path}（备份 {backup.name}）")
        if result["migrated_format"]:
            print("env 已从字符串迁移为标准对象格式")
        if dropped:
            print("已移除拼错的代理变量：" + "、".join(dropped))
        print(f"  HTTP_PROXY  {target}")
        print(f"  HTTPS_PROXY {target}")
        print(f"  NO_PROXY    {merged}")
        if info["auth"]:
            print("  提示：URL 含账号密码，已按原样写入；代理回 407 时检查百分号编码")
        for item in messages:
            print(f"  {item}")
    if args.no_restart:
        return EXIT_OK
    return EXIT_OK if result["verified"] else EXIT_PROBLEM


def cmd_unset(args: argparse.Namespace) -> int:
    path = resolve_service_json(args.service_json)
    if not path.exists():
        print(f"找不到 {path}；确认 OpenCode 已初始化", file=sys.stderr)
        return EXIT_USAGE
    try:
        data, env, fmt = load_service(path)
    except ServiceFormatError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FORMAT

    removed: list[str] = []
    typos = {issue["name"] for issue in audit_names(env)}
    for name in list(env):
        if name.upper() in PROXY_VARS or name in typos:
            removed.append(name)
            env.pop(name, None)
    if args.all:
        for name in list(env):
            if name.upper() == "NO_PROXY":
                removed.append(name)
                env.pop(name, None)

    if not removed:
        print("没有可移除的代理变量（NO_PROXY 默认保留，如需一并清理加 --all）")
        return EXIT_OK

    backup = write_service(path, data, env)
    result: dict[str, object] = {
        "service_json": str(path),
        "backup": str(backup),
        "removed": sorted(removed),
        "kept_no_proxy": "NO_PROXY" in env or "no_proxy" in env,
        "restarted": False,
        "verified": False,
    }
    messages: list[str] = []
    if args.no_restart:
        messages.append("已写入存储层，未重启；重启后生效")
    else:
        ok, details = restart_and_verify((), tuple(removed), args.timeout)
        result["restarted"] = True
        result["verified"] = ok
        messages.extend(details)

    if args.json:
        result["messages"] = messages
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"已写入 {path}（备份 {backup.name}）")
        print("移除：" + "、".join(sorted(removed)))
        if result["kept_no_proxy"]:
            print("保留：NO_PROXY（如需一并清理加 --all）")
        for item in messages:
            print(f"  {item}")
    if args.no_restart:
        return EXIT_OK
    return EXIT_OK if result["verified"] else EXIT_PROBLEM


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--service-json", help="service.json 路径；默认取 `opencode debug paths` 的 config 目录")
    common.add_argument("--json", action="store_true", help="输出机器可读 JSON")

    parser = argparse.ArgumentParser(
        prog="opencode_proxy.py",
        description="检查、设置、移除 OpenCode V2 后台服务的代理环境变量（三层对照 + 变量名审计 + 单次重启）。",
        epilog="退出码：0 正常；1 发现问题或核验未通过；2 用法/IO 错误；3 service.json 的 env 格式不受支持。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", parents=[common], help="检查存储层、live 进程、shell 与代理可达性")
    status.add_argument("--no-probe", action="store_true", help="跳过 TCP 探活（不出网）")
    status.add_argument("--timeout", type=float, default=PROBE_TIMEOUT, help=f"单次 TCP 探活超时秒数，默认 {PROBE_TIMEOUT}")
    status.set_defaults(func=cmd_status)

    setter = sub.add_parser("set", parents=[common], help="写入 HTTP(S)_PROXY，合并 NO_PROXY，重启并核验")
    setter.add_argument("url", help="代理 URL，如 http://127.0.0.1:<port>")
    setter.add_argument("--no-proxy", default="", help="追加的 NO_PROXY 条目（逗号分隔），回环地址会自动补齐")
    setter.add_argument("--no-restart", action="store_true", help="只写存储层，不重启服务")
    setter.add_argument("--timeout", type=float, default=RESTART_TIMEOUT, help=f"等待重启生效的秒数，默认 {RESTART_TIMEOUT:.0f}")
    setter.set_defaults(func=cmd_set)

    unset = sub.add_parser("unset", parents=[common], help="移除代理变量（默认保留 NO_PROXY）")
    unset.add_argument("--all", action="store_true", help="连 NO_PROXY 一起移除")
    unset.add_argument("--no-restart", action="store_true", help="只写存储层，不重启服务")
    unset.add_argument("--timeout", type=float, default=RESTART_TIMEOUT, help=f"等待重启生效的秒数，默认 {RESTART_TIMEOUT:.0f}")
    unset.set_defaults(func=cmd_unset)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return EXIT_USAGE
    except OSError as exc:
        print(f"IO 错误：{exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
