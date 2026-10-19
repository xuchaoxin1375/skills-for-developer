## 更新日志

记录本仓库的迁移历史与重要变更。后续仅记录影响使用或维护的变化，例如新增 skill、职责或触发条件调整、兼容性及治理变化；纯措辞或排版微调无需逐条记录。

### 未发布

- `resilient-browser-fetch` 把 `curl_cffi` 提为层 0 推荐依赖并接出 `--impersonate`：此前它只在代理 scheme 为 socks5/其他非 http(s) 时才被调用，且写死 `impersonate="chrome"`（滚动别名指向的 Chrome 版本随 curl_cffi 升级漂移，无法固定与复现），因此用 http 代理时层 0 永远是 Python 栈的 TLS 指纹。现在 `FetchOptions.impersonate` 与 CLI `--impersonate <目标>` 会让层 0 走 curl_cffi 的浏览器同族 TLS/HTTP2 指纹（默认目标 `chrome124`，目标名按 `curl_cffi.requests.BrowserType` 校验；未装 curl_cffi 或目标非法在参数校验阶段直接报错，不静默退回），结果记 `notes: impersonate:<目标>` 并在日志说明；socks 路径改用同一默认目标，`StaticSessionOptions.impersonate` 让静态批量也可用，curl_cffi 路径补齐与 stdlib 路径一致的 `retries` 重试（实测经代理的 TLS 握手偶发 `OPENSSL_internal:invalid library`），`probe_static` 与 `check_environment.py` 的提示由"不可用"改为"推荐安装"。文档写清边界：可过部分站点的 TLS/客户端指纹检查，但不解 JS 挑战（挑战仍要层 2）；浏览器层自带指纹并会告警忽略该参数；`requests`/`httpx` 不改变 TLS 指纹，故不列为依赖。
- `resilient-browser-fetch` 判定与等待时机两处调整：`validation_reasons` 不再把状态码单独判为拦截——HTTP 403 且正文无拦截特征、长度达标、调用方 `expected_texts`/`--expect-text` 全部命中时按可用内容接受，结果写入 `notes`（`http_status:403:accepted_by_content`）并在日志告警，其余 4xx/5xx 与任何带内容侧信号的响应仍失败（站点对可疑请求回 403 却下发完整正文时不再被误判为拦截页并白升一档，实测该正文可能尚未水合，需要完整客户端渲染仍应显式升层）；新增 `--wait-until`/`FetchOptions.wait_until`（`commit`/`domcontentloaded`/`load`(默认)/`networkidle`）决定取源码与关闭窗口的时机，层 1 直接映射 Playwright `goto(wait_until=...)`（已是 networkidle 时不再重复等待，`--network-idle` 保留为遗留开关），层 2/3 把 `commit`/`domcontentloaded` 映射为 Scrapling `load_dom=False`、`networkidle` 映射为 `network_idle=True`，层 0 告警忽略。SKILL.md 与 `module-api.md` 补等待判定表、403 语义，以及"汇报用表格给出实际出口、各引擎模式与结果、文件与大小、notes 注记"的要求；`platforms.md` 记录不传 `--profile-dir` 时临时 profile 随进程清理、异常终止会在系统临时目录留下 `resilient-fetch-*` 与 Playwright profile/artifacts 残骸的前缀与清理口径。
- `resilient-browser-fetch` 补齐层 1 批量会话 `BrowserBatchSession`（`browser_session.py`）：单 browser/单 context、每页一个 tab、受限并发，只要 playwright/patchright，不再为"需要渲染但无挑战"的批量任务装 scrapling；复用 `SiteRequest`/`FetchResult`/`PageRejectedError`/`WarmupError` 契约与同源/路径/文本校验，并因有真实 DOM 而额外支持 `expected_selector`/`wait_selector`；命中挑战抛错并带 `block_reasons` 供升档，`headless=False + challenge_wait_ms` 可等人工过验证，另有 `wall_timeout_ms` 单页硬超时、`retries` 瞬时错误重试、可选 `profile_dir`/`screenshot_dir`。批量工作流按依赖给出三条会话路径的选择表（层 0 `StaticBatchSession` / 层 1 `BrowserBatchSession` / 层 2+ `SiteSessionManager`）与升档触发条件。
- `htmlmini` 渲染通路对接上游分层引擎并支持指定解释器：save_page 通路按上游可用层判断（层 1 只渲染、层 2/3 带挑战求解），有求解引擎/需要 `--headful`/本机无 Chrome 时走 save_page，层 1 与 Chrome 同能力时优先零依赖 Chrome `dump-dom`，Chrome 崩溃再回退 save_page 并合并两段报错；新增 `--python-bin` / MCP `python_bin` / `HTMLMINI_PYTHON`（默认 `python`/`python3`，往往不是装了 playwright/scrapling 的环境），支持 `auto` 扫描本机 conda/venv/uv/PATH 自动挑选具备层 ≥1 的解释器（日志明示，`HTMLMINI_ENV_SCAN=0` 可关闭）；显式指定后不回退、指错即报错，渲染失败的错误信息会点名实际探测的解释器并在存在更合适环境时给出其路径；Trafilatura 增强同样遵循该解释器。
- `resilient-browser-fetch` 引擎按能力分四层并解除 scrapling 硬依赖：层 0 `static`（stdlib，零第三方依赖）→ 层 1 `playwright`（普通渲染，无求解）→ 层 2 `scrapling`（挑战求解）→ 层 3 `cloak-cdp`（指纹底座）。`auto` 只把**已安装**的引擎列入顺序并按层升档，缺件记 `skipped(unavailable)`，不再"所有引擎均失败"；显式 `--engine` 缺件仍硬失败。新增层 0/层 1 引擎、层 0 批量会话 `StaticBatchSession`（首页单路预热 + 受限并发 + 每页硬超时，命中挑战抛错交由调用方升档）；`attempts.json` 升到 `schema_version: 2` 并给每个引擎标 `kind`（`ok`/`blocked`/`blocked_or_empty`/`unavailable`/`runtime_error`）。依赖按层拆文件：`requirements.txt` 收敛为本层 0 依赖（仅可选 `curl_cffi`），新增 `requirements-stealth.txt`（层 2），`requirements-cloak.txt` 改为引用层 2。`check_environment.py` 新增 `--list-envs`：扫描本机候选解释器（当前、`VIRTUAL_ENV`/`CONDA_PREFIX`、PATH、Windows `py -0p`、conda registry 与常见根目录、venv/virtualenv/uv 目录）逐个子进程探测可用层与包，按能力排序并给出可复制的运行命令；环境归属改按前缀内容识别，未 activate 直接调用环境解释器也能认出 `conda:<env>`/`venv(uv)`，`conda run` 示例一律补 `--no-capture-output`（GBK 控制台下不加会 `UnicodeEncodeError`）。层 1 现在也支持有头人工验证：`--headful --challenge-wait-ms` 会打开窗口、等人工过完验证再执行选择器/截图/取源码，并打印操作指引与进度；缺件跳过与全缺件失败都会提示"依赖可能装在别的 Python 环境"并指向 `--list-envs`。
- `repo-governance` 补存量仓库判断与代理交接记录：改造轨道要求先读既有 git 状态（`git status`/`git diff`/`git ls-files`/`.gitignore`）作判断依据，发现口径不一致（未追踪且无规则覆盖的大目录、已入库的应忽略产物、规则互相矛盾）作为问题列给用户而不擅自改口径；代理上下文一节要求把已确认的项目级约定与偏好（是否入库、改动后跑哪些检查、提交与推送方式、需先问的范围）写进 `AGENTS.md`，避免后续代理重复调研与重复提问。
- `repo-governance` 补提交范围与产物默认策略：`.gitignore` 一节把构建产物与缓存的默认排除引到红线节并给出 Node 侧清单（`.next/`、`.nuxt/`、`.svelte-kit/`、`.turbo/`、`.vite/`、`coverage/`、`*.tsbuildinfo`），要求由规则明文表达，说明隐式排除不可审计；AI 操作约束新增「提交范围拿不准先确认」，澄清未追踪且无忽略规则只说明还没决定，不等于有意排除。
- `skill-authoring-sync` 扩展职责与触发：新增「同步 harness 配置偏好（本机 → 真源）」流程（逐字段比对、采纳取舍、写入、校验、提交授权），description 与 README 索引补「同步配置」「同步 opencode 设置/偏好」触发词；`user-profile` 动词命中表补同源入口。`config/opencode/cli.json` 真源回写本机现状（补 `keybinds.session.toggle.thinking`、`tabs.mode`，`session.thinking` 改 `hide`）。
- 新增 `config/recommended-skills.txt`（需依赖/命令的复杂 skill 推荐部署名单，首批 `htmlmini`）：链接脚本在链接完成后处理名单——依赖（`pnpm install`，交互询问缺省 Yes，非交互默认跳过）与命令安装（默认装成直接可调用：Linux `~/.local/bin`，Windows `%USERPROFILE%\.local\bin` 并补用户 PATH；`--verify-only` 一并检查，`--unlink` 同步移除命令、保留依赖目录）。`check-skills.py` 加名单一致性检查（名单孤儿报错，含 `package.json` 却不在名单提醒）。
- README 新增「部署清单（新机 / 首次 / 代理执行）」：链接安装（非交互须首跑带 `--apply-recommended-cli`/`--skip-recommended-cli`，免二次全量）→ 全局 AGENTS.md 恢复合并 → 结构校验 → 链接校验 → 服务端计数对照五步有序给出；服务端计数补「落盘再解析」的跨平台计数片段（长 JSON 走管道会截断，`missing` 须为 `none`）。新增 `docs/wsl-opencode-reuse.md`：规定 WSL 复用 Windows 侧 providers、密钥与代理的配置分层、三种方式选型、密钥红线与验证，skill 分发仍走链接脚本。
- 新增 `scripts/check-skills.py`（零依赖，Windows/Linux 通用）：一遍校验 frontmatter（`name` 与目录一致且 kebab、非空 `description`、多行须 `>`/`|` 折叠缩进）、README 检索入口、红线真实路径、五 harness 安装数；补上链接脚本只查存在性不查内容的盲区。用法见 README“结构校验”一节，`--no-harness` 可进 CI。
- `doc-rewrite-review` frontmatter 改 `>` 折叠块：此前 `description` 第二行顶格续行，被服务端静默丢弃（`skill.list` 42 缺 1，链接校验却全绿），现恢复 43；`opencode-provider-config` 示例 `/tmp/setenv.log` 改 `"$HOME/setenv.log"`（红线禁写死 `/tmp`）。

