"""frontend-design低级违例的轻量静态扫描。只读，退出码恒0并打印报告。

命中项及含义：
- hex-literal-in-component：组件里写了颜色字面量，应改用语义令牌
- div-onclick：div加onClick当按钮，应改用<button>
- bare-outline-none：outline:none且无:focus-visible替代，键盘用户会丢位置
- window-alert：window.alert/confirm，应改自定义<dialog>
- user-scalable-no：禁用浏览器缩放，违反WCAG 1.4.4
"""
import re
import sys
from pathlib import Path

PATTERNS = [
    ("hex-literal-in-component", re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")),
    ("div-onclick", re.compile(r"<div[^>]*onClick", re.IGNORECASE)),
    ("bare-outline-none", re.compile(r"outline\s*:\s*['\"]?none", re.IGNORECASE)),
    ("window-alert", re.compile(r"window\.(alert|confirm)\s*\(")),
    ("user-scalable-no", re.compile(r"user-scalable\s*=\s*no", re.IGNORECASE)),
]

TARGET_SUFFIXES = {".tsx", ".jsx", ".ts", ".js", ".vue", ".css", ".scss", ".html"}


def scan(root: Path) -> int:
    hits = 0
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix in TARGET_SUFFIXES]
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in PATTERNS:
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    print(f"{path}:{lineno}: {name}: {line.strip()[:160]}")
                    hits += 1
    print(f"scanned={len(files)} hits={hits}")
    return 0


if __name__ == "__main__":
    scan(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("."))
