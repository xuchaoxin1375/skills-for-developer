# skills-for-developer

本地 skills 唯一真源仓库（跨平台：Windows + Linux 共用）。实体只存这里，各 agent harness 侧通过链接引用，不存副本（Windows 用 **Junction**，Linux 用 **symlink**）。

## Skill 目录（检索入口）

真源布局：`skills/<skill-name>/`（一个目录一个 skill，必须包含 `SKILL.md`，可带自有的 `references/`、`scripts/` 等）；`scripts/` 放链接脚本，`docs/` 放协作说明，`.workspaces/` 放本地评估产物（git 忽略，不提交）。

| Skill 目录 | 一句话说明 | 关键词 / 何时用 |
|---|---|---|
| `skills/doc-polish` | 技术/业务文档全面改写与质量提升：不改变原意，正式化、规范化、严谨化、清晰化，补充结构、示例、表格与 Mermaid 图（原名 doc-polish-zh，已去语言限定） | 润色、改写、审校、优化文档、【原文】、polish、rewrite、proofread、edit、improve docs |
| `skills/scripting-best-practices` | Shell (Bash) 与 Python 脚本的编写、审查与重构规范，生产级健壮性要求（原 opencode） | 写脚本、审脚本、重构 `.sh` / `.bash` / `.py`、排查脚本健壮性 |
| `skills/resilient-browser-fetch` | 采集受反爬保护的网站：Scrapling 过 Cloudflare 挑战、可选 CloakBrowser CDP 浏览器，保存渲染后 HTML、截图与诊断元数据，中文输出（原 codex） | 反爬、Cloudflare、Turnstile、抓取、采集、代理连通性、会话复用 |
| `skills/htmlmini` | 网页核心骨架提取：Defuddle→Trafilatura(可选)→semantic→UI清单自动回退，省约 75–99% token；CLI+MCP双形态（原 claude） | html、网页、页面、设计稿、面板、仪表盘、总结、分析、审查 |
| `skills/skill-authoring-sync` | agent harness 新建自定义 skill 并同步到真源仓库：真源唯一、链接分发、跨机器 git 同步 | 新建 skill、安装 skill、同步 skill、链接校验、真源管理 |
| `skills/repo-governance` | 开源仓库规范治理与安全提交：脚手架清单、LICENSE 选型、行尾归一化、隐私红线、提交分支门禁 | 新建仓库、规范化改造、提交检查、CONTRIBUTING、CI、审计密钥 |
| `skills/tech-learning-research` | 技术话题系统讲解、联网调研与选型推荐：搜索先行、方案权衡、详略与深度分级 | 学习、技术调研、方案对比、选型推荐、research、tutorial、comparison |
| `skills/markdown-style` | Markdown 行文风格与排版规范（正本）：只改形式不改实质，标题/列表/表格/代码块/Mermaid 统一用法；文档合并与多文档整合定稿后走本规范收尾 | 排版、风格迁移、规范格式、统一标题、markdown lint、format、文档合并、文档整合、章节合并、统稿 |
| `skills/lightweight-app-builder` | 模糊小工具需求落成轻量跨平台可交付程序：分诊代决策、形态判定、技术选型、打包签名分发，六步流程 | 做个工具、写脚本、小软件、CLI、桌面应用、技术选型、打包分发 |
| `skills/frontend-design` | Web/桌面小工具界面设计：布局栅格、渐进式披露、响应式、克制动效、可用性铁律，独立使用不依赖 builder，三断点截图交付验收；存量缺陷深查转 frontend-ux-qa | 界面丑、布局乱、美化、适配手机、加载动画、新建改版、交付验收、可用性、UX |
| `skills/frontend-ux-qa` | 存量前端 UI 缺陷诊断与验收门禁：`L/C/S/V/A/F/N/I/D/P/G/H` 编号体系，现象→根因→修复→验收，溢出/CLS 脚本与 DoD 可进 CI | 布局溢出、横向滚动、缺陷诊断、UI 验收门禁、axe、DoD、AGENTS.md UI 约束、CI 拦截 |
| `skills/arena-preview` | arena.ai 项目包预览：解压指纹、后台运行、主题与核心文件分析、一屏预览报告 | 预览项目包、arena 交付、解压运行、主题分析、跑起来看看 |
| `skills/distinctive-design-director` | 有辨识度的视觉方向与品味主导的点评打磨：外部种子发散、设计简报收敛、只看成品评审、删减去模板味 | 设计灵感、审美方向、视觉风格、情绪板、视觉发散、界面点评、去模板化、去除AI味、design inspiration、UI critique |
| `skills/powershell-pitfalls` | PowerShell 5.1/pwsh 常见错误排查：静默失败、退出码、编码乱码与 BOM、引号插值、别名冲突、Junction 误删 | powershell报错、pwsh报错、脚本没输出、退出码、中文乱码、BOM、引号转义、别名冲突、junction、troubleshooting |
| `skills/agentic-web-search` | 智能体联网搜索优化：时间锚定、探测查询、迭代扩词、来源分级与交叉验证、知识冲突与假前提裁决、预算控制与输出规范，含工具参数与评测参考 | 联网搜索、搜索优化、检索词陈旧、信息过时、知识冲突、假前提、交叉验证、来源分级、搜索预算、引用不实、web search |
| `skills/web-animation-guide` | Web动画应用指导：选型、性能与无障碍落地，原生优先，零依赖片段与回退写法 | web动画、WAAPI、滚动驱动、View Transitions、GSAP、reduced-motion、动效卡顿 |
| `skills/adaptive-responsive-guide` | Web前端自适应响应式适配指南：视口断点、媒体/容器查询、clamp流体、Flex/Grid内在布局、响应式图片、偏好与触控、国内vw适配、操作区收纳决策与验收 | 自适应、响应式、适配指南、媒体查询、容器查询、clamp、dvh/svh、按钮放不下、窄屏溢出、横向滚动、触控目标、主操作菜单、选中浮层 |
| `skills/sticky-position` | CSS `position: sticky` 粘性定位实现规范：三句心智模型、七种场景标准写法、六类失效根因排查、sticky/fixed 选型、兼容降级与无障碍上线清单 | 吸顶、吸底、吸附、置顶导航、表头冻结、粘性侧栏、分组标题顶走、层叠卡片、抽屉切侧栏、sticky 不生效/粘不住、滚动到某处停住、scroll-padding、overflow 劫持、诊断脚本、is-stuck 哨兵 |
| `skills/ai-verified-delivery` | AI 编程质量与可验证交付：统一风险分级、验证门禁与防假通过、证据版本绑定、完整性检查、交接恢复、独立复核及适用发布回滚；咨询与验收分模式 | AI coding 质量、做一半、验收标准、门禁、verify、DoD、L0-L4 定级、风险评分、RTM、tasks、独立验证、完成报告、回滚、弱模型约束 |
| `skills/admin-console-design` | 后台控制台设计与实现：默认fable整体主题或完整局部模板，按需补sonnet列宽/撤销与gpt导入/验收；附设计与交互功能目录、源码、依赖边界与预览快照，默认继承设计并接业务，标明参考缺口 | 后台面板、管理后台、admin、console、dashboard、侧栏折叠悬停、列表编辑批量、设置页、向导、Cloudflare-inspired |
| `skills/skill-patcher` | 存量 skill 打补丁：实战复盘沉淀为增量条目，语言简练、不污染、项目无关、配人话例子 | 修补 skill、打补丁、沉淀教训、skill 措辞审查、去污染、项目无关性 |
| `skills/reference-to-skill` | 多份参考文档/模型报告提炼成 skill：贡献比较、证据分类、目标审查、冲突裁决、规则落点与验证；支持建议、新建和改进 | 多文档提炼、提取精华、参考资料转 skill、对比报告完善 skill、规则整合、reference to skill |
| `skills/codex-model-config` | Codex 接第三方/自定义模型：建 profile、写模型目录、窗口档位与工具字段（独立仓库，submodule 引用） | 接模型、自定义模型、第三方模型、model_providers、models.json、context window、profile、codex config |

