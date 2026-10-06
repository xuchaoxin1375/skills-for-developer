# 响应式基础：视口、断点、单位

> 何时读：页面骨架、首屏、窄屏溢出、全屏高度不对时。原则：**内在布局优先，查询只做兜底；容器管组件，视口管页面**。
> 来源提炼：`自适应-响应式设计/demo-*/responsive-*.md` + 两份 `index.html` 实验。

## viewport meta（每页必写）

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
```

- 禁 `user-scalable=no` / `maximum-scale=1`（无障碍红线，Lighthouse 报错）。
- 沉浸式全屏才加 `viewport-fit=cover`，配合 `env(safe-area-inset-*)`。
- 聊天/表单页按需加 `interactive-widget=resizes-content`；iOS 不支持，用 `visualViewport` 兜底。

## 像素与视口心智

- CSS 像素才是布局单位；DPR 决定位图要几倍宽（DPR=3 的 390CSS 宽约需 1170 物理像素）。
- 桌面缩放会改 CSS 视口宽，媒体查询会切换；WCAG 400% 缩放约等于 320CSS 宽。
- 无 meta 时移动布局视口约 980px，会被整体缩小。

## 高度单位选型

```css
.hero { min-height: 100vh; min-height: 100svh; }
.chat { height: 100vh; height: 100dvh; }
```

- 首屏 Hero：`100svh`（最小可见，保证完整可见不跳）。
- 全屏壳/弹窗/聊天：`100dvh`（实时跟随，但地址栏伸缩会重排）。
- 旧浏览器回退：先写 `100vh` 再写新单位。
- `svh/lvh/dvh` 默认不随软键盘变；要键盘感知用 `interactive-widget` 或 JS 写 `--vvh`。

## 宽度坑

- 通栏用 `width: 100%`，不用 `100vw`（Windows 经典滚动条占宽，会横向溢出）。
- `scrollbar-gutter: stable` 防滚动条出现时左右跳。
- 异形屏：`padding-bottom: max(12px, env(safe-area-inset-bottom))`。

## 断点策略（移动优先）

```css
.list { display: grid; gap: 1rem; }
@media (width >= 40rem) { .list { grid-template-columns: repeat(2, 1fr); } }
@media (width >= 64rem) { .list { grid-template-columns: repeat(3, 1fr); } }
```

- 基础样式面向窄屏，`min-width` 向上增强。
- **按内容定断点**：拉宽窗口，撑不住/太空旷处就是断点；不按机型（375/414）硬编码。
- 断点用 `rem/em`（跟随用户默认字号），2–4 个即可；组件内部变化交给容器查询 + 内在布局。
- 骨架重排推荐 `grid-template-areas` 字符画，只改一处。
- Grid 视觉重排不改 DOM/Tab 顺序，DOM 保持逻辑阅读顺序。
