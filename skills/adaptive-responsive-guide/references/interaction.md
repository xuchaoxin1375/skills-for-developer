# 渐进披露与交互状态

> 何时读：流程步骤 4。选中触发、悬停增强、键盘等价，一次做全，不留“只有鼠标能用”的路径。

## 选择与显示

- 可交互主体（卡片/列表项/表格行/工具栏项均同理）用语义 `<button>` 或 `<a>`，不用带点击的 `div`；不把交互控件嵌套进另一个按钮。
- 点击/触控主体切换选中：选中显示操作区，再点收起，点另一项切换上下文。
- 键盘：`Tab/Shift+Tab` 可预测到达，`Enter/Space` 切换或执行真实按钮行为；焦点进主体或操作区要能识别操作且焦点可见。
- 悬停可提前展示，但不能是唯一入口；触控不要求长按模拟悬停。
- 浮层锚定所属实例：实心背景、边界、对比度、合理层级；不遮唯一识别信息，不让相邻项混淆归属。
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

- 双态图标（展开↔收起、汉堡↔关闭）**两份都预渲染，用属性切换**，click 里不碰 `innerHTML`
  （会摘掉事件 target，栏外关闭逻辑跟着错）：

```css
#railCollapse .rc-close { display: inline-flex; }
#railCollapse .rc-open { display: none; }
#railCollapse[data-ic="open"] .rc-open { display: inline-flex; }
#railCollapse[data-ic="open"] .rc-close { display: none; }
```

## 菜单、弹窗与反馈

| 状态 | 期望行为 |
|---|---|
| 菜单打开 | 触发器 `aria-expanded`，菜单项完整标签，触控区按 44 基线 |
| 菜单关闭 | `Escape` 关，点外部关，关后焦点回触发器 |
| 弹窗打开 | 语义 dialog，标题明确，焦点进弹窗，关后回原触发位 |
| 表单错 | 文字解释、关联字段、聚焦首错、保留输入 |
| 成功/失败 | 可感知状态提示（`role=status/alert`），失败给原因与恢复路径，不用 `alert()`，不只变颜色闪一下 |

`Esc` 层级：先关最内层弹层，再清外层选中态。原生 `<dialog>` 验证关闭与焦点回归；自建 dialog 自担焦点管理与模态责任。

## 菜单形态与闭环（demo1 做法，触屏优先 bottom-sheet）

- 形态：触屏窄宽用底部动作面板（整屏宽、行高 ≥50px、带把手与 `safe-area`，demo1 `.sheet-mask`）；
  指针宽屏用锚定下拉（`bottom: calc(100% + 8px)`，demo2/3 `.dropdown-menu`）。两者菜单项顺序、名称、行为一致，只是呈现位置不同。
- 闭环一次做全（demo1 参考实现）：`lastTrigger` 记录触发器，关后 `focus()` 回去；`Esc` 按面板 → 预览弹窗 → 重命名弹窗逐层关；
  点遮罩/点外部关；成功/失败走 `role=status` toast（2200ms 自动收）；重命名空值不关弹窗、聚焦输入框、保留原值。
- 触发/关闭矩阵（选中浮层适用）：触屏点按卡片空白处或“显示操作”按钮展开，再点/点外部/`Esc` 收起；
  鼠标悬停或焦点进入只做临时显示、可移入浮层不消失，点击才固定；键盘 `Tab` 进卡片、`Enter/Space` 激活或固定，`Esc` 关闭不困焦点。
- 悬停临时展开（peek）四道闸 + 两条纪律，缺一条就会在触屏/动画态下乱跳：
  ① `matchMedia('(hover:hover)')` 不匹配直接不启用；② `prefers-reduced-motion: reduce` 下不启用；
  ③ 进出各带延迟（进 ~280ms、出 ~180ms）并互相 `clearTimeout`；④ 已钉住/已展开时不抢。
  纪律一：**临时态（peek）绝不写回记忆状态**（`localStorage`/组件值只记用户点按的收起或钉住）；
  纪律二：常驻入口（展开键）始终可见，触屏/键盘没有 hover，不能只靠悬停展开。

## 动效与偏好

- 过渡 ≤320ms（常用 120/200/320），只动 transform/opacity，缓动 `cubic-bezier(0.2,0,0,1)`；能用 `transform` 折叠就不动 `width/grid`（布局过渡触发重排）。
- 侧栏/面板折叠确实要改布局（`width`/`padding-left`/`grid-template-columns`）时，**动画期临时关掉重绘源**：加个一次性类
  （如 `body.rail-anim`，`transitionend` 或定时移除），把 `backdrop-filter`、大 `box-shadow` 置 `none`——
  它们每帧全屏重绘，是折叠动画掉帧的头号原因，过渡结束立即恢复。
- 跟随 `prefers-reduced-motion`；拿不准选型查 `web-animation-guide`，时长禁令以本 skill 为准。
