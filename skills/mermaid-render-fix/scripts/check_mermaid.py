"""Heuristic pre-check for Mermaid blocks: finds unquoted [ ] inside node text,
raw ';' in sequence diagrams, and non-ASCII quadrantChart labels without quotes.

Usage:
  python check_mermaid.py <markdown-or-mmd-file>

Exit codes: 0 = no suspicious lines, 2 = suspicious lines found.
Does NOT replace real rendering (mmdc/kroki); use it for fast triage only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

NON_ASCII = re.compile(r"[^\x00-\x7f]")
QUADRANT_AXIS = re.compile(r"^(x-axis|y-axis)\s+(.+)$", re.IGNORECASE)
QUADRANT_LABEL = re.compile(r"^quadrant-([1-4])\s+(.+?)\s*$", re.IGNORECASE)
QUADRANT_POINT = re.compile(r"^(.+?):\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]\s*$")


def is_quoted(text: str) -> bool:
    text = text.strip()
    return len(text) >= 2 and text.startswith('"') and text.endswith('"')


def load_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".mmd":
        return [text]
    return re.findall(r"```mermaid\n(.*?)```", text, re.S)


def quadrant_hits(block: str) -> list[str]:
    """quadrantChart: mermaid 10.x-11.x 的词法器要求非 ASCII 文案加引号，坐标须在 0~1。"""
    hits = []
    for i, raw in enumerate(block.splitlines(), start=1):
        line = raw.strip()
        axis = QUADRANT_AXIS.match(line)
        if axis:
            body = axis.group(2)
            if "-->" not in body:
                hits.append(f"line {i}: axis has no '-->': {line[:120]}")
                continue
            if any(NON_ASCII.search(p) and not is_quoted(p) for p in body.split("-->")):
                hits.append(f"line {i}: unquoted non-ASCII axis text: {line[:120]}")
            continue
        label = QUADRANT_LABEL.match(line)
        if label and NON_ASCII.search(label.group(2)) and not is_quoted(label.group(2)):
            hits.append(f"line {i}: unquoted non-ASCII quadrant label: {line[:120]}")
            continue
        point = QUADRANT_POINT.match(line)
        if point:
            name, x, y = point.group(1).strip(), float(point.group(2)), float(point.group(3))
            if NON_ASCII.search(name) and not is_quoted(name):
                hits.append(f"line {i}: unquoted non-ASCII point name: {line[:120]}")
            if not (0 <= x <= 1 and 0 <= y <= 1):
                hits.append(f"line {i}: coordinate outside 0~1: {line[:120]}")
    return hits


def check_block(block: str) -> list[str]:
    hits = []
    lines = block.splitlines()
    head = next((ln.strip() for ln in lines if ln.strip()), "")
    for i, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        # Node like X[...] / X{...} whose text opens without a quote
        # but contains a second [ inside -> parser will break.
        m = re.search(r"\w+([\[{])([^\"'\]]*)", line)
        if m and not line[line.index(m.group(1)) + 1 :].lstrip().startswith('"'):
            rest = line.split(m.group(1), 1)[1]
            inner = rest[1:] if rest.startswith('"') else rest
            if "[" in inner.split("]", 1)[0]:
                hits.append(f"line {i}: unquoted '[' in node text: {raw.strip()[:120]}")
        # Semicolon inside sequenceDiagram must be #59;
        if line.startswith("sequenceDiagram") or "->>" in line or "-->>" in line:
            if ";" in line and "#59;" not in line:
                hits.append(f"line {i}: raw ';' in sequence diagram: {raw.strip()[:120]}")
    if head.lower().startswith("quadrantchart"):
        hits.extend(quadrant_hits(block))
    return hits


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python check_mermaid.py <file.md|file.mmd>")
        return 1
    path = Path(sys.argv[1])
    blocks = load_blocks(path)
    if not blocks:
        print("NO_MERMAID_BLOCKS")
        return 1
    failed = False
    for bi, block in enumerate(blocks):
        hits = check_block(block)
        status = "SUSPICIOUS" if hits else "OK"
        print(f"BLOCK {bi}: {status} ({len(block.splitlines())} lines)")
        for h in hits:
            print("  " + h)
            failed = True
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
