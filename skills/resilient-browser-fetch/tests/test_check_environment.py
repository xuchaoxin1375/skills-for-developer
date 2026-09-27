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
