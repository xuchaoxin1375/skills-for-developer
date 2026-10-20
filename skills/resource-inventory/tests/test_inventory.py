"""inventory.py 的回归测试：委派、降级与项目探测。

pytest 风格（与兄弟 skill 的测试一致）；也可直接运行 `python tests/test_inventory.py`，
不依赖第三方包与外部网络。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
INVENTORY = HERE.parent.parent / "scripts" / "inventory.py"

CHECK_ENV_STUB = """
import json

def scan_environments(required, scripts_dir):
    return []
"""

BROWSER_STUB = '''
def discover_browsers():
    class Candidate:
        def as_dict(self):
            return {"browser": "stub", "path": "/stub/chrome", "source": "stub",
                    "eligible": True, "reason": "stub"}

    return [Candidate()]
'''

PROBE_STUB = """
import json
import sys

print(json.dumps({
    "url": "https://example.test/trace",
    "direct": {"ok": False, "status": None, "seconds": 0.1, "egress": None, "error": "stub"},
    "usable": [{"port": 7897, "verdict": "usable (mixed)", "protocols": ["http"]}],
    "summary": {"usable": 1},
    "blindSpots": [],
}, ensure_ascii=False))
sys.exit(0)
"""


def child_env() -> dict[str, str]:
    """子进程环境：沿用当前环境并强制 UTF-8 输出。"""
    return {**os.environ, "PYTHONUTF8": "1"}


def run_script(script: Path, *args: str) -> tuple[int, str, str]:
    """跑一次脚本，返回 (退出码, stdout, stderr)；只用于 --json / --help 这类确定性调用。"""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(script), *args],
        capture_output=True,
        timeout=180,
        env=child_env(),
        check=False,
    )
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


def run_inventory(*args: str) -> tuple[int, dict[str, Any] | None, str]:
    """跑一次 inventory.py，返回 (退出码, 解析后的 JSON 或 None, stderr)。"""
    code, stdout, stderr = run_script(INVENTORY, *args)
    data = None
    if stdout.strip():
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            data = None
    return code, data, stderr


def make_skills_root(base: Path, *, with_siblings: bool = True) -> Path:
    """搭一个最小 skills 目录：resource-inventory 实体 + 可控的兄弟 skill 桩。"""
    root = base / "skills"
    (root / "resource-inventory" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "resource-inventory" / "scripts" / "inventory.py").write_text("", encoding="utf-8")
    if not with_siblings:
        return root
    check_env = root / "resilient-browser-fetch" / "scripts" / "check_environment.py"
    check_env.parent.mkdir(parents=True, exist_ok=True)
    check_env.write_text(CHECK_ENV_STUB, encoding="utf-8")
    browser = root / "browser-automation" / "scripts" / "browser_discovery.py"
    browser.parent.mkdir(parents=True, exist_ok=True)
    browser.write_text(BROWSER_STUB, encoding="utf-8")
    probe = root / "network-access" / "scripts" / "probe_local_proxies.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(PROBE_STUB, encoding="utf-8")
    return root


def write_stub_scan(skills_root: Path, environment_path: str) -> None:
    """让 check_environment.py 桩返回一个具名解释器，用于断言委派结果被透传。"""
    payload = {
        "required": ["playwright"],
        "environments": [
            {
                "path": environment_path,
                "version": "3.13.0",
                "manager": "conda:stub",
                "source": "stub",
                "engines": ["static", "playwright", "scrapling"],
                "levels": [0, 1, 2],
                "packages": {"playwright": "1.0.0", "scrapling": None},
                "ok": True,
            }
        ],
    }
    script = skills_root / "resilient-browser-fetch" / "scripts" / "check_environment.py"
    script.write_text(
        "import json\n\nDATA = " + repr(payload) + "\n\n"
        "def scan_environments(required, scripts_dir):\n    return DATA['environments']\n\n"
        "def main():\n    print(json.dumps(DATA, ensure_ascii=False))\n    return 0\n\n"
        "if __name__ == '__main__':\n    raise SystemExit(main())\n",
        encoding="utf-8",
    )


def make_project(root: Path) -> Path:
    """搭一个有 test 工具痕迹的项目。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "packageManager": "pnpm@12.0.0",
                "scripts": {"test": "vitest run", "build": "vite build"},
                "devDependencies": {"@playwright/test": "1.0.0", "vitest": "2.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (root / "playwright.config.ts").write_text("export default {}\n", encoding="utf-8")
    (root / ".venv").mkdir(exist_ok=True)
    return root


def test_report_json_structure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        write_stub_scan(skills_root, "/stub/python")
        code, report, stderr = run_inventory("--json", "--skills-root", str(skills_root))
        assert code == 0, stderr
        assert report is not None
        for section in ("host", "runtimes", "pythonEnvs", "browsers", "proxies", "projects"):
            assert section in report
        assert report["skillsRoot"] == str(skills_root.resolve())


def test_python_envs_delegation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        write_stub_scan(skills_root, "/stub/python")
        code, report, stderr = run_inventory("--json", "--skills-root", str(skills_root))
        assert code == 0, stderr
        section = report["pythonEnvs"]
        assert section["available"] is True
        assert section["environments"][0]["path"] == "/stub/python"
        assert section["environments"][0]["packages"] == {"playwright": "1.0.0"}
        assert section["recommended"] == "/stub/python"
        assert section["owner"] == "resilient-browser-fetch"


def test_browsers_delegation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        code, report, stderr = run_inventory("--json", "--skills-root", str(skills_root))
        assert code == 0, stderr
        section = report["browsers"]
        assert section["available"] is True
        assert section["candidates"][0]["browser"] == "stub"
        assert section["owner"] == "browser-automation"


def test_missing_siblings_degrade() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp), with_siblings=False)
        code, report, stderr = run_inventory("--json", "--skills-root", str(skills_root), "--probe-proxy")
        assert code == 0, stderr
        assert report["pythonEnvs"]["available"] is False
        assert report["browsers"]["available"] is False
        assert report["proxies"]["probe"]["ran"] is False
        assert "reason" in report["pythonEnvs"]


