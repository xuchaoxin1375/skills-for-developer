## 受托管的截图工作流

Agent 独立采集首屏和滚动多屏时统一用 `scripts/shot_scroll.py`，默认只拍首屏。`shot-quick.ps1` 是同一入口的 PowerShell 兼容包装，不再直接创建 Chrome 进程。截图触发、取景和实际查看按 [视觉验收](../../ai-verified-delivery/references/visual-acceptance.md)，资源政策按 [测试资源预算与回收](../../web-app-testing/references/environment-and-maintenance.md#测试资源预算与回收)。

### 普通浏览器与 Playwright 的区别

**普通 Chrome/Edge 本身就能截图、打印 PDF、滚动、点击和填写表单。** 人可以直接操作，也可以通过浏览器的自动化接口控制。Playwright 是操作浏览器的 Python/Node 等语言库；它负责把这些能力组织成可重复的脚本，截图仍由浏览器渲染生成。

| 比较项 | 直接使用普通浏览器 | 通过 Playwright 操作浏览器 |
|---|---|---|
| 截图 | 开发者工具可拍视口、区域、元素和整页；不要求安装 Playwright | 可编程选择视口、元素、区域和整页，便于批量重复 |
| 交互与就绪 | 人判断何时操作和截图；无头命令本身不表达业务流程 | 用定位器操作，支持自动等待；仍需明确业务就绪条件和结果断言 |
| 环境与隔离 | 日常窗口通常带有个人登录、扩展和设置 | 可固定视口、配置和独立 browser context（浏览器上下文），减少会话干扰 |
| 回归与证据 | 手动截图适合观察和沟通；单张图片不证明流程正确 | 配合测试 runner（运行器）执行断言，按配置收集截图、trace（执行轨迹）和失败信息 |
| 资源回收 | 人关闭窗口；命令启动的后台进程需另管 | 正常路径可显式关闭；调用端被强杀时仍需外层进程托管 |

**浏览器、自动化库、测试运行器和资源托管各有职责。** 浏览器负责页面渲染与执行，Playwright 库负责控制，测试运行器负责用例编排、断言与报告，guardian 或 CI/容器负责相应范围的期限和回收。Python 使用 pytest 等运行器，Node 项目可用 Playwright Test；安装 Playwright 包不会自动获得完整测试体系或异常退出后的进程回收保障。

有头/无头（headful/headless）只表示是否显示浏览器界面，与是否使用 Playwright 是两个选择。普通 Chrome 支持无头运行，Playwright 也可以显示窗口；无头运行仍会占用 CPU、内存并创建进程。具体能力见 [Chrome 无头模式](https://developer.chrome.com/docs/chromium/headless)与 [Playwright 截图接口](https://playwright.dev/python/docs/screenshots)。

### 如何选择

- **临时看图或人工复现**：直接使用已安装浏览器的开发者工具，无需为截图安装 Playwright。手动证据可用于诊断；验收要求自动断言时，另补对应检查。
- **Agent 首屏或滚动多屏采集**：使用下文受托管入口，统一输出、总期限和本轮进程回收。裸浏览器无头截图命令虽然能出图，但若没有外层托管，不能作为本入口的自动回退。
- **登录、交互、多视口或持续回归**：沿用项目的 Playwright 等自动化与测试运行器，按业务状态等待和断言；固定浏览器、OS、字体等视觉基线。
- **已有浏览器工具或远程托管服务**：先复用其实际可用能力，确认会话所有者、总期限、并发限制及释放方式。服务端托管能减少本地进程负担，仍需核对断线后的会话回收；“远程”本身不证明资源已释放。

Chrome 手动截图的最短路径如下；Edge 可在对应开发者工具中查找截图命令，菜单随版本和语言变化：

1. 打开目标页面和开发者工具，让开发者工具获得焦点。
2. Windows/Linux 按 `Ctrl+Shift+P`，macOS 按 `Command+Shift+P`，打开[命令菜单](https://developer.chrome.com/docs/devtools/command-menu/)，输入 `screenshot`。
3. 选择所需截图命令；区域截图使用 **Capture area screenshot**，再拖动选择范围。整页、元素及设备模拟取景见 [Chrome 开发者工具截图说明](https://developer.chrome.com/blog/devtools-tips-33)。

整页截图只覆盖当前渲染内容，不保证触发全部懒加载，也不等于滚动多屏；虚拟列表和页面内部滚动容器需按目标状态另取景。按坐标切片（视口拼接、`captureBeyondViewport` 之类的 clip 取景）只截文档内容，不重绘 `position: fixed/sticky` 元素——固定头部、粘性侧栏只在真实滚动后的视口里出现，取景方式直接决定第 N 屏长什么样。

### 复用已安装浏览器与连接已有会话

**免下载浏览器不等于免装自动化库。** 下文 `--channel msedge` / `--channel chrome` 让 Playwright 启动本机已安装的 Edge/Chrome；目标 Python 环境仍需 Playwright 包，但不必另下载默认 Chromium。它启动独立自动化实例，不会自动接管用户已开的窗口或继承个人登录；系统浏览器自动更新后也需复核视觉基线。Firefox/WebKit 依赖 Playwright 对应制品，不能照搬这两个 channel 替换成任意本机 Firefox/Safari。兼容性和企业策略限制见 [受支持浏览器](https://playwright.dev/python/docs/browsers)。

连接现有浏览器属于另一种所有权模式。Playwright 的 `connect_over_cdp()` 使用 Chrome DevTools Protocol（CDP，Chrome 开发者工具协议）连接已暴露端点的 Chromium 浏览器；它仅支持 Chromium 系浏览器，部分高级功能的兼容性低于原生 Playwright 协议连接，见 [CDP 连接说明](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)。原始 CDP 也能实现交互和截图，但等待、错误恢复、证据和资源管理需要调用方组织。

仅在任务明确需要且端点受控时复用现有会话，确认页面和浏览器由谁关闭；不要接管日常个人 profile 或按浏览器名称批量结束进程。本截图入口只管理自己启动的进程树，**不提供连接现有 CDP 会话的选项**，其回收保证不覆盖外部浏览器。

### 使用

不知道本机浏览器装在哪里时，先用 `--list-browsers` 只读列出候选；任务允许任一系统 Chromium 浏览器时可用 `--discover-browser` 自动选择。Windows 注册表、Scoop、macOS 应用包、Linux 包安装及包装器边界按 [查找已安装的浏览器](browser-discovery.md)，不传选择参数时仍使用匹配的 Playwright 默认制品。

目标 Python 环境需已有 Playwright；先复用项目环境，不自动安装依赖。`<skill-dir>` 指本 skill 目录：

```powershell
# 首屏，指定输出文件
python -X utf8 <skill-dir>/scripts/shot_scroll.py --url 'https://example.com' --out page.png

# 一次浏览器会话拍两屏；使用已安装的 Edge，免下载浏览器制品
python -X utf8 <skill-dir>/scripts/shot_scroll.py --url 'https://example.com' --screens 2 --channel msedge --out-dir shots

# PowerShell 7 兼容入口；-Python 可指定虚拟环境解释器
& <skill-dir>/scripts/shot-quick.ps1 -Url 'https://example.com' -Channel msedge -Out page.png
```

未指定输出时，每轮使用独立的系统临时目录 `opencode/shots/<run-id>`，成功图片作为结果保留。指定同一输出文件时，仅成功采集并回收浏览器后才替换文件；失败不会预先删除旧图片。多张图片逐文件原子替换，不承诺整批事务，未收到本轮全部 `SHOT` 行不能将旧文件或部分结果当本轮成功证据。

默认视口 `1440×900`，单次操作超时 30 秒，整个 worker 总期限 60 秒，收尾另留最多约 8 秒。可用 `--width`、`--height`、`--timeout-ms`、`--wall-timeout-ms` 调整；最多 20 屏、宽高各不超过 8192。`--settle-ms` / `--step-wait-ms` 默认 500 毫秒，只是采集等待，不是业务就绪断言；需要交互、登录或精确状态等待时使用项目的受管测试 runner。

代理按 `--proxy` → `SCRAPE_PROXY` →（指定 `--discover-proxy` 时）机外登记解析；没有代理设置且未要求发现时直连。只验证登记端点监听，不据此宣称出口可用。日志不打印代理凭据和页面查询参数。`--channel chrome/msedge`、`--executable-path`、`--discover-browser` 互斥；显式路径必须指向可读的原生浏览器文件，不传包装脚本或垫片。

国内安装按 [浏览器安装与国内网络](../../network-access/references/browser-installation.md) 区分包源和制品源。本机有 Edge/Chrome 时可只补目标环境的 Playwright 包；不允许补包且没有可用自动化工具时，记录自动化未执行。人工仍可通过开发者工具截图，是否满足验收取决于任务要求；Agent 不回退到无期限的裸浏览器命令。

### 生命周期与托管边界

`managed_browser.py` 提供独立的本地守护进程（guardian）；没有常驻服务、浏览器池或远程浏览器依赖。Windows 作业对象（Job Object）约束本轮进程树；Linux 的 subreaper 负责接收失去父进程的后代，pidfd 是绑定进程身份的文件描述符。

1. 调用端创建独立 guardian，持有通信管道作为存活信号。guardian 持有操作系统文件锁，同一用户、同一临时目录默认只允许一轮任务；第二轮返回忙，不排队、不自动重试。
2. worker 先等待启动配置。Windows 中，guardian 将其加入启用 `KILL_ON_JOB_CLOSE` 的 Job Object 后才放行；Chromium、Playwright 驱动与后代继承约束，不凭全机进程数认领资源。
3. Playwright 显式关闭 context 和 browser；总期限覆盖启动、导航、截图和正常关闭。到期或调用端管道断开时，guardian 终止本轮进程树。
4. 即使 worker 正常返回，也清理残留后代，核验作业内活动进程归零，再发布截图并删除本轮 profile、浏览器临时文件。worker 原始输出丢弃，避免无界日志增长及凭据回显；失败仅返回异常类型与已知排查提示。
5. 调用端被强制结束时，guardian 通过管道 EOF 收尾。Windows 中 guardian 自身被强制结束，Job Object 仍负责终止成员，但文件清理无法继续；下次运行检测遗留目录并拒绝启动。

Linux 使用独立进程组及 subreaper，回收被重新托管的后代；用 pidfd 确认并终止进程，涵盖另建 session 的浏览器，不只终止原进程组。要求内核和 Python 支持 pidfd。其他平台启动前明确拒绝，交给项目已有受管 runner；不宣称 macOS 具有同等保障。Windows 已实测，Linux 分支需在目标环境另验。

成功必须同时得到本轮 `SHOT` 行和 `CLEANUP verified`，并实际查看图片；文件存在仅证明采集，不证明视觉符合预期。资源收尾不明时禁止叠加失败轮。

| 退出码 | 含义与处理 |
|---|---|
| `0` | 截图及清理成功 |
| `1` | 启动、导航、截图或 worker 失败；检查环境与页面，不盲目重试 |
| `2` | 参数、代理发现或平台能力不满足；修正条件再执行 |
| `3` | 已有任务持锁；等待本轮收尾，不绕过锁并发启动 |
| `4` | 清理未确认或 guardian 异常；停止新增任务，核对资源 |
| `124` | worker 超过总期限，已完成收尾；页面未验收 |
| `130` | 用户取消或调用端退出；guardian 执行收尾 |

状态目录为系统临时目录中的 `opencode/browser-tasks`；Linux 使用 `opencode-<uid>` 隔离用户，截图结果目录同样采用这个前缀。失败清理会保留 `cleanup-failed.json` 与本轮目录，后续运行拒绝继续。恢复时先确认锁已释放、本轮进程资源已终止，再只处理该记录指向的本轮目录与标记；不要按 Chrome 名称或端口杀进程，不删整个共享临时目录。仅 guardian 意外退出留下目录时也适用。系统关机、整个容器被销毁或宿主强杀全部相关进程后，不能指望应用继续清文件；下一轮保守阻断。

### 迁移与复用

- 实现、浏览器发现和测试在 `browser-automation` 统一维护。旧 `frontend-qa/scripts/shot_scroll.py` 与 `shot-quick.ps1` 作为 CLI 委托保留参数和退出码；旧参考文件保留跳转。直接依赖旧内部模块或测试目录的调用需更新到本 skill，不维护第二份运行实现。
- `shot_scroll.py` 的默认屏数由 2 改为 1；多屏显式传 `--screens 2`。
- `shot-quick.ps1` 现在需要 Python Playwright，移除按 PATH/最大缓存版本猜浏览器、隐式环境浏览器覆盖及裸 Chrome 回退。`-Chrome` 映射到 `--executable-path`，推荐 `-Channel msedge/chrome` 或匹配项目版本的缓存。
- 常用安装位置的查找通过显式 `--discover-browser` / `-DiscoverBrowser` 启用；`--list-browsers` / `-ListBrowsers` 可在未安装 Playwright 时只读列候选。它们不恢复旧入口的隐式选版本与失败回退。
- 旧 `-VirtualBudget` 已移除，改用 `-TimeoutMs` 与 `-WallTimeoutMs`。页面虚拟时间不能作为进程总期限。
- 其他 skill 的单次视口截图可引用本入口。复杂测试沿用项目 runner；`resilient-browser-fetch` 的挑战处理、持久会话及 `htmlmini` 渲染回退不因本次改动自动获得相同托管保障。

### 验证

```powershell
python -X utf8 -m unittest discover -s <skill-dir>/tests -v
```

生命周期用例使用真实 worker 和持有监听端口的后代，验证成功残留、失败、超时、取消、调用端强制退出、并发拒绝及清理失败阻断，同时保留不相关监听实例。Windows 另验 guardian 强制退出的 Job Object 回收；浏览器用例需要可启动的匹配 Chromium，验证本地两屏、失败不替换旧结果及含空格中文路径。公共网站、代理出口和视觉质量不在这些测试的证明范围。
