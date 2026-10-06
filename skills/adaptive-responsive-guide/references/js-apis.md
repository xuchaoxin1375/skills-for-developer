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
- 验收证据：把 change 写成滚动日志（时间 + 查询串 + matches，**只留最近 10 条**），验收记录直接截图这条日志：

```js
const add = (q, matches) => {
  const li = document.createElement('li');
  li.append(new Date().toTimeString().slice(0, 8), q, String(matches));
  log.prepend(li); while (log.children.length > 10) log.lastChild.remove();
};
mql.addEventListener('change', (e) => add(mql.media, e.matches));
```

- 媒体特性认不认识：`if (mql.media === 'not all')` 说明浏览器**不识别**这条查询（归一结果），比 `matches===false` 更早发现写错特性名。

## 状态单点同步（状态挂在 body 类上时）

```js
new MutationObserver(syncRailBtn).observe(document.body, { attributes: true, attributeFilter: ['class'] });
```

状态类一变，由一个 observer 反向同步触发器的 `aria-expanded` / `aria-label` / `title` / 图标，
不必在每个改状态的地方重复写四处；同步函数开头记得判断“当前是否归我管”，避免误改别的组件。

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
  `k = 0` 且放得下则主操作退图标 + 更多（见 `patterns.md` 进阶）。测量行与真按钮同组件同样式**含图标**（缺图标每颗低估约 22px，
  会算多可见数导致挤压），`visibility:hidden + absolute + inert + aria-hidden`，宽 `max-content`，文案变化（如“加入对比”→“移出对比”）与字体加载后重算。
  测量行若在命名容器外，不受方案规则影响：`···` 按钮须强制 `display:inline-flex` 才能量到 `w_more`（量不到则恒为 0，
  实测特定宽度带溢出最高 25px）；宽度一律用 `getBoundingClientRect().width` 小数值，`offsetWidth` 取整逐颗丢精度。
- 可用宽 `W` 必须扣掉操作区自身内边距（`clientWidth - paddingLeft - paddingRight`，小数）：`clientWidth` 含 padding，
  不扣等于判据多算 28px，362–386/412–424 带必溢出。
- 测量行自身不得撑开文档可滚区：用 `position:fixed`（视口锚定，不计入文档滚动溢出），否则 320/390 视口出现页面级横滚。
  `absolute + inset:0` 看似隐藏，`max-content` 宽仍会计入 `scrollWidth`。
- 实现五坑（实测可卡死/卡顿/溢出页面，必须遵守）：
  1. `fonts.ready.then(relayout)` 只注册一次，**禁写进 `relayout()` 内部**——已 resolved 的 promise 会形成微任务自循环，渲染器常驻满载、无头环境直接 wedged。
  2. 去重签名只看输出集合（可见集 + 切换文案），**不看原始像素宽 `W`**——`W` 逐像素都变，拖滑条会逐帧 `innerHTML` 重建（实测一次拖动 236 次变更→修后 15 次）。
  3. `input` 事件与 `ResizeObserver` 回调一律 rAF 节流（一帧最多算一次）；直接操纵的属性（如滑条驱动的 `max-width`）禁加 `transition`，否则跟手滞后 + 逐帧重算。
  4. 常驻按钮只许增长不许收缩（`flex:1 0 auto`），挤压永远由折叠解决，不靠压文字；残留 `flex:1 1 0 + min-width:0` 是挤压主凶，先清零。
  5. 菜单开着时禁重建菜单 DOM（连焦点一起销毁）：只更新页脚按钮与计数，菜单重建延后到关闭时；关闭后若数据脏则重算一次。
     回归断言：开菜单后拖滑条，菜单仍开且焦点不动；关后重开内容与新宽度一致。

## 其它

- `visualViewport`：软键盘/双指缩放可见区。iOS 不支持 `interactive-widget`，用它把可见高写进 CSS 变量：

```js
const vv = window.visualViewport;
if (vv) { const update = () =>
    document.documentElement.style.setProperty('--vvh', `${vv.height}px`);
  vv.addEventListener('resize', update); update(); }
```

- `IntersectionObserver`：懒加载/目录高亮/吸顶检测（滚动状态查询普及前的兜底）。
- 读数口径（调试面板/滑块/容器宽度显示）：`offsetWidth - clientWidth` 是滚动条差值，
  `clientWidth - paddingLeft - paddingRight` 才是内容盒宽——**与 `@container` 判据一致的值**；只扣 padding 不扣滚动条，读数会偏大一圈。
- 禁 UA 嗅探定布局；服务端确需设备信息用 Client Hints（`Sec-CH-UA-Mobile` 等，仅 Chromium 系，优化手段）。
