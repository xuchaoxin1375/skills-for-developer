# 本机网络观测

仅记录某台工作机器的带日期事实，不作为其他机器、平台或生产服务器的默认配置。端口、协议、路由和公共服务状态都可能变化，任务前重新核验。

本文件所有端口、进程名、登记条目名均为单机示例（已脱敏为占位），禁止复制为配置；用前按 [proxy-registry.md](proxy-registry.md) 流程重新核验本机。

## 2026-10-09 历史记录

- 本地代理 `http://localhost:<port>` TCP 可达，经代理取 `https://pypi.org/simple/` 返回 200。
- pip 已配 USTC（`%APPDATA%\pip\pip.ini`）；uv 当时无用户级镜像配置，依靠代理访问官方源。
- 当时 `HTTP_PROXY`/`HTTPS_PROXY` 已设置；这些观测不证明后续请求或其他客户端仍使用同一路线。

## 2026-10-10 目标核验

执行环境：Windows PowerShell 调用 `curl.exe`。两个本地端口存在 TCP 监听，仅验证其中一个的 HTTP 代理协议；另一端口未核验协议或出口。`HTTP_PROXY`/`HTTPS_PROXY` 已配置，`ALL_PROXY`/`NO_PROXY` 未配置；没有输出代理凭据。

原始目标：`https://raw.githubusercontent.com/hunshcn/gh-proxy/master/README.md`。使用连接超时 5 秒；直连总期限 12 秒、代理 20 秒、加速 15 秒；无自动重试。

| 路线 | 设置 | HTTP / 退出码 | 耗时 | 内容 |
| --- | --- | --- | --- | --- |
| 绕过显式代理 | `--noproxy '*'` | 200 / 0 | 1.84 秒 | 3,637 字节 README |
| 本地 HTTP 代理 | `--proxy http://127.0.0.1:<port>` | 200 / 0 | 1.18 秒 | 3,637 字节 README |
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

## 2026-10-11 模型参数数据源双路探测

执行环境：国内 Windows，`curl.exe` + UA `Mozilla/5.0`，连接超时 5 秒、总期限 20 秒；为 opencode-provider-config 选备用数据源（models.dev 访问慢），总结任务触发。

| 数据源 | 直连 | 代理(登记默认条目) | 备注 |
| --- | --- | --- | --- |
| openrouter.ai/api/v1/models | 200 / 3.5s / 766KB | 200 / 3.1s | 458 模型，无需鉴权；字段最全（`context_length`、模态、`supported_parameters`） |
| models.dev/api.json | 200 / 18.0s / 5.4MB | 200 / 18.1s | 直连代理都慢，印证"访问慢"体感 |
| litellm raw（githubusercontent） | 20s 超时仅落 16KB（截断） | 200 / 8.6s / 2.7MB | 直连不可用，需代理 |
| litellm jsdelivr 镜像 | 200 / 6.3s / 2.7MB | 200 / 10.8s | 直连可用；另一 *nix 设备曾遇 jsdelivr 异常响应，单点观测不互相推广 |

字段形状已核验：OpenRouter `data[].context_length`/`architecture.input_modalities`/`top_provider.max_completion_tokens`；LiteLLM 键含 `provider/` 前缀、`max_input_tokens`/`supports_*` 标志，新模型可能滞后。未验证：海外生产直连、镜像长期稳定性、跨日波动。

## 2026-10-11 代理资源核验与登记

- 某代理工具进程监听本地回环端口；用 `curl.exe -x http://127.0.0.1:<port>` 访问境外网关 `/v1/models` 返回 200，补上此前"未核验该端口协议"的缺口。
- 同日核验服务端已持久化全局 `HTTP_PROXY`/`HTTPS_PROXY`（值为本机回环代理地址），`NO_PROXY` 含回环地址与一条直连业务域名；shell 环境变量仍指向另一本地端口，本次未核验其监听与协议。
- 已创建登记文件 `~/.config/proxy-resources.json`（默认条目见该文件，`source: registry`）；约定与流程见 [proxy-registry.md](proxy-registry.md)，后续任务先读登记再做有界核验。
- 真直连对照（`--noproxy '*'`）：被阻断域名三次 15 秒超时；shell 代理变量曾让同命令"假直连成功"，测直连必须显式绕过代理变量。

- 同日修正：服务端 `NO_PROXY` 原为空格分隔，已改为逗号分隔（放行域名不变）并重启服务生效；空格写法可能被 HTTP 客户端解析失败而使放行域名静默走代理。修正后官方 Go 端点经代理调用验证通过。

## 2026-10-11 站点拦截观测（arena.ai）

执行环境：Windows PowerShell 调用 `curl.exe`，连接超时 5 秒、单次总期限 20 秒，无自动重试；总结任务触发，双路有界探测一次完成。

