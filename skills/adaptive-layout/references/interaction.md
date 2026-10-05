# 渐进披露与交互状态

> 何时读：流程步骤 4。选中触发、悬停增强、键盘等价，一次做全，不留“只有鼠标能用”的路径。

## 选择与显示

- 卡片主体用语义 `<button>` 或 `<a>`，不用带点击的 `div`；不把交互控件嵌套进另一个按钮。
- 点击/触控主体切换选中：选中显示操作区，再点收起，点另一张切换上下文。
- 键盘：`Tab/Shift+Tab` 可预测到达，`Enter/Space` 切换或执行真实按钮行为；焦点进卡片或操作区要能识别操作且焦点可见。
- 悬停可提前展示，但不能是唯一入口；触控不要求长按模拟悬停。
- 浮层锚定所属卡片：实心背景、边界、对比度、合理层级；不遮唯一识别信息，不让相邻卡片混淆归属。
- 单选（当前操作上下文）与批量复选（加入对比/批量任务）用不同控件与状态，后者给数量、继续、清空。

## 图标按钮语义

```html
<button type="button" aria-label="重命名">
  <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><!-- 装饰图标 --></svg>
</button>
<button type="button" aria-label="移出对比" aria-pressed="true">
  <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><!-- 装饰图标 --></svg>
</button>
```

图标不参与名称，读的是 `aria-label`；切换态同步名称与 `aria-pressed`。不用 `title` 当唯一名称，不用 `div onClick` 伪装按钮。

## 菜单、弹窗与反馈

| 状态 | 期望行为 |
|---|---|
| 菜单打开 | 触发器 `aria-expanded`，菜单项完整标签，触控区按 44 基线 |
| 菜单关闭 | `Escape` 关，点外部关，关后焦点回触发器 |
| 弹窗打开 | 语义 dialog，标题明确，焦点进弹窗，关后回原触发位 |
| 表单错 | 文字解释、关联字段、聚焦首错、保留输入 |
| 成功/失败 | 可感知状态提示（`role=status/alert`），失败给原因与恢复路径，不用 `alert()`，不只变颜色闪一下 |

`Esc` 层级：先关最内层弹层，再清外层选中态。原生 `<dialog>` 验证关闭与焦点回归；自建 dialog 自担焦点管理与模态责任。

## 动效与偏好

- 过渡 ≤320ms（常用 120/200/320），只动 transform/opacity，缓动 `cubic-bezier(0.2,0,0,1)`。
- 跟随 `prefers-reduced-motion`；拿不准选型查 `web-animation-guide`，时长禁令以本 skill 为准。
