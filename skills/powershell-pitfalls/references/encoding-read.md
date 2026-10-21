## UTF-8 文件读取与工具输出乱码

### 症状与根因

读取包含中文、重音字符或 emoji 的 UTF-8 无 BOM 文件时，`Get-Content` 可以退出码为 0，却输出乱码。先区分两层：

| 层次 | 根因 | 修复与验证 |
|---|---|---|
| 文件字节 → PowerShell 字符串 | 5.1 未指定编码时按 ANSI 码页读取无 BOM 文件 | 已知 UTF-8 文件用 `-Encoding UTF8`，用包含非 ASCII 的样本比较实际文本 |
| PowerShell 字符串 → 输出字节 → 工具文本 | 输出方与捕获方编码不一致，或宿主另做转码 | 核对当前进程输出编码和捕获端解码；无法统一时输出 ASCII JSON 后还原 |

`-Encoding UTF8` 只解决第一层；设置 `[Console]::OutputEncoding` 不会修复已误读的字符串。切换 pwsh 7 能改善默认文件解码，仍可能在第二层失败。`chcp 65001` 也不能替代文件读取编码和捕获端核验。

### 形态初判与码点裁决

链路按“文件字节 → 字符串 → stdout 字节 → harness 文本 → 渲染”分层；字体缺字只表现为方框，与前三层的 mojibake 不同。形态只做初判：生僻汉字堆（UTF-8 按 GBK 解）指向读取层；`U+FFFD` 指向输出/捕获层（GBK 按 UTF-8 解）；`??` 指向 `$OutputEncoding` 的 ASCII 丢失。裁决以全 ASCII 码点为准，不凭显示文本：

```powershell
[int[]][char[]](Get-Content -LiteralPath '.workspaces/encoding-probe.txt' -Encoding UTF8 -Raw).Trim() -join ' '
# 中文样本期望 20013 25991；码点正确但显示烂则为输出层，码点错则为读取层
```

### Python 与工具捕获编码

- PowerShell 输出编码与 Python 捕获端默认编码不一致时，`subprocess(..., text=True)` 可能乱码或抛 `UnicodeDecodeError`。先确定生产方编码，再显式指定 `encoding='utf-8'`（生产方确为 UTF-8 时），或先捕获 bytes 并严格按已知编码解码。
- `PYTHONIOENCODING=utf-8` 或 `python -X utf8` 可控制相应的 Python 编码行为，不能修复 PowerShell 已误读的文件或自行改变其输出字节。
- Unicode 文本向不支持该字符的输出端写入时可能抛 `UnicodeEncodeError`；在工具链无法统一编码时按本文最小复现用 ASCII JSON 保真回退。替换错误字符只用于诊断摘要，不作为正确读取的证据。

### 子进程 stdout 经重定向被二次编码（不是源文件坏）

2026-10-21，本机 pwsh 7.5.4 实测：某 Node CLI（帮助文本为中文）执行 `node cli.js --help > out.txt` 后，`out.txt` 用 UTF-8 解码得到 `鍓ュ帀 CSS/JS`（原文"剥掉 CSS/JS"的 UTF-8 字节被按 GBK 解读后又写成 UTF-8），用 GBK/cp936 解码反而抛 `UnicodeDecodeError`；同一命令改走字节通道落盘，文件内容完全正确。

| 通道 | 落盘字节 | 按 UTF-8 读取 |
|---|---|---|
| `node cli.js --help > out.txt` | UTF-8(GBK 误读(UTF-8(原文))) | 双重错位 |
| `execFileSync(..., {encoding:'buffer'})` 直接写 Buffer | 原始 UTF-8 字节 | 正确 |

要点：

- 重定向按 **.NET 的输出编码**解读子进程字节流。**`chcp` 与它不同步**：`chcp 65001` 只改控制台代码页，`.NET` 的 `[Console]::OutputEncoding` 仍是 936 时，输出照样被按 GBK 误读（见下节对照表）。要判断重定向是否保真，看 `[Console]::OutputEncoding.CodePage`，不看 `chcp`。
- 落到文件里的仍是**合法 UTF-8**，只是内容双重错位；因此"文件能按 UTF-8 打开"不能证明内容没被改写。
- 判定顺序：先按字节通道复核（Python `subprocess.run(..., capture_output=True).stdout` 直接写文件；Node `execFileSync(..., {encoding:'buffer'})` 写 Buffer），再判断乱码发生在生产方还是捕获层。
- 误判代价：这类现象很容易被当成"CLI 源码里的模板字符串或文件编码坏了"，进而去改源文件。**先证明乱码发生在哪一层再动手**；生产方是 UTF-8 就不必改它。

