# 安装与 Agent 集成

本 Skill 的安装分为两部分：

1. 将 Skill 目录放入 Agent 能发现的 skills 目录。
2. 在实际执行 Python 的 Conda/venv 环境中安装 Scrapling 和浏览器依赖。

Agent 只负责读取 `SKILL.md`，不会替代 Python 包或浏览器安装。建议优先使用目录链接，便于更新本地 Skill；不支持链接时再复制目录。不要把 `.venv`、`__pycache__`、`.pytest_cache`、profile 或真实抓取输出复制到 Agent 的 skills 目录。

## 目录变量

Linux/macOS：

```bash
export SKILL_DIR="$HOME/.codex/skills/resilient-browser-fetch"
```

Windows PowerShell：

```powershell
$SkillDir = Join-Path $HOME ".codex\skills\resilient-browser-fetch"
```

如果当前 Skill 位于其他工作区，将 `SKILL_DIR` 或 `$SkillDir` 改为实际目录。以下命令假定源目录已经存在。

## Codex CLI

Codex 从 `$CODEX_HOME/skills` 发现 Skill；未设置 `CODEX_HOME` 时通常使用 `~/.codex/skills`。本技能已经位于当前 Codex skills 目录时无需复制，启动新会话后即可使用：

```bash
ls "$HOME/.codex/skills/resilient-browser-fetch/SKILL.md"
```

若源目录在其他位置，Linux/macOS 可以创建目录链接：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -sfn "$SKILL_DIR" "${CODEX_HOME:-$HOME/.codex}/skills/resilient-browser-fetch"
```

Windows PowerShell 使用目录 Junction：

```powershell
$CodexSkills = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME "skills"
} else {
    Join-Path $HOME ".codex\skills"
}
New-Item -ItemType Directory -Force -Path $CodexSkills | Out-Null
New-Item -ItemType Junction `
  -Path (Join-Path $CodexSkills "resilient-browser-fetch") `
  -Target $SkillDir
```

已有同名目录时，先确认它确实指向本 Skill；不要盲目覆盖用户目录。

参考：[OpenAI Codex Skills](https://developers.openai.com/codex/skills/)。

## Claude Code

Claude Code 支持个人、项目和插件三个层级。个人安装对所有项目生效，项目安装应提交到项目版本库：

Linux/macOS：

```bash
mkdir -p "$HOME/.claude/skills"
ln -sfn "$SKILL_DIR" "$HOME/.claude/skills/resilient-browser-fetch"
```

Windows PowerShell：

```powershell
$ClaudeSkills = Join-Path $HOME ".claude\skills"
New-Item -ItemType Directory -Force -Path $ClaudeSkills | Out-Null
New-Item -ItemType Junction `
  -Path (Join-Path $ClaudeSkills "resilient-browser-fetch") `
  -Target $SkillDir
