"""Offline regression tests for upstream clone validation and safe linking.

Run: python -X utf8 tests/test_upstream_skill_links.py -v
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


def load_linker():
    path = Path(__file__).resolve().parents[1] / "scripts/link-upstream-skills.py"
    spec = importlib.util.spec_from_file_location("upstream_linker_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UpstreamLinksTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="upstream-links-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.clone = self.root / "third-party/mock"
        self.clone.mkdir(parents=True)
        self.source = self.clone / "skills/one"
        self.source.mkdir(parents=True)
        (self.source / "SKILL.md").write_bytes(b"---\nname: one\ndescription: test\n---\nOriginal\n")
        self.git("init", "-q")
        self.git("remote", "add", "origin", "https://example.invalid/upstream.git")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.entry = {
            "url": "https://example.invalid/upstream.git",
            "directory": "third-party/mock",
            "revision": self.git("rev-parse", "HEAD"),
            "skills": {"one": "skills/one"},
        }
        self.write_config()
        self.linker = load_linker()
        self.helpers = self.linker.load_link_helpers()
        self.helpers.backup_root = lambda: self.root / "backups"
        self.targets = [("sandbox", self.root / "harness skills")]

    def git(self, *args: str) -> str:
        return subprocess.run(
            [
                "git", "-C", str(self.clone), "-c", "user.name=Upstream Test",
                "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
                "-c", "core.autocrlf=false", "-c", f"core.hooksPath={self.root / 'no-hooks'}",
                *args,
            ], check=True, capture_output=True, encoding="utf-8", timeout=15,
        ).stdout.strip()

    def write_config(self) -> None:
        path = self.root / "config/upstream-skills.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"repositories": [self.entry]}), encoding="utf-8")

    def link(self, **kwargs) -> int:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return self.linker.link_sources([("one", self.source)], self.targets, self.helpers, **kwargs)

    def test_clean_source_and_include(self) -> None:
        self.assertEqual(self.linker.sources(self.root, {"one"}), [("one", self.source)])
        self.assertEqual(self.linker.sources(self.root, {"other"}), [])

    def test_version_drift_rejected(self) -> None:
        self.entry["revision"] = "0" * 40
        self.write_config()
        with self.assertRaisesRegex(ValueError, "revision differs"):
            self.linker.sources(self.root, set())

    def test_origin_drift_rejected(self) -> None:
        self.entry["url"] = "https://example.invalid/different.git"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "origin differs"):
            self.linker.sources(self.root, set())

    def test_changed_upstream_rejected(self) -> None:
        (self.source / "SKILL.md").write_bytes(b"Local patch\n")
        with self.assertRaisesRegex(ValueError, "local changes"):
            self.linker.sources(self.root, set())

    def test_untracked_upstream_patch_rejected(self) -> None:
        (self.source / "LOCAL.md").write_bytes(b"Local rules\n")
        with self.assertRaisesRegex(ValueError, "local changes"):
            self.linker.sources(self.root, set())

    def test_traversal_and_absolute_paths_rejected(self) -> None:
        for value in ("../escape", "/absolute", "C:/absolute", "a\\b", "a/./b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.linker.inside(self.root, value)

    def test_invalid_commit_rejected(self) -> None:
        self.entry["revision"] = "main"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "commit SHA"):
            self.linker.sources(self.root, set())

    def test_local_name_collision_rejected(self) -> None:
        local = self.root / "skills/one"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_bytes(b"local")
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.linker.sources(self.root, set())

    def test_missing_skill_rejected(self) -> None:
        self.entry["skills"]["one"] = "skills/missing"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "Missing upstream"):
            self.linker.sources(self.root, set())

    def test_missing_clone_is_optional_and_reported(self) -> None:
        self.entry["directory"] = "third-party/not-installed"
        self.write_config()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(self.linker.sources(self.root, set()), [])
        self.assertIn("Optional clone missing", output.getvalue())

    def test_missing_clone_with_installed_link_is_not_optional(self) -> None:
        missing = self.root / "third-party/not-installed"
        target = self.targets[0][1] / "one"
        self.helpers.create_link(target, self.source)
        self.entry["directory"] = "third-party/not-installed"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "clone missing but skill"):
            self.linker.sources(self.root, set(), self.targets)
        self.assertFalse(missing.exists())
        self.helpers.remove_link(target)

    def test_link_verify_idempotency_and_unlink(self) -> None:
        original = (self.source / "SKILL.md").read_bytes()
        self.assertEqual(self.link(), 0)
        self.assertEqual(self.link(), 0)
        self.assertEqual(self.link(verify_only=True), 0)
        link = self.targets[0][1] / "one"
        self.assertTrue(self.helpers.link_points_directly(link, self.source))
        self.assertEqual(self.link(unlink=True), 0)
        self.assertFalse(link.exists())
        self.assertEqual((self.source / "SKILL.md").read_bytes(), original)

    def test_verify_missing_link_does_not_create(self) -> None:
        self.assertEqual(self.link(verify_only=True), 1)
        self.assertFalse(self.targets[0][1].exists())

    def test_conflicting_entity_requires_explicit_backup_replace(self) -> None:
        entity = self.targets[0][1] / "one"
        entity.mkdir(parents=True)
        (entity / "user.txt").write_bytes(b"do not lose")
        self.assertEqual(self.link(), 1)
        self.assertEqual((entity / "user.txt").read_bytes(), b"do not lose")
        self.assertEqual(self.link(replace=True), 0)
        backups = list((self.root / "backups").rglob("user.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"do not lose")
        self.assertTrue(self.helpers.link_points_directly(entity, self.source))
        self.assertEqual(self.link(unlink=True), 0)

    def test_unlink_does_not_touch_foreign_link(self) -> None:
        foreign = self.root / "foreign"
        foreign.mkdir()
        link = self.targets[0][1] / "one"
        self.helpers.create_link(link, foreign)
        self.assertEqual(self.link(unlink=True), 1)
        self.assertTrue(self.helpers.link_points_directly(link, foreign))
        self.helpers.remove_link(link)


if __name__ == "__main__":
    unittest.main()
