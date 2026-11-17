#!/usr/bin/env python3
"""对比多个 PyPI Simple 镜像在当前网络下的索引与包文件取回速度。

做什么
    对每个候选 index 测两段：`<index>/<包名>/` 索引页，以及该索引页里一个 wheel 的 Range 读取。
    package 与 uv 共用同一套 Simple 索引，所以 pip 结论可直接用于 uv。
    每段多次采样取中位数，按文件段相对最优源的倍数给出 常驻 / 备选 / 不可用。

不做什么
    - 不判断镜像是否同步到最新、不校验哈希、不证明该平台可安装。
    - 不修改 pip/uv/git 配置，除非显式 `--out`，否则不写任何文件。
    - 不覆盖 conda、brew、npm；那些源用对应工具或 chsrc 核对。

用法
    python -X utf8 scripts/bench_pypi_mirrors.py
    python -X utf8 scripts/bench_pypi_mirrors.py --package numpy --samples 3 --workers 3
    python -X utf8 scripts/bench_pypi_mirrors.py --index https://repo.huaweicloud.com/repository/pypi/simple --json
    python -X utf8 scripts/bench_pypi_mirrors.py --direct --timeout 5
    python -X utf8 scripts/bench_pypi_mirrors.py --from-file indexes.txt --max-ratio 1.5 --out result.json

退出码：0 至少一个源在全部包上两段都可用；1 都不可用；2 没有候选。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit

UA = "bench-pypi-mirrors/1.0"

# 种子只是起点，不代表可用；正式候选以本机实测为准。
SEED_INDEXES = (
    "https://repo.huaweicloud.com/repository/pypi/simple",
    "https://mirrors.ustc.edu.cn/pypi/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://mirrors.cernet.edu.cn/pypi/web/simple",
    "https://pypi.org/simple",
)

DEFAULT_PACKAGES = ("requests", "numpy")

HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)

_JSON = False


def say(msg):
    print(msg, file=sys.stderr if _JSON else sys.stdout, flush=True)


def normalize_index(value):
    """把 `host/simple/`、`https://host/simple` 统一成带 scheme、无结尾斜杠的 index。"""
    text = value.strip()
    if not text:
        raise ValueError("空 index")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"不是可用的 HTTP(S) 索引：{value}")
    if parts.query or parts.fragment:
        raise ValueError(f"索引不应带查询串或片段：{value}")
    path = parts.path.rstrip("/")
    if not path:
        raise ValueError(f"索引缺少路径（应形如 /simple）：{value}")
    return f"{parts.scheme}://{parts.netloc}{path}"


def load_candidates(args):
    values = list(args.index)
    if args.from_file:
        try:
            lines = Path(args.from_file).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise SystemExit(f"读不到候选文件：{exc}")
        values.extend(line for line in lines if line.strip() and not line.lstrip().startswith("#"))
    if not values:
        values = list(SEED_INDEXES)
    seen, out = set(), []
    for value in values:
        try:
            index = normalize_index(value)
        except ValueError as exc:
            say(f"[skip] {exc}")
            continue
        if index not in seen:
            seen.add(index)
            out.append(index)
    return out


def build_opener(proxy, direct):
    if direct:
        return urlreq.build_opener(urlreq.ProxyHandler({}))
    if proxy:
        return urlreq.build_opener(urlreq.ProxyHandler({"http": proxy, "https": proxy}))
    return urlreq.build_opener()


def timed_get(opener, url, timeout, max_bytes, byte_range=False):
    """timeout 是本次请求的总预算，不只是单次 socket 等待。"""
    req = urlreq.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    if byte_range:
        req.add_header("Range", f"bytes=0-{max_bytes - 1}")
    start = time.monotonic()
    try:
        with opener.open(req, timeout=timeout) as resp:
            chunks, total = [], 0
            while total <= max_bytes:
                if time.monotonic() - start > timeout:
                    return {
                        "ok": False,
                        "timeout": True,
                        "error": f"超出 {timeout:g}s 预算（已读 {total} 字节）",
                        "seconds": round(time.monotonic() - start, 3),
                    }
                chunk = resp.read(min(65536, max_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            return {
                "ok": True,
                "status": resp.status,
                "bytes": total,
                "seconds": round(time.monotonic() - start, 3),
                "data": b"".join(chunks),
            }
    except HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": f"HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        timed_out = isinstance(reason, TimeoutError) or "timed out" in str(reason).lower()
        return {"ok": False, "error": f"{type(reason).__name__}: {reason}", "timeout": timed_out}


def bare_path(href):
    """去掉查询串与 sha256 片段，只留可判断扩展名的路径。"""
    return href.split("?", 1)[0].split("#", 1)[0]


def pick_wheel(hrefs):
    """优先纯 Python wheel，其次任意 wheel，最后退回 sdist；只用于测文件段速度。"""
    wheels = [href for href in hrefs if bare_path(href).lower().endswith(".whl")]
    for href in wheels:
        if "-none-any.whl" in bare_path(href).lower():
            return href, "wheel-any"
    if wheels:
        return wheels[-1], "wheel"
    sdists = [href for href in hrefs if bare_path(href).lower().endswith((".tar.gz", ".zip"))]
    if sdists:
        return sdists[-1], "sdist"
    return None, None


def probe_index(opener, index, package, timeout):
    url = f"{index}/{package}/"
    # 只看前 128 KB 取链接：Simple 页可能上万条，读全页会让慢线路主导总耗时。
    result = timed_get(opener, url, timeout, 128 * 1024)
    if not result["ok"]:
        return {"ok": False, "url": url, "note": result.get("error", "失败"), "timeout": result.get("timeout", False)}
    text = result["data"].decode("utf-8", "replace")
    hrefs = HREF_RE.findall(text)
    wheel, kind = pick_wheel(hrefs)
    if not hrefs or not wheel:
        return {"ok": False, "url": url, "note": "不是 Simple 索引页或没有可下载文件", "seconds": result["seconds"]}
    return {
        "ok": True,
        "url": url,
        "seconds": result["seconds"],
        "bytes": result["bytes"],
        "file_url": urljoin(url, wheel),
        "file_kind": kind,
    }


def probe_file(opener, file_url, timeout, range_bytes):
    result = timed_get(opener, bare_path(file_url), timeout, range_bytes, byte_range=True)
    if not result["ok"]:
        return {"ok": False, "note": result.get("error", "失败"), "timeout": result.get("timeout", False)}
    if result["bytes"] <= 0:
        return {"ok": False, "note": "空响应"}
    seconds = result["seconds"] or 0.001
    return {
        "ok": True,
        "seconds": seconds,
        "bytes": result["bytes"],
        "kbps": round(result["bytes"] / seconds / 1024, 1),
        "partial": result["status"] == 206,
    }


def measure(opener, index, package, timeout, range_bytes, samples):
    index_runs, file_runs, notes = [], [], []
    last_kind = None
    for _ in range(samples):
        probe = probe_index(opener, index, package, timeout)
        if not probe["ok"]:
            notes.append(probe["note"])
            break
        index_runs.append(probe["seconds"])
        file_probe = probe_file(opener, probe["file_url"], timeout, range_bytes)
        if not file_probe["ok"]:
            notes.append(f"文件段：{file_probe['note']}")
            break
        file_runs.append(file_probe["seconds"])
        last_kind = probe["file_kind"]
    if not index_runs:
        return {
            "ok": False,
            "note": notes[0] if notes else "未取到索引页",
        }
    entry = {
        "ok": bool(file_runs),
        "index_seconds": round(statistics.median(index_runs), 3),
        "index_samples": len(index_runs),
    }
    if file_runs:
        entry["file_seconds"] = round(statistics.median(file_runs), 3)
        entry["file_samples"] = len(file_runs)
        entry["kbps"] = round(range_bytes / statistics.median(file_runs) / 1024, 1)
        entry["file_kind"] = last_kind
    if notes:
        entry["note"] = "；".join(dict.fromkeys(notes))
    return entry


def check_index_source(index, packages, timeout, range_bytes, samples, proxy, direct):
    opener = build_opener(proxy, direct)
    results = {pkg: measure(opener, index, pkg, timeout, range_bytes, samples) for pkg in packages}
    return {"index": index, "results": results}


def ratio_of(value, best):
    if not best:
        return None
    return round(value / best, 2)


def judge(entry, best_file, max_ratio):
    """按文件段相对最优源的倍数给判定；文件段不可用时一律不可用。"""
    if not entry.get("ok"):
        return "不可用"
    ratio = ratio_of(entry["file_seconds"], best_file)
    if ratio is None:
        return "不可用"
    return "常驻" if ratio <= max_ratio else "备选"


def pad(text, width):
    """按终端显示宽度补空格，中文按两列算。"""
    shown = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - shown)


def host_of(index):
    return urlsplit(index).netloc


def print_table(package, rows, samples, range_bytes, timeout, route, max_ratio):
    print(f"包 {package}：索引页一次 + 文件段 Range {range_bytes} 字节 × {samples} 次取中位数")
    print(f"单次超时 {timeout:g} 秒；路线 {route}；判定阈值 文件段 ≤ 最优源 {max_ratio:g} 倍为常驻")
    print()
    print(pad("源", 34) + pad("索引", 10) + pad("文件", 10) + pad("速度", 12) + "判定")
    print("-" * 78)
    for row in rows:
        entry = row["entry"]
        index_cell = f"{entry['index_seconds']:g}s" if entry.get("index_seconds") else "-"
        file_cell = f"{entry.get('file_seconds', 0):g}s" if entry.get("file_seconds") else "-"
        speed_cell = f"{entry['kbps']:g}KB/s" if entry.get("kbps") else "-"
        print(pad(host_of(row["index"]), 34) + pad(index_cell, 10) + pad(file_cell, 10) + pad(speed_cell, 12) + row["verdict"])
    print()
    for row in rows:
        note = row["entry"].get("note")
        if note:
            print(f"  {host_of(row['index'])}：{note}")
    print()
    print("结果只描述当次网络与当次目标；文件段取的是索引页里一个 wheel，不代表该平台可安装或哈希正确。")
    print("文件段 403/429 或超预算，说明该源对你的文件下载通道与索引不同（常见于把文件请求转到别的站点），不能只看索引段就定为常驻。")


def main(argv=None):
    global _JSON
    ap = argparse.ArgumentParser(
        prog="bench_pypi_mirrors.py",
        description="对比多个 PyPI Simple 镜像在当前网络下的索引与包文件速度，给出常驻/备选/不可用。",
    )
    ap.add_argument("--index", action="append", default=[], metavar="URL", help="候选 Simple 索引，可重复；不带 scheme 时补 https://")
    ap.add_argument("--from-file", metavar="PATH", help="从文件读候选索引，每行一个，# 开头为注释")
    ap.add_argument("--package", action="append", default=[], metavar="NAME", help=f"要测的包，可重复；默认 {'/'.join(DEFAULT_PACKAGES)}")
    ap.add_argument("--samples", type=int, default=2, help="每个包每段采样次数，取中位数，默认 2")
    ap.add_argument("--range-bytes", type=int, default=524288, help="文件段读取字节数，默认 524288")
    ap.add_argument("--timeout", type=float, default=8.0, help="单次请求超时秒数，默认 8")
    ap.add_argument("--workers", type=int, default=4, help="并行测的源数，默认 4")
    ap.add_argument("--max-ratio", type=float, default=2.0, help="文件段慢于最优源多少倍就降为备选，默认 2.0")
    ap.add_argument("--proxy", metavar="URL", help="显式走该代理（默认沿用进程环境）")
    ap.add_argument("--direct", action="store_true", help="绕过环境代理")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON（进度走 stderr）")
    ap.add_argument("--out", metavar="PATH", help="把 JSON 结果另存到文件（UTF-8）")
    args = ap.parse_args(argv)

    _JSON = args.json
    packages = tuple(args.package) or DEFAULT_PACKAGES
    if args.samples < 1:
        ap.error("--samples 至少为 1")
    if args.timeout <= 0:
        ap.error("--timeout 必须为正数")
    if args.range_bytes < 1024:
        ap.error("--range-bytes 至少 1024")
    if args.max_ratio <= 1:
        ap.error("--max-ratio 必须大于 1")
    if args.proxy and args.direct:
        ap.error("--proxy 与 --direct 只能选一个")

    candidates = load_candidates(args)
    if not candidates:
        say("没有可用候选索引。")
        return 2

    say(f"候选 {len(candidates)} 个，包 {', '.join(packages)}，采样 {args.samples} 次，并行 {args.workers}")
    entries = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(check_index_source, index, packages, args.timeout, args.range_bytes, args.samples, args.proxy, args.direct): index
            for index in candidates
        }
        for future, index in futures.items():
            try:
                entries.append(future.result())
            except Exception as exc:  # noqa: BLE001 - 单个源失败不能中断其余候选
                entries.append({"index": index, "results": {}, "error": f"{type(exc).__name__}: {exc}"})
            say(f"[done] {host_of(index)}")

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "timeout_s": args.timeout,
        "range_bytes": args.range_bytes,
        "samples": args.samples,
        "max_ratio": args.max_ratio,
        "route": "direct" if args.direct else (args.proxy or "环境变量/默认"),
        "packages": list(packages),
        "sources": [],
    }

    verdicts = []
    for package in packages:
        rows = []
        usable = [entry["results"].get(package) or {} for entry in entries]
        best_file = min((item["file_seconds"] for item in usable if item.get("file_seconds")), default=None)
        for entry in entries:
            item = entry["results"].get(package) or {"ok": False, "note": entry.get("error", "未测到")}
            rows.append({"index": entry["index"], "entry": item, "verdict": judge(item, best_file, args.max_ratio)})
        rows.sort(key=lambda row: (not row["entry"].get("ok"), row["entry"].get("file_seconds") or 9e9, row["index"]))
        verdicts.append((package, rows, best_file))

    for entry in entries:
        record = {"index": entry["index"], "host": host_of(entry["index"]), "results": entry["results"]}
        if entry.get("error"):
            record["error"] = entry["error"]
        payload["sources"].append(record)
    for package, rows, _ in verdicts:
        for record in payload["sources"]:
            row = next(row for row in rows if row["index"] == record["index"])
            record.setdefault("verdict", {})[package] = row["verdict"]

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json:
        print(text)
    else:
        route = payload["route"]
        for package, rows, _ in verdicts:
            print_table(package, rows, args.samples, args.range_bytes, args.timeout, route, args.max_ratio)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")

    healthy = any(
        all((entry["results"].get(pkg) or {}).get("ok") for pkg in packages)
        for entry in entries
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
