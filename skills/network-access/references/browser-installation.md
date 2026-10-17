## Playwright 与 Scrapling 浏览器安装

国内安装浏览器、`playwright install` / `scrapling install` 下载失败时读取。先确认实际执行位置、目标解释器或项目包管理器，再按本文件选路；包索引的设置见 [依赖下载](dependency-downloads.md)，Scrapling 的环境与安装行为见 [平台与依赖](../../resilient-browser-fetch/references/platforms.md)。

普通 Chrome/Edge 可以直接通过开发者工具截图，无需 Playwright；自动化可以由 Playwright 控制这些已安装的浏览器。**Playwright 包与浏览器制品分别安装**：使用已安装 Chrome/Edge 的 channel 可省去浏览器下载，仍需目标环境中的 Playwright 包。人工截图、自动化、测试运行器及资源托管的选择见 [普通浏览器与 Playwright 的区别](../../frontend-qa/references/screenshot-workflow.md#普通浏览器与-playwright-的区别)。

### 分清四个阶段

| 阶段 | 配置与检查 | 常见误判 |
|---|---|---|
| 安装 Python/Node 包 | pip/uv 的 Simple 源、npm/pnpm 的 registry，保留项目锁定版本 | 换包源后，以为浏览器也会从同一镜像下载 |
| 下载浏览器制品 | Playwright 下载器的代理/制品源；CloakBrowser 等独立下载器另查支持项 | 把 `SCRAPE_PROXY` 或浏览器运行时 `proxy` 当作安装代理 |
| 安装系统依赖 | Linux 发行版包管理器与提权后的环境；Windows/macOS 按 CLI 当前行为检查 | 把 `install-deps` 的系统包或平台组件错误当作 Chromium CDN 故障 |
| 启动并操作页面 | 实际 runner、浏览器版本、系统库、字体和运行时代理 | 包可导入、缓存存在或安装命令退出 0 就判可用 |

### 安装前先复用已有环境

1. 检查项目依赖、锁文件、目标解释器与所需浏览器。Python 用该环境的 `python -m playwright`，Node 用项目实际包管理器的本地 CLI，如 `pnpm exec playwright`；先确认包已安装，避免把可能自动取包的 `npx` / `pnpm dlx` 当只读探针。
   不确定系统浏览器位置时，按 [查找已安装的浏览器](../../frontend-qa/references/browser-discovery.md) 只读列候选，覆盖常见注册表/目录、Scoop、应用包和 Linux 安装；不因 PATH 没有命令便直接下载。
2. 已有 runner 能启动目标浏览器时直接复用。包升级后再由同一包版本安装匹配制品；临时下载另一个 CLI 版本可能装出当前项目用不了的浏览器。
3. 默认只补当前任务需要的浏览器。无参数 `install` 可能安装多种浏览器；测试要求 Firefox/WebKit 时仍需补齐。`--only-shell` / `--no-shell` 先核对本地帮助与启动方式，不因使用 headless 就假定只需 headless shell。
4. 已有 Chrome/Edge 且任务允许时可用对应 `channel`，先实际启动；它不自动等同于项目原有视觉基线。`playwright install chrome` 会安装浏览器，不能用来探测现有 Chrome。

### 国内选路

**浏览器大包优先用已登记的可用 HTTP/mixed 代理访问官方 CDN；无代理或代理失败时，才选择已核验的制品镜像。** Python/Node 包可继续用已核验的国内包源，两者独立配置。海外执行优先原站直连；容器、WSL 和 CI 里的环回地址不代表宿主机代理。

- 按 [代理登记](proxy-registry.md) 读取本机资源，不猜端口。Playwright 下载子进程使用 `HTTPS_PROXY`；HTTPS 目标也可通过 `http://` 代理入口访问，不把 SOCKS 端口冒充 HTTP 端口。
- 先检查已有 `PLAYWRIGHT_DOWNLOAD_HOST` 及 `PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST` / `PLAYWRIGHT_FIREFOX_DOWNLOAD_HOST` / `PLAYWRIGHT_WEBKIT_DOWNLOAD_HOST`。浏览器专用变量优先于通用变量；过期镜像覆盖不清除时，设置代理后仍可能访问旧镜像。
- 默认选择一条路线。通过代理访问官方 CDN 时，不顺手再填镜像地址；切回官方源需在任务进程内撤销相关镜像覆盖并保存原值。明确需要代理访问内部制品库时可以组合配置。
- 所有变量只影响当前终端及后续子进程。用专用终端，或保存旧值并在任务后恢复；不写全局代理、`setx` 或项目内的本机端口。检查 `NO_PROXY` 是否让下载域名绕过代理。

以下示例假定目标环境已有 Playwright、已确认未被旧镜像覆盖。替换代理占位符后执行；Python 的 `python` 指目标环境解释器，Node 选择项目已有的本地 CLI，二选一。命令失败时停止后续步骤。

```powershell
$env:HTTPS_PROXY = 'http://127.0.0.1:<port>'
$env:PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT = '120000'
python -X utf8 -m playwright install --dry-run chromium
if ($LASTEXITCODE -ne 0) { throw 'Playwright download plan failed' }
python -X utf8 -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Playwright browser installation failed' }
```

```bash
(
  export HTTPS_PROXY='http://127.0.0.1:<port>'
  export PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT='120000'
  python -m playwright install --dry-run chromium &&
    python -m playwright install chromium
)
```

Node 项目将上述两条 Python 命令分别替换为 `pnpm exec playwright install --dry-run chromium`、`pnpm exec playwright install chromium`，或项目对应的本地 CLI；不另装全局 Playwright。`120000` 是慢线路的空闲等待示例（毫秒），不是连接超时或安装总期限；有持续下载进展的大包可运行更久，外层仍需按任务预算限制整个安装进程，不能叠加无限重试。

### 镜像回退

`PLAYWRIGHT_DOWNLOAD_HOST` 指向兼容 Playwright 路径规则的**制品基址**，不是 npm registry、PyPI Simple 源或某个 ZIP 文件。候选镜像可能只覆盖旧版或部分平台，不维护永久默认的公共镜像地址。

1. 为目标包版本设置候选基址，重新运行同一 CLI 的 `install --dry-run chromium`。PowerShell 为 `$env:PLAYWRIGHT_DOWNLOAD_HOST = '<已核验制品基址>'`；Bash 为 `export PLAYWRIGHT_DOWNLOAD_HOST='<已核验制品基址>'`。专用浏览器变量的优先级仍有效。
2. 检查输出中的**全部制品**和实际 URL。Chromium 安装还可能需要 headless shell、FFmpeg、平台辅助工具；不同版本可能采用 Chrome for Testing 等不同路径，不手写固定 revision/ZIP 路径。
3. 用有界 GET 检查具体文件及重定向后的来源，确认不是 HTML 错误页。HEAD、首页 200 或拼接 URL 正确均不证明文件能下载；小段取回也不证明完整归档无损，最终以下载器完整安装及启动为准。可信制品有签名/校验值时一并核对。
4. 404/缺版本时回退原站或另一已核验来源；TLS 错误按下载器支持配置受信任 CA，例如 Playwright 的 Node 驱动用 `NODE_EXTRA_CA_CERTS`。不关闭证书或完整性校验，也不靠清空全部缓存解决网络慢。

`--dry-run` 不执行下载，只能证明当前 CLI 解析出的版本、路径和计划地址。不能把它记作“镜像可用”或“浏览器已安装”。

### Scrapling 与其他下载器

Scrapling 使用目标环境里的 `scrapling` CLI；其 Playwright 子进程继承安装环境的 `HTTPS_PROXY` 和 `PLAYWRIGHT_*` 设置。先核对该版本安装行为：`scrapling install` 可能同时执行系统依赖安装，不能直接当作纯下载替换命令。需要拆分阶段、处理安装标记或 Linux 权限时，读 [Scrapling 安装行为](../../resilient-browser-fetch/references/platforms.md#scrapling-安装行为)。

`SCRAPE_PROXY`、抓取参数 `--proxy` 和 Playwright `launch(proxy=...)` 控制页面访问，不替代下载代理；反过来，`HTTPS_PROXY` 下载成功也不证明页面访问已走代理。CloakBrowser 有自己的二进制与下载器，不能假定 `PLAYWRIGHT_DOWNLOAD_HOST` 对它生效；按其实际版本支持配置并单独验证。

Linux 的 `install-deps chromium` / `install --with-deps` 使用系统包管理器，可能提权。分别核验系统软件源与提权后代理是否保留；必要时在已授权的系统依赖步骤显式传代理，不给整个包安装过程一律加 `sudo`。Windows 也可能调用 Media Feature Pack 安装脚本；各平台先核对目标版本 `install-deps --help` / `install-deps --dry-run chromium` 的输出，浏览器归档可下载不代表平台组件已就绪。

### 缓存与安装后验证

确认运行进程能访问目标包版本匹配的缓存；安装与运行的用户、容器或 `PLAYWRIGHT_BROWSERS_PATH` 不同时，显式核对路径和权限。默认缓存：Windows `%LOCALAPPDATA%\ms-playwright`，macOS `$HOME/Library/Caches/ms-playwright`，Linux `${XDG_CACHE_HOME:-$HOME/.cache}/ms-playwright`；自定义位置按实际环境变量。不要通过改目录名、伪造安装标记或复制任意 Chrome 来冒充匹配制品。CI 缓存按包版本、OS 和架构区分，命中缓存仍检查系统依赖并实际启动。

先用项目 runner 启动所需浏览器并断言本地页面，隔离外网因素。Python 的最小示例：

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        page = browser.new_page()
        page.set_content('<h1 id="ready">browser-ready</h1>')
        assert page.locator('#ready').inner_text() == 'browser-ready'
        print(browser.version)
    finally:
        browser.close()
```

Node 沿用项目 runner 做同等启动与断言；Scrapling 还需通过实际 fetcher 启动并取回一个受控页面，CloakBrowser 通过其引擎另验。`check_environment.py` 只读诊断有助于定位包、CLI 和代理端口，不会证明 Scrapling 浏览器已启动。最后再验证任务目标及运行时代理，分别报告下载、启动、页面业务结果与未运行项。
