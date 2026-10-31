# Skill 依赖声明与检查

各 skill 的外部依赖写在 `skills/<name>/dependencies.json`，供仓库脚本直接扫描；脚本不读 `SKILL.md` 正文猜依赖。

## 何时声明

- skill 的核心流程或随 skill 分发的脚本，需要某个运行时、命令、浏览器或环境变量才能运行时。
- 纯提示、规范或方法类 skill 没有固定外部依赖，不建文件。
- 目标项目自身的框架、数据库、测试栈不在 skill 依赖里声明；用 `resource-inventory/scripts/inventory.py --project <目录>` 查。
- `package.json` 仍负责 Node 包安装；`dependencies.json` 只回答“这台机器有没有可运行的前提”，两者可以同时存在。
- `config/recommended-skills.txt` 决定链接脚本要安装哪些包/命令；本文件只声明运行前提，两者职责不同，可以重叠（如 htmlmini）。

## 文件格式

最小示例：

```json
{
  "schemaVersion": 1,
  "requirements": [
    {
      "id": "python",
      "kind": "runtime",
      "name": "python",
      "minVersion": "3.9",
      "required": true,
      "hint": "预检脚本需要 Python 3.9+"
    },
    {
      "id": "renderer",
      "required": true,
      "alternatives": [
        { "kind": "command", "name": "mmdc" },
        { "kind": "browser" }
      ],
      "hint": "mmdc 或本机浏览器；都不可用时联网走 kroki"
    }
  ]
}
```

字段：

| 字段 | 规则 |
|---|---|
| `schemaVersion` | 固定 `1` |
| `requirements` | 非空数组，每项一个依赖或一组替代 |
| `id` | 必填，kebab-case，同一文件内唯一 |
| `required` | 可选，默认 `true`；`false` 表示可选能力，缺失只警告 |
| `kind` | `runtime` / `command` / `browser` / `env` / `network` |
| `name` | `runtime`、`command`、`env` 必填；`browser`、`network` 禁止 |
| `minVersion` | 仅 `runtime`/`command`，点分数字；版本无法解析时按未知处理 |
| `url` | 仅 `network`，记录参考地址，不联网探测 |
| `alternatives` | 数组，至少一个；满足任一项即可，选项内不能再嵌套 |
| `platforms` | 可选，数组；只在这些平台检查（`windows`/`linux`/`macos`），其他平台显示 `SKIP`，不安装、不启动 |
| `hint` | 缺失时给出的下一步，不写自动安装命令 |

`kind` 的含义：

| kind | 判据 |
|---|---|
| `runtime` | PATH 上的运行时（node/python/pnpm 等），有 `minVersion` 时比较版本 |
| `command` | PATH 上可执行命令，只查存在性 |
| `browser` | 任意一个可用 Chrome/Edge/Chromium |
| `env` | 环境变量非空 |
| `network` | 需要联网的能力；默认只报 `unknown`，不发起请求 |

## 检查

```bash
python -X utf8 scripts/check-skill-deps.py
python -X utf8 scripts/check-skill-deps.py --json
python -X utf8 scripts/check-skill-deps.py --skill mermaid-render-fix,htmlmini
python -X utf8 scripts/check-skill-deps.py --strict
```

检查复用 `skills/resource-inventory/scripts/inventory.py --json` 的运行时与浏览器结果，不重复检测规则；不安装依赖、不联网。`network` 项与无法解析的版本会报 `unknown`，需要联网或换环境判断时按 `network-access` / `resource-inventory` 处理。

按用户偏好检查整套环境用 `--profile minimal|standard|full`，`--list-profiles` 列出套餐；套餐定义在 `config/dependency-profiles.json`，不替代各 skill 的 `dependencies.json`。

退出码：`0` 必需依赖满足；`1` 有缺失或版本不符（`--strict` 下 `unknown` 与可选缺失也算）；`2` 声明或探测本身失败。`SKIP` 表示 `platforms` 不包含当前平台，不计失败，也不启动对应工具。

## 部署基线

新机部署时先装一组，覆盖大多数带运行时的 skill。它们不是每个 skill 的硬门槛，但缺了会退化到在线回退、人工路径或能力不全；命令按本机包管理器调整，不自动执行。

