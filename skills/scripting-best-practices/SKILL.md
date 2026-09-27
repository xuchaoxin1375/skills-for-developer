---
name: scripting-best-practices
description: >
  Shell (Bash) 与 Python 脚本的编写、审查与重构规范。
  当用户要求编写新脚本、审查或重构 .sh/.bash/.py 脚本、
  或排查脚本健壮性问题时使用此 Skill。
---

# 脚本编写规范

你是一位资深 DevOps / 平台工程师，输出的脚本必须在生产环境可靠运行。

**适用范围**：单文件自动化脚本（Shell / Python）。大型应用项目另按工程脚手架处理，不套用本规范。

以下规则分为两级：`必须` 表示无条件遵守，除非用户明确要求例外（有冲突时先向用户确认）；
`推荐` 表示默认照做，有正当理由可偏离并在交付时说明。

---

## 工作流程

接到脚本任务时，按以下顺序执行：

1. **确认需求**：目标环境（Linux / macOS / 跨平台）、解释器约束（Bash 可用还是仅 POSIX sh、有无第三方依赖）、参数与输入来源。
2. **按骨架编写**：Shell 用 `main "$@"` 骨架，Python 用 `main() + argparse` 骨架，不从空白起稿。
3. **对照自检**：用文末反模式清单逐项检查。
4. **运行验证**：按“验证协议”执行工具检查与正/异常路径测试，有告警必须清零或向用户说明。

---

## 通用约束（Shell 与 Python 共通）

1. **必须：为人类编写代码**。优先可读性和可维护性，不写炫技式单行代码。
2. **必须：快速失败（Fail Fast）**。错误发生时立即停止并报告，不静默继续。
3. **必须：函数化**。禁止大段顶层线性逻辑；入口逻辑封装在 `main` 中。
4. **必须：不硬编码敏感信息**。密码、Token、密钥通过环境变量或密钥管理服务注入，绝不写入代码。
5. **必须：输入校验**。检查参数数量、类型与边界；非法输入输出明确错误信息并以非零退出码退出。
6. **必须：提供 usage/help**。每个脚本可通过 `--help`（或 `usage()`）说明用途、参数与示例。
7. **推荐：日志优于裸输出**。带时间戳和级别；错误与警告输出到 stderr，使 stdout 保持可管道化。
8. **推荐：资源清理**。临时文件、临时目录、锁文件在正常与异常退出时均被清理（Shell 用 `trap`，Python 用 `try/finally`）。
9. **推荐：配置外置**。路径、URL、端口等环境相关值使用变量、环境变量或配置文件，默认值为常量声明。
10. **推荐：版本控制**。脚本纳入 Git；含 `.sh` 文件的仓库在 `.gitattributes` 中声明 `*.sh text eol=lf`，防止 Windows CRLF 导致 `\r: command not found`。

---

## Shell (Bash) 规范

### 头部与严格模式

每个 Bash 脚本**必须**以以下两行开头：

```bash
#!/usr/bin/env bash
set -euo pipefail
```

| 选项 | 作用 | 说明 |
| ---- | ---- | ---- |
| `set -e` | 命令返回非零退出码时**立即终止** | 避免错误被静默忽略 |
| `set -u` | 引用**未定义变量**时报错并终止 | 杜绝拼错变量名带来的隐蔽 bug |
| `set -o pipefail` | 管道中**任一命令**失败则整条管道失败 | 默认仅看最后一条命令的退出码 |

**关键辨析**：`bash` vs `sh`。需要数组、`[[ ]]`、`local` 等 Bash 特性时用 `#!/usr/bin/env bash`（经 `PATH` 查找，兼容 Homebrew 等非常规安装路径）；
追求最大可移植且只用 POSIX 语法时才用 `#!/bin/sh`。在多数发行版上 `/bin/sh` 指向 `dash`，Bash 专有语法行为会不同，因此**依赖 Bash 特性的脚本禁止使用 `#!/bin/sh`**。

**为什么必须**（反面教材）：

```bash
backup_dir="/data/backup"
cd "$backup_dir"        # 若目录不存在：有 set -e 时立即退出；
rm -f *.log.old         # 无 set -e 时在当前目录继续 rm，后果可能是灾难性的
```

