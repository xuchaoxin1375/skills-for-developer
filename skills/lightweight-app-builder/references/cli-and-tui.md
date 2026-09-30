# CLI 与 TUI 构建

命令行工具（Command-Line Interface，CLI）和终端文本界面（Terminal UI，TUI）是两种东西：**CLI 面向"敲一条命令完成任务"，TUI 面向"在终端里持续操作一个界面"**。两者可以共存，常见做法是 Cobra 或 `clap` 负责命令结构，TUI 框架负责其中一个交互子命令。

## 目录

- 命令行用法的形式化说明与字段表
- 命令结构设计与配置优先级
- 各语言默认技术栈与 Go 交叉编译
- Shell 脚本严格模式
- 输出纪律与流水线友好
- TUI 框架对比与实现要点
- Windows 终端注意事项
- 测试与文档自动生成

## 命令行用法的形式化说明

一个规范的 CLI 帮助信息通常长这样：

```text
app [全局选项] <子命令> [子命令选项] <位置参数...>
```

逐项解释，这一行决定了用户会不会用你的工具：

| 字段 | 含义 | 设计规则 | 常见误用 |
| --- | --- | --- | --- |
| `app` | 可执行文件名 | 全小写、无空格、可在任何目录调用 | 用中文或带空格的名字 |
| `[全局选项]` | 方括号表示**可省略**，作用于所有子命令 | 只放 `--verbose`、`--config`、`--no-color`、`--version`、`--help` | 把只对某个子命令有意义的选项放这里 |
| `<子命令>` | 尖括号表示**必填**，动词 | 用动词命名：`add`、`list`、`remove`、`run` | 用名词或缩写 |
| `[子命令选项]` | 只影响当前子命令 | 长选项必有，高频项才配短选项 | 同一语义在不同子命令里用不同名字 |
| `<位置参数...>` | 按顺序传入、不带 `--` 的值 | 最多一到两个；`...` 表示可重复 | 把可选信息设计成位置参数，导致顺序难以记忆 |

**两条铁律**：同类信息永远用同一个选项名；凡是能写成长选项的，就不要让用户去记短选项。短选项只保留给最高频的三五个。

凡视角歧义的参数（如相对谁解析），必须在 `--help` 写清。

## 命令结构设计与配置优先级

- **动宾结构**：`app image resize`，而不是 `app resize-image`。子命令可嵌套但不要超过两层。
- **默认子命令**：最常用的动作允许省略，例如 `app` 直接等价 `app list`。
- **零参数即帮助**：无参数运行时打印一段友好的说明和一个最简示例，而不是报错退出。这是非技术用户的第一次接触，直接决定印象。
- **干跑模式**：凡会修改文件系统的命令必须提供 `--dry-run`，先打印将要发生什么。这是安全感的来源。
- **破坏性操作要确认**：删除、覆盖必须默认要求输入 `y` 确认，同时提供 `--yes` 供脚本调用。
- **配置优先级**：命令行选项 > 环境变量 > 项目级配置 > 用户级配置 > 内置默认值。五层关系必须在 `--help` 里写清楚。

配置位置与优先级统一如下，不要手拼路径，用库获取：

| 层级（高→低） | 说明 | 存放位置 / 命名 |
| --- | --- | --- |
| 命令行选项 | 本次调用最高优先生效 | `--dry-run`、`--config` 等 |
| 环境变量 | 供容器与 CI 覆盖 | 统一命名为 `MYTOOL_<OPTION>` 全大写下划线形式 |
| 项目级配置 | 当前目录向上查找，同项目共享 | `.mytoolrc` / `mytool.toml` |
| 用户级配置 | 跨项目个人偏好 | Python `platformdirs.user_config_dir()`；Rust `dirs::config_dir()`；Go `os.UserConfigDir()` |
| 内置默认值 | 兜底 | 写死在代码中 |

