---
name: web-animation-guide
description: Web 动画的技术选型、实现与排障：CSS Transition/Animation、WAAPI、requestAnimationFrame、FLIP、scroll-driven、View Transitions、SVG/Canvas、GSAP/Motion/Lottie；含打断与清理、性能与卡顿、prefers-reduced-motion 合规。当用户要做动效、排查动画卡顿或减弱动效，或评审动画代码时使用；反馈目的与设计预算走 frontend-design，响应式布局走 adaptive-responsive-guide。
---

# Web Animation Guide

基于 `Web动画指南@合并版.md`（2026-10-04，四源合并） distilled。原则：能 CSS 不 JS，能原生不引库，能 transform 不布局，不支持仍可用。

## 职责边界

本 skill 集中维护动效技术选型、示例、打断与清理、兼容、性能和减弱处理。与 `frontend-design` 同用时，反馈目的和工具界面预算读取其 `references/motion.md`；实际时长/缓动读取项目令牌。本 skill 示例值只用于演示，不覆盖项目设计预算；单独使用时根据场景定令牌，不要求加载整个前端设计流程。

## 工作流程

1. **三问先行**：什么触发（状态/时间/滚动）？什么定进度（时钟/scroll/view）？谁绘制（合成器/WAAPI/rAF/Canvas）？先给选型结论。
2. **查表选型**：见 `references/selection.md`。区分滚动**驱动**（跟进度，可反向）vs 滚动**触发**（越过播一次，用 IntersectionObserver）。
3. **性能线索非保证**：`transform/opacity` 通常只合成；颜色阴影描边可能重绘；`width/height/top` 可能重排。以 DevTools 实测为准。
4. **实现交付**：说明选型与令牌来源，给适用的回退、减弱处理和资源清理；用户要示例时给最小可运行代码。评审/咨询只输出相关结论与验证，不强行附代码。
5. **版本不拍板**：Firefox 滚动驱动、Safari/VT 版本号众说不一，一律写“以 MDN/caniuse 当日为准”，demo 走检测+静态回退。

## 速查表（ condensed ）

| 场景 | 首选 |
|---|---|
| 两状态插值 | `transition` 显式属性 + `:hover/:focus-visible`，禁 `all` |
| 弹窗开/关 | 原生 dialog + 支持时启用 `@starting-style`/`allow-discrete`；退出配置与所需布局常驻，语义关闭不等动画；见 `references/interactions.md` |
| 耗时按钮忙态 | 同步忙态与防重入，延迟等待指示，成功/失败恢复；减弱下保留静态文字 |
| 下拉/菜单 | 简单进出场用透明度/微位移；需打断控制时用 WAAPI；普通 disclosure 不伪装 ARIA menu |
| 循环/多阶段 | `@keyframes`；无限须可停；`timing` 作用于每段之间 |
| 沿曲线 | `offset-path` + `offset-distance`，`@supports` 回退直线 |
| 暂停/反向/变速/拖进度，少量 | WAAPI `element.animate()`，`updatePlaybackRate`，`finished.catch` |
| 物理/指针/逐帧 | rAF + 时间戳 `dt`，上限 0.04~0.05s，`hidden` 停 |
| 列表重排位移 | FLIP：记录→真改→反向→`animate`；或 VT 快照 |
| 进度条/随滚揭示，简单 | CSS `scroll()/view()` + `animation-range`，默认终态可见 |
| pin/scrub/叙事 | GSAP ScrollTrigger |
| 视图切换/形变 | `startViewTransition` / `@view-transition`，时长读项目令牌，同页名唯一 |
| 粒子/图表/游戏 | Canvas + DPR上限2 + 可见性停帧；超大/3D 另议 |
| 设计资产 | Lottie/PAG（中文转曲）/Rive（许可核实）；不为按钮引引擎 |

## 决策树

```
两状态？→ transition（含 starting-style 处理 display:none）
绑滚动？→ 简单用 CSS scroll-driven+回退 / 复杂用 GSAP
视图切换？→ View Transitions
要运行时控制？→ 少量 WAAPI / 多元素 GSAP/Motion
布局位移？→ FLIP / layout / VT
大量自绘？→ Canvas/WebGL
设计资产？→ Lottie/PAG/Rive
否则 → keyframes
```

## 必查坑（详情见 references）