> 约定：`SKILL.md` 头部的 `description` 是 agent 侧的触发依据；上表是给人看的检索入口，两处语义保持一致，改 skill 时同步更新。

## 维护文档

- [更新日志](CHANGELOG.md)：迁移历史与重要变更记录。
- [Skill 编写、提炼与维护协作](docs/skill-authoring-workflow.md)：`reference-to-skill`、社区版 `skill-creator`、`skill-patcher` 与 `skill-authoring-sync` 的职责、引用方式和维护取舍，含社区版/系统版区分与验证边界。

## Harness 映射（Win / Linux 路径同构，只是家目录写法不同）

| Harness  | Windows skills 目录 | Linux skills 目录 | 说明 |
|---|---|---|---|
| Agents 通用 | `%DSH_AGENTS_HOME%/skills`（默认 `%USERPROFILE%/.agents/skills`） | `${DSH_AGENTS_HOME:-~/.agents}/skills` | 全量链接；Pi 等标准兼容 harness 共用，第三方实体不动 |
| OpenCode | `%USERPROFILE%/.config/opencode/skills` | `~/.config/opencode/skills` | 全量链接 23 个 skill |
| Codex | `%USERPROFILE%/.codex/skills` | `~/.codex/skills` | 全量链接; 自带的 `.system/`、`AGENTS.md` 等原样保留, 脚本不碰 |
| Claude | `%USERPROFILE%/.claude/skills` | `~/.claude/skills` | 全量链接 |
| DeepSeek Harness | `%DSH_HOME%/skills`（默认 `%USERPROFILE%/.dsh/skills`） | `${DSH_HOME:-~/.dsh}/skills` | 全量链接；dsh 原生用户级（rank 高于通用位置） |

