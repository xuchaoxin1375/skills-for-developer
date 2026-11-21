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

## 2026-10-20 站点拦截观测：无头浏览器与有头真实浏览器

执行环境：国内 Windows；先枚举本机代理候选并逐个探测（连接超时 5 秒、总预算 25 秒、无重试），出口以 `https://www.cloudflare.com/cdn-cgi/trace` 的 `ip=` 回显确认。目标为某 Cloudflare 保护的汽车配件电商商品页（RevolutionParts 白标站），任务为总结商品与适配信息。

| 路线与方式 | 结果 |
| --- | --- |
| 登记默认条目 + 静态抓取 | 403，Cloudflare 拦截页（`cloudflare_interstitial`） |
| 登记默认条目 + Playwright 无头 | 403，`sorry, you have been blocked` |
| 另一登记条目 `<port-B>`（出口与默认条目不同）+ 静态抓取 | 403，拦截页 |
| `<port-B>` + Playwright 无头 + 系统 Chrome | 403，拦截页，正文不含目标零件号 |
| `<port-B>` + Playwright **有头** + 系统 Chrome | 403 状态码但 247,202 字节真实正文，含目标零件号、价格与适配车型；按 `http_status:403:accepted_by_content` 接受 |

- **拦截由无头特征触发，不由出口决定**：同一出口无头被判拦、有头真实浏览器可取回正文；换另一个登记条目在无头下仍是 403。把 403 直接归因于“出口被封”会误判为站点或代理不可用。
- **登记默认条目不是唯一入口**：本次有三个可用入口（出口互不相同），只重试默认条目不足以判定站点可达性。
- **同一端口的两种协议结果可不同**：默认条目的 `http://` 探测超时、`socks5h://` 返回 200，该入口仍属可用；按单一协议失败跳过该条目会漏掉可用入口。
- **状态码可低于正文质量**：403 配真实正文（长度、期望文本、无拦截特征均达标）时按既有判定接受并记 `notes`，不为状态码继续升档。
- **页面表格可能由接口填充**：本次取回的正文里适配表整表为空行而商品信息完整，该站表格行经 XHR 注入；要逐条明细需查页面自己的接口，不是换个引擎就能拿到。

对照：第三方 reader 服务取回的首屏字段与本地有头结果一致，两个来源互证内容未失真；该路线在 skill 中属需用户同意的回退，不作为本地失败后的默认动作。

未验证：层 2/3 的自动求解表现、`--headful` 在其他拦截站点的通过率、真实浏览器带既有 cookie 与全新 profile 的差异、`--real-chrome` 无头形态的适用范围、Linux/macOS 与有头所需 Xvfb、跨日稳定性。

## 2026-10-20 挑战站点：层选择与论坛帖覆盖度

执行环境：国内 Windows；代理由本机登记条目提供（端口以 `<port>` 占位），未做出口 IP 回显核验。目标为某 Cloudflare 保护的 Discourse 论坛公开帖及其同源接口；总结任务触发。

| 路线与方式 | 结果 |
| --- | --- |
| 直连（不走代理） | 连接超时（单次上限约 21 秒），未取到正文 |
| 登记代理 + 层 0 `static` | 403，`cloudflare_interstitial` |
| 登记代理 + 层 1 `playwright`（无头） | 403，`cloudflare_challenge_markers`、`cloudflare_interstitial` |
| 登记代理 + 层 2 `scrapling` | 200，渲染后 HTML 约 731 KB；求解约 7–10 秒。`--engine scrapling` 钉层比 `auto` 少两次注定失败的升档尝试 |
| 同上 + 同帖 `.json` 接口 | 200，约 53 KB JSON：`posts_count: 111`、`reply_count: 65`、`post_stream.stream` 111 个 id，首屏只内联 20 楼 |
| 同上 + `.json?page=2` | 200，20 楼，`post_number` 21–40 |

- 该 origin 当前需层 2；层 0/1 均判挑战。已知这一事实后不必每次重跑低层。
- **渲染 HTML 的节点数不等于内容总量**：同帖渲染 DOM 只含 7 个楼层元素，站点接口报 111 楼。用渲染节点数写"覆盖一致"会得出错误的完整性结论。
- `htmlmini` 的 URL 抓取只跟环境代理变量或 `--proxy`，不读本机登记：未指定时日志为 `[proxy: none]` 并直接失败（约 11 秒），失败原因是路线未指定，不是站点不可达。
- `htmlmini --render` 在默认解释器（只有层 1）下选零依赖 Chrome `dump-dom`，得到约 8 KB 挑战空壳，随后报"像客户端渲染壳、请用 `--render=always`"；加 `--python-bin auto` 选到带求解引擎的解释器后改走 save_page，约 18 秒取得正文。提示与真实原因不一致，重复 `--render=always` 不会改善。

