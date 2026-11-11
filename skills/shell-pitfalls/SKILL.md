---
name: shell-pitfalls
description: >
  Windows 与 POSIX 外壳（PowerShell 5.1/pwsh 7、bash/Git Bash，cmd.exe 仅回退）的执行与排障：
  选壳、编码、退出码、启动/profile、引号与路径、管道与输出。
  Windows 首次调用某个外壳前加载，含单行抓取、读取、解析与命令链；已加载规则直接复用，常规执行不预读诊断材料。
  需要按用户视角复验 Tab 补全、菜单与读屏时，按真实窗口注入按键的流程执行。
  仅用原生 read 查看文本无需加载；脚本编写规范走 scripting-best-practices。
---

## 外壳选择与执行入口

- Windows 默认 PowerShell；需要 POSIX 工具、`.sh` 脚本或仓库里的 bash 脚本时用 Git Bash；cmd.exe 仅作最后回退。按任务与现有脚本选壳，不为单条命令来回切换，也不把两个壳的引号、路径和退出码规则混用。
- 普通文本读取优先用可靠的原生工具，不为加载本 skill 改用 shell。
- 首次调用某个外壳前加载；复用本轮已确认的外壳、版本和启动方式。未知时将版本、必要命令可用性等本地检查合并到一次调用，不逐项探测，不无故嵌套 shell。
- 每次调用先应用所选外壳的编码设置，原生程序直接输出；需筛选或落盘时优先用程序自身选项。成功后检查实际内容与退出码，出现乱码、静默失败或交互异常才读对应参考。

## PowerShell（Windows 默认）

每次新的 PowerShell 调用都在第一次输出前设置，不依赖上次调用或插件是否覆盖当前会话：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

