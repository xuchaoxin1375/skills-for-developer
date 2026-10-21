---
name: powershell-pitfalls
description: >
  预防与排查 Windows PowerShell 5.1 / pwsh 7 的编码乱码、分层体检与校准、
  静默失败、退出码、启动/profile、引号与参数、路径和输出流问题。在 agent 使用 PowerShell
  读取非 ASCII 文件、选择外壳启动方式、编写或运行任何 PowerShell 脚本片段
  （.ps1 文件或行内片段）时使用。
  仅用原生 read 查看文本无需加载；不处理 Linux shell 问题。
---

# PowerShell 踩坑速查

默认只读本文件。详细步骤、版本表和历史案例在 references；仅在对应问题出现时读取相关章节，不预读全部参考。

## 工作流程

1. 按任务选择工具；普通文本查看优先用可靠的原生读取工具，不为加载此 skill 改用 shell。
2. 必须用 PowerShell 时，确认实际外壳、版本和启动方式；避免无必要的嵌套 shell。
3. 出错后先做最小复现，修复后检查实际结果与退出码；退出码 0、英文输出或手动终端正常都不足以证明工具读取正确。

## 文件读取与输出编码（agent 读文件前）

- **先区分读取与交付**：供代理分析时按需搜索或读取片段。用户要求工具输出原文时，使用实际展示正文的工具，并遵守指定输出方式；仅内部读取或最终回复重打全文不能代替。大文件原样交付优先用文件入口或复制，避免默认把全文读入上下文再复写。
- 已知 UTF-8 文件用 `Get-Content -LiteralPath '文件路径' -Raw -Encoding UTF8`；按行处理省略 `-Raw`，其他编码按实际格式读取。`cat` / `type` 只是 `Get-Content` 的别名，接受同一套参数：经别名读取非 ASCII 文本时同样必须显式传 `-Encoding`（如 `cat -Encoding UTF8 文件`），不传则与直接调用一样按默认编码解码、一样乱码。确切路径优先 `-LiteralPath`，防止 `[ ]` 被当通配符。
- **Select-String 会乱码也会静默漏配**：输出层与 `Get-Content` 同源，直接输出匹配行前先跑编码模板；解码层它自带文件读取，5.1 与 pwsh 7 默认按 UTF-8 解码——无 BOM 的 UTF-8 中文可直接检索，GBK/ANSI 文件则 0 匹配、不报错（5.1 的 `Get-Content` 默认按 ANSI，行为相反）。文件编码不确定时先按实际编码读成字符串再管道：
  ```powershell
  Get-Content -LiteralPath 'f.txt' -Encoding UTF8 | Select-String -Pattern '验证'
  ```
  核对检索结果只看匹配计数，不凭捕获行文本下结论。
- **文件解码与输出捕获是两层**：pwsh 7 或输出属性为 UTF-8 不保证工具捕获正确。直接输出非 ASCII 前，在实际工具和相同启动方式下用小样核验；shell 捕获链路未验证或已有乱码记录时，有 Python 则优先用 ASCII JSON 保真读取：

```powershell
python -c "from pathlib import Path; import json; print(json.dumps(Path('docs/example.md').read_text(encoding='utf-8'), ensure_ascii=True))"
```

