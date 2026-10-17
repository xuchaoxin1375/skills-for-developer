"""Browser discovery contracts: read-only inventory, opt-in choice and no retries."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import browser_discovery as discovery  # noqa: E402
import shot_scroll as screenshot  # noqa: E402
from managed_browser import TaskError  # noqa: E402


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="browser-路径 空格-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def binary(self, relative: str, header: bytes = b"MZ\x00\x00") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(header)
        path.chmod(0o755)
        return path

    def test_windows_per_user_and_scoop_current(self) -> None:
        chrome = self.binary("local/Google/Chrome/Application/chrome.exe")
        edge = self.binary("scoop/apps/microsoft-edge/current/msedge.exe")
        # A newer unused Scoop directory must never win over the current link.
        self.binary("scoop/apps/microsoft-edge/999/msedge.exe")
        entries = discovery.common_locations(
            "win32",
            {
                "LOCALAPPDATA": str(self.root / "local"),
                "SCOOP": str(self.root / "scoop"),
            },
            self.root,
        )
        found = discovery.inspect_candidates(entries, "win32")
        self.assertEqual({item.path for item in found}, {str(chrome), str(edge)})
        self.assertTrue(all(item.eligible for item in found))

    def test_scripts_shims_missing_files_and_duplicate_locations(self) -> None:
        native = self.binary("real/chrome.exe")
        shim = self.binary("shims/chrome.exe")
        shim.with_suffix(".shim").write_text("path = real", encoding="utf-8")
        script = self.binary("wrapper/chrome.cmd", b"@echo off")
        found = discovery.inspect_candidates(
            [
                ("chrome", native, "first"),
                ("chrome", native, "second"),
                ("chrome", shim, "PATH"),
                ("chrome", script, "PATH"),
                ("chrome", self.root / "missing.exe", "missing"),
            ],
            "win32",
        )
        self.assertEqual(len(found), 3)
        self.assertEqual([item.eligible for item in found], [True, False, False])
        self.assertEqual(found[0].source, "first")

    def test_linux_wrappers_and_launcher_excluded_native_elf_kept(self) -> None:
        script = self.binary("google-chrome", b"#!/bin/sh\n")
        elf = self.binary("chrome", b"\x7fELF")
        snap = self.binary("snap", b"\x7fELF")
        found = discovery.inspect_candidates(
            [
                ("chrome", script, "PATH"),
                ("chrome", elf, "system-package"),
                ("chromium", snap, "PATH"),
            ],
            "linux",
        )
        self.assertEqual([item.eligible for item in found], [False, True, False])

    def test_macos_user_bundle_and_macho(self) -> None:
        chrome = self.binary(
            "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            b"\xcf\xfa\xed\xfe",
        )
        found = discovery.inspect_candidates(
            discovery.common_locations("darwin", {}, self.root), "darwin"
        )
        self.assertTrue(
            any(item.path == str(chrome) and item.eligible for item in found)
        )

    def test_inventory_never_starts_guardian_or_resolves_proxy(self) -> None:
        with (
            mock.patch.object(screenshot, "discover_browsers", return_value=[]),
            mock.patch.object(screenshot, "run_managed") as runner,
            mock.patch.object(screenshot, "resolve_proxy") as proxy,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(screenshot.main(["--list-browsers"]), 0)
        self.assertEqual(json.loads(output.getvalue())["candidates"], [])
        runner.assert_not_called()
        proxy.assert_not_called()

    def test_windows_inventory_prefers_edge_and_fixed_path_over_path_shim(self) -> None:
        chrome = self.binary("chrome.exe")
        edge = self.binary("msedge.exe")
        with (
            mock.patch.object(discovery.sys, "platform", "win32"),
            mock.patch.object(discovery, "windows_app_paths", return_value=[]),
            mock.patch.object(
                discovery,
                "common_locations",
                return_value=[
                    ("chrome", chrome, "Scoop:current"),
                    ("msedge", edge, "fixed"),
                ],
            ),
            mock.patch.object(discovery.shutil, "which", return_value=None),
        ):
            found = discovery.discover_browsers()
        self.assertEqual([item.browser for item in found], ["msedge", "chrome"])

    def test_opt_in_selection_is_deterministic_and_failure_does_not_retry(self) -> None:
        candidate = discovery.BrowserCandidate(
            "msedge", "chosen.exe", "App Paths", True, "native"
        )
        with (
            mock.patch.object(
                screenshot, "discover_browsers", return_value=[candidate]
            ),
            mock.patch.object(
                screenshot, "resolve_proxy", return_value=(None, "direct")
            ),
            mock.patch.object(
                screenshot, "run_managed", side_effect=TaskError("launch failed", 1)
            ) as runner,
        ):
            self.assertEqual(
                screenshot.main(["--url", "http://example.test", "--discover-browser"]),
                1,
            )
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args[1]["executable_path"], "chosen.exe")

    def test_missing_discovery_fails_before_guardian(self) -> None:
        with (
            mock.patch.object(screenshot, "discover_browsers", return_value=[]),
            mock.patch.object(screenshot, "run_managed") as runner,
        ):
            self.assertEqual(
                screenshot.main(["--url", "http://example.test", "--discover-browser"]),
                2,
            )
        runner.assert_not_called()

    def test_default_does_not_discover_or_change_project_browser(self) -> None:
        with (
            mock.patch.object(screenshot, "discover_browsers") as discover,
            mock.patch.object(
                screenshot, "resolve_proxy", return_value=(None, "direct")
            ),
            mock.patch.object(
                screenshot, "run_managed", return_value={"artifacts": []}
            ) as runner,
        ):
            self.assertEqual(screenshot.main(["--url", "http://example.test"]), 0)
        discover.assert_not_called()
        self.assertIsNone(runner.call_args.args[1]["executable_path"])
        self.assertIsNone(runner.call_args.args[1]["channel"])

    def test_conflicting_browser_options_or_missing_url_rejected(self) -> None:
        with mock.patch.object(screenshot, "run_managed") as runner:
            for arguments in (
                [],
                ["--list-browsers", "--url", "http://example.test"],
                [
                    "--url",
                    "http://example.test",
                    "--discover-browser",
                    "--channel",
                    "msedge",
                ],
                [
                    "--url",
                    "http://example.test",
                    "--executable-path",
                    str(self.root / "missing.exe"),
                ],
            ):
                with (
                    self.subTest(arguments=arguments),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    with self.assertRaises(SystemExit) as raised:
                        screenshot.main(arguments)
                    self.assertEqual(raised.exception.code, 2)
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
