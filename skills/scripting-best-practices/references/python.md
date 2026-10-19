> 本文件是 `scripting-best-practices` 的按需参考，只在处理对应语言时读取。通用约束、工作流程与验证协议仍以 [SKILL.md](../SKILL.md) 为准。

# Python 脚本规范

## 头部与入口

```python
#!/usr/bin/env python3
"""script_name.py - 一句话功能描述。

用法:
    python script_name.py --env staging --output /data/backup
"""
```

## 脚本骨架（标准库优先）

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

## 强制规则

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

## 文件读写编码（UTF-8，默认）

必须：读写文本文件时显式指定编码。常规文本按 UTF-8 处理：读用 `Path.read_text(encoding="utf-8")`，写用 `Path.write_text(..., encoding="utf-8")`；需去掉字节顺序标记（BOM，Byte Order Mark）时读用 `encoding="utf-8-sig"`。子进程输出编码见“本地工具：文件遍历与子进程”第 3 条，不与本条混用。禁止用 `errors="replace"` 或 ASCII 转义做常规输出，它们只掩盖误读；诊断链路无法统一编码时的保真回退见 `powershell-pitfalls` 的编码参考。

```python
from pathlib import Path
Path("example.txt").write_text("中文", encoding="utf-8")
text = Path("example.txt").read_text(encoding="utf-8")
```

## 执行侧编码（UTF-8，默认）

必须：从 shell/任务调度启动 Python 时，调用侧与被调侧编码对齐。管道重定向下
Python 按系统 locale 编码 stdout（中文 Windows 默认 GBK），而调用侧（如已设
UTF-8 的 PowerShell）按 UTF-8 解码，错位即乱码——文件读写已显式 UTF-8 也救不了输出管道。默认：

- 单次：`python3 -X utf8 <script>.py`；
- 父子多层 python（脚本内再起子进程）：父进程先设 `PYTHONUTF8=1`，子进程继承；
- 新脚本文件本身：UTF-8 无 BOM，换行 LF（仓库 `.gitattributes` 已对 `*.py` 强制）。

反例证据：外层有 `-X utf8` 而内层无，内层 GBK 输出在外层直接 `UnicodeDecodeError`。
文件内容编码见上一节，不与本条混用。

## 命名风格（PEP 8）

变量/函数 `snake_case`；常量 `UPPER_SNAKE_CASE`；类 `PascalCase`；文件名 `snake_case.py`。

## 质量工具

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

## Tab 补全

| 框架 | 补全支持 | 接入方式 |
| ---- | -------- | -------- |
| Click（≥ 8.0） | 内建 | 零代码；在 README 告知激活命令：`eval "$(_<PROG>_COMPLETE=bash_source <prog>)"`（`<PROG>` 为可执行文件名的大写形式，短横线转下划线；zsh/fish 换用对应的 `zsh_source`/`fish_source`） |
| argparse | 第三方库 argcomplete | 文件顶部加 `# PYTHON_ARGCOMPLETE_OK`，`parse_args()` **之前**调用 `argcomplete.autocomplete(parser)`；用户侧 `pip install argcomplete` 后运行一次 `activate-global-python-argcomplete` |
| Typer | 内建（基于 Click） | 告知用户运行 `<prog> --install-completion` |

动态值：Click 用 `shell_complete` 回调（如 `@click.argument("env", shell_complete=get_envs)`，按 `incomplete` 前缀过滤）；
argcomplete 用自定义 Completer（如 `.completer = argcomplete.DirectoriesCompleter()`）。
有 `choices` 的参数框架自动补全，无需额外代码。

---

## 反模式自检清单

- [ ] 是否有 `if __name__ == "__main__":`？
- [ ] 是否用了 `print` 而非 `logging`？
- [ ] 是否有裸 `except` 或 `except: pass`？
- [ ] 外部命令是否用了 `subprocess.run()`（列表参数）？
- [ ] 是否有硬编码路径/密码？
- [ ] 文本读写是否显式指定 encoding？是否误用 errors="replace" 或 ASCII 转义做常规输出？
- [ ] 经 shell 启动 Python 是否对齐执行侧编码（单次 `-X utf8`，多层父进程设 `PYTHONUTF8=1`）？详见“执行侧编码”节。
- [ ] 是否通过 Ruff 零告警？
- [ ] 需要补全时是否已接入（Click 内建 / argcomplete / Typer）并在 README 说明激活方式？
