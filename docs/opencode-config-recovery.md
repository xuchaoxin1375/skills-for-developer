# OpenCode 本机配置丢失与恢复

本文处理 `~/.config/opencode/` 下 `cli.json`、`plugins/`、`AGENTS.md` 在环境重置、清理或误删后的恢复。先确认仓库真源没有丢，再从真源恢复 live 副本；不要拿 live 的最小默认内容反向覆盖仓库。

`opencode.json` 的 providers、`service.json` 的密钥与 `auth.json` 的登录态不在本文范围：它们不入本仓库、不能从真源恢复，按 `opencode-provider-config` 与 [WSL 复用 Windows 侧 OpenCode 配置](wsl-opencode-reuse.md)的密钥红线处理。

## 先分清真源与副本

| 位置 | 角色 | 丢失后的处理 |
| --- | --- | --- |
| `config/opencode/cli.json` | TUI 偏好真源，入 git | `git status` / `git log` 确认；不要用 live 文件覆盖 |
| `config/global-AGENTS.md` | 全局规则真源，入 git | 同上 |
| `plugins/<name>/` | 插件真源，入 git | 用链接脚本重建 Junction / symlink |
| `~/.config/opencode/cli.json` | 实际生效副本 | 先备份 live，再从真源恢复 |
| `~/.config/opencode/plugins/<name>` | 指向仓库插件的链接 | 重新建链 |
| `~/.config/opencode/AGENTS.md` | 实际生效副本 | 从真源恢复 |
| `~/.zcode/AGENTS.md` | 指向 OpenCode 副本的 symlink | 副本恢复后通常自动可解析；仍悬空时重建 |

判断原则：仓库文件有 git 历史且 `git status` 干净时，以仓库为真源。OpenCode 在配置丢失后可能重新生成最小默认 `cli.json`（例如只剩 `$schema` 和 `tabs`），这类文件不是仓库真源。

## 常见现象与判断

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `cli.json` 只剩几十字节，或只有 `$schema` 与 `tabs` | 原文件被移除后，OpenCode 重新生成默认配置 | 备份 live，再从 `config/opencode/cli.json` 恢复 |
| `plugins/` 目录不存在，或插件显示未装载 | 配置目录被重置，链接未重建 | 跑 `link-plugins.ps1` / `link-plugins.sh`，再用 `-VerifyOnly` / `--verify-only` 核对 |
| `AGENTS.md` 缺失，`~/.zcode/AGENTS.md` 悬空 | OpenCode 副本缺失，ZCode symlink 指向它 | 恢复 `AGENTS.md`；悬空链接可重建 |
| harness 侧实体 skill 目录消失，出现 `~/.skills-migration-backup/<时间戳>/...` | 链接脚本把实体替换为 Junction / symlink 时的正常备份 | 不是配置丢失；确认备份内容后再决定是否删除 |

## 恢复步骤

### Windows

```powershell
# 只读核对：仓库真源、live 文件与插件链接
git status --short -- config/opencode/cli.json config/global-AGENTS.md plugins
Get-Item "$env:USERPROFILE\.config\opencode\cli.json" -ErrorAction SilentlyContinue
Get-ChildItem "$env:USERPROFILE\.config\opencode\plugins" -ErrorAction SilentlyContinue

# 从真源恢复 cli.json，并重建插件链接与 AGENTS.md
powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 -ApplyRecommendedCli -SkipRecommendedSkills -SkipThirdPartySkills -SkipDepCheck -SkipSubmodules

# 分别验证插件链接与运行态
powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1 -VerifyOnly
```

`-ApplyRecommendedCli` 是恢复 `cli.json` 的关键；只跑默认部署或带 `-SkipRecommendedCli` 时，`cli.json` 不会被改写。`apply_recommended_cli` 会先把现有 live 文件备份为同目录 `cli.json.bak-<时间戳>`。

### Linux / macOS

