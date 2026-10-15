# 技术片段（集成时补齐回退、减弱与清理）

这些是局部技术片段，并非每段都可独立运行。完整弹窗、按钮忙态与下拉示例集中维护在 [interactions.md](interactions.md)；减弱/清理/验证统一见 [performance-a11y.md](performance-a11y.md)。数值是示例默认值，实际读取项目令牌。

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

## 弹窗 / 按钮忙态 / 下拉

见 [interactions.md](interactions.md) 的完整示例；这里不再维护第二份进出场和焦点代码。

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

内容层三策略：clip（壳反向 `scale(1/sx,1/sy)` 保像素，揭示框观感；反 scale 锚点必须与壳缩放中心同一点——取终态壳中心在内容层局部坐标里显式设 `transform-origin`，差一点全程错位）/ fade（内容 `opacity 0→1` + 骨架层反向交叉顶中点）/ stretch（直接跟随变形，仅用于明确的形变设计并验全过程）。普通窗口关闭优先稳定布局的淡出/短位移，不默认套用 FLIP 拉伸。
新元素无 First 改 `opacity+translateY` 入场；删节点先播出场再卸载。

## 首值不补间（入场触发三选一）

```css
/* ① @starting-style（完整写法见 interactions.md；display/overlay 需 allow-discrete） */
```
```js
// ② 挂载后双 rAF 再加类，保证浏览器已完成首帧
requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('in')));
// ③ 入场直接用 @keyframes（fill-mode: both 防延迟闪烁）
```

## 小区域高度展开（仍会布局）

```css
.panel { display: grid; grid-template-rows: 0fr; }
.panel[data-open] { grid-template-rows: 1fr; }
.panel > div { min-height: 0; overflow: hidden; }
@media (prefers-reduced-motion: no-preference) {
  @supports (grid-template-rows: 1fr) {
    .panel { transition: grid-template-rows var(--motion-enter, 200ms) ease-out; }
  }
}
/* 语义开合、inert 与焦点由调用方同步管理；不支持过渡时直接终态。 */
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

## SVG 定位与动画分层

```html
<!-- 外层定位置（属性保留），内层跑动画；两者不可压到同一元素 -->
<g transform="translate(120,80)">
  <g class="spin">…</g>
</g>
```

```css
.spin { transform-box: fill-box; transform-origin: center; animation: spin 1s linear infinite; }
```

## 双解骨骼定分支

两段骨骼加两端约束的角色动作（如脚踩踏板、手握车把），中间关节有两个镜像解：
开工即固定用哪一支，全程不变，不逐帧取夹角更小的解。死点（曲柄最高/最低处）
附近两解几乎重合，偏离后迅速分开，逐帧就近必在死点处跳变。

验证：冻结动画到典型相位（首尾与中间帧），取关键元素 `getBoundingClientRect()` 换算回 SVG 坐标，与设计锚点核对；只看截图会漏掉被裁在屏外的缺件。闭环约束（接触不脱离、关节不超伸）另在正交极限相位逐个冻结，断言关节角区间与末端贴合偏差，只验首尾会漏掉中间相位超伸；构造上让贴合恒为零，即末端直接取约束目标坐标，不各自画好再对齐。

## SVG 一体性画法

解剖相连的部位共用外轮廓，内部不画分割线：肢体用变宽填充多边形（根部宽、末端窄）而非等宽描边；相连体共用同一填充（用户空间渐变保证同色场），肢体自身不画描边、只靠遮挡关系表达前后；过渡缝用天然遮盖物（围巾、衣领、阴影）藏住。例：大腿根部深埋入躯干路径内部再出头，根部不出头不画线；脚画成小腿末端的膨大，而非独立椭圆压在线端。

## SVG 描边 + Canvas DPR

```js
path.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }],
  { duration: 1500, fill: 'forwards' }).finished.catch(()=>{});
const dpr = Math.min(devicePixelRatio || 1, 2);
canvas.width = rect.width * dpr; ctx.setTransform(dpr,0,0,dpr,0,0);
```
