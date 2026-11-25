# 动画排查：先确认它真的在播放

调参、评审“感觉不对”、动画没生效、跨设备表现不一致时，先按本页排除环境抑制，再用 DevTools 慢放定位。不要在动画被关闭的状态下评判曲线或节奏。

## 何时读

- 用户说“动画很差/没有动画/不如某某产品”，或要求调时长、缓动、编排。
- 改完动画要验收，尤其是侧栏、面板、抽屉这类容器展开。
- 同一页面在本机正常、在用户机器上瞬切，或反过来。

## 一、先排除 reduce 与全局覆盖

系统设置会直接改变 `prefers-reduced-motion`，页面里的全局规则又可能把时长压到接近零。两者的效果都是“瞬间到位”，很容易被误判成缓动写错或实现没生效。

| 环境 | 开关位置 |
| --- | --- |
| Windows 11 | 设置 → 辅助功能 → 视觉效果 → 动画效果 |
| Windows 10 | 设置 → 轻松使用 → 显示 → 在 Windows 中显示动画 |
| macOS | 系统设置 → 辅助功能 → 显示 → 减少动态效果 |
| iOS / iPadOS | 设置 → 辅助功能 → 动态效果 → 减弱动态效果 |
| Android | 设置 → 无障碍 → 移除动画（厂商名称可能不同） |

浏览器侧可以只对当前标签页模拟，不改系统：

- DevTools → Rendering → **Emulate CSS media feature `prefers-reduced-motion`**，在 `no-preference` 与 `reduce` 之间切换。
- DevTools → Animations 面板也能配合慢放；两者作用不同，不能互相替代。

页面侧先查三件事：

```js
matchMedia("(prefers-reduced-motion: reduce)").matches;
getComputedStyle(el).transitionProperty;   // none / 具体属性
document.getAnimations().length;            // 触发后立即看
```

再查应用有没有全局兜底，例如 `transition-duration: 0.01ms !important`、组件库的 `motion-reduce:*`、JS 里的 `matchMedia` 分支。它们会让源码里仍写着 250ms，计算值却变成 0.01ms，肉眼看到的就是瞬切。

**确认是 reduce 导致瞬切时，先告诉用户，不要在瞬切画面上调曲线。** 让用户临时打开系统动画，或用 Rendering 面板模拟 `no-preference`；验收后再恢复用户偏好。不要为了“看起来有动画”而静默绕过 `reduce`。

### 半套实现不算参照

有些产品只关掉一部分：容器自身 `transition: none`，外层布局轨道仍在动。Cloudflare 侧栏在 reduce 下就是这样：面板 57→260 瞬切，外壳 `grid-template-columns` 仍走 250ms；在 90ms 冻结时面板已是 260px，内容轨道才到 87px。它看起来“还有动画”，但状态并不同步，不能拿它当正确基线。

触发后立刻用 `document.getAnimations()` 看整棵树，分别确认容器、布局轨道、标签/图标、内边距是否都在同一策略下；只查一个元素的 `transition` 会漏掉半套实现。

## 二、DevTools Animations：10% 慢放

打开方式：DevTools → `Esc` → More tools → **Animations**；或 `Ctrl+Shift+P` 输入 “Show Animations”。

1. 先把播放速度调到 **10%**，再触发交互；面板会记录本次所有动画的时间线。
2. 看时间线上有哪些属性、各自的起止、延迟和缓动，重点找：
   - 同一元素上多个动画（`width` + `transform` + `opacity`）是否同帧开始、同帧结束；容器到了、内容还在追就是不同步。
   - 有没有属性根本没启动，或中途被第二次状态更新打断、重启动画。
   - 标签、分组标题、品牌字这类子元素是否在容器还没让出空间时就出现、被裁成半个字或省略号。
   - 布局属性（`width`、`height`、`margin`、`grid-template-*`）是否每帧重排；是否本可以用 `transform`/FLIP。
3. 拖时间线到 25%/50%/75%，分别看中间帧；10% 慢放能把“半个字形、边缘错位、分组行跳动”放大到肉眼可见。
4. 再以 100% 正常速度回放，确认体感和节奏；慢放通过不代表正常速度自然。

慢放看到的问题要回到代码找对应层，而不是只调总时长。例：文字在 90ms 出现半字，通常是标签盒随容器收缩且用了 `text-overflow: ellipsis`，或图标/内边距与文字不同曲线。

## 三、逐帧采样与冻结

10% 慢放用来“看”，需要数值证据时用 rAF 采样。截图会扰动时序，采样与截图分开跑。

```js
const samples = [];
const t0 = performance.now();
function tick() {
  samples.push({
    t: Math.round(performance.now() - t0),
    w: aside.getBoundingClientRect().width,
    labelW: label.getBoundingClientRect().width,
  });
  if (performance.now() - t0 < 800) requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
```

冻结到指定时间，便于截图和对比：

```js
document.getAnimations().forEach((a) => {
  a.pause();
  a.currentTime = 125;
});
```

采样结果看三件事：容器与子元素是否同帧到位、实际曲线是否等于设计值、帧间隔是否有明显长帧。无头浏览器可以用 Playwright 的 CDP screencast 拿 60fps 帧，再看接触表或逐帧图。

## 四、判读与记录

| 现象 | 先查 |
| --- | --- |
| 完全不动 | 系统/浏览器 reduce、全局 0.01ms、`transition-property: none`、值未变化、首帧写入 |
| 动了但“很廉价” | 10% 慢放：标签半字/省略号、子元素不同步、条件挂载、多个布局属性 |
| 只有某台机器不同 | 该机器 reduce 设置、浏览器模拟、组件库的减弱分支 |
| 慢放正常、正常速度别扭 | 曲线与时长、位移距离、是否有延迟或二次触发 |

记录时写明：日期、OS/浏览器、`prefers-reduced-motion` 实际值、是否用了 Rendering 模拟、播放速度、以及结论是在“动画真实播放”还是“瞬切”状态下得出。没有这行信息，后续很容易重复误判。