## 链接方式：Junction（Win）/ symlink（Linux）

- skill 都是目录。Windows 用 Junction（无需管理员权限，`New-Item -ItemType Junction`）；Linux 用 symlink（`ln -s`，无权限要求）。
- 对读取方透明：Node / Python 的常规文件读取会直接穿透。
- 链接目标是**本机绝对路径**，两台机器的仓库路径可以不同（如 Win 下 `C:/repos/...`、Linux 下 `~/repos/...`）。同步靠 git 传实体，每台机器 clone 后跑一遍自己平台的链接脚本即可。**不要把链接本体提交到 git**。

## 常用操作

Windows（PowerShell）：

```powershell
# 全量链接 (首次迁移 / 新增 skill / 换机器后恢复, 幂等)
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1

# 只检查, 不修改
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -VerifyOnly

# 只处理部分 skill
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -Include doc-polish,htmlmini

# 移除本仓库创建的链接 (实体不受影响)
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -Unlink
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
4. 原位置的实体在首次替换为链接时会自动备份到 `~/.skills-migration-backup/<时间戳>/<harness>/<name>`（Win 下即 `%USERPROFILE%/.skills-migration-backup/...`），备份移出 skills 目录是为了避免被 harness 误扫为重复 skill，确认无误后可手工删除备份。

5. 跑 skill-creator 评估时，过程产物（`outputs/`、`benchmark.json`、`review.html` 等 `*-workspace/` 目录）统一放仓库根 `.workspaces/<skill-name>-workspace/`（已在 `.gitignore` 忽略，本地独占）；**禁止**放入 `skills/` 下（链接脚本会对无 `SKILL.md` 目录告警，且过程产物不许进入真源同步）。留到 skill 稳定作回归基线，过时后整目录删除。

## 开源许可

MIT（见 `LICENSE`），可自由使用、修改、分发，保留版权声明即可。
