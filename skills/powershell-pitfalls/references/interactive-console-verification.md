# 交互式控制台验证（模拟按键与读屏）

## 适用条件

- Windows 交互式桌面会话，需要复验用户按 Tab 后实际看到的界面：候选菜单、排序、描述列、选中后的输入行变化、预测视图。
- 只关心候选集合时，优先用非交互入口：`[System.Management.Automation.CommandCompletion]::CompleteInput($line, $cursor, $null)`；本流程用于补全引擎之外的界面层差异。
- 需要目标程序有独立控制台窗口；纯服务会话或无桌面环境不适用。

## 基本做法

1. 启动独立窗口：`Start-Process pwsh -ArgumentList '-NoLogo','-NoExit' -PassThru`。保留 profile，才是在验证用户日常环境；启动后读 `(Get-Process -Id <pid>).MainWindowHandle`，非 0 表示控制台窗口已建立。
2. 等待提示符：固定等待只作首次试探，应以读屏结果确认；profile 初始化耗时因机器而异。
3. 附加控制台：探针进程先 `FreeConsole()`，再 `AttachConsole(<pid>)`，用 `CreateFileW("CONIN$"/"CONOUT$")` 取得输入输出句柄。
4. 注入按键：`WriteConsoleInputW` 写入 `KEY_EVENT_RECORD`，`EventType = 1`，每字符发送按下与抬起两条；虚拟键码用 `VkKeyScanW(ch)` 取低字节，扫描码用 `MapVirtualKeyW(vk, 0)`。文本的修饰键从 `VkKeyScanW` 高字节解析。
5. 读取屏幕：`GetConsoleScreenBufferInfo` 取 `dwSize` 与 `srWindow`，逐行 `ReadConsoleOutputCharacterW`，再 `TrimEnd()`；按可见窗口读取，不读整块缓冲区。
6. 顺序验证：先跑已知命令的对照（如 `Get-Chi` + Tab），确认注入与读屏链路，再测目标命令；一次只注入一步并等待重绘。
7. 清行与退出：菜单打开时先 `Esc` 关闭菜单，再 `Ctrl+C` 清行；最后输入 `exit` 回车退出，进程仍在时用 `Stop-Process` 兜底。

## 关键常量与常见坑

- `dwControlKeyState`：`SHIFT_PRESSED = 0x0010`、`LEFT_CTRL_PRESSED = 0x0008`、`LEFT_ALT_PRESSED = 0x0002`。把 Shift 写成 `0x0008` 会让大写字母变成 Ctrl 组合，例如 `G` 显示为 `^G`、`C` 触发取消。
- 探针附加控制台后，PowerShell 宿主的成功流输出可能直接写入目标控制台并覆盖输入行。附加期间保持静默，结果只写文件。
- 脚本参数不要命名为 `Pid`，它与自动变量 `$PID` 冲突，改用 `TargetPid` 一类名称。
- `MenuComplete` 的行为是首个 Tab 用第一个候选替换当前词并展开菜单；在新词上再按 Tab 会重新补全，不保证在候选列表内循环。
- 输入时的列表视图（如 `<History(...) XxxFlags(...)>`）是预测，不是 Tab 候选菜单；判读以输入行是否被替换、是否出现候选菜单为准。
- 截图用 `PrintWindow(hwnd, hdc, 2)`（`PW_RENDERFULLCONTENT`），可抓取非前台窗口。pwsh 7.5（.NET 9）下 `Add-Type` 引用 `System.Drawing` 会缺 `System.Private.Windows.Core`，改用 Windows PowerShell 5.1 并加 `-ReferencedAssemblies System.Drawing`。
- 不要用 `SendKeys` 或 `AppActivate`：会抢前台焦点，目标未激活时直接失败；直接写输入缓冲区不依赖焦点。

## 验收与清理

- 对照命令复现预期菜单，才算注入机制有效；对不上时先查字符回显、修饰键常量与读屏范围，不要先改补全配置。
- 记录环境版本（pwsh、PSReadLine、目标程序）、对照结果、目标结果与进程清理状态；截图只作辅助证据，判读仍以屏幕文本为准。
- 验证结束确认没有残留 pwsh 或 conhost 窗口。
