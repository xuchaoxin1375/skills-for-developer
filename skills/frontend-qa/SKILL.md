---
name: frontend-qa
description: >
  存量 Web 前端缺陷诊断与视觉验收。用于页面空白、布局溢出/响应式、弹窗/焦点、可读性/对比度、无障碍 axe、表单、导航、深色模式、CLS/LCP/INP、跨平台、欺骗模式、AGENTS.md UI 约束及 DoD/CI 门禁，也用于 Agent 查看截图判断 UI 缺陷。
  新建或美化界面先走 frontend-design；单独浏览器发现、截图工具使用与自动化操作走 browser-automation；测试用例与回归体系走 web-app-testing；安装下载走 network-access；响应式改造方案与断点设计走 adaptive-responsive-guide，粘性定位细节走 sticky-position；UI 侧 DoD 检查留在本 skill，交付定级与跨阶段质量门禁走 ai-verified-delivery。
---

# Frontend  QA（存量前端缺陷诊断与验收门禁）

你按资深前端质量工程师兼 Design QA 负责人行事。UI 分类与专项诊断以本 skill 的 `references/catalog.md`（合并版盘点，`L/C/S/V/A/F/N/I/D/P/G/H` 编号体系）为准，阈值争议以 catalog 开头“来源声明”和所引用领域正本为准；UI 完成清单只在 `references/definition-of-done.md` 维护。

分工：新建/改版/美化（线框、令牌、UX 文案）先调 `frontend-design`；本 skill 负责**存量 UI 诊断与专项门禁**，不重复设计决策。浏览器发现、工具选型、截图和自动化操作复用 [browser-automation](../browser-automation/SKILL.md)。

需要规划前后端测试、编写业务回归或建立真实 API/数据库测试环境时按需读 [web-app-testing](../web-app-testing/SKILL.md)；本 skill 继续负责 UI 缺陷与体验专项，共用计划和有效证据，不重新启动测试或交付全流程。快慢分层不另定放行政策；完整交付按 [唯一等级矩阵](../ai-verified-delivery/references/levels-and-gates.md)，截图触发、取景与证据按 [视觉验收](../ai-verified-delivery/references/visual-acceptance.md)，局部缺陷优先特写，遮挡与滚动关系保留视口上下文。

## 何时读什么（渐进加载）

- 单独浏览器选型、截图、安装位置或截图进程回收任务转 `browser-automation`，不启动 UI catalog、DoD 或完整测试流程；询问安装/下载则转 `network-access` 的安装参考。
- 诊断页面缺陷时先读 `references/catalog.md` 的对应类别节，不要通读全文：
  布局→`L`；假数据极值→`C`；缺状态→`S`；跳动卡顿→`V`；对比度焦点语义→`A`；表单→`F`；URL后退→`N`；动效toast→`I`；间距色彩深色→`D`；Win/Mac/iOS/微信→`P`；约束agent→`G`；欺骗性模式→`H`。
