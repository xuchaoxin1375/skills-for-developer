"""probe_local_proxies.py 的离线回归测试：PID 归组、IPv6 与排序。

pytest 风格；也可直接运行 `python tests/test_probe_local_proxies.py`，不访问外网。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve()
SCRIPT = HERE.parent.parent / "scripts" / "probe_local_proxies.py"


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("probe_local_proxies_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def usable_entry(port: int, direct: bool = False) -> dict:
    return {
        "host": "127.0.0.1",
        "port": port,
        "verdict": "usable (mixed)",
        "egressMatchesDirect": direct,
        "protocols": {
            "http": {"ok": True, "seconds": 1.0, "egress": {"ip": "203.0.113.1"}},
            "socks5": {"ok": True, "seconds": 1.0, "egress": {"ip": "203.0.113.1"}},
        },
    }


def test_build_candidates_keeps_pid_and_ipv6_loopback() -> None:
    module = load_module()
    args = SimpleNamespace(port=[7899])
    hits = [("mihomo/clash", "123", "verge-mihomo.exe")]
    listening = [("0.0.0.0", 17100, "123"), ("::1", 17200, "123")]
    candidates = module.build_candidates(args, [], hits, listening)
    by_port = {item["port"]: item for item in candidates}

    assert by_port[17100]["host"] == "127.0.0.1"
    assert by_port[17100]["pids"] == ["123"]
    assert by_port[17100]["processes"] == ["verge-mihomo.exe"]
    assert by_port[17200]["host"] == "::1"
    assert by_port[7899]["sources"] == ["cli"]


def test_source_text_includes_pid() -> None:
    module = load_module()
    text = module.source_text({"sources": ["proc:verge-mihomo.exe"], "pids": ["123"]})
    assert "verge-mihomo.exe" in text
    assert "pid=123" in text


def test_build_instances_groups_by_pid_and_ignores_unowned_ports() -> None:
    module = load_module()
    candidates = [
        {"port": 17100, "pids": ["123"], "processes": ["verge-mihomo.exe"], "verdict": "usable (mixed)"},
        {"port": 17110, "pids": ["123"], "processes": ["verge-mihomo.exe"], "verdict": "unknown (timeout)"},
        {"port": 17200, "pids": ["456"], "processes": ["verge-mihomo.exe"], "verdict": "usable (mixed)"},
        {"port": 7899, "pids": [], "processes": [], "verdict": "usable (mixed)"},
    ]
    instances = module.build_instances(candidates)

    assert [item["pid"] for item in instances] == ["123", "456"]
    assert instances[0]["ports"] == [17100, 17110]
    assert instances[0]["usablePorts"] == [17100]
    assert instances[1]["ports"] == [17200]


def test_sorted_usable_puts_direct_egress_last() -> None:
    module = load_module()
    report = {"candidates": [usable_entry(17100), usable_entry(17200, direct=True)]}
    assert [item["port"] for item in module.sorted_usable(report)] == [17100, 17200]


def test_url_of_brackets_ipv6_literal() -> None:
    module = load_module()
    entry = {"host": "::1", "port": 7890, "protocols": {"http": {"ok": True}}}
    assert module.url_of(entry) == "http://[::1]:7890"


def test_load_registry_reads_instance_mixed_entries() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / "proxy-resources.json"
        registry.write_text(
            json.dumps(
                {
                    "proxies": [
                        {"name": "flat", "url": "http://127.0.0.1:7897"},
                    ],
                    "instances": [
                        {"name": "robin", "mixed": "http://127.0.0.1:17797", "listeners": {"all": 17100}},
                    ],
                }
            ),
            encoding="utf-8",
        )
        original = module.REGISTRY
        module.REGISTRY = registry
        try:
            entries = module.load_registry()
        finally:
            module.REGISTRY = original
    assert {entry["name"] for entry in entries} == {"flat", "robin:mixed"}
    assert {entry["port"] for entry in entries} == {7897, 17797}


def test_help_lists_copy_all_and_json() -> None:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), "--help"],
        capture_output=True,
        timeout=30,
        check=False,
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    assert proc.returncode == 0
    assert "--copy-all" in out
    assert "--json" in out


def main() -> int:
    """无 pytest 时的独立运行入口。"""
    tests = [(name, obj) for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]
    failures = 0
    for name, func in tests:
        try:
            func()
        except AssertionError as error:
            failures += 1
            print(f"FAIL {name}: {error}")
        else:
            print(f"ok   {name}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
