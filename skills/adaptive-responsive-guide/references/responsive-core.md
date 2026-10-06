# 响应式基础：视口、断点、单位

> 何时读：页面骨架、首屏、窄屏溢出、全屏高度不对时。原则：**内在布局优先，查询只做兜底；容器管组件，视口管页面**。
> 来源提炼：`自适应-响应式设计/demo-opus5.5max/responsive-css-guide.md` + 两份实验页（`demo-opus5.5max/index.html`、面板侧边栏集锦）。

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
- 为什么：`100vh` 按“地址栏收起后”的大视口计算，首屏底部会被挤出屏幕（macOS 悬浮滚动条下不易察觉）。
- 旧浏览器回退：先写 `100vh` 再写新单位。
- `svh/lvh/dvh` 默认不随软键盘变；要键盘感知用 `interactive-widget` 或 JS 写 `--vvh`。

## 安全区 env()（沉浸式全屏、固定底部操作栏必做）

```css
.action-bar { position: fixed; inset-inline: 0; bottom: 0;
  padding: 12px 16px;
  padding-bottom: max(12px, env(safe-area-inset-bottom)); } /* 保底 12px，有安全区自动加大 */
```

| 写法 | 含义 |
|---|---|
| `env(safe-area-inset-top)` | 刘海、状态栏 |
| `env(safe-area-inset-left/right)` | 横屏左右刘海/圆角 |
| `env(safe-area-inset-bottom)` | 底部 Home 指示条 |
| `env(name, fallback)` | 第二参是回退值，环境变量不存在时用 |

前提是 meta 加 `viewport-fit=cover`；否则 `env()` 恒为 0。

## 软键盘与底部操作栏（聊天/表单页，B+A 叠加高频）

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
```

| 取值 | 软键盘弹出时 | 对 `vh/dvh` | 适用 |
|---|---|---|---|
| `resizes-visual`（Chromium Android 默认） | 只缩视觉视口，键盘盖住页面底部 | 不变 | 普通内容页 |
| `resizes-content` | 布局视口一起缩、页面重排 | 随之变小 | 聊天输入栏、底部表单（要贴键盘） |
| `overlays-content` | 两视口都不变，键盘全遮 | 不变 | 配 VirtualKeyboard API 自行处理（仅 Chromium） |

```css
.chat { height: 100vh;                    /* 兜底 */
  height: var(--vvh, 100dvh);             /* JS 算的可见高，其次 dvh */
  display: grid; grid-template-rows: auto 1fr auto; }
.chat__messages { overflow-y: auto; overscroll-behavior: contain; } /* 列表滚到头不带整页橡皮筋 */
.chat__input { padding-bottom: max(.5rem, env(safe-area-inset-bottom)); }
```

- `interactive-widget` 仅 Chromium/Firefox(Android)，iOS Safari 不支持，必须 JS 兜底（见 `js-apis.md` `visualViewport`）。

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
