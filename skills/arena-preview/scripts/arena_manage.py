#!/usr/bin/env python3
"""arena_manage.py —— 检测目录新增项目包，按需解压。

用法:
    python scripts/arena_manage.py <目录> [--pick 1,3] [-y] [--json] [--no-rebuild]

行为:
    扫描目录，比对 *.zip 与同名已解压目录，逐包定状态：
      NEW     有 zip、无可用解压目录（新增，待选）
      OK      已解压可用（zip 可在可不在）
      STALE   zip 比解压目录新（包更新过，可选重解）
      ORPHAN  有解压目录、无对应 zip（保留，不管）
      WARN    同名目录存在但不是项目（无 package.json/index.html，需人工看）
    打印状态表；有 NEW/STALE 且为交互终端时，提示输入序号选择解压
    （如 1,3 / a 全选 / 回车跳过）；--pick 直接指定，-y 全选 NEW。
    解压后默认调 arena_compare.py --no-rebuild？不——默认重建入口页
    （调 arena_compare.py --no-extract，保证没选的包不被顺手解掉）。
退出码: 0 正常；2 参数/目录错误。
零依赖，只用标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena_unpack import unwrap  # noqa: E402

SKIP = {"_compare", "_arena", "node_modules", "dist", "build", ".git", "arena-apps"}


def is_project(d: str) -> bool:
    return os.path.isdir(d) and (
        os.path.exists(os.path.join(d, "package.json"))
        or os.path.exists(os.path.join(d, "index.html"))
    )


def dir_mtime(root: str) -> float:
    latest = 0.0
    for dp, dns, fs in os.walk(root):
        dns[:] = [d for d in dns if d not in {"node_modules", "dist", "build", ".git"}]
        for f in fs:
            try:
                latest = max(latest, os.path.getmtime(os.path.join(dp, f)))
            except OSError:
                pass
    return latest


def scan(directory: str) -> list[dict]:
    rows: list[dict] = []
    zips: dict[str, str] = {}
    for name in sorted(os.listdir(directory)):
        if name in SKIP:
            continue
        p = os.path.join(directory, name)
        if name.endswith(".zip") and os.path.isfile(p):
            zips[os.path.splitext(name)[0]] = p
    for base in sorted(zips):
        zp, dest = zips[base], os.path.join(directory, base)
        kb = os.path.getsize(zp) // 1024
        if not (os.path.isdir(dest) and os.listdir(dest)):
            rows.append({"name": base, "status": "NEW", "zip": zp,
                         "detail": f"zip {kb}KB，未解压"})
        elif not is_project(unwrap(dest)):
            rows.append({"name": base, "status": "WARN", "zip": zp,
                         "detail": f"同名目录非项目，需人工看: {dest}"})
        elif os.path.getmtime(zp) > dir_mtime(unwrap(dest)) + 1:
            rows.append({"name": base, "status": "STALE", "zip": zp,
                         "detail": f"zip 比解压目录新（{kb}KB），可选重解"})
        else:
            rows.append({"name": base, "status": "OK", "zip": zp,
                         "detail": "已解压可用"})
    for name in sorted(os.listdir(directory)):
        if name in SKIP or name.endswith(".zip"):
            continue
        p = os.path.join(directory, name)
        if os.path.isdir(p) and is_project(unwrap(p)) and name not in zips:
            rows.append({"name": name, "status": "ORPHAN", "zip": "",
                         "detail": "无对应 zip，保留不管"})
    return rows


def extract(row: dict, directory: str, force: bool) -> None:
    base = row["name"]
    dest = os.path.join(directory, base)
    if force and os.path.isdir(dest):
        shutil.rmtree(dest)
        print(f"  清掉旧目录: {dest}")
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(row["zip"]) as z:
        z.extractall(dest)
    print(f"  已解压: {dest}")


def parse_pick(s: str, n: int) -> list[int]:
    s = s.strip().lower()
    if s in {"a", "all"}:
        return list(range(n))
    out: list[int] = []
    for part in s.replace("，", ",").split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= n:
            out.append(int(part) - 1)
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser(description="检测新增项目包，按需解压")
    ap.add_argument("dir", help="项目包所在目录")
    ap.add_argument("--pick", default="",
                    help="非交互指定序号，如 --pick 1,3（对照状态表）")
    ap.add_argument("-y", "--yes", action="store_true", help="全选 NEW，不询问")
    ap.add_argument("--json", action="store_true", help="只输出 JSON 状态表，不动作")
    ap.add_argument("--no-rebuild", action="store_true", help="解压后不重建入口页")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        print(f"错误：找不到目录 {args.dir}", file=sys.stderr)
        return 2
    directory = os.path.abspath(args.dir)
    rows = scan(directory)
    actionable = [r for r in rows if r["status"] in {"NEW", "STALE"}]

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(f"扫描: {directory}")
    seq = 0
    for r in rows:
        if r in actionable:
            seq += 1
            print(f"  [{seq}] {r['status']:6} {r['name']} — {r['detail']}")
        else:
            print(f"       {r['status']:6} {r['name']} — {r['detail']}")
    if not actionable:
        print("无新增/可更新的包，无事可做。")
        return 0

    if args.pick:
        idx = parse_pick(args.pick, len(actionable))
    elif args.yes:
        idx = [i for i, r in enumerate(actionable) if r["status"] == "NEW"]
    elif sys.stdin.isatty():
        s = input("输入序号解压（如 1,3 / a 全选 / 回车跳过）：")
        idx = parse_pick(s, len(actionable))
    else:
        print("非交互终端：未解压任何包（--pick 指定或 -y 全选 NEW）。")
        return 0
    if not idx:
        print("已跳过，未解压任何包。")
        return 0

    for i in idx:
        r = actionable[i]
        print(f"解压 [{i + 1}] {r['name']} ({r['status']})…")
        extract(r, directory, force=(r["status"] == "STALE"))
    if not args.no_rebuild:
        print("重建入口页（--no-extract：没选的不动）…")
        cmp_py = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "arena_compare.py")
        rc = subprocess.run([sys.executable, cmp_py, directory,
                             "--no-extract"]).returncode
        if rc:
            print(f"入口页重建失败（exit {rc}），解压结果保留", file=sys.stderr)
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
