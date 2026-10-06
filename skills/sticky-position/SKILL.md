---
name: sticky-position
description: >
  CSS position: sticky 粘性定位的实现规范、场景写法与失效排查。凡是要做吸顶/吸底导航、
  冻结表头与首列、分组标题逐段顶走、侧边目录跟随、章节内浮动操作条，或反馈 sticky 不生效、
  不粘、粘不住、被顶走时机不对、被遮挡/被盖住时，一律加载本 skill。即使用户只说"吸顶"、
  "置顶"、"吸附"、"表头固定"、"滚动到某个位置停住"、"像钉在那里一样"，没有点名 sticky
  也应使用。也用于评审他人 sticky 代码、排查"我明明写了 position: sticky 却没反应"。
---

# position: sticky 实现规范

## 为什么值得按规范写

sticky 用一行声明替代"JS 监听滚动 + 切 fixed + 手动补占位"的整套逻辑，且保留文档流空间、
切换瞬间不抖动。但它的失效**不会抛任何错误**——元素只是像从未声明过一样滚走了。所以本规范
的价值在于两件事：写的时候一次写对（附强制项），坏的时候按固定顺序排查（附排查表）。

## 一、心智模型（三句话，解释一切怪异行为）

1. **滚动容器决定粘在哪里**：最近的可滚动祖先（`overflow` 计算值非 `visible`；若无则为视口）。
2. **包含块决定粘多久**：通常是直接父元素。sticky 被约束在包含块内，父元素滚出视野即解除粘住，
   永不越出其边界。
3. **inset 阈值决定何时粘**：目标轴上至少一个 inset 非 `auto`，元素距滚动容器边缘不足该距离时粘住。

三态生命周期：**流动态**（如 relative）→ **粘住态**（吸附在阈值线）→ **推离态**（包含块底边追上，
被一起带走）。反向滚动时状态逆向恢复。推离态是 sticky 区别于 fixed 的灵魂特性。

更精确的术语是**粘性约束矩形**：包含块矩形与"流盒按 inset 偏移后的矩形"的交集，
sticky 永远只能待在这个黄色区域里。定量公式：**可粘行程 ≈ 包含块高度 − 元素高度**——
行程 ≤ 0 时看起来就是"完全不粘"（排查第 3 条）。

三点易错的语义：

- sticky **并未**真的切换成 fixed：计算样式里 `position` 始终是 `sticky`，始终保留布局空间，
  "先像 relative 后像 fixed"只是便于理解的类比。
- 包含块是"直接父元素"（常见块布局中），**不是**"任何带 position 的祖先"——那是 absolute 的规则。
- 同为 `top: 50px`：relative 是"立刻从原位下移 50px"；sticky 是"平时待在原位，距容器顶部不足
  50px 时才粘住"。某轴两个 inset 都为 `auto` 时，该轴 sticky 行为与 relative 相同。
  另注意：增大 `top` 只改变吸附位置的上方留白，**不会**撑高父容器。
- sticky **自建层叠上下文**（MDN，极老桌面浏览器除外）。后果有三：子元素的 `z-index` 被锁在
  内部盖不住外部；同层 sticky 按 DOM 顺序层叠、后来者居上（这正是"共享父元素时后来者只覆盖
  不顶走"的底层原因）；后续内容里若有定位元素（如带 `relative` 的卡片角标），无 `z-index`
  的导航会被它们盖住——这就是强制项要求 `z-index` 的由来。

## 二、最小可用写法

```css
.sticky-element {
  position: sticky;
  top: 0;              /* 粘性阈值：目标轴至少一个，缺失则永不生效 */
  z-index: 10;         /* 粘住后会压在内容之上 */
  background: #fff;    /* 必须不透明，否则下方文字透出 */
}
```

字段速查：

| 字段 | 含义 | 典型用途 |
|---|---|---|
| `top` | 元素上边缘与滚动容器上边缘的最小距离 | 吸顶导航、表头（最常用） |
| `bottom` | 元素下边缘与容器下边缘的最小距离 | 吸底操作条 |
| `left` / `right` | 水平轴同理 | 横向滚动、表格首列冻结 |
| `inset-block-start` | 逻辑属性版，随书写模式自动映射 | 竖排 / RTL / 国际化布局 |

竖排时 `inset-block-start: 0` 自动等价于 `right: 0`，横排等价于 `top: 0`——多语言布局优先用逻辑属性。

## 三、六种场景的标准写法

完整结构与成套 CSS 见 `references/patterns.md`，此处只给选型骨架：

