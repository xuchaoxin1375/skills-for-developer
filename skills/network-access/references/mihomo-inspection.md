# 代理客户端配置与节点体检（mihomo / Clash 系）

回答的是"这套代理配置本身是否健康"：有哪些可用 profile、节点池多大、分组当前选中谁、哪些节点已经死了、为什么切组没效果。入口可用性与选路仍归 [SKILL.md](../SKILL.md) 与 [代理登记](proxy-registry.md)，本页不重复。

## 适用与边界

- 需要核对 profile 与订阅状态、节点与分组、当前链路、失效节点时读本页。
- 只读：脚本只用 GET 与本地延迟探测，不发 `PUT /proxies/{name}`、不 `PATCH /configs`、不写登记文件。
- 不做逐节点真实出口核验：那需要切换节点（写操作，会改变当前代理行为），单次任务要另行取得授权并约定切回策略。
- 只覆盖 Clash 兼容控制 API（mihomo、Clash Verge Rev、mihomo-party、FlClash 等）；sing-box、xray 的本地接口不同，不套用本流程。

## 三层对象，报告要说清读的是哪层

| 层 | 是什么 | 常见位置 |
| --- | --- | --- |
| 配置源 | 订阅、本地 profile、merge/script 增强片段 | `%APPDATA%/io.github.clash-verge-rev.clash-verge-rev/profiles/`、`~/Library/Application Support/...`、`~/.config/mihomo/` |
| 运行时配置 | 客户端拼装后真正交给内核的那份 | 同目录下的 `clash-verge.yaml` 或 `config.yaml`，由客户端生成 |
| 控制 API | 内核当前认知（节点、分组选中、规则、连接） | `external-controller` 指向的回环端口 |

UI 里改的东西通常写回 profile 或运行时配置，不写回订阅；三者不一致时以控制 API 的当前状态为准，以运行时配置解释"为什么"。

定位顺序：先看内核进程的 `-d`/`--directory` 与 `-f`/`--config`（Windows 查 CIM 命令行，Linux 读 `/proc`，macOS 用 `ps`），再退回候选目录扫描，最后才用 `--config`。Windows 单客户端默认先扫描（约 0.1 秒），出现多个客户端、一个都没找到，或传 `--process` 时才查进程（约 0.3 秒）；Linux 的 `/proc` 读取很便宜，直接进程优先。进程可能看不见：以服务账户运行、TUN 模式、跑在 WSL/容器里，或 GUI 没拉起内核时，只能靠目录扫描或 `--config`。报告会写明"发现方式"。找不到配置时用 `--config` 显式指定，不要按文件名猜——不同客户端版本的文件名会变。

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

新版内核的 provider 节点不在 `/proxies` 里，单节点测速会 404，只能对**成员全是叶子**的组做整组测速；含子组的组返回的是子组名，不能直接当节点结果用。认证用 `Authorization: Bearer <secret>`，secret 从运行时配置读；只走回环时风险有限，但不要把它写进报告或提交。

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
- **管道 / Unix socket 不校验 secret**：`external-controller-pipe` 与 `external-controller-unix` 访问时不验证 secret，能读到 socket 的本机用户就能切节点；`allow-lan` 与 `external-controller: 0.0.0.0` 同时开才需要强 secret 与防火墙。
- **`-ext-ctl` / `-secret` 会覆盖配置**：进程命令行优先于 YAML，报告要先按进程参数取控制口和密钥，再去读配置。

## 报告口径与脱敏

报告包含：可用配置、运行时状态、节点池、订阅与规则集、分组与当前选中、默认出口链路、规则面、延迟（可选）、提示与风险、盲区。

固定脱敏项：`secret` 只在报告里写"是否设置 + 长度"；订阅 URL 只保留主机名；节点 `server`、`uuid`、`password` 不进入任何输出。报告仍会含本机路径与节点名，外发前按需裁剪。

## 工作流

1. 先不加 `--delay` 跑一次，确认配置发现正确、API 可达、默认链路与分组符合预期。
2. 读"提示与风险"：空组、混入直连、轮换策略、不可达节点、默认链路。
3. 需要现势健康时加 `--delay`，用 `--group` 收窄范围；它会真实出网，逐节点一次请求。
4. 订阅或规则集疑似过期时，先看 `updatedAt` 与缓存文件 mtime 是否一致，再判断是更新失败还是重启重置；需要手动触发更新时，那是写操作，单独确认。
5. 目标站 403 或超时，转 [SKILL.md](../SKILL.md) 的错误分流：先看 `/connections` 的 `rule` 与 `chains`，确认没有落到 `DIRECT`，再判断出口 IP 或风控。
6. 需要"每个节点的真实出口"时，单独申请切节点授权，并写明切回策略；只读检查给不出这个结论。

## 盲区

- 逐节点出口 IP、ASN 与地区：需要切换节点或按节点发请求，属写操作/额外流量。
- 延迟只代表测试 URL；目标站的限流、挑战与地区限制不在本检查内。
- 客户端专有的 profile 增强链（merge/script）不逐条求值；只按运行时产物判断。
- 触发订阅或规则集更新、修改 provider、切换节点都是写操作，不在只读检查内。
- 跨平台：Windows 的 `%APPDATA%` 路径与 macOS/Linux 不同，脚本按候选目录枚举，找不到时以 `--config` 为准。
