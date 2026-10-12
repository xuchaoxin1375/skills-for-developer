---
name: powershell-pitfalls
description: >
  预防与排查 Windows PowerShell 5.1 / pwsh 7 的编码乱码、静默失败、退出码、
  启动/profile、引号与参数、路径和输出流问题。在 agent 使用 PowerShell
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

- ASCII JSON 按 JSON 还原，不用模型逐字复写。用户要求原文展示时，由程序还原并经可靠工具输出；转义文本或被截断的片段不算完整原文。
- 编码设置与读取放在同次调用；`[Console]::OutputEncoding` 控制相关输出，`$OutputEncoding` 控制向原生程序管道输入文本，均不替代文件解码或保证宿主转码。禁止把 `errors="replace"` 的有损文本当完整内容审查或修改文件。
- 直接输出非 ASCII 前，**每次新的 shell 调用**都要同次先设输出编码再读文件；`-Encoding` 只管文件解码，文件读对了、缺前两行照样乱码。模板三行整体复制，不要只摘最后一行：
  ```powershell
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
  Get-Content -LiteralPath '示例.md' -Encoding UTF8 -ErrorAction Stop
  ```
  判读标准：行号对但中文烂为显示层问题，重跑模板而非换解码；模板无效才走 ASCII JSON 保真通道。
- 修显示乱码时不静默修改全局 profile、系统代码页或原文件编码。需由 5.1 解析且含非 ASCII 的 UTF-8 `.ps1` 应带 BOM；普通文档无需批量加 BOM。

## Agent 启动参数与 profile 例外

普通自动化优先直接使用已安装的 pwsh 7，并在实际外壳启动层跳过 profile；工具有相应选项时按其语义配置，无需额外嵌套进程。显式启动时用完整参数名 `-NoLogo -NoProfile`，仅无交互任务加 `-NonInteractive`。

验证独立运行/CI 时显式导入所需初始化；复现 profile 集成或交互问题时保留目标初始化，不统一强加 `-NoProfile` / `-NonInteractive`。外层已加载的 profile 影响不能靠内层参数撤销；`-NoProfile` 也不修复文件编码。

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
| 用户要求工具输出原文；交互式 help 乱码 | [工具输出原文](references/encoding-read.md#用户要求工具输出原文)；[help 与分页器](references/encoding-read.md#交互式-help-乱码检查分页器) |
| 启动/profile 集成、5.1 与 pwsh 兼容差异 | [启动方式与版本差异](references/startup-and-version.md) |
| 跨层引号、别名、精确路径、写入、原生参数或 Junction | [文件与程序调用](references/files-and-invocation.md) |
| 静默失败、异常未捕获、退出码或返回对象混入日志 | [错误与输出契约](references/errors-and-output.md) |

## 验证与维护

按任务核验结果、退出码及变更范围；编码核验必须包含非 ASCII 样本。探针放临时或被忽略的工作目录，避免混入交付。涉及本仓库 skill 链接时用现有链接脚本 `-VerifyOnly` 校验。

历史记录只证明所记环境。新坑记录症状、复现、根因和修复；根因未定位时明确限制，不推广为通用结论。
