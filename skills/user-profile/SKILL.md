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
- **PowerShell**：带逻辑的脚本片段一律用 PowerShell。读非 ASCII 文件用 `-LiteralPath`
  加显式 `-Encoding`；必需操作加 `-ErrorAction Stop`；原生命令紧跟查 `$LASTEXITCODE`；
  退出码 0 或纯英文输出不能证明读取正确。
- **脚本（非 PowerShell）**：默认 UTF-8。Python 一律 `-X utf8`（父子多层时父进程先设
  `PYTHONUTF8=1`）、读写显式 `encoding="utf-8"`；新脚本文件 UTF-8 无 BOM、换行 LF。
  细节见 `scripting-best-practices`。

## 域指针（需细节时加载，不预读）

| 情况 | 加载 |
|---|---|
| 出网慢/失败、GitHub/文档抓取、依赖下载、镜像/加速、超时·403·限流分流 | `network-access`（含其 `references/network-access.md` 命令与分流表） |
| 编写/运行 PowerShell 片段、非 ASCII 乱码、静默失败、退出码、启动/profile、引号路径 | `powershell-pitfalls`（按其“按需读取”表只读相关章节） |
| 编写/审查/重构 `.sh`/`.bash`/`.py` 脚本、脚本执行侧与文件侧 UTF-8 默认、换行/BOM、子进程输出编码 | `scripting-best-practices`（先读其 Python“文件读写/执行侧编码”两节） |

## 约束

- 本机端口、镜像与一次测量是线索，不是永久默认值；实测不一致时以实测为准。
- 单次任务优先进程级/命令级配置，不静默改系统代理或全局 Git 配置。
- 不把本文件当全仓技能地图：各域职责与触发以其 `description` 为准，不在此复制。

## 验证协议

1. 在仓库根运行 `powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -VerifyOnly`
   或 `./scripts/link-skills.sh --verify-only`，确认链接与正文可读。
2. 检查 harness 可用列表中存在 `user-profile`，且 README 检索表与 description 语义一致。
