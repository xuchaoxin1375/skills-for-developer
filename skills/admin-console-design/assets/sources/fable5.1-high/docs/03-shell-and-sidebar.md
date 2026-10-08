# 03 · 应用外壳与侧边栏

外壳（Shell）= 顶栏（TopBar）+ 侧边栏（Sidebar）+ 内容区（Main）+ 页脚。本篇重点规定侧边栏的状态机与交互细节，这是 Cloudflare Dashboard 体验最成熟的部分之一。

## 1. 结构尺寸

| 元素 | 尺寸 |
| --- | --- |
| 顶栏高度 | 56px，`position: sticky; top: 0`，z-index 50 |
| 侧边栏（展开） | 264px |
| 侧边栏（折叠 / Rail） | 56px，仅图标 |
| 导航行高 | 36px（一级）、32px（二级） |
| 图标尺寸 | 18px，置于 36×36 的方块中，**展开/折叠时图标 x 坐标不变** |
| 内容区 | `max-width: 1440px`，水平内边距 16 / 24 / 32 |

## 2. 顶栏

从左到右：

1. 移动端汉堡按钮（< 768px 显示）。
2. Logo（返回首页）。
3. 分隔线 + **资源切换器**：收藏星标、当前域名、套餐 Badge、上下箭头。点击弹出 Popover，内含搜索框与列表（`role=listbox`）。
4. 弹性空白。
5. 右侧：Ask AI、Support（< 1024px 隐藏文字按钮）、通知、主题菜单、头像菜单。

### 必须

- 顶栏首个可聚焦元素之前提供"Skip to main content"链接（仅聚焦时可见）。
- 资源名称在窄屏下 `truncate`，最大宽度 60vw，不得把右侧按钮挤出屏幕。

## 3. 侧边栏状态机

```
            toggle / "["                     hover ≥110ms 或 focus-within
  pinned  ◀──────────────▶  rail (collapsed)  ─────────────────────────▶  peek
                                   ▲                                       │
                                   └─────── mouseleave ≥220ms / Esc / blur ─┘

  < 768px:  hidden  ──hamburger──▶  drawer (modal)  ──backdrop / Esc / 导航──▶  hidden
```

| 状态 | 布局宽度（占位） | 视觉宽度 | 说明 |
| --- | --- | --- | --- |
| `pinned` | 264 | 264 | 桌面默认（≥1024）。持久化 `localStorage("cfui.sidebar.pinned")`。 |
| `rail` | 56 | 56 | 平板默认（768–1023）或用户折叠后。 |
| `peek` | **56** | 264 | 悬停/聚焦临时展开，**覆盖**内容区（`position: fixed` + `shadow-3` + z-40），**不推挤**内容。 |
| `drawer` | 0 | min(264, 85vw) | 移动端，模态，锁定 body 滚动。 |

### 必须

- **Peek 不得改变内容区布局**（内容不能因悬停而左右跳动）。实现：外层 `<aside>` 只按 `pinned` 决定占位宽度；内层面板 `fixed`，按 `expanded = pinned || hoverPeek || focusPeek` 决定视觉宽度。
- 进入延迟 ≥ 100ms（仅鼠标悬停，防止划过误触发）；离开延迟 ≥ 200ms（仅鼠标，允许短暂越界）。键盘聚焦立即展开，不经过悬停计时器；失焦立即收起焦点态，不取消悬停计时器。
- 键盘：`Tab` 进入折叠侧边栏时自动 `focusPeek`；焦点完全离开后收起焦点态；`Esc` 调用 `dismissPeek()` 收起，焦点保留在可见的稳定侧边栏控件上（一般为原焦点；若原焦点是收起后隐藏的子菜单项，则移到 Quick search 按钮），**不** `blur()` 到 BODY。`dismissPeek()` 仅在焦点实际留在面板内时置 `suppressFocus`（`document.activeElement.closest("[data-state]")`），此时后续 `focusIn`/Tab 不立即重开 peek，焦点完全离开面板后清除；hover-only peek（焦点在外，如 main）则不抑制，外部焦点保持不动，下一次键盘进入仍能正常打开 peek。鼠标悬停不受抑制，指针离开再进入即可重开 hover peek。
- 点击"折叠"按钮后，即使鼠标仍停留在侧边栏，也**不得**立刻重新 peek（需等鼠标离开一次再激活悬停）。实现见 `ShellContext.collapseNow()` 的 `suppressHover` 标志，仅阻塞悬停，不阻塞键盘 `focusPeek`。
- 悬停与聚焦独立：`hoverPeek`/`focusPeek` 分状态存放，`peek = hoverPeek || focusPeek`；`FocusOut` 只清焦点态，不再用 `:hover` 查询保活；悬停计时器卸载时清理，避免卸载后 `setState`。
- 只对 `width / box-shadow / opacity` 做过渡（280ms，ease-out）；文字标签使用 `opacity` 淡入且 **延迟 75ms**，避免宽度未到位时文字溢出闪烁。
- 内部内容固定为 264px 宽（`w-[var(--sidebar-expanded)]`），面板 `overflow: hidden` 裁切，外层工具区/导航/底部统一 `px-0`，`Row` 保持 `pl-[10px]`，这样 rail/peek 切换时主图标 x 保持 19px 不变。这样展开过程中文字不会重新折行。
- 手风琴展开会纵向推动后续条目，属预期行为：页稳定（`main` 不被 peek 推挤）与目标稳定（rail/peek 图标 x 不变）分开验收，不要求分组展开零位移。
- 折叠态下带子菜单的一级项：同一 `<button>` 节点贯穿 rail/peek（`as="button"` 不变，仅换 `onClick`/属性，原地更新不替换 DOM），语义保持按钮，避免 pointerdown→peek→pointerup 丢失点击。Rail 调整：分组 rail 由链接改为按钮（与 Recents 一致，Recents 同合同），点击直达首个子页面；展开态点击切换手风琴。另在按住主键期间延迟 hover/focus peek（`pressHold`）：按住期间不展开所以行不位移；松开时 focus 重开延迟到 click 之后（`focusRearmT` 零延迟计时，跑在 click 之后），hover 按正常 110ms 重开——这样 click 仍按按下时的 rail 语义（直达首个子页面）执行，不会被松开时的 peek 切换为手风琴。`focusRearmT` 有句柄跟踪：纳入共用的计时清理（`dismiss`/`collapse`/卸载时取消），新按压可取代旧的重开，回调先判 `panel.isConnected` 再看当前焦点，避免 stale 面板误触发。hover/focus 展开能力保留，不为规避问题而禁用。
- 当前路由所在分组自动展开，并以左侧 3px 品牌色竖条标记激活项。

