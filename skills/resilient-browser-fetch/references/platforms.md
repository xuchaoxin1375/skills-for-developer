# 平台与依赖

## 包管理器与国内源

先运行 `uv --version`。Python 环境可由 Conda、`venv` 或 `uv venv` 创建；如果 `uv` 可用，优先使用 `uv pip` 并通过 `--python` 明确该环境的解释器。只有 `uv` 不可用时才在激活的同一环境中回退到 `python -m pip`。不要在一次安装流程中交替使用两个安装器，也不要因为使用 `uv pip` 就另建环境。保留用户现有的 `uv.toml`、环境变量和 pip 配置，不要无条件覆盖国内源。

国内安装前按 [依赖下载](../../network-access/references/dependency-downloads.md) 选择包源，按 [浏览器安装与国内网络](../../network-access/references/browser-installation.md) 准备浏览器下载路线，再执行下方对应平台命令。包可用已核验的国内镜像；浏览器制品默认先走已核验的国内制品镜像（大包不耗代理额度），缺件或校验不过再回退已登记代理访问官方源，不等到长时间下载失败后才配置。

`UV_DEFAULT_INDEX` / `PIP_INDEX_URL` 只控制对应安装器的包源；浏览器下载的 `HTTPS_PROXY` 需在启动 `scrapling install` **之前**设置并由子进程继承。`SCRAPE_PROXY` / 抓取 `--proxy` 只控制页面访问，不解决安装下载。

## Scrapling 安装行为

已核对的 Scrapling 0.4.11 与 0.4.15 中，`scrapling install` 依次调用当前解释器的 `playwright install chromium`、`playwright install-deps chromium`，再更新 TLD 数据，并写入包目录下的安装标记。因此它不只是浏览器下载：Linux 上可能触及系统包与提权；Windows 的 Playwright CLI 可能调用 Media Feature Pack 安装脚本。执行前核对本地 `scrapling install --help`、`python -m playwright install-deps --dry-run chromium` 输出、系统权限及代理继承。其他版本检查本地实现，不从命令名推断行为。

需要完整初始化且系统依赖步骤已确认适用于当前平台时，沿用该版本官方 `scrapling install` 入口。若系统依赖已由镜像/管理员提供、任务只需修复缺失浏览器，可在同一目标环境单独运行 `python -m playwright install chromium`，并明确系统依赖与其他初始化未由这条命令覆盖；不要给包安装或整个抓取过程一律加 `sudo`。

出现 `The dependencies are already installed` 只表示命中安装标记，不证明当前缓存、Playwright 版本或系统库可用。升级包、换运行用户或缓存路径后先实际启动；缺浏览器时定向补齐，确需重跑完整初始化才核对 `--force`，不默认强制重装或手工伪造标记。

`check_environment.py` 检查解释器、包导入、CLI、代理端口和可选 CloakBrowser 文件信息，不启动 Scrapling 浏览器；它通过后仍须用实际 fetcher 取回一个受控页面并断言内容。

系统 Chrome 未识别时，可按 [浏览器发现](../../browser-automation/references/browser-discovery.md) 只读补查注册表、Scoop 等常用位置，再核对当前 fetcher 支持的参数。发现的 Edge/Chromium 不自动等同于 `--real-chrome` 所要求的 Google Chrome，也不能代替 CloakBrowser 专用制品。

## Conda 环境配合 uv

Conda 负责 Python 版本、环境目录和非 Python 运行库，`uv pip` 只负责向选定解释器安装 Python 包。环境名称可以是 `scrapling`、`main`、`base` 或用户已有名称，不要硬编码。

Linux/macOS：

```bash
conda create -n scrapling python=3.12 -y  # 已有环境时省略
PYTHON="$(conda run -n scrapling python -c 'import sys; print(sys.executable)')"
uv pip install --python "$PYTHON" -r <skill-dir>/requirements-stealth.txt
conda run -n scrapling --no-capture-output scrapling install
conda run -n scrapling --no-capture-output python -X utf8 <skill-dir>/scripts/check_environment.py
```

Windows PowerShell：

```powershell
conda create -n scrapling python=3.12 -y  # 已有环境时省略
$Python = (conda run -n scrapling python -c "import sys; print(sys.executable)" | Select-Object -Last 1).Trim()
uv pip install --python $Python -r <skill-dir>\requirements-stealth.txt
conda run -n scrapling --no-capture-output scrapling install
conda run -n scrapling --no-capture-output python -X utf8 <skill-dir>\scripts\check_environment.py
```

运行脚本时使用 `conda run -n <env> --no-capture-output python -X utf8 ...` 或先 `conda activate <env>`。`conda run` 不带 `--no-capture-output` 时会捕获子进程输出再用自己的 stdout 重印，在 GBK 代码页的 Windows 上遇到中文输出会 `UnicodeEncodeError`（实测），必须带上。不要用环境 A 的 Python 加载包，却因为 PATH 顺序调用环境 B 的 `scrapling` 命令；诊断脚本会分别报告当前解释器和当前环境旁的 CLI。

不确定哪个环境有目标层时，用 `check_environment.py --list-envs` 扫描（识别 `conda:<env>`/`conda:base`/`venv`/`venv(uv)`/`system`，按可运行层排序并给出建议命令）；诊断按"运行它的解释器"判定，未 activate 直接调用 `...\envs\<name>\python.exe` 也会被正确识别为 conda 环境。

## Linux（优先）