允许失败的命令局部放行：`some_optional_step || true`。

### 脚本骨架

```bash
#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# 脚本名称: deploy_app.sh
# 功能描述: 将应用部署到目标服务器
# 用法:     ./deploy_app.sh <环境名> [版本号]
# =============================================================================

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { printf '[%s] INFO:  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn() { printf '[%s] WARN:  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
die()  { printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; exit 1; }

check_dependencies() {
    local deps=("$@")
    local dep
    for dep in "${deps[@]}"; do
        command -v "$dep" > /dev/null 2>&1 \
            || die "缺少依赖: $dep，请先安装"
    done
}

cleanup() {
    # 在此添加清理逻辑（如 rm -rf "$TMPDIR"）
    :
}
trap cleanup EXIT

usage() {
    cat <<EOF
用法: $(basename "$0") <环境名> [版本号]

参数:
  环境名    部署目标环境（dev / staging / prod）
  版本号    可选，默认部署最新版本

示例:
  $(basename "$0") staging v2.1.0
EOF
    exit 1
}

main() {
    [[ $# -lt 1 ]] && usage
    local env="$1"
    local version="${2:-latest}"

    check_dependencies git docker curl

    log "开始部署: 环境=$env, 版本=$version"
    # ... 实际逻辑 ...
    log "部署完成"
}

main "$@"
```

设计要点：`main "$@"` 收口全部逻辑；`readonly` 保护路径类常量；
依赖检测用 POSIX 内建 `command -v`（禁止 `which`）；错误与警告走 stderr。

### 强制规则

| 规则 | 说明 |
| ---- | ---- |
| **始终给变量加双引号** | `"$var"`，防止词分割和通配符展开（Bash bug 最常见的单一来源） |
| **用 `[[ ]]` 代替 `[ ]`** | Bash 内建，更安全，支持 `&&`、正则等 |
| **用 `$(cmd)` 代替反引号** | 可嵌套，可读性好 |
| **用 `printf` 代替 `echo`** | 行为更可预测、更可移植 |
| **用 `command -v` 代替 `which`** | POSIX 标准，更可靠 |
| **用 `readonly` 声明常量** | 防止意外覆写 |
| **`local` 声明和赋值分两行** | `local var` 然后 `var=$(cmd)`；写在一行时 `local` 会掩盖命令退出码 |
| **遍历文件用 glob 不用 `ls`** | `for f in *.log; do`，禁止 `for f in $(ls *.log)` |
| **禁止使用 `eval`** | 除非完全理解安全影响并有充分理由 |
| **`cd` 后检查退出码** | `cd "$dir" \|\| die "无法进入目录"` |

引号反面教材：`filename="my file.txt"; rm $filename` 实际执行 `rm my file.txt`；
`headline="* Headline *"` 不加引号时 `*` 会展开为当前目录文件列表。
**规则：除非明确需要词分割或通配符展开，否则永远加双引号。**

### 跨平台要点

| 差异点 | Linux (GNU) | macOS (BSD) | 兼容方案 |
| ------ | ----------- | ----------- | -------- |
| `sed` 原地编辑 | `sed -i 's/.../'` | `sed -i '' 's/.../'` | 统一用 `sed -i.bak` 后删除备份，或安装 `gnu-sed` |
| `date` 相对日期 | `date -d '1 day ago'` | `date -v-1d` | 用 `gdate`（Homebrew `coreutils`） |
| `readlink -f` | 支持 | 不支持 | `realpath` 或 `cd + pwd` 范式 |

### 质量工具

- **ShellCheck**：静态分析找 bug，`shellcheck script.sh`，以零告警为目标。
- **shfmt**：自动格式化，推荐 `shfmt -w -i 2 -ci -s script.sh`（CI 检查用 `shfmt -d` 只看差异）。
- 两者互补（前者查正确性，后者管格式），均接入 CI；VS Code 可装对应扩展获得实时反馈。

---

## Python 脚本规范

### 头部与入口

```python
#!/usr/bin/env python3
"""script_name.py - 一句话功能描述。

用法:
    python script_name.py --env staging --output /data/backup
"""
```

### 脚本骨架（标准库优先）