缓存用 `user_cache_dir()`（可随时删除），数据用 `user_data_dir()`（删除等于丢数据，需提示），日志用 `user_log_dir()` 或 `--log-file` 显式指定。

## 各语言默认技术栈与 Go 交叉编译

| 语言 | 参数解析 | 交互提示 | TUI | 表格/样式 | 单文件分发 |
| --- | --- | --- | --- | --- | --- |
| Go | Cobra 或 Kong | `huh` | Bubble Tea + Lip Gloss | `table` 包 | 原生支持 |
| Rust | `clap` derive API | `inquire` | ratatui + crossterm | `comfy-table` | 原生支持 |
| Python | Typer（基于 Click） | `questionary` 或 `rich.prompt` | Textual | Rich | PyInstaller，不能交叉编译 |
| TypeScript | `oclif` 或 Commander | `@clack/prompts` | Ink | `ink-table` | `bun build --compile` |

**选择依据**：这些是各语言 2026 年的主流共识——Cobra 支撑着 `kubectl` 与 `gh`，`clap` 的派生宏能把参数定义写成结构体并自动生成帮助，Typer 用 Python 类型注解直接生成命令，`oclif` 加 Ink 是 Claude Code 与 Gemini CLI 的同款组合。

**最小可用骨架（Python + Typer）**，注释说明了每一行存在的理由：

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12", "rich>=13"]
# ///
"""把指定目录里 30 天前的文件按扩展名归档。"""
import typer
from rich.console import Console

app = typer.Typer(help="按修改时间归档旧文件", no_args_is_help=True)
console = Console()

