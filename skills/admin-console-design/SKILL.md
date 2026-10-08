---
name: admin-console-design
description: >
  后台控制台/管理面板设计与实现(Cloudflare风格):外壳与侧边栏（折叠/Rail/悬停peek/抽屉）、顶栏、数据表格（列宽拖拽/排序/批量/粘性操作列/窄屏切卡）、表单与设置页与向导（两级校验/草稿/离开保护/危险区）、设计令牌与深浅主题、响应式与无障碍验收。
  凡是提到后台面板、管理后台、控制台、admin/console/dashboard、DNS记录/站点设置这类页、侧边栏和折叠悬停展开操作、表格调宽（列宽调整）/排序/筛选/批量/行内编辑（表项编辑）、表单校验/向导/设置保存，或说要做/评审一套像Cloudflare的控制台、查控制台反例与传统缺陷，即使没点名本skill也要加载。
---

# 后台控制台设计

共同栈 React19+Vite7+Tailwind v4 CSS-first+Lucide+单文件+自研hash路由+无后端（localStorage mock）。
本 skill 给出**可直接复用的骨架 + 为什么这样做**，细节查 `references/`，不要在 SKILL.md 外自创第五种页型。
参考稿即标准模板：先复用其设计与交互细节，再按业务调整功能对接；不模糊借鉴、不跨稿拼凑，调整写理由。例：侧栏照 fable 搭，导航项与按钮按程序功能换、接到真实功能。
构建产物三步用（见 `references/builds-comparison.md` §4–§5 定参考来源）：先定来源再双击对应 `index.html` 离线开，亲手点出折叠/悬停/抽屉/命令面板/窄屏再看；条件允许时用浏览器工具渲染截图验证所见；落地数值以本页收敛口径为准，不直接复用产物数值。例：调侧栏先开 fable 点 Collapse 再悬停截图，看内容是否移动。

## 适用范围

- 新建后台控制台、管理面板、站点级控制台（外壳+导航+表格+表单+设置+概览）。
- 改版现有控制台的侧边栏、表格、表单页（先按本 skill 骨架对齐，再谈视觉）。
- 评审他人控制台实现（按文末自检逐项打勾）。
- 不用本 skill：纯落地页/小工具视觉发散（转 `distinctive-design-director`）、
  通用响应式收纳选型（转 `adaptive-responsive-guide`）、存量页按编号查根因（转 `frontend-ux-qa`）。

## 工作流程（按 0–5，评审只走 5）

### 0——先定页型，再读对应的 reference

四种页型四选一，不自创：

| 页型 | 何时用 | 必读 |
|---|---|---|
| 仪表盘 Overview | 状态总览+快捷入口，无重型图表时用 Stat+清单代替 | 主流程即可 |
| 列表+编辑（旗舰） | DNS记录式：搜/筛/排/页/选/批量/行内改 | `references/tables.md` |
| 表单单列/设置页/向导 | ≤7字段单列卡；多组设置一卡一决策；多步用 Stepper | `references/forms.md` |
| 外壳 Shell | 任何页都需要先定外壳 | `references/shell-sidebar.md` + `references/tokens.md` |

令牌先行：任何视觉决策先写进 CSS 变量（见 `references/tokens.md`），组件只用语义类，禁裸色。

**收敛口径**（三工程原值有分歧，以本表为默认；分歧本身是各工程的真实设计选择，
如 gpt `docs/05` 声明这些数值非 Cloudflare 官方，同项目内必须只用一套、不许混）：

| 项 | 本 skill 收敛 | fable | sonnet | gpt |
|---|---|---|---|---|
| peek 进/出意图延迟 | 120/220ms | 110/220 | 120/250 | 120/240 |
| 侧栏宽度过渡时长 | 240ms | 280 | 220 | 220 |
| 列宽键盘步长 | 8/32 | 16/64 | 8/32 | 无列宽拖拽 |
| 表格切卡片阈值 | 容器 <640 | <640 | <700 | <640（@container） |
| z-index 套 | fable 完整套 | 完整套（顶栏50…Toast100） | 简化套（顶栏20…Toast80） | 按需 |
| 圆角档 | 4/6/8/12 | 4/6/8/12 | 4/8/12/full | 4/6/8/12 |
| 外壳断点 | <768 抽屉 / 768–1023 Rail / ≥1024 固定 | 同左 | 同左 | 工作台 ≤1000 / 站点 960（docs 内 960/961 与实现互斥，以实现为准） |
| 抽屉宽度 | min(288,100vw-48)，原生 dialog | min(264,85vw) | min(288,100vw-48) | 280~300 |

