---
name: user-profile
description: >
  个人高频默认值：搜索渠道顺位、多通道分工与托管搜索兜底边界；配置仅作本机案例；Windows shell、路径和自建工具版本偏好。
  会话动手前由全局 AGENTS.md 加载；保留 PowerShell、网络、脚本及检索的按需入口，领域执行细则不在此维护。
---

## User Profile（个人常驻默认值）

本文件维护个人工具选择与高频默认；跨任务协作、费用和外部操作授权以当前全局 `AGENTS.md` 为准，领域机制以对应 skill 为准。明确用户要求优先。

### 工具与输出偏好

- **搜索渠道顺位与分工**：用户当轮指定且可用的渠道优先；未指定时按下述顺位定默认起点，不是“只用第一个”：
  1. `Tavily`（已配置且当轮可用时）：通用搜索首选，透明度高、通用性好；额度与并发按账号/套餐，`topic=news` + 时间过滤的时效检索也适用；
  2. agent harness 独立搜索入口（如 OpenCode 的 `web_search` / `websearch`）：Tavily 不可用、明确耗尽或不适合该任务时使用，模糊查询与官方源覆盖较好，但参数不可控；
  3. `anysearch`：仅作备用通道，前序通道不可用、明确耗尽或不适合该任务时使用；定位垂直搜索，适合明确领域内的检索、批量搜索与整页提取，不承担通用搜索默认起点；
  4. 模型/供应商内置托管搜索（如 OpenAI Responses 托管搜索）仅作最后兜底,不允许静默使用,请求费用较高,需要申请才能使用。
  多个通道可用时按任务长处分工，同一子问题只选一个主通道；交叉验证或主通道失败/受限时才用第二通道，不把同一查询扇出到所有渠道。配置只作本机案例：命令名、路径、key、默认渠道不假设在其他设备或 harness 可用，换设备先重跑可用性核对；已安装/目录可见/配置存在都不等于可用，未实测只标“已配置/未测”。任何联网/搜索操作必须显式调用并展示工具调用，不能静默调用；切换渠道、扩大范围或新增费用仍受本轮授权约束。分工与降级见 `agentic-web-search` 的“渠道选择、分工与回退”，配置与代办边界见 `harness-web-check`，逐档测试见 `references/cli-recipes.md`。
- **供应商托管搜索**：只作最后兜底，前序通道不可用、明确耗尽或不适合该任务时才考虑；不默认启用、不静默回退，使用前说明实际路径、费用及供应商/协议/harness 适配情况。原因是这条路径的调用、计费与取证不够透明；费用不明或超出本轮授权时先确认。这不禁用普通 Responses 文本与函数调用，也不把 harness 独立搜索或 Console 的 Hosted Web Search 仅凭名称归为模型供应商托管搜索。
- **搜索透明性**：路径归属与配置层禁用的证据按 `harness-web-check`；偏好/skill 是行为约束，不报告成配置层硬禁用。
- **配置代办**：用户明确授权后，可代查官方文档、给出配置步骤，或代注册免费账号/创建 API key；不代付、不绕过验证码或服务条款、不复制本机凭据到其他设备或仓库，保存前确认位置与权限。细节按 `harness-web-check`。
- **Windows shell**：优先 PowerShell，其次 git-bash，cmd.exe 仅作最后回退；带逻辑的 Windows 片段用 PowerShell，启动与执行细节按 `powershell-pitfalls`。
- **路径**：优先使用 `/`；Windows 特殊路径和目标工具兼容性例外见 [路径分隔符](../powershell-pitfalls/references/files-and-invocation.md#路径分隔符优先用-)。
- **自建工具版本**：脚本/小工具采用本地日期时间 `YYYY.MM.DD.HHmm`，不手搓语义化版本；唯一真源在 `package.json` 的 `version`，其余位置运行时读取，并提供重打入口(如 `pnpm stamp`)。四段号仅用于本地 link/安装，不发布到只接受三段 semver 的 npm registry。
- **Markdown 文档修改**：修改既有文档时，新增与改动内容按 `markdown-style` 规范执行，不迁就存量不规范写法；仅当明确要求延续原文档风格时才沿用；全文规范化需单独授权。
- **修改范围对齐**：修改指示或范围模糊不清(包括用户可能未意识到)时，先对齐真实意图与改动边界再动手；不先按自己的理解改一版再解释。范围明确的局部修改不重复确认。

### 问答沉淀

- 对用户疑问的排查与探索，回答后判断结论是否有长期价值（机制解释、选型结论、踩坑与修复步骤）；有价值就主动询问是否写入文档，不默认只留在会话里。
- 个人偏好：可复用的结论默认记到 skills 仓库的对应 skill 或 references；只在当前项目成立的操作细节留在项目仓库文档，两边不重复抄同一份内容。
- 写入前说明拟落点与范围，避免把一次排查扩写成通用教程。

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
