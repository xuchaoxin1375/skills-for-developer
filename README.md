# skills-for-developer

自有 skills 的唯一真源仓库（跨平台：Windows + Linux 共用）。自有实体在 `skills/`，上游实体独立管理；各 agent harness 侧通过链接引用，不存适配副本（Windows 用 **Junction**，Linux 用 **symlink**）。

## 日常 AI 编程先看这里

不必记全仓目录，也不必每次跑完全部流程。按当前问题选一个主入口，其他方法只补缺少的判断：

| 当前问题 | 主入口 | 不要顺带启动 |
|---|---|---|
| 想法还不清楚，先把方案问透 | 上游 `grill-me` → `grilling` | 讨论并留术语/决策时选 `grill-with-docs`；已有规格先复用 |
| 业务术语、状态或关系说不清 | 上游 `domain-modeling` | 只读术语表不启动建模，不批量改名 |
| 模块接口难用、薄包装太多、修改扩散 | 上游 `codebase-design` | 本地调用方不因此扩成全仓治理 |
| 明确要求测试驱动实现 | 上游 `tdd` | 不因引用而安装整套上游流程 |
| 需要测试覆盖、真实集成与回归 | [web-app-testing](skills/web-app-testing/SKILL.md) | 不另建验收等级或重复计划 |
| 难 bug 或性能回归需要定位 | 上游 `diagnosing-bugs` | 不凭猜测直接改实现 |
| 评审提交差异 | 上游 `code-review` | 未提交/暂存范围按本地快照约定另核；评审不等于验收 |
| 判断是否真的做完、证据是否足够 | [ai-verified-delivery](skills/ai-verified-delivery/SKILL.md) | 不重跑版本与范围匹配的评审/测试 |

跨模块工程约束和长期运行用 `swe-gov`，仓库配置用 `repo-gov`，配套文档用 `project-docs`；前端、网络与环境问题仍按下方领域索引选取。详细职责只在 [共用边界表](skills/web-app-testing/references/skill-boundaries.md)维护。

### 用户调用与模型调用

