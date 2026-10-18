# 本机代理资源登记（proxy-registry）

## 定位与原则

- 登记文件：`~/.config/proxy-resources.json`，每台机器一份，跨任务、跨 harness 复用，记住"这台机器有哪些代理资源、哪个优先"。
- 登记是线索不是事实：每次使用前做一次有界核验——**以经该端口的一次实际请求为准**（取回目标并看出口回显），端口监听只是线索；失效就更新或删除条目，不静默沿用。
- 与 [local-observations.md](local-observations.md) 的分工：登记文件是**结构化的当前资源索引**（机器可读、程序读写）；observations 是**带日期的验证叙事记录**（人读、存疑证）。登记条目的核验过程写进 observations，登记文件只留结论字段。
- 常见代理工具（mihomo 及其图形封装等）多以 HTTP 代理形式提供服务，登记 `type` 与 `url` 即可；工具进程名和端口因机器而异，不跨机器复制登记内容。
- 本机代理不止 mihomo 一类：`*ray`（v2ray/xray）、sing-box、ss/trojan/hysteria 等各有自己的进程名与常见端口，发现阶段按候选枚举，不假定只有一种。

## 候选发现：进程与端口扫描

登记为空或条目失效时，先枚举候选再逐个核验，不按端口段顺序盲试。候选来自进程名与配置（可读客户端 inbounds 配置）；**优先用进程实际监听的端口**，下表端口只是取不到归属时的人工兜底（WSL/容器/TUN 情形），不是事实：

| 候选家族 | 进程名线索（模糊匹配） | 常见端口线索 |
| --- | --- | --- |
| mihomo / Clash 系 | `mihomo`、`clash`、`clash-verge`、`mihomo-party`、`flclash` | 7890/7891（经典 http/socks）、7897（部分图形版默认）、9090（控制 API） |
| v2ray / xray 系（`*ray`） | `xray`、`v2ray`、`v2rayN`、`v2rayA`、`nekoray` | 10808/10809（图形端常见 socks/http）、1080 |
| sing-box 系 | `sing-box`、`nekobox`、`hiddify`、`karing` | 配置示例常见 2080，实际以 inbounds 为准 |
| 其它隧道 | `ss-local`、`shadowsocks`、`trojan`、`hysteria`、`tuic`、`naive` | 各自配置端口（常见 1080） |
| GUI / 系统级封装（核心不明或只做 TUN） | `surge`、`quantumult`、`stash`、`loon`、`netch`、`proxifier`、`surfboard` | 由各自设置决定，部分只做 TUN、不提供本地端口 |

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalAddress -match '^(127\.0\.0\.1|::1|0\.0\.0\.0|::)$' |
  Select-Object LocalAddress,LocalPort,OwningProcess
Get-Process | Where-Object ProcessName -match 'mihomo|clash|verge|sing-box|singbox|xray|v2ray|ss-local|shadowsocks|trojan|hysteria|tuic|naive|nekobox|hiddify|karing'
```

```bash
ss -ltnp | grep -E '127\.0\.0\.1|::1'
ps -eo pid,comm,args | grep -Ei 'mihomo|clash|sing-box|xray|v2ray|ss-local|shadowsocks|trojan|hysteria|tuic|naive'
```

进程名别用 `ss`、`ray` 这类两字母模式：会误命中 `csrss`、`lsass`、`CrossDevice…` 等系统进程与无关程序，噪声淹没真实候选。

三条判据，少一条就会把候选判错：

- **端口 ≠ 协议**：同一端口常同时接受 HTTP 与 SOCKS（mixed 端口），两协议各探一次比按端口号猜更快；`http://` 与 `socks5h://` 都试。
- **监听 ≠ 代理入口**：控制、统计、内核 API 入站在监听表里与代理端口无异；实测有监听端口两种协议都不可用（http 立即失败、socks 超时），它不是代理入口。
- **扫不到监听 ≠ 没有代理**：代理跑在 WSL、虚拟机或容器里、经回环转发暴露在宿主端口上时，宿主既没有该进程也没有监听条目；TUN/透明路由同样不进监听表。实测有端口在两条枚举路径里都没有 LISTENING 行、归属进程不明，但 TCP 探活成功且经它取回 200。**定论只认经该端口的一次实际请求**（取回目标并看出口回显），不认端口表。

每个候选一次有界探测（沿用 [network-access.md](network-access.md)“有界诊断与超时”的连接/总耗时期限），候选由进程名与配置给出、不在端口段上顺序扫；核验通过的各自登记一条，不互相覆盖。

上述枚举与探测已固化为 [scripts/probe_local_proxies.py](../scripts/probe_local_proxies.py)（纯标准库，`python -X utf8 scripts/probe_local_proxies.py`）：

