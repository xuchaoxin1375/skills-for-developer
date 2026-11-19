---
name: python-runtime-setup
description: >
  Windows、Linux、macOS 上安装与切换 Python 运行时、安装 uv，并为项目选择隔离环境与依赖锁定方式的选型与验收。
  按“全局 uv 工具 + 全局缓存 + 每项目解释器/venv/锁文件”分层，覆盖 uv 是否全局可用、PATH 冲突、多份安装、
  uv.lock/uv sync/uv run、--locked/--frozen、缓存复用与清理、uv tool/uvx、PEP 723 与 CI。
  项目依赖镜像/代理/下载失败归 network-access，脚本编写归 scripting-best-practices，本机环境盘点归 resource-inventory。
---

# Python 运行时与 uv 环境

## 适用范围

安装或更换 Python、安装 uv、决定 uv 是否全局可用、给项目选择 venv/uv/conda、固定依赖与 Python 版本、排查 PATH 冲突或缓存复用时加载。产出是一套明确的运行时与环境方案，以及可验证的验收结果；平台命令按需读[安装与 PATH](references/install-and-path.md)，故障按需读[排障](references/troubleshooting.md)。

不在本 skill：

- 包索引、镜像、代理、下载失败与构建失败，按 [network-access](../network-access/SKILL.md) 的依赖下载与安装分诊。
- 脚本、CLI 的代码结构与参数规范，按 [scripting-best-practices](../scripting-best-practices/SKILL.md)。
- 本机已有哪些运行时与包管理器，按 [resource-inventory](../resource-inventory/SKILL.md)。
- 小工具形态选型与打包分发，按 [lightweight-app-builder](../lightweight-app-builder/SKILL.md)。
- 项目业务数据标准与运行命令，按项目文档。

## 最短执行路径

1. **先探测**：`uv --version`、`where.exe uv`（Windows）或 `command -v uv`、`python -V`；再读项目的 `pyproject.toml`、`uv.lock`、`.python-version`，以及是否已有 `requirements.txt` 或 `environment.yml`。已有工具链不因“统一”而更换。
2. **分层决策**：分别决定 uv 二进制、缓存、解释器和项目环境，不从“全局安装”一步跳到“全局包”。
3. **只装一次 uv**：已有安装先复用；没有才安装。装完把入口放入 PATH，只保留一套主导安装。
4. **同步项目**：固定 Python，生成或校验锁文件，`uv sync`，用 `uv run` 执行；不要把手动激活 venv 当作默认路径。
5. **验收**：确认 `uv`、解释器、锁文件、环境和缓存位置，记录未覆盖项。

## 分层模型

| 层 | 归属 | 规则 |
| --- | --- | --- |
| uv 二进制 | 每用户或每机器一份 | 放入 PATH 后全局可用；不装进项目 venv，不写进项目依赖 |
| uv 缓存 | 全局共享 | 默认在用户缓存目录；与 venv 同盘才能硬链接复用；不手工修改 |
| Python 解释器 | 项目固定，可多处共享 | 用 `.python-version` 记录；不要依赖 PATH 上碰巧命中的 `python` |
| 项目环境 | 每项目独立 | `.venv` + `uv.lock`；不共享、不提交、不跨项目复制 |

“全局可用”指第一层，不是第三、四层。多个项目可以共用一个 uv 和一份缓存，但仍应各有自己的 `.venv` 和锁文件。

## 该不该全局可用

该。uv 是工具，不是项目依赖。

- 全局一份 uv 可避免每个项目重复安装，也让脚本和 agent 在任何目录都能调用。
- 全局 uv 不会让项目共用包版本；依赖仍由各项目的 `uv.lock` 和 `.venv` 隔离。
- 已有安装时先找实际路径，不要因为 `uv` 不在 PATH 就再装一份。`python -m uv` 能用，说明二进制通常已存在，只是入口目录不在 PATH。
- 同时存在 pip、pipx、Scoop、winget、standalone 多套安装时，保留一套并移除或降级其余入口；`uv --version` 与 `python -m uv --version` 不一致就是典型信号。
- 重复安装的主要代价不是磁盘，而是版本漂移和 PATH 歧义。

安装方式与取舍：