```

项目级安装则把目录链接或复制目录放在：

```text
<project>/.claude/skills/resilient-browser-fetch/SKILL.md
```

启动 Claude Code 后使用 `/skills` 检查发现结果。插件安装应由插件自己的 `plugin.json` 管理，不要把插件目录和个人 Skill 目录混用。

参考：[Claude Code Skills](https://docs.anthropic.com/en/docs/claude-code/skills)。

## Cursor

Cursor 支持全局和项目 Skill：

```text
全局：~/.cursor/skills/resilient-browser-fetch/SKILL.md
项目：<project>/.cursor/skills/resilient-browser-fetch/SKILL.md
兼容目录：~/.agents/skills/ 或 <project>/.agents/skills/
```

全局目录可以使用同样的符号链接或 Junction 命令，将目标改成 `$HOME/.cursor/skills`。项目级 Skill 适合随代码库版本控制；全局 Skill 适合个人工具和跨项目复用。安装后在 Cursor 的 Customize → Skills 中检查是否已发现。

参考：[Cursor Agent Skills](https://cursor.com/docs/skills)。

## Gemini CLI

Gemini CLI 支持用户级和 workspace 级目录，也提供官方管理命令。推荐使用 `link`，这样源目录更新后无需重复复制：

```bash
gemini skills link "$SKILL_DIR" --scope user
gemini skills list --all
```

项目级安装：

```bash
gemini skills link "$SKILL_DIR" --scope workspace
```

如果使用已发布的 Git 仓库，也可以：

```bash
gemini skills install https://github.com/<owner>/<repo>.git --consent
```

Gemini 的默认发现位置是：

```text
用户级：~/.gemini/skills/ 或 ~/.agents/skills/
项目级：.gemini/skills/ 或 .agents/skills/
```

参考：[Gemini CLI Agent Skills](https://geminicli.com/docs/cli/skills/)。

## 其他兼容 Agent

许多遵循 Agent Skills 开放目录约定的工具会读取以下位置之一：

```text
项目：.agents/skills/resilient-browser-fetch/SKILL.md
用户：~/.agents/skills/resilient-browser-fetch/SKILL.md
```

具体工具如果同时提供官方 `skills link`、插件市场或配置项，应优先使用官方入口，不要假定所有 Agent 都支持同一目录、同一命令或同一 frontmatter 扩展。

## 安装 Python 与浏览器依赖

依赖按引擎分层，只装当前任务需要的层；`auto` 会在缺件时自动跳过对应引擎。

| 层 | 用途 | 安装 |
| --- | --- | --- |
| 0 | 静态 HTTP（默认可用） | 无需安装；**推荐**装 `curl_cffi`（socks 代理，以及 `--impersonate` 的 TLS/HTTP2 伪装） |
| 1 | 无头/有头渲染 | `playwright`（或 `patchright`）+ `playwright install chromium` |
| 1/备用 | 直接 CDP（系统 Chrome） | `requirements-nodriver.txt`；需系统 Chrome；无需 `playwright install`；AGPL-3.0 |
| 1/备用 | 晚接入（先让挑战跑完再接入） | 复用层 1 的 `playwright`/`patchright`（只需它的 CDP 连接能力）+ 系统 Chrome/Chromium/Edge；**不需要** `playwright install chromium` |
| 2 | 挑战求解 | `requirements-stealth.txt` + `scrapling install` |
| 3 | 指纹底座 | `requirements-cloak.txt` + `python -m cloakbrowser install` |

层号表示能力档位，不是隐蔽性排名。层 2 的 `scrapling[fetchers]` 会安装 Patchright；层 1 默认也优先 Patchright，所以装层 2 后层 1 的实际驱动可能变化。要固定或对照，使用 `--playwright-api playwright|patchright`（只影响层 1）。层 2/3 的控制面仍是 Patchright，层 3 只替换指纹底座；详细矩阵见 [检测层与引擎选择](detection-layers.md)。

### 浏览器 revision 与 install 命令

`playwright install`、`patchright install`、`scrapling install` 不是同一层的命令：

- `playwright install` 与 `patchright install` 各自用自己 driver 的 `browsers.json` 决定 revision，装进同一个 cache（Windows 默认 `%LOCALAPPDATA%\ms-playwright`）；不同 revision 并存，不互相覆盖。
- `scrapling install` 只是对当前解释器的 `playwright install chromium`、`playwright install-deps chromium` 的封装，并写安装标记；它不会调用 `patchright install`。
- Scrapling 0.5 的层 2 控制面是 Patchright；使用 Patchright 的路径（层 2/3，或层 1 显式 `--playwright-api patchright`）需要 Patchright 的 revision。如果 Playwright 与 Patchright 的 revision 不一致，安装命令成功但启动会报 `Executable doesn't exist ... chromium-xxxx`。

因此装层 2 时，除 `scrapling install` 外再补一次目标环境的 Patchright 安装，并对比两边的 revision：

```bash
<目标环境解释器> -m patchright install chromium
<目标环境解释器> -m playwright install --dry-run chromium
<目标环境解释器> -m patchright install --dry-run chromium
```

对比输出的 `Install location` 是否为同一个 `chromium-xxxx`；不一致就补跑 Patchright 的安装。两边都只装 `chromium`，不带参数会额外拉 Firefox/WebKit，而 Patchright 只支持 Chromium 系。`scrapling install --force` 只绕过安装标记，不会把 `--force` 传给 Playwright；要修复已存在的浏览器，用 `-m playwright install --force chromium` 或 `-m patchright install --force chromium`。不要设 `PLAYWRIGHT_BROWSERS_PATH=0`（两个包会各装各的）；也不要把 `playwright uninstall --all` 当作只清理一个包，共享 revision 会被一起删。

