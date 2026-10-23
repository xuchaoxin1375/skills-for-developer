---
name: opencode-provider-config
description: 把第三方 AI API（中转站/NewAPI/one-api 渠道/自定义 OpenAI 兼容网关）接入 OpenCode 的完整流程：获取模型列表、网络与 DNS 诊断、联网查模型参数、写 providers 配置、设置服务环境变量与代理、端到端验证。凡是用户给出 API 地址+密钥要求"接入 opencode"、"配置自定义供应商/模型"、"添加中转站"、"第三方模型接入"、"配置 provider"，或需要在 OpenCode 中新增非内置模型、调整已有或内置模型的上下文（limit）、查 /v1/models 列表、用 models.dev 查模型上下文参数时使用本 skill。
---

# OpenCode 自定义供应商模型接入流程

## 适用范围

- 第三方中转站（NewAPI / one-api / uni-api 等 OpenAI 兼容网关）接入 OpenCode V2。
- 已内置 catalog 的供应商改用自定义 baseURL 时，直接覆盖 `settings.baseURL` 即可，不必新建 provider。
- 不适用于 OAuth 型供应商（Copilot 等），走 `/connect` 交互流程。

## 工作流程

### 1. 获取并筛选模型列表

先用 `curl.exe`（PowerShell 中 `curl` 是 `Invoke-WebRequest` 别名，必须写 `curl.exe`）请求网关：

```bash
curl.exe -s -m 30 <baseURL>/v1/models -H "Authorization: Bearer <KEY>"
```

OpenCode 官方 provider 例外：Console 与 Go 的模型目录免 key 即可查（`/inference/v1/models` 含 `*-free`、`/inference/go/v1/models`，以及 models.dev 的 `opencode` / `opencode-go` 条目——后者还带 cost/limit）；但**你的可用范围**要 key（`GET /console/api/v2/config`，免 key 返回 401）。公开目录 ≠ 可用范围（实测公开 85/37 对工作区 84/29），可用性判定以工作区配置或 `opencode models` 为准。

筛选规则：

- 对话模型才配进 OpenCode；嵌入（`*-embed*`）、重写、翻译、安全审查（`*content-safety*`）类模型不适合做 agent，直接跳过。
- 网关常同时暴露多种协议（`supported_endpoint_types` 含 `anthropic`/`openai`），OpenCode 一律走 OpenAI 协议即可，只取模型 `id`。
- 同一网关域名常并存多把 key，各自对应不同渠道分组、模型目录互不相交：已有该域名的 provider 时，先拿新旧 key 各拉一次 `/v1/models` 比对，再决定新增还是覆盖。新 key 暴露的是既有 provider 里没有的模型组，就新建 provider 并配独立 `env` 变量名（与既有 key 错开），不覆盖既有 key——覆盖会让旧 provider 静默丢掉一半模型。例：同域名旧 key 只暴露通用对话组，新 key 另开专用系列，两组并存。

### 2. 网络诊断（直连超时时按序排查）

1. 先确认是全局超时还是该域名：测一个国内可达域名（如 `www.baidu.com`）对比。测"直连"必须加 `curl.exe --noproxy "*"`，否则 shell 的 `http_proxy`/`https_proxy` 会让假直连通过——直连"成功"三次，加 `--noproxy "*"` 重测才发现实际一直超时。
2. 查系统代理线索：注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings` 的 `ProxyServer`（即使 `ProxyEnable=0`，其值也常是最近一次使用的代理端口），再 `netstat -ano -p tcp | findstr <端口>` 确认代理进程仍在监听。
3. 用 DoH 查真实 IP（防 DNS 污染）：`https://cloudflare-dns.com/dns-query?name=<域名>&type=A`（header `accept: application/dns-json`）或 `https://dns.google/resolve?name=<域名>`。污染特征：不同 DNS 服务器返回 Dropbox/Twitter 等无关 IP。
4. 验证代理可用：`curl.exe -x http://127.0.0.1:<port> https://<域名>/v1/models -H "Authorization: Bearer <KEY>"`，返回 JSON 即通。
5. 直连与代理都失败时才考虑 `--resolve` 强制 IP，但被阻断时会握手重置，不必强求。