- `animation-timeline` 写在 `animation` 简写**之后**；滚动时长 `1ms` 只是兼容写法；简写两时间值第一是时长第二是延迟，写反不报错只慢半拍。
- transition 只在**值变化**时启动：首屏/同帧写入起终点不播（首值不补间）→ 入场用 keyframes、`@starting-style`、或挂载后双 `requestAnimationFrame` 再加类；`display:none` 需 `transition-behavior: allow-discrete`；拖拽/初始化复位时临时 `transition: none` 防“自动飞过去”。
- 高度 auto 展开：小区域可用 `grid-template-rows: 0fr↔1fr`，它仍会布局；大范围联动按实测选 FLIP 或瞬时重排。选型与回退见 `references/selection.md`，不把 scaleY 当通用高度替代。雪碧图等用 `steps()`；数值令牌插值用 `@property`。
- 关闭语义立即生效、焦点及时移出，但退出可见期间必须保留内容与布局，结束后再清理视觉层；取消/零时长也能收尾。例：dialog 移除 `[open]` 后，纵向排列和内边距仍保留，不挤成横排。
- `fill:forwards` 长期占优先级，用完写终值+`cancel()` 或 `commitStyles()`；`Infinity` 调 `finish()` 抛错。
- `transitionend` 每属性一次；值未变、零时长或取消时可能不触发。退出清理覆盖完成、取消、无动画与卸载，不用 `.01ms` 保事件。
- `will-change` 临前加事后删；禁全局常驻、`translateZ(0)` 迷信、`setInterval 16ms`；读写交错=强制同步布局，先批量读再批量写（或 rAF 合批）。
- React：FLIP 测量用 `useLayoutEffect`（`useEffect` 会闪一帧瞬移）；VT 回调内 `flushSync` 提交；卸载 `cancel()`，StrictMode 双挂载要求初始化可重复；列表用稳定 `key`。
- 弹簧物理：`F = -k(x-target) - c·v`，`v += F*dt; x += v*dt`，dt 秒且钳 ≤0.032~0.05；过冲克制（按钮/危险操作无回弹）。
- 全局控制用 `document.getAnimations()` 批量 `pause()/updatePlaybackRate()`，做全站暂停与慢放，不必逐个持有引用。
- SVG 原点加 `transform-box:fill-box`；SMIL 暂停须 `pauseAnimations()`，CSS 停不住它。
- SVG 同一元素不同时承载 `transform` 属性与 CSS `transform` 动画：运行中的动画替换该元素自身的属性位移（静态祖先的位移保留），部件会被画到未位移处或屏外。外层 `g` 用属性定位置，内层 `g` 跑 `@keyframes`；`transform-box` 只定动画原点，不恢复被替换的位移。写法见 `references/snippets.md`“SVG 定位与动画分层”。
- 减弱策略统一见 `references/performance-a11y.md`；关闭非必要位移/循环，保留静态信息，JS 动画也处理偏好变化。例：保存中的 spinner 停转，文字仍说明正在保存。
- 中文逐字用 chars 或 `Intl.Segmenter('zh')`；竖排注意轴对调；npm/CDN 走 npmmirror（用前验证）；微信/X5/iOS 实测。

## 实现示例输出模板

```markdown
**选型**：一句话为什么是它，不为什么不用XX
**代码**：最小可运行片段（显式属性/回退/减弱三件套）
**验证**：DevTools 看什么，低端机/120Hz/减弱模式怎么测
```

## References

- `references/selection.md`：完整技术边界 + 库体积对比 + 决策细节
- `references/snippets.md`：局部技术片段（过渡/首值不补间/高度展开/steps/@property/全局暂停/读写分批/React/弹簧/WAAPI/rAF/FLIP/滚动/VT/SVG/Canvas）；集成时按对应技术补齐回退、减弱与清理
- `references/interactions.md`：可独立运行的弹窗、按钮忙态与下拉示例；实现用户交互时读，含关闭、焦点、防重入、取消和无动画路径
- `references/performance-a11y.md`：性能/无障碍/兼容/国内/中文清单

## 自检与示例回归

- 关闭/取消/零时长是否仍落正确终态，隐藏区域是否不可聚焦，旧动画是否不能覆盖最后命令？
- 退出可见期间是否保留内容与布局，移除开合标记是否不会改变排列、尺寸或裁切？
- 是否按 `references/performance-a11y.md` 检查中间帧与正常速度连续性，而非只验首尾和帧率？
- 严格 SVG（多部件联动、接触或跟随约束）是否冻结典型相位、用包围盒换算回 SVG 坐标核对了关键锚点，而非只看全屏截图（被裁在屏外的缺件肉眼易漏）？
- 定向运动（行进/旋转/流动）是否过了一遍方向链：主体朝向→旋转件转向→传动与尾迹走向→背景退行及视差方向，有一处相反即返工？
- reduce 初始与运行中切换时是否保留静态信息，清理是否覆盖 JS 动画与监听？
- 时长是否读取项目令牌，示例默认值是否没有变成第二套设计预算？

改交互示例后，在仓库根目录用已有 Python Playwright 与 Chromium 运行 `python skills/web-animation-guide/tests/test_interactions.py --artifacts .workspaces/motion-check`。测试直接提取 Markdown 代码，覆盖退出中间帧布局、正常/reduce、取消/零时长/缺 API、焦点、防重入与错误恢复；结果与截图是本地评估产物，不放入 skill。通过范围以实际浏览器为准，其他技术片段按需另验。