复现（探针放被忽略的工作目录，输出用 ASCII JSON 判读，避免显示层干扰）：

```powershell
chcp                                  # 936：控制台代码页
[Console]::OutputEncoding.CodePage    # 真正决定重定向解码的是这一项
$OutputEncoding.CodePage              # 管道传给原生命令的文本编码

node cli.js --help > out-redirect.txt
node -e "const {execFileSync}=require('child_process');const fs=require('fs');fs.writeFileSync('out-bytes.txt',execFileSync(process.execPath,['cli.js','--help'],{encoding:'buffer'}))"

python -c "import json,pathlib;print(json.dumps({p:pathlib.Path(p).read_bytes().decode('utf-8','replace')[:40] for p in ['out-redirect.txt','out-bytes.txt']},ensure_ascii=True))"
```

预期：两个文件都能按 UTF-8 解码，但 `out-redirect.txt` 的内容是双重错位字形，`out-bytes.txt` 是原文。

### 链式 CLI 处理的推荐做法（实测对照）

多段 CLI 输出串成一条管道/重定向时，**每一跳都要过一次 PowerShell 的文本层**，任何一跳没设对编码就整条链失真。下面每种做法在本机 pwsh 7.5.4 上单独跑在一个新进程里，并**先把控制台复位到脏状态**（`chcp 936` + .NET 编码 936）以保证可比：

| 做法 | 落盘内容 |
|---|---|
| 什么都不设 | **MANGLED** |
| 只设 `[Console]::OutputEncoding` / `$OutputEncoding` = UTF8（`chcp` 仍 936） | OK |
| 只 `chcp 65001`（.NET 仍 936） | **MANGLED** |
| 两者都设 | OK |
| 生产者自己按字节写文件（Node `writeFileSync(Buffer)` / Python `write_bytes`） | OK |
| 管道里插"字节闸门"（见下） | OK |

推荐顺序：

