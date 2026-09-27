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
  README.md
```

每个 skill 目录必须包含 `SKILL.md` (及该 skill 自带的 `references/`、`scripts/` 等)。

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
