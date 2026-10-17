"""Legacy CLI; the maintained implementation lives in browser-automation."""

from pathlib import Path
import runpy
import sys


def main() -> None:
    entry = (
        Path(__file__).resolve().parents[2]
        / "browser-automation/scripts/shot_scroll.py"
    )
    sys.path.insert(0, str(entry.parent))
    runpy.run_path(str(entry), run_name="__main__")


if __name__ == "__main__":
    main()
