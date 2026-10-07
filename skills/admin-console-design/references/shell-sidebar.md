# 外壳与侧边栏

三工程一致结论：槽（占位）与视觉（浮层）解耦 + 覆盖不推挤 + 悬/焦两路 peek。

## 骨架

```
AppShell: min-h flex-col > TopBar(sticky h56 z50) + div flex-1 > [DesktopSidebar(slot) + MobileDrawer + div flex-1 min-w-0 > main(max1440 px4/6/8 py5/8) + footer] + CommandPalette
```

- 文档级滚动，不要整页 `height:100vh + 内滚` 锁死（锚点/回顶/读屏都依赖原生滚动）。
- `main` 必须 `flex-1 min-w-0`，长域名/URL 才能收缩；`peek` 时 main 可 `opacity:.92` 暗示浮层。
- `wide` 演示页允许 `max-w-none`，其余页一律 max1440 居中。

## 尺寸（收敛值）

- 展开 240（fable 264 / sonnet 240 / gpt 224，收敛 240，定死一个不再改）。
- Rail 56：图标盒 40 用 8+40+8，图标盒 36 用 10+36+10；图标 18 居中，中心 x=28=56/2，展开/折叠 x 不变。
- 顶栏 56，行高 36/子项 32，内容 max1440，表单卡 720/向导 768/设置 896。

## 状态机公式

```
pinned: expanded | collapsed（localStorage，如 cfui.sidebar.pinned，失败静默降级）
rail = medium(768-1023) || (wide>=1024 && collapsed)
peek = rail && ((!suppressed && (hover || kbFocus)) || forced)
expanded = wide ? (pinned==expanded || peek) : medium ? peek : false
slotWidth = wide ? (expanded?240:56) : medium ? 56 : 0
overlay = expanded && slotWidth<240 → fixed + shadow-2 + z40（fable 套：侧栏 top:56 起不与顶栏重叠，40<顶栏50 无妨；
          sonnet 通高侧栏才需槽40>顶栏20。按 tokens.md 所选层级套定死，内容永不重排）
drawer = narrow(<768) → 原生 dialog + 焦点陷阱 + Esc + 点外关，宽 min(288,100vw-48)（收敛值；fable 旧 264 / gpt 280~300 不用）
```

- `hover` 只在 rail 记，`pointerenter/leave` 忽略 touch（`pointerType==touch` 直接走 forced）。
- `suppressed`：点收起按钮后置位，直到指针离开一次才清，防“刚收起又因 hover 立即重开”。
- 键盘：`:focus-visible` 进入侧栏视同 hover（peek），鼠标点击的焦点不触发（防抖）。
  Tab 进 peek，Esc 收 peek 并回触发器；`[` 切换 pinned，Ctrl+K 开命令面板。
- 触屏：点图标 `forced=true`，点外/Esc/导航后关闭。
- 时序：进/出意图延迟 120/220ms（fable 110/220、sonnet 120/250、gpt 120/240，收敛 120/220），
  宽度过渡时长另算（280/220/220，收敛 240ms）；只动 width/box-shadow/opacity；
  文字 `opacity+visibility + 展开延迟50–75ms/折叠立即`，不用 display:none（读屏仍可读），不用 height:auto/left/top。
- 延时验收可调：默认 120/220；演示/验收页可做 120/250/400 三档（默认 120，抄 gpt Workbench），关闭悬停不影响固定与键盘。
- 子菜单：`grid-template-rows:0fr→1fr + visibility`，无需测高；折叠时 `visibility:hidden` 移出 Tab。
- 持久化 pinned；`prefers-reduced-motion` 归零；`overscroll-behavior:contain` 防穿透；折叠藏滚动条（`scrollbar-width:none`）。

## 像素级坑（sonnet/fable 实证）

