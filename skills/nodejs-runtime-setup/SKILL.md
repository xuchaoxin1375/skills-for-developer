---
name: nodejs-runtime-setup
description: >
  Windows、Linux、macOS 上安装 Node.js 运行时、切换版本与安装 pnpm 的选型与验收。
  按单版本、多版本、团队锁版本三类场景给出默认方案（官方安装器与 winget、fnm、nvm-windows、Volta），
  说明国内网络下二进制镜像、registry 与独立下载的边界，以及各方式的失败模式与回退；
  覆盖 PATH 冲突、符号链接权限、Corepack 随 Node 25 移除后的 pnpm 安装、EPERM 与全局 bin 排障。
  项目依赖安装与镜像选路归 network-access，本机环境盘点归 resource-inventory。
---

# Node.js 运行时与 pnpm 安装

## 适用范围

安装或更换 Node.js 运行时、在多个版本间切换、安装 pnpm 时加载。产出是**一套明确的安装方式与可验证的验收结果**，不是命令清单；命令按需读[平台安装命令](references/install-commands.md)。

不在本 skill：

- 项目依赖从哪里下载、镜像与代理怎么选，按 [依赖下载](../network-access/references/dependency-downloads.md)。
- 本机已有哪些运行时、包管理器与代理入口，按 [resource-inventory](../resource-inventory/SKILL.md)。
- 包管理器对项目的影响（锁文件、workspace）按项目现有声明处理，不删锁、不换管理器。
- 脚本本身的编写规范，按 scripting-best-practices。

## 最短执行路径

1. **先探测再装**：看 `node -v`、`npm -v`、`pnpm -v` 与 PATH 优先级（Windows `where.exe node`，*nix `command -v node`），再读项目的 `package.json`（`engines`、`packageManager`）与锁文件。已有项目沿用现有工具链，不为“统一”重装。
2. **按场景选一套**：从场景表取默认方案。机器上已存在多种安装时，先决定保留哪一套，不叠加。
3. **安装**：按[平台安装命令](references/install-commands.md)执行；改 PATH、装全局包、动系统策略前先说明影响。
4. **验收**：跑验收清单。失败项按“可靠性与失败模式”定位，不重复安装。

## 场景默认

| 场景 | 默认方案 | 取舍 |
| --- | --- | --- |
| 只用一个版本、新手、或要求与教程一致 | 官方安装器：Windows MSI 或 `winget`，macOS 官方 pkg；Linux 用 fnm 而非发行版旧包 | 路径与卸载流程标准；升级靠覆盖安装或包管理器 |
| 多项目需要不同版本 | fnm | 原生跨平台、切换快，按 `.node-version` / `.nvmrc` 自动切换；Windows 需符号链接权限 |
| 已有 nvm 习惯或团队统一要求 | Windows 用 nvm-windows，*nix 用 nvm-sh | 命令熟悉；两代实现和 v1/v2 配置命令不同，不混用文档 |
| 团队要求 Node 与包管理器版本随仓库锁定 | Volta，或 fnm + `engines` + `packageManager` | 新成员无需手工切换；`engines` 只声明范围，不会自动切版本 |
| 需要 Linux 工具链、CI 与 Linux 一致 | WSL2 内的 Node | 与 Windows 原生隔离；不要把 Windows 项目放在挂载盘跑重型构建 |

**只保留一套主导安装**。MSI、Scoop、fnm 的 `system` 条目、nvm 的当前版本都会写 PATH；保留多套时 `node -v` 只命中第一个，看起来像“切换没生效”。出现这种情况先查实际路径，不反复重装。

## 版本基线

版本号会变，正文不写死。判断顺序：查官方发布页确认目标版本处于 Active LTS 还是 Maintenance，再看是否满足项目 `engines`。奇数版不进 LTS，不用于长期项目；已 EOL 的版本不用于新环境。`winget search OpenJS.NodeJS` 与 `fnm ls-remote` 可看当前可安装版本，以实际输出为准。

## pnpm 安装

Node.js **25 起不再分发 Corepack**，`corepack enable` 在 26 上直接报找不到命令。按环境选：

| 方式 | 适用 | 注意 |
| --- | --- | --- |
| `npm i -g pnpm` | 已有 Node，Windows 首选 | pnpm 官方在 Windows 上推荐这种方式，避免独立脚本被 Defender 拦截 |
| 独立安装脚本 | 没有 Node，或想脱离 Node 升级 | pnpm 12 起为原生可执行文件，装完不需要 Node；Windows 仍有 Defender 拦截风险 |
| `npx get-pnpm` | Node 22.13+ | 只用于安装，之后运行 pnpm 不再需要 Node |
| Corepack | Node 24 及更早 | Node 25+ 无此命令；`COREPACK_NPM_REGISTRY` 只影响它自己下载包管理器的来源 |

- 项目已用 `packageManager` 锁定 pnpm 版本时保留该字段；安装方式由执行环境决定，不改写项目声明。
- **全局工具不跟 pnpm 优先**：pnpm 的全局 bin 默认不在 PATH，`mmdc` 之类用 `npm i -g`。
- pnpm 复用 npm 的 `.npmrc`，registry 通常不必重复设置；Yarn 2+ 改用 `.yarnrc.yml`，不要混用。
- Windows 无开发者模式时，pnpm 对项目目录退化为 junction，普通安装依赖不需要提权；项目 `postinstall` 直接调用 `symlinkSync(..., "dir")` 仍可能 `EPERM`，优先改脚本或为当前用户开权限。
- pnpm 命令异常时先 `where.exe pnpm.*` / `command -v pnpm`，确认没有旧版 JS 实现排在前面，清理后再装。

