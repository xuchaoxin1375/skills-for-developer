# 交互式控制台验证（模拟按键与读屏）

## 适用条件

- Windows 交互式桌面会话，需要复验用户按 Tab 后实际看到的界面：候选菜单、排序、描述列、选中后的输入行变化、预测视图。
- 只关心候选集合时，优先用非交互入口：`[System.Management.Automation.CommandCompletion]::CompleteInput($line, $cursor, $null)`；本流程用于补全引擎之外的界面层差异。
- 需要目标程序有独立控制台窗口；纯服务会话或无桌面环境不适用。
- 代理代为验证时，目标窗口由探针独占。用户在同一窗口操作会污染结果，见[与他人操作共存](#与他人操作共存)。

## 基本做法

1. 启动独立窗口：`Start-Process pwsh -ArgumentList '-NoLogo','-NoExit' -PassThru`。保留 profile，才是在验证用户日常环境。**不要用 `MainWindowHandle` 判断窗口就绪**：实测它可能一直是 0，而控制台已经能读屏。
2. 等待提示符：轮询读屏直到出现提示符或超时。固定等待只作首次试探，profile 初始化耗时因机器而异；超时按失败处理，不靠延长等待掩盖问题。
3. 附加控制台：探针进程先 `FreeConsole()`，再 `AttachConsole(<pid>)`，用 `CreateFileW("CONIN$"/"CONOUT$")` 取得输入输出句柄。`CONOUT$` 按读写打开（`GENERIC_READ|GENERIC_WRITE`，`0xC0000000`）；实测只给 `GENERIC_READ` 时 `GetConsoleScreenBufferInfo` 返回 `ERROR_ACCESS_DENIED`(5)，看起来像附加失败。
4. 注入按键：`WriteConsoleInputW` 写入 `KEY_EVENT_RECORD`，`EventType = 1`，每字符发送按下与抬起两条；虚拟键码用 `VkKeyScanW(ch)` 取低字节，扫描码用 `MapVirtualKeyW(vk, 0)`。文本的修饰键从 `VkKeyScanW` 高字节解析。`Ctrl+C` 是例外：默认控制台模式下真实 Ctrl+C 会被当作控制事件，而写入的是按键记录，二者在 Tab 菜单中的行为不同；验证 Ctrl+C 要改用 `keybd_event`/`SendInput` 并校验前台窗口。
5. 读取屏幕：`GetConsoleScreenBufferInfo` 取 `dwSize` 与 `srWindow`，逐行 `ReadConsoleOutputCharacterW`，再 `TrimEnd()`；按可见窗口读取，不读整块缓冲区。每次读屏重新取尺寸，不缓存——终端尺寸和滚动位置会被用户或终端本身改变。附加后不要改用 `[Console]::WindowWidth` 一类 .NET 成员：它们持有启动时的句柄缓存，会报"句柄无效"。
6. 顺序验证：先跑已知命令的对照（如 `Get-Chi` + Tab），确认注入与读屏链路，再测目标命令；一次只注入一步并等待重绘。
7. 清行与退出：菜单打开时先 `Esc` 关闭菜单，再 `Ctrl+C` 清行（真实按键下 Ctrl+C 在菜单中可能无效）；最后输入 `exit` 回车退出，进程仍在时用 `Stop-Process` 兜底。只结束本次启动的进程与窗口：结束目标 shell 后终端窗口可能仍在（实测 Windows Terminal 窗口保留），需要按自己的 pid 关闭并复查，不按进程名批量结束。

## 宿主差异（conhost 与 ConPTY）

Windows Terminal 用 ConPTY（`OpenConsole.exe`）承载控制台，传统控制台是 `conhost.exe`。两者都能附加与读屏，但窗口归属和尺寸来源不同；结论要记录宿主，不互相外推。

| 项目 | conhost | ConPTY（Windows Terminal） |
| --- | --- | --- |
| 目标 shell 的子进程 | 出现 `conhost.exe` | 由终端进程启动 `OpenConsole.exe`，`conhost.exe` 不是 shell 子进程 |
| `MainWindowHandle` | 实测可为 0，不能作就绪判断 | 窗口归 Windows Terminal，shell 进程通常为 0 |
| `GetConsoleWindow` | 可返回有效句柄 | 可返回有效句柄 |
| 读屏尺寸来源 | 控制台缓冲区设置 | 跟随终端窗口，实测 120×30 与终端默认窗口一致 |

实测环境：Windows 11、pwsh 7.6.3、PSReadLine 2.4.5。同一探针分别附加 `Start-Process pwsh` 与 `wt.exe -w -1 pwsh` 的会话，附加与读屏均成功。探针从代理自身的 shell 启动时，目标窗口可能并未真正显示在桌面上（`MainWindowHandle` 为 0、窗口矩形为零）；需要用户可见的界面验证时，从桌面会话启动。

## 与他人操作共存

探针不抢前台焦点，不等于用户碰不到同一个控制台。以下干扰会直接改变判读结果：

- **输入缓冲区争用**：用户在该窗口键入或粘贴，会和注入的按键交错成混合内容。判读前核对输入行与预期完全一致，不一致就重跑，不挑选看起来正确的片段。
- **前台焦点**：`WriteConsoleInputW` 不依赖焦点，用户切走窗口不影响读屏。`keybd_event`/`SendInput` 例外，按键发给当时的前台窗口，可能落进用户的编辑器或浏览器；只在必须验证真实按键时使用，先 `SetForegroundWindow`、核对 `GetForegroundWindow()`，结束后恢复原前台。
- **窗口尺寸、字号与滚动**：用户拖动窗口、改字号或滚动，都会改变 `srWindow` 与可见内容。每次注入与读屏前重新取尺寸，只判读提示符之后的有效行。
- **目标提前退出**：用户关闭窗口时，注入和读屏一起失败，现象与"菜单没有出现"相似。先查目标 `HasExited`，不要把进程消失当成补全没生效。
- **共享持久状态**：profile、PSReadLine 历史文件、临时目录、端口与服务、剪贴板都会留下痕迹。测试命令会写进用户真实历史，写过的文件与改动过的服务不随进程退出复原；用临时历史路径、临时工作目录和独立 profile，结束后核对改动范围并告知用户。
- **机器负载**：同机上的构建、同步、杀毒扫描会拉长 profile 初始化，固定等待必须换成轮询加超时上限。

需要用户配合时，明确说明"这段时间不要在该窗口输入或调整窗口大小"，而不是默认窗口不会被碰。

## 关键常量与常见坑

- `dwControlKeyState`：`SHIFT_PRESSED = 0x0010`、`LEFT_CTRL_PRESSED = 0x0008`、`LEFT_ALT_PRESSED = 0x0002`。把 Shift 写成 `0x0008` 会让大写字母变成 Ctrl 组合，例如 `G` 显示为 `^G`、`C` 触发取消。
- `CONOUT$` 只给读权限会在 `GetConsoleScreenBufferInfo` 上返回 `ERROR_ACCESS_DENIED`(5)；按读写打开。遇到 5 先查访问权限，不先怀疑附加失败。
- `FreeConsole()` 在进程本来没有控制台时也返回 `true`，`GetLastError` 可能残留 6；判断以返回值为准。
- `MainWindowHandle` 不能证明控制台可用：实测目标进程与其 `conhost` 子进程都为 0 时仍能附加读屏，窗口矩形也可能为零。就绪以读屏出现提示符为准。
- 附加成功后，PowerShell 宿主的成功流输出可能直接写入目标控制台并覆盖输入行。附加期间保持静默，结果只写文件。
- 脚本参数不要命名为 `Pid`，它与自动变量 `$PID` 冲突，改用 `TargetPid` 一类名称。
- `MenuComplete` 的行为是首个 Tab 用第一个候选替换当前词并展开菜单；在新词上再按 Tab 会重新补全，不保证在候选列表内循环。
- 输入时的列表视图（如 `<History(...) XxxFlags(...)>`）是预测，不是 Tab 候选菜单；判读以输入行是否被替换、是否出现候选菜单为准。
- 截图用 `PrintWindow(hwnd, hdc, 2)`（`PW_RENDERFULLCONTENT`），可抓取非前台窗口。pwsh 7.5（.NET 9）下 `Add-Type` 引用 `System.Drawing` 会缺 `System.Private.Windows.Core`，改用 Windows PowerShell 5.1 并加 `-ReferencedAssemblies System.Drawing`。
- 不要用 `SendKeys` 或 `AppActivate`：会抢前台焦点，目标未激活时直接失败；直接写输入缓冲区不依赖焦点。需要验证真实 Ctrl+C 时是例外：用 `keybd_event`/`SendInput`，先 `SetForegroundWindow` 并核对 `GetForegroundWindow()`，焦点不对就中止。
- 菜单中的 Ctrl+C：真实按键在默认控制台模式下不会关闭菜单、也不会清行；只把 Ctrl+C 绑到 `CancelLine` 同样无效。先 `Esc` 关菜单再 `Ctrl+C`；若要在菜单内一次生效，需在 Tab/MenuComplete 包装里临时设置 `[Console]::TreatControlCAsInput = $true`（并绑定 `CancelLine`），结束后恢复。

## 验收与清理

- 对照命令复现预期菜单，才算注入机制有效；对不上时先查字符回显、修饰键常量与读屏范围，不要先改补全配置。
- 记录环境版本（pwsh、PSReadLine、宿主、目标程序）、对照结果、目标结果与进程清理状态；截图只作辅助证据，判读仍以屏幕文本为准。
- 验证结束确认没有残留 pwsh 或 conhost 窗口，并复查终端窗口是否随 shell 一起关闭；只按记录的 pid 结束进程，不按进程名批量清理。
