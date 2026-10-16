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
- **网络选路**：国内默认走代理/镜像，海外默认直连原站。陌生外链先双路有界探测
  （`--noproxy '*'` vs `--proxy`，连接 5s/单次 20s 上限）再抓取，结论同一任务复用；
  确认抓取工具的实际出口。需代理先读 `~/.config/proxy-resources.json` 并轻量核验，
  无可用代理直接问用户，不盲试端口、不静默放弃。
- **PowerShell**：带逻辑的片段一律用 PowerShell，运行前先加载 `powershell-pitfalls`。任何可能输出非 ASCII 的调用（含读文件、`Get-ChildItem` 枚举、`Select-String` 结果）同次先设输出编码再输出；必需操作加 `-ErrorAction Stop`；原生命令紧跟查 `$LASTEXITCODE`；退出码 0 或纯英文输出不能证明读取正确。
- **脚本（非 PowerShell）**：默认 UTF-8。Python 一律 `-X utf8`（父子多层时父进程先设
  `PYTHONUTF8=1`）、读写显式 `encoding="utf-8"`；新脚本文件 UTF-8 无 BOM、换行 LF。
  细节见 `scripting-best-practices`。
- **本地提炼skill**：聚焦规则与执行所需内容，不默认保留原材料、来源引用或指纹；具体边界按[内容与语言规范](../skill-authoring-sync/references/skill-content-guidelines.md#正文与参考的组织)。

### 重点技能

常用,重要的事集中强调. 现成的技能利用起来.

动词命中即加载：

1. 写PowerShell 命令/脚本/片段/防乱码: `powershell-pitfalls`；
2. 访问网络/请求失败/出网慢/镜像: `network-access`；
3. 验收/复现/回归/门禁/交付质量: `ai-verified-delivery`；
4. 测试代码/编写测试: `web-app-testing`
5. 存量页找错/截图验收/溢出/断点: `frontend-ux-qa`；
<!-- 6. 写脚本: `scripting-best-practices`。 -->

## 域指针（需细节时加载，不预读）

| 情况                                                                                                  | 加载                                                                     |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 出网慢/失败、GitHub/文档抓取、依赖下载、镜像/加速、超时·403·限流分流                                | `network-access`（含其 `references/network-access.md` 命令与分流表） |
| 编写/运行 PowerShell 片段、非 ASCII 乱码、静默失败、退出码、启动/profile、引号路径                    | `powershell-pitfalls`（按其“按需读取”表只读相关章节）                |
| 编写/审查/重构脚本（.sh/.bash/.py/.mjs/.js，含 Node CLI）、脚本执行侧与文件侧 UTF-8 默认、换行/BOM、子进程输出编码 | `scripting-best-practices`（先读其通用约束，再按语言读对应章节） |

## 约束

- 本机端口、镜像与一次测量是线索，不是永久默认值；实测不一致时以实测为准。
- 单次任务优先进程级/命令级配置，不静默改系统代理或全局 Git 配置。
- 不把本文件当全仓技能地图：各域职责与触发以其 `description` 为准，不在此复制。

## 验证协议

1. 在仓库根运行 `powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -VerifyOnly`
   或 `./scripts/link-skills.sh --verify-only`，确认链接与正文可读。
2. 检查 harness 可用列表中存在 `user-profile`，且 README 检索表与 description 语义一致。