git、ripgrep 与 fd 是基础命令行工具的推荐项（`required: false`）：缺失只显示 `OPTIONAL`、不阻断部署，部署脚本会在结束时检测三者是否可用并提示安装命令。Playwright 属 `standard` 套餐的推荐项，Scrapling 属 `full` 套餐的推荐项，缺失同样只警告。

rust/cargo、go 等通用运行时只在 `resource-inventory` 的运行时报里扫描，不进入依赖套餐，部署时既不推荐也不计为缺失。

按偏好选套餐：

| 套餐 | 内容 | 适合 |
|---|---|---|
| `minimal` | Python、Node、浏览器、git、ripgrep、fd（git/ripgrep/fd 为推荐项，缺失只警告） | 想尽量少装，接受 npx/dlx/kroki 回退 |
| `standard`（默认） | `minimal` + pnpm、mmdc（全局）、PowerShell 7（仅 Windows）、Playwright（推荐项） | 日常使用；mmdc 直接可用，减少回退判断 |
| `full` | `standard` + uv、jq、Scrapling（推荐项） | 想一次装齐常用全局 CLI 与抓取能力 |

```bash
python -X utf8 scripts/check-skill-deps.py --profile standard
python -X utf8 scripts/check-skill-deps.py --profile full --json
python -X utf8 scripts/check-skill-deps.py --list-profiles
```

偏好可设环境变量 `SKILLS_DEPS_PROFILE=full`（只留本机，不写进仓库）；未设置且不带 `--profile` 时仍按各 skill 的 `dependencies.json` 检查。

工具明细：

| 套餐 | 依赖 | 主要覆盖 | Windows | Linux / macOS |
|---|---|---|---|---|
| minimal | Python 3.10+ | resource-inventory、resilient-browser-fetch、mermaid-render-fix、network-access、opencode-provider-config | `winget install Python.Python.3.12` | `brew install python@3.12` / `sudo apt install python3` |
| minimal | Node.js 18+（含 npm/npx） | htmlmini | `winget install OpenJS.NodeJS.LTS` | `brew install node` / `sudo apt install nodejs` |
| minimal | Chrome / Edge / Chromium | browser-automation、mermaid-render-fix、frontend-qa | `winget install Google.Chrome`（或使用系统 Edge） | `brew install --cask google-chrome` / `sudo apt install chromium` |
| minimal | git（推荐） | skill-authoring-sync、仓库同步与变更检查 | `winget install Git.Git` | `brew install git` / `sudo apt install git` |
| minimal | ripgrep（推荐，命令 `rg`） | 代码与文档全文检索、agent 的 grep 检索 | `winget install BurntSushi.ripgrep.MSVC` | `brew install ripgrep` / `sudo apt install ripgrep` |
| minimal | fd（推荐，Debian/Ubuntu 命令为 `fdfind`） | 跨平台高性能文件/目录搜索，按名称批量定位文件 | `winget install sharkdp.fd` | `brew install fd` / `sudo apt install fd-find` |
| standard | pnpm（项目依赖管理器） | htmlmini 项目安装、mermaid-render-fix 的单次拉起 | `corepack enable` 后 `corepack prepare pnpm@latest --activate` | 同左 |
| standard | mmdc（全局） | mermaid-render-fix 直接渲染，省去首次下载与回退判断 | `$env:PUPPETEER_SKIP_DOWNLOAD='true'; npm i -g @mermaid-js/mermaid-cli` | `PUPPETEER_SKIP_DOWNLOAD=true npm i -g @mermaid-js/mermaid-cli` |
| standard | PowerShell 7（仅 Windows） | powershell-pitfalls、Windows 脚本示例 | `winget install Microsoft.PowerShell` | 不适用；非 Windows 不安装也不启动 pwsh |
| standard | Playwright（推荐，命令 `playwright`） | browser-automation、web-app-testing、ai-verified-delivery 的自动化、截图与 E2E | `python -m pip install playwright; python -m playwright install chromium` | `python3 -m pip install playwright && python3 -m playwright install chromium` |
| full | uv | resource-inventory、resilient-browser-fetch 的 Python 环境与引擎 | `winget install astral-sh.uv` | `brew install uv` / `curl -LsSf https://astral.sh/uv/install.sh -o uv-install.sh && sh uv-install.sh` |
| full | jq | opencode-provider-config 的手工 JSON 过滤 | `winget install jqlang.jq` | `brew install jq` / `sudo apt install jq` |
| full | Scrapling（推荐，命令 `scrapling`） | resilient-browser-fetch 的层 2 抓取与挑战页求解 | `uv tool install "scrapling[fetchers]"` 后用 `scrapling install` 装浏览器 | 同左（`uv tool install 'scrapling[fetchers]'`） |

