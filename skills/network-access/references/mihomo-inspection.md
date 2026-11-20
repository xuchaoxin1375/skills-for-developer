# 代理客户端配置与节点体检（mihomo / Clash 系）

回答的是"这套代理配置本身是否健康"：有哪些可用 profile、节点池多大、分组当前选中谁、哪些节点已经死了、为什么切组没效果。入口可用性与选路仍归 [SKILL.md](../SKILL.md) 与 [代理登记](proxy-registry.md)，本页不重复。

## 适用与边界

- 需要核对 profile 与订阅状态、节点与分组、当前链路、失效节点时读本页。
- 只读：脚本只用 GET 与本地延迟探测，不发 `PUT /proxies/{name}`、不 `PATCH /configs`、不写登记文件。
- 多实例按进程分别检查；默认单实例报告不代表整机。`--list-instances` 只枚举本地实例信息，不查 API。
- 不做逐节点真实出口核验：那需要切换节点（写操作，会改变当前代理行为），单次任务要另行取得授权并约定切回策略。
- 只覆盖 Clash 兼容控制 API（mihomo、Clash Verge Rev、mihomo-party、FlClash 等）；sing-box、xray 的本地接口不同，不套用本流程。

## 三层对象，报告要说清读的是哪层

| 层 | 是什么 | 常见位置 |
| --- | --- | --- |
| 配置源 | 订阅、本地 profile、merge/script 增强片段 | `%APPDATA%/io.github.clash-verge-rev.clash-verge-rev/profiles/`、`~/Library/Application Support/...`、`~/.config/mihomo/` |
| 运行时配置 | 客户端拼装后真正交给内核的那份 | 同目录下的 `clash-verge.yaml` 或 `config.yaml`，由客户端生成 |
| 控制 API | 内核当前认知（节点、分组选中、规则、连接） | `external-controller` 指向的回环端口 |

UI 里改的东西通常写回 profile 或运行时配置，不写回订阅；三者不一致时以控制 API 的当前状态为准，以运行时配置解释"为什么"。这三层是**单实例内部**的层级；多实例还要先加一层实例清单（PID、`-d`、`-f`、controller），否则 A 的 profile 与 B 的 API 会混在一起。

定位顺序：先看内核进程的 `-d`/`--directory` 与 `-f`/`--config`（Windows 查 CIM 命令行，Linux 读 `/proc`，macOS 用 `ps`），再退回候选目录扫描，最后才用 `--config`。Windows 单客户端默认先扫描（约 0.1 秒），扫描只覆盖已知客户端目录；自定义 `-d` 的多实例可能只看到一个，脚本会在 stderr 提示。零个候选或传 `--process` 时才查进程（约 0.3 秒）；要枚举全部实例用 `--list-instances`。Linux 的 `/proc` 读取很便宜，直接进程优先。进程可能看不见：以服务账户运行、TUN 模式、跑在 WSL/容器里，或 GUI 没拉起内核时，只能靠目录扫描或 `--config`。报告会写明"发现方式"。找不到配置时用 `--config` 显式指定，不要按文件名猜——不同客户端版本的文件名会变。**默认报告只覆盖一个实例；多实例先用 `--list-instances` 枚举。**

## 多实例：先枚举，再逐个检查

多实例的判据是**独立进程**，不是 GUI 里有多少 profile：每个实例有自己的 `-d`、`-f`、mixed-port、external-controller 与 listeners 端口段，可以同时运行。切换 GUI profile 不等于启动新实例。

```bash
python -X utf8 <skill>/scripts/inspect_mihomo.py --list-instances
python -X utf8 <skill>/scripts/inspect_mihomo.py --list-instances --json
```

`--list-instances` 只读本地文件与进程，不查 API；输出每个实例的 PID、客户端、`-d`、运行时配置、mixed-port、controller、listeners 与配置里出现的 `strategy`。完整检查再对每个实例执行：

```bash
python -X utf8 <skill>/scripts/inspect_mihomo.py --config <runtime> --controller <host:port>
```

- 没有实例管理脚本时，按进程命令行里的 `-d`/`-f` 枚举；Windows 用 `Get-CimInstance Win32_Process`，Linux 读 `/proc`，macOS 用 `ps`。

```powershell
Get-CimInstance Win32_Process -Filter "Name LIKE '%mihomo%' OR Name LIKE '%clash%'" |
  Select-Object ProcessId,Name,CommandLine
```

