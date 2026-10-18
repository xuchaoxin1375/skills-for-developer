"""Light-engine contracts: PNG slicing, WebSocket frames, end-to-end capture.

Run: python -X utf8 -m unittest discover -s skills/browser-automation/tests -v
Pure-unit cases need only the standard library; browser cases are skipped when no
eligible system browser exists. All network traffic stays on the local fixture.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import http.server
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zlib

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import browser_discovery as discovery  # noqa: E402
import light_browser as light  # noqa: E402
from managed_browser import TaskError  # noqa: E402


def encode_png(width: int, height: int, rows: list[bytes], color: int = 2) -> bytes:
    """Encode rows with explicit filter bytes so tests can force filter types."""
    body = bytearray()
    for filter_type, raw in rows:
        body.append(filter_type)
        body.extend(raw)
    assert len(body) == height * (1 + len(rows[0][1]))
    header = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + light._png_chunk(b"IHDR", header)
        + light._png_chunk(b"IDAT", zlib.compress(bytes(body), 6))
        + light._png_chunk(b"IEND", b"")
    )


def decode_png(data: bytes) -> tuple[int, int, int, list[bytes]]:
    """Decode to unfiltered rows; test-only so production stays filter-preserving."""
    width, height, channels, _ = light.png_geometry(data)
    stride = 1 + width * channels
    scanlines = zlib.decompress(
        b"".join(p for k, p in light._png_chunks(data) if k == b"IDAT")
    )
    assert len(scanlines) == stride * height
    rows: list[bytes] = []
    previous = bytes(width * channels)
    for index in range(height):
        offset = index * stride
        line = bytearray(scanlines[offset + 1 : offset + stride])
        light._unfilter(scanlines[offset], line, previous, channels)
        previous = bytes(line)
        rows.append(previous)
    return width, height, channels, rows


def pixel(data: bytes, x: int, y: int) -> tuple[int, ...]:
    width, _, channels, rows = decode_png(data)
    offset = x * channels
    return tuple(rows[y][offset : offset + channels])


class PngTests(unittest.TestCase):
    def test_slice_rewrites_the_first_row_filter(self) -> None:
        # Row 0 uses Up; a standalone copy of row 1 would decode against zeros.
        top = bytes([10, 20, 30] * 2)
        rows = [(0, top), (2, bytes(6)), (2, bytes(6))]
        source = encode_png(2, 3, rows)
        first, second = light.split_png(source, 2)
        self.assertEqual(pixel(first, 0, 0), (10, 20, 30))
        self.assertEqual(pixel(second, 1, 0), (10, 20, 30))
        self.assertEqual(decode_png(second)[1], 1)

    def test_slice_keeps_interior_rows_and_dimensions(self) -> None:
        rows = [(0, bytes([1, 2, 3] * 4)) for _ in range(4)]
        slices = light.split_png(encode_png(4, 4, rows), 2)
        self.assertEqual(len(slices), 2)
        for image in slices:
            width, height, channels, _ = light.png_geometry(image)
            self.assertEqual((width, height, channels), (4, 2, 3))
            self.assertEqual(pixel(image, 3, 1), (1, 2, 3))

    def test_unsupported_png_geometry_fails_fast(self) -> None:
        palette = encode_png(2, 2, [(0, bytes(4))] * 2, color=3)
        with self.assertRaises(TaskError) as raised:
            light.png_geometry(palette)
        self.assertEqual(raised.exception.code, 1)
        with self.assertRaises(TaskError):
            light.split_png(encode_png(2, 1, [(0, bytes(6))]), 3)

    def test_corrupt_chunk_is_rejected(self) -> None:
        source = bytearray(encode_png(2, 2, [(0, bytes(6))] * 2))
        source[20] ^= 0xFF
        with self.assertRaises(TaskError):
            light.split_png(bytes(source), 2)


class StubDevTools(threading.Thread):
    """Answer one WebSocket upgrade, then send a split message around a ping."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.client_frames: list[tuple[int, bytes]] = []

        self.client_frames: list[tuple[int, bytes]] = []

    def run(self) -> None:
        connection, _ = self.server.accept()
        with connection:
            request = b""
            while b"\r\n\r\n" not in request:
                request += connection.recv(1)
            key = next(
                line.split(b": ", 1)[1]
                for line in request.split(b"\r\n")
                if line.lower().startswith(b"sec-websocket-key:")
            )
            accept = base64.b64encode(
                hashlib.sha1(key + light.WS_GUID.encode()).digest()
            )
            connection.sendall(
                b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n"
            )
            self._frame(connection, 0x1, b"par", final=False)
            self._frame(connection, 0x9, b"ping")
            self._frame(connection, 0x0, b"tial", final=True)
            # The client answers the ping before the caller sees the message.
            for _ in range(2):
                connection.settimeout(5)
                try:
                    self.client_frames.append(self._read_frame(connection))
                except (OSError, TimeoutError):
                    break

    @staticmethod
    def _frame(
        sock: socket.socket, opcode: int, payload: bytes, final: bool = True
    ) -> None:
        header = bytearray([(0x80 if final else 0) | opcode])
        header.append(len(payload))
        sock.sendall(bytes(header) + payload)

    @staticmethod
    def _read_frame(sock: socket.socket) -> tuple[int, bytes]:
        first, second = sock.recv(2)
        length = second & 0x7F
        mask = sock.recv(4)
        data = b""
        while len(data) < length:
            data += sock.recv(length - len(data))
        return first & 0x0F, bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))


