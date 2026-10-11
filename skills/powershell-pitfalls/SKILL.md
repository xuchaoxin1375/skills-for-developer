---
name: powershell-pitfalls
description: >
  Windows PowerShell 5.1 与 pwsh 7 的常见错误排查与预防：脚本无输出/静默失败、退出码异常、
  UTF-8 读写与工具输出乱码、profile 加载选择、原生命令退出码与参数、路径通配符、管道输出污染、
  BOM、引号插值与转义、别名冲突、Junction 误删。
  在 Windows agent 中用 Get-Content/type/cat 读取含非 ASCII 的 UTF-8 文档、源码或日志时也使用，
  提前区分文件解码与输出捕获，不等乱码后再加载；agent 选择 PowerShell 启动参数时也适用。
  适用于 powershell报错、pwsh报错、脚本没输出、退出码不对、中文乱码、编码、BOM、引号转义、
  别名冲突、外部程序失败未捕获、参数丢失、路径误匹配、函数返回多值、junction删除；
  also for PowerShell troubleshooting and encoding mojibake.
---

# PowerShell 踩坑速查（v5.1 / pwsh 7）

本 skill 收录真实排障及复现后的规则；历史案例与本机观测不推广为所有宿主的行为。

## 适用范围

- Windows 下写/调 `.ps1`、在 agent harness 里拼 shell 命令。
- 不适用：Linux shell（bash/zsh）问题、.NET 编程问题。

## 工作流程：先判外壳，再最小复现

1. 先确认命令实际跑在哪层外壳： harness 工具层可能是 pwsh，`powershell` 另起的是 5.1，
   `cmd /c` 又是一层。跨层传参每过一层就多一次引号/插值。
   读取已知 UTF-8 文件时先按下方“文件读取与输出编码”执行；`type`/`cat` 在 PowerShell 中通常也是 `Get-Content` 的别名。
2. 用最小用例复现（hello-world `.ps1` 先跑通，再加参数）。
3. 对照下表定位，修完重跑并检查退出码。

判外壳一句话：`where X` 在 pwsh 下无输出是正常的——`where` 是 `Where-Object` 的别名，
不是没找到命令。用 `Get-Command X` 或 `where.exe X`。

## Agent 启动参数与 profile 例外

普通文件读取、仓库检查和不依赖用户初始化的自动化命令，推荐以 `-NoProfile` 启动实际执行的 PowerShell，减少 profile 的额外输出、别名/函数覆盖和初始化影响。使用完整参数名，便于审查；`-NoLogo` 可减少启动信息，`-NonInteractive` 只用于不需要交互提示的任务。

```powershell
pwsh.exe -NoLogo -NoProfile -NonInteractive -Command 'Get-Location'
# 目标明确要求 Windows PowerShell 5.1 时：
powershell.exe -NoLogo -NoProfile -NonInteractive -Command 'Get-Location'
```

**开发或测试 PowerShell 代码、模块时，按被测契约选择启动方式，不能统一强加 `-NoProfile`。**

- 验证脚本/模块自身、独立运行或 CI 行为时，使用 `-NoProfile` 并显式导入所需模块/初始化，可发现隐式依赖。`-NoProfile` 不会禁止 `Import-Module`、模块自动加载，也不会清空继承的环境变量。
- 验证 profile 集成、交互体验，或复现依赖 profile 函数、别名、模块导入、驱动器和环境设置的问题时，保留或显式加载相关初始化。需要真实启动行为时使用目标版本、宿主及其对应 profile；手动 dot-source 只是定向加载，不等于完整启动复现。需用户输入或提示的测试也不强加 `-NonInteractive`。
- 需要同时承诺独立运行与用户会话兼容时，分别检查无 profile 与所需初始化环境，不用单一环境通过替代另一项。测试所需初始化优先使用隔离夹具，不覆盖用户现有 profile。