```bash
ps -eo pid,comm,args | grep -Ei 'mihomo|clash' | grep -v grep
```

- 实例管理脚本的 `list`/`status` 通常只列自己 PID 文件管理的实例，GUI 实例不在内；两者要合并。
- `--list-instances` 里 PID 为 `-` 的是目录扫描到的配置，不证明对应进程正在运行；PID 有值才说明能从进程 `-d`/`-f` 定位到。
- `listeners` 是同一实例的额外入站端口，不是独立实例；`171xx`、`172xx` 这类端口段只是本机约定，读到 `name`/`port`/`proxy` 再判断用途，不按端口号猜国家。
- 默认 `inspect_mihomo.py` 只报告一个实例；发现多个代理相关进程时会在 stderr 提示，不会自动汇总全部实例。
- `round-robin` 实例按连接轮换出口；需要同一 worker 固定出口时用 `consistent-hashing`、`sticky-sessions` 或 `select`，不要把固定出口当成所有实例的默认。

## 只读 API 与认证

| 端点 | 用途 |
| --- | --- |
| `GET /version` | 内核与是否 meta |
| `GET /configs` | 当前模式、端口、TUN、allow-lan |
| `GET /proxies` | 节点与分组、`now`、`history`、`alive` |
| `GET /providers/proxies` | 订阅更新时间、节点数、流量与到期 |
| `GET /providers/rules` | 规则集的更新时间和条数 |
| `GET /rules` | 规则数量、类型与兜底目标 |
| `GET /connections` | 实时连接链（`chains`）与命中的规则 |
| `GET /proxies/{name}/delay?url=&timeout=` | 单节点延迟（会出网；新版内核的 provider 节点可能 404） |
| `GET /group/{name}/delay?url=&timeout=` | 整组延迟（会出网）；嵌套组返回子组结果，不展开到叶子 |

新版内核的 provider 节点不在 `/proxies` 里，单节点测速会 404，只能对**成员全是叶子**的组做整组测速；含子组的组返回的是子组名，不能直接当节点结果用。认证用 `Authorization: Bearer <secret>`，secret 从运行时配置读；只走回环时风险有限，但不要把它写进报告或提交。更新类请求（`PUT /providers/proxies/{name}`、`PUT /providers/rules/{name}`、`PUT /configs?force=true`）不在只读检查内，执行前确认授权与流量代价。

## 节点缺失：先比内容，再看过滤

节点在订阅里有、运行配置里没有时，按这个顺序查：

- **先确认控制 API 真的读到了运行时**：报告"叶子节点 0 个"且控制 API 不可用时，多半是没读到内核（Unix socket 控制口、服务账户、TUN 等），不是节点真空。此时不要据"0 个"下"订阅失效/无可用节点"的结论；先让 API 可达（见下条"管道 / Unix socket"），或核对 profile 文件里 `proxies:` 的实际条数再判断。
- **先比 provider 本地节点与订阅当前响应**：`--compare-subscriptions` 会主动 GET 一次，列出"本地缺失 / 线上已移除"。有差异通常说明本地缓存旧于订阅，而不是分组写错。
- **再查过滤**：`filter`、`exclude-filter`、`use`、`include-all` 是否覆盖这个节点；名字能否过正则。
- **再确认端点**：新版 `/proxies` 不含 provider 节点，只看它会误判整池。
- **最后才看**组类型、`hidden`、健康检查和客户端显示。
- `updatedAt` 与缓存文件 mtime 都不能证明内容新鲜：重启会把 `updatedAt` 重置为缓存 mtime；304 或内容未变只推进时间；更新失败保留旧缓存。判断"有没有新节点"必须比内容，不能比时间。

## 判读口径

