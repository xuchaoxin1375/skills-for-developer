# 外壳、侧栏与全局操作

默认对象为 fable 当前归档源码。本页是[功能目录](feature-catalog.md)的外壳部分；实现规则见[外壳与侧栏](shell-sidebar.md)，依赖取用见[模板单元](template-units.md)。下表“已实现”均指源码状态，运行证据另见[工程对照](builds-comparison.md#已执行抽查与已知缺口)。

视觉对照可看已归档的 [Rail](builds/shots/fable-rail-1440-2026-10-08.webp) 与 [peek](builds/shots/fable-peek-1440-2026-10-08.webp)；它们只证明相应视口和状态的外观。

## 源码定位

| 代号 | 入口 | 负责的功能 |
|---|---|---|
| S1 | [AppShell](../assets/sources/fable5.1-high/src/components/shell/AppShell.tsx) | 顶栏、侧栏槽、内容、全局浮层挂载 |
| S2 | [Sidebar](../assets/sources/fable5.1-high/src/components/shell/Sidebar.tsx) | 导航外观、分组、点击语义、Esc 回焦、移动抽屉 |
| S3 | [ShellContext](../assets/sources/fable5.1-high/src/components/shell/ShellContext.tsx) | pinned、hover/focus、按住点击、快捷键、移动/搜索开关 |
| S4 | [nav](../assets/sources/fable5.1-high/src/data/nav.ts) / [App](../assets/sources/fable5.1-high/src/App.tsx) | 导航配置、路由与占位页 |
| S5 | [TopBar](../assets/sources/fable5.1-high/src/components/shell/TopBar.tsx) | 当前域名、主题、账户、全局操作 |
| S6 | [CommandPalette](../assets/sources/fable5.1-high/src/components/shell/CommandPalette.tsx) | 快捷搜索及键盘导航 |
| S7 | [theme](../assets/sources/fable5.1-high/src/lib/theme.tsx) / [index.css](../assets/sources/fable5.1-high/src/index.css) | 深浅主题、颜色、密度与过渡 |

## 外壳与导航的设计

| 功能 | 设计细节 | 交互与结果 | 实现边界 / 入口 |
|---|---|---|---|
| 三个主要区域 | 顶部资源/全局操作；左侧导航；主内容保留独立页标题和操作区 | 路由切换更新文档标题并滚到顶部 | hash 路由演示；需对接目标路由，S1/S4 |
| 侧栏层级 | Quick search、Back to Domains；Overview/Recents/Guide/Lab；主要产品分组；底部 Settings/固定开关 | 当前页高亮，当前组自动打开；展开组的箭头旋转，子项缩进 | Recents 为静态条目，不是真实最近访问；S2/S4 |
| 图标与文本 | 主图标固定位置，Rail 隐藏标签、快捷键与多余说明；peek 显示完整标签 | 固定图标槽避免展开时整体横移；可 Tab 主入口，隐藏子链接 `tabIndex=-1` | 隐藏文本不能代替名称，源码用 aria-label；17 主图标位置有局部运行证据，S2/S7 |
| 占位槽与覆盖层 | expanded 占完整侧宽；Rail 占窄槽；peek 视觉变宽并有分隔/阴影 | 临时展开覆盖主内容，主内容位置和宽度不变 | 槽由 pinned/布局决定；不只复制 nav，还需 S1/S2/S3 |
| 参数与偏好 | fable 264/56、顶栏 56；宽度过渡 280ms；进入/离开 110/220ms | 固定偏好保存到 `cfui.sidebar.pinned`；未存时桌面默认展开、平板默认 Rail | 既有存储偏好可改变平板结果，不是“平板始终 Rail”；参数只描述此模板，S3/S7 |

## Rail、peek 与关闭的完整路径

| 触发 / 状态 | 源码行为 | 必须一起保留的细节 | 边界 / 入口 |
|---|---|---|---|
| 鼠标进入未固定 Rail | 可悬停设备等待 110ms 后 hoverPeek | 不推挤 main；取消旧进入/退出计时器 | hover 与 focus 独立，不共用一个 expanded 原始状态，S3 |
| 鼠标离开 | 延迟 220ms 清 hoverPeek | 若键盘焦点仍在侧栏，focusPeek 保持展开 | 鼠标离开不能藏住仍在操作的键盘焦点，S3 |
| 键盘进入 / 离开 | 进入设置 focusPeek；离开整个面板才清除 | 子项之间跳焦不关闭；Rail 主入口有名称和焦点样式 | 此实现以 focus 进入驱动，不是 sonnet 的 `:focus-visible` 模型，S2/S3 |
| Rail 上直接点击分组 | 立即导航该组第一个子页；同一 BUTTON 节点保留 | 点击发生时仍按 Rail 语义解释，不被临时展开改成折叠组 | 原生链接新标签能力需另行取舍，S2 |
| peek / expanded 点击分组 | 切换该组展开；键盘先进入 peek 后 Enter 同样切换 | 当前页标识、按钮 aria-expanded、子项显隐一起变化 | 与 sonnet Rail 点击“强制展开该组”不同，S2/S4 |
| 指针按住 Rail 项 | pointerdown 期间延后 hover/focus peek；释放后再启用 | 不让目标在 pointerdown/pointerup 之间移走；click 后才重新开启 focusPeek | 节点身份、click 语义和图标位置是不同检查；不能仅看截图，S2/S3 |
| 手动收起 | 清临时状态，抑制 hover 直到指针离开；固定开关更新偏好 | 按钮仍在指针下也不会立刻弹回；不封死后续键盘入口 | 抑制 hover 与抑制 focus 分开，S3 |
| Esc 关闭 peek | 清 peek；仍可见主入口保留焦点，隐藏子项回 Quick search | 焦点仍在面板时暂不因 focus 再开；彻底离开后键盘重入能展开 | hover-only Esc 且焦点在 main 时不能留下无法清除的抑制；已有局部测试，S2/S3 |
| `[` 快捷键 | 非输入/可编辑区域切换固定偏好 | 输入正文时不抢键；Ctrl/Meta/Alt 不误触 | 与点击收起的瞬态清理路径需在目标中核对，S3 |
| 路由 / 设备变化 | 导航关闭抽屉；非悬停设备导航清临时状态；离开移动断点关闭抽屉 | 固定偏好与临时状态区分 | 不是所有路由/断点变化都统一重置全部六态，S3 |

## 移动抽屉、顶栏与搜索

| 功能 | 设计 | 操作流程 | 边界 / 入口 |
|---|---|---|---|
| 移动导航 | hamburger 替代常驻侧栏；遮罩与左侧抽屉；完整标签、顶部关闭按钮 | 打开锁 body 滚动、焦点到关闭；Esc/遮罩/导航关闭 | MobileDrawer 未实现完整 Tab trap 和明确触发器回焦；复用需补，S2/S5 |
| 域名菜单 | 当前域名、星标、套餐徽章；Popover 中三个站点、计划/状态/当前勾选 | 点站点更新顶栏本地选择；星标局部切换 | 搜索框未绑定筛选；选择未联动 DNS 数据，DNS 使用常量 ZONE；free 徽章固定，S5 |
| 全局入口 | Ask AI、Support、通知圆点、主题图标、头像菜单；窄屏隐藏部分次要项 | Ask AI 打开命令面板；Support 进入文档；账户 Settings 跳路由 | 无 AI 服务、通知按钮无动作、Sign out 无认证动作；不能照搬成假功能，S5 |
| 主题 | light/dark/system 菜单及当前选中；语义色映射 | `cfui.theme` 存储；system 跟随 matchMedia 变化 | 原色对及 reduced-motion 有已知限制，见令牌/验证；S5/S7 |
| 跳过导航 | 顶栏有 skip link 指向 main | 键盘可跳过重复导航的意图 | `href="#main"` 与 hash 路由的实际兼容未在本目录验证，需测目标，S1/S5 |
| 打开命令面板 | 居中搜索框、分组结果、图标/副文案、底部按键提示；最大宽 640 | Quick search、Ask AI 或 Ctrl/⌘+K；打开重置搜索并聚焦输入、锁 body 滚动 | modal 外观不等于完整模态；未见完整 trap / 明确 opener 回焦，S3/S6 |
| 搜索结果 | 默认前 10；输入后最多 12；页面与 DNS 记录分组 | label/content 忽略大小写匹配；上下键有限边界、active 项滚入视野、鼠标变 active；Enter/点击跳转，DNS 带 `q` | 记录来自 INITIAL_RECORDS 快照，编辑后不会实时更新全局结果；S6 |
| 关闭面板 | Esc 或点遮罩 | 关闭搜索层，目标路由提供结果 | 背景隔离与关闭回焦需补测/补齐，S6 |

## 此单元的复用检查

对照固定展开、Rail、hover peek、keyboard peek、混合输入、按住再松手、手动收起、Esc 重入及移动抽屉；同条件检查 main 是否位移、图标位置、分组节点和 click 结果。侧栏只需实际导航配置，不要求保留无业务意义的产品占位页。

顶栏域名切换、全局搜索与账号动作要接真实资源/记录/认证；没有对应能力就明确适配，不能用 Toast 代替业务成功。弹层的焦点和滚动隔离按[响应式与验证](responsive-a11y.md)补齐；以上源码边界不是降低目标标准的豁免。