参数应作用于 agent 实际启动的外壳；外层已经加载 profile 后，再嵌套启动 `-NoProfile` 子进程，不能撤销外层的初始化影响。也不为纯文件读取增加无必要的嵌套 shell。`-NoProfile` 不改变 5.1 的默认文件读取编码，编码问题仍按下一节处理。

## 版本差异（出大头的地方）

| 行为 | Windows PowerShell 5.1 | pwsh 7 |
|---|---|---|
| `Get-Content` 未指定编码、文件无 BOM | 按系统 ANSI 码页解码；例如代码页 936 | 默认按 UTF-8 解码 |
| 含非 ASCII 的 UTF-8 无 BOM 脚本 | 有误读、解析或行为异常风险；历史案例见下 | 按 UTF-8 解析 |
| 控制台/工具捕获的输出编码 | 取决于宿主、`[Console]::OutputEncoding` 与捕获方 | 默认通常为 UTF-8，仍须核对捕获方 |
| `>` 重定向默认编码 | UTF-16LE | UTF8NoBOM |
| `Set-Content -Encoding UTF8` | UTF-8 带 BOM | UTF-8 无 BOM |
| `&&` / `||` 链接命令 | 不支持 | 支持；与 PowerShell 对象管道不同 |
| 原生命令参数传递 | 旧式传递，空参数/内嵌引号可能变化 | 7.3+ 受 `$PSNativeCommandArgumentPassing` 控制，仍与目标程序有关 |
| `Write-Host` | 面向控制台，捕获/重定向行为与版本有关 | 同左 |

真实案例：`scripts/link-skills.ps1`（UTF-8 无 BOM、含中文）用文档化方式
`powershell -File ... -VerifyOnly` 调用时零输出、退出码 0，看起来像"检查通过"，
实际一行没执行；同一文件用 pwsh 跑则正常报出 3 处缺失。修复：文件加 UTF-8 BOM
（内容零改动），之后 5.1/pwsh 双双正常。教训：**需由 5.1 执行且含非 ASCII 的 UTF-8 `.ps1` 应带 BOM**，
否则误读可能影响执行；普通 UTF-8 文档读取按下一节显式指定编码，无需为读取批量加 BOM。

## 文件读取与输出编码（agent 读文件前）

- **文件解码**：已知文件是 UTF-8 时，使用 `Get-Content -LiteralPath '文件路径' -Raw -Encoding UTF8`；按行处理时省略 `-Raw`。优先直接选择已安装的 pwsh 7，但不以外壳名称替代编码核验；其他已知编码按实际格式读取，不一律强按 UTF-8。
- **输出捕获**：内容已正确解码却在工具中乱码时，检查 PowerShell 输出字节与工具/Python 解码是否一致。可在当前进程设置 UTF-8 输出；`[Console]::OutputEncoding` 管相关输出编码，`$OutputEncoding` 管向原生程序管道传入文本，二者都不代替 `Get-Content -Encoding`。不为排障静默改全局 profile、系统代码页或文件编码。
- **保真回退**：显式读 UTF-8、核对输出后仍乱码，改用 Python 显式解码并输出 `json.dumps(..., ensure_ascii=True)`；ASCII 转义可跨越不匹配的输出链路，得到后按 JSON 还原。不得把 `errors="replace"` 的有损文本当完整内容继续审查或据此改文件。

适用于 5.1 与 pwsh 7 的命令：

```powershell
$PSVersionTable.PSVersion
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
Get-Content -LiteralPath 'docs/example.md' -Raw -Encoding UTF8
```

捕获方仍乱码时，用已有 Python 输出 ASCII JSON：

```powershell
python -c "from pathlib import Path; import json; print(json.dumps(Path('docs/example.md').read_text(encoding='utf-8'), ensure_ascii=True))"
```

批量读取可以输出“路径 → 内容”的 JSON 对象，单次读取后还原使用，不反复打印乱码或重读全文。症状、双层根因、最小复现与验证边界见 [编码读取排障](references/encoding-read.md)。

## 分类坑位

### 1. 引号与插值（跨层第一杀手）

