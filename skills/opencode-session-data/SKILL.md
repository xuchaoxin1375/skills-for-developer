---
name: opencode-session-data
description: >
  OpenCode 本地会话历史的查询、检索与迁移：跨工作目录列出或检索历史会话（标题与正文），
  按目录、项目、时间过滤，定位会话来源与子会话，导出或移动会话，理解 session_v2/session_message
  表结构与只读查询方式；含 session-search 命令、/api/session 参数与 WebUI 入口。
  用于“上次在哪个项目讨论过某话题”“列出所有项目的会话”“这个会话在哪个目录”
  “批量导出或迁移会话”等问题；不用于 OpenCode 配置、provider、插件、TUI 设置或模型目录维护。
---

## 跨项目会话查询

OpenCode 的会话集中存在一个本地数据库里，与当前工作目录无关；“只看到本目录会话”来自客户端列表过滤，不是数据隔离。需要跨项目检索时，走数据库或服务端 API，不要逐个目录切换。

### 结论速查

| 需求 | 入口 |
| --- | --- |
| 在 TUI 里跨项目检索标题与正文 | `/session-search`（TUI 插件，选中直接跳转） |
| 在 TUI 里按标题/项目浏览 | `Ctrl+O` 或 `/open`（内置，不含正文） |
| 在全部项目里搜标题与正文（终端） | `session-search <查询词>` |
| 列出最近会话（全部目录） | `session-search` |
| 清理超过 N 天未更新的会话 | `session-prune --older-than 7d`（先预览，`--apply` 执行） |
| 不装工具，只查标题 | `opencode api get "/api/session?search=<词>"` |
| 精确 SQL、批量导出、字段核对 | 只读打开 `opencode.db` |

## 数据位置与结构

- 默认库路径：`~/.local/share/opencode/opencode.db`；`OPENCODE_DB` 环境变量可覆盖，`opencode debug paths db` 打印当前渠道实际使用的库路径。
- 会话主表：`session_v2`（当前）与 `session`（V1 旧表）；消息在 `session_message`，旧消息在 `message` + `part`。
- 关键字段：`id`、`title`、`directory`、`project_id`、`parent_id`（子会话）、`time_updated`、`time_archived`。
- 目录字段不统一：同一路径可能存成 `C:/repos/x` 或 `C:\repos\x`，过滤用子串而不是全等比较。
- 查询一律只读打开（`mode=ro` 或 `readOnly: true`）。OpenCode 运行中使用 **WAL**(Write-Ahead Logging, 预写日志)，只读并发安全；不要在服务运行时写库、删库或改表。
- 当前正在进行的会话可能延迟落库；刚发出的内容查不到时，等本轮结束再查。

## session-search 命令

`session-search` 是本 skill 的配套 **CLI**(Command-Line Interface, 命令行界面)，用 Node.js 的 `node:sqlite` 直接读库，不需要 OpenCode 服务在线。