注意"意图延迟"（进/出 peek 前的等待）与"宽度过渡时长"（width 动画本身）是两回事，别混写。

### 1——搭外壳（Topbar 56 + Sidebar + Page）

为什么槽与视觉要解耦：悬停展开若推挤内容，整页会左右抖一次；覆盖展开则内容不动，
用户只感到“浮出一层”，这是三份工程一致选择覆盖（overlay）而非推挤的原因。

- 骨架：`Topbar(sticky h56 z50) + Sidebar(slot占位) + main(max1440 居中 flex-1 min-w-0) + footer`。
  文档级滚动，侧边栏与顶栏 sticky，不要整页定高锁死。
- 尺寸默认：展开 240（定死不再改），Rail 56，顶栏 56，内容 max1440，
  表单卡 720（向导 768，设置 896）。三工程分别是 224/240/264，本 skill 收敛为 240。
- 侧边栏状态机（详见 `references/shell-sidebar.md`）：`pinned(展开/折叠，持久化) / hover-peek / kbFocus-peek / forced(触屏点开) / suppressed(点收起后直到离开一次) / drawer(<768)`。
  设计与交互以 fable 为默认（见 `references/builds-comparison.md` §1）：区域与结构、状态机、覆盖行为、通用控件（搜索框、返回上级、导航分组、底部收起）复用，六态、覆盖不推挤、像素坑逐项对齐；导航项与功能按钮按程序换、对接真实功能；通用控件的增删先申请并写理由。例：导航项可换，搜索框与收起按钮不删。
  进/出意图延迟 120/220ms（见收敛口径表），只动 width/box-shadow/opacity，文字用 opacity+visibility 延迟 75ms，
  不用 display:none（保读屏可读），不用 height:auto/left/top 做动画。
- 顶栏：汉堡（仅窄屏）+ Logo + 资源切换器（星标+域名truncate+套餐Badge）+ 右侧 AskAI/Support（窄屏藏文字）+ 通知/主题/头像。
  资源名 `max-60vw truncate`，极窄允许藏次要入口但永不藏主操作。

### 2——定令牌与主题

为什么只换令牌不换代码：深色不是滤镜反转，而是另一套低亮灰+提亮主色；
先定义好两套变量，组件零改动跟随主题，这就是三工程都用 `data-theme + color-scheme` 的原因。

- 语义层：`bg/subtle/hover/surface/canvas/text(1-3)/border/primary(+hover/soft)/success/warning/danger(+soft)/brand(橙，只做标识≤5%)/focus/link`。
  浅色主蓝 `#0051c3`，深色提亮 `#6ea8ff ~ #7fb0ff`（保白字对比）， brand 橙 `#f6821f` 两主题同值。
- 字体：正文 Inter + PingFang/YaHei，技术值等宽 + `tabular-nums`；字号 ≤7 档，圆角 4/6/8/12（或 sonnet 的 4/8/12/full，二选一），
  阴影 3 级，间距只用 4/8/12/16/24/32/48；图标与参考稿同语义同图形整套复用，只用一套 Lucide（16/18/20），不自选近似图标；无对位图标时用同语义 Lucide 并声明，不硬套错语义图标；同一侧栏内图标不得重样，不同功能必须可区分。例：搜索用 Lucide Search，不手画放大镜；任务无对位图标，用同语义 History 并声明；查记录另用 Database 与搜索区分。