def test_invalid_skills_root_falls_back() -> None:
    code, report, stderr = run_inventory("--json", "--skills-root", "Z:/definitely-missing-root")
    assert code == 0, stderr
    assert report["runtimes"]["available"] is True


def test_unlocatable_skills_root_degrades() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        isolated = Path(tmp) / "skills" / "resource-inventory" / "scripts"
        isolated.mkdir(parents=True)
        copied = isolated / "inventory.py"
        shutil.copyfile(INVENTORY, copied)
        code, stdout, stderr = run_script(copied, "--json")
        assert code == 0, stderr
        report = json.loads(stdout)
        assert report["skillsRoot"] is None
        assert report["pythonEnvs"]["available"] is False
        assert report["browsers"]["available"] is False
        assert report["runtimes"]["available"] is True


def test_project_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        project = make_project(Path(tmp) / "demo")
        code, report, stderr = run_inventory(
            "--json", "--skills-root", str(skills_root), "--project", str(project)
        )
        assert code == 0, stderr
        section = report["projects"][0]
        assert section["available"] is True
        assert section["packageManager"] == "pnpm"
        assert section["lockfiles"] == ["pnpm-lock.yaml"]
        assert "playwright.config.ts" in section["configFiles"]
        assert sorted(section["packageJson"]["testFrameworks"]) == ["playwright", "vitest"]
        assert section["virtualenvs"] == [".venv"]


def test_project_missing_dir_degrades() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        code, report, stderr = run_inventory(
            "--json", "--skills-root", str(skills_root), "--project", str(Path(tmp) / "nope")
        )
        assert code == 0, stderr
        assert report["projects"][0]["available"] is False
        assert "reason" in report["projects"][0]


def test_probe_proxy_delegation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        code, report, stderr = run_inventory(
            "--json", "--skills-root", str(skills_root), "--probe-proxy", "--probe-budget", "6"
        )
        assert code == 0, stderr
        probe = report["proxies"]["probe"]
        assert probe["ran"] is True and probe["ok"] is True
        assert probe["usable"][0]["port"] == 7897


