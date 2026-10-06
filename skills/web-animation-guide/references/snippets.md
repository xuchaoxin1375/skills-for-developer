# 可粘贴片段（均含回退/减弱要点，版本以 MDN 为准）

## Transition（显式属性 + 键盘）

```css
.card { transition: transform 250ms cubic-bezier(.2,.8,.2,1), box-shadow 250ms ease; }
.card:hover, .card:focus-visible { transform: translateY(-4px); }
```

## Keyframes + linear() 回弹

```css
.ball.bounce { animation: drop 1.4s both;
  animation-timing-function: linear(0,.063,.25,.563,1 36.4%,.812,.75,.813,1 72.7%,.953,.938,.953,1 90.9%,.984,1); }
@keyframes drop { from { transform: translateY(-70px); } to { transform: translateY(0); } }
```

## starting-style dialog

```css
dialog { opacity: 0; translate: 0 20px;
  transition: opacity .4s, translate .4s, display .4s allow-discrete, overlay .4s allow-discrete; }
dialog[open] { opacity: 1; translate: 0 0; }
@starting-style { dialog[open] { opacity: 0; translate: 0 20px; } }
```

## Motion Path（回退直线）

```css
.dot { left: 12px; top: 78px; }
@supports (offset-path: path("M 0 0 L 1 1")) {
  .dot { left: 0; top: 0; offset-path: path("M 12 78 C 52 6 137 117 188 64"); }
  .go .dot { animation: orb 4s linear infinite alternate; }
}
@keyframes orb { to { offset-distance: 100%; } }
```

## 滚动揭示（默认可见 + 回退）

```css
.reveal { opacity: 1; }
@supports (animation-timeline: view()) {
  .reveal { animation: rv linear both; animation-timeline: view(); animation-range: entry 0% entry 60%; }
}
/* 不支持时 JS 加 .need-io + IO 补 .in-view */
```

## 滚动兜底公式（不支持 animation-timeline 时）

```js
// 只写 transform；进度条 scaleX，入场一次性加类
if (!CSS.supports('animation-timeline: scroll()')) {
  scroller.addEventListener('scroll', () => requestAnimationFrame(() => {
    const p = Math.min(1, scroller.scrollTop / (scroller.scrollHeight - scroller.clientHeight));
    bar.style.transform = `scaleX(${p})`;
  }), { passive: true });
  new IntersectionObserver(es => es.forEach(e =>
    e.isIntersecting && e.target.classList.add('in-view')),
    { root: scroller, threshold: .3 }).observe(el);
}

## VT（同文档）

```js
function withVT(u) {
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) { u(); return; }
  document.startViewTransition(u);
}
```

## VT 进阶（命名 + 变量化编排 + 收尾）

```js
// 按数据 id 命名（快照内唯一），时长走变量，结束后清场防冲突
function withVTNamed(update, name, dur = '420ms') {
  const root = document.documentElement;
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) { update(); return null; }
  root.style.setProperty('--vt-dur', dur);
  el.style.viewTransitionName = name; // 如 'vt-' + id；React 内 update 包 flushSync
  const vt = document.startViewTransition(update);
  vt.finished.finally(() => { el.style.viewTransitionName = ''; root.style.removeProperty('--vt-dur'); });
  return vt;
}
/* CSS：::view-transition-group(*) { animation-duration: var(--vt-dur, 420ms); }
   错峰：old 快照先走（约 60% 时长），new 快照延迟进（约 80% 时长 + 18% delay）；
   禁给 old 写 animation:none，否则新快照未到时旧盖直接硬切。 */

## WAAPI（变速/拖动/cancel 安全）

```js
const an = el.animate(
  [{ transform: 'translateX(0)' }, { transform: 'translateX(220px)', offset: .7 }, { transform: 'translateX(0)' }],
  { duration: 2000, easing: 'ease-in-out', fill: 'both' });
an.pause();
an.updatePlaybackRate(2); // 不跳帧
scrub.oninput = () => { an.pause(); an.currentTime = +scrub.value; };
an.finished.catch(() => {}); // cancel 会 reject
```

## rAF（dt 上限 + 隐藏停）

```js
let last = 0;
function frame(ts) {
  const dt = Math.min((ts - last) / 1000, .05); last = ts;
  x += v * dt; // 不假设 60Hz
  if (!document.hidden) id = requestAnimationFrame(frame);
}
```

## FLIP

```js
const first = new Map(els.map(x => [x, x.getBoundingClientRect()]));
mutate(); // 真改 DOM
els.forEach(x => {
  const a = first.get(x), b = x.getBoundingClientRect();
  x.animate([{ transform: `translate(${a.left-b.left}px,${a.top-b.top}px)` }, { transform: 'none' }],
    { duration: 400, easing: 'cubic-bezier(.2,.8,.2,1)' });
});
```

