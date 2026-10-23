#!/usr/bin/env python3
"""render_mmd.py - render one Mermaid file (or the blocks of a markdown file) with mermaid-cli.

Cross-platform on purpose: Windows, Linux and macOS, standard library only, so the
mermaid-render-fix loop keeps working on machines without PowerShell.

Typical use:
    python -X utf8 render_mmd.py -i block.mmd
    python -X utf8 render_mmd.py -i block.mmd -o block.svg -s 1200
    python -X utf8 render_mmd.py -i block.mmd -c

Run `--help` for options, exit codes and common symptoms.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOG = logging.getLogger("render_mmd")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_SUSPICIOUS = 2
EXIT_NO_RENDERER = 3
EXIT_RENDER_FAILED = 4
EXIT_NO_BROWSER = 5

EXIT_CODES = {
    EXIT_OK: "render succeeded",
    EXIT_USAGE: "usage or input error",
    EXIT_SUSPICIOUS: "precheck reported SUSPICIOUS (only with -c)",
    EXIT_NO_RENDERER: "no renderer available (no mmdc / pnpm / npx)",
    EXIT_RENDER_FAILED: "render failed or the output file is missing/empty",
    EXIT_NO_BROWSER: "no browser found and no -p puppeteer config given",
}

MIN_PYTHON = (3, 9)
PATH_ENV_VARS = ("PUPPETEER_EXECUTABLE_PATH", "CHROME_PATH")


def setup_logging() -> None:
    """KEY=VALUE lines to stdout, diagnostics to stderr."""

    class MaxLevelFilter(logging.Filter):
        def __init__(self, max_level: int) -> None:
            super().__init__()
            self.max_level = max_level

        def filter(self, record: logging.LogRecord) -> bool:
            return record.levelno <= self.max_level

    LOG.setLevel(logging.INFO)
    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(logging.Formatter("%(message)s"))
    out.setLevel(logging.INFO)
    out.addFilter(MaxLevelFilter(logging.INFO))
    err = logging.StreamHandler(sys.stderr)
    err.setFormatter(logging.Formatter("render_mmd: %(message)s"))
    err.setLevel(logging.WARNING)
    LOG.addHandler(out)
    LOG.addHandler(err)
    # Console display only: an echoed precheck line may carry non-ASCII text that
    # the local code page cannot encode. Files are always read/written as UTF-8.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def build_epilog() -> str:
    codes = "\n".join(f"  {code}  {text}" for code, text in EXIT_CODES.items())
    return f"""environment:
  PUPPETEER_SKIP_DOWNLOAD is forced on: a local browser is reused instead of
  downloading Chromium. Set -b/--browser or -p/--puppeteer-config to override
  the detected browser path.

exit codes:
{codes}

examples:
  python -X utf8 render_mmd.py -i block.mmd
  python -X utf8 render_mmd.py -i block.mmd -o block.svg -s 1200
  python -X utf8 render_mmd.py -i block.mmd -c
  python -X utf8 render_mmd.py -i doc.md -o out.md

common symptoms:
  no browser found        pass -b <path> or -p <config>; Playwright Chromium counts
  no output produced      parser error or mermaid-cli flags; read stderr above
  RENDERER_EXIT=0 but     mermaid-cli can exit 0 on a parse error - the artefact
    RENDER=FAILED         check, not the exit code, is the gate
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="render_mmd.py",
        description="Render one Mermaid file (or the mermaid blocks of a markdown file).",
        epilog=build_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input", required=True, dest="input_file",
        help=".mmd file, or .md file whose mermaid blocks get rendered",
    )
    parser.add_argument(
        "-o", "--output", default="", dest="output_file",
        help="output path, format follows the extension (.png/.svg/.pdf); "
             "default for .mmd input: <input>.png",
    )
    parser.add_argument(
        "-s", "--size", type=int, default=0,
        help="max width/height in px for png, max-width for svg (mermaid-cli --size)",
    )
    parser.add_argument("-t", "--theme", default="", help="mermaid theme name")
    parser.add_argument(
        "-b", "--browser", default="", dest="browser",
        help="explicit Chrome/Edge/Chromium executable; skips auto-detection",
    )
    parser.add_argument(
        "-p", "--puppeteer-config", default="", dest="puppeteer_config",
        help="existing puppeteer config JSON; skips browser detection",
    )
    parser.add_argument(
        "-c", "--check-only", action="store_true",
        help="run the heuristic precheck only, no rendering",
    )
    parser.add_argument(
        "-k", "--keep-temp", action="store_true",
        help="keep the generated puppeteer config for debugging",
    )
    return parser.parse_args(argv)