- Python 命令使用 `python -X utf8`，不依赖控制台代码页。
- 已验证编码守卫在当前会话注入时可省手写前缀；不要为省这两行专门跑插件诊断，手写幂等且安全。插件排障见[编码守卫确认](references/encoding-read.md#编码守卫插件确认注入是否生效)。
- 输出与宿主捕获是不同层，前缀不能保证所有工具链都保真；不静默修改系统代码页、全局 profile 或源文件编码。

## 文件读取与输出编码（agent 读文件前）

- 已知 UTF-8 文本用 `Get-Content -LiteralPath <路径> -Encoding UTF8 -ErrorAction Stop`，整份读取才加 `-Raw`；`cat`／`type` 只是别名，同样需要明确编码。其他编码按实际文件读取，需由5.1解析且含非ASCII的UTF-8脚本应带BOM。
- `Select-String` 自行读取文件时也有解码边界；文件编码不明时先按实际编码解码再匹配。零匹配或退出码0不证明解码正确。
- **不要默认将原生命令输出接 PowerShell 文本管道或重定向**：优先生产者自己筛选、自己写文件，随后用可靠工具读取。字节正确而显示乱时，不据此改源文件；不能把有损替换后的文本当完整原文。
- 用户要求工具展示原文时，内部读取、转义文本或最终回复重打都不能替代实际完整展示；大文件优先交文件，不把全文读入上下文再复写。
- 怀疑乱码时按[编码分层与校准](references/encoding-read.md)定位；ASCII JSON、字节通道、7.4+直接重定向例外与链式处理细节均在该参考，不在正常执行前通读。

## 启动与执行底线

- PowerShell 普通自动化优先已安装的 pwsh 7，在实际启动层跳过 profile；显式启动用 `-NoLogo -NoProfile`，无交互任务才加 `-NonInteractive`。复现 profile 集成时保留目标初始化，不统一强加跳过。
- 必需 cmdlet 操作用 `-ErrorAction Stop`；每个原生程序后立即检查 `$LASTEXITCODE`，失败则按契约退出，不让后一条成功命令掩盖失败。诊断与业务输出分流，不混入 `Format-*` 展示对象。
- 直接调用优先 `& $exe @argumentList`，不用 `Invoke-Expression` 拼接执行。路径、空参数、JSON 与多层引号不确定时离线核对 argv，不用外部收费请求试错。
- 多段命令、含中文或嵌套引号的复杂命令写成 `.ps1` 再用 `-File` 调用，不在 `-Command` 里拼引号链；行内只保留单条可读命令。
- 确切文件路径优先 `-LiteralPath`，脚本资源从 `$PSScriptRoot` 定位，写入核对编码、BOM与换行；不把 `>` 与不同版本的 `Set-Content` 当成跨平台等价写法。
- 删除 Junction 只删链接本身，不用 `-Recurse`；递归操作先核对目标范围。执行策略异常先查来源和生效范围，不默认改全局策略。

## bash / Git Bash

- 启动方式决定读哪些 rc：`bash -lc` 是登录 shell，读 `/etc/profile` 与 `~/.bash_profile`（或 `~/.bash_login`、`~/.profile`）；`bash -c` 非登录非交互，只读 `$BASH_ENV`；`bash -ic` 才会读 `~/.bashrc`。需要补全、别名等交互配置时显式用 `-ic`，不假定 `-c` 已加载。
- 多段或含嵌套引号的命令写成 `.sh`，先 `bash -n` 查语法；临时排查加 `bash -x` 看实际执行。中文与引号密集的命令不塞进一层又一层 `-c` 字符串。
- 退出码：`$?` 只看上一条命令；管道默认只取最后一条的状态，需要任一段失败即失败时 `set -o pipefail`，逐段状态看 `PIPESTATUS`。`set -e` 在 `if` 条件、`&&`／`||` 左侧与部分命令替换位置不生效，不能把它当唯一错误处理。
- 路径：Git Bash 用 `/c/...` 表示盘符，交给原生 Windows 程序时 MSYS 会自动转换；不需要转换时用 `MSYS2_ARG_CONV_EXCL`（旧版 `MSYS_NO_PATHCONV=1`）按参数排除，显式转换用 `cygpath -w`／`-u`。PATH 分隔符在 MSYS 内是 `:`，与 PowerShell 的 `;` 不通用。
- `.sh` 保持 LF：CRLF 会让 shebang 变成 `/usr/bin/env: 'bash\r': No such file or directory`，heredoc 与函数定义也会带上 `\r`。
- 编码：Git Bash 一般按 UTF-8 处理文本，但原生 Windows 程序写回控制台的输出仍受代码页影响；中文乱码先分清是文件、locale 还是控制台，再按[编码分层与校准](references/encoding-read.md)定位。Python 同样用 `-X utf8`。
- 需要 TTY 的程序（交互式解释器、分页器、读取终端尺寸的命令）在非终端环境可能直接失败；`winpty` 只解决交互输入，不能当作自动化通用补丁。
- rc、路径转换、TTY 与未实测边界见 [bash 与其他 POSIX 壳](references/bash-and-other-shells.md)。

## 交互式 shell 验证

按用户视角复验 Tab 补全、参数菜单与预测视图时，用独立窗口 + 注入按键 + 读屏，不用 `SendKeys` 抢焦点：另起一个保留 profile 的交互式 shell，由探针附加其控制台写按键并读屏，以提示符出现判断就绪，不与用户输入混用。pwsh/PSReadLine 与 Git Bash 的启动差异、Ctrl+C 例外、截图与清理见[交互式控制台验证](references/interactive-console-verification.md)；只关心候选集合时优先用补全引擎的非交互入口。

## 按需读取

| 条件 | 参考 |
| --- | --- |
| 中文乱码、零匹配、捕获／管道／重定向失真 | [编码读取排障](references/encoding-read.md)；先分层，必要时跑其中的校准脚本 |
| 用户要求原文展示或帮助分页异常 | [原文输出](references/encoding-read.md#用户要求工具输出原文)、[帮助与分页器](references/encoding-read.md#交互式-help-乱码检查分页器) |
| PowerShell 启动、版本或 profile 集成问题 | [启动与版本差异](references/startup-and-version.md) |
| PowerShell 路径、引号、参数、进程等待或 Junction | [文件与程序调用](references/files-and-invocation.md) |
| PowerShell 静默失败、退出码或日志混入结果 | [错误与输出契约](references/errors-and-output.md) |
| bash/Git Bash 的 rc、路径转换、CRLF、TTY 与退出码细节 | [bash 与其他 POSIX 壳](references/bash-and-other-shells.md) |
| 验证 Tab 补全/菜单（pwsh 与 Git Bash、真实窗口、模拟按键、读屏、截图、与用户共存） | [交互式控制台验证](references/interactive-console-verification.md) |

## 验证与维护

核对实际内容、退出码与变更范围；编码验证包含非ASCII样本，历史记录不代表当前宿主通过。探针放临时或被忽略目录，常规成功执行不启动完整体检。涉及 skill 分发时运行仓库既有链接校验。
