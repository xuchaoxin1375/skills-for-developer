---
name: opencode-provider-config
description: 把第三方 AI API（中转站/NewAPI/one-api/自定义兼容网关）或官方 API key 型端点（如 Google AI Studio）接入 OpenCode V2，或补全、审查已有模型参数：核实输入输出模态、工具、思考等级与 variants、上下文/输出上限，写 providers 配置、切换 Responses/Messages。用于接入供应商与模型、配置 provider、查 /v1/models 或 models.dev，或让 OpenCode 走代理、检查/设置/移除代理（`scripts/opencode_proxy.py`）、按运行模式做一次性代理覆盖（`--standalone`/`serve`/`--server`）、排查服务端 env 不生效；不要求重新接入或提供新密钥。通用 OpenCode 使用归 opencode，Codex 模型配置归 codex-model-config。
---

# OpenCode 供应商接入与模型参数流程

## 适用范围

- 第三方中转站（NewAPI / one-api / uni-api 等 OpenAI 兼容网关）接入 OpenCode V2。
- 官方 API key 型端点接入内置 provider：不写 `providers`，凭据走服务端环境变量，目录来自 models.dev；细节见 [官方 provider](references/official-providers.md)。
- 已内置 catalog 的供应商改用自定义 baseURL：只覆盖 `settings.baseURL`，不新建 provider。
- OAuth 型供应商（Copilot 等）不适用，走 `/connect`。
- V2 配置形状以 `opencode` skill 与官方文档为准；本 skill 只管 API key 型接入、模型参数与协议落地，不沿用 V1 字段。
- 搜索工具可见性与调用验收归 [harness-web-check](../harness-web-check/SKILL.md)；订阅与平台托管搜索的归属按其适配说明核实，不从套餐或 Responses 通路推断。只有证据指向协议或模型能力时才由本 skill 局部修复。

## 核心用例

| 目标 | 最短入口 |
| --- | --- |
| 新网关接入 | 第 1 步拉目录 → 第 2 步一次问清 → 第 3 步取参数 → 第 4 步写配置 → 第 5 步写密钥 → 第 6 步验证。 |
| 已有模型补模态、工具或档位 | 从第 3 步开始，按 [模型参数配置](references/model-parameters.md) 只覆盖目标字段；不重接、不重写密钥。 |
| 只改上下文或输出上限 | 核对渠道真实上限，只写 `limit`，再核对服务解析值。 |
| Google AI Studio 免费 key | 内置 `google` provider + `GEMINI_API_KEY`，见 [官方 provider](references/official-providers.md)。 |

## 主流程

按需执行；只补参数时从第 3 步开始，不重拉目录、不改服务环境。联网前按 `network-access` 选路，检索策略按 `agentic-web-search`。

### 1. 拉目录

```bash
curl.exe -s -m 30 <baseURL>/v1/models -H "Authorization: Bearer <KEY>"
```

- 请求失败（无解析、拒绝连接、证书错误、404）先报实际错误并确认地址；只有超时才按 `network-access` 的诊断顺序判断直连与代理，不静默重试，也不自行替换域名。
- 再拉网关的 `/api/pricing`（多数 NewAPI 免鉴权，需要就带同一 Authorization）：一次拿到每个模型的 `description`（常见上下文、输出、模态）、`enable_groups`、分组倍率与 `supported_endpoint` 的真实 path。把 key 的模型清单与 `enable_groups` 对照即可确定分组和上限，优先于逐模型搜索；404 或格式不同就跳过。
- 同域名已有多把 key：各拉一次目录比对。模型组不同就新建 provider + 独立 `env` 名，不覆盖旧 key（覆盖会让旧 provider 静默丢模型）。
- 只配对话模型：跳过 embed、重写、翻译、内容安全、生图/生视频与审计模型。
- 大 JSON 先落盘再按模型名过滤，不整段读入上下文。

### 2. 定范围（只问一次）

- 拉完目录后**一次性问清**：日常用哪个模型、是否授权极小真实调用。不要先查完全部参数再问，也不要替用户挑模型。
- 用户说“不测/先不测”就停在配置与目录校验，交付写明未验证。
- 真实模型调用与本地抓包都要明确授权。

### 3. 取参数：一次取够

证据优先级与停止条件：

1. 网关 `/api/pricing` 的 description / tags，代表渠道真实限制。
2. 聚合目录：`python -X utf8 scripts/model_info.py --source openrouter <系列名>`（Windows 用 `python`，*nix 用 `python3`；一次一个 pattern，命中即停）。脚本只给上下文、模态、工具与布尔推理，不含档位；`reasoning=true` 不代表支持任意档位。
3. 只在聚合源冲突、或档位缺证据时查官方模型卡 / 发布说明。

- 每个模型最多 2 次外部查询；同系列已确认的档位集合可直接复用，交付注明依据。
- 渠道标称上限低于聚合源时按渠道配，其余按 OpenRouter 类聚合值配；理由写一行，不展开论证。
- 取不到就留空或只写 `supported: true`，标“未知/未验证”；不猜数值，不拿通用 128K/32K 冒充真实能力。
- 字段映射、档位集合与验收口径见 [模型参数配置](references/model-parameters.md)。

### 4. 写配置并核对目录

全局 `%USERPROFILE%/.config/opencode/opencode.json`（Linux `~/.config/opencode/`；本机可能是 `opencode.jsonc`）。先读全文，只增不删。

