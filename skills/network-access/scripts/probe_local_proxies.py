#!/usr/bin/env python3
"""按进程名匹配本机代理，探测它实际监听的端口，默认 5 秒内给结论。

做什么
    1. 列举本机进程，按代理家族名匹配（mihomo/clash/verge、xray/v2ray、sing-box、ss/trojan/hysteria…）。
    2. 取这些进程**实际监听的端口**（不是猜常见端口表），逐个做一次有界探测：
       先 TCP 探活，再按协议试一次（登记声明的协议优先，另一个随后），取回目标并读出口回显。
    3. 另外把登记文件 ~/.config/proxy-resources.json 里的端口与 --port 指定的端口一并探。
    谁先出结果谁先打，不等整轮。

不做什么
    - 不猜端口、不扫端口段：候选只来自「进程名匹配到的监听端口」＋「登记」＋「--port」。
    - 不断言"没有代理"：进程与端口两张表有共同盲区——代理跑在 WSL/虚拟机/容器里时，
      宿主看不到该进程也看不到监听条目；TUN/透明路由同样不进表。**超时太久一律记 unknown。**

用法
    python -X utf8 scripts/probe_local_proxies.py                    # 默认 5 秒预算
    python -X utf8 scripts/probe_local_proxies.py --match my-proxy   # 追加自定义进程名（正则，可重复）
    python -X utf8 scripts/probe_local_proxies.py --only-match xray  # 只用自定义正则，忽略内置家族表
    python -X utf8 scripts/probe_local_proxies.py --port 7890        # 补一个宿主看不到进程的端口
    python -X utf8 scripts/probe_local_proxies.py --budget 20 --timeout 6   # 要排干净时放宽
    python -X utf8 scripts/probe_local_proxies.py --copy             # 给出可直接粘贴的代理环境变量行
    python -X utf8 scripts/probe_local_proxies.py --watch 30         # 常驻重扫，只报可用端口的增删
    python -X utf8 scripts/probe_local_proxies.py --json             # 机器可读；进度走 stderr

退出码：0 至少一个可用；1 探过但都不可用；2 没有候选。仅标准库。
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import io
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

DEFAULT_URL = "https://www.cloudflare.com/cdn-cgi/trace"
DEFAULT_BUDGET = 5.0  # 总预算（含枚举与探测）；到点未完成的端口记 unknown
DEFAULT_TIMEOUT = 2.5  # 单次探测上限；总预算才是硬上限
REGISTRY = Path.home() / ".config" / "proxy-resources.json"
UA = "probe-local-proxies/1.2"

# 家族进程名线索。一律用具体模式：两字母的 ss/ray 会误命中 csrss/lsass/CrossDevice…
FAMILIES = (
    ("mihomo/clash", re.compile(r"mihomo|clash|verge|flclash", re.I)),
    ("v2ray/xray", re.compile(r"xray|v2ray|nekoray", re.I)),
    ("sing-box", re.compile(r"sing-box|singbox|nekobox|hiddify|karing", re.I)),
    ("other-tunnels", re.compile(r"ss-local|shadowsocks|trojan|hysteria|tuic|naive", re.I)),
    ("gui/tun", re.compile(r"surge|quantumult|stash|loon|netch|proxifier|surfboard|warp", re.I)),
)
LOOPBACK_HOSTS = {"127.0.0.1", "0.0.0.0", "::", "::1", "[::]", "[::1]", "localhost"}

# 人读模式流式打 stdout；--json 时进度走 stderr，stdout 只留 JSON。每条都 flush。
_OUT = sys.stdout


def say(msg):
    print(msg, file=_OUT, flush=True)


def left(deadline):
    return max(0.0, deadline - time.monotonic())


def run(cmd):
    """跑一个只读的枚举命令；失败返回空串（枚举是线索，不是成败判据）。"""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10, errors="replace").stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def mask(url):
    """去掉代理 URL 里的凭据，报告只出现协议+主机+端口。"""
    try:
        u = urlsplit(url if "://" in url else f"http://{url}")
        return f"{u.scheme}://{u.hostname or ''}{(f':{u.port}') if u.port else ''}"
    except ValueError:
        return "<unparsable>"


def list_processes():
    """[(pid, name)]，跨平台尽力而为。"""
    out = []
    if os.name == "nt":
        for row in csv.reader(io.StringIO(run(["tasklist", "/fo", "csv", "/nh"]))):
            if len(row) >= 2 and row[1].strip().isdigit():
                out.append((row[1].strip(), row[0].strip()))
        return out
    proc = Path("/proc")
    if proc.is_dir():
        for entry in proc.iterdir():
            if entry.name.isdigit():
                try:
                    out.append((entry.name, (entry / "comm").read_text(errors="replace").strip()))
                except OSError:
                    pass
        if out:
            return out
    for line in run(["ps", "-eo", "pid=,comm="]).splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out.append((parts[0], parts[1].strip()))
    return out


def compile_extra(patterns):
    """把 --match 给的正则编译成家族表项；非法正则抛 ValueError 交给 argparse 报用法错误。

    统一加 re.IGNORECASE：Windows 进程名大小写与写法都不稳（Xray.exe / xray），
    诊断脚本按"能命中"优先；要精确大小写就在模式里写 (?-i)。
    """
    out = []
    for pat in patterns:
        out.append(("custom", re.compile(pat, re.I)))
    return out


def match_families(procs, extra=(), only=False):
    """[(family, pid, name)]：进程名命中代理家族的进程。

    extra 是 --match 编译出的自定义家族表；only=True 时忽略内置表，只用 extra——
    内置表刻意放宽（verge/clash/xray 都在内），想只看自己认识的名字时用 --only-match。
    """
    table = tuple(extra) + (() if only else FAMILIES)
    hits = []
    for pid, name in procs:
        for family, pattern in table:
            if pattern.search(name):
                hits.append((family, pid, name))
                break
    return hits


def list_listening():
    """[(host, port, pid)]，本机 LISTENING 的 TCP 端口；pid 尽力而为，取不到给空串。"""
    out = []
    if os.name == "nt":
        for line in run(["netstat", "-ano", "-p", "tcp"]).splitlines():
            m = re.match(r"\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)", line)
            if m and m.group(1) in LOOPBACK_HOSTS:
                out.append((m.group(1), int(m.group(2)), m.group(3)))
        return out
    # Linux/macOS：ss 能带出 users:(("name",pid=N))，用它把端口挂到进程上
    for line in run(["ss", "-ltnpH"]).splitlines() + ([] if os.name == "nt" else run(["ss", "-ltnp"]).splitlines()):
        m = re.search(r"(\S+):(\d+)\s", line)
        if not m:
            continue
        host, port = m.group(1), int(m.group(2))
        if host not in LOOPBACK_HOSTS:
            continue
        pm = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        out.append((host, port, pm.group(2) if pm else ""))
    if not out:  # 兜底：只有端口，没有 pid
        for line in run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"]).splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 9 and parts[8].startswith("TCP") and ":" in parts[8]:
                h, _, p = parts[8].rpartition(":")
                if p.isdigit() and h in LOOPBACK_HOSTS:
                    out.append((h, int(p), parts[1]))
    # 去重
    return sorted(set(out))


def tcp_open(host, port, timeout):
    if timeout <= 0.05:
        return None
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise OSError("connection closed mid-handshake")
        buf += chunk
    return buf


def fetch_with(opener, url, timeout):
    req = urlreq.Request(url, headers={"user-agent": UA, "accept": "*/*"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except HTTPError as e:
        return e.code, (e.read().decode("utf-8", "replace") if e.fp else "")


def fetch_via_http(proxy_url, url, timeout):
    """http 代理：urllib 的 ProxyHandler，https 目标自动走 CONNECT 隧道。"""
    return fetch_with(urlreq.build_opener(urlreq.ProxyHandler({"http": proxy_url, "https": proxy_url})), url, timeout)


def fetch_via_socks5(host, port, url, timeout):
    """socks5h（域名交代理解析）+ 自己发 HTTP/1.1，约 40 行，免第三方依赖。"""
    u = urlsplit(url)
    target, tport = u.hostname, u.port or (443 if u.scheme == "https" else 80)
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        sock.sendall(b"\x05\x01\x00")  # 无认证
        if recv_exact(sock, 2)[1] != 0:
            raise OSError("socks5 greeting rejected")
        name = target.encode("idna")
        sock.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + tport.to_bytes(2, "big"))
        head = recv_exact(sock, 4)
        if head[1] != 0:
            raise OSError(f"socks5 connect failed (rep={head[1]})")
        atyp = head[3]
        if atyp == 1:
            recv_exact(sock, 6)
        elif atyp == 4:
            recv_exact(sock, 18)
        elif atyp == 3:
            recv_exact(sock, recv_exact(sock, 1)[0] + 2)
        else:
            raise OSError(f"socks5 unknown atyp={atyp}")
        stream = ssl.create_default_context().wrap_socket(sock, server_hostname=target) if u.scheme == "https" else sock
        try:
            path = (u.path or "/") + (f"?{u.query}" if u.query else "")
            stream.sendall(f"GET {path} HTTP/1.1\r\nhost: {target}\r\nuser-agent: {UA}\r\naccept: */*\r\nconnection: close\r\n\r\n".encode())
            data = b""
            while True:
                chunk = stream.recv(65536)
                if not chunk:
                    break
                data += chunk
        finally:
            if stream is not sock:
                stream.close()
    finally:
        sock.close()
    head, _, body = data.decode("utf-8", "replace").partition("\r\n\r\n")
    m = re.match(r"HTTP/\d\.\d\s+(\d+)", head)
    return (int(m.group(1)) if m else 0), body


def parse_egress(body):
    info = {}
    for line in body.splitlines():
        if "=" in line and line.split("=", 1)[0] in ("ip", "colo", "loc"):
            k, v = line.split("=", 1)
            info[k] = v.strip()
    return info


def probe(scheme, host, port, url, timeout, deadline):
    """一次有界探测，返回结果 dict（ok/status/seconds/egress/error）。"""
    budget = min(timeout, left(deadline))
    if budget <= 0.05:
        return {"ok": False, "status": None, "seconds": 0.0, "egress": {}, "error": "no budget left"}
    started = time.time()
    try:
        if scheme == "http":
            status, body = fetch_via_http(f"http://{host}:{port}", url, budget)
        else:
            status, body = fetch_via_socks5(host, port, url, budget)
        ok = status == 200
        return {"ok": ok, "status": status, "seconds": round(time.time() - started, 2),
                "egress": parse_egress(body), "error": None if ok else f"HTTP {status}"}
    except (OSError, URLError, ValueError, ssl.SSLError) as e:
        return {"ok": False, "status": None, "seconds": round(time.time() - started, 2),
                "egress": {}, "error": f"{type(e).__name__}: {e}"[:140]}
    except Exception as e:  # 防御：探测线程里的意外不该拖垮整轮
        return {"ok": False, "status": None, "seconds": round(time.time() - started, 2),
                "egress": {}, "error": f"unexpected {type(e).__name__}: {e}"[:140]}


def kind_of(res):
    """失败性质：只有对方按协议语义回了话（问候被拒/4xx/连接被拒）才算不可用；超时与中断属未知。"""
    if res.get("ok"):
        return "ok"
    err = res.get("error") or ""
    if "no budget" in err:
        return "no-budget"
    if "TimeoutError" in err or "timed out" in err:
        return "timeout"
    if "EOF" in err:
        return "unknown"
    if "greeting rejected" in err or "connect failed (rep=" in err:
        return "rejected"
    if "ConnectionRefused" in err or "10061" in err or "actively refused" in err or "拒绝" in err:
        return "refused"
    return "rejected"


def verdict_of(entry, protocols):
    """三态：usable / not a proxy（有语义证据）/ unknown（超时、预算、TCP 无应答）。"""
    ok = [p for p in protocols if entry["protocols"].get(p, {}).get("ok")]
    if ok:
        return "usable (mixed)" if len(ok) == len(protocols) and len(protocols) > 1 else f"usable ({ok[0]})"
    if entry["tcpOpen"] is False:
        return "not listening"
    if entry["tcpOpen"] is None:
        return "unknown (no budget for TCP check)"
    kinds = [kind_of(entry["protocols"][p]) for p in protocols if p in entry["protocols"]]
    if "no-budget" in kinds:
        return "unknown (budget exhausted)"
    if any(k in ("timeout", "unknown") for k in kinds):
        return f"unknown ({next(k for k in kinds if k in ('timeout', 'unknown'))})"
    if kinds and all(k in ("rejected", "refused") for k in kinds):
        return f"not a proxy ({'+'.join(sorted(set(kinds)))})"
    return "unknown"


def load_registry():
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for e in data.get("proxies") or []:
        u = urlsplit(str(e.get("url", "")))
        if u.hostname and u.port:
            out.append({"host": u.hostname, "port": u.port, "scheme": u.scheme, "name": e.get("name", "?")})
    return out


def build_candidates(args, registry, procs_hits, listening):
    """候选 = 命中进程实际监听的端口 ∪ 登记条目 ∪ --port。不猜端口、不扫端口段。"""
    cand = {}

    def add(host, port, source, scheme=None):
        host = "127.0.0.1" if host in LOOPBACK_HOSTS else host
        it = cand.setdefault((host, port), {"host": host, "port": port, "sources": [], "scheme": None})
        if source and source not in it["sources"]:
            it["sources"].append(source)
        if scheme in ("http", "socks5") and not it["scheme"]:
            it["scheme"] = scheme

    # 1) 进程名匹配到的进程 → 它自己监听的端口
    proc_names = {pid: name for _, pid, name in procs_hits}
    for host, port, pid in listening:
        if pid and pid in proc_names:
            add(host, port, f"proc:{proc_names[pid]}")
    # 2) 登记条目（宿主看不到进程时，登记是唯一的入口线索）
    for e in registry:
        add(e["host"], e["port"], f"registry:{e['name']}", e["scheme"])
    # 3) 显式指定
    for p in args.port:
        add("127.0.0.1", p, "cli")

    def rank(it):
        s = " ".join(it["sources"])
        return 0 if ("cli" in s or "proc:" in s) else 1
    return [cand[k] for k in sorted(cand, key=lambda k: (rank(cand[k]), k[1]))]


def probe_candidate(item, protocols, args, deadline):
    """一个候选：TCP 探活 → 逐协议试，任一成功即停（预算允许时补另一协议以标注 mixed）。"""
    entry = {"host": item["host"], "port": item["port"], "sources": item["sources"], "protocols": {}, "verdict": ""}
    host, port = item["host"], item["port"]
    if left(deadline) <= 0.05:
        entry["tcpOpen"] = None
        entry["verdict"] = "unknown (budget exhausted)"
        return entry
    entry["tcpOpen"] = tcp_open(host, port, min(args.timeout, left(deadline), 0.5))
    if entry["tcpOpen"] is False:
        entry["verdict"] = "not listening"
        return entry
    order = ([item["scheme"]] if item["scheme"] in protocols else []) + [p for p in protocols if p != item["scheme"]]
    for proto in order:
        if left(deadline) <= 0.05:
            entry["protocols"][proto] = {"ok": False, "status": None, "seconds": 0.0, "egress": {}, "error": "no budget left"}
            continue
        entry["protocols"][proto] = probe(proto, host, port, args.url, args.timeout, deadline)
        if entry["protocols"][proto]["ok"]:
            # 成功即停；还有预算就补另一个协议，用于分辨 mixed 与单协议
            rest = order[order.index(proto) + 1:]
            if rest and left(deadline) > 0.05:
                entry["protocols"][rest[0]] = probe(rest[0], host, port, args.url, args.timeout, deadline)
            break
    entry["verdict"] = verdict_of(entry, protocols)
    return entry


def fmt_result(proto, res):
    if res["ok"]:
        extra = f" egress={res['egress']['ip']}" if res["egress"].get("ip") else ""
        return f"{proto} 200 {res['seconds']}s{extra}"
    return f"{proto} fail {res['seconds']}s ({kind_of(res)})"


def fmt_candidate(entry):
    detail = " | ".join(fmt_result(p, r) for p, r in entry["protocols"].items())
    return f"probe: {entry['host']}:{entry['port']:<7} {detail}  -> {entry['verdict']}"


def probe_direct(url, timeout, deadline):
    budget = min(timeout, left(deadline))
    if budget <= 0.05:
        return {"ok": False, "status": None, "seconds": 0.0, "egress": {}, "error": "no budget left"}
    started = time.time()
    try:
        status, body = fetch_with(urlreq.build_opener(urlreq.ProxyHandler({})), url, budget)
        return {"ok": status == 200, "status": status, "seconds": round(time.time() - started, 2),
                "egress": parse_egress(body), "error": None}
    except (OSError, URLError) as e:
        return {"ok": False, "status": None, "seconds": round(time.time() - started, 2),
                "egress": {}, "error": f"{type(e).__name__}: {e}"[:140]}


def scan_once(args, protocols, deadline, stream, extra=()):
    """跑一轮枚举 + 探测。stream=True 时逐条打进度（人读模式）。返回 report；无候选返回 None。"""
    started = time.monotonic()
    procs = list_processes() if left(deadline) > 0.1 else []
    hits = match_families(procs, extra, args.only_match)
    listening = list_listening() if left(deadline) > 0.1 else []
    registry = load_registry()
    cands = build_candidates(args, registry, hits, listening)

    if stream:
        for family, pid, name in hits:
            say(f"probe: 进程命中 {family:<14} pid={pid:<7} {name}")
    # 命中进程却一个端口都没挂上：端口表取不到归属（权限/WSL/容器），这才值得提示。不猜端口。
    matched_pids = {pid for _, pid, _ in hits}
    attributed = {pid for _, _, pid in listening if pid in matched_pids}
    if matched_pids and not attributed and stream:
        names = ", ".join(f"{n}(pid={p})" for _, p, n in hits)
        say(f"probe: 注意 命中进程未挂上任何监听端口：{names}；宿主可能看不到它的端口，用 --port 补")

    if not cands:
        if stream:
            say("no candidates: 没有候选端口（进程未命中、登记为空、--port 未给）。这不等于本机没有代理。")
        return None

    if stream:
        proc_n = sum(1 for c in cands if any(s.startswith("proc:") for s in c["sources"]))
        custom = f"，自定义模式 {len(extra)} 个" if extra else ""
        say(f"probe: {len(cands)} 个候选端口（进程 {proc_n} 个 / 登记 {len(registry)} 条 / --port {len(args.port)} 个），预算 {args.budget}s，单次上限 {args.timeout}s{custom}")
    report = {"url": args.url, "budget": args.budget, "timeout": args.timeout, "direct": None,
              "processesMatched": [{"family": f, "pid": p, "name": n} for f, p, n in hits],
              "candidates": [], "summary": {}, "blindSpots": []}

    # 候选同批并发：候选多时串行跑不完 5 秒预算。
    # 每个候选内部仍串行（TCP 探活 → 逐协议），每次探测都被剩余预算裁剪，所以整体不超预算。
    ordered = [None] * len(cands)
    with cf.ThreadPoolExecutor(max_workers=max(1, min(args.workers, len(cands) + 1))) as pool:
        jobs = {pool.submit(probe_candidate, item, protocols, args, deadline): ("cand", i) for i, item in enumerate(cands)}
        jobs[pool.submit(probe_direct, args.url, args.timeout, deadline)] = ("direct", -1)
        for fut in cf.as_completed(jobs):
            kind, i = jobs[fut]
            if kind == "direct":
                d = fut.result()
                report["direct"] = d
                if stream:
                    say(f"probe: direct 对照 {'200' if d['ok'] else 'fail'} {d['seconds']}s egress={d['egress'].get('ip') or '-'}")
                continue
            entry = fut.result()
            ordered[i] = entry
            if stream and entry["verdict"] != "not listening":
                say(fmt_candidate(entry))
    report["candidates"] = ordered

    # 直连对照用于识别 TUN/透明路由：出口与直连相同 = 可疑，可能该端口并没真正生效
    d = report["direct"] or {}
    for c in report["candidates"]:
        if not c["verdict"].startswith("usable"):
            continue
        ip = next((r["egress"].get("ip") for r in c["protocols"].values() if r["ok"] and r["egress"].get("ip")), None)
        if ip and d.get("egress", {}).get("ip"):
            c["egressMatchesDirect"] = ip == d["egress"]["ip"]
            if c["egressMatchesDirect"] and stream:
                say(f"probe: 注意 {c['host']}:{c['port']} 出口与直连相同——可能没真正生效或被 TUN 接管")

    elapsed = round(time.monotonic() - started, 2)
    count = lambda pre: len([c for c in report["candidates"] if c["verdict"].startswith(pre)])
    report["summary"] = {
        "usable": count("usable"),
        "notAProxy": count("not a proxy"),
        "unknown": count("unknown"),
        "notListening": count("not listening"),
        "elapsedSeconds": elapsed,
        "budgetSeconds": args.budget,
    }
    # 结构化可用清单：让读 --json 的 agent 不必自己从 candidates 里过滤排序
    report["usable"] = [
        {"host": c["host"], "port": c["port"], "url": url_of(c), "protocols": ok_protocols(c),
         "egress": egress_of(c), "sources": c["sources"], "verdict": c["verdict"],
         "egressMatchesDirect": bool(c.get("egressMatchesDirect"))}
        for c in sorted_usable(report)
    ]
    report["blindSpots"] = [
        "进程表与端口表的共同盲区：代理跑在 WSL/虚拟机/容器里时宿主看不到该进程与其监听端口，TUN/透明路由也不进表——这类入口只能靠 --port 或登记补",
        "内置家族名表只覆盖常见客户端（mihomo/clash/verge、xray/v2ray、sing-box、ss/trojan/hysteria、surge/warp 等）；小众客户端用 --match 加正则，想收窄用 --only-match",
        "只探命中进程自己监听的端口与登记/--port 给的端口；不猜端口表、不扫端口段",
        f"超时与预算到点记 unknown，不代表该端口不是代理（当前单次上限 {args.timeout}s、总预算 {args.budget}s，放宽用 --timeout / --budget）",
    ]
    return report


def usable_of(report):
    return [c for c in report["candidates"] if c["verdict"].startswith("usable")]


def ok_protocols(entry):
    return [p for p in ("http", "socks5") if entry["protocols"].get(p, {}).get("ok")]


def url_of(entry):
    """可用入口的 URL：优先 http（HTTP(S)_PROXY 能直接用），只有 socks5 通才给 socks5://。"""
    return f"http://{entry['host']}:{entry['port']}" if "http" in ok_protocols(entry) else f"socks5://{entry['host']}:{entry['port']}"


