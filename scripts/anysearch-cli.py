#!/usr/bin/env python3
"""AnySearch 短命令：安装 shim，并把基础调用转发到 AnySearch skill CLI。

日常用法：
  python -X utf8 scripts/anysearch-cli.py --install
  anysearch "查询词"
  ws "查询词"

包装只做入口解析、基础搜索简写与命令管理；查询计划、来源分级与预算仍按
skills/agentic-web-search 的规则执行。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROG = "anysearch"
ALIAS = "ws"
SUBCOMMANDS = {"search", "batch_search", "extract", "get_sub_domains", "doc"}
DEFAULT_LIMIT = "5"


def skill_dir() -> Path:
    override = os.environ.get("ANYSEARCH_SKILL_DIR")
    if override:
        return Path(override).expanduser()
    root = os.environ.get("THIRD_PARTY_SKILLS_HOME")
    base = (
        Path(root).expanduser()
        if root
        else Path.home() / ".local" / "share" / "skills-for-developer" / "third-party"
    )
    return base / "anysearch"


def bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def script_path() -> Path:
    return Path(__file__).resolve()


def help_text() -> str:
    return f"""AnySearch 短命令（基础搜索）

用法:
  {PROG} "查询词"                      通用搜索，默认 {DEFAULT_LIMIT} 条
  {PROG} search "查询词" --max_results 5
  {PROG} batch_search --query A --query B
  {PROG} extract URL
  {PROG} get_sub_domains --domain finance
  {PROG} doc                           完整接口说明
  {ALIAS} "查询词"                     同一入口的短别名

管理:
  {PROG} --install                     安装 {PROG} / {ALIAS} 命令到 ~/.local/bin
  {PROG} --uninstall                   只移除本包装安装的命令
  {PROG} --status                      查看入口、凭据与命令状态

环境变量:
  ANYSEARCH_SKILL_DIR        指定 anysearch skill 目录
  THIRD_PARTY_SKILLS_HOME    第三方 skill 根目录
"""


def normalize(args: list[str]) -> list[str]:
    """首个参数不是子命令或选项时，按基础搜索处理。"""
    if args[0] in SUBCOMMANDS or args[0].startswith("-"):
        return args
    out = ["search", *args]
    has_limit = any(
        a in ("-m", "--max_results") or a.startswith("--max_results=") for a in args
    )
    if not has_limit:
        out += ["--max_results", DEFAULT_LIMIT]
    return out


def resolve_cli() -> list[str]:
    directory = skill_dir()
    py_cli = directory / "scripts" / "anysearch_cli.py"
    js_cli = directory / "scripts" / "anysearch_cli.js"
    if py_cli.is_file() and importlib.util.find_spec("requests") is not None:
        return [sys.executable, "-X", "utf8", str(py_cli)]
    if js_cli.is_file() and shutil.which("node"):
        return ["node", str(js_cli)]
    if py_cli.is_file():
        return [sys.executable, "-X", "utf8", str(py_cli)]
    raise SystemExit(f"AnySearch 未安装或入口缺失：{directory}")


def key_source() -> str:
    if os.environ.get("ANYSEARCH_API_KEY"):
        return "环境变量"
    env_file = skill_dir() / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANYSEARCH_API_KEY" and value.strip():
                return ".env"
    return "无（匿名访问，限流更低）"


def shim_text() -> str:
    python = sys.executable
    script = script_path()
    if os.name == "nt":
        return f'@echo off\r\n"{python}" -X utf8 "{script}" %*\r\n'
    return f'#!/bin/sh\nexec "{python}" -X utf8 "{script}" "$@"\n'


def shim_path(name: str) -> Path:
    return bin_dir() / (f"{name}.cmd" if os.name == "nt" else name)


def install() -> int:
    directory = bin_dir()
    directory.mkdir(parents=True, exist_ok=True)
    text = shim_text()
    for name in (PROG, ALIAS):
        path = shim_path(name)
        if path.exists():
            existing = path.read_text(encoding="utf-8", errors="replace")
            if str(script_path()) not in existing:
                print(f"跳过 {path}：已存在且不是本包装安装")
                continue
            if existing == text:
                print(f"已就绪：{path}")
                continue
        path.write_text(text, encoding="utf-8", newline="")
        if os.name != "nt":
            path.chmod(0o755)
        print(f"已安装：{path}")
    path_dirs = {
        Path(p).resolve()
        for p in os.environ.get("PATH", "").split(os.pathsep)
        if p.strip()
    }
    if directory.resolve() not in path_dirs:
        print(f"提示：把 {directory} 加入 PATH 后，新终端可按命令名调用。")
    return 0


def uninstall() -> int:
    for name in (PROG, ALIAS):
        path = shim_path(name)
        if not path.is_file():
            print(f"未安装：{path}")
            continue
        if str(script_path()) not in path.read_text(encoding="utf-8", errors="replace"):
            print(f"跳过 {path}：不是本包装安装")
            continue
        path.unlink()
        print(f"已移除：{path}")
    return 0


def status() -> int:
    directory = skill_dir()
    py_cli = directory / "scripts" / "anysearch_cli.py"
    js_cli = directory / "scripts" / "anysearch_cli.js"
    print(f"skill 目录：{directory}")
    print(f"Python 入口：{'OK' if py_cli.is_file() else '缺失'}")
    print(f"Node 入口：{'OK' if js_cli.is_file() else '缺失'}")
    print(f"API key：{key_source()}")
    for name in (PROG, ALIAS):
        path = shim_path(name)
        state = "OK" if path.is_file() else "未安装"
        print(f"命令 {name}：{state}（{path}）")
    path_dirs = {
        Path(p).resolve()
        for p in os.environ.get("PATH", "").split(os.pathsep)
        if p.strip()
    }
    print(f"PATH 含 {bin_dir()}：{'是' if bin_dir().resolve() in path_dirs else '否'}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] in ("--install", "--uninstall", "--status"):
        action = args[0]
        return {"--install": install, "--uninstall": uninstall, "--status": status}[action]()
    if not args or args[0] in ("-h", "--help"):
        print(help_text(), end="")
        return 0
    cmd = [*resolve_cli(), *normalize(args)]
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