```bash
# 只读核对：仓库真源、live 文件与插件链接
git status --short -- config/opencode/cli.json config/global-AGENTS.md plugins
ls -l "$HOME/.config/opencode/cli.json" 2>/dev/null
ls -l "$HOME/.config/opencode/plugins" 2>/dev/null

# 从真源恢复 cli.json，并重建插件链接与 AGENTS.md
./scripts/deploy.sh --apply-recommended-cli --skip-recommended-skills --skip-third-party-skills --skip-dep-check --skip-submodules

# 分别验证插件链接与运行态
./scripts/link-plugins.sh --verify-only
```

## 恢复后验证

PowerShell：

```powershell
$repoCli = (Resolve-Path 'config/opencode/cli.json').Path
$liveCli = "$env:USERPROFILE\.config\opencode\cli.json"
(Get-Content -LiteralPath $repoCli -Raw -Encoding UTF8) -eq (Get-Content -LiteralPath $liveCli -Raw -Encoding UTF8)

$repoAgents = (Resolve-Path 'config/global-AGENTS.md').Path
$liveAgents = "$env:USERPROFILE\.config\opencode\AGENTS.md"
(Get-Content -LiteralPath $repoAgents -Raw -Encoding UTF8) -eq (Get-Content -LiteralPath $liveAgents -Raw -Encoding UTF8)
```

Bash：

```bash
cmp -s config/opencode/cli.json "$HOME/.config/opencode/cli.json" && echo cli-ok
cmp -s config/global-AGENTS.md "$HOME/.config/opencode/AGENTS.md" && echo agents-ok
```

ZCode 链接：

```powershell
Get-Item "$env:USERPROFILE\.zcode\AGENTS.md" -ErrorAction SilentlyContinue |
  Select-Object LinkType, Target
```

```bash
readlink "$HOME/.zcode/AGENTS.md"
```

插件以 `link-plugins` 的校验结果为准：链接正常且日志显示插件已装载，才算恢复完成。只看到目录存在或被链接，不等于运行态已装载。

## 不要做什么

- 不要把 live 的最小 `cli.json` 复制回 `config/opencode/cli.json`；先看 `git status` 与 `git log`。
- 不要用 `-SkipRecommendedCli` / `--skip-recommended-cli` 做恢复；它会明确跳过 `cli.json`。
- 不要只跑 `link-plugins` 就认为三件配置都恢复了；`cli.json`、`plugins/`、`AGENTS.md` 分别验证。
- 不要把 `link-skills -VerifyOnly` 的“全部链接正常”当作 AGENTS.md 或 cli.json 已恢复；该命令只校验链接与推荐/第三方 skill。`AGENTS.md` 用 `deploy.ps1 -VerifyOnly` / `deploy.sh --verify-only` 或本文的内容对比核对。
- 不要在未确认备份前删除 `~/.skills-migration-backup/`；实体 skill 目录被替换为链接时，旧内容可能只在这里。
- 不要用 `link-skills -Unlink` / `--unlink` 做恢复；它只移除链接，不恢复配置。
- 不要整目录回滚 `~/.config/opencode`；`service.json` 的 `password` / `port` 属于当前服务实例，只恢复缺失的 `cli.json`、`AGENTS.md` 与插件链接。
- 不要把 `service.json`、`auth.json` 当普通配置提交或跨机复制；密钥与登录态不在本文范围。

## 备份位置

| 备份 | 来源 |
| --- | --- |
| `~/.config/opencode/cli.json.bak-<时间戳>` | `apply_recommended_cli` 覆盖前自动备份 |
| `~/.skills-migration-backup/<时间戳>/<harness>/<skill>/` | `link-skills` 把实体目录替换为链接前备份 |
| `~/.skills-migration-backup/<时间戳>/opencode-plugins/<name>/` | `link-plugins` 把实体插件目录替换为链接前备份 |
| `~/.zcode/AGENTS.md.bak-<时间戳>` | ZCode 迁移时可能留下的普通文件备份，不由本仓库脚本统一管理 |

备份只用于人工核对；确认 live 已恢复且不再需要旧内容后再手工清理。