def best_seconds(entry):
    return min((r["seconds"] for r in entry["protocols"].values() if r["ok"]), default=float("inf"))


def egress_of(entry):
    return next((r["egress"].get("ip") for r in entry["protocols"].values() if r["ok"] and r["egress"].get("ip")), None)


def sorted_usable(report):
    """可用入口排序：可用协议多的在前（mixed 先于单协议），同档按最快一次探测耗时。"""
    return sorted(usable_of(report), key=lambda c: (-len(ok_protocols(c)), best_seconds(c)))


def source_text(entry):
    """候选来源的人话：进程名 / 登记名 / --port。"""
    parts = []
    for src in entry["sources"]:
        if src.startswith("proc:"):
            parts.append(f"进程 {src[5:]}")
        elif src.startswith("registry:"):
            parts.append(f"登记 {src[9:]}")
        elif src == "cli":
            parts.append("--port 指定")
        else:
            parts.append(src)
    return " / ".join(parts)


def recap(report, args):
    """收尾整理：把候选按结论分堆点名——可用的是哪几个（给 URL、出口、来源），
    不可判定/不是代理入口/未监听又是哪几个。人读模式的结论就靠这一块。"""
    s = report["summary"]
    say(f"probe: 用时 {s['elapsedSeconds']}s / 预算 {args.budget}s")
    say(f"summary: usable={s['usable']} not-a-proxy={s['notAProxy']} unknown={s['unknown']} not-listening={s['notListening']}")

    usable = sorted_usable(report)
    if usable:
        say(f"probe: 可用入口 {len(usable)} 个（协议多的在前，同档按耗时）：")
        for i, c in enumerate(usable, 1):
            egress = egress_of(c) or "-"
            tag = "  [出口与直连相同，可能没真正生效]" if c.get("egressMatchesDirect") else ""
            lead = "   ← 首选" if i == 1 else ""
            say(f"  {i}. {url_of(c):<26} {c['verdict']:<15} 出口 {egress:<18} 来自 {source_text(c)}{tag}{lead}")
        say("probe: 要把它贴进环境变量：加 --copy（只输出，不改你的配置）")
    else:
        say("probe: 本轮没有可用入口——先看下面的不可判定项与盲区，加大 --budget/--timeout 再试，别就此判「本机没有代理」。")

    groups = [
        ("不可判定", "unknown", "预算内没取回内容，不等于「不是代理」；加大 --timeout/--budget 重试"),
        ("不是代理入口", "not a proxy", "对方按协议语义回了话（如 CONNECT 4xx、socks 问候被拒）"),
        ("未监听", "not listening", "TCP 探活就没通，登记/--port 里的陈旧条目常见"),
    ]
    for label, prefix, why in groups:
        items = sorted((c for c in report["candidates"] if c["verdict"].startswith(prefix)), key=lambda c: c["port"])
        if not items:
            continue
        ports = "、".join(f"{c['port']}（{c['verdict'].split('(')[-1].rstrip(')')}）" if "(" in c["verdict"] else str(c["port"]) for c in items)
        say(f"probe: {label} {len(items)} 个：{ports} —— {why}")

    if any(c["verdict"].startswith("unknown") for c in report["candidates"]) and args.budget <= DEFAULT_BUDGET:
        say(f"probe: 要排干净就加大：--budget 20 --timeout 6（当前 {args.budget}s / {args.timeout}s）")
    if not usable:  # 只有可能被误读成"没有代理"时才展开盲区，正常情况不刷屏
        for spot in report["blindSpots"]:
            say(f"probe: 盲区：{spot}")