| 场景 | 关键写法 | 最容易漏的一件事 |
|---|---|---|
| ① 吸顶导航 | `top: 0; z-index; background` | 三件套缺一不可（阈值/层级/不透明背景） |
| ② 分组索引（字母索引、章节标题） | 每组独立包含块，`top: 0` | 组必须各自包一层容器，否则后来者只"覆盖"不"顶走" |
| ③ 表格表头 + 首列冻结 | 写在 `th`/`td` 上，交叉格同时 `top`+`left` 且 z-index 最高 | 不要写在 `thead`/`tr`；表格容器 `border-collapse: separate` |
| ④ 侧边目录 TOC | `top: 80px; align-self: flex-start` | Flex/Grid 子项默认被拉伸，不加 `align-self` 就没空间可粘 |
| ⑤ 吸底操作条 | `bottom: 0`，放在所属内容末尾 | 不是写 `bottom` 就能任意吸底，仍受包含块约束 |
| ⑥ 层叠卡片 | 多个 sticky 共享同一包含块，`top` 依次递增 | 卡片要高于视口才有层叠观感；容器结束时一起被推走 |
| ⑦ 响应式断点切换 | 窄屏抽屉/底部栏 ↔ 宽屏 sticky 常驻，用媒体查询切换 `position` | 切换时 `top`/`bottom` 让位值也要跟着换（见 patterns.md） |

## 四、写代码时的强制项

这几条是评审时的硬性检查点，任何一条缺失都按缺陷处理：

1. **必有阈值**：目标轴至少一个非 `auto` 的 inset，并确认没被层叠中更低处的规则覆盖。
2. **必给不透明背景 + 合理 z-index**：粘住后会与后续内容重叠，透明背景会让文字叠成一团。
   允许的替代方案是半透明 + `backdrop-filter: blur()` 毛玻璃，但必须实测确认下方文字不可辨认。
3. **父容器必须留有余量**：包含块要高于 sticky 元素，否则没有可移动空间，看起来就像不粘。
   可粘行程 ≈ 包含块高度 − 元素高度，≤ 0 即失效。
4. **Flex/Grid 中补 `align-self: flex-start`（Grid 用 `start`）**：否则子项被 stretch 拉满等高，
   等价于第 3 条失效。
5. **表格写在 `th`/`td` 上**：`thead`/`tr` 上的 sticky 历史支持不一，单元格写法最稳；角单元格
   同时具备 `top` + `left` 并使用最高 z-index。
6. **配套锚点让位**：有吸顶栏就必须给滚动容器设 `scroll-padding-top`，或给目标设 `scroll-margin-top`，
   否则锚点跳转和 Tab 焦点会被吸顶区遮住。两者可叠加但别重复预留过大空白。
7. **优先纯 CSS**：不要用滚动监听模拟定位。确需感知"当前是否吸附"，用 Intersection Observer
   哨兵元素或 `@container scroll-state(stuck: top)`（见 `references/compat-a11y.md`）。

## 五、sticky 还是 fixed

| 维度 | `position: fixed` | `position: sticky` |
|---|---|---|
| 文档流 | 脱离，不占空间（需占位防抖） | **保留原空间**，无抖动 |
| 参照物 | 视口（祖先带 `transform` 时改为该祖先） | 最近的滚动容器 |
| 生效范围 | 永远固定 | **仅在包含块内**，滚过即释放 |
| 需要阈值 | 否 | 是（至少一个 inset） |
| 局部滚动区 | 不跟随局部容器（只认视口） | 天然支持容器内粘滞 |

判据一句话：**永远悬浮用 fixed**（全局悬浮按钮、回到顶部、客服入口）；**只在所属内容范围内停留
用 sticky**（分组标题、章节侧栏、表头）。口诀：陪一段路用 sticky，永远悬浮用 fixed。

## 六、失效排查（按此顺序，不要跳）

sticky 失效不报错，按固定顺序过一遍即可定位：

1. **阈值**：目标轴 inset 是否都是 `auto`？补 `top`/`bottom`/`left`/`right`。
2. **祖先 overflow**：某个祖先是否成了非预期的滚动容器？移除；只裁剪改 `overflow: clip`；
   确需滚动则给它明确高度。
3. **父级空间**：包含块是否与 sticky 一样高？增加内容/空间，必要时把 sticky 上移一层 DOM。
4. **拉伸**：Flex/Grid 子项是否被 stretch 拉满？设 `align-self: flex-start`。
5. **高度来源**：父级 `height: 100%` / `-webkit-fill-available` 是否无可靠参照？改 `min-height`
   或明确高度。
6. **样式覆盖**：DevTools Computed 里 `position`、`inset` 的最终值是什么？提高选择器特异性。

第 2 条最阴险：为某个需要横向滚动的兄弟元素给祖先加了 `overflow-x: hidden`，sticky 立刻失灵。
规范规定**一轴为 hidden/auto/scroll 时，另一轴的 `visible` 被计算为 `auto`**，所以 `overflow-x: hidden`
实际得到 `hidden auto`，是一个货真价实的滚动容器。纯裁剪需求改用 `overflow: clip`（不创建滚动容器）。
`contain: paint` / `contain: layout` 等容器性属性同样会劫持，排查时别漏掉。

控制台一次列出嫌疑祖先（`clip` 已排除）：