| 路线 | 设置 | HTTP / 耗时 | 结果 |
| --- | --- | --- | --- |
| 直连 | `--noproxy '*'` | 403 / 0.5 秒 | 拦截，未取到正文 |
| 默认代理 | `--proxy http://127.0.0.1:<port>` | 200 / 1.9 秒 | 取得正文，最终 URL 重定向为 `https://arena.ai/company/about` |

代理路线落盘正文经网页骨架提取（htmlmini）成功取得完整页面内容，未启用浏览器渲染；`resilient-browser-fetch` 对该站未验证。单站点单路径观测，不推广到该域其他路径或其他拦截站点。

## 2026-10-18 内置网页抓取工具的出口与失败形态

执行环境：国内 Windows；被测对象是 opencode harness 的内置 `webfetch` 工具（只有 `url`、`format=text|markdown|html`、`timeout` 参数，**没有代理与 UA 开关**），对照工具为 `curl.exe`。总结/评估任务触发，探测一次完成。

| 通路 | 目标（出口回显） | 结果 |
| --- | --- | --- |
| 内置 `webfetch` | `https://www.cloudflare.com/cdn-cgi/trace` | 200，出口 `240e:…`（IPv6，colo=SJC） |
| `curl.exe --noproxy '*'` | 同上 | 200，**与内置抓取同一出口 IP** |
| `curl.exe --proxy http://127.0.0.1:<port>` | 同上 | 200，出口 `120.33.…`（colo=LAX） |

- 该内置抓取**走真直连，不读 `HTTP(S)_PROXY`**（UA 为 opencode 自身标识）。与 `htmlmini`/`curl` 靠环境变量或 `--proxy` 指定路线的方式不同：宿主工具未提供路线开关时，只能通过出口回显判断实际路径。
- 内容观测（`format=markdown`）：服务端渲染页面能取到正文（营销页首屏与章节结构、定价对比表、文档正文）；**客户端渲染或 CMS 注入的内容取不到**（某产品页的定价卡与 FAQ 答案整块缺失）。
- 失败形态：Cloudflare 挑战站（`nowsecure.nl`）返回挑战空壳且**不报错**，最易被误当正文；`x.com` 超时以 `{"error":{"type":"unknown","message":"Request timed out"},"content":[]}` 返回而非抛错，调用方需自行判错；`api.ipify.org` 直连与代理均传输层失败，说明直连可达性随目标而异。
- 格式语义：`format=markdown` 对 HTML 是"HTML→Markdown 转换"（保留转换痕迹：转义字符、列表间空行、协议相对图片地址、表格被拉平为逐行文本）；非 HTML 输入（raw markdown、JSON 端点）原样透传；`format=html` 的属性引号被去除（如 `lang=en`），不是响应原始字节。

未验证：其他 harness 与版本、页面 JS 是否执行、真实浏览器指纹下的挑战页、Linux/macOS、长期可达性与跨日波动。

## 2026-10-18 多代理家族并存与候选扫描的边界

执行环境：国内 Windows；先枚举回环监听与进程名，再对每个候选做一次有界探测（连接超时 5 秒、总期限 15 秒、无重试），出口以 `https://www.cloudflare.com/cdn-cgi/trace` 的 `ip=` 回显确认。该机同时运行两套本机代理程序：Clash Verge（mihomo 核心，图形版默认 mixed 端口）与 v2rayN（xray 核心，图形端常见 socks 端口），另有一个查不到归属的回环端口。

| 候选端口（占位） | 枚举可见性 | `http://` 探测 | `socks5h://` 探测 | 出口 |
| --- | --- | --- | --- | --- |
| `<port-A>` | 监听 + 进程 `verge-mihomo` | 200 / <1s | 200 / <1s | `<ip-A>`（LAX） |
| `<port-B>` | 监听 + 进程 `xray` | 200 / <1s | 200 / <1s | `<ip-B>`（LAX） |
| `<port-C>` | 监听 + 进程 `xray` | HTTP=000（立即） | 5s 超时 | 无（非代理入口） |
| `<port-D>` | **两条枚举路径都无 LISTENING 行、无归属进程** | 200 / 0.8s | 未测 | `<ip-C>`（LAX） |

