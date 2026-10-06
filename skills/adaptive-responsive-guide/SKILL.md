---
name: adaptive-responsive-guide
description: >
  Web前端自适应响应式适配指南：视口与断点、媒体查询与容器查询、clamp流体排版、
  Flex/Grid内在布局、响应式图片、深色与 reduced-motion、逻辑属性、国内vw适配、
  操作区按钮放不下、卡片/工具栏/表格操作列/弹窗底部窄屏拥挤、容器宽度变化、
  移动端适配、触控目标。
  凡是提到自适应、响应式、适配指南、媒体查询、容器查询、clamp、视口单位dvh/svh、
  按钮放不下、窄屏溢出/挤压、横向滚动、越界、overflow、触控目标、操作区收纳、
  主操作+更多菜单、选中浮层、溢出探针、极窄(≤320/200px侧栏/104px下限)、P0优先级、降级阶梯时使用本 skill，
  即使没点名自适应、只说手机上按钮挤/压扁/被裁/点不到/图片模糊/高度被遮、受窗口限制、极限窄、卡片在小窗里放不下也要加载。
  覆盖决策选型、响应式实现、交互状态与验收清单；生成与验收两种模式。
---

# 自适应布局设计与适配

独立通用 skill：输入是“会变化的空间 + 要保住的可用性”，输出是决策、代码与验收。
依据有五：① `自适应操作区按钮布局设计与适配/.../card-actions-design-guide.md`
泛化到工具栏、表格操作列、表单操作栏、弹窗底部、导航；
② `自适应-响应式设计/demo-opus5.5max`（`responsive-css-guide.md` 指南 + `index.html` 实验页）
提供通用响应式能力：视口、媒体/容器查询、流体、Grid/Flex、图片、偏好、国内适配；
③ `自适应-响应式设计/WebUI…面板侧边栏设计集锦-muse-spark1.3.html`（面板/侧栏三态、按钮梯子、验收读数案例）。
④ 本 skill 自带可运行对照 `references/demos/card-actions-responsive-demo.html`
（卡片操作区四方案合一：换行基线 / 主操作+更多 / 图标 / 横滑，Priority+ 动态折叠 + 探针滑条，见 `overflow-squeeze.md`）。
⑤ `自适应-响应式设计/极窄自适应/` 五项目（`responsive-card-layout-optimization-opus5.5max` 五级 em 阶梯/P0–P3/零 Observer 收纳/诊断探针为主，
`responsive-card-layout-optimization-qwen3.8-27b` cqi 流体/对照演示台为辅，其余三项目补失效分类与样本切换；收敛见 `references/extreme-narrow.md`）。

与其它 skill 分工，不重复：
`frontend-design` 管栅格、令牌、渐进披露、三断点交付；`frontend-ux-qa` 管存量缺陷编号深查与 CI 门禁；
`distinctive-design-director` 管视觉主张；`web-animation-guide` 管动效选型细节。
本 skill 只管“空间变化时布局怎么变、操作怎么收纳、如何证明可用”。

## 适用范围

双轨道，用哪个先路由（0），不要混着写：

- A 操作区收纳：任何可复用模块里的操作区放不下（例如卡片/列表项/工具栏/表格行操作/弹窗底部/表单提交栏之一），
动作超 3–4 个、窄侧栏/双列/弹窗里复用的同一组件、320–1440 验证。卡片只是示例之一，不是前提。
- B 通用响应式：视口高度被遮（100vh/100dvh）、软键盘盖住底部操作栏、断点怎么定、字号间距跳变、网格换行、
图片模糊/流量大/CLS 跳动、深色/reduced-motion、强制颜色、RTL/竖排、vw 无限放大、1px 细线、
侧栏/面板三态（展开↔图标轨↔抽屉）。
不用本 skill：纯视觉风格发散（转 `distinctive-design-director`）、存量页按编号根因深查（转 `frontend-ux-qa`）。

## 流程（生成模式按 0–5，验收模式只走 5）

### 0——先路由，再读对应的 reference

