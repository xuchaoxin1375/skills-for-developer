#!/usr/bin/env bash
# 启用仓库自带的 .githooks：pre-commit 跑结构与链接检查。
# 用法（仓库根）：bash scripts/install-hooks.sh
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
git -C "$root" config core.hooksPath .githooks
chmod +x "$root/.githooks/pre-commit" 2>/dev/null || true
echo "已启用 .githooks：pre-commit 将运行 check-skills.py --no-harness --strict 与 check-links.py"