def test_registry_absent_and_custom() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        missing = Path(tmp) / "no-registry.json"
        code, report, stderr = run_inventory(
            "--json", "--skills-root", str(skills_root), "--registry", str(missing)
        )
        assert code == 0, stderr
        assert report["proxies"]["registry"]["available"] is False

        registry = Path(tmp) / "proxy-resources.json"
        registry.write_text(
            json.dumps(
                {
                    "updated": "2026-01-01",
                    "default": "stub",
                    "proxies": [
                        {
                            "name": "stub",
                            "type": "http",
                            "url": "http://127.0.0.1:1",
                            "source": "registry",
                            "verified": "2026-01-01",
                            "notes": "stub",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        code, report, stderr = run_inventory(
            "--json", "--skills-root", str(skills_root), "--registry", str(registry)
        )
        assert code == 0, stderr
        section = report["proxies"]["registry"]
        assert section["available"] is True
        assert section["entries"][0]["name"] == "stub"
        assert section["updated"] == "2026-01-01"


def test_human_output_lists_sections() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(INVENTORY), "--skills-root", str(skills_root)],
            capture_output=True,
            timeout=180,
            env=child_env(),
            check=False,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace")
        assert proc.returncode == 0
        for heading in ("[运行时]", "[Python 环境与引擎层]", "[浏览器]", "[代理]"):
            assert heading in stdout


def test_help_is_available() -> None:
    proc = subprocess.run(
        [sys.executable, str(INVENTORY), "--help"],
        capture_output=True,
        timeout=60,
        env=child_env(),
        check=False,
    )
    assert proc.returncode == 0
    text = proc.stdout.decode("utf-8", errors="replace")
    assert "用法" in text or "usage" in text


def load_inventory_module() -> Any:
    """把 inventory.py 当模块加载，用于纯函数级断言。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("inventory_under_test", INVENTORY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mask_url_hides_credentials() -> None:
    module = load_inventory_module()
    assert module.mask_url("http://user:pass@127.0.0.1:7897") == "http://***@127.0.0.1:7897"
    assert module.mask_url("http://127.0.0.1:7897") == "http://127.0.0.1:7897"


def test_venv_probe_reports_installed_packages() -> None:
    module = load_inventory_module()
    result = module.probe_venv_packages(Path(sys.executable), 30)
    assert isinstance(result, dict)
    assert set(result) == set(module.VENV_PROBE_PACKAGES)


def test_only_filter() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        code, report, stderr = run_inventory("--json", "--skills-root", str(skills_root), "--only", "proxies")
        assert code == 0, stderr
        assert "proxies" in report
        for absent in ("host", "runtimes", "pythonEnvs", "browsers", "projects"):
            assert absent not in report


def test_proxy_env_is_reported_masked() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        env = {**child_env(), "HTTPS_PROXY": "http://user:secret@127.0.0.1:7897"}
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(INVENTORY), "--json", "--only", "proxies", "--skills-root", str(skills_root)],
            capture_output=True,
            timeout=120,
            env=env,
            check=False,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace")
        assert proc.returncode == 0
        report = json.loads(stdout)
        assert report["proxies"]["env"]["HTTPS_PROXY"] == "http://***@127.0.0.1:7897"
        assert "secret" not in stdout


def test_project_installed_bins() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skills_root = make_skills_root(Path(tmp))
        project = make_project(Path(tmp) / "demo")
        bins = project / "node_modules" / ".bin"
        bins.mkdir(parents=True)
        (bins / "playwright.cmd").write_text("@echo off\n", encoding="utf-8")
        code, report, stderr = run_inventory(
            "--json", "--skills-root", str(skills_root), "--project", str(project)
        )
        assert code == 0, stderr
        installed = report["projects"][0]["installed"]
        assert installed["nodeModulesBins"] == ["playwright"]
        assert "venvPython" not in installed


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
