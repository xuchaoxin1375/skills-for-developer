"""inspect_mihomo.py 的回归测试：配置解析、脱敏、分组判读与离线报告。

pytest 风格（与兄弟脚本一致）；也可直接运行
`python tests/test_inspect_mihomo.py`，不访问外网。
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
SCRIPT = HERE.parent.parent / "scripts" / "inspect_mihomo.py"

CONFIG = """\
mode: rule
mixed-port: 7890
socks-port: 7891
allow-lan: false
ipv6: true
unified-delay: true
external-controller: 127.0.0.1:9090
secret: 's3cr3t-value'
log-level: info
tun:
  enable: false
  stack: gVisor
proxy-providers:
  online:
    type: http
    url: https://example.invalid/sub?token=abc
    interval: 43200
    health-check:
      enable: true
      interval: 300
proxy-groups:
- name: PROXY
  type: select
  proxies:
  - ALL-LB
  - DIRECT
  - REJECT
- name: ALL-LB
  type: load-balance
  use:
  - online
  url: http://example.invalid/204
  interval: 300
  strategy: round-robin
  exclude-filter: (?i)(流量|到期)
- name: EMPTY
  type: load-balance
  use:
  - missing
rule-providers:
  cn:
    type: http
    behavior: ipcidr
    url: https://example.invalid/cn.yaml
    path: ./ruleset/cn.yaml
    interval: 86400
rules:
- MATCH,PROXY
"""

PROFILES = """\
# Profiles Config for Clash Verge
current: uid-active
items:
- uid: uid-active
  type: local
  name: default.generated.yaml
  file: uid-active.yaml
  updated: 1795059447
- uid: uid-remote
  type: remote
  name: remote-sub
  file: uid-remote.yaml
  url: https://sub.example.invalid/api?token=secret
  updated: 1795014516
- uid: uid-merge
  type: merge
  file: merge.yaml
