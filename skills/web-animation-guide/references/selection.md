# 选型细节

## 技术边界

| 技术 | 典型用途 | 必须知道的边界 |
|---|---|---|
| Transition | 悬停/聚焦/展开 | 状态变化触发；显式列属性 |
| `@keyframes` | 加载/强调/多阶段 | 多元素编排弱；无限须可停 |
| Motion Path | 曲线装饰 | `offset-path/path()` + `offset-distance`；响应式坐标小心 |
| WAAPI | 暂停/反向/变速/拖进度 | 同 CSS 引擎；默认 easing 是 linear（CSS 是 ease）；keyframes 驼峰，连字符静默无效；`composite/replace/add`（拖拽偏移用 add 保基变换）；`finished` cancel 会 reject |
| rAF | 物理/跟随/自绘调度 | 主线程；`dt` 上限；`hidden` 停 |
| FLIP | 布局位移转合成 | 真 DOM 先变，视觉补偿；scale 扭曲圆角/阴影需反补偿；新元素无 First 改入场；删除先提交语义、后卸退出视觉层；打断用代际守卫 |
| SVG | 图标/路径/图表 | `pathLength=1` + `dashoffset 1→0`；形变需等点数 |
| Canvas 2D | 粒子/图表/游戏 | DPR≤2；`OffscreenCanvas` 可进 Worker |
| scroll()/view() | 进度/揭示 | 合成器友好；兼容未收敛，静态回退；`animation-range` 关键字：`entry`（进→全进）/`contain`（全在内）/`exit`（开始离→全离）/`cover`（全全程）/`when`（单点对齐） |
| `@starting-style` + `transition-behavior: allow-discrete` | 首次挂载/`display`/`overlay` 进出场 | 需 `@supports` 回退；同帧写起终点不播，双 rAF 兜底 |
| `grid-template-rows: 0fr↔1fr` | 小区域高度展开 | 子层 `min-height:0; overflow:hidden`；仍触发布局，测联动成本；不支持时瞬时展开 |
| `steps(n, jump-*)` | 雪碧图/打字机/翻牌 | n=帧数；jump-end 默认，jump-none 首尾帧都保留 |
| `@property` | 渐变角/数值令牌插值 | 未注册的自定义属性不补间 |
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
| Ant Design 动效规范 | 0（规范） | 中文设计原则“自然、高效、克制”，可采纳其动效语言；引包另核验维护与许可 |

原则：同一元素同一属性只归一主；不为按钮引引擎。

## 令牌来源与尺寸选型

实际时长、缓动、位移来自项目令牌；与 `frontend-design` 同用时，工具界面默认预算见其 `references/motion.md`。本文件不维护第二套时长或 stagger 表，示例数值只作演示；整组编排不能拖延任务可用。

- 普通进出场优先透明度/变换；仅为了方向感，不必动画真实高度。
- 退出时保留布局的实现边界见 `interactions.md`：关闭属性/状态类只控制可见性，所需排列、尺寸、内边距和裁切常驻或放稳定内层；不要提前清空正文。淡出也会因选择器失效而重排，不能只查动画属性。
- 必须推动相邻内容的小折叠区可用 Grid 高度过渡；不要声称它只走合成器。大内容/多面板联动先测布局成本，再选 FLIP 或瞬时重排。
- FLIP 包含终态布局与测量，不保证零回流；scale 会变形文字、圆角和阴影，按需反补偿或淡化。重内容冻结只用于隐藏内容策略；揭示内容应先按终态排版，避免动画后跳变。
- 必要遮罩可掩盖中间重排，但不代替性能优化；遮罩独立于运动面板，避免跟随面板透明度叠加造成闪暗。骨架与密集文本交接不做长时间交叉淡化，避免鬼影。
- `scaleY` 不会推动相邻布局且会压缩内容，不作为通用高度回退；不支持或减弱时直接给正确终态。
- 减弱与收尾策略统一见 `performance-a11y.md`，不为保事件强行留极短动画。
