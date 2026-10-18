"""Lifecycle integration tests; only browser tests require installed Playwright.

Run: python -X utf8 -m unittest discover -s skills/browser-automation/tests -v
All network traffic stays on the local HTTP fixture. No public sites are used.
"""

from __future__ import annotations

import _thread
import functools
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
LEGACY_SCRIPTS = SCRIPTS.parents[1] / "frontend-qa/scripts"
sys.path.insert(0, str(SCRIPTS))
import managed_browser as manager  # noqa: E402

WORKER = Path(__file__).with_name("lifecycle_worker.py")
COMMAND = [sys.executable, "-X", "utf8", str(WORKER)]


def wait_for(predicate, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition did not become true before deadline")
        time.sleep(0.05)


def reachable(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="managed-browser-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.ready = self.root / "leaf-port"
        self.sentinel = socket.socket()
        self.sentinel.bind(("127.0.0.1", 0))
        self.sentinel.listen(20)
        self.addCleanup(self.sentinel.close)

    def request(self, mode: str = "hang") -> dict:
        return {
            "command": COMMAND,
            "payload": {"ready": str(self.ready), "mode": mode},
            "wall_timeout_ms": 15000,
            "state_root": str(self.state),
        }

    def assert_released(self) -> None:
        port = int(self.ready.read_text(encoding="utf-8"))
        wait_for(lambda: not reachable(port))
        wait_for(lambda: not list(self.state.glob("run-*")))
        self.assertFalse((self.state / "cleanup-failed.json").exists())
        self.assertTrue(reachable(self.sentinel.getsockname()[1]))

    def start_guardian(self) -> subprocess.Popen:
        process = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPTS / "managed_browser.py"),
                "--guardian",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        process.stdin.write((json.dumps(self.request()) + "\n").encode())
        process.stdin.flush()
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.stdin.close)
        wait_for(self.ready.exists)
        return process

    def test_success_reaps_residual_child(self) -> None:
        manager.run_managed(
            COMMAND, self.request("success")["payload"], 10000, state_root=self.state
        )
        self.assert_released()

    @unittest.skipUnless(
        sys.platform.startswith("linux"), "Linux subreaper/pidfd regression"
    )
    def test_detached_descendant_is_reaped(self) -> None:
        manager.run_managed(
            COMMAND,
            self.request("detached-success")["payload"],
            10000,
            state_root=self.state,
        )
        self.assert_released()

    def test_failure_reaps_child(self) -> None:
        with self.assertRaises(manager.TaskError) as raised:
            manager.run_managed(
                COMMAND,
                self.request("failure")["payload"],
                10000,
                state_root=self.state,
            )
        self.assertEqual(raised.exception.code, 1)
        self.assert_released()

    def test_hard_timeout_reaps_tree(self) -> None:
        with self.assertRaises(manager.TaskError) as raised:
            manager.run_managed(
                COMMAND, self.request()["payload"], 1500, state_root=self.state
            )
        self.assertEqual(raised.exception.code, 124)
        self.assert_released()

    def test_cancellation_and_parallel_rejection(self) -> None:
        guardian = self.start_guardian()
        try:
            with self.assertRaises(manager.TaskError) as raised:
                manager.run_managed(
                    COMMAND, self.request()["payload"], 10000, state_root=self.state
                )
            self.assertEqual(raised.exception.code, 3)
        finally:
            guardian.stdin.close()  # Same lifeline closure as Ctrl+C.
            guardian.wait(timeout=12)
        self.assertEqual(json.loads(guardian.stdout.read())["code"], 130)
        self.assert_released()

    def test_forced_caller_death(self) -> None:
        caller = subprocess.Popen(
            COMMAND + ["--caller"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        caller.stdin.write((json.dumps(self.request()) + "\n").encode())
        caller.stdin.flush()
        try:
            wait_for(self.ready.exists)
        finally:
            caller.kill()
            caller.wait(timeout=5)
            caller.stdin.close()
        self.assert_released()

    def test_keyboard_interrupt_waits_for_cleanup(self) -> None:
        stop = threading.Event()

        def interrupt_when_started() -> None:
            while not stop.wait(0.02):
                if self.ready.exists():
                    _thread.interrupt_main()
                    return

        thread = threading.Thread(target=interrupt_when_started)
        thread.start()
        try:
            with self.assertRaises(manager.TaskError) as raised:
                manager.run_managed(
                    COMMAND, self.request()["payload"], 10000, state_root=self.state
                )
            self.assertEqual(raised.exception.code, 130)
        finally:
            stop.set()
            thread.join(timeout=2)
        self.assert_released()

    @unittest.skipUnless(os.name == "nt", "Job Object regression")
    def test_forced_guardian_death_closes_job(self) -> None:
        guardian = self.start_guardian()
        guardian.kill()
        guardian.wait(timeout=5)
        port = int(self.ready.read_text(encoding="utf-8"))
        wait_for(lambda: not reachable(port))
        # A dead guardian cannot delete files. Subsequent runs fail closed.
        with self.assertRaises(manager.TaskError) as raised:
            manager.run_managed(
                COMMAND, self.request()["payload"], 10000, state_root=self.state
            )
        self.assertEqual(raised.exception.code, 4)

    def test_cleanup_failure_blocks_following_run(self) -> None:
        cancelled = threading.Event()
        original_close = manager.ProcessScope.close

        def close_then_fail(scope: manager.ProcessScope) -> None:
            original_close(scope)
            raise OSError("test cleanup failure")

        with mock.patch.object(manager.ProcessScope, "close", close_then_fail):
            response = manager._guard(self.request("success"), cancelled)
        self.assertEqual(response["code"], 4)
        with self.assertRaises(manager.TaskError) as raised:
            manager.run_managed(
                COMMAND, self.request()["payload"], 10000, state_root=self.state
            )
        self.assertEqual(raised.exception.code, 4)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="screenshots-中文-")
        cls.root = Path(cls.temporary.name)
        (cls.root / "index.html").write_text(
            '<html><body style="margin:0"><div style="height:900px;background:red">First</div>'
            '<div style="height:900px;background:blue">Second</div></body></html>',
            encoding="utf-8",
        )
        # Grows while scrolling, so a jump-to-bottom capture would shoot the wrong screen.
        (cls.root / "lazy.html").write_text(
            '<html><body style="margin:0"><div style="height:1800px;background:red"></div>'
            '<div id="more"></div><script>let n=0;'
            "addEventListener('scroll',()=>{if(n<2){n++;const d=document.createElement('div');"
            "d.style.cssText='height:900px;background:green';"
            "document.getElementById('more').appendChild(d);}});"
            "</script></body></html>",
            encoding="utf-8",
        )
        cls.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(cls.root))
        )
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/index.html"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.temporary.cleanup()

    def cli(
        self, *arguments: str, script: Path | None = None
    ) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.pop("SCRAPE_PROXY", None)
        return subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(script or SCRIPTS / "shot_scroll.py"),
                *arguments,
            ],
            capture_output=True,
            encoding="utf-8",
            env=env,
            timeout=20,
        )

    def test_real_browser_scroll_and_cleanup(self) -> None:
        result = self.cli(
            "--url",
            self.url,
            "--screens",
            "2",
            "--settle-ms",
            "0",
            "--step-wait-ms",
            "0",
            "--out-dir",
            str(self.root / "scroll"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        shots = sorted((self.root / "scroll").glob("*.png"))
        self.assertEqual(len(shots), 2)
        self.assertNotEqual(shots[0].read_bytes(), shots[1].read_bytes())
        self.assertIn("CLEANUP verified", result.stderr)
        self.assertFalse(list(manager.STATE_ROOT.glob("run-*")))

    def test_bottom_capture_walks_growing_page(self) -> None:
        output = self.root / "末屏 底部.png"
        result = self.cli(
            "--url",
            f"http://127.0.0.1:{self.server.server_port}/lazy.html",
            "--to-bottom",
            "--settle-ms",
            "0",
            "--out",
            str(output),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))
        metrics = json.loads(re.search(r"PAGE metrics=(\{.*\})", result.stderr).group(1))
        # Both lazy blocks appear only after scrolling: 3600px tall, shot at the end.
        self.assertEqual(metrics["d"], 3600)
        self.assertEqual(metrics["y"], metrics["d"] - metrics["h"])
        self.assertIn("CLEANUP verified", result.stderr)
        self.assertFalse(list(manager.STATE_ROOT.glob("run-*")))

    def test_discovered_system_browser_is_managed(self) -> None:
        from browser_discovery import discover_browsers

        if not any(item.eligible for item in discover_browsers()):
            self.skipTest("No native system browser in supported common locations")
        output = self.root / "自动发现 浏览器.png"
        result = self.cli("--url", self.url, "--discover-browser", "--out", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))
        self.assertIn("BROWSER discovered=", result.stderr)
        self.assertIn("BROWSER version=", result.stderr)
        self.assertIn("CLEANUP verified", result.stderr)
        self.assertFalse(list(manager.STATE_ROOT.glob("run-*")))

    def test_legacy_python_cli_delegates_capture_and_inventory(self) -> None:
        inventory = self.cli(
            "--list-browsers", script=LEGACY_SCRIPTS / "shot_scroll.py"
        )
        self.assertEqual(inventory.returncode, 0, inventory.stderr)
        self.assertIn("candidates", json.loads(inventory.stdout))
        output = self.root / "旧入口 Python.png"
        result = self.cli(
            "--url",
            self.url,
            "--out",
            str(output),
            script=LEGACY_SCRIPTS / "shot_scroll.py",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(int.from_bytes(output.read_bytes()[16:20], "big"), 1440)
        self.assertIn("CLEANUP verified", result.stderr)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 required")
    def test_legacy_powershell_delegates_bound_parameters(self) -> None:
        output = self.root / "旧入口 PowerShell.png"
        result = subprocess.run(
            [
                shutil.which("pwsh"),
                "-NoProfile",
                "-File",
                str(LEGACY_SCRIPTS / "shot-quick.ps1"),
                "-Url",
                self.url,
                "-Out",
                str(output),
                "-Python",
                sys.executable,
                "-Width",
                "800",
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(int.from_bytes(output.read_bytes()[16:20], "big"), 800)
        self.assertIn("CLEANUP verified", result.stderr)

    def test_timeout_preserves_previous_artifact(self) -> None:
        output = self.root / "previous.png"
        output.write_bytes(b"previous")
        result = self.cli(
            "--url",
            self.url,
            "--settle-ms",
            "20000",
            "--wall-timeout-ms",
            "1500",
            "--out",
            str(output),
        )
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(output.read_bytes(), b"previous")
        self.assertNotIn("SHOT ", result.stdout)
        self.assertFalse(list(manager.STATE_ROOT.glob("run-*")))

    def test_bad_arguments_do_not_start_browser(self) -> None:
        for arguments in (
            ("--url", "file:///invalid"),
            ("--url", self.url, "--height", "0"),
            ("--url", self.url, "--screens", "2", "--out", "bad.png"),
            ("--url", self.url, "--to-bottom", "--screens", "2"),
        ):
            result = self.cli(*arguments)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("RUN ", result.stderr)

    def test_output_failure_still_cleans_resources(self) -> None:
        occupied = self.root / "not-a-directory"
        occupied.write_text("keep", encoding="utf-8")
        result = self.cli("--url", self.url, "--out-dir", str(occupied))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("SHOT ", result.stdout)
        self.assertEqual(occupied.read_text(encoding="utf-8"), "keep")
        self.assertFalse(list(manager.STATE_ROOT.glob("run-*")))
        self.assertFalse((manager.STATE_ROOT / "cleanup-failed.json").exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 required")
    def test_powershell_adapter_unicode_path(self) -> None:
        output = self.root / "首屏 含空格.png"
        result = subprocess.run(
            [
                shutil.which("pwsh"),
                "-NoProfile",
                "-File",
                str(SCRIPTS / "shot-quick.ps1"),
                "-Url",
                self.url,
                "-Out",
                str(output),
                "-Python",
                sys.executable,
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 required")
    def test_powershell_bottom_switch_delegates(self) -> None:
        output = self.root / "包装器 末屏.png"
        result = subprocess.run(
            [
                shutil.which("pwsh"),
                "-NoProfile",
                "-File",
                str(SCRIPTS / "shot-quick.ps1"),
                "-Url",
                f"http://127.0.0.1:{self.server.server_port}/lazy.html",
                "-ToBottom",
                "-Out",
                str(output),
                "-Python",
                sys.executable,
                "-WallTimeoutMs",
                "60000",
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))
        metrics = json.loads(re.search(r"PAGE metrics=(\{.*\})", result.stderr).group(1))
        self.assertEqual(metrics["d"], 3600)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 required")
    def test_powershell_browser_inventory_and_discovery(self) -> None:
        base = [
            shutil.which("pwsh"),
            "-NoProfile",
            "-File",
            str(SCRIPTS / "shot-quick.ps1"),
            "-Python",
            sys.executable,
        ]
        inventory = subprocess.run(
            base + ["-ListBrowsers"], capture_output=True, encoding="utf-8", timeout=10
        )
        self.assertEqual(inventory.returncode, 0, inventory.stderr)
        candidates = json.loads(inventory.stdout)["candidates"]
        if not any(item["eligible"] for item in candidates):
            self.skipTest("No native system browser for PowerShell discovery")
        output = self.root / "包装器 自动发现.png"
        result = subprocess.run(
            base + ["-Url", self.url, "-DiscoverBrowser", "-Out", str(output)],
            capture_output=True,
            encoding="utf-8",
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))
        self.assertIn("CLEANUP verified", result.stderr)
        self.assertFalse(list(manager.STATE_ROOT.glob("run-*")))


if __name__ == "__main__":
    unittest.main()
