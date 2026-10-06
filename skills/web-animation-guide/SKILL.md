---
name: web-animation-guide
description: Web动画应用指导：选型、性能与无障碍落地。Whenever user mentions web动画、CSS Transition/Animation、WAAPI、requestAnimationFrame、FLIP、滚动驱动scroll-driven、View Transitions、SVG/Canvas动画、GSAP/Motion/Lottie、动效卡顿、prefers-reduced-motion、高度展开收起、steps逐格、弹簧spring、@property, even if they don't say skill, use this skill. Also for animation selection, jank debugging, reduced-motion compliance.
---

# Web Animation Guide

基于 `Web动画指南@合并版.md`（2026-10-04，四源合并） distilled。原则：能 CSS 不 JS，能原生不引库，能 transform 不布局，不支持仍可用。

## 工作流程

1. **三问先行**：什么触发（状态/时间/滚动）？什么定进度（时钟/scroll/view）？谁绘制（合成器/WAAPI/rAF/Canvas）？先说结论再给代码。
2. **查表选型**：见 `references/selection.md`。区分滚动**驱动**（跟进度，可反向）vs 滚动**触发**（越过播一次，用 IntersectionObserver）。
3. **性能线索非保证**：`transform/opacity` 通常只合成；颜色阴影描边可能重绘；`width/height/top` 可能重排。以 DevTools 实测为准。
4. **输出必须含**：选型理由一句话 + 最小可运行代码 + `@supports`/运行时回退 + `prefers-reduced-motion` 处理 + 清理（cancel/断观察器）。
5. **版本不拍板**：Firefox 滚动驱动、Safari/VT 版本号众说不一，一律写“以 MDN/caniuse 当日为准”，demo 走检测+静态回退。

## 速查表（ condensed ）

| 场景 | 首选 |
|---|---|
| 两状态插值 | `transition` 显式属性 + `:hover/:focus-visible`，禁 `all` |
| 循环/多阶段 | `@keyframes`；无限须可停；`timing` 作用于每段之间 |
| 沿曲线 | `offset-path` + `offset-distance`，`@supports` 回退直线 |
| 暂停/反向/变速/拖进度，少量 | WAAPI `element.animate()`，`updatePlaybackRate`，`finished.catch` |
| 物理/指针/逐帧 | rAF + 时间戳 `dt`，上限 0.04~0.05s，`hidden` 停 |
| 列表重排位移 | FLIP：记录→真改→反向→`animate`；或 VT 快照 |
| 进度条/随滚揭示，简单 | CSS `scroll()/view()` + `animation-range`，默认终态可见 |
| pin/scrub/叙事 | GSAP ScrollTrigger |
| 视图切换/形变 | `startViewTransition` / `@view-transition`，300~500ms，同页名唯一 |
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
- 高度 auto 展开：首选 `grid-template-rows: 0fr↔1fr`（子层 `overflow:hidden`），次选 scaleY（内容会变形）；禁逐帧动 `height`。雪碧图/打字机/翻牌用 `steps(n, jump-*)`，n=帧数；渐变/数值令牌要插值先 `@property` 注册类型化变量。
- 状态是真相、动画只是表达：业务提交（落库/切视图/发请求）不依赖 `transitionend`/`finished`，先提交语义状态再叠视觉。
- `fill:forwards` 长期占优先级，用完写终值+`cancel()` 或 `commitStyles()`；`Infinity` 调 `finish()` 抛错。
- `transitionend` 每属性一次；值未变不触发。
- `will-change` 临前加事后删；禁全局常驻、`translateZ(0)` 迷信、`setInterval 16ms`；读写交错=强制同步布局，先批量读再批量写（或 rAF 合批）。
- React：FLIP 测量用 `useLayoutEffect`（`useEffect` 会闪一帧瞬移）；VT 回调内 `flushSync` 提交；卸载 `cancel()`，StrictMode 双挂载要求初始化可重复；列表用稳定 `key`。
- 弹簧物理：`F = -k(x-target) - c·v`，`v += F*dt; x += v*dt`，dt 秒且钳 ≤0.032~0.05；过冲克制（按钮/危险操作无回弹）。
- 全局控制用 `document.getAnimations()` 批量 `pause()/updatePlaybackRate()`，做全站暂停与慢放，不必逐个持有引用。
- SVG 原点加 `transform-box:fill-box`；SMIL 暂停须 `pauseAnimations()`，CSS 停不住它。
- 减弱偏好至少 `.01ms` 一刀切（保事件），最好精细降级；WAAPI/SMIL/Canvas 全覆盖；站内开关可覆盖系统。
- 中文逐字用 chars 或 `Intl.Segmenter('zh')`；竖排注意轴对调；npm/CDN 走 npmmirror（用前验证）；微信/X5/iOS 实测。

## 输出模板

```markdown
**选型**：一句话为什么是它，不为什么不用XX
**代码**：最小可运行片段（显式属性/回退/减弱三件套）
**验证**：DevTools 看什么，低端机/120Hz/减弱模式怎么测
```

## References

- `references/selection.md`：完整技术边界 + 库体积对比 + 决策细节
- `references/snippets.md`：可粘贴代码（过渡/首值不补间/高度展开/steps/@property/全局暂停/读写分批/React 集成/弹簧/WAAPI/rAF/FLIP 与反补偿/代际守卫/滚动兜底/VT 进阶/SVG/Canvas/starting-style）
- `references/performance-a11y.md`：性能/无障碍/兼容/国内/中文清单
