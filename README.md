# skills-for-developer

本地 skills 唯一真源仓库（跨平台：Windows + Linux 共用）。实体只存这里，各 agent harness 侧通过链接引用，不存副本（Windows 用 **Junction**，Linux 用 **symlink**）。

## Skill 目录（检索入口）

真源布局：`skills/<skill-name>/`（一个目录一个 skill，必须包含 `SKILL.md`，可带自有的 `references/`、`scripts/` 等）；`scripts/` 放链接脚本，`docs/` 放协作说明，`.workspaces/` 放本地评估产物（git 忽略，不提交）。

仓库校验：`python scripts/check-skills.py` 检查结构/索引/路径红线；`python scripts/check-links.py` 检查 Markdown 相对链接与锚点；`python scripts/check-skill-deps.py` 按各 skill 的 `dependencies.json` 检查本机依赖，声明格式见 [skill 依赖声明](docs/skill-dependencies.md)。

| Skill 目录                             | 一句话说明                                                                                                                                                                                                                                                                                  | 关键词 / 何时用                                                                                                                                                                                               |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `skills/doc-rewrite-review`          | 技术/业务文档合并改写与质量提升：多份文档先差异对比、按权威与适用范围取舍，按最终主题核定文件名，修正文／拆分复用并清理重复载体；单篇保留有效原意，正式化、规范化、严谨化、清晰化，补充结构、示例、表格与 Mermaid 图（原名 doc-polish-zh，已去语言限定；2026-10-13 由 doc-polish 改名）                                                                                                           | 润色、改写、审校、优化文档、【原文】、polish、rewrite、proofread、edit、improve docs、合并文档、多文档合并、合并草稿、多AI回答合并、去重取优、合并后文件名 |
| `skills/project-docs`                | 为程序与仓库规划并编写配套文档：按项目规模定最小文档集，按顺序写 README、`--help`、配置与 API 参考、CHANGELOG、ADR、部署与 Runbook，用读者视角验收并审查存量缺口；排版/注释/改写各归邻近 skill | 写 README、补文档、项目该配哪些文档、文档缺口、交付前文档检查、CHANGELOG、ADR、Runbook、AGENTS.md、部署文档、API 文档、配置说明 |
| `skills/scripting-best-practices`    | Shell / Python / Node 脚本与小工具 CLI 的编写、审查与重构规范：快速失败、输入校验、`--help` 与退出码、长选项为主并给常用短选项、批量覆盖/下发的幂等与预检、UTF-8 与跨平台换行、多脚本交付；语言细则按需读 `references/`（原 opencode） | 写脚本、审脚本、重构`.sh` / `.bash` / `.py` / `.mjs` / `.js`、Node CLI、排查脚本健壮性、UTF-8 编码默认、批量下发、覆盖写入、预检门禁、强制覆盖、幂等判定、长选项、短选项、--help、退出码、多脚本交付 |
| `skills/resilient-browser-fetch`     | 稳健网页采集：抓取需渲染页面、Cloudflare/Turnstile/Akamai 挑战页、拦截页与人工验证；按能力分层选 HTTP、Playwright/Patchright、Scrapling、指纹底座或有头浏览器，缺件降级；含会话复用、HTML 快照、浏览器依赖与图形环境排障；选路走 network-access（原 codex） | 反爬、Cloudflare、Turnstile、Akamai、SEC-CPT、SBSD、边缘封禁、Reference #、抓取、采集、挑战页、挑战窗口、404/410、会话复用、同站探针、HTML 快照、保存网页、图片保留 URL、离线存档、Scrapling 环境安装、Playwright、Patchright、CloakBrowser、nodriver、chrome-late、晚接入、接入时机、cdp-attach、接管浏览器、复用真实浏览器会话、软错误页、批量晚接入、控制面、真实浏览器会话复用、同类方案对比、DrissionPage、浏览器回收、AGPL、不做首跳选路 |
| `skills/htmlmini`                    | 网页核心骨架提取：总结、分析、审查页面，或从 URL/本地快照取表格、榜单、分数、规格；默认不整份读 HTML；CLI+MCP 双形态，含 web_fetch/渲染/接口分流；写或改页面代码与设计评审归 frontend-design/frontend-qa，批量采集归 resilient-browser-fetch（原 claude） | html、URL、网页、页面、设计稿、面板、仪表盘、总结、分析、审查、查看、看一下、提取、取数、分数、表格、榜单、web_fetch 分流、页面取数、后端接口、XHR、JSON 接口、落盘 HTML 快照、调研取数、正则/脚本解析 HTML、爬虫侦察（契约另核） |
| `skills/skill-authoring-sync`        | agent harness 新建自定义 skill 并同步到真源仓库：新建必要性判断、真源唯一、真源定位、链接分发、跨机器 git 同步、本机配置偏好回写真源；本地提炼默认不归档原材料与指纹，内容写作引用仓库规范；写 skill 正文/AGENTS.md 的指针、信息层级、主词与修剪见 `references/writing-for-agents.md`                                                                                                                                                                  | 新建 skill、是否新建 skill、安装 skill、同步 skill、同步配置、同步 opencode 设置/偏好、回写配置、链接校验、真源管理、真源位置、定位真源、skill 变更、查变更、写 skill 正文、AGENTS.md 写作、context pointer、leading word、信息层级、修剪                                                                                                                                                                    |
| `skills/repo-gov`                     | 公开/私有仓库治理与安全提交：按用途选配 README、LICENSE、.gitignore/.gitattributes、CONTRIBUTING、SECURITY、行为准则与模板；提交前检查、密钥/大文件审计、分支与评审保护、CI 与依赖/构建供应链控制；应用架构转 swe-gov，文档内容转 project-docs | 初始化仓库、新建仓库、LICENSE、许可证选择、SECURITY、CONTRIBUTING、.gitignore、.gitattributes、提交检查、CI、分支保护、供应链、审计密钥、repo-gov、仓库治理 |
| `skills/swe-gov`                     | 软件工程治理：长期应用工程基线，模块/数据/状态归属、异步任务恢复、ADR、契约兼容、进程容量与运行恢复、检查与门禁设计边界、文档一致性、去重取舍、地图／Skill及定期整理、技术债与效能反馈；按需复用测试、仓库和交付政策 | 应用开发规范、架构治理、状态管理、异步任务、进程治理、ADR、契约演进、兼容迁移、幂等副作用、SLO、恢复、门禁设计、误报、启发式检查、文档一致性、文档去重、文档整理、代码地图、技术债、持续维护、swe、工程治理 |
| `skills/tech-learning-research`      | 技术话题系统讲解、联网调研与选型推荐：研究范围与取证覆盖面、方案权衡、详略等级、成文与排版收尾；检索执行（查询词、来源分级、预算与限流）归 `agentic-web-search`；产物是笔记/文档/代码时同样先调研，落盘类 skill 不抢触发 | 学习、技术调研、方案对比、选型推荐、做法盘点、research、tutorial、comparison、调研先行 |
| `skills/grilling`                    | 设计拷问：按设计树逐轮提问，先问前置已定的 frontier，每题附推荐答案，直到分支问空、双方对齐；正文保留上游英文原文（MIT，见 SOURCE.md） | 拷问、压力测试方案、grill me、设计树、需求对齐、方案评审、动手前想清楚、先别写代码先问我 |
| `skills/markdown-style`              | Markdown 行文风格与排版规范（正本）：只改形式不改实质，标题/列表/表格/代码块/Mermaid 统一用法；文档合并与多文档整合定稿后走本规范收尾（合并本身归 `doc-rewrite-review`）；skill 指令内容与语言按仓库写作规范                                                                                                                   | 排版、风格迁移、规范格式、统一标题、markdown lint、format、合并后排版、统稿排版、章节并入正文、附录并入正文                                                                                                                 |
| `skills/lightweight-app-builder`     | 模糊小工具需求落成轻量跨平台可交付程序：分诊代决策、形态判定、技术选型、打包签名分发，六步流程；与 repo-gov/swe-gov/ai-verified-delivery 分层组合，已有脚本的编写与重构规范转 scripting-best-practices | 做个工具、写脚本、小软件、CLI、桌面应用、技术选型、打包分发、轻量应用构建 |
| `skills/frontend-design`             | Web/桌面小工具界面设计：任务、页面结构、令牌、通用交互与整体交付；共用对比度与截图协议，局部验收优先特写；线框接入 adaptive-responsive-guide，动效设计查 motion.md、技术查 web-animation-guide，存量深查转 frontend-qa；页面代码/配置片段的高亮、行号与复制查 code-display.md                                                                   | 界面丑、布局乱、美化、适配手机、加载动画、文字/图标难辨、对比度、页面可读性、新建改版、交付验收、可用性、UX、代码高亮、行号、源码片段                                                                                                   |
| `skills/frontend-qa`              | 存量前端 UI 缺陷诊断与视觉验收：Playwright 用户流程、关键态视觉判断、对比度与可读性、溢出/CLS 及 DoD CI 门禁；截图工具和浏览器操作复用 browser-automation，测试用例与回归体系转 web-app-testing | 布局溢出、弹窗关闭、焦点回归、对比度、页面可读性、UI 截图验收、Agent 视觉理解、Playwright 流程验收、axe、DoD、CI 拦截 |
| `skills/browser-automation` | 本地浏览器与工具预检、路径定位、浏览器操作方案及测试运行器决策；指导交互、等待、下载与会话所有权，区分新建实例、接管已登录会话与托管浏览器，给出只读发现和含总期限/进程树回收的托管截图，保留旧 QA 截图 CLI 委托 | Chrome/Edge/Chromium、浏览器在哪、安装路径、Scoop、便携浏览器、普通浏览器与 Playwright、Puppeteer、Selenium、MCP、工具/框架选型、浏览器自动化、CDP、远程浏览器、接管已登录会话、浏览器归属、shot-quick、shot_scroll、截图卡住、进程残留、资源回收 |
| `skills/web-app-testing`             | 前后端 Web 自动化测试规划、编写与维护：有效断言、真实 API/存储、Playwright 回归用例、真实浏览器运行时验证（逐步断言、控制台/网络证据）、测试层与开发侧/独立测试阶段区分、隔离、运行器资源预算与 CI，含幂等/副作用和兼容回归；浏览器工具决策与操作转 browser-automation，工程设计按应用治理，交付证据按 ai-verified-delivery | Web 测试、自动化测试、该测什么、什么时候写测试、单元/组件/集成/E2E、Playwright 回归用例、运行时验证、浏览器验证、控制台报错、网络请求断言、假通过、开发侧测试、独立测试、系统测试、验收测试、准出测试、API 契约、数据库、权限回归、幂等/兼容回归、过度 Mock、测试隔离、不稳定测试、测试并发、资源预算、CI 分层 |
| `skills/diagnosing-bugs`             | 难 bug 与性能回归诊断：先造能变红的反馈回路，再最小化、列可证伪假设、单变量插桩、修复与回归；正文保留上游英文原文（MIT，见 SOURCE.md） | debug、诊断、复现、red loop、最小化、二分、性能回归、偶发 bug、修 bug、先复现再猜 |
| `skills/arena-preview`               | arena.ai 项目包预览：解压指纹、后台运行、主题与核心文件分析、一屏预览报告；展示截图用于验收时转共用协议                                                                                                                                                                                     | 预览项目包、arena 交付、解压运行、主题分析、跑起来看看                                                                                                                                                        |
| `skills/distinctive-design-director` | 有辨识度的视觉方向与品味主导的点评打磨：外部种子发散、设计简报收敛、只看成品评审、删减去模板味；落地实现转 frontend-design，存量缺陷与验收转 frontend-qa；对比度与截图行为复用共用规范 | 设计灵感、审美方向、视觉风格、情绪板、视觉发散、界面点评、去模板化、去除AI味、design inspiration、UI critique |
| `skills/powershell-pitfalls`         | PowerShell 5.1/pwsh 执行与排障：编写/运行脚本片段、读取选择、编码保真、编码体检与校准、启动和安全底线，诊断与版本细节按需读取；原生 read 常规查看无需加载                                                                                                                                           | PowerShell 读文件、编写脚本、Get-Content/type/cat、UTF-8、默认UTF-8输出、NoProfile、profile、PowerShell 开发测试、退出码、原生参数、Start-Process、LiteralPath、管道输出、中文乱码、编码体检、BOM、引号、别名、junction |
| `skills/agentic-web-search`          | 智能体联网搜索优化：时间锚定、探测查询、迭代扩词、来源分级与交叉验证、知识冲突与假前提裁决、预算分档与停止条件、搜索/抓取请求节奏与 429 冷却、子代理委派与证据验收、引用与日期标注，含工具参数与评测参考；报告成文与详略归 `tech-learning-research` | 联网搜索、搜索优化、检索词陈旧、信息过时、知识冲突、假前提、交叉验证、来源分级、搜索预算、引用不实、子代理委派、跨模型检索、web search |
| `skills/web-animation-guide`         | Web动画技术实现：选型、示例、退出布局保持、中间帧验证、打断清理、兼容、性能与减弱动效；读取项目令牌，截图取景与查看复用共用协议；反馈目的与设计预算归 frontend-design，响应式布局归 adaptive-responsive-guide | web动画、WAAPI、滚动驱动、View Transitions、GSAP、reduced-motion、动效卡顿 |
| `skills/adaptive-responsive-guide`   | 响应式专项：视口/容器阈值、流体排版、Flex/Grid、响应式图片、窄屏操作区收纳、溢出与滚动、触控目标、深色与 reduced-motion 布局、范围化验收；纯视觉方向、存量深查、动效技术与页面整体设计分别归邻近 skill | 自适应、响应式、适配指南、媒体查询、容器查询、clamp、dvh/svh、按钮放不下、窄屏溢出、横向滚动、触控目标、操作区收纳、极窄视口 |
| `skills/sticky-position`             | CSS`position: sticky` 粘性定位实现规范：三句心智模型、七种场景标准写法、六类失效根因排查、sticky/fixed 选型、兼容降级与无障碍上线清单                                                                                                                                                     | 吸顶、吸底、吸附、置顶导航、表头冻结、粘性侧栏、分组标题顶走、层叠卡片、抽屉切侧栏、sticky 不生效/粘不住、滚动到某处停住、scroll-padding、overflow 劫持、诊断脚本、is-stuck 哨兵                              |
| `skills/ai-verified-delivery`        | AI 编程质量与规格驱动可验证交付：规格/AC/任务到证据追踪，唯一风险等级/状态；维护共用截图触发、特写/视口/全页取景、实际查看与视觉证据协议；复核与适用发布恢复，工程设计/测试按需协作                                                                                                         | AI coding 质量、spec、SDD、需求拆解、验收标准、门禁、verify、DoD、L0-L4、RTM、截图验收、特写、复核、完成报告、例外、风险接受、发布恢复                                                                        |
| `skills/admin-console-design`        | 后台控制台设计与实现：默认沿用整体主题与页面结构，按需补列宽/撤销、导入校验与验收案例；附功能目录、源码、依赖边界与快照，默认继承设计并接业务，标明参考缺口；对比度与截图复用共用规范 | 后台面板、管理后台、admin、console、dashboard、侧栏折叠悬停、列表编辑批量、设置页、向导、Cloudflare-inspired |
| `skills/skill-patcher`               | 存量 skill 实战补丁：把真实漏验、误判或执行失败修成增量条目；一般写作审查按编写入口，内容与语言复用仓库规范                                                                                                                                                                                 | 实战复盘、修补 skill、真实逃逸、补丁措辞审查、去污染、项目无关性                                                                                                                                              |
| `skills/reference-to-skill`          | 一份或多份资料（文档/规范/报告）提炼成 skill：贡献比较、证据分类、目标审查、冲突裁决、规则落点与验证；支持建议、新建和改进，含是否值得沉淀的判断；本地提炼聚焦能力本身，不默认保留来源与指纹                                                                                                                                                       | 多文档提炼、单份资料转 skill、提取精华、参考资料转 skill、是否值得做成 skill、给 agent 的指南、对比报告完善 skill、规则整合、reference to skill                                                                                                                      |
| `skills/code-comments`              | 代码与配置注释编写、精简和审查：接口契约、实现意图、配置决策、工具指令、跨文件关联及维护条件；附Python docstring与Nginx示例 | 注释最佳实践、补充注释、清理冗余注释、过时注释、文档字符串、docstring、TODO、noqa、检查豁免、配置注释 |
| `skills/codex-model-config`          | Codex 接第三方/自定义模型：建 profile、写模型目录、窗口档位与工具字段；排查 web_search 不下发、模型不调用搜索与工具行为异常（独立仓库，submodule 引用） | 接模型、自定义模型、第三方模型、model_providers、models.json、context window、profile、codex config、web_search 不生效、模型不调用搜索、搜索工具不下发、standalone web.run |
| `skills/network-access`              | 任何外链抓取、联网下载或代理/镜像配置前的网络选路：国内试验与海外生产的直连/代理/镜像、Windows 与 *nix 配置、GitHub/文档访问、Python/Node.js/conda 依赖与 Playwright/Scrapling 浏览器安装下载；下载前复用环境，浏览器发现与操作转 browser-automation，含超时/403/5xx/限流分流与加速核验及本机观测 | 出网、外网资源、GitHub、文档访问、依赖下载、安装脚本、下载慢、超时、403、5xx、回退、镜像源、文件加速、代理、mihomo、直连、pip、uv、npm、pnpm、Yarn、conda、miniforge、Python、Node.js、Playwright 安装、playwright install、scrapling install、国内浏览器下载、浏览器制品镜像、联网、网络环境 |
| `skills/opencode-provider-config`    | 第三方 AI API（中转站/NewAPI/OpenAI 兼容网关）接入 OpenCode：拉`/v1/models` 筛模型、DNS/代理诊断、多源查模型参数（OpenRouter/models.dev/LiteLLM，自带零依赖 Python 脚本 model_info.py，含 Windows 与 *nix 手工取法）、写 providers 配置、切 Responses 协议（模型级 package 覆盖与抓包验证）、覆盖已有/内置模型的上下文（limit）、service set env 持久化代理与密钥、三步端到端验证；env/代理排障细节见 references/service-env.md | 接入 opencode、自定义供应商、配 provider、中转站、NewAPI、one-api、第三方模型、改模型上下文、limit、/v1/models、models.dev、openrouter、litellm、上下文窗口、模态、model_info.py、baseURL、service set env、OpenCode 接模型、responses 协议、openai-response、/v1/responses、模型级 package、协议切换        |
| `skills/mermaid-render-fix`          | Mermaid 渲染失败诊断与修复：提块复现 Parse error、修节点引号与转义、mmdc/kroki 复验回写；含规范化/兼容性体检（按最低目标版本选写法，象限图与架构图非 ASCII 文案引号、缺箭头、坐标越界、版本下限）；语法正本走 markdown-style | mermaid 渲染失败、Parse error、got SQS、图挂了、节点方括号、修图、复验、检查 mermaid、规范化 mermaid、兼容性、象限图报错、架构图报错、Lexical error、Unrecognized text |
| `skills/user-profile`                | 个人常驻默认值：本地提炼skill聚焦能力、网络选路与 PowerShell 执行底线，及转调 network-access/powershell-pitfalls/scripting-best-practices 的指针；优先由全局 AGENTS.md 显式加载，网络/PowerShell 任务可按关键词兜底                                                                                                                         | 常驻偏好、个人默认值、user-profile、全局偏好、动手前加载、代理/镜像/出网、shell/乱码/编码、脚本编写/UTF-8                                                                                                                     |
| `skills/note-blog-archivist`         | 经验结论沉淀到本地笔记/博客仓库：定位笔记总目录、复用现有文档最小追加或按目录规则新建，省去手动归类；仅接单份已定稿内容，合并/改写不在此列                                                                                                                                                                                                                   | 存笔记、记一笔、沉淀经验、放到博客、经验库、归档笔记、笔记分类、并进现有笔记 |
| `skills/resource-inventory`          | 本机资源体检与复用：一次聚合当前会话环境、运行时版本、Python 解释器与引擎层、浏览器候选、代理环境变量/登记/实际入口、项目已有测试与包管理工具及已装证据；检测逻辑仍属各域 skill，本 skill 只做聚合与判读，避免重复安装和环境误判 | 本机有什么、环境探测、资源全景、避免重复安装、Python 环境在哪、浏览器在哪、代理入口、测试栈、换机器排查 |