**结论：只要本地直连不可达，就必须把代理配置到 OpenCode 服务端**（见第 4 步），只在当前 shell 临时 export 是不够的；反向同样成立——直连可达的设备不设代理变量。

### 3. 联网查模型参数

数据源按序取用，一个源查全即停；字段冲突时以供应商官方文档为最终权威。所有大 JSON 一律先落盘、按模型名过滤出目标条目再读，不把整段响应拖进上下文。

**首选**：本 skill 自带零依赖脚本 `scripts/model_info.py`（纯标准库，多源自动回退，jsdelivr 超时自动落回 raw）：Windows `python <本skill目录>/scripts/model_info.py <模型名>`（部分机器是 `py`），*nix `python3 <本skill目录>/scripts/model_info.py <模型名>`；`--source all` 跨源合并，`--json` 输出供程序读取，无命中退出码 1、全源失败退出码 2。脚本不可用或需自定义时再手工取（下表与示例）。

一次要查多个模型时先 `--source openrouter`：全源模式会逐个卡在 litellm/jsdelivr 超时上，几个模型就能跑成分钟级且可能整体超时；openrouter 通常一个文件覆盖多数主流模型，命中即停，只对没命中的模型再补 `--source all` 或官方文档。

| 数据源（按序） | 关键字段 | 可达性与取法 |
| --- | --- | --- |
| `https://openrouter.ai/api/v1/models` | `data[]`：`context_length`、`architecture.input_modalities`/`output_modalities`、`top_provider.max_completion_tokens`、`supported_parameters`（含 `tools`/`reasoning`）、定价 | 无需鉴权，单文件约 0.8MB，通常直连最快，以实测为准 |
| `https://models.dev/api.json` | `prov.models[id]`：`limit.context`/`limit.output`、`modalities`、`tool_call`、`reasoning` | 文件数 MB 常偏慢；慢或 403 时改走代理 |
| LiteLLM JSON `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json` | 键=模型名（常带 `provider/` 前缀）：`max_input_tokens`、`max_output_tokens`、`mode`、`supports_function_calling`/`supports_vision`/`supports_reasoning`、定价 | raw 直连常超时/截断：走代理，或 jsdelivr 镜像 `https://cdn.jsdelivr.net/gh/BerriAI/litellm@main/model_prices_and_context_window.json`；新模型可能滞后 |
| 供应商官方文档/发布博客 | 权威兜底；国产供应商站点国内直连可达 | 搜索或按 `network-access` 抓取 |

- 下载统一 `curl -A "Mozilla/5.0"`（脚本 HTTP 库常被 403）；解析前校验 JSON 完整性，截断文件解析报 Unterminated string，重取即可。
- 平台解析差异：Windows PowerShell 必须写 `curl.exe`（`curl` 是 `Invoke-WebRequest` 别名），用 `ConvertFrom-Json` 过滤（`jq`/`python3` 非默认安装，Windows 上常只有 `py`/`python`）；*nix 用 `curl` + `jq`（或 `python3`）。
- 把 `limit.context`/`limit.output` 写进配置的 `limit` 字段；工具调用（agent 必需）、reasoning 与输入模态（图片等）决定模型能否上岗。
- 三源都没有的模型（新发布/小众）用保守值（如 context 128000、output 32000），后续按实际报错再调。

Windows 过滤示例（PowerShell）：

```powershell
curl.exe -s -m 30 -A "Mozilla/5.0" -o models.json https://openrouter.ai/api/v1/models
(Get-Content models.json -Raw | ConvertFrom-Json).data | Where-Object { $_.id -match "glm-5.3" } |
  Select-Object id, context_length, @{n="max_out";e={$_.top_provider.max_completion_tokens}},
    @{n="io";e={($_.architecture.input_modalities -join "+") + "->" + ($_.architecture.output_modalities -join "+")}},
    @{n="tools";e={$_.supported_parameters -contains "tools"}} | ConvertTo-Json
```