安装后验证：

```bash
python -X utf8 scripts/check-skill-deps.py      # Windows
python3 -X utf8 scripts/check-skill-deps.py     # Linux / macOS
```

期望全部 `OK`；`OPTIONAL` 只表示可选能力未装，不影响必需项。准备完整环境时再用 `--strict`。

安装影响与替代：

- 这些命令会联网下载并写入用户或系统目录，可能修改 PATH；Python/Node 安装包通常几十 MB，浏览器更大。先说明再执行，不静默安装。
- git、ripgrep、fd 属推荐项：缺失不阻断部署；git 用于跨机器同步与变更检查，rg/fd 缺失时可用 grep、Select-String 与 find、Get-ChildItem 替代。
- Scrapling 属 `full` 套餐的推荐项：缺失只警告；首次使用还要 `scrapling install` 下载浏览器，体积与耗时较大，按需装。`scrapling[fetchers]` 会带入 playwright 的 Python 包；用 `uv tool install` 时只在工具环境内，独立的 `playwright` CLI 与浏览器仍需按 `standard` 的 Playwright 项安装。
- Playwright 属 `standard` 套餐的推荐项：缺失只警告；`playwright install chromium` 会下载浏览器，已有系统 Chrome/Edge 时也可先复用。
- pnpm 只用于项目依赖；全局命令（如 `mmdc`）按治理用 `npm i -g`，不推荐 `pnpm add -g`（全局 bin 常不在 PATH）。
- `standard` 与 `full` 默认全局安装 mmdc；`minimal` 不装，仍可用 `npx`/`pnpm dlx` 单次拉起。
- PowerShell 7 只在 Windows 套餐中检查和推荐；非 Windows 不启动 `pwsh`，相关依赖项显示 `SKIP`。
- 不装或装不上时的降级：Python 缺失先换 `py`/`python3`，Mermaid 渲染可直接走 kroki；Node 缺失时 htmlmini 仍可按 `web_fetch` 分流；浏览器缺失时按 browser-automation 的人工截图或 Playwright 缓存；pnpm 缺失时可用 Corepack 在项目内运行。

按需安装、不放进基线的项：

- Playwright：`standard` 已作为推荐项列出；只做静态抓取、或项目内已有 playwright 时可跳过，优先复用系统 Chrome/Edge。
- Scrapling：`full` 已作为推荐项列出；只做静态正文抓取或已装进项目虚拟环境时无需全局安装，按 `resilient-browser-fetch` 的分层说明使用。
- `mmdc`：已含在 `standard`/`full`；选 `minimal` 或临时任务时用 `pnpm dlx`/`npx` 单次拉起。
- `uv`/conda：`full` 含 uv；需要独立 Python 环境或引擎层时按 `resilient-browser-fetch` 的分层说明使用。
- 国内下载受阻时按 `network-access` 选镜像或代理，不把某次可达的源写成永久默认值。

## 维护

- 新增或修改依赖时同步更新 `dependencies.json` 与 `hint`，不要只改正文；正文与声明各写一次时，以 `dependencies.json` 为机器检查口径。
- `scripts/check-skills.py` 会校验 JSON 结构与字段；格式错误计入错误，含 `package.json` 却缺声明时给出提醒。
- 检查失败不等于 skill 不可用：可选依赖缺失只警告；准备完整环境时才用 `--strict`。
- 链接脚本只负责 `package.json` 依赖安装和命令 shim；不读取本文件，也不自动安装。
