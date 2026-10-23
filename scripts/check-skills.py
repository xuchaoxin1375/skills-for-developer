#!/usr/bin/env python3
"""真源 skill 快速校验（零依赖，仅标准库）。

查六件事，对应上次踩坑的盲区（链接脚本只查 SKILL.md 存在性，不校验内容）：
  1. frontmatter：定界符、`name` 与目录一致且 kebab、`description` 非空、
     多行 description 必须用 `>`/`|` 折叠块并缩进（顶格续行曾导致服务端静默丢弃）。
  2. README 索引：每个 skill 在 README.md 有 `skills/<name>` 入口。
  3. 红线路径：skill 正文/引用/示例/配套脚本不得出现仓库外真实路径。
  4. 各 harness 安装数：每个真源 skill 在 5 个 harness 侧都是指向真源的链接。
  5. 推荐部署名单：config/recommended-skills.txt 的名字须有对应真源目录；
     含 package.json（需依赖安装）却不在名单中的给出提醒。
  6. 依赖声明：skills/*/dependencies.json 的结构与字段校验，见
     docs/skill-dependencies.md；含 package.json 却未声明依赖时给出提醒。

用法（仓库根）：
  python3 scripts/check-skills.py
  python3 scripts/check-skills.py --include doc-rewrite-review,htmlmini
  python3 scripts/check-skills.py --no-harness      # 只查仓库侧（含 CI）
  python3 scripts/check-skills.py --repo <path>     # 指定仓库根（默认脚本上级）
  python3 scripts/check-skills.py --strict          # 警告也视为失败

退出码：0 通过；1 有错误（--strict 下警告也算）。
"""

import argparse
import os
import re
import sys
from pathlib import Path

from skill_deps import load_manifest, validate_manifest, validate_profiles

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KEY = re.compile(r"^([A-Za-z0-9_./-]+):(.*)$")
BLOCK_MARK = {"#", ">", "|", ">-", "|-", ">+", "|+"}

# 红线路径模式（skill 正文/引用/示例/配套脚本不得出现仓库外真实路径）。
# 含 … 省略号的行视为规则举例说明，跳过；子模块目录另行豁免（上游来源边界）。
PATH_PATTERNS = [
    (re.compile(r"C:\\Users\\"), "C:\\Users\\…"),
    (re.compile(r"C:\\tools\\"), "C:\\tools\\…"),
    (re.compile(r"/home/"), "/home/…"),
    (re.compile(r"(?<![\w$<{])/tmp/"), "写死的 /tmp/…"),
]
# 端口字面量模式（127.0.0.1/localhost 后跟具体端口）。
# 本机代理端口因机器而异，不得写进真源；真实值走登记文件或环境变量。
# 豁免：占位写法（<port>、<实际端口>、…举例）、黑洞 :1、动态 :0。
PORT_PATTERNS = [
    re.compile(r"127\.0\.0\.1:(?!0\b|1\b)\d+"),
    re.compile(r"localhost:(?!0\b|1\b)\d+"),
]
PORT_PLACEHOLDERS = ("<port>", "<实际端口>", "…")
REDLINE_EXEMPT_DIRS = {"codex-model-config"}  # submodule，上游来源边界，不改写上游


