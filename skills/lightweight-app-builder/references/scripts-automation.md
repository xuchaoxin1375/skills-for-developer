# 自动化脚本构建

脚本的判断标准很简单：**没有人盯着它跑**。它通常由定时器、文件变化、或者另一段程序触发，因此设计重心从"好不好看"变成"可不可靠、出了问题能不能查"。

## 目录

- 脚本与 CLI 的分界
- Python 脚本标准形态（内联元数据字段表）
- Shell 与 PowerShell 规范
- 定时任务三平台配置
- 可靠性四件套
- 凭据管理
- 一键安装脚本
- 跨平台坑位清单

## 脚本与 CLI 的分界

| 特征 | 脚本 | CLI |
| --- | --- | --- |
| 触发方式 | 定时、事件、被其他程序调用 | 人手敲 |
| 参数复杂度 | 固定或极少 | 多子命令多选项 |
| 输出要求 | 日志为主，几乎不打印到屏幕 | 人类可读 + 机器可读 |
| 失败处理 | 自动重试、断点续跑、告警 | 报错给用户看 |
| 交付形式 | 脚本文件 + 调度配置 | 可执行程序 |

如果一个"脚本"开始长出第三个参数和交互提示，就把它升级为 CLI。**半途半脚的脚本是最难维护的形态**。

## Python 脚本标准形态

