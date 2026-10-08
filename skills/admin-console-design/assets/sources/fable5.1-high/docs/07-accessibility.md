# 07 · 无障碍（Accessibility）

无障碍是验收底线。本篇按"必须 / 应该 / 可以 / 避免"列出规则，并给出本模拟稿中的实现位置。

## 1. 键盘

### 必须

- 所有交互元素可通过 `Tab` 到达、`Enter/Space` 激活；顺序与视觉顺序一致。
- 浮层打开后焦点进入浮层；关闭后焦点回到触发元素（Popover、Menu、Dialog 均实现）。
- 模态（Dialog、移动抽屉、命令面板）具备焦点陷阱与 `Esc` 关闭。
- 列表型浮层（Menu、命令面板）支持 `↑ ↓ Home End` 导航。
- 折叠侧边栏在键盘聚焦时自动展开（peek），失焦收起。
- 提供"Skip to main content"链接。

### 应该

- 全局快捷键不与输入冲突（输入框内不响应 `[`、`Space`）。
- 向导换步后把焦点移到步骤标题。

## 2. 焦点可见

- `:focus-visible` 统一 2px 主色外描边 + 2px offset；**禁止** `outline: none` 而无替代。
- 输入框聚焦：边框主色 + 2px 30% 主色环。
- 自定义单选卡片用 `:has(:focus-visible)` 在整卡显示焦点环。

## 3. 命中目标与间距

- 桌面 ≥ 24×24px；触屏 ≥ 44×44px。复选框 16px 视觉框外包 24px 命中区；图标按钮 32/36px。
- 相邻可点击元素间距 ≥ 4px。

## 4. 对比度

| 组合 | 浅色 | 深色 |
| --- | --- | --- |
| text / surface | 15.9:1 | 13.8:1 |
| text-2 / surface | 8.4:1 | 9.0:1 |
| text-3 / surface | 4.6:1 | 5.3:1 |
| primary / surface（文字） | 7.6:1 | 7.3:1 |
| white / primary（按钮） | 7.6:1 | — |
| fg-inverse / primary（深色按钮） | — | 8.9:1 |

- 正文、占位符、辅助文字 ≥ 4.5:1；图标与边框 ≥ 3:1。
- 状态不仅靠颜色：错误带图标与文字，Proxied 带云朵图标 + 文字，排序带箭头 + `aria-sort`。

## 5. 语义与 ARIA

| 组件 | 语义 |
| --- | --- |
| 导航 | `<nav aria-label="Primary">`，激活项 `aria-current="page"`，分组按钮 `aria-expanded` + `aria-controls` |
| 开关 | `<button role="switch" aria-checked>` + `aria-labelledby/-describedby` |
| 复选框 | 原生 `<input type=checkbox>`（自定义外观），`indeterminate` 由 ref 设置 |
| 表格 | `<caption>`、`<th scope=col>`、`aria-sort` |
| 字段 | `<label for>`、`aria-invalid`、`aria-describedby` 指向 hint/error、错误 `role=alert` |
| Tooltip | `role=tooltip` + 触发元素 `aria-describedby`，hover 与 focus 都能触发 |
| Popover | `role=dialog aria-label`，触发按钮 `aria-expanded aria-haspopup` |
| Dialog | `role=dialog aria-modal aria-labelledby aria-describedby` |
| Toast | 容器 `role=region aria-label="Notifications"`；成功 `role=status`，错误 `role=alert` |
| 命令面板 | `role=combobox aria-activedescendant` + `role=listbox/option` |
| 步骤条 | `<ol aria-label="Progress">`，当前步 `aria-current="step"` |
| 分段控件 | `role=radiogroup` + `role=radio aria-checked` |

### 必须

- 纯图标按钮 `aria-label`；装饰图标 `aria-hidden`。
- 不用 `div onClick` 伪装按钮；可点击的东西就是 `<button>` 或 `<a href>`。
- 不使用仅 hover 可达的功能：Tooltip 可聚焦触发；行操作按钮常显（非 hover 才出现）。

## 6. 动效与偏好

- `prefers-reduced-motion: reduce` 时所有过渡/动画时长 → 0.01ms。
- `prefers-color-scheme` 作为"跟随系统"主题的来源，实时监听。
- `color-scheme` 跟随主题，原生控件与滚动条随之变化。

## 7. 文本与国际化

- 中英混排行高 ≥ 1.6；不使用 `letter-spacing` 压缩正文。
- 文本允许折行；不设置 `user-scalable=no`。
- 日期/数字使用 `tabular-nums`。

## 8. 验收方法

1. 拔掉鼠标走一遍主要流程：新增 DNS 记录 → 编辑 → 删除 → 撤销。
2. 浏览器缩放 200%：布局不破、无横向滚动。
3. 开启系统"减少动态效果"：侧边栏/浮层仍可用。
4. 使用 Lighthouse / axe 扫描：无 critical/serious 问题。
5. 屏幕阅读器（NVDA/VoiceOver）朗读表单：标签、错误、必填状态可被读出。