*nix 过滤示例（jq）：

```bash
curl -s -m 30 -A "Mozilla/5.0" https://openrouter.ai/api/v1/models \
  | jq '[.data[] | select(.id | test("glm-5.3")) | {id, context_length, max_out: .top_provider.max_completion_tokens, io: (.architecture.input_modalities | join("+")), tools: (.supported_parameters | index("tools")) != null}]'
```

### 4. 写配置与设置服务环境变量

**配置文件**（全局 `~/.config/opencode/opencode.json`，保留已有内容只增不删）：

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "<providerID>/<modelID>",       // 默认模型
  "providers": {
    "<providerID>": {                       // 模型引用前缀
      "name": "展示名",
      "env": ["<PROVIDER>_API_KEY"],        // 密钥环境变量名
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": { "baseURL": "https://<域名>/v1" },
      "models": {
        "<modelID>": {                      // 键 = opencode 模型 ID
          "name": "展示名",
          "modelID": "<网关侧模型名>",       // 与键不同时才写
          "limit": { "context": 1048576, "output": 131072 }
        }
      }
    }
  }
}
```

**只改已有模型的上下文/limit**（含内置 catalog 与官方套餐模型）：模型已存在时，配置条目只写要覆盖的字段，不必重复 `name`/`modelID`/`package`，写全反而容易盖错。改上下文只写 `limit.context`：

```jsonc
{
  "providers": {
    "opencode": {                        // 已内置的 provider ID，直接覆盖，不新建 provider
      "models": {
        "<modelID>": { "limit": { "context": 1048576 } }
      }
    }
  }
}
```

例：把官方免费模型 `opencode/deepseek-v4.1-flash-free` 的上下文提到 1M，只需在 `providers.opencode.models` 加上述条目，其他字段一概不动。`limit` 只是 OpenCode 侧声明的容量上限，不改变网关/供应商的真实能力——超出其支持范围仍会报错或截断；数值取自数据源或供应商文档，不臆造。改完 `opencode reload` 热加载，进行中的请求仍用旧值，下一请求起生效。

**服务端环境变量**（密钥与代理必须持久化到服务，`opencode run`/TUI 才能用；改之前先 `opencode service get env` 抄下既有值——该命令只读，读 `service.json` 的 `env` 块，与 live 进程快照、shell 变量分属三层，细节见 [references/service-env.md](references/service-env.md)）：

```bash
opencode service set env <PROVIDER>_API_KEY <KEY>