- 外层 pwsh 的双引号会展开 `$变量`、反引号转义、`$( )`。`python -c "..."` 里若含 `$`
 （如 `$PSVersionTable` 或要透传给内层的 `$`），外层必须用**单引号**包裹整段 python 代码。
- 症状实例：`-Command "$PSVersionTable.PSVersion"` 被外层展开成
  `System.Management...PSVersion` 当命令执行而报错——错的不是内层，是外层先吃了 `$`。
- `[CmdletBinding()]param()` 前不能有任何可执行语句。调试探针 `Write-Output` 插错位置
  会直接报 `Unexpected attribute 'CmdletBinding'` / `Unexpected token 'param'`。
  探针只能插在 `param()` 块**之后**。

### 2. 别名与命令冲突（cmd 肌肉记忆翻车）

| 想用的 cmd 写法 | pwsh 下实际发生 | 改用 |
|---|---|---|
| `fc /b a b` | `fc` = `Format-Custom`，报位置参数错误 | `fc.exe /b a b` |
| `where powershell` | `where` = `Where-Object`，无输出 | `where.exe` / `Get-Command` |
| `dir /s /b` | 参数错误 | `Get-ChildItem -Recurse` |
| `mkdir -p a/b/c` | 位置参数错误 | `New-Item -ItemType Directory -Force` 或逐级建 |

### 3. 执行脚本与退出码

- 被执行策略拒绝时先用 `Get-ExecutionPolicy -List` 核对生效范围和脚本来源；确需临时放行可信脚本时才使用进程级 `-ExecutionPolicy Bypass`。不默认修改全局策略；该参数不授予管理员权限，也不能覆盖组策略。
- `powershell -File s.ps1 -VerifyOnly -Include name`：`-File` 后参数直传给脚本，
  `[switch]` 开关照常用。
- `exit N` 即进程退出码，外层用 `$LASTEXITCODE` 读。注意 `-File` 模式退出码透出正常，
  "退出码 0 但无输出"首先怀疑版本差异表里的编码问题，而不是"执行成功"。
- 独立诊断探针可用 `Write-Output` 提供可捕获结果；返回业务对象的函数应分离诊断流，不能把日志混入成功输出。`Write-Host` 用于宿主展示，其捕获取决于宿主与输出流设置。
- cmdlet 的非终止错误不一定进入 `catch`，必需操作可用 `-ErrorAction Stop`。原生 EXE 的非零退出码应立即按该工具语义检查 `$LASTEXITCODE`，不能仅依赖 `try/catch` 或 `$ErrorActionPreference`；`$?` 会被后续命令改写。复现与处理见 [错误与输出契约](references/errors-and-output.md)。

### 4. 输出捕获与编码（python/工具侧）

- PowerShell 输出编码与 Python 捕获端默认编码不一致时，`subprocess(..., text=True)` 可能乱码或抛 `UnicodeDecodeError`。先确定生产方编码，再显式指定 `encoding='utf-8'`（生产方确为 UTF-8 时），或先捕获 bytes 并严格按已知编码解码。
- `PYTHONIOENCODING=utf-8` 或 `python -X utf8` 可控制相应的 Python 编码行为，不能修复 PowerShell 已误读的文件或自行改变其输出字节。
- Unicode 文本向不支持该字符的输出端写入时可能抛 `UnicodeEncodeError`；在工具链无法统一编码时按上节用 ASCII JSON 保真回退。替换错误字符只用于诊断摘要，不作为正确读取的证据。

### 5. 文件与链接（Junction，最危险区）

- 建 Junction：`New-Item -ItemType Junction -Path <link> -Target <dest>`（Win 无需管理员）。
- **删 Junction 只删链接本体**：`Remove-Item <junction>`，绝不加 `-Recurse`
 （加了会删目标目录内容）。Linux 对应：`rm <symlink>` 不加 `-r`，路径尾不加 `/`。
