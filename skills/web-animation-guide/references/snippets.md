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

## VT（同文档）

```js
function withVT(u) {
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) { u(); return; }
  document.startViewTransition(u);
}
```

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

## SVG 描边 + Canvas DPR

```js
path.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }],
  { duration: 1500, fill: 'forwards' }).finished.catch(()=>{});
const dpr = Math.min(devicePixelRatio || 1, 2);
canvas.width = rect.width * dpr; ctx.setTransform(dpr,0,0,dpr,0,0);
```