未验证：其他挑战站点的层通过率、`--headful` 表现、profile 复用对 clearance 的保持时长、Linux/macOS、跨日波动与该站速率限制。

## 2026-10-21 同一出口按客户端品牌判决：Chrome 被拒、Edge 放行

执行环境：国内 Windows；本机两套代理并存（Clash Verge 的 mihomo 混合端口 `<port-A>`、v2rayN 的 xray 端口 `<port-B>`），整机 `HTTP_PROXY`/`HTTPS_PROXY` 指向 `<port-B>`。目标为某 Akamai Bot Manager 保护的商城商品页。出口以 `api.ipify.org` / `ip-api.com` 回显确认。

| 路线 | 出口 | 结果 |
| --- | --- | --- |
| `<port-B>` + `http://` | `23.239.105.146`（AS53850 GorillaServers，`hosting=true`） | HTTP 代理可用：CONNECT 隧道正常，`http://example.com` 返回 200 |
| `<port-B>` + `socks5://` | 同上 | 同一出口，协议不同不影响出口归属 |
| `<port-A>` | `162.251.162.205`（AS53767 iCastCenter） | 另一条独立上游 |
| Chrome + `<port-B>` | 同上 | **403 `Access Denied` + `X-Reference-Error: 18.…`**（`Server: AkamaiGHost`） |
| Edge + `<port-B>` | 同上 | ✅ 正常页 |
| Chrome + `<port-A>` / 直连 | — | ✅ 正常页（直连出口 `120.33.226.133`，AS4134） |

- **受控对照**：只换浏览器可执行文件，出口、协议（`http://` 与 `socks5://` 出口 IP 相同）、profile（全新）、启动参数全不变。结论：Akamai 的边缘判决会按**客户端品牌**分叉，`Chrome` 被拒而 `Edge` 放行。这与"换出口"是两条不同的路线——被这类边缘封禁卡住时，先问"是不是只挡了某个客户端"。
- **协议与 profile 都不是变量**：`<port-B>` 同时接受 `http://` 与 `socks5://`，两种写法判决相同；用别的出口预热过的 profile 再走 `<port-B>` 仍被拒（Akamai 的 `akavpau` 绑 IP，换出口即失效）。
- **curl 指纹会掩盖判据**：三条路线的 curl 请求都是 403，不能用 curl 的结果区分"哪条出口能过"；有头真实浏览器 + 同一出口才看得出品牌差异。
- **工具侧的默认行为**：`resilient-browser-fetch` 的 `chrome-late` 默认拉起 Chrome，会继承 Chrome 的判决——用户自己的 Edge 在同一出口能开，晚接入引擎却一直失败。已加 `--browser-brand edge`（或 `--executable-path <Edge 路径>`、环境变量 `RESILIENT_BROWSER`）与 `htmlmini --chrome-bin` 透传。品牌解析为**注册表优先**（Windows `App Paths\<exe>`，本机实测与固定路径候选一致）、**点名即严格**（该品牌没装就报错，不静默换用别的浏览器），并在 `notes` 里回写 `browser_channel` 与 `browser_path` 以便核对实际拉起的二进制。
- **本机代理登记**：`~/.config/proxy-resources.json` 只登记了 `<port-A>`（已核验 HTTP 代理可用）。`<port-B>` 也在监听且两种协议都能用，但它的出口是机房 IP、撞 Akamai 边缘封禁，暂不作为默认条目。

未验证：边缘判决随时间与频次的波动、是否只针对该站、Edge 的其他版本是否同样放行、机房 IP 段整体信誉、Linux/macOS 上的同品牌差异。

## 2026-10-21 GitHub raw 三路线复核

执行环境：国内 Windows PowerShell 调用 `curl.exe`；目标 `https://raw.githubusercontent.com/mattpocock/skills/main/README.md`；连接超时 5 秒，直连总期限 12 秒、代理 20 秒、加速 15 秒，无自动重试。