def parse_frontmatter(fm_lines, base_no):
    """解析 frontmatter 块。fm_lines 为 --- 之间的行（不含定界符）。

    返回 (data, errors, warnings)。base_no 为 fm_lines[0] 对应 1-based 行号。
    只支持本仓库约定的子集：顶层 key、# 注释/空行、`>`/`|` 折叠块、
    `metadata:` 类嵌套块（跳过）。不引入 PyYAML 依赖。
    """
    data, errors, warnings = {}, [], []
    seen = set()
    i, n = 0, len(fm_lines)
    while i < n:
        ln = fm_lines[i]
        no = base_no + i
        if ln.strip() == "" or ln.lstrip().startswith("#"):
            i += 1
            continue
        if ln.strip() == "...":
            i += 1
            continue
        m = KEY.match(ln)
        if not m:
            errors.append(
                f"第{no}行无法解析为顶层 key"
                f"（顶格续行？多行 description 须用 > 折叠块并缩进）: {ln[:60]!r}"
            )
            i += 1
            continue
        key, rest = m.group(1), m.group(2)
        if key in seen:
            errors.append(f"第{no}行重复 key: {key}")
        seen.add(key)
        val = rest.strip()
        if val in BLOCK_MARK and val != "#":
            i += 1
            buf = []
            while i < n and (
                fm_lines[i].startswith((" ", "\t")) or fm_lines[i].strip() == ""
            ):
                buf.append(fm_lines[i].strip())
                i += 1
            text = (
                " ".join(b for b in buf if b)
                if val.startswith(">")
                else "\n".join(buf).strip("\n")
            )
            if not text:
                errors.append(f"第{no}行 {key} 折叠块为空")
            data[key] = text
            continue
        if val == "":
            # 空值：嵌套块（如 metadata:）则跳过整个缩进区，否则记空字符串
            j = i + 1
            while j < n and fm_lines[j].strip() == "":
                j += 1
            if j < n and fm_lines[j].startswith((" ", "\t")):
                data[key] = "<nested>"
                i += 1
                while i < n and (
                    fm_lines[i].startswith((" ", "\t"))
                    or fm_lines[i].strip() == ""
                ):
                    i += 1
                continue
            data[key] = ""
            i += 1
            continue
        data[key] = val
        i += 1
        # 前瞻：inline 值之后出现顶格非 key 行 = 未折叠的多行（历史坑）
        if i < n:
            nxt = fm_lines[i]
            if (
                nxt.strip() not in ("", "...")
                and not nxt.startswith((" ", "\t"))
                and not KEY.match(nxt)
            ):
                errors.append(
                    f"{key} 疑似多行未折叠：第{base_no + i}行顶格续行"
                    f"（须改用 > 块并缩进）: {nxt[:60]!r}"
                )
    return data, errors, warnings


def check_skill(skill_dir):
    """校验单个 skill，返回 (errors, warnings)。"""
    errors, warnings = [], []
    name = skill_dir.name
    p = skill_dir / "SKILL.md"
    try:
        text = p.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as e:
        return [f"{name}: SKILL.md 不可读（{e}）"], []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return [f"{name}: 缺少 frontmatter 起始 ---"], []
    try:
        end = lines.index("---", 1)
    except ValueError:
        return [f"{name}: 缺少 frontmatter 结束 ---"], []
    data, errs, _ = parse_frontmatter(lines[1:end], 2)
    errors.extend(f"{name}: {e}" for e in errs)
    if "name" not in data:
        errors.append(f"{name}: frontmatter 缺少 name")
    else:
        if data["name"] != name:
            errors.append(f"{name}: name {data['name']!r} 与目录名不一致")
        if not KEBAB.match(data["name"]):
            errors.append(f"{name}: name 非 kebab 小写 exact 格式")
    if "description" not in data or not data.get("description", "").strip():
        errors.append(f"{name}: frontmatter 缺少非空 description")
    return errors, warnings


def redline_scan(skill_dir):
    """红线路径扫描，返回 errors。"""
    errors = []
    if skill_dir.name in REDLINE_EXEMPT_DIRS:
        return errors
    targets = [skill_dir / "SKILL.md"]
    for sub in ("references", "scripts"):
        d = skill_dir / sub
        if d.is_dir():
            targets.extend(f for f in d.rglob("*") if f.is_file())
    for f in targets:
        try:
            content = f.read_text(encoding="utf-8-sig", errors="strict")
        except (OSError, UnicodeError):
            continue
        rel = f.relative_to(skill_dir.parent.parent)
        for no, ln in enumerate(content.splitlines(), 1):
            if "…" in ln:
                continue  # 规则举例说明（含省略号），非真实路径
            for rx, label in PATH_PATTERNS:
                if rx.search(ln):
                    errors.append(f"{rel}:{no} 疑似仓库外真实路径（{label}）")
                    break
    return errors