class WebSocketTests(unittest.TestCase):
    def test_reassembles_fragments_and_answers_ping(self) -> None:
        stub = StubDevTools()
        stub.start()
        client = light.WebSocket(f"ws://127.0.0.1:{stub.port}/devtools/browser/x", 5)
        try:
            self.assertEqual(client.receive_text(), "partial")
            client.send_text("hello")
        finally:
            client.close()
        stub.join(timeout=5)
        opcodes = [opcode for opcode, _ in stub.client_frames]
        payloads = [payload for _, payload in stub.client_frames]
        self.assertEqual(opcodes[0], 0xA, "the ping must be answered first")
        self.assertIn(b"hello", payloads)
        stub.server.close()

    def test_non_websocket_scheme_is_rejected(self) -> None:
        with self.assertRaises(TaskError):
            light.WebSocket("http://127.0.0.1:1/x", 1)


class DiscoveryGapTests(unittest.TestCase):
    def test_product_labels_and_command_parsing(self) -> None:
        self.assertEqual(discovery._product_from_registration("Brave"), "brave")
        self.assertEqual(
            discovery._product_from_registration("Google Chrome"), "chrome"
        )
        self.assertEqual(
            discovery._product_from_registration("Firefox-308046"), "other"
        )
        self.assertEqual(
            discovery._executable_from_command(
                '"C:\\Program Files\\Brave\\brave.exe" --single-argument %1'
            ),
            Path("C:\\Program Files\\Brave\\brave.exe"),
        )
        self.assertIsNone(discovery._executable_from_command("%1"))

    def test_playwright_cache_is_reported_as_informational(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pw-cache-") as temporary:
            artifact = Path(temporary) / "chromium-1234" / "chrome-win" / "chrome.exe"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"MZ\x00\x00")
            entries = discovery.playwright_cache_locations(
                "win32", {"PLAYWRIGHT_BROWSERS_PATH": temporary}, Path(temporary)
            )
            found = discovery.inspect_candidates(entries, "win32")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source, "playwright-cache")
        self.assertEqual(found[0].browser, "chromium")
        self.assertTrue(found[0].eligible)

    def test_select_browser_filters_by_product_and_eligibility(self) -> None:
        from browser_discovery import BrowserCandidate

        candidates = [
            BrowserCandidate("msedge", "edge.exe", "fixed", True, "native"),
            BrowserCandidate("chrome", "chrome.exe", "fixed", True, "native"),
        ]
        with mock.patch.object(
            discovery, "discover_browsers", return_value=candidates
        ):
            self.assertEqual(discovery.select_browser().path, "edge.exe")
            self.assertEqual(discovery.select_browser("chrome").path, "chrome.exe")
            self.assertIsNone(discovery.select_browser("brave"))
        wrapper = [
            BrowserCandidate("brave", "brave.cmd", "PATH", False, "wrapper"),
        ]
        with mock.patch.object(discovery, "discover_browsers", return_value=wrapper):
            self.assertIsNone(discovery.select_browser())


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass


class LightEngineTests(unittest.TestCase):
    """Browser cases reuse an installed browser; no Playwright package needed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.candidate = discovery.select_browser()
        cls.temporary = tempfile.TemporaryDirectory(prefix="light-engines-")
        cls.root = Path(cls.temporary.name)
        (cls.root / "sticky.html").write_text(
            '<html><body style="margin:0">'
            '<div style="position:sticky;top:0;height:80px;background:#00ff00">H</div>'
            '<div style="height:900px;background:#ff0000">First</div>'
            '<div style="height:900px;background:#0000ff">Second</div>'
            "</body></html>",
            encoding="utf-8",
        )
        cls.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(cls.root))
        )
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/sticky.html"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.temporary.cleanup()

    def setUp(self) -> None:
        if self.candidate is None:
            self.skipTest("No eligible system browser for light engines")

    def capture(self, engine: str) -> list[bytes]:
        import subprocess

        out = self.root / engine
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPTS / "shot_scroll.py"),
                "--url",
                self.url,
                "--engine",
                engine,
                "--executable-path",
                self.candidate.path,
                "--screens",
                "2",
                "--settle-ms",
                "200",
                "--step-wait-ms",
                "200",
                "--out-dir",
                str(out),
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CLEANUP verified", result.stderr)
        shots = sorted(out.glob("*.png"))
        self.assertEqual(len(shots), 2)
        return [shot.read_bytes() for shot in shots]

    def test_oneshot_slices_a_single_tall_capture(self) -> None:
        first, second = self.capture("oneshot")
        self.assertEqual(light.png_geometry(first)[:2], (1440, 900))
        self.assertEqual(pixel(first, 5, 5), (0, 255, 0))
        # Sticky elements render once: the slice below carries no pinned header.
        self.assertEqual(pixel(second, 5, 5), (255, 0, 0))

    def test_cdp_scroll_keeps_the_sticky_header(self) -> None:
        first, second = self.capture("cdp")
        self.assertEqual(light.png_geometry(second)[:2], (1440, 900))
        self.assertEqual(pixel(first, 5, 5), (0, 255, 0))
        self.assertEqual(pixel(second, 5, 5), (0, 255, 0))

    def test_light_engine_requires_an_explicit_browser(self) -> None:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPTS / "shot_scroll.py"),
                "--url",
                self.url,
                "--engine",
                "oneshot",
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("RUN ", result.stderr)


class DoctorTests(unittest.TestCase):
    def test_doctor_does_not_start_a_guardian_or_launch(self) -> None:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPTS / "shot_scroll.py"),
                "--doctor",
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIn(report["recommended"]["engine"], ("playwright", "cdp", "none"))
        self.assertIn("package", report["playwright"])
        self.assertNotIn("RUN ", result.stderr)
        if report["selected"] is not None:
            self.assertEqual(report["selected"]["launch"], "not-probed")

    def test_probe_launch_requires_doctor(self) -> None:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPTS / "shot_scroll.py"),
                "--url",
                "http://example.test",
                "--probe-launch",
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
