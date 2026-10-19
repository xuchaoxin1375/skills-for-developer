from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import check_environment as subject


def test_add_check_preserves_required_flag() -> None:
    checks: list[dict[str, object]] = []
    subject.add_check(checks, "optional", False, "missing", required=False)
    assert checks == [{"name": "optional", "ok": False, "required": False, "detail": "missing"}]


def test_package_version_returns_none_for_unknown_package() -> None:
    assert subject.package_version("package-that-cannot-exist-resilient-fetch-test") is None


def test_chrome_candidates_only_returns_existing_paths() -> None:
    assert all(isinstance(path, Path) and path.exists() for path in subject.chrome_candidates())


def test_executable_version_returns_none_when_command_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(subject.shutil, "which", lambda _name: None)
    assert subject.executable_version("uv") is None


def test_executable_version_reads_stdout(monkeypatch) -> None:
    monkeypatch.setattr(subject.shutil, "which", lambda _name: "/usr/bin/uv")
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, stdout="uv 1.2.3\n", stderr=""),
    )
    assert subject.executable_version("uv") == "uv 1.2.3"


def test_environment_executable_prefers_current_interpreter_directory(
    monkeypatch, tmp_path: Path
) -> None:
    suffix = ".exe" if subject.os.name == "nt" else ""
    interpreter = tmp_path / f"python{suffix}"
    command = tmp_path / f"scrapling{suffix}"
    command.touch()
    monkeypatch.setattr(subject.sys, "executable", str(interpreter))

    assert subject.environment_executable("scrapling") == command


def test_python_environment_detail_identifies_conda(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(subject.sys, "prefix", str(tmp_path))
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path))
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "scrapling")

    detail = subject.python_environment_detail()

    assert "conda:scrapling" in detail


def test_environment_manager_detects_conda_from_prefix_contents(tmp_path: Path) -> None:
    (tmp_path / "conda-meta").mkdir()

    assert subject.environment_manager(tmp_path) == f"conda:{tmp_path.name}"


def test_environment_manager_labels_conda_root_as_base(tmp_path: Path) -> None:
    (tmp_path / "conda-meta").mkdir()
    (tmp_path / "envs").mkdir()

    assert subject.environment_manager(tmp_path) == "conda:base"


def test_environment_manager_distinguishes_uv_venv(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "pyvenv.cfg").write_text("home = /usr/bin\ninclude-system-site-packages = false\n")
    uv = tmp_path / "uv"
    uv.mkdir()
    (uv / "pyvenv.cfg").write_text("home = /usr/bin\nuv = 0.8.4\n")

    assert subject.environment_manager(plain) == "venv"
    assert subject.environment_manager(uv) == "venv(uv)"
    assert subject.environment_manager(tmp_path / "missing") == "system"


