# 控件、反馈与其他页面功能

本页记录 fable 的共享设计和其他页面，供[功能目录](feature-catalog.md)按需查阅。所有“保存/创建/检测”均需区分演示状态与真实业务；目标规则见[表单](forms.md)、[令牌](tokens.md)和[响应式与验证](responsive-a11y.md)。

## 源码定位

| 代号 | 入口 |
|---|---|
| P1 | [primitives](../assets/sources/fable5.1-high/src/components/ui/primitives.tsx) |
| P2 | [layout](../assets/sources/fable5.1-high/src/components/ui/layout.tsx) |
| P3 | [overlays](../assets/sources/fable5.1-high/src/components/ui/overlays.tsx) |
| P4 | [OverviewPage](../assets/sources/fable5.1-high/src/pages/OverviewPage.tsx) |
| P5 | [SettingsPage](../assets/sources/fable5.1-high/src/pages/SettingsPage.tsx) |
| P6 | [FormPatternsPage](../assets/sources/fable5.1-high/src/pages/forms/FormPatternsPage.tsx) |
| P7 | [DocsPage](../assets/sources/fable5.1-high/src/pages/DocsPage.tsx) |
| P8 | [ResponsiveLabPage](../assets/sources/fable5.1-high/src/pages/ResponsiveLabPage.tsx) |
| P9 | [index.css](../assets/sources/fable5.1-high/src/index.css) / [theme](../assets/sources/fable5.1-high/src/lib/theme.tsx) |

## 共享视觉和基础控件

| 功能 | 设计和交互 | 实现边界 / 入口 |
|---|---|---|
| 字体、层级、密度 | Inter 优先字体栈；正文与技术值分用 sans/mono；字号 11/12/13/14/16/20/28；圆角 4/6/8/12；页面/卡片/分隔层有语义映射 | 数字是原稿值；未证明 bundled 字体实际加载，缺字体会改变观感；原色对仍有缺口，P9 |
| 深浅主题 | light/dark 独立变量；system 跟随系统；颜色承担层级、品牌、动作、危险/成功含义 | 实际前景/背景须测，不能只看有 dark class；见令牌中修正起点，P9 |
| Button | primary/secondary/ghost/danger/danger-outline/link；32/36/44 三档；图标与文本一致间距 | loading spinner + aria-busy 并禁用；目标的按钮禁用语义和权限需接线，P1 |
| Badge / Toggle / Checkbox | 状态有文字及语义色；切换控件有当前态；选择支持部分态 | 组件外观不替代可访问名称及业务状态，P1 |
| Field | 可见 label、必填/optional、labelAside 计数、帮助或错误；错误文字与图标 | Input/Select/Textarea 按 id 推导描述 ID，但元素未必存在，关联需核对，P1 |
| 输入框 | 默认高 36，等宽选项、前后图标、禁用态、focus ring；TXT 等长文本用 textarea | 保留控件边框/密度/焦点视觉；原输入边框对比需修，P1/P9 |
| 页面区块 | PageHeader、Card、Alert、EmptyState、InfoTip、CollapsibleCard | 标题和状态概括在折叠后仍可见；错误/空态不能只复制静态文字，P2 |

## 浮层与反馈

| 功能 | 设计 | 触发、关闭和焦点 | 源码边界 / 入口 |
|---|---|---|---|
| Popover | portal、锚点下方 6px、左右至少 8px、宽不超 viewport−16、最大高度 | resize/scroll 重定位；点击外部关闭；Esc 回锚点；尝试自动聚焦首输入 | 首次 focus effect 可能先于 portal 挂载；定位未说明完整翻转避让，需验证，P3 |
| Menu | Popover 内 role=menu，选中/禁用态与分组 | 箭头循环 enabled items，Home/End；选择调用回调并关闭 | 没回调的菜单项不因此有业务功能，P3 |
| Dialog | 桌面居中，手机 bottom sheet；sm/md/lg 420/560/760；最高 92vh | portal、锁 body、捕获/恢复焦点、Tab 端点循环、Esc/遮罩关闭 | 无 background inert；嵌套浮层/滚动锁非统一管理。单个 querySelector 中 data-autofocus 并非优先级保证；危险动作初始焦点需修，P3 |
| Dialog footer | 宽屏右对齐，窄屏堆叠动作 | 同一操作的窄屏入口 | flex-col-reverse 的视觉/Tab 顺序问题需修，P3 |
| Toast | 桌面右下最大宽 380，手机左右留 16；图标、标题、描述、可选 Undo、关闭；最多显示 4 条 | error 为 alert、其他 status；error 8s、其他 5s | 无 hover 暂停/完整卸载计时器清理；Undo 必须真实恢复，P3 |
| reduced-motion | CSS 过渡时长降级 | 不应妨碍操作完成 | JS smooth scroll/自动宽度扫动并不会自动受 CSS 规则限制，P7/P8/P9 |

