## UTF-8 文件读取与工具输出乱码

### 症状与根因

读取包含中文、重音字符或 emoji 的 UTF-8 无 BOM 文件时，`Get-Content` 可以退出码为 0，却输出乱码。先区分两层：

| 层次 | 根因 | 修复与验证 |
|---|---|---|
| 文件字节 → PowerShell 字符串 | 5.1 未指定编码时按 ANSI 码页读取无 BOM 文件 | 已知 UTF-8 文件用 `-Encoding UTF8`，用包含非 ASCII 的样本比较实际文本 |
| PowerShell 字符串 → 输出字节 → 工具文本 | 输出方与捕获方编码不一致，或宿主另做转码 | 核对当前进程输出编码和捕获端解码；无法统一时输出 ASCII JSON 后还原 |

`-Encoding UTF8` 只解决第一层；设置 `[Console]::OutputEncoding` 不会修复已误读的字符串。切换 pwsh 7 能改善默认文件解码，仍可能在第二层失败。`chcp 65001` 也不能替代文件读取编码和捕获端核验。

### Python 与工具捕获编码

- PowerShell 输出编码与 Python 捕获端默认编码不一致时，`subprocess(..., text=True)` 可能乱码或抛 `UnicodeDecodeError`。先确定生产方编码，再显式指定 `encoding='utf-8'`（生产方确为 UTF-8 时），或先捕获 bytes 并严格按已知编码解码。
- `PYTHONIOENCODING=utf-8` 或 `python -X utf8` 可控制相应的 Python 编码行为，不能修复 PowerShell 已误读的文件或自行改变其输出字节。
- Unicode 文本向不支持该字符的输出端写入时可能抛 `UnicodeEncodeError`；在工具链无法统一编码时按本文最小复现用 ASCII JSON 保真回退。替换错误字符只用于诊断摘要，不作为正确读取的证据。

### 最小复现与修复

以下在 PowerShell 中执行，Python 创建 UTF-8 无 BOM 样本；样本正文用转义生成，避免命令本身的中文传参干扰结果。过程产物放被忽略的 `.workspaces/`。

```powershell
python -c "from pathlib import Path; p=Path('.workspaces/encoding-probe.txt'); p.parent.mkdir(parents=True, exist_ok=True); p.write_text('\u4e2d\u6587 caf\u00e9 \u65e5\u672c\u8a9e \U0001f600', encoding='utf-8')"
$PSVersionTable.PSVersion
[System.Text.Encoding]::Default.CodePage
[Console]::OutputEncoding.CodePage
$OutputEncoding.CodePage

# 先统一当前进程的相关输出编码，独立观察文件读取差异。
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
Get-Content -LiteralPath '.workspaces/encoding-probe.txt' -Raw
Get-Content -LiteralPath '.workspaces/encoding-probe.txt' -Raw -Encoding UTF8

# 输出链路仍乱码时采用保真回退。
python -c "from pathlib import Path; import json; print(json.dumps(Path('.workspaces/encoding-probe.txt').read_text(encoding='utf-8'), ensure_ascii=True))"
```

预期正文为 `中文 café 日本語 😀`。ASCII JSON 的 `\uXXXX` 转义、emoji 的代理对和 `\n` 是合法 JSON 表达，应按 JSON 还原；它们不表示原文件损坏。普通 UTF-8 样本使用 `encoding='utf-8'`；实际文件含 UTF-8 BOM 且需要去掉标记时，Python 使用 `utf-8-sig`。

### 实测记录与限制

2026-10-11，本机复现使用 Python 捕获 `-NoProfile -NonInteractive` 子进程的原始 stdout，再严格按指定输出编码解码并比较样本文本：

| 场景 | Windows PowerShell 5.1（ANSI 936） | pwsh 7.5.3 |
|---|---|---|
| 已设置 UTF-8 输出，默认 `Get-Content` | 非 ASCII 内容错误，退出码 0 | 内容正确 |
| 已设置 UTF-8 输出，显式 `-Encoding UTF8` | 内容正确 | 内容正确 |
| Python 显式读 UTF-8，ASCII JSON 输出并还原 | 内容正确 | 内容正确 |

同次任务中，直接经 agent 工具输出的 pwsh 7 `Get-Content -Encoding UTF8` 仍显示乱码；追加进程 UTF-8 输出设置也未修复，Python ASCII JSON 路线能保真读取。这证明当前工具链还有输出/捕获问题，尚未定位其具体转码环节，不能归因于 5.1，也不能承诺只换 pwsh 就解决。

以上验证文件读取和受控子进程捕获，以及当前 agent 的回退路线；不证明所有终端、profile 或 agent 宿主具有相同默认编码。遇到新环境按同一非 ASCII 样本核验，不通过退出码 0 或一段英文输出推定编码正确。

### 实际工具的启动方式对照

2026-10-11，针对“手动执行正常，agent 仍可能乱码”的反馈，使用上述同一 UTF-8 样本，经 `exec_command` 直接捕获 pwsh 7.5.3 输出，比较工具的 `login` 参数：

| 实际调用 | 捕获结果 |
|---|---|
| `login=false`，`Get-Content -Raw -Encoding UTF8` | `中文 café 日本語 😀`，正确 |
| `login=true`，同一读取命令 | 中文、重音字符和 emoji 损坏，退出码 0 |
| `login=true`，同次调用先设置两个 UTF-8 输出属性再读取 | 仍损坏 |
| `login=true`，Python 显式读 UTF-8 并输出 ASCII JSON | 转义内容正确 |