- 新增 `user-profile`（个人常驻默认值：网络选路与 PowerShell 执行底线，及转调 `network-access`/`powershell-pitfalls` 的指针；仅由全局 AGENTS.md 显式加载，`autoinvoke: false` 不进候选列表；全局 AGENTS.md 收敛为一行）。
- 全局偏好可恢复：新增 `config/global-AGENTS.md`（与 `~/.config/opencode/AGENTS.md` 字节一致），README 补新机恢复命令；缺才复制、不一致只提示不覆盖。
- `powershell-pitfalls` 升级默认 UTF-8：每次 PowerShell 调用先设输出编码、Python 探针用 `-X utf8`；`link-skills.ps1` 脚本内默认 UTF-8 回显（5.1 的 GBK 默认不再污染采集侧）。
- `frontend-design` 与 `adaptive-responsive-guide` 明确整体设计/响应式专项分工，在线框阶段识别空间约束，统一断点、滚动与浮层选型及范围化验收；截图助手支持320px、自定义宽度与实际视口核对。
- `web-animation-guide` 集中交互实现、退出布局保持与中间帧验证，动效设计预算由 `frontend-design` 维护；补齐可运行弹窗/忙态/下拉示例与15项浏览器回归，同步前端QA清单。
- `agentic-web-search` 补齐搜索/抓取的并发与频率约束、共享冷却、有限重试与预算控制，区分临时限流和配额耗尽，同步提示词与回归场景。
- `network-access`（原目录 `local-env` 已更名收尾，目录与 frontmatter `name` 一致）：扩展国内试验与海外生产的跨平台网络指导，覆盖 GitHub 加速核验、超时/403 分流和 Python/Node.js 依赖及额外下载；相关调研与构建 skill 统一引用，归档带日期的目标实测；各 harness 侧 `local-env` 重复链接移除，只保留 `network-access`。
- `network-access`（原 `local-env`，国内用户出网与下载偏好：镜像优先、代理次之、裸连兜底的回退流程，附本机实测环境；仅供参考，实际不一致时以实际为准）。
- `htmlmini` 可靠性：远程抓取默认 30s 超时（之前无超时可挂起），空/脏 HTML 不再崩（linkedom 空文档 `title` 抛错已修），终端裸跑无管道时直接提示；`npm test` 现跑 smoke 17 + MCP 自检 + 新增 `reliability` 36 断言（编解码、本地回环 HTTP、CLI 退出码、MCP 错误路径，全无外部依赖）。

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