层 0 的 `curl_cffi` 是推荐项而非必需：不装也能用 stdlib 路径抓取，只是不能走 socks 代理，也没有 `--impersonate`。装了以后用 `--impersonate chrome124`（或 `chrome136`、`safari184` 等具体目标）就能以浏览器同族的 TLS/HTTP2 指纹出网，可过部分站点的客户端指纹检查；它不解 JS 挑战，挑战仍要层 2。目标写具体版本而不是 `chrome` 这类滚动别名（别名指向的版本随 curl_cffi 升级漂移，不便复现与对照），可用 `check_environment.py` 或 `curl_cffi.requests.BrowserType` 查询。经代理的 TLS 握手偶有瞬时失败，脚本按 `retries` 重试。`requests`/`httpx` 不改变 TLS 指纹，本 Skill 不作为依赖。

复验这层时用 JA4 而不是 JA3：对 `tls.peet.ws/api/all` 抓一次，`--engine static` 与 `--impersonate chrome124` 的 `ja4` 分别落在 h1 与 h2 两个不同族（本机实测 `t13d1713h1_ab0a1bf427ad_89ab6efea773` 与 `t13d1516h2_8daaf6152771_02713d6af862`，后者与真 Chrome 的 HTTP/2 段一致），而 `ja3_hash` 逐次连接都会变、不适合做对照。

先选择实际运行脚本的环境，并按 [平台与依赖](platforms.md) 准备包源和浏览器下载路线；国内浏览器安装前先设置下载代理，不能用后续抓取的 `--proxy` 替代。`scrapling install` 还会执行 Playwright 系统依赖步骤，影响因平台而异，执行前核对该版本行为与权限。Conda 环境示例（Windows PowerShell）：

```powershell
$Python = (conda run -n scrapling python -c "import sys; print(sys.executable)" | Select-Object -Last 1).Trim()
# 层 1（按需）
uv pip install --python $Python playwright
conda run -n scrapling --no-capture-output playwright install chromium
# 层 2（挑战求解，按需）
uv pip install --python $Python -r (Join-Path $SkillDir "requirements-stealth.txt")
conda run -n scrapling --no-capture-output scrapling install
conda run -n scrapling --no-capture-output python -X utf8 (Join-Path $SkillDir "scripts\check_environment.py") --proxy "http://127.0.0.1:<port>"
```

> `conda run` 必须带 `--no-capture-output`：不带时它会先捕获子进程输出、再用自己的 stdout 重印，在 GBK 代码页的 Windows 控制台上，本 Skill 的中文输出会直接触发 `UnicodeEncodeError: 'gbk' codec can't encode character ...`（实测）。`--no-capture-output` 让子进程直接写终端，配合 `-X utf8` 才是可靠组合。

Linux/macOS：

```bash
PYTHON="$(conda run -n scrapling python -c 'import sys; print(sys.executable)')"
uv pip install --python "$PYTHON" -r "$SKILL_DIR/requirements-stealth.txt"   # 层 2，按需
conda run -n scrapling --no-capture-output scrapling install
conda run -n scrapling --no-capture-output python -X utf8 "$SKILL_DIR/scripts/check_environment.py" --proxy 'http://127.0.0.1:<port>'
```

没有 Conda 时，将 `<目标环境解释器>` 替换为 `.venv/bin/python` 或 Windows 的 `.venv\Scripts\python.exe`。没有 `uv` 时，在同一环境中使用 `python -m pip install -r requirements-stealth.txt`。

### 用哪个解释器运行：先扫描，不要假设 PATH 上的 `python` 是全的

`python scripts/resilient_fetch.py` 与 `python scripts/check_environment.py` 都用**运行它的那个解释器**去找依赖层，全局默认环境常常只有层 0/1。先扫描本机候选环境：

```bash
python <skill-dir>/scripts/check_environment.py --list-envs                 # 只列，不判定
python <skill-dir>/scripts/check_environment.py --list-envs --require-stealth  # 缺层则退出码 1
```

输出会列出每个候选解释器的管理方式（`conda:<env>`、`conda:base`、`venv`、`venv(uv)`、`system`）、Python 版本、**可运行的层**、已装包，并按能力排序给出建议命令。安装了 nodriver 时引擎行会多出 `nodriver`；它仍只在 `--headful` 的 `auto` 中启用。例如：