- 主题：`light/dark/system` 三态 + localStorage + 首屏内联脚本读缓存设 `data-theme` 防闪；
  `color-scheme` 跟随主题。动效 `120/200/280ms + cubic-bezier(.2,0,0,1)`，只过渡 transform/opacity/width/grid-rows，
  `prefers-reduced-motion` 压到 0.01ms。层级收敛为 fable 完整套：侧栏20/peek40/顶栏50/抽屉60/Popover70/Tooltip80/Dialog90/Toast100/跳链100
  （sonnet 简化套 20/30/40/80/100 为可选变体，同项目只用一套，两套明细见 `references/tokens.md`）。
- 复制即用值见 `references/tokens.md`。

### 3——做表格（列表页是控制台的脸）

为什么工具栏主操作永远在最右：用户视线从左（搜索）扫到右（Add），右端是操作落点；
三工程一致把 primary 放最右，危险 Delete 藏进批量条/行末图标，这就是“首屏一件事”的落地。

读 `references/tables.md` 按此骨架：`PageHeader + Alert汇总 + 工具栏(搜索flex-1 max520 + Filters + Display + Import/Export + Add primary最右) + chips + 表格卡(配额条+表+Showing) + 浮动批量条 + 分页`。
表/表单默认复用 fable DNS 页的设计与交互（骨架 9 层＋行内/弹窗共用同一表单同一校验）；列宽与 Undo 按 sonnet 口径、导入原子性按 gpt 口径，数值按收敛口径。例：先开 fable 对骨架，再按另两家补齐短板。

- 搜索防抖 150ms，Filters 草稿/应用分离（Apply/Enter 才生效），Display 记列显隐+密度到 localStorage。
- 表：`table-fixed + colgroup + 每列min/max（Name140-520/Content160-720类）+ 固定列禁调 + 填充列吸余`；
  表头按钮三态排序 + `aria-sort`；首列复选（含 indeterminate + Shift连选 + 选全部匹配）；
  末列操作 `sticky right0 + 不透明行实色 + 滚动阴影`，Edit 文因是主行操，Delete 用图标。
- 列宽调节：8px 热区/1px 线/hover 3px 主色，`role=separator + 键盘←→8/Shift32/Home还原/双击还原`（sonnet 步长，fable 为 16/64，见收敛口径表），
  拖时只写 DOM 松手才 setState+持久化，止冒泡防误排序。
- 行内展开与弹窗共用同一表单同一校验（RecordEditor 模式），开后焦点进首字段，关后回 Edit，
  `aria-expanded/haspopup`。批量条 `fixed bottom16 max520 深色`，删除给 Undo（8s）优于强确认。
- <640px 容器切卡片（sonnet 工程为 <700，统一用 <640；三行式，thead保留语义但视觉隐藏），表卡只渲染其一防双编辑器重 id；
  表容器自有 `overflow-x:auto + 可聚焦region`，页面级永无横滚。
- 列表不过屏：任何列表不得撑出单屏高度，长列表必须分页＋表内滚动（表头 sticky）。例：59 个账号分 6 页，表框内滚。

### 4——做表单/设置/向导

为什么保存按钮不置灰：置灰等于不告诉用户缺什么；三工程一致用“可点提交→汇总→首错聚焦→保留输入”，
这就是两级校验（失焦即时 + 提交汇总）的由来。

读 `references/forms.md`：

- 结构：`Field(label+control36px+hint/error role=alert+计数器) + 必填*/Optional + placeholder只做示例`；
  布局 <640 单列按钮 `flex-col-reverse` primary 在上，≥1024 用 12 栅，≥7 项分组，≥3 组加右侧粘性大纲。
- 校验：纯函数 `validateRecord`（一字段一可行动消息：哪里错+为什么+如何改，给示例值）；
  `noValidate + blur单字段 + 已touched输入同步 + 提交全量+汇总Alert+首错focus+scrollIntoView + 保留已填`；
  服务端冲突映射回字段。允许粘贴+规范化，窄屏输入 16px 但禁禁缩放。
