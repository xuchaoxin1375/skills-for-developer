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
| `Set-Content -Encoding UTF8` | UTF-8 带 BOM | UTF-8 无 BOM |

表格针对文本写入；pwsh 7.4+ 的原生 stdout 直接重定向有字节保留行为，不把字符串示例推广到所有原生/二进制输出。

跨 5.1/7 明确写 UTF-8 无 BOM、保持字符串自身换行的方式：

```powershell
# $targetPath 是已确定的完整文件系统路径，父目录已存在。
# $text 是要写入的完整文本；WriteAllText 会覆盖目标文件。
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($targetPath, $text, $utf8NoBom)
```

更新现有文件时按格式契约保留所需编码、BOM 和换行；不为修显示乱码改写原文件。用原始字节/前导标记检查实际编码，不只用屏幕显示判断。需由 5.1 解析的非 ASCII `.ps1` 则按正文使用 UTF-8 BOM，不能套用无 BOM 示例。

读后写必须两端显式指定编码；不用 `>` 结果当原始 stdout（5.1 为 UTF-16LE；7.4+ 原生重定向保留原始字节）。写后用 `Format-Hex` 或前导字节核验，不只看显示。

### 参数数组与旧式原生命令传递

直接调用优先把程序和参数分开：

```powershell
$argumentList = @('--input', $inputPath, '--label', 'two words')
& $exe @argumentList
$nativeExit = $LASTEXITCODE
```

不使用 `Invoke-Expression` 重新解释拼接命令。参数数组减少自行拼接，但不是所有版本的 argv 保真保证：5.1 旧式传递可能丢空字符串、移除内嵌引号；7.3+ 还受 `$PSNativeCommandArgumentPassing` 与目标程序/包装器影响。`-EncodedCommand` 只解决 PowerShell 命令文本的跨层传输，不修复对原生程序的 argv 传递。

遇到必须传空值、JSON 或复杂引号的协议，优先使用目标明确支持的配置文件、响应文件或结构化 stdin；也可选择经过验证的调用层。不能假定任意 CLI 支持这些接口。验证目标实际收到的参数，覆盖空值、空格、引号和路径，不把 PowerShell 变量中的字符串正确当目标已收到正确。

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
- 使用 Python argv 记录器：两者直接调用均保留带空格参数；5.1 丢掉空参数和内嵌引号，pwsh 的本次调用保留。两者 `Start-Process -ArgumentList` 数组的带空格项都被拆为两个参数。

以上验证本机版本及目标程序，不证明所有包装器、PowerShell 7 小版本或第三方 CLI 有相同参数行为。需要兼容 5.1 的代码也不能直接照抄 `&&`/`||` 等新版本语法。
