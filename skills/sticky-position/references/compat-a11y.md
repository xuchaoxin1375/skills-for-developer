# 兼容性、渐进增强与无障碍

## 一、浏览器支持

| 浏览器 | 版本 | 备注 |
|---|---|---|
| Chrome | 56+ | 稳定 |
| Edge | 16+ | 稳定 |
| Firefox | 32+ | 稳定 |
| Safari | 13+ | 更早版本需 `-webkit-` 前缀 |
| Opera | 42+ | 稳定 |
| Samsung Internet | 6.2+ | 稳定 |
| 国内主流浏览器 | ✓ | 360 / QQ / UC / 微信 WebView（Chromium/WebKit 内核） |
| IE 11 及更早 | ✗ | 非法值 → 回退为 `static` |

移动端另需注意：始终包含 viewport meta 标签，缺失时各种定位行为都会异常；
避免在父元素上使用 `overflow: hidden`（回到失效排查原因 2）。

关联特性兼容（排查与渐进增强时会用到，用 `CSS.supports(属性, 值)` 可在 JS 侧实时检测）：

| 特性 | Chrome/Edge | Firefox | Safari | 说明 |
|---|---|---|---|---|
| `overflow: clip` | 90+ | 81+ | 16+ | 排查方案 B 的前置条件 |
| `scroll-state()` 查询 | 133+ | ✗ | ✗ | 仅 Chromium，跨浏览器用 IO 哨兵兜底 |
| 逻辑属性（`inset-block-start` 等） | 87+ | 66+ | 14.1+ | 国际化布局可放心用 |
| `scroll-margin-top` | 广泛支持 | 广泛支持 | 广泛支持 | 锚点让位，旧 WebView 也基本可用 |

打印样式：纸上没有"滚动"，sticky 应整体回退，否则可能每页重复表头或产生空白页：

```css
@media print {
  .site-nav, .toc, thead th, .action-bar { position: static !important; }
}
```

```js
// 打印前展开所有折叠说明，打印后恢复（CSS 无法强制打开 details）
let opened = [];
window.addEventListener('beforeprint', () => {
  opened = [...document.querySelectorAll('details')].map((el) => [el, el.open]);
  opened.forEach(([el]) => { el.open = true; });
});
window.addEventListener('afterprint', () => {
  opened.forEach(([el, was]) => { el.open = was; });
});
```

## 二、渐进增强模板

不支持 sticky 时回退 `static` 通常是可接受的降级，但如果面板里有 `position: absolute`
的子元素（角标、弹钮），回退后会以外层容器为参照"飞出去"。先写 `relative` 兜底保住参照：

```css
.panel {
  position: relative;              /* 兜底：保证 absolute 子元素有参照 */
}
@supports (position: sticky) {
  .panel {
    position: sticky;              /* 增强：能力到位才升级 */
    bottom: 20px;
  }
}
```

- 兜底声明写在外层，增强写在 `@supports` 内，形成清晰的降级 / 增强分层。
- 老 Safari 双写：先 `position: -webkit-sticky;` 再 `position: sticky;`（Safari 13+ 已无需前缀，
  仅在需要兼顾很老的 iOS 时保留）。
- JS 侧特性检测：`CSS.supports('position', 'sticky')`。
- 需要精确区分能力时，CSS 用 `@supports`，两者等价但作用层不同。

## 三、无障碍与用户体验

| 项 | 要求 | 写法 |
|---|---|---|
| 锚点让位 | 标题不被吸顶栏遮住 | `html { scroll-padding-top: 64px; }` 或目标 `scroll-margin-top: 16px`，两者可叠加但别重复预留过大空白 |
| 键盘焦点 | Tab 聚焦的链接不被吸顶区遮挡 | 同上统一治理；焦点轮廓清晰可见 |
| 对比度 | 吸附后叠在内容之上 | 背景不透明、文本对比度达 WCAG AA、文字放大后仍可读 |
| 占屏高度 | 小屏吸顶元素持续吞掉可视区 | 降低高度；或"下滑隐藏 / 上滑再现"（sticky 定位 + JS 切 `transform`） |
| 窄屏 | 挤占阅读空间 | 窄屏取消侧边目录吸附，恢复常规排版 |
| 动效 | 尊重系统偏好 | `@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }` |

配套模板：

```css
html { scroll-padding-top: 64px; }
section[id] { scroll-margin-top: 16px; }
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
}
```

## 四、性能边界

- 不用滚动监听模拟定位，不代表任何 sticky 内容都自动 60 FPS——复杂绘制仍可能带来开销，**需实测**。
- 需要"吸附状态联动"（如吸附后加阴影、显进度条）时只有两种正规手段（不要用滚动监听读 `scrollY`
  算位置，高频且易抖）：

**方案一（推荐）：Intersection Observer 哨兵。** sticky 本身不提供"我粘住了"的回调，
经典解法是在其**自然位置正上方**放一个 1px 的哨兵，观察它离开滚动口的时刻——全程无 onscroll：

```html
<div class="scroller">
  <div class="sentinel" aria-hidden="true"></div>
  <div class="toolbar">工具栏</div>
  …长内容…
</div>
```

```css
.toolbar { position: sticky; top: 0; }
.toolbar.is-stuck { box-shadow: 0 2px 8px rgb(0 0 0 / .15); }
.sentinel { height: 1px; }
```

```js
const bar = document.querySelector('.toolbar');
const io = new IntersectionObserver(([entry]) => {
  bar.classList.toggle('is-stuck', !entry.isIntersecting);
}, { root: document.querySelector('.scroller'), threshold: 0 }); // 视口滚动时省略 root
io.observe(document.querySelector('.sentinel'));
```

**方案二（Chromium-only）：滚动状态容器查询。** 纯声明式，规则写在容器上、作用于**后代**：

```css
.header-wrap {
  position: sticky;
  top: 0;
  container-type: scroll-state;
}
@container scroll-state(stuck: top) {
  .header-wrap > .header { box-shadow: 0 2px 8px rgb(0 0 0 / .15); }
}
```

三个坑：阴影必须加在**内层** `.header` 上（查询作用于容器的后代，不能直接打扮容器自己）；
除 `stuck` 外还有 `snapped`（滚动吸附当前项）、`scrollable: bottom`（下方还有可滚内容）等条件；
**仅 Chrome/Edge 133+ 支持**，跨浏览器一律用方案一兜底。
- 需要随滚动进度变化的效果（进度条、视差），优先 CSS 滚动驱动动画
  （`animation-timeline: scroll()`）而非 JS 读取 `scrollY`。
- 平滑锚点滚动配合 `prefers-reduced-motion` 关闭，避免动效不适。

## 五、上线前核对（与 SKILL.md 第九节一致）

1. 目标轴至少一个非 `auto` 的 inset。
2. 已确认最近滚动容器，无非预期 overflow 祖先，也查了 `contain`。
3. 包含块足够大，未被 Flex / Grid 拉满。
4. 背景不透明、z-index 合理，交叉单元格层级最高。
5. 锚点、Tab 焦点、放大内容不被吸顶区遮挡。
6. 窄屏、短视口与真实触屏滚动已检查。
7. 目标浏览器已验证，不支持时可自然降级。
8. 定位由 CSS 完成，未引入高频重排与不必要动效。