| 路线 | 设置 | HTTP / 退出码 | 耗时 | 大小 |
| --- | --- | --- | --- | --- |
| 直连 | `--noproxy '*'` | 000 / 28 | 12.0 秒 | 0 字节（超时） |
| 登记默认代理 | `--proxy http://127.0.0.1:<port>` | 200 / 0 | 0.6 秒 | 16,461 字节 |
| gh-proxy 加速 | `https://gh-proxy.com/` 前缀，`--noproxy '*'` | 200 / 0 | 3.4 秒 | 16,461 字节 |

代理与加速取回文件 SHA-256 一致：`345041D56CF1411B6B3CA1CC54014D26C563890F817F4CB9E2CB193DCD771A3E`。结论：本机直连 raw 原站在 12 秒内未取到任何字节；代理与加速均可用，代理更快。未验证：其他 raw 路径、大文件、Release/archive/git clone、跨日波动、Linux/macOS。

## 2026-10-21 npm install ETIMEDOUT 排查

执行环境：国内 Windows；Node 24.21.0 / npm 11.19.0，用户级 `.npmrc` 仅设 `registry=https://registry.npmmirror.com` 与 `allow-scripts=...`；整机 `HTTP_PROXY`/`HTTPS_PROXY` 指向 `http://localhost:<port>`（xray，登记名 `xray-10808`）。目标为 `registry.npmmirror.com` 与 `cdn.npmmirror.com`。

- 路线：直连 0.05–0.15 s；经 `<port 7897>`、经 `<port 10808>`（http 与 socks5 各一次）均 200，registry 元数据与 tarball 都可取。用 4 个常见依赖做真实 `npm install`（独立缓存、`--ignore-scripts`）：首次 80 包 43 s，其中 `has-symbols` 单个元数据请求两次 `FETCH_ERROR` 后 40 s 才 200；同样的安装在新缓存下重跑 1.5–2.5 s 通过（经 10808 / 经 7897 / 国内镜像绕代理这三种设置都能通）。
- **`npm config get proxy` 返回 `null` 不能证明 npm 不用代理**：该值不反映环境变量派生的设置。用黑洞代理 + 全新 `--cache` 做对照才可靠——只设 `HTTP(S)_PROXY` / `http_proxy` 时 `npm view` 报 `ECONNREFUSED 127.0.0.1:1`，说明 npm 11 **确实读取**这些环境变量（与 `proxy=null` 的读数不矛盾）。
- `npm_config_noproxy=registry.npmmirror.com,cdn.npmmirror.com` 在黑洞代理下仍 200，说明 npm 的 `noproxy` 会放行指定域名，可用于"国内镜像直连、其余走代理"。
- 本机 `fetch-timeout=300000`（默认 5 分钟）：单请求打嗝会被放大成"卡住不动"，随后才报 ETIMEDOUT；诊断期建议 `--fetch-timeout=30000 --fetch-retries=5`。
- 未复现持续性 ETIMEDOUT（无用户项目路径），以上只证明本机当前到 npm 生态各源可达、且间歇性单请求停顿存在。未验证：具体项目的 `.npmrc`/锁文件固定源、install 脚本额外下载、Git/VCS 依赖、跨日稳定性。

## 2026-10-30 GitHub git 传输直连可用

执行环境：国内 Windows；同一仓库已有 `origin`（Gitee）与 `github` 两个远端，均为 HTTPS。未加任务级代理参数，沿用进程现有环境，未做出口回显。

- `git fetch github main`、`git push github main` 均退出码 0，`ls-remote` 返回与本地 HEAD 一致的 SHA；同期 `fetch`/`push` Gitee 同样成功。
- 与 2026-10-21 的 raw 直连观测（12 秒超时）对照：文件入口与 git 传输入口可达性不同，不能互推；本次只证明 fetch/push 小改动可用。
- 未验证：`clone`、大仓库与大文件、SSH 22/443、LFS 对象、代理路线对照、跨日与其他网络环境。

## 2026-10-30 GitHub 加速镜像与代理对照

执行环境：国内 Windows PowerShell 调用 `curl.exe`；连接超时 5 秒，单次总期限 20–30 秒，无自动重试，未做出口回显。加速前缀 `https://gh-proxy.com/`，代理为本机登记默认条目。

