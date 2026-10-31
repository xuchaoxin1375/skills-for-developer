#!/usr/bin/env python3
"""第三方 skill 推荐名单的安装、同步与校验工具。

实体不入本仓库：首次安装放到第三方共享根目录
（$THIRD_PARTY_SKILLS_HOME 或 ~/.local/share/skills-for-developer/third-party），
全部 harness 目录建立链接，避免同一 skill 多份副本与本地配置不同步。

日常命令：
  python -X utf8 scripts/third-party-skills.py list
  python -X utf8 scripts/third-party-skills.py status
  python -X utf8 scripts/third-party-skills.py install
  python -X utf8 scripts/third-party-skills.py sync
  python -X utf8 scripts/third-party-skills.py verify
  python -X utf8 scripts/third-party-skills.py uninstall --name anysearch
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "third-party-skills.txt"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 400 * 1024 * 1024
META_NAME = ".third-party-install.json"
INSTALLER_NAME = "scripts/third-party-skills.py"


class RegistryError(Exception):
    pass


class InstallError(Exception):
    pass


@dataclass
class Entry:
    name: str
    repo: str
    kind: str
    ref: str
    preserve: list[str]
    description: str

    @property
    def source_url(self) -> str:
        bucket = "tags" if self.kind == "tag" else "heads"
        return f"https://github.com/{self.repo}/archive/refs/{bucket}/{self.ref}.zip"


def out(message: str = "") -> None:
    print(message)


def warn(message: str) -> None:
    print(f"警告: {message}", file=sys.stderr)


def fail(message: str) -> None:
    print(f"错误: {message}", file=sys.stderr)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def home_dir() -> Path:
    return Path.home()


def agents_home() -> Path:
    return Path(os.environ.get("DSH_AGENTS_HOME") or (home_dir() / ".agents"))


def dsh_home() -> Path:
    return Path(os.environ.get("DSH_HOME") or (home_dir() / ".dsh"))


def third_party_home() -> Path:
    return Path(
        os.environ.get("THIRD_PARTY_SKILLS_HOME")
        or (home_dir() / ".local" / "share" / "skills-for-developer" / "third-party")
    )


def harness_targets() -> list[tuple[str, Path]]:
    return [
        ("opencode", home_dir() / ".config" / "opencode" / "skills"),
        ("codex", home_dir() / ".codex" / "skills"),
        ("claude", home_dir() / ".claude" / "skills"),
        ("agents", agents_home() / "skills"),
        ("dsh", dsh_home() / "skills"),
    ]


def canonical_dir(entry: Entry) -> Path:
    return third_party_home() / entry.name


def backup_root() -> Path:
    return home_dir() / ".third-party-skills-backup"


def split_names(values: list[str] | None) -> list[str]:
    names: list[str] = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names


def parse_registry() -> list[Entry]:
    if not REGISTRY.is_file():
        raise RegistryError(f"缺少第三方 skill 名单: {REGISTRY}")
    entries: list[Entry] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(REGISTRY.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 6:
            raise RegistryError(
                f"{REGISTRY.name}:{lineno}: 需要 6 列（name|repo|kind|ref|preserve|description），实际 {len(parts)} 列"
            )
        name, repo, kind, ref, preserve_raw, description = parts
        if not NAME_RE.match(name):
            raise RegistryError(f"{REGISTRY.name}:{lineno}: 名称不是 kebab-case: {name!r}")
        if name in seen:
            raise RegistryError(f"{REGISTRY.name}:{lineno}: 名称重复: {name}")
        seen.add(name)
        if (REPO_ROOT / "skills" / name / "SKILL.md").is_file():
            raise RegistryError(
                f"{REGISTRY.name}:{lineno}: {name} 与 skills/ 下的自定义 skill 重名；第三方 skill 不能占用真源目录"
            )
        if not REPO_RE.match(repo):
            raise RegistryError(f"{REGISTRY.name}:{lineno}: repo 需为 owner/name: {repo!r}")
        if kind not in {"tag", "branch"}:
            raise RegistryError(f"{REGISTRY.name}:{lineno}: kind 只能是 tag 或 branch: {kind!r}")
        if not ref or not REF_RE.match(ref) or ".." in ref:
            raise RegistryError(f"{REGISTRY.name}:{lineno}: ref 不合法: {ref!r}")
        preserve: list[str] = []
        if preserve_raw:
            for item in preserve_raw.split(","):
                item = item.strip().replace("\\", "/")
                if not item:
                    raise RegistryError(f"{REGISTRY.name}:{lineno}: preserve 含空项")
                p = PurePosixPath(item)
                if p.is_absolute() or ".." in p.parts:
                    raise RegistryError(f"{REGISTRY.name}:{lineno}: preserve 必须是 skill 内的相对路径: {item!r}")
                preserve.append(str(p))
        if not description:
            raise RegistryError(f"{REGISTRY.name}:{lineno}: description 不能为空")
        entries.append(Entry(name, repo, kind, ref, preserve, description))
    return entries


def select_entries(entries: list[Entry], names: list[str]) -> list[Entry]:
    if not names:
        return entries
    by_name = {e.name: e for e in entries}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise RegistryError(f"名单中没有这些第三方 skill: {', '.join(unknown)}")
    return [by_name[n] for n in names]


def is_link_like(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if hasattr(path, "is_junction") and path.is_junction():
            return True
        os.readlink(path)
        return True
    except (OSError, ValueError):
        return False


def resolved(path: Path) -> Path:
    return Path(os.path.realpath(path))


def same_path(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(str(resolved(a))) == os.path.normcase(str(resolved(b)))
    except OSError:
        return False


def direct_target(path: Path) -> Path | None:
    """读取链接的第一跳目标；不是链接或读取失败时返回 None。"""
    try:
        raw = os.readlink(path)
    except (OSError, ValueError):
        return None
    if raw.startswith("\\\\?\\"):
        raw = raw[4:]
    target = Path(raw)
    if not target.is_absolute():
        target = path.parent / target
    return target


def link_points_directly(link: Path, target: Path) -> bool:
    direct = direct_target(link)
    if direct is None:
        return False
    # 只比较链接里存的第一跳路径，不穿透中间链接，避免把链式链接误判为直接链接。
    return os.path.normcase(os.path.abspath(direct)) == os.path.normcase(os.path.abspath(target))


def unique_path(path: Path) -> Path:
    if not os.path.lexists(path):
        return path
    for i in range(1, 1000):
        candidate = path.with_name(f"{path.name}-{i}")
        if not os.path.lexists(candidate):
            return candidate
    raise InstallError(f"无法找到可用的备份路径: {path}")


def backup_entity(path: Path, label: str, name: str) -> Path:
    dest = unique_path(backup_root() / now_stamp() / label / name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dest))
    out(f"  已备份原有实体: {path} -> {dest}")
    return dest


def create_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).decode(errors="replace").strip()
            raise InstallError(f"创建 Junction 失败: {link} -> {target} {detail}")
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_link(link: Path) -> None:
    try:
        os.unlink(link)
    except OSError:
        os.rmdir(link)


def read_meta(directory: Path | None) -> dict | None:
    if directory is None:
        return None
    path = directory / META_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        warn(f"安装元数据不可读，按未登记处理: {path} ({exc})")
        return None


def meta_matches(entry: Entry, meta: dict | None) -> bool:
    return bool(meta) and (
        meta.get("repo") == entry.repo
        and meta.get("kind") == entry.kind
        and meta.get("ref") == entry.ref
    )


def write_meta(directory: Path, entry: Entry, digest: str) -> None:
    data = {
        "name": entry.name,
        "repo": entry.repo,
        "kind": entry.kind,
        "ref": entry.ref,
        "source_url": entry.source_url,
        "archive_sha256": digest,
        "preserve": entry.preserve,
        "installed_at": now_iso(),
        "installer": INSTALLER_NAME,
    }
    with open(directory / META_NAME, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def find_legacy_entity(entry: Entry) -> Path | None:
    for _label, target_dir in harness_targets():
        path = target_dir / entry.name
        if os.path.lexists(path) and not is_link_like(path) and (path / "SKILL.md").is_file():
            return path
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(entry: Entry, timeout: int, proxy: str | None) -> tuple[Path, str]:
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        entry.source_url,
        headers={"User-Agent": "skills-for-developer-third-party-installer/1"},
    )
    out(f"  下载 {entry.source_url}")
    fd, raw = tempfile.mkstemp(prefix=f"third-party-{entry.name}-", suffix=".zip")
    os.close(fd)
    dest = Path(raw)
    try:
        with opener.open(req, timeout=timeout) as resp, open(dest, "wb") as fh:
            total = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise InstallError(f"压缩包超过 {MAX_ARCHIVE_BYTES // (1024 * 1024)} MiB，拒绝安装")
                fh.write(chunk)
        return dest, sha256_file(dest)
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def validate_zip(zf: zipfile.ZipFile) -> None:
    total = 0
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        pure = PurePosixPath(name)
        if not name or pure.is_absolute() or ".." in pure.parts:
            raise InstallError(f"压缩包含不安全路径: {info.filename!r}")
        if pure.parts and re.match(r"^[A-Za-z]:", pure.parts[0]):
            raise InstallError(f"压缩包含绝对盘符路径: {info.filename!r}")
        if any(":" in part for part in pure.parts):
            raise InstallError(f"压缩包含 Windows 非法路径: {info.filename!r}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise InstallError(f"压缩包含符号链接，拒绝安装: {info.filename!r}")
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise InstallError(f"解压后超过 {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MiB，拒绝安装")


def payload_root(extract_dir: Path) -> Path:
    if (extract_dir / "SKILL.md").is_file():
        return extract_dir
    dirs = [p for p in extract_dir.iterdir() if p.is_dir() and p.name != "__MACOSX"]
    if len(dirs) == 1 and (dirs[0] / "SKILL.md").is_file():
        return dirs[0]
    raise InstallError("压缩包内未找到唯一的 skill 目录（需要 SKILL.md）")


def verify_manifest(root: Path) -> None:
    manifest = root / "SHA256SUMS.txt"
    if not manifest.is_file():
        return
    out("  校验 SHA256SUMS.txt")
    for lineno, raw in enumerate(manifest.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise InstallError(f"SHA256SUMS.txt:{lineno}: 格式不合法")
        expected, rel = parts
        rel = rel.lstrip("*").replace("\\", "/")
        pure = PurePosixPath(rel)
        if pure.is_absolute() or ".." in pure.parts:
            raise InstallError(f"SHA256SUMS.txt:{lineno}: 路径不安全: {rel!r}")
        target = root / rel
        if not target.is_file():
            raise InstallError(f"SHA256SUMS.txt:{lineno}: 文件不存在: {rel}")
        actual = sha256_file(target)
        if actual.lower() != expected.lower():
            raise InstallError(f"SHA256SUMS.txt:{lineno}: 校验失败: {rel}")


def copy_preserved(old_dir: Path | None, new_dir: Path, entry: Entry, old_meta: dict | None) -> None:
    if old_dir is None:
        return
    preserved = list(entry.preserve)
    if old_meta:
        for item in old_meta.get("preserve", []):
            if isinstance(item, str) and item not in preserved:
                preserved.append(item)
    for rel in preserved:
        pure = PurePosixPath(rel)
        if pure.is_absolute() or ".." in pure.parts:
            warn(f"忽略不安全的保留路径: {rel!r}")
            continue
        src = old_dir / rel
        if not os.path.lexists(src):
            continue
        dst = new_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        out(f"  保留本地文件: {rel}")


def install_entry(entry: Entry, force: bool, sync_mode: bool, timeout: int, proxy: str | None) -> None:
    target = canonical_dir(entry)
    old_dir: Path | None = None
    if os.path.lexists(target):
        if is_link_like(target):
            raise InstallError(f"共享实体路径是链接，需手工处理: {target}")
        old_dir = target
    else:
        old_dir = find_legacy_entity(entry)

    old_meta = read_meta(old_dir)
    installed = meta_matches(entry, old_meta)
    if not force and target.is_dir() and installed and entry.kind == "tag":
        out(f"[{entry.name}] 已是 {entry.ref}，跳过下载")
        ensure_links(entry)
        return
    if not force and target.is_dir() and sync_mode and installed and entry.kind == "branch":
        out(f"[{entry.name}] 分支 {entry.ref} 已安装；分支模式同步仍会重新拉取")
    if not force and target.is_dir() and not sync_mode and installed:
        out(f"[{entry.name}] 已安装 {entry.ref}（用 --force 重装）")
        ensure_links(entry)
        return

    with tempfile.TemporaryDirectory(prefix=f"third-party-{entry.name}-") as tmp:
        tmp_path = Path(tmp)
        zip_path, digest = download(entry, timeout, proxy)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                validate_zip(zf)
                extract_dir = tmp_path / "extract"
                extract_dir.mkdir()
                zf.extractall(extract_dir)
            payload = payload_root(extract_dir)
            verify_manifest(payload)
            copy_preserved(old_dir, payload, entry, old_meta)

            if os.path.lexists(target):
                backup_entity(target, "third-party", entry.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(payload), str(target))
            write_meta(target, entry, digest)
            out(f"[{entry.name}] 已安装 {entry.ref} -> {target}")
        finally:
            zip_path.unlink(missing_ok=True)

    ensure_links(entry)


def ensure_links(entry: Entry) -> None:
    canonical = canonical_dir(entry)
    if not (canonical / "SKILL.md").is_file():
        raise InstallError(f"共享实体缺少 SKILL.md: {canonical}")
    targets = harness_targets()
    # 先处理 agents：它可能是旧版共享实体所在位置，先迁走再修正其他链接。
    targets.sort(key=lambda item: 0 if item[0] == "agents" else 1)
    for label, target_dir in targets:
        link = target_dir / entry.name
        if os.path.lexists(link):
            if link_points_directly(link, canonical):
                out(f"  [{label}] 链接正常")
                continue
            if is_link_like(link):
                if same_path(link, canonical):
                    remove_link(link)
                    create_link(link, canonical)
                    out(f"  [{label}] 已改为直接链接 -> {canonical}")
                else:
                    warn(f"[{label}] {link} 指向别处（{resolved(link)}），不覆盖")
                continue
            backup_entity(link, label, entry.name)
        create_link(link, canonical)
        out(f"  [{label}] 已链接 -> {canonical}")


def status_entry(entry: Entry) -> None:
    target = canonical_dir(entry)
    meta = read_meta(target)
    if not target.is_dir():
        legacy = find_legacy_entity(entry)
        suffix = f"（发现旧实体 {legacy}）" if legacy else ""
        out(f"[{entry.name}] 未安装 {entry.ref}{suffix}")
        return
    if meta:
        if meta_matches(entry, meta):
            state = "已安装"
        else:
            state = f"可更新 {meta.get('repo')}@{meta.get('ref')} -> {entry.repo}@{entry.ref}"
        out(f"[{entry.name}] {state}：{target}")
    else:
        out(f"[{entry.name}] 已存在但无安装元数据：{target}")
    for label, target_dir in harness_targets():
        link = target_dir / entry.name
        if not os.path.lexists(link):
            out(f"  [{label}] 缺失")
        elif link_points_directly(link, target):
            out(f"  [{label}] OK")
        elif same_path(link, target):
            out(f"  [{label}] 非直接链接（重跑 sync 修正）")
        else:
            out(f"  [{label}] 指向异常: {link}")


def verify_entries(entries: list[Entry], strict: bool) -> int:
    errors = 0
    for entry in entries:
        target = canonical_dir(entry)
        if not target.is_dir():
            out(f"[{entry.name}] 未安装（可选）")
            continue
        if is_link_like(target):
            fail(f"[{entry.name}] 共享实体路径是链接: {target}")
            errors += 1
            continue
        if not (target / "SKILL.md").is_file():
            fail(f"[{entry.name}] 缺少 SKILL.md: {target}")
            errors += 1
            continue
        meta = read_meta(target)
        if meta is None:
            fail(f"[{entry.name}] 缺少安装元数据: {target / META_NAME}")
            errors += 1
        elif not meta_matches(entry, meta):
            message = (
                f"[{entry.name}] 版本/来源可更新: "
                f"{meta.get('repo')}@{meta.get('ref')} -> {entry.repo}@{entry.ref}（运行 sync）"
            )
            if strict:
                fail(message)
                errors += 1
            else:
                warn(message)
        link_errors = 0
        for label, target_dir in harness_targets():
            link = target_dir / entry.name
            if not os.path.lexists(link):
                fail(f"[{entry.name}] [{label}] 链接缺失: {link}")
                link_errors += 1
            elif not link_points_directly(link, target):
                if same_path(link, target):
                    fail(f"[{entry.name}] [{label}] 非直接链接，运行 sync 修正: {link}")
                else:
                    fail(f"[{entry.name}] [{label}] 链接指向异常: {link}")
                link_errors += 1
        errors += link_errors
        if link_errors == 0:
            out(f"[{entry.name}] OK {entry.ref}")
    return errors


def uninstall_entry(entry: Entry, force: bool) -> int:
    target = canonical_dir(entry)
    errors = 0
    if os.path.lexists(target):
        if is_link_like(target):
            remove_link(target)
            out(f"[{entry.name}] 已移除共享实体链接: {target}")
        elif read_meta(target) is not None or force:
            backup_entity(target, "third-party", entry.name)
            out(f"[{entry.name}] 实体已移入备份")
        else:
            fail(f"[{entry.name}] 无安装元数据，拒绝删除（确需删除加 --force）: {target}")
            errors += 1
    for label, target_dir in harness_targets():
        link = target_dir / entry.name
        if not os.path.lexists(link):
            continue
        if is_link_like(link) and same_path(link, target):
            remove_link(link)
            out(f"  [{label}] 已移除链接")
        else:
            warn(f"[{label}] 不是本工具创建的链接，不动: {link}")
    return errors


def cmd_list(entries: list[Entry]) -> int:
    for entry in entries:
        out(f"{entry.name}\t{entry.kind}:{entry.ref}\t{entry.source_url}\t{entry.description}")
    return 0


def cmd_status(entries: list[Entry]) -> int:
    for entry in entries:
        status_entry(entry)
    return 0


def cmd_install(entries: list[Entry], args) -> int:
    errors = 0
    for entry in entries:
        try:
            install_entry(entry, args.force, args.command == "sync", args.timeout, args.proxy)
        except Exception as exc:
            fail(f"[{entry.name}] 安装失败: {exc}")
            errors += 1
    return 1 if errors else 0


def cmd_verify(entries: list[Entry], args) -> int:
    return 1 if verify_entries(entries, args.strict) else 0


def cmd_uninstall(entries: list[Entry], args) -> int:
    errors = 0
    for entry in entries:
        errors += uninstall_entry(entry, args.force)
    return 1 if errors else 0


def add_common(sub, *, require_selection: bool = False) -> None:
    sub.add_argument("--name", action="append", default=[], help="只处理指定名称，可重复或逗号分隔")
    sub.add_argument("--proxy", default="", help="下载代理，如 http://127.0.0.1:7897；默认读取环境变量")
    sub.add_argument("--timeout", type=int, default=60, help="下载超时秒数（默认 60）")
    sub.add_argument("--force", action="store_true", help="强制重装或删除（按命令语义）")
    sub.add_argument("--strict", action="store_true", help="verify 时把版本可更新也计为失败")
    if require_selection:
        sub.add_argument("--all", action="store_true", help="卸载名单内全部（需显式指定）")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="第三方 skill 推荐名单：安装、同步、校验",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -X utf8 scripts/third-party-skills.py status\n"
            "  python -X utf8 scripts/third-party-skills.py install --name anysearch\n"
            "  python -X utf8 scripts/third-party-skills.py sync\n"
            "  python -X utf8 scripts/third-party-skills.py uninstall --name anysearch\n"
        ),
    )
    subs = parser.add_subparsers(dest="command", required=True)
    for command, help_text in [
        ("list", "列出名单"),
        ("status", "查看安装与链接状态"),
        ("install", "安装未安装的条目"),
        ("sync", "安装缺失并更新版本"),
        ("verify", "校验已安装条目与本机链接"),
        ("uninstall", "卸载条目（实体移入备份）"),
    ]:
        sub = subs.add_parser(command, help=help_text)
        add_common(sub, require_selection=command == "uninstall")

    args = parser.parse_args(argv)
    try:
        entries = parse_registry()
        names = split_names(args.name)
        if names:
            entries = select_entries(entries, names)
        elif args.command == "uninstall" and not args.all:
            raise RegistryError("uninstall 需要 --name，或显式加 --all")
        if args.command == "list":
            return cmd_list(entries)
        if args.command == "status":
            return cmd_status(entries)
        if args.command in {"install", "sync"}:
            return cmd_install(entries, args)
        if args.command == "verify":
            return cmd_verify(entries, args)
        if args.command == "uninstall":
            return cmd_uninstall(entries, args)
    except RegistryError as exc:
        fail(str(exc))
        return 2
    except InstallError as exc:
        fail(str(exc))
        return 1
    except KeyboardInterrupt:
        fail("已取消")
        return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
