# 本机网络观测

仅记录当前工作机器的带日期事实，不作为其他机器、平台或生产服务器的默认配置。端口、协议、路由和公共服务状态都可能变化，任务前重新核验。

## 2026-10-09 历史记录

- 本地代理 `http://localhost:10808` TCP 可达，经代理取 `https://pypi.org/simple/` 返回 200。
- pip 已配 USTC（`%APPDATA%\pip\pip.ini`）；uv 当时无用户级镜像配置，依靠代理访问官方源。
- 当时 `HTTP_PROXY`/`HTTPS_PROXY` 已设置；这些观测不证明后续请求或其他客户端仍使用同一路线。

## 2026-10-10 目标核验

执行环境：Windows PowerShell 调用 `curl.exe`。`10808` 和 `7897` 存在 TCP 监听，仅验证 `http://127.0.0.1:10808` 的 HTTP 代理协议；未核验 `7897` 协议或出口。`HTTP_PROXY`/`HTTPS_PROXY` 已配置，`ALL_PROXY`/`NO_PROXY` 未配置；没有输出代理凭据。

原始目标：`https://raw.githubusercontent.com/hunshcn/gh-proxy/master/README.md`。使用连接超时 5 秒；直连总期限 12 秒、代理 20 秒、加速 15 秒；无自动重试。

| 路线 | 设置 | HTTP / 退出码 | 耗时 | 内容 |
| --- | --- | --- | --- | --- |
| 绕过显式代理 | `--noproxy '*'` | 200 / 0 | 1.84 秒 | 3,637 字节 README |
| 本地 HTTP 代理 | `--proxy http://127.0.0.1:10808` | 200 / 0 | 1.18 秒 | 3,637 字节 README |
| 加速服务，绕过显式代理 | 原链接前加 `https://gh-proxy.com/`，`--noproxy '*'` | 200 / 0 | 1.02 秒 | 3,637 字节 README |

代理原站与加速文件 SHA-256 一致：`7805A315A56A4182499A736E29C486BFF90D68F6CC228713D3DA09D272EF283E`。小样本耗时用于记录取回事实，不作为线路性能排名；未确认底层 TUN/透明路由，不能断言“无任何代理”。

通过本地代理读取用户给出的资源页面、GitHub issue #116、curl 手册和 GitHub REST 故障排查，均返回 200。issue #116 明确提示公共额度可能耗尽、部分地址可能被服务禁止，并建议控制访问频次。

未验证：海外生产、Linux/macOS/CMD/WSL/容器、Release 大文件、archive、git clone、任意普通文档的加速。Tavily 提取因已存 OAuth 会话刷新返回 401，改用公开页面读取；这个认证错误不计为目标站点网络故障。

## 2026-10-10 Python/Node.js 依赖探针

执行环境：Windows PowerShell；本地工具为 uv 0.12.17、npm 11.19.0、pnpm 12.4.1。命令显式指定包源，继承当前进程代理及其他既有客户端配置，未隔离或确认底层出口；结果不作为直连可用性证明。

| 客户端与目标 | 镜像 | 官方源 | 结果 |
| --- | --- | --- | --- |
| `python -m pip download six==1.17.0` | `https://mirrors.ustc.edu.cn/pypi/simple` | `https://pypi.org/simple` | 两边退出码 0，实际 wheel 的 SHA-256 一致 |
| `npm.cmd pack is-number@7.0.0` | `https://registry.npmmirror.com` | `https://registry.npmjs.org` | 两边退出码 0，实际 tarball 的 SHA-256 一致 |
| `pnpm.cmd view is-number@7.0.0 dist.integrity --registry=...` | `https://registry.npmmirror.com` | 未另测 | 返回完整性字段，与 npm 下载报告一致；仅元数据验证 |

pip 使用临时下载目录、`--no-deps --only-binary=:all: --no-cache-dir --timeout 15 --retries 1`；npm 使用临时产物目录、独立缓存和 `--ignore-scripts --fetch-timeout=15000 --fetch-retries=1 --maxsockets=2`。未安装进项目，也未执行生命周期脚本。

- `six-1.17.0-py2.py3-none-any.whl` SHA-256：`4721F391ED90541FDDACAB5ACF947AA0D3DC7D27B2E1E8EDA2BE8970586C3274`。
- `is-number-7.0.0.tgz` SHA-256：`7B75C1057198CF97696909A9BEE176C9C5E9BCB5B03BF3ECEF2F484DEFADD51E`。
- pnpm `view` 使用带 `--fetch-timeout`/`--fetch-retries` 的命令被拒绝，首先报 `--fetch-timeout` 不受支持；移除这两个参数后查询成功。`install --help` 支持 `--fetch-timeout`、`--network-concurrency` 与 `--registry`，不能跨子命令直接照搬参数。

pip/uv/npm/pnpm/Yarn 与 Playwright 相关官方页面经本地代理读取并核对。未验证：完整项目安装、uv 下载、Yarn 运行、私有包、额外二进制下载、Linux/macOS/CMD 或海外生产。

## 2026-10-10 conda 探针

执行环境：Windows PowerShell；本地为 scoop 版 miniforge、conda 26.3.2。安装级与用户级两处 `.condarc` 合并生效：`nodefaults` 去 defaults，`custom_channels` 中 `conda-forge → https://mirrors.pku.edu.cn/anaconda/cloud`、`bioconda → https://mirrors.ustc.edu.cn/anaconda/cloud`。

- `conda search --override-channels -c conda-forge ca-certificates`：退出码 0，约 20 秒出结果，channel 列为 `conda-forge`（经北大镜像解析）。
- 代理验证：`HTTP(S)_PROXY` 指向黑洞 `http://127.0.0.1:1` 时同命令报 `ProxyError`，确认 conda 读取环境代理变量。
- 任务级覆盖：`CONDA_CHANNELS='bioconda,conda-forge'` 经 `conda config --show channels` 确认生效；`CONDARC` 指定文件变量同条件未改变有效 channels，不采用。

未验证：完整环境安装、私有 channel、大包下载、Linux/macOS 或海外生产。
