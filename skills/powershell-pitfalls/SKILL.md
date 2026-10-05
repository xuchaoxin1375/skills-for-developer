---
name: powershell-pitfalls
description: 排查 Windows PowerShell 5.1 与 pwsh 7 的常见错误与错误用法：脚本无输出/静默失败、退出码异常、编码乱码与 BOM、引号插值与转义、别名冲突、重定向编码、Junction 误删。适用于 powershell报错、pwsh报错、脚本没输出、退出码不对、中文乱码、BOM、引号转义、别名冲突、junction删除；also for powershell troubleshooting, silent script failure, exit code, encoding mojibake, quoting and aliases.
---

# PowerShell 踩坑速查（v5.1 / pwsh 7）

本 skill 案例来自真实排障（`skills-for-developer` 2026-10-02 link-skills 事件），
只收录经复现验证的坑，不收道听途说。

## 适用范围

- Windows 下写/调 `.ps1`、在 agent harness 里拼 shell 命令。
- 不适用：Linux shell（bash/zsh）问题、.NET 编程问题。

## 工作流程：先判外壳，再最小复现

1. 先确认命令实际跑在哪层外壳： harness 工具层可能是 pwsh，`powershell` 另起的是 5.1，
   `cmd /c` 又是一层。跨层传参每过一层就多一次引号/插值。
2. 用最小用例复现（hello-world `.ps1` 先跑通，再加参数）。
3. 对照下表定位，修完重跑并检查退出码。

判外壳一句话：`where X` 在 pwsh 下无输出是正常的——`where` 是 `Where-Object` 的别名，
不是没找到命令。用 `Get-Command X` 或 `where.exe X`。

## 版本差异（出大头的地方）

| 行为 | Windows PowerShell 5.1 | pwsh 7 |
|---|---|---|
| 无 BOM 文件编码 | 按系统 ANSI 码页（中文系统=GBK）解码 | 按 UTF-8 解码 |
| 含中文无 BOM 脚本 | **可静默零输出、退出码 0**（真实案例见下） | 正常执行 |
| 控制台中文输出 | GBK | UTF-8 |
| `>` 重定向默认编码 | UTF-16LE | UTF8NoBOM |
| `Write-Host` | 面向控制台，捕获/重定向行为与版本有关 | 同左 |

真实案例：`scripts/link-skills.ps1`（UTF-8 无 BOM、含中文）用文档化方式
`powershell -File ... -VerifyOnly` 调用时零输出、退出码 0，看起来像"检查通过"，
实际一行没执行；同一文件用 pwsh 跑则正常报出 3 处缺失。修复：文件加 UTF-8 BOM
（内容零改动），之后 5.1/pwsh 双双正常。教训：**含非 ASCII 的 `.ps1` 必须带 BOM**，
否则 5.1 下的"正常退出"不可信。

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

- 未签名脚本加 `-ExecutionPolicy Bypass`，否则可能直接拒绝加载。
- `powershell -File s.ps1 -VerifyOnly -Include name`：`-File` 后参数直传给脚本，
  `[switch]` 开关照常用。
- `exit N` 即进程退出码，外层用 `$LASTEXITCODE` 读。注意 `-File` 模式退出码透出正常，
  "退出码 0 但无输出"首先怀疑版本差异表里的编码问题，而不是"执行成功"。
- 诊断输出优先 `Write-Output`（可被捕获）；`Write-Host` 留给人看。

### 4. 输出捕获与编码（python/工具侧）

- 5.1 输出的中文是 GBK 字节，`subprocess(..., text=True)` 会 `UnicodeDecodeError`。
  改用 bytes 捕获 + `decode(errors="replace")`，或设 `PYTHONIOENCODING=utf-8`。
- 反过来往 GBK 控制台打印解不出的字符（如 `\ufffd`）会 `UnicodeEncodeError`。
  显示前先做 errors 处理，或写文件再看。
- 结论：凡是"报错在 python 侧、不在 powershell 侧"的乱码，先查两端的编解码，
  不是脚本的错。

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

## 反模式自检清单

- [ ] 含中文的 `.ps1` 是否带 BOM？（5.1 下无 BOM = 未定义行为）
- [ ] 跨层命令是否数过有几层外壳、每层引号是否配对？
- [ ] `python -c` 外层是否用了单引号（内含 `$` 时）？
- [ ] 是否把 `where/fc/dir/mkdir -p` 当 cmd 用了？
- [ ] 是否把"退出码 0"当成了"执行成功"（有输出吗？输出符合预期吗？）？
- [ ] 诊断输出是否用了可捕获的 `Write-Output`？
- [ ] `Remove-Item` 删链接时是否带了 `-Recurse`？（有就停手）
- [ ] 仓库里是否残留了 `tmp-*.ps1` / `verify_out.txt` 类探针垃圾？
- [ ] `git status` 是否确认无链接本体被暂存？

## 验证协议

1. 最小用例先行：改动后先跑 hello-world 级用例，再跑全量。
2. 看三种东西：输出内容、退出码（`$LASTEXITCODE`）、`git status`。
3. 链接类操作：跑仓库链接脚本 `-VerifyOnly` 全绿。
4. 新坑入库标准：必须写清症状→复现命令→根因→修复，四项缺一不可；
   只出现一次、说不清根因的不入库。