def natural_key(path: Path) -> tuple:
    """Sort chromium-1243 above chromium-999."""
    for part in path.parts:
        match = re.fullmatch(r"chromium-(\d+)", part)
        if match:
            return (int(match.group(1)), str(path))
    return (0, str(path))


def windows_candidates() -> list[Path]:
    bases = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    rels = [
        r"Google\Chrome\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
        r"BraveSoftware\Brave-Browser\Application\brave.exe",
        r"Chromium\Application\chrome.exe",
    ]
    found = []
    for base in bases:
        if not base:
            continue
        for rel in rels:
            found.append(Path(base) / rel)
    playwright = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    found.extend(sorted(playwright.glob("chromium-*/chrome-win*/chrome.exe"), key=natural_key, reverse=True))
    return found


def linux_candidates() -> list[Path]:
    found = [
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/snap/bin/chromium"),
        Path("/opt/google/chrome/chrome"),
        Path("/usr/bin/microsoft-edge"),
        Path("/usr/bin/microsoft-edge-stable"),
    ]
    playwright = Path.home() / ".cache" / "ms-playwright"
    found.extend(sorted(playwright.glob("chromium-*/chrome-linux*/chrome"), key=natural_key, reverse=True))
    return found


def macos_candidates() -> list[Path]:
    apps = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
    ]
    playwright = Path.home() / "Library" / "Caches" / "ms-playwright"
    apps.extend(
        sorted(
            playwright.glob("chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"),
            key=natural_key,
            reverse=True,
        )
    )
    return apps


