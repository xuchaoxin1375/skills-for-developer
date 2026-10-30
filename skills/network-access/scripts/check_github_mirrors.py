#!/usr/bin/env python3
"""核验 GitHub 加速镜像前缀在当前网络下对哪些资源类型可用，并给出速度。

做什么
    对每个候选前缀（形如 https://gh-proxy.com/）分别测四类公开小目标：
    raw 单文件、archive 压缩包、Release 资产（Range 前若干字节）、git 传输（ls-remote）。
    每类独立判定：一个前缀支持 raw 不代表支持 Release 或 git。

不做什么
    - 不保证镜像长期可用：结果只描述当次网络、当次出口、当次目标。
    - 不测私有资源、不测推送、不测大文件完整性；Range 成功只证明该段可取。
    - 不自动改 git remote、不写全局配置、不把结果登记进代理登记文件。

用法
    python -X utf8 scripts/check_github_mirrors.py                      # 内置种子 + 全部资源类型
    python -X utf8 scripts/check_github_mirrors.py --targets raw,release
    python -X utf8 scripts/check_github_mirrors.py --prefix https://gh-proxy.com/ --prefix https://ghfast.top/
    python -X utf8 scripts/check_github_mirrors.py --from-file mirrors.txt --json
    python -X utf8 scripts/check_github_mirrors.py --direct --timeout 5 --out result.json

退出码：0 至少一个前缀在请求的类型上可用；1 探测过但都不可用；2 没有候选。仅标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

UA = "check-github-mirrors/1.0"

# 种子只是起点，不代表可用；正式候选仍从收录页或用户处取得。
SEED_PREFIXES = (
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://ghfast.top/",
)

RAW_URL = "https://raw.githubusercontent.com/octocat/Hello-World/master/README"
ARCHIVE_URL = "https://github.com/hunshcn/gh-proxy/archive/refs/heads/master.zip"
RELEASE_URL = (
    "https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/"
    "ripgrep-14.1.1-x86_64-pc-windows-msvc.zip"
)
GIT_REPO = "https://github.com/hunshcn/gh-proxy.git"

TARGETS = ("raw", "archive", "release", "git")

_JSON = False


def say(msg):
    print(msg, file=sys.stderr if _JSON else sys.stdout, flush=True)


def normalize_prefix(value):
    """把 'gh-proxy.com'、'gh-proxy.com/'、'https://gh-proxy.com' 统一成带 scheme 和结尾斜杠。"""
    text = value.strip()
    if not text:
        raise ValueError("空前缀")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"不是可用的 HTTP(S) 前缀：{value}")
    if parts.query or parts.fragment:
        raise ValueError(f"前缀不应带查询串或片段：{value}")
    if parts.path not in ("", "/"):
        raise ValueError(f"前缀不应带路径：{value}")
    return f"{parts.scheme}://{parts.netloc}/"


def load_candidates(args):
    values = list(args.prefix)
    if args.from_file:
        try:
            lines = Path(args.from_file).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise SystemExit(f"读不到候选文件：{exc}")
        values.extend(line for line in lines if line.strip() and not line.lstrip().startswith("#"))
    if not values:
        values = list(SEED_PREFIXES)
    seen, out = set(), []
    for value in values:
        try:
            prefix = normalize_prefix(value)
        except ValueError as exc:
            say(f"[skip] {exc}")
            continue
        if prefix not in seen:
            seen.add(prefix)
            out.append(prefix)
    return out


def build_opener(proxy, direct):
    if direct:
        return urlreq.build_opener(urlreq.ProxyHandler({}))
    if proxy:
        return urlreq.build_opener(urlreq.ProxyHandler({"http": proxy, "https": proxy}))
    return urlreq.build_opener()


def http_probe(opener, url, byte_range, timeout, max_bytes):
    req = urlreq.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    if byte_range:
        req.add_header("Range", f"bytes=0-{byte_range - 1}")
    start = time.monotonic()
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
            return {
                "ok": True,
                "status": resp.status,
                "bytes": len(data),
                "seconds": round(time.monotonic() - start, 2),
                "ctype": resp.headers.get("Content-Type", ""),
                "sample": data[:512],
            }
    except HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": f"HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        timed_out = isinstance(reason, TimeoutError) or "timed out" in str(reason).lower()
        return {"ok": False, "error": f"{type(reason).__name__}: {reason}", "timeout": timed_out}


def looks_like_html(sample):
    head = sample.lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html") or head.startswith(b"<?xml")


def classify(kind, result):
    """按内容特征判定取回是否像真内容，而不是镜像的错误页。"""
    sample = result.pop("sample", b"")
    if not result.get("ok"):
        if result.get("timeout"):
            return False, "超时（不可判定，可放宽 --timeout 复测）"
        return False, result.get("error", "失败")
    if result["bytes"] == 0:
        return False, "空响应"
    if kind == "zip":
        if sample.startswith(b"PK\x03\x04"):
            return True, ""
        return False, "非 ZIP（可能是错误页）"
    if looks_like_html(sample):
        return False, "返回 HTML（可能是错误页）"
    return True, ""


def speed_kbps(result):
    seconds = result.get("seconds") or 0
    if not result.get("ok") or seconds <= 0:
        return 0.0
    return round(result["bytes"] / seconds / 1024, 1)


def check_git(prefix, timeout):
    if not shutil.which("git"):
        return {"ok": False, "error": "git 未安装", "skipped": True}
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--heads", prefix + GIT_REPO],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=max(timeout * 2, 10),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "git 超时（不可判定，可放宽 --timeout 复测）", "timeout": True}
    except OSError as exc:
        return {"ok": False, "error": f"git 启动失败：{exc}"}
    elapsed = round(time.monotonic() - start, 2)
    refs = [line for line in proc.stdout.splitlines() if line.strip()]
    if proc.returncode == 0 and refs:
        return {"ok": True, "refs": len(refs), "seconds": elapsed}
    detail = (proc.stderr or "").strip().splitlines()
    return {
        "ok": False,
        "error": f"git 退出码 {proc.returncode}" + (f"：{detail[0][:120]}" if detail else ""),
        "seconds": elapsed,
    }


def probe_target(kind, opener, url, byte_range, timeout, max_bytes):
    result = http_probe(opener, url, byte_range, timeout, max_bytes)
    ok, note = classify(kind, result)
    return {
        "ok": ok,
        "note": note,
        "status": result.get("status"),
        "bytes": result.get("bytes"),
        "seconds": result.get("seconds"),
        "kbps": speed_kbps(result),
        "timeout": result.get("timeout", False),
    }


def check_prefix(prefix, targets, timeout, range_bytes, proxy, direct):
    opener = build_opener(proxy, direct)
    results = {}
    if "raw" in targets:
        results["raw"] = probe_target("text", opener, prefix + RAW_URL, 0, timeout, 65536)
    if "archive" in targets:
        results["archive"] = probe_target("zip", opener, prefix + ARCHIVE_URL, range_bytes, timeout, range_bytes)
    if "release" in targets:
        results["release"] = probe_target("zip", opener, prefix + RELEASE_URL, range_bytes, timeout, range_bytes)
    if "git" in targets:
        git = check_git(prefix, timeout)
        results["git"] = {
            "ok": git["ok"],
            "note": git.get("error", ""),
            "refs": git.get("refs"),
            "seconds": git.get("seconds"),
            "skipped": git.get("skipped", False),
            "timeout": git.get("timeout", False),
        }
    entry = {"prefix": prefix, "results": results}
    entry["usable_for"] = [name for name, value in results.items() if value["ok"]]
    return entry


def cell(name, value):
    if not value:
        return "-"
    if value.get("skipped"):
        return "skip"
    if not value["ok"]:
        return "timeout" if value.get("timeout") else "fail"
    if name == "release" and value.get("kbps"):
        return f"{value['kbps']:g}KB/s"
    if name == "git" and value.get("refs"):
        return f"ok/{value['refs']}"
    return "ok"


def pad(text, width):
    """按终端显示宽度补空格，中文按两列算。"""
    shown = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - shown)


def print_table(entries, targets, timeout, range_bytes, route):
    print("探测目标（公开小样本；Range 只覆盖前若干字节，不代表完整文件）：")
    print(f"  raw     {RAW_URL}")
    print(f"  archive {ARCHIVE_URL}（前 {range_bytes} 字节）")
    print(f"  release {RELEASE_URL}（前 {range_bytes} 字节）")
    print(f"  git     ls-remote <前缀>+{GIT_REPO}")
    print(f"  单次超时 {timeout:g} 秒；git 上限 {max(timeout * 2, 10):g} 秒；HTTP 路线 {route}")
    print()
    print(f"{pad('前缀', 30)}" + "".join(pad(name, 12) for name in targets) + "结论")
    print("-" * (30 + 12 * len(targets) + 12))
    for entry in entries:
        row = pad(entry["prefix"], 30)
        for name in targets:
            row += pad(cell(name, entry["results"].get(name)), 12)
        verdict = "可用：" + ",".join(entry["usable_for"]) if entry["usable_for"] else "不可用"
        print(row + verdict)
    print()
    for entry in entries:
        for name in targets:
            value = entry["results"].get(name) or {}
            if not value.get("ok") and value.get("note"):
                print(f"  {entry['prefix']} {name}: {value['note']}")
    print()
    print("结果只描述当次网络与当次目标；换前缀后按同样方式复测，不把结论写成长期可用。")


def main(argv=None):
    global _JSON
    ap = argparse.ArgumentParser(
        prog="check_github_mirrors.py",
        description="核验 GitHub 加速镜像前缀对 raw/archive/Release/git 的可用性与速度。",
    )
    ap.add_argument("--prefix", action="append", default=[], metavar="URL", help="候选前缀，可重复；不带 scheme 时补 https://")
    ap.add_argument("--from-file", metavar="PATH", help="从文件读候选前缀，每行一个，# 开头为注释")
    ap.add_argument("--targets", default=",".join(TARGETS), help=f"要测的资源类型，逗号分隔，默认全部：{','.join(TARGETS)}")
    ap.add_argument("--timeout", type=float, default=8.0, help="单次 HTTP 超时秒数，默认 8")
    ap.add_argument("--range-bytes", type=int, default=262144, help="archive/Release 测试的字节数，默认 262144")
    ap.add_argument("--workers", type=int, default=4, help="并行探测的前缀数，默认 4")
    ap.add_argument("--proxy", metavar="URL", help="HTTP 探测显式走该代理（默认沿用进程环境）")
    ap.add_argument("--direct", action="store_true", help="HTTP 探测绕过环境代理；git 探测仍沿用环境")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON（进度走 stderr）")
    ap.add_argument("--out", metavar="PATH", help="把结果另存到文件（UTF-8）")
    args = ap.parse_args(argv)

    _JSON = args.json
    targets = tuple(t.strip() for t in args.targets.split(",") if t.strip())
    unknown = [t for t in targets if t not in TARGETS]
    if unknown:
        ap.error(f"未知资源类型：{','.join(unknown)}（可选 {','.join(TARGETS)}）")
    if args.timeout <= 0 or args.range_bytes < 1024:
        ap.error("--timeout 必须为正数，--range-bytes 至少 1024")
    if args.proxy and args.direct:
        ap.error("--proxy 与 --direct 只能选一个")

    candidates = load_candidates(args)
    if not candidates:
        say("没有可用候选前缀。")
        return 2

    entries = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(check_prefix, prefix, targets, args.timeout, args.range_bytes, args.proxy, args.direct): prefix
            for prefix in candidates
        }
        for future in futures:
            prefix = futures[future]
            try:
                entries.append(future.result())
            except Exception as exc:  # 单个前缀的异常不影响其余候选
                entries.append({"prefix": prefix, "results": {}, "usable_for": [], "error": f"{type(exc).__name__}: {exc}"})

    entries.sort(key=lambda item: (-len(item["usable_for"]), item["prefix"]))
    route = "direct" if args.direct else (args.proxy or "环境变量/默认")
    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "timeout_s": args.timeout,
        "range_bytes": args.range_bytes,
        "route": route,
        "targets": {
            "raw": RAW_URL,
            "archive": ARCHIVE_URL,
            "release": RELEASE_URL,
            "git": f"ls-remote <prefix>+{GIT_REPO}",
        },
        "mirrors": entries,
        "usable": [entry["prefix"] for entry in entries if entry["usable_for"]],
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json:
        print(text)
    else:
        print_table(entries, targets, args.timeout, args.range_bytes, route)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")

    return 0 if payload["usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
