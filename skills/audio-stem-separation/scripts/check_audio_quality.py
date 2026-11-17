#!/usr/bin/env python3
"""Measure a track's real bandwidth, loudness and lossy-codec ceiling.

A declared bitrate says nothing about what the audio actually holds: a 128 kbps
MP3 re-saved as FLAC, or upsampled into a 320 kbps MP3, keeps its 13-17 kHz
ceiling. This script decodes the file, averages the spectrum, and reports where
the content stops, how steep that stop is, the level above it, plus EBU R128
loudness and true peak. Use it before separation to decide whether a heavy
model (htdemucs_ft, BS-RoFormer) can buy anything.

Usage:
  python check_audio_quality.py song.flac
  python check_audio_quality.py a.flac b.mp3 --seconds 120
  python check_audio_quality.py a.flac --compare b.mp3
  python check_audio_quality.py a.flac --json

Requires ffmpeg/ffprobe on PATH and numpy (the demucs environment has it).
--compare needs no extra dependency: it decodes both files to 8 kHz mono and
cross-correlates the 100 ms energy envelope, so you can tell "same master,
different encode" from "different performance".

Exit codes: 0 = measured, 1 = runtime error, 2 = bad arguments.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

np = None  # imported lazily so --help works on a bare interpreter


def ensure_numpy():
    """The demucs environment already has numpy; a stock python3 may not."""
    global np
    if np is None:
        try:
            import numpy as _np
        except ImportError:
            sys.exit("error: numpy not found — run it with the demucs interpreter, "
                     "or `python -m pip install numpy`")
        np = _np
    return np

SR = 44100
NFFT = 8192
WALL_SPAN = 500         # Hz over which a codec wall must collapse the level
WALL_HARD = 40.0        # dB per WALL_SPAN: a codec wall
WALL_SOFT = 25.0        # dB per WALL_SPAN: steep enough to be ambiguous
ENV_RATE = 8000
ENV_STEP = 0.1          # seconds per envelope frame for --compare

BANDS = [(0, 1000), (1000, 4000), (4000, 8000), (8000, 12000), (12000, 14000),
         (14000, 16000), (16000, 17000), (17000, 18000), (18000, 19000),
         (19000, 20000), (20000, 21000), (21000, 22050)]


def die(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def probe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,sample_rate,channels,bit_rate:format=duration,bit_rate",
         "-select_streams", "a:0", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    stream = (j.get("streams") or [{}])[0]
    fmt = j.get("format") or {}
    return {
        "codec": stream.get("codec_name", "?"),
        "sample_rate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "bit_rate": int(stream.get("bit_rate") or fmt.get("bit_rate") or 0),
        "duration": float(fmt.get("duration") or 0.0),
    }


def decode(path: str, rate: int = SR, seconds: float | None = None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error"]
    if seconds:
        cmd += ["-t", f"{seconds}"]
    cmd += ["-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4")


def avg_spectrum(x: np.ndarray) -> np.ndarray:
    win = np.hanning(NFFT).astype(np.float32)
    n = (len(x) - NFFT) // (NFFT // 2)
    if n < 1:
        raise ValueError("audio shorter than one analysis window")
    acc = np.zeros(NFFT // 2 + 1)
    for i in range(n):
        seg = x[i * NFFT // 2: i * NFFT // 2 + NFFT] * win
        acc += np.abs(np.fft.rfft(seg)) ** 2
    return acc / n


def band_db(psd: np.ndarray, lo: float, hi: float) -> float:
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    m = (f >= lo) & (f < hi)
    if not m.any():
        return -200.0
    return float(10 * np.log10(psd[m].mean() + 1e-30))


def measure(path: str, seconds: float | None) -> dict:
    ensure_numpy()
    info = probe(path)
    psd = avg_spectrum(decode(path, SR, seconds))
    ref = band_db(psd, 1000, 4000)
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    db = 10 * np.log10(psd + 1e-30)

    # smooth ~200 Hz, then locate the steepest sustained drop: that is where an
    # encoder low-pass sits. A master roll-off falls far more gently.
    k = max(1, int(200 / (SR / NFFT)))
    sm = np.convolve(db, np.ones(k) / k, mode="same")
    span = int(round(WALL_SPAN / (SR / NFFT)))
    nyq = SR / 2
    cand = np.where((freqs >= 6000) & (freqs + WALL_SPAN < nyq))[0]
    drop = np.array([sm[i] - sm[i + span] for i in cand])
    best = int(np.argmax(drop)) if len(cand) else 0
    wall = float(freqs[cand[best]]) if len(cand) else 0.0
    wall_drop = float(drop[best]) if len(cand) else 0.0
    floor = band_db(psd, wall + WALL_SPAN, nyq) - ref if wall else -200.0

    return {
        "file": path,
        **info,
        "wall_hz": int(round(wall, -1)),
        "wall_drop_db": round(wall_drop, 1),
        "floor_above_wall_db": round(floor, 1),
        "bands_db": {f"{lo//1000}-{hi//1000}k": round(band_db(psd, lo, hi) - ref, 1)
                     for lo, hi in BANDS},
    }


def loudness(path: str) -> dict:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, check=True).stderr
    tail = out[-4000:]
    i = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", tail)
    p = re.search(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", tail)
    return {"lufs": float(i.group(1)) if i else None,
            "true_peak_dbfs": float(p.group(1)) if p else None}


def verdict(r: dict) -> tuple[str, str]:
    """Short label + what it usually means."""
    wall, drop, floor = r["wall_hz"], r["wall_drop_db"], r["floor_above_wall_db"]
    if drop < WALL_SOFT:
        return "no wall", ("no codec cliff; a gentle roll-off near 21 kHz is the master, "
                           "not the encoder")
    silent = ", digital silence above" if floor < -70 else ", content above it"
    if drop < WALL_HARD:
        return "steep roll-off", (f"{wall/1000:.1f} kHz falls {drop:.0f} dB within "
                                  f"{WALL_SPAN} Hz{silent}; a 20 kHz master low-pass and a "
                                  "high-bitrate codec look the same, so compare another copy")
    if wall < 15000:
        return "narrow", f"low-bitrate lossy (~96-128k){silent}"
    if wall < 17500:
        return "128-160k", f"typical 128-160k ceiling at {wall/1000:.1f} kHz{silent}"
    if wall < 19500:
        return "192k", f"typical 192k ceiling at {wall/1000:.1f} kHz{silent}"
    if wall < 21000:
        return "320k/AAC", f"codec wall at {wall/1000:.1f} kHz{silent}"
    return "high-bitrate", f"ceiling at {wall/1000:.1f} kHz — high-bitrate lossy{silent}"


def envelope(x: np.ndarray, rate: int) -> np.ndarray:
    w = int(rate * ENV_STEP)
    n = len(x) // w
    return np.sqrt((x[:n * w].reshape(n, w) ** 2).mean(1))


def compare(a: str, b: str) -> dict:
    ensure_numpy()
    ea = envelope(decode(a, ENV_RATE), ENV_RATE)
    eb = envelope(decode(b, ENV_RATE), ENV_RATE)
    if len(ea) < 50 or len(eb) < 50:
        return {"error": "too short to compare"}
    span = int(5 / ENV_STEP)
    best = (-2.0, 0)
    step = int(30 / ENV_STEP)
    for start in range(0, min(len(ea), len(eb)) - step, step):
        seg = ea[start:start + step]
        for lag in range(-span, span + 1):
            if 0 <= start + lag and start + lag + step <= len(eb):
                r = float(np.corrcoef(seg, eb[start + lag:start + lag + step])[0, 1])
                if r > best[0]:
                    best = (r, lag)
    return {"offset_s": round(best[1] * ENV_STEP, 2), "correlation": round(best[0], 3),
            "same_master": best[0] >= 0.95}


def main() -> int:
    ap = argparse.ArgumentParser(description="Report real bandwidth, loudness and codec ceiling.")
    ap.add_argument("files", nargs="+", help="audio file(s) to measure")
    ap.add_argument("--seconds", type=float, default=None, help="analyse only the first N seconds")
    ap.add_argument("--compare", metavar="REF", default=None,
                    help="cross-correlate the first file against REF (same master?)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            return die(f"{tool} not found on PATH")
    missing = [p for p in args.files if not os.path.isfile(p)]
    if missing:
        return die("file not found: " + ", ".join(missing))

    rows = []
    try:
        for path in args.files:
            row = measure(path, args.seconds)
            row.update(loudness(path))
            row["verdict"], row["verdict_note"] = verdict(row)
            rows.append(row)
    except subprocess.CalledProcessError as exc:
        err = exc.stderr or b""
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        last = err.strip().splitlines()
        return die(last[-1] if last else f"ffmpeg failed on {exc.cmd[-1]}")

    cmp = None
    if args.compare:
        try:
            cmp = compare(args.files[0], args.compare)
        except subprocess.CalledProcessError:
            return die("--compare could not decode one of the files")

    if args.json:
        print(json.dumps({"files": rows, "compare": cmp}, ensure_ascii=False, indent=1))
        return 0

    for r in rows:
        mb = r["bit_rate"] / 1000 if r["bit_rate"] else 0
        print(f"\n{r['file']}")
        print(f"  declared   {r['codec']} {r['sample_rate']} Hz {r['channels']} ch "
              f"{mb:.0f} kbps {int(r['duration'] // 60)}:{r['duration'] % 60:04.1f}")
        if r["wall_drop_db"] < WALL_SOFT:
            print(f"  ceiling    none up to 21 kHz (steepest {WALL_SPAN} Hz drop "
                  f"{r['wall_drop_db']} dB at {r['wall_hz'] / 1000:.1f} kHz)")
        else:
            print(f"  ceiling    {r['wall_hz'] / 1000:.1f} kHz "
                  f"(drops {r['wall_drop_db']} dB within {WALL_SPAN} Hz, "
                  f"floor {r['floor_above_wall_db']} dB above)")
        print(f"  loudness   {r['lufs']} LUFS, true peak {r['true_peak_dbfs']} dBFS")
        print("  bands      " + "  ".join(f"{k}:{v:+.0f}" for k, v in r["bands_db"].items()))
        print(f"  verdict    {r['verdict']} — {r['verdict_note']}")
    if cmp:
        if "error" in cmp:
            print(f"\ncompare    {cmp['error']}")
        else:
            same = "same master" if cmp["same_master"] else "different performance or edit"
            print(f"\ncompare    offset {cmp['offset_s']:+.2f}s, r={cmp['correlation']} — {same}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
