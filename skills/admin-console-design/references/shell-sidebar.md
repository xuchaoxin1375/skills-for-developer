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
overlay = expanded && slotWidth<240 → fixed + shadow-2 + z40(盖过顶栏z50? 按工程取槽40>顶栏20或40>50，定死槽40盖顶栏，内容不重排)
drawer = narrow(<768) → 原生 dialog + 焦点陷阱 + Esc + 点外关
```

- `hover` 只在 rail 记，`pointerenter/leave` 忽略 touch（`pointerType==touch` 直接走 forced）。
- `suppressed`：点收起按钮后置位，直到指针离开一次才清，防“刚收起又因 hover 立即重开”。
- 键盘：`:focus-visible` 进入侧栏视同 hover（peek），鼠标点击的焦点不触发（防抖）。
  Tab 进 peek，Esc 收 peek 并回触发器；`[` 切换 pinned，Ctrl+K 开命令面板。
- 触屏：点图标 `forced=true`，点外/Esc/导航后关闭。
- 时序：进 120ms 出 220–250ms，只动 width/box-shadow/opacity；文字 `opacity+visibility + 展开延迟50–75ms/折叠立即`，
  不用 display:none（读屏仍可读），不用 height:auto/left/top。
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

## 顶栏

`sticky h56 bg-surface border-b z50 px2/3`：左汉堡（仅 narrow）+ Logo（橙云自绘，非 CF 标）+ 收藏星 +
资源切换器（Popover listbox，`max-60vw truncate + free Badge`）+ 右 `ml-auto` AskAI/Support（<1024/480 渐隐文字）+ 通知 dot + ThemeMenu（三态 system/light/dark）+ AccountMenu。
极窄隐藏次要入口，永不藏主操作；面包屑 narrow 藏转 mobile-top-brand。