```jsonc
{
  "providers": {
    "<providerID>": {
      "name": "<展示名>",
      "env": ["<PROVIDER>_API_KEY"],
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": { "baseURL": "https://<域名>/v1" },
      "models": {
        "<modelID>": {
          "name": "<展示名>",
          "modelID": "<网关侧 ID>",
          "capabilities": {
            "tools": true,
            "input": ["text", "image"],
            "output": ["text"],
            "reasoning": {
              "supported": true,
              "effort": ["low", "medium", "high", "xhigh", "max"]
            }
          },
          "limit": { "context": 1050000, "output": 128000 }
        }
      }
    }
  }
}
```

- `modelID` 只在与键不同时写；已有模型只补一个字段时，条目只写该字段。
- `toggle: true` 在当前版本可能不生成 `none` variant；要“关闭思考”档位时用显式 `variants`：`[{ "id": "none", "settings": { "reasoningEffort": "none" } }]`。
- 保存后自动热加载。校验：

```bash
opencode models | findstr <providerID>
opencode api get /api/model
```

按 `providerID` 过滤核对 `package`、能力、`limit` 与 variants。服务刚重启时该接口可能返回空数组，等 2 秒重试一次，不据此判定配置失败。

### 5. 写密钥

```bash
opencode service get env
opencode service set env <PROVIDER>_API_KEY <KEY>
```

- `set env` 会重启后台服务，当前命令常以 `Tool execution interrupted` 结束；变量已落盘，不要重试，用只读 `get env` 确认（展示打码）。
- 变量名与配置的 `env` 逐字一致；写错也能写入成功，但请求会报缺 key。
- 密钥只放服务端 env，不进配置文件。定稿后一次写入，减少重启。
- 只有本地直连确实不通时才配代理，并持久化到服务端：直连/代理诊断按 `network-access`，持久化、变量名、`NO_PROXY` 与一次性覆盖见 [服务端 env 与代理](references/service-env.md)。

### 6. 验证

默认只测用户点名的模型：

1. `get env`：密钥与代理齐全（打码）。
2. `opencode models | findstr <providerID>`：目标模型都在。
3. 直连极小请求（唯一必需）：`/v1/chat/completions`，单轮 `OK`，`max_tokens` 16–64，请求体写文件后 `--data-binary "@<文件>"`，限时 10 秒（最多 15）。HTTP 200 且输出 tokens 非零即通；推理模型 `content` 为 null 但 usage 有输出也判可用。
4. `opencode run -m <provider>/<model> "OK"`：仅用户明确要求经 harness 验证时执行；会注入全局上下文，单次上万 token。
5. `api get /api/model`：改过参数时核对解析值。

超时即记“该时段不可用”，换时段复测，不改配置也不延长超时硬试。报告分开写“配置已识别 / 目录已核对 / 真实调用已验证”，未测项（工具、图片、各档位、最大窗口）单独列出。

## 协议选择

| 模型族 | 网关声明 | 配置 |
| --- | --- | --- |
| GPT / OpenAI 系 | `openai-response` 且直连 200 | 模型级 `@opencode/ai/providers/openai-compatible/responses` |
| Claude 系 | `anthropic` | provider 级 `@opencode/ai/providers/anthropic-compatible`，`baseURL` 带 `/v1` |
| 其余或未实测 | `openai` | 默认 `@opencode/ai/providers/openai-compatible` |

- 没有实测证据就留在 Chat Completions；不能只凭 `/v1/models` 的声明切协议。
- Responses 只覆盖目标模型，不改 provider 级。
- 切换步骤、最小请求与抓包确认见 [协议切换](references/protocols.md)。

## 约束

- 密钥不进 `opencode.json`；`settings.apiKey` 只在用户明确要求时考虑。
- 改配置前读全文；不覆盖无关 provider、MCP 与既有 env。
- 同域名多 key 不合并、不覆盖；providerID 与 env 名先查占用。
- 服务端 env 全局生效：代理变量只增合并不覆盖；`NO_PROXY` 逗号分隔、含回环，PowerShell 下含逗号的值加引号并核对落盘格式。
- `set env` / `restart` 会重启服务，逐条执行，不与其它重启类命令串排。
- 只实测用户点名的模型；纯连通性抽查用组内最便宜的一档。
- 目录出现档位不等于网关接受该档位；未验证的能力不写成已验证。

## 自检

按改动范围勾选；真实请求项仅在授权后执行，未执行就标未测。

- [ ] 已筛掉非对话模型；同域名多 key 已比对。
- [ ] 参数有来源，未知项未猜填；渠道上限冲突按渠道值处理。
- [ ] 配置只增改目标项，无关内容未被覆盖。
- [ ] `opencode models` 与 `/api/model` 已核对，或说明未核验原因。
- [ ] `get env` 有目标变量且拼写一致；代理变量名只含 `HTTP(S)_PROXY`/`ALL_PROXY`/`NO_PROXY`。
- [ ] 只测点名模型，单轮极简，限时 10–15 秒。
- [ ] 协议切换有直连 200 证据；未测则仍是默认协议。
- [ ] 交付区分“配置 / 目录 / 真实调用”，并列出未测项。

## 验证协议

1. `opencode models | findstr <providerID>` 出现目标 ID。
2. `/api/model` 中目标条目与本次改动一致。
3. 获准时对点名模型做一次直连极简请求，按第 6 步判定；`opencode run` 仍需单独授权，不作为默认抽查。
4. 通路通过不代表模态、工具、全部档位与最大窗口已验证。
5. 后台服务 live 陈旧时区分存储层与 live；只有获准的 `--standalone` 同配置验证通过才报告该结果。
