# 流体尺寸、内在布局、响应式媒体、国内移动适配

> 何时读：字号间距跳变、网格换行、图片 CLS/流量、vw 无限放大、1px 细线时。
> 提炼自 `自适应-响应式设计/`（opus 指南 + 两份实验页：教学手册与面板侧边栏集锦）；查询语法细节以 MDN/caniuse 为准。

## clamp / min / max

```css
.container { width: min(100% - 2rem, 72rem); margin-inline: auto; }
.title { font-size: clamp(1rem, 0.9rem + 0.5vw, 1.4rem); }
```

- `min()` 设上限，`max()` 设下限，`clamp(MIN,VAL,MAX)` 首选值夹中间；MIN>MAX 时 MIN 胜出。
- 组件级流体把 `vw` 换 `cqi`（跟容器不跟视口）。
- 出血文章网格：两侧 `minmax(var(--gap),1fr)` 吸剩余空间，正文列居中，头图 `.full-bleed` 跨全宽。

## 单位与内在尺寸速查（空间算错多半在这）

| 项 | 要点 |
|---|---|
| `%` padding/margin | **都相对包含块的宽度**，不是各自方向；高度百分比要求父有确定高 |
| `em` | 相对当前 `font-size`，多层嵌套会累乘；组件内间距用 `rem` |
| `ch` / `ic` | `ch` 对中文不准，中文行长用 `ic`（`max-inline-size: 40ic`） |
| `lh` / `rlh` | 相对行高，可按行数限高（`max-block-size: 5lh`，Baseline 2023） |
| `fr` | 只能用于 Grid 轨道 |
| `min-content` / `max-content` / `fit-content` | 能收缩到的最小宽（最长词/图）/ 不换行宽 / 介于二者且最多占满可用宽 |

- `min-content`/`fit-content` 是“空间不够时元素怎么缩”的底层答案：放不下优先换行或收纳，别靠 `overflow:hidden` 硬压。
- 图片裁切三件套：`aspect-ratio:16/9` + `object-fit:cover` + `object-position:top`（人像保上半身）。
- `flex` 三值：`flex:1`=`1 1 0%`（按份数分、不看内容）、`flex:none`=`0 0 auto`、`flex:auto`=`1 1 auto`（按内容定基准）；
  “常驻按钮只许增长不许被压”写 `flex:1 0 auto`（见 `js-apis.md` 五坑之 4）。

## 流体排版公式与硬规则

- 已知 minVw/minFont、maxVw/maxFont：`slope=(maxF-minF)/(maxV-minV)`，`VAL=截距rem + slope*100 vw`。
- 例 16px@360→20px@1280：`clamp(1rem, 0.9022rem + 0.4348vw, 1.25rem)`。
- 三条红线：① 首选值必须含 `rem` 项（禁纯 `vw` 字号，否则缩放不跟随，违 WCAG 1.4.4）；② MAX ≤ 2.5×MIN；③ 实测 200%/400% 缩放。
- 中文：行高 1.6–1.8，标题加 `text-wrap: balance`，行长用 `max-inline-size: 40ic`（中文）/`65ch`（西文）。
- 间距同样流体化：`--space-s/m/l` 三档 `clamp()`。

## 内在网格与 Flex（能不用查询就不用）

```css
.grid { display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); }
.features { display: flex; flex-wrap: wrap; gap: 1rem; }
.features > * { flex: 1 1 15rem; }
```

- RAM：`auto-fit` 空轨折叠拉伸（少量铺满），`auto-fill` 保留空轨（宽度统一）；`min(100%,15rem)` 防窄容器溢出。
- 选型判据：Flex 换行时**最后一行会被拉伸填满**——特性介绍很自然，商品网格会让末行卡片特别宽，此时改用 Grid RAM。
- 数量查询写法（`:nth-last-child(n + 5)` 起强制独占一行）在 Flex 上给 `flex-basis:100%`，在 Grid 上给 `grid-column:1 / -1`。
- 侧栏（无查询）：`.main{flex-basis:0;flex-grow:999;min-inline-size:60%}` 窄到 60% 自动堆叠。
- Switcher：`flex-basis:calc((30rem - 100%)*999)` 全有或全无切换，无尴尬中间态。
- subgrid：模块 `grid-row: span 3; grid-template-rows: subgrid` 跨项对齐标题/正文/操作（如价格/按钮）。
- 逻辑属性优先：`inline-size/block-size/margin-inline/padding-inline/inset-inline:0/text-align:start`，RTL 与竖排自动镜像。

## 响应式图片与 CLS

```html
<img src="news-960.jpg"
  srcset="news-480.jpg 480w, news-960.jpg 960w, news-1440.jpg 1440w"
  sizes="(width >= 64rem) 33vw, (width >= 40rem) 50vw, 100vw"
  width="1920" height="1080" alt="信息性描述" loading="lazy" decoding="async">
```

