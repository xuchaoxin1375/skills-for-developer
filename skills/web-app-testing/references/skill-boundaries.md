## 测试相关 Skill 的职责与维护边界

本文件维护职责归属和协作方式，不定义另一套测试、阈值或门禁政策。调整相关 skill 的接口或发现规则冲突时读取；普通测试任务只按需要读取对应领域的指引。

### 唯一维护位置

| 决策或规则 | 维护位置 | 其他 Skill 如何使用 |
|---|---|---|
| Web 测试覆盖层、用例设计、编写时机、数据环境与测试维护 | [web-app-testing 正文](../SKILL.md)及其三个实施参考 | 按需引用方法，保留本领域的验收结果，不复制详细实施表 |
| 长期应用架构、ADR、契约演进、运行目标与维护方法 | [swe-gov](../../swe-gov/SKILL.md)及其领域参考 | 提供产品约束与工程决策，测试负责验证，交付负责证据与完成判断 |
| 交付等级、必需检查组合、DoR/DoD | [等级与门禁](../../ai-verified-delivery/references/levels-and-gates.md) | 按影响面定级；测试建议和局部清单不另定等级 |
| 交付状态、报告事实与授权边界 | [ai-verified-delivery 正文](../../ai-verified-delivery/SKILL.md) | 测试结果作为输入，不另定义总体完成状态 |
| 例外字段、风险接受与正式批准事实 | [交付例外与责任](../../ai-verified-delivery/references/spec-driven-delivery.md#例外与责任) | 运行/安全例外沿用项目权限与同一字段，不把原失败改成通过 |
| 验证入口契约、证据版本、零用例/跳过/重试判定 | [验证入口与模板](../../ai-verified-delivery/references/verify-and-templates.md) | 测试 CI 与专项 job 接入同一汇总政策 |
| 截图触发、取景优先级、采集、实际查看与视觉证据 | [视觉验收](../../ai-verified-delivery/references/visual-acceptance.md) | 设计、响应式、动效与 UI QA 提供判断内容，复用取景、证据与触发政策 |
| 浏览器发现、工具/运行器选型、自动化操作、截图工具及其进程托管 | [browser-automation](../../browser-automation/SKILL.md)及其参考与脚本 | 测试设计和 UI 诊断按需协作；单独浏览器任务不加载完整测试/验收流程；其他抓取工具需另验自身支持与回收能力 |
| 浏览器包/制品安装、国内下载代理与镜像选路 | [浏览器安装](../../network-access/references/browser-installation.md) | 安装与下载问题由 network-access 处理；可启动性由实际运行器验证 |
| 测试资源容量、并发预算、资源归属及异常回收政策 | [测试资源预算与回收](environment-and-maintenance.md#测试资源预算与回收) | 截图 guardian 是具体执行机制，不能替代整个测试环境或远程服务的资源管理 |
| UI 缺陷分类、诊断与专项验收方法 | [frontend-qa/catalog](../../frontend-qa/references/catalog.md) | 测试计划引用相关类别；不把完整 UI 扫描强加给每个后端任务 |
| UI 完成清单模板 | [UI DoD](../../frontend-qa/references/definition-of-done.md) | catalog 只链接模板；按适用范围纳入总体 DoD，不另判整个产品完成 |
| 界面设计与呈现规则 | [frontend-design](../../frontend-design/SKILL.md)及其领域路由 | 测试验证产品已确定的设计，不通过测试规范重选设计 |
| 轻量工具形态、打包/安装和 CLI/桌面专有基线 | [lightweight-app-builder](../../lightweight-app-builder/SKILL.md)及其 quality-gates | 本地 Web 按产品模型借用测试方法；不把轻量形态限制推广到普通服务端应用 |
| 仓库工作流、合并保护、依赖/密钥审计与构建供应链 | [repo-gov](../../repo-gov/SKILL.md)及其 CI 参考 | 请求仓库治理时使用；普通补测试不自动补社区文件或改分支政策 |
| Shell/Python/Node 脚本健壮性与风格 | [scripting-best-practices](../../scripting-best-practices/SKILL.md) | 编写相关测试/编排脚本时使用，不代替业务测试设计 |

保留简短的相同底线，例如“Mock 不证明真实持久化”，有助于局部阅读；可变的等级表、状态表、阈值、报告字段和详细实施矩阵只在归属位置维护。领域清单列出要验的结果，测试实施指引解释如何得到有效证据，两者不是重复测试要求。

### 选择入口与协作

| 用户主要问题 | 主入口 | 条件触发的协作 |
|---|---|---|
| 测什么、补回归、测试难维护 | web-app-testing | 有交付定级/验收需求才读交付政策；有 UI 专项才读 QA |
| 建立应用规范、架构/接口演进、运行与长期维护 | swe-gov | 工程约束交给测试验证；仓库配置和交付判断分别按需协作 |
| 功能是否完整、能否交付、证据是否足够 | ai-verified-delivery | Web 测试设计/环境缺口交给测试 skill，UI 专项交给 QA |
| 已有页面交互/布局/可访问性缺陷 | frontend-qa | 跨到真实 API、存储或业务回归时借用测试方法 |
| 浏览器装在哪、工具/运行器怎么选、浏览器自动化操作、拍截图、shot-quick 卡住或进程残留 | browser-automation | 需要测试覆盖、断言与回归维护才转 web-app-testing；页面缺陷判断交 frontend-qa，安装下载交 network-access |
| playwright install / scrapling install、国内浏览器下载慢或制品镜像配置 | network-access | 路径发现引用 browser-automation，Scrapling 的初始化及专用引擎按 resilient-browser-fetch 核对 |
| 新建或改版界面 | frontend-design | 设计完成后按风险验 UI；新增业务行为时规划对应测试 |
| 模糊的轻量小工具需求 | lightweight-app-builder | 先确定形态；仅对适用 Web/GUI 引用专项，不让 CLI 套 UI 全流程 |
| 建 CI、提交前治理 | repo-gov | 根据项目测试命令接入；有测试设计问题再读取测试方法 |

引用是按需读取，不是递归调用。进入协作 skill 时只补当前缺少的决策，不重新启动父流程；同一主问题不因多个 description 命中而叠加多套完整工作流。

浏览器工具按 URL、截图文件和资源收尾交付，自动化测试按场景、断言和回归用例交付。依用户所需结果选入口，不能只凭出现 Playwright 就同时启动所有测试相关 skill。

同一任务共用一份 AC/测试计划、一套项目检查入口与一份交付报告。多个 skill 可以引用同一次版本匹配的测试、截图和日志；已完成且仍有效的检查不重复执行。相关输入变化、失败未解决或影响面扩大时，依交付政策重验。

### 冲突与维护

用户和项目明确约定优先。在同一范围出现冲突时，先核对上表归属位置和实际影响，修正引用方或过期模板；不能简单合并所有清单或取最严规则，造成范围无故扩张。领域检查不能削减当前必需验证，方法示例也不能增加未经确定的产品承诺。

修改规则先改归属文件，再检查调用它的入口、模板与 README 索引；只有职责改变才更新本表。CI 分组可按项目变化，但不能另建一套验收状态或“通过”政策。项目确需复制模板时记录来源与版本并按项目政策维护，skill 仓库内不保留同一模板的多份实体。

维护走查至少包含：纯后端补测试不启动 UI 全扫；UI 缺陷不强建数据库；CLI 交付不套 UI DoD；跨层功能共用计划和证据；必需集成失败不能由快速检查通过覆盖；同一截图按同一来源判定。静态引用正确只证明文件关系有效，不证明代理一定遵循路由。