```js
const target = document.querySelector('.sticky');
if (!target) console.warn('No .sticky element found');
for (let p = target?.parentElement; p; p = p.parentElement) {
  const { overflowX, overflowY } = getComputedStyle(p);
  const risky = ['auto', 'scroll', 'hidden', 'overlay'];
  if ([overflowX, overflowY].some(v => risky.includes(v))) console.log({ overflowX, overflowY }, p);
}
```

详细的根因机理、故障复现基线与 John Kavanagh 五步检查法见 `references/troubleshooting.md`。

## 七、兼容性与渐进增强（要点）

- Chrome 56+ / Edge 16+ / Firefox 32+ / Safari 13+ / Opera 42+ 稳定支持，国内主流浏览器
  （Chromium/WebKit 内核）无问题。**IE 11 及更早不支持**，回退为 `static`——回正常流通常是可接受的降级。
- 需兼顾不支持的浏览器时，先写 `position: relative` 兜底保住内部 absolute 子元素的定位参照，
  再在 `@supports (position: sticky)` 中增强：
  `.panel { position: relative; }` + `@supports (position: sticky) { .panel { position: sticky; bottom: 20px; } }`
- 老 Safari 双写：先 `position: -webkit-sticky;` 再 `position: sticky;`。
- JS 侧可用 `CSS.supports('position', 'sticky')` 做特性检测。

数据与降级示例见 `references/compat-a11y.md`。

## 八、无障碍与体验

- **控制占屏高度**：小屏上吸顶元素持续吞掉可视区，降低高度，或用"下滑隐藏、上滑再现"
  （定位仍由 sticky 负责，只用少量 JS 切 `transform`）。
- **锚点与焦点让位**：`scroll-padding-top` / `scroll-margin-top` 统一治理锚点跳转与 Tab 焦点遮挡。
- **对比度与层级**：吸附后叠在内容之上，背景不透明、文本对比度达 WCAG AA，文字放大后仍可读。
- **窄屏与短视口**：实测真实触屏滚动，必要时窄屏取消侧栏吸附。
- **性能别想当然**：不用滚动监听 ≠ 自动 60 FPS，复杂绘制仍需实测；吸附状态联动优先
  Intersection Observer 或滚动驱动动画，并尊重 `prefers-reduced-motion`。

## 九、上线前自检

1. 目标轴上至少有一个非 `auto` 的 inset 阈值。
2. 已确认最近滚动容器，没有非预期的 overflow 祖先（也查了 `contain`）。
3. 包含块足够大，元素有移动空间，没有被 Flex / Grid 拉满。
4. 背景不透明、z-index 合理，表格交叉单元格层级最高。
5. 页内锚点、Tab 焦点、内容放大后都不会被吸顶区遮挡。
6. 窄屏、短视口与真实触屏滚动已检查。
7. 已验证目标浏览器，不支持 sticky 时能自然降级。
8. 定位用 CSS 完成，未引入高频重排与不必要的动效。

## 十、验证协议

交付前逐项跑一遍，全部通过才算完成：

1. **三态实滚**：在真实页面里滚动，依次观察流动态 → 粘住态 → 推离态，反向滚动应逆向恢复。
2. **DevTools Computed**：确认 `position` 计算值为 `sticky`、目标 inset 非 `auto`。
3. **嫌疑祖先脚本**：控制台跑第六节脚本，确认没有非预期滚动容器。
4. **遮挡检查**：点击页内锚点、Tab 遍历焦点，确认不被吸顶区遮住。
5. **窄屏检查**：移动视口与触屏滚动下，占屏高度与层级正常。
6. **降级检查**：在不支持 sticky 的环境（或 DevTools 关闭该特性）确认回退符合预期。

## 参考文件

- `references/patterns.md` — 七种场景的完整 HTML 结构与成套 CSS（可直接复制）。
- `references/troubleshooting.md` — 六类失效根因机理、控制台六步诊断脚本、故障基线复现、Kavanagh 五步检查法。
- `references/compat-a11y.md` — 浏览器支持数据、渐进增强模板、无障碍与性能、感知吸附状态的两种代码方案。

## 延伸阅读（素材来源）

- MDN：[CSS position](https://developer.mozilla.org/zh-CN/docs/Web/CSS/position)（规范术语与权威行为定义）
- W3C：[CSS Positioned Layout Module Level 3](https://www.w3.org/TR/css-position-3/)（sticky 规范出处）
- 张鑫旭：[杀了个回马枪，还是说说 position:sticky 吧](https://www.zhangxinxu.com/wordpress/2018/12/css-position-sticky/)（粘性约束矩形的中文深度解读）
- Elad Shechter：[CSS Position Sticky — How It Really Works!](https://elad.medium.com/css-position-sticky-how-it-really-works-54cd01dc2d46)（三态机制经典图解）
- caniuse：[CSS position: sticky](https://caniuse.com/css-sticky)（各移动浏览器最新支持情况）
