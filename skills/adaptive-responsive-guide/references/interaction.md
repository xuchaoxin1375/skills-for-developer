## 渐进披露与交互状态

> 何时读：流程步骤 4。选中触发、悬停增强、键盘等价，一次做全，不留“只有鼠标能用”的路径。

通用语义、键盘和焦点基线见[通用无障碍](../../frontend-design/references/a11y.md)，表单与反馈见[通用交互](../../frontend-design/references/interaction.md)。下面维护收纳、定位与跨宽度状态；示例的图标或角色只为说明语义，不另设产品视觉规范。独立使用时保留原生按钮、可访问名、键盘等价与焦点回归底线。

### 选择与显示

- 可交互主体（卡片/列表项/表格行/工具栏项均同理）用语义 `<button>` 或 `<a>`，不用带点击的 `div`；不把交互控件嵌套进另一个按钮。
- 点击/触控主体切换选中：选中显示操作区，再点收起，点另一项切换上下文。
- 键盘：`Tab/Shift+Tab` 可预测到达，`Enter/Space` 切换或执行真实按钮行为；焦点进主体或操作区要能识别操作且焦点可见。
- 悬停可提前展示，但不能是唯一入口；触控不要求长按模拟悬停。
- 浮层锚定所属实例：实心背景、边界、对比度、合理层级；不遮唯一识别信息，不让相邻项混淆归属。
- 单选（当前操作上下文）与批量复选（加入对比/批量任务）用不同控件与状态，后者给数量、继续、清空。

### 图标按钮语义

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

### 菜单、弹窗与反馈

| 状态 | 期望行为 |
|---|---|
| 菜单打开 | 触发器 `aria-expanded`，菜单项完整标签，触控区按 44 基线 |
| 菜单关闭 | `Escape` 关，点外部关，关后焦点回触发器 |
| 弹窗打开 | 语义 dialog，标题明确，焦点进弹窗，关后回原触发位 |
| 表单错 | 文字解释、关联字段、聚焦首错、保留输入 |
| 成功/失败 | 可感知状态提示（`role=status/alert`），失败给原因与恢复路径，不用 `alert()`，不只变颜色闪一下 |

`Esc` 层级：先关最内层弹层，再清外层选中态。原生 `<dialog>` 验证关闭与焦点回归；自建 dialog 自担焦点管理与模态责任。

- 菜单视口放置：开前量触发器上下可用空间，下方不够则上翻并封顶滚动，滚动/缩放跟随重放；裁剪祖先内的触发器同样处理。例：末排长菜单上翻显示，不伸出视口。

### 菜单形态与闭环（demo1 的 bottom-sheet 示例）

- 形态按 `page-patterns.md`“滚动归属与浮层形态”选择；demo1 `.sheet-mask` 的底部动作面板与 demo2/3 `.dropdown-menu` 的锚定下拉是示例，尺寸换成项目令牌。切换形态时菜单项顺序、名称、行为一致，触控目标与安全区仍达标。
- 闭环一次做全（demo1 参考实现）：`lastTrigger` 记录触发器，关后 `focus()` 回去；`Esc` 按面板 → 预览弹窗 → 重命名弹窗逐层关；
  点遮罩/点外部关；成功/失败走 `role=status` toast（2200ms 自动收）；重命名空值不关弹窗、聚焦输入框、保留原值。
- 触发/关闭矩阵（选中浮层适用）：触屏点按卡片空白处或“显示操作”按钮展开，再点/点外部/`Esc` 收起；
  鼠标悬停或焦点进入只做临时显示、可移入浮层不消失，点击才固定；键盘 `Tab` 进卡片、`Enter/Space` 激活或固定，`Esc` 关闭不困焦点。
- 悬停临时展开（peek）四道闸 + 两条纪律，缺一条就会在触屏/动画态下乱跳：
  ① `matchMedia('(hover:hover)')` 不匹配直接不启用；② `prefers-reduced-motion: reduce` 下不启用；
  ③ 进出各带延迟（进 ~280ms、出 ~180ms）并互相 `clearTimeout`；④ 已钉住/已展开时不抢。
  纪律一：**临时态（peek）绝不写回记忆状态**（`localStorage`/组件值只记用户点按的收起或钉住）；
  纪律二：常驻入口（展开键）始终可见，触屏/键盘没有 hover，不能只靠悬停展开。

### 动效与偏好

时长与缓动读取项目令牌；反馈目的、工具界面默认预算与中间帧稳定性见[动效设计](../../frontend-design/references/motion.md)。实现、性能与减弱处理见 `web-animation-guide` 的 [selection.md](../../web-animation-guide/references/selection.md) 与 [performance-a11y.md](../../web-animation-guide/references/performance-a11y.md)，退出所需布局见 [interactions.md](../../web-animation-guide/references/interactions.md)。本 skill 不维护属性禁令或另一套时长。

侧栏折叠确需推动主内容时，按实测选布局过渡、FLIP 或瞬时重排；`transform` 不能自动替代布局变化。若重绘成本实测来自滤镜或阴影，可缩小范围或临时降级，但不能因此制造闪暗；收尾覆盖完成、取消和无动画路径。跨断点或 reduced-motion 变化后，最后状态、焦点与退出布局仍正确。
