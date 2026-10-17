"""Read-only discovery of installed Chromium browsers; never launch candidates.

Only inspect a bounded catalog, App Paths and known PATH command names. A native
header is a format check, not a signature, compatibility or trust verification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shutil
import sys
from typing import Iterable, Mapping


@dataclass(frozen=True)
class BrowserCandidate:
    browser: str
    path: str
    source: str
    eligible: bool
    reason: str

    def as_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def native_binary(path: Path, platform: str) -> bool:
    """Exclude launch scripts and common Scoop shims without executing them."""
    if not path.is_file():
        return False
    if path.suffix.lower() in {".cmd", ".bat", ".ps1", ".sh"}:
        return False
    if path.with_suffix(".shim").exists():
        return False
    if path.resolve().name in {"snap", "flatpak", "bwrap", "sh", "bash", "env"}:
        return False
    if platform == "win32" and path.suffix.lower() != ".exe":
        return False
    if platform != "win32" and not os.access(path, os.X_OK):
        return False
    with path.open("rb") as stream:
        header = stream.read(4)
    if platform == "win32":
        return header[:2] == b"MZ"
    if platform.startswith("linux"):
        return header == b"\x7fELF"
    if platform == "darwin":
        return header in {
            b"\xfe\xed\xfa\xce",
            b"\xce\xfa\xed\xfe",
            b"\xfe\xed\xfa\xcf",
            b"\xcf\xfa\xed\xfe",
            b"\xca\xfe\xba\xbe",
            b"\xbe\xba\xfe\xca",
            b"\xca\xfe\xba\xbf",
            b"\xbf\xba\xfe\xca",
        }
    return False


def windows_app_paths() -> list[tuple[str, Path, str]]:
    """Read Chrome/Edge App Paths from both registry views; ignore open commands."""
    if sys.platform != "win32":
        return []
    import winreg

    found: list[tuple[str, Path, str]] = []
    for browser, executable in (("msedge", "msedge.exe"), ("chrome", "chrome.exe")):
        for hive, label in (
            (winreg.HKEY_CURRENT_USER, "HKCU"),
            (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
        ):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                key_path = (
                    rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{executable}"
                )
                try:
                    with winreg.OpenKey(
                        hive, key_path, 0, winreg.KEY_READ | view
                    ) as key:
                        value, kind = winreg.QueryValueEx(key, "")
                    if isinstance(value, str) and kind in (
                        winreg.REG_SZ,
                        winreg.REG_EXPAND_SZ,
                    ):
                        path = Path(os.path.expandvars(value).strip().strip('"'))
                        if path.is_absolute():
                            found.append((browser, path, f"App Paths:{label}"))
                except OSError:
                    continue  # Missing or inaccessible registration is optional.
    return found


def common_locations(
    platform: str, env: Mapping[str, str], home: Path
) -> list[tuple[str, Path, str]]:
    """Build fixed candidates; no drive scan, recursive walk or revision guessing."""
    found: list[tuple[str, Path, str]] = []
    if platform == "win32":
        for variable in (
            "PROGRAMFILES",
            "PROGRAMW6432",
            "PROGRAMFILES(X86)",
            "LOCALAPPDATA",
        ):
            if not env.get(variable):
                continue
            root = Path(env[variable])
            for browser, relative in (
                ("msedge", "Microsoft/Edge/Application/msedge.exe"),
                ("chrome", "Google/Chrome/Application/chrome.exe"),
                ("chromium", "Chromium/Application/chrome.exe"),
            ):
                found.append((browser, root / relative, f"env:{variable}"))
        scoop_roots = [Path(env.get("SCOOP") or home / "scoop")]
        if env.get("SCOOP_GLOBAL"):
            scoop_roots.append(Path(env["SCOOP_GLOBAL"]))
        elif env.get("PROGRAMDATA"):
            scoop_roots.append(Path(env["PROGRAMDATA"]) / "scoop")
        for root in scoop_roots:
            for package, browser, binary in (
                ("microsoft-edge", "msedge", "msedge.exe"),
                ("googlechrome", "chrome", "chrome.exe"),
                ("chrome", "chrome", "chrome.exe"),
                ("chrome-portable", "chrome", "chrome.exe"),
                ("chromium", "chromium", "chrome.exe"),
            ):
                for relative in (
                    binary,
                    f"Application/{binary}",
                    f"App/{binary}",
                    f"App/Chrome-bin/{binary}",
                ):
                    found.append(
                        (
                            browser,
                            root / "apps" / package / "current" / relative,
                            "Scoop:current",
                        )
                    )
    elif platform == "darwin":
        for root in (Path("/Applications"), home / "Applications"):
            for browser, app, executable in (
                ("chrome", "Google Chrome", "Google Chrome"),
                ("msedge", "Microsoft Edge", "Microsoft Edge"),
                ("chromium", "Chromium", "Chromium"),
            ):
                found.append(
                    (
                        browser,
                        root / f"{app}.app/Contents/MacOS/{executable}",
                        "app-bundle",
                    )
                )
    elif platform.startswith("linux"):
        for browser, path in (
            ("chrome", "/opt/google/chrome/chrome"),
            ("msedge", "/opt/microsoft/msedge/msedge"),
            ("chromium", "/usr/lib/chromium/chromium"),
            ("chromium", "/usr/lib64/chromium-browser/chromium-browser"),
            ("chromium", "/usr/lib/chromium-browser/chromium-browser"),
            ("chrome", "/usr/bin/google-chrome"),
            ("chrome", "/usr/bin/google-chrome-stable"),
            ("msedge", "/usr/bin/microsoft-edge"),
            ("chromium", "/usr/bin/chromium"),
            ("chromium", "/usr/bin/chromium-browser"),
            ("chromium", "/snap/bin/chromium"),
        ):
            found.append((browser, Path(path), "system-package"))
    return found


def inspect_candidates(
    locations: Iterable[tuple[str, Path, str]], platform: str
) -> list[BrowserCandidate]:
    """Keep existing files, deduplicate resolved paths, and label wrappers."""
    found: list[BrowserCandidate] = []
    seen: dict[str, int] = {}
    for browser, path, source in locations:
        try:
            if not path.is_absolute() or not path.is_file():
                continue
            # Check sidecars before resolving links: a shim may point elsewhere.
            eligible = native_binary(path, platform)
            resolved = path.resolve(strict=True)
            identity = (
                str(resolved).casefold() if platform == "win32" else str(resolved)
            )
            candidate = BrowserCandidate(
                browser,
                str(resolved),
                source,
                eligible,
                "native-format; launch not verified"
                if eligible
                else "wrapper/shim/non-native; manual setup required",
            )
            if identity in seen:
                index = seen[identity]
                if eligible and not found[index].eligible:
                    found[index] = candidate
                continue
            seen[identity] = len(found)
            found.append(candidate)
        except (OSError, RuntimeError):
            continue  # Optional locations may be unreadable or have broken links.
    return found


def discover_browsers() -> list[BrowserCandidate]:
    """List browsers in predictable preference order; never probe by --version."""
    platform = sys.platform
    locations = windows_app_paths() + common_locations(
        platform, os.environ, Path.home()
    )
    names = (
        (
            ("msedge", "msedge.exe"),
            ("chrome", "chrome.exe"),
            ("chromium", "chromium.exe"),
        )
        if platform == "win32"
        else (
            ("chrome", "google-chrome"),
            ("chrome", "google-chrome-stable"),
            ("msedge", "microsoft-edge"),
            ("msedge", "microsoft-edge-stable"),
            ("chromium", "chromium"),
            ("chromium", "chromium-browser"),
        )
    )
    for browser, name in names:
        path = shutil.which(name)
        if path:
            locations.append((browser, Path(path), "PATH"))
    preference = {
        name: rank
        for rank, name in enumerate(
            ("msedge", "chrome", "chromium")
            if platform == "win32"
            else ("chrome", "msedge", "chromium")
        )
    }
    return sorted(
        inspect_candidates(locations, platform),
        key=lambda item: preference[item.browser],
    )
