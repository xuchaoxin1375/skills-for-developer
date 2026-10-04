# 选型细节

## 技术边界

| 技术 | 典型用途 | 必须知道的边界 |
|---|---|---|
| Transition | 悬停/聚焦/展开 | 状态变化触发；显式列属性 |
| `@keyframes` | 加载/强调/多阶段 | 多元素编排弱；无限须可停 |
| Motion Path | 曲线装饰 | `offset-path/path()` + `offset-distance`；响应式坐标小心 |
| WAAPI | 暂停/反向/变速/拖进度 | 同 CSS 引擎；`composite/replace/add`；`finished` cancel 会 reject |
| rAF | 物理/跟随/自绘调度 | 主线程；`dt` 上限；`hidden` 停 |
| FLIP | 布局位移转合成 | 真 DOM 先变，视觉补偿 |
| SVG | 图标/路径/图表 | `pathLength=1` + `dashoffset 1→0`；形变需等点数 |
| Canvas 2D | 粒子/图表/游戏 | DPR≤2；`OffscreenCanvas` 可进 Worker |
| scroll()/view() | 进度/揭示 | 合成器友好；兼容未收敛，静态回退 |
| IO | 进入播一次 | 只发现时机，非逐帧引擎 |
| VT 同文档/跨文档 | 切换/形变/导航 | `startViewTransition` / `@view-transition{navigation:auto}`；过渡期不可交互 |

## 库对比（体积随版本变，用前核实）

| 方案 | gzip | 选谁 |
|---|---|---|
| 原生 CSS/WAAPI | 0 | 80% UI 默认 |
| Motion One | ~12KB | 非 React 轻量 |
| GSAP 核心 | ~22KB | timeline 位置参数（`-=0.3`/`<`）、ScrollTrigger pin+scrub；现全免费可商用 |
| Motion（原Framer） | 较大 | `motion/react` + AnimatePresence + layout/手势 |
| Anime.js v4 | ~17KB | 中小补间，SVG 好 |
| Lottie | 视渲染器 | AE JSON；中文转形状 |
| Rive | 小 | 状态机交互；许可核实 |
| PAG/Galacean | — | 国产中文/Wasm/营销特效 |

原则：同一元素同一属性只归一主；不为按钮引引擎。
