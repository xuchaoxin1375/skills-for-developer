"""frontend-design低级违例的轻量静态扫描。只读，打印报告。

无匹配文件时返回 2，避免错误路径被当成“扫描通过”。

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

LINE_PATTERNS = [
    ("hex-literal-in-component", re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")),
    ("bare-outline-none", re.compile(r"outline\s*:\s*['\"]?none", re.IGNORECASE)),
    ("window-alert", re.compile(r"window\.(alert|confirm)\s*\(")),
    ("user-scalable-no", re.compile(r"user-scalable\s*=\s*no", re.IGNORECASE)),
]

# JSX 的 div 开标签可能跨多行；单行正则会把 onClick 漏在下一行。
TEXT_PATTERNS = [
    ("div-onclick", re.compile(r"<div\b[^>]*\bonClick", re.IGNORECASE | re.DOTALL)),
]

TARGET_SUFFIXES = {".tsx", ".jsx", ".ts", ".js", ".vue", ".css", ".scss", ".html"}


def collect_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix in TARGET_SUFFIXES else []
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in TARGET_SUFFIXES
    ]


def scan(root: Path) -> int:
    hits = 0
    files = collect_files(root)
    if not files:
        print(
            f"scanned=0 hits=0 (no matching files under {root})",
            file=sys.stderr,
        )
        return 2
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in LINE_PATTERNS:
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    print(f"{path}:{lineno}: {name}: {line.strip()[:160]}")
                    hits += 1
        for name, pattern in TEXT_PATTERNS:
            for match in pattern.finditer(text):
                lineno = text.count("\n", 0, match.start()) + 1
                snippet = " ".join(match.group(0).split())[:160]
                print(f"{path}:{lineno}: {name}: {snippet}")
                hits += 1
    print(f"scanned={len(files)} hits={hits}")
    return 0


if __name__ == "__main__":
    sys.exit(scan(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")))
