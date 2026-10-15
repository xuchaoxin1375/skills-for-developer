# Python、Node.js 与 conda 依赖下载

网络路线、Windows/*nix 代理与错误分流见 [network-access.md](network-access.md)。本文件补充包管理器的配置与验证边界；国内镜像为候选，引用前用任务需要的包名、版本和平台核验，海外生产按实际执行位置优先验证官方源。conda 走 channel 映射语义（channel 名 → 镜像 URL），不是 URL 替换，以 `conda config --show channels` 的实际解析为准。

## 先定位下载阶段

| 阶段 | Python | Node.js | 核验内容 |
| --- | --- | --- | --- |
| 索引/元数据 | PyPI Simple API、包版本和 wheel 标签 | registry 元数据、版本及 dist 信息 | 目标包版本是否存在，私有包路由是否正确 |
| 实际包文件 | wheel/sdist，可能由独立文件域名托管 | tarball，可能来自锁文件中的绝对 URL | 文件可取回、格式正确、哈希/完整性符合预期 |
| 构建或安装时额外下载 | 隔离构建依赖、uv 管理的 Python、Git/VCS 依赖 | 生命周期脚本、Playwright 浏览器、Electron/原生组件、Corepack 下载包管理器 | 实际失败主机、该下载器的代理与镜像支持 |

镜像首页或一次版本查询成功只覆盖前段。`No matching distribution`、peer dependency 冲突、编译失败或 install script 退出不直接等于网络故障；先检查解释器/平台、包约束、构建工具及失败日志中的阶段。

## 配置范围与临时覆盖

优先检查项目声明的包管理器（如 `packageManager`、锁文件）及已安装版本，沿用现有工具。无锁文件、无 `packageManager` 约束且可自由选择时，Node.js 优先用 pnpm：安装用 `pnpm install`（有 `pnpm-lock.yaml` 时加 `--frozen-lockfile`），单次执行用 `pnpm dlx <pkg>` 代替 `npx <pkg>`，全局工具用 `pnpm add -g <pkg>`；有锁文件或已声明工具时沿用现有工具，不删锁换管理器。单次参数优先于修改用户级配置；长期项目设置需要写明用途和适用环境，不能把本机代理地址提交进项目。

| 工具 | 任务级源配置 | 适用边界 |
| --- | --- | --- |
| pip | `python -m pip ... --index-url "<已核验simple源>"` 或 `PIP_INDEX_URL` | 使用目标解释器；Simple 源包含 `/simple`，检查已有 extra index/find-links 配置 |
| uv | `--default-index "<已核验simple源>"` 或 `UV_DEFAULT_INDEX` | uv 不读取 pip 的配置文件；项目附加索引和源绑定仍可能优先，先检查实际配置 |
| npm | `npm ci --registry="<已核验registry>"` 或 `npm_config_registry` | 仅默认 registry；项目 `.npmrc`、scope 绑定、锁文件和脚本的 URL 需分别检查 |
| pnpm | `pnpm install --frozen-lockfile --registry="<已核验registry>"` | 核对具体版本和子命令参数；配置文件职责随大版本变化 |
| Yarn Classic（1.x） | 安装命令的 `--registry` 或版本支持的配置 | 不套用现代 Yarn 的 `.yarnrc.yml` 配置 |
| 现代 Yarn | 进程变量 `YARN_NPM_REGISTRY_SERVER` 或项目 `.yarnrc.yml` 的 `npmRegistryServer` | 不能假定 `.npmrc` 的 registry/代理配置生效，scope 用对应 Yarn 配置 |
| conda | `CONDA_CHANNELS="<channel>[,<channel>]"`（逗号分隔，只影响本次进程） | custom_channels 映射与 nodefaults 仍按合并后配置生效，先 `conda config --show channels` 与 `--show-sources` 核对实际解析 |

已核验的候选示例：Python `https://mirrors.ustc.edu.cn/pypi/simple`，Node.js `https://registry.npmmirror.com`，conda channel 映射如 `conda-forge → https://mirrors.pku.edu.cn/anaconda/cloud`、`bioconda → https://mirrors.ustc.edu.cn/anaconda/cloud`。这些地址在小包观测中可用，不承诺所有包、平台或日期均可用；官方回退分别为 `https://pypi.org/simple`、`https://registry.npmjs.org` 与 `repo.anaconda.com`。

下面只展示当前任务终端的源变量；任选所需工具，替换占位符后执行。关闭专用终端即可结束覆盖；复用已有终端时保存并恢复原值。代理仍按网络访问参考配置，不能由源变量代替。

```bash
export PIP_INDEX_URL='<已核验simple源>'
export UV_DEFAULT_INDEX='<已核验simple源>'
export npm_config_registry='<已核验registry>'
export YARN_NPM_REGISTRY_SERVER='<已核验registry>'
export CONDA_CHANNELS='<channel>[,<channel>]'
```

```powershell
$env:PIP_INDEX_URL = '<已核验simple源>'
$env:UV_DEFAULT_INDEX = '<已核验simple源>'
$env:npm_config_registry = '<已核验registry>'
$env:YARN_NPM_REGISTRY_SERVER = '<已核验registry>'
$env:CONDA_CHANNELS = '<channel>[,<channel>]'
```

CMD 对应 `set "变量名=值"`；Windows 调用 npm/pnpm 时可写 `npm.cmd`/`pnpm.cmd`，避免 PowerShell 脚本 shim 受执行策略拦截。不要为此永久放宽系统执行策略。

当前 pnpm 文档区分 `pnpm-workspace.yaml` 与 `.npmrc`：后者主要负责 registry/auth，其他设置按当前版本文档处理。不同子命令也可能接受不同参数；例如安装命令的 `--fetch-timeout` 不能直接复制到 `pnpm view`。先看实际命令帮助，诊断子命令缺少超时参数时由调用方约束进程期限。

## conda / miniforge

- 配置按安装级、用户级合并生效，用 `conda config --show-sources` 定位每项来源。常见国内做法：`nodefaults` 去掉官方 `defaults`，`custom_channels` 把 `conda-forge`、`bioconda` 等指向镜像；`show_channel_urls: true` 便于审计实际来源。
- 任务级覆盖用 `CONDA_CHANNELS`（逗号分隔，只影响本次进程）；`CONDARC` 指定文件变量在本机 conda 26.3.2 实测未改变有效 channels，不采用。
- conda 读取 `HTTP(S)_PROXY` 环境变量（黑洞代理下报 `ProxyError` 已验证）；未配 `proxy_servers` 时先确认环境代理是否实际被使用，不假定直连或代理。
- 探针用小包元数据查询，不做完整安装：`conda search --override-channels -c conda-forge <包名>`，看 channel 列与返回耗时；私有 channel 与扫包工具的源不在此覆盖。

## 回退、私有包与锁文件

- 镜像缺包或同步滞后时，对同一包约束显式切换官方源再试，并记录来源。pip `--extra-index-url` 将多处候选一起比较，不提供主备优先级；混入私有包可能导致依赖混淆，应维持私有源绑定。
- uv 默认 `first-index` 限制在首个包含包的索引中选版本；镜像已有包但缺少目标版本时，不能假定会自动查询后续索引。401/403 通常也会中止索引搜索，先诊断原因，不默认改为 `unsafe-best-match` 或忽略认证错误。
- 私有 scope、Git/VCS 依赖和直接 URL 不随默认 registry 一起切换；令牌保持与正确域名/源绑定，诊断只报告脱敏 host 和配置层级，避免完整转储配置中的凭据。
- 锁文件可能固定 registry、tarball、索引或 Git commit。换镜像后仍访问旧主机时先定位固定来源；确需迁移来源时把锁文件差异作为可审阅变更，保留版本与校验，不静默重写全部 URL。
- 验证现有项目沿用 `uv sync --locked`、`npm ci`、`pnpm install --frozen-lockfile`、现代 `yarn install --immutable` 等适用命令；因源变化或 manifest 不一致失败时诊断差异，不删除锁文件或换包管理器来规避。
- 只有缓存损坏/哈希异常有证据时才针对性清理；网络慢不默认清空缓存。证书错误配置受信任 CA（按客户端支持使用 CA 文件或系统证书库），不关闭 TLS/完整性校验；uv 的证书选项先核对本地版本。

## 并发、超时与重试

包管理器自身可能同时发出多个请求。限制 Agent 的命令数量不能替代内部下载限制；单请求超时也不等于整个依赖安装的总期限。按代理容量和实际失败降低并发，设有限重试，任务总期限由调用方控制，避免外层再次叠加整轮安装重试。

| 工具 | 可核对的设置 | 单位与范围 |
| --- | --- | --- |
| pip | `--timeout` / `PIP_TIMEOUT`，`--retries` / `PIP_RETRIES` | 超时为秒，属于请求/socket 等待；不是安装总期限 |
| uv | `UV_HTTP_CONNECT_TIMEOUT`、`UV_HTTP_TIMEOUT`、`UV_HTTP_RETRIES`、`UV_CONCURRENT_DOWNLOADS` | 连接/读取超时为秒；设置的引入版本不同，先核对本地支持 |
| npm | `--fetch-timeout`、`--fetch-retries`、`--maxsockets` | 超时为毫秒；maxsockets 是每 origin 连接上限，不等于全局请求频率 |
| pnpm | 安装命令的 `--fetch-timeout`、`--network-concurrency`，版本对应的 `fetchRetries` | 超时为毫秒；CLI 支持以具体子命令帮助为准 |
| 现代 Yarn | `httpTimeout`、`httpRetry`、`networkConcurrency`，及对应 `YARN_*` 变量 | 超时类型/写法按当前版本文档核对，不能直接抄 npm 参数 |

诊断起点可用 15～30 秒请求等待、至多 1 次工具内部重试、2～4 个可配置下载并发；大包与慢线路按进展调整，确认 429/403 限流时优先遵守服务端冷却，不能靠多次整轮重装或镜像轮询解决。

## 包源之外的下载

- uv 管理的 Python 运行时下载不由 PyPI 镜像控制；按受支持的官方渠道/内部镜像核验 `UV_PYTHON_INSTALL_MIRROR`，或使用任务允许的已有解释器。
- Playwright 浏览器下载读取其自身 `HTTPS_PROXY`、`PLAYWRIGHT_DOWNLOAD_HOST` 等配置，目标镜像须匹配版本与平台。`PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT` 虽名为 connection，官方文档说明它控制无数据进展的空闲等待，不是硬连接/总期限。
- Electron、原生预编译包、node-gyp 头文件、Corepack 和 Git 依赖按各自下载器检查实际目标与代理；不要假定 npm registry 覆盖这些下载，也不硬编码未经核验的第三方专用镜像。
- `--ignore-scripts` 可帮助判断失败是否在生命周期脚本；诊断跳过脚本不代表依赖安装或应用已完成，正常交付仍需恢复必要步骤并验证运行。

## 验证与依据

先查一个所需固定版本的元数据，再用真实包管理器取回实际包文件；临时目录与独立缓存可减少环境修改。pip 可用 `download --no-deps --only-binary=:all:` 做已有 wheel 的小包探针；npm 可用 `pack --ignore-scripts` 做 registry 包文件探针。它们只验证指定目标，不代替完整依赖图和安装脚本验收。

Windows 的 pip/npm 小包镜像与官方源下载及哈希对照、conda 北大镜像 search 探针见 [local-observations.md](local-observations.md)。uv 参数已核对本地帮助，pnpm 已验证元数据查询；Yarn 与其他平台仅作官方文档核对，不宣称安装实测。

官方文档于 2026-10-10 读取核对；规则落地前结合安装版本复查：

- [pip 配置](https://pip.pypa.io/en/stable/topics/configuration/)与 [pip install](https://pip.pypa.io/en/stable/cli/pip_install/)：生效层级、多索引与依赖混淆。
- [uv 索引](https://docs.astral.sh/uv/concepts/indexes/)与 [环境变量](https://docs.astral.sh/uv/reference/environment/)：源策略、超时、并发与运行时镜像。
- [npm 配置](https://docs.npmjs.com/cli/v11/using-npm/config)：registry、代理、请求与证书参数；引用版本与本机 npm 主版本匹配。
- [pnpm 设置](https://pnpm.io/settings)与 [网络设置](https://pnpm.io/settings/network)：配置文件职责、超时与并发。
- [现代 Yarn 配置](https://yarnpkg.com/configuration/yarnrc)：registry、代理与 HTTP 设置。
- [Playwright 浏览器](https://playwright.dev/docs/browsers)：独立下载源、代理、CA 与空闲超时。
