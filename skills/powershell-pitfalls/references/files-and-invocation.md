## 文件路径、写入格式与程序参数

### 引号不取消路径通配符

当目录同时有 `item[1].txt` 和 `item1.txt` 时：

```powershell
Get-Content -Path 'item[1].txt'         # 通配符匹配 item1.txt
Get-Content -LiteralPath 'item[1].txt'  # 读取名称含方括号的文件
```

确切用户文件名使用支持 `-LiteralPath` 的读取、移动和删除命令；需要模式匹配时才使用 `-Path`。如果命令没有 `-LiteralPath`，按其接口处理，不随意套参数。批量文件操作不能把枚举结果拼成另一层 shell 命令再执行。

### 脚本目录、任务目录与 .NET 进程目录

脚本自己的资源用 `Join-Path $PSScriptRoot 'data/example.json'`。用户输入的相对路径按已确定的任务工作目录解释，不自动改成脚本目录。`$PSScriptRoot` 在普通交互命令中未必有脚本目录；不为了方便静默切换整个会话目录。

PowerShell location 与 `[Environment]::CurrentDirectory` 不保证同步。.NET 文件 API 使用完整文件系统路径，避免 PowerShell 中已切目录而 API 仍访问旧目录。存在的任务文件可用 `(Resolve-Path -LiteralPath $inputPath).ProviderPath`；新文件从明确的文件系统基目录用 `Join-Path` 组成路径。

### 明确写入编码、BOM 和换行

| 写法 | Windows PowerShell 5.1 | pwsh 7 |
|---|---|---|
| 字符串 `>` / `Out-File` 默认写入 | UTF-16LE，带 BOM | UTF-8 无 BOM |
| 新文件 `Set-Content` 未指定编码 | 系统 ANSI 编码 | UTF-8 无 BOM |
| `Export-Csv` 未指定编码 | ASCII，中文变 `?`（信息丢失） | UTF-8 无 BOM |
| `Set-Content -Encoding UTF8` | UTF-8 带 BOM | UTF-8 无 BOM |

表格针对文本写入；pwsh 7.4+ 的原生 stdout 直接重定向有字节保留行为，不把字符串示例推广到所有原生/二进制输出。

`[System.Text.Encoding]::UTF8` 不是"无 BOM"的别名：它带 BOM 前缀，`File.WriteAllText(..., [System.Text.Encoding]::UTF8)` 在 5.1 与 7 都写出 `EF BB BF`（2026-10-21 实测）；要无 BOM 一律用 `New-Object System.Text.UTF8Encoding($false)`。

跨 5.1/7 明确写 UTF-8 无 BOM、保持字符串自身换行的方式：

```powershell
# $targetPath 是已确定的完整文件系统路径，父目录已存在。
# $text 是要写入的完整文本；WriteAllText 会覆盖目标文件。
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($targetPath, $text, $utf8NoBom)
```

更新现有文件时按格式契约保留所需编码、BOM 和换行；不为修显示乱码改写原文件。用原始字节/前导标记检查实际编码，不只用屏幕显示判断。需由 5.1 解析的非 ASCII `.ps1` 则按正文使用 UTF-8 BOM，不能套用无 BOM 示例。

读后写必须两端显式指定编码；不用 `>` 结果当原始 stdout（5.1 为 UTF-16LE；7.4+ 原生重定向保留原始字节）。写后用 `Format-Hex` 或前导字节核验，不只看显示。

### 交给 Linux shell 的文本必须用 LF

把 here-string、模板或变量拼成的脚本经 `ssh` 下发时，换行符跟着源文件走：`.psm1`/`.ps1` 保存为 CRLF 时，here-string 原样带出 CRLF。远端 bash 与 zsh 都不把 CR 当空白字符，`then`、`fi`、`}` 这些标记会退化成普通词，典型报错是 `syntax error: unexpected end of file`、`parse error near ...`，位置往往落在脚本末尾，看起来像最后一行写错。

2026-10-28 实测：7 台目标机（4 台 bash、3 台 zsh 登录）同一份下发命令全部失败；把生成的字节原样交 `bash -n` / `zsh -n` 复现出与线上一致的报错，去掉 CR 后两者都通过。

组装完显式归一，不依赖编辑器或 `.gitattributes` 的 eol 设置：

```powershell
# $remoteCmd 是要交给远端 shell 的整段文本
$remoteCmd = ($remoteCmd -replace "`r`n", "`n") -replace "`r", ''
```

验证时把**将要下发的真实字节**写到文件后交 `bash -n` / `zsh -n`，不要先做换行归一化再验证——那正好把缺陷洗掉。

### 参数数组与旧式原生命令传递

直接调用优先把程序和参数分开：

```powershell
$argumentList = @('--input', $inputPath, '--label', 'two words')
& $exe @argumentList
$nativeExit = $LASTEXITCODE
```

不使用 `Invoke-Expression` 重新解释拼接命令。参数数组减少自行拼接，但不是所有版本的 argv 保真保证：5.1 旧式传递可能丢空字符串、移除内嵌引号；7.3+ 还受 `$PSNativeCommandArgumentPassing` 与目标程序/包装器影响。`-EncodedCommand` 只解决 PowerShell 命令文本的跨层传输，不修复对原生程序的 argv 传递。

遇到必须传空值、JSON 或复杂引号的协议，优先使用目标明确支持的配置文件、响应文件或结构化 stdin；也可选择经过验证的调用层。不能假定任意 CLI 支持这些接口。验证目标实际收到的参数，覆盖空值、空格、引号和路径，不把 PowerShell 变量中的字符串正确当目标已收到正确。

