# 外壳与侧边栏

默认采用 fable 的顶栏、搜索/返回、导航分组、底部控制与页面节奏。当前归档已分离hoverPeek/focusPeek，修复主图标横移、Esc焦点丢失与分组节点替换，并保护按住指针时的目标和点击语义；其实现仍不等同于下述完整模型。需要完整输入策略或临时展开时参考 sonnet，继续核对[已知缺口与验证范围](builds-comparison.md)。

## 结构与参数

`Topbar + SidebarSlot(占位) + SidebarPanel(视觉) + main(min-width:0) + 可选footer`。

文档滚动为默认，导航内部可滚动；工作台允许固定高度，但明确滚动所有者。fable 原值为展开264/Rail56/顶栏56/max1440；sonnet 展开240。沿用基底，按文本和挂载容器调整，不强制收敛。

Rail 图标居中与展开后位置稳定是两项检查。把内边距、边框、图标盒全部计入坐标；临时展开不要再次横移可点击图标。顶栏保留当前资源上下文与全局入口；资源切换器仅多资源业务需要时加入。

## 状态模型（参考 sonnet，参数用所选模板）

```text
pinned: expanded | collapsed                // 固定偏好，可持久化
hover, kbFocus, forced, suppressed: boolean // 临时状态
layout: wide | medium | narrow
rail        = medium || (wide && pinned == collapsed)
peek        = rail && ((!suppressed && (hover || kbFocus)) || forced)
visualOpen  = wide ? (pinned == expanded || peek) : medium ? peek : false
slotWidth   = wide ? (pinned == expanded ? expandedWidth : railWidth)
            : medium ? railWidth : 0
visualWidth = visualOpen ? expandedWidth : railWidth
overlay     = visualOpen && slotWidth < expandedWidth
drawer      = narrow && drawerOpen
```

**槽宽不使用 visualOpen 或 peek**。固定切换可以改变槽宽，临时展开不可以。模型不要求同名变量或强换状态库。

- 意图延迟与宽度过渡分别配置：fable 进/出110/220ms、宽度280ms；sonnet120/250ms、宽度220ms。
- 进入/离开清相反计时器；卸载、路由/布局切换和手动控制清过期事件。
- 点收起且指针仍在导航时抑制 hover，离开一次恢复；键盘收起且指针在外不能留下永久抑制。
- 键盘进入可展开；焦点仍在导航时不能因鼠标离开藏起。鼠标点击收起按钮的焦点不能反向重开。Esc 回到稳定入口，避免直接 blur 丢失焦点。
- 触屏不能依赖 hover：中等布局有临时展开按钮，外部点击/Esc/导航后关；窄屏有汉堡与抽屉关闭入口。
- 默认可用768/1024两个断点；fable 平板行为受存储偏好影响，不是已实现的强制Rail。CSS、JS、测试采用同单位/边界，检查767/768和1023/1024，无需特殊小数rem。

## 标签、分组与可访问名称

- Rail 主入口保留 Tab 和名称，可用 aria-label 或视觉隐藏标签。opacity:0 通常仍在可访问树；visibility:hidden/display:none 会隐藏名称来源，需补独立名称。不能声称“在DOM中就仍可读”。
- 收起子项移出Tab，可用hidden/inert/visibility/tabIndex=-1；不要出现不可见焦点。隐藏方式按动画需要选，不全面禁display:none。
- 链接用aria-current=page，分组按钮用aria-expanded/controls；避免Rail是链接、peek突然变按钮而打断点击。当前fable分组统一为按钮：Rail点击首个子页、展开态切换手风琴，失去链接的新标签页能力；需要原生链接时分开导航与展开动作，或采用一致的分组展开契约。
- 默认展开当前路径组；子菜单展开会移动后续行，不能把所有offsetTop全等当普遍要求。

## 覆盖与点击稳定

分别检查 **页面稳定**（main left/width不变）和 **目标稳定**（mousedown与mouseup仍是同一按钮/链接）。只验第一层不能声称全部零位移。

- 固定图标列、单行导航标签、只扩文本区；长说明可折行，但不要在一次指针动作中改变点击位置或重挂载目标。fable在按住主键时延后peek，松开后先完成click再恢复展开；同时验证动作结果（如实际路由），不能只记录click事件。
- 面板脱离Grid/Flex流，槽仍占原轨；需要时指定main轨道。grid-column:2仅适用于对应两列结构。
- 定位可相对稳定祖先，必要时读取rect；不是所有peek都必须fixed、捕获rect或滚动即关闭。
- 用computed style检查显隐优先级，避免堆选择器。层级看实际stacking context和侧栏起点；原生模态dialog在top layer。

## 抽屉、命令面板与验证

抽屉采用已有可靠组件或原生dialog.showModal，处理名称、首焦、Esc、遮罩策略、滚动锁和回焦；原生能力不替代未保存保护。

命令面板为可选效率入口。采用时支持Ctrl/⌘+K、↑↓、Enter、Esc、可见活动项和可访问名称；输入中快捷键不误触。combobox/listbox语义须有匹配键盘行为。

验证记布局、存储偏好和输入方式。覆盖折叠→进入→离开、快速划过、手动收起后仍悬停、键盘进入/Esc、触屏显式展开、窄屏抽屉，范围只限本次采用的能力。