使用 CPython 3.10+ 和独立虚拟环境。层 0（静态 HTTP）不需要任何第三方包，可直接用；需要渲染时按需加层 1，需要挑战求解时再加层 2，只有明确需要 CloakBrowser 指纹底座时才装层 3。

```bash
python3 -m venv .venv
# 层 1（按需）
uv pip install --python .venv/bin/python playwright
.venv/bin/playwright install chromium
# 层 2（挑战求解，按需）
uv pip install --python .venv/bin/python -r <skill-dir>/requirements-stealth.txt
.venv/bin/scrapling install
```

没有 `uv` 时回退：

```bash
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r <skill-dir>/requirements-stealth.txt
scrapling install
```

启用 CloakBrowser CDP 回退：

```bash
uv pip install --python .venv/bin/python -r <skill-dir>/requirements-cloak.txt
.venv/bin/python -m playwright install-deps chromium
.venv/bin/python -m cloakbrowser install
.venv/bin/python <skill-dir>/scripts/check_environment.py --require-cloak
```

`scrapling install` 的浏览器与系统依赖步骤见上方说明。CloakBrowser 使用自己的 Chromium，按该版本发行与校验机制验证，使用 `python -m cloakbrowser install` 预下载，不在首次业务抓取时才发现缺失。它的二进制下载与 Playwright 独立；精简 Linux 镜像仍可能需要 `playwright install-deps chromium` 提供系统库，这一步不下载 Playwright 浏览器。

无桌面服务器保持默认无头。需要有头排障时配置真实 X11/Wayland，或使用 Xvfb：

```bash
sudo apt-get update && sudo apt-get install -y xvfb
Xvfb :99 -screen 0 1920x1080x24 >$HOME/xvfb.log 2>&1 &
export DISPLAY=:99
.venv/bin/python <skill-dir>/scripts/resilient_fetch.py --headful --humanize ...
```

容器内的 `127.0.0.1` 是容器自身。代理运行在宿主机时，使用可路由的宿主地址；Linux Docker 可显式添加 `--add-host=host.docker.internal:host-gateway`。给 Chromium 足够的 `/dev/shm`，避免以 `--no-sandbox` 掩盖权限或容器配置问题。

## Windows

优先使用不加载用户配置的 PowerShell，避免 profile 中的编码、代理或启动脚本影响结果：

```powershell
powershell -NoProfile
py -3.12 -m venv .venv
uv pip install --python .\.venv\Scripts\python.exe -r <skill-dir>\requirements-stealth.txt
.\.venv\Scripts\scrapling.exe install
$env:SCRAPE_PROXY = "http://127.0.0.1:<port>"
.\.venv\Scripts\python.exe <skill-dir>\scripts\resilient_fetch.py --url "https://example.com" --out ".\page.html"
```

没有 `uv` 时执行 `.\.venv\Scripts\Activate.ps1`，再使用 `python -m pip install -r ...`。可选 CloakBrowser 使用 `requirements-cloak.txt` 和 `.\.venv\Scripts\python.exe -m cloakbrowser install`。只有 `--real-chrome` 才要求系统 Google Chrome；找不到时使用 `--executable-path "C:\<完整路径>\chrome.exe"`。保持源码、日志和 HTML 为 UTF-8。

WSL 内的 `127.0.0.1` 不应假定等同 Windows 宿主。先确认 Mihomo 的监听地址、防火墙和 WSL 到宿主的路由，再运行环境诊断。

## macOS

```bash
python3 -m venv .venv
uv pip install --python .venv/bin/python -r <skill-dir>/requirements-stealth.txt
.venv/bin/scrapling install
export SCRAPE_PROXY='http://127.0.0.1:<port>'
.venv/bin/python <skill-dir>/scripts/resilient_fetch.py --url 'https://example.com' --out './page.html'
```

Apple Silicon 与 Intel 必须使用匹配当前 Python 架构的浏览器和虚拟环境。CloakBrowser 二进制若被 Gatekeeper 隔离，先核对官方发行说明和签名，再按官方说明处理 quarantine；不要关闭整机安全机制。

## 版本与代理下载

本技能按层限定依赖范围：`curl_cffi` 可选（本机实测 0.15.0 可用），层 2 的 `scrapling[fetchers]` 限定 `>=0.4.11,<0.6`，层 3 的 `cloakbrowser` 限定 `>=0.4.10,<0.5`。`0.5` 的 `StealthyFetcher`、`solve_cloudflare` 与层 1/2 的 `headless` 参数已在本机实测通过；放开 `0.6+` 或 `cloakbrowser 0.5+` 前，重新核对 `StealthyFetcher`、`solve_cloudflare`、`cdp_url` 和 CloakBrowser `launch_async` 的签名，并用真实挑战站点重跑逐层验证。

开发或修改技能脚本时安装质量检查依赖：

```bash
uv pip install --python .venv/bin/python -r <skill-dir>/requirements-dev.txt
```

Windows 将解释器路径改为 `.\.venv\Scripts\python.exe`。没有 `uv` 时激活虚拟环境并使用 `python -m pip install -r ...`。

代理下载按共用安装参考配置；CloakBrowser 的下载器另查当前版本支持项并验证实际下载，不能假定 `PLAYWRIGHT_DOWNLOAD_HOST` 对它生效。

代理出口国家应与语言、时区和 WebRTC/DNS 行为一致。`cloakbrowser[geoip]` 会增加 GeoIP 依赖和首次数据库下载，只在确有需要时安装：

```bash
uv pip install --python .venv/bin/python 'cloakbrowser[geoip]>=0.4.10,<0.5'
```