上表方法保持**模型可调用，也可由用户显式指定**；`grill-me`、`grill-with-docs` 保留上游的**用户调用入口**配置。调用类型不授予写入、费用或发布权限。元数据与 harness 差异见 [调用规则](skills/skill-authoring-sync/references/writing-for-agents.md#harness-调用差异)。

Matt 的 `to-spec`、`to-tickets`、`implement-spec` 等**用户调用流程入口**不由本仓库自动安装或替你启动；方法引用不能绕过显式调用意图。需要这类流程时再单独评估，不能因为入口没安装就强制装整包。

这八个 Matt skill（含 `tdd`）统一采用独立 clone + 精选链接，**上游原样管理，不再维护本地同名适配版或零散 CLI 安装**。选择、安装与更新见 [上游 skill](docs/upstream-skills.md)，来源版本及目录由 `config/upstream-skills.json` 维护；重合处只调整自有 skill。

## Skill 目录（检索入口）

真源布局：`skills/<skill-name>/`（一个目录一个 skill，必须包含 `SKILL.md`，可带自有的 `references/`、`scripts/` 等）；`scripts/` 放链接脚本，`docs/` 放协作说明，`.workspaces/` 放本地评估产物（git 忽略，不提交）。

仓库校验：`python scripts/check-skills.py` 检查结构/索引/路径红线；`python scripts/check-links.py` 检查 Markdown 相对链接与锚点；`python scripts/check-skill-deps.py` 按各 skill 的 `dependencies.json` 检查本机依赖，声明格式见 [skill 依赖声明](docs/skill-dependencies.md)。

提交前自检：`bash scripts/install-hooks.sh`（Windows：`powershell -File scripts/install-hooks.ps1`）启用 `.githooks/pre-commit`，每次提交自动跑结构检查与链接检查；`git commit --no-verify` 可临时跳过。

| Skill 目录                             | 一句话说明                                                                                                                                                                                                                                                                                  | 关键词 / 何时用                                                                                                                                                                                               |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `skills/doc-rewrite-review` | 文档实质改写、审校与多源合并；也承接基于充分材料的学习文档、教材与教程编写。区分实践教程与系统教材，按目标放置必要说明、必读概念单元和解释专题，同时检查阅读负担与学习结果；共享参考提供案例与可追溯依据，不套固定课程或把合并门禁用于局部修改 | 改写、审校、合并、学习文档、教材编写、教科书式、概念放置、必读概念单元、章节衔接、论证层次、[教学依据](skills/doc-rewrite-review/references/learning-design-foundations.md)、逆向设计、认知负荷、研究边界、编排策略、教程编写、充分资料、Diátaxis、[应用案例](skills/doc-rewrite-review/references/diataxis-cases.md)、学习路线、概念引入、定义与定理、目标活动评价对齐、理解对齐、最小工作模型、状态变化、状态表、同尺度快照、图表文分工、因果分析、读者能力、概念破循环、输出读法、检查点、迁移练习、提取练习、间隔应用、目录重整 |
| `skills/project-docs` | 按产物职责与实际发布部署需求规划、编写和验收项目文档，覆盖 README、契约、安装、调用、排障与恢复；项目学习文档的编排与跨篇衔接采用doc-rewrite-review的共享正本，不重复教学清单 | 写 README、补文档、文档缺口、快速开始、项目学习文档、共享教学参考、跨篇衔接、读者背景、CHANGELOG、ADR、Runbook、AGENTS.md、部署文档、CLI/API/SDK/配置参考、文档一致性、默认值漂移、状态自查、故障排查 |
| `skills/scripting-best-practices`    | Shell / Python / Node 脚本与小工具 CLI 的编写、审查与重构规范：快速失败、输入校验、`--help` 与退出码、长选项为主并给常用短选项、批量覆盖/下发的幂等与预检、长耗时操作的进度与提示、UTF-8 与跨平台换行、多脚本交付、功能衍伸面与完成定义（启用、状态、停用、卸载、文档验收）；语言细则按需读 `references/`（原 opencode） | 写脚本、审脚本、重构`.sh` / `.bash` / `.py` / `.mjs` / `.js`、Node CLI、排查脚本健壮性、UTF-8 编码默认、批量下发、覆盖写入、预检门禁、强制覆盖、幂等判定、长选项、短选项、--help、退出码、多脚本交付、进度提示、长时间无输出、部署脚本无响应、功能衍伸面、完成定义、依赖检查、启用状态、停用、卸载、回落、状态查询 |
| `skills/resilient-browser-fetch`     | 稳健网页采集：抓取需渲染页面、Cloudflare/Turnstile/Akamai 挑战页、拦截页与人工验证；按能力分层选 HTTP、Playwright/Patchright、Scrapling、指纹底座或有头浏览器，缺件降级；含会话复用、HTML 快照、浏览器依赖与图形环境排障；选路走 network-access（原 codex） | 反爬、Cloudflare、Turnstile、Akamai、SEC-CPT、SBSD、边缘封禁、Reference #、抓取、采集、挑战页、挑战窗口、404/410、会话复用、同站探针、HTML 快照、保存网页、图片保留 URL、离线存档、Scrapling 环境安装、Playwright、Patchright、CloakBrowser、nodriver、chrome-late、晚接入、接入时机、cdp-attach、接管浏览器、复用真实浏览器会话、软错误页、批量晚接入、控制面、真实浏览器会话复用、同类方案对比、DrissionPage、浏览器回收、AGPL、不做首跳选路 |
| `skills/htmlmini`                    | 网页核心骨架提取：URL／本地快照的摘要与取数，不整份读HTML；常规静态提取走短路径，复用快照，复杂渲染与排障按需读取；可用时优先于普通web_fetch，缺失可回退；选择器契约回原始DOM核对，写改页面归frontend-design/frontend-qa，批量采集归resilient-browser-fetch | HTML、网页、摘要、取数、表格、榜单、快照复用、轻量提取、渲染分流、web_fetch、采集侦查 |
| `skills/skill-authoring-sync` | 自定义 skill 真源、分发与跨机同步；第三方保持上游原样，现成 CLI 或独立 clone 精选链接，不保存同名适配版；调用方式与安装来源分开核对 | 新建/修改/安装/同步 skill、真源、上游原样、clone、精选链接、用户调用、模型调用、AGENTS.md 写作 |
| `skills/repo-gov`                     | 公开/私有仓库治理与安全提交：按用途选配 README、LICENSE、.gitignore/.gitattributes、CONTRIBUTING、SECURITY、行为准则与模板；提交前检查、密钥/大文件审计、分支与评审保护、CI 与依赖/构建供应链控制；应用架构转 swe-gov，文档内容转 project-docs | 初始化仓库、新建仓库、LICENSE、许可证选择、SECURITY、CONTRIBUTING、.gitignore、.gitattributes、提交检查、CI、分支保护、供应链、审计密钥、repo-gov、仓库治理 |
| `skills/swe-gov` | 长期应用的跨模块约束、数据/状态归属、契约兼容、运行恢复和维护；局部接口设计归 codebase-design，术语/ADR 记录归 domain-modeling，差异评审归 code-review | 工程治理、共享契约、状态归属、兼容迁移、异步任务、SLO、恢复、技术债、文档一致性、门禁设计 |
| `skills/tech-learning-research` | 话题系统讲解、调研与选型：先定产物、读者和成功判据，复用材料、按缺口取证再成文，按需核实工作机制；详略与证据状态独立，核心缺证不确定推荐，可分离缺口交限定范围结果；保留报告交付确认，学习文档编排采用共享教学正本，检索执行归agentic-web-search | 学习、学习文档、教材编写、编排策略、调研、方案比较、选型、做法盘点、工作机制、材料复用、证据缺口、限定范围、报告交付、research、tutorial、comparison |
| `skills/markdown-style` | 通用排版正本：纯排版只改形式，写作/改写可复用规则而不套内容零改动门槛；行内代码按位置处理管道符（正文不转义、表格优先数字实体），并优先英文、保留原样引用，教材编号按出版与交叉引用需要例外保留；区分可复制命令与终端记录，图示按需选用与验证，不公开空候选清单；skill指令内容按仓库写作规范 | 排版、风格迁移、格式复用、加粗、标题、教材编号、交叉引用、列表、表格、代码块、行内代码、管道符处理、HTML 实体、表格单元格、复制命令、终端记录、Mermaid、图示选择、状态表、状态快照、本地链接 |
| `skills/lightweight-app-builder`     | 模糊小工具需求落成轻量跨平台可交付程序：分诊代决策、形态判定、技术选型、打包签名分发，六步流程；与 repo-gov/swe-gov/ai-verified-delivery 分层组合，已有脚本的编写与重构规范转 scripting-best-practices | 做个工具、写脚本、小软件、CLI、桌面应用、技术选型、打包分发、轻量应用构建 |
| `skills/frontend-design`             | Web/桌面小工具界面设计：任务、页面结构、令牌、通用交互与整体交付；共用对比度与截图协议，局部验收优先特写；线框接入 adaptive-responsive-guide，动效设计查 motion.md、技术查 web-animation-guide，存量深查转 frontend-qa；页面代码/配置片段的高亮、行号与复制查 code-display.md                                                                   | 界面丑、布局乱、美化、适配手机、加载动画、文字/图标难辨、对比度、页面可读性、新建改版、交付验收、可用性、UX、代码高亮、行号、源码片段                                                                                                   |
| `skills/frontend-qa`              | 存量前端 UI 缺陷诊断与视觉验收：Playwright 用户流程、关键态视觉判断、对比度与可读性、溢出/CLS 及 DoD CI 门禁；截图工具和浏览器操作复用 browser-automation，测试用例与回归体系转 web-app-testing | 布局溢出、弹窗关闭、焦点回归、对比度、页面可读性、UI 截图验收、Agent 视觉理解、Playwright 流程验收、axe、DoD、CI 拦截 |
| `skills/browser-automation` | 本地浏览器与工具预检、路径定位、浏览器操作方案及测试运行器决策；指导交互、等待、下载与会话所有权，区分新建实例、接管已登录会话与托管浏览器，给出只读发现和含总期限/进程树回收的托管截图，保留旧 QA 截图 CLI 委托 | Chrome/Edge/Chromium、浏览器在哪、安装路径、Scoop、便携浏览器、普通浏览器与 Playwright、Puppeteer、Selenium、MCP、工具/框架选型、浏览器自动化、CDP、远程浏览器、接管已登录会话、浏览器归属、shot-quick、shot_scroll、截图卡住、进程残留、资源回收 |
| `skills/web-app-testing` | Web 测试覆盖、断言、真实 API/存储与浏览器回归、隔离和 CI 维护；可用的 tdd 管开发循环，code-review 管差异评审，ai-verified-delivery 管最终证据；共用计划不叠加流程 | 测什么、何时写测试、单元/组件/集成/E2E、Playwright、真实集成、Mock 边界、测试隔离、不稳定测试、CI |
| `skills/arena-preview`               | arena.ai 项目包预览：解压指纹、后台运行、主题与核心文件分析、一屏预览报告；展示截图用于验收时转共用协议                                                                                                                                                                                     | 预览项目包、arena 交付、解压运行、主题分析、跑起来看看                                                                                                                                                        |
| `skills/distinctive-design-director` | 有辨识度的视觉方向与品味主导的点评打磨：外部种子发散、设计简报收敛、只看成品评审、删减去模板味；落地实现转 frontend-design，存量缺陷与验收转 frontend-qa；对比度与截图行为复用共用规范 | 设计灵感、审美方向、视觉风格、情绪板、视觉发散、界面点评、去模板化、去除AI味、design inspiration、UI critique |
| `skills/shell-pitfalls`         | 外壳执行与排障（PowerShell 5.1/pwsh 7、bash/Git Bash，cmd.exe 仅回退）：选壳、编码、退出码、启动/profile、引号与路径、管道输出；含按用户视角模拟按键复验 Tab 补全与读屏；首次调用前加载，常规执行复用规则，原生 read 无需加载 | PowerShell、bash、Git Bash、cmd、首次调用、合并预检、UTF-8、退出码、NoProfile、管道、中文乱码、BOM、引号、Junction、交互验证、Tab补全、按键注入、读屏、共存干扰、ConPTY、MSYS、CRLF、winpty |
| `skills/agentic-web-search` | 联网搜索与证据核验：轻量入口，按主张覆盖而非按维度凑搜索，依据新线索或缺口迭代；保留次数、费用与限流边界；复杂协议按需读，报告范围与交付归tech-learning-research | 联网搜索、轻量查询、证据覆盖、材料复用、独立来源、官方核验、费用授权、预算、429、多跳、迭代、交叉验证 |
| `skills/harness-web-check`          | 模型在agent harness中的联网工具配置、实际下发与正确调用验收：区分配置/可见性/后端搜索/模型行为，分别核实工具入口、执行位置与底层搜索供应商；区分模型订阅、平台托管搜索与供应商原生工具，复用已有支持证据；先本地校验，不以收费请求试错；OpenCode优先、流程通用，按授权最小修复与复测；配置仅作本机案例，含换设备核对与免费账号/API key 代办边界；检索质量与网络选路分别归邻近skill | 搜索工具没配置好、联网工具检查、模型不调用搜索、假称已搜索、工具下发、模型/渠道切换后联网失效、搜索冒烟测试、harness搜索验收、设备本地配置、代办注册、API key 创建、托管搜索与CLI渠道归属 |
| `skills/web-animation-guide`         | Web动画技术实现：选型、示例、退出布局保持、中间帧验证、打断清理、兼容、性能与减弱动效；读取项目令牌，截图取景与查看复用共用协议；反馈目的与设计预算归 frontend-design，响应式布局归 adaptive-responsive-guide | web动画、WAAPI、滚动驱动、View Transitions、GSAP、reduced-motion、动效卡顿 |
| `skills/adaptive-responsive-guide`   | 响应式专项：视口/容器阈值、流体排版、Flex/Grid、响应式图片、窄屏操作区收纳、溢出与滚动、触控目标、深色与 reduced-motion 布局、范围化验收；纯视觉方向、存量深查、动效技术与页面整体设计分别归邻近 skill | 自适应、响应式、适配指南、媒体查询、容器查询、clamp、dvh/svh、按钮放不下、窄屏溢出、横向滚动、触控目标、操作区收纳、极窄视口 |
| `skills/sticky-position`             | CSS`position: sticky` 粘性定位实现规范：三句心智模型、七种场景标准写法、六类失效根因排查、sticky/fixed 选型、兼容降级与无障碍上线清单                                                                                                                                                     | 吸顶、吸底、吸附、置顶导航、表头冻结、粘性侧栏、分组标题顶走、层叠卡片、抽屉切侧栏、sticky 不生效/粘不住、滚动到某处停住、scroll-padding、overflow 劫持、诊断脚本、is-stuck 哨兵                              |
| `skills/ai-verified-delivery` | 规格/任务到最终证据的追踪、风险等级与交付状态；复用已有 spec/工单与有效评审，不重建同义流程；维护共用视觉证据政策，局部设计、访谈、测试和差异评审各归邻近方法 | 是否做完、证据不足、SDD、验收条件、交付定级、verify、DoD、RTM、视觉验收、发布恢复 |
| `skills/admin-console-design`        | 后台控制台设计与实现：默认沿用整体主题与页面结构，按需补列宽/撤销、导入校验与验收案例；附功能目录、源码、依赖边界与快照，默认继承设计并接业务，标明参考缺口；对比度与截图复用共用规范 | 后台面板、管理后台、admin、console、dashboard、侧栏折叠悬停、列表编辑批量、设置页、向导、Cloudflare-inspired |
| `skills/skill-patcher`               | 存量 skill 实战补丁：把真实漏验、误判或执行失败修成增量条目；一般写作审查按编写入口，内容与语言复用仓库规范                                                                                                                                                                                 | 实战复盘、修补 skill、真实逃逸、补丁措辞审查、去污染、项目无关性                                                                                                                                              |
| `skills/reference-to-skill`          | 一份或多份资料（文档/规范/报告）提炼成 skill：贡献比较、证据分类、目标审查、冲突裁决、规则落点与验证；支持建议、新建和改进，含是否值得沉淀的判断；本地提炼聚焦能力本身，不默认保留来源与指纹                                                                                                                                                       | 多文档提炼、单份资料转 skill、提取精华、参考资料转 skill、是否值得做成 skill、给 agent 的指南、对比报告完善 skill、规则整合、reference to skill                                                                                                                      |
| `skills/code-comments`              | 代码与配置注释编写、精简和审查：接口契约、实现意图、配置决策、工具指令、跨文件关联及维护条件；附Python docstring与Nginx示例 | 注释最佳实践、补充注释、清理冗余注释、过时注释、文档字符串、docstring、TODO、noqa、检查豁免、配置注释 |
| `skills/codex-model-config`          | Codex 接第三方/自定义模型：建 profile、写模型目录、窗口档位与工具字段；排查 web_search 不下发、模型不调用搜索与工具行为异常（独立仓库，submodule 引用） | 接模型、自定义模型、第三方模型、model_providers、models.json、context window、profile、codex config、web_search 不生效、模型不调用搜索、搜索工具不下发、standalone web.run |
| `skills/network-access`              | 外链抓取、下载与Git远端操作前选路：普通网页稳定可直连，国内Google／OpenAI与已知不稳站点优先代理，小页面直连约3–5秒仍无有效响应时考虑改路；GitHub按资源类型选已核验镜像／加速、代理或稳定直连，私有资源不交公共加速、推送走原站；按需读登记与同站观测，失败分流、包／浏览器下载与依赖安装分诊下沉参考 | 网络选路、稳定直连、慢直连、3–5秒、代理、GitHub、镜像加速、镜像可用性、代理可用性、Google、OpenAI、超时、403、5xx、429、Git、依赖下载、依赖冲突、pip安装失败、包管理器失败、scoop安装失败、uv、conda、pipx、工具链选型、wheel、PEP668、浏览器制品 |
| `skills/opencode-provider-config`    | 第三方 AI API 接入 OpenCode V2 及已有模型参数补全/审查：拉目录、核实模型规格与已知渠道差异，映射输入输出模态、工具、思考等级/预算与 variants、上下文/输入/输出上限；思考档位按上游公开完整集合配置，缩减依据见 references/model-parameters.md；多源脚本仅作线索，不猜填未知规格；写 providers、选 Responses/Messages 协议、持久化密钥与服务端代理（`HTTP_PROXY`/`NO_PROXY`、状态检查/设置/移除、走代理不生效排查，脚本 opencode_proxy.py），分开目录校验与按授权真实验证；搜索工具调用验收归 `harness-web-check`；细节见 references/model-parameters.md、references/service-env.md | 接入 opencode、自定义供应商、provider、中转站、NewAPI、第三方模型、模型参数、capabilities、模态、工具调用、reasoning、思考等级、effort、budget、variants、上下文窗口、limit、/v1/models、model_info.py、opencode_proxy.py、models.dev、baseURL、service set env、Responses、Messages、协议切换、走代理、HTTP_PROXY、HTTPS_PROXY、NO_PROXY、代理不生效、代理状态检查、移除代理、HPPTS_PROXY、地区限制 |
| `skills/mermaid-render-fix`          | Mermaid 渲染失败诊断与修复：提块复现 Parse error、修节点引号与转义、mmdc/kroki 复验回写；含规范化/兼容性体检（按最低目标版本选写法，象限图与架构图非 ASCII 文案引号、缺箭头、坐标越界、版本下限）；语法正本走 markdown-style | mermaid 渲染失败、Parse error、got SQS、图挂了、节点方括号、修图、复验、检查 mermaid、规范化 mermaid、兼容性、象限图报错、架构图报错、Lexical error、Unrecognized text |
| `skills/user-profile`                | 个人高频默认值：搜索渠道顺位（Tavily 通用首选 → harness 内置搜索 → anysearch 垂直备用 → 供应商托管搜索兜底），含多通道按任务分工、可用性判定与回退边界；配置只作本机案例，托管搜索不静默切换，行为约束不冒充配置硬禁用；含 Windows shell、路径和自建工具版本偏好，以及 skill 使用反馈（低效时提修补建议、用户确认后再改），由全局 AGENTS.md 在会话动手前加载；领域细则与跨任务授权各归其入口 | 常驻偏好、个人默认值、user-profile、全局偏好、动手前加载、搜索渠道、渠道顺位、多通道分工、回退边界、Tavily 通用搜索、harness 内置搜索、anysearch 垂直备用、托管搜索兜底、设备本地配置、Windows shell、路径、日期版本、skill 使用反馈、修补建议 |
| `skills/note-blog-archivist`         | 经验结论沉淀到本地笔记/博客仓库：定位笔记总目录、复用现有文档最小追加或按目录规则新建，省去手动归类；仅接单份已定稿内容，合并/改写不在此列                                                                                                                                                                                                                   | 存笔记、记一笔、沉淀经验、放到博客、经验库、归档笔记、笔记分类、并进现有笔记 |
| `skills/resource-inventory`          | 本机资源体检与复用：一次聚合当前会话环境、运行时版本、Python 解释器与引擎层、浏览器候选、代理环境变量/登记/实际入口、项目已有测试与包管理工具及已装证据；检测逻辑仍属各域 skill，本 skill 只做聚合与判读，避免重复安装和环境误判 | 本机有什么、环境探测、资源全景、避免重复安装、Python 环境在哪、浏览器在哪、代理入口、测试栈、换机器排查 |
| `skills/nodejs-runtime-setup`        | Node.js 运行时与 pnpm 安装：按单版本、多版本、团队锁版本选默认方案（官方安装器/winget、fnm、nvm-windows、Volta），区分二进制镜像、registry 与独立下载，给失败模式与回退；覆盖 PATH 冲突、符号链接权限、Corepack 移除后的 pnpm 安装与 EPERM；依赖镜像选路归 network-access | 安装 Node、装 Node.js、node 版本、切换 Node 版本、fnm、nvm-windows、nvm、Volta、pnpm 安装、corepack 不存在、Node 26、Windows 装 Node、国内镜像装 Node、PATH 多个 node、符号链接 1314、npm EPERM |
| `skills/cross-platform-binary-deploy` | 跨平台 CLI 二进制部署：按 OS/架构映射 release 资产、校验 SHA-256、安全解压、原子替换、PATH、版本固定与回滚；先判断何时改用包管理器，下载选路归 network-access | 二进制部署、release 资产、跨平台安装、GitHub Release、固定版本、SHA-256、校验、解压、原子替换、PATH、升级、卸载、回滚、无包管理器、包管理器版本旧 |

> 约定：`SKILL.md` 头部的 `description` 是 agent 侧的触发依据；上表是给人看的检索入口，两处语义保持一致，改 skill 时同步更新。

## 插件目录（检索入口）

真源布局：`plugins/<plugin-name>/`（一个目录一个插件，**入口必须是包根目录的 `index.ts`**）；
`scripts/link-plugins.ps1`（Windows，Junction）/ `scripts/link-plugins.sh`（Linux，symlink）
链接到 `~/.config/opencode/plugins/<name>`，OpenCode 自动发现该目录下的插件包。
装载规则（入口文件、发现路径、静默失败）、验证方法与"插件 vs skill"分工见
[插件制品](docs/plugins.md)。

| 插件目录                             | 一句话说明                                                                                                                                                                                                                        | 关键词 / 何时用                                                                                                                        |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `plugins/powershell-encoding-guard` | 把 `skills/shell-pitfalls` 的机械步骤前置到 OpenCode 的 shell 钩子：Windows + PowerShell 自动前置编码语句与 `PYTHONUTF8=1`；原生命令输出经文本层时只写诊断日志、**默认不改写工具输出**（追加提示需显式开 `appendNote`）；判断类规则仍由 skill 负责；自带诊断通道，确认当前会话是否被覆盖 | PowerShell 编码、乱码、shell 钩子、OpenCode 插件、编码前置、原生命令管道、PYTHONUTF8、native 输出落盘、诊断通道、location 路由、热重载、重复装载 |

## 维护文档

- [仓库维护入口](AGENTS.md)：供代理读取的短入口。
- [全局 AGENTS.md 真源](config/global-AGENTS.md)：会话入口、跨任务协作与授权底线；个人工具默认由 `user-profile` 维护，领域细则留在对应 skill。新机恢复与本机合并见下文，链接脚本不覆盖各 harness 的 AGENTS.md。
- [WSL 复用 Windows 侧 OpenCode 配置](docs/wsl-opencode-reuse.md)：完整配置（含模型配置）在 WSL 侧的复用范围、方式选型、密钥红线与验证（复用后默认不测活）；skill 分发仍走链接脚本。
- [Skill 仓库治理](docs/skill-governance.md)：规则归属、职责划分、变更流程与分级验证。
- [Skill 依赖声明与部署基线](docs/skill-dependencies.md)：`dependencies.json` 格式、检查命令与新机推荐依赖。
- [第三方 skill 推荐名单](config/third-party-skills.txt)：上游仓库、固定版本、升级保留文件；实体不入本仓库，部署时询问，按需同步。
- [独立 clone 的上游 skill](docs/upstream-skills.md)：Matt 方法/入口的原样管理、精选链接、新机恢复与更新；不与 CLI 或旧安装器重复接管。
- [插件制品（OpenCode 插件）](docs/plugins.md)：插件真源布局、链接分发、装载规则（入口文件/发现路径/静默失败/全局键占用/location 路由）、通用验证清单与 skill 分工。
- [Skill 内容与语言规范](docs/skill-content-guidelines.md)：约束强度、正文与参考落点、指令措辞、术语、例子和写作复核。
- 变更历史：直接看 `git log`；本仓库不维护独立 CHANGELOG，提交信息按 Conventional Commits 记录目的与影响。
- [Skill 编写、提炼与维护协作](docs/skill-authoring-workflow.md)：`reference-to-skill`、社区版 `skill-creator`、`skill-patcher` 与 `skill-authoring-sync` 的职责、引用方式和维护取舍，含社区版/系统版区分与验证边界。
- [Skill 触发评测](skills/skill-authoring-sync/references/trigger-eval.md)：正负例取样、子代理判定 prompt、判据、记录格式与案例库；改 description 时使用。
- [Skill 编写参考（格式、元描述与多 skill 冲突）](docs/skill-authoring-reference.md)：公开规范与客户端实现汇总、description 写法与触发评测入口、职责矩阵与冲突处置、保存位置、跨平台与评测指标；非规范正本。
- [skill-up 行为评测试点](docs/skill-up-pilot.md)：范围、用例、验收与决策规则；未纳入默认流程。
- [核心方法与测试的职责边界](skills/web-app-testing/references/skill-boundaries.md)：需求、建模、模块设计、开发循环、代码评审、测试与交付各自的维护位置；按需组合，复用计划与有效证据。
- [测试层、测试阶段与责任](skills/web-app-testing/references/coverage-and-layers.md#测试层测试阶段与责任)：区分测试层、开发侧验证与独立测试阶段；单元/组件/CI 通过不等于系统、验收或准出结论，独立复核也不等于独立测试。
- [测试资源预算与回收](skills/web-app-testing/references/environment-and-maintenance.md#测试资源预算与回收)：测试与验收先设容量、并发及期限，登记资源归属，验明异常回收再重试；web-app-testing、ai-verified-delivery与frontend-qa共用。
- [共用截图与视觉验收协议](skills/ai-verified-delivery/references/visual-acceptance.md)：截图触发、取景优先级、采集、实际查看与证据的唯一维护位置；相关 skill 引用，不各自维护完整截图规则。
- [浏览器安装与国内网络](skills/network-access/references/browser-installation.md)：Playwright/Scrapling 的包源、浏览器制品、系统依赖与启动验证；国内下载代理、镜像回退及缓存复用的共用入口。
- [依赖安装失败分诊](skills/network-access/references/dependency-install-recovery.md)：Python/Node 依赖冲突、无匹配 wheel、PEP 668、构建失败与镜像慢/超时的分阶段处理；包管理器失败时改走上游 Release 制品，重试预算与验证。
- [普通浏览器截图与 Playwright](skills/browser-automation/references/screenshot-workflow.md#普通浏览器与-playwright-的区别)：人工截图、自动化、测试运行器与资源托管的分工，已安装 Chrome/Edge 的复用及 CDP 会话边界。
- [查找已安装的浏览器](skills/browser-automation/references/browser-discovery.md)：只读列候选与显式自动选择，覆盖 Windows 注册表/Scoop、macOS 应用包及 Linux 常用目录，区分原生文件、包装器与沙箱安装。
- [浏览器工具与框架决策](skills/browser-automation/references/tool-and-framework-choice.md)：检查现有浏览器工具，选择控制库及测试运行器；含浏览器归属三态与接管已登录会话的取舍，自动化操作指导由 browser-automation 维护，测试设计沿用 web-app-testing。

## Harness 映射（Win / Linux 路径同构，只是家目录写法不同）

| Harness          | Windows skills 目录                                                   | Linux skills 目录                        | 说明                                                             |
| ---------------- | --------------------------------------------------------------------- | ---------------------------------------- | ---------------------------------------------------------------- |
| Agents 通用      | `%DSH_AGENTS_HOME%/skills`（默认 `%USERPROFILE%/.agents/skills`） | `${DSH_AGENTS_HOME:-~/.agents}/skills` | 全量链接；Pi 等标准兼容 harness 共用；第三方实体由 `third-party-skills.py` 管理 |
| OpenCode         | `%USERPROFILE%/.config/opencode/skills`                             | `~/.config/opencode/skills`            | 全量链接仓库中的 skill                                           |
| Codex            | `%USERPROFILE%/.codex/skills`                                       | `~/.codex/skills`                      | 全量链接; 自带的`.system/`、`AGENTS.md` 等原样保留, 脚本不碰 |
| Claude           | `%USERPROFILE%/.claude/skills`                                      | `~/.claude/skills`                     | 全量链接                                                         |
| DeepSeek Harness | `%DSH_HOME%/skills`（默认 `%USERPROFILE%/.dsh/skills`）           | `${DSH_HOME:-~/.dsh}/skills`           | 全量链接；dsh 原生用户级（rank 高于通用位置）                    |
| ZCode            | `%USERPROFILE%/.zcode/skills`（优先），回退 `%USERPROFILE%/.agents/skills` | `~/.zcode/skills`（优先），回退 `~/.agents/skills` | 只读取不建链，复用 Agents 通用行的链接；个别 skill 只想在 ZCode 内覆盖时放 `~/.zcode/skills`；全局 AGENTS.md 落 `~/.zcode/AGENTS.md`（见「全局 AGENTS.md 同步与合并」） |

## 链接方式：Junction（Win）/ symlink（Linux）

- skill 都是目录。Windows 用 Junction（无需管理员权限，`New-Item -ItemType Junction`）；Linux 用 symlink（`ln -s`，无权限要求）。
- 对读取方透明：Node / Python 的常规文件读取会直接穿透。
- 链接目标是**本机绝对路径**，两台机器的仓库路径可以不同（如 Win 下 `C:/repos/...`、Linux 下 `~/repos/...`）。同步靠 git 传实体，每台机器 clone 后跑一遍自己平台的链接脚本即可。**不要把链接本体提交到 git**。

## 常用操作

Windows（PowerShell）：

```powershell
# 一键部署（skill + 插件 + 全局 AGENTS.md + 依赖检查, 末尾打印效率复盘）
powershell -ExecutionPolicy Bypass -File scripts/deploy.ps1
powershell -ExecutionPolicy Bypass -File scripts/deploy.ps1 -Plan
powershell -ExecutionPolicy Bypass -File scripts/deploy.ps1 -VerifyOnly

# 全量链接 (首次迁移 / 新增 skill / 换机器后恢复, 幂等)
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1

# 只预览部署计划, 不修改
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -Plan

# 只检查, 不修改
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -VerifyOnly

# 只处理部分 skill
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -Include doc-rewrite-review,htmlmini

# 推荐 skill（依赖显式安装 / 依赖与命令都不装）
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -ApplyRecommendedSkills
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -SkipRecommendedSkills

# 第三方 skill（默认询问 No；显式安装 / 跳过 / 同步版本）
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -ApplyThirdPartySkills
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -SkipThirdPartySkills
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -SyncThirdPartySkills

# 移除本仓库创建的链接 (实体不受影响)
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -Unlink

# 插件链接 (Junction 到 ~/.config\opencode\plugins\<name>)
powershell -ExecutionPolicy Bypass -File scripts/link-plugins.ps1
powershell -ExecutionPolicy Bypass -File scripts/link-plugins.ps1 -VerifyOnly
powershell -ExecutionPolicy Bypass -File scripts/link-plugins.ps1 -Unlink
```

Linux：

```bash
# 一键部署（skill + 插件 + 全局 AGENTS.md + 依赖检查）
./scripts/deploy.sh
./scripts/deploy.sh --plan
./scripts/deploy.sh --verify-only

# 先把仓库同步过去（以 remote 为准，两边推拉即可；路径不必与 Windows 一致）
git clone <remote-url> ~/repos/skills-for-developer
cd ~/repos/skills-for-developer

# 全量链接（幂等）
./scripts/link-skills.sh

# 只预览部署计划，不修改
./scripts/link-skills.sh --plan

# 只检查 / 只处理部分 / 移除
./scripts/link-skills.sh --verify-only
./scripts/link-skills.sh --include doc-rewrite-review,htmlmini
./scripts/link-skills.sh --unlink

# 推荐 skill（需依赖/命令，名单见 config/recommended-skills.txt，当前为 htmlmini）：
# 依赖交互询问（缺省 Yes），非交互默认跳过；命令默认装成直接可调用
# （Linux ~/.local/bin，Windows %USERPROFILE%\.local\bin 并补用户 PATH）
./scripts/link-skills.sh --apply-recommended-skills  # 显式安装依赖（代理执行同一次带上）
./scripts/link-skills.sh --skip-recommended-skills   # 依赖与命令都不装（含 verify 中的对应检查）

# 第三方 skill（名单见 config/third-party-skills.txt，默认询问 No）：
./scripts/link-skills.sh --apply-third-party-skills  # 显式安装，不询问
./scripts/link-skills.sh --skip-third-party-skills   # 跳过安装与校验
./scripts/link-skills.sh --sync-third-party-skills   # 安装缺失并更新到名单版本

# 插件链接（symlink 到 ~/.config/opencode/plugins/<name>）
./scripts/link-plugins.sh
./scripts/link-plugins.sh --verify-only
./scripts/link-plugins.sh --unlink
```

链接脚本会顺手清理**指向本仓库、但目标已不存在的悬空链接**（skill 重命名或删除后的残留）；
`--verify-only` 会把它计为异常并给出重跑提示。指向别处的链接与 harness 自带内容不动；
`--include` 时只清理名单内的名字。`check-skills.py` 也会把本仓库的悬空链接报为 ERROR。

## 第三方 skill 推荐

`skills/` 只存本仓库自定义的真源；第三方 skill 不复制进来，统一登记在
`config/third-party-skills.txt`。每条记录为
`name | repo | kind | ref | preserve | description`，当前登记 `anysearch` v3.1.1。

- 部署时交互询问，**默认 No**（第三方上游代码，安装前可先看名单与仓库）；非交互环境默认跳过。
  显式安装用 `-ApplyThirdPartySkills` / `--apply-third-party-skills`。
- 实体只放一份：第三方共享根目录 `$THIRD_PARTY_SKILLS_HOME/<name>`
  （默认 `~/.local/share/skills-for-developer/third-party/<name>`）；各已登记的 harness 目录都用
  Junction/symlink 指向它，避免 Key 与 `runtime.conf` 出现多份副本。
  默认不放在仓库内，避免 `git clean -xdf` 误删第三方实体与 `.env`；如确需仓库内共享根，可把
  `THIRD_PARTY_SKILLS_HOME` 指向仓库内的 `third-party/`（`.gitignore` 已预留），安装器按同一路径管理。
- 升级由名单 `ref` 驱动。改 `ref` 后运行 `-SyncThirdPartySkills` / `--sync-third-party-skills`，
  或 `python -X utf8 scripts/third-party-skills.py sync`。`preserve` 列出的文件
  （如 anysearch 的 `.env`、`runtime.conf`）在升级时保留。安装器下载 GitHub archive 并解压，
  不执行 `git clone`；上游 submodule/LFS 不会自动获取，这类第三方需单独评估。
- 安装器只接受 HTTPS GitHub archive，拒绝路径穿越与符号链接，并在发现 `SHA256SUMS.txt`
  时校验其中列出的文件。
- 卸载：`python -X utf8 scripts/third-party-skills.py uninstall --name anysearch`
  （实体移入 `~/.third-party-skills-backup/`，不直接删除）。
- 查看状态：`python -X utf8 scripts/third-party-skills.py status`；
  校验已装条目与本机链接：`... verify`。
- 短命令：`python -X utf8 scripts/anysearch-cli.py --install` 把 `anysearch` / `ws` 装到
  `~/.local/bin`（只做入口解析与基础搜索简写，不改第三方实体）；`--status` 查看入口与凭据，
  `--uninstall` 只删本包装。

## 部署清单（新机 / 首次 / 代理执行）

部署 = 推荐基线依赖 + skill 链接安装 + 全局 AGENTS.md 合并 + 两级校验。按下列顺序一次跑完，避免来回补步；各步细则见对应小节，此处只给顺序与开关。

先跑 `--plan` / `-Plan` 可预览链接新建与替换数量、cli.json、推荐 skill 和第三方状态，不修改任何文件。交互模式只对未就绪项提问：cli.json 缺失默认应用、已存在差异默认保留；推荐依赖默认安装；第三方 skill 默认不装。完成后会打印已处理与未处理的摘要。

优先用一键脚本 `scripts/deploy.ps1`（Windows）/ `scripts/deploy.sh`（Linux）串起下面各步（skill 链接、插件链接、全局 AGENTS.md、依赖检查），并在末尾打印各阶段耗时与效率复盘；分步命令只在排障或只做单步时使用。一键脚本同样支持 `-Plan` / `--plan`、`-VerifyOnly` / `--verify-only` 与 `-Quiet` / `--quiet`。

1. **推荐基线依赖（强烈建议）**：按 `minimal` / `standard` / `full` 选套餐（默认 `standard`，含全局 mmdc；PowerShell 7 仅 Windows）；`full` 再补 uv、jq 与 Scrapling（推荐项）。它们覆盖 resource-inventory、htmlmini、mermaid-render-fix、browser-automation、network-access 等，缺了会退化到在线回退、人工路径或能力不全。基础命令行工具 git、ripgrep、fd 与 Playwright、Scrapling 为推荐项（缺失只警告），部署脚本结束时会检测并提示安装命令，不阻断部署。检查命令与安装明细见 [依赖套餐](docs/skill-dependencies.md#部署基线)。
2. **链接安装（首跑即定 cli.json）**：命令见「常用操作」。交互终端只对未就绪项询问；非交互环境（代理执行、CI）没有询问环节，默认跳过，若要应用推荐配置必须在**同一次**执行带开关，否则得二次全量跑：
   ```bash
   ./scripts/link-skills.sh --apply-recommended-cli   # 应用推荐 TUI 配置
   ./scripts/link-skills.sh --skip-recommended-cli   # 保持本机 TUI 配置
   ```
   Windows 对应 `scripts\link-skills.ps1 -ApplyRecommendedCli` / `-SkipRecommendedCli`。
   推荐 skill（`config/recommended-skills.txt`，当前为 htmlmini）同次一并处理：
   只对未就绪项询问，一次确认是否安装依赖（`pnpm install`）并创建命令，缺省 Yes；
   非交互默认跳过依赖（同一次带 `--apply-recommended-skills` 显式安装），命令仍装成
   直接可调用（Linux `~/.local/bin`，Windows `%USERPROFILE%\.local\bin` 并补用户 PATH），
   用 `--skip-recommended-skills` 两者都不装。
   第三方 skill（`config/third-party-skills.txt`，当前为 anysearch）交互询问**默认 No**；
   非交互用 `--apply-third-party-skills` 安装，或用 `--sync-third-party-skills` 同步名单版本。
   插件（`plugins/`）由一键脚本一并处理；分步执行时跑 `scripts/link-plugins.sh`（Windows `scripts\link-plugins.ps1`），链到 `~/.config/opencode/plugins/`；只对 OpenCode 生效，不进 skills 目录。
3. **全局 AGENTS.md 恢复/合并**：见「全局 AGENTS.md 同步与合并」——缺才复制；不一致只提示，由人或代理对比后合并，不直接覆盖。
4. **结构校验**：`python3 scripts/check-skills.py`，frontmatter、README 索引、红线路径、第三方名单与各 harness 安装数全过，见「结构校验」。
5. **链接校验**：`./scripts/link-skills.sh --verify-only`（Windows `-VerifyOnly`），须回显「全部链接正常」；插件另跑 `scripts/link-plugins.sh --verify-only`（Windows `scripts\link-plugins.ps1 -VerifyOnly`）。
6. **服务端计数对照**：`opencode reload` 后拉 `skill.list` 落盘计数，真源须全部在列，片段见「结构校验」末尾。

### 部署后效率复盘（可选反馈）

部署完成或校验通过后，用约 1 分钟复盘本轮部署，避免流程劣化被当成正常：

- **记录耗时**：`deploy.ps1` / `deploy.sh` 末尾会按阶段打印耗时；与上一轮或本机预期对比，某步明显变慢时先查网络、包管理器缓存、PATH 与磁盘，而不是重复全量重跑。
- **记录二次补步**：是否出现"本可一次执行、却因缺开关或缺步骤又跑一遍"（cli.json、推荐依赖、AGENTS.md、插件）。出现即说明指南或脚本仍有缺口。
- **可选反馈**：把耗时、二次补步与难读的输出反馈给仓库维护者（提 issue 或直接告知）；不反馈不影响部署，反馈用于优化本指南与脚本。
- **改动前后对比**：调整部署脚本或指南后，先用 `-Plan` / `--plan` 与 `-VerifyOnly` / `--verify-only` 记一次基线，再改；避免把劣化当成正常。

WSL（Windows 子系统）首次部署除上述步骤外，还要复用 Windows 侧的完整配置（含模型配置），见 [WSL 复用 Windows 侧 OpenCode 配置](docs/wsl-opencode-reuse.md)。

## 推荐的 OpenCode TUI 设置

真源：`config/opencode/cli.json`（图片预览、侧栏、tabs、主题等本机备份）。
跑链接脚本部署时，交互终端下若目标缺失或不一致会询问是否应用
（覆盖前原文件备份为同目录 `cli.json.bak-<时间戳>`）；非交互环境默认跳过：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -ApplyRecommendedCli
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -SkipRecommendedCli
```

```bash
./scripts/link-skills.sh --apply-recommended-cli
./scripts/link-skills.sh --skip-recommended-cli
```

`opencode.json`（供应商）与密钥（`service.json`/`auth.json`）不在此列，
按需走 `opencode-provider-config` 与 `opencode auth import` 另行处理。

本机偏好改动后如何回写真源、哪些项只留本机，见 `skills/skill-authoring-sync/SKILL.md` 的「同步 harness 配置偏好（本机 → 真源）」；本页只维护分发命令。

## 结构校验（frontmatter/索引/红线/安装数）

链接脚本只查 `SKILL.md` 存在与链接指向，不校验内容；
`description` 顶格续行曾导致服务端静默丢弃 skill 而链接校验全绿。
改 skill 后跑一遍零依赖的 `scripts/check-skills.py`（Windows/Linux 通用）：

```powershell
# 全量：frontmatter + README 索引 + 红线路径 + 各 harness 安装数
python3 scripts/check-skills.py

# 只查仓库侧（含 CI，不碰 harness）
python3 scripts/check-skills.py --no-harness

# 只查部分 skill / 警告也视为失败
python3 scripts/check-skills.py --include doc-rewrite-review,htmlmini
python3 scripts/check-skills.py --strict
```

```bash
python3 scripts/check-skills.py
python3 scripts/check-skills.py --no-harness
```

依赖检查（可选，需 Python）：`python3 scripts/check-skill-deps.py` 按各 skill 的 `dependencies.json` 检查本机运行时、命令与浏览器；`--json` 供代理读取，`--strict` 用于准备完整环境。声明格式与新机基线见 [Skill 依赖声明与部署基线](docs/skill-dependencies.md)。

通过后再跑链接校验与服务端计数对照（`skill.list` 应含全部真源数 + 兼容源/内置）。JSON 较长，先落盘再解析，避免管道截断半截输出；两段计数命令都在仓库根目录执行，整段贴进同一次调用一次跑完（每次独立调用都有服务调度与快照开销，拆散跑更慢）。`reload` 后等约 5 秒再 `list`——重扫是异步的，紧跟查询可能读到中间态；若 `missing` 非 `none`，隔几秒重查一次，仍非 `none` 才算异常：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -VerifyOnly
opencode reload
opencode api skill.list > $env:TEMP\skills.json
python3 -c "import json,os;ids={s['id'] for s in json.load(open(os.environ['TEMP']+'/skills.json'))['data']};src={d for d in os.listdir('skills') if os.path.isfile('skills/'+d+'/SKILL.md')};print('server:',len(ids),'| in-source:',len(src&ids),'/',len(src),'| missing:',sorted(src-ids) or 'none')"
```

```bash
./scripts/link-skills.sh --verify-only
opencode reload
sleep 5   # 等重扫落定，紧跟查询可能读到中间态
f="${TMPDIR:-/tmp}/opencode-skills.json"
opencode api skill.list > "$f"
python3 -c "import json,sys,os;ids={s['id'] for s in json.load(open(sys.argv[1]))['data']};src={d for d in os.listdir('skills') if os.path.isfile('skills/'+d+'/SKILL.md')};print('server:',len(ids),'| in-source:',len(src&ids),'/',len(src),'| missing:',sorted(src-ids) or 'none')" "$f"
```

`missing` 必须为 `none`、`in-source` 为满额；`server` 大于真源数属正常（含兼容源与内置 skill）。

## 全局 AGENTS.md同步与合并

> 重点任务,部署此仓库既包括普通skill部署安装,也包括全局agents.md的合并.

真源：`config/global-AGENTS.md`（以它为基准；允许各 harness 保留本机定制，通用条目两边保持一致）。每个消费全局 `AGENTS.md` 的 harness 一个部署目标：OpenCode 落 `~/.config/opencode/AGENTS.md`，ZCode 落 `~/.zcode/AGENTS.md`（ZCode 的用户级指令文件只认该路径，不回退 `~/.agents`）。链接脚本不碰各 harness 的 `AGENTS.md`；一键部署脚本 `scripts/deploy.ps1` / `deploy.sh` 会在目标缺失时复制，内容不一致只警告（通用条目由人或代理对比合并，本机定制保留，不自动覆盖）。分步执行时 `-VerifyOnly`/`--verify-only` 会一并提示差异：目标缺失计异常，内容不一致只警告（存在本机定制时属正常）。新机 clone 后跑一次一键脚本即可；已存在且不一致时合并通用条目，本机专属条目留在本机副本。

Windows（PowerShell）：

```powershell
$src = Join-Path (git rev-parse --show-toplevel) 'config\global-AGENTS.md'
$targets = @(
  (Join-Path $env:USERPROFILE '.config\opencode\AGENTS.md'),
  (Join-Path $env:USERPROFILE '.zcode\AGENTS.md')
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
foreach ($dst in $targets) {
  if (-not (Test-Path -LiteralPath $dst)) { New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null; Copy-Item -LiteralPath $src -Destination $dst; "$dst restored" }
  elseif ([System.Linq.Enumerable]::SequenceEqual([byte[]][System.IO.File]::ReadAllBytes($src), [byte[]][System.IO.File]::ReadAllBytes($dst))) { "$dst already in sync" }
  else { "$dst differs from the source (local customization allowed); merge shared entries manually, will not overwrite" }
}
```

Linux：

```bash
src="$(git rev-parse --show-toplevel)/config/global-AGENTS.md"
for dst in ~/.config/opencode/AGENTS.md ~/.zcode/AGENTS.md; do
  if [ ! -f "$dst" ]; then mkdir -p "$(dirname "$dst")"; cp "$src" "$dst"; echo "$dst restored";
  elif cmp -s "$src" "$dst"; then echo "$dst already in sync";
  else echo "$dst differs from the source (local customization allowed); merge shared entries manually, will not overwrite"; fi
done
```

## 日常工作流

1. 改 skill: 直接改仓库里的 `skills/<name>/`，改完即对**本机**所有 harness 生效, 无需重新链接；跨机器用 `git push/pull` 同步，声称已对齐前按 `skill-authoring-sync` 的「跨机器同步与对齐判定」直接核对远端，不以 `git status -sb` 代替。
2. 新增 skill: 在 `skills/` 下新建目录 + `SKILL.md`, 然后在**每台机器**上运行一次该平台的链接脚本。
3. 删除 skill: 先运行 `-Unlink` / `--unlink` (或手工删除各 harness 下对应链接), 再删仓库目录。注意删除链接只删链接不删实体：Win 用 `Remove-Item <junction>`（不要加 `-Recurse`），Linux 用 `rm <symlink>`（不要加 `-r`，且路径末尾不要加 `/`）。
4. 原位置的实体在首次替换为链接时会自动备份到 `~/.skills-migration-backup/<时间戳>/<harness>/<name>`（Win 下即 `%USERPROFILE%/.skills-migration-backup/...`），备份移出 skills 目录是为了避免被 harness 误扫为重复 skill，确认无误后可手工删除备份。
5. 跑 skill-creator 评估时，过程产物（`outputs/`、`benchmark.json`、`review.html` 等 `*-workspace/` 目录）统一放仓库根 `.workspaces/<skill-name>-workspace/`（已在 `.gitignore` 忽略，本地独占）；**禁止**放入 `skills/` 下（链接脚本会对无 `SKILL.md` 目录告警，且过程产物不许进入真源同步）。留到 skill 稳定作回归基线，过时后整目录删除。

## 开源许可

MIT（见 `LICENSE`），可自由使用、修改、分发，保留版权声明即可。