2026 年的首选是 `uv` 配合脚本内联元数据（PEP 723）。一个文件自带依赖声明，任何机器装好 `uv` 之后一条命令即可运行。

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["rich>=13.7", "httpx>=0.27"]
# ///
"""每晚整理下载目录，并把结果写入日志。"""
```

内联元数据字段逐项解释：

| 字段 | 含义 | 不写会怎样 |
| --- | --- | --- |
| `requires-python` | 允许运行的 Python 版本范围 | 旧版本 Python 上会出现语法错误而不是友好提示 |
| `dependencies` | 运行所需第三方包及最低版本 | 用户要手动 `pip install`，脚本失去"一条命令跑起来"的能力 |
| `[tool.uv]` 段（可选） | `uv` 专属设置，如国内镜像源 | 走默认源，国内可能下载缓慢 |

要点：

- 依赖版本**只写下限**（`>=`），锁版本交给 `uv.lock`；脚本类单文件项目可以接受较宽松的范围。
- **显式编码**：所有 `open()` 都写 `encoding="utf-8"`，否则 Windows 上默认编码是 GBK，中文必然乱码。
- **路径一律 `pathlib.Path`**，并从 `Path.home()` 或配置项出发构造，不要依赖当前工作目录。
- **结构固定为三段**：`load_config()` 读配置 → `process()` 纯逻辑 → `main()` 串联并处理异常。逻辑函数不打印、不做 I/O，方便测试。

## Shell 与 PowerShell 规范

Bash 脚本头部固定写：

```bash
#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
```

这四行的含义：`-e` 让任何命令失败立即退出；`-u` 禁止使用未定义变量；`-o pipefail` 让管道中任一环节失败都算失败；`IFS` 收紧分词规则，避免带空格的文件名被拆开。

**强制工具链**：提交前必须通过 `shellcheck`（静态检查）和 `shfmt -w`（格式化）。这两步能在写代码阶段就抓住绝大多数跨平台与引号错误。

PowerShell 侧对应规则：

- 文件头写 `[CmdletBinding()]` 与 `param()`，启用 `$ErrorActionPreference = "Stop"`。
- 编码保存为**带 BOM 的 UTF-8**（Windows PowerShell 5.1 对无 BOM 的 UTF-8 会按 ANSI 解析，中文注释会乱码；PowerShell 7 则无此问题）。
- 提供 `-WhatIf` 支持，与 Bash 的 `--dry-run` 对应。

## 定时任务三平台配置

| 平台 | 工具 | 示例命令 | 说明 |
| --- | --- | --- | --- |
| Windows | 任务计划程序 | `schtasks /Create /TN "CleanDownloads" /TR "pythonw C:\tools\clean.py" /SC DAILY /ST 23:30` | 用 `pythonw` 避免弹出黑色控制台窗口 |
| Linux | cron | `30 23 * * * /usr/local/bin/clean.sh >> /var/log/clean.log 2>&1` | 需要确认用户有 crontab 权限 |
| macOS | launchd | 用 `launchctl` 加载 `~/Library/LaunchAgents/com.example.clean.plist` | macOS 上 cron 已不推荐，日志要单独指定 |

**cron 五个字段的含义**：依次是分钟（0–59）、小时（0–23）、日（1–31）、月（1–12）、星期（0–7，0 和 7 都是周日），`*` 表示"每一个"。因此 `30 23 * * *` 就是"每天 23 点 30 分"。

**调度配置必须脚本化**：提供 `scripts/install-task.ps1` 与 `scripts/install-cron.sh`，支持 `--uninstall`。手把手教用户点界面是低质量交付，可重复执行的命令才是。

## 可靠性四件套

无人值守脚本的可靠性由四件事决定：

1. **幂等**：重复执行不产生重复结果。用"目标已存在则跳过"或"以内容哈希为键"来保证，而不是依赖"上次跑到哪了"。
2. **原子写**：写文件先写临时文件再 `rename`，进程中途被杀也不会留下半截文件。
3. **并发锁**：用一个带过期时间的锁文件（或 `fcntl`/`msvcrt` 文件锁）防止上一次还没跑完、下一次又启动。
4. **断点续跑**：长任务把进度落盘为 JSON 状态文件，重启后从上次位置继续，而不是从头再来。

配套的**失败策略**要在设计阶段定死并写进决策记录：出错即停（数据一致性要求高时）、或记录后继续（批量处理可容忍个别失败时，最后输出失败清单）。默认推荐后者，因为它符合"第二天早上来看结果"的真实使用方式。

## 凭据管理

- **禁止硬编码**密钥到脚本或提交进仓库。
- 本地开发用 `.env` 文件 + `.gitignore` 排除，并提供 `.env.example` 作为模板。
- 更安全的做法是走系统凭据库：macOS 钥匙串、Windows 凭据管理器、Linux 下的 Secret Service，Python 可用 `keyring` 库统一访问。
- 脚本启动时若取不到凭据，应打印一行"请在 X 位置配置 Y"，而不是抛出难懂的异常栈。

## 一键安装脚本

安装脚本要满足：幂等、可指定版本、可指定安装位置、能自动下载对应平台的产物、最后打印验证命令。

```bash
#!/usr/bin/env bash
set -euo pipefail
VERSION="${VERSION:-latest}"
PREFIX="${PREFIX:-$HOME/.local/bin}"
# 1. 探测平台  2. 拼出下载地址  3. 下载并校验 SHA256  4. 安装到 PREFIX  5. 提示 PATH 配置
```

配套必须提供 Windows 版 `install.ps1`，逻辑一致但用 `Invoke-WebRequest` 与 `$env:USERPROFILE`。**两个脚本的功能集必须对齐**，这是跨平台交付最容易偷工减料的地方。

国内网络环境下，下载 GitHub 释放文件应支持 `--mirror` 参数，自动在原链接前拼接当前可用的镜像代理前缀，并在文档中注明**镜像站可用性会变化，使用前需自行核实**。

## 跨平台坑位清单

- **换行符**：`*.sh` 必须是 LF，否则在 Linux 上报 `/bin/bash^M: bad interpreter`。仓库根目录的 `.gitattributes` 写 `*.sh text eol=lf` 一劳永逸。
- **编码**：Windows 控制台默认 GBK。脚本开头设置 `PYTHONUTF8=1`，或在 PowerShell 里 `[Console]::OutputEncoding = [Text.UTF8Encoding]::new()`。
- **权限位**：Git 默认不保留可执行位，需要 `git update-index --chmod=+x scripts/install.sh`。
- **临时目录**：不要写死 `/tmp`，用 `tempfile`/`$env:TEMP`。
- **进程终止**：Windows 上杀进程树要用 `taskkill /T`，`kill` 一个父进程不会带走子进程。