def copy_lines(report, shell):
    """可直接粘贴的代理环境变量行；只输出，不写任何配置。默认只给第一个可用入口。"""
    lines = []
    for c in usable_of(report):
        proto = next((p for p, r in c["protocols"].items() if r["ok"] and p == "http"), None)
        url = f"http://{c['host']}:{c['port']}" if proto else f"socks5://{c['host']}:{c['port']}"
        egress = next((r["egress"].get("ip") for r in c["protocols"].values() if r["ok"] and r["egress"].get("ip")), "-")
        lines.append(f"# {c['host']}:{c['port']}  {c['verdict']}  egress={egress}")
        if proto is None:
            lines.append("#   注意：只有 socks5 通，HTTP(S)_PROXY 一般要求 http 代理入口")
        if shell == "pwsh":
            lines += [f"$env:HTTP_PROXY = '{url}'", f"$env:HTTPS_PROXY = '{url}'"]
        elif shell == "cmd":
            lines += [f'set "HTTP_PROXY={url}"', f'set "HTTPS_PROXY={url}"']
        elif shell == "bash":
            lines += [f'export http_proxy="{url}"', f'export https_proxy="{url}"', f'export HTTPS_PROXY="{url}"']
        lines.append("")
    return lines


def watch_line(report, prev):
    """一行变化摘要：上一次的可用端口集合对比本次，新增/失效点名。
    只报端口不报协议——预算紧时补探第二协议会被裁掉，标注会来回抖，不是真变化。"""
    stamp = time.strftime("%H:%M:%S")
    now = {c["port"] for c in usable_of(report)}
    tags = " ".join(str(p) for p in sorted(now)) or "-"
    if prev is None:
        return f"{stamp} 首轮    usable={len(now)} [{tags}]"
    added = sorted(now - prev)
    lost = sorted(prev - now)
    if not added and not lost:
        return f"{stamp} 无变化  usable={len(now)} [{tags}]"
    parts = []
    if added:
        parts.append("新增 " + " ".join(str(p) for p in added))
    if lost:
        parts.append("失效 " + " ".join(str(p) for p in lost))
    return f"{stamp} 变化    {'; '.join(parts)}；现有 usable={len(now)} [{tags}]"


