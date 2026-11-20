---
name: network-access
description: >
  外链抓取、联网下载、Git 远端操作（clone/fetch/pull/push；推送走原站）或代理/镜像配置前的网络选路入口。
  本机代理客户端与系统代理体检（mihomo/Clash 的 profile、节点池、分组、订阅用量、多实例）也走本 skill。
  普通网页直连可用且稳定时可省代理；国内 Google、OpenAI 或已知直连不稳的站点优先代理，GitHub 按资源类型选择已核验镜像／加速、代理或稳定直连；普通小页面直连约3–5秒仍无有效响应时考虑切代理。
  部署新机、换网络或排查镜像/源配置时，先跑 scripts/check_network_env.py：默认只读配置，--probe 才做有界可达性探测。
  复用同站观测与本轮结果，按需读取代理登记；超时、403、5xx、429 按错误类型回退，不原样重发或绕过限流。
  包与浏览器下载、大文件多连接、安装失败分诊、镜像和跨平台配置按需读参考；纯本地操作不加载。HTML 提取、浏览器操作和 PowerShell 编码归各自 skill。
---

## 网络环境与资源访问

试验默认在国内、生产默认在海外；用户指定的环境优先。本 skill 决定实际请求路线，不因“涉及外网”就一律用代理，也不因一次能直连就认定稳定。

## 最短执行路径

