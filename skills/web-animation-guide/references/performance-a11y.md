# 性能 / 无障碍 / 兼容清单

## 性能

- 优先 `transform/opacity`（通常利于合成，不保证零成本）；颜色、阴影、裁切可能重绘；宽高、位置与 Grid 行轨过渡可能布局。小区域可按实测使用布局过渡，大范围联动优先 FLIP 或瞬时重排。独立 `translate/scale/rotate` 也需实测。
- scroll/resize/mousemove 不直写样式，用 rAF 合批或 CSS 驱动；先读后写。
- `will-change` 临前加事后删；禁全局常驻、`translateZ(0)`、 `setInterval 16ms`。
- 大模糊阴影滤镜慎用；`contain: layout paint` 限范围。
- 验证：Performance + Paint flashing + Layer borders + CPU 降速 + 120Hz + 低端机；无头可复现用 Playwright 采样 rect/opacity/遮罩曲线（逐点断言飞行形状），采样与截图分跑——截图会扰动 WAAPI 读数。

## 无障碍（必须）

```css
@media (prefers-reduced-motion: reduce) {
  /* 目标组件：保留可见终态，不为 transitionend 留极短时长 */
  .motion-panel, .motion-panel::before, .motion-panel::after,
  .busy-spinner { animation: none !important; transition: none !important; }
}
```

- 减弱下关闭非必要位移、缩放、视差与循环；默认瞬时切换，必要时可保留短透明度/颜色反馈。等待用静态图标和文字表达，不因 spinner 有语义就强制旋转。
- CSS 不会取消 JS 创建的 WAAPI/rAF/SMIL/Canvas 动画；开始前检测并监听 `matchMedia` 变化，取消后落正确终态，卸载移除监听/观察器/帧调度。
- 5s+ 自动播放给暂停；自动**更新**的信息不享 5 秒豁免（WCAG 2.2.2 条件不同）；勿闪烁传信（2.3.1 简明线：每秒≤3 次）；`opacity:0` ≠ 删除（焦点/读屏同步），隐藏交互内容要配 `inert`/`hidden`/焦点管理。
- 站内开关可进一步减弱系统设置，不静默抵消系统的 reduce；有效减弱条件为系统 reduce 或用户选择减弱。
- 无 hover-only 功能；焦点可见（禁裸 `outline:none`）；触控目标 44px（桌面≥24px）；正文对比度 ≥4.5:1；320px 宽可回流、页面级无横向滚动；中文行高 ≥1.6。
- `aria-live` 关键状态礼貌播报，不逐帧读计时器；进度用带可访问名的 `progressbar`；Canvas 重要内容给等价文本/数据表。
- 骨架 shimmer 用 transform 位移渐变层，不动 `background-position`（每帧 Paint）。

## 诚实进度

- 等待分级采用项目交互规范；与 `frontend-design` 同用时见其 `references/motion.md`。同步忙态与防重入独立于等待指示延迟。
- 未知总量用阶段行 + 不确定条，禁伪造百分比、禁 90% 久停、禁暗示未完成事务已完成。
- 本地计时模拟必须明示，不伪装服务端进度。

## 进出场与忙态验证矩阵

必须检查动画起止附近与代表性中间帧，并以正常速度回放检查连续性；慢放定位跳位、拉伸、裁切、闪暗与非预期速度突变，性能合格不代替视觉稳定。例：弹窗首尾正常，关闭一半时正文换行挤乱，仍不通过。

| 场景 | 必查结果 |
|---|---|
| 正常进入与退出 | 两个方向均有过渡；关闭语义、焦点与业务提交不等动画完成 |
| 退出开始与中间帧 | 开合标记移除后内容与布局仍保持；默认窗口可统一位移/等比缩放，不发生正文重排或非等比拉伸；先断言再查看截图 |
| 快速开→关→开、进入前立即关 | 最后命令决定终态，旧动画/回调不覆盖新状态 |
| 无属性变化、零时长、取消动画 | 不等 `transitionend`；视觉层可清理，隐藏内容不可聚焦 |
| reduce 首次加载与运行中切换 | 停非必要运动并落终态，文字与任务操作保留 |
| 特性不支持 | 直接正确终态，无不可见内容或退出残留 |
| 关闭按钮、Esc、触发源移除 | 层可关闭，焦点回有效入口或合理后备位置 |
| 短/长任务、连点、失败 | 同步防重入，短任务不闪指示，长任务有静态文本，失败恢复并可重试 |
| 卸载或移除组件 | 清动画与监听，迟到回调不改已销毁组件 |

行为先用真实浏览器断言；静态截图在 reduce 模式通过不能证明正常动效。正常模式单独采样活动动画/透明度与布局，再查看关键态截图；取景与查看按 [视觉验收协议](../../ai-verified-delivery/references/visual-acceptance.md)。截图与时间采样分跑，不以固定等待或截图文件存在代替断言。可暂停并定位到退出的 0/25/50/75/接近100%：默认淡出/位移窗口用布局尺寸和相对坐标排除整体变换；主动重排/形变按预期轨迹验，不要求所有动效几何恒定。正常速度回放与设备流畅度另验，暂停采样不能证明体感丝滑。

## 兼容 / 国内 / 中文

- `@supports` + 运行时检测（`'animate' in Element.prototype` 等），不 UA 嗅探。
- Chrome/Edge/Firefox/Safari + 真移动端 + 微信 X5 + iOS WebKit 实测。
- npm 走 npmmirror；CDN 用前验证可达；tree-shaking；原生 0KB 优先。
- 中文逐字用 chars 或 `Intl.Segmenter('zh')`；Lottie 中文转曲；`font-display:swap` + `fonts.ready` 再入场；竖排注意轴对调。
