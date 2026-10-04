# 性能 / 无障碍 / 兼容清单

## 性能

- 只动 `transform/opacity`；禁 `width/height/top` 做持续运动。
- scroll/resize/mousemove 不直写样式，用 rAF 合批或 CSS 驱动；先读后写。
- `will-change` 临前加事后删；禁全局常驻、`translateZ(0)`、 `setInterval 16ms`。
- 大模糊阴影滤镜慎用；`contain: layout paint` 限范围。
- 验证：Performance + Paint flashing + Layer borders + CPU 降速 + 120Hz + 低端机。

## 无障碍（必须）

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
```

- `.01ms` 保事件触发；精细做法：位移视差停，颜色透明保留，入场变 ≤0.3s 淡入。
- JS `matchMedia` 监听；WAAPI/SMIL/Canvas/视频全覆盖；站内开关可覆盖系统。
- 5s+ 自动播放给暂停；勿闪烁传信；`opacity:0` ≠ 删除（焦点/读屏同步）。

## 兼容 / 国内 / 中文

- `@supports` + 运行时检测（`'animate' in Element.prototype` 等），不 UA 嗅探。
- Chrome/Edge/Firefox/Safari + 真移动端 + 微信 X5 + iOS WebKit 实测。
- npm 走 npmmirror；CDN 用前验证可达；tree-shaking；原生 0KB 优先。
- 中文逐字用 chars 或 `Intl.Segmenter('zh')`；Lottie 中文转曲；`font-display:swap` + `fonts.ready` 再入场；竖排注意轴对调。