## FLIP 进阶（scale 装饰反补偿 + 代际守卫）

```js
// 反补偿：scale 会同步放大圆角/阴影，起始帧除回去，结束帧恢复
const sx = a.width / b.width, sy = a.height / b.height;
x.animate([
  { transform: `translate(${a.left-b.left}px,${a.top-b.top}px) scale(${sx},${sy})`,
    borderRadius: `${R / sx}px`, boxShadow: `0 ${24 * sy}px ${48 * sy}px rgba(0,0,0,.25)` },
  { transform: 'none', borderRadius: `${R}px`, boxShadow: '0 24px 48px rgba(0,0,0,.25)' }
], { duration: 420, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'both' })
  .finished.then(() => x.getAnimations().forEach(p => p.cancel())) // 收尾撤 fill，让样式接管
  .catch(() => {}); // cancel 会 reject
```

```js
// 代际守卫：连点/反向不再闪跳，任何命令式动画可套
let gen = 0;
async function fly(to) {
  const my = ++gen;
  anims.forEach(a => a.cancel());
  /* ...本次飞行... */
  if (gen !== my) return; // 旧飞行自行退出
}
```

内容层三策略（按观感选）：clip（壳反向 `scale(1/sx,1/sy)` 保像素，揭示框观感；反 scale 锚点必须与壳缩放中心同一点——取终态壳中心在内容层局部坐标里显式设 `transform-origin`，差一点全程错位）/ fade（内容 `opacity 0→1` + 骨架层反向交叉顶中点）/ stretch（直接跟随，许变形）。
新元素无 First 改 `opacity+translateY` 入场；删节点先播出场再卸载。

## 首值不补间（入场触发三选一）

```css
/* ① @starting-style（完整写法见文首 dialog 示例；display/overlay 需 allow-discrete） */
```
```js
// ② 挂载后双 rAF 再加类，保证浏览器已完成首帧
requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('in')));
// ③ 入场直接用 @keyframes（fill-mode: both 防延迟闪烁）
```

## 高度 auto 展开（禁逐帧动 height）

```css
.panel { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 240ms cubic-bezier(.2,.8,.2,1); }
.panel[data-open] { grid-template-rows: 1fr; }
.panel > div { overflow: hidden; }
/* 不支持时回退 scaleY（内容会变形）或 max-height 估算法 */
```

## steps() 逐格 / 雪碧图

```css
.strip { width: 800%; animation: frame 2400ms steps(8, end) infinite; } /* 8 帧 */
@keyframes frame { to { transform: translateX(-87.5%); } }
/* jump-start / jump-end(默认) / jump-none / jump-both 控制首尾帧停留 */
```

## @property 类型化令牌（渐变/数值可插值）

```css
@property --angle { syntax: "<angle>"; initial-value: 0deg; inherits: false; }
.aurora { background: conic-gradient(from var(--angle), #08f, #f08);
  transition: --angle 1.2s linear; } /* 未注册则直接跳变 */
```

## 全站暂停 / 慢放（无需逐个持引用）

```js
document.getAnimations().forEach(a => a.pause());
document.getAnimations().forEach(a => a.updatePlaybackRate(.5)); // 慢放走查
```

## 读写分批（避免强制同步布局）

```js
// 坏：读写交替，每轮强制重排。好：先批量读，再批量写
const hs = els.map(e => e.offsetHeight);
requestAnimationFrame(() => els.forEach((e, i) => { e.style.height = hs[i] * 2 + 'px'; }));
```

## React 集成要点

```js
// FLIP：useLayoutEffect 绘制前同步测量（useEffect 会闪一帧瞬移）
useLayoutEffect(() => { /* measure → invert → animate */ });
// VT：回调内同步提交 DOM
document.startViewTransition(() => flushSync(() => setState(next)));
// 卸载：animRef.current?.cancel()；StrictMode 双挂载 → 初始化可重复、清理完整
```

## 弹簧积分（rAF）

```js
// F = -k(x - target) - c·v；dt 秒，钳 ≤0.032
const dt = Math.min(.032, (t - last) / 1000); last = t;
vel += (-k * (pos - target) - c * vel) * dt; pos += vel * dt;
el.style.transform = `translateX(${pos}px)`; // 只写 transform
```

## SVG 描边 + Canvas DPR

```js
path.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }],
  { duration: 1500, fill: 'forwards' }).finished.catch(()=>{});
const dpr = Math.min(devicePixelRatio || 1, 2);
canvas.width = rect.width * dpr; ctx.setTransform(dpr,0,0,dpr,0,0);
```