- `w`=固有宽（配 `sizes`），`x`=密度（固定尺寸头像用）；`sizes` 从左取首命中，末项默认。
- `sizes` 三条硬规则：**只能写长度不能写百分比**（`50%` 是图片模糊/超清的头号根因）；`x` 描述符不写 `sizes`；
  浏览器选图 = 槽位宽 × DPR，最终裁量权在浏览器，实测看 `currentSrc` 而非理论值。
- `sizes="auto, (width >= 64rem) 33vw, 100vw"`：懒加载图按实际显示宽选图，逗号后是给不支持者的回退（仅 Chromium 126+）。
- 美术指导（不同构图）用 `picture>source[media+type]`，具体条件写前面，`alt/width/height` 写 `img` 上。
- 首屏 LCP 图不懒加载，加 `fetchpriority="high"`；`width/height` 或 `aspect-ratio + object-fit:cover` 预留空间防 CLS。
- 背景图：`image-set(1x/2x)`；视频 iframe：`width:100%;height:auto;aspect-ratio:16/9`。
- 国内 OSS 免手切多套：阿里 `?x-oss-process=image/resize,w_800/format,webp`，腾讯 `?imageMogr2/thumbnail/800x/format/webp`，七牛 `?imageView2/2/w/800/format/webp`。

## 用户偏好与触控（必验）

```css
@media (hover:hover) and (pointer:fine){ .card:hover{ box-shadow:...; } }
@media (any-pointer:coarse){ .toolbar button{ min-block-size:44px; min-inline-size:44px; } }
@media (prefers-reduced-motion:no-preference){ html{ scroll-behavior:smooth; } }
```

- 深色：`:root{color-scheme:light dark; --bg:light-dark(#fff,#0b1020)}` + `<meta name="color-scheme" content="light dark">`（meta 在 CSS 前生效，减白屏闪）。
- `light-dark()` 兼容坑：**不支持的浏览器丢弃整条声明**（旧 WebView 整页错）→ 先写普通值再 `@supports` 包，或用“变量 + `[data-theme]`”传统方案。
- 三态主题（跟随系统/浅/深）首屏注入防 FOUC：渲染前内联脚本读 `localStorage` + `matchMedia('(prefers-color-scheme: dark)')`，
  写 `data-theme` 到 `<html>`，`localStorage` 一律 `try/catch`；`prefers-color-scheme` 留给 `light-dark()` 覆盖不到的场景（如切图片）。
- 强制颜色（Windows 对比度主题）：颜色会被系统覆盖，**选中态/进度/边框不能只靠背景色**，补
  `@media (forced-colors: active){ [aria-current=true], [aria-pressed=true]{outline:2px solid Highlight} .panel{border-color:CanvasText} }`；DevTools Rendering 可模拟。
- 触控与指针：判“能不能悬停”用 `any-hover`（触屏笔记本 `hover` 与 `pointer:fine` 可能同时命中），判“是否存在粗糙指针”用 `any-pointer:coarse`。
- 动效渐进增强；老项目兜底用 `reduce` 全局压制（动画→0.01ms）。
- 触控基线产品 44×44；WCAG 2.2 AA 最低 24×24（2.5.8）；图标扩大点击区用 `::after{inset:-10px}`。
- 操作禁只 hover 出现；触屏点按/聚焦必须有等价路径。

## 国内 H5 vw 适配与回退

| 方案 | 结论 |
|---|---|
| rem+lib-flexible | 已废弃，只维护旧项目 |
| vw+postcss-px-to-viewport | 主流，纯 CSS；分支用 `postcss-px-to-viewport-8-plugin`，Windows 路径用 `/node_modules[\\/]vant/` 正则；`viewportWidth` 可传函数按文件返回 375/750（Vant 按 375，自有页按设计稿） |
| vw+限宽 | 推荐：`postcss-mobile-forever`（`appSelector+maxDisplayWidth`，模式可选 vw/max-vw/rem/mq 四种）或手写 `min(4.2667vw,25.6px)` + `#app{max-width:600px}` |
| 字号 | 布局用 vw/百分比，字号用 rem+`clamp()`（跟随系统字号） |
| 1px 细线 | 伪元素 `scaleY(.5/.3333)` + `-webkit-min-device-pixel-ratio` 与 `min-resolution` 双写；`border-width:.5px` Android 取整慎用 |
| 小程序 | rpx=750 宽；Taro/uni-app 以 750 为基准自动转；旧 WebView 基线别拍脑袋，用埋点上报 `UA/viewport 宽` + 真机回归定 |

表格外两条：`<source media>` 与关键布局**写传统 `min-width`**（新范围语法在旧 WebView 直接不命中）；CSS 背景图多分辨率加 `-webkit-image-set()` 前缀。

## 前沿（渐进增强，非生产默认）

- 样式查询（`@container style(--variant:promo)`，Firefox 待补，Interop 2026）、滚动状态查询（仅 Chromium 133+，兜底 IntersectionObserver）、`if()`（仅 Chromium 137+）、锚点定位（Baseline 2026）、`grid-lanes` 瀑布流（实验）、`sizes=auto`（仅 Chromium 126+）。
