# 网络访问、代理与回退

## 环境与路线

试验默认在国内、生产默认在海外，是技术方案的背景假设，不代替具体任务的实测。包镜像、GitHub 文件加速和代理解决的问题不同：包镜像可能同步滞后，文件加速只支持特定 URL，代理仍受目标权限和限流约束。

先确定请求由谁发出。本地代理只能直接服务能访问它的客户端；远程 `web_search`/`web_fetch` 服务不会因本机设置环境变量就自动使用该代理。WSL、容器和远程服务器中的 `127.0.0.1` 指向各自环境；访问宿主机代理时按网络模式选择地址，并核验监听范围和可达性。

日常选路采用[主文件的选路默认](../SKILL.md#选路默认)，不因登记有代理就强制使用，也不对已知直连不稳的站点重复直连试错。大体积制品与大包优先已核验镜像或稳定直连，不让有额度限制的代理承担默认大流量；缺件或校验不过再回退原站。海外生产不继承本机回环代理或未经验证的公共加速服务。

## 跨平台代理配置

从实际 Mihomo 或其他代理配置读取 HTTP、mixed 或 SOCKS 入口。
HTTP 代理常写成 `http://127.0.0.1:<实际端口>`，即使目标是 HTTPS 也可使用这个 HTTP 代理入口；`HTTPS_PROXY` 名称不代表入口必须写 `https://`。
SOCKS 入口另用 `socks5://` 或客户端支持的 `socks5h://`（由代理解析目标域名），不能只看端口猜协议。

以下为专用任务终端的示例，执行前替换端口；只影响当前终端及其后续子进程，任务后关闭该终端。已有环境需要保留时优先使用命令级代理参数，或保存原值再恢复。

### Linux/macOS（Bash/Zsh）

```bash
task_proxy_url='http://127.0.0.1:<实际端口>'
export http_proxy="$task_proxy_url"
export https_proxy="$task_proxy_url"
export HTTPS_PROXY="$task_proxy_url"
```

环境变量区分大小写。curl 的 HTTP 代理变量使用小写 `http_proxy`，不能仅设置大写 `HTTP_PROXY`；其他客户端按各自文档处理。

### Windows PowerShell

```powershell
$taskProxyUrl = 'http://127.0.0.1:<实际端口>'
$env:HTTP_PROXY = $taskProxyUrl
$env:HTTPS_PROXY = $taskProxyUrl
```

Windows 环境变量通常不区分大小写，且当前进程的修改不会自动影响已启动的应用。调用 curl 时写 `curl.exe`，避免 Windows PowerShell 的同名别名；不为本次任务使用 `setx` 写持久配置。

### Windows CMD

```bat
set "task_proxy_url=http://127.0.0.1:<实际端口>"
set "HTTP_PROXY=%task_proxy_url%"
set "HTTPS_PROXY=%task_proxy_url%"
```

检查已有 `NO_PROXY`/`no_proxy`：其排除项可能使目标绕过代理，`ALL_PROXY` 也可能影响默认路线。浏览器、Git、SDK 或服务进程可能不读取这些变量；按客户端显式配置，并用该客户端读取目标验证。Git 可用本次命令的 `-c http.proxy=<代理URL>`，不写全局 `insteadOf`；浏览器使用其支持的启动或上下文代理参数。

## 有界诊断与超时

下面是故障诊断的有界命令示例，不是日常抓取必跑的前置流程。普通小页面的慢直连改路窗口按[选路默认](../SKILL.md#选路默认)执行；明确需要故障对照时，连接超时5秒、单次总耗时20秒可作诊断起点。大文件按大小、进展与带宽调整。连接超时覆盖连接建立阶段，总耗时覆盖整个取回；重试另受次数和任务总期限约束。

下面用公开 GitHub 文件示意。在 Linux/macOS 用 `curl`；Windows 用 `curl.exe`，`<原始URL>` 与端口先替换。代理诊断须确认 `NO_PROXY` 没有排除目标。

```bash
curl --silent --show-error --location --noproxy '*' --connect-timeout 5 --max-time 20 --output origin-direct.md --write-out 'HTTP=%{http_code} total=%{time_total}\n' '<原始URL>'
curl --silent --show-error --location --proxy "$task_proxy_url" --connect-timeout 5 --max-time 20 --output origin-proxy.md --write-out 'HTTP=%{http_code} total=%{time_total}\n' '<原始URL>'
```

```powershell
curl.exe --silent --show-error --location --noproxy '*' --connect-timeout 5 --max-time 20 --output origin-direct.md --write-out 'HTTP=%{http_code} total=%{time_total}\n' '<原始URL>'
curl.exe --silent --show-error --location --proxy $taskProxyUrl --connect-timeout 5 --max-time 20 --output origin-proxy.md --write-out 'HTTP=%{http_code} total=%{time_total}\n' '<原始URL>'
```

curl 的 `--noproxy '*'` 绕过 curl 所配置的显式代理，但不能绕过透明代理或 TUN 路由；“直连”记录需说明实际出口是否确认。CMD 可用同样的参数，字符串改用双引号，代理变量写 `%task_proxy_url%`；写入 `.bat` 时 `--write-out` 中的 `%` 需写成 `%%`。

只有需要对照路线或诊断故障时才双路探测，不作为陌生 URL 的默认前置步骤；可在预算内并行，但成功取回的正文直接落盘复用，不再沿获胜路线重抓。同一任务内复用同站、同客户端结果。
内置网页抓取等工具走宿主进程默认网络环境，其路线不受本节参数控制；需要指定路线时改用带显式参数的 curl 取回。
网页正文抓取与提取优先按 [htmlmini 的使用边界](../../htmlmini/SKILL.md#使用边界)执行，普通内置抓取作为回退；需要原始响应或网络诊断时用显式 `curl`，需 TLS 伪装时用 `curl_cffi`（同路线复用代理），确认挑战页（含 5xx 异构后现挑战特征）才转 `resilient-browser-fetch`。已有正文或快照直接复用，不逐工具重抓；`curl` 5xx 未做异构对照前不判源站死。

同时检查退出码、HTTP 状态、最终 URL、正文或文件格式；HTTP 200 可能是登录页、拦截页或加速站首页，TCP 端口通只证明存在监听服务。
curl 默认不会把 HTTP 403 判为进程失败，下载交付可用 `--fail` 并仍保存必要的错误诊断；不要用 HEAD 成功代替实际 GET 核验。

`--max-time` 只限制单次取回；curl 开启 `--retry` 后每次尝试重新计时，`--retry-max-time` 只在开始新重试前检查，已启动的取回仍可能超过这个期限。需要硬总期限时由调用方限制整个进程；本例不自动重试，避免与 Agent 重试叠加。

## 慢速与停滞的发现

大文件判“能不能继续”看的是每秒拿到多少，不是有没有结束：总超时只能兜住卡死，兜不住 35 KB/s 爬三小时。

- **阈值从已知路线来**：取本机 bench 或镜像公开基准里可用路线的 1/5；超过 100 MB 的文件，绝对下限放在 100–200 KB/s。
- **curl 自带上限**：`--connect-timeout 5 --speed-limit 200000 --speed-time 15`，连续 15 秒低于 200 KB/s 即退出（退出码 28，属路线不可靠，不是源站故障），换前缀或代理；同时用 `-w '%{size_download} %{speed_download}\n'` 留证据。
- **aria2c**：`--lowest-speed-limit=200K --timeout=10 --max-tries=1`，配合多连接；触发后保留 `.aria2` 控制文件，换路线 `--continue=true` 续传。
- **没有内置阈值的下载器**（工具自带进度条、包管理器、模型加载器）：外部采样落盘大小，每 10 秒一次；连续 3 次零增长或低于阈值就终止进程换路。采样时用 `wc -c < <file>`，不要用 `stat -f`（macOS 装了 coreutils 时 `stat` 是 GNU 版）。
- **超时或中断后的第一个动作是查产物**：落盘字节数、进程是否真退出、包是否已装上。超时不等于失败，原样重跑会重复消耗流量与时间；工具只按“文件存在”跳过下载时，要自己比对 `Content-Length` 或哈希。
- **记录**：路线、字节数、耗时、采样时段；单次结论不外推为“某站更快”。

## 错误分流

| 现象 | 检查与处理 |
| --- | --- |
| DNS、连接或 TLS 握手失败，HTTP 尚未返回 | 核验代理协议/地址、解析、证书和出口；对同一公开目标做有界的另一条路线对照，不凭一次失败断言整个网络故障 |
| 已连接但读取超时/大文件慢 | 检查文件大小、下载进展、上游速度和总耗时；仅有依据时调整期限或采用支持的续传 |
| HTTP 401/403，正文提示权限或登录 | 检查认证、资源权限和目标 URL；代理/镜像不能修复凭据或授权，停止重复请求 |
| HTTP 403，正文只有简短 Forbidden，无挑战/登录/限流特征 | 先排除只按请求头拦截：同一路线补 `User-Agent`、`Accept`、`Accept-Language`、`Referer` 重测一次；200 即沿用该请求头。仍 403 再按权限、WAF/挑战或限流分流 |
| HTTP 403，正文为 WAF/挑战/区域拦截 | 保留失败来源与页面信息；确需渲染取证时转 `resilient-browser-fetch`，不默认套 GitHub 加速前缀。同一目标换出口后可能返回**不同类型的拦截**（如一个出口 `Attention Required \| cf-error-details` 属 IP 层拒绝，另一个 `Just a moment...` / `cf-mitigated: challenge` 属可解挑战），响应体要逐个比对而非只比状态码 |
| HTTP 403/429 且正文或响应头明确提示限流 | 遵守 `Retry-After`、供应商重置时间和共享冷却；按 `agentic-web-search` 调度；429 可在冷却后用已核验的另一出口做一次有界验证，记录出口与状态，不连续轮换或绕过冷却 |
| HTTP 5xx（含 500/502/503/504 及 Cloudflare 520 系） | 简头 curl 的 5xx 可能是反爬指纹拦截，不是源站死的充分证据。先保留状态码、正文与 `cf-ray`/`server` 头等证据，再换出口有界对照一次（直连↔代理，沿用“有界诊断与超时”的单次上限，不叠加自动重试）；另一路成功即沿用该路。两路一致 5xx 时补一次异构对照：补全浏览器头（Accept/Accept-Language/Upgrade-Insecure-Requests/Sec-Fetch-*）重测，或同路线 `curl_cffi`，或真实浏览器；出现 302 跳 `/_sc/challenge`、`/_sec/`、`challenge`、`captcha`、`turnstile`，或 403 带 `sct`/`cf_clearance` cookie、`X-Robots-Tag: noindex`，即按挑战页转 `resilient-browser-fetch`。异构仍 5xx 才判源站故障并记录，不逐个出口轮询，不转镜像加速 |
| HTTP 404 或加速站拒绝 URL | 检查原始链接、分支/标签、服务支持范围；GitHub 私有资源也可能以 404 隐藏权限问题 |

### 先确认实际出口，再判断“IP 被拒”

代理端口可达、请求返回 403，不等于目标走了预期节点。客户端可能因全局/规则模式、全局模式的分组选择（如 `GLOBAL`）、分流规则或 TUN 设置把目标送到 `DIRECT`；这时 403 反映的是直连出口，不是代理 IP 被拒。

排查时先查客户端日志或连接记录中的规则、组、节点与实际链路，再用同一目标做直连/代理对照，记录状态码、响应体和可得的实际出口。只有日志确认请求走了预期节点、且该节点仍返回同类拒绝页，才把原因归到出口 IP/地区/信誉或协议指纹；否则先修客户端的模式、分组或规则。

例：全局模式的 `GLOBAL` 组选中 `DIRECT`，规则模式的兜底规则指向代理组；同一目标直连 403、代理 200，差异在客户端把流量送到哪里，不是目标站封了代理 IP。

代理端口开放、能连目标只证明链路可用，不等于出口能过 WAF。WAF 还会看 ASN、地区、IP 信誉、TLS/浏览器指纹和会话行为；同一代理下载文档正常，目标站点仍可能因机房 ASN、地区不匹配或短时间高频请求直接 403。换出口时记录实际出口、ASN/地区和目标响应，不要用“能连”代替“能过”，也不要用连续轮换出口规避明确的限流冷却；429 持续时可用一个已核验出口做一次有界验证并记录。同一客户端可能持有多个出口（多监听端口、多节点订阅），**默认出口被拒不等于站点不可达**：先确认有几个可用入口，各发一次目标请求并比对响应体，再下结论。

确需判断“代理都不可用”或“站点对所有出口拒绝”时，需在任务期限内核对相关登记候选与协议，不只重试 `default`；混合端口的HTTP失败不代表SOCKS也失败。客户端里挂着的节点也算候选：同一监听端口背后的不同节点是不同出口，默认选中的节点被拒不代表其他节点不可用。只为取回正文时，找到有效路线就停止，不穷举剩余候选；预算不足以完成对照时报告未核验范围，不强判源站故障或整机无代理。

GitHub REST API 的 403 可能是限流：检查错误正文、`x-ratelimit-remaining`、`x-ratelimit-reset` 与 `retry-after`。官方规则要求等待指定冷却；已确认次级限流且无等待值时至少等 1 分钟，后续再指数退避。供应商明确规则优先于通用退避起点，不能将所有 403 当作网络不通。

## GitHub 加速镜像

加速镜像用于公开 GitHub 资源的取回：raw 单文件、Release 资产、archive 压缩包，以及部分服务支持的只读 git 传输。它只解决"取得到、取得快"，不解决权限、私有资源和推送，所以按资源类型与体积选路，不按"哪个站点还活着"选。

加速前缀是只读通道：它不接收推送，也不需要账号凭据。不要为加速域名配置 Git 凭据（`credential.<url>`）或推送地址（`pushurl`），也不要把令牌交给第三方加速站；经加速克隆或拉取后需要推送时，remote 的推送地址必须指回原站（如 `git remote set-url --push origin https://github.com/<owner>/<repo>.git`）。若同时配置了目录级或全局 `insteadOf`，推送地址要用不匹配该规则的形式（如 `https://github.com:443/...`），否则会一并被改写到镜像。

国内网络访问 GitHub 公开资源时，默认第一动作是套用该资源类型已核验的加速，不先直连、不为小文件先试直连；直连只作为加速不可用时的回退。回退直连首响约 3 秒仍无有效响应，即判该路线不可靠，改走加速或代理，不原样重复同一 URL、不靠延长超时等结果。

| 资源 | 首选 | 回退 | 说明 |
| --- | --- | --- | --- |
| raw 单文件、文档、KB 级小资产 | 已核验加速（含 jsDelivr 单文件）优先；无可用加速再登记代理或有界直连 | 所选路线失败后换另一适用路线 | 小文件同样先加速，不先直连试错；目标请求即验证 |
| Release 资产、archive、数 MB 以上的安装包 | 已核验加速镜像 | 按已有记录选稳定直连或代理，代理需有额度余量 | 大流量默认不占代理额度；已知直连不稳时不强制先试直连 |
| 只读克隆、`ls-remote` | 已核验支持Git传输的加速或代理，按已有记录选 | SSH 443或有界稳定直连 | `ls-remote`可核验协议支持；克隆后remote改回原站，私有资源不交公共加速，推送一律原站 |
| 仓库网页、REST API | 代理 / 直连 | — | 加速前缀不适用 |

没有可用代理不妨碍使用已核验的公开文件加速；没有适用加速时再回退代理或有界直连。大文件优先已核验镜像；不因镜像首页可用就认定raw、Release、archive和Git传输都可用。

前缀自身返回 403/429 时，问题在加速站而不是目标资源：该前缀拒绝或限流，换下一个已登记前缀，不重试同一 URL、不延长超时。先分清两种 403——目标站按自身规则拒绝（换前缀无用），与前缀拒绝转发（换前缀有效）；看响应头与响应体归属（`Server`、`Via`、拦截页特征），以及请求是否根本没到目标。公开前缀的可用性随时变化，同一天内不同前缀、不同前缀对不同资产都可能给出相反结果。

Release 资产换前缀后仍要按官方 digest 校验：`api.github.com` 的 release 元数据里带 `sha256`，直连 API 通常可用；取回文件后比对 `sha256sum` 或 `Get-FileHash`，不一致就丢弃并换通道，不带着未校验的二进制继续安装。

用法：按服务规则把完整原链接放在前缀之后，例如 `https://<加速前缀>/https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>`。这是 GitHub 资源加速，不是通用文档代理；Release、archive、raw、网页和 git 传输各自核验，不能从一种推断另一种可用。

jsDelivr 的 `gh` 路径（`https://cdn.jsdelivr.net/gh/<owner>/<repo>@<ref>/<path>`）可缓存并直出仓库内单文件，但它不是前缀加速，也不保证绕过 raw：未命中缓存时可能 301 到 `raw.githubusercontent.com`（实测同一仓库有的文件 200、有的 301 到 raw）。它只覆盖仓库文件，不支持 Release 资产、archive 和私有仓库；分支引用可能命中 CDN 缓存，需要与仓库当前内容一致时改用提交 SHA。把它当作 raw 的候选路线，取回后检查最终 URL 与状态；301 到 raw 不算加速成功，不因 CDN 首页可用就推断任意文件可取。

**发现与核验**

- 取候选：两个收录页、用户提供的前缀、已知种子；收录页不是实时状态，种子也不保证可用。
- 有界探测：按 raw、archive、Release（Range 前若干字节）、git 传输四类分别测；`scripts/check_github_mirrors.py` 一次给出可用性与速度，默认沿用当前进程网络环境，可用 `--direct` 或 `--proxy` 指定路线。可用性筛选按约 3 秒首响预算（`--timeout 3`），大文件下载进度另判。
- 判据：状态码、内容特征（ZIP 魔数、正文非 HTML 错误页）、字节数与耗时；超时记为不可判定，换其他候选，不原样重试同一路线，也不据此断言"不支持该资源"。
- 选路：每类取当次最快且可用的前缀；同类只用一个，不并发轮询多个镜像。
- 全不可用：按主表回退代理与有界直连，失败作为当次事实记录，不据此写"镜像已死"。

- 每次使用记录原始 URL、加速 URL、日期、执行位置、路线、HTTP/退出码、最终 URL、耗时与大小；有官方校验值时比对 SHA-256。原站不可达且无可信校验时只能说"文件取回"，不能声称与原文一致。
- 小样本测速只用于当次选路，不写成"某站更快"的长期结论；同一入口的表现随文件大小、时段与并发变化。一个文件可用只覆盖该目标与当时出口。
- 候选可从 [GitHub 文件加速](https://yishijie.gitlab.io/ziyuan/) 与 [gh-proxy 镜像站点收集](https://github.com/hunshcn/gh-proxy/issues/116) 发现；列表收录不证明当下可用，不维护"永久可用"的域名清单。
- 已有候选全部不可用、且任务确实需要加速时，可有界搜索新的公开候选（官方文档、镜像站索引、项目社区），把结果只当线索，按资源类型和目标文件核验；仍不可用就回退代理/直连或询问用户，不并发轮询，不把新候选写成永久默认。
- 第三方公共服务只用于适合公开分发的资源，不向其转发私有仓库、令牌、Cookie 或签名下载 URL；不关闭 TLS 校验来掩盖证书错误。
- 403/429 明确限流时遵守冷却；429 可用已核验的另一出口做一次有界验证，不连续轮换镜像或出口绕过；WAF 挑战页按错误分流转 `resilient-browser-fetch`，不默认套加速前缀。
- 加速取回失败（404、白名单拒绝、超时）先确认原始链接与服务支持范围，再换候选或回退路线；生产环境不依赖第三方公共加速，发布物走官方渠道或自有镜像。

**失效更换与健康检查**

- 判失效看归属：同一前缀的 raw、archive、Release、git 传输都失败，而站点首页仍能打开时，按该前缀当前不可用处理。403 正文是站点自定义拒绝语、带 `remote:` 前缀，或 `Server`/`Web-Server` 指向前缀，说明请求没到目标，换前缀即可，不当成 GitHub、仓库权限或凭据问题；单类失败只否定该类。
- 体检用 `scripts/check_github_mirrors.py --timeout 3 --targets <本次需要的类型>`：`ok` 才算可用，`timeout` 记不可判定并换候选，`fail` 按失败归属判断。只测本次要用的资源类型，不要求四类全绿；结果只对当次网络与目标有效。
- 换已有 remote：拉取地址换成新前缀（`git remote set-url origin https://<新前缀>/https://github.com/<owner>/<repo>.git`），推送仍走原站。用目录级或全局 `insteadOf` 时，`pushInsteadOf` 的 base 不能与 `insteadOf` 的值相同（同值会被当成无改写，push 回退到镜像），改用 `https://github.com:443/` 这类不匹配的写法；已有 `remote.*.pushurl` 指向 `https://github.com/...` 时也会先被 `insteadOf` 改写，需改成 `https://github.com:443/...` 或删除。换完分别用 `git ls-remote origin` 与原站 remote 核验读写路线；`git status -sb` 用的是本地缓存，不能证明远端状态。
- 记录：把日期、前缀、资源类型与结果写进 [local-observations.md](local-observations.md) 的带日期条目。那是本机当次事实，不是长期可用清单；隔一段时间、换网络或再次使用前重新体检。

## 多连接下载

镜像和加速站常按**单连接**限速；把同一文件拆成多段并发取回，可能比换路线更有效。它只缓解连接级限速，不修复权限、404、WAF、限流或源站故障，也不替代选路。

启用前确认：

- 文件较大，拆分收益能覆盖额外请求开销；aria2 默认 `--min-split-size=20M`，小于约 40 MiB 的文件不会分片。
- 目标支持 Range：`curl -sS -r 0-1023 -o /dev/null -w '%{http_code}\n' '<url>'` 返回 206；返回 200 时多连接不生效，或是镜像对当前资产忽略了 Range。同一前缀对不同文件的支持也可能不同，按目标重新确认。
- 单连接吞吐明显低于可用带宽，且服务方未禁止并发；公开资源或自有镜像才加并发，私有、签名或需要 Cookie 的资源不交给公共加速。

本机有 `aria2c` 时用四连接起步；没有就保持单连接 `curl`，不为一次下载自动安装。

```bash
aria2c \
  --max-connection-per-server=4 --split=4 --min-split-size=1M \
  --continue=true --file-allocation=none --max-tries=1 \
  --connect-timeout=10 --timeout=10 \
  --dir /path/to/dir --out <file-name> \
  '<mirror-url>'
```

- `-x/--max-connection-per-server` 默认 1，不显式设置不会多连接；`-s/--split` 默认 5，但受 `-x` 与 `--min-split-size` 共同约束。
- 同一文件有多个等价镜像时，把 URI 放在输入文件的同一行、用 TAB 分隔，`-s` 会在多个来源间分配连接；不同文件可用 `-j` 并发，但总连接数仍受服务端限流约束。
- `--continue=true` 支持断点续传；中断后保留 `.aria2` 控制文件，完成后自动删除。有官方 SHA-256 时下载后比对，不以“下完”代替内容正确。
- aria2c 与 curl 一样会读 `http_proxy`/`https_proxy`；要绕过显式代理用 `--all-proxy=`，但不能据此声称绕过透明路由。
- 出现 429/403 时降低并发或回退单连接，遵守冷却；429 可在冷却后用已核验的另一出口做一次有界验证，不连续轮换或继续加连接绕过限流。

判断收益时用同一 URL、同一路线比较单连接与多连接的耗时或吞吐，至少各测一次并记录文件大小、日期与时段；结果只用于当次选路，不写成“某站更快”的长期结论。大文件以持续进展和总期限判断，不用小页面 3–5 秒窗口。

不适用：pip/npm/uv 等包管理器下载（并发、锁文件与镜像配置由各自工具控制）；服务器不支持 Range 或明确限流；私有仓库、签名 URL 与需要认证的资源。

## GitHub 与 Git 客户端

GitHub 的网页/raw、git 传输（`clone`/`fetch`/`push`）和 LFS 对象是不同入口，可达性互不推断。加速镜像的 git 传输支持需逐站核验（`ls-remote` 可通不代表 `clone` 稳定），推送一律走原站。

- **内置抓取工具**：没有代理开关的 harness 抓取工具（如 `webfetch`）读取 GitHub raw/blob 正文时，把加速前缀套在原始 URL 前（形如 `https://<加速前缀>/https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>`）；只用于公开只读文件，不用它访问 API、网页、私有资源或推送。直连已失败过的同一 URL 不原样重试，换前缀或按既有记录改走 jsDelivr 等 CDN 镜像。
- **代理**：有可用代理时用本次命令的 `-c http.proxy=<代理URL> -c https.proxy=<代理URL>`，不改全局 `http.proxy` 或 `url.*.insteadOf`。git 经 libcurl 读 `http_proxy`/`https_proxy`/`NO_PROXY`，但 `NO_PROXY` 排除目标或客户端自有配置会让它静默改路；URL 级 `http.<url>.proxy` 优先于通用 `http.proxy`，换入口前用 `git config --get-urlmatch http.proxy <目标URL>` 查当前生效值，并用同一 URL 级键覆盖。用 `GIT_TRACE=1` 或 `GIT_CURL_VERBOSE=1` 看实际请求，输出含目标地址与代理，贴出前去掉凭据。代理地址带用户名密码时用进程环境变量传入，避免出现在命令行与进程列表。
- **SSH**：22 端口在国内常被阻断。先 `ssh -T -p 443 git@ssh.github.com` 验证，可用时用 `GIT_SSH_COMMAND='ssh -p 443 -o HostName=ssh.github.com'` 或本次 `-c core.sshCommand=...`；`~/.ssh/config` 属于全局配置，用户未要求不改。
- **加速镜像（只读）**：前缀按 git 传输核验后，`git clone --depth 1 https://<加速前缀>/https://github.com/<owner>/<repo> <dir>`；克隆完执行 `git remote set-url origin https://github.com/<owner>/<repo>`，后续 fetch/push 走原站。`ls-remote` 通但 `clone` 报 `early EOF` 时按连接中断换路线，不在同一前缀重试。
- **传输量**：只读浏览用 `--depth 1` 或 `--filter=blob:none`；要在该仓库提交或比对历史时用完整克隆，浅克隆的历史不完整。
- **中断**：`early EOF`、`RPC failed`、`The remote end hung up unexpectedly` 多为连接被掐断或超时，换路线（直连↔代理↔SSH 443）重试一次即可；`http.postBuffer` 只在有据时调整，不当作通用解法。
- **代理入口失败**：推送走原站，国内通常依赖代理。先用一次有界目标请求（如 `git ls-remote`）核验登记入口，失败就换其他已登记或已核验候选；仍不通立即报告，不连续重试同一 `push`。TLS 握手失败、连接超时或重置属于路线问题，换入口前不必反复推送试探。
- **push 被拒**：`non-fast-forward` 先 fetch 比较两侧提交（对齐判定见 `skill-authoring-sync`）；403/422 多为凭据、token 权限、分支保护或必需检查，换网络无效；不 `--force`。

## 依据与验证记录

- [curl 手册](https://curl.se/docs/manpage.html)：代理变量、`--proxy`、`--noproxy`、连接/总耗时与重试语义。
- [GitHub REST API 故障排查](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api)：403/429 限流、权限和超时分流。
- [gh-proxy 项目说明](https://github.com/hunshcn/gh-proxy)：资源类型及公共演示服务限制；不能据此推断所有同名服务能力相同。

上述页面于 2026-10-10 读取核对；本机目标测试见 [local-observations.md](local-observations.md)。Windows 下 curl.exe 的直连、代理、加速三条取回路线已实测，PowerShell 代码块另通过语法解析；环境变量设置与 Linux/macOS/CMD 示例完成文档核对，不宣称已逐个平台运行。