def port_scan(skill_dir):
    """端口字面量扫描，返回 (errors, warnings)。

    scripts/** 命中记错误（行为级绑定）；SKILL.md/references/** 命中记警告
    （文档示例，逐步收敛）。tests/ 不在扫描范围。
    """
    errors, warnings = [], []
    if skill_dir.name in REDLINE_EXEMPT_DIRS:
        return errors, warnings
    groups = [
        ([skill_dir / "SKILL.md"], warnings, "文档示例疑似写死本地端口"),
    ]
    for sub, bucket, label in (
        ("references", warnings, "文档示例疑似写死本地端口"),
        ("scripts", errors, "脚本疑似写死本地端口"),
    ):
        d = skill_dir / sub
        if d.is_dir():
            groups.append(
                ([f for f in d.rglob("*") if f.is_file()], bucket, label)
            )
    for targets, bucket, label in groups:
        for f in targets:
            try:
                content = f.read_text(encoding="utf-8-sig", errors="strict")
            except (OSError, UnicodeError):
                continue
            rel = f.relative_to(skill_dir.parent.parent)
            for no, ln in enumerate(content.splitlines(), 1):
                if any(ph in ln for ph in PORT_PLACEHOLDERS):
                    continue
                for rx in PORT_PATTERNS:
                    if rx.search(ln):
                        bucket.append(f"{rel}:{no} {label}（真实值走登记/环境变量）")
                        break
    return errors, warnings


def check_dependencies(skill_dir):
    """校验 skills/<name>/dependencies.json 的结构，返回 (errors, warnings)。"""
    errors, warnings = [], []
    name = skill_dir.name
    path = skill_dir / "dependencies.json"
    if not path.is_file():
        if (skill_dir / "package.json").is_file():
            warnings.append(f"{name}: 含 package.json 但缺少 dependencies.json（外部依赖未声明？）")
        return errors, warnings
    try:
        data = load_manifest(path)
    except (OSError, UnicodeError, ValueError) as e:
        errors.append(f"{name}: dependencies.json 无法读取或解析（{e}）")
        return errors, warnings
    for message in validate_manifest(data):
        errors.append(f"{name}: dependencies.json {message}")
    return errors, warnings


def check_profiles(repo):
    """校验 config/dependency-profiles.json（依赖套餐），返回 (errors, warnings)。"""
    path = repo / "config" / "dependency-profiles.json"
    if not path.is_file():
        return [], []
    try:
        data = load_manifest(path)
    except (OSError, UnicodeError, ValueError) as e:
        return [f"dependency-profiles.json 无法读取或解析（{e}）"], []
    return [f"dependency-profiles.json {message}" for message in validate_profiles(data)], []


def link_target(path):
    """返回链接目标（规范化后），实体/不存在返回 None。

    用 realpath 与 abspath 比较，同时覆盖 symlink 与 Windows Junction，
    不依赖平台专有 API。
    """
    try:
        ap = os.path.normcase(os.path.abspath(path))
        rp = os.path.normcase(os.path.realpath(path))
    except OSError:
        return None
    if not os.path.lexists(path):
        return None
    return rp if rp != ap else None


def read_recommended(repo):
    """读取推荐部署名单，返回名字列表；文件缺失/不可读返回 None。"""
    p = repo / "config" / "recommended-skills.txt"
    try:
        text = p.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    names = []
    for raw in text.splitlines():
        name = raw.split("#", 1)[0].strip()
        if name:
            names.append(name)
    return names


