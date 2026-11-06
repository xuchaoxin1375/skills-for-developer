# 依赖安装失败分诊

用于 `pip install`、`uv pip install`、`npm install`、`pnpm install`、`conda install` 失败、冲突、卡住或超时。先按错误定位阶段，再只改一个变量；镜像地址、代理与超时参数仍按[依赖下载](dependency-downloads.md)配置，本文件不重复那张配置表。

## 先读错误，不先重跑

安装失败可以按阶段归类，多数错误能直接落到其中一段。把完整错误、命令、解释器和包管理器版本一起留下，再决定动作；同一命令原样重跑通常只会重复等待。

| 阶段 | 典型信号 | 先确认 | 不要 |
|---|---|---|---|
| 解释器与环境 | `externally-managed-environment`、`Permission denied`、`No module named pip`、包装到了另一个 Python | 实际解释器、是否虚拟环境、pip 是否属于该解释器 | 直接 `--break-system-packages`、`sudo pip` 或换一个 `pip` 命令 |
| 解析 | `ResolutionImpossible`、`conflicting dependencies`、`ResolutionTooDeep`、反复下载同一包的多个版本 | 冲突链、顶层版本约束、当前环境已有的包 | 换镜像、反复 `--upgrade`、用 `--no-deps` 绕过 |
| 可用性 | `No matching distribution`、`Could not find a version` | 目标版本的 `Requires-Python`、平台 wheel、索引是否真的包含该版本 | `--ignore-requires-python`、假定镜像故障 |
| 下载 | `ReadTimeout`、`ConnectionReset`、`SSLError`、502/503/504、长时间无进展 | 失败主机、是索引还是包文件、是否有下载进展 | 清空缓存、整轮重装、连续切换多个镜像 |
| 构建 | `Failed building wheel`、缺 `gcc`/头文件、`No module named distutils`、`BackendUnavailable` | 是否有匹配 wheel、构建工具链和 Python 版本 | 关闭 TLS、盲目 `--no-build-isolation` |
| 安装后 | `ModuleNotFoundError`、命令找不到、`pip check` 报破损 | 当前解释器、脚本入口、包的实际版本 | 仅凭退出码 0 判定成功 |

`No matching distribution` 不是“下载慢”。它表示当前索引、Python 版本或平台没有可安装的分发；单纯换更快的镜像不会改变可用性，先确认是索引缺版本还是 Python/平台不匹配。

## 零副作用预检

先确认环境和解析结果，再决定是否下载安装。以下命令对应当前 `python`；目标环境不是 PATH 上的解释器时，换成它的绝对路径。

```bash
python -c "import sys; print(sys.executable); print(sys.version); print('venv' if sys.prefix != sys.base_prefix else 'base')"
python -m pip --version
python -m pip config debug
python -m pip check

# 只解析、不写环境；报告记录最终选择的版本和来源
python -m pip install --dry-run --ignore-installed --report pip-report.json "<需求>"
```

