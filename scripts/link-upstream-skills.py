#!/usr/bin/env python3
"""Link selected skills from existing upstream clones; never clone, update or edit upstream."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import ModuleType


def load_link_helpers() -> ModuleType:
    path = Path(__file__).with_name("third-party-skills.py")
    spec = importlib.util.spec_from_file_location("upstream_link_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load link helpers: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def inside(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        not relative or pure.is_absolute() or "\\" in relative
        or any(p in {"", ".", ".."} or ":" in p for p in relative.split("/"))
    ):
        raise ValueError(f"Not a relative directory: {relative!r}")
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes source root: {relative!r}")
    return target


def git(directory: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *args], check=True,
        capture_output=True, encoding="utf-8", timeout=20,
    ).stdout.strip()


def sources(
    repo_root: Path, include: set[str], targets: list[tuple[str, Path]] | None = None,
) -> list[tuple[str, Path]]:
    config = repo_root / "config/upstream-skills.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for repository in data["repositories"]:
        clone = inside(repo_root, repository["directory"])
        revision = repository["revision"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("revision must be a full lowercase commit SHA")
        selected = []
        for name, relative in repository["skills"].items():
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or name in seen:
                raise ValueError(f"Invalid or duplicate skill: {name}")
            seen.add(name)
            if (repo_root / "skills" / name / "SKILL.md").exists():
                raise ValueError(f"Upstream name conflicts with local skill: {name}")
            path = inside(clone, relative)
            if not include or name in include:
                selected.append((name, path))
        if not selected:
            continue
        if not clone.exists():
            if any(os.path.lexists(directory / name) for name, _path in selected for _label, directory in (targets or [])):
                raise ValueError(f"Upstream clone missing but skill links/entities exist; restore clone first: {clone}")
            print(f"[upstream] Optional clone missing: {clone}; see docs/upstream-skills.md")
            continue
        if not (clone / ".git").exists():
            raise ValueError(f"Not an independent Git clone: {clone}")
        if git(clone, "rev-parse", "HEAD") != revision:
            raise ValueError(f"Upstream revision differs from config: {clone}")
        if git(clone, "remote", "get-url", "origin") != repository["url"]:
            raise ValueError(f"Upstream origin differs from config: {clone}")
        for name, path in selected:
            if not (path / "SKILL.md").is_file():
                raise ValueError(f"Missing upstream SKILL.md: {path}")
            if git(clone, "status", "--porcelain", "--untracked-files=all", "--", str(path)):
                raise ValueError(f"Upstream skill has local changes; keep them outside upstream: {name}")
            result.append((name, path))
    return result


def link_sources(
    selected: list[tuple[str, Path]], targets: list[tuple[str, Path]], helpers: ModuleType,
    *, verify_only: bool = False, unlink: bool = False, replace: bool = False,
) -> int:
    errors = 0
    for name, source in selected:
        for label, directory in targets:
            link = directory / name
            matches = helpers.is_link_like(link) and helpers.link_points_directly(link, source)
            if unlink:
                if matches:
                    helpers.remove_link(link)
                    print(f"[{label}] {name}: unlinked (source retained)")
                elif os.path.lexists(link):
                    print(f"[{label}] {name}: not our direct link, untouched", file=sys.stderr)
                    errors += 1
                continue
            if matches:
                print(f"[{label}] {name}: OK")
                continue
            if verify_only or (os.path.lexists(link) and not replace):
                print(f"[{label}] {name}: missing/conflicting link; inspect before --replace", file=sys.stderr)
                errors += 1
                continue
            if os.path.lexists(link):
                if helpers.is_link_like(link):
                    helpers.remove_link(link)
                else:
                    helpers.backup_entity(link, label, name)
            helpers.create_link(link, source)
            print(f"[{label}] {name}: linked -> {source}")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Link selected unmodified upstream skills from config/upstream-skills.json; no network.",
        epilog=(
            "Examples: python scripts/link-upstream-skills.py --verify-only; "
            "python scripts/link-upstream-skills.py --include grill-me; "
            "python scripts/link-upstream-skills.py --replace; "
            "python scripts/link-upstream-skills.py --unlink --include grill-me. "
            "Missing clones are optional; version/source drift fails. --replace backs up entities, "
            "replaces link objects only, and never edits source files. Exit: 0 OK, 1 link errors, 2 invalid source/config."
        ),
    )
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--include", action="append", default=[], help="Comma-separated names; repeatable; intersection with config")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true", help="Read-only source/version/link verification")
    mode.add_argument("--unlink", action="store_true", help="Remove matching direct links only; keep upstream clone")
    mode.add_argument("--replace", action="store_true", help="Explicitly migrate conflicting links/entities; entities are backed up")
    args = parser.parse_args(argv)
    try:
        helpers = load_link_helpers()
        include = {name.strip() for value in args.include for name in value.split(",") if name.strip()}
        targets = helpers.harness_targets()
        selected = sources(args.repo_root.resolve(), include, targets)
        return link_sources(
            selected, targets, helpers,
            verify_only=args.verify_only, unlink=args.unlink, replace=args.replace,
        )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"upstream links: {exc}; see docs/upstream-skills.md", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
