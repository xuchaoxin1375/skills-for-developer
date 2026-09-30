#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""形态与技术栈推荐器：交互式问卷，输出建议方案与理由。

用法：
    python scripts/recommend.py
    python scripts/recommend.py --batch "不会终端,无网络,数据不出本机,1万条,每天"
"""

from __future__ import annotations

import argparse
import sys

QUESTIONS = [
    ("terminal", "使用者会不会敲命令？(yes/no)", "no"),
    ("unattended", "程序需要无人值守自动运行吗？(yes/no)", "no"),
    ("rich_ui", "需要实时刷新或方向键交互的界面吗？(yes/no)", "no"),
    ("native_window", "需要双击图标打开的窗口或系统托盘吗？(yes/no)", "no"),
    ("offline", "必须在无网络环境下运行吗？(yes/no)", "no"),
    ("team_lang", "维护者熟悉哪门语言？(none/python/go/rust/typescript)", "none"),
    ("scale", "单次处理数据量级？(small/medium/large)", "small"),
]

LANG_STACK = {
    "none": ("Python 3.12 + uv", "生态最全，出问题最容易查到答案"),
    "python": ("Python 3.12 + uv", "复用既有代码与数据处理能力"),
    "go": ("Go 1.23 + Cobra", "编译快、贡献者好找、单文件分发"),
    "rust": ("Rust + clap derive", "启动毫秒级、内存最省、无 GC 停顿"),
    "typescript": ("TypeScript + oclif", "与前端同语言，类型全链路共享"),
}


def ask(key: str, prompt: str, default: str) -> str:
    try:
        raw = input(f"{prompt} [默认 {default}] ").strip().lower()
    except EOFError:
        raw = ""
    return raw or default


def decide(answers: dict[str, str]) -> dict[str, object]:
    if answers["unattended"] == "yes":
        form = "自动化脚本"
    elif answers["terminal"] == "yes":
        form = "TUI 终端界面" if answers["rich_ui"] == "yes" else "CLI 命令行工具"
    elif answers["native_window"] == "yes":
        form = "桌面 GUI"
    else:
        form = "本地 Web UI"

    stack_note = ""
    if form == "桌面 GUI":
        stack = "Tauri 2 + Vite 前端"
        reason = "安装包约 3-15 MB，内存 20-100 MB，自带移动端升级路径"
        alt = "Electron（只写 JS 且要求三平台渲染完全一致时）；Wails v2（团队写 Go）"
        stack_note = "需要安装 Rust 工具链，首次构建约 1 分钟"
    elif form in ("CLI 命令行工具", "TUI 终端界面"):
        lang = answers["team_lang"] if answers["team_lang"] in LANG_STACK else "go"
        stack, why = LANG_STACK[lang]
        reason = f"{why}；单文件分发，拷贝即可运行"
        alt = "Go/Cobra（通用首选）、Rust/clap（性能优先）、Python/Typer（改起来最省事）"
    elif form == "本地 Web UI":
        stack = "Vite + React + Hono 或 FastAPI 本地服务"
        reason = "开发快、界面漂亮、无需安装包与签名"
        alt = "纯静态页面（无后端需求时，复杂度直接减半）"
    else:
        lang = answers["team_lang"] if answers["team_lang"] in LANG_STACK else "none"
        stack, why = LANG_STACK[lang]
        reason = f"{why}；配合系统定时任务即可无人值守"
        alt = "改做 CLI（开始长出第三个参数时）"

    cautions: list[str] = []
    if answers["offline"] == "yes":
        cautions.append("无网络：依赖必须在交付时全部就位，README 提供离线安装说明")
    if answers["scale"] in ("medium", "large"):
        cautions.append("数据量大：使用分批流式处理与进度显示，存储选 SQLite")
    if form == "桌面 GUI":
        cautions.append("跨平台：Tauri 依赖系统 WebView，关键页面需在三个平台各验证一次")
    if form == "自动化脚本":
        cautions.append("无人值守：必须实现幂等、原子写入、并发锁与日志轮转")

    return {
        "form": form,
        "stack": stack,
        "reason": reason,
        "alternatives": alt,
        "cautions": cautions,
        "stack_note": stack_note,
    }


def render(result: dict[str, object]) -> None:
    print("\n=== 推荐结果 ===")
    print(f"程序形态: {result['form']}")
    print(f"推荐栈  : {result['stack']}")
    print(f"理由    : {result['reason']}")
    print(f"备选    : {result['alternatives']}")
    if result["stack_note"]:
        print(f"代价    : {result['stack_note']}")
    print("注意事项:")
    for item in result["cautions"] or ["无特殊注意事项"]:
        print(f"  - {item}")
    print("\n下一步: 把以上结论写入 docs/DECISIONS.md，再按形态读取对应参考文档。")


def main() -> int:
    parser = argparse.ArgumentParser(description="形态与技术栈推荐器")
    parser.add_argument("--batch", help="以逗号分隔的答案串，跳过交互")
    args = parser.parse_args()

    if args.batch:
        parts = [p.strip() for p in args.batch.split(",")]
        if len(parts) != len(QUESTIONS):
            print(f"--batch 需要 {len(QUESTIONS)} 个答案，收到 {len(parts)} 个", file=sys.stderr)
            return 2
        answers = dict(zip([q[0] for q in QUESTIONS], parts))
    else:
        answers = {key: ask(key, prompt, default) for key, prompt, default in QUESTIONS}

    render(decide(answers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
