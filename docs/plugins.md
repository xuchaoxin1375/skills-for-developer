# 插件制品（OpenCode 插件）

本仓库除 skill 外还维护一类制品：**OpenCode 插件**。规则归属：实体的目录、命名、链接分发、
路径与验证由本文维护；插件内部的行为规则由插件自身的 README 与对应 skill 共同负责。

## 真源与分发

```text
skills-for-developer/
  plugins/
    <plugin-name>/          # 真源：一个目录一个插件，含 index.ts（入口）
  scripts/
    link-plugins.ps1        # Windows：Junction 到 ~/.config/opencode/plugins/<name>
    link-plugins.sh         # Linux/macOS：symlink 到 ~/.config/opencode/plugins/<name>
```

- 真源唯一：harness 侧只放链接，不存实体；改动直接改真源，改完即对本机生效。
- 链接脚本幂等，只管理仓库里存在的插件名；顺带清理指向本仓库、但目标已不存在的
  悬空链接（插件重命名/删除后的残留，`-VerifyOnly` 计为异常）；该目录下其他来源的插件不动；
  路径上是实体目录时先备份到 `~/.skills-migration-backup/<时间戳>/opencode-plugins/` 再替换为链接。
- 插件只对 OpenCode 生效（其他 harness 没有插件机制），因此不分发到 skills 目录。
- `opencode.json`（供应商与密钥）不入库，插件注册不依赖它：靠 `~/.config/opencode/plugins/`
  自动发现，因此真源里不出现机器绝对路径。

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1
powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1 -VerifyOnly
powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1 -Unlink
```

```bash
# Linux/macOS
./scripts/link-plugins.sh
./scripts/link-plugins.sh --verify-only
./scripts/link-plugins.sh --unlink
```

## 装载规则（实测 + 上游确认）

OpenCode V2 对**本地目录插件**的实际装载行为（2.1.1 实测，文档未写全）：

| 事项 | 结论 |
| --- | --- |
| 入口文件 | 固定为**包根目录的 `index.ts` / `index.js`**；`package.json` 的 `exports` / `main` 不被采纳 |
| 入口放 `src/index.ts` | 会被静默跳过（无报错），插件看起来"没生效" |
| 自动发现 | `~/.config/opencode/plugins/`（全局）与 `.opencode/plugins/`（项目）同一套布局；目录与 `.ts` / `.js` 文件都认，Junction / symlink 指向的目录也认 |
| `opencode.json` 的 `plugins` 数组 | 只接受目录或 npm 包；指向 `.ts` 文件被拒（`configured plugin path must be a directory`，上游 issue anomalyco/opencode#49608、#46551） |
| 导入 `@opencode/plugin` | 部分版本 / 平台解析不到（#49608）；本地插件直接导出 `{ id, setup }` 纯对象最稳 |
| 失败可见性 | **静默**：只在服务端日志留痕，界面无提示；改完必须核对日志中的 `loading plugin` 行 |
| 实例粒度 | 服务端**按 location 各装载一份**插件实例（同一进程、同一模块）；宿主把 shell 事件路由到哪份实例由它自己的加载顺序决定，插件猜不到 |
| location 标识 | `ctx.location.directory` 实测就是 location 标识（目录路径）；按 location 记账钩子句柄时用它 |
| 全局键占用 | 宿主会在 `globalThis[插件 id]` 上放自己的值（实测是 `Map`）；插件别拿这个字符串键当自己的注册表，否则要么 setup 抛 `registry.get is not a function`（装载静默失败），要么与宿主共用一张表。用 `Symbol.for` 之类的独立键 |
| 不要注销别的实例 | 插件**不要**在同 location 的新实例 setup 时注销旧实例的钩子：被注销的很可能正是宿主正在路由的那份，结果该 location 的 shell 事件全部失联（插件静默失效）。重复实例留着无害（注入幂等、提示去重），想清旧代码就重启服务 |
| 文件改动 | 改插件文件会触发重载（重新装载并重新 setup）；**重载顺序是先注销旧钩子再 setup 新实例**，此刻若文件是半成品，该 location 会短暂变成"插件不在"的状态 |
| 诊断通道 | 宿主静默吞掉装载失败，插件应自带一行式诊断日志（写系统临时目录），否则"没生效"无从查起；诊断文件路径与格式由插件 README 定义 |
| 覆盖范围 | 钩子由宿主按 location 路由：同一服务里不同会话可能有的被覆盖、有的没有。插件无法判断当前会话是否被覆盖，只能按下面的验证清单实测 |

因此本仓库的插件包结构固定为：`index.ts`（入口）+ `package.json` + 可选 `test/` + `README.md`。
测试用 `node --test`（Node 24 自带类型擦除，无需构建步骤），不引入运行时依赖。
**Node 24 下 `node --test <目录>` 会失败**（目录参数被当入口模块解析，报 `MODULE_NOT_FOUND`），
只能不带参数跑或直接指定测试文件。

插件包的 `version` 按日期时间打（`YYYY.MM.DD.HHmm`），唯一真源是 `package.json`，
配 `scripts/stamp-version.mjs` 入口重打（`npm run stamp`）。

## 验证清单（任何插件通用）

宿主不会在界面上提示插件状态，"生效与否"只能实测。按顺序走完，每一步都可能单独骗过人：

1. **服务端日志有 `loading plugin`**，且同一 id 没有 `failed to load plugin`。
   日志位置：`~/.local/share/opencode/log/opencode.log`（Windows 为
   `%USERPROFILE%\.local\share\opencode\log\opencode.log`）。
2. **插件自带测试通过**（`node --test`），确认入口文件能被加载、核心逻辑没写错。
3. **一次真实调用核对行为**：命令里不要自己写插件会注入的内容，用能自证的标记验证
   （输出中文、诊断文件里的 `injected` 行）。
4. **改完插件再验一次**：热重载后旧实例与新实例并存，行为可能不一致，要确认当前会话仍被覆盖。

第 3 步最常见的误区：命令里**自己写了**插件会注入的前置内容，日志里就分不清是插件注入
还是自己写的。判定注入要看插件自己的标记，不要拿"命令跑通了"当证据。

## 新增与修改

1. 在 `plugins/<name>/` 写真源（入口 `index.ts`；`package.json` 只放元信息）。
2. 更新仓库 `README.md` 的「插件目录」检索表。
3. 本机分发：跑 `scripts/link-plugins.ps1`（或 `.sh`）建链接。
4. 验证：插件自带测试通过 + 服务端日志出现 `loading plugin` + 一次真实调用核对行为。
5. 跨机器：`git push/pull` 传实体，各机器跑一遍自己平台的链接脚本。

## 与 skill 的分工

skill 负责**规则与判断**（什么时候该用哪种编码策略、输出怎么判读），插件负责**机械执行**
（每次调用都要写的那几行、已知高危形态的提示）。两者不互相替代：

- 判断类规则留在 skill（`-ErrorAction Stop` 的时机、退出码契约、落盘链路设计、何时改用原生
  `read` 工具），插件不替代理做判断。
- 插件自动前置的编码语句与 skill 的"安全前缀"一致且幂等，两边同时存在不冲突。
- 插件的行为变更要同步到对应 skill，避免 skill 与实际执行不一致。

## 验证与维护

- 插件逻辑改动：先跑插件自带测试，再按上面的验证清单做一次真实调用对照。
- 装载失败优先查服务端日志（`loading plugin` / `failed to load plugin`），不要只看界面。
- 宿主静默吞掉装载失败：插件应自带诊断通道（写临时目录的一行日志），否则"没生效"无从查起；
  写法见 [编码守卫插件](../plugins/powershell-encoding-guard/README.md) 的「已踩过的坑」一节。
- 改插件文件要一次写完整：重载期间读到半成品会让该 location 的钩子全部失效。
- 上游规范变化时按真实版本核对接口，不把本文当上游文档的复制品。
