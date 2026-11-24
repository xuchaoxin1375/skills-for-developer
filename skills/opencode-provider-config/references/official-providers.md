# 官方套餐与官方 API key 型 provider

## OpenCode 官方套餐（opencode / opencode-go）

- 免费与 Go 订阅是现成 provider，不需要写 `providers`。
- 凭据由 `/connect`（TUI）或 `opencode auth login` 保存到服务端 SQLite（路径用 `opencode debug paths db` 查）；`auth.json` 只在 V2 迁移时导入一次，之后改它无效。
- 管理：`opencode auth list/export/switch/logout`。
- 一把工作区凭据同时授权两个 provider（`env` 均为 `OPENCODE_CONSOLE_TOKEN`）；只订阅 Go 也会出现 `opencode/<id>-free`。
- 目录免 key 可查：`/inference/v1/models` 含 `*-free`，`/inference/go/v1/models`；models.dev 的 `opencode` / `opencode-go` 条目带 limit 与 cost。公开目录不等于可用范围，以工作区配置或 `opencode models` 为准。
- 同名模型先枚举：`opencode models | findstr <系列名>`；免费变体带 `-free`，普通变体需要 Console 余额。
- 报 `api_key_expired`：旧格式 `sk-…` 已失效，去 Console → Keys → Add Service Account 建 `oc_sk_…` 后重连；重新登录不会续期旧 key。
- 免费模型直接 curl 可能 403 `FreeTierError`，用 `opencode run` 按客户端身份验证；Go 模型直连需带 `x-opencode-session`。
- 免费或低价档的提示词可能用于训练，不放隐私与客户数据。

## Google AI Studio

- 内置 `google` provider，不写 `providers`；凭据变量 `GEMINI_API_KEY`（或 `GOOGLE_API_KEY`、`GOOGLE_GENERATIVE_AI_API_KEY`），写一个即可。
- 模型目录来自 models.dev；需要覆盖参数时只写 `providers.google.models.<modelID>` 的目标字段。
- 先最小 `generateContent` 确认 key、模型与链路，再写服务端 env。国内直连 `generativelanguage.googleapis.com` 常超时，代理按 [服务端 env 与代理](service-env.md) 持久化。
- 先用独立实例验证，避免重启共享服务：在命令内设 `GEMINI_API_KEY` 与代理 env，再跑 `opencode run --standalone -m google/<model> "OK"`。
- 免费档按 project 限流（RPM/TPM/RPD 只在 AI Studio 限流页可见）；429 即触限，不换 key 绕过。
- Gemini 3/4 默认开思考，思考 token 计入输出预算；`maxOutputTokens` 太小会 `MAX_TOKENS` 且文本为空。