- **分组类型**：`select` 手动选中并在 `now` 回显；`url-test` 自动选延迟最低；`fallback` 按顺序取可用；`load-balance` 按策略分摊；`relay` 串联。`include-all`、`filter`、`exclude-filter`、`use` 决定成员从哪来、被谁挡掉。
- **链路不等于入口**：端口可达只证明能连；实际走哪条链要看兜底规则和连接记录的 `chains`。规则只有 `MATCH -> <组>` 时，未命中规则的流量都走那个组，切其他组不会改变结果。
- **名字不等于地区**：订阅里的节点名可以随便写。真实出口要按 IP/colo/ASN 判断，且需要逐节点验证。
- **延迟不等于目标站可用**：测速打的是测试 URL（常用 `generate_204`）。延迟低只说明到那个 URL 快，不代表目标站能过风控或不被限流。
- **历史不等于当下**：`history` 里的 0 或 `alive: false` 是上次结果，报告要注明"需复测"，不能直接写成"节点已死"。
- **provider 新旧**：对比 `updatedAt` 与配置里的 `interval`；订阅过期看 `subscriptionInfo.Expire`，用量看 `Upload + Download`。空 `file` provider 会让引用它的分组退化成空组。
- **节点可能只在一个端点里**：新版内核的 provider 节点只出现在 `/providers/proxies`，`/proxies` 只给分组与内置项；旧版两边都有。读节点池要合并两个来源，否则会把整池节点报成只剩分组。

## 订阅、规则集与缓存

订阅节点、规则集、Geo 数据是三条独立更新链路，没有"全局关闭"开关。

- `interval` 的单位是秒；**不写等 0**：启动时拉一次，之后不再轮询。`type: file` 不下载，监听本地文件变化。
- 重启时先读缓存，只有缓存年龄超过 `interval` 才强制刷新；因此 `updatedAt` 会被重置为缓存文件的 mtime，**重启后变旧不代表没更新**。更新失败按指数退避重试，保留旧缓存。
- 内容没变时只把 mtime 推到当前时间，不重写内容；mtime 停滞也不等于没更新。
- 缓存位置：显式 `path` 以 `-d` 的 HomeDir 为基准（相对路径不是相对 YAML 所在目录）；HTTP 未写 `path` 时按 URL 的 MD5 落在 `<HomeDir>/proxies/<md5>`，规则集在 `<HomeDir>/rules/<md5>`。API 不暴露缓存路径，只能这样推算。
- `proxy` 字段不写不等于直连：实测会走策略路由，最终由规则决定；要确定行为就显式写 `proxy: DIRECT` 或某个组。
- 订阅用量与 ETag 存在 `<HomeDir>/cache.db`；`health-check.interval` 是测速节奏，与订阅更新无关，且 `lazy` 默认 true，没被使用的节点不会全量测速。
- 显式固定 `path` 后换 URL，旧缓存可能顶替新订阅；换 URL 时同步删缓存。`size-limit` 可限制单次下载大小。

判断新鲜度要同时看 API 与文件：`updatedAt` 给内核视角，缓存文件 mtime 给磁盘视角。只看其中一个都会误判。

手动刷新：订阅用 `PUT /providers/proxies/{name}`，规则集用 `PUT /providers/rules/{name}`；返回 `204` 只表示请求被受理，是否真的换内容要回查 `updatedAt`、节点数与日志。更新会重建相关的 `load-balance`/`select` 组，可能在途连接受影响，也会消耗一次订阅请求。

Verge 的**本地 profile** 菜单没有"更新"（只有使用/编辑/删除）：本地文件没有上游可拉。"使用"只是重新加载配置，缓存年龄未超过 `interval` 时不会重新下载；远程 profile 的"更新"只刷新 profile 文件，不等于运行中的 provider 缓存已刷新。

## 出口轮换策略按场景选

| 策略 | 行为 | 适合 |
| --- | --- | --- |
| `round-robin` | 按连接轮换出口 | 无登录公开页面爬虫，用多个出口分散频次 |
| `consistent-hashing`（默认） | 按目标主机固定出口 | 同一站点需要稳定 IP，或减少连接抖动 |
| `sticky-sessions` | 按会话粘住出口 | 带登录态、购物车、验证码流程 |
| `select` 固定单节点 | 人工锁定一个出口 | 需要可复现的出口证据，或排障对照 |
| `url-test` | 自动取最快 | 只追求速度、不介意延迟波动时换出口 |

看到 `round-robin` 不要判成缺陷：对匿名公开页爬虫是刻意选择，对需要会话一致性的站点才是风险。报告按目标类型给建议，不按"哪种更高级"排序。同一个 `load-balance` 组内节点数太少时，轮换带来的 IP 变化范围也有限，要结合成员数看。

## 常见结构与陷阱

