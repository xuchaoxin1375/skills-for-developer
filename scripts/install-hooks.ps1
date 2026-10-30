# 启用仓库自带的 .githooks：pre-commit 跑结构与链接检查。
# 用法（仓库根）：powershell -File scripts/install-hooks.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
git -C $root config core.hooksPath .githooks
Write-Host "已启用 .githooks：pre-commit 将运行 check-skills.py --no-harness --strict 与 check-links.py"