| 目标与路线 | HTTP / 退出码 | 取回 | 耗时 | 速度 |
| --- | --- | --- | --- | --- |
| Release 资产直连（1 MiB range） | 206 / 28 | 360,448 B 后超时 | 20.0 s | 约 18 KB/s |
| Release 资产经加速（1 MiB） | 206 / 0 | 1,048,576 B | 12.9 s | 约 81 KB/s |
| Release 资产经代理（1 MiB） | 206 / 0 | 1,048,576 B | 5.3 s | 约 198 KB/s |
| Release 资产经加速（完整 2,058,893 B） | 206 / 0 | 2,058,893 B | 22.1 s | 约 93 KB/s |
| Release 资产经代理（完整 2,058,893 B） | 206 / 0 | 2,058,893 B | 5.5 s | 约 374 KB/s |
| archive 经加速 | 200 / 0 | 9,421 B | 3.7 s | — |
| archive 直连 | 200 / 0 | 9,421 B | 1.4 s | — |
| `git ls-remote` 经加速前缀 | 0 | 45 条引用 | — | — |

- 加速与代理取回的 Release 文件 SHA-256 相同（`D0F534024C42AFD6CB4D38907C25CD2B249B79BBE6CC1DBEE8E3E37C2B6E25A1`），archive 两路也相同（`406BA12F3D2D8492E7BDC2FDD692DE22B03AE9C89F7D5D4C3AB5310B8B898855`），内容一致。
- 本次代理比加速快 2–4 倍；加速可用但不是最快路线，不能据此写死“镜像更快”。选路按当次样本，加速的主要收益是不占代理额度、大文件可直连。
- `ls-remote` 经加速前缀成功，说明该实例支持 git 智能 HTTP 读取；本次未测 `clone`、大仓库与推送。
- 未验证：其他加速实例、大文件长时间稳定性、并发与限流、跨日波动、私有资源。

## 2026-11-01 小仓库直连 clone 与 archive 下载可用

执行环境：国内 Windows PowerShell；进程未设 `HTTP(S)_PROXY`，未指定代理或加速前缀。

- `git ls-remote https://github.com/<owner>/<repo>` 返回 HEAD 与分支引用，退出码 0；随后 `git clone --depth 1` 同一公开小仓库退出码 0，耗时未单独计时，未触发超时。
- 同期用第三方 skill 安装器（urllib 直连）下载同仓库 `archive/refs/heads/master.zip` 成功；archive 入口与 git 传输入口在本次均可用。
- 与 2026-10-30 的 fetch/push 直连观测一致，仍不能据此推断 raw 文件入口——2026-10-21 raw 直连曾 12 秒超时。
- 未验证：大仓库、LFS、clone 中断恢复、代理与加速前缀对照、跨日与其他网络环境。

## 2026-10-30 加速镜像核验脚本两轮对照

执行环境：国内 Windows；`check_github_mirrors.py --direct --timeout 8 --workers 3`，目标为 raw 单文件、archive、Release 前 262144 字节与 `ls-remote`，两轮间隔约数分钟。

| 前缀 | 第一轮 | 第二轮 |
| --- | --- | --- |
| `https://gh-proxy.com/` | raw/archive/release 可用（release 80 KB/s），git 可用（4 refs） | raw/archive/release 可用（90 KB/s），git 超时 |
| `https://ghproxy.net/` | raw/git 可用，archive/release 超时 | 四类可用（release 10.8 KB/s） |
| `https://ghfast.top/` | 四类全超时 | 四类全超时 |

- 同一前缀两轮结果不同，印证超时只能记不可判定；脚本据此把超时与内容特征不符分开报告。
- `ghfast.top` 两轮全超时，本次判为不可用，但不足以断言长期失效。
- 未验证：完整大文件下载、并发与限流、跨日波动、其他网络环境。

## 2026-11-08 GitHub raw 超时后改用 jsDelivr

执行环境：国内 Windows，OpenCode `webfetch`（工具自带的代理/直连配置，未显式指定路线）。同一目标 `https://raw.githubusercontent.com/sigoden/argc/main/src/shell.rs` 两次传输失败（默认期限与 60 秒各一次，未取得正文），改用 `https://cdn.jsdelivr.net/gh/sigoden/argc@main/src/shell.rs` 一次取得完整正文；同轮 `api.github.com` REST 请求正常。

- 本次属两个反例：先直连而非先走已核验加速，以及 raw 超时后原样重发同一 URL；按现行选路应第一步走加速，3 秒无首响即改路。
- 复核同一仓库：`src/shell.rs` 返回 200；`README.md` 返回 301 到 `raw.githubusercontent.com` 后超时。jsDelivr 未命中缓存时会回落到 raw，不能当通用绕过，301 到 raw 不算加速成功。
- 未记录 HTTP 状态、耗时与字节数，未确认实际出口；jsDelivr 只证明该公开仓库文件在当次可取，不外推到 Release、archive 或私有仓库。

## 2026-11-15 GitHub 直连 TLS 握手失败，改用登记默认代理