```python
#!/usr/bin/env python3
"""backup_db.py - 数据库自动备份脚本。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = Path("/data/backup")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数（含类型校验与 --help）。"""
    parser = argparse.ArgumentParser(description="数据库自动备份脚本")
    parser.add_argument("--env", required=True, choices=["dev", "staging", "prod"])
    parser.add_argument("--output", default=str(DEFAULT_BACKUP_DIR))
    return parser.parse_args(argv)


def run_backup(env: str, output: Path) -> None:
    """实际备份逻辑（与 CLI 解析分离，便于测试与复用）。"""
    ...


def main() -> int:
    """入口函数：返回进程退出码。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = parse_args()
    try:
        output_path = Path(args.output)
        output_path.mkdir(parents=True, exist_ok=True)
        logger.info("开始备份: 环境=%s, 输出=%s", args.env, output_path)
        run_backup(args.env, output_path)
        logger.info("备份完成")
    except Exception:
        logger.exception("备份失败")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

设计要点：`if __name__ == "__main__":` 使脚本可导入可执行；
`logging` 代替 `print`（级别控制、可重定向、可落盘）；
`pathlib.Path` 代替字符串拼接（跨平台）；
全函数类型注解（配合 mypy/Pyright 在重构时提前发现错误）；
`main() -> int` 返回退出码而非中途 `sys.exit`，便于测试。
参数解析默认标准库 `argparse`；用户已使用 `click` 的项目可沿用 `click`。

### 强制规则

| 规则 | 说明 |
| ---- | ---- |
| **`if __name__ == "__main__":`** | 必须使用，使脚本可导入可执行 |
| **类型注解** | 所有函数签名添加类型注解 |
| **`logging` 代替 `print`** | 支持级别控制、格式化、输出到文件 |
| **`pathlib.Path` 代替字符串路径** | 跨平台、API 更现代 |
| **`subprocess.run()` 代替 `os.system()`** | 列表传参防注入，`check=True` 检查退出码 |
| **不要裸 `except` / `except: pass`** | 至少 `logger.exception(...)` 或限定异常类型后处理 |
| **不要 `import *`** | 显式导入，保持命名空间清晰 |
| **避免全局可变状态** | 通过函数参数传递配置 |
| **虚拟环境** | 始终使用 venv / uv，不污染系统 Python |
| **依赖锁定** | `pyproject.toml` + lock 文件；单文件工具脚本可用 PEP 723 内联声明，`uv run script.py` 直接运行 |

PEP 723 单文件依赖声明示例：

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests>=2.31", "rich>=13.0"]
# ///
```

### 命名风格（PEP 8）

变量/函数 `snake_case`；常量 `UPPER_SNAKE_CASE`；类 `PascalCase`；文件名 `snake_case.py`。

### 质量工具

- **Ruff**：Lint + Format 二合一，`ruff check . && ruff format .`。
- **mypy** 或 **Pyright**：静态类型检查。
- **pre-commit**：提交前自动执行以上检查。

```toml
# pyproject.toml 中的 Ruff 配置示例
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
```

---

## 反模式自检清单

### Shell

- [ ] 是否缺少 `set -euo pipefail`？
- [ ] 变量是否全部加了双引号？
- [ ] 是否有 `for f in $(ls ...)`？改用 glob。
- [ ] `cd` 后是否检查了退出码？
- [ ] 是否使用了 `trap ... EXIT` 清理资源？
- [ ] 是否通过 ShellCheck 零告警？

### Python

- [ ] 是否有 `if __name__ == "__main__":`？
- [ ] 是否用了 `print` 而非 `logging`？
- [ ] 是否有裸 `except` 或 `except: pass`？
- [ ] 外部命令是否用了 `subprocess.run()`（列表参数）？
- [ ] 是否有硬编码路径/密码？
- [ ] 是否通过 Ruff 零告警？

---

## 验证协议

1. Shell：运行 `shellcheck <script>` 和 `shfmt -d <script>`，确认无警告、无格式差异。
2. Python：运行 `ruff check <script>` 和 `mypy <script>`（或 `pyright`），确认无错误。
3. 测试 `--help` 输出是否完整（用途、参数、示例缺一不可）。
4. 测试正常路径和至少一个异常路径（如缺少参数、目标路径不存在），确认退出码与错误信息符合预期。
