# 启动方式与版本差异

仅在选择启动参数、复现 profile 集成或核对跨版本行为时读取对应章节。普通文件读取按 [正文的编码规则](../SKILL.md#文件读取与输出编码agent-读文件前)执行。

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

参数应作用于 agent 实际启动的外壳；外层已经加载 profile 后，再嵌套启动 `-NoProfile` 子进程，不能撤销外层的初始化影响。也不为纯文件读取增加无必要的嵌套 shell。`-NoProfile` 不改变 5.1 的默认文件读取编码，编码问题按 [编码读取排障](encoding-read.md)处理。

Agent 会话禁 `chcp`：它改共享控制台代码页，污染后续子进程。需显式编码时在每条命令同次设置正文三行模板，不依赖 profile；无控制台句柄时 `Console` 赋值可终止错误，加 `try/catch`。

## profile 里适合放什么（编码相关）

`$PROFILE` 只在该进程未使用 `-NoProfile` 时加载。agent harness 常以 `-NoProfile` 启动，profile 修不了 agent 调用（那条链路由 harness 的 shell 配置负责）；它适合固化交互式终端、手动 `-File` 脚本和不带 `-NoProfile` 的工具。

加载顺序：AllUsersAllHosts → AllUsersCurrentHost → CurrentUserAllHosts → CurrentUserCurrentHost。要覆盖所有宿主放 `$PROFILE.CurrentUserAllHosts`，只修当前宿主放 `$PROFILE`。

配置块要放在文件最顶部、任何输出之前：profile 里后续的模块初始化或欢迎语一旦先输出，编码器就按旧值绑定，之后再设属性只改读数、不改实际写出（时机实测见 [编码读取排障](encoding-read.md) 的 2026-10-21 记录）。最小可用写法（源码保持 ASCII，避免 5.1 解析问题）：

```powershell
try {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [Console]::OutputEncoding = $utf8NoBom
    # [Console]::InputEncoding = $utf8NoBom   # optional
    $global:OutputEncoding = $utf8NoBom
} catch { }
```

- `try/catch` 必需：无真实控制台句柄的宿主里赋值可能抛终止错误。
- 赋值成功会改当前窗口的控制台代码页，同窗口子进程继承 UTF-8；这是预期行为，但会影响只认 GBK 的旧式控制台程序。
- 5.1 读取的 profile 若含非 ASCII 注释，文件保持 UTF-8 BOM；纯 ASCII 块可放进无 BOM 文件。

不建议放进 profile：

- `chcp`：改共享控制台代码页，副作用跨子进程；.NET 赋值已够。
- `$PSDefaultParameterValues['*:Encoding'] = 'utf8'`：5.1 的 `utf8` 写文件带 BOM，且会把 5.1 默认 ANSI 读取改成 UTF-8，读坏 GBK 旧文件。
- 编码块之前的中文 banner/emoji：会把编码器提前绑定到旧编码。
- 系统级 UTF-8 beta 开关：影响全机，不是 profile 能解决的问题。

验证（新开窗口）：

```powershell
[Console]::OutputEncoding.CodePage    # 65001
"中文 café 日本語 😀"
help <自定义函数>                      # 分页器路径，单独看
```

`-NoProfile` 启动不会执行这段块；但子进程可能继承同一控制台的 65001，能否正常显示仍取决于该进程自身的控制台与捕获方，不能拿交互窗口的结果推断 agent。

`help` 走分页器，历史上在 profile 里设控制台编码曾让它乱码；出现时去掉 `InputEncoding`，或用 `Get-Help <命令> -Full`。

## 版本差异（出大头的地方）

| 行为 | Windows PowerShell 5.1 | pwsh 7 |
|---|---|---|
| `Get-Content` 未指定编码、文件无 BOM | 按系统 ANSI 码页解码；例如代码页 936 | 默认按 UTF-8 解码 |
| 含非 ASCII 的 UTF-8 无 BOM 脚本 | 有误读、解析或行为异常风险；历史案例见下 | 按 UTF-8 解析 |
| 控制台/工具捕获的输出编码 | 取决于宿主、`[Console]::OutputEncoding` 与捕获方 | 默认通常为 UTF-8，仍须核对捕获方 |
| 字符串 `>` / `Out-File` 默认写入编码 | UTF-16LE | UTF8NoBOM |
| `Get-Content -Encoding Default` 读 GBK 文件 | 按系统 ANSI（如 936）解码，正确 | 按 UTF-8 解码，失败 |
| `-Encoding Byte` / `-AsByteStream` | 支持 `Byte` | 已移除 `Byte`，改用 `-AsByteStream` |
| `Set-Content -Encoding UTF8` | UTF-8 带 BOM | UTF-8 无 BOM |
| `&&` / `\|\|` 链接命令 | 不支持 | 支持；与 PowerShell 对象管道不同 |
| 原生命令参数传递 | 旧式传递，空参数/内嵌引号可能变化 | 7.3+ 受 `$PSNativeCommandArgumentPassing` 控制，仍与目标程序有关 |
| `Write-Host` | 面向控制台，捕获/重定向行为与版本有关 | 同左 |

表格中的重定向编码针对字符串写入；原生 stdout 与二进制重定向的版本边界见 [写入格式](files-and-invocation.md#明确写入编码bom-和换行)。

处理 GBK 旧文件别靠 `-Encoding Default`：5.1 的 `Default` 是系统 ANSI（如 936），7 的 `Default` 是 UTF-8。用 `[System.IO.File]::ReadAllText($path, [System.Text.Encoding]::GetEncoding(936))` 显式指定（2026-10-21 实测：同一 GBK 文件 5.1 `-Encoding Default` 读取正确、7 失败；`GetEncoding(936)` 两版均正确）。

真实案例：`scripts/link-skills.ps1`（UTF-8 无 BOM、含中文）用文档化方式
`powershell -File ... -VerifyOnly` 调用时零输出、退出码 0，看起来像"检查通过"，
实际一行没执行；同一文件用 pwsh 跑则正常报出 3 处缺失。修复：文件加 UTF-8 BOM
（内容零改动），之后 5.1/pwsh 双双正常。教训：**需由 5.1 执行且含非 ASCII 的 UTF-8 `.ps1` 应带 BOM**，
否则误读可能影响执行；普通 UTF-8 文档读取按 [正文的编码规则](../SKILL.md#文件读取与输出编码agent-读文件前)显式指定编码，无需为读取批量加 BOM。
