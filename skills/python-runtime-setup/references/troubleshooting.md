# 排障

先区分“uv 本身找不到”“解释器不对”“锁或环境不同步”“缓存或磁盘”“项目工具链选择”。一次只改一层，不重复安装。

## uv 找不到或有多份

| 检查 | 说明 |
| --- | --- |
| `uv --version` | 当前 PATH 命中的 uv |
| `python -m uv --version` | Python 用户脚本目录中的启动器找到的二进制 |
| `where.exe uv` / `command -v uv` | 所有可见入口 |
| `Get-Command uv -All`（PowerShell） | 同名命令的所有来源 |

处理：

- 只有 `python -m uv` 可用：把用户脚本目录加入 PATH（Windows 常见 `%APPDATA%\Python\Python3<minor>\Scripts`，Unix 常见 `~/.local/bin`），不要重装。
- 两套版本不同：保留一套；移除旧 shim、卸载旧包或调整 PATH 顺序。不要用 `uv self update` 更新包管理器安装的 uv。
- 改完 PATH 新开终端；当前进程不会自动刷新。

## 解释器不对

- `uv python find` 看 uv 实际选中的解释器。
- `uv run python -V` 看项目内实际版本。
- `.python-version` 固定项目版本；`uv python pin <version>` 写入；`uv python install <version>` 安装。
- 需要临时指定时用 `uv run --python <version>`；不要改全局 `python` 指向来修项目。
- 已有 conda 环境可以作为解释器来源，但不要在同一环境里混用 conda 和 pip/uv 安装同一批包。
- `UV_PYTHON` 等环境变量可能覆盖选择；先检查当前环境变量，再改项目文件。

## 锁文件与环境

- `uv lock --check`：锁文件是否与 `pyproject.toml` 一致。
- `uv sync --check`：环境是否与锁文件一致。
- `--locked`：锁文件过期直接失败，适合 CI 或复跑。
- `--frozen`：按现有锁文件执行，不检查是否过期；适合锁文件就是合同的场景。
- `uv run` 默认不删除多余包；`uv sync` 默认精确同步。手工 `uv pip install` 后环境可能有多余包，用 `uv sync` 清理。
- 不删除 `uv.lock` 来绕过冲突；确认 `pyproject.toml` 的变更是有意的，再 `uv lock`。
- 从 `requirements.txt` 迁移时保留原文件作对照，用 `uv add -r requirements.txt` 后核对版本差异。

## 缓存与磁盘

- `uv cache dir` 查看缓存位置；默认全局，不是每项目一份。
- 缓存与 venv 同文件系统时，uv 尽量硬链接；跨盘会复制。目录大小相加会高估实际占用。
- 抽查硬链接：Python `os.stat(path).st_nlink`；Windows 也可用 `fsutil hardlink list <file>`。
- `uv cache prune` 清理未使用项；`uv cache clean <package>` 清单个包；`--refresh` 重新校验。不要手工删缓存目录。
- 只有缓存损坏、哈希异常等证据才清缓存；网络慢不默认清空缓存。
- CI 可缓存 uv cache，结束时 `uv cache prune --ci`。

## 系统 Python 与 PEP 668

- `externally-managed-environment` 表示系统 Python 受保护；新建 venv、用 `uv tool install` 或 pipx。
- 不默认 `--break-system-packages`；只有用户明确要求并理解风险时才考虑。
- 项目依赖不要装进系统 Python；全局 CLI 用隔离工具环境。

## 工具环境

- `uv tool list` 查看已安装工具；`uv tool dir` 查看工具目录。
- 工具环境不手工 pip 修改；升级用 `uv tool upgrade`，损坏时重新 `uv tool install`。
- 项目内开发工具（pytest、ruff、mypy）用 `uv add --dev` 和 `uv run`，不要装成全局 tool。

## 索引、镜像与构建

- uv 不读取 pip 的 `pip.conf` / `PIP_INDEX_URL`；索引配置用 `--default-index`、`UV_DEFAULT_INDEX` 或项目 `[[tool.uv.index]]`。
- 镜像、代理、超时、证书、构建失败与依赖冲突按 [network-access](../../network-access/SKILL.md) 的依赖下载和安装分诊处理。
- 不要为了绕过解析失败删除锁文件或切换包管理器；先定位是索引、版本约束还是构建工具。

## 何时停止

- 同一现象连续两次修复无变化，停止重复安装，保存 `uv --version`、`where.exe uv` / `command -v uv`、`uv python find`、`uv cache dir`、项目文件状态和实际错误。
- 需要改系统 Python、机器 PATH、CI 或团队工具链时，先说明影响并取得确认。