- 安装：由 `scripts/link-skills.ps1` / `link-skills.sh` 从 `skills/opencode-session-data/` 注册；Windows 装到 `%USERPROFILE%\.local\bin\`（`session-search`、`session-prune` 各带 `.cmd` + `.ps1` 包装），Linux 装到 `~/.local/bin/`。
- 要求：Node.js 22.13 及以上（`node:sqlite`；22.5–22.12 仍需 `--experimental-sqlite`）。
- 命令不可用时，直接运行 `node <skill-dir>/scripts/session-search.js`，参数相同。

```shell
$ session-search                                # 最近 20 个会话，覆盖所有目录
$ session-search carapace                       # 标题或正文含 carapace
$ session-search git 补全 --dir scripts         # 两个词都要命中，且目录含 scripts
$ session-search --days 7 --roots-only          # 最近 7 天的主会话
$ session-search --project ai-ecom --json       # 项目匹配，输出 JSON
```

- 多个词默认 **AND**；`--any` 改为 **OR**。
- `--scope title|content|all` 控制搜索范围；`--limit 0` 不限条数。
- `--archived` 才包含已归档会话；默认排除。
- 结果按更新时间倒序；每条给出时间、标题、目录、会话 ID，正文命中附片段。
- `--json` 时 stdout 只有 JSON，字段含 `titleMatches`、`contentMatches`、`totalMatches`、`snippet`、`legacy`。
- 退出码：`0` 正常（无匹配也是 0），`2` 参数或读取错误。

### session-prune（按时间清理）

`session-prune` 按最后更新时间 `time_updated` 找超过指定时长的根会话；默认只预览，加 `--apply` 才执行。

```shell
$ session-prune                                      # 预览超过 7 天未更新的会话
$ session-prune --older-than 30d                     # 预览超过 30 天
$ session-prune --older-than 7d --apply              # 执行删除
$ session-prune --older-than 7d --apply --archive    # 改为归档
$ session-prune --apply --export ./session-backup    # 先导出再删除
```

- `--older-than` 接受 `h`/`d`/`w`；`--dir`、`--project`、`--include-archived`、`--limit` 与 `session-search` 语义一致。
- 只处理根会话；家族里只要有一个仍在运行或最近更新，就跳过整个家族。
- 删除会连带子会话；归档只隐藏、不释放空间；`--export` 会导出根会话及其子会话（服务端 `sanitize`）。
- dry-run 只读数据库；`--apply` 需要本机后台服务（`service.json`）。
- 删除后数据库文件不会自动缩小；需要时停服务、备份后 `VACUUM`。

## 在 OpenCode 里直接调用

`/session-search` 由 TUI 插件 `plugins/opencode-session-search` 提供：打开关键词输入框，检索标题与正文，结果列表里选中后直接跳转到会话，**不提交提示词、不调用模型**。

- 安装：`scripts/link-plugins.ps1 -Include opencode-session-search`（Linux 用 `link-plugins.sh --include`），安装后重启 TUI。
- 关键词留空时列出最近会话；多个词用空格分隔，按 AND 匹配；列表里还能继续输入过滤。
- 正文检索复用本 skill 的 `session-search --json`；CLI 不可用时退化为服务端标题检索。
- 内置的 `Ctrl+O` / `/open` 是“会话 + 项目”合并菜单，适合按标题或项目浏览，不搜正文。
- TUI 插件装载失败是静默的：查 `~/.local/share/opencode/log/opencode.log` 里的 `loading plugin` / `failed to load plugin`。
- 插件会把选中的会话 ID 交给 TUI 路由，仍由 TUI 自己加载内容；检索结果不会被发送给模型。

## 服务端 API

服务端列表接口默认就是全局的，返回项带 `location.directory`，可跨目录筛选与翻页。

```shell
$ opencode api get "/api/session?limit=100&search=carapace"
```

可用参数：`limit`、`order`（`asc`/`desc`）、`search`、`directory`、`project`、`subpath`、`parentID`（`null` 只看主会话）、`archived`、`cursor`。翻页把上一页的 `cursor.next` 传给 `cursor`。

已知限制（本机 v2.3.2 实测）：

- `search` 只匹配标题，不搜正文；正文检索用 `session-search` 或直接查库。
- `opencode api get` 的 URL 只应用第一个查询参数，`--param key=value` 不生效。需要组合 `search` + `order` + `cursor` 时，用 `session-search`，或按“服务端直连”发送完整查询串。
- `opencode session list` 只列当前项目的顶层会话，不能当全局列表用。

### 服务端直连

需要完整参数组合时，从 `opencode service status` 取地址，从 `~/.config/opencode/service.json` 取密码（不回显、不入库），按 Basic 认证访问：

```shell
$ curl -u opencode:<password> "http://127.0.0.1:<port>/api/session?limit=20&order=asc&search=carapace"
```

用户名固定为 `opencode`，只改密码。脚本或命令里不要把密码写进仓库或日志。

## WebUI 与内置命令

- `Ctrl+O` 或 `/open` 打开“会话 + 项目”合并搜索菜单，覆盖全部项目、不调用模型；`/sessions`（`<leader>l`）只列当前项目。
- `opencode pair` 打印一次性链接（5 分钟内有效），在浏览器打开 WebUI；它的会话列表来自同一个服务端接口，通常比 TUI 的当前项目列表完整，适合浏览和人工翻找。
- `opencode session export <sessionID>` 导出单个会话为 JSON，`opencode session import` 导入；跨机迁移会话用这两个命令。
- 把会话换到当前目录继续：先 `POST /api/session/<id>/move` 改 `directory`，或在会话所属目录运行 `opencode -s <sessionID>`。

## 直接查库

只读连接后用 SQL 过滤；正文存在 JSON 字符串里，取片段前要解析。

```sql
select s.id, s.title, s.directory, s.time_updated
from session_message m
join session_v2 s on s.id = m.session_id
where m.data like '%关键词%'
  and s.time_archived is null
group by s.id
order by s.time_updated desc;
```

- 用户消息的文本在 `data.text`；助手消息在 `data.content` 里 `type = "text"` 的条目；V1 旧消息在 `part.data` 的 `text` 字段。
- 直接 `LIKE` 原始 JSON 会把工具名、元数据也算进命中，做“是否讨论过”的判断时应解析后再匹配。
- `LIKE` 仅对 ASCII 大小写不敏感；`%`、`_` 需转义（`ESCAPE '\'`）。
- 会话表结构可能随版本变化；先 `pragma table_info(session_v2)` 核对字段，不假设列名长期稳定。

## 边界与安全

- 数据库含全部提示词、文件片段与工具输出，检索结果可能包含密钥；导出或贴出前先脱敏。
- 不要为了“刷新列表”删除库、`-wal`/`-shm` 文件或服务文件；服务生命周期用 `opencode service`。
- 归档、删除、移动会话优先用内置命令或 API，不直接改表。
- 会话 ID 以 `ses_` 开头；子会话与父会话共用同一目录，默认会一起出现在结果里，需要主会话时加 `--roots-only`。

## 验证

```shell
$ session-search --version
$ session-search --limit 3
$ session-search carapace --json | python -X utf8 -c "import json,sys; print(len(json.load(sys.stdin)['results']))"
$ node --check <skill-dir>/scripts/session-search.js
```

- 空结果应输出“未找到匹配的会话”且退出码为 0；错误库路径退出码为 2。
- TUI 插件：`/session-search` 应打开输入框与结果列表，选中后跳转，且不产生新的用户消息或模型调用；插件自测用 `node --test plugins/opencode-session-search/test/plugin.test.ts`。
- 所有查询都是只读打开，不写业务表；不要用本流程做写库操作，需要备份时先复制 `opencode.db`。
