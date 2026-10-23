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
REQ_KEYS = {"id", "required", "hint", "kind", "name", "minVersion", "url", "alternatives"}
OPTION_KEYS = {"kind", "name", "minVersion", "url"}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")


def load_manifest(path: Path) -> object:
    """读取 JSON 声明；解析错误由调用方转成带路径的提示。"""
    return json.loads(path.read_text(encoding="utf-8-sig"))


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

        extra = sorted(set(req) - {"id", "required", "hint", "alternatives"})
        if extra:
            errors.append(f"{where} alternatives 模式不支持字段: {', '.join(extra)}")
        alternatives = req["alternatives"]
        if not isinstance(alternatives, list) or not alternatives:
            errors.append(f"{where}.alternatives 必须是非空数组")
            continue
        for option_index, option in enumerate(alternatives, 1):
            errors.extend(
                _validate_spec(option, f"{where}.alternatives[{option_index}]", OPTION_KEYS)
            )
    return errors