1. **识别请求方与目标**：区分本机、WSL/容器、远程服务，以及网页、Git 传输、包和大文件。远程搜索服务不受本机回环代理控制，搜索成功不代表本地正文抓取可用。
2. **复用线索选路**：先用本轮同站、同客户端已确认的路线；需要历史线索时按域名检索[本机观测](references/local-observations.md)，只读命中片段，不通读整个记录。无先验时按下表选择，不默认双路测速。
3. **直接取目标并核验**：获取正文或文件本身就是路线验证，检查退出码、状态、最终 URL 与内容；不要先探测再用同一路线重复下载。带连接与总耗时上限，成功即复用原文或快照。
4. **按失败原因回退**：慢或传输失败才切换有依据的路线，权限错误检查授权，限流遵守冷却；需要排障时读[错误分流](references/network-access.md#错误分流)。同一 URL 同路线超时或传输错误后不原样重发。

## 本机网络与镜像体检

部署新机、换网络、确认 pip/npm/conda 实际走哪个源，或“装得慢、不确定有没有走镜像”时，先跑一次只读报告：

```bash
python -X utf8 <skill>/scripts/check_network_env.py
python -X utf8 <skill>/scripts/check_network_env.py --json --project .
python -X utf8 <skill>/scripts/check_network_env.py --probe
```

报告覆盖环境变量与**系统代理**（Windows Internet Settings、macOS `scutil --proxy`、Linux `gsettings`（GNOME））、Git `insteadOf`、pip/uv、npm/pnpm/yarn/corepack、conda、Playwright 制品变量、项目 `.npmrc`/uv 配置与锁文件下载主机。默认不联网；`--probe` 只对实际生效的 GitHub、npm registry、PyPI 索引各做一次有界请求，不重试。

- 配置回答“本机设置成了什么”，不证明“目标包现在可用”；镜像与文件仍需按目标包和版本实测。
- **系统代理不等于终端代理**：系统代理只影响遵循系统设置的应用；终端和多数 CLI 只看环境变量，TUN 才接管未设变量的流量。报告会同时给出两者，任一为空都不代表另一层没开。
- **Windows 有两套系统代理**：Internet Settings 供 WinINET/浏览器，WinHTTP 供部分服务；脚本读前者，服务走 WinHTTP 时用 `netsh winhttp show proxy` 另查。
- `--json` 里 `route.env` 是环境变量，`route.system` 是系统代理；以后者看 `enabled` 判断是否开启，`configuredServer` 只表示注册表里曾配置过。
- 代理登记只作线索；入口可用性用 `scripts/probe_local_proxies.py`，多实例看 `--json` 的 `instances[]`（按 PID 归组），本脚本不扫描端口。
- URL 中的账号口令与 npm 认证字段不会进入报告；锁文件固定主机不随换源自动改变。
- 只检查当前解释器的 pip；其他 Python 环境用该环境的 `python -m pip config list` 单独核对。
- GitHub 直连探测失败不代表仓库不可用；文件加速与 Git 传输候选按 `scripts/check_github_mirrors.py` 分别核验。

### 本机代理环境体检顺序

按“配置 → 接管 → 入口 → 客户端 → 出口”分层，不要用一层的结果代替另一层：

1. **配置层（只读、不出网）**：`check_network_env.py` 看环境变量、系统代理与登记。
2. **接管层**：确认是系统代理、环境变量还是 TUN 在接管；mihomo 的 TUN 开关看 `inspect_mihomo.py` 报告，其它客户端看是否出现 `tun`/`utun`/`Mihomo` 虚拟网卡或默认路由被接管。系统代理开启不影响未遵循它的终端，只设环境变量也不影响新开的 GUI 应用。
3. **入口层（会出网）**：`probe_local_proxies.py` 按进程与登记枚举候选，逐个做 HTTP/SOCKS5 探测并比对直连出口。
4. **客户端层（默认只读）**：`inspect_mihomo.py --list-instances` 先枚举实例，再按 `--config`/`--controller` 查 profile、节点池与分组；`--delay` 才测速。
5. **出口层**：经目标入口请求一次回显服务，确认出口与直连不同；`egressMatchesDirect: true` 说明该入口可能没真正生效。

常见误判：只看环境变量一行，系统代理开启时仍会以为没有代理；反过来只设环境变量时，新终端和 GUI 应用仍直连。报告会分列环境变量与系统代理，结论要写明是哪一层在生效。`--probe` 在 Windows/macOS 可能继承系统代理；Linux 的 gsettings 不会自动进入本脚本探测，需要时用 `--proxy` 指定。

### 代理客户端体检

端口可用只说明入口能连，不等于配置健康。要看 profile、节点池、分组当前选中、默认出口链路与失效节点时：

```bash
python -X utf8 <skill>/scripts/inspect_mihomo.py --list-instances
python -X utf8 <skill>/scripts/inspect_mihomo.py
python -X utf8 <skill>/scripts/inspect_mihomo.py --json --delay --group PROXY
```

默认只读，不发 `PUT`/`PATCH`、不切节点；`--delay` 才出网。定位优先用内核进程的 `-d`/`-f`，再退回候选目录；Windows 单客户端先扫描，扫描只覆盖已知客户端目录，零个候选或 `--process` 时才查进程，`--process` 可强制先查。**默认报告只覆盖一个实例**；发现多个代理相关进程时会在 stderr 提示。多实例先用 `--list-instances` 枚举每个实例的 PID、`-d`/`-f`、mixed-port、external-controller、listeners 与策略，再逐个用 `--config`/`--controller` 检查，不把单实例报告当整机结论。`--list-instances` 只覆盖 Clash 兼容控制 API；v2ray/xray、sing-box 等先用 `probe_local_proxies.py` 看入口，配置体检暂无等价能力。报告同时给出订阅与规则集的更新周期、缓存路径与新鲜度，不触发下载；节点数和订阅对不上时用 `--compare-subscriptions` 对比当前响应（会计入订阅流量）。判读口径、轮换策略与常见陷阱见[客户端体检](references/mihomo-inspection.md)。入口探测仍用 `probe_local_proxies.py`，两者不互相替代。

## 选路默认

| 场景 | 路线与切换条件 |
| --- | --- |
| 普通网页，直连已知可用且稳定 | 可直接访问，无需读取、发现或验证本机代理 |
| 国内普通小页面，无可用同站记录 | 可先有界直连；约3–5秒仍未取得有效响应、反复超时或速度明显不稳定时考虑代理加速，不反复等待完整长超时 |
| 国内 Google、OpenAI 或已知直连不通／不稳的普通站点 | 优先已有登记代理访问原站，免直连预探测；本轮有稳定直连证据或用户指定时可直连 |
| GitHub公开文件下载 | 国内网络默认先走该资源类型已核验的镜像／加速（raw、Release、archive 各自核验），小文件同样先加速，不为小文件先直连试错；无可用加速时才按登记代理→有界直连回退。直连首响约3秒仍无有效响应即判不可靠，改路且不原路重试 |
| 国内包与浏览器制品下载 | 按[依赖下载](references/dependency-downloads.md)与[浏览器安装](references/browser-installation.md)选已核验镜像或原站路线，保留私有源与锁文件；包源不代替浏览器制品源 |
| 大文件、Release、archive | 优先已核验镜像；无可用镜像时再稳定直连或代理，不默认消耗代理大流量；按大小、进展和带宽设置期限，不套小页面3–5秒阈值。单连接明显低于可用带宽且目标支持 Range 时，按[多连接下载](references/network-access.md#多连接下载)用 aria2c 拆分连接 |
| GitHub网页／API、私有资源与Git传输 | 网页／API及私有资源通常用代理或稳定直连；只读克隆可选已核验支持Git传输的加速。文件加速不通用于网页、API或Git，私有资源不交公共加速，推送走原站，细则见[Git 客户端](references/network-access.md#github-与-git-客户端) |
| 海外生产 | 原站直连优先，不继承本机回环代理或未经验证的公共镜像 |

**3–5秒是小页面改路的参考窗口，不是所有请求的硬超时**：GitHub 公开资源直连按约 3 秒首响判断，3 秒内无有效响应即改走加速或代理，不延长同一路线等待；普通小页面仍按 3–5 秒参考窗口。工具支持时设置相应首响／连接与总耗时预算；不能中止在途请求时，使用工具现有的有界期限，失败后换路，不假装已按阈值取消。慢但持续有有效下载进展的大文件、渲染等待与工具冷启动分别判断。已取到完整正文就直接使用，为后续同站请求记下较优路线，不为追求更快再抓一次。

## 代理与出口边界

- **需要代理时才查登记**：先读本机标准位置 `~/.config/proxy-resources.json`；登记只是线索，以经该入口的一次目标请求验证，不另发探针。本轮已确认的同环境入口可复用。登记失效才按[代理发现与登记](references/proxy-registry.md)有界查找；仍无可用入口时询问用户，不盲扫端口。
- **省略代理不等于直连**：工具可能继承环境变量或自有配置。要绕过显式代理时使用客户端的直连开关，例如 curl 的 `--noproxy '*'`、htmlmini 的 `--proxy direct`；不能据此声称绕过了透明路由。仅在出口诊断需要时查出口，不为每个网页额外请求回显服务。
- **配置只影响本次任务**：代理按消费者环境传入，不在会话开头无条件设置全局代理；优先命令级参数或必要的进程变量，不改系统设置和全局 Git 配置。Windows 与 *nix 的配置和协议差异见[跨平台代理配置](references/network-access.md#跨平台代理配置)。
- **代理不加速渲染**：渲染耗时在浏览器启动、等待与引擎阶梯，不在带宽；不要用全局代理"加速"渲染。代理按源选：普通网页直连优先，OpenAI 等已知直连不通的站点用代理。
- **推送依赖的代理失败即改路或报告**：GitHub 推送走原站并通常依赖可用代理。实际生效的代理入口失败时，用一次经该入口的目标请求判断可用性（如 `git ls-remote`），失败立即换其他已登记或已核验入口；候选都不可用就报告失败与已试路线，不对同一 `git push` 反复重试。凭据、权限或非快进错误换代理无效，按错误类型处理。
- **错误类型不能混用**：401／权限拒绝不能靠换代理修复；429 不轮换出口绕过。403／5xx 先按错误分流诊断，确认挑战页且确需渲染时才转 [resilient-browser-fetch](../resilient-browser-fetch/SKILL.md)，不一见状态码就启动浏览器。挑战页不等于 IP 封禁：先按该 skill 的检测层判断，不要在本 skill 内继续换出口或手写浏览器探针。
- **先确认实际出口，再判断“IP 被拒”**：代理客户端的模式、全局模式的分组选择（如 `GLOBAL`）或分流规则可能把目标送到 `DIRECT`；端口可达只证明入口可用，不证明请求走了预期节点。目标返回 403/WAF 拒绝页时，先查客户端日志或连接记录里的规则、组、节点与实际链路，再用同一目标对比直连与代理。确认走了预期节点仍被拒，才考虑出口 IP/地区/信誉或协议指纹；不要把客户端设置成直连造成的拒绝归因于代理 IP。排查顺序见[错误分流](references/network-access.md#错误分流)。
- **按策略隔离时用独立实例**：轮询、目标粘性、会话粘性等策略需要隔离时，用本机的实例管理脚本（示例名 `mihomo_instance.py`，未随本 skill 分发；从零生成模板与实例可参考公开的 [learnProxy](https://github.com/xuchaoxin1375/learnProxy)）或等价的后台进程管理方式分别启动实例，不靠切换 GUI profile。固定出口只在 `consistent-hashing`、`sticky-sessions` 或 `select` 下成立；`round-robin` 实例本来就会按连接轮换，不能承诺同一 worker 始终一个出口。每个实例独立 `-d`/`-f`、mixed-port、external-controller 和 listeners 端口段，可同时运行；同一实例内再用 `listeners` 按国家/worker 分流。不要用 `round-robin` 让同一会话每请求换 IP。TUN 只在一个实例开。
- **证据范围如实说明**：端口开放不证明代理协议或目标可用；代理可达不证明出口能过站点风控。一次失败不能断言全部候选不可用或源站故障，预算不够就报告尚未核验，不穷举补齐结论。
- **镜像保留来源与权限边界**：按资源类型核验，保留官方 URL；不向公共加速站转发私有仓库、凭据或签名链接，不关闭证书校验。GitHub 加速前缀（如 `gh-proxy.com`）是只读通道：只用于 clone/fetch 与文件下载，不向镜像推送，也不为镜像域名配置 Git 凭据（`credential.<url>`）或推送地址；推送与凭据只对原站使用。

## 按需读取

| 条件 | 入口 |
| --- | --- |
| 需指定代理、诊断超时／403／5xx、使用 GitHub 镜像或 Git | [网络诊断与回退](references/network-access.md)的相关章节 |
| 已确认挑战页、需要渲染 DOM，或要判断单站能否抓取 | [resilient-browser-fetch](../resilient-browser-fetch/SKILL.md)：按有头 → `chrome-late`／`cdp-attach` 的阶梯处理；不要在本 skill 内手写浏览器探针或反复换出口 |
| 部署新机、换网络、确认镜像/源配置、系统代理或装得慢 | `scripts/check_network_env.py` 的帮助；默认只读配置，`--probe` 做有界探测 |
| 代理登记缺失或失效、需要发现候选 | [代理登记](references/proxy-registry.md)；已有脚本 `scripts/probe_local_proxies.py`，参数查其帮助，不另写扫描器 |
| 需要看 mihomo/Clash 的 profile、节点池、分组选中与失效节点 | `scripts/inspect_mihomo.py`；多实例先用 `--list-instances` 枚举，再逐个 `--config`/`--controller` 检查；判读与陷阱见[客户端体检](references/mihomo-inspection.md)，只读，`--delay` 才出网 |
| 需要核验文件加速候选 | `scripts/check_github_mirrors.py` 的帮助；镜像首页可用不代表目标资源可用 |
| 大文件单连接慢、考虑 aria2c 多连接 | [多连接下载](references/network-access.md#多连接下载)的适用条件与参数；先确认 Range、单连接瓶颈与并发许可 |
| 安装 Python／Node.js／conda 依赖 | [依赖下载](references/dependency-downloads.md)，区分索引、包文件与额外下载，按其中“镜像选型顺序”判定；PyPI/uv 候选可先跑 `scripts/bench_pypi_mirrors.py` |
| 依赖安装报错、版本冲突、无匹配 wheel、PEP 668 或反复超时 | [依赖安装失败分诊](references/dependency-install-recovery.md)，先分段再决定换源、改约束、换工具链或重装 |
| 安装或下载浏览器制品 | [浏览器安装](references/browser-installation.md)，先复用本机环境，不自动安装 |
| 只需网页提取、搜索调度或全面资源盘点 | 分别按 [htmlmini](../htmlmini/SKILL.md)、[agentic-web-search](../agentic-web-search/SKILL.md)、[resource-inventory](../resource-inventory/SKILL.md)，不因引用重启完整网络流程 |

## 自检与验证

- [ ] 是否按站点稳定性选路，普通稳定网页未强制代理，已知不稳站点未重复直连试错？
- [ ] 是否仅在需要时读取代理登记，历史观测按域名检索，正文取回即验证且没有重抓？
- [ ] 是否区分显式代理、默认环境和透明路由，未把省参数叫作真直连？
- [ ] 是否把“系统代理开启”“环境变量已设”“TUN 接管”分开确认，没有用其中一层代替另一层？
- [ ] 目标返回 403/WAF 拒绝页时，是否先核对客户端实际命中的规则、组与节点，确认请求没有落到 `DIRECT`，再判断出口 IP 被拒？
- [ ] 回退是否有总耗时与次数边界，限流未被绕过，权限／挑战／源站故障未混淆？
- [ ] GitHub 公开资源是否先走已核验加速；直连约 3 秒无首响是否立即改路，且没有原样重发同一 URL？
- [ ] 推送等依赖代理的操作是否先核验入口，失败后改路或报告，没有反复重试同一路线？
- [ ] 大文件多连接是否只在单连接受限、支持 Range 且资源允许并发时启用，未用于小文件、私有资源或包管理器下载？
- [ ] 部署新机或怀疑走错源时，是否先看 `check_network_env.py` 报告的配置来源，而不是直接换镜像？
- [ ] 是否把配置报告当成可用性结论，或把 `--probe` 的一次成功当成所有包、平台与日期都可用？
- [ ] 看节点与分组时，是否把端口可用、节点名或历史延迟当成了实际出口与链路结论？
- [ ] 报告"节点池 0 个"且控制 API 不可用时，是否先让 API 可达（Unix socket 控制口用 `--controller unix:/path`）再下结论，而不是据"0 个"判成订阅失效？
- [ ] 看到 `round-robin` 轮换时，是否按目标是否要求会话一致来评价，而不是一律判成缺陷？
- [ ] 多实例时是否先用 `--list-instances` 枚举，再按实例分别检查，未把单实例报告当成整机结论？
- [ ] 是否把 `probe_local_proxies.py` 的"排序第一"当成任务默认出口，或把 `egressMatchesDirect: true` 的入口当成正常代理？

维护时运行仓库结构、链接与分发校验，桌面走查稳定直连、慢直连、已知代理站点、限流与大文件场景。改选路或体检脚本时跑 `python -X utf8 skills/network-access/tests/test_check_network_env.py`；改客户端体检脚本时跑 `python -X utf8 skills/network-access/tests/test_inspect_mihomo.py`；改入口探测脚本时跑 `python -X utf8 skills/network-access/tests/test_probe_local_proxies.py`；真实探测只在需要时执行，并记录实际环境、客户端、日期与路线。真实验证仅报告实际环境、客户端、日期与路线，未执行的平台或性能对照不声称通过。
