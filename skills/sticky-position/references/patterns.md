# 七种场景的完整写法

每节给出结构要点 + 可直接复制的 CSS。所有示例都满足 SKILL.md 第四节的强制项
（阈值、不透明背景、z-index、包含块余量、锚点让位）。

嵌套滚动容器建议加 `overscroll-behavior: contain`，防止滚到头时带动外层页面一起滚
（链式滚动会干扰粘滞观感与调试判断）。

## ① 吸顶导航：横幅走，导航留

**结构要点**：导航与足够长的正文共用同一个包含块——不能被一个仅与导航等高的父级包住，
否则没有可粘的行程。横幅在导航之上，随页面正常滚走。

```css
.site-nav {
  position: sticky;
  top: 0;              /* 生效前提 */
  z-index: 10;         /* 盖住后续内容 */
  background: #fff;    /* 防止透出 */
}
```

```html
<div class="page">          <!-- 包含块：包住横幅 + 导航 + 长正文 -->
  <header class="banner">…</header>
  <nav class="site-nav">…</nav>
  <main>…长正文…</main>
</div>
```

配套：`html { scroll-padding-top: calc(var(--nav-h) + 8px); }` 让锚点跳转不被导航遮挡。

为什么 `z-index` 不能省：后续内容里常有定位元素（如为角标而设 `relative` 的文章卡片），
定位元素默认盖在无 `z-index` 的 sticky 之上——关掉 `z-index`，导航会被滚上来的卡片盖住。
毛玻璃替代：`background: rgb(255 255 255 / .85); backdrop-filter: saturate(1.6) blur(12px);`
可替代纯不透明背景，但必须实测确认下方文字不可辨认。

## ② 分组索引：新标题把旧标题顶走

**结构要点**：**每组独立包含块**是"推挤"观感的来源。若多个同级标题都直接挂在同一个长 `dl` 下，
它们的包含块相同，粘在同一位置时后来者只会**覆盖**前者，而不是把它顶走；用分组容器包住
"标题 + 该组内容"，上一组的包含块在组尾结束，下一组滚上来时自然把前一个推走。

```css
.contact-group dt {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #e4efde;
}
```

```html
<div class="contact-group">     <!-- 独立包含块 -->
  <dt>A</dt> …该组联系人…
</div>
<div class="contact-group">
  <dt>B</dt> …该组联系人…
</div>
```

## ③ 表格冻结：表头 + 首列 + 交叉格

**结构要点**：sticky 写在 `th`/`td` 上（而非 `thead`/`tr`），这是兼容性最稳的写法。
交叉单元格同时具备 `top` 和 `left`，并使用最高层级。表格用 `border-collapse: separate`
（合并边框会让 sticky 表头的边框表现异常）。

```css
.table-scroll { height: 288px; overflow: auto; }   /* 自己的滚动口 */
table { border-collapse: separate; border-spacing: 0; }

thead th {
  position: sticky;
  top: 0;
  z-index: 3;
  background: #e6efe2;
}
tbody th {                      /* 首列 */
  position: sticky;
  left: 0;
  z-index: 2;
  background: #f0f5eb;
}
thead th:first-child {          /* 交叉格：两轴都粘 + 最高层级 */
  left: 0;
  z-index: 4;
  background: #d6e5ce;
}
```

注：现代浏览器也可能支持 `thead`/`tr` 上的 sticky，此处采用单元格写法是为减少历史兼容问题，
不是说其他写法永远无效。但**表格 + sticky 务必逐浏览器实测**：曾有案例（父级 `overflow: auto`
后首列能固定、首行却不粘），边框与背景在不同内核下表现不一。

层级必须拉开梯度——**首列 1 ＜ 表头 2 ＜ 交叉格 3**（上面的 2/1/3 只是示例值，守住相对顺序即可）。
原因：同层级时 DOM 靠后的 `tbody` 单元格会在纵向滚动时盖住角单元格，关掉角单元格的高层级、
横向滚动即可复现。

边框写法：`border-collapse: collapse` 时边框属于表格而不属于单元格，不会跟着 sticky 单元格走；
改用 `separate + border-spacing: 0`，把边框画在单元格上，边框才会随冻结格一起移动。

## ④ 侧边目录 TOC：只陪伴所属文章

**结构要点**：Flex/Grid 里子项默认被 stretch 拉到与正文等高，没有剩余行程可粘，
`align-self: flex-start` 几乎必写。已有吸顶导航时 `top` 要给它让位。目录自身过长可设
`max-height` + `overflow-y: auto`——**它自己的 overflow 不会把"自己"变成其粘滞参照祖先**
（参照永远是再往外找的滚动容器）。

```css
.layout { display: flex; gap: 24px; }
.toc {
  position: sticky;
  top: 80px;                                  /* 导航高 64px + 间距 16px：top = 吸顶物高度 + 间距 */
  align-self: flex-start;                     /* 关键一行 */
  max-height: calc(100vh - 96px);
  max-height: calc(100dvh - 96px);            /* 移动端用 dvh：100vh 会把网址栏后的区域也算进去 */
  overflow-y: auto;
}
```

`top` 让位公式：**top = 上方吸顶物高度 + 间距**（如 40px 导航 + 12px 间距 = `top: 52px`；
关掉让位、`top: 0` 时目录会钻到吸顶导航下面）。同理，锚点目标用
`scroll-margin-top: 导航高 + 8px`。旧浏览器不认识 `dvh` 会整条忽略，
所以 `vh` 版写在前、`dvh` 版写在后做渐进增强。

