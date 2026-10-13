---
name: opencode-provider-config
description: 把第三方 AI API（中转站/NewAPI/one-api 渠道/自定义 OpenAI 兼容网关）接入 OpenCode 的完整流程：获取模型列表、网络与 DNS 诊断、联网查模型参数、写 providers 配置、设置服务环境变量与代理、端到端验证。凡是用户给出 API 地址+密钥要求"接入 opencode"、"配置自定义供应商/模型"、"添加中转站"、"第三方模型接入"、"配置 provider"，或需要在 OpenCode 中新增非内置模型、查 /v1/models 列表、用 models.dev 查模型上下文参数时使用本 skill。
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

筛选规则：

- 对话模型才配进 OpenCode；嵌入（`*-embed*`）、重写、翻译、安全审查（`*content-safety*`）类模型不适合做 agent，直接跳过。
- 网关常同时暴露多种协议（`supported_endpoint_types` 含 `anthropic`/`openai`），OpenCode 一律走 OpenAI 协议即可，只取模型 `id`。

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

**服务端环境变量**（密钥与代理必须持久化到服务，`opencode run`/TUI 才能用；改之前先 `opencode service get env` 抄下既有值——该命令只读，读 `service.json` 的 `env` 块，与 live 进程快照、shell 变量分属三层，见下文"存储与生效分离"）：

```bash
opencode service set env <PROVIDER>_API_KEY <KEY>

# 以下三行仅当该网关直连不可达才执行：先 get env 读既有值，合并后回写，不照模板覆盖；
# 端口来自实测/登记/用户告知，设备上没有可用代理就不设，不臆造端口
opencode service set env HTTPS_PROXY http://127.0.0.1:<port>
opencode service set env HTTP_PROXY http://127.0.0.1:<port>
opencode service set env NO_PROXY "localhost,127.0.0.1,::1,<既有放行域名>"   # 回环必须绕过；逗号分隔，合并既有值；含逗号的值加引号（PowerShell 否则拆成数组）
opencode service start   # set env 本身也会重启服务
```

**按域名分流代理**：代理是进程级的，JSON 配置无法按 provider 配代理（源码的 `options.fetch` 是函数，写不进配置文件）。同一供应商有多个入口域名、部分直连部分被阻断时，用服务端全局代理 + `NO_PROXY` 分流：直连可达的域名加进 `NO_PROXY`，其余域名自动走代理。例：域名 A 直连、域名 B 被阻断，则 `NO_PROXY` 加 A，两套 provider 配置共用同一服务端代理即可自动分流，启动时无需设置任何环境变量。

**密钥错位排查**：同一 provider 下所有模型均报网关侧“无可用渠道”，但配置文件与单模型直连测试均正常时，应优先怀疑实际生效的密钥与本次配置的密钥不一致（多会话共用同一后台服务时易发生混用）。以下命令仅输出 `True`/`False`，不打印密钥明文：

```bash
python3 -c "import os; print(os.environ.get('<PROVIDER>_API_KEY','') == '<KEY>')"
```

输出 `False` 即确认错位：不同密钥对应不同的网关账号，其模型目录与分组权限各自独立。此时换用正确的密钥并重启服务即可恢复，无需修改 provider 配置。

**变量名占用前置检查**：定 `env` 变量名前，先查四层是否已有同名（`service get env`、当前 shell 进程、Windows `User`/`Machine` 注册表），任一层有值且与本次密钥不同即视为占用，必须换名，不得覆盖用户既有变量。以下命令只查有无，不输出值：

```powershell
[Environment]::GetEnvironmentVariable("<NAME>","User")
[Environment]::GetEnvironmentVariable("<NAME>","Machine")
```

任一返回非空即占用。`providerID` 同理：不得与内置供应商同名（内置改 `baseURL` 只覆盖 `settings.baseURL`，见适用范围）。

**大小写代理变量**：shell 环境中通常仅存在小写 `http_proxy` 系变量，但部分 HTTP 客户端仅识别大写变量。恢复代理时，应以 `env | grep -i proxy` 的实测值为准补齐大写三变量（端口照抄实测值，不得臆造；写入方式见上文模板），`NO_PROXY` 保持逗号分隔。

**已知行为**：每次 `service set env` 都会重启后台服务，导致正在执行的 shell 命令以 "Tool execution interrupted"（导出日志中也显示为 "Command cancelled"）中断——这不是失败，变量已写入。变量名与取值全部定稿后再写入，`set env` 次数即重启次数，能少一次就少一次；逐条设置、每条跑完重新确认即可；确认用只读的 `opencode service get env`（输出含密钥，展示前先打码）。

