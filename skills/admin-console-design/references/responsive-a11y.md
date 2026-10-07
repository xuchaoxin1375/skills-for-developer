# 响应式与无障碍（控制台验收版）

通用收纳决策走 `adaptive-responsive-guide`，本页只给定案参数与验收探针。

## 断点（外壳媒体查询 + 内容容器查询）

- 外壳：`<640 drawer+单列+表切卡+按钮堆+Dialog底抽 / 640-767 抽屉+表横滚+6栅 / 768-1023 Rail+peek+统计2列 / 1024-1279 固定+12栅+大纲 / ≥1280 统计4列 / ≥1536 max1440居中`。
- 内容：DNS 表 ≥700 表 / <700 卡；表单 ≥1040 助栏；设置 ≥720 分栏。视口只定页级列数边距导航，组件布局看容器。
- 基线 390/768/1440 逐页 + 320 回流 + 300 不溢；禁 100vw（用 100%），禁固定 px 列，禁 `overflow-x:hidden` 伪造适配（确需裁切 用 clip，hidden 会劫持 sticky）。

## 防溢出三件套

`min-w-0/minmax(0,1fr)` 遍布 + 长值 `ellipsis/anywhere`（技术值 break-all+mono）+ 浮层 `min(期望,100vw-16)`。
`*box-sizing`，`html scroll-padding-top 88px`，媒体 `max-width:100%`，根 `overflow-x:clip`（不破 sticky）。
按钮 `flex-wrap`，窄屏文字 `sr-only` 留图标保名；触屏全控件 44px（含 checkbox-hit44），桌面 24/36，图标 32/36 间距 4。

## 语义与键盘

- 全 Tab 达 + Enter/Space 激 + 顺序一致；浮层进焦关还焦；模态陷阱 Esc；列表 ↑↓HomeEnd；Rail 聚焦 peek；Skip link 首位。
- 焦点 `:focus-visible 2px 主色 + 2px offset`，禁无替代 outline:none；输入主色边+30% 环。
- ARIA：nav/switch/checkbox/table/field/tooltip/popover/dialog/toast/combobox/步骤 ol/分段 radiogroup；图标按钮 aria-label，装饰 aria-hidden，禁 div onClick，禁仅 hover 行操作常显；状态非色（图标文+aria-sort）。
- 文本行高 1.6，禁压缩，允许折行，禁 user-scalable=no，数字 tabular-nums。

## 验收探针（复制即跑）

```js
// 1. 页面级横溢（三宽+300极端，期望全 pass）
for (const w of [1440,768,390,320,300]) { /* 置宽后断言 */ console.assert(document.documentElement.scrollWidth <= window.innerWidth, 'overflow at '+w); }
// 2. 窄屏主操作可达（300px 下 Add/Edit/Save 仍可见可点）
// 3. 侧栏 peek 不移内容：hover 前后 .workspace-main left 不变（Rail 64/56）
// 4. reduced-motion：transition≈0
```

- 发布门槛 P0 阻断：存/删/浮层/键盘/窄主操作任一失败即阻断。
- 诚实声明：构建成功≠视觉/无障碍/交互验收；无浏览器能力不许声称验收；截图必须人眼确认。
- 性能：搜索 `useDeferredValue` + 防抖，列拖只写 DOM，滚动 dataset+RO+rAF，动画仅 width/opacity/transform/grid-rows，监听按需绑卸。