执行环境：国内 Windows PowerShell。`git ls-remote github` 直连 `https://github.com/<owner>/<repo>` 报 `schannel: failed to receive handshake, SSL/TLS connection failed`；`git fetch github main` 无代理时长时间无输出后被中断。随后用 curl 经登记默认入口（7897）取同一仓库的 git info/refs 返回 200；登记备选入口（10808）4 秒连接超时。`git config --get-urlmatch http.proxy <目标URL>` 显示 URL 级配置仍指向 10808，故只加通用 `-c http.proxy=<7897>` 时 git 仍走失效入口；改用 `-c http.https://github.com.proxy=<7897>` 覆盖 URL 级键后，`ls-remote` 退出码 0，返回与本地 HEAD 一致的 SHA。同期 `git ls-remote origin`（`https://gh-proxy.com/...`）也返回同一 SHA。

- 与 2026-10-30 直连 fetch/push 成功对照：GitHub Git 传输的直连可用性随时段与网络变化，不能沿用旧结论；失败后先核验实际生效的代理入口或改走镜像，不重复直连或重复 push。
- URL 级 `http.<url>.proxy` 优先于通用 `http.proxy`，换入口必须覆盖前者；本次未测试 `git push github`，只证明只读 git 传输与镜像路线当次可用。

## 2026-11-17 PyPI 源与聚合入口实测（macOS）

执行环境：国内 macOS（Apple Silicon）、Python 3.11、pip 24.0→26.3；进程未设代理变量，未做出口回显。耗时与速度只描述当次链路，不作为线路排名。

`python -m pip index versions` 与 `pip download --no-deps --no-cache-dir` 两段分别计：

| 源 | 索引页 | 包文件段 | 备注 |
| --- | --- | --- | --- |
| `repo.huaweicloud.com/repository/pypi/simple` | 0.07–0.15 s | 0.10–0.44 s（1.2–4.9 MB/s） | 全部样本可用，端到端 `numpy` 5.3 MB 1.01 s |
| `mirrors.aliyun.com/pypi/simple` | 0.07–0.27 s；`numpy` 页 1.3 MB 需 8 s 以上 | 0.26–3.18 s | 可用但波动大 |
| `mirrors.ustc.edu.cn/pypi/simple` | 0.11–0.39 s | 0.32–0.60 s（约 0.85–1.05 MB/s） | 与本机 3.11 匹配的 cp311 wheel 可用 |
| `mirrors.cernet.edu.cn/pypi/web/simple` | 0.37–0.55 s（含 302） | `pyyaml` 175 KB 2.05 s，`numpy` 0.47 s（1.1 MB/s） | 端到端明显慢于华为云（0.61 s） |
| `pypi.org/simple` | 0.68–1.21 s；`numpy` 页读不完 | 超 8 s 预算，约 24–330 KB/s | 直连不适合装大包 |

- **文件段结论依赖所选文件**：先用 3.15 解释器测时，选中 `numpy` 最新的 cp315 wheel，USTC 与 CERNET 都把请求 302 到 `mirrors.tuna.tsinghua.edu.cn`，本机对该域名稳定 403（偶发 429）；改用本机 3.11 对应的 cp311 wheel 后，两家文件段正常（0.5–0.6 s）。判定为“该文件未在本地缓存、回源到拒本站点”，不是整站的可用性结论。
- **聚合入口的 302 稳定但有边界**：`mirrors.cernet.edu.cn` 连续 6 次请求 PyPI 均落到 `unicom.mirrors.ustc.edu.cn`；npm 与 brew 路径落到 `mirror.nju.edu.cn`。`/huggingface/`、`/dockerhub/v2/`、GitHub raw 路径均 404，不能当统一加速网关用。
- **chsrc 与端到端测法给出不同排名**：`chsrc measure pip` 报 USTC 19.2 MB/s、NJU 18.1、PKU 16.3、华为 10.5、MirrorZ 10.0（TUNA 与北外 403）；同一时段 `pip download` 端到端是华为云 1.01 s、USTC 0.85–2.07 s（`numpy` 5.3 MB）。两者测的样例不同，选源以端到端为准，chsrc 用于快速筛掉明显不通的站。
- **工具**：以上两段由 `scripts/bench_pypi_mirrors.py` 一次跑出（`--samples 2 --workers 4` 约 15–30 s）；`pip config debug` 确认本机用户级 `pip.conf` 曾同时配置 5 个索引且 `install.user = true`，后者会让 venv 内安装直接失败。

