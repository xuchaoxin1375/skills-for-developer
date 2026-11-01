---
name: user-profile
description: >
  个人高频默认值：搜索渠道三档顺位与供应商托管搜索兜底边界、Windows shell、路径和自建工具版本偏好。
  会话动手前由全局 AGENTS.md 加载；保留 PowerShell、网络、脚本及检索的按需入口，领域执行细则不在此维护。
---

## User Profile（个人常驻默认值）

本文件维护个人工具选择与高频默认；跨任务协作、费用和外部操作授权以当前全局 `AGENTS.md` 为准，领域机制以对应 skill 为准。明确用户要求优先。

### 工具与输出偏好

- **搜索渠道三档顺位**：用户当轮指定且可用的渠道优先；未指定时按三档选主通道，前档不可用才降级：
  1. 已配置的第三方搜索：`anysearch` 优先（免费不限量，可用时不刻意限次），配置好的 `Tavily` 备用（额度与并发按其账号/套餐）；
  2. agent harness 暴露的独立搜索入口（如 OpenCode 的 `web_search` / `websearch`）；
  3. 模型/供应商内置托管搜索（如 OpenAI Responses 托管搜索）仅作最后兜底。
  已安装、目录可见或配置存在都不等于可用，未实测只标“已配置/未测”；任何联网/搜索操作必须显式调用并展示工具调用，不能静默调用；不因历史默认覆盖用户当前选择；切换渠道、扩大范围或新增费用仍受本轮授权约束。降级条件与额度分工见 `agentic-web-search` 的“渠道选择与回退”，逐档测试步骤见其 `references/cli-recipes.md`。
- **供应商托管搜索**：只作第三档兜底，前两档不可用或明确耗尽时才考虑；不默认启用、不静默回退，使用前说明实际路径、费用及供应商/协议/harness 适配情况。原因是这条路径的调用、计费与取证不够透明；费用不明或超出本轮授权时先确认。这不禁用普通 Responses 文本与函数调用，也不把 harness 独立搜索或 Console 的 Hosted Web Search 仅凭名称归为模型供应商托管搜索。
- **搜索透明性**：路径归属与配置层禁用的证据按 `harness-web-check`；偏好/skill 是行为约束，不报告成配置层硬禁用。
- **Windows shell**：优先 PowerShell，其次 git-bash，cmd.exe 仅作最后回退；带逻辑的 Windows 片段用 PowerShell，启动与执行细节按 `powershell-pitfalls`。
- **路径**：优先使用 `/`；Windows 特殊路径和目标工具兼容性例外见 [路径分隔符](../powershell-pitfalls/references/files-and-invocation.md#路径分隔符优先用-)。
- **自建工具版本**：脚本/小工具采用本地日期时间 `YYYY.MM.DD.HHmm`，不手搓语义化版本；唯一真源在 `package.json` 的 `version`，其余位置运行时读取，并提供重打入口(如 `pnpm stamp`)。四段号仅用于本地 link/安装，不发布到只接受三段 semver 的 npm registry。

### 按需入口

只加载当前任务命中的领域，不预读全部入口；其他任务直接按可用 skill 的 description 选择，不在这里维护全仓技能地图。

| 触发情况 | 加载入口与细则归属 |
|---|---|
| Windows 首次发出 PowerShell 调用前，包含单行读取/抓取/解析 | `powershell-pitfalls`：编码、管道、退出码、启动/profile 与参数 |
| 外链抓取、依赖下载或代理/镜像配置前 | `network-access`：环境假设、代理登记、实际出口、选路与失败分流 |
| 编写、审查或重构脚本/CLI | `scripting-best-practices`：UTF-8、选项、覆盖预检、核心用例与决策留档 |
| 联网检索与证据核验 | `agentic-web-search`：常规流程与一次性搜索例外；配置/工具下发/实际调用检查转 `harness-web-check` |
| 文档排版或 skill 内容维护 | `markdown-style` 管排版；`skill-authoring-sync` 管真源与写作规范入口 |

### 验证协议

1. 在仓库根运行 `powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -VerifyOnly` 或 `./scripts/link-skills.sh --verify-only`，确认链接与正文可读。
2. 检查 harness 可用列表中存在 `user-profile`，且 README 检索表与 description 语义一致。