"""


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("inspect_mihomo_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        capture_output=True,
        timeout=60,
        check=False,
    )
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


@contextlib.contextmanager
def workspace():
    path = Path(tempfile.mkdtemp(prefix="inspect-mihomo-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def fixture_ctx(tmp: Path) -> dict:
    config = tmp / "runtime.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    profiles = tmp / "profiles.yaml"
    profiles.write_text(PROFILES, encoding="utf-8")
    return {
        "client": "test",
        "root": str(tmp),
        "runtime_config": str(config),
        "profiles_file": str(profiles),
        "candidates": [str(config)],
        "_text": CONFIG,
    }


def fixture_api() -> dict:
    return {
        "version": {"version": "v0-test", "meta": True},
        "configs": {
            "mode": "rule",
            "mixed-port": 7890,
            "port": 0,
            "socks-port": 0,
            "allow-lan": False,
            "tun": {"enable": False, "stack": "gVisor"},
        },
        "proxies": {
            "proxies": {
                "PROXY": {"type": "Selector", "now": "ALL-LB", "all": ["ALL-LB", "DIRECT", "REJECT"]},
                "ALL-LB": {"type": "LoadBalance", "now": None, "all": ["node-a", "node-b"]},
                "EMPTY": {"type": "LoadBalance", "now": None, "all": ["COMPATIBLE"]},
                "DIRECT": {"type": "Direct"},
                "REJECT": {"type": "Reject"},
                "COMPATIBLE": {"type": "Compatible"},
                "node-a": {"type": "Vless", "alive": True, "history": [{"delay": 120}]},
                "node-b": {"type": "Hysteria2", "alive": False, "history": [{"delay": 0}]},
                "剩余流量：1 GB": {"type": "Hysteria2", "alive": True, "history": [{"delay": 90}]},
            }
        },
        "providers": {
            "providers": {
                "online": {
                    "vehicleType": "HTTP",
                    "updatedAt": "2026-01-01T00:00:00Z",
                    "proxies": [{"name": "node-a"}],
                    "subscriptionInfo": {"Expire": 1, "Total": 1},
                },
                "missing": {"vehicleType": "File", "proxies": []},
            }
        },
        "rules_providers": {
            "providers": {
                "cn": {
                    "vehicleType": "HTTP",
                    "updatedAt": "2026-01-01T00:00:00Z",
                    "ruleCount": 10,
                }
            }
        },
        "rules": {
            "rules": [
                {"type": "RuleSet", "payload": "cn", "proxy": "DIRECT"},
                {"type": "Match", "payload": "", "proxy": "PROXY"},
            ]
        },
        "connections": {"connections": [{"chains": ["node-a", "ALL-LB", "PROXY"]}]},
    }


def build(tmp: Path) -> dict:
    module = load_module()
    return module.build_model(fixture_ctx(tmp), fixture_api(), None)


def test_parse_config_reads_controller_secret_and_tun() -> None:
    module = load_module()
    parsed = module.parse_config_text(CONFIG)
    assert parsed["keys"]["external-controller"] == "127.0.0.1:9090"
    assert parsed["keys"]["secret"] == "s3cr3t-value"
    assert parsed["keys"]["mixed-port"] == "7890"
    assert parsed["tun"] == {"enable": "false", "stack": "gVisor"}


def test_parse_profiles_masks_url_and_keeps_remote_metadata() -> None:
    module = load_module()
    chain = module.parse_profile_chain(PROFILES)
    assert chain["current"] == "uid-active"
    remote = next(i for i in chain["items"] if i["uid"] == "uid-remote")
    assert remote["url"] == "<masked>"
    assert remote["urlHost"] == "sub.example.invalid"
    assert "token=secret" not in json.dumps(chain)


def test_parse_group_defs_keeps_strategy_filter_and_use() -> None:
    module = load_module()
    groups = {g["name"]: g for g in module.parse_group_defs(CONFIG)}
    assert groups["ALL-LB"]["type"] == "load-balance"
    assert groups["ALL-LB"]["strategy"] == "round-robin"
    assert groups["ALL-LB"]["use"] == ["online"]
    assert groups["ALL-LB"]["filters"][0]["key"] == "exclude-filter"
    assert groups["PROXY"]["use"] == []


def test_human_age_handles_epoch_strings_and_missing_values() -> None:
    module = load_module()
    assert module.human_age("0001-01-01T00:00:00Z") == "未记录"
    assert module.human_age(None) == "未记录"
    assert "天前" in module.human_age("1783506004")


def test_build_model_flags_empty_group_direct_members_and_rotation() -> None:
    with workspace() as tmp:
        model = build(tmp)
    titles = {f["title"] for f in model["findings"]}
    assert "存在空分组" in titles
    assert "主选择组混入直连/拒绝项" in titles
    rotation = next(f for f in model["findings"] if f["title"] == "轮换出口的分组")
    assert "无登录公开页面爬虫" in rotation["detail"]
    empty = next(g for g in model["nodes"]["groups"] if g["name"] == "EMPTY")
    assert empty["leaves"] == 0


def test_build_model_reports_default_chain_and_unreachable_nodes() -> None:
    with workspace() as tmp:
        model = build(tmp)
    chain = next(f for f in model["findings"] if f["title"] == "默认出口链路")
    assert "PROXY -> ALL-LB" in chain["detail"]
    unreachable = next(f for f in model["findings"] if f["title"] == "有节点不在任何分组里")
    assert "剩余流量" in unreachable["detail"]


def test_build_model_includes_rule_providers() -> None:
    with workspace() as tmp:
        model = build(tmp)
    rule = next(p for p in model["providers"] if p["kind"] == "rule")
    assert rule["name"] == "cn"
    assert rule["count"] == 10


def test_model_and_report_never_contain_secret_or_subscription_url() -> None:
    module = load_module()
    with workspace() as tmp:
        model = build(tmp)
    dumped = json.dumps(model, ensure_ascii=False)
    assert "s3cr3t-value" not in dumped
    assert "token=secret" not in dumped
    report = module.render(model)
    assert "s3cr3t-value" not in report
    assert "默认出口链路" in report
    assert "## 分组与当前选中" in report


def test_explicit_config_with_unreachable_controller_exits_1() -> None:
    with workspace() as tmp:
        config = tmp / "runtime.yaml"
        config.write_text(
            "external-controller: 127.0.0.1:1\nsecret: x\nmode: rule\nproxy-groups:\nrules:\n",
            encoding="utf-8",
        )
        code, out, _ = run_script("--config", str(config))
    assert code == 1
    assert "# mihomo 环境检查报告" in out
    assert "控制 API：不可用" in out


def test_missing_config_exits_2() -> None:
    with workspace() as tmp:
        code, _, err = run_script("--config", str(tmp / "nope.yaml"))
    assert code == 2
    assert "没有找到" in err


def test_parse_process_paths_handles_d_and_f_flags() -> None:
    module = load_module()
    windows = r'"\\?\C:\Apps\verge-mihomo.exe" -d C:\Data\verge -f "C:\Data\verge\clash-verge.yaml" -ext-ctl-pipe \\.\pipe\verge'
    parsed = module.parse_process_paths(windows, posix=False)
    assert parsed["dirs"] == [r"C:\Data\verge"]
    assert parsed["files"] == [r"C:\Data\verge\clash-verge.yaml"]

    posix = "/usr/bin/mihomo -d /etc/mihomo --config=/etc/mihomo/config.yaml"
    parsed = module.parse_process_paths(posix, posix=True)
    assert parsed["dirs"] == ["/etc/mihomo"]
    assert parsed["files"] == ["/etc/mihomo/config.yaml"]


def test_find_client_uses_process_directory() -> None:
    module = load_module()
    module.CLIENT_ROOTS = ()
    with workspace() as tmp:
        (tmp / "runtime.yaml").write_text(CONFIG, encoding="utf-8")
        processes = [
            {"pid": 4242, "name": "verge-mihomo.exe", "exe": "", "cmdline": f'-d "{tmp}"'}
        ]
        ctx = module.find_client(None, processes=processes)
    assert ctx is not None
    assert ctx["discovery"] == "process"
    assert ctx["process"] == {"name": "verge-mihomo.exe", "pid": 4242}
    assert ctx["runtime_config"].endswith("runtime.yaml")


def test_find_client_falls_back_to_directory_scan() -> None:
    module = load_module()
    with workspace() as tmp:
        (tmp / "runtime.yaml").write_text(CONFIG, encoding="utf-8")
        module.CLIENT_ROOTS = (("test", str(tmp)),)
        ctx = module.find_client(None, processes=[], use_process=False)
    assert ctx is not None
    assert ctx["discovery"] == "scan"
    assert ctx["runtime_config"].endswith("runtime.yaml")


def test_parse_provider_defs_separates_provider_and_health_check_intervals() -> None:
    module = load_module()
    defs = module.parse_provider_defs(CONFIG)
    proxy = defs[("proxy", "online")]
    assert proxy["type"] == "http"
    assert proxy["interval"] == 43200
    assert proxy["healthCheckInterval"] == 300
    rule = defs[("rule", "cn")]
    assert rule["path"] == "./ruleset/cn.yaml"
    assert rule["interval"] == 86400


def test_resolve_provider_path_uses_explicit_path_or_url_md5() -> None:
    module = load_module()
    defs = module.parse_provider_defs(CONFIG)
    home = Path("/home/user/.config/mihomo")
    explicit = module.resolve_provider_path(defs[("rule", "cn")], str(home))
    assert Path(explicit) == home / "ruleset" / "cn.yaml"
    digest = hashlib.md5(b"https://example.invalid/sub?token=abc").hexdigest()
    derived = module.resolve_provider_path(defs[("proxy", "online")], str(home))
    assert Path(derived) == home / "proxies" / digest
    assert module.resolve_provider_path({"type": "inline"}, str(home)) is None


def test_build_providers_marks_stale_against_own_interval() -> None:
    module = load_module()
    now = datetime.now(timezone.utc)
    defs = {("proxy", "p"): {"name": "p", "kind": "proxy", "type": "http",
                             "interval": 43200, "url": "https://example.invalid/sub", "path": ""}}
    api = {"p": {"vehicleType": "HTTP", "updatedAt": (now - timedelta(hours=30)).isoformat(),
                 "proxies": [{"name": "a"}], "subscriptionInfo": {}}}
    rows = module.build_providers(api, {}, defs, None)
    assert rows[0]["stale"] is True
    api["p"]["updatedAt"] = (now - timedelta(hours=6)).isoformat()
    rows = module.build_providers(api, {}, defs, None)
    assert rows[0]["stale"] is False


def test_merge_nodes_includes_provider_only_nodes() -> None:
    module = load_module()
    merged = module.merge_nodes(
        {"GROUP": {"type": "Selector", "all": ["node-a"]}},
        {"prov": {"proxies": [{"name": "node-a", "type": "Vless"}]}},
    )
    assert merged["node-a"]["type"] == "Vless"
    assert module.leaf_names(merged) == ["node-a"]


def test_parse_process_paths_reads_ext_ctl_and_secret() -> None:
    module = load_module()
    parsed = module.parse_process_paths(
        r"mihomo -d C:\data -ext-ctl 127.0.0.1:9090 -secret topsecret", posix=False
    )
    assert parsed["dirs"] == [r"C:\data"]
    assert parsed["controller"] == "127.0.0.1:9090"
    assert parsed["secret"] == "topsecret"


def test_delay_group_targets_uses_leaf_groups_only() -> None:
    module = load_module()
    proxies = {
        "TOP": {"type": "Selector", "all": ["SUB"]},
        "SUB": {"type": "LoadBalance", "all": ["leaf"]},
        "LEAF": {"type": "LoadBalance", "all": ["leaf"]},
        "leaf": {"type": "Vless"},
        "DIRECT": {"type": "Direct"},
    }
    calls: list[str] = []

    def fake(base, secret, path, timeout=8):
        calls.append(path)
        return {"SUB": 1} if "/group/TOP/" in path else ({"leaf": 123} if "/group/LEAF/" in path else {})

    original = module.api_get
    module.api_get = fake
    try:
        result = module.delay_group_targets("http://x", "", ["leaf"], proxies, "http://test", 1000)
    finally:
        module.api_get = original
    assert result == {"leaf": 123}
    assert not any("/group/TOP/" in call for call in calls)


def test_parse_subscription_names_reads_proxies_section() -> None:
    module = load_module()
    text = (
        "proxies:\n"
        "- { name: A, type: vless }\n"
        '- { name: "B node", type: ss }\n'
        "- name: D\n"
        "  type: trojan\n"
        "proxy-groups:\n"
        "- name: GROUP\n"
    )
    assert module.parse_subscription_names(text) == ["A", "B node", "D"]


def test_compare_subscriptions_separates_real_and_info_nodes() -> None:
    module = load_module()
    defs = {("proxy", "p"): {"name": "p", "kind": "proxy", "type": "http",
                             "url": "https://example.invalid/sub"}}
    api = {"p": {"proxies": [{"name": "A"}, {"name": "OLD"}, {"name": "剩余流量：1 GB"}]}}
    original = module.fetch_subscription
    module.fetch_subscription = lambda url, proxy_url=None, timeout=20: (
        "proxies:\n- name: A\n- name: NEW\n- name: 剩余流量：2 GB\n"
    )
    try:
        rows = module.compare_subscriptions(defs, api, None)
    finally:
        module.fetch_subscription = original
    assert rows[0]["addedReal"] == ["NEW"]
    assert rows[0]["addedInfo"] == ["剩余流量：2 GB"]
    assert rows[0]["removedReal"] == ["OLD"]


def test_help_lists_core_options() -> None:
    code, out, _ = run_script("--help")
    assert code == 0
    for option in ("--config", "--controller", "--json", "--delay", "--report", "--process", "--no-process",
                   "--compare-subscriptions", "--subscription-proxy"):
        assert option in out


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