未验证：跨日与不同运营商出口的波动、海外网络、conda/brew/npm 在同机的同类对照、TUNA 拒绝本机文件请求的持续时间与原因。

## 2026-11-17 GitHub Release 大文件实测（macOS）

执行环境：国内 macOS（Apple Silicon）、zsh；未设代理变量，未做出口回显。目标为单个 Release 资产 `BS-Roformer-SW.ckpt`（699,412,152 字节）。

| 路线 | 取回 | 备注 |
| --- | --- | --- |
| `github.com` 直连 | 26–35 KB/s，206 | 按此速度需约 5 小时；同日晚些对另一 Release 直连报 `SSL unexpected eof` |
| 前缀 `https://gh-proxy.com/` | 760 KB/s，Range 请求返回 200 | 实际不可续传，只用整段下载 |
| 前缀 `https://ghfast.top/` | 3.4–5.3 MB/s，206 | 支持 Range，2–3 分钟下完，落盘字节数与 `content-length` 一致 |

- 判定：Release 资产先测已登记加速前缀再决定，直连只作回退；`scripts/check_github_mirrors.py --targets release` 可在一次调用内筛掉超时前缀（本次 `gh.llkk.cc`、`ghproxy.net`、`github.moeyy.xyz` 均 15 s 超时）。
- 同一模型仓库走 HuggingFace 时未见可用的旧线索；本次该权重实际托管在 GitHub Release，不在 HF，按资源实际托管位置选路。
- 未验证：其他时段与运营商、其他 Release 尺寸、代理路线对照、Git 传输在该前缀下的表现。

## 2026-11-17 aria2c 多连接对照（macOS）

执行环境：国内 macOS（Apple Silicon）、zsh；curl 8.20.0、aria2 1.37.0（Homebrew）。进程未配置 `http(s)_proxy`（仅有 `NO_PROXY`/`no_proxy`），两组仍用 `--noproxy '*'` / `--all-proxy=` 显式禁用代理；未做出口回显。下载文件逐次删除，未比对校验和；耗时只描述当次链路，不作为线路排名。

| 目标 | 工具与连接 | 结果 |
| --- | --- | --- |
| `https://gh-proxy.com/https://github.com/denoland/deno/releases/download/v2.1.9/deno-aarch64-apple-darwin.zip`（41,767,371 B） | curl，1 | 两次：180 s 超时（收到 31,946,628 B，约 0.17 MiB/s）；另一轮 87.5 s 完成（0.45 MiB/s） |
| 同上 | aria2c `-x4 -s4 -k1M`，4 | 两次：16.3 s（2.44 MiB/s）、27.8 s（1.44 MiB/s）；字节数与 `content-length` 一致，进度显示 `CN:4` |
| `https://npmmirror.com/mirrors/node/v22.14.0/node-v22.14.0-darwin-arm64.tar.gz`（47,035,396 B） | curl，1 | 3.2 s，14.01 MiB/s |
| 同上 | aria2c `-x4 -s4 -k1M`，4 | 2.25 s，19.90 MiB/s |

- gh-proxy 单连接被压到 0.2–0.5 MiB/s，四连接提升到 1.4–2.4 MiB/s；同一前缀的 699 MB 资产在 2026-11-17 另一轮测试中单连接约 760 KB/s，量级一致。该前缀对 Deno zip 的 Range 请求返回 206，进度确认 `CN:4`；对上述 699 MB 资产曾返回 200，说明同一前缀的 Range 支持按资产而变，不能只测一次前缀就套到所有文件。
- npmmirror 单连接已达 14 MiB/s，四连接只提升约 1.4 倍，远小于限速镜像；多连接不是通用提速，先判断单连接是否受限。
- 每组只有一到两次样本，未控制 CDN 缓存、时段与运营商波动；不能写成“某站更快”的长期结论，也不能推断其他镜像、文件大小或海外网络。
- 未验证：`-x8` 及更高并发、跨日对照、代理路线、429/403 限流反应、断点续传控制文件行为。

## 2026-11-18 超时与慢速下载的两次教训（macOS）