| 方式 | 适用 | 更新 |
| --- | --- | --- |
| standalone 安装器 | 希望独立于 Python、单文件自更新 | `uv self update` |
| Scoop / winget / Homebrew | 已用对应包管理器，想统一升级 | 包管理器的 upgrade |
| pipx | 已有 Python，想把 uv 放在隔离工具环境 | `pipx upgrade uv` |
| pip `--user` | 已有 Python，接受用户级脚本目录 | `python -m pip install --user --upgrade uv` |
| 项目 venv 内安装 | 不推荐 | 会随项目复制、版本分散 |

平台命令、PATH 写法和卸载步骤见[安装与 PATH](references/install-and-path.md)。

## 项目工作流

- **新项目**：`uv init` → `uv add` → `uv lock` → `uv sync` → `uv run`。
- **已有项目**：先读现有 `pyproject.toml`、锁文件和 Python 版本；已有 pip/conda 项目不默认迁移，迁移需明确授权并保留原锁文件作对照。
- **提交**：`pyproject.toml`、`uv.lock`、`.python-version` 入库；`.venv/` 忽略。锁文件由 uv 管理，不手工编辑。
- **固定 Python**：`uv python pin <version>` 写 `.python-version`；需要新解释器时 `uv python install <version>`。不要依赖 `python` 当前指向的版本。
- **运行**：优先 `uv run <command>`，它会检查锁文件与环境；不要把手动 `activate` 当作默认流程。
- **精确同步**：`uv sync` 默认删除锁文件之外的多余包；`uv run` 默认保留多余包。环境被手工装过东西时，用 `uv sync` 回到锁文件状态。
- **复现**：自动化用 `uv run --locked`（锁文件过期即失败）或 `uv run --frozen`（按现有锁文件执行，不检查是否过期）；健康检查用 `uv lock --check`、`uv sync --check`。
- **迁移**：从 `requirements.txt` 迁移时用 `uv add -r requirements.txt`，核对解析结果后再切换；不要直接删除原锁文件或 requirements。

## 缓存与依赖复用

- uv 缓存全局共享；安装时尽量把缓存文件硬链接进 venv，而不是复制。缓存与 venv 不在同一文件系统时会退化为复制。
- 多个 venv 共享依赖时，表观大小相加会明显大于实际占用；判断是否复用看 inode/硬链接数（如 `os.stat().st_nlink`），不要只看目录大小。
- 复用受平台、Python ABI、包版本影响：cp313 的 wheel 不能给 cp312 用；不同包版本各占条目；不同索引可能增加元数据缓存。
- 常用命令：`uv cache dir` 查看位置，`uv cache prune` 清理未使用项，`uv cache clean <package>` 清单个包，`--refresh` 强制重新校验。不要手工删缓存目录。
- 不要把 `UV_CACHE_DIR` 设成每项目一份；确有隔离需求时写明原因和清理责任。CI 结束可跑 `uv cache prune --ci`。

## 工具与脚本

- 一次性命令用 `uvx <tool>`；需要长期在 PATH 上则 `uv tool install <tool>`，升级用 `uv tool upgrade <tool>`。工具环境由 uv 管理，不手工 pip 修改。
- 项目内的 pytest、ruff、mypy 等开发工具应装进项目环境（如 `uv add --dev`），用 `uv run pytest`；只有需要脱离项目、供其他程序调用的 CLI 才用 `uv tool`。
- 单文件脚本用 PEP 723 内联依赖，`uv run script.py` 自动建临时环境；脚本结构、参数与编码规范按 [scripting-best-practices](../scripting-best-practices/SKILL.md) 的 Python 参考。
- 不要用 `uv tool` 安装项目运行依赖，也不要把项目依赖装进 tool 环境。

## 选型

| 场景 | 默认 | 取舍 |
| --- | --- | --- |
| 新项目、无既有约束 | uv + `pyproject.toml` + `uv.lock` | 解析快、锁文件完整；团队需接受 uv |
| 已有 pip / requirements 项目 | 沿用 pip/venv | 迁移会改锁文件与 CI；除非明确收益，不静默切换 |
| 已有 conda/科学计算栈 | 沿用 conda | 不因“uv 更快”替换整套环境；混用 pip/conda 需先确认 |
| 单文件脚本、一次性任务 | PEP 723 + `uv run` | 不需要项目脚手架；复杂项目仍用 `pyproject.toml` |
| 全局 CLI 工具 | `uvx` 或 `uv tool install` | 工具与项目隔离；项目内开发工具仍用 `uv run` |
| 系统 Python / PEP 668 | venv、`uv tool`、pipx | 不默认 `--break-system-packages`；不往系统 Python 装项目依赖 |
| 团队或 CI 已锁定其他工具 | 跟随项目 | 不因个人偏好改工具链；迁移单独评估 |

