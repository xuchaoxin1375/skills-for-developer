## 页面级经典布局模式（别用操作区决策树套）

> 何时读：整页骨架（三栏/侧栏/抽屉/表格）怎么摆时。来源：opus 布局章 + `index.html:1744` 实验室 + 面板侧边栏集锦（三态 rail）。
> 与 `patterns.md` 分工：这里管页面，`patterns.md` 管模块内操作收纳。

### 滚动归属与浮层形态

先按任务和可见空间选择形态，再确定内容与操作区的滚动归属；不能将设备名称直接映射成强制全屏或统一内部滚动。

| 场景 | 默认选择 | 验收边界 |
| --- | --- | --- |
| 页面列表、文章与一般长内容 | 页面纵向滚动；需要时分页或虚拟化 | 增长不能导致横向溢出，不为每个模块增加独立滚动条 |
| 受限弹窗、固定工作面板、日志区 | 限高内容区滚动，标题/必要操作可保留在外 | 高度受可见视口约束，子项可收缩；缩放或键盘弹起后内容与操作仍可达，避免多重嵌套滚动 |
| 短确认、少量详情 | 能容纳时保留普通弹窗 | 关闭入口、正文和操作完整，不能为“手机端”强行拉满 |
| 短操作列表、上下文选择 | 空间合适时可用底部面板 | 给安全区留空间，长菜单限高可滚；不将示例 90vh 或行高当统一令牌 |
| 长表单、复杂编辑、空间不足的详情 | 可转全屏弹窗或独立页面 | 提供明确返回/关闭，保留输入与上下文；按 `responsive-core.md` 处理可见高度与软键盘 |
| 表格、代码或确需二维阅读的内容 | 可使用可发现、可聚焦的局部横向滚动 | 不将操作入口藏在滑动后面，不使页面产生非必要横向滚动 |

`overscroll-behavior` 可隔离受限面板的滚动；固定高度是工作区策略，不适用于所有文本。异步槽位防跳动与内容可达性同时验，不用死高度裁切放大后的正文。切换浮层形态或滚动容器时，保留业务状态并将焦点移到有效位置。

固定页眉与次级栏的优先级来自页面任务；总高度预算写入项目令牌并按横屏、缩放和软键盘验证，遮挡时收纳或解除次级固定区域。多层 sticky 的偏移按实际高度共享；实现与失效诊断按需查 `sticky-position`，不在这里维护第二套定位代码。

### 五种多设备模式（Luke Wroblewski 2012）

| 模式 | 做法 |
|---|---|
| 主体流式 Mostly Fluid | 大屏居中限宽，小屏堆叠（`max-width`+一个断点） |
| 列下沉 Column Drop | 变窄时列逐个掉下去（Grid/Flex 换行+断点） |
| 布局变换 Layout Shifter | 断点下结构大变（`grid-template-areas` 重排） |
| 微调 Tiny Tweaks | 单栏只调字号间距（流体排版） |
| 画布外 Off Canvas | 导航藏屏外按需滑入（transform+抽屉，本页侧栏即示例） |

### 一行布局速查（web.dev Ten modern layouts）

- 超级居中：`display:grid; place-items:center`（弹窗/空状态）
- 解构煎饼：父 `flex-wrap:wrap` + 子 `flex:1 1 150px`
- 侧栏说：`grid-template-columns:minmax(150px,25%) 1fr`（无需查询）
- 煎饼堆叠：`grid-template-rows:auto 1fr auto`（页脚贴底，整页用 `min-height:100svh`）
- 圣杯：`grid-template:auto 1fr auto / auto 1fr auto`；RAM：`repeat(auto-fit,minmax(150px,1fr))`
- 夹住行长：`width:clamp(23ch,60%,46ch)`；保比例：`aspect-ratio:16/9`
- 12 列栅格：`grid-template-columns:repeat(12,1fr)`；排队 Line Up：`flex-direction:column; justify-content:space-between`
  （等高卡片**底部按钮对齐**，卡片操作区高度不齐时首选）

### 后台骨架三档（底部标签栏 → 左导航 → 加右面板）

```css
.app { display: grid; min-height: 100svh;
  grid-template: "header" auto "main" 1fr "nav" auto / 1fr; } /* 区域串 + 行高 / 斜杠后列宽 */
.app > nav { grid-area: nav; position: sticky; bottom: 0; }   /* 手机：底部标签栏 */

@media (width >= 48rem) {
  .app { grid-template: "header header" auto "nav main" 1fr "nav aside" auto / 14rem 1fr; }
  .app > nav { position: static; }                            /* 平板：左侧竖导航 */
}
@media (width >= 80rem) {
  .app { grid-template: "header header header" auto "nav main aside" 1fr / 16rem 1fr 20rem; }
}
```

一串区域名换一套即换骨架，只改 `grid-template` 一处；`grid-template` 是 rows/columns/areas 的简写。
阈值按内容实测，`48/80rem` 只是示例。

### 侧栏/面板三态（展开 ↔ 图标轨 ↔ 抽屉，案例 muse-spark / opus 实测）

- 状态全部挂在 `body`（或 `<html>`）一个类上，视觉差异用 `:is() + :not()` 声明式表达，避免每态各写一堆规则：

```css
body { padding-left: var(--rail-cw); }                       /* 默认 68px 图标轨 */
@media (min-width: 1280px) {
  body:not(.rail-collapsed):not(.rail-auto) { padding-left: var(--rail-w); }   /* 展开 280px */
}
@media (min-width: 768px) {
  /* 收起/自动态：仅 ≥768px 走图标轨，手机一律走抽屉，不经过这里 */
  body:is(.rail-collapsed, .rail-auto):not(.rail-pin):not(.rail-peek) { padding-left: var(--rail-cw); }
  body:is(.rail-collapsed, .rail-auto):not(.rail-pin):not(.rail-peek) .rail__label { display: none; } /* 标签整颗隐藏，不挤成竖排 */
}
@media (max-width: 767px) { body { padding-left: 0; } }      /* 手机抽屉（配合上面的 off-canvas） */
```

- 五种互斥态：展开 / 收起 / 自动 / 钉住（`rail-pin`，点按=常驻）/ peek（悬停临时展开，**不写回记忆状态**）。
- 折叠不靠 `transform` 时可用**变量列宽**：`grid-template-columns: var(--col-sidebar, var(--sidebar-w)) minmax(0,1fr)`，
  折叠时 `--col-sidebar: 0px` 并 `visibility:hidden`，相邻列平滑接管，主区不位移（适合“侧栏折叠但内容不动”）。
- 手机抽屉与图标轨共用同一套展开键：图标轨里**展开键必须常驻**（触屏/键盘无悬停，它是唯一入口），
  标签文字整颗 `display:none` 而不是挤成竖排。

### 可访问抽屉（窄屏滑入/大屏常驻）

```css
.drawer { position: fixed; inset-block: 0; inset-inline-start: 0; width: min(85vw, 20rem);
  transform: translateX(-100%); visibility: hidden; transition: transform .3s, visibility 0s .3s; }
.drawer[data-open="true"] { transform: none; visibility: visible; transition: transform .3s; }
@media (width >= 64rem) { .drawer { position: sticky; transform: none; visibility: visible; } }
@media (prefers-reduced-motion: reduce) { .drawer { transition: none; } }
```

触发按钮带 `aria-expanded/aria-controls`；打开给主内容加 `inert`；Esc/点遮罩关，焦点回触发器；锁滚动；可用原生 `dialog`/`popover` 代替自建。

### 响应式表格双策略

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