文章末尾（TOC 的包含块结束）时目录随之离开，不会脱离所属文章继续跟随。

目录高亮（scrollspy）配套：用 Intersection Observer 观察各节，`rootMargin: "-30% 0px -60% 0px"`
让"进入视口中部偏上"的节成为当前高亮。定位仍由 sticky 负责，IO 只做高亮、不参与定位。

## ⑤ 吸底操作条：`bottom` 约束另一条边

**结构要点**：放在所属内容的**末尾**。内容不足一屏时待在原位；内容长时先粘在滚动口底部，
滚到自然位置后回归文档流。不是写 `bottom` 就能让任意元素吸底——正常流位置、父级边界、
可移动空间三条约束同样成立，后续章节不属于它的包含块。

```css
.action-bar {
  position: sticky;
  bottom: 0;
  z-index: 2;
  background: #e9f0e4;
  box-shadow: 0 -2px 8px rgb(0 0 0 / .08);   /* 顶部阴影：与正文分隔，否则像连成一片 */
}
```

移动端安全区：全面屏手机的底部 Home 指示条会压住操作条。页面先允许铺满
（`viewport-fit=cover`），再用环境变量让位：

```css
.action-bar {
  padding-bottom: max(12px, env(safe-area-inset-bottom));
}
```

软键盘说明：`svh`/`lvh`/`dvh` 默认都不随软键盘变化。如需"键盘弹出时输入栏贴住键盘"
（如聊天页），给 viewport 加 `interactive-widget=resizes-content` 让布局视口一起缩小；
iOS Safari 不支持该字段，用 `visualViewport.height` 写入 `--vvh` 兜底，
容器高度写 `height: var(--vvh, 100dvh)`（`100vh` 兜底写最前）。

## ⑥ 层叠卡片：top 递增，同容器一起被推走

**结构要点**：多张卡片共享**同一个包含块**，`top` 依次递增（如 0 / 26px / 52px）。
向下滚动时后一张盖住前一张，形成层叠观感；容器结束时全部一起被推走。
每张卡片要高于视口一部分，否则叠不出层次。

```css
.stack > .card { position: sticky; background: #fff; }
.stack > .card:nth-child(1) { top: 0; z-index: 1; }
.stack > .card:nth-child(2) { top: 26px; z-index: 2; }
.stack > .card:nth-child(3) { top: 52px; z-index: 3; }
```

`z-index` 递增不是可选：同层 sticky 按 DOM 顺序层叠，后来者本就居上，
显式层级让意图稳定、不依赖默认层叠。

## ⑦ 响应式断点切换：窄屏抽屉 ↔ 宽屏 sticky 常驻

同一元素在不同断点下换定位方式，是响应式 + sticky 最常见的结合：

```css
/* 窄屏：抽屉，滑入滑出 */
.drawer {
  position: fixed;
  inset-block: 0;
  inset-inline-start: 0;
  width: min(85vw, 20rem);
  transform: translateX(-100%);
  visibility: hidden;
  transition: transform .3s, visibility 0s .3s;
}
.drawer[data-open="true"] { transform: none; visibility: visible; transition: transform .3s; }

/* 宽屏：常驻侧栏 */
@media (width >= 64rem) {
  .drawer { position: sticky; top: var(--header-h); transform: none; visibility: visible; }
}
@media (prefers-reduced-motion: reduce) { .drawer { transition: none; } }
```

抽屉的无障碍配套（定位切换时同样要切）：触发按钮带 `aria-expanded` + `aria-controls`；
打开时背后主内容加 `inert` 锁焦点；支持 Esc 与遮罩关闭，关闭后焦点回到触发按钮；
也可用原生 `dialog` / `popover` 代替手写。

镜像场景——手机底部标签栏，大屏变回普通侧栏：

```css
.app > nav { position: sticky; bottom: 0; }   /* 手机：底部标签栏 */
@media (width >= 48rem) {
  .app > nav { position: static; }            /* 平板+：左侧导航，不再粘 */
}
```

注意：断点切换 `position` 时，`top`/`bottom` 让位值也要跟着换
（如窄屏无顶导用 `top: 12px`，宽屏有顶导改 `top: 80px`），否则切断点后出现遮挡或空隙。

## 通用补充

- **横向冻结 / 竖排**：多语言或竖排场景优先 `inset-block-start` 等逻辑属性，
  竖排时自动映射为 `right: 0`。
- **下滑隐藏、上滑再现**：定位仍交给 sticky，只用少量 JS（被动监听 + 方向阈值）切换
  `transform`，避免用 JS 参与定位本身。顶部 60px 内保持可见，避免一进页面就没导航：

```css
.site-nav { position: sticky; top: 0; transition: transform .25s; }
.site-nav.is-hidden { transform: translateY(-100%); }
```

```js
let lastY = 0;
scroller.addEventListener('scroll', (e) => {
  const y = e.currentTarget.scrollTop;
  const dy = y - lastY;
  if (Math.abs(dy) < 4) return;            // 方向阈值：小抖动忽略
  nav.classList.toggle('is-hidden', dy > 0 && y > 60);
  lastY = y;
}, { passive: true });
```