## 概览与设置

| 页面功能 | 设计与操作 | 实际结果及边界 / 入口 |
|---|---|---|
| Nameserver setup | 主要设置卡、两个 NS 值和复制按钮、检查/注册商说明入口 | copy 未 await optional clipboard，仍总报成功；Check 只有 Toast，注册商按钮无处理；目标需真实读写/检测，P4 |
| Checklist / Traffic / Quick actions | 完成/待办清单，四个静态统计和四个快捷操作；主次分区 | 部分链接可导航；数据静态，Analytics 按钮无动作；不是监控系统，P4 |
| TLS / CNAME flattening | 每个卡片说明、选项与自己的保存区，dirty/saved 文案 | React state；无变化禁用 Save，保存更新本卡基线；不持久化/无 API，P5 |
| DNSSEC / Email obfuscation | 状态文字、开关与帮助，区别于分区 Save | DNSSEC 即时切换加 Toast；Email 为本地切换；不是真实安全配置，P5 |
| Danger zone | 页末危险卡；Pause/Remove 有后果说明和独立确认 | Pause→Toast 的 Resume 再给 Toast；无持久暂停；Remove 要精确输入 ZONE，完成提示明确 mock；不实际移除资源，P5 |
| 未实现的产品页 | 复用页头与 PlaceholderPage 说明 | DNS Analytics 和多数产品分组仅占位；不能从导航存在推断功能完备，见 App 路由，P4/P5 |

## 长表单与向导

| 功能 | 设计与流程 | 实现边界 / 入口 |
|---|---|---|
| Create 分区 | Basics → Origin → Performance → Security，再 Review；名称/域名、环境选择卡、tags、Origin 类型卡/条件字段、端口、TLS/cache/rate limit/WAF/bot fight/notes/同意 | 原说明“14 fields/4 sections”不宜当硬计数；按条件实际显隐，P6 |
| Tags / Notes | tags Enter/逗号/blur 加入、小写去重、最多 8；空输入 Backspace 删除末项；notes 500 字计数 | 输入机制与限制一同迁移，不只抄输入框样式，P6 |
| 右侧目录 | lg 右侧 240px sticky outline；分区错误徽章；IntersectionObserver 标当前节；点目录滚到分区 | sticky 容器和标题偏移一起移植；JS smooth scroll 需尊重 reduced-motion，P6 |
| 校验和 Review | blur touched、提交摘要、点击错误定位；最终确认信息与同意项 | IPv4 正则只匹配形状，未检查 octet 范围；首次错误聚焦同步时机需核对，P6 |
| 未保存条与创建 | 窄屏底部 sticky dirty bar；模拟 600ms 创建成功后清表单、滚顶部 | 无草稿持久化/beforeunload/站内 guard；clean 时 aria-hidden/移出视觉仍有可聚焦控件，需修；成功非真实创建，P6 |
| 三步向导 | Domain → Plan → Confirm；序号/连线/完成勾选；窄屏隐藏步骤文字；当前步可操作、未来步禁用、可回以前步骤；Back 保留域名/计划，换步 rAF 聚焦标题 | 最终摘要、说明和确认；无 API/忙碌/失败态；演示价非真实报价，P6 |
| 向导结束 | Add 提示成功并回起点；step/domain/touched 重置，plan 保留 | 不能宣称全部清空或草稿存储；资源未真实创建，P6 |

## 文档与开发预览工具

| 工具 | 设计与交互 | 使用边界 / 入口 |
|---|---|---|
| Design Guide | 内置 Markdown/GFM，文章卡片、文档名、前后篇；xl 右侧 240px 目录，窄屏顶端可折叠目录 | h2/h3 slug、滚动高亮、点击 smooth scroll；未知 slug 回首篇。原文属于来源，不能把旧自述验收当证据，P7 |
| Responsive Lab | 五条路由预览；single 或 390/768/1440 triple；宽度 280–1600 步长 1，320/390/768/1024/1440 预设；高度 560/720/900 | 真实 iframe CSS 宽度，transform 仅缩放显示；主题同步、hash 导航；`frame` 避免递归 Lab 入口，P8 |
| 自动扫宽与 dock | 260px/s 往返、速度 .5/1/2；Space 非输入区启停；宽屏可选 sticky dock | 注释说预设会暂停，但未见对应暂停逻辑；不能当自动验收或生产控制台功能；原稿 stored pinned 可覆盖“tablet Rail”标注，P8 |

共享控件应随所选单元按实际 import 取依赖；开发舞台和文档不必搬到生产。通用控件可靠性、真实资源设置与未保存保护是接线时的工作，不能从一套精致外观推断已经完成。