- **监听 ≠ 代理入口**：`<port-C>` 在监听表里与其余代理端口无异，但两种协议都取不回内容——它是内核/控制类入站。只看“有监听”就登记会存进一条死条目。
- **扫不到监听 ≠ 没有代理**：`<port-D>` 在 `Get-NetTCPConnection` 与 `netstat -ano` 里都没有监听行，`netsh interface portproxy` 也无转发规则，归属进程不明；但 TCP 探活成功、经它取回 200 且出口与直连不同。该机同时跑着 WSL 发行版与 `vmmemWSL`/`wslservice`/多个 `wslhost` 进程，倾向解释为 WSL 侧代理经回环转发暴露在宿主端口，或 TUN/驱动级拦截；两种解释本次都未确认。
- **端口 ≠ 协议**：上表两个可用入口对 `http://` 与 `socks5h://` 都返回 200，说明是 mixed 端口；只看端口号（如把 10808 一律当 socks）会漏掉 HTTP 用法。
- **同一端口段不等于同一出口**：三个可用入口的出口 IP 互不相同，是三条独立上游；且同一端口两次请求的出口 IP 也会变（多节点按连接分配），"出口 IP"只是一次取回的事实、不是该入口的固定属性。耗时只记录取回事实，不作线路排名。
- **短模式误匹配**：按 `ss`、`ray` 过滤进程名会命中 `csrss`、`lsass`、`CrossDevice…` 等，候选表要用 `ss-local`、`xray` 这类具体模式。内置家族表刻意放宽（`verge`、`clash` 都在内），要收窄或补小众客户端用 `--match REGEX` 追加、`--only-match` 只看自定义正则；写两字母模式仍会误命中，这一点不会因为可自定义而消失。
- **同一入口是否回话也会变**：同一个端口一次 `http://` 取回 200、另一次 `http://` 与 `socks5h://` 双双超时（超时点即单次上限）。所以预算内的失败只能记“不可判定”——它既可能是该端口不是代理，也可能只是这轮没赶上。

未验证：`<port-D>` 的实际归属与协议（含是否只接受 HTTP）、其他家族端口、Linux/macOS/容器内枚举差异、跨日稳定性与限流状态。本次核验可用的条目已更新到 [proxy-registry.md](proxy-registry.md) 所述登记文件。

上述按进程名匹配 + 探测监听端口的流程已固化为 `scripts/probe_local_proxies.py` 并复跑核对：命中 mihomo 与 `*ray` 两家族进程后只探它们自身监听的端口，监听但非代理的端口（如 GUI 控制端口）判为“不是代理入口”，无监听条目的端口靠登记补上；`--match`/`--only-match` 可自定义家族名（实测 `--only-match xray` 后 GUI 控制端口从候选里消失，`--match explorer --only-match` 命中非代理进程时不产生候选）；把单次上限收紧时该端口被判为不可判定而非“不是代理”，放宽后恢复可用——印证"歧义性失败不能下否证结论"。默认预算与单次上限已放宽到 5 秒 / 2.5 秒。

## 2026-10-18 Playwright 制品：镜像与官方 CDN 的对照

执行环境：国内 Windows；Playwright 1.64.0，`%LOCALAPPDATA%\ms-playwright` 原本为空。包锁定的制品为 `chromium-1248` 与 `chromium_headless_shell-1248`（Chrome for Testing 156.0.8078.4，另有 ffmpeg-1013、winldd-1007），取自 `install --dry-run chromium`。把 `PLAYWRIGHT_BROWSERS_PATH` 指向空目录后启动，报错直接点名 `<空目录>\chromium_headless_shell-1248\chrome-headless-shell-win64\chrome-headless-shell.exe`，可据此确认包与制品是成对锁定、不接受换成别的 revision。

| 路线 | 实测 |
| --- | --- |
| 制品镜像 `<mirror-base>` 直连（无代理） | `--dry-run` 解析出全部制品的镜像 URL；`chrome-win64.zip` HEAD 200 / `application/zip` / 207,073,013 B；前 8 MiB 有界 GET 206、22.1 MB/s、首字节 `504B0304`（真 ZIP）；`install chromium` 未在本机复跑（当时已装好） |
| 官方 CDN 经登记代理 | `install chromium` 全链 4 件成功，159 s；中途一次 `ECONNRESET`，靠 fallback host 与重试自愈 |
| 官方 CDN 直连 | 前 8 MiB 有界 GET 45 s 超时，只取回 5,576,817 B（约 0.12 MB/s） |
| 官方 CDN 经登记代理（同一文件单次 8 MiB） | TLS 握手失败（`schannel: failed to receive handshake`），本次未取到数据；与上一行“整链安装成功”不矛盾，属单次失败 |

结论（仅限本机与本次）：镜像对包锁定的 revision 命中且直连比经代理快一个量级，适合作为大包默认路线；代理路线可用但慢、且要消耗代理额度。版本滞后不是主要风险，判据是 `--dry-run` 的制品清单是否与包锁定项逐项对齐。

未验证：镜像长期稳定性与对其他 revision/平台/浏览器的覆盖、并发与限流行为、代理额度实际消耗、Linux/macOS/CI、企业内网制品库。核验过的这个基址已按 [proxy-registry.md](proxy-registry.md) 的 `artifact_mirrors` 记入本机登记文件，使用前仍要 `--dry-run` 与包锁定的 revision 对齐。