**例外（写入丢失）**：经由服务端派生的 shell 执行 `set env` 时，服务重启可能先于 CLI 完成写入即将其终止，导致写入丢失（`get env` 仍为空）。若多次重试后 `get env` 依然为空，即属此情形，应改用 detached 方式执行，并以只读命令确认：

```bash
setsid nohup opencode service set env <KEY_NAME> <KEY_VALUE> >"$HOME/setenv.log" 2>&1 < /dev/null &
sleep 75
opencode service get env                                        # 只读确认已落盘（输出含密钥，展示前打码）
ps -o pid,ppid,lstart,cmd $(pgrep -f "serve --service")         # 以 STARTED 时间最新者为当前服务进程
```

`service restart` 完全生效约需 1 分钟：重启后不得以 pgrep 返回的第一个 PID 为准（该进程可能处于正在退出的瞬态），必须以上述 `ps` 输出中 `STARTED` 时间最新者为准，再对其核验环境变量。

**存储与生效分离**：环境变量有三层——shell 里 export 的临时变量（对服务进程无效，见第 2 步结论）、`get env` 读的持久化存储（`service.json` 的 `env` 块）、运行中服务进程启动时继承的快照（读法 `tr '\0' '\n' < /proc/<PID>/environ`）。三者可各自不同步；`get env` 为空并不代表服务进程中无此变量——修改服务级 env 之前，除 `get env` 外，还应查询 live 服务进程的环境（密钥经掩码处理，不输出明文）：

```bash
SERV_PID=$(pgrep -f "serve --service" | head -n 1)
tr '\0' '\n' < /proc/$SERV_PID/environ | grep -E "PROXY|_API_KEY" | sed -E 's/(sk-)[A-Za-z0-9]+/\1****/g'
```

修改存储后，必须重启服务一次，新进程才会继承更新后的变量；多次 `set env` 意味着多次重启并多次打断用户会话，因此应一次合并写好 `env` 块，再执行单次 restart。重启本身有风险：只存在于旧进程 environ 快照、未持久化的代理变量会随旧进程消失，任何重启前先双查（`get env`＋live environ），缺的先补持久化再重启；从服务派生的 shell 里直接跑 `service restart` 可能被重启连带打断，用 detached 方式（`setsid nohup … &`）执行，重启后按 STARTED 时间定位新进程并核验 PROXY 变量仍在。

**live 未生效的判定与隔离验证**（Windows 无 `/proc` 时，以对照与隔离为准）：`service status` 端口与 `opencode.log` 中 `spawning process` 的 `run=` 是否变化，是重启是否真正生效的判据；两者不变即 live 仍是旧快照，此时重复 `set env`/`restart` 只是空转，应停手。用已知正常模型做对照：已知模型 `run` 正常、新模型报缺 key，即 live 陈旧而非配置错。先用 `run --standalone` 隔离验证（私有服务继承当前 shell 环境，同条命令内设变量并验证，密钥不落盘到配置文件）：

```powershell
$env:<VAR_NAME> = "<KEY>"; opencode run --standalone -m <providerID>/<modelID> "reply with exactly: OK"
```

通过即证明配置与密钥无误；后台服务侧改用会话外部重启（新开终端、任务管理器、重启机器）后再按第 5 步重验，不在会话内空转重试。

### 5. 端到端验证（按序，缺一不可）

1. `opencode service get env` —— 密钥、代理变量齐全（打码展示）。
2. `opencode models | findstr <providerID>` —— 配置被识别、模型全部列出。
3. `opencode run -m <provider>/<model> "reply with exactly: OK"` —— 真实调用，默认限时 10 秒（可酌情放宽到 15 秒）：超时即判该模型当前时段可靠性不佳，不换长超时重试翻案（见约束/规范）；同时 `opencode.log`（`~/.local/share/opencode/log/`）确认请求已发出、无 4xx。
4. 用 `max_tokens=512` 直接打 `/v1/chat/completions`，只测本次接入要用的模型，不逐一遍历分组全量（默认限时 10 秒，可酌情放宽到 15 秒）：核对 `choices[0].message.content` 非空、`finish_reason`（reasoning 模型小 max_tokens 会 `length` 且 content 为 null，属正常，说明思考占用了输出预算）、`usage` 里 `reasoning_tokens`。

## OpenCode 官方套餐（opencode / opencode-go）

- 官方免费与 Go 订阅是现成 provider：凭据经 TUI `/connect` 写入 `~/.local/share/opencode/auth.json`（`opencode` / `opencode-go` 条目），模型引用 `opencode/<id>`、`opencode-go/<id>`；opencode.ai 不放行 `NO_PROXY` 即自动走服务端代理。
- 同名模型先枚举再选 ID：`opencode models | findstr <系列名>`。例：免费变体带 `-free` 后缀，普通变体报 "Insufficient account funds" 需 Console 余额；`Contributor` 变体低价但提示词会用于模型训练。

