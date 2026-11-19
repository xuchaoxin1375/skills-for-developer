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
from pathlib import Path
from typing import Any

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
        assert "secret" not in stdout


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
