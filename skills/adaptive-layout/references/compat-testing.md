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

工程链：Vite 7 默认 `baseline-widely-available`；`postcss-preset-env` 降级范围语法/嵌套；`browserslist` 统一定目标；ESLint CSS `use-baseline` 拦截不兼容特性。

## 调试测试

- DevTools 设备模式（`Ctrl+Shift+M`）、Rendering 面板模拟 `prefers-*/forced-colors/print`、容器查询徽章看命中规则；Safari 数据线调 iPhone，`chrome://inspect` 调 Android。
- 多视口：Responsively（开源）、Polypane（付费）；云真机：BrowserStack/LambdaTest；国内：微信开发者工具、vConsole/Eruda；审计：Lighthouse。
- 跨平台必查：Windows 占宽滚动条（`100vw` 只在此暴露）、125%/150% 显示缩放小数 DPR、 Win 雅黑 vs mac 苹方（禁固定高文本容器）。
- 验收宽度：320/375–430/768/1024/1280/1440/1920+；缩放 200%/400%（400%≈320宽，查双向滚动）；横屏 360 高；键盘弹起；深色/reduce/对比度主题；德语长词/RTL；弱网图片；触屏+鼠标。
- 性能：图片写宽高防 CLS；LCP 图 `fetchpriority=high` 不懒加载（可 `link preload imagesrcset`）；`media=print` 样式低优先级下载不阻塞；长页 `content-visibility:auto + contain-intrinsic-size`。

## 兼容核心（首个默认支持版本，上线前复核）

范围语法 104/63/16.4（2023）；容器尺寸 105/110/16.0（2023）；`clamp` 79/75/13.1；`svh/dvh` 108/101/15.4（2025-06 广泛）；`subgrid` 117/71/16.0；`:has` 105/121/15.4；`light-dark` 123/120/17.5（2024）；锚点定位 125/147/26（2026）。
样式查询（111/待定/18，Interop 2026）、滚动状态（仅 133+）、`if()`（仅 137+）、`grid-lanes`（实验）、`sizes=auto`（仅 126+）一律渐进增强。
