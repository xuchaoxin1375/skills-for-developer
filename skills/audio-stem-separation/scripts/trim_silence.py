#!/usr/bin/env python3
"""Cut or mute near-silent stretches of an audio file.

Separation stems go quiet wherever the other stem carries the song: a vocal
stem has a silent intro/break/outro, an instrumental stem has silent verses.
`--mode cut` removes those stretches (timeline changes; good for listening),
`--mode mute` keeps the timeline and only zeroes the level (good for mixing).

Usage:
  python trim_silence.py song.mp3 --dry-run
  python trim_silence.py song.mp3 --output song-trim.mp3 --mode cut
  python trim_silence.py song.mp3 --output song-mute.mp3 --mode mute

Requires ffmpeg (and ffprobe for the duration report) on PATH or via --ffmpeg.
Only the Python standard library is used.

Exit codes: 0 = done (also when there is nothing to trim), 1 = runtime error
(ffmpeg missing, decode/encode failed), 2 = bad arguments.
"""
from __future__ import annotations

import argparse
import array
import math
import shutil
import subprocess
import sys
from pathlib import Path

FRAME_SEC = 0.02          # analysis hop
SMOOTH_FRAMES = 5         # ~100 ms smoothing against single transient spikes
FADE_SEC = 0.015          # click guard at every splice point
MIN_DB = -180.0           # floor for digital silence

CODECS = {
    ".mp3": None,           # filled per bitrate below
    ".wav": ["-c:a", "pcm_s16le"],
    ".flac": ["-c:a", "flac"],
    ".m4a": None,
    ".aac": None,
    ".ogg": ["-c:a", "libvorbis", "-q:a", "6"],
}


