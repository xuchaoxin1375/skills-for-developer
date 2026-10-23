#!/usr/bin/env python3
"""按 skills/*/dependencies.json 检查本机依赖（零第三方依赖）。

用法:
    python -X utf8 scripts/check-skill-deps.py
    python -X utf8 scripts/check-skill-deps.py --json
    python -X utf8 scripts/check-skill-deps.py --skill mermaid-render-fix
    python -X utf8 scripts/check-skill-deps.py --profile standard
    python -X utf8 scripts/check-skill-deps.py --list-profiles
    python -X utf8 scripts/check-skill-deps.py --strict

声明格式见 docs/skill-dependencies.md。
检查复用 resource-inventory/scripts/inventory.py --json 的运行时/浏览器结果；
不重复探测规则，不安装依赖，不联网（network 类只报 unknown）。

退出码: 0 必需依赖满足；1 缺失/版本不符（--strict 下 unknown/可选缺失也算）；
        2 声明或探测本身失败。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_deps import load_manifest, validate_manifest, validate_profiles  # noqa: E402

VERSION_RE = re.compile(r"\d+(?:\.\d+)*")
STATUS_LABEL = {
    "ok": "OK",
    "missing": "MISSING",
    "mismatch": "VERSION",
    "unknown": "UNKNOWN",
    "optional-missing": "OPTIONAL",
}


class CheckError(Exception):
    """声明或依赖探测失败，对应退出码 2。"""


def parse_version(text: str) -> tuple[int, ...]:
    match = VERSION_RE.search(text or "")
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def version_at_least(actual: tuple[int, ...], minimum: tuple[int, ...]) -> bool:
    size = max(len(actual), len(minimum))
    return actual + (0,) * (size - len(actual)) >= minimum + (0,) * (size - len(minimum))


def load_manifests(repo: Path, wanted: set[str]) -> list[tuple[str, dict]]:
    manifests: list[tuple[str, dict]] = []
    for path in sorted((repo / "skills").glob("*/dependencies.json")):
        name = path.parent.name
        if wanted and name not in wanted:
            continue
        try:
            data = load_manifest(path)
        except (OSError, ValueError) as error:
            raise CheckError(f"{path} 无法读取或解析: {error}") from error
        errors = validate_manifest(data)
        if errors:
            raise CheckError(f"{path} 结构不合法: " + "; ".join(errors))
        manifests.append((name, data))  # type: ignore[arg-type]
    return manifests


def run_inventory(script: Path, repo: Path, timeout: float) -> dict:
    if not script.is_file():
        raise CheckError(f"找不到 resource-inventory 脚本: {script}")
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(script),
        "--json",
        "--only",
        "runtimes,browsers",
        "--skills-root",
        str(repo / "skills"),
    ]
    env = {**os.environ, "PYTHONUTF8": "1"}
    try:
        process = subprocess.run(  # noqa: S603 - 参数为仓库内固定脚本
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckError(f"inventory.py 执行失败: {error}") from error
    if process.returncode != 0:
        detail = process.stderr.strip().splitlines()
        raise CheckError(
            f"inventory.py 退出码 {process.returncode}"
            + (f": {detail[0][:200]}" if detail else "")
        )
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise CheckError(f"inventory.py 输出无法解析: {error}") from error
    if not isinstance(report, dict):
        raise CheckError("inventory.py 输出不是 JSON 对象")
    return report


class Inventory:
    """把 inventory.py 的报告整理成按名字/浏览器查询的索引。"""

    def __init__(self, report: dict) -> None:
        runtimes = report.get("runtimes") or {}
        self.runtimes = {
            str(tool.get("name", "")).lower(): tool
            for tool in runtimes.get("tools", [])
            if tool.get("name")
        }
        browsers = report.get("browsers") or {}
        self.browsers = [
            item for item in browsers.get("candidates", []) if item.get("eligible")
        ]


def spec_label(spec: dict) -> str:
    kind = spec["kind"]
    if kind in {"browser", "network"}:
        return kind
    return f"{kind}:{spec.get('name', '?')}"


def check_spec(spec: dict, inventory: Inventory) -> tuple[str, str]:
    """返回 (status, detail)。status ∈ ok/missing/mismatch/unknown。"""
    kind = spec["kind"]
    if kind in {"runtime", "command"}:
        name = spec["name"]
        tool = inventory.runtimes.get(name.lower())
        if tool:
            version_text = str(tool.get("version") or "")
            detail = f"{version_text or '?'} ({tool.get('path')})"
            minimum = spec.get("minVersion")
            if minimum:
                actual = parse_version(version_text)
                if not actual:
                    return "unknown", f"{detail}；版本无法解析"
                if not version_at_least(actual, parse_version(minimum)):
                    return "mismatch", detail
            return "ok", detail
        located = shutil.which(name)
        if not located:
            return "missing", "PATH 上未找到"
        if kind == "runtime" and spec.get("minVersion"):
            return "unknown", f"{located}；版本未探测"
        return "ok", located
    if kind == "browser":
        if inventory.browsers:
            item = inventory.browsers[0]
            return "ok", f"{item.get('browser')}: {item.get('path')}"
        return "missing", "未发现可用浏览器"
    if kind == "env":
        return ("ok", "已设置") if os.environ.get(spec["name"]) else ("missing", "未设置")
    if kind == "network":
        return "unknown", "未联网探测"
    return "unknown", f"未知 kind: {kind}"


def check_requirement(req: dict, inventory: Inventory) -> tuple[str, str]:
    if "alternatives" in req:
        results = [
            (spec_label(option), *check_spec(option, inventory))
            for option in req["alternatives"]
        ]
        for label, status, detail in results:
            if status == "ok":
                return "ok", f"{label} ({detail})"
        if any(status == "unknown" for _, status, _ in results):
            unknown = [label for label, status, _ in results if status == "unknown"]
            return "unknown", "未确定: " + ", ".join(unknown)
        return "missing", "候选均不可用: " + ", ".join(label for label, _, _ in results)
    return check_spec(req, inventory)


def check_skill(name: str, manifest: dict, inventory: Inventory) -> dict:
    requirements = []
    for req in manifest["requirements"]:
        status, detail = check_requirement(req, inventory)
        required = req.get("required", True)
        if not required and status in {"missing", "mismatch"}:
            status = "optional-missing"
        requirements.append(
            {
                "id": req["id"],
                "required": required,
                "status": status,
                "detail": detail,
                "hint": req.get("hint", ""),
            }
        )
    failed = any(
        item["required"] and item["status"] in {"missing", "mismatch"}
        for item in requirements
    )
    warned = any(item["status"] in {"unknown", "optional-missing"} for item in requirements)
    return {
        "name": name,
        "ok": not failed,
        "warn": warned,
        "requirements": requirements,
    }


def platform_key() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def load_profile_config(repo: Path) -> dict:
    path = repo / "config" / "dependency-profiles.json"
    if not path.is_file():
        raise CheckError(f"找不到依赖套餐配置: {path}")
    try:
        data = load_manifest(path)
    except (OSError, ValueError) as error:
        raise CheckError(f"{path} 无法读取或解析: {error}") from error
    errors = validate_profiles(data)
    if errors:
        raise CheckError(f"{path} 结构不合法: " + "; ".join(errors))
    return data  # type: ignore[return-value]


def resolve_profile(name: str, config: dict) -> list[str]:
    profiles = config["profiles"]

    def walk(current: str, seen: set[str]) -> list[str]:
        if current in seen:
            raise CheckError(f"套餐 extends 出现循环: {current}")
        profile = profiles[current]
        parent = profile.get("extends")
        tools = walk(parent, seen | {current}) if parent else []
        for tool in profile.get("tools", []):
            if tool not in tools:
                tools.append(tool)
        return tools

    return walk(name, set())


def check_profile(name: str, config: dict, inventory: Inventory) -> dict:
    profile = config["profiles"][name]
    tools = []
    for key in resolve_profile(name, config):
        tool = config["tools"][key]
        requirement = tool["requirement"]
        status, detail = check_requirement(requirement, inventory)
        required = requirement.get("required", True)
        if not required and status in {"missing", "mismatch"}:
            status = "optional-missing"
        install = tool.get("install") or {}
        command = install.get(platform_key()) or install.get("default", "")
        tools.append(
            {
                "id": key,
                "label": tool.get("label", key),
                "required": required,
                "status": status,
                "detail": detail,
                "why": tool.get("why", ""),
                "install": command,
                "impact": tool.get("impact", ""),
                "alternative": tool.get("alternative", ""),
            }
        )
    failed = any(
        item["required"] and item["status"] in {"missing", "mismatch"} for item in tools
    )
    warned = any(item["status"] in {"unknown", "optional-missing"} for item in tools)
    return {
        "name": name,
        "label": profile.get("label", name),
        "description": profile.get("description", ""),
        "ok": not failed,
        "warn": warned,
        "tools": tools,
    }


def render_profile_human(profile: dict, strict: bool) -> str:
    lines = [f"== 依赖套餐: {profile['name']} / {profile['label']} =="]
    if profile["description"]:
        lines.append(profile["description"])
    lines.append("")
    for item in profile["tools"]:
        suffix = "" if item["required"] else " (可选)"
        lines.append(
            f"  {item['id']:<16} {STATUS_LABEL[item['status']]:<9} {item['detail']}{suffix}"
        )
        if item["status"] != "ok":
            if item["why"]:
                lines.append(f"    为什么: {item['why']}")
            if item["install"]:
                lines.append(f"    安装: {item['install']}")
            if item["impact"]:
                lines.append(f"    影响: {item['impact']}")
            if item["alternative"]:
                lines.append(f"    替代: {item['alternative']}")
    counts: dict[str, int] = {}
    for item in profile["tools"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    lines.append("")
    lines.append(
        f"汇总: {len(profile['tools'])} 项；缺失 {counts.get('missing', 0)}，"
        f"版本不符 {counts.get('mismatch', 0)}，未知 {counts.get('unknown', 0)}，"
        f"可选缺失 {counts.get('optional-missing', 0)}"
    )
    if strict:
        lines.append("--strict 已开启：unknown 与可选缺失也计入失败。")
    return "\n".join(lines)


def summary_of(items: list[dict]) -> dict:
    return {
        "tools": len(items),
        "missing": sum(1 for item in items if item["status"] == "missing"),
        "mismatch": sum(1 for item in items if item["status"] == "mismatch"),
        "unknown": sum(1 for item in items if item["status"] == "unknown"),
        "optionalMissing": sum(
            1 for item in items if item["status"] == "optional-missing"
        ),
    }


def render_human(results: list[dict], strict: bool) -> str:
    lines = ["== skill 依赖 =="]
    for skill in results:
        mark = "FAIL" if not skill["ok"] else ("WARN" if skill["warn"] else "OK")
        lines.append(f"[{skill['name']}] {mark}")
        for item in skill["requirements"]:
            suffix = "" if item["required"] else " (可选)"
            lines.append(
                f"  {item['id']:<20} {STATUS_LABEL[item['status']]:<9} {item['detail']}{suffix}"
            )
            if item["hint"] and item["status"] not in {"ok"}:
                lines.append(f"  {'':20} 提示: {item['hint']}")
    counts: dict[str, int] = {}
    for skill in results:
        for item in skill["requirements"]:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
    lines.append("")
    lines.append(
        f"汇总: {len(results)} 个 skill / {sum(counts.values())} 项依赖；"
        f"缺失 {counts.get('missing', 0)}，版本不符 {counts.get('mismatch', 0)}，"
        f"未知 {counts.get('unknown', 0)}，可选缺失 {counts.get('optional-missing', 0)}"
    )
    if strict:
        lines.append("--strict 已开启：unknown 与可选缺失也计入失败。")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按 skills/*/dependencies.json 或依赖套餐检查本机依赖。",
        epilog=(
            "示例:\n"
            "  python -X utf8 scripts/check-skill-deps.py\n"
            "  python -X utf8 scripts/check-skill-deps.py --json\n"
            "  python -X utf8 scripts/check-skill-deps.py --skill mermaid-render-fix\n"
            "  python -X utf8 scripts/check-skill-deps.py --profile standard\n"
            "  python -X utf8 scripts/check-skill-deps.py --list-profiles\n"
            "  python -X utf8 scripts/check-skill-deps.py --strict"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument(
        "--skill",
        default="",
        help="只检查指定 skill，逗号分隔",
    )
    parser.add_argument(
        "--profile",
        default="",
        help="检查依赖套餐（minimal/standard/full；未给时读 SKILLS_DEPS_PROFILE）",
    )
    parser.add_argument("--list-profiles", action="store_true", help="列出可用依赖套餐")
    parser.add_argument("--strict", action="store_true", help="unknown 与可选缺失也视为失败")
    parser.add_argument("--repo", default="", help="仓库根（默认由脚本位置推导）")
    parser.add_argument(
        "--inventory",
        default="",
        help="resource-inventory 的 inventory.py 路径（默认从仓库推导）",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="inventory.py 超时秒数")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo = Path(args.repo) if args.repo else Path(__file__).resolve().parent.parent
    inventory_path = (
        Path(args.inventory)
        if args.inventory
        else repo / "skills" / "resource-inventory" / "scripts" / "inventory.py"
    )
    wanted = {name.strip() for name in args.skill.split(",") if name.strip()}
    profile_name = args.profile.strip()
    if profile_name and wanted:
        print("错误: --profile 与 --skill 不能同时使用", file=sys.stderr)
        return 2
    if not profile_name and not wanted:
        profile_name = os.environ.get("SKILLS_DEPS_PROFILE", "").strip()

    if args.list_profiles:
        try:
            config = load_profile_config(repo)
        except CheckError as error:
            print(f"错误: {error}", file=sys.stderr)
            return 2
        for name, profile in config["profiles"].items():
            tools = ", ".join(resolve_profile(name, config))
            print(f"{name}\t{profile.get('label', name)}\t{tools}")
            if profile.get("description"):
                print(f"  {profile['description']}")
        return 0

    if profile_name:
        try:
            config = load_profile_config(repo)
            if profile_name not in config["profiles"]:
                choices = ", ".join(config["profiles"])
                raise CheckError(f"未知套餐 {profile_name}；可选 {choices}")
            report = run_inventory(inventory_path, repo, args.timeout)
        except CheckError as error:
            print(f"错误: {error}", file=sys.stderr)
            return 2
        inventory = Inventory(report)
        result = check_profile(profile_name, config, inventory)
        failed = not result["ok"]
        warned = result["warn"]
        summary = summary_of(result["tools"])
        if args.json:
            print(
                json.dumps(
                    {
                        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "mode": "profile",
                        "profile": {
                            "name": result["name"],
                            "label": result["label"],
                            "description": result["description"],
                        },
                        "inventory": str(inventory_path),
                        "strict": args.strict,
                        "tools": result["tools"],
                        "summary": summary,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render_profile_human(result, args.strict))
        return 1 if failed or (args.strict and warned) else 0

    try:
        manifests = load_manifests(repo, wanted)
        if not manifests:
            print("未发现 skills/*/dependencies.json（或过滤后为空）。")
            return 0
        report = run_inventory(inventory_path, repo, args.timeout)
    except CheckError as error:
        print(f"错误: {error}", file=sys.stderr)
        return 2

    inventory = Inventory(report)
    results = [check_skill(name, manifest, inventory) for name, manifest in manifests]
    failed = any(not skill["ok"] for skill in results)
    warned = any(skill["warn"] for skill in results)
    summary = {
        "skills": len(results),
        "requirements": sum(len(skill["requirements"]) for skill in results),
        "missing": sum(
            1 for skill in results for item in skill["requirements"]
            if item["status"] == "missing"
        ),
        "mismatch": sum(
            1 for skill in results for item in skill["requirements"]
            if item["status"] == "mismatch"
        ),
        "unknown": sum(
            1 for skill in results for item in skill["requirements"]
            if item["status"] == "unknown"
        ),
        "optionalMissing": sum(
            1 for skill in results for item in skill["requirements"]
            if item["status"] == "optional-missing"
        ),
    }

    if args.json:
        print(
            json.dumps(
                {
                    "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "inventory": str(inventory_path),
                    "strict": args.strict,
                    "skills": results,
                    "summary": summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_human(results, args.strict))

    return 1 if failed or (args.strict and warned) else 0


if __name__ == "__main__":
    sys.exit(main())
