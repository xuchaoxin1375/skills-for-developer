# 平台与依赖

## 包管理器与国内源

先运行 `uv --version`。Python 环境可由 Conda、`venv` 或 `uv venv` 创建；如果 `uv` 可用，优先使用 `uv pip` 并通过 `--python` 明确该环境的解释器。只有 `uv` 不可用时才在激活的同一环境中回退到 `python -m pip`。不要在一次安装流程中交替使用两个安装器，也不要因为使用 `uv pip` 就另建环境。保留用户现有的 `uv.toml`、环境变量和 pip 配置，不要无条件覆盖国内源。

国内网络下载失败且用户尚未配置镜像时，可在当前 shell 临时设置国内 PyPI 镜像与代理：

```bash
# uv 用户设置这一项
export UV_DEFAULT_INDEX='https://pypi.tuna.tsinghua.edu.cn/simple'
# pip 用户改为设置这一项
export PIP_INDEX_URL='https://pypi.tuna.tsinghua.edu.cn/simple'
export HTTPS_PROXY='http://127.0.0.1:7897'
```

PowerShell 使用：

```powershell
# uv 用户设置这一项
$env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
# pip 用户改为设置这一项
$env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
```

只设置实际使用的安装器对应变量。镜像用于 Python 包索引，`HTTPS_PROXY` 同时可帮助浏览器二进制下载；镜像不可用或包版本滞后时临时回到官方 PyPI。

## Conda 环境配合 uv

Conda 负责 Python 版本、环境目录和非 Python 运行库，`uv pip` 只负责向选定解释器安装 Python 包。环境名称可以是 `scrapling`、`main`、`base` 或用户已有名称，不要硬编码。

Linux/macOS：

```bash
conda create -n scrapling python=3.12 -y  # 已有环境时省略
PYTHON="$(conda run -n scrapling python -c 'import sys; print(sys.executable)')"
uv pip install --python "$PYTHON" -r <skill-dir>/requirements.txt
conda run -n scrapling scrapling install
conda run -n scrapling python <skill-dir>/scripts/check_environment.py
```

Windows PowerShell：

```powershell
conda create -n scrapling python=3.12 -y  # 已有环境时省略
$Python = (conda run -n scrapling python -c "import sys; print(sys.executable)" | Select-Object -Last 1).Trim()
uv pip install --python $Python -r <skill-dir>\requirements.txt
conda run -n scrapling scrapling install
conda run -n scrapling python <skill-dir>\scripts\check_environment.py
```

运行脚本时使用 `conda run -n <env> python ...` 或先 `conda activate <env>`。不要用环境 A 的 Python 加载包，却因为 PATH 顺序调用环境 B 的 `scrapling` 命令；诊断脚本会分别报告当前解释器和当前环境旁的 CLI。

## Linux（优先）

使用 CPython 3.10+ 和独立虚拟环境。先安装 Scrapling；只有默认引擎失败或明确需要 CloakBrowser 指纹底座时才安装可选依赖。

```bash
python3 -m venv .venv
uv pip install --python .venv/bin/python -r <skill-dir>/requirements.txt
.venv/bin/scrapling install
```

没有 `uv` 时回退：

```bash
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r <skill-dir>/requirements.txt
scrapling install
```

启用 CloakBrowser CDP 回退：

```bash
uv pip install --python .venv/bin/python -r <skill-dir>/requirements-cloak.txt
.venv/bin/python -m playwright install-deps chromium
.venv/bin/python -m cloakbrowser install
.venv/bin/python <skill-dir>/scripts/check_environment.py --require-cloak
```

`scrapling install` 安装 Scrapling fetcher 所需浏览器；CloakBrowser 使用自己的已签名 Chromium，`python -m cloakbrowser install` 预下载它，运行时不应临时下载。CloakBrowser 不需要 `playwright install chromium`，但精简 Linux 镜像需要 `playwright install-deps chromium` 提供系统库。