def harness_targets():
    home = Path.home()
    agents = Path(
        os.environ.get("DSH_AGENTS_HOME") or (home / ".agents")
    )
    dsh = Path(os.environ.get("DSH_HOME") or (home / ".dsh"))
    return [
        ("opencode", home / ".config" / "opencode" / "skills"),
        ("codex", home / ".codex" / "skills"),
        ("claude", home / ".claude" / "skills"),
        ("agents", agents / "skills"),
        ("dsh", dsh / "skills"),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description="真源 skill 快速校验")
    ap.add_argument("--include", default="",
                    help="只检查指定 skill，逗号分隔")
    ap.add_argument("--no-harness", action="store_true",
                    help="只查仓库侧（frontmatter/索引/红线），跳过 harness 安装数")
    ap.add_argument("--repo", default="",
                    help="仓库根（默认由脚本位置推导）")
    ap.add_argument("--strict", action="store_true",
                    help="警告也视为失败")
    args = ap.parse_args(argv)

    repo = Path(args.repo) if args.repo else Path(__file__).resolve().parent.parent
    skills_dir = repo / "skills"
    if not skills_dir.is_dir():
        print(f"skills 目录不存在: {skills_dir}")
        return 1

    want = {s.strip() for s in args.include.split(",") if s.strip()}
    skills = sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
        and (not want or d.name in want)
    )
    no_skb = sorted(
        d.name for d in skills_dir.iterdir()
        if d.is_dir() and not (d / "SKILL.md").is_file()
    )
    errors, warnings = [], []
    for d in no_skb:
        if not want or d in want:
            warnings.append(f"{d}: 缺少 SKILL.md（链接脚本将跳过）")

    for s in skills:
        e, w = check_skill(s)
        errors.extend(e)
        warnings.extend(w)
        errors.extend(redline_scan(s))
        pe, pw = port_scan(s)
        errors.extend(pe)
        warnings.extend(pw)
        de, dw = check_dependencies(s)
        errors.extend(de)
        warnings.extend(dw)

    pe, pw = check_profiles(repo)
    errors.extend(pe)
    warnings.extend(pw)

    # 推荐部署名单（只在全量检查时核对，--include 过滤后名单天然不全）
    if not want:
        rec = read_recommended(repo)
        if rec is None:
            warnings.append("config/recommended-skills.txt 不存在或不可读，跳过推荐名单检查")
        else:
            have = {s.name for s in skills}
            for n in rec:
                if n not in have:
                    errors.append(f"推荐名单 {n} 在 skills/ 下无对应目录（含 SKILL.md）")
            for s in skills:
                if (s / "package.json").is_file() and s.name not in rec:
                    warnings.append(f"{s.name} 含 package.json（需依赖安装？）但不在推荐名单中")

    # README 索引
    readme = repo / "README.md"
    if readme.is_file():
        try:
            idx = readme.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as e:
            errors.append(f"README.md 不可读（{e}）")
            idx = ""
        for s in skills:
            if f"skills/{s.name}" not in idx:
                errors.append(f"{s.name}: README.md 缺少 skills/{s.name} 检索入口")
        for m in sorted(set(re.findall(r"skills/([a-z0-9]+(?:-[a-z0-9]+)*)", idx))):
            if not (skills_dir / m).is_dir():
                warnings.append(f"README.md 提及 skills/{m}，但目录不存在（孤儿入口？）")
    else:
        warnings.append("README.md 不存在，跳过索引检查")

    # harness 安装数
    if not args.no_harness:
        repo_names = {s.name for s in skills}
        for label, target in harness_targets():
            if not target.is_dir():
                errors.append(f"[{label}] 缺失目录: {target}")
                continue
            ok = missing = drift = wrong = 0
            for s in skills:
                link = target / s.name
                if not os.path.lexists(link):
                    missing += 1
                    errors.append(f"[{label}] {s.name} 缺失（期望 -> {s}）")
                    continue
                tgt = link_target(str(link))
                if tgt is None:
                    drift += 1
                    errors.append(f"[{label}] {s.name} 是实体目录/文件，需备份后替换为链接")
                    continue
                exp = os.path.normcase(os.path.abspath(s))
                if tgt == exp:
                    ok += 1
                else:
                    wrong += 1
                    errors.append(f"[{label}] {s.name} 指向错误: {tgt}")
            try:
                extras = sorted(
                    p.name for p in target.iterdir()
                    if p.name not in repo_names
                    and os.path.lexists(str(p))
                    and "AGENTS" not in p.name
                    and not p.name.startswith(".")
                )
            except OSError:
                extras = []
            print(f"[{label}] {ok}/{len(skills)} OK，缺失{missing}，实体{drift}，"
                  f"指错{wrong}，额外{len(extras)}"
                  + (f"（{', '.join(extras[:8])}{'…' if len(extras) > 8 else ''}）" if extras else ""))
            if extras and ("system" not in extras):
                pass  # harness 自带/第三方内容不动，仅告知数量

    print(f"仓库 skill 数: {len(skills)}")
    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    failed = bool(errors) or (args.strict and bool(warnings))
    print("FAIL" if failed else "全部校验通过。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
