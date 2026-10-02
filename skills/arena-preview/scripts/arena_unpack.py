#!/usr/bin/env python3
"""arena_unpack.py —— arena.ai 项目包解压 + 指纹识别。

用法:
    python scripts/arena_unpack.py <project.zip> [--out DIR] [--json]

行为:
    解压到与 zip 同目录的 <包名>/（默认，原地解压不另建容器），自动剥掉单层包裹目录；
    打印目录树（跳过 node_modules/dist/.git，上限 120 项）、框架指纹、
    scripts 表、主题与入口文件定位、建议的运行命令。
退出码: 0 正常；2 参数/文件错误。
零依赖，只用标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile

SKIP_DIRS = {"node_modules", "dist", "build", ".git", ".next", "__pycache__"}
THEME_HINTS = ("tailwind.config", "index.css", "theme", "global.css", "app.css")
ENTRY_HINTS = ("index.html", "src/main.", "src/App.", "src/index.", "app/page.",
               "pages/index.", "src/app.")


def unwrap(root: str) -> str:
    """zip 只有单层包裹目录时（如 pkg/src/...）返回包裹内路径，否则返回 root。"""
    entries = [e for e in os.listdir(root) if e != "__MACOSX"]
    if len(entries) == 1 and os.path.isdir(os.path.join(root, entries[0])):
        inner = os.path.join(root, entries[0])
        if os.path.exists(os.path.join(inner, "package.json")) or os.path.exists(
            os.path.join(inner, "index.html")
        ):
            return inner
    return root


def tree(root: str, limit: int = 120) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        for name in sorted(filenames):
            if len(out) >= limit:
                out.append("...（截断，只显示前 %d 项）" % limit)
                return out
            p = name if rel == "." else os.path.join(rel, name)
            out.append(("  " * depth) + p.replace(os.sep, "/"))
    return out


def fingerprint(root: str) -> dict:
    pkg_path = os.path.join(root, "package.json")
    pkg: dict = {}
    if os.path.exists(pkg_path):
        with open(pkg_path, encoding="utf-8") as f:
            pkg = json.load(f)
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    scripts = pkg.get("scripts", {})

    files = [os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
             for dp, _, fs in os.walk(root) for f in fs]
    flat = [p for p in files if not p.split("/")[0] in SKIP_DIRS]
    cfg = lambda *names: [p for p in flat for n in names if p.endswith(n)]

    framework = "unknown"
    if cfg("vite.config.ts", "vite.config.js"):
        framework = "Vite+" + ("Vue" if "vue" in deps else "React" if "react" in deps else "?")
    elif cfg("next.config.js", "next.config.mjs", "next.config.ts"):
        framework = "Next.js"
    elif "vue" in deps and ("@vue/cli-service" in deps or cfg("vue.config.js")):
        framework = "VueCLI"
    elif not pkg and os.path.exists(os.path.join(root, "index.html")):
        framework = "static"

    theme = sorted({p for p in flat for h in THEME_HINTS if h in os.path.basename(p)})
    entry = sorted({p for p in flat for h in ENTRY_HINTS if h in p})[:8]
    docs = sorted({p for p in flat if os.path.basename(p).lower().startswith("readme")
                   or "/docs/" in p and p.endswith(".md")})[:8]
    return {
        "framework": framework,
        "scripts": scripts,
        "dep_count": len(deps),
        "deps": sorted(deps)[:30],
        "theme_files": theme[:8],
        "entry_files": entry,
        "docs": docs,
    }


def suggest(fp: dict) -> list[str]:
    fw = fp["framework"]
    s = fp["scripts"]
    if fw.startswith("Vite") or fw in ("Next.js", "VueCLI"):
        cmds = ["npm install", "npm run build"]
        cmds.append("npx serve dist 或 npm run preview（静态预览，默认先看这个）")
        if "dev" in s:
            cmds.append("改代码才用：npm run dev（后台，Vite 默认 5173/Next 默认 3000）")
        return cmds
    if fw == "static":
        return ["直接用浏览器打开 index.html，或 python3 -m http.server 起本地服务"]
    if fp["scripts"]:
        return [f"npm run {k}" for k in s]
    return ["无可识别的运行入口，先读 docs/ 与 README"]


def main() -> int:
    ap = argparse.ArgumentParser(description="arena.ai 项目包解压 + 指纹识别")
    ap.add_argument("zip", help="项目包路径")
    ap.add_argument("--out", default="", help="解压目录（默认 zip 同级的 _arena/<包名>）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--limit", type=int, default=120)
    args = ap.parse_args()

    if not os.path.isfile(args.zip):
        print(f"错误：找不到 {args.zip}", file=sys.stderr)
        return 2
    try:
        with zipfile.ZipFile(args.zip) as z:
            bad = [i.filename for i in z.infolist() if os.path.isabs(i.filename) or ".." in i.filename]
            if bad:
                print(f"错误：zip 含危险路径，已拒绝：{bad[:3]}", file=sys.stderr)
                return 2
            out = args.out or os.path.join(
                os.path.dirname(os.path.abspath(args.zip)),
                os.path.splitext(os.path.basename(args.zip))[0])
            os.makedirs(out, exist_ok=True)
            z.extractall(out)
    except zipfile.BadZipFile:
        print("错误：不是有效的 zip 包", file=sys.stderr)
        return 2

    root = unwrap(out)
    fp = fingerprint(root)
    result = {
        "project_dir": root,
        "unwrapped": root != out,
        "tree": tree(root, args.limit),
        **fp,
        "suggest": suggest(fp),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"项目目录: {root}" + ("（已剥包裹目录）" if result["unwrapped"] else ""))
        print(f"框架指纹: {fp['framework']}，依赖 {fp['dep_count']} 个")
        print("scripts: " + ("；".join(f"{k}: {v}" for k, v in fp["scripts"].items()) or "无"))
        print("主题文件: " + ("；".join(fp["theme_files"]) or "未发现"))
        print("入口文件: " + ("；".join(fp["entry_files"]) or "未发现"))
        print("文档: " + ("；".join(fp["docs"]) or "无"))
        print("建议运行:")
        for c in result["suggest"]:
            print(f"  - {c}")
        print("目录树:")
        for line in result["tree"]:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
