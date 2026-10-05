# 选型细节

## 技术边界

| 技术 | 典型用途 | 必须知道的边界 |
|---|---|---|
| Transition | 悬停/聚焦/展开 | 状态变化触发；显式列属性 |
| `@keyframes` | 加载/强调/多阶段 | 多元素编排弱；无限须可停 |
| Motion Path | 曲线装饰 | `offset-path/path()` + `offset-distance`；响应式坐标小心 |
| WAAPI | 暂停/反向/变速/拖进度 | 同 CSS 引擎；默认 easing 是 linear（CSS 是 ease）；keyframes 驼峰，连字符静默无效；`composite/replace/add`（拖拽偏移用 add 保基变换）；`finished` cancel 会 reject |
| rAF | 物理/跟随/自绘调度 | 主线程；`dt` 上限；`hidden` 停 |
| FLIP | 布局位移转合成 | 真 DOM 先变，视觉补偿；scale 扭曲圆角/阴影需反补偿；新元素无 First 改入场；删先播后卸；打断用代际守卫 |
| SVG | 图标/路径/图表 | `pathLength=1` + `dashoffset 1→0`；形变需等点数 |
| Canvas 2D | 粒子/图表/游戏 | DPR≤2；`OffscreenCanvas` 可进 Worker |
| scroll()/view() | 进度/揭示 | 合成器友好；兼容未收敛，静态回退 |
| IO | 进入播一次 | 只发现时机，非逐帧引擎 |
| VT 同文档/跨文档 | 切换/形变/导航 | `startViewTransition` / `@view-transition{navigation:auto}`；过渡期不可交互；命名按数据 id，快照内唯一；old/new 错峰，禁 `animation:none` 硬切旧快照 |

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

## 时长 / 缓动令牌（直接抄）

| 用途 | 时长 | 缓动 |
|---|---|---|
| 小反馈（按压/勾选） | 120~200ms | 进场 `cubic-bezier(0,0,.2,1)` |
| 进入 | 200~240ms | `cubic-bezier(0,0,.2,1)`（ease-out 系） |
| 退出 | 160~200ms，可略快于进入 | `cubic-bezier(.4,0,1,1)`（ease-in 系） |
| 布局变化（FLIP/展开） | 200~320ms，上限 320ms | 同进入 |
| 视图切换（VT） | 300~500ms | 同进入 |

- stagger 间隔 40~80ms，整组 ≤600ms，不拖任务；`delay` 仅用于必要编排。
- 单次动效 >2s 的不叫过渡，叫进度：给进度条 + 已用时间 + 取消/可离开（见诚实进度）。
- reduced-motion 下把时长归零而非删除动画（保事件触发），位移视差停，颜色透明保留。
