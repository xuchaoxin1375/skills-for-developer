# 页面级经典布局模式（别用操作区决策树套）

> 何时读：整页骨架（三栏/侧栏/抽屉/表格）怎么摆时。来源：opus 布局章 + `index.html:1744` 实验室。
> 与 `patterns.md` 分工：这里管页面，`patterns.md` 管模块内操作收纳。

## 五种多设备模式（Luke Wroblewski 2012）

| 模式 | 做法 |
|---|---|
| 主体流式 Mostly Fluid | 大屏居中限宽，小屏堆叠（`max-width`+一个断点） |
| 列下沉 Column Drop | 变窄时列逐个掉下去（Grid/Flex 换行+断点） |
| 布局变换 Layout Shifter | 断点下结构大变（`grid-template-areas` 重排） |
| 微调 Tiny Tweaks | 单栏只调字号间距（流体排版） |
| 画布外 Off Canvas | 导航藏屏外按需滑入（transform+抽屉，本页侧栏即示例） |

## 一行布局速查（web.dev Ten modern layouts）

- 超级居中：`display:grid; place-items:center`（弹窗/空状态）
- 解构煎饼：父 `flex-wrap:wrap` + 子 `flex:1 1 150px`
- 侧栏说：`grid-template-columns:minmax(150px,25%) 1fr`（无需查询）
- 煎饼堆叠：`grid-template-rows:auto 1fr auto`（页脚贴底，整页用 `min-height:100svh`）
- 圣杯：`grid-template:auto 1fr auto / auto 1fr auto`；RAM：`repeat(auto-fit,minmax(150px,1fr))`
- 夹住行长：`width:clamp(23ch,60%,46ch)`；保比例：`aspect-ratio:16/9`

## 可访问抽屉（窄屏滑入/大屏常驻）

```css
.drawer { position: fixed; inset-block: 0; inset-inline-start: 0; width: min(85vw, 20rem);
  transform: translateX(-100%); visibility: hidden; transition: transform .3s, visibility 0s .3s; }
.drawer[data-open="true"] { transform: none; visibility: visible; transition: transform .3s; }
@media (width >= 64rem) { .drawer { position: sticky; transform: none; visibility: visible; } }
@media (prefers-reduced-motion: reduce) { .drawer { transition: none; } }
```

触发按钮带 `aria-expanded/aria-controls`；打开给主内容加 `inert`；Esc/点遮罩关，焦点回触发器；锁滚动；可用原生 `dialog`/`popover` 代替自建。

## 响应式表格双策略

| 策略 | 做法 | 取舍 |
|---|---|---|
| 横向滚动 | 外层 `overflow-x:auto` + `tabindex=0 role=region aria-label` | 保留语义，需左右滑 |
| 卡片化堆叠 | 窄时行变卡片，`td::before{content:attr(data-label)}` 显示列名（用容器查询，窄栏也生效） | 小屏自然，改 display 后部分浏览器丢语义需补 ARIA |

```css
.table-wrap { container-type: inline-size; }
@container (width < 36rem) {
  .rtable thead { display: none; }
  .rtable tr { display: block; margin-block-end: .75rem; border: 1px solid #ddd; border-radius: 8px; }
  .rtable td { display: flex; justify-content: space-between; gap: 1rem; }
  .rtable td::before { content: attr(data-label); font-weight: 600; }
}
```