- 实体占住了链接位置时：先 `Move-Item` 到备份目录（必须移出 skills 目录，
  否则 harness 会误扫成重复 skill），再建链接。

### 6. 静默失败二分法（屡试不爽）

1. hello-world 对照：`Write-Output AAA` 的 tmp 脚本能跑，说明外壳与调用方式没问题。
2. 从 `param()` 块后逐段插 `Write-Output PROBE-<位置>`，看断在哪两行之间。
3. 断点前后加变量值探针（如 `"DIR=" + $skillsDir`），注意探针字符串本身别引入新的插值坑。
4. 探针文件（`tmp-*.ps1`）与重定向输出文件用完即删，不许留在仓库里。

### 7. 文件路径与写入格式

确切文件名含 `[]` 等通配符字符时使用支持 `-LiteralPath` 的命令；只加引号不能取消 `-Path` 的通配符解释。脚本资源从 `$PSScriptRoot` 定位，任务文件从明确工作目录定位，不混用 .NET 进程目录与 PowerShell location。

写文本时确认编码、BOM 和换行契约，不能把 `>`、`Set-Content -Encoding UTF8` 当成跨版本等价操作。路径与写入示例见 [文件与程序调用](references/files-and-invocation.md)。

### 8. 原生程序参数与进程

直接调用优先 `& $exe @argumentList`，一项一个参数，不用 `Invoke-Expression` 重新解析拼接命令。5.1 的旧式传递仍可能丢空参数或内嵌引号；`Start-Process -ArgumentList` 会拼接数组，不保证参数边界。复杂参数按目标接口选择并实际核验 argv，不能只看进程成功启动；具体方法见 [文件与程序调用](references/files-and-invocation.md)。

### 9. 函数结果与诊断输出

函数中未被消费的表达式和 `Write-Output` 都进入成功输出流，`return` 不会删除此前输出。返回对象的函数用 `Write-Verbose`/`Write-Debug` 等分离诊断，消化无用方法返回值；仅在展示阶段使用 `Format-*`，不把格式化对象当原始数据。例子及捕获边界见 [错误与输出契约](references/errors-and-output.md)。

## 反模式自检清单

- [ ] 需由 5.1 执行且含非 ASCII 的 UTF-8 `.ps1` 是否带 BOM？
- [ ] 已知 UTF-8 文件是否显式 `-Encoding UTF8`，输出端与捕获端是否匹配；仍乱码时是否保真回退？
- [ ] 启动参数是否符合被测契约：普通自动化优先 `-NoProfile`，profile/交互相关开发测试保留所需初始化？
- [ ] 跨层命令是否数过有几层外壳、每层引号是否配对？
- [ ] `python -c` 外层是否用了单引号（内含 `$` 时）？
- [ ] 是否把 `where/fc/dir/mkdir -p` 当 cmd 用了？
- [ ] 是否把"退出码 0"当成了"执行成功"（有输出吗？输出符合预期吗？）？
- [ ] 独立诊断是否可捕获，业务数据输出是否与诊断分离？
- [ ] 原生命令退出码是否立即检查，cmdlet 必需操作是否有明确错误处理？
- [ ] 确切路径、工作目录和写入格式是否明确，空参数/带引号参数是否保持边界？
- [ ] 返回对象的函数是否混入日志或无用返回值，展示格式化是否放在数据处理之后？
- [ ] `Remove-Item` 删链接时是否带了 `-Recurse`？（有就停手）
- [ ] 仓库里是否残留了 `tmp-*.ps1` / `verify_out.txt` 类探针垃圾？
- [ ] `git status` 是否确认无链接本体被暂存？

## 验证协议

1. 最小用例先行：改动后先跑 hello-world 级用例，再跑全量。
2. 看三种东西：输出内容、退出码（`$LASTEXITCODE`）、`git status`。
3. 链接类操作：跑仓库链接脚本 `-VerifyOnly` 全绿。
4. 新坑入库标准：必须写清症状→复现命令→根因→修复，四项缺一不可；
   只出现一次、说不清根因的不入库。
