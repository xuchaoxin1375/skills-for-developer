#!/usr/bin/env python3
"""Find wide/decorrelated stretches in a stereo vocal stem.

Backing vocals and vocalise often sit wide in the stereo field while the lead
is centered. This tool prints low-correlation runs as candidates for listening;
it does not prove a run is backing vocals.

Usage:
  python scan_vocal_layers.py vocals.flac
  python scan_vocal_layers.py vocals.flac --threshold-corr 0.4 --min-duration 2
  python scan_vocal_layers.py vocals.flac --hop 0.25 --floor-db -55

Requires ffmpeg on PATH or via --ffmpeg. Only the Python standard library is used.

Exit codes: 0 = done (also when there are no candidates), 1 = runtime error
(ffmpeg missing, decode failed), 2 = bad arguments.
"""
from __future__ import annotations

import argparse
import array
import math
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_RATE = 8000
DEFAULT_HOP = 0.5
DEFAULT_THRESHOLD = 0.5
DEFAULT_MIN_DURATION = 1.0
DEFAULT_FLOOR_DB = -60.0
MIN_DB = -180.0


def die(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def bad_arg(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 2


def decode_stereo(path: Path, ffmpeg: str, rate: int) -> tuple[array.array, array.array]:
    """Decode to interleaved float32, then split into left and right channels."""
    cmd = [ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-i", str(path),
           "-ac", "2", "-ar", str(rate), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "ffmpeg failed")
    samples = array.array("f")
    samples.frombytes(proc.stdout)
    if sys.byteorder == "big":
        samples.byteswap()
    if len(samples) % 2:
        samples = samples[:-1]
    return samples[0::2], samples[1::2]


def db(value: float) -> float:
    return 20 * math.log10(value) if value > 1e-9 else MIN_DB


def frame_rows(left: array.array, right: array.array, hop: int) -> list[dict[str, float]]:
    """Per-hop RMS, L/R correlation, and side-to-mid ratio."""
    rows: list[dict[str, float]] = []
    count = min(len(left), len(right)) // hop
    for i in range(count):
        block_l = left[i * hop:(i + 1) * hop]
        block_r = right[i * hop:(i + 1) * hop]
        dot = ll = rr = mid_energy = side_energy = 0.0
        for a, b in zip(block_l, block_r):
            dot += a * b
            ll += a * a
            rr += b * b
            mid_energy += ((a + b) * 0.5) ** 2
            side_energy += ((a - b) * 0.5) ** 2
        den = math.sqrt(ll * rr)
        corr = dot / den if den > 1e-12 else 0.0
        mid_db = db(math.sqrt(mid_energy / hop))
        side_db = db(math.sqrt(side_energy / hop))
        rows.append({
            "corr": corr,
            "mid_db": mid_db,
            "side_mid_db": side_db - mid_db if mid_db > MIN_DB else MIN_DB,
        })
    return rows


def find_runs(
    rows: list[dict[str, float]],
    hop_sec: float,
    threshold_corr: float,
    floor_db: float,
    min_duration: float,
) -> list[dict[str, float]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, row in enumerate(rows):
        flagged = row["corr"] < threshold_corr and row["mid_db"] > floor_db
        if flagged and start is None:
            start = i
        elif not flagged and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(rows)))

    out: list[dict[str, float]] = []
    for first, last in runs:
        duration = (last - first) * hop_sec
        if duration < min_duration:
            continue
        chunk = rows[first:last]
        out.append({
            "start": first * hop_sec,
            "end": last * hop_sec,
            "duration": duration,
            "corr": sum(r["corr"] for r in chunk) / len(chunk),
            "side_mid_db": sum(r["side_mid_db"] for r in chunk) / len(chunk),
            "mid_db": sum(r["mid_db"] for r in chunk) / len(chunk),
        })
    return out


def fmt(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scan_vocal_layers.py",
        description="Find wide/decorrelated stretches that may be backing vocals or vocalise.",
        epilog="Examples:\n"
               "  python scan_vocal_layers.py vocals.flac\n"
               "  python scan_vocal_layers.py vocals.flac --threshold-corr 0.4 --min-duration 2\n"
               "  python scan_vocal_layers.py vocals.flac --hop 0.25 --floor-db -55",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="stereo vocal stem (any format ffmpeg can decode)")
    parser.add_argument("--threshold-corr", type=float, default=DEFAULT_THRESHOLD,
                        help=f"flag frames with L/R correlation below this (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--min-duration", type=float, default=DEFAULT_MIN_DURATION,
                        help=f"only report runs at least this long, in seconds (default: {DEFAULT_MIN_DURATION})")
    parser.add_argument("--hop", type=float, default=DEFAULT_HOP,
                        help=f"analysis hop in seconds (default: {DEFAULT_HOP})")
    parser.add_argument("--analysis-rate", type=int, default=DEFAULT_RATE,
                        help=f"decode rate for analysis (default: {DEFAULT_RATE})")
    parser.add_argument("--floor-db", type=float, default=DEFAULT_FLOOR_DB,
                        help=f"ignore frames below this mid RMS (default: {DEFAULT_FLOOR_DB})")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable (default: ffmpeg)")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress messages")
    parser.add_argument("-V", "--version", action="version", version="scan_vocal_layers.py 2026.11.18")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    src = Path(args.input)
    if not src.is_file():
        return bad_arg(f"input not found: {src}")
    if not -1.0 <= args.threshold_corr <= 1.0:
        return bad_arg("--threshold-corr must be between -1 and 1")
    if args.min_duration <= 0:
        return bad_arg("--min-duration must be > 0")
    if args.hop <= 0:
        return bad_arg("--hop must be > 0")
    if args.analysis_rate < 1000:
        return bad_arg("--analysis-rate must be >= 1000")
    if args.floor_db > 0:
        return bad_arg("--floor-db must be <= 0")

    ffmpeg = shutil.which(args.ffmpeg)
    if not ffmpeg:
        return die(f"ffmpeg not found: {args.ffmpeg} (install ffmpeg or pass --ffmpeg)")

    note = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))
    note(f"decoding {src.name} ...")
    try:
        left, right = decode_stereo(src, ffmpeg, args.analysis_rate)
    except RuntimeError as exc:
        return die(f"decode failed: {exc}")
    if not left:
        return die("decoded audio is empty")

    hop = max(int(round(args.hop * args.analysis_rate)), 1)
    hop_sec = hop / args.analysis_rate
    rows = frame_rows(left, right, hop)
    duration = len(left) / args.analysis_rate
    runs = find_runs(rows, hop_sec, args.threshold_corr, args.floor_db, args.min_duration)

    print(f"input       {src.name}  {fmt(duration)}")
    print(f"settings    hop {hop_sec:g}s, corr < {args.threshold_corr:g}, "
          f"floor {args.floor_db:g} dB, min duration {args.min_duration:g}s")
    if not runs:
        print("candidates  none")
        return 0

    print(f"candidates  {len(runs)}")
    for run in runs:
        print(f"  {fmt(run['start'])} -> {fmt(run['end'])}  "
              f"({run['duration']:5.1f}s)  corr {run['corr']:5.2f}  "
              f"side/mid {run['side_mid_db']:5.1f} dB  mid {run['mid_db']:5.1f} dB")
    print("note: low correlation is a candidate, not proof; confirm lead presence and boundaries by listening.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
