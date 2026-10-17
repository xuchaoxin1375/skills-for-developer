## 查找已安装的浏览器

准备下载前，先复用项目已能运行的浏览器。项目锁定浏览器时沿用其运行器，不因发现系统版本就替换基线；任务允许使用系统 Chrome/Edge/Chromium 时，可以按本文查找。**找到文件、能启动、业务验收通过是三种不同证据。**

### 只读列出候选

`<skill-dir>` 指 `frontend-qa` 目录。入口只需 Python 标准库，不导入 Playwright、不联网、不安装、不执行候选的 `--version`，也不创建 guardian 或浏览器进程：

```powershell
python -X utf8 <skill-dir>/scripts/shot_scroll.py --list-browsers

# PowerShell 7 包装入口；-Python 可选目标解释器
& <skill-dir>/scripts/shot-quick.ps1 -ListBrowsers
```

输出 JSON 中的 `browser`、`path`、`source` 说明产品、解析后的真实文件和发现渠道；`eligible` 只表示通过原生格式及包装器排除检查。未发现候选时输出空数组并退出 0，表示查询完成；不表示环境已就绪。文件头检查不验证签名、来源可信性、架构、依赖或兼容性，候选应来自任务认可的安装渠道。

### 常见安装渠道与检索范围

下表列常见位置，详细候选只在 `scripts/browser_discovery.py` 维护。目录不存在即跳过，不全盘搜索，不递归枚举用户目录或安装器缓存。

| 系统与渠道 | 检索方式 | 使用边界 |
|---|---|---|
| Windows 官方安装、winget、Chocolatey | Chrome/Edge 的 HKCU/HKLM App Paths，分别读取 32/64 位注册表视图；再查 `%ProgramFiles%`、`%ProgramW6432%`、`%ProgramFiles(x86)%`、`%LOCALAPPDATA%` 下的产品目录 | winget/Chocolatey 安装常落在产品标准目录；不执行包管理器，也不解析默认浏览器的打开命令 |
| Windows Scoop | `$env:SCOOP`、`$env:SCOOP_GLOBAL`；未配置时用用户目录下 `scoop` 和 `%ProgramData%` 下 `scoop` 的常见布局，检查应用的 `current` 入口及常见真实 EXE 相对位置 | 不选最大版本目录，不执行 `shims`，不依赖包管理器命令已加入 PATH |
| macOS 官网安装、Homebrew cask | 系统和用户的 `Applications` 下 Chrome/Edge/Chromium `.app` 包内 `Contents/MacOS` 的真实文件 | 只支持只读发现；当前截图 guardian 不支持 macOS，运行交给项目已有受管工具 |
| Linux deb/rpm、发行版 Chromium | 常见 `/opt` 产品目录、`/usr/lib` / `/usr/lib64` 的 Chromium 实体和 `/usr/bin` 入口；补查已知 PATH 命令 | shell 启动脚本只列为候选，自动模式仅选择原生 ELF 文件；仍需实际验证共享库和运行依赖 |
| Snap、Flatpak、AppImage、自定义便携目录 | Snap 常见入口可出现在候选中；Flatpak/AppImage 和自定义目录由用户明确提供或按对应安装工具查询 | 不绕过沙箱启动器、挂载和命名空间要求；不把 `snap`、`flatpak` 等启动器当浏览器，不默认探测可移动盘或任意目录 |

PATH 只补查已知浏览器命令，使用文件查询，不执行 `where` / `which` 或候选程序；软链接解析后去重。Windows 默认优先 Edge、Chrome、Chromium，其他系统优先 Chrome、Edge、Chromium；同一产品优先注册表、固定目录，再到 PATH。排序仅为无需指定产品的临时采集提供稳定选择，不表示某种浏览器更符合项目基线。

### 选择并验证

浏览器选择分为三种显式方式，互斥使用；不传选择参数时仍使用目标 Playwright 包对应的默认制品，不自动改用系统版本：

```powershell
# 常规安装优先指定产品，由 Playwright 的 channel 解析
python -X utf8 <skill-dir>/scripts/shot_scroll.py --url 'https://example.com' --channel msedge --out page.png

# 不要求特定产品时，从常用位置选择首个 eligible 候选
python -X utf8 <skill-dir>/scripts/shot_scroll.py --url 'https://example.com' --discover-browser --out page.png

# 自定义/便携安装，明确传真实文件；不传启动脚本或 shim
python -X utf8 <skill-dir>/scripts/shot_scroll.py --url 'https://example.com' --executable-path '<真实浏览器文件>' --out page.png

# PowerShell 兼容入口支持相同选择
& <skill-dir>/scripts/shot-quick.ps1 -Url 'https://example.com' -DiscoverBrowser -Out page.png
```

`--discover-browser` 未找到合格候选时退出 2；选定后启动或采集失败时，返回该次错误，**不轮流启动其他候选、不自动下载、不切换成裸浏览器命令**。日志记录选中产品、来源和解析后的路径；成功后记录实际浏览器版本与清理结果，仍需查看截图判断页面是否符合预期。启动总期限与异常回收按 [托管截图工作流](screenshot-workflow.md#生命周期与托管边界)。

截图仍需目标环境的 Playwright 包。使用受控本地页面先验证浏览器启动和截图，再验证外网、代理与业务；浏览器制品及系统依赖准备按 [浏览器安装](../../network-access/references/browser-installation.md)。发现脚本不猜 Playwright 缓存版本；缓存由实际运行环境的 Playwright/项目运行器解析。

### 其他 skill 如何复用

安装排障或抓取工具可调用这个只读入口补充浏览器位置证据，再通过自身支持的 `channel` / `executable_path` 等参数使用目标。`htmlmini` 和 `resilient-browser-fetch` 各有现存探测逻辑，覆盖范围及参数语义不同；本入口不会替换它们的探测器，不证明 Scrapling/CloakBrowser 能使用这些候选，也不让其他脚本自动获得同等生命周期保障。

Windows 已真实验证路径发现与受管截图。Linux/macOS 的候选规则仅在 Windows 上使用隔离文件样本验证，尚未在对应系统实际安装和启动；不将样本测试当作这些平台的运行验证。
