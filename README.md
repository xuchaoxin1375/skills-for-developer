# skills-for-developer

本地 skills 唯一真源仓库（跨平台：Windows + Linux 共用）。实体只存这里，各 agent harness 侧通过链接引用，不存副本（Windows 用 **Junction**，Linux 用 **symlink**）。

## 目录结构

```text
skills-for-developer/
  skills/
    doc-polish-zh/              # 原 opencode
    scripting-best-practices/   # 原 opencode
    resilient-browser-fetch/    # 原 codex
    htmlmini/                   # 原 claude
  scripts/
    link-skills.ps1             # Windows：创建 / 校验 / 移除 Junction（幂等）
    link-skills.sh              # Linux/macOS：创建 / 校验 / 移除 symlink（幂等）
  .gitattributes                # 锁定 .sh/.ps1/.py 为 LF，防跨平台换行问题
  LICENSE                     # MIT，宽松开源
  README.md
```

每个 skill 目录必须包含 `SKILL.md` (及该 skill 自带的 `references/`、`scripts/` 等)。

## Skill 目录（检索入口）

| Skill 目录 | 一句话说明 | 关键词 / 何时用 |
|---|---|---|
| `skills/doc-polish-zh` | 中文技术/业务文档全面改写与质量提升：不改变原意，正式化、规范化、严谨化、清晰化，补充结构、示例、表格与 Mermaid 图 | 润色、改写、审校、优化文档、【原文】 |
| `skills/scripting-best-practices` | Shell (Bash) 与 Python 脚本的编写、审查与重构规范，生产级健壮性要求 | 写脚本、审脚本、重构 `.sh` / `.bash` / `.py`、排查脚本健壮性 |
| `skills/resilient-browser-fetch` | 采集受反爬保护的网站：Scrapling 过 Cloudflare 挑战、可选 CloakBrowser CDP 浏览器，保存渲染后 HTML、截图与诊断元数据，中文输出 | 反爬、Cloudflare、Turnstile、抓取、采集、代理连通性、会话复用 |
| `skills/htmlmini` | 网页核心骨架提取：先剥离 CSS/JS/冗余（省约 97–99% token）再总结、分析、审查 HTML 或 URL | html、网页、页面、设计稿、面板、仪表盘、总结、分析、审查 |

> 约定：`SKILL.md` 头部的 `description` 是 agent 侧的触发依据；上表是给人看的检索入口，两处语义保持一致，改 skill 时同步更新。

## Harness 映射（Win / Linux 路径同构，只是家目录写法不同）

| Harness  | Windows skills 目录 | Linux skills 目录 | 说明 |
|---|---|---|---|
| OpenCode | `%USERPROFILE%\.config\opencode\skills` | `~/.config/opencode/skills` | 全量链接 4 个 skill |
| Codex | `%USERPROFILE%\.codex\skills` | `~/.codex/skills` | 全量链接; 自带的 `.system/`、`AGENTS.md` 等原样保留, 脚本不碰 |
| Claude | `%USERPROFILE%\.claude\skills` | `~/.claude/skills` | 全量链接 |

## 链接方式：Junction（Win）/ symlink（Linux）

- skill 都是目录。Windows 用 Junction（无需管理员权限，`New-Item -ItemType Junction`）；Linux 用 symlink（`ln -s`，无权限要求）。
- 对读取方透明：Node / Python 的常规文件读取会直接穿透。
- 链接目标是**本机绝对路径**，两台机器的仓库路径可以不同（如 Win 下 `C:\repos\...`、Linux 下 `~/repos/...`）。同步靠 git 传实体，每台机器 clone 后跑一遍自己平台的链接脚本即可。**不要把链接本体提交到 git**。

## 常用操作

Windows（PowerShell）：

```powershell
# 全量链接 (首次迁移 / 新增 skill / 换机器后恢复, 幂等)
powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1

# 只检查, 不修改
powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -VerifyOnly

# 只处理部分 skill
powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -Include doc-polish-zh,htmlmini

# 移除本仓库创建的链接 (实体不受影响)
powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -Unlink
```

Linux：

```bash
# 先把仓库同步过去（以 remote 为准，两边推拉即可；路径不必与 Windows 一致）
git clone <remote-url> ~/repos/skills-for-developer
cd ~/repos/skills-for-developer

# 全量链接（幂等）
./scripts/link-skills.sh

# 只检查 / 只处理部分 / 移除
./scripts/link-skills.sh --verify-only
./scripts/link-skills.sh --include doc-polish-zh,htmlmini
./scripts/link-skills.sh --unlink
```

## 日常工作流

1. 改 skill: 直接改仓库里的 `skills/<name>/`，改完即对**本机**所有 harness 生效, 无需重新链接；跨机器用 `git push/pull` 同步。
2. 新增 skill: 在 `skills/` 下新建目录 + `SKILL.md`, 然后在**每台机器**上运行一次该平台的链接脚本。
3. 删除 skill: 先运行 `-Unlink` / `--unlink` (或手工删除各 harness 下对应链接), 再删仓库目录。注意删除链接只删链接不删实体：Win 用 `Remove-Item <junction>`（不要加 `-Recurse`），Linux 用 `rm <symlink>`（不要加 `-r`，且路径末尾不要加 `/`）。
4. 原位置的实体在首次替换为链接时会自动备份到 `~/.skills-migration-backup/<时间戳>/<harness>/<name>`（Win 下即 `%USERPROFILE%\.skills-migration-backup\...`），备份移出 skills 目录是为了避免被 harness 误扫为重复 skill，确认无误后可手工删除备份。

## 迁移记录

- 2026-09-27: 从本机迁入 4 个用户 skill (文件数: doc-polish-zh 1、scripting-best-practices 1、resilient-browser-fetch 21、htmlmini 1), 哈希校验一致后原位置替换为指向本仓库的 Junction。Codex `.system/` 等 harness 自带内容未纳入。

## 开源许可

MIT（见 `LICENSE`），可自由使用、修改、分发，保留版权声明即可。
