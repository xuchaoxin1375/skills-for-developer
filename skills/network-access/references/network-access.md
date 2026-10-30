# 网络访问、代理与回退

## 环境与路线

试验默认在国内、生产默认在海外，是技术方案的背景假设，不代替具体任务的实测。包镜像、GitHub 文件加速和代理解决的问题不同：包镜像可能同步滞后，文件加速只支持特定 URL，代理仍受目标权限和限流约束。

先确定请求由谁发出。本地代理只能直接服务能访问它的客户端；远程 `web_search`/`web_fetch` 服务不会因本机设置环境变量就自动使用该代理。WSL、容器和远程服务器中的 `127.0.0.1` 指向各自环境；访问宿主机代理时按网络模式选择地址，并核验监听范围和可达性。

国内环境已有可用代理时优先访问官方原站；无代理时才为支持的公开资源选择已核验的镜像或加速。大体积制品与大包（浏览器制品、Electron 组件、模型权重等）例外：默认先试已核验的镜像或直连原站，不让有额度限制的代理承担大流量，缺件或校验不过再回退官方（可经代理）。海外生产先测试原站直连，不继承本机环回代理地址，也不把第三方公共加速服务作为未经验证的生产依赖。

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

小页面诊断的推荐起点：连接超时 5 秒、单次总耗时 20 秒；大文件按大小和带宽调整，不能把小页面期限套给所有下载。连接超时覆盖 DNS/连接/握手，总耗时覆盖整个取回；重试另受次数和任务总期限约束。

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

双路探测只为选路，两条探测可并行发起以缩短判断时间；选定后正文抓取显式沿用获胜路线（`--proxy` 或 `--noproxy '*'`），同一任务内不重复探测。
内置网页抓取等工具走宿主进程默认网络环境，其路线不受本节参数控制；需要指定路线时改用带显式参数的 curl 取回。
工具按从轻到重：内置抓取→显式 `curl`→需 TLS 伪装时 `curl_cffi`（同路线复用代理）→确认挑战页（含 5xx 异构后现挑战特征）才转 `resilient-browser-fetch`；`curl` 已 200 落盘即交付，不逐级重试；`curl` 5xx 未做异构对照前不判源站死。

同时检查退出码、HTTP 状态、最终 URL、正文或文件格式；HTTP 200 可能是登录页、拦截页或加速站首页，TCP 端口通只证明存在监听服务。
curl 默认不会把 HTTP 403 判为进程失败，下载交付可用 `--fail` 并仍保存必要的错误诊断；不要用 HEAD 成功代替实际 GET 核验。

`--max-time` 只限制单次取回；curl 开启 `--retry` 后每次尝试重新计时，`--retry-max-time` 只在开始新重试前检查，已启动的取回仍可能超过这个期限。需要硬总期限时由调用方限制整个进程；本例不自动重试，避免与 Agent 重试叠加。

## 错误分流

| 现象 | 检查与处理 |
| --- | --- |
| DNS、连接或 TLS 握手失败，HTTP 尚未返回 | 核验代理协议/地址、解析、证书和出口；对同一公开目标做有界的另一条路线对照，不凭一次失败断言整个网络故障 |
| 已连接但读取超时/大文件慢 | 检查文件大小、下载进展、上游速度和总耗时；仅有依据时调整期限或采用支持的续传 |
| HTTP 401/403，正文提示权限或登录 | 检查认证、资源权限和目标 URL；代理/镜像不能修复凭据或授权，停止重复请求 |
| HTTP 403，正文只有简短 Forbidden，无挑战/登录/限流特征 | 先排除只按请求头拦截：同一路线补 `User-Agent`、`Accept`、`Accept-Language`、`Referer` 重测一次；200 即沿用该请求头。仍 403 再按权限、WAF/挑战或限流分流 |
| HTTP 403，正文为 WAF/挑战/区域拦截 | 保留失败来源与页面信息；确需渲染取证时转 `resilient-browser-fetch`，不默认套 GitHub 加速前缀 |
| HTTP 403/429 且正文或响应头明确提示限流 | 遵守 `Retry-After`、供应商重置时间和共享冷却；按 `agentic-web-search` 调度，不换出口绕过 |
| HTTP 5xx（含 500/502/503/504 及 Cloudflare 520 系） | 简头 curl 的 5xx 可能是反爬指纹拦截，不是源站死的充分证据。先保留状态码、正文与 `cf-ray`/`server` 头等证据，再换出口有界对照一次（直连↔代理，沿用“有界诊断与超时”的单次上限，不叠加自动重试）；另一路成功即沿用该路。两路一致 5xx 时补一次异构对照：补全浏览器头（Accept/Accept-Language/Upgrade-Insecure-Requests/Sec-Fetch-*）重测，或同路线 `curl_cffi`，或真实浏览器；出现 302 跳 `/_sc/challenge`、`/_sec/`、`challenge`、`captcha`、`turnstile`，或 403 带 `sct`/`cf_clearance` cookie、`X-Robots-Tag: noindex`，即按挑战页转 `resilient-browser-fetch`。异构仍 5xx 才判源站故障并记录，不逐个出口轮询，不转镜像加速 |
| HTTP 404 或加速站拒绝 URL | 检查原始链接、分支/标签、服务支持范围；GitHub 私有资源也可能以 404 隐藏权限问题 |

