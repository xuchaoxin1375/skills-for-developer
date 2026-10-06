# 溢出 × 挤压联调（极窄容器诊治）

> 何时读：出现页面级横滚、按钮越过卡片边框、`受窗口限制`下仍溢出、或修溢出时把字压扁/目标小于基线时。A/B 轨道都可能进这里：它是“空间不够”的失败态，不是新轨道。
> 来源：`web-design-best-practices-guide-fable5.1high`（案例复盘 01 + 指南 02 + 探针 `useOverflowProbe`）、`web-design-best-practices-guide-glm5.3flash`（OverflowLab 10 缺陷 + `labSource.ts` broken/fixed）、`web-design-best-practices-guide-grok4.6xhigh`（7 显式策略 + `min-width:auto` 陷阱）。

## 不等式（定位起点）

`min-content > 可用宽` 即溢出。`min-content` = 不可断行盒之和 + gap + padding（含图标+汉字+内边距的按钮组、长 URL/hash、无空格标识符、固定宽图/表/pre）。

- 挤压（squeeze）= 允许收缩但压坏可用性：字号缩小、`ellipsis` 吃关键信息、`flex-shrink:1` 压标签、触控目标 `<44`（触屏）/`<24`（指针）。
-  overflow（溢出）= 禁止收缩但无收窄策略：`flex nowrap` + `white-space:nowrap` + `flex-shrink:0`，容器一小于总宽即越界（`412px` 容器 vs `~420px` 按钮行是标准案例）。
-  二者联调：同一约束只能选**显式收窄策略**，不许在二者之间左右横跳，更不许用 `overflow:hidden` 把溢出变裁切（内容不可达，`sticky` 失效）。

## 五选一（显式策略，默认 `visible` 不算策略）

| 策略 | 做法 | 适用 |
|---|---|---|
| 整颗换行 | `flex-wrap:wrap`，按钮 `nowrap + shrink:0`，不足整颗下行；极窄可 `flex:1 1 100%` 单列 | 基线，动作 ≤2 或低风险页 |
| 进“更多” | Priority+ 按 `W >= sum(B_i)+(N-1)*G` 算 `k`，其余进菜单 | 默认推荐，主次明确时 |
| 整颗图标化 | `44px` 图标 + 准确 `aria-label`，宽时容器查询恢复文字 | 语义稳定、用户已学习时 |
| 仅文本截断 | 只给非关键文本 `ellipsis + title/展开/复制`，金额/标识/状态禁截 | 未知长文本 |
| 局部滚动 | 外层 `overflow-x:auto + tabindex=0 role=region aria-label` + 渐隐/箭头提示，自身 `max-width:100%` | 表/码/宽图/芯片条，须可发现 |

## 成因速查（先对号，再改码）

| # | 成因 | 识别 | 对策 |
|---|---|---|---|
| 1 | 长串无断点 | 删字就不溢 | `overflow-wrap:anywhere; min-width:0` |
| 2 | flex 子 `min-width:auto` | `truncate` 不生效、兄弟被挤出 | 子项 `min-width:0`；Grid 用 `minmax(0,1fr)` |
| 3 | 固定宽 | 容器一小即溢 | `width:100%; max-width:<n>px` |
| 4 | `100vw`/content-box+padding | 右侧恒差 15–28px | `100%`；`box-sizing:border-box` |
| 5 | 表/pre/宽图无包裹 | 320 下撑破 | 外层 `overflow-x:auto`，内 `min-width:max-content` |
| 6 | 负 margin/绝对定位/装饰 | 溢出量恒定 | 装饰 `right:0` 约束；容器 `overflow:clip` 只兜底 |
| 7 | `columns:2`/固定列网格 | 窄下列宽过小 | `repeat(auto-fit,minmax(min(100%,15rem),1fr))` |
| 8 | 缩放/大字号 | 只在 125–200% 出现 | `rem` + 弹性布局，不写 px 死高 |

## 探针（debug 专用，上线关）

```js
// 最外层越界元素才标红；overflow:auto/scroll 内可达内容不算失败；hidden/clip 切掉的标黄（裁切≠修复）
const cr = root.getBoundingClientRect();
for (const el of root.querySelectorAll('*')) {
  const r = el.getBoundingClientRect();
  const over = Math.max(0, r.right - cr.right, cr.left - r.left);
  if (over > 0.5) mark(el, over);
}
// 页面级：document.documentElement.scrollWidth <= clientWidth + 1
// 组件级：可见按钮恒满足 scrollWidth - clientWidth <= 1（横滑条内滚动除外）
```

- 采样：`220–1440px` 逐 `20px` 扫 + `320/390/768/1440` 点检 + `<320` 极限（`231px` 受限态）；滑块直接改容器宽，`1:1` 渲染，不缩放压字号。
- 极窄加采样（见 `extreme-narrow.md`）：下限 104/105/120、阈值 ±1px 双侧、典型窄 160/240/280/320；挤压三探针（最小宽/文本列 3.5 字宽/胶囊 1.7 行高）+ 子元素最右边缘算法；极值样本（56 字符无空格/CJK/德语/伪本地化/emoji/超大数字）。
- 读数用内容盒宽（`clientWidth - padding - 滚动条差`），与 `@container` 判据一致。
- 可运行对照：`demos/card-actions-responsive-demo.html`（单文件，Priority+ 动态折叠 + 四态预览 + 宽度滑条 300–800，
  复现 412 溢出带修复与 236→15 变更收敛；直接浏览器打开拖滑条即验）。

## 协调纪律

- 按钮标签：完整显示或整颗隐藏/进菜单，禁 `shrink/ellipsis/减字号`；`--tap` 触屏 `44`、指针 `24` 不动，间距 `≥8`。
- 容器查容器：卡片内部用 `@container`，视口只管列数边距导航；`1440` 窗口里的 `320` 卡片仍按卡片收缩。
- `overflow-x:clip` 只做页面级防护网；`hidden` 掩盖一律判失败（焦点环/菜单/阴影被裁）。
- 装饰溢出（阴影/焦点环/徽章跨界 `≤8px`）允许，前提是不改 `scrollWidth`、可点穿。
