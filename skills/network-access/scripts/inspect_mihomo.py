#!/usr/bin/env python3
"""检查本机 mihomo / Clash 系客户端的配置、节点与分组，输出概述报告（默认只读）。

做什么
    1. 发现本机客户端的运行时配置与 profile 列表（Clash Verge Rev、mihomo-party、
       FlClash、裸核 -d 目录等），从配置里取 external-controller 与 secret。
    2. 只读 GET Clash 兼容 API：/version、/configs、/proxies、/providers/proxies、
       /rules、/connections。
    3. 汇总为报告：可用配置、运行时状态、节点池、分组与当前选中、订阅状态、规则面、
       以及按场景给出的提示（含空组、混入 DIRECT、信息节点、策略选择）。
    4. --delay 追加一次有界延迟测速（默认逐叶子节点，真实出网）。

不做什么
    - 不发 PUT/PATCH：不切节点、不改模式、不写代理登记文件。
    - 不凭节点名判断地区或真实出口：需要逐节点出口必须切节点，属写操作，另需授权。
    - 不把 load-balance 的 round-robin 当成缺陷：轮换出口对无登录公开页爬虫是有效策略，
      对带会话的站点才是风险，报告按场景提示。

用法
    python -X utf8 scripts/inspect_mihomo.py
    python -X utf8 scripts/inspect_mihomo.py --json
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
import json
import os
import re
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
SPECIAL_PROXIES = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}
JUNK_NAME_RE = re.compile(r"官网|官方|剩余|到期|过期|套餐|重置|流量|试用|expire|traffic|official", re.I)
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


def find_client(explicit: Path | None) -> dict | None:
    """返回 {client, root, runtime_config, profiles_file, candidates}。"""
    if explicit:
        if not explicit.is_file():
            return None
        text = explicit.read_text(encoding="utf-8", errors="replace")
        return {
            "client": "explicit",
            "root": str(explicit.parent),
            "runtime_config": str(explicit),
            "profiles_file": None,
            "candidates": [str(explicit)],
            "_text": text,
        }

    best = None
    for label, raw in CLIENT_ROOTS:
        root = expand(raw)
        if not root.is_dir():
            continue
        candidates, texts = [], {}
        for path in iter_yaml(root):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            keys = parse_config_text(text)["keys"]
            if "external-controller" in keys or "mixed-port" in keys:
                candidates.append(path)
                texts[str(path)] = text
        if not candidates:
            continue
        # 运行时配置通常最完整也最新：优先带控制口和 groups/rules 的那份，再按时间。
        def score(p: Path) -> tuple:
            body = texts[str(p)]
            keys = parse_config_text(body)["keys"]
            rich = bool(re.search(r"^(proxy-groups|proxy-providers|rules)\s*:", body, re.M))
            return (
                1 if keys.get("external-controller") else 0,
                1 if rich else 0,
                p.stat().st_mtime,
                p.stat().st_size,
            )

        candidates.sort(key=score, reverse=True)
        picked = candidates[0]
        profiles = root / "profiles.yaml"
        entry = {
            "client": label,
            "root": str(root),
            "runtime_config": str(picked),
            "profiles_file": str(profiles) if profiles.is_file() else None,
            "candidates": [str(p) for p in candidates[:10]],
            "_text": texts[str(picked)],
        }
        best = entry
        break
    return best


def api_get(base: str, secret: str, path: str, timeout: float = API_TIMEOUT):
    req = urlreq.Request(base + path, headers={"User-Agent": UA, "Accept": "application/json"})
    if secret:
        req.add_header("Authorization", f"Bearer {secret}")
    opener = urlreq.build_opener(urlreq.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
        if raw[:1] in (b"{", b"["):
            return json.loads(raw)
        return raw.decode("utf-8", "replace")


def delay_one(base: str, secret: str, name: str, test_url: str, timeout_ms: int):
    path = "/proxies/{}/delay?{}".format(
        urlparse.quote(name, safe=""),
        urlparse.urlencode({"url": test_url, "timeout": timeout_ms}),
    )
    try:
        data = api_get(base, secret, path, timeout=timeout_ms / 1000 + 3)
        return name, data.get("delay"), None
    except Exception as exc:  # noqa: BLE001
        return name, None, f"{type(exc).__name__}: {exc}"


def leaf_names(proxies: dict) -> list[str]:
    return [
        n
        for n, p in proxies.items()
        if p.get("type") not in GROUP_TYPES and n not in SPECIAL_PROXIES
    ]


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


def human_age(ts) -> str:
    if not ts or str(ts).startswith("0001"):
        return "未记录"
    if isinstance(ts, str) and ts.strip().isdigit():
        ts = int(ts.strip())
    if isinstance(ts, (int, float)):
        try:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return str(ts)
    else:
        try:
            dt = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", str(ts).replace("Z", "+00:00")))
        except ValueError:
            return str(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = int((datetime.now(timezone.utc) - dt).total_seconds())
    if secs < 0:
        return f"{-secs}s 后（时钟偏差）"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    return f"{secs // 86400} 天前"


def build_model(ctx: dict, api: dict, delay: dict | None) -> dict:
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

    provs = []
    for name, p in providers.items():
        sub = p.get("subscriptionInfo") or {}
        used = (sub.get("Upload") or 0) + (sub.get("Download") or 0)
        total = sub.get("Total") or 0
        provs.append(
            {
                "name": name,
                "vehicle": p.get("vehicleType"),
                "count": len(p.get("proxies") or []),
                "updatedAt": p.get("updatedAt"),
                "age": human_age(p.get("updatedAt")),
                "expire": sub.get("Expire"),
                "usedGB": round(used / 1024**3, 2),
                "totalGB": round(total / 1024**3, 2) if total else None,
            }
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
            "runtimeConfig": ctx["runtime_config"],
            "profilesFile": ctx.get("profiles_file"),
            "candidates": ctx.get("candidates") or [],
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

    weak_provs = [p["name"] for p in model["providers"] if p["vehicle"] == "File" and not p["count"]]
    if weak_provs:
        add("warn", "空的 file provider", f"{', '.join(weak_provs)} 没有节点；引用它们的组会退化成空组。")

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
    add(f"叶子节点 {nodes['leafTotal']} 个：" + "、".join(f"{k} {v}" for k, v in sorted(nodes["byType"].items(), key=lambda kv: -kv[1])))
    add("")
    if model["providers"]:
        add("| provider | 类型 | 节点 | 更新时间 | 用量 |")
        add("| --- | --- | --- | --- | --- |")
        for p in model["providers"]:
            usage = f"{p['usedGB']} GB" + (f" / {p['totalGB']} GB" if p["totalGB"] else "")
            add(f"| `{p['name']}` | {p['vehicle']} | {p['count']} | {p['age']} | {usage} |")
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
    parser.add_argument("--controller", help="覆盖 external-controller，如 <host>:<port>")
    parser.add_argument("--secret", help="覆盖 secret；默认从配置读取，不落盘不回显")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（stdout 只留 JSON）")
    parser.add_argument("--report", metavar="PATH", help="把 Markdown 报告另存到文件")
    parser.add_argument("--delay", action="store_true", help="追加延迟测速（会真实出网）")
    parser.add_argument("--group", action="append", default=[], help="只测指定分组的叶子成员，可重复")
    parser.add_argument("--test-url", default=DEFAULT_TEST_URL, help=f"延迟测试 URL（默认 {DEFAULT_TEST_URL}）")
    parser.add_argument("--delay-timeout", type=int, default=DEFAULT_DELAY_TIMEOUT, help="单节点超时毫秒数")
    parser.add_argument("--delay-limit", type=int, default=DEFAULT_DELAY_LIMIT, help="单次最多测多少节点")
    parser.add_argument("--workers", type=int, default=8, help="测速并发数")
    args = parser.parse_args(argv)

    ctx = find_client(Path(args.config).expanduser().resolve() if args.config else None)
    if not ctx:
        print("没有找到 mihomo/Clash 系运行时配置；用 --config 指定，或用 probe_local_proxies.py 先找端口。", file=sys.stderr)
        return 2

    text = ctx["_text"]
    cfg = parse_config_text(text)["keys"]
    controller = args.controller or cfg.get("external-controller")
    secret = args.secret if args.secret is not None else cfg.get("secret") or ""

    api: dict = {}
    api_ok = False
    if controller:
        base = controller if controller.startswith(("http://", "https://")) else f"http://{controller}"
        endpoints = {
            "version": "/version",
            "configs": "/configs",
            "proxies": "/proxies",
            "providers": "/providers/proxies",
            "rules": "/rules",
            "connections": "/connections",
        }
        errors = []
        try:
            api["version"] = api_get(base, secret, "/version", timeout=3)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"version: {type(exc).__name__}")
            api["error"] = "控制 API 不可用（" + "; ".join(errors) + "）"
        else:
            for key, path in endpoints.items():
                if key == "version":
                    continue
                try:
                    api[key] = api_get(base, secret, path)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{key}: {type(exc).__name__}")
            api_ok = "proxies" in api
            if not api_ok:
                api["error"] = "控制 API 不完整（" + "; ".join(errors) + "）"
    else:
        api["error"] = "配置里没有 external-controller"

    delay = None
    if args.delay and api_ok:
        proxies = api["proxies"].get("proxies") or {}
        if args.group:
            targets: list[str] = []
            for g in args.group:
                targets.extend(group_leaf_members(g, proxies))
        else:
            targets = leaf_names(proxies)
        targets = list(dict.fromkeys(targets))[: max(1, args.delay_limit)]
        base = controller if controller.startswith(("http://", "https://")) else f"http://{controller}"
        results = []
        with cf.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = [
                pool.submit(delay_one, base, secret, name, args.test_url, args.delay_timeout)
                for name in targets
            ]
            for fut in cf.as_completed(futures):
                name, delay_ms, error = fut.result()
                if delay_ms is not None:
                    results.append({"name": name, "delay": delay_ms})
                else:
                    results.append({"name": name, "delay": None, "error": error or "no response"})
        delay = {
            "ran": True,
            "testUrl": args.test_url,
            "timeoutMs": args.delay_timeout,
            "targets": len(targets),
            "results": sorted(results, key=lambda x: (x["delay"] is None, x["delay"] or 0)),
        }

    model = build_model(ctx, api, delay)
    model["apiOk"] = api_ok
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