- A 操作区放不下 → 走 1–5，重点读 `patterns.md + container-queries.md + interaction.md`。出现横滚/越界/压扁时加读 `overflow-squeeze.md`。
- B 通用响应式 → 跳过 1–2，直接走 3 + 4 + 5。3 必读 `responsive-core.md + fluid-grid-media.md`；
按需加读：概念不清补 `concepts.md`，断点/打印补 `media-queries.md`，整页骨架/抽屉/表格补 `page-patterns.md`，
随断点改行为/监听尺寸补 `js-apis.md`，选型定基线/验收补 `compat-testing.md`。
- 两者叠加（如窄容器里操作区放不下）→ 都走：先 B 定骨架与流体，再 A 做收纳。
- 进 ≤320px 极窄（含 200px 侧栏、240–280 极限复用，直至约 104px 下限）→ 加读 `extreme-narrow.md`（P0–P3 矩阵、五级 em 阶梯、退让六序、零 Observer 与动态 Priority+ 二选一、挤压三探针）。

### 1——先认主次，不先画布局

用一句话写清：有哪些动作、哪个最高频、哪个推进主任务、判断依据是什么。
频率相近时不许硬点一个当主操作。写不清就先问用户或记下假设再往下走。
为什么：收纳的前提是主次，错了后面全错。

### 2——按决策树选策略

读 `references/patterns.md`。按序判断，不按“手机用图标、桌面用文字”刻板印象：

1. 有明显高频主操作 → 主操作常驻 + 其余进“更多”纵向菜单。
2. 多实例、动作低频、想降常驻干扰 → 点击/聚焦选中后显示浮层（hover 仅增强）。
3. 同一组件进宽窄不同容器（全宽/双列/侧栏/弹窗）→ 按容器宽度自适应（它可与 1/2 组合，不是第五种信息架构）。
4. 都不符合 → 完整文字自然换行当基线（纵向长一点，好过看不懂、点不到）。
5. 固定图标行只给熟悉、语义稳定、数量少、且每个都有准确可访问名的动作。
6. 一律不用滑动/横向拖动/长按来发现操作。

### 3——按容器宽度实现，不按设备名

读 `references/container-queries.md`（A，含样式/滚动查询与塌陷陷阱）
+ `references/responsive-core.md`（B 骨架）+ `references/fluid-grid-media.md`（B 流体/网格/图片）
+ 按需 `concepts.md / media-queries.md / page-patterns.md / js-apis.md / compat-testing.md`。
原则：**容器决定组件布局，视口只决定页级列数边距导航**。

- B 先定骨架：标准 viewport meta；移动优先、按内容定 2–4 个 rem 断点；内在布局优先
（RAM `auto-fit + minmax(min(100%,15rem),1fr)`、Flex wrap/sidebar/switcher、subgrid），查询只兜底。
- B 再定流体：容器 `width:min(100%-2rem,72rem)`；字号间距 `clamp()` 且含 rem 项、MAX≤2.5×MIN；
首屏 `100svh`、全屏壳 `100dvh`（先写 `vh` 回退）；通栏 `100%` 不用 `100vw`。
- B 再定媒体：`srcset+sizes`（w 配 sizes，x 给固定尺寸），美术指导用 `picture`，
`width/height` 或 `aspect-ratio` 防 CLS，LCP 图 `fetchpriority=high` 不懒加载。
- B 骨架细节：完整语法与打印见 `media-queries.md`；整页三栏/抽屉/表格见 `page-patterns.md`；
随断点改行为/监听尺寸见 `js-apis.md`；框架选型/基线/验收见 `compat-testing.md`。
- A 通用做法：可复用模块设命名容器 `container: xxx / inline-size`，`@container (min-width: 实测阈值)` 切宽窄两态；
阈值按真实字体/标签/边距实测，320/390/768/1440 只是验证点；文字约束顺序完整标签→整颗换行→图标+可访问名→次要进菜单；旧环境回退主操作+菜单或换行，动作不消失。

### 4——交互状态闭环

读 `references/interaction.md`。触发、浮层、菜单、弹窗、反馈一次做全：