## 约束/规范

- 密钥只写入 `service set env` 与配置引用（`env` 变量名），**不写进 `opencode.json` 明文**（`settings.apiKey` 仅在用户明确要求时才考虑）。
- 修改既有 `opencode.json` 前先读全文，保留无关配置。
- `service set env`、`mcp add` 等会重启服务的操作不要连排在同一条命令里，逐条执行。
- **必须**：`NO_PROXY` 必须逗号分隔；PowerShell 下含逗号的值必须加双引号，否则逗号被解析为数组、落盘变成空格分隔，例：`opencode service set env NO_PROXY "localhost,127.0.0.1,::1,<既有放行域名>"`。接手既有配置先核验分隔符，空格分隔一律改正。例：`localhost 127.0.0.1 ::1` 的空格写法可能不被 HTTP 客户端解析，放行域名静默走代理。
- **必须**：改服务级 env 前先 `opencode service get env` 抄下既有值；`HTTP(S)_PROXY`/`NO_PROXY` 对设备上所有 provider 全局生效，只增合并不覆盖。例：设备原有模型靠既有代理变量连通，新接入照模板覆盖后旧模型静默断链。
- **必须**：重启 opencode 服务前先双查代理环境（`get env` ＋ live 进程 environ），只在旧进程快照里的代理一重启就丢；重启用 detached 方式，事后核验新进程 environ 里 PROXY 仍在。例：模型靠 HTTPS_PROXY 连网，裸 restart 后集体断链，查 environ 才发现新进程没继承。
- **必须**：只实测本次接入要用的模型（默认或用户点名的），分组内其余模型不逐一验可用性与速度。例：分组 20 个模型只用 2 个，就只测那 2 个，不跑完 20 个。
- **必须**：单模型验证默认限时 10 秒，可酌情放宽到 15 秒；超时即判该模型当前时段可靠性不佳，不改配置不删条目，换时段复测即可。例：12 秒回的模型放宽到 15 秒重测；仍超时也不动配置，其他时段可能就通了。
- skill 正文与示例中不得出现真实密钥、真实域名（用 `<…>` 占位）与本机绝对路径。

## 自检

- [ ] 模型列表经过筛选，只配对话模型
- [ ] 本地直连不通时代理已持久化到服务端（非仅 shell export）
- [ ] `NO_PROXY` 含 `localhost,127.0.0.1`；多入口分流时直连域名已加入（按域名分流，不按 provider 配代理）
- [ ] `NO_PROXY` 已核验为逗号分隔，空格分隔的既有值已改正？
- [ ] 改服务级 env 前 `get env` 抄了既有值，代理三变量是合并不是覆盖？
- [ ] `get env`（持久化存储）与 live 服务进程环境一致：无陈旧密钥，大写代理变量齐全？
- [ ] `env` 变量名定名前已查四层占用，同名不同值已换名，未覆盖用户既有变量？
- [ ] 含逗号的 `set env` 值已加引号写入并核验为逗号分隔；写入次数已是最少？
- [ ] 重启生效已用端口/`run=` 变化确认；live 陈旧时已用已知模型对照并以 `--standalone` 隔离验证通过？
- [ ] 重启后是否以上述 `ps` 命令中 `STARTED` 时间最新的服务进程为准完成核验，而非 pgrep 返回的任意 PID？
- [ ] 直连可达的设备未设代理变量，代理端口无臆造？
- [ ] 官方套餐同名模型先 `opencode models | findstr` 枚举变体再选 ID？
- [ ] 直连测试用了 `--noproxy "*"`，未被 shell 代理 env 污染
- [ ] `limit` 参数来自任一数据源并经交叉核验或官方确认，非臆造
- [ ] 只实测了接入要用的模型，未逐一遍历分组全量？
- [ ] 单模型验证默认限时 10 秒（可放宽到 15 秒），超时判当前时段可靠性不佳而非无限重试？
- [ ] 重启服务前双查代理环境（get env＋live environ），重启后新进程 PROXY 仍在？
- [ ] 三步验证（get env → models → run）全部通过
- [ ] 配置文件原有内容未被覆盖

## 验证协议

接入成功的判定：`opencode models` 出现 `<providerID>/<modelID>`，且 `opencode run -m <providerID>/<默认模型>` 返回模型正常回复；只对本次接入要用的每个模型各做一次直接 API 调用确认 `content` 可产出，每次默认限时 10 秒（可酌情放宽到 15 秒）。后台服务 live 陈旧且会话内重启无效时，以存储侧齐全＋ `--standalone` 同配置验证通过为准，后台侧待外部重启后重验。
