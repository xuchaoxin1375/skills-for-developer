# 性能 / 无障碍 / 兼容清单

## 性能

- 只动 `transform/opacity`（合成，极低）；`color/box-shadow/clip-path` 走 Paint（中，短促小面积可用）；`filter:blur` 高成本（限时长限面积）；`width/height/top/left/margin/font-size/flex-grow` 走 Layout（禁逐帧，位移改 translate、缩放改 scale、排序改 FLIP）。`translate/scale/rotate` 独立属性与 `transform` 等价，均可单独过渡。
- scroll/resize/mousemove 不直写样式，用 rAF 合批或 CSS 驱动；先读后写。
- `will-change` 临前加事后删；禁全局常驻、`translateZ(0)`、 `setInterval 16ms`。
- 大模糊阴影滤镜慎用；`contain: layout paint` 限范围。
- 验证：Performance + Paint flashing + Layer borders + CPU 降速 + 120Hz + 低端机；无头可复现用 Playwright 采样 rect/opacity/遮罩曲线（逐点断言飞行形状），采样与截图分跑——截图会扰动 WAAPI 读数。

## 无障碍（必须）

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
```

- `.01ms` 保事件触发；精细做法：位移视差停，颜色透明保留，入场变 ≤0.3s 淡入。
- JS `matchMedia` 监听；WAAPI/SMIL/Canvas/视频全覆盖；站内开关可覆盖系统。
- 5s+ 自动播放给暂停；自动**更新**的信息不享 5 秒豁免（WCAG 2.2.2 条件不同）；勿闪烁传信（2.3.1 简明线：每秒≤3 次）；`opacity:0` ≠ 删除（焦点/读屏同步），隐藏交互内容要配 `inert`/`hidden`/焦点管理。
- 站内动效开关只能 further reduce：系统已 reduce 时，页面不可重新开启动效。
- 无 hover-only 功能；焦点可见（禁裸 `outline:none`）；触控目标 44px（桌面≥24px）；正文对比度 ≥4.5:1；320px 宽可回流、页面级无横向滚动；中文行高 ≥1.6。
- `aria-live` 关键状态礼貌播报，不逐帧读计时器；进度用带可访问名的 `progressbar`；Canvas 重要内容给等价文本/数据表。
- 骨架 shimmer 用 transform 位移渐变层，不动 `background-position`（每帧 Paint）。

## 诚实进度

- ≤100ms 直接完成，不造加载态；100ms~2s 轻量不确定进度；>2s 给进度 + 已用时间 + 取消/可离开。
- 未知总量用阶段行 + 不确定条，禁伪造百分比、禁 90% 久停、禁暗示未完成事务已完成。
- 本地计时模拟必须明示，不伪装服务端进度。

## 兼容 / 国内 / 中文

- `@supports` + 运行时检测（`'animate' in Element.prototype` 等），不 UA 嗅探。
- Chrome/Edge/Firefox/Safari + 真移动端 + 微信 X5 + iOS WebKit 实测。
- npm 走 npmmirror；CDN 用前验证可达；tree-shaking；原生 0KB 优先。
- 中文逐字用 chars 或 `Intl.Segmenter('zh')`；Lottie 中文转曲；`font-display:swap` + `fonts.ready` 再入场；竖排注意轴对调。