乱码调用中，`[Console]::OutputEncoding.WebName` 报告 `utf-8`；将读取结果逐字符转为整数输出，得到正确的 UTF-16 码元序列。这将问题定位在字符串之后的输出/捕获链路，而非文件解码。带 profile 初始化的调用出现额外启动输出，但本对照未定位具体转码环节，不能据此断言某条 profile 语句是根因，也不能承诺所有环境都由 `login=false` 修复。

复现时，用同一工具分别提交以下命令，并保持文件路径、外壳版本及其他参数一致；工具不支持 `login` 时，按其接口比较实际外壳是否加载 profile，不额外嵌套 shell 替代对照。

```powershell
[Console]::OutputEncoding.WebName
$content = Get-Content -LiteralPath '.workspaces/encoding-probe.txt' -Raw -Encoding UTF8
$content
($content.ToCharArray() | ForEach-Object { [int]$_ }) -join ','
```

本样本预期码元为 `20013,25991,32,99,97,102,233,32,26085,26412,35486,32,55357,56832`。字符串码元正确而可见正文损坏时，直接采用 ASCII JSON；不要继续反复设置编码或打印整篇乱码。重新选择启动方式后，需要在实际工具里重新核验；进程级编码设置也不能假定跨工具调用保留。

### 用户要求工具输出原文

“读取文件供代理分析”和“通过工具向用户输出原文”是不同的交付要求。2026-10-11 的反馈中，代理面对后者只调用了内部 `read` 工具，随后在最终回复中重打文件全文。编码注意事项没有拦住这种输出方式偏差；模型复写既增加重复输出，也不能代替程序保真输出。

用户明确要求直接调用工具输出原文时，使用能展示实际 stdout 或原文结果的工具，在已核验的读取路线中直接输出正文。例如，PowerShell 显式按文件编码读取，再将结果直接送入工具输出；不要仅凭“Read 文件名”这类状态提示宣称正文已展示，也不要让内部读取工具的默认偏好覆盖用户指定的输出方式。

ASCII JSON 是跨编码链路的传输格式，不是用户所要的原文。采用该回退时，用程序解析 JSON 并通过工具输出还原文本，不让模型逐字复写。输出限额不足时通过工具分块输出，说明截断或缺口，不把片段称为全文。工具输出完成后只简短确认；用户另行要求在最终回复粘贴全文时按其要求执行。

检查时分别走查“内部读取正常但用户只见读取状态”和“ASCII JSON 正确但尚未还原输出”两种情况：两者都未完成工具输出原文，不能用最终回复重打全文补齐。本说明是针对反馈的行为约束；结构校验或桌面走查不证明其他代理已遵循它。

### 交互式 `help` 乱码：检查分页器

2026-10-11，在用户级 profile 开头设置 `[Console]::OutputEncoding` 和 `$OutputEncoding` 为 UTF-8 后，agent 工具读取中文恢复正常，但用户的交互式 pwsh 中，`help` 显示自定义函数的中文帮助出现乱码。撤回该设置后，用户确认直接使用 `Get-Help <命令名> -Full` 可以正确显示。这是工具捕获与交互式帮助需要分别验证的实例，不能把前者成功当作全局编码修复完成。

本机 pwsh 7.5.3 的 `help` 是包装函数：先调用 `Get-Help`，再把适用的帮助结果交给分页器；Windows 默认使用原生程序 `more.com`，可由环境变量 `PAGER` 指定其他分页器。检查函数定义及 `Get-Help` 对象中的中文，确认原始帮助内容正确；交互式乱码应继续排查分页器的输入、输出编码与控制台码页，而不是先改函数源码或帮助文件编码。具体转码环节未在交互式终端中独立复现，不将本案例推广为所有 `more.com` 调用都会乱码。

针对已有中文注释帮助的自定义函数，在同一个交互式窗口对照以下命令；`Get-ExampleCommand` 是占位命令名，应替换为实际函数：

```powershell
# 经过 help 的分页器，观察是否乱码。
help Get-ExampleCommand

# 直接显示完整帮助，绕过 help 的自动分页。
Get-Help Get-ExampleCommand -Full

# 需要分页时，可使用 PowerShell 自身的分页；在目标终端核验显示与翻页。
Get-Help Get-ExampleCommand -Full | Out-Host -Paging
```

**关键是直接调用 `Get-Help`，不是 `-Full` 修复编码。**`-Full` 只选择完整帮助视图；本机 `help` 在默认视图下也会选择完整帮助，再调用分页器。若 `Get-Help` 正常、`help` 乱码，优先绕过或检查分页器；若两者都乱码，继续区分帮助内容本身与显示链路。自定义或其他版本的 `help` 行为需通过 `Get-Command help` 的定义核对，不能假定它只是 `Get-Help` 的别名。

agent 自动化读取优先在实际工具中核验跳过 profile 的路线，并将编码设置限制在该进程；本机 `exec_command` 的 `login=false` 已验证可用，不代表其他工具的同名参数具有相同语义。确需修改用户 profile 时，保留原配置，并分别核验工具读取、交互式帮助和相关原生程序管道；出现回归时只撤回本次改动并重开进程。`Out-Host -Paging` 在本案例中是替代建议，用户确认的效果仅覆盖直接调用 `Get-Help -Full`。
