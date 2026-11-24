# 协议切换：Responses 与 Anthropic Messages

判断依据：`/v1/models` 的 `supported_endpoint_types`、`/api/pricing` 的 `supported_endpoint` path，以及本文件的最小实测。声明支持不代表该模型在该渠道可用；只切换实测通过的模型。

## Responses（GPT / OpenAI 系）

模型级覆盖，不改 provider 级：

```jsonc
{
  "providers": {
    "<providerID>": {
      "models": {
        "<modelID>": {
          "package": "@opencode/ai/providers/openai-compatible/responses",
          "limit": { "context": 1050000, "output": 128000 }
        }
      }
    }
  }
}
```

三步验证：

1. 直连 `POST <baseURL>/v1/responses`，body 写成文件：`{"model":"<modelID>","input":"OK","max_output_tokens":64}`。确认 200 且 `output[].content[].type=output_text` 非空；小预算只有 reasoning、`content` 为空但 usage 有输出，也算通路。
2. 改配置后用 `opencode api get /api/model` 确认目标模型 `package` 已是 responses 版本；`opencode models` 只列 ID，不能证明协议。
3. 用本地抓包服务（返回 400 即可）看请求 path：responses 模型只打 `/v1/responses`，同 provider 的 chat 模型只打 `/v1/chat/completions`。回复文本相同不能证明协议已切换，两套路由都能产出同样的内容。

- Responses 的默认值与 Chat 不同（`store`、`include` 等）；文本返回 `OK` 只证明文本通路。
- 做 agent 前补一次工具调用验证：让模型读一个含唯一标记的文件并回显该标记。
- 不要用一个模型的结果推断同组其他模型。

## Anthropic Messages（Claude 系）

provider 级覆盖，同组 Claude 共用：

```jsonc
{
  "providers": {
    "<providerID>": {
      "package": "@opencode/ai/providers/anthropic-compatible",
      "settings": { "baseURL": "https://<域名>/v1" }
    }
  }
}
```

- 客户端只在 baseURL 后拼 `/messages`，所以必须自带 `/v1`；裸域名会 404。
- 鉴权用 `x-api-key`，客户端自动带 `anthropic-version`。
- 直连验证：`POST <baseURL>/v1/messages`，body 用 `messages[].content` 与 `max_tokens`，看 `content[].text` 非空。
- 用抓包确认请求落在 `/v1/messages`。

## 回退

任一验证失败：恢复默认 `@opencode/ai/providers/openai-compatible`，记录失败现象与请求 path，不逐档试错。