def die(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def decode(path: Path, ffmpeg: str, rate: int) -> array.array:
    """Decode to mono float32 so RMS is independent of channel layout."""
    cmd = [ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-i", str(path),
           "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "ffmpeg failed")
    samples = array.array("f")
    samples.frombytes(proc.stdout)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def frame_db(samples: array.array, rate: int) -> list[float]:
    hop = max(int(rate * FRAME_SEC), 1)
    count = len(samples) // hop
    out: list[float] = []
    for i in range(count):
        block = samples[i * hop:(i + 1) * hop]
        energy = 0.0
        for v in block:
            energy += v * v
        rms = math.sqrt(energy / hop)
        out.append(20 * math.log10(rms) if rms > 1e-9 else MIN_DB)
    return out


def smooth(values: list[float], width: int) -> list[float]:
    if width <= 1 or not values:
        return list(values)
    half = width // 2
    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + v)
    n = len(values)
    return [ (prefix[min(i + half + 1, n)] - prefix[max(i - half, 0)]) /
             (min(i + half + 1, n) - max(i - half, 0)) for i in range(n) ]


def find_cuts(db: list[float], frame_sec: float, threshold: float, min_silence: float):
    cuts, start = [], None
    for i, value in enumerate(db):
        if value < threshold:
            if start is None:
                start = i
        elif start is not None:
            if (i - start) * frame_sec >= min_silence:
                cuts.append((start * frame_sec, i * frame_sec))
            start = None
    if start is not None and (len(db) - start) * frame_sec >= min_silence:
        cuts.append((start * frame_sec, len(db) * frame_sec))
    return cuts


def keep_segments(cuts, duration: float, pad: float, min_keep: float):
    kept, prev = [], 0.0
    for c0, c1 in cuts:
        if c1 - c0 <= 2 * pad:      # too short to survive the padding
            continue
        head, tail = c0 + pad, c1 - pad
        if head > prev:
            kept.append((prev, head))
        prev = max(prev, tail)
    if prev < duration:
        kept.append((prev, duration))
    return [(s, e) for s, e in kept if e - s >= min_keep]


def build_graph(kept, mode: str, cuts) -> str:
    if mode == "mute":
        chain = ",".join(f"volume=volume=0:enable='between(t,{c0:.3f},{c1:.3f})'" for c0, c1 in cuts)
        return f"[0:a]{chain}[out]"
    parts, labels = [], []
    for i, (start, end) in enumerate(kept):
        seg = f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS"
        if i > 0:
            seg += f",afade=t=in:st=0:d={FADE_SEC}"
        if i < len(kept) - 1:
            seg += f",afade=t=out:st={max(end - start - FADE_SEC, 0):.3f}:d={FADE_SEC}"
        parts.append(f"{seg}[s{i}]")
        labels.append(f"[s{i}]")
    parts.append("".join(labels) + f"concat=n={len(kept)}:v=0:a=1[out]")
    return ";".join(parts)


def encoder_args(suffix: str, bitrate: str):
    suffix = suffix.lower()
    if suffix not in CODECS:
        raise RuntimeError(f"unsupported output format '{suffix}', use one of: {', '.join(CODECS)}")
    fixed = CODECS[suffix]
    if fixed is not None:
        return fixed
    if suffix in (".mp3",):
        return ["-c:a", "libmp3lame", "-b:a", bitrate]
    return ["-c:a", "aac", "-b:a", bitrate]


def probe_duration(path: Path, ffprobe: str | None) -> float | None:
    if not ffprobe:
        return None
    proc = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def fmt(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:06.3f}"


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="trim_silence.py",
        description="Cut (or mute) near-silent stretches of an audio file.",
        epilog="Examples:\n"
               "  python trim_silence.py vocals.mp3 --dry-run\n"
               "  python trim_silence.py vocals.mp3 --output vocals-trim.mp3 --mode cut\n"
               "  python trim_silence.py vocals.mp3 --output vocals-mute.mp3 --mode mute "
               "--threshold-db -45 --pad 0.3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", help="source audio file (any format ffmpeg can decode)")
    p.add_argument("-o", "--output", help="output file; default <input>-trim<ext>, "
                                          "required for --mode mute")
    p.add_argument("-m", "--mode", choices=["cut", "mute"], default="cut",
                   help="cut removes the silent stretches, mute keeps the timeline (default: cut)")
    p.add_argument("--threshold-db", type=float, default=-50.0,
                   help="level below which a frame counts as silence (default: -50)")
    p.add_argument("--min-silence", type=float, default=1.0,
                   help="only handle silent runs at least this long, in seconds (default: 1.0)")
    p.add_argument("--pad", type=float, default=0.2,
                   help="seconds kept on each side of the silence (default: 0.2)")
    p.add_argument("--min-keep", type=float, default=1.0,
                   help="drop kept fragments shorter than this, in seconds (default: 1.0)")
    p.add_argument("--bitrate", default="320k", help="bitrate for lossy output (default: 320k)")
    p.add_argument("--analysis-rate", type=int, default=22050,
                   help="decode rate for the RMS analysis (default: 22050)")
    p.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable (default: ffmpeg)")
    p.add_argument("--dry-run", action="store_true", help="print the segment table only")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress progress messages")
    p.add_argument("-V", "--version", action="version", version="trim_silence.py 2026.11.17")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    src = Path(args.input)
    if not src.is_file():
        return die(f"input not found: {src}")
    if args.pad < 0 or args.min_silence <= 0 or args.min_keep < 0:
        return die("--pad/--min-keep must be >= 0 and --min-silence > 0")
    ffmpeg = shutil.which(args.ffmpeg)
    if not ffmpeg:
        return die(f"ffmpeg not found: {args.ffmpeg} (install ffmpeg or pass --ffmpeg)")

    if args.mode == "mute" and not args.output:
        return die("--mode mute needs --output (the timeline is preserved, so a new file is required)")

    out, codec = None, []
    if not args.dry_run:
        out = Path(args.output) if args.output else src.with_name(f"{src.stem}-trim{src.suffix}")
        if out.resolve() == src.resolve():
            return die("refusing to overwrite the input; pass a different --output")
        try:
            codec = encoder_args(out.suffix, args.bitrate)
        except RuntimeError as exc:
            return die(str(exc))

    note = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))
    note(f"decoding {src.name} ...")
    try:
        samples = decode(src, ffmpeg, args.analysis_rate)
    except RuntimeError as exc:
        return die(f"decode failed: {exc}")
    duration = len(samples) / args.analysis_rate
    if duration <= 0:
        return die("decoded audio is empty")

    db = smooth(frame_db(samples, args.analysis_rate), SMOOTH_FRAMES)
    cuts = find_cuts(db, FRAME_SEC, args.threshold_db, args.min_silence)
    kept = keep_segments(cuts, duration, args.pad, args.min_keep)

    print(f"input      {src.name}  {fmt(duration)}")
    print(f"threshold  {args.threshold_db} dB, min silence {args.min_silence}s, "
          f"pad {args.pad}s, min keep {args.min_keep}s")
    if not cuts:
        print("silent stretches  none -> nothing to trim, no output written")
        return 0
    print(f"silent stretches  {len(cuts)}")
    for c0, c1 in cuts:
        print(f"  {fmt(c0)} -> {fmt(c1)}  ({c1 - c0:5.2f}s)")
    total_cut = sum(c1 - c0 for c0, c1 in cuts)
    print(f"total silent      {total_cut:.2f}s")
    if args.mode == "cut":
        print(f"kept segments     {len(kept)} / {sum(e - s for s, e in kept):.2f}s")
        for s, e in kept:
            print(f"  keep {fmt(s)} -> {fmt(e)}  ({e - s:6.2f}s)")
        if not kept:
            print("every segment fell below --min-keep; lower it or raise --pad")
            return 1

    if args.dry_run:
        return 0

    graph = build_graph(kept, args.mode, cuts)
    cmd = [ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-y", "-i", str(src),
           "-filter_complex", graph, "-map", "[out]", *codec, str(out)]
    note(f"encoding {out.name} ...")
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        return die("encode failed: " + proc.stderr.decode("utf-8", "replace").strip())

    got = probe_duration(out, shutil.which("ffprobe"))
    if got is not None:
        expected = sum(e - s for s, e in kept) if args.mode == "cut" else duration
        delta = abs(got - expected)
        print(f"output     {out}  {fmt(got)}  (expected {fmt(expected)}, delta {delta:.3f}s)")
        if delta > 0.2:
            print("warning: duration differs by more than 0.2s, check the segment table", file=sys.stderr)
    else:
        print(f"output     {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