代理端口开放、能连目标只证明链路可用，不等于出口能过 WAF。WAF 还会看 ASN、地区、IP 信誉、TLS/浏览器指纹和会话行为；同一代理下载文档正常，目标站点仍可能因机房 ASN、地区不匹配或短时间高频请求直接 403。换出口时记录实际出口、ASN/地区和目标响应，不要用“能连”代替“能过”，也不要用轮换出口规避明确的限流冷却。

GitHub REST API 的 403 可能是限流：检查错误正文、`x-ratelimit-remaining`、`x-ratelimit-reset` 与 `retry-after`。官方规则要求等待指定冷却；已确认次级限流且无等待值时至少等 1 分钟，后续再指数退避。供应商明确规则优先于通用退避起点，不能将所有 403 当作网络不通。

## 无代理的 GitHub 文件加速

可从 [GitHub 文件加速](https://yishijie.gitlab.io/ziyuan/) 与 [gh-proxy 镜像站点收集](https://github.com/hunshcn/gh-proxy/issues/116) 发现候选；列表收录不证明当下可用。服务可能有 URL 白名单、文件大小、地域、配额及访问频次限制，引用前核验目标，不维护“永久可用”的域名清单。

对支持的公开 GitHub 文件，可按服务规则把加速前缀包裹在完整原链接之前。例如候选形式 `https://gh-proxy.com/https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>`；这是 GitHub 资源加速，不是通用文档代理。Release、archive、raw、网页和 git clone 各自验证，不能从一种推断另一种可用。

- 记录原始 URL、加速 URL、测试日期、执行位置、路线、HTTP/退出码、最终 URL、耗时及内容核验方式。引用事实仍指向原始官方来源，取回路径另记。
- 同一公开文件可比较原站与加速结果的 SHA-256；下载产物优先对照官方签名/校验值。原站不可达且无可信校验时，只能说明“文件取回”，不能声称与原文一致。
- 第三方公共服务只用于适合公开分发的资源，不向其转发私有仓库、令牌、Cookie 或签名下载 URL；不关闭 TLS 校验来掩盖证书错误。
- 一个小文件可用只覆盖该目标与当时出口；生产、WSL/容器、其他平台、大文件和 git clone 的状态另行验证。限流后遵守冷却，不能逐个镜像轮询同一受限站点。

## GitHub 与 Git 客户端

GitHub 的网页/raw、git 传输（`clone`/`fetch`/`push`）和 LFS 对象是不同入口，可达性互不推断。文件加速只服务文件取回，不能当 remote 或 clone 源；推送走原站，不经第三方加速。

- **代理**：有可用代理时用本次命令的 `-c http.proxy=<代理URL> -c https.proxy=<代理URL>`，不改全局 `http.proxy` 或 `url.*.insteadOf`。git 经 libcurl 读 `http_proxy`/`https_proxy`/`NO_PROXY`，但 `NO_PROXY` 排除目标或客户端自有配置会让它静默改路；用 `GIT_TRACE=1` 或 `GIT_CURL_VERBOSE=1` 看实际请求，输出含目标地址与代理，贴出前去掉凭据。代理地址带用户名密码时用进程环境变量传入，避免出现在命令行与进程列表。
- **SSH**：22 端口在国内常被阻断。先 `ssh -T -p 443 git@ssh.github.com` 验证，可用时用 `GIT_SSH_COMMAND='ssh -p 443 -o HostName=ssh.github.com'` 或本次 `-c core.sshCommand=...`；`~/.ssh/config` 属于全局配置，用户未要求不改。
- **传输量**：只读浏览用 `--depth 1` 或 `--filter=blob:none`；要在该仓库提交或比对历史时用完整克隆，浅克隆的历史不完整。
- **中断**：`early EOF`、`RPC failed`、`The remote end hung up unexpectedly` 多为连接被掐断或超时，换路线（直连↔代理↔SSH 443）重试一次即可；`http.postBuffer` 只在有据时调整，不当作通用解法。
- **push 被拒**：`non-fast-forward` 先 fetch 比较两侧提交（对齐判定见 `skill-authoring-sync`）；403/422 多为凭据、token 权限、分支保护或必需检查，换网络无效；不 `--force`。

## 依据与验证记录

- [curl 手册](https://curl.se/docs/manpage.html)：代理变量、`--proxy`、`--noproxy`、连接/总耗时与重试语义。
- [GitHub REST API 故障排查](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api)：403/429 限流、权限和超时分流。
- [gh-proxy 项目说明](https://github.com/hunshcn/gh-proxy)：资源类型及公共演示服务限制；不能据此推断所有同名服务能力相同。

上述页面于 2026-10-10 读取核对；本机目标测试见 [local-observations.md](local-observations.md)。Windows 下 curl.exe 的直连、代理、加速三条取回路线已实测，PowerShell 代码块另通过语法解析；环境变量设置与 Linux/macOS/CMD 示例完成文档核对，不宣称已逐个平台运行。