@app.command()
def archive(
    folder: str = typer.Argument(..., help="要整理的目录"),
    days: int = typer.Option(30, help="超过多少天视为旧文件"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印将要做的操作"),
):
    """主命令：扫描并归档。"""
    console.print(f"[bold]扫描[/bold] {folder}，阈值 {days} 天，dry_run={dry_run}")

if __name__ == "__main__":
    app()
```

运行方式是 `uv run archive.py ~/Downloads --days 30 --dry-run`。`uv` 会按文件头部的内联元数据自动建好虚拟环境并装依赖，用户不需要懂 `pip` 和 `venv`。

完整 Typer / Cobra 目录布局归 `engineering-standards.md`，此处不展开：`cli.py` 只做解析与输出，业务放 `core/`，外部世界放 `adapters/`。

Go 的杀手级优势是交叉编译，一条命令产出全平台二进制：

`GOOS=windows GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o dist/mytool.exe .`

| 字段 | 含义 |
| --- | --- |
| `GOOS` | 目标系统，取 `windows` / `darwin` / `linux` |
| `GOARCH` | 目标架构，`amd64` 或 `arm64` |
| `-trimpath` | 去掉本机绝对路径，构建可复现 |
| `-ldflags="-s -w"` | 去符号表与调试信息，体积减约 30% |
| `-o` | 输出文件路径 |

实际项目建议用 GoReleaser 一次产出全平台产物，避免手写循环。

## Shell 脚本严格模式

只做系统运维胶水、逻辑极短时才用 Shell，Bash 脚本在 Windows 上不能原生运行，用户含 Windows 时改用编译产物或提供 `.ps1` 双份。规范头三行逐字保留：

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
```

| 字段 | 作用 |
| --- | --- |
| `#!/usr/bin/env bash` | 经 `env` 找 bash，兼容非 `/bin` 路径，不用 `[[ ]]` 等特性时才可用 `sh` |
| `set -e` / `-u` | 任一命令失败即退出；引用未定义变量即报错，防 `rm -rf ""` 类灾难 |
| `set -o pipefail` | 管道任一环失败则整条失败，否则 `curl x \| bash` 中 `curl` 失败也被吞掉 |
| `set -E` | `ERR` trap 可被函数继承 |
| `IFS=$'\n\t'` | 词分割只按换行制表符，含空格文件名不被拆散 |

配套工具链：`shellcheck` 做静态检查，`shfmt -w -i 2 -ci` 统一格式。

## 输出纪律与流水线友好

CLI 的价值一半在于能和其他工具串起来。四条规则：

- **数据走 stdout，日志走 stderr**。两者绝不能混，否则管道和重定向会污染数据。
- **机器可读输出**：提供 `--json`，字段名稳定、不随版本改名；破坏字段变更是大版本事件。
- **颜色自动关闭**：检测到输出不是终端（被重定向）时自动去色，同时尊重 `NO_COLOR` 环境变量与 `--no-color` 选项。
- **进度不打扰**：长任务用单行刷新的进度条（Rich、`mpb`、`indicatif`），并把最终结果汇总成一行"成功 128 个，跳过 3 个，失败 2 个（见日志）"。

**退出码约定**：`0` 成功，`1` 运行错误，`2` 用法错误，`130` 用户中断。脚本与 CI 全靠退出码判断成败，随便返回 `0` 是最常见的工程事故来源。

## TUI 框架对比与实现要点

| 框架 | 语言 | 架构风格 | 上手难度 | 适合 |
| --- | --- | --- | --- | --- |
| Bubble Tea | Go | Elm 架构（Model、Update、View） | 低 | 快速做出好看的交互界面 |
| ratatui | Rust | 立即模式，自己控制循环 | 中 | 高刷新率、精细控制、性能敏感 |
| Textual | Python | 声明式组件 + CSS | 低 | 数据面板、表单、工具型应用 |
| Ink | TypeScript | React 组件 | 中（需会 React） | 已有 React 经验的团队 |

**中文场景必须注意**：中文、全角符号在终端占两列宽度，若不使用 `unicode-width` 类处理，表格边框会错位。Textual 与 ratatui 内置了宽度计算，自己拼字符串则一定要引入等宽处理（Go 用 `go-runewidth`，Python 用 `wcwidth`）。

TUI 实现五要点：

- **必须能退出**：`q`、`Ctrl+C`、`Esc` 至少支持两个，并在界面上明示。
- **非 TTY 降级**：被管道或在 CI 中时自动切一次性纯文本输出，否则刷乱码。
- **异常复位**：退出（包括异常）必须恢复终端状态，Python 用 `try/finally`，Go 用 `defer`。
- **CJK 宽度**：对齐按显示宽度计算，全角占 2 列，否则中英混排必错位。
- **监听 resize**：窗口尺寸变化时重排布局，高刷新场景优先考虑 ratatui。

## Windows 终端注意事项

- **ANSI 转义码**：Windows 10 1809 之后的终端（Windows Terminal、新版 conhost）支持 ANSI 颜色，但旧版 `conhost` 需要显式启用虚拟终端处理。主流库（Rich、crossterm、Bubble Tea）已自动处理，**自己手写转义码会翻车**。
- **字体**：中文等宽渲染依赖终端字体，文档里建议用户使用 Windows Terminal 而不是老旧的命令提示符。
- **路径长度**：超过 260 字符会失败，长路径需开启系统长路径支持或使用 `\\?\` 前缀。
- **Ctrl+C 语义**：Windows 上信号模型不同，涉及优雅退出的逻辑要分别测试。

## 测试与文档自动生成

- **快照测试**：对 `--json` 输出和关键帮助文本做快照，避免无意间破坏用户脚本。
- **解析测试优先**：先测参数解析与默认值，再测业务逻辑，因为 CLI 的大部分 bug 出在参数层。
- **隔离铁律**：禁读写真实目录与用户家目录，端到端一律用临时目录，用完即删。
- **自动生成补全**：Cobra 一次调用生成 Bash、Zsh、Fish、PowerShell 补全；`clap` 有 `clap_complete`；Typer 提供 `--install-completion`。把补全安装写进安装脚本。
- **帮助文本即文档**：每个选项都写 `help`，用 `--help` 生成 `docs/USAGE.md` 的命令参考部分，避免两处不同步。