```text
[OK] conda:scrapling    %USERPROFILE%\.conda\envs\scrapling\python.exe  (来源: conda-envs)
     Python 3.13.13  层 0/1/2/3  引擎: static, playwright, scrapling, cloak-cdp
[WARN] system           <PATH 上的解释器>  (来源: current)
     Python 3.13.15  层 0/1  引擎: static, playwright
     缺: scrapling
建议解释器(满足 scrapling): %USERPROFILE%\.conda\envs\scrapling\python.exe
   直接调用: & "%USERPROFILE%\.conda\envs\scrapling\python.exe" -X utf8 <scripts>/resilient_fetch.py --url <URL>
   conda:    conda run -n scrapling --no-capture-output python -X utf8 <scripts>/resilient_fetch.py --url <URL>
```

候选来源包括当前解释器、`VIRTUAL_ENV`/`CONDA_PREFIX`、PATH 上的 `python`/`python3`/`python3.1x`、Windows `py -0p` 启动器、conda 环境（`~/.conda/environments.txt` 与常见根目录及其 `envs/`）、venv/virtualenv/uv 常见目录；按解析后的真实路径去重，最多探测 12 个，每个用子进程 `-X utf8` 探测，不 activate、不改环境。`--list-envs` 可与 `--json` 组合，便于脚本解析。

只有需要 CloakBrowser 底座（层 3）时才安装可选依赖：

```bash
uv pip install --python <目标环境解释器> -r "$SKILL_DIR/requirements-cloak.txt"
<目标环境解释器> -m cloakbrowser install
```

只有需要直接 CDP 备用（nodriver）时才安装；它复用系统 Chrome，不下载浏览器：

```bash
uv pip install --python <目标环境解释器> -r "$SKILL_DIR/requirements-nodriver.txt"
<目标环境解释器> -X utf8 "$SKILL_DIR/scripts/check_environment.py" --require-nodriver
```

- 需要系统 Chrome/Chromium；`check_environment.py` 的 `system-chrome` 与 `nodriver-chrome` 会检查。
- 显式路线用 `--engine nodriver`；加入 `auto` 必须同时加 `--headful`，且它排在层 3 之后。无头 nodriver 通常明显更弱，不建议用于反检测。
- 许可为 AGPL-3.0；商用或 SaaS 使用前先评估，不要把它当作无条件默认依赖。
- 不支持挑战求解，也不伪造指纹；目标卡 Patchright 控制面时才作为备用，不能替代层 2 的求解能力。

晚接入（`chrome-late`）不需要额外安装包：它复用层 1 的 `playwright`/`patchright` 做 CDP 连接，自己拉起系统浏览器。因此只要满足两条：

- 系统装有 Chrome/Chromium/Edge（`check_environment.py` 的 `system-chrome` 会检查）；用 `--executable-path` 可显式指定路径。
- 有可用的显示环境：Windows/macOS 直接可用，Linux 需 `DISPLAY` 或 Xvfb。

用法是显式 `--engine chrome-late`（不进 `auto`），并用 `--settle-ms` 调整"最小静默窗口"、`--render-timeout-ms` 调整"接入后等渲染稳定的上限"。引擎自带的浏览器由它负责回收。

需要在 CI 或安装校验中把某层标为必需时，用 `--require-playwright`、`--require-stealth`、`--require-cloak`、`--require-nodriver`；默认只有 Python 版本是必需的，缺层只报 WARN，退出码仍为 0。

开发或修改本 Skill 时，额外安装 `requirements-dev.txt`，并运行 Ruff、Pyright 和 pytest；仅使用 Skill 时不需要开发依赖。

## 验证与更新

安装后验证各层：

1. Agent 能发现 `SKILL.md`。
2. 目标 Python 环境能运行 `check_environment.py` 完成只读诊断，并确认输出末尾的"可用引擎"行符合预期层级；该脚本不证明浏览器已启动。装 nodriver 时再确认 `nodriver` 与 `nodriver-chrome` 两项。
3. 实际抓一个受控页面并按层断言：层 0 用静态页、层 1 用客户端渲染页、层 2/3 用挑战页、nodriver 用有头模式，再核对 `.meta.json` 的 `engine`、`notes` 与 `.attempts.json` 的 `kind`。

更新源码时，链接安装会自动看到变化；复制安装需要重新复制 Skill 目录。更新依赖或浏览器版本后，重新运行环境诊断和最小 smoke test。不要把真实 profile 当作源码同步目录，也不要在多个浏览器进程之间共享同一个持久 profile。