def main(argv=None):
    ap = argparse.ArgumentParser(description="按进程名匹配本机代理并探测其监听端口（默认 5 秒预算，只报告不写配置）")
    ap.add_argument("--port", type=int, action="append", default=[], help="追加候选端口，可重复（用于宿主看不到进程的入口）")
    ap.add_argument("--match", action="append", default=[], metavar="REGEX", help="追加进程名匹配正则，可重复；默认已覆盖 mihomo/clash/verge、xray/v2ray、sing-box、ss/trojan/hysteria、surge 等")
    ap.add_argument("--only-match", action="store_true", help="忽略内置家族名表，只用 --match 给的正则（想收窄匹配范围时用）")
    ap.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help=f"总预算秒数（含枚举），默认 {DEFAULT_BUDGET}；到点未完成的记 unknown")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"单次探测上限秒数，默认 {DEFAULT_TIMEOUT}；总预算才是硬上限")
    ap.add_argument("--protocols", default="http,socks5", help="探测协议，默认 http,socks5")
    ap.add_argument("--workers", type=int, default=16, help="并发探测数，默认 16")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"探测目标，默认 {DEFAULT_URL}（读 ip= 出口回显）")
    ap.add_argument("--copy", action="store_true", help="额外打印可直接粘贴的代理环境变量行（只输出，不写配置）")
    ap.add_argument("--shell", choices=("auto", "pwsh", "cmd", "bash"), default="auto", help="--copy 的目标 shell，默认按平台（Windows 给 pwsh+cmd，其它给 bash）")
    ap.add_argument("--watch", type=float, default=0, metavar="SEC", help="常驻重扫：每 SEC 秒扫一轮，只在可用集合变化时点名（Ctrl+C 退出）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON（进度打印到 stderr；配合 --watch 时每轮一行 NDJSON）")
    args = ap.parse_args(argv)

    global _OUT
    _OUT = sys.stderr if args.json else sys.stdout
    try:
        extra = compile_extra(args.match)
    except re.error as e:  # 非法正则：按用法错误退出（exit 2），不吐 traceback
        ap.error(f"--match 正则无效：{e}")
    if args.only_match and not extra:
        ap.error("--only-match 需要配合至少一个 --match（否则没有任何进程名可匹配）")
    protocols = [p.strip() for p in args.protocols.split(",") if p.strip() in ("http", "socks5")] or ["http"]

    if args.watch > 0:
        prev = None
        try:
            while True:
                t0 = time.monotonic()
                report = scan_once(args, protocols, time.monotonic() + max(0.2, args.budget), stream=False, extra=extra)
                if report is None:
                    say("no candidates: 没有候选端口（进程未命中、登记为空、--port 未给）。")
                    return 2
                if args.json:
                    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "summary": report["summary"],
                                      "usable": [{"host": c["host"], "port": c["port"], "verdict": c["verdict"]} for c in usable_of(report)]},
                                     ensure_ascii=False), file=sys.stdout, flush=True)
                else:
                    say(watch_line(report, prev))
                prev = {c["port"] for c in usable_of(report)}
                time.sleep(max(0.5, args.watch - (time.monotonic() - t0)))
        except KeyboardInterrupt:  # 扫描中途或等待中被 Ctrl+C 都从这里出去，不吐 traceback
            say("probe: 退出监听")
            return 0

    report = scan_once(args, protocols, time.monotonic() + max(0.2, args.budget), stream=True, extra=extra)
    if report is None:
        return 2
    s = report["summary"]
    recap(report, args)

    if args.copy and s["usable"]:
        shells = ("pwsh", "cmd") if os.name == "nt" else ("bash",)
        if args.shell != "auto":
            shells = (args.shell,)
        say("probe: 可直接粘贴的代理设置（只输出，不改你的配置）")
        for sh in shells:
            say(f"probe: --- {sh} ---")
            for line in copy_lines(report, sh):
                say(line)
    elif args.copy:
        say("probe: 没有可用入口，--copy 无内容可给")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stdout, flush=True)
    return 0 if s["usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