- 联动：Type 切换 label/placeholder，互斥时强制（如 MX/TXT 关代理）并说明原因；条件字段出现才校验，切换清不适用值。
- 草稿：新增每次 update 持久化，取消/关抽屉 Toast“草稿已保留”，成功清空；编辑仅实例内。
  脏保护：JSON 比对 + 站内守卫 + beforeunload，保存即解，删除时清脏防幽灵拦截。
- 设置：一卡一决策，Footer 左状态右 Save（dirty 才启用），Toggle 即时+toast；危险区底部独立红描边远离首屏，
  高风险输名确认但按钮可点（以校验说话）。向导：线性进度可回退，换步焦点到标题，最后 Review 汇总回改。
- 浮层：Popover 非模态（外部点/Esc 关+视口夹取，<640 变底板），Modal 原生 dialog（焦点陷阱+Esc+回焦），
  Toast 右下 live polite（成功5s/撤销8s）。

### 5——验证交付（评审与交付都走这里）

- 三宽 390/768/1440 + 极端 300/320：`scrollWidth<=innerWidth` 页面无横滚，长 URL `break-all`，浮层 `min(期望,100vw-16)`。
- 侧栏：hover 不移内容（main left 不变），键盘 Tab 聚焦亦 peek，触屏点开点外关，`[` 与 Ctrl+K 可用，Rail 零文字泄露+不可聚焦。
- 表单：空提交聚首错→非法标 `aria-invalid`→合法保存→刷新持久→重开空；草稿取消保留；删除二次确认默认焦非危险键。
- 主题三态 + reduced-motion 各验一次；200%/400% 缩放回流单列；拔鼠（纯键盘）走完新增改删撤销。
- 交付物：页型结论 + 令牌 diff + 三断点截图 + 验证记录 + 已知问题。截图先全景后特写，浮层用视口截图。

## MUST / SHOULD / AVOID（精简，详见 references）

- MUST：四页型四选一；令牌先行禁裸色；槽视觉解耦+覆盖不推挤；悬展必有键盘等价；触屏有点开按钮；
  表格末列粘性常驻+不透明；保存不置灰而是提交校验+首焦；脏保护+删清脏；页面无横滚；焦点可见；对比正文4.5/非文3；
  语义按钮不用 div onClick；图标按钮必有 aria-label；禁禁粘贴/禁缩放；危险远离首屏+二次确认。
  悬浮覆盖零位移：peek/抽屉展开时图标列 x/行高两态不变、文本全单行，用探针验几何一致+内容不动+点击落点对（见 references/shell-sidebar.md“覆盖展开零位移”）。
- MUST：侧栏复用 fable 的设计与交互（区域/结构/通用控件复用），功能按钮按业务换、对接真实功能；通用控件的增删先申请并写理由。例：删搜索框须申请，换导航项不用。
- SHOULD：主操作唯一且最右；语义色配图标文字；Filter 草稿/应用分离；列宽本地持久；批量 Undo 优于强确认；
  空态分零数据/零匹配；窄屏切卡保操作可用；保存显式/即时按风险分文案。
- AVOID：整页定高锁死；推挤式展开；height:auto/left/top 动画；display:none 藏标签；100vw 通栏；
  overflow-x:hidden 掩盖溢出；卡套卡；多主按钮；纯 hover 入口；alert/confirm 原生框；成功无感。
  传统四缺陷反例对照（固定侧栏无抽屉/强制 min-width 页面横滚/placeholder 当标签+置灰提交/笼统错误不聚焦）见
  `references/anti-patterns.md`，评审先跑那张表。
- MUST：参考稿按标准模板复用设计与交互细节，功能按业务调整对接；禁模糊借鉴与跨稿拼凑，形态按挂载裁剪并声明的不算拼凑。例：表格列宽与 Undo 按 sonnet 做，排序不自拼他稿。
- MUST：设计与交互代码整块复用再改名适配，不逐行重写；功能接线按业务重写、对接真实功能。例：侧栏样式与状态机整块复用，只换令牌变量名；按钮行为按程序功能写。
- MUST：动工前先定参考来源并亲手点开产物验证，条件允许时渲染截图留证，落地按收敛口径，不直接复用产物数值。例：写“fable 悬停内容未移”而非“侧栏通过”。