- **超时≠失败**：venv 内 `pip install mlx-audio-separator` 两次撞到 900 秒外部超时。第一次是 `install.user=true` 直接报错；第二次单索引下实际已装完，只靠 `pip list` 才发现。结论：超时后先查落盘与安装结果，再决定是否重跑，不原样重试。
- **慢速要设吞吐阈值**：699 MB 的 Release 资产直连 26–35 KB/s，后台跑了 39 分钟（51 MB）才被人为发现，期间只有总超时、没有速度判据。换 `ghfast.top` 后 2–3 分钟完成并核对字节数。结论：大文件按吞吐设阈值（本次下限 200 KB/s、15 秒窗口），不以总超时兜底。
- 同一时段自建脚本里 `stat -f%z` 因 coreutils 覆盖 BSD `stat` 失效，导致等待循环空转 20 分钟；改用 `wc -c < <file>` 后正常。脚本类等待条件要能被外部观测验证。

## 2026-11-19 mihomo 客户端配置与分组体检（Windows）

执行环境：国内 Windows；Clash Verge Rev（`verge-mihomo v1.19.25`，meta 内核），mixed `<port-A>`，控制口 `<ctl-port>`，`mode: rule`；系统代理、TUN、开机自启均关闭。检查用 `inspect_mihomo.py`（只读 GET）加一次组延迟测速，未切节点。

三层结构都落到了：profile 目录里有运行时拼装产物 `clash-verge.yaml`、同端口的片段 `config.yaml`、`profiles.yaml`（3 个可切换 profile，另有多个约 91 B 的 merge/script/rules/proxies/groups 片段）。运行时产物才是内核实际加载的那份，文件名不能按客户端版本硬编码。

- 默认链路是 `MATCH -> PROXY -> 美国-LB`（3 个节点，`load-balance` + `round-robin`）。出口回显 `US / PHX`，`/connections` 的 `chains` 与之一致；入口端口可用与链路命中是两件事。
- 池内 34 个节点，27 个有响应；7 个完全无响应集中在台湾家宽 1–4、日本 SAK-3/4 与京都原生，另 1 个香港节点卡在 5000ms。历史 `history` 有 9 个记录为 0/false，复测后仍是上述 7 个，历史值和现势要分开写。
- 规则只有 17 条：4 条 `RULE-SET -> DIRECT`，12 条 `IN-NAME crawler-* -> 地区组`，最后 `MATCH -> PROXY`。因此切 `ALL-SELECT` 或地区组对普通流量没有效果，这是"切了没反应"的直接原因。
- 实测到的结构问题：`PROXY` 组混入 `DIRECT`/`REJECT`；`自建-LB` 与 `俄罗斯-LB` 因 `s4`/`s6` 两个空 `file` provider 退化成只剩 `COMPATIBLE` 的空组；订阅把"剩余流量/套餐到期/距离下次重置"做成 3 个可用的 Hysteria2 节点，虽被各组的 `exclude-filter` 挡住，仍在 provider 里参与健康检查，客户端 `junk-filter` 没清掉；名字含"2倍率"的 2 个真实节点被 `exclude-filter` 关键词一并挡掉。
- 配置定位：`verge-mihomo.exe` 的命令行同时带 `-d <profile-dir>` 与 `-f <profile-dir>/clash-verge.yaml`，可直接定位运行时文件。本机目录扫描约 88 ms（7 个候选），进程枚举（PowerShell CIM）约 275 ms，所以脚本在 Windows 上单客户端先扫描，只有零个/多个客户端或 `--process` 时才查进程。进程信息的收益在便携安装、自定义 `-d` 和多客户端歧义，不在速度；以服务账户运行或 GUI 没拉起内核时进程不可见，仍要回退目录扫描。
- 新版内核的 `/proxies` 不再包含 provider 节点：同日升到 v1.19.33 后，该端点只返回 22 条分组与内置项（含 `PASS-RULE`），39 个节点只在 `/providers/proxies` 里；v1.19.25 时两边都有。按单一来源读会把节点池误报成 1 个，必须合并两处。
- provider 与规则集：`online-sub1` 的 `interval` 是 43200（12h），缓存落在 `<HomeDir>/proxies/<url 的 md5>`；4 个规则集 `interval` 86400，显式 `path: ./ruleset/*.yaml`。`s4`/`s6` 两个 file provider 的路径不存在，因此对应组退化成空组。`updatedAt` 在重启后会等于缓存 mtime，只看它会把"刚重启"误判成"刚更新"。
- `-ext-ctl-pipe` 不校验 secret；本机 Verge 用命名管道给 GUI，同时保留 TCP 控制口，报告默认按 TCP 读，管道只在进程参数里出现时记录、不当 HTTP 入口。
- 测速也受同一个端点变化影响：provider 节点 `/proxies/{name}/delay` 返回 404；对 `ALL-LB` 这类成员全是叶子的组调用 `/group/ALL-LB/delay` 约 5 秒可用，而对 `PROXY`（成员是子组）调用返回的是子组名。脚本因此先试单节点，失败后只挑成员全为叶子的组整组测，并记录本次用了哪种方式。
- BP6 缺失复核：`online-sub1` 的 `updatedAt` 与缓存 mtime 都是 11:37，但缓存内容仍是 BP1-3（9997.48 GB）；同一 URL 用 `clash.meta` UA 直接 GET 返回 42 个节点，含 BP6 与 2 个澳门节点（9992.23 GB）。未启用的 `雪山 Link` profile 文件（前一日 23:08）也有 BP6。结论：`美国-LB` 的 filter 没问题，是 provider 缓存旧于订阅；内容新鲜度不能靠 `updatedAt`/mtime 判断。
- Verge 的本地 profile 菜单没有"更新"（只有使用/编辑/删除），"使用"只重新加载配置；缓存年龄小于 `interval` 时不会重拉。强制刷新走 `PUT /providers/proxies/online-sub1`（写操作，204 只表示受理），或等 12h 到点；`--compare-subscriptions` 可在只读范围内先确认差异。
- 结论：端口探测通过不等于配置健康；`round-robin` 对无登录公开页爬虫是刻意选择，报告只按场景提示，不判缺陷。

