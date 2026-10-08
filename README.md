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
  .workspaces/                  # 本地评估产物（git 忽略，不提交、不同步）
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
| `skills/markdown-style` | Markdown 行文风格与排版规范（正本）：只改形式不改实质，标题/列表/表格/代码块/Mermaid 统一用法；文档合并与多文档整合定稿后走本规范收尾 | 排版、风格迁移、规范格式、统一标题、markdown lint、format、文档合并、文档整合、章节合并、统稿 |
| `skills/lightweight-app-builder` | 模糊小工具需求落成轻量跨平台可交付程序：分诊代决策、形态判定、技术选型、打包签名分发，六步流程 | 做个工具、写脚本、小软件、CLI、桌面应用、技术选型、打包分发 |
| `skills/frontend-design` | Web/桌面小工具界面设计：布局栅格、渐进式披露、响应式、克制动效、可用性铁律，独立使用不依赖 builder，三断点截图交付验收；存量缺陷深查转 frontend-ux-qa | 界面丑、布局乱、美化、适配手机、加载动画、新建改版、交付验收、可用性、UX |
| `skills/frontend-ux-qa` | 存量前端 UI 缺陷诊断与验收门禁：`L/C/S/V/A/F/N/I/D/P/G/H` 编号体系，现象→根因→修复→验收，溢出/CLS 脚本与 DoD 可进 CI | 布局溢出、横向滚动、缺陷诊断、UI 验收门禁、axe、DoD、AGENTS.md UI 约束、CI 拦截 |
| `skills/arena-preview` | arena.ai 项目包预览：解压指纹、后台运行、主题与核心文件分析、一屏预览报告 | 预览项目包、arena 交付、解压运行、主题分析、跑起来看看 |
| `skills/distinctive-design-director` | 有辨识度的视觉方向与品味主导的点评打磨：外部种子发散、设计简报收敛、只看成品评审、删减去模板味 | 设计灵感、审美方向、视觉风格、情绪板、视觉发散、界面点评、去模板化、去除AI味、design inspiration、UI critique |
| `skills/powershell-pitfalls` | PowerShell 5.1/pwsh 常见错误排查：静默失败、退出码、编码乱码与 BOM、引号插值、别名冲突、Junction 误删 | powershell报错、pwsh报错、脚本没输出、退出码、中文乱码、BOM、引号转义、别名冲突、junction、troubleshooting |
| `skills/agentic-web-search` | 智能体联网搜索优化：时间锚定、探测查询、迭代扩词、来源分级与交叉验证、知识冲突与假前提裁决、预算控制与输出规范，含工具参数与评测参考 | 联网搜索、搜索优化、检索词陈旧、信息过时、知识冲突、假前提、交叉验证、来源分级、搜索预算、引用不实、web search |
| \skills/web-animation-guide\ | Web动画应用指导：选型、性能与无障碍落地，原生优先，零依赖片段与回退写法 | web动画、WAAPI、滚动驱动、View Transitions、GSAP、reduced-motion、动效卡顿 |
| `skills/adaptive-responsive-guide` | Web前端自适应响应式适配指南：视口断点、媒体/容器查询、clamp流体、Flex/Grid内在布局、响应式图片、偏好与触控、国内vw适配、操作区收纳决策与验收 | 自适应、响应式、适配指南、媒体查询、容器查询、clamp、dvh/svh、按钮放不下、窄屏溢出、横向滚动、触控目标、主操作菜单、选中浮层 |
| `skills/sticky-position` | CSS `position: sticky` 粘性定位实现规范：三句心智模型、七种场景标准写法、六类失效根因排查、sticky/fixed 选型、兼容降级与无障碍上线清单 | 吸顶、吸底、吸附、置顶导航、表头冻结、粘性侧栏、分组标题顶走、层叠卡片、抽屉切侧栏、sticky 不生效/粘不住、滚动到某处停住、scroll-padding、overflow 劫持、诊断脚本、is-stuck 哨兵 |
| `skills/ai-verify-gates` | AI 编程工程质量与可验证交付：风险分级定级、统一验证门禁、完整性防做一半、独立复核、发布回滚与闭环 | AI coding 质量、做一半、验收标准、门禁、verify、DoD、L0-L4 定级、风险评分、RTM、tasks、独立验证、完成报告、回滚、弱模型约束 |
| `skills/admin-console-design` | Cloudflare风格后台控制台设计：外壳侧边栏/数据表格/表单设置向导/令牌主题/响应式验收/收敛口径对照与Legacy反例，三工程提炼可直接复用 | 后台面板、管理后台、控制台、admin、console、dashboard、侧边栏折叠悬停、表格调宽批量、表单校验、设置页、向导、Cloudflare、反例、命令面板 |
| `skills/skill-patcher` | 存量 skill 打补丁：实战复盘沉淀为增量条目，语言简练、不污染、项目无关、配人话例子 | 修补 skill、打补丁、沉淀教训、skill 措辞审查、去污染、项目无关性 |

> 约定：`SKILL.md` 头部的 `description` 是 agent 侧的触发依据；上表是给人看的检索入口，两处语义保持一致，改 skill 时同步更新。

## Harness 映射（Win / Linux 路径同构，只是家目录写法不同）

