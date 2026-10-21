# powershell-encoding-guard（OpenCode 插件）

把 `skills/powershell-pitfalls` 中**每次 shell 调用都要做**的机械步骤前置到 OpenCode 的
shell 钩子，减少"每次都要记得写那两行"的遗漏。

## 做什么

| 能力 | 触发条件 | 行为 |
| --- | --- | --- |
| 编码前置 | Windows + PowerShell 外壳（`pwsh` / `powershell`） | 在命令前插入 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 与 `$OutputEncoding = [System.Text.Encoding]::UTF8`，并置 `PYTHONUTF8=1` |
| 风险提示 | 原生命令输出经 PowerShell 文本层（管道 / stdout 重定向） | 在工具结果末尾追加替代方案（程序自带 `--format` / `--out`、字节闸门） |

命令里已经写过编码语句时**不重复注入**（幂等）。

实测（本机 OpenCode 2.1.1，Windows）：同样执行 `python -c "print('中文测试')"`，
无插件时输出为乱码 `���Ĳ���`，装载本插件后输出为 `中文测试`。

## 不做什么

- 不替代理做判断：`何时加 -ErrorAction Stop`、退出码契约、落盘链路设计、什么时候改用原生
  `read` 工具，仍由 `skills/powershell-pitfalls` 维护。
- 不自动补 `-Encoding UTF8`：GBK / ANSI 文件会被改坏，编码必须按实际文件格式判定。
- 不改写命令结构、不重排管道、不阻断 cmdlet 之间的管道（那是 .NET 字符串，不是本插件的目标形态）。
- 不做系统级编码统一（改系统代码页 / 区域设置会影响本机所有程序）。

## 模式

`options.mode`（也可用环境变量 `OPENCODE_PS_GUARD_MODE`）：

| 模式 | 行为 |
| --- | --- |
| `off` | 不注册任何钩子 |
| `warn`（默认） | 编码前置 + 风险提示；不改命令语义 |
| `enforce` | 额外拒绝高危形态（Windows 上按 OpenCode 默认 shell 为 PowerShell 处理） |

其他选项：`assumePowerShell`（未识别外壳时是否按 PowerShell 处理，默认 false）、
`injectOnPosix`（非 Windows 也注入，默认 false）、`preamble`（覆盖前置语句）。

自动发现方式注册（`~/.config/opencode/plugins/<name>`）时读不到 `options`，用环境变量设模式；
需要在意 mode 时改用 `opencode.json` 的 `plugins` 数组条目形式（此时请去掉自动发现
链接，避免同一插件装载两次）。

Windows 上给服务端设环境变量（`~/.config/opencode/service.json` 的 `env` 段）：

```json
{
  "env": {
    "OPENCODE_PS_GUARD_MODE": "enforce"
  }
}
```

## 装载规则（本机实测 + 上游确认）

OpenCode V2 对**本地目录插件**的装载规则（2.1.1 实测）：

- 入口文件固定是**包根目录的 `index.ts` / `index.js`**：`package.json` 的 `exports` / `main`
  **不被采纳**。把入口放在 `src/index.ts` 会被静默跳过（无任何报错）。
- 目录可以被 `~/.config/opencode/plugins/` 自动发现（与 `.opencode/plugins/` 同一套布局），
  直接放 `.ts` / `.js` 文件也会被发现；Junction / symlink 指向的目录同样可被发现。
- `opencode.json` 的 `plugins` 数组条目**只接受目录或 npm 包**，指向 `.ts` 文件会被拒
  （上游 issue anomalyco/opencode#49608、#46551：`configured plugin path must be a directory`）。
- 本地插件 `import { Plugin } from "@opencode/plugin"` 在部分版本/平台解析不到（#49608），
  因此本插件**不导入 SDK**，直接导出 `{ id, setup }` 纯对象（上游给出的可用绕法）。
- **装载失败是静默的**：只在服务端日志里留痕，界面无提示。改完插件务必核对日志里的
  `loading plugin` 行。
- 服务端**按 location 各装载一份实例**（同一进程、同一模块）：`ctx.location.directory` 实测
  就是 location 标识（`C:\repos\blogs` 这类目录路径）。宿主把 shell 事件路由到哪个实例，
  由它自己的加载顺序决定，插件侧无法判断。