## 故障分流

| 现象 | 先查 | 动作 |
| --- | --- | --- |
| `uv` 找不到 | PATH、安装来源、`python -m uv` 是否可用 | 已有二进制则补 PATH；没有才安装；新开终端 |
| `uv` 与 `python -m uv` 版本不同 | `where.exe uv` / `command -v uv` | 找到两套来源，保留一套；移除或调整 PATH |
| 解释器不对 | `uv python find`、`.python-version`、`--python` | 固定版本或显式指定；不要重装 uv |
| 锁文件过期 | `uv lock --check`、`--locked` 报错 | 确认 `pyproject.toml` 变更后 `uv lock`；不删锁绕过 |
| 环境不同步 | `uv sync --check` | `uv sync`；`uv run` 默认不清理多余包 |
| 磁盘占用像重复 | 缓存与 venv 是否同盘、硬链接数 | 同盘才链接；跨盘会复制；不手工删缓存 |
| PEP 668 / 系统 Python 拒绝安装 | 当前解释器是否系统管理 | 新建 venv、`uv tool` 或 pipx；不默认破坏系统保护 |
| 索引、镜像、代理、构建失败 | 下载链路与构建日志 | 转 [network-access](../network-access/SKILL.md) 的依赖下载与安装分诊 |
| 工具环境被手工改坏 | `uv tool list`、工具目录 | 重新 `uv tool install`，不要 pip 修补 |

更细的诊断命令与平台差异见[排障](references/troubleshooting.md)。

## 验收清单

- [ ] `uv --version` 有输出；`where.exe uv` / `command -v uv` 只指向计划保留的一套。
- [ ] `uv cache dir` 在预期磁盘；缓存与项目 venv 同盘，或已知会复制。
- [ ] 项目有 `pyproject.toml`、`uv.lock`、`.python-version`；`.venv/` 未入库。
- [ ] `uv lock --check` 与 `uv sync --check` 通过。
- [ ] `uv run python -V` 与 `.python-version` 一致。
- [ ] 需要全局工具时，`uv tool list` 可见，且没有把项目依赖装进 tool 环境。
- [ ] 新开终端仍能找到 `uv`；PATH 变更已记录，回退方式明确。

## 按需读取

| 条件 | 入口 |
| --- | --- |
| 需要平台安装命令、PATH 写法、升级/卸载与验收 | [安装与 PATH](references/install-and-path.md) |
| 多份安装、解释器、锁文件、缓存、PEP 668 的具体诊断 | [排障](references/troubleshooting.md) |
| 索引、镜像、代理、下载失败与构建失败 | [network-access](../network-access/SKILL.md) |
| 脚本结构、参数、编码与 PEP 723 写法 | [scripting-best-practices](../scripting-best-practices/SKILL.md) |
| 先盘点本机已有运行时与包管理器 | [resource-inventory](../resource-inventory/SKILL.md) |
| 工具形态选型、打包与分发 | [lightweight-app-builder](../lightweight-app-builder/SKILL.md) |

## 依据与维护

- [uv 安装](https://docs.astral.sh/uv/getting-started/installation/)：standalone、pipx、pip、Scoop、winget、Homebrew 与升级方式。
- [uv 项目](https://docs.astral.sh/uv/guides/projects/)：项目结构、`.python-version`、`uv.lock`、`uv add` 与 `uv run`。
- [锁定与同步](https://docs.astral.sh/uv/concepts/projects/sync/)：`--locked`、`--frozen`、`uv lock --check`、`uv sync` 的精确/非精确行为。
- [缓存](https://docs.astral.sh/uv/concepts/cache/)：全局缓存、同文件系统链接、`uv cache prune` 与 CI 缓存。
- [工具](https://docs.astral.sh/uv/concepts/tools/)：`uvx` 与 `uv tool install` 的隔离、升级和 PATH。
- [Python 版本](https://docs.astral.sh/uv/concepts/python-versions/)：`uv python install/pin/find` 与解释器发现。

2026-11-19 按 uv 0.13.9 核对；版本与命令会变化，执行前用 `uv --version` 和 `uv <command> --help` 复核。维护时同步更新 README 索引行并跑仓库校验脚本。