| Harness  | Windows skills 目录 | Linux skills 目录 | 说明 |
|---|---|---|---|
| OpenCode | `%USERPROFILE%/.config/opencode/skills` | `~/.config/opencode/skills` | 全量链接 12 个 skill |
| Codex | `%USERPROFILE%/.codex/skills` | `~/.codex/skills` | 全量链接; 自带的 `.system/`、`AGENTS.md` 等原样保留, 脚本不碰 |
| Claude | `%USERPROFILE%/.claude/skills` | `~/.claude/skills` | 全量链接 |

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
- 2026-09-28: `markdown-style` 列表选型新增步骤顺序须用有序列表规则，禁用 `①②③` 序号，自检同步。
- 2026-09-28: `doc-polish` 与 `tech-learning-research` 新增英文专有名词配中文与来历说明规则（以 `ss` 为例）。
- 2026-09-28: `markdown-style` 新增标点与括号一节，默认使用英文括号（圆括号、方括号、花括号），自检与工作流程同步。
- 2026-09-28: `tech-learning-research` 新增成文前 Mermaid 门禁（候选图 `TODO` 清单加非线性、非重复、可承载三项），工作流程与自检同步；网络命令总览排障路径节删除与有序列表重复的线性顺序图。
- 2026-09-28: `tech-learning-research` 取证优先级新增引用链接格式规则，须用 `[标题](url)` 行内语法（括号紧贴，空格与括号编码），自检同步。
- 2026-09-28: `markdown-style` 行内标记新增反引号防滥用边界（仅代码字段命令路径用反引号，普通强调一律加粗），自检同步；`doc-polish` 图文对应由四条增至五条（默认会读图、只讲重点、禁空话），反引号与自检同步；`tech-learning-research` 示意图说明与风格快照同步。
- 2026-09-30: `markdown-style` 触发描述与适用范围纳入文档合并与多文档整合类任务（章节合并、附录并入正文、统稿后排版收尾），检索表同步。
- 2026-09-30: `frontend-design` 与小工具开发 skill 解耦（独立使用，技术栈只作输入），新增可用性铁律一节（状态可见、可撤销、防错优先等十二条），版本升至 1.2.0，检索表同步。
- 2026-10-01: `frontend-design` 全文中文化（SKILL.md、5个新建reference、DESIGN.md模板、scan.py注释；旧文件本就是中文），description改中文触发词，与检索表对齐。
- 2026-10-02: 新增 `distinctive-design-director`（差异化设计导演：外部种子发散、设计简报收敛、只看成品评审、删减去模板味，全中文），真源落 `skills/distinctive-design-director`，随链接脚本分发；`.agents` 侧实体副本按漂移处理（备份后替换为 Junction）。附带修复：`scripts/link-skills.ps1` 补 UTF-8 BOM——无 BOM 时 Windows PowerShell 5.1 按系统代码页解码含中文脚本会导致静默零输出（退出码 0），文档化调用方式失效；补 BOM 后 5.1/pwsh 均正常。
- 2026-10-02: 新增 `powershell-pitfalls`（PowerShell 5.1/pwsh 踩坑速查：静默失败、退出码、编码/BOM、引号插值、别名冲突、Junction 误删；案例全部来自本仓库真实排障证据），随链接脚本分发。
- 2026-10-03: 新增 `agentic-web-search`（智能体联网搜索优化：时间锚定、探测查询、迭代扩词、来源分级与交叉验证、知识冲突与假前提裁决、预算控制与输出规范），由 `prompts/ai联网` 两篇指南分析整合而成，含工具参数、提示词模板与评测参考三个 reference，随链接脚本分发。
- 2026-10-05: 新增 `adaptive-layout`（Web前端自适应布局设计与适配：收纳决策、容器查询实现、交互状态与验收清单，由卡片操作区案例提炼泛化），随链接脚本分发；确立评估产物治理规则：`*-workspace/` 禁入 `skills/`，统一放 git 忽略的 `.workspaces/` 作回归基线（记入 `skill-authoring-sync` 规范与日常工作流）。
- 2026-10-05: 新增 `sticky-position`（`position: sticky` 实现规范与失效排查，由 `web-learn/前端设计/粘性设计sticky` 的两份单文件教程与两个演示工程整合泛化，含 patterns / troubleshooting / compat-a11y 三个 reference），随链接脚本分发。
- 2026-10-06: `sticky-position` 复核补齐（对照自适应 demo 与 gpt6astra 单文件页）：诊断脚本升级为六步自动版、IO 哨兵与 scroll-state 给出完整代码、新增层叠卡片与响应式断点切换两种场景、表格 z-index 梯度与层叠上下文说明、安全区/dvh/打印等移动端细节。
- 2026-10-06: `ai-coding-quality` 更名 `ai-verify-gates`（名实统一：目录与 frontmatter `name` 一致），三 harness 链接同步切换为新名。
- 2026-10-07: 新增 `admin-console-design`（Cloudflare风格后台控制台：外壳侧边栏/表格/表单设置向导/令牌主题/响应式验收，三工程提炼），随链接脚本分发；`frontend-design` 接入后台控制台路由（骨架转交、表单细节引用 `admin-console-design/references/forms.md`）。
- 2026-10-07: `admin-console-design` 覆盖度审计补齐：收敛口径对照表（时序/列宽/切卡/z-index/圆角三工程分歧，修4处口径矛盾）、新增 `anti-patterns.md`（Legacy 四缺陷反例）、命令面板规范、Undo 快照实现、导入导出原子性、宽度验收工具、来源边界声明；并入"覆盖展开零位移"实证节。

## 开源许可

MIT（见 `LICENSE`），可自由使用、修改、分发，保留版权声明即可。