把整段脚本作为**单个参数**交给远端 shell（`ssh host '...'`）时，这条风险最直接：5.1 实测会把参数里的双引号全部移除（argv 中剩余 0 个，7.5.4 完整保留），远端于是报引号未闭合。这类场景改用单引号书写脚本，或改走 `bash -s` 的标准输入、base64 传输，不让引号穿过命令行；路径类参数靠参数校验保证不含空白后，也不必再加引号。

### ForEach-Object -Parallel 的 runspace 边界

`-Parallel` 把每一项放进独立 runspace，除显式传入的变量与文本外都拿不到。2026-10-28 在 pwsh 7.5.4 逐项实测：

- **模块内自定义函数不可见**：并行脚本块里调用同一模块的函数直接 `CommandNotFound`，`Start-ThreadJob` 同样不可见。把单项逻辑写成自包含脚本块，顺序与并发复用同一份，避免两套实现漂移。
- **`$using:` 不接受 scriptblock 对象**：报 "A ForEach-Object -Parallel using variable cannot be a script block"。传代码就传 `.ToString()` 文本，在 runspace 内 `[scriptblock]::Create($using:text)` 还原。
- **`$using:` 传的是快照**：`$using:stopwatch` 在 runspace 里恒为传入时的读数，计时、进度计数这类活状态必须在 runspace 内新建。
- **`Write-Host` 会转发到主控制台**，也能被 `6>&1` 捕获成 `InformationRecord`；逐项进度用它，结果对象照旧走成功流，两者不互相污染。

### Start-Process 不是 argv 数组接口

`Start-Process -ArgumentList @('a', 'two words')` 会把数组拼成命令行，`two words` 可能成为两个参数。需要它的异步、窗口或重定向功能时，按目标解析规则构造并验证命令行；不依赖一套通用引号替换覆盖所有 EXE、`.cmd` 与 shell。仅需同步执行时可优先直接调用。

同步检查退出码用 `-Wait -PassThru` 返回的进程对象之 `.ExitCode`，不读旧的 `$LASTEXITCODE`。后台程序不立刻判业务成功；就绪与输出结果仍按任务契约检查。

### 跨层引号与插值

- 外层 pwsh 的双引号会展开 `$变量`、反引号转义、`$( )`。`python -c "..."` 里若含 `$`
 （如 `$PSVersionTable` 或要透传给内层的 `$`），外层必须用**单引号**包裹整段 python 代码。
- 症状实例：`-Command "$PSVersionTable.PSVersion"` 被外层展开成
  `System.Management...PSVersion` 当命令执行而报错——错的不是内层，是外层先吃了 `$`。
- `[CmdletBinding()]param()` 前不能有任何可执行语句。调试探针 `Write-Output` 插错位置
  会直接报 `Unexpected attribute 'CmdletBinding'` / `Unexpected token 'param'`。
  探针只能插在 `param()` 块**之后**。

### 别名与命令冲突

| 想用的 cmd 写法 | pwsh 下实际发生 | 改用 |
|---|---|---|
| `fc /b a b` | `fc` = `Format-Custom`，报位置参数错误 | `fc.exe /b a b` |
| `where powershell` | `where` = `Where-Object`，无输出 | `where.exe` / `Get-Command` |
| `dir /s /b` | 参数错误 | `Get-ChildItem -Recurse` |
| `mkdir -p a/b/c` | 位置参数错误 | `New-Item -ItemType Directory -Force` 或逐级建 |

### Junction 的创建、删除与实体迁移

- 建 Junction：`New-Item -ItemType Junction -Path <link> -Target <dest>`（Win 无需管理员）。
- **删 Junction 只删链接本体**：`Remove-Item <junction>`，绝不加 `-Recurse`
 （加了会删目标目录内容）。Linux 对应：`rm <symlink>` 不加 `-r`，路径尾不加 `/`。
- 实体占住了链接位置时：先 `Move-Item` 到备份目录（必须移出 skills 目录，
  否则 harness 会误扫成重复 skill），再建链接。

### 验证记录

2026-10-11，在 Windows PowerShell 5.1 与 pwsh 7.5.3 的隔离子进程中复现：

- `-Path` 的方括号匹配到了另一个文件，`-LiteralPath` 读取精确文件。
- 从另一个工作目录执行脚本时，`$PSScriptRoot` 与 `(Get-Location).Path` 不同。
- 5.1 字符串 `>` 文件以 `FF FE` 开头，`-Encoding UTF8` 文件以 `EF BB BF` 开头；pwsh 对应文本文件无 BOM。明确 `UTF8Encoding($false)` 的 .NET 写入在两者均无 BOM，文本完整。
- 2026-10-21：`File.WriteAllText(..., [Text.Encoding]::UTF8)` 在 5.1 与 7 都写出 `EF BB BF`（`GetPreamble()` 均 3 字节）；`Export-Csv` 未指定编码时 5.1 把中文写成 `??`（ASCII，信息丢失），7 写 UTF-8 无 BOM。
- 使用 Python argv 记录器：两者直接调用均保留带空格参数；5.1 丢掉空参数和内嵌引号，pwsh 的本次调用保留。两者 `Start-Process -ArgumentList` 数组的带空格项都被拆为两个参数。
- 2026-10-28：`.psm1` 以 CRLF 保存时，here-string 拼出的远端命令带 CR，bash 与 zsh 都拒绝解析（`unexpected end of file` / `parse error near`）；同一份字节交 `bash -n`、`zsh -n` 可复现，去 CR 后通过。同一环境用 argv 记录器对比：5.1.26100 把参数内的双引号全部移除，7.5.4 完整保留。

以上验证本机版本及目标程序，不证明所有包装器、PowerShell 7 小版本或第三方 CLI 有相同参数行为。需要兼容 5.1 的代码也不能直接照抄 `&&`/`||` 等新版本语法。
