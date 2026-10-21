---
name: user-profile
description: >
  全局偏好记录,重点阅读并实践,任何会话都要确保读取这里的常驻默认值：优先由全局 AGENTS.md 显式加载.
---
# User Profile（个人常驻默认值）

本 skill 只存个人高频偏好与域指针，优先由全局 `AGENTS.md` 显式加载；涉及网络选路或 PowerShell 时也可按关键词加载兜底，不依赖单一入口。
域规则以被指 skill 正文为准，本文件只保留能改变默认动作的底线摘要。

## 常驻底线

- **环境假设**：试验默认在国内，生产部署默认在海外服务器；用户明确指定的环境优先。
- **网络选路**：国内默认走代理/镜像，海外默认直连原站。登记有可用代理时直接采用、
  免双路探测（抓取本身即核验，成功时不预读长文档）；无可用登记时直连按总耗时上限
  （含首字节等待）熔断后切代理，结论同一任务复用；确认抓取工具的实际出口。
  需代理先读 `~/.config/proxy-resources.json`，无可用代理直接问用户，不盲试端口、不静默放弃。
- **PowerShell**：带逻辑的片段一律用 PowerShell，运行前先加载 `powershell-pitfalls`。任何可能输出非 ASCII 的调用（含读文件、`Get-ChildItem` 枚举、`Select-String` 结果）同次先设输出编码再输出；必需操作加 `-ErrorAction Stop`；原生命令紧跟查 `$LASTEXITCODE`；退出码 0 或纯英文输出不能证明读取正确。**多段 CLI 串成管道或重定向时**同样要先设编码（`[Console]::OutputEncoding` 与 `$OutputEncoding`，`chcp` 单独不够），且优先改成"文件接力"或字节闸门——每一跳都要过 PowerShell 的文本解码，漏设一次整条链失真。
- **脚本（非 PowerShell）**：默认 UTF-8。Python 一律 `-X utf8`（父子多层时父进程先设
  `PYTHONUTF8=1`）、读写显式 `encoding="utf-8"`；新脚本文件 UTF-8 无 BOM、换行 LF。
  细节见 `scripting-best-practices`。
- **版本号**：自建脚本/小工具的版本号按**日期时间**打，格式 `YYYY.MM.DD.HHmm`（本地时间，
  如 `2026.10.19.1750`），不用手搓语义化版本；唯一真源放 `package.json` 的 `version`，
  其余位置运行时读取，并配一个按当前时间重打的入口（如 `pnpm stamp`）。四段号只用于
  本地 link/安装，不发 npm registry（npm 只认三段 semver）。
- **本地提炼skill**：聚焦规则与执行所需内容，不默认保留原材料、来源引用或指纹；具体边界按[内容与语言规范](../skill-authoring-sync/references/skill-content-guidelines.md#正文与参考的组织)。

### 重点技能

常用,重要的事集中强调. 现成的技能利用起来.

动词命中即加载：

1. 写PowerShell 命令/脚本/片段/防乱码/执行多段 CLI 链式管道: `powershell-pitfalls`；
2. 访问网络/请求失败/出网慢/镜像: `network-access`；
3. 验收/复现/回归/门禁/交付质量: `ai-verified-delivery`；
4. 测试代码/编写测试: `web-app-testing`
5. 存量页找错/截图验收/溢出/断点: `frontend-qa`；
6. 看HTML/网页/URL并总结/取数/查分查表: `htmlmini`（先提取再回答，禁直接读原文或手写正则取数；需代理/渲染落盘时与 `network-access` 配合，落盘后再按文件模式提取）；
7. 同步配置/同步opencode设置(偏好)/回写配置真源: `skill-authoring-sync`（先比对本机与真源，只把可跨机的项合入 `config/opencode/cli.json` 等真源，走仓库脚本校验；提交按明确指示）；

## 域指针（需细节时加载，不预读）

| 情况                                                                                                  | 加载                                                                     |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 出网慢/失败、GitHub/文档抓取、依赖下载、镜像/加速、超时·403·限流分流                                | `network-access`（含其 `references/network-access.md` 命令与分流表） |
| 编写/运行 PowerShell 片段、非 ASCII 乱码、静默失败、退出码、启动/profile、引号路径                    | `powershell-pitfalls`（按其“按需读取”表只读相关章节）                |
| 多段 CLI 输出串成管道/重定向、命令输出落盘后中文变乱码、想按字节传输出                            | `powershell-pitfalls` 的《编码读取排障》——链式 CLI 处理的推荐做法与实测对照 |
| 编写/审查/重构脚本（.sh/.bash/.py/.mjs/.js，含 Node CLI）、脚本执行侧与文件侧 UTF-8 默认、换行/BOM、子进程输出编码 | `scripting-best-practices`（先读其通用约束，再按语言读对应章节） |

## 约束

- 本机端口、镜像与一次测量是线索，不是永久默认值；实测不一致时以实测为准。
- 单次任务优先进程级/命令级配置，不静默改系统代理或全局 Git 配置。
- 不把本文件当全仓技能地图：各域职责与触发以其 `description` 为准，不在此复制。

## 验证协议

1. 在仓库根运行 `powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -VerifyOnly`
   或 `./scripts/link-skills.sh --verify-only`，确认链接与正文可读。
2. 检查 harness 可用列表中存在 `user-profile`，且 README 检索表与 description 语义一致。