1. **首选：文件接力，不传文本**。每个 CLI 自己写文件（`--out` / `--save-html` 这类参数），下一步只读文件。生产方写字节而不是让 shell 替它转码，本仓库的 `resilient_fetch.py --out`、`htmlmini --save-html` / `--output` 就是这个模式。
2. **必须走管道时，在同一次调用里、第一个 CLI 之前设编码**：

   ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   $OutputEncoding = [System.Text.Encoding]::UTF8
   ```

   `chcp 65001` 可以一起设，但它单独不够；真正起作用的是上面两行。
3. **管道里插一个"字节闸门"**，把文本管道换成字节传递：

   ```powershell
   node build.js | python -X utf8 -c "import sys,pathlib;pathlib.Path('out.json').write_bytes(sys.stdin.buffer.read())"
   ```

   闸门按原始字节读 stdin 并按字节写文件，绕开 PowerShell 的文本解码。
4. **兜底：ASCII JSON 中间格式**。`json.dumps(..., ensure_ascii=True)` 传文本，接收端 `json.loads` 还原，链路只剩 ASCII。

配套注意：

- **编码设置是控制台级的，会被后续进程继承**：`chcp` 与 .NET 的输出编码都作用于共享控制台，一个进程改过之后，同控制台里后面的进程会继承它。因此**每次调用都显式设置**（幂等），不要指望"上一次设过了"；同理，上一次调用的输出也不能用来推断这一次的正确性。
- 同一台机器上"同一条命令"可能给出不同结果，原因就是环境状态被前面的命令改过。**复现时先复位环境，再比较**。
- 判读分两层：**文件内容本身就是乱的** → 解码层，按上面 1–4 处理；**文件内容对、只有工具里显示乱码** → 捕获层，改用 ASCII JSON 或让程序直接把结果输出到工具。

探针脚本与逐 case 复现见 `.workspaces/encoding-probe/chained-cli-probe.ps1`（被忽略的临时目录，不入库）。

### 落盘那一跳会坏，直接写 stdout 不一定坏（分层判定）

同一个 UTF-8 生产者，两条去路结果不同（2026-10-21 本机 pwsh 7.5.4 实测，每个 case 单独起进程并先把控制台复位到 936 脏状态）：

| 去路 | 宿主/文件收到什么 |
|---|---|
| 生产者 → stdout（不经 PowerShell 文本层） | 正确 UTF-8 字节 |
| 生产者 → `\| Out-String` → stdout | 正确 UTF-8 字节（本次全部 8 个 case 均如此，含把 .NET 输出编码设成 936 的） |
| 生产者 → `\| Out-File -Encoding UTF8` → 文件 | **双重错位**（基线 case） |
| 生产者 → 自己按字节写文件 | 正确 UTF-8 字节 |

要点：

- **坏在"解码 + 按目标编码重编码"这一跳**：`Out-File`/`>` 会先把子进程字节按 .NET 输出编码解码成字符串，再按目标编码写回。两个编码不一致就错位，而文件仍是合法 UTF-8——所以"能按 UTF-8 打开"不能证明内容没被改写。
- **直接写 stdout 走的是另一条路**（本次测量没出现损坏）。但历史上（2026-10-11/12）别的 harness 上曾出现"内容正确、工具捕获后乱码"，那是**宿主的捕获层**二次转码，不受 `.NET` 属性控制。
- **判定方法**：同一命令取两种——直接 stdout 一次、落盘后按字节读一次。直接 stdout 正常而文件乱 → 坏在落盘那一跳；两者都乱 → 再往上游查（生产方编码、捕获层）。
- **推论**：链式处理里最该避免的是"用重定向当中转"。要么让生产者自己写文件（`--out` 这类参数），要么用字节闸门，要么干脆不落盘。

### "全部统一到 UTF-8"要分清统一的是哪几跳

方向对，但"统一"的对象分层，逐层处理：

| 层 | 谁能统一 | 怎么做 |
|---|---|---|
| 文件内容 | 自己 | 统一 UTF-8 无 BOM（脚本、快照、日志都按此写） |
| 进程链路（子进程输出 → PowerShell 字符串 → 再写出） | 自己 | **每次调用显式声明**：.NET 输出编码设 UTF-8、子进程 `-X utf8`/默认 UTF-8、生产者写字节、消费者按字节读 |
| 宿主/工具的捕获与显示 | **不能** | 兜底：ASCII JSON 中间格式，或让程序把结果写文件后由可靠工具读 |

两点提醒：

- **不要做系统级"统一"**：改系统代码页、区域设置会影响本机所有程序（含仍按 GBK 工作的老程序），属于用户决定的事；agent 只做**进程级**设置（幂等、可丢弃）。
- **进程级设置不跨调用保留**：每次新的 shell 调用都要同次先设；`chcp` 与 .NET 输出编码都作用于共享控制台，会被后续进程继承，所以要显式设而不是靠"上次设过"。

### 稳与不稳的边界：只有"不经 PowerShell 文本层"是稳的

2026-10-21 多轮实测（每 case 单独起进程，先把控制台复位到 chcp 936 + .NET 936，再施加该 case 自己的设置；结论用宿主端字节判定，输出用 ASCII JSON 避免显示层干扰）：

| 路径 | 保真 |
|---|---|
| 子进程**直写 stdout**（不经 PowerShell 文本层） | **稳定正确**（子进程 pwsh 与 agent shell 都正确） |
| 生产者**自己按字节写文件**（Node `writeFileSync(Buffer)` / Python `write_bytes`） | **稳定正确** |
| 管道里插**字节闸门**（按原始字节读 stdin 再写文件） | **稳定正确** |
| **PowerShell 管道/重定向中转**（`\| Select-Object` / `\| Out-String` / `\| Out-File`） | **不保证** |

关于"中转"这一行的实测细节（**同一配置在不同宿主下结果不同**）：

| 设置 | 子进程 pwsh 里（管道 → stdout） | agent shell 里（管道 → stdout） |
|---|---|---|
| 什么都不设 | 非 UTF-8 字节（GBK） | UTF-8 但个别字节被替换成 U+FFFD |
| `.NET` 输出编码设 UTF-8 | 正确 | **整行乱码**（比不设更糟） |
| `chcp 65001` | 非 UTF-8 字节 | — |
| 两者都设 | 正确 | — |

结论：

- **"设了编码就万事大吉"不成立**：中转路径的保真取决于控制台代码页、.NET 输出编码、是否重定向、宿主是不是同一个控制台，这些在 agent shell 与子进程里组合不同。实测出现过"设成 UTF-8 反而比不设更乱"。
- **唯一稳定的做法是绕开 PowerShell 的文本层**：让原生命令直写 stdout，或让程序自己写文件，或在管道里插字节闸门。
- 因此 agent 的默认动作应是：**不给原生命令的输出接 PowerShell 管道/重定向**。要筛选就让程序自己筛（`--format`、`grep` 之类原生筛选，或用字节闸门后再筛），要落盘就用程序的 `--out` 参数。

症状对照（用来判"坏在哪"）：

| 看到的现象 | 含义 |
|---|---|
| 整行乱码（`docs(����): ...`） | UTF-8 字节被按 GBK 解读 |
| 稀疏替换符（`落盘那一�?显示`） | 同上，但部分字节无法成对 → 被换成 U+FFFD，**信息已丢失** |
| 存储的提交信息/文件内容是干净的，只有显示乱 | 问题在显示/中转层，不是内容被改写 |

判定动作：**先确认内容本身是否干净**（提交信息用 `git log --format=%B` 按字节读，文件用二进制读），再怀疑显示层。内容干净 + 显示乱 → 属于中转/捕获层，按上面的"绕开文本层"处理；内容也乱 → 往上游查生产方。

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

2026-10-12，在另一 agent harness 的 shell 工具（pwsh 7.5.4）复现同一现象：UTF-8 无 BOM 中文文件经 `Get-Content -LiteralPath … -Encoding UTF8` 读取后，工具捕获输出仍为乱码；同文件经 Python `read_bytes` 核验为合法 UTF-8，ASCII JSON 路线还原正确。再次确认故障位于“字符串之后的输出/捕获链路”，与文件解码、pwsh 版本无关；跨 harness 遇到时直接采用 ASCII JSON，不重复调试编码参数。

### Select-String 检索的解码层与输出层

2026-10-12，OpenCode shell 工具（pwsh 7.5.4，子进程 Windows PowerShell 5.1，本机 ANSI 936）用同一中文样本写入 UTF-8 无 BOM、带 BOM、GBK 三种文件，对照 `Select-String` 的匹配计数（结果只用 ASCII 标签输出，避免捕获层干扰判读）：

| 场景 | 5.1 | pwsh 7 |
|---|---|---|
| `Select-String` 直接检索无 BOM UTF-8 | 1（默认按 UTF-8 解码） | 1 |
| `Select-String` 直接检索带 BOM UTF-8 | 1 | 1 |
| `Select-String` 直接检索 GBK 文件 | 0（静默漏配） | 0（静默漏配） |
| 按实际编码读成字符串后管道 `Select-String` | 1 | 1 |
| `Get-Content` 默认编码读无 BOM UTF-8 后管道 | 0（按 ANSI 误解码） | 1（默认 UTF-8） |

要点：同一无 BOM UTF-8 文件，5.1 的 `Select-String` 能检索而 `Get-Content` 默认读出的文本是错的，两个 cmdlet 的默认解码方向相反；GBK 文件两版 `Select-String` 都静默漏配且退出码 0。5.1 的 `Select-String` 无 `-Encoding` 参数，需控制文件解码时用管道路线。输出层：两版未设 `[Console]::OutputEncoding` 时，匹配行经工具捕获均为乱码；本 harness 同次调用先设输出编码后显示正确，与上文另一 harness“追加输出设置仍未修复”的记录并存，各自只证明所记环境。5.1 输出被重定向捕获时，结果尾部会附加 `#< CLIXML` 进度序列化噪声，属诊断噪声，不影响匹配计数。