无桌面服务器保持默认无头。需要有头排障时配置真实 X11/Wayland，或使用 Xvfb：

```bash
sudo apt-get update && sudo apt-get install -y xvfb
Xvfb :99 -screen 0 1920x1080x24 >/tmp/xvfb.log 2>&1 &
export DISPLAY=:99
.venv/bin/python <skill-dir>/scripts/resilient_fetch.py --headful --humanize ...
```

容器内的 `127.0.0.1` 是容器自身。代理运行在宿主机时，使用可路由的宿主地址；Linux Docker 可显式添加 `--add-host=host.docker.internal:host-gateway`。给 Chromium 足够的 `/dev/shm`，避免以 `--no-sandbox` 掩盖权限或容器配置问题。

## Windows

优先使用不加载用户配置的 PowerShell，避免 profile 中的编码、代理或启动脚本影响结果：

```powershell
powershell -NoProfile
py -3.12 -m venv .venv
uv pip install --python .\.venv\Scripts\python.exe -r <skill-dir>\requirements.txt
.\.venv\Scripts\scrapling.exe install
$env:SCRAPE_PROXY = "http://127.0.0.1:7897"
.\.venv\Scripts\python.exe <skill-dir>\scripts\resilient_fetch.py --url "https://example.com" --out ".\page.html"
```

没有 `uv` 时执行 `.\.venv\Scripts\Activate.ps1`，再使用 `python -m pip install -r ...`。可选 CloakBrowser 使用 `requirements-cloak.txt` 和 `.\.venv\Scripts\python.exe -m cloakbrowser install`。只有 `--real-chrome` 才要求系统 Google Chrome；找不到时使用 `--executable-path "C:\完整路径\chrome.exe"`。保持源码、日志和 HTML 为 UTF-8。

WSL 内的 `127.0.0.1` 不应假定等同 Windows 宿主。先确认 Mihomo 的监听地址、防火墙和 WSL 到宿主的路由，再运行环境诊断。

## macOS

```bash
python3 -m venv .venv
uv pip install --python .venv/bin/python -r <skill-dir>/requirements.txt
.venv/bin/scrapling install
export SCRAPE_PROXY='http://127.0.0.1:7897'
.venv/bin/python <skill-dir>/scripts/resilient_fetch.py --url 'https://example.com' --out './page.html'
```

Apple Silicon 与 Intel 必须使用匹配当前 Python 架构的浏览器和虚拟环境。CloakBrowser 二进制若被 Gatekeeper 隔离，先核对官方发行说明和签名，再按官方说明处理 quarantine；不要关闭整机安全机制。

## 版本与代理下载

本技能的 requirements 文件限定到已验证的 `0.4.x` API 范围。升级到 `0.5+` 前重新核对 `StealthyFetcher`、`solve_cloudflare`、`cdp_url` 和 CloakBrowser `launch_async` 的签名并重跑真实站点验证。

开发或修改技能脚本时安装质量检查依赖：

```bash
uv pip install --python .venv/bin/python -r <skill-dir>/requirements-dev.txt
```

Windows 将解释器路径改为 `.\.venv\Scripts\python.exe`。没有 `uv` 时激活虚拟环境并使用 `python -m pip install -r ...`。

国内网络下载依赖时，浏览器安装命令也应继承 `HTTPS_PROXY`：

```bash
export HTTPS_PROXY='http://127.0.0.1:7897'
uv pip install --python .venv/bin/python -r <skill-dir>/requirements-cloak.txt
.venv/bin/python -m cloakbrowser install
```

代理出口国家应与语言、时区和 WebRTC/DNS 行为一致。`cloakbrowser[geoip]` 会增加 GeoIP 依赖和首次数据库下载，只在确有需要时安装：

```bash
uv pip install --python .venv/bin/python 'cloakbrowser[geoip]>=0.4.10,<0.5'
```