def test_python_environment_detail_detects_conda_without_activation(
    monkeypatch, tmp_path: Path
) -> None:
    """直接调用某个环境的 python.exe 时没有 CONDA_PREFIX，也必须认出 conda。"""

    (tmp_path / "conda-meta").mkdir()
    monkeypatch.setattr(subject.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(subject.sys, "base_prefix", str(tmp_path))
    monkeypatch.setattr(subject.sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.delenv("CONDA_PREFIX", raising=False)

    assert "conda:" in subject.python_environment_detail()


def test_interpreter_in_prefers_scripts_then_bin(tmp_path: Path) -> None:
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    windows = scripts / "python.exe"
    windows.touch()
    unix = tmp_path / "bin" / "python"
    unix.parent.mkdir()
    unix.touch()

    # 两者都在时按 Windows 布局优先；只有 POSIX 布局时也要能找到。
    assert subject.interpreter_in(tmp_path) == windows
    assert subject.interpreter_in(tmp_path / "posix") is None
    only_posix = tmp_path / "only-posix"
    only_posix_bin = only_posix / "bin"
    only_posix_bin.mkdir(parents=True)
    (only_posix_bin / "python").touch()

    assert subject.interpreter_in(only_posix) == only_posix_bin / "python"


def test_interpreter_candidates_dedups_and_keeps_sources(monkeypatch, tmp_path: Path) -> None:
    interpreter = tmp_path / "env" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    monkeypatch.setattr(subject.sys, "executable", str(interpreter))
    monkeypatch.setattr(subject.shutil, "which", lambda name: str(interpreter) if name == "python" else None)
    monkeypatch.setattr(subject, "conda_env_prefixes", lambda: [])
    monkeypatch.setattr(subject, "virtualenv_prefixes", lambda: [])
    monkeypatch.setattr(subject, "launcher_pythons", lambda: [])

    candidates = subject.interpreter_candidates()

    assert candidates == [{"path": str(interpreter.resolve()), "source": "current"}]


def test_interpreter_candidates_skips_missing_prefixes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(subject.shutil, "which", lambda _name: None)
    monkeypatch.setattr(subject, "conda_env_prefixes", lambda: [tmp_path / "gone"])
    monkeypatch.setattr(subject, "virtualenv_prefixes", lambda: [])

    assert subject.interpreter_candidates() == [
        {"path": str(Path(subject.sys.executable).resolve()), "source": "current"}
    ]


def test_probe_interpreter_reports_layers_of_the_current_python() -> None:
    scripts = Path(subject.__file__).resolve().parent

    payload = subject.probe_interpreter(subject.sys.executable, scripts)

    assert payload["ok"] is True
    assert payload["version"]
    assert "static" in payload["engines"]


def test_probe_interpreter_reports_failure_without_raising(tmp_path: Path) -> None:
    payload = subject.probe_interpreter(str(tmp_path / "missing-python"), tmp_path)

    assert payload["ok"] is False
    assert "无法运行" in payload["detail"]


def test_scan_environments_ranks_richer_environments_first(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        subject,
        "interpreter_candidates",
        lambda: [
            {"path": str(tmp_path / "plain"), "source": "PATH"},
            {"path": str(tmp_path / "rich"), "source": "conda-envs"},
        ],
    )
    monkeypatch.setattr(
        subject,
        "probe_interpreter",
        lambda path, _scripts: {
            "path": path,
            "ok": True,
            "version": "3.13.0",
            "prefix": path,
            "engines": ["static", "playwright", "scrapling"] if path.endswith("rich") else ["static"],
            "packages": {},
        },
    )

    environments = subject.scan_environments(("scrapling",), tmp_path)

    assert [entry["path"] for entry in environments] == [str(tmp_path / "rich"), str(tmp_path / "plain")]
    assert environments[0]["satisfies"] == []
    assert environments[0]["levels"] == [0, 1, 2]
    assert environments[1]["satisfies"] == ["scrapling"]


def test_format_environment_report_marks_states_and_recommends_commands() -> None:
    environments = [
        {
            "path": "C:/conda/envs/scrapling/python.exe",
            "ok": True,
            "manager": "conda:scrapling",
            "source": "conda-envs",
            "version": "3.13.13",
            "engines": ["static", "scrapling"],
            "levels": [0, 2],
            "packages": {"scrapling": "0.5"},
            "satisfies": [],
        },
        {
            "path": "C:/scoop/python.exe",
            "ok": True,
            "manager": "system",
            "source": "PATH",
            "version": "3.13.15",
            "engines": ["static"],
            "levels": [0],
            "packages": {},
            "satisfies": ["scrapling"],
        },
        {"path": "C:/broken/python.exe", "ok": False, "detail": "退出码 1: boom"},
    ]

    report = "\n".join(subject.format_environment_report(environments, ("scrapling",)))

    assert "[OK] conda:scrapling" in report
    assert "[WARN] system" in report
    assert "[--] 无法探测" in report
    assert "缺: scrapling" in report
    assert "建议解释器(满足 scrapling): C:/conda/envs/scrapling/python.exe" in report
    assert "conda run -n scrapling --no-capture-output" in report


def test_format_environment_report_without_requirements_drops_state_marks() -> None:
    environments = [
        {
            "path": "C:/python.exe",
            "ok": True,
            "manager": "system",
            "source": "PATH",
            "version": "3.13.15",
            "engines": ["static"],
            "levels": [0],
            "packages": {},
            "satisfies": [],
        }
    ]

    report = subject.format_environment_report(environments, ())

    assert report[1].startswith("[  ] ")
    assert "建议解释器" not in "\n".join(report)


def test_format_environment_report_explains_when_nothing_satisfies() -> None:
    environments = [
        {
            "path": "C:/python.exe",
            "ok": True,
            "manager": "system",
            "source": "PATH",
            "version": "3.13.15",
            "engines": ["static"],
            "levels": [0],
            "packages": {},
            "satisfies": ["cloak-cdp"],
        }
    ]

    report = "\n".join(subject.format_environment_report(environments, ("cloak-cdp",)))

    assert "没有解释器同时具备 cloak-cdp" in report

