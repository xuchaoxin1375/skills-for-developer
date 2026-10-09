## 更新日志

记录本仓库的迁移历史与重要变更。后续仅记录影响使用或维护的变化，例如新增 skill、职责或触发条件调整、兼容性及治理变化；纯措辞或排版微调无需逐条记录。

### 未发布

- 新增 `local-env`（国内用户出网与下载偏好：镜像优先、代理次之、裸连兜底的回退流程，附本机实测环境；仅供参考，实际不一致时以实际为准）。

- `admin-console-design` 改为整体主题或完整局部模板复用：保留有依据的 fable 设计偏好，明确业务接线、依赖边界和参考缺口；归档三工程源码及哈希，同步 sonnet 舞台和 fable 侧栏修复后的预览/截图；补齐设计与交互功能目录，区分各稿的已实现、演示和占位能力。

### 历史记录

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
- 2026-10-08: `codex-model-config`（Codex 接第三方/自定义模型）以 submodule 接入：独立仓库 pin 文档链接化去重版本，克隆需 `--recurse-submodules`；两仓全局忽略 Codex 运行时产物 `agents/openai.yaml`（真源为 `SKILL.md`）；检索表与链接计数同步。
- 2026-10-08: `ai-verify-gates` 更名 `ai-verified-delivery`，定位为 AI 编程质量与可验证交付，涵盖规格验收、实现约束、验证门禁、独立复核及适用发布恢复；同步真源名称、检索入口、相关引用与三 harness 链接。
- 2026-10-08: 新增 `reference-to-skill`（多份参考文档/模型报告提炼复用规则：贡献比较、证据分类、冲突裁决、规则落点与验证），检索表与链接同步。
- 2026-10-08: 文档重组：迁移历史移出 README 入 `CHANGELOG.md`，新增 `docs/skill-authoring-workflow.md`（`reference-to-skill`/`skill-creator`/`skill-patcher` 与 `skill-authoring-sync` 协作分工）。
- 2026-10-08: `codex-model-config` submodule pin 至 `check_profile.py` 版本（手写第三方配置静态检查）；4 个 SKILL frontmatter YAML 合规修复；README 目录树补齐 22→23 个。