## 输出结构（ALWAYS 用此模板）

```markdown
# [控制台/页面]方案
## 1 页型与 IA（四选一+导航分组+为什么不用其它）
## 2 外壳（Topbar/Sidebar 状态机与尺寸+令牌 diff）
## 3 表格/表单（骨架+校验/批量/脏保护关键片段）
## 4 响应式与无障碍（断点/容器查询+键盘/焦点/对比）
## 5 验证（390/768/1440+300 结果，主题与 reduced-motion）
## 6 已知问题
```

## 自检（出稿前逐项过）

- [ ] 页型四选一且写了不用其它页型的理由？
- [ ] 令牌先行，组件无裸色，深色是独立映射而非反转？
- [ ] 侧边栏槽视觉解耦，hover 不移内容，键盘/触屏有等价路径，suppressed 与持久化处理了？侧栏设计与交互对齐 fable，功能按钮按业务，通用控件差异有申请理由？
- [ ] 表格末列粘性+不透明+阴影，列宽有最小/键盘/持久，批量有 Undo/明示，窄屏切卡后操作可用，长列表分页+内滚不过屏？
- [ ] 表单两级校验+首焦+留输+可行动文案，草稿与脏保护闭环，危险区隔离？
- [ ] 页面无横滚，浮层夹取，触控 24/44，对比达标，reduced-motion 归零？
- [ ] 悬浮覆盖前后几何一致、内容未位移、点击落点正确，探针验过？
- [ ] 视觉矩阵（状态×视口×主题）逐图目检，已看/未覆盖显式记录？
- [ ] 定了参考来源并亲手点开产物验过关键状态（条件允许已截图），落地数值用收敛口径？
- [ ] 参考稿复用设计与交互后再调整功能对接，无模糊借鉴与跨稿拼凑？
- [ ] 表/表单以 fable DNS 页为默认整体模板，列宽/Undo 与导入短板按另两家与收敛口径补齐？
- [ ] 对位图标同图形复用，非对位未硬套（同语义 Lucide 且有声明），同栏图标互异，交互代码整块复用、功能接线按业务？
- [ ] 输出用了上面的六节模板？

## 验证协议

1. `SKILL.md` 头部 description 与仓库 `README.md` 检索表语义一致。
2. 新 skill 在 harness 可见/可加载。
3. 链接脚本全量 `-VerifyOnly` 通过；`git status` 无链接本体被暂存。

## 参考文件

- `references/shell-sidebar.md` — 外壳骨架与侧边栏状态机时序与像素规范。
- `references/tokens.md` — 设计令牌复制即用值与主题/动效/层级。
- `references/tables.md` — 数据表格骨架与列宽/排序/批量/粘性/卡片降级。
- `references/forms.md` — 表单/设置/向导结构与两级校验/草稿/脏保护/危险区。
- `references/responsive-a11y.md` — 断点/容器查询/防溢出/触控/语义与验收探针。
- `references/anti-patterns.md` — Legacy 传统反例四缺陷与传统 vs 改进对照，评审先跑此表。
- `references/builds-comparison.md` — 三构建产物特点与对比（fable 侧栏正本 / gpt 规范验收 / sonnet 列宽 Undo 反例），先看本页决定参考来源。
- `references/builds/` — 三工程构建产物快照（单文件 `index.html`，双击即开的成品预览，见其 README；无源码时也能看到成品形态）。
- `references/cf-intuition-map.md` — Cloudflare 用户直觉映射表（导航/表格/表单/反馈四心智逐项对齐 + 零偏差自测），还原 UI 前先按表亲手点产物。
- `references/cf-customization-guide.md` — 自定义边界（必复用 vs 可改清单 + 改前理由模板 + mock 换真实 API 接线指南），只改功能定义与接线，不动直觉层。
- `references/cf-design-analysis.md` — 三工程设计分析总表（定位/功能/侧边栏/表格/表单/顶栏/令牌/互补点，带可取之处批注），查"有什么、好在哪"看这篇。