def find_browser() -> Path | None:
    for var in PATH_ENV_VARS:
        value = os.environ.get(var)
        if value and Path(value).is_file():
            return Path(value)
    if sys.platform.startswith("win"):
        candidates = windows_candidates()
    elif sys.platform == "darwin":
        candidates = macos_candidates()
    else:
        candidates = linux_candidates()
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def pnpm_major(exe: str) -> int:
    try:
        proc = subprocess.run(
            [exe, "--version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    first = (proc.stdout or "").strip().split(".")[0]
    return int(first) if first.isdigit() else 0


def resolve_renderer() -> tuple[str, list[str]] | None:
    mmdc = shutil.which("mmdc")
    if mmdc:
        return ("mmdc", [mmdc])
    pnpm = shutil.which("pnpm")
    if pnpm:
        cmd = [pnpm, "dlx"]
        if pnpm_major(pnpm) >= 10:
            # pnpm 10+ blocks dependency build scripts unless allowed.
            cmd.append("--allow-build=puppeteer")
        cmd += ["--package", "@mermaid-js/mermaid-cli", "mmdc"]
        return ("pnpm-dlx", cmd)
    npx = shutil.which("npx")
    if npx:
        return ("npx", [npx, "-y", "-p", "@mermaid-js/mermaid-cli", "mmdc"])
    return None


def write_puppeteer_config(browser: Path, directory: Path) -> Path:
    payload: dict[str, object] = {"executablePath": str(browser)}
    if not sys.platform.startswith("win"):
        payload["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
    path = directory / "puppeteer.json"
    # mermaid-cli feeds this file straight to JSON.parse: no BOM, real UTF-8.
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def run_precheck(path: Path) -> tuple[int, str]:
    checker = Path(__file__).resolve().parent / "check_mermaid.py"
    if not checker.is_file():
        LOG.warning("precheck script not found: %s", checker)
        return (-1, "")
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(checker), str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError as exc:
        LOG.warning("precheck failed to start: %s", exc)
        return (-1, "")
    return (proc.returncode, proc.stdout or "")


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    if sys.version_info < MIN_PYTHON:
        LOG.error(
            "Python %s+ required, found %s",
            ".".join(map(str, MIN_PYTHON)), sys.version.split()[0],
        )
        return EXIT_USAGE
    args = parse_args(argv)

    input_path = Path(args.input_file)
    if not input_path.is_file():
        LOG.error("input not found: %s", input_path)
        return EXIT_USAGE
    input_path = input_path.resolve()
    is_markdown = input_path.suffix.lower() in {".md", ".markdown"}
    LOG.info("INPUT=%s", input_path)

    code, report = run_precheck(input_path)
    for line in report.splitlines():
        LOG.info("%s", line)
    if "NO_MERMAID_BLOCKS" in report:
        LOG.error("no mermaid blocks found in %s", input_path.name)
        return EXIT_USAGE
    # The precheck is heuristic; any other failure (old interpreter, broken
    # module) must not stop a render that may still succeed.
    if code not in (0, 2, -1):
        LOG.warning("precheck exited %s; continuing, rendering is authoritative", code)

    if args.check_only:
        if "SUSPICIOUS" in report:
            return EXIT_SUSPICIOUS
        LOG.info("CHECK=OK")
        return EXIT_OK

    if args.output_file:
        output_path = Path(args.output_file)
    elif is_markdown:
        LOG.error("markdown input needs an explicit -o/--output (e.g. -o out.md)")
        return EXIT_USAGE
    else:
        output_path = input_path.with_suffix(".png")

    renderer = resolve_renderer()
    if renderer is None:
        LOG.error("no renderer found: install mmdc, or make pnpm/npx available")
        return EXIT_NO_RENDERER
    renderer_name, command = renderer
    LOG.info("RENDERER=%s", renderer_name)

    temp_dir: Path | None = None
    try:
        if args.puppeteer_config:
            config_path = Path(args.puppeteer_config)
            if not config_path.is_file():
                LOG.error("puppeteer config not found: %s", config_path)
                return EXIT_USAGE
        else:
            browser = Path(args.browser) if args.browser else find_browser()
            if browser is None:
                LOG.error("no browser found; pass -b/--browser or -p/--puppeteer-config")
                return EXIT_NO_BROWSER
            if not browser.is_file():
                LOG.error("browser not found: %s", browser)
                return EXIT_NO_BROWSER
            temp_dir = Path(tempfile.mkdtemp(prefix="render_mmd_"))
            config_path = write_puppeteer_config(browser, temp_dir)
            LOG.info("BROWSER=%s", browser)

        command += ["-p", str(config_path), "-i", str(input_path), "-o", str(output_path)]
        if args.size > 0:
            command += ["--size", str(args.size)]
        if args.theme:
            command += ["--theme", args.theme]

        # The output is a derived artefact: clearing it first makes the
        # existence check a real signal instead of a stale file.
        if output_path.exists():
            output_path.unlink()

        env = os.environ.copy()
        env["PUPPETEER_SKIP_DOWNLOAD"] = "1"
        started = time.perf_counter()
        proc = subprocess.run(command, env=env)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        LOG.info("ELAPSED_MS=%d", elapsed_ms)
        LOG.info("RENDERER_EXIT=%s", proc.returncode)

        if proc.returncode != 0:
            LOG.info("RENDER=FAILED")
            LOG.error("renderer exited with %s", proc.returncode)
            return EXIT_RENDER_FAILED
        if not output_path.exists() or output_path.stat().st_size == 0:
            LOG.info("RENDER=FAILED")
            LOG.error(
                "no output produced: %s (exit was 0; see stderr for the parser error)",
                output_path,
            )
            return EXIT_RENDER_FAILED

        LOG.info("RENDER=OK")
        LOG.info("OUTPUT=%s", output_path.resolve())
        LOG.info("BYTES=%d", output_path.stat().st_size)
        if temp_dir is not None and args.keep_temp:
            LOG.info("PUPPETEER_CONFIG=%s", config_path)
        return EXIT_OK
    finally:
        if temp_dir is not None and not args.keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
