# Vue 3 外壳候选参考

这是 2026-11-23 从内部 Vue 3 批次工作台移植出的**同栈候选参考**，用于 Vue 3 项目复用 Cloudflare-inspired 的后台外壳布局与交互。它不是第四套主模板，不是 Cloudflare 官方组件或还原稿，也不包含 Cloudflare 的商标、Logo 或配色要求。

## 定位与边界

- **只参考布局与交互**：顶栏 56px、侧栏展开 264px / Rail 56px、分组导航、Rail 悬停／键盘 peek、移动抽屉、焦点与滚动规则。
- **配色不绑定 Cloudflare**：`style.css` 使用宿主项目的深青／中性令牌作为示例；迁移时替换为宿主设计令牌，不要把这里的颜色当作 Cloudflare 还原标准。
- **技术栈**：Vue 3 + TypeScript + Vite + Vue Router（宿主使用 hash 路由）。`App.vue` 默认请求 `/api/health`，宿主可替换为自己的状态客户端。
- **不包含**：命令面板、账号菜单、主题切换、通知中心、资源／域名切换器、DNS 列表和表单；参考稿里的这些能力不应在没有业务接线时补成假入口。
- **不是可独立运行工程**：没有 `package.json`、路由入口和内容页；文件用于复制、适配和对照，不替代宿主的信息架构与验收。

## 文件

| 文件 | 作用 |
| --- | --- |
| `App.vue` | 外壳状态机：pinned/peek/drawer、计时器、Esc、焦点回收、顶栏面包屑、服务状态、响应式布局 |
| `components/SidebarNav.vue` | 分组导航、当前项、橙色／品牌色指示条、收起态标签处理、底部折叠按钮 |
| `components/Icon.vue` | 外壳使用的内联 SVG 图标，避免额外图标依赖 |
| `style.css` | 宿主完整样式表；外壳、侧栏、顶栏、抽屉和响应式规则是可复用部分，卡片／表格／表单是批次工作台的内容示例 |
| `verification.json` | 1280／1440／768／390 的实测布局与交互记录 |

## 交互契约

- **固定展开/收起**：桌面默认按视口决定展开；折叠偏好写入 `localStorage` 的 `admin.sidebar.pinned`。展开 264px，Rail 56px。
- **临时展开（peek）**：Rail 上鼠标进入或键盘焦点进入时，面板以浮层展开到 264px；外层槽位仍为 56px，主内容 `left` 和宽度不位移。鼠标离开或焦点离开后延迟收起。
- **手动收起抑制**：指针仍在侧栏时点击收起，不因 hover 立即弹回；指针离开一次后恢复 hover peek。键盘收起且指针在外时不会留下永久抑制。
- **Esc**：关闭 peek，并把焦点移到 `#main`，避免焦点留在侧栏后立即重新触发 peek。
- **移动抽屉**：小于 1024px 显示汉堡按钮；抽屉含遮罩、Esc 关闭、Tab 焦点陷阱、body 滚动锁、路由变化关闭和关闭后焦点回到汉堡按钮。
- **导航语义**：当前项使用 `aria-current="page"`；Rail 标签隐藏时链接仍有 `aria-label` 与 `title`；折叠按钮有 `aria-expanded` 和 `aria-controls`。
- **内容收纳**：`.app-main` 建立 `container-name: main` 容器；宿主可在主内容变窄时用容器查询隐藏表格次要列，示例见 `style.css` 的 batch/site 表规则。
- **减少动态**：`prefers-reduced-motion: reduce` 下关闭非必要过渡和抽屉入场动画，状态仍可切换。

## 集成步骤

1. 复制 `App.vue`、`components/` 和 `style.css` 的外壳部分到宿主；保留 `#main`、`.app-main`、`.content` 和 `SidebarNav` 的结构。
2. 把 `crumbs` 的路径、`SidebarNav` 的导航项和品牌文案换成宿主路由；不要把示例的 `/batches` 当作通用路由。
3. 把 `HEALTH_URL` 改成宿主的健康接口；状态字段不匹配时只改 `Health`、`loadHealth` 和 `serviceText`，不要改侧栏状态机。
4. 用宿主令牌替换 `:root`；品牌色、主操作色、边框和状态色都要重新做对比度检查。
5. `style.css` 中的卡片、表格、表单、`.preview-table`、`.wizard-grid` 等是批次内容示例，不是外壳依赖；只取需要的部分，避免带上无关业务样式。
6. 保留 `prefers-reduced-motion`、焦点样式、`aria-*` 和抽屉焦点陷阱；不要为了视觉还原删掉键盘路径。

## 验证记录

2026-11-23 在 Chromium（Playwright）中按 1280×900、1440×900、768×900、390×844 检查，详见 `verification.json`：

- 1280 展开：侧栏槽位 264、面板 264、主内容 left 264、宽 1016。
- 1280 Rail：槽位 56、面板 56、主内容 left 56、宽 1224。
- 1280 peek：槽位 56、面板 264、主内容 left 56、宽 1224（不推挤内容）。
- 手动收起后 hover 不立即弹回；Esc 关闭 peek，焦点落在 `main`。
- 768／390 抽屉可开、Esc 可关，`document.scrollWidth === innerWidth`，控制台错误 0。
- 宿主侧同时通过 193 个后端测试、前端 Vitest 与生产构建；真实批次 2 个站点、14 条有效商品、0 失败。

限制：只验证 Chromium；没有 NVDA/VoiceOver、Safari/Firefox、深色主题或所有缩放状态的证据；颜色示例来自宿主，不代表 Cloudflare 官方色板。
