"""Real subprocess fixture: a worker and a child that holds a listening socket."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
import time

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    if sys.argv[1:] == ["--caller"]:
        from managed_browser import run_managed

        request = json.loads(sys.stdin.readline())
        run_managed(
            request["command"],
            request["payload"],
            request["wall_timeout_ms"],
            state_root=Path(request["state_root"]),
        )
        return 0
    if sys.argv[1:2] == ["--leaf"]:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            Path(sys.argv[2]).write_text(
                str(listener.getsockname()[1]), encoding="utf-8"
            )
            time.sleep(25)  # Test failure cannot leave an unbounded orphan.
        return 0
    config = json.loads(sys.stdin.readline())  # Start gate used by the real guardian.
    subprocess.Popen(
        [sys.executable, "-X", "utf8", __file__, "--leaf", config["ready"]],
        stdin=subprocess.DEVNULL,
        start_new_session=config["mode"] == "detached-success",
    )
    deadline = time.monotonic() + 5
    while not Path(config["ready"]).exists():
        if time.monotonic() > deadline:
            return 1
        time.sleep(0.02)
    if config["mode"] in ("success", "detached-success"):
        (Path(config["workspace"]) / "result.json").write_text(
            '{"code":0}', encoding="utf-8"
        )
        return 0  # Intentionally leave a child for residual-process cleanup.
    if config["mode"] == "failure":
        return 1
    time.sleep(25)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