- 语义按钮/链接承载，不用 `div onClick`；不嵌套交互控件。
- 选中可切换可收起；键盘 `Tab/Enter/Space` 全通，`Esc` 先关内层再清外层，关闭焦点回触发器。
- `hover` 用 `@media (any-hover: hover)` 包裹，`:focus-within` 与点击等价，触屏不依赖 hover/长按。
- 单选（当前操作上下文）与复选（批量任务）分离：后者给计数、继续、清空。
- 反馈用页面状态区或 `role=status/alert`，不用 `alert()`；表单错关联字段、聚焦首错、保留输入。

### 5——验证交付

读 `references/acceptance.md`。交付物固定四件：决策结论 + 关键代码 diff + 验证记录 + 已知问题。溢出/挤压回归按 `overflow-squeeze.md` 探针法（220–1440 逐 20px + 320/390/768/1440 + <320 极限）。

- 同一组件验 320/390/768/1440 + 窄侧栏复用态；页面级无非必要横向滚动。
- 宽窄两态动作顺序、名称、行为一致；按钮文字要么完整显示要么整体隐藏，不许挤压截断省略号。
- 触控基线 44×44（产品基线，非 WCAG AA 要求，AA 最低 24×24，见 acceptance 边界）。
- 深色/浅色/系统主题、减少动态偏好各验一次。

## MUST / SHOULD / AVOID（精简，详见 references）

- MUST：标准 viewport meta 且不禁缩放；标签完整或整体隐藏，禁挤压裁切省略号；所有动作键盘可达；图标必有准确可访问名；320 回流无页面级横滚；焦点可见，禁无替代 `outline:none`；字号不用纯 vw；图片有 `width/height` 或 `aspect-ratio`。
- SHOULD：多实例低频先试选中浮层，主次明确先试主操作+菜单；容器查询优先；内在布局（RAM/Flex wrap）优先于查询；动效 ≤320ms 只动 transform/opacity 跟随 reduced-motion；逻辑属性优先；国内 H5 限最大宽。
- AVOID：横向滚动/滑动露出/仅 hover 入口；小字号压窄按钮；只用颜色表选中；`title` 当唯一名称；禁用提交代校验；禁缩放禁粘贴；模块内再套内部滚动区；通栏 `100vw`；纯 vw 字号；窄屏 `display:none` 删内容（重排不删减，收纳只是移进菜单不消失）；`overflow-x: hidden` 掩盖溢出且让 sticky 失效（找根因，确需裁切用 `clip`）。

## 输出结构（ALWAYS 用此模板）

```markdown
# [场景]自适应方案
## 1 决策（A写主次+所选策略+为什么不用其它；B写布局目标+断点/流体选型+为什么不用其它）
## 2 布局（宽/窄两态说明+容器阈值与实测依据；B加断点与流体参数来源）
## 3 代码（容器查询+菜单/浮层关键片段，回退说明；B加视口/流体/网格/图片片段）
## 4 交互（触发/切换/关闭/焦点/反馈）
## 5 验证（320/390/768/1440+窄栏结果，主题与 reduced-motion）
## 6 已知问题
```

## 自检（出稿前逐项过）

- [ ] 0 已路由（A/B/叠加），读了对应的 reference？
- [ ] A 主次有依据，频率相近没硬点主操作？B 断点按内容、阈值实测，320 等只是验证点？
- [ ] 决策树走过且写了不用其它方案的理由？
- [ ] 标签无挤压截断省略号，假适配 CSS（标签上 ellipsis/shrink）清零？
- [ ] 字号含 rem 项、MAX≤2.5×MIN？图片有宽高/aspect-ratio？通栏没用 100vw？viewport 没禁缩放？
- [ ] hover 被 any-hover 包裹，键盘/触屏有等价路径？
- [ ] 单选批量状态分离，Esc 层级与焦点回归定义了？
- [ ] 44 基线表述没写成 WCAG AA 要求？
- [ ] 进 ≤320 极窄时读了 `extreme-narrow.md`（P0–P3 矩阵、阈值 ±1px、floor 下限、退让六序）？
- [ ] 输出用了上面的六节模板？

## 验证协议

1. `SKILL.md` 头部 description 与仓库 `README.md` 检索表语义一致。
2. 新 skill 在 harness 可见/可加载。
3. 链接脚本全量 `-VerifyOnly` 通过；`git status` 无链接本体被暂存。