- **空组**：`use` 指向空 provider，或 `filter` 一个都没命中。选中空组等于放弃代理，UI 上不一定报错。
- **主选择组混入 `DIRECT`/`REJECT`**：误选一次就是整机直连或全阻断，且没有明显提示。
- **订阅信息节点**：把"剩余流量""到期时间"做成同名节点。`exclude-filter` 只作用于分组展开，客户端层的 `junk-filter` 是另一道；两道都没覆盖时，这些节点仍会参与 provider 健康检查。
- **关键词误伤**：`exclude-filter` 里的"倍率""试用"等词会把真实节点一并挡掉，表现为 provider 条数多于分组内可见节点数。
- **规则过薄**：只有 `MATCH` 兜底时，地区组只在特定进程名或规则集命中时生效；用户以为"切组没效果"通常就是这里。
- **系统级接管**：TUN 和系统代理都关闭时，只有显式设置代理变量的进程受影响；新终端默认直连。
- **secret 短**：只绑回环时风险有限，但本机任意进程都能读取节点与切换节点；报告只写长度，不回显值。
- **管道 / Unix socket 不校验 secret**：`external-controller-pipe` 与 `external-controller-unix`（含进程参数 `-ext-ctl-unix` / `-ext-ctl-pipe`）访问时不验证 secret，能读到 socket 的本机用户就能切节点；`allow-lan` 与 `external-controller: 0.0.0.0` 同时开才需要强 secret 与防火墙。
- **`-ext-ctl` / `-ext-ctl-unix` / `-secret` 会覆盖配置**：进程命令行优先于 YAML，报告要先按进程参数取控制口和密钥，再去读配置。macOS 上 Clash Verge Rev 默认用 `-ext-ctl-unix <socket 路径>`，配置里 `external-controller` 为空；此时只有走 Unix socket 才能读到运行时节点，脚本会自动解析进程参数里的 socket 路径，或用 `--controller unix:/path/to/socket` / `--controller /path/to/socket` 显式指定。

## 报告口径与脱敏

报告包含：可用配置、运行时状态、节点池、订阅与规则集、分组与当前选中、默认出口链路、规则面、延迟（可选）、提示与风险、盲区。多实例时每个实例一份报告，或明确写出本次只报告哪个实例；单实例报告不能代替整机实例清单。

固定脱敏项：`secret` 只在报告里写"是否设置 + 长度"；订阅 URL 只保留主机名；节点 `server`、`uuid`、`password` 不进入任何输出。报告仍会含本机路径与节点名，外发前按需裁剪。

## 工作流

多实例先跑 `--list-instances` 选定实例；下面的步骤都针对已选定的一个实例。

1. 先不加 `--delay` 跑一次，确认配置发现正确、API 可达、默认链路与分组符合预期。
2. 读"提示与风险"：空组、混入直连、轮换策略、不可达节点、默认链路。
3. 节点数与订阅对不上时，加 `--compare-subscriptions` 对比本地 provider 与订阅当前响应；它只 GET，会消耗订阅流量，但不更新配置。
4. 需要现势健康时加 `--delay`，用 `--group` 收窄范围；它会真实出网，逐节点一次请求。
5. 订阅或规则集疑似过期时，先看 `updatedAt` 与缓存文件 mtime 是否一致，再判断是更新失败还是重启重置；需要手动触发更新时，那是写操作，单独确认。
6. 目标站 403 或超时，转 [SKILL.md](../SKILL.md) 的错误分流：先看 `/connections` 的 `rule` 与 `chains`，确认没有落到 `DIRECT`，再判断出口 IP 或风控。
7. 需要"每个节点的真实出口"时，单独申请切节点授权，并写明切回策略；只读检查给不出这个结论。

## 盲区

- 逐节点出口 IP、ASN 与地区：需要切换节点或按节点发请求，属写操作/额外流量。
- 延迟只代表测试 URL；目标站的限流、挑战与地区限制不在本检查内。
- 客户端专有的 profile 增强链（merge/script）不逐条求值；只按运行时产物判断。
- 触发订阅或规则集更新、修改 provider、切换节点都是写操作，不在只读检查内。
- `--compare-subscriptions` 会真实请求订阅地址，计入订阅流量与请求次数；响应不是 Clash 配置时只能报"未解析"。
- 默认报告只覆盖一个实例；`--list-instances` 只枚举本地信息，不查 API，多实例的节点池与分组仍需逐个检查。
- 跨平台：Windows 的 `%APPDATA%` 路径与 macOS/Linux 不同，脚本按候选目录枚举，找不到时以 `--config` 为准。
