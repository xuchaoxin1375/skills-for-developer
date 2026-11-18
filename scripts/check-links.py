#!/usr/bin/env python3
"""校验仓库内 Markdown 相对链接与锚点（零依赖，仅标准库）。

检查范围：README.md、docs/**/*.md、skills/**/*.md；跳过 node_modules、assets/sources
与子模块 codex-model-config。只校验行内 Markdown 链接；外部 URL、reference-style
链接和 HTML href 不校验。指向未初始化子模块的链接计为跳过并提示，不按失败处理。
锚点按 GitHub 常见 slug 规则近似：小写、去标点、空格转连字符、重复标题追加 -1。

用法（仓库根）：
  python scripts/check-links.py
  python scripts/check-links.py --repo <path>

退出码：0 通过；1 有错误。
"""

import argparse
import difflib
import re
import sys
import urllib.parse
from pathlib import Path

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")
HTML_ANCHOR = re.compile(r"<a\s+[^>]*(?:id|name)=\"([^\"]+)\"", re.IGNORECASE)
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "data:")


def github_slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    out: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in HTML_ANCHOR.finditer(line):
            out.add(m.group(1))
        m = HEADING.match(line)
        if not m:
            continue
        base = github_slug(m.group(2))
        n = counts.get(base, 0)
        counts[base] = n + 1
        out.add(base if n == 0 else f"{base}-{n}")
    return out


def iter_files(repo: Path):
    files = [repo / "README.md"]
    files += list((repo / "docs").glob("*.md"))
    for p in (repo / "skills").rglob("*.md"):
        if any(part in p.parts for part in ("codex-model-config", "node_modules")):
            continue
        if "assets" in p.parts and "sources" in p.parts:
            continue
        files.append(p)
    return sorted({p.resolve() for p in files if p.is_file()})


def strip_inline_code(line: str) -> str:
    return re.sub(r"`[^`]*`", "", line)


def submodule_roots(repo: Path) -> list[Path]:
    """从 .gitmodules 读取子模块路径；不依赖 git 命令，zip 包同样适用。"""
    gm = repo / ".gitmodules"
    if not gm.is_file():
        return []
    roots = []
    for line in gm.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"\s*path\s*=\s*(.+?)\s*$", line)
        if m:
            roots.append((repo / m.group(1)).resolve())
    return roots


def submodule_uninitialized(root: Path) -> bool:
    """子模块目录缺失或为空时视为未初始化；有内容但缺目标文件仍按错误处理。"""
    if not root.is_dir():
        return True
    try:
        return not any(root.iterdir())
    except OSError:
        return True


def check(repo: Path):
    repo = repo.resolve()
    errors: list[str] = []
    skipped: list[str] = []
    submodules = submodule_roots(repo)
    checked = 0
    for f in iter_files(repo):
        in_fence = False
        for no, line in enumerate(f.read_text(encoding="utf-8-sig").splitlines(), 1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            line = strip_inline_code(line)
            for m in LINK.finditer(line):
                target = m.group(1).strip()
                if not target or target.startswith(EXTERNAL):
                    continue
                # 裸词通常是非路径占位符（如 url、path），不是相对链接
                if not any(ch in target for ch in "./#"):
                    continue
                checked += 1
                path_part, _, frag = target.partition("#")
                if path_part:
                    path = (f.parent / path_part).resolve()
                    if not path.exists():
                        owner = next(
                            (r for r in submodules if path == r or r in path.parents),
                            None,
                        )
                        if owner is not None and submodule_uninitialized(owner):
                            skipped.append(
                                f"{f.relative_to(repo)}:{no} 子模块未初始化，跳过: {target}"
                            )
                        else:
                            errors.append(f"{f.relative_to(repo)}:{no} 链接目标不存在: {target}")
                        continue
                else:
                    path = f
                if frag:
                    if not path.is_file():
                        errors.append(f"{f.relative_to(repo)}:{no} 锚点目标不是文件: {target}")
                        continue
                    frag = urllib.parse.unquote(frag)
                    available = anchors(path)
                    if frag not in available:
                        close = difflib.get_close_matches(frag, available, n=1, cutoff=0.6)
                        hint = f"（最接近: #{close[0]}）" if close else ""
                        errors.append(f"{f.relative_to(repo)}:{no} 锚点不存在: {target}{hint}")
    summary = f"检查 {checked} 个内部链接，{len(errors)} 个问题"
    if skipped:
        summary += f"，{len(skipped)} 个跳过（子模块未初始化）"
    print(summary)
    for e in errors:
        print(f"ERROR: {e}")
    for s in skipped:
        print(f"SKIP: {s}")
    print("FAIL" if errors else "全部链接通过。")
    return 1 if errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="校验仓库内 Markdown 链接与锚点")
    ap.add_argument("--repo", default="", help="仓库根（默认由脚本位置推导）")
    args = ap.parse_args(argv)
    repo = Path(args.repo) if args.repo else Path(__file__).resolve().parent.parent
    return check(repo)


if __name__ == "__main__":
    sys.exit(main())
