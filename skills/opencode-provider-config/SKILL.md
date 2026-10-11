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

**结论：只要本地直连不可达，就必须把代理配置到 OpenCode 服务端**（见第 4 步），只在当前 shell 临时 export 是不够的。

### 3. 联网查模型参数

拿到模型名后查 `https://models.dev/api.json`（全量 JSON，按 `prov.models[modId]` 取）或搜索官网/发布博客，确定：

- `limit.context`（上下文窗口）与 `limit.output`（最大输出）：写配置的 `limit` 字段，避免上下文截断或输出超限。
- 是否支持工具调用（agent 必需）、是否 reasoning 模型、输入模态（图片等）。
- 没查到的模型用保守值（如 context 128000、output 32000），后续按实际报错再调。

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

**服务端环境变量**（密钥与代理必须持久化到服务，`opencode run`/TUI 才能用）：

```bash
opencode service set env <PROVIDER>_API_KEY <KEY>
opencode service set env HTTPS_PROXY http://127.0.0.1:<port>
opencode service set env HTTP_PROXY http://127.0.0.1:<port>
opencode service set env NO_PROXY localhost,127.0.0.1,::1   # 回环必须绕过；多入口分流时直连域名也加这里
opencode service start   # set env 本身也会重启服务
```

**按域名分流代理**：代理是进程级的，JSON 配置无法按 provider 配代理（源码的 `options.fetch` 是函数，写不进配置文件）。同一供应商有多个入口域名、部分直连部分被阻断时，用服务端全局代理 + `NO_PROXY` 分流：直连可达的域名加进 `NO_PROXY`，其余域名自动走代理。例：域名 A 直连、域名 B 被阻断，则 `NO_PROXY` 加 A，两套 provider 配置共用同一服务端代理即可自动分流，启动时无需设置任何环境变量。

**已知行为**：每次 `service set env` 都会重启后台服务，导致正在执行的 shell 命令以 "Tool execution interrupted" 中断——这不是失败，变量已写入。逐条设置、每条跑完重新确认即可；确认用只读的 `opencode service get env`（输出含密钥，展示前先打码）。

### 5. 端到端验证（按序，缺一不可）

1. `opencode service get env` —— 密钥、代理变量齐全（打码展示）。
2. `opencode models | findstr <providerID>` —— 配置被识别、模型全部列出。
3. `opencode run -m <provider>/<model> "reply with exactly: OK"` —— 真实调用。首次调用经代理可能较慢，短超时会误判；超时则放后台加长超时重跑，同时 `opencode.log`（`~/.local/share/opencode/log/`）确认请求已发出、无 4xx。
4. 用 `max_tokens=512` 直接打 `/v1/chat/completions` 测每个模型：核对 `choices[0].message.content` 非空、`finish_reason`（reasoning 模型小 max_tokens 会 `length` 且 content 为 null，属正常，说明思考占用了输出预算）、`usage` 里 `reasoning_tokens`。

## 约束/规范

- 密钥只写入 `service set env` 与配置引用（`env` 变量名），**不写进 `opencode.json` 明文**（`settings.apiKey` 仅在用户明确要求时才考虑）。
- 修改既有 `opencode.json` 前先读全文，保留无关配置。
- `service set env`、`mcp add` 等会重启服务的操作不要连排在同一条命令里，逐条执行。
- skill 正文与示例中不得出现真实密钥、真实域名（用 `<…>` 占位）与本机绝对路径。

## 自检

- [ ] 模型列表经过筛选，只配对话模型
- [ ] 本地直连不通时代理已持久化到服务端（非仅 shell export）
- [ ] `NO_PROXY` 含 `localhost,127.0.0.1`；多入口分流时直连域名已加入（按域名分流，不按 provider 配代理）
- [ ] 直连测试用了 `--noproxy "*"`，未被 shell 代理 env 污染
- [ ] `limit` 参数来自 models.dev 或官网，非臆造
- [ ] 三步验证（get env → models → run）全部通过
- [ ] 配置文件原有内容未被覆盖

## 验证协议

接入成功的判定：`opencode models` 出现 `<providerID>/<modelID>`，且 `opencode run -m <providerID>/<默认模型>` 返回模型正常回复；每个模型至少一次直接 API 调用确认 `content` 可产出。
