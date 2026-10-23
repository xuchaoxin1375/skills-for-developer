"""Heuristic pre-check for Mermaid blocks: finds unquoted [ ] inside node text.

Usage:
  python check_mermaid.py <markdown-or-mmd-file>

Exit codes: 0 = no suspicious lines, 2 = suspicious lines found.
Does NOT replace real rendering (mmdc/kroki); use it for fast triage only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def load_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".mmd":
        return [text]
    return re.findall(r"```mermaid\n(.*?)```", text, re.S)


def check_block(block: str) -> list[str]:
    hits = []
    for i, raw in enumerate(block.splitlines(), start=1):
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
