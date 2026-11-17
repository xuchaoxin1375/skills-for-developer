#!/usr/bin/env python3
"""Download Demucs pretrained weights into a local model repo.

demucs 4.x resolves a bag name through HuggingFace first; where HF is not
reachable it retries instead of failing fast, so the run looks frozen. Building
a local repo (bag yaml + checkpoint) lets demucs load with `--repo` fully
offline.

Usage:
  python fetch_model.py --list
  python fetch_model.py --model htdemucs --dir ~/.cache/demucs-models
  demucs --repo ~/.cache/demucs-models -n htdemucs --two-stems=vocals -o out/ song.mp3

Run it with the interpreter that has demucs installed: the available model list
and bag yaml are read from the installed package. Files come from
dl.fbaipublicfiles.com and are verified against the checksum embedded in their
name (sha256 prefix), so a truncated download never reaches demucs.

Exit codes: 0 = repo ready, 1 = runtime error, 2 = bad arguments.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT_URL = "https://dl.fbaipublicfiles.com/demucs/"
SIG_RE = re.compile(r"[0-9a-f]{8}")
CHUNK = 1 << 20


def die(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def remote_dir() -> Path:
    spec = importlib.util.find_spec("demucs")
    if spec is None or spec.submodule_search_locations is None:
        raise RuntimeError("demucs is not importable by this interpreter: "
                           "install it here (`python -m pip install demucs`) or activate the right venv")
    path = Path(list(spec.submodule_search_locations)[0]) / "remote"
    if not (path / "files.txt").is_file():
        raise RuntimeError(f"{path} has no files.txt; is this a demucs install?")
    return path


def parse_files(root: Path) -> dict[str, str]:
    """sig -> relative url path, following the `root:` sections of files.txt."""
    models: dict[str, str] = {}
    prefix = ""
    for line in (root / "files.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("root:"):
            prefix = line.split(":", 1)[1].strip()
            continue
        sig = line.split("-", 1)[0]
        models[sig] = prefix + line
    return models


def available_models(root: Path) -> list[str]:
    return sorted(p.stem for p in root.glob("*.yaml"))


def bag_signatures(root: Path, model: str) -> list[str]:
    bag = root / f"{model}.yaml"
    if not bag.is_file():
        raise RuntimeError(f"unknown model '{model}'; see --list")
    sigs = SIG_RE.findall(bag.read_text(encoding="utf-8"))
    if not sigs:
        raise RuntimeError(f"{bag} lists no model signature")
    return list(dict.fromkeys(sigs))


def download(url: str, dest: Path, checksum: str, force: bool) -> None:
    if dest.is_file() and not force:
        if hashlib.sha256(dest.read_bytes()).hexdigest().startswith(checksum):
            print(f"  reuse {dest.name} (checksum ok)")
            return
        print(f"  checksum mismatch on {dest.name}, downloading again")
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  get   {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, tmp.open("wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                buf = resp.read(CHUNK)
                if not buf:
                    break
                fh.write(buf)
                done += len(buf)
                if total:
                    pct = done * 100 // total
                    if pct % 10 == 0:
                        print(f"        {pct:3d}%  {done / 1e6:6.1f} MB", file=sys.stderr)
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"download failed: {exc}; try --base-url with a mirror") from exc
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    if not digest.startswith(checksum):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch for {dest.name}: expected {checksum}*, got {digest[:8]}")
    tmp.replace(dest)
    print(f"  ok    {dest.name} ({dest.stat().st_size / 1e6:.1f} MB, sha256 {checksum})")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="fetch_model.py",
        description="Download Demucs weights into a local --repo directory (offline load).",
        epilog="Examples:\n"
               "  python fetch_model.py --list\n"
               "  python fetch_model.py --model htdemucs --dir ~/.cache/demucs-models\n"
               "  python fetch_model.py --model htdemucs_ft --dir D:\\models\\demucs --force",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--list", action="store_true", help="list model names, then exit")
    p.add_argument("--model", default="htdemucs",
                   help="bag name from --list, or a bare 8-hex signature (default: htdemucs)")
    p.add_argument("--dir", default="~/.cache/demucs-models",
                   help="target repo directory (default: ~/.cache/demucs-models)")
    p.add_argument("--base-url", default=ROOT_URL,
                   help=f"weight host, override for a mirror (default: {ROOT_URL})")
    p.add_argument("--force", action="store_true", help="re-download even if a valid file exists")
    p.add_argument("-V", "--version", action="version", version="fetch_model.py 2026.11.17")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        root = remote_dir()
    except RuntimeError as exc:
        return die(str(exc))

    if args.list:
        print("\n".join(available_models(root)))
        return 0

    try:
        files = parse_files(root)
        if SIG_RE.fullmatch(args.model):
            sigs = [args.model]
            bag = None
        else:
            sigs = bag_signatures(root, args.model)
            bag = root / f"{args.model}.yaml"
    except RuntimeError as exc:
        return die(str(exc))

    missing = [s for s in sigs if s not in files]
    if missing:
        return die(f"no weight file for signature(s) {', '.join(missing)} in files.txt")

    target = Path(args.dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    print(f"repo   {target}")
    print(f"model  {args.model} -> {', '.join(sigs)}")
    try:
        for sig in sigs:
            rel = files[sig]
            name = rel.rsplit("/", 1)[-1]
            checksum = name.split("-", 1)[1].split(".")[0] if "-" in name else ""
            if not checksum:
                return die(f"cannot read checksum from file name {name}")
            download(args.base_url + rel, target / name, checksum, args.force)
        if bag is not None:
            (target / bag.name).write_text(bag.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  ok    {bag.name}")
    except RuntimeError as exc:
        return die(str(exc))

    print("\nready. next:")
    print(f"  demucs --repo {target} -n {args.model} --two-stems=vocals "
          f"--mp3 --mp3-bitrate 320 -d cpu -o out/ song.mp3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