> 约定：`SKILL.md` 头部的 `description` 是 agent 侧的触发依据；上表是给人看的检索入口，两处语义保持一致，改 skill 时同步更新。

## 插件目录（检索入口）

真源布局：`plugins/<plugin-name>/`（一个目录一个插件，**入口必须是包根目录的 `index.ts`**）；
`scripts/link-plugins.ps1`（Windows，Junction）/ `scripts/link-plugins.sh`（Linux，symlink）
链接到 `~/.config/opencode/plugins/<name>`，OpenCode 自动发现该目录下的插件包。
装载规则（入口文件、发现路径、静默失败）、验证方法与"插件 vs skill"分工见
[插件制品](docs/plugins.md)。

| 插件目录                             | 一句话说明                                                                                                                                                                                                                        | 关键词 / 何时用                                                                                                                        |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `plugins/powershell-encoding-guard` | 把 `skills/powershell-pitfalls` 的机械步骤前置到 OpenCode 的 shell 钩子：Windows + PowerShell 自动前置编码语句与 `PYTHONUTF8=1`；原生命令输出经文本层时只写诊断日志、**默认不改写工具输出**（追加提示需显式开 `appendNote`）；判断类规则仍由 skill 负责；自带诊断通道，确认当前会话是否被覆盖 | PowerShell 编码、乱码、shell 钩子、OpenCode 插件、编码前置、原生命令管道、PYTHONUTF8、native 输出落盘、诊断通道、location 路由、热重载、重复装载 |

