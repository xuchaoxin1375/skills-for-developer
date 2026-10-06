# JS 辅助 API（CSS 做不到时才用）

> 何时读：要随断点改行为（非样式）或读元素尺寸计算时。原则：**CSS 能做的不用 JS**。来源：opus JS 章 + `index.html:2380`。
> 对应实验：`matchMedia` change 日志、`ResizeObserver` 图表重绘。

## matchMedia（监听断点行为）

```js
const mql = window.matchMedia('(min-width: 64rem)'); // 传统写法兼容最好
function handle(e) { document.body.classList.toggle('is-desktop', e.matches); }
handle(mql);
mql.addEventListener('change', handle); // 只在跨越断点触发，比 resize 高效
```

- `mql.matches / mql.media / change 事件`；Safari 14 前用废弃 `addListener`。
- 典型：跨断点关闭抽屉、移除遮罩/滚动锁（行为非样式）。

## ResizeObserver（监听元素尺寸）

```js
const ro = new ResizeObserver(() => chart.resize()); // 如 ECharts 在侧栏收起后重绘
ro.observe(chart.getDom());
```

- 不要在 `resize` 里直接读写布局；行为用 `matchMedia`，元素尺寸用 `ResizeObserver`。

## Priority+ 测量折叠（操作区专用，CSS 做不到动态 k 时才用）

- 输入：操作区可用宽 `W`（`ResizeObserver` 监听），隐藏测量行读每个带文字按钮自然宽 `w_i`、更多按钮宽 `w_more`、
  主操作纯图标宽 `w_icon`，间距 `G` 与 CSS `gap` 一致；判据 `W >= sum(B_i)+(N-1)*G`。
- 流程：全放得下则全显；否则按优先级累加 `acc = w_more + sum(w_i) + gaps` 算最大可见数 `k`，前 `k` 个按显示顺序渲染、其余进菜单；
  `k = 0` 且放得下则主操作退图标 + 更多（见 `patterns.md` 进阶）。测量行与真按钮同组件同样式（`visibility:hidden + absolute + inert + aria-hidden`，
  宽 `max-content`），文案变化（如“加入对比”→“移出对比”）与字体加载后重算，无布局反馈环。

## 其它

- `visualViewport`：软键盘/双指缩放可见区（见 `responsive-core.md` 聊天页 `--vvh` 兜底）。
- `IntersectionObserver`：懒加载/目录高亮/吸顶检测（滚动状态查询普及前的兜底）。
- 禁 UA 嗅探定布局；服务端确需设备信息用 Client Hints（`Sec-CH-UA-Mobile` 等，仅 Chromium 系，优化手段）。
