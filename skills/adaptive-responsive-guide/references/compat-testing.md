# 框架、调试、兼容与前沿（落地清单）

> 何时读：选型、定基线、验收、看新特性时。来源：opus 框架/测试/前沿/兼容四章 + `index.html:2339`。
> 结论一律以 MDN/caniuse/webstatus.dev 实时数据为准。

## 框架速查

| 工具 | 响应式能力 |
|---|---|
| Tailwind v4 | `sm–2xl` 断点（rem）、`max-md` 范围变体、内置容器查询（父 `@container` + 子 `@md:`）；`@theme{--breakpoint-3xl:120rem}` 自定义 |
| Bootstrap 5.3 | 12 列栅格 `.col-md-6`，后台速搭 |
| AntD/Element Plus | Row/Col 断点；AntD `Grid.useBreakpoint()` |
| Vant/NutUI/TDesign | 移动端库，Vant 按 375 设计 |
| Utopia / Every Layout | 流体字号间距计算器 / Stack/Sidebar/Switcher 无查询原语 |
| UnoCSS | 原子化，断点 `@media` 前缀与 `min-`/`max-` 变体，需自己定 `preflights` 与主题断点 |

Tailwind 区间显示：只在某段宽度露出用 `hidden md:max-lg:block`（窄屏与更宽屏都隐藏），常用于“过渡态才出现”的操作。

工程链：Vite 7 默认 `baseline-widely-available`；`postcss-preset-env` 降级范围语法/嵌套；`browserslist` 统一定目标；ESLint CSS `use-baseline` 拦截不兼容特性。

## 调试测试

- DevTools 设备模式（`Ctrl+Shift+M`）、Rendering 面板模拟 `prefers-*/forced-colors/print`、容器查询徽章看命中规则；Safari 数据线调 iPhone，`chrome://inspect` 调 Android。
- 断点/单位**实测装置**（验收演示可直接抄）：
  - `vh/svh/lvh/dvh` 并排探针：`position:fixed; left:-9999px; visibility:hidden` 里放四个 `height:100vh/svh/lvh/dvh` 的 1px 子块，读 `getBoundingClientRect().height`
    （外移+隐藏，不产生滚动与 CLS），一眼看出地址栏伸缩差与键盘差异。
  - 真视口 iframe：`<iframe srcdoc>` 有**自己的视口**，桌面页内即可演示 360px 下的 `@media`/`vw`/`matchMedia`（DevTools 模拟在部分场景不触发 `matchMedia`）。
  - `auto-fill`/`auto-fit` 空轨：DevTools Grid 叠加层看轨道，或 `getComputedStyle(el).gridTemplateColumns` 出现 `0px` 即为折叠。
  - 特性是否被识别：`matchMedia(q).media === 'not all'` → 浏览器不认这条查询（详见 `js-apis.md`）。
- 国内 WebView 基线别拍脑袋：埋点上报 UA + 视口宽分布，配真机回归定（工具见 vConsole/Eruda）。
- 多视口：Responsively（开源）、Polypane（付费）；云真机：BrowserStack/LambdaTest；国内：微信开发者工具、vConsole/Eruda；审计：Lighthouse。
- 浏览器自动化优先 playwright（E2E/截图/断言），先 evaluate 探真实 DOM 再断言；CDP（远程调试端口+截图）为回退；手拼无头浏览器截图命令不用。
- 跨平台必查：Windows 占宽滚动条（`100vw` 只在此暴露）、125%/150% 显示缩放小数 DPR、 Win 雅黑 vs mac 苹方（禁固定高文本容器）。
- 验收宽度：320/375–430/768/1024/1280/1440/1920+；缩放 200%/400%（400%≈320宽，查双向滚动）；横屏 360 高；键盘弹起；深色/reduce/对比度主题；德语长词/RTL；弱网图片；触屏+鼠标。
- 性能：图片写宽高防 CLS；LCP 图 `fetchpriority=high` 不懒加载（可 `link preload imagesrcset`）；`media=print` 样式低优先级下载不阻塞；长页 `content-visibility:auto + contain-intrinsic-size`。

## 兼容核心（首个默认支持版本，上线前复核）

先认清标签：**Baseline（web.dev/WebDX）**，`Newly available` = 四引擎桌面+移动最新版都支持；`Widely available` = 之后再过 30 个月才叫“广泛可用”。
引用本文件的“Baseline 20XX”指前者——新近可用 ≠ 可放心上线，关键布局仍要回退。

范围语法 104/63/16.4（2023）；容器尺寸 105/110/16.0（2023）；`clamp` 79/75/13.1；`svh/dvh` 108/101/15.4（2025-06 广泛）；`subgrid` 117/71/16.0；`:has` 105/121/15.4；`light-dark` 123/120/17.5（2024）；锚点定位 125/147/26（2026）。
常被漏的回退项：`inert` 102/112/15.5（抽屉遮挡主内容靠它）；`fetchpriority` 102/132/17.2（LCP 图）；`text-wrap:balance` 114/121/17.5；
`overflow:clip` 90/81/16（`overflow-x` 裁切保 sticky）；逻辑属性 87/66/14.1；`aspect-ratio` 88/89/15；Flex `gap` 84/63/14.1；
**`interactive-widget` 108/132/Firefox132/Safari 否**（iOS 无键盘感知，必须 `visualViewport` 兜底）。
样式查询（111/待定/18，Interop 2026）、滚动状态（仅 133+）、`if()`（仅 137+）、`grid-lanes`（实验）、`sizes=auto`（仅 126+）一律渐进增强。
