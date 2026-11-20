"""check_network_env.py 的回归测试：解析、脱敏、项目配置与离线报告。

pytest 风格（与兄弟 skill 的测试一致）；也可直接运行
`python tests/test_check_network_env.py`，不依赖第三方包与外部网络。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve()
SCRIPT = HERE.parent.parent / "scripts" / "check_network_env.py"


def load_module() -> Any:
    """把脚本当模块加载，用于纯函数级断言。"""
    spec = importlib.util.spec_from_file_location("check_network_env_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(*args: str, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """跑一次脚本，返回 (退出码, stdout, stderr)。"""
    child_env = {**os.environ, "PYTHONUTF8": "1", **(env or {})}
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        capture_output=True,
        timeout=120,
        env=child_env,
        check=False,
    )
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


def test_mask_url_hides_credentials() -> None:
    module = load_module()
    assert module.mask_url("https://user:token@mirror.example/simple") == "https://***@mirror.example/simple"
    assert module.mask_url("https://mirror.example/simple") == "https://mirror.example/simple"


def test_mask_proxy_server_hides_credentials() -> None:
    module = load_module()
    assert module.mask_proxy_server(
        "http=user:secret@proxy.example:8080;https=proxy.example:8080"
    ) == "http=***@proxy.example:8080;https=proxy.example:8080"


def test_parse_pip_config_list_and_prefix_priority() -> None:
    module = load_module()
    parsed = module.parse_key_value_lines(
        "global.index-url='https://global.example/simple'\n"
        ":env:.index-url='https://env.example/simple'\n"
        "install.trusted-host='mirror.example'\n"
    )
    assert parsed["global.index-url"] == "https://global.example/simple"
    assert module.pick_prefixed(parsed, "index-url") == "https://env.example/simple"
    assert module.pick_prefixed(parsed, "missing") is None


def test_read_ini_keeps_network_keys() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pip.ini"
        path.write_text(
            "[global]\nindex-url = https://user:secret@mirror.example/simple\n"
            "timeout = 15\n[install]\ntrusted-host = mirror.example\n",
            encoding="utf-8",
        )
        values = module.read_ini(path, module.PIP_KEYS)
        assert values["global.index-url"] == "https://***@mirror.example/simple"
        assert values["install.trusted-host"] == "mirror.example"
        assert all("timeout" not in key for key in values)


def test_read_npmrc_filters_tokens_and_unknown_keys() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".npmrc"
        path.write_text(
            "registry=https://registry.npmmirror.com\n"
            "//registry.npmjs.org/:_authToken=secret-token\n"
            "allow-scripts=some-package\n",
            encoding="utf-8",
        )
        values = module.read_npmrc(path)
        assert values == {"registry": "https://registry.npmmirror.com"}
        assert "secret-token" not in json.dumps(values)


def test_filter_npm_config_whitelists_keys() -> None:
    module = load_module()
    filtered = module.filter_npm_config(
        {
            "registry": "https://user:secret@registry.example",
            "proxy": "http://proxy.example:8080",
            "_authToken": "secret-token",
            "//registry.example/:_authToken": "secret-token",
            "strict-ssl": True,
            "fetch-timeout": 300000,
        }
    )
    assert filtered["registry"] == "https://***@registry.example"
    assert filtered["strict-ssl"] is True
    assert filtered["fetch-timeout"] == 300000
    assert "secret-token" not in json.dumps(filtered)


def test_yarn_config_readers_ignore_auth() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        modern = Path(tmp) / ".yarnrc.yml"
        modern.write_text(
            "npmRegistryServer: \"https://registry.npmmirror.com\"\n"
            "npmAuthToken: \"secret-token\"\n"
            "nodeLinker: node-modules\n",
            encoding="utf-8",
        )
        classic = Path(tmp) / ".yarnrc"
        classic.write_text(
            "registry \"https://registry.npmmirror.com\"\n"
            "//registry.npmjs.org/:_authToken \"secret-token\"\n",
            encoding="utf-8",
        )
        modern_values = module.read_yarnrc_yml(modern)
        classic_values = module.read_yarnrc_classic(classic)
        assert modern_values == {"npmRegistryServer": "https://registry.npmmirror.com"}
        assert classic_values == {"registry": "https://registry.npmmirror.com"}
        assert "secret-token" not in json.dumps(modern_values) + json.dumps(classic_values)


def test_uv_project_config_parsing() -> None:
    module = load_module()
    if module.tomllib is None:
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pyproject.toml"
        path.write_text(
            "[tool.uv]\n"
            "default-index = \"https://mirror.example/simple\"\n"
            "\n"
            "[[tool.uv.index]]\n"
            "name = \"mirror\"\n"
            "url = \"https://mirror.example/simple\"\n",
            encoding="utf-8",
        )
        parsed = module.read_uv_config(path, True)
        assert parsed["defaultIndex"] == "https://mirror.example/simple"
        assert parsed["indexes"][0]["name"] == "mirror"
        assert parsed["indexes"][0]["url"] == "https://mirror.example/simple"


def test_lockfile_hosts_scan_is_bounded() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "package-lock.json"
        path.write_text(
            json.dumps(
                {
                    "packages": {
                        "node_modules/a": {"resolved": "https://registry.npmmirror.com/a/-/a-1.0.0.tgz"},
                        "node_modules/b": {"resolved": "https://registry.npmjs.org/b/-/b-1.0.0.tgz"},
                    }
                }
            ),
            encoding="utf-8",
        )
        result = module.lockfile_hosts(path)
        assert result["hosts"] == ["registry.npmmirror.com", "registry.npmjs.org"]
        assert result["truncated"] is False


def test_git_config_output_parsing_and_masking() -> None:
    module = load_module()
    text = (
        'file:"/home/dev/.gitconfig"\turl.https://mirror.example/github/.insteadof https://github.com/\n'
        'file:"/home/dev/.gitconfig"\thttp.proxy http://user:secret@proxy.example:8080\n'
    )
    entries = module.parse_git_config_output(text, "global")
    assert entries[0]["value"] == "https://github.com/"
    assert entries[1]["value"] == "http://***@proxy.example:8080"
    assert entries[1]["scope"] == "global"


def test_classify_status() -> None:
    module = load_module()
    assert module.classify_status(401) == "auth-or-blocked"
    assert module.classify_status(403) == "auth-or-blocked"
    assert module.classify_status(429) == "rate-limited"
    assert module.classify_status(404) == "not-found"
    assert module.classify_status(503) == "server-error"


def test_build_probe_specs_uses_effective_sources() -> None:
    module = load_module()
    report = {
        "git": {"available": True},
        "node": {"npm": {"available": True, "registry": "https://registry.example"}},
        "python": {
            "pip": {
                "available": True,
                "indexUrl": "https://pypi.example/simple",
                "extraIndexUrls": ["https://extra.example/simple"],
            },
            "uv": {"available": False},
        },
    }
    specs = module.build_probe_specs(report)
    targets = [spec["target"] for spec in specs]
    urls = [spec["url"] for spec in specs]
    assert "github-git" in targets
    assert "npm-registry" in targets
    assert "pypi-index" in targets
    assert "pypi-extra" in targets
    assert "https://registry.example/is-number/latest" in urls
    assert "https://pypi.example/simple/is-number/" in urls
    assert "https://extra.example/simple/is-number/" in urls


def test_probe_specs_respect_selected_groups() -> None:
    module = load_module()
    assert module.build_probe_specs({}) == []
    report = {
        "git": {"available": False},
        "node": {"npm": {"available": False}},
        "python": {"pip": {"available": False}, "uv": {"available": False}},
    }
    specs = module.build_probe_specs(report)
    assert [spec["target"] for spec in specs] == ["github-raw"]


def test_offline_artifacts_report_is_masked() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / "proxy-resources.json"
        registry.write_text(
            json.dumps(
                {
                    "updated": "2026-01-01",
                    "artifact_mirrors": [
                        {
                            "name": "stub",
                            "type": "playwright-download-host",
                            "url": "https://user:secret@cdn.example/playwright",
                            "verified": "2026-01-01",
                            "notes": "stub",
                        }
                    ],
                    "proxies": [],
                }
            ),
            encoding="utf-8",
        )
        code, stdout, stderr = run_script("--json", "--only", "artifacts", "--registry", str(registry))
        assert code == 0, stderr
        report = json.loads(stdout)
        assert report["mode"] == "offline"
        assert report["probe"]["ran"] is False
        assert report["artifacts"]["artifactMirrors"][0]["url"] == "https://***@cdn.example/playwright"
        assert "secret" not in stdout


def test_route_proxy_env_is_masked() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / "proxy-resources.json"
        registry.write_text(json.dumps({"proxies": []}), encoding="utf-8")
        code, stdout, stderr = run_script(
            "--json",
            "--only",
            "route",
            "--registry",
            str(registry),
            env={"HTTPS_PROXY": "http://user:secret@proxy.example:8080"},
        )
        assert code == 0, stderr
        report = json.loads(stdout)
        assert report["route"]["env"]["HTTPS_PROXY"] == "http://***@proxy.example:8080"
        assert "system" in report["route"]
        assert "secret" not in stdout


def test_parse_proxy_server_variants() -> None:
    module = load_module()
    assert module.parse_proxy_server("127.0.0.1:7897") == {
        "http": "127.0.0.1:7897",
        "https": "127.0.0.1:7897",
    }
    assert module.parse_proxy_server(
        "http=127.0.0.1:7897;https=127.0.0.1:7898;socks=127.0.0.1:7899"
    ) == {
        "http": "127.0.0.1:7897",
        "https": "127.0.0.1:7898",
        "socks": "127.0.0.1:7899",
    }
    assert module.endpoint_url("http", "127.0.0.1:7897") == "http://127.0.0.1:7897"
    assert module.endpoint_url("socks", "127.0.0.1:7899") == "socks5://127.0.0.1:7899"


def test_parse_scutil_proxy() -> None:
    module = load_module()
    info = module.parse_scutil_proxy(
        "<dictionary> {\n"
        "  ExceptionsList : <array> {\n"
        "    0 : *.local\n"
        "    1 : 169.254/16\n"
        "  }\n"
        "  HTTPEnable : 1\n"
        "  HTTPPort : 7897\n"
        "  HTTPProxy : 127.0.0.1\n"
        "  HTTPSEnable : 0\n"
        "  SOCKSEnable : 1\n"
        "  SOCKSPort : 7898\n"
        "  SOCKSProxy : 127.0.0.1\n"
        "  ProxyAutoConfigEnable : 0\n"
        "  ProxyAutoDiscoveryEnable : 0\n"
        "}\n"
    )
    assert info["available"] is True
    assert info["enabled"] is True
    assert info["http"] == "http://127.0.0.1:7897"
    assert info["socks"] == "socks5://127.0.0.1:7898"
    assert "https" not in info
    assert info["bypass"] == "*.local, 169.254/16"


def test_windows_system_proxy_reads_registry() -> None:
    module = load_module()
    values = {
        "ProxyEnable": 1,
        "ProxyServer": (
            "http=127.0.0.1:7897;https=127.0.0.1:7897;socks=127.0.0.1:7898"
        ),
        "ProxyOverride": "localhost;127.*",
        "AutoConfigURL": "",
        "AutoDetect": 0,
    }

    class FakeKey:
        def __enter__(self) -> "FakeKey":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    def query(key: object, name: str) -> tuple[Any, int]:
        if name in values:
            return values[name], 1
        raise OSError(name)

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=lambda root, path: FakeKey(),
        QueryValueEx=query,
    )
    with mock.patch.dict(sys.modules, {"winreg": fake_winreg}):
        info = module.windows_system_proxy()
    assert info["available"] is True
    assert info["enabled"] is True
    assert info["http"] == "http://127.0.0.1:7897"
    assert info["socks"] == "socks5://127.0.0.1:7898"
    assert info["bypass"] == "localhost;127.*"


def test_windows_system_proxy_detects_pac() -> None:
    module = load_module()
    values = {
        "ProxyEnable": 0,
        "AutoConfigURL": "http://pac.example/proxy.pac",
        "AutoDetect": 1,
    }

    class FakeKey:
        def __enter__(self) -> "FakeKey":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    def query(key: object, name: str) -> tuple[Any, int]:
        if name in values:
            return values[name], 1
        raise OSError(name)

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=lambda root, path: FakeKey(),
        QueryValueEx=query,
    )
    with mock.patch.dict(sys.modules, {"winreg": fake_winreg}):
        info = module.windows_system_proxy()
    assert info["enabled"] is True
    assert info["pac"] == "http://pac.example/proxy.pac"
    assert info["autoDetect"] is True


def test_linux_system_proxy_reads_gsettings() -> None:
    module = load_module()
    responses = {
        ("org.gnome.system.proxy", "mode"): "'manual'",
        ("org.gnome.system.proxy.http", "host"): "'127.0.0.1'",
        ("org.gnome.system.proxy.http", "port"): "7897",
        ("org.gnome.system.proxy.https", "host"): "'127.0.0.1'",
        ("org.gnome.system.proxy.https", "port"): "7898",
        ("org.gnome.system.proxy.socks", "host"): "''",
        ("org.gnome.system.proxy.socks", "port"): "0",
        ("org.gnome.system.proxy", "ignore-hosts"): "['localhost', '127.0.0.0/8']",
    }

    def fake_run(args: list[str], timeout: float, extra_env: dict[str, str] | None = None):
        return 0, responses.get((args[2], args[3]), ""), ""

    with mock.patch.object(module.shutil, "which", return_value="/usr/bin/gsettings"):
        with mock.patch.object(module, "run_command", side_effect=fake_run):
            info = module.linux_system_proxy()
    assert info["available"] is True
    assert info["enabled"] is True
    assert info["mode"] == "manual"
    assert info["http"] == "http://127.0.0.1:7897"
    assert info["https"] == "https://127.0.0.1:7898"
    assert "socks" not in info
    assert info["bypass"] == "['localhost', '127.0.0.0/8']"


def test_render_route_distinguishes_system_proxy_from_env() -> None:
    module = load_module()
    report = {
        "generated": "2026-01-01T00:00:00+08:00",
        "mode": "offline",
        "route": {
            "env": {"NO_PROXY": "127.0.0.1,localhost"},
            "system": {
                "available": True,
                "enabled": False,
                "configuredServer": "127.0.0.1:7897",
            },
            "registry": {"available": False, "reason": "stub"},
        },
        "probe": {"ran": False, "reason": "stub"},
    }
    text = module.render_human(report)
    assert "系统代理: 关闭（已配置 127.0.0.1:7897，但未启用）" in text
    assert "只有环境变量生效" not in text

    report["route"]["system"] = {
        "available": True,
        "enabled": True,
        "http": "http://127.0.0.1:7897",
    }
    text = module.render_human(report)
    assert "系统代理: http=http://127.0.0.1:7897" in text
    assert "系统代理已开但环境变量未设" in text


def test_invalid_only_exits_nonzero() -> None:
    code, stdout, stderr = run_script("--only", "nope")
    assert code == 2
    assert "未知分组" in stderr
    assert stdout == ""


def test_help_is_available() -> None:
    code, stdout, stderr = run_script("--help")
    assert code == 0, stderr
    assert "--probe" in stdout
    assert "--project" in stdout
    assert "--registry" in stdout


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
