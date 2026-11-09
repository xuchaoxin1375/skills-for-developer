---
name: powershell-pitfalls
description: >
  Windows PowerShell 5.1 / pwsh 7 的执行与排障：编码、退出码、启动/profile、引号、路径和输出流。
  Windows 首次 PowerShell 调用前加载，含单行抓取、读取、解析与命令链；已加载规则直接复用，常规执行不预读诊断材料。
  需要按用户视角复验 Tab 补全/PSReadLine 交互时，按真实窗口注入按键与读屏的流程执行。
  仅用原生 read 查看文本无需加载；不处理 Linux shell 问题。
---

## PowerShell 执行入口

1. 普通文本读取优先用可靠的原生工具，不为加载本 skill 改用 shell。
2. 首次 PowerShell 调用前加载；复用本轮已确认的外壳、版本和启动方式。未知时将版本、必要命令可用性等本地检查合并到一次调用，不逐项探测，不无故嵌套 shell。
3. 每次调用先应用下方编码前缀，原生程序直接输出；需筛选或落盘时优先用程序自身选项。成功后检查实际内容与退出码，出现乱码或执行异常才读对应参考。

## 默认 UTF-8（shell 输出与回显）

每次新的 PowerShell 调用都在第一次输出前设置，不依赖上次调用或插件是否覆盖当前会话：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

- Python 命令使用 `python -X utf8`，不依赖控制台代码页。
- 已验证编码守卫在当前会话注入时可省手写前缀；不要为省这两行专门跑插件诊断，手写幂等且安全。插件排障见[编码守卫确认](references/encoding-read.md#编码守卫插件确认注入是否生效)。
- PowerShell 输出与宿主捕获是不同层，前缀不能保证所有工具链都保真；不静默修改系统代码页、全局 profile 或源文件编码。

## 文件读取与输出编码（agent 读文件前）

- 已知 UTF-8 文本用 `Get-Content -LiteralPath <路径> -Encoding UTF8 -ErrorAction Stop`，整份读取才加 `-Raw`；`cat`／`type` 只是别名，同样需要明确编码。其他编码按实际文件读取，需由5.1解析且含非ASCII的UTF-8脚本应带BOM。
- `Select-String` 自行读取文件时也有解码边界；文件编码不明时先按实际编码解码再匹配。零匹配或退出码0不证明解码正确。
- **不要默认将原生命令输出接 PowerShell 文本管道或重定向**：优先生产者自己筛选、自己写文件，随后用可靠工具读取。字节正确而显示乱时，不据此改源文件；不能把有损替换后的文本当完整原文。
- 用户要求工具展示原文时，内部读取、转义文本或最终回复重打都不能替代实际完整展示；大文件优先交文件，不把全文读入上下文再复写。
- 怀疑乱码时按[编码分层与校准](references/encoding-read.md)定位；ASCII JSON、字节通道、7.4+直接重定向例外与链式处理细节均在该参考，不在正常执行前通读。

## 启动与执行底线

- 普通自动化优先已安装的 pwsh 7，在实际启动层跳过 profile；显式启动用 `-NoLogo -NoProfile`，无交互任务才加 `-NonInteractive`。复现 profile 集成时保留目标初始化，不统一强加跳过。
- 必需 cmdlet 操作用 `-ErrorAction Stop`；每个原生程序后立即检查 `$LASTEXITCODE`，失败则按契约退出，不让后一条成功命令掩盖失败。诊断与业务输出分流，不混入 `Format-*` 展示对象。
- 直接调用优先 `& $exe @argumentList`，不用 `Invoke-Expression` 拼接执行。路径、空参数、JSON 与多层引号不确定时离线核对 argv，不用外部收费请求试错。
- 确切文件路径优先 `-LiteralPath`，脚本资源从 `$PSScriptRoot` 定位，写入核对编码、BOM与换行；不把 `>` 与不同版本的 `Set-Content` 当成跨平台等价写法。
- 删除 Junction 只删链接本身，不用 `-Recurse`；递归操作先核对目标范围。执行策略异常先查来源和生效范围，不默认改全局策略。
- 验证 Tab 补全等交互行为时不改用 `SendKeys` 抢焦点；按[交互式控制台验证](references/interactive-console-verification.md)启动独立窗口、向输入缓冲区注入按键并读屏。窗口由探针独占，以读屏出现提示符判断就绪，不用 `MainWindowHandle`，不与用户输入混用。

## 按需读取

| 条件 | 参考 |
| --- | --- |
| 中文乱码、零匹配、捕获／管道／重定向失真 | [编码读取排障](references/encoding-read.md)；先分层，必要时跑其中的校准脚本 |
| 用户要求原文展示或帮助分页异常 | [原文输出](references/encoding-read.md#用户要求工具输出原文)、[帮助与分页器](references/encoding-read.md#交互式-help-乱码检查分页器) |
| 启动、版本或 profile 集成问题 | [启动与版本差异](references/startup-and-version.md) |
| 路径、引号、参数、进程等待或 Junction | [文件与程序调用](references/files-and-invocation.md) |
| 静默失败、退出码或日志混入结果 | [错误与输出契约](references/errors-and-output.md) |
| 验证 Tab 补全/PSReadLine 交互（真实窗口、模拟按键、读屏、截图、与用户共存） | [交互式控制台验证](references/interactive-console-verification.md) |

## 验证与维护

核对实际内容、退出码与变更范围；编码验证包含非ASCII样本，历史记录不代表当前宿主通过。探针放临时或被忽略目录，常规成功执行不启动完整体检。涉及 skill 分发时运行仓库既有链接校验。