- 需要可执行检查时读 `scripts/` 下对应脚本（控制台粘贴或进 CI），不要背诵。
- 启动浏览器、服务或重复截图验收前，读[测试资源预算与回收](../web-app-testing/references/environment-and-maintenance.md#测试资源预算与回收)，按可用容量限制worker/实例并发，登记并验明异常收尾；不得叠加未回收的失败轮。
- 需要采集 UI 证据时，截图方式和执行按 [托管截图工作流](../browser-automation/references/screenshot-workflow.md)；需要定位系统浏览器时读 [浏览器发现](../browser-automation/references/browser-discovery.md)。本 skill 判断页面缺陷与证据是否足够，不另维护浏览器候选、超时或回收实现。
- 需要 UI 完成清单时读 `references/definition-of-done.md`，按适用范围纳入项目 `AGENTS.md`/`DESIGN.md`；优先引用，需项目快照时标注来源与版本，不把 UI 清单当整个产品的完成标准。
- 对比度/可读性读取 [共用规范](../frontend-design/references/contrast-readability.md)，按实际背景测量并补测自动未判项；例：图片上白字不能因axe无报错而放行。

## 模式一：评审存量 UI（Review）

1. 确定输入：变更范围、可运行入口/路由、预期用户结果和已有证据；截图可以由本流程采集，不要求用户预先提供。缺少入口或预期结果时先补齐，不能只凭静态代码宣称视觉验收。
2. 先执行可自动断言的用户流程：点击、填写、提交、取消、关闭、Esc、后退、刷新和等待；断言可见状态、业务结果、焦点回归和数据变化。自动化能发现的问题先修复，不用截图替代行为测试。
3. 根据变更风险决定是否截图：纯文案且不影响几何/状态的错别字可免截图并记录理由；按钮、导航、表头等文案可能改变换行/挤压时要做针对性检查；布局、弹窗、状态和交互变化必须让 Agent 实际打开关键状态截图。Agent 按用户任务检查按钮响应结果、弹窗是否可关闭、关闭后的页面/焦点状态、元素挤压遮挡、溢出裁切、文字完整性和响应式操作区。截图验收不是图片存档、像素处理或“文件存在”检查。显示类缺陷以症状区像素截图与几何测量（列宽/行高/裁剪边界）为准；类名、透明度、命中测试、打印正常都不等于屏幕画出；先留存修前失败证据再修再回归。
4. 按影响面选择 `L/C/S/V/A/F/N/I/D/P/H` 对应类别；全面 UI 盘点时再按类别逐项检查。每条命中给已有编号（如 `L-02`），新类别单独说明，不冒充 catalog 编号。
5. 每个命中项输出四要素：现象→根因→修复（含代码）→验收。修复优先 catalog 已有方案，禁止用 `overflow:hidden` 掩盖溢出、禁止裸 `outline:none`、禁止 `user-scalable=no`。
6. 按产品支持范围和改动选择宽度，覆盖相关断点两侧、等值及问题区间；不能只测几个端点就宣称连续适配。`320/360/390/480/600/768/834/1024/1180/1280/1440/1920` 与 `400px` 矮视口是候选样本，不要求每个局部修复全扫。响应式判据按对应领域规范。

## 模式二：约束新生成（Generate）

1. 输出组件代码时强制满足：`min-width:0`（可收缩子项）、媒体 `max-width:100%+height:auto`（禁 `width:auto`）、容器 `max-width` 非固定宽、表单可见 `<label>`、图片有尺寸/`alt`、异步视图 `Loading/Empty/Error` 三态起步。
2. 颜色间距字号只许引用设计令牌；动效预算见 `frontend-design/references/motion.md`，技术与减弱/回退验收见 `web-animation-guide/references/performance-a11y.md`，不另设属性禁令；目标≥`24×24`（移动端 `44×44`）。弹窗/列表/耗时操作检查双向反馈与忙态，允许减弱/兼容路径瞬时切换；无忙态连点可重提须修复。关键状态截图由 Agent 实际查看，附自动化动作结果和截图证据，不以截图替代 Playwright 断言。
3. 在 `DESIGN.md`/`AGENTS.md` 中声明 MUST/SHOULD/NEVER 并绑定检查器（axe/stylelint/Playwright），情绪板式描述（“现代简洁有呼吸感”）一律改写为数值枚举。

## 速查阈值（与 catalog 一致）

- CWV：`LCP≤2.5s / INP≤200ms / CLS≤0.1`（75分位，节流冷缓存测；0.08 说法不采纳）。
- 对比：普通文字 `≥4.5:1`，大字 `≥3:1`，必要图标/控件识别线索对相邻色 `≥3:1`；placeholder与只读值不豁免，装饰边框不一概3:1。项目强化与AAA另标，详见共用规范。
- Reflow：`320px` 单列无二维滚动（即 `1280px@400%`）；文本间距覆盖下无裁切。
- 目标 `≥24×24`，焦点 `:focus-visible` 且不被遮挡（2.4.11）。

## 输出格式

评审报告一律用此模板：

```markdown
## UI评审结论（共 N 项：阻塞 X / 建议 Y）
### [BLOCK] L-02 min-width:auto 陷阱（卡片标题撑破）
- 现象：…
- 根因：…
- 修复：```css … ```
- 验收：…
```

生成任务末尾必须附自检清单：适用的宽度检查 + axe 零违例 + 自动化关键旅程 + 视觉触发决策（截图结论或有理由的 `N/A`）+ DoD 勾选结果，缺一即视为未完成（对应 `G-10`）。
