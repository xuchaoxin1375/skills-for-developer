"""Zero-dependency light capture engines: one-shot screenshot and minimal CDP.

Standard library only, so a target environment without the Playwright package can
still capture screenshots with an installed Chromium browser. ``shot_scroll.py``
selects these engines explicitly with ``--engine``; both run inside the same
managed worker, so the guardian still owns the deadline, the process-tree
containment and the verified cleanup. Fidelity differs from Playwright: see
references/screenshot-workflow.md.
"""

from __future__ import annotations

import base64
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import time
from typing import Any
from urllib.parse import urlparse
import zlib

from managed_browser import TaskError

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
CHANNELS = {2: 3, 6: 4}  # Only truecolour RGB/RGBA; other colour types are rejected.


def png_geometry(data: bytes) -> tuple[int, int, int, bool]:
    """Return (width, height, bytes per pixel, interlace) for a supported PNG."""
    if data[:8] != PNG_MAGIC:
        raise TaskError("浏览器未返回 PNG 数据。", 1)
    if data[12:16] != b"IHDR":
        raise TaskError("PNG 缺少 IHDR 块。", 1)
    width, height, depth, color, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", data[16:29]
    )
    if depth != 8 or color not in CHANNELS or compression or filter_method:
        raise TaskError("PNG 编码不受支持；改用 --engine cdp 或 Playwright。", 1)
    return width, height, CHANNELS[color], bool(interlace)


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Split a PNG stream into (type, payload) pairs, verifying each CRC."""
    chunks: list[tuple[bytes, bytes]] = []
    offset = 8
    while offset + 8 <= len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        stored = data[offset + 8 + length : offset + 12 + length]
        if len(payload) != length or len(stored) != 4:
            raise TaskError("PNG 数据被截断。", 1)
        if struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF) != stored:
            raise TaskError("PNG 块校验失败。", 1)
        chunks.append((kind, payload))
        offset += 12 + length
    return chunks


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _unfilter(kind: int, line: bytearray, previous: bytes, channels: int) -> None:
    """Reverse one PNG row filter in place, given the decoded row above."""
    if kind == 0:
        return
    for index in range(len(line)):
        left = line[index - channels] if index >= channels else 0
        up = previous[index]
        up_left = previous[index - channels] if index >= channels else 0
        if kind == 1:
            line[index] = (line[index] + left) & 0xFF
        elif kind == 2:
            line[index] = (line[index] + up) & 0xFF
        elif kind == 3:
            line[index] = (line[index] + ((left + up) >> 1)) & 0xFF
        elif kind == 4:
            estimate = left + up - up_left
            candidates = (
                abs(estimate - left),
                abs(estimate - up),
                abs(estimate - up_left),
            )
            predictor = (left, up, up_left)[candidates.index(min(candidates))]
            line[index] = (line[index] + predictor) & 0xFF
        else:
            raise TaskError(f"未知 PNG 行过滤类型 {kind}。", 1)


def _encode_png(width: int, height: int, channels: int, body: bytes) -> bytes:
    header = struct.pack(
        ">IIBBBBB", width, height, 8, 2 if channels == 3 else 6, 0, 0, 0
    )
    return (
        PNG_MAGIC
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(body, 6))
        + _png_chunk(b"IEND", b"")
    )


def split_png(data: bytes, parts: int) -> list[bytes]:
    """Split a tall capture into `parts` equal vertical slices.

    Later slices re-encode their first row as an unfiltered row: a row filter may
    reference the row above, which no longer exists once the rows are separated.
    """
    width, height, channels, interlace = png_geometry(data)
    if parts <= 0:
        raise TaskError("切片数量必须为正整数。", 1)
    if parts == 1:
        return [data]
    stride = 1 + width * channels
    scanlines = zlib.decompress(
        b"".join(payload for kind, payload in _png_chunks(data) if kind == b"IDAT")
    )
    if len(scanlines) != stride * height:
        raise TaskError("PNG 扫描行长度与图头不一致。", 1)
    rows = height // parts
    if rows <= 0:
        raise TaskError("来源图高度不足以切成所需的屏数。", 1)
    images: list[bytes] = []
    previous = bytes(width * channels)
    cursor = 0
    for index in range(parts):
        start = index * rows
        while cursor <= start:
            offset = cursor * stride
            line = bytearray(scanlines[offset + 1 : offset + stride])
            _unfilter(scanlines[offset], line, previous, channels)
            previous = bytes(line)
            cursor += 1
        body = (
            b"\x00"
            + previous
            + scanlines[(start + 1) * stride : (start + rows) * stride]
        )
        images.append(_encode_png(width, rows, channels, body))
    return images


def binary_version(path: Path) -> str | None:
    """Read the Windows file version without launching the browser."""
    if os.name != "nt":
        return None
    import ctypes

    size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    pointer = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not ctypes.windll.version.VerQueryValueW(
        buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)
    ):
        return None
    fixed = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
    ms, ls = fixed[2], fixed[3]
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def launch_browser(executable: str, arguments: list[str]) -> subprocess.Popen[bytes]:
    """Start a headless browser as a child of the managed worker."""
    options: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    )
    return subprocess.Popen(
        [executable, *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **options,
    )


def terminate_browser(process: subprocess.Popen[bytes]) -> None:
    """Stop the browser without assuming it already exited."""
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def oneshot_arguments(
    config: dict[str, Any], shot: Path, profile: Path
) -> list[str]:
    """Build the single-capture headless command; no CDP and no Playwright."""
    arguments = [
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--force-device-scale-factor=1",
        f"--user-data-dir={profile}",
        f"--window-size={config['width']},{config['height'] * config['screens']}",
        f"--screenshot={shot}",
    ]
    if config["settle_ms"]:
        arguments.append(f"--virtual-time-budget={config['settle_ms']}")
    if config["proxy"]:
        arguments.append(f"--proxy-server={config['proxy']}")
    arguments.append(config["url"])
    return arguments


def oneshot_capture(config: dict[str, Any], shots_dir: Path) -> str:
    """Capture one tall window and slice it; sticky layout is rendered once."""
    profile = shots_dir.parent / "tmp" / "oneshot-profile"
    raw = shots_dir / "0.png"
    arguments = oneshot_arguments(config, raw, profile)
    process = launch_browser(config["executable_path"], arguments)
    try:
        deadline = time.monotonic() + config["timeout_ms"] / 1000
        while process.poll() is None:
            if time.monotonic() >= deadline:
                raise TaskError("轻模式截图超过单次操作超时。", 1)
            time.sleep(0.05)
        if not raw.is_file():
            raise TaskError("浏览器未写出截图；检查浏览器版本与启动参数。", 1)
        slices = split_png(raw.read_bytes(), config["screens"])
    finally:
        terminate_browser(process)
    for index, image in enumerate(slices):
        (shots_dir / f"{index}.png").write_bytes(image)
    return binary_version(Path(config["executable_path"])) or "unknown"


class WebSocket:
    """Minimal RFC 6455 client socket: masked text frames, ping/pong, close."""

    def __init__(self, url: str, timeout: float) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
            raise TaskError("DevTools 端点不是可用的 ws:// 地址。", 1)
        self.timeout = timeout
        self.socket = socket.create_connection(
            (parsed.hostname, parsed.port), timeout=timeout
        )
        self.buffer = bytearray()
        self._handshake(parsed.hostname, parsed.port, parsed.path or "/")

    def _recv_exact(self, length: int) -> bytes:
        while len(self.buffer) < length:
            chunk = self.socket.recv(65536)
            if not chunk:
                raise TaskError("DevTools 连接已断开。", 1)
            self.buffer.extend(chunk)
        data = bytes(self.buffer[:length])
        del self.buffer[:length]
        return data

    def _handshake(self, host: str, port: int, path: str) -> None:
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        header = bytearray()
        while b"\r\n\r\n" not in header:
            chunk = self.socket.recv(1)
            if not chunk:
                raise TaskError("DevTools 未完成 WebSocket 握手。", 1)
            header.extend(chunk)
            if len(header) > 8192:
                raise TaskError("WebSocket 握手响应异常。", 1)
        lines = header.decode("latin-1").split("\r\n")
        if "101" not in lines[0].split(" ")[:2]:
            raise TaskError("DevTools 拒绝了 WebSocket 升级。", 1)
        expect = base64.b64encode(
            hashlib.sha1(f"{key}{WS_GUID}".encode("ascii")).digest()
        ).decode("ascii")
        if not any(
            line.lower() == f"sec-websocket-accept: {expect}".lower()
            for line in lines[1:]
        ):
            raise TaskError("WebSocket 握手校验失败。", 1)

    def _send(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 1 << 16:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", length))
        mask = secrets.token_bytes(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.socket.sendall(bytes(header) + masked)

    def send_text(self, payload: str) -> None:
        self._send(0x1, payload.encode("utf-8"))

    def receive_text(self) -> str:
        """Return one complete text message, answering pings until it arrives."""
        message = bytearray()
        while True:
            first, second = self._recv_exact(2)
            final, opcode = bool(first & 0x80), first & 0x0F
            masked, length = bool(second & 0x80), second & 0x7F
            if length == 126:
                (length,) = struct.unpack(">H", self._recv_exact(2))
            elif length == 127:
                (length,) = struct.unpack(">Q", self._recv_exact(8))
            if masked:
                mask = self._recv_exact(4)
                payload = bytes(
                    byte ^ mask[index % 4]
                    for index, byte in enumerate(self._recv_exact(length))
                )
            else:
                payload = self._recv_exact(length)
            if opcode == 0x9:
                self._send(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                raise TaskError("DevTools 主动关闭连接。", 1)
            message.extend(payload)
            if final:
                return message.decode("utf-8")

    def close(self) -> None:
        try:
            self._send(0x8, b"")
        except OSError:
            pass
        finally:
            self.socket.close()


class CDPSession:
    """Command/event client over one DevTools WebSocket connection."""

    def __init__(self, url: str, timeout: float) -> None:
        self.socket = WebSocket(url, timeout)
        self.timeout = timeout
        self.pending = 0
        self.events: deque[dict[str, Any]] = deque()

    def _send(self, method: str, params: dict[str, Any], session: str | None) -> int:
        self.pending += 1
        message: dict[str, Any] = {"id": self.pending, "method": method}
        if params:
            message["params"] = params
        if session:
            message["sessionId"] = session
        self.socket.send_text(json.dumps(message))
        return self.pending

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """Send a command and return its result, buffering unrelated events."""
        wanted = self._send(method, params or {}, session)
        while True:
            message = json.loads(self.socket.receive_text())
            if message.get("id") == wanted:
                if "error" in message:
                    detail = message["error"].get("message", "unknown")
                    raise TaskError(f"DevTools 命令 {method} 失败：{detail}", 1)
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)

    def wait_event(
        self, method: str, session: str | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Wait for one named event, honouring events buffered while calling."""
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)
        while True:
            for index, event in enumerate(self.events):
                if event.get("method") == method and (
                    session is None or event.get("sessionId") == session
                ):
                    del self.events[index]
                    return event
            if time.monotonic() >= deadline:
                raise TaskError(f"等待 DevTools 事件 {method} 超时。", 1)
            message = json.loads(self.socket.receive_text())
            if "method" in message:
                self.events.append(message)

    def close(self) -> None:
        self.socket.close()