复现注意：探针脚本曾在新调用中引用上一调用定义的样本变量，写入空文件后所有场景计数全 0，险些误判为“GBK 必漏配”；跨调用重跑探针必须在本调用内重建样本，并用字节回读（按写入编码读回后 `-match`）先验证样本本身。

同日用户在交互终端（pwsh 7 与 Windows PowerShell 5.1 各一，加载 profile）按上述命令清单复核，全部匹配计数与预期一致：解码层结论在交互环境与 agent 捕获链路均成立，输出层乱码仅出现在捕获链路。

### Select-String 编码探针（复现用）

在 pwsh 7 中整体运行；样本在本脚本内重建（避免跨调用引用悬空变量写入空文件），先按写入编码字节回读再计数，输出全为 ASCII 标签，可与上文对照表逐项比较：

```powershell
$ErrorActionPreference = 'Stop'
$dir = Join-Path (Join-Path $env:TEMP 'opencode') ('ss-probe-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$text = "ascii marker line`r`n验证 content line`r`n"
$gbEnc = [Text.Encoding]::GetEncoding(936)
$files = @{ nobom = [Text.UTF8Encoding]::new($false); bom = [Text.UTF8Encoding]::new($true); gbk = $gbEnc }
foreach ($k in $files.Keys) { [IO.File]::WriteAllText((Join-Path $dir "$k.txt"), $text, $files[$k]) }
$pat = '验证'
foreach ($k in $files.Keys) {
  $rt = [IO.File]::ReadAllText((Join-Path $dir "$k.txt"), $files[$k]) -match $pat
  "RT_$k=$rt"
  if (-not $rt) { throw "sample $k corrupted" }
}
$nb = Join-Path $dir 'nobom.txt'; $bm = Join-Path $dir 'bom.txt'; $gb = Join-Path $dir 'gbk.txt'
'NOBOM7=' + (Select-String -LiteralPath $nb -Pattern $pat).Count
'BOM7='   + (Select-String -LiteralPath $bm -Pattern $pat).Count
'GBK7='   + (Select-String -LiteralPath $gb -Pattern $pat).Count
'GPIPE7=' + ([IO.File]::ReadAllLines($gb, $gbEnc) | Select-String -Pattern $pat).Count
'UDEF7='  + (Get-Content -LiteralPath $nb | Select-String -Pattern $pat).Count
$inner = @"
`$ProgressPreference = 'SilentlyContinue'
`$c1 = (Select-String -LiteralPath '$nb' -Pattern '验证').Count
`$c2 = (Select-String -LiteralPath '$bm' -Pattern '验证').Count
`$c3 = (Select-String -LiteralPath '$gb' -Pattern '验证').Count
`$c4 = (Get-Content -LiteralPath '$gb' | Select-String -Pattern '验证').Count
`$c5 = (Get-Content -LiteralPath '$nb' | Select-String -Pattern '验证').Count
Write-Output ('NOBOM51=' + `$c1)
Write-Output ('BOM51=' + `$c2)
Write-Output ('GBK51=' + `$c3)
Write-Output ('GPIPE51=' + `$c4)
Write-Output ('UDEF51=' + `$c5)
"@
powershell -NoProfile -NonInteractive -EncodedCommand ([Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner)))
"exit51=$LASTEXITCODE"
Remove-Item -LiteralPath $dir -Recurse -Force
'CLEANUP=done'
```

预期（2026-10-12，本机 ANSI 936，pwsh 7.5.4 + 5.1 子进程）：`RT_*` 三行均为 True（键序不定）；`NOBOM7=1`、`BOM7=1`、`GBK7=0`、`GPIPE7=1`、`UDEF7=1`；`NOBOM51=1`、`BOM51=1`、`GBK51=0`、`GPIPE51=1`、`UDEF51=0`；`exit51=0`。计数不符时，先核对本机 ANSI 码页（`(Get-Culture).TextInfo.ANSICodePage`）与 PowerShell 版本，再决定是否修订记录；不在其他机器把本表当硬断言。输出层（捕获乱码）验证不在本探针内，直接用「文件读取与输出编码」节的模板对照。子进程内 `$ProgressPreference = 'SilentlyContinue'` 实测消除了上文提到的 `#< CLIXML` 噪声。

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
