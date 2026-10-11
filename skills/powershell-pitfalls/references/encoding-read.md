## UTF-8 文件读取与工具输出乱码

### 症状与根因

读取包含中文、重音字符或 emoji 的 UTF-8 无 BOM 文件时，`Get-Content` 可以退出码为 0，却输出乱码。先区分两层：

| 层次 | 根因 | 修复与验证 |
|---|---|---|
| 文件字节 → PowerShell 字符串 | 5.1 未指定编码时按 ANSI 码页读取无 BOM 文件 | 已知 UTF-8 文件用 `-Encoding UTF8`，用包含非 ASCII 的样本比较实际文本 |
| PowerShell 字符串 → 输出字节 → 工具文本 | 输出方与捕获方编码不一致，或宿主另做转码 | 核对当前进程输出编码和捕获端解码；无法统一时输出 ASCII JSON 后还原 |

`-Encoding UTF8` 只解决第一层；设置 `[Console]::OutputEncoding` 不会修复已误读的字符串。切换 pwsh 7 能改善默认文件解码，仍可能在第二层失败。`chcp 65001` 也不能替代文件读取编码和捕获端核验。

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