def read_devtools_endpoint(profile: Path, deadline: float) -> str:
    """Wait for Chrome to publish the DevTools port and browser path."""
    active = profile / "DevToolsActivePort"
    while True:
        try:
            lines = active.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        if len(lines) >= 2 and lines[0].strip().isdigit():
            return f"ws://127.0.0.1:{lines[0].strip()}{lines[1].strip()}"
        if time.monotonic() >= deadline:
            raise TaskError("浏览器未开放 DevTools 端口；改用 --engine oneshot。", 1)
        time.sleep(0.05)


def cdp_arguments(config: dict[str, Any], profile: Path) -> list[str]:
    """Build the DevTools-enabled headless command for real scrolling."""
    arguments = [
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--force-device-scale-factor=1",
        "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
        f"--window-size={config['width']},{config['height']}",
    ]
    if config["proxy"]:
        arguments.append(f"--proxy-server={config['proxy']}")
    arguments.append("about:blank")
    return arguments


def cdp_capture(config: dict[str, Any], shots_dir: Path) -> str:
    """Drive the real page with CDP: navigate, scroll per screen, capture."""
    profile = shots_dir.parent / "tmp" / "cdp-profile"
    process = launch_browser(config["executable_path"], cdp_arguments(config, profile))
    session: CDPSession | None = None
    operation_timeout = config["timeout_ms"] / 1000
    try:
        endpoint = read_devtools_endpoint(
            profile, time.monotonic() + operation_timeout
        )
        session = CDPSession(endpoint, operation_timeout)
        product = session.call("Browser.getVersion").get("product", "unknown")
        target = session.call("Target.createTarget", {"url": "about:blank"})
        attached = session.call(
            "Target.attachToTarget", {"targetId": target["targetId"], "flatten": True}
        )
        page = attached["sessionId"]
        session.call("Page.enable", session=page)
        session.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": config["width"],
                "height": config["height"],
                "deviceScaleFactor": 1,
                "mobile": False,
            },
            session=page,
        )
        session.call("Page.navigate", {"url": config["url"]}, session=page)
        session.wait_event("Page.loadEventFired", session=page)
        time.sleep(config["settle_ms"] / 1000)
        for index in range(config["screens"]):
            encoded = session.call(
                "Page.captureScreenshot", {"format": "png"}, session=page
            )
            (shots_dir / f"{index}.png").write_bytes(
                base64.b64decode(encoded["data"])
            )
            if index + 1 < config["screens"]:
                session.call(
                    "Runtime.evaluate",
                    {"expression": "window.scrollBy(0, window.innerHeight)"},
                    session=page,
                )
                time.sleep(config["step_wait_ms"] / 1000)
        try:
            session.call("Browser.close")
        except (OSError, TaskError):
            pass  # A closing browser may drop the connection first.
        return product.split("/", 1)[-1]
    finally:
        if session is not None:
            session.close()
        terminate_browser(process)


def probe_launch(executable: str, timeout_ms: int) -> str:
    """Verify a candidate actually starts, bounded and headless."""
    process = launch_browser(
        executable, ["--headless=new", "--disable-gpu", "--dump-dom", "about:blank"]
    )
    try:
        deadline = time.monotonic() + timeout_ms / 1000
        while process.poll() is None:
            if time.monotonic() >= deadline:
                raise TaskError("候选浏览器在期限内未退出。", 1)
            time.sleep(0.05)
    finally:
        terminate_browser(process)
    if process.returncode != 0:
        raise TaskError(f"候选浏览器启动失败（退出码 {process.returncode}）。", 1)
    return binary_version(Path(executable)) or "unknown"


def capture(config: dict[str, Any], shots_dir: Path) -> str:
    """Dispatch a light engine by name; the caller owns the workspace layout."""
    engine = config["engine"]
    if engine == "oneshot":
        return oneshot_capture(config, shots_dir)
    if engine == "cdp":
        return cdp_capture(config, shots_dir)
    raise TaskError(f"未知轻量引擎：{engine}", 2)


if __name__ == "__main__":
    raise SystemExit("Internal engine module; use shot_scroll.py --help.")
