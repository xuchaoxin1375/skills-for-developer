# skills-for-developer

本地 skills 唯一真源仓库（跨平台：Windows + Linux 共用）。实体只存这里，各 agent harness 侧通过链接引用，不存副本（Windows 用 **Junction**，Linux 用 **symlink**）。

## 目录结构

```text
skills-for-developer/
  skills/
    doc-polish/                   # 文档改写与审校（原 doc-polish-zh，已去语言限定）
    scripting-best-practices/   # 原 opencode
    resilient-browser-fetch/    # 原 codex
    htmlmini/                   # 原 claude
    skill-authoring-sync/       # skill 新建与同步规范
    repo-governance/            # 开源仓库治理与提交规范
    tech-learning-research/     # 技术学习·信息调研·方案探索
    markdown-style/             # Markdown 行文风格与排版规范（风格正本）
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
| `skills/doc-polish` | 技术/业务文档全面改写与质量提升：不改变原意，正式化、规范化、严谨化、清晰化，补充结构、示例、表格与 Mermaid 图 | 润色、改写、审校、优化文档、【原文】、polish、rewrite、proofread、edit、improve docs |
| `skills/scripting-best-practices` | Shell (Bash) 与 Python 脚本的编写、审查与重构规范，生产级健壮性要求 | 写脚本、审脚本、重构 `.sh` / `.bash` / `.py`、排查脚本健壮性 |
| `skills/resilient-browser-fetch` | 采集受反爬保护的网站：Scrapling 过 Cloudflare 挑战、可选 CloakBrowser CDP 浏览器，保存渲染后 HTML、截图与诊断元数据，中文输出 | 反爬、Cloudflare、Turnstile、抓取、采集、代理连通性、会话复用 |
| `skills/htmlmini` | 网页核心骨架提取：Defuddle→Trafilatura(可选)→semantic→UI清单自动回退，省约 75–99% token；CLI+MCP双形态 | html、网页、页面、设计稿、面板、仪表盘、总结、分析、审查 |
| `skills/skill-authoring-sync` | agent harness 新建自定义 skill 并同步到真源仓库：真源唯一、链接分发、跨机器 git 同步 | 新建 skill、安装 skill、同步 skill、链接校验、真源管理 |
| `skills/repo-governance` | 开源仓库规范治理与安全提交：脚手架清单、LICENSE 选型、行尾归一化、隐私红线、提交分支门禁 | 新建仓库、规范化改造、提交检查、CONTRIBUTING、CI、审计密钥 |
| `skills/tech-learning-research` | 技术话题系统讲解、联网调研与选型推荐：搜索先行、方案权衡、详略与深度分级 | 学习、技术调研、方案对比、选型推荐、research、tutorial、comparison |
| `skills/markdown-style` | Markdown 行文风格与排版规范（正本）：只改形式不改实质，标题/列表/表格/代码块/Mermaid 统一用法 | 排版、风格迁移、规范格式、统一标题、markdown lint、format |

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
powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -Include doc-polish,htmlmini

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
./scripts/link-skills.sh --include doc-polish,htmlmini
./scripts/link-skills.sh --unlink
```

## 日常工作流

1. 改 skill: 直接改仓库里的 `skills/<name>/`，改完即对**本机**所有 harness 生效, 无需重新链接；跨机器用 `git push/pull` 同步。
2. 新增 skill: 在 `skills/` 下新建目录 + `SKILL.md`, 然后在**每台机器**上运行一次该平台的链接脚本。
3. 删除 skill: 先运行 `-Unlink` / `--unlink` (或手工删除各 harness 下对应链接), 再删仓库目录。注意删除链接只删链接不删实体：Win 用 `Remove-Item <junction>`（不要加 `-Recurse`），Linux 用 `rm <symlink>`（不要加 `-r`，且路径末尾不要加 `/`）。
4. 原位置的实体在首次替换为链接时会自动备份到 `~/.skills-migration-backup/<时间戳>/<harness>/<name>`（Win 下即 `%USERPROFILE%\.skills-migration-backup\...`），备份移出 skills 目录是为了避免被 harness 误扫为重复 skill，确认无误后可手工删除备份。

## 迁移记录

- 2026-09-27: 从本机迁入 4 个用户 skill (文件数: doc-polish-zh 1、scripting-best-practices 1、resilient-browser-fetch 21、htmlmini 1), 哈希校验一致后原位置替换为指向本仓库的 Junction。Codex `.system/` 等 harness 自带内容未纳入。
- 2026-09-27: 新增 skill-authoring-sync（skill 新建与真源同步规范，链接模型），随链接脚本分发。
- 2026-09-27: 新增 repo-governance（开源仓库治理与安全提交规范，模糊项已具体化），随链接脚本分发。
- 2026-09-27: htmlmini v2（实现体收进 `skills/htmlmini`，MCP 工具正名 `htmlmini_*` + 旧拼写别名，UI 清单按可访问语义重写，`--mode/--extractor/--completion`，`save_page` 产物 `.meta.json` 自动利用）。
- 2026-09-28: `doc-polish-zh` 更名 `doc-polish`（去语言限定，触发词同步放宽），harness 链接同步切换。
- 2026-09-28: 新增 tech-learning-research（技术学习·信息调研·方案探索），随链接脚本分发。
- 2026-09-28: 新增 markdown-style（Markdown 行文风格与排版规范，风格正本），随链接脚本分发。
- 2026-09-28: `doc-polish` 新增 mermaid 图文对应四条规则（只引可见文本、方位以渲染为准、逐件可指认、图例先行），自检追加对应两问。
- 2026-09-28: `markdown-style` 正文与换行新增中英文混排无需加空格规则，自检追加对应一项。

## 开源许可

MIT（见 `LICENSE`），可自由使用、修改、分发，保留版权声明即可。
