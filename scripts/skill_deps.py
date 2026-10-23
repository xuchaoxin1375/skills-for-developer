"""skills/*/dependencies.json 的共享结构定义与校验。

声明格式与语义见 docs/skill-dependencies.md；本模块只负责结构，
不探测本机环境。scripts/check-skills.py 用它做静态校验，
scripts/check-skill-deps.py 用它读取并校验后再做运行时检查。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_VERSION = 1
KINDS = {"runtime", "command", "browser", "env", "network"}
TOP_KEYS = {"schemaVersion", "requirements"}
REQ_KEYS = {
    "id",
    "required",
    "hint",
    "kind",
    "name",
    "minVersion",
    "url",
    "alternatives",
    "platforms",
}
OPTION_KEYS = {"kind", "name", "minVersion", "url"}
PLATFORMS = {"windows", "linux", "macos"}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")

PROFILE_TOP_KEYS = {"schemaVersion", "default", "profiles", "tools"}
PROFILE_KEYS = {"label", "description", "extends", "tools"}
TOOL_KEYS = {"label", "why", "requirement", "install", "impact", "alternative"}


def load_manifest(path: Path) -> object:
    """读取 JSON 声明；解析错误由调用方转成带路径的提示。"""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _validate_platforms(spec: dict, where: str) -> list[str]:
    if "platforms" not in spec:
        return []
    platforms = spec["platforms"]
    if not isinstance(platforms, list) or not platforms:
        return [f"{where}.platforms 必须是非空数组"]
    unknown = sorted({str(item) for item in platforms} - PLATFORMS)
    return [f"{where}.platforms 含未知平台: {', '.join(unknown)}"] if unknown else []


def _validate_spec(spec: object, where: str, allowed: set[str]) -> list[str]:
    """校验一个依赖项或备选项的公共字段。"""
    errors: list[str] = []
    if not isinstance(spec, dict):
        return [f"{where} 必须是对象"]
    extra = sorted(set(spec) - allowed)
    if extra:
        errors.append(f"{where} 含未知字段: {', '.join(extra)}")
    kind = spec.get("kind")
    if kind not in KINDS:
        errors.append(f"{where} kind 必须是 {'/'.join(sorted(KINDS))} 之一")
        return errors

    name = spec.get("name")
    if kind in {"runtime", "command", "env"}:
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where} kind={kind} 需要非空 name")
    elif "name" in spec:
        errors.append(f"{where} kind={kind} 不允许 name")

    if "minVersion" in spec:
        if kind not in {"runtime", "command"}:
            errors.append(f"{where} minVersion 只用于 runtime/command")
        elif not isinstance(spec["minVersion"], str) or not VERSION_RE.match(spec["minVersion"]):
            errors.append(f"{where} minVersion 须为点分数字（如 3.9、18）")

    errors.extend(_validate_platforms(spec, where))

    if kind == "network":
        url = spec.get("url")
        if url is not None and (
            not isinstance(url, str) or not url.startswith(("http://", "https://"))
        ):
            errors.append(f"{where} url 须以 http:// 或 https:// 开头")
    elif "url" in spec:
        errors.append(f"{where} url 只用于 network")
    return errors


def validate_manifest(data: object) -> list[str]:
    """返回结构错误列表；空列表表示通过。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是对象"]
    extra = sorted(set(data) - TOP_KEYS)
    if extra:
        errors.append(f"含未知顶层字段: {', '.join(extra)}")

    version = data.get("schemaVersion")
    if isinstance(version, bool) or not isinstance(version, int) or version != SCHEMA_VERSION:
        errors.append(f"schemaVersion 必须是 {SCHEMA_VERSION}")

    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append("requirements 必须是非空数组")
        return errors

    seen: set[str] = set()
    for index, req in enumerate(requirements, 1):
        where = f"requirements[{index}]"
        if not isinstance(req, dict):
            errors.append(f"{where} 必须是对象")
            continue
        extra = sorted(set(req) - REQ_KEYS)
        if extra:
            errors.append(f"{where} 含未知字段: {', '.join(extra)}")

        req_id = req.get("id")
        if not isinstance(req_id, str) or not ID_RE.match(req_id):
            errors.append(f"{where}.id 须为 kebab-case")
        elif req_id in seen:
            errors.append(f"{where}.id 重复: {req_id}")
        else:
            seen.add(req_id)

        if "required" in req and not isinstance(req["required"], bool):
            errors.append(f"{where}.required 必须是布尔值")
        if "hint" in req and (
            not isinstance(req["hint"], str) or not req["hint"].strip()
        ):
            errors.append(f"{where}.hint 必须是非空字符串")

        has_kind = "kind" in req
        has_alternatives = "alternatives" in req
        if has_kind == has_alternatives:
            errors.append(f"{where} 必须且只能有 kind 或 alternatives")
            continue
        if has_kind:
            errors.extend(_validate_spec(req, where, REQ_KEYS))
            continue

        extra = sorted(set(req) - {"id", "required", "hint", "alternatives", "platforms"})
        if extra:
            errors.append(f"{where} alternatives 模式不支持字段: {', '.join(extra)}")
        errors.extend(_validate_platforms(req, where))
        alternatives = req["alternatives"]
        if not isinstance(alternatives, list) or not alternatives:
            errors.append(f"{where}.alternatives 必须是非空数组")
            continue
        for option_index, option in enumerate(alternatives, 1):
            errors.extend(
                _validate_spec(option, f"{where}.alternatives[{option_index}]", OPTION_KEYS)
            )
    return errors