## 网络与可靠性

下载分成三条独立链路，只改一条通常仍慢：

| 链路 | 典型内容 | 处理 |
| --- | --- | --- |
| Node 二进制 | MSI、ZIP、fnm / nvm 安装的版本 | fnm 用 `FNM_NODE_DIST_MIRROR`，nvm-windows 用 `node_mirror`；镜像同步滞后时该版本 404，临时回退官方源 |
| npm registry | `npm install`、`pnpm install` 取包 | 按 network-access 的依赖下载配置；`.npmrc` 的 registry 不影响二进制安装 |
| 独立下载器 | pnpm 安装脚本、Electron / Puppeteer 制品、GitHub Release | 各自有来源与代理设置；装包管理器的渠道与装依赖的渠道互不相干，优先用包管理器分发 |

**可靠性判定**：

| 方式 | 失败模式 | 恢复 |
| --- | --- | --- |
| 官方安装器 / 包管理器 | 包清单滞后、下载中断 | 换官网原包或另一包管理器；安装包比对官方 `SHASUMS256.txt` |
| fnm | 缺少符号链接权限（`os error 1314`）、镜像落后 | 开启开发者模式或授予“创建符号链接”；换镜像或官方源 |
| nvm-windows | v1 需管理员、安装路径含空格或中文导致 `nvm use` 失败 | 改用 v2 或换简单路径；不照抄另一代的配置命令 |
| Scoop | 与 MSI / fnm 抢 PATH，升级替换 `current` 目录 | `scoop reset`；长期多版本改用 fnm |
| pnpm 独立脚本 | Defender 拦截、旧版残留遮蔽 | 加 Defender 排除项或改用 `npm i -g pnpm`；清理残留 shim |

- 镜像只解决速度，不解决可信度：首次安装至少核对一次官方哈希；镜像缺校验文件时从官方取。
- 镜像滞后导致装不到目标版本就明确回退官方源，不把某个镜像写死为唯一来源。
- 企业网络需要代理时，npm 用 `proxy` / `https-proxy`，Node 24.5+/22.21+ 的 `http`、`https` 与 `fetch` 支持 `NODE_USE_ENV_PROXY=1` 读取 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`；代理只解决通路，不改变包来源。
- 不关闭 TLS 校验来“解决”证书错误；企业代理替换证书时配置受信任 CA（`NODE_EXTRA_CA_CERTS`、npm `cafile` 或系统根证书）。
- Windows 上 `npm.ps1 cannot be loaded` 是 PowerShell 执行策略拦截，不是 npm 损坏：当前用户设为 `RemoteSigned` 后新开终端；组策略锁定时找管理员，详见 shell-pitfalls 的 PowerShell 部分。

## 验收清单

- [ ] `node -v`、`npm -v` 有输出，版本在计划的支持线内。
- [ ] `where.exe node` / `command -v node` 只指向计划保留的那一套安装。
- [ ] `npm config get prefix` 在用户目录，`npm i -g` 不需要管理员。
- [ ] `pnpm -v` 正常，且 PATH 中只有一个 pnpm 来源。
- [ ] 多版本工具能看到目标版本，项目目录的版本文件能触发自动切换。
- [ ] 手工下载的安装包经过哈希校验，或来自可信的包管理器渠道。
- [ ] registry 可达：`npm view <包名> version` 能返回结果。

## 按需读取

| 条件 | 入口 |
| --- | --- |
| 需要平台具体命令、镜像地址、profile 写法与校验命令 | [平台安装命令](references/install-commands.md) |
| 依赖安装慢、镜像选择、代理与超时 | [依赖下载](../network-access/references/dependency-downloads.md) |
| 依赖安装失败、版本冲突、无匹配 wheel、PEP 668 或构建失败 | [依赖安装失败分诊](../network-access/references/dependency-install-recovery.md) |
| 先盘点本机已装的运行时与包管理器 | [resource-inventory](../resource-inventory/SKILL.md) |

## 依据与维护

- [Node.js Releases](https://nodejs.org/en/about/previous-releases)：LTS 与 Maintenance 的时间线，版本基线以它为准。
- [Node.js 下载页](https://nodejs.org/en/download)：官方安装器与 `SHASUMS256.txt`。
- [Corepack 移除说明](https://github.com/nodejs/node/commit/570d8d3f10)：Node.js 25 起不再分发 Corepack。
- [pnpm 安装](https://pnpm.io/installation)：pnpm 12 原生可执行文件、Windows 推荐 npm、`npx get-pnpm` 的 Node 版本要求。
- [fnm](https://github.com/Schniz/fnm)：Windows 符号链接要求、`FNM_NODE_DIST_MIRROR`、`--use-on-cd`。
- [nvm-windows 镜像](https://docs.nvm-windows.com/features/mirrors/)：v2 `nvm config set` 与 v1 独立命令的差异。
- [Node.js 企业网络配置](https://nodejs.org/en/learn/http/enterprise-network-configuration)：`NODE_USE_ENV_PROXY`、`NODE_USE_SYSTEM_CA` 的适用版本。

官方页面于 2026-11-06 读取核对；版本号、包名与镜像地址会变化，执行前用 `node -v`、`fnm --version`、`winget search` 或镜像目录确认。维护时更新本文件与 README 索引行，并按仓库校验脚本复跑。