- 改插件文件会触发重载（重新装载并重新 setup）；重载后旧实例仍在，新实例也会注册，
  两者行为一致（注入幂等、提示去重）。

因此本包结构固定为：`index.ts`（入口）+ `package.json` + `test/` + `README.md`。

## 已踩过的坑（照抄前先读）

### 1. 注册表别用 `globalThis[插件 id]` 这种字符串键

早期实现把"各 location 的钩子句柄"放在 `globalThis["powershell-encoding-guard"]`。
宿主也会在**同名键**上放自己的值（实测是一个 `Map`），于是：

- 宿主写入的值不是 `Map` 时，`registry.get` 不是函数，setup 直接抛
  `TypeError: registry.get is not a function`，宿主记一条
  `failed to load plugin` 就完事——**界面无任何提示，插件静默失效**（本机出现过 35 次）；
- 宿主写入的值是 `Map` 时，插件与宿主共用一张表，`registry.set` 会把插件的条目塞进宿主的表。

现在改用 `Symbol.for("opencode.plugin-registry.powershell-encoding-guard")` 做键，
与宿主的字符串键互不干扰；注册表值还会做 `instanceof Map` 校验，不对就重建。

### 2. 不要注销别的实例的钩子

宿主把 shell 事件路由到哪个插件实例，由它自己的加载顺序决定，插件猜不到。
早期实现为了"避免重复装载留下两份钩子"，在同 location 的新实例 setup 时把旧实例的钩子
注销掉——实测这会**把宿主正在路由的那份打死**：该 location 的 shell 事件从此全部失联，
插件静默失效，界面无提示。

现在的做法：**不主动注销任何实例的钩子**。重复实例留着无害——注入幂等（命令里已有前缀就
跳过），风险提示按 `[powershell-encoding-guard]` 标记去重。代价是旧版本的代码会一直留到
进程重启；想彻底清掉就重启服务。

### 3. 热重载期间的文件半成品会让 location 失去钩子

宿主重载插件的顺序是**先注销旧实例的钩子，再 setup 新实例**。如果此刻插件文件是半成品
（语法错误、函数没定义），新实例装载失败，旧钩子又已经被注销，这个 location 就变成
"插件完全不在"的状态，直到下一次成功装载。

因此：**改插件文件要一次写完整**，写完先跑测试再让宿主重载；重载后必须做一次真实调用验证
（见下节）。宿主日志里的失败原因分两种，格式也不同：

```text
level=WARN message="failed to load plugin" plugin.id=powershell-encoding-guard cause="Cause([Die(TypeError: ...)])"
level=WARN message="failed to load plugin" target="...powershell-encoding-guard" ref=err_xxx cause="Cause([Die(BuildMessage: Expected \")\" but found \";\")])"
```

### 4. 宿主静默吞掉装载失败 → 插件自带诊断通道

插件每次 setup、每次钩子注销、每次 shell 事件都会往临时目录写一行：

```text
<系统临时目录>/opencode/powershell-encoding-guard.log
```

典型内容：

```text
2026-10-21T03:24:06.670Z setup mode=warn location=C:\repos\blogs host.globalThis[powershell-encoding-guard]=undefined
2026-10-21T03:24:36.557Z shell.create.before location=... shell="...pwsh.EXE" powershell=true hasPreamble=false cmd="Get-ChildItem ..."
2026-10-21T03:24:36.558Z shell.injected location=... cmd="Get-ChildItem ..."
```

排查顺序：先看服务端日志有没有 `loading plugin` / `failed to load plugin`，再看这个文件里
有没有对应的 `setup` 行；两者都没有，说明插件根本没被装载。

## 怎么验证插件真的生效

1. 服务端日志出现 `loading plugin`，且没有对应的 `failed to load plugin`。
2. 服务端日志的 `spawning process` 行里，命令参数**前面多出**两行编码语句
   （这是"注入生效"的直接证据）。