- **子进程输出经重定向会被二次编码**：`cmd > file` 会按 **.NET 的输出编码**（`[Console]::OutputEncoding`）解读子进程的字节流再写出，文件仍是合法 UTF-8，内容却已双重错位（形如 `鍓ュ帀`）。**`chcp` 与它不同步**：只 `chcp 65001` 而 .NET 仍是 936 时照样乱码，真正起作用的是下面两行，且要在**同一次调用、第一个 CLI 之前**设置：

  ```powershell
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
  ```

  多段 CLI 串成链时，每一跳都要过这层文本解码，任一跳漏设整条链失真。遇到"行号对、中文乱码"先怀疑这一层：同一命令按字节捕获（Python 读 `bytes`、Node `execFileSync(..., {encoding:'buffer'})`）复核；确认是捕获层就换字节通道或 ASCII JSON，**不要据此去改源文件编码**。链式处理的推荐做法（文件接力 / 字节闸门 / ASCII JSON 中间格式）与实测对照见 [编码读取排障](references/encoding-read.md#链式-cli-处理的推荐做法实测对照)。
- **编码设置是控制台级的，会被后续进程继承**：`chcp` 与 .NET 输出编码都作用于共享控制台，一个进程改过之后同控制台的后续进程会继承。因此每次调用都要显式设置（幂等），也别用上一次调用的结果推断这一次；复现前先把环境复位，否则"同一条命令"会给出不同结果。**别拿 `chcp` 的数字当证据**：本机实测 `[Console]::OutputEncoding=65001`、子进程也继承 65001 时，`chcp` 仍打印 936；实际状态看 `[Console]::OutputEncoding.CodePage`，用 `[Console]::IsOutputRedirected` 区分捕获模式（agent shell 恒为 `True`，此时写 stdout 走 .NET 编码而非 `WriteConsoleW`）。
- **稳的只有"不经 PowerShell 文本层"**：子进程直写 stdout、生产者自己按字节写文件、管道里插字节闸门——这三种实测稳定正确。**给原生命令的输出接 PowerShell 管道/重定向**（`| Select-Object` / `| Out-String` / `| Out-File`）**不保证保真**：同一配置在 agent shell 与子进程里结果不同，实测出现过"把 .NET 输出编码设成 UTF-8 反而比不设更乱"。所以 agent 的默认动作是**不接管道**：要筛选就让程序自己筛（`--format`、原生 `grep`），要落盘就用程序的 `--out` 参数或字节闸门。
- **坏在"落盘那一跳"，不是显示那一跳**：输出先经过 PowerShell 文本层时（`| Out-File`、`| Out-String`、先经函数/变量再 `>`），会把子进程字节按 .NET 输出编码解码成字符串、再按目标编码写回，两处编码不一致就双重错位（文件仍是合法 UTF-8，内容已坏）。**7.4+ 直接把原生命令 stdout 重定向到文件是例外，保留原始字节**：7.5.4 实测该写法 PASS，同一调用包进函数再 `>` 或 `| Out-File` 即 MANGLED；5.1 无此例外，直接调用同样 MANGLED。判定方法：同一命令取两种——直接 stdout 一次、落盘后按字节读一次；stdout 正常而文件乱 = 坏在落盘那一跳，链式处理就别拿重定向当中转。
- **agent 里的显示确实与编码相关，但那一跳不由你控制**：宿主的捕获层曾把正确内容再转码一次，`.NET` 属性修不了它。所以"全部统一到 UTF-8"要分清对象——文件层统一 UTF-8 无 BOM、进程链路每次调用显式声明 UTF-8，宿主捕获层只能用 ASCII JSON 中间格式或"程序写文件 + 可靠工具读"兜底。**不要做系统级统一**（改系统代码页/区域设置会影响本机所有程序），agent 只做进程级设置。

- ASCII JSON 按 JSON 还原，不用模型逐字复写。用户要求原文展示时，由程序还原并经可靠工具输出；转义文本或被截断的片段不算完整原文。
- 编码设置与读取放在同次调用；`[Console]::OutputEncoding` 控制相关输出，`$OutputEncoding` 控制向原生程序管道输入文本，均不替代文件解码或保证宿主转码。禁止把 `errors="replace"` 的有损文本当完整内容审查或修改文件。
- 直接输出非 ASCII 前，**每次新的 shell 调用**都要同次先设输出编码再读文件；**设置要在该进程第一次输出之前**：实测同一进程先输出过一行再设，5.1 与 pwsh 7.5.4 中文仍乱，换成新调用先设再输出即正常。`-Encoding` 只管文件解码，文件读对了、缺前两行照样乱码。模板三行整体复制，不要只摘最后一行：
  ```powershell
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
  Get-Content -LiteralPath '示例.md' -Encoding UTF8 -ErrorAction Stop
  ```
  判读标准：行号对但中文烂为显示层问题，重跑模板而非换解码；模板无效才走 ASCII JSON 保真通道。
- **已装载编码守卫插件时不必手写前缀**：OpenCode 插件 `plugins/powershell-encoding-guard` 会在 Windows 的 PowerShell 调用前自动前置上述语句并置 `PYTHONUTF8=1`（幂等，命令里已写不冲突），并在"原生命令输出经 PowerShell 文本层"时追加替代方案提示。插件只做机械前置与形态提示，判断类规则（何时加 `-ErrorAction Stop`、退出码契约、落盘链路设计）仍在本 skill 维护。**但不要依赖它**：宿主按 location 路由钩子，同一服务里不同会话可能有的被覆盖、有的没有，装载失败还是静默的。是否被覆盖看系统临时目录 `opencode/powershell-encoding-guard.log` 有没有 `setup` 与 `shell.injected` 行；没有就按上面模板手写，模板永远安全（排查见[编码读取排障](references/encoding-read.md#编码守卫插件确认注入是否生效)）。
- 修显示乱码时不静默修改全局 profile、系统代码页或原文件编码。需由 5.1 解析且含非 ASCII 的 UTF-8 `.ps1` 应带 BOM；普通文档无需批量加 BOM。
- **先分层再修**：怀疑乱码、换新 harness/终端，或想确认"设了编码到底有没有用"时，先跑 `scripts/calibrate-encoding.ps1`（每个用例独立进程、ANSI 基线、码点裁决），不要从反复改编码参数试起；判读见[编码体检与校准](references/encoding-read.md#编码体检与校准脚本)。

## 默认 UTF-8（shell 输出与回显）

- 每次 PowerShell 调用先设下面两行（同次调用内、任何输出之前）：`powershell`（5.1）
  默认 GBK，直接输出中文会被采集侧按 UTF-8 解错；pwsh 7 默认即 UTF-8，设了也无害。
  ```powershell
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
  ```
- Python 运行与探针一律加 `-X utf8`（如 `python -X utf8 script.py`、`python -X utf8 -c ...`，只影响本次调用），不再依赖控制台代码页。
- 判读：中文回显可读且退出码正确；纯状态判断仍可用 ASCII 断言。

## Agent 启动参数与 profile 例外

普通自动化优先直接使用已安装的 pwsh 7，并在实际外壳启动层跳过 profile；工具有相应选项时按其语义配置，无需额外嵌套进程。显式启动时用完整参数名 `-NoLogo -NoProfile`，仅无交互任务加 `-NonInteractive`。

验证独立运行/CI 时显式导入所需初始化；复现 profile 集成或交互问题时保留目标初始化，不统一强加 `-NoProfile` / `-NonInteractive`。外层已加载的 profile 影响不能靠内层参数撤销；`-NoProfile` 也不修复文件编码。需要给交互式会话固化 UTF-8 时，放置位置、最小配置与禁忌见 [profile 里适合放什么](references/startup-and-version.md#profile-里适合放什么编码相关)；它不作用于 `-NoProfile` 的 agent 链路。

## 执行底线

- **错误与输出**：必需 cmdlet 操作用 `-ErrorAction Stop`；原生程序退出码紧跟调用检查 `$LASTEXITCODE`，按工具契约判成功。函数诊断与业务输出分流，避免日志、方法返回值或 `Format-*` 对象混入结果。
- **引号与参数**：每层 shell 都可能展开变量和引号；直接调用优先 `& $exe @argumentList`，不用 `Invoke-Expression` 重新解释拼接命令。涉及空参数、JSON 或内嵌引号时核验目标实际收到的 argv。
- **路径与写入**：确切路径用支持 `-LiteralPath` 的接口；脚本资源从 `$PSScriptRoot` 定位，任务文件从明确工作目录定位。写入时确认编码、BOM 和换行，不能把 `>` 或 `Set-Content -Encoding UTF8` 当成跨版本等价操作。
- **链接与文件操作**：删除 Junction 只删链接本体，不用 `-Recurse`；递归删除或移动前核对绝对目标范围，不把枚举路径拼进另一层 shell。
- **权限与配置**：执行策略拒绝时先查生效范围和脚本来源；确需临时放行可信脚本才用进程级 Bypass，不默认改全局策略。

## 按需读取

| 遇到的问题 | 只读取对应参考或章节 |
|---|---|
| 中文乱码、Select-String 漏配、Python 捕获、编码小样与历史证据 | [编码读取排障](references/encoding-read.md) |
| 怀疑乱码、换 harness/终端后要先确认坏在哪一跳 | [编码体检与校准（脚本）](references/encoding-read.md#编码体检与校准脚本) |
| 用户要求工具输出原文；交互式 help 乱码 | [工具输出原文](references/encoding-read.md#用户要求工具输出原文)；[help 与分页器](references/encoding-read.md#交互式-help-乱码检查分页器) |
| 启动/profile 集成、5.1 与 pwsh 兼容差异 | [启动方式与版本差异](references/startup-and-version.md) |
| 跨层引号、别名、精确路径、写入、原生参数或 Junction | [文件与程序调用](references/files-and-invocation.md) |
| 静默失败、异常未捕获、退出码或返回对象混入日志 | [错误与输出契约](references/errors-and-output.md) |

## 验证与维护

按任务核验结果、退出码及变更范围；编码核验必须包含非 ASCII 样本。探针放临时或被忽略的工作目录，避免混入交付。涉及本仓库 skill 链接时用现有链接脚本 `-VerifyOnly` 校验。

历史记录只证明所记环境。新坑记录症状、复现、根因和修复；根因未定位时明确限制，不推广为通用结论。