def validate_profiles(data: object) -> list[str]:
    """校验 config/dependency-profiles.json（依赖套餐）的结构。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是对象"]
    extra = sorted(set(data) - PROFILE_TOP_KEYS)
    if extra:
        errors.append(f"含未知顶层字段: {', '.join(extra)}")
    version = data.get("schemaVersion")
    if isinstance(version, bool) or not isinstance(version, int) or version != SCHEMA_VERSION:
        errors.append(f"schemaVersion 必须是 {SCHEMA_VERSION}")

    profiles = data.get("profiles")
    tools = data.get("tools")
    if not isinstance(profiles, dict) or not profiles:
        errors.append("profiles 必须是非空对象")
    if not isinstance(tools, dict) or not tools:
        errors.append("tools 必须是非空对象")
    if errors:
        return errors

    for key, tool in tools.items():
        where = f"tools.{key}"
        if not isinstance(key, str) or not ID_RE.match(key):
            errors.append(f"{where} 工具名须为 kebab-case")
        if not isinstance(tool, dict):
            errors.append(f"{where} 必须是对象")
            continue
        extra = sorted(set(tool) - TOOL_KEYS)
        if extra:
            errors.append(f"{where} 含未知字段: {', '.join(extra)}")
        label = tool.get("label")
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{where}.label 必须是非空字符串")
        for field in ("why", "impact", "alternative"):
            if field in tool and (
                not isinstance(tool[field], str) or not tool[field].strip()
            ):
                errors.append(f"{where}.{field} 必须是非空字符串")

        requirement = tool.get("requirement")
        requirement_errors = validate_manifest(
            {"schemaVersion": SCHEMA_VERSION, "requirements": [requirement]}
        )
        errors.extend(f"{where}.requirement: {message}" for message in requirement_errors)
        if isinstance(requirement, dict) and requirement.get("id") != key:
            errors.append(f"{where}.requirement.id 必须与工具名一致")

        install = tool.get("install")
        if not isinstance(install, dict) or not install:
            errors.append(f"{where}.install 必须是非空对象")
        else:
            for platform, command in install.items():
                if platform not in {"windows", "linux", "macos", "default"}:
                    errors.append(f"{where}.install 含未知平台: {platform}")
                if not isinstance(command, str) or not command.strip():
                    errors.append(f"{where}.install.{platform} 必须是非空命令")

    for name, profile in profiles.items():
        where = f"profiles.{name}"
        if not isinstance(name, str) or not ID_RE.match(name):
            errors.append(f"{where} 套餐名须为 kebab-case")
        if not isinstance(profile, dict):
            errors.append(f"{where} 必须是对象")
            continue
        extra = sorted(set(profile) - PROFILE_KEYS)
        if extra:
            errors.append(f"{where} 含未知字段: {', '.join(extra)}")
        label = profile.get("label")
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{where}.label 必须是非空字符串")
        extends = profile.get("extends")
        if extends is not None and (
            not isinstance(extends, str) or extends not in profiles
        ):
            errors.append(f"{where}.extends 必须指向已存在的套餐")
        names = profile.get("tools")
        if not isinstance(names, list):
            errors.append(f"{where}.tools 必须是数组")
        else:
            seen: set[str] = set()
            for tool_name in names:
                if not isinstance(tool_name, str) or tool_name not in tools:
                    errors.append(f"{where}.tools 含未知工具: {tool_name}")
                elif tool_name in seen:
                    errors.append(f"{where}.tools 重复: {tool_name}")
                else:
                    seen.add(tool_name)

    default = data.get("default")
    if not isinstance(default, str) or default not in profiles:
        errors.append("default 必须指向已存在的套餐")

    for name in profiles:
        seen: set[str] = set()
        current = name
        while (
            isinstance(current, str)
            and current in profiles
            and isinstance(profiles[current], dict)
        ):
            if current in seen:
                errors.append(f"profiles.{name} 的 extends 出现循环")
                break
            seen.add(current)
            current = profiles[current].get("extends")
    return errors
