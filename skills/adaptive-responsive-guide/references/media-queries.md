# 媒体查询完整语法（页面级主力）

> 何时读：要写断点、打印样式、PWA/无JS降级时。来源：opus 媒体查询章 + `index.html:968` 实验场。
> 原则：媒体查询管页面骨架，不管组件内部是文字还是菜单（那是容器查询的事）。

## 形式

```css
@media [not|only] <media-type> [and <media-condition>] { /* 规则 */ }
@media <media-condition> { /* 规则 */ }
```

| 项 | 含义 |
|---|---|
| `not` | 对整条取反（`@media not print`） |
| `only` | 历史遗留，现代可省略 |
| `<media-type>` | `all`（默认）、`screen`、`print`；其余已废弃 |
| `<media-condition>` | 媒体特性组合，可用 `and/or/not`（`or` 为 Level 4 新增） |
| 逗号 `,` | 查询列表，任一命中即生效 |

出现位置不只 `@media`：`link[media]`、`source[media]`、`@import`、JS `matchMedia()`。

## 范围语法（推荐，但关键布局留传统回退）

| 传统 | 范围 | 含义 |
|---|---|---|
| `(min-width: 768px)` | `(width >= 768px)` | 含边界 |
| `(max-width: 767.98px)` | `(width < 768px)` | `<` 不含边界，天然避开 768px 重叠 |
| `(min-width:400px) and (max-width:700px)` | `(400px <= width <= 700px)` | 区间 |

- 老代码 `767.98px` 是为避开 `min/max` 都含边界的重叠；范围语法无此问题。
- 兼容 Baseline 2023（Chrome 104/Firefox 63/Safari 16.4）；国内旧 WebView 用 `postcss-preset-env` 降级或关键布局直接写传统。

## 常用特性速查

视口：`width/height`（断点）、`aspect-ratio`、`orientation`；显示：`resolution(2dppx)`、`color-gamut(p3)`、`dynamic-range`；交互：`hover/any-hover`、`pointer/any-pointer`；偏好：`prefers-color-scheme/reduced-motion/contrast`、`forced-colors`；环境：`display-mode(standalone)`、`scripting(none)`。
已废弃：`device-width/device-height/device-aspect-ratio`（测整屏非视口）。

## 移动优先 + 打印

```css
.list { display: grid; gap: 1rem; }
@media (width >= 40rem) { .list { grid-template-columns: repeat(2, 1fr); } }
@media print {
  .page-nav, .page-aside, .ad-slot { display: none; }
  a[href^="http"]::after { content: " (" attr(href) ")"; }
}
```

断点用 `rem/em`（以浏览器初始字号为基准，跟随用户字号设置），2–4 个；Grid 重排不改 DOM/Tab 顺序。