## 维护文档

- [仓库维护入口](AGENTS.md)：供代理读取的短入口。
- [全局 AGENTS.md 真源](config/global-AGENTS.md)：个人常驻引用（一行），新机恢复用；链接脚本不碰各 harness 的 AGENTS.md。
- [WSL 复用 Windows 侧 OpenCode 配置](docs/wsl-opencode-reuse.md)：完整配置（含模型配置）在 WSL 侧的复用范围、方式选型、密钥红线与验证（复用后默认不测活）；skill 分发仍走链接脚本。
- [Skill 仓库治理](docs/skill-governance.md)：规则归属、职责划分、变更流程与分级验证。
- [Skill 依赖声明与部署基线](docs/skill-dependencies.md)：`dependencies.json` 格式、检查命令与新机推荐依赖。
- [插件制品（OpenCode 插件）](docs/plugins.md)：插件真源布局、链接分发、装载规则（入口文件/发现路径/静默失败/全局键占用/location 路由）、通用验证清单与 skill 分工。
- [Skill 内容与语言规范](docs/skill-content-guidelines.md)：约束强度、正文与参考落点、指令措辞、术语、例子和写作复核。
- 变更历史：直接看 `git log`；本仓库不维护独立 CHANGELOG，提交信息按 Conventional Commits 记录目的与影响。
- [Skill 编写、提炼与维护协作](docs/skill-authoring-workflow.md)：`reference-to-skill`、社区版 `skill-creator`、`skill-patcher` 与 `skill-authoring-sync` 的职责、引用方式和维护取舍，含社区版/系统版区分与验证边界。
- [Skill 触发评测](skills/skill-authoring-sync/references/trigger-eval.md)：正负例取样、子代理判定 prompt、判据、记录格式与案例库；改 description 时使用。
- [skill-up 行为评测试点](docs/skill-up-pilot.md)：范围、用例、验收与决策规则；未纳入默认流程。
- [测试相关 Skill 的职责与维护边界](skills/web-app-testing/references/skill-boundaries.md)：测试设计、交付等级与证据、UI 专项、工具打包和仓库 CI 的唯一维护位置；含构建应用时的 skill 组合顺序，按需协作并复用计划与有效证据。
- [测试层、测试阶段与责任](skills/web-app-testing/references/coverage-and-layers.md#测试层测试阶段与责任)：区分测试层、开发侧验证与独立测试阶段；单元/组件/CI 通过不等于系统、验收或准出结论，独立复核也不等于独立测试。
- [测试资源预算与回收](skills/web-app-testing/references/environment-and-maintenance.md#测试资源预算与回收)：测试与验收先设容量、并发及期限，登记资源归属，验明异常回收再重试；web-app-testing、ai-verified-delivery与frontend-qa共用。
- [共用截图与视觉验收协议](skills/ai-verified-delivery/references/visual-acceptance.md)：截图触发、取景优先级、采集、实际查看与证据的唯一维护位置；相关 skill 引用，不各自维护完整截图规则。
- [浏览器安装与国内网络](skills/network-access/references/browser-installation.md)：Playwright/Scrapling 的包源、浏览器制品、系统依赖与启动验证；国内下载代理、镜像回退及缓存复用的共用入口。
- [普通浏览器截图与 Playwright](skills/browser-automation/references/screenshot-workflow.md#普通浏览器与-playwright-的区别)：人工截图、自动化、测试运行器与资源托管的分工，已安装 Chrome/Edge 的复用及 CDP 会话边界。
- [查找已安装的浏览器](skills/browser-automation/references/browser-discovery.md)：只读列候选与显式自动选择，覆盖 Windows 注册表/Scoop、macOS 应用包及 Linux 常用目录，区分原生文件、包装器与沙箱安装。
- [浏览器工具与框架决策](skills/browser-automation/references/tool-and-framework-choice.md)：检查现有浏览器工具，选择控制库及测试运行器；含浏览器归属三态与接管已登录会话的取舍，自动化操作指导由 browser-automation 维护，测试设计沿用 web-app-testing。

## Harness 映射（Win / Linux 路径同构，只是家目录写法不同）

| Harness          | Windows skills 目录                                                   | Linux skills 目录                        | 说明                                                             |
| ---------------- | --------------------------------------------------------------------- | ---------------------------------------- | ---------------------------------------------------------------- |
| Agents 通用      | `%DSH_AGENTS_HOME%/skills`（默认 `%USERPROFILE%/.agents/skills`） | `${DSH_AGENTS_HOME:-~/.agents}/skills` | 全量链接；Pi 等标准兼容 harness 共用，第三方实体不动             |
| OpenCode         | `%USERPROFILE%/.config/opencode/skills`                             | `~/.config/opencode/skills`            | 全量链接仓库中的 skill                                           |
| Codex            | `%USERPROFILE%/.codex/skills`                                       | `~/.codex/skills`                      | 全量链接; 自带的`.system/`、`AGENTS.md` 等原样保留, 脚本不碰 |
| Claude           | `%USERPROFILE%/.claude/skills`                                      | `~/.claude/skills`                     | 全量链接                                                         |
| DeepSeek Harness | `%DSH_HOME%/skills`（默认 `%USERPROFILE%/.dsh/skills`）           | `${DSH_HOME:-~/.dsh}/skills`           | 全量链接；dsh 原生用户级（rank 高于通用位置）                    |
| ZCode            | `%USERPROFILE%/.zcode/skills`（优先），回退 `%USERPROFILE%/.agents/skills` | `~/.zcode/skills`（优先），回退 `~/.agents/skills` | 只读取不建链，复用 Agents 通用行的链接；个别 skill 只想在 ZCode 内覆盖时放 `~/.zcode/skills` |

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
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -Include doc-rewrite-review,htmlmini

# 推荐 skill（依赖显式安装 / 依赖与命令都不装）
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -ApplyRecommendedSkills
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -SkipRecommendedSkills

# 移除本仓库创建的链接 (实体不受影响)
powershell -ExecutionPolicy Bypass -File scripts/link-skills.ps1 -Unlink

# 插件链接 (Junction 到 ~/.config\opencode\plugins\<name>)
powershell -ExecutionPolicy Bypass -File scripts/link-plugins.ps1
powershell -ExecutionPolicy Bypass -File scripts/link-plugins.ps1 -VerifyOnly
powershell -ExecutionPolicy Bypass -File scripts/link-plugins.ps1 -Unlink
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
./scripts/link-skills.sh --include doc-rewrite-review,htmlmini
./scripts/link-skills.sh --unlink

# 推荐 skill（需依赖/命令，名单见 config/recommended-skills.txt，当前为 htmlmini）：
# 依赖交互询问（缺省 Yes），非交互默认跳过；命令默认装成直接可调用
# （Linux ~/.local/bin，Windows %USERPROFILE%\.local\bin 并补用户 PATH）
./scripts/link-skills.sh --apply-recommended-skills  # 显式安装依赖（代理执行同一次带上）
./scripts/link-skills.sh --skip-recommended-skills   # 依赖与命令都不装（含 verify 中的对应检查）

# 插件链接（symlink 到 ~/.config/opencode/plugins/<name>）
./scripts/link-plugins.sh
./scripts/link-plugins.sh --verify-only
./scripts/link-plugins.sh --unlink
```

链接脚本会顺手清理**指向本仓库、但目标已不存在的悬空链接**（skill 重命名或删除后的残留）；
`--verify-only` 会把它计为异常并给出重跑提示。指向别处的链接与 harness 自带内容不动；
`--include` 时只清理名单内的名字。`check-skills.py` 也会把本仓库的悬空链接报为 ERROR。

## 部署清单（新机 / 首次 / 代理执行）

部署 = 推荐基线依赖 + skill 链接安装 + 全局 AGENTS.md 合并 + 两级校验。按下列顺序一次跑完，避免来回补步；各步细则见对应小节，此处只给顺序与开关。

1. **推荐基线依赖（强烈建议）**：按 `minimal` / `standard` / `full` 选套餐（默认 `standard`，含全局 mmdc；PowerShell 7 仅 Windows）；`full` 再补 uv 与 jq。它们覆盖 resource-inventory、htmlmini、mermaid-render-fix、browser-automation、network-access 等，缺了会退化到在线回退、人工路径或能力不全。检查命令与安装明细见 [依赖套餐](docs/skill-dependencies.md#部署基线)。
2. **链接安装（首跑即定 cli.json）**：命令见「常用操作」。交互终端不带开关会询问；非交互环境（代理执行、CI）没有询问环节，默认跳过，若要应用推荐配置必须在**同一次**执行带开关，否则得二次全量跑：
   ```bash
   ./scripts/link-skills.sh --apply-recommended-cli   # 应用推荐 TUI 配置
   ./scripts/link-skills.sh --skip-recommended-cli   # 保持本机 TUI 配置
   ```
   Windows 对应 `scripts\link-skills.ps1 -ApplyRecommendedCli` / `-SkipRecommendedCli`。
   推荐 skill（`config/recommended-skills.txt`，当前为 htmlmini）同次一并处理：
   依赖（`pnpm install`）交互询问缺省 Yes、非交互默认跳过（同一次带
   `--apply-recommended-skills` 显式安装）；命令（`htmlmini`）默认装成直接可调用
   （Linux `~/.local/bin`，Windows `%USERPROFILE%\.local\bin` 并补用户 PATH），
   用 `--skip-recommended-skills` 两者都不装。
   插件（`plugins/`）单独跑 `scripts/link-plugins.sh`（Windows `scripts\link-plugins.ps1`），链到 `~/.config/opencode/plugins/`；只对 OpenCode 生效，不进 skills 目录。
3. **全局 AGENTS.md 恢复/合并**：见「全局 AGENTS.md 同步与合并」——缺才复制；不一致只提示，由人或代理对比后合并，不直接覆盖。
4. **结构校验**：`python3 scripts/check-skills.py`，frontmatter、README 索引、红线路径与五 harness 安装数全过，见「结构校验」。
5. **链接校验**：`./scripts/link-skills.sh --verify-only`（Windows `-VerifyOnly`），须回显「全部链接正常」；插件另跑 `scripts/link-plugins.sh --verify-only`（Windows `scripts\link-plugins.ps1 -VerifyOnly`）。
6. **服务端计数对照**：`opencode reload` 后拉 `skill.list` 落盘计数，真源须全部在列，片段见「结构校验」末尾。

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
# 全量：frontmatter + README 索引 + 红线路径 + 五 harness 安装数
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

真源：`config/global-AGENTS.md`（与目标文件字节一致）。链接脚本不碰各 harness 的 `AGENTS.md`，但 `-VerifyOnly`/`--verify-only` 会一并提示漂移：目标缺失计异常，内容不一致只警告（由人或代理手工合并，不自动覆盖）。新机 clone 后跑一次下面命令；已存在且不一致时只提示，需agent对比后合并(或手工合并，不是直接覆盖)。

Windows（PowerShell）：

```powershell
$src = Join-Path (git rev-parse --show-toplevel) 'config\global-AGENTS.md'
$dst = Join-Path $env:USERPROFILE '.config\opencode\AGENTS.md'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
if (-not (Test-Path -LiteralPath $dst)) { New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null; Copy-Item -LiteralPath $src -Destination $dst; 'restored' }
elseif ((Get-FileHash -LiteralPath $src).Hash -eq (Get-FileHash -LiteralPath $dst).Hash) { 'already in sync' }
else { 'differs, merge manually (one line), will not overwrite' }
```

Linux：

```bash
src="$(git rev-parse --show-toplevel)/config/global-AGENTS.md"
dst=~/.config/opencode/AGENTS.md
if [ ! -f "$dst" ]; then mkdir -p "$(dirname "$dst")"; cp "$src" "$dst"; echo 'restored';
elif cmp -s "$src" "$dst"; then echo 'already in sync';
else echo 'differs, merge manually (one line), will not overwrite'; fi
```

## 日常工作流

1. 改 skill: 直接改仓库里的 `skills/<name>/`，改完即对**本机**所有 harness 生效, 无需重新链接；跨机器用 `git push/pull` 同步，声称已对齐前按 `skill-authoring-sync` 的「跨机器同步与对齐判定」直接核对远端，不以 `git status -sb` 代替。
2. 新增 skill: 在 `skills/` 下新建目录 + `SKILL.md`, 然后在**每台机器**上运行一次该平台的链接脚本。
3. 删除 skill: 先运行 `-Unlink` / `--unlink` (或手工删除各 harness 下对应链接), 再删仓库目录。注意删除链接只删链接不删实体：Win 用 `Remove-Item <junction>`（不要加 `-Recurse`），Linux 用 `rm <symlink>`（不要加 `-r`，且路径末尾不要加 `/`）。
4. 原位置的实体在首次替换为链接时会自动备份到 `~/.skills-migration-backup/<时间戳>/<harness>/<name>`（Win 下即 `%USERPROFILE%/.skills-migration-backup/...`），备份移出 skills 目录是为了避免被 harness 误扫为重复 skill，确认无误后可手工删除备份。
5. 跑 skill-creator 评估时，过程产物（`outputs/`、`benchmark.json`、`review.html` 等 `*-workspace/` 目录）统一放仓库根 `.workspaces/<skill-name>-workspace/`（已在 `.gitignore` 忽略，本地独占）；**禁止**放入 `skills/` 下（链接脚本会对无 `SKILL.md` 目录告警，且过程产物不许进入真源同步）。留到 skill 稳定作回归基线，过时后整目录删除。

## 开源许可

MIT（见 `LICENSE`），可自由使用、修改、分发，保留版权声明即可。
