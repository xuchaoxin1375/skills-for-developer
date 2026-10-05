---
name: skill-authoring-sync
description: >
  在 agent harness 中新建自定义 skill 并同步到真源仓库集中管理。
  当用户要求新建 skill、询问是否建议创建skill时给出肯定回答、把 skill 安装到 harness、或复盘/同步/分发/校验已有 skill 时使用此 Skill。
---

# Skill 新建与真源同步规范

你是负责 skill 全生命周期的工程师：新建、评审、分发、同步，所有操作可审计、可回放。

**核心原则：真源唯一、无副本**。实体只存真源仓库
`skills-for-developer/skills/<skill-name>/`；各 harness 侧一律放
**链接**（Windows Junction、Linux symlink），不存实体。任何修改直接改真源，
改完即对本机所有 harness 生效；跨机器靠 `git push/pull` 同步实体，
每台机器跑一遍自己平台的链接脚本即可。

**适用范围**：各 agent harness（OpenCode / Codex / Claude）的自定义 skill。
分发与校验统一走仓库 `scripts/` 下的链接脚本，不手写零散命令。

---

## 目录与命名约定

真源布局（一个 skill 一个目录）：

```text
skills-for-developer/
  skills/
    <skill-name>/
      SKILL.md                 # 必需：frontmatter + 正文
      references/              # 可选：长篇参考材料
      scripts/                 # 可选：配套脚本
  scripts/
    link-skills.ps1            # Windows：创建 / 校验 / 移除 Junction（幂等）
    link-skills.sh             # Linux/macOS：创建 / 校验 / 移除 symlink（幂等）
```

- 必须：`<skill-name>` 使用 kebab-case 小写英文（如 `scripting-best-practices`）。
- 必须：`SKILL.md` 以 frontmatter 开头，含 `name`（与目录名一致）与
  `description`（写清触发条件：什么请求下加载本 skill）。
- 必须：新增/修改 skill 时同步更新仓库 `README.md` 的“Skill 目录”检索表，
  两处语义保持一致。
- 推荐：正文按“适用范围 → 工作流程 → 约束/规范 → 自检 → 验证协议”组织；
  正文即工件，不套嵌套代码围栏，不夹带安装教程与链接聚合。

## 工作流程

### 新增 skill

1. **确认需求**：skill 名称、description 触发条件、适用范围与例外；全新编写还是从现有文档改造。
2. **写真源**：在 `skills/` 下新建目录 + `SKILL.md`，目录须含 `SKILL.md`
  （链接脚本只处理含 `SKILL.md` 的目录，缺失者警告跳过）。
3. **更新索引**：在仓库 `README.md` “Skill 目录”表追加一行（一句话说明 + 关键词）。
4. **本机分发**：Windows 跑 `scripts\link-skills.ps1`（可先 `-VerifyOnly` 预检，
   可用 `-Include <name>` 只处理新 skill）；Linux 跑 `./scripts/link-skills.sh`。
5. **验证同步**：链接脚本全量 `-VerifyOnly` 通过；skill 在 harness 可见/可加载。
6. **跨机器**：`git push` 推实体；其他机器 `pull` 后跑一遍自己平台的链接脚本。
   **不要把链接本体提交到 git**。

### 修改 skill

直接改真源实体，改完即对本机所有 harness 生效，无需重新链接；
跨机器用 `git push/pull` 同步。改后同步更新 `README.md` 检索表（如语义变化）。

### 删除 skill

1. 先运行链接脚本 `-Unlink` / `--unlink`（或手工删各 harness 下对应链接），再删仓库目录。
2. 必须：删链接只删链接不删实体——Windows 用 `Remove-Item <junction>`
  （不要加 `-Recurse`），Linux 用 `rm <symlink>`（不要加 `-r`，路径末尾不要加 `/`）。

### 评估过程产物

skill-creator 评估循环的过程产物（`outputs/`、`benchmark.json`、`review.html`
等 `*-workspace/` 目录）**禁止**放入 `skills/` 下：链接脚本只处理含
`SKILL.md` 的目录，无 `SKILL.md` 者每次运行告警；且过程产物不是 skill 实体，
不许进入真源 git 同步。

统一放仓库根 `.workspaces/<skill-name>-workspace/`（已在 `.gitignore` 忽略，
本地独占、不提交、不跨机器同步）。留到 skill 稳定作为回归基线（改 skill 时
以前次输出为 baseline 跑下一 iteration），结论过时后整目录删除。

### 副本漂移处理

harness 侧出现**实体目录**（非链接）即视为漂移：链接脚本会自动将其备份到
`~/.skills-migration-backup/<时间戳>/<harness>/<name>`（备份移出 skills 目录，
避免被 harness 误扫为重复 skill），再替换为正确链接。备份确认无误后手工删除。
备份目录永不纳入版本控制。

## 验证协议

1. Windows：`scripts\link-skills.ps1 -VerifyOnly` 全量通过；
   Linux：`./scripts/link-skills.sh --verify-only` 全量通过。
2. 新 skill 在 harness 中可见/可加载（出现在可用 skill 列表即算通过）。
3. 抽查正文：描述的触发条件在对应请求下能命中加载。
4. `git status` 确认无链接本体被误暂存。

## 红线

- 不把 harness 链接本体提交到 git；`git add` 只点名实体文件。
- `git commit/push` 必须用户明确指示才做。
- 不在 harness 侧手工存放实体副本；所有改动走“真源 → 链接生效”单向流动。
