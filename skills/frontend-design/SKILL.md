---
name: Frontend Design
description: Web/桌面小工具界面设计：布局栅格、渐进式披露、响应式、克制动效、可用性铁律。凡是新建/改版/美化网页、组件、表单、仪表盘、落地页，或提到界面丑、布局乱、适配手机、加载动画时使用，覆盖生成与交付验收两种模式；存量页面缺陷深查与CI门禁转frontend-ux-qa。
---

# 前端界面设计

两种模式：**生成**（按步骤1–6）与**交付验收**（只走验收清单）。标准依据：`prompts/前端设计合并版.md`。分工：存量页面缺陷深查（按编号根因/复现/验收）与CI门禁转 `frontend-ux-qa`，本 skill 不重复其编号体系。

## 步骤1——任务与渐进披露

用一句话说清：用户是谁、主要任务是什么、下一步操作是什么。信息不明时记下假设，绝不用装饰掩盖需求缺失。然后读 `references/progressive-disclosure.md`：首屏只做一件事、主操作不超过3个；表单超过7项必须分组或分步；危险操作远离首屏并二次确认；空状态只给一件事加一个主按钮。

## 步骤2——先画线框，再写样式

读 `references/layout.md`。四种布局模式四选一（仪表盘 / 表单单列480–640 / 列表+详情 / 设置页），不许自创第五种。间距组件内只用 `4、8、12、16、24、32、48`，`64`只允许页面级大间距。先出线框（每块区域写清是什么+多宽+装什么）并经确认，再写一句CSS。底线读 `references/a11y.md`（WCAG 2.2 AA：全键盘可达、焦点可见且不被遮挡、目标≥24px/触屏≥44px、文字对比4.5:1/大文字与非文字3:1、320px回流、中文`lang`、行高≥1.6、CJK不用斜体与两端对齐）。

## 步骤3——视觉先写进令牌

读 `references/visual-tokens.md` 与 `references/tokens.md`。所有视觉决策先写进令牌（项目缺 `DESIGN.md` 时从 `assets/DESIGN.md` 复制）：三层令牌、组件只用语义层；字号档≤7档；圆角≤4档；阴影≤3级且带色相；只用一套图标库。`oklch()`可用但要给老WebView留sRGB回退；合规看WCAG对比率，APCA只作设计参考。

## 步骤4——交互、动效、文案

读 `references/interaction.md`、`references/motion.md`、`references/icons-motion.md`、`references/ux-copy-modals.md`。异步视图必须有加载/空/错/成功态且可恢复；刷新保留旧数据。反馈预算：≤100ms直接变；100–300ms用过渡掩盖；约300ms后才出局部加载；>2s长等待给阶段说明+已用计时+取消+缩小范围出口。常规过渡≤320ms（`120/200/320`），缓动 `cubic-bezier(0.2,0,0,1)`；只动`transform/opacity`；跟随`prefers-reduced-motion`。按钮文案=动词+对象+后果。一次只开一个弹窗；破坏性确认写清对象名。

## 步骤5——响应式与状态

读 `references/responsive.md`。用 `scripts/screenshot.mjs` 看390/768/1440三宽；表格要有降级（横滑冻结首列/卡片列表/列显隐）；触控目标达标；页面级不许横向滚动。表单：可见标签、正确`type/inputmode/autocomplete`、失焦+提交两级校验、内联可修复错误（`aria-describedby`）、首错聚焦、保留已填数据、允许粘贴。

## 步骤6——审查与交付

先跑 `scripts/scan.py` 扫低级违例，再按 `assets/design-review-checklist.md` 与 `references/checklist.md` 逐项打勾，顺序：任务→恢复→键盘窄屏→视觉→装饰。需按编号深查缺陷根因/复现/验收时，转 `frontend-ux-qa` 的 catalog（`L/C/S/V/A/F/N/I/D/P/G/H`）。结论分三级：阻断（MUST/NEVER违反）/建议（SHOULD）/细节，每条注明文件与规则。交付物：线框、令牌差异、三断点截图、清单打勾、已知问题。假按钮、虚假进度、键盘陷阱、对比度失败一律不许放行。

## NEVER（两种模式通用）

无替代的`outline:none`、`div onClick`按钮、仅hover功能、`window.alert`、禁用提交代替校验、禁粘贴/禁缩放、纯装饰渐变/满屏毛玻璃/标题emoji/卡片套卡片、任何欺骗模式。详见 `references/anti-patterns.md`；需按编号深查时转 `frontend-ux-qa`。