- 分隔线用 `::after` 不占盒模型，否则 56px 偏 0.5px。
- Rail 内边距只算一次：内容固定宽（如 264）+ 面板 `overflow:hidden` 裁切时，外层 `px-2` 会与行 `pl-10` 叠加
  （8+10+18=中心36≠28，图标偏右 8px，左空18右剩2；fable 2026-10-07 实证）。
  必须 `expanded ? px-2 : px-0`，分隔线同步 `expanded ? mx-4/mx-2 : mx-[16px]`（24宽居中）；active 竖条同理回贴左边缘 0。
- 图标盒恒定 28–40 居中，文字 `flex:1 min-w-0 overflow:hidden nowrap`，折叠只 fade 不改布局。
- Rail 零文字泄露 + 不可聚焦（tabindex 移除），`aria-current=page` 加深+600，active 左 3px brand 条。
- 分组 `<button aria-expanded/controls>`，折叠点先展栏再展组；默认只展含当前页组，路由变自动展。
- 命令面板开时侧栏收起逻辑正常；`canHover=(hover:hover) and (pointer:fine)` 门控。

## 覆盖展开零位移（2026-10 实证，不遵守则点击被吞）

为什么：hover-peek 在 mousedown 与 mouseup 之间把面板变 fixed，若行高/图标 x 变了，
目标就从鼠标下跑掉（实证：点击落到 DIV.spacer 上，弹窗打不开）。覆盖必须几何全等：

- 图标列 x 与行高在 Rail/展开两态恒定：叶子固定 `min-height`（如 52px），分组缩进只作用于文字列
  （图标 padding 两态同值），Rail 只做裁剪（`overflow:hidden`）不改 `padding/justify/flex-direction`；
  注意选择器优先级：`.sidenav button(0,1,1)` 会吃掉单类名的 `min-height`，行高规则至少 `(0,2,0)`。
- 侧栏内所有文本单行：Rail 窄宽下换行会造成两态行高差（实证：空提示换行差 99px），
  用 `nowrap+overflow:hidden` 消灭；该规则同样适用于脚注与次要说明。
- 脱离网格要锁列：aside 变 fixed（peek/抽屉）后脱离网格，`page` 必须显式 `grid-column:2`
  （移动单列改回 1），否则内容掉进第一轨（实证：内容左移到 15px、宽被压到 52px）。
- 收起键在 Rail 下保持可见可用：它是唯一的鼠标展开入口，藏掉会同时断掉用户与门禁复位点击；
  Rail 行保持同布局，两个图标并排裁剪即可。
- fixed 定位用悬停时刻捕获的 rect（top/left/height），滚动/resize/Esc 关；手动收起后 suppressed
  到指针离开一次；验证探针：peek 前后逐行 `offsetTop` 全等 + 内容 `left` 不变 + 点击落点仍是按钮。
- 显形规则要高于隐藏规则：收起后悬停无字，就是显字与藏字优先级打平（同为 0,3,0），先写的输了。修法是显形多加一层（如 `.shell .sidenav[data-peek="open"] .lbl` 提到 0,4,0）——只打平不够。隐藏若按宽度分两套，768 过不代表 1440 过，要逐套测；复现按用户原话路径走。

## 命令面板（fable `docs/03` §5）

- 触发：`Ctrl/⌘+K` 全局、侧栏搜索按钮、顶栏 Ask AI；开启时侧栏收起逻辑保持正常。
- 语义：`role=combobox` + `aria-activedescendant`；↑↓ 导航、↵ 打开、Esc 关闭，滚动态保持可见项在视口内。
- 数据源：导航项 + 业务对象（示例为 DNS 记录），**按分组显示**；底部显示快捷键说明。

## 顶栏

`sticky h56 bg-surface border-b z50 px2/3`：左汉堡（仅 narrow）+ Logo（橙云自绘，非 CF 标）+ 收藏星 +
资源切换器（Popover listbox，`max-60vw truncate + free Badge`）+ 右 `ml-auto` AskAI/Support（<1024/480 渐隐文字）+ 通知 dot + ThemeMenu（三态 system/light/dark）+ AccountMenu。
极窄隐藏次要入口，永不藏主操作；面包屑 narrow 藏转 mobile-top-brand。
