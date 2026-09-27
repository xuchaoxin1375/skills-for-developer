# skills-for-developer

本地 skills 唯一真源仓库。实体只存这里,各 agent harness 侧通过 Windows **Junction** 引用,不存副本。

## 目录结构

```text
skills-for-developer/
  skills/
    doc-polish-zh/              # 原 opencode
    scripting-best-practices/   # 原 opencode
    resilient-browser-fetch/    # 原 codex
    htmlmini/                   # 原 claude
  scripts/
    link-skills.ps1             # 创建 / 校验 / 移除 Junction 的幂等脚本
  README.md
```

每个 skill 目录必须包含 `SKILL.md` (及该 skill 自带的 `references/`、`scripts/` 等)。

## Harness 映射

| Harness  | skills 目录 | 说明 |
|---|---|---|
| OpenCode | `%USERPROFILE%\.config\opencode\skills` | 全量链接 4 个 skill |
| Codex | `%USERPROFILE%\.codex\skills` | 全量链接; 自带的 `.system/`、`AGENTS.md` 等原样保留, 脚本不碰 |
| Claude | `%USERPROFILE%\.claude\skills` | 全量链接 |

## 为什么用 Junction

- skill 都是目录, Junction 是 Windows 原生目录链接, 无需管理员权限 / 开发者模式即可创建 (`mklink /J` / `New-Item -ItemType Junction`)。
- 对读取方透明: Node / Python 的常规文件读取会直接穿透。
- 限制: 必须是本地绝对路径, 不支持相对路径和单文件链接。本场景两者都满足 (目录 + 同机)。
- 如需跨机器同步仓库, 在新机器上重新执行链接脚本即可, 不要把 Junction 本体提交到 git。

## 常用操作

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

## 日常工作流

1. 改 skill: 直接改仓库里的 `skills/<name>/`, 改完即对所有 harness 生效, 无需重新链接。
2. 新增 skill: 在 `skills/` 下新建目录 + `SKILL.md`, 然后运行一次链接脚本。
3. 删除 skill: 先运行 `-Unlink` (或手工删除各 harness 下对应 Junction), 再删仓库目录。注意 `Remove-Item <junction>` 只删链接不删实体, 不要加 `-Recurse` 误操作。
4. 原位置的实体在首次替换为 Junction 时会自动备份到 `%USERPROFILE%\.skills-migration-backup\<时间戳>\<harness>\<name>` (移出 skills 目录, 避免被 harness 误扫为重复 skill), 确认无误后可手工删除备份。

## 迁移记录

- 2026-09-27: 从本机迁入 4 个用户 skill (文件数: doc-polish-zh 1、scripting-best-practices 1、resilient-browser-fetch 21、htmlmini 1), 哈希校验一致后原位置替换为指向本仓库的 Junction。Codex `.system/` 等 harness 自带内容未纳入。