### Rail（图标带）专项规则

| 规则 | 级别 | 实现 |
| --- | --- | --- |
| 图标在 56px 带内**水平居中** | 必须 | 行左内边距 10px + 36px 图标盒 → 图标中心 x = 28px = 56/2；展开后该坐标不变，只在右侧淡入文字 |
| 折叠态**不得露出任何文字 / 徽标 / 快捷键**（含半个字符） | 必须 | 标签 `opacity:0` **且** `visibility:hidden`；面板 `overflow:hidden`；内容容器固定 264px 不重排 |
| 隐藏文字不可被 Tab 聚焦、不被读屏朗读 | 必须 | `visibility:hidden` 天然满足；二级菜单容器额外 `aria-hidden` |
| 用户可**主动**控制固定/折叠，而非只靠自动判断 | 必须 | 底部"Collapse / Keep expanded"按钮（`aria-pressed`）+ 快捷键 `[`；状态持久化 |
| 展开动画只改 `width` 与 `box-shadow`，文字延迟 75ms 淡入 | 应该 | 避免宽度未到位时文字被裁切出现"跳字" |
| 折叠时文字立即隐藏（不等淡出） | 应该 | 收窄过程中不会出现被截断的半个单词 |

### 应该

- Rail 态下纯图标项提供 `aria-label`；不额外显示 Tooltip（悬停会展开，Tooltip 多余）；折叠按钮使用 `title` 提示快捷键。
- Peek 态下内容区透明度微降至 0.92，暗示其为临时覆盖层。
- 提供全局快捷键 `[` 切换固定/折叠。
- 导航区域独立滚动（`overflow-y: auto; overscroll-behavior: contain`），顶部工具（搜索、返回）与底部（设置、折叠）固定。

### 可以

- "Recents" 分组列出最近访问的页面，附两级面包屑。
- 一级项右侧显示 `New` / `Demo` 徽标。

### 避免

- 悬停展开时推挤内容（引发整页重排与 CLS）。
- 用 `display: none` 切换标签（无法过渡）；用 `visibility` + `opacity` 或裁切。
- 在触屏设备上依赖 hover：`(hover: none)` 时禁用 peek，改由折叠按钮或点击图标操作。

## 4. 移动端抽屉

- 触发：顶栏汉堡按钮；关闭：遮罩点击、`Esc`、路由变化、关闭按钮。
- 打开时锁定 `body` 滚动，焦点移入抽屉，`role=dialog aria-modal`。
- 宽度 `min(264px, 85vw)`，保证 320px 屏幕仍能看到遮罩区域。

## 5. 命令面板（Quick search）

- 触发：`Ctrl/⌘ + K`、侧边栏搜索按钮、顶栏 Ask AI。
- `role=combobox` + `aria-activedescendant`；↑↓ 导航，↵ 打开，Esc 关闭。
- 数据源：导航项 + 业务对象（示例中为 DNS 记录），按分组显示。
- 底部显示快捷键说明。

## 6. 内容区与页脚

- `<main id="main" tabindex="-1">`，供 Skip link 聚焦。
- 页脚链接水平排列可折行，窄屏居中。
- 页面骨架：`PageHeader(title, description, actions, meta)` → `Alert` → 内容。

## 7. 实现索引

| 文件 | 职责 |
| --- | --- |
| `src/components/shell/ShellContext.tsx` | 状态机、延迟计时、快捷键、持久化 |
| `src/components/shell/Sidebar.tsx` | `DesktopSidebar`（pinned/rail/peek）、`MobileDrawer`、`SidebarContent` |
| `src/components/shell/TopBar.tsx` | 顶栏、资源切换器、主题菜单 |
| `src/components/shell/CommandPalette.tsx` | 快速搜索 |
| `src/components/shell/AppShell.tsx` | 组合与页脚 |