3. shell 里查环境变量：`[Environment]::GetEnvironmentVariable('PYTHONUTF8','Process')` 返回 `1`。
4. 跑一个会输出非 ASCII 的命令（例如 `python -c "print('中文')"`），输出可读。
5. 跑一个"原生命令接 cmdlet 管道"的命令（例如 `git --version | Select-String git`），
   工具结果末尾出现 `[powershell-encoding-guard]` 提示。

第 2 步要注意区分：命令里**自己写了**前缀时，日志里只会出现一份（幂等），
不能据此判断是插件注入还是自己写的。

## 本机实测（2026-10-21，OpenCode 2.1.1 / Node 24.21.0 / Windows）

| 场景 | 做法 | 结果 |
| --- | --- | --- |
| 编码前置 | 命令不写前缀，直接 `python -c "print('中文测试-插件验证')"` | 输出可读；服务端日志的 `spawning process` 里能看到被前置的两行 |
| `PYTHONUTF8` 注入 | `[Environment]::GetEnvironmentVariable('PYTHONUTF8','Process')` | `1`；Python 3.13 的 `sys.stdout.encoding` 为 `utf-8`（默认会是 cp936） |
| 幂等 | 命令自己写前缀 | 日志里前缀只出现一份 |
| 管道提示 | `git --version \| Select-String git` | 工具结果末尾追加替代方案 |
| 重定向提示 | `node -e "..." > out.txt` | 工具结果末尾追加替代方案 |
| 不误报 | `git --version \| more`（native→native） | 无提示 |
| 无插件基线 | 清掉 `PYTHONUTF8`、控制台输出编码设 936 后跑同一条 python 命令 | 输出乱码（GBK 字节被按 UTF-8 解码） |

## 已知边界

- 前置编码只作用于**进程内文本层**；宿主捕获层的二次转码不在插件可控范围内，仍需按 skill 的
  判读标准核对输出（退出码 0 / 纯英文输出不能证明读取正确）。
- `enforce` 在工具执行前拿不到实际外壳（shell 钩子晚于工具钩子回调），因此按平台取保守立场：
  Windows 上按 PowerShell 处理，其他平台只拦"native → cmdlet 管道"这类在 bash 下不可能出现的形态。
- 风险识别是形态级启发式：命令集合有维护成本，新增原生命令需要同步 `index.ts` 的清单；
  PowerShell 内置别名（`cat`/`ls`/`sort`/`where` 等）刻意不在清单内，避免误报。
- 清单外的原生 exe（例如 `certutil`）接 cmdlet 管道时会被**保守**判为风险：提示方向是
  "多提醒"，不会漏报；`findstr` / `fc` 这类常见 Windows 原生工具已列入清单。
- `2> file`（只重定向 stderr）与 `2>&1` 不算高危；`> file`、`1> file`、`&> file` 算。
- PowerShell 7 的条件运算符 `||` 不是数据管道，不提示。
- 提示是**无条件追加**到工具结果：包括代理自己写的 `native | Select-String` 这类命令，
  属预期行为，不是误报。
- 钩子由宿主按 location 路由，同一服务里不同会话的表现可能不同（有的会话有注入、有的没有）；
  这是宿主行为，插件侧无法干预，用上面的验证步骤确认当前会话是否被覆盖。

## 本地验证

```bash
node --test        # 22 条：前置、幂等、外壳分流、风险识别、warn/enforce/off、宿主键冲突与重复装载回归
```

**Node 24 下 `node --test test/` 会失败**：目录参数会被当成入口模块解析，报
`Cannot find module .../test`。只能不带参数跑（自动发现 `test/` 下的 `*.test.ts`），
或直接指定测试文件 `node --test test/plugin.test.ts`。

版本号按日期时间打（`YYYY.MM.DD.HHmm`），唯一真源是 `package.json` 的 `version`：

```bash
npm run stamp                          # 用当前时间重打
node scripts/stamp-version.mjs 2026.10.21.1108   # 或显式指定
```

## 分发

真源在本仓库 `plugins/powershell-encoding-guard/`；本机通过
`scripts/link-plugins.ps1`（Windows，Junction）/ `scripts/link-plugins.sh`（Linux，symlink）
链接到 `~/.config/opencode/plugins/<name>`，OpenCode 自动发现该目录下的插件包。