# 以下三行仅当该网关直连不可达才执行：先 get env 读既有值，合并后回写，不照模板覆盖；
# 端口来自实测/登记/用户告知，设备上没有可用代理就不设，不臆造端口
opencode service set env HTTPS_PROXY http://127.0.0.1:<port>
opencode service set env HTTP_PROXY http://127.0.0.1:<port>
opencode service set env NO_PROXY "localhost,127.0.0.1,::1,<既有放行域名>"   # 回环必须绕过；逗号分隔，合并既有值；含逗号的值加引号（PowerShell 否则拆成数组）
opencode service start   # set env 本身也会重启服务
```

服务端 env 的高频底线：`set env` 会重启服务，变量名与取值定稿后一次合并写入；改前先 `opencode service get env` 抄下既有值，代理变量只增合并不覆盖；`NO_PROXY` 保持逗号分隔并含回环。按域名分流、密钥错位、变量名占用、大小写代理变量、写入丢失、存储与生效分离、live 未生效等排障细节，见 [references/service-env.md](references/service-env.md)。

### 5. 端到端验证（按序，缺一不可）

先定测哪个模型再动手：请求里已点名模型就只测它；用户只给了地址和密钥时，拉完 `/v1/models` 后**问一次**要测哪个 id（列出候选、把最可能当默认的那个放首位），不要自行挑一个代他决定，更不要按分组顺序逐个试。用户说"都不测/先不测"就停在配置与目录校验，并在交付里写明未做真实调用验证。

1. `opencode service get env` —— 密钥、代理变量齐全（打码展示）。
2. `opencode models | findstr <providerID>` —— 配置被识别、模型全部列出。
3. `opencode run -m <provider>/<model> "reply with exactly: OK"` —— 真实调用，默认限时 10 秒（可酌情放宽到 15 秒）：超时即判该模型当前时段可靠性不佳，不换长超时重试翻案（见约束/规范）；同时 `opencode.log`（`~/.local/share/opencode/log/`）确认请求已发出、无 4xx。
4. 用 `max_tokens=512` 直接打 `/v1/chat/completions`，只测本次接入要用的模型，不逐一遍历分组全量（默认限时 10 秒，可酌情放宽到 15 秒）：核对 `choices[0].message.content` 非空、`finish_reason`（reasoning 模型小 max_tokens 会 `length` 且 content 为 null，属正常，说明思考占用了输出预算）、`usage` 里 `reasoning_tokens`。官方 Console 免费模型（`opencode/*-free`）**不能**用直连 curl 判定：免费档按客户端身份放行，非 OpenCode 客户端一律 403 `FreeTierError`，这类模型改用 `opencode run -m opencode/<id>-free` 验证；Go 模型直连需带 `x-opencode-session`。
   - 请求体先写成文件再用 `--data-binary "@<文件>"`：PowerShell 里内联 `-d "{\"model\":…}"` 经转义常被拆坏，网关回 400 `invalid JSON request body`，看起来像密钥或协议问题，实际只是引号被吃掉。
   - 限时用执行器的超时参数（或 curl 的 `-m`）施加；Windows 下别写成 `timeout 10 <命令>`——那里的 `timeout` 是系统自带的等待命令，不认这种用法，直接报 "Invalid syntax. Default option is not allowed more than '1' time(s)"，命令根本没跑。

改过 `limit` 时追加一步：`opencode api get /api/model` 取服务解析后的目录，确认目标模型的 `limit.context` 已是新值。`opencode models` 只列模型 ID、不显示 limit，不能用来验证。

## OpenCode 官方套餐（opencode / opencode-go）

- 官方免费与 Go 订阅是现成 provider：凭据由 `/connect`（TUI）或 `opencode auth login` 保存到**服务端 SQLite**（路径用 `opencode debug paths db` 查；`~/.local/share/opencode/auth.json` 只在 V2 迁移时导入一次，之后改它无效），管理用 `opencode auth list/export/switch/logout`。模型引用 `opencode/<id>`、`opencode-go/<id>`；opencode.ai 不放行 `NO_PROXY` 即自动走服务端代理。
- **一把工作区凭据同时授权 `opencode` 与 `opencode-go` 两个 provider**（工作区配置里两者共用同一凭据，`env` 均为 `OPENCODE_CONSOLE_TOKEN`）；只订阅 Go 时不必另填 Console key，`opencode/<id>-free` 会随同一份工作区配置出现。报 `api_key_expired`（"Create a new API key in OpenCode Console…"）说明凭据是旧格式或已过期：`sk-…` 旧 key 已失效，须在 Console → **Keys** → Add Service Account 建 `oc_sk_…`（可设权限与有效期）后重新连接，**重新登录不会续期旧 key**。
- 同名模型先枚举再选 ID：`opencode models | findstr <系列名>`。例：免费变体带 `-free` 后缀，普通变体报 "Insufficient account funds" 需 Console 余额；`Contributor` 变体低价但提示词会用于模型训练。

## 约束/规范

- 密钥只写入 `service set env` 与配置引用（`env` 变量名），**不写进 `opencode.json` 明文**（`settings.apiKey` 仅在用户明确要求时才考虑）。
- 修改既有 `opencode.json` 前先读全文，保留无关配置。
- `service set env`、`mcp add` 等会重启服务的操作不要连排在同一条命令里，逐条执行。
- **必须**：`NO_PROXY` 必须逗号分隔；PowerShell 下含逗号的值必须加双引号，否则逗号被解析为数组、落盘变成空格分隔，例：`opencode service set env NO_PROXY "localhost,127.0.0.1,::1,<既有放行域名>"`。接手既有配置先核验分隔符，空格分隔一律改正。例：`localhost 127.0.0.1 ::1` 的空格写法可能不被 HTTP 客户端解析，放行域名静默走代理。
- **必须**：改服务级 env 前先 `opencode service get env` 抄下既有值；`HTTP(S)_PROXY`/`NO_PROXY` 对设备上所有 provider 全局生效，只增合并不覆盖。例：设备原有模型靠既有代理变量连通，新接入照模板覆盖后旧模型静默断链。
- **必须**：重启 opencode 服务前先双查代理环境（`get env` ＋ live 进程 environ），只在旧进程快照里的代理一重启就丢；重启用 detached 方式，事后核验新进程 environ 里 PROXY 仍在。例：模型靠 HTTPS_PROXY 连网，裸 restart 后集体断链，查 environ 才发现新进程没继承。
- **必须**：只实测本次接入要用的模型（用户点名的那个），分组内其余模型不逐一验可用性与速度。用户没点名就先问一次，不自行代表他选。例：分组 20 个模型只用 2 个，就只测那 2 个，不跑完 20 个。
- **必须**：单模型验证默认限时 10 秒，可酌情放宽到 15 秒；超时即判该模型当前时段可靠性不佳，不改配置不删条目，换时段复测即可。例：12 秒回的模型放宽到 15 秒重测；仍超时也不动配置，其他时段可能就通了。
- skill 正文与示例中不得出现真实密钥、真实域名（用 `<…>` 占位）与本机绝对路径。

## 自检

- [ ] 模型列表经过筛选，只配对话模型。
- [ ] 本地直连不通时代理已持久化到服务端，不是只在当前 shell export。
- [ ] `NO_PROXY` 为逗号分隔、含回环；多入口分流时直连域名已加入，代理端口来自实测或用户告知。
- [ ] 改服务级 env 前已 `get env` 抄下既有值，代理变量只增合并不覆盖。
- [ ] `env` 变量名与 `providerID` 未占用既有名称；同名不同值已换名。
- [ ] 同域名多把 key 时已各自拉 `/v1/models` 比对分组，模型组不同时新增 provider 用独立 `env` 名，未覆盖既有 key。
- [ ] `set env` 次数已压到最少；含逗号的值已加引号并核验落盘格式。
- [ ] `get env` 与 live 服务进程环境一致：无陈旧密钥，大写代理变量齐全。
- [ ] 重启生效已用端口/`run=` 变化或新进程 environ 确认；重启后以 `STARTED` 时间最新的进程为准；live 陈旧时已用 `--standalone` 隔离验证。
- [ ] 直连测试用了 `--noproxy "*"`，未被 shell 代理 env 污染。
- [ ] 官方套餐同名模型先 `opencode models | findstr` 枚举变体；`api_key_expired` 按 Console 新建 `oc_sk_…` 处理，未去改 `auth.json`。
- [ ] 官方免费模型用 `opencode run` 验证，未据直连 curl 的 403 判接入失败。
- [ ] `limit` 来自数据源或官方文档，并经交叉核验；覆盖已有/内置模型时只写 `limit`，且已用 `opencode api get /api/model` 确认解析值。
- [ ] 只实测本次接入要用的模型，默认限时 10 秒（最多放宽到 15 秒）；用户未点名时已问过一次，未自行挑模型、未逐组遍历。
- [ ] 直连验证的请求体走文件（`--data-binary "@…"`），限时用执行器超时参数而非 `timeout` 前缀。
- [ ] 三步验证（get env → models → run）全部通过，配置文件原有内容未被覆盖。

## 验证协议

接入成功的判定：`opencode models` 出现 `<providerID>/<modelID>`，且 `opencode run -m <providerID>/<默认模型>` 返回模型正常回复；只对本次接入要用的每个模型各做一次直接 API 调用确认 `content` 可产出，每次默认限时 10 秒（可酌情放宽到 15 秒）。后台服务 live 陈旧且会话内重启无效时，以存储侧齐全＋ `--standalone` 同配置验证通过为准，后台侧待外部重启后重验。