`--dry-run` 仍可能下载元数据或 wheel 来解析，不是零流量操作；`--report` 用来留下最终选择，便于对比两次尝试。只查某个固定版本有没有可取的 wheel 时，用 `pip download --no-deps --only-binary=:all: -d <临时目录> "<包==版本>"` 做小探针，细则见[依赖下载](dependency-downloads.md#验证与依据)。

## Python 解析冲突

冲突发生在依赖图里，不是网络故障。pip 的 `ResolutionImpossible` 会列出 `The conflict is caused by:`，逐行看是哪个父包限制了这个公共依赖，以及哪些限制来自你自己的固定版本。

按成本从低到高尝试，每次只改一项并重新解析：

1. **换干净环境复现**：新建 venv，只装目标包。若能成功，冲突来自原环境已有的包；把任务隔离在这个 venv，不要继续在原环境里拆包。
2. **审计顶层约束**：删掉不必要的精确 pin，只保留真正需要固定的包；让 pip 为其余包选择兼容版本。
3. **给公共依赖加约束**：用 `constraints.txt` 或命令行给冲突的传递依赖一个双方都接受的范围。约束不会主动安装该包，只限制已出现的版本。
4. **一起升级冲突双方**：`pip install --upgrade <a> <b>`，而不是只升级一侧。默认的 `only-if-needed` 不会无故升级全部依赖；只有确实要整体前移时才用 `eager`。
5. **确认无解**：换替代包、拆分环境，或如实报告不可兼容的组合。不要为了让安装“成功”而引入未满足的依赖。

`--no-deps` 只用于诊断“哪个包导致导入失败”，不能当作交付状态；`--force-reinstall` 只在有缓存损坏、文件损坏或哈希异常证据时使用，不解决版本冲突。

需要更快得到解析结论时，可用 uv 只做解析预演，不改变项目现有工具链：

```bash
uv pip compile requirements.in -o requirements.txt
```

已有 `uv.lock` 的项目用 `uv lock` / `uv sync --locked`，不要同时用 pip 修改同一个环境。uv 同样可能为了解析而构建旧版本源码；失败时仍按构建阶段处理。

## 无匹配 wheel 与构建失败

| 判断 | 动作 |
|---|---|
| 目标版本没有当前 Python/平台的 wheel | `pip install --only-binary=:all: "<包==版本>"` 验证；确认后换支持的解释器或换有 wheel 的版本 |
| 有 wheel，但默认选了更新的源码包 | 用 `--prefer-binary`，或显式指定有 wheel 的版本 |
| 源码包需要编译 | 先补系统构建依赖：编译器和 Python 开发头文件；Linux 常见是 `build-essential` 加对应库的 `-dev` 包，Windows 装 Build Tools，macOS 装 Xcode Command Line Tools |
| 旧版本在新 Python 上构建失败 | 提高下界或加约束避开旧版本；必要时换旧 Python。`distutils` 在新 Python 已移除，不能靠重试解决 |
| 构建后端缺少运行时依赖 | 只有确认构建依赖已全部预装、且项目确实要求时，才用 `--no-build-isolation`；它不是通用修复 |

构建失败先找“不构建”的路线（二进制 wheel、较新版本、受支持的 Python）。补工具链是第二步；不要一上来就关闭隔离或证书校验。

## 环境与权限

- `externally-managed-environment` 是 PEP 668 的保护：系统 Python 由发行版管理。新建 venv；命令行工具用 `uv tool install` 或 pipx；系统包用发行版包管理器。`--break-system-packages` 只作为明确知情后的最后手段，不作为默认修复。
- 先确认 `python -m pip` 与 `python` 是同一个解释器。PATH 上有多个 Python 时，`pip install` 成功但目标脚本导入失败，通常是装错了环境。
- `--user` 也不是 PEP 668 的绕过方式；它同样会被标记为外部管理。
- 权限错误先看目录归属和虚拟环境位置；不要用 `sudo` 改变用户级 Python 环境的归属。

## 下载慢、超时与镜像

先确认失败在索引元数据、包文件、构建期额外下载还是独立制品下载；四者的源不同，换包索引只影响前两者。选路、代理和镜像候选按[依赖下载](dependency-downloads.md)与[网络诊断](network-access.md)执行，这里只保留安装侧的顺序：

1. 选定一个已核验的主源，保留官方源作为一次回退；不要同时挂多个公共镜像“赛跑”。
2. 用固定版本的小包探针确认主源确有该版本；没有就换官方源一次，并记录实际来源。
3. 给请求设有限超时与重试：pip 的 `--timeout` / `--retries` 起点与 uv、npm、pnpm 的变量见[依赖下载](dependency-downloads.md#并发超时与重试)。这是单请求预算，不是整个安装的总期限。
4. 大包看进展而不是套小页面阈值；有持续下载进展就让它在任务总预算内跑完，不因“慢”反复杀掉重来。
5. 缓存默认复用；只有缓存损坏、哈希不符或来源切换导致旧响应干扰时，才做针对性刷新。网络慢本身不是清空缓存的理由。
6. 私有包、Git/VCS 和直接 URL 不随公共镜像切换；不要把私有源和公共 `--extra-index-url` 混在一起来“顺便”找依赖。

镜像缺版本、同步滞后或元数据陈旧时，只对同一约束回退官方源一次。解析冲突、构建失败和权限错误不会因为换源而消失。

## 减少无效尝试的预算

下面是建议默认值，不是跨环境的硬指标；任务有更严格期限或已知慢线路时，在开始前改预算并说明。

| 动作 | 建议上限 | 停止或改路条件 |
|---|---|---|
| 原样重跑同一失败命令 | 0 次 | 瞬时网络错误交给工具内置重试，不手工叠加整轮安装 |
| 同一源/同一代理路线重试 | 工具内部重试之外再跑 1 次 | 已改超时/重试参数，或确认是瞬时错误 |
| 切换镜像或索引 | 1 次 | 主源缺版本或不可达 → 官方源一次 → 再按 network-access 改代理/直连 |
| 解析策略调整 | 每次只改一项 | 先 `--dry-run` 或 `uv pip compile`；没有新证据不重复同一组约束 |
| 全量重装 | 仅在损坏证据下 | 冲突、慢、权限错误都不构成全量重装理由 |
| 总安装期限 | 任务开始时设定 | 大包按进展续期；超期报告实际进度，不无限等待 |

一条可复用的顺序是：**预检 → 解析预演 → 一次安装 → 验证**。失败发生在哪一段，就只改那一段；不要把“换源、升级、重装、清缓存”打包成一次尝试，否则无法判断哪一步有效。

## 安装后验证

- `python -m pip check` 返回 0，或明确列出仍存在的破损依赖。
- 用目标解释器导入一次，并打印实际版本；需要命令行时再跑一次 `<命令> --version`。
- 跑任务真正依赖的最小路径，例如渲染一张图、启动一次浏览器或调用一次 API；安装命令退出 0 不等于能力可用。
- 保留本次解析报告或 `pip freeze` 的关键行，以及实际使用的源主机（不记录凭据）。

## Node.js 与 conda

- **npm `ERESOLVE`**：先读冲突双方要求的版本，用 `npm ls <包>` 确认现有树；优先对齐 peer 依赖或升级上层包。`--legacy-peer-deps`、`--force` 会跳过检查，只在明确接受风险时使用；长期修复用 `overrides` 并留下锁文件变更。
- **pnpm**：用 `pnpm why <包>` 查来源，`pnpm.overrides` 处理传递依赖；有锁文件时保持 `--frozen-lockfile`，不要为了绕过冲突删锁。
- **conda**：优先保持 channel 优先级与 `libmamba` 求解器；同一环境里不要用 conda 和 pip 反复安装同一个包。channel 映射与镜像配置见[依赖下载](dependency-downloads.md#conda--miniforge)。

## 依据

以下页面于 2026-11-06 读取；命令和默认值随版本变化，执行前用本地 `--help` 核对。

- [pip install](https://pip.pypa.io/en/stable/cli/pip_install/)：`--dry-run`、`--report`、`--only-binary`、`--prefer-binary`、`--no-build-isolation`、`--break-system-packages`。
- [pip 依赖解析](https://pip.pypa.io/en/stable/topics/dependency-resolution/)：回溯、`ResolutionImpossible`、约束与放宽版本的建议。
- [pip check](https://pip.pypa.io/en/stable/cli/pip_check/)：已安装依赖的一致性检查。
- [uv 锁定环境](https://docs.astral.sh/uv/pip/compile/)与[构建失败](https://docs.astral.sh/uv/reference/troubleshooting/build-failures/)：只解析预演、构建工具链与约束。
- [PEP 668](https://peps.python.org/pep-0668/)：外部管理环境与虚拟环境优先。