未验证：逐节点真实出口（需 `PUT /proxies/{name}` 切节点，属写操作）、目标站的限流与风控、mihomo-party/FlClash 的目录差异、macOS 与 Linux、v1.19.33 之前版本的 `/proxies` 行为是否稳定。

## 2026-11-20 mihomo 多实例枚举（Windows）

执行环境：国内 Windows；同一台机器 3 个 `verge-mihomo` 内核进程：GUI 实例（mixed `<gui-port>` / controller `<gui-ctl>`）、`robin` 实例（mixed `<robin-port>` / controller `<robin-ctl>` / listeners `<robin-band>`）、`ch` 实例（mixed `<ch-port>` / controller `<ch-ctl>` / listeners `<ch-band>`）。只读检查，未切节点，未跑 `--delay`。

- 默认 `inspect_mihomo.py` 走 Windows 单根目录快路径，只报告 GUI 实例；两个自定义 `-d` 的实例不在候选目录里，扫描结果看起来"只有一个客户端"。
- `--process` 会枚举进程，但 `pick_entry` 仍只选一个（本次为 `ch`），不会输出另外两个；需要在 stderr 提示之外显式用 `--list-instances`。
- `--list-instances` 能一次列出 3 个实例的 PID、`-d`/`-f`、mixed、controller、listeners 与策略；完整检查仍需对每个实例单独 `--config`/`--controller`。
- `probe_local_proxies.py` 能探到 30+ 个监听端口；`instances[]` 按 PID 归组后能区分 GUI/`robin`/`ch`，`usable[]` 中 `egressMatchesDirect: true` 的入口排在最后。
- 结论：多实例下"端口可用"不等于"实例可用"；先枚举实例，再按实例检查。默认单实例报告不能代表整机。

未验证：其他客户端/平台的多实例行为；逐节点真实出口；各实例策略组的实际轮换效果。

## 2026-11-21 内置 webfetch 套加速前缀与 Release 下载（Windows）

执行环境：国内 Windows 11、PowerShell 7；`gh-proxy.com` 加速前缀；目标为 raw 单文件与 Obscura v0.2.7 Windows stealth 资产（77,011,421 字节）。未做出口回显。

- `webfetch https://gh-proxy.com/https://raw.githubusercontent.com/octocat/Hello-World/master/README` 一次返回 `Hello World!`；同一工具直连 GitHub raw 曾在 2026-11-08 两次超时。内置抓取工具没有代理开关，raw/blob 正文可直接套前缀。
- 同一 Release 资产：直连约 1.5 分钟只取到约 400 KB（约 2.6 KB/s，随后中断）；改用 `https://gh-proxy.com/https://github.com/...` 后 165.5 s 完成，平均约 454 KB/s，落盘字节数 77,011,421 与资产大小一致。
- `check_github_mirrors.py --targets raw,release` 当次：gh-proxy 76.6 KB/s、ghfast 60.7 KB/s、ghproxy.net 19.2 KB/s（Release 前 256 KiB）。前缀速度与资源类型、时段相关，不能把本次排名当长期结论。
- 结论：国内网络下 GitHub 公开只读资源先走已核验前缀；内置抓取工具同样适用，不先直连试错。只描述当次网络。