- 候选来自三处：**命中代理家族名的进程自己监听的端口**（不猜端口表）、登记文件条目、`--port`；不扫端口段。
- 家族名表**可自定义**：`--match REGEX` 追加（可重复，按不区分大小写匹配），`--only-match` 只用自定义正则、忽略内置表；非法正则按用法错误退出（exit 2）。
- 命中进程却一个端口都没挂上时提示用 `--port`——宿主看不到该进程的端口（权限、WSL/容器）不能靠猜补。
- 对每个候选各做一次 `http` 与 `socks5` 有界探测，并先取一条**直连对照**比对出口；`--json` 输出供 agent 读。
- `--copy` 额外打印**可直接粘贴的代理环境变量行**（Windows 给 pwsh+cmd，其它给 bash；`--shell` 可指定）。只输出不写配置——改环境变量是用户的事，脚本不代劳。
- `--watch SEC` 常驻重扫，每轮一行：首轮 / 无变化 / 变化（点名新增与失效的端口）；`--json` 时每轮一行 NDJSON。
- 默认总预算 5 秒（`--budget`）、单次探测上限 2.5 秒（`--timeout`），候选同批并发。结论只分三态——可用 / 不是代理入口（对方按协议语义回了话，如 CONNECT 4xx、socks 问候被拒）/ 不可判定（超时、预算到点）。
- 收尾按结论**分堆点名**：可用入口逐个给 URL（http 优先，只有 socks5 通才给 `socks5://`）、出口 IP、来源（进程名 / 登记名 / `--port`）与排序（协议多的在前，同档按耗时，首个标首选）；随后点名不可判定、不是代理入口、未监听的分别是哪几个。**只有本轮没有可用入口时才展开盲区**，不输出“没有代理”。
- `--json` 除 `candidates[]` 外另给 `usable[]`：`{host, port, url, protocols, egress, sources, verdict, egressMatchesDirect}`，agent 不必自己过滤排序；`blindSpots[]` 恒在。

## 文件格式（JSON）

```json
{
  "updated": "<YYYY-MM-DD>",
  "default": "<proxies[0].name>",
  "proxies": [
    {
      "name": "<短名，如 mihomo-mixed>",
      "type": "http | socks5",
      "url": "http://127.0.0.1:<port>",
      "source": "registry | env | user | manual",
      "verified": "<YYYY-MM-DD>",
      "notes": "<一句备注：工具名、混合端口、适用范围>"
    }
  ]
}
```

- `source` 取值：`registry`（注册表/系统线索发现）、`env`（环境变量发现）、`user`（用户告知）、`manual`（文档或配置文件读到）。
- `default` 指向优先使用的条目；多代理并列时选最近核验可用者。
- **不把代理凭据写进登记文件**：需要认证的代理，`url` 留地址部分，凭据经环境变量或用户输入在单次任务中提供。

### 可选：制品镜像条目（`artifact_mirrors`）

同一文件可另存一个**与代理无关**的顶层数组 `artifact_mirrors`，记录本机核验过的制品基址（如 `PLAYWRIGHT_DOWNLOAD_HOST` 指向的镜像），字段为 `name`、`type`、`url`、`source`、`verified`、`notes`。它不参与代理选择：读取代理的调用只认 `proxies`，制品基址必须显式取出并设进对应下载器变量。

- 与 `proxies` 分开的理由：混入会被当成代理入口（按 `url` 取端口去探测），既探不通也污染候选。
- 每条都要写 `verified` 与核验口径（覆盖了哪个版本/revision、怎么核验的），并在 `notes` 注明该基址的适用范围与回退路线。
- 同样是**线索不是事实**：每次使用前按 [浏览器安装](browser-installation.md) 用 `--dry-run` 与包锁定的 revision 逐项对齐，缺件或校验不过就换路线，不因为登记过就默认可用。

## 读写流程

- **读**：任务需要代理 → 先读登记文件 → 对 `default`（或唯一条目）做一次有界探测 → 可用直接用；不可用把该条目标记失效（更新 `verified` 并在 `notes` 注明），再走发现流程。
- **写**：新发现（注册表 `ProxyServer` 线索、`netstat` 确认监听、环境变量、读配置）或用户提供的代理，核验通过后写入条目并刷新 `updated`；同机多个代理并列登记，不互相覆盖。
- **询问衔接**：登记无可用条目 → 按有界诊断探测常见端口与系统线索 → 仍无可用代理时**向用户提问**（交互式询问或文字均可），问清代理地址/端口或申请授权等待；拿到后先核验再登记，并按用户回复继续任务，不反复盲试、不静默放弃。

## 自检

- [ ] 登记值使用前做了有界核验，失效条目已更新或删除？
- [ ] 新核验可用的代理已登记（含 `source` 与 `verified`），登记文件无凭据明文？
- [ ] 找不到可用代理时询问了用户，而非盲试端口或放弃任务？
