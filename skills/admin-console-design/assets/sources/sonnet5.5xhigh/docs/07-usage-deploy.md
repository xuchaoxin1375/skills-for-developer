# 07 · 部署与使用说明

## 1. 环境与命令

| 项 | 要求 |
| --- | --- |
| Node.js | 18 及以上 |
| 浏览器 | Chrome / Edge 105+、Safari 16+、Firefox 110+（需要容器查询、`:has()`、原生 `<dialog>`） |

```bash
npm install        # 安装依赖
npm run dev        # 开发模式（热更新）
npm run build      # 构建，产物为 dist/index.html（单文件，已内联脚本与样式）
npm run preview    # 本地预览构建产物
```

**部署**：把 `dist/index.html` 放到任意静态托管（Nginx、OSS、GitHub Pages、对象存储）即可。应用使用 hash 路由，**无需服务端重写规则**。

> 预览区通过 iframe 加载同一文档的另一个 hash 路由。若托管环境通过 `sandbox` 或 `X-Frame-Options` 禁止同源嵌入，可使用舞台顶部的「新标签页打开」。

## 2. 使用说明（设计稿）

1. **选择场景**：左侧面板选择 DNS 记录、添加记录、SSL/TLS 设置、添加站点或概览；面板可用左上角按钮收起。
2. **改变宽度**：底部浮层的滑条（240 – 1920px）、数值框或预设按钮；「适应舞台」开启时按比例缩放以完整显示。
3. **自动扫描**：点击「宽度扫描」，在 280 – 1600px 之间往返，速度可调；任意手动操作会暂停扫描。
4. **侧边栏**：浮层中可手动切换「侧边栏展开 / 折叠为图标栏」，也可点击「侧边栏行为演示」自动循环四个阶段（说明文字同步显示）。
   **表格**：在 DNS 记录场景中拖动列头右缘调整列宽、点击表头排序、勾选并使用底部批量条、点击 Edit 行内展开或弹窗编辑（见 [08](08-data-table-spec.md)）。
5. **查看模式**：改进方案 / 传统方案 / 并排对比。
6. **主题**：右上角切换跟随系统（默认）/ 浅色 / 深色；预览页同步。
7. **文档**：顶部「文档」页签，左侧为文档地图（可收起），右侧为本页大纲。

浮层可以收起为「控制 · XXXpx」小按钮；舞台会自动为浮层预留空间，避免遮挡预览。

### 预览页内的快捷键

| 按键 | 行为 |
| --- | --- |
| `[` | 折叠 / 展开侧边栏（宽屏） |
| `Ctrl/⌘ + K` | 快速搜索（命令面板） |
| `Esc` | 关闭浮层、对话框、抽屉 |
| `Enter`（筛选浮层中） | 应用筛选 |

## 3. 目录结构

```text
docs/                         规范文档（Markdown）
src/
  App.tsx                     顶层路由（展示壳 / 设计稿）
  index.css                   设计令牌 + 组件样式
  lib/
    route.tsx                 hash 路由、Link、导航守卫
    theme.ts                  主题（浅 / 深 / 系统）
    hooks.ts                  useLayout / usePersisted / useElementSize …
    bridge.ts                 父子页面消息协议
  ui/                         Modal / Popover / controls / Toast / columns（可调列宽、滚动提示）
  dashboard/                  设计稿本体
    DashboardApp.tsx          外壳：侧边栏 + 顶栏 + 页面 + 页脚；快捷键；消息桥
    Sidebar.tsx               侧边栏状态机与组件（可复用）
    Topbar.tsx / CommandPalette.tsx / nav.ts / data.tsx
    Legacy.tsx                「传统方案」对比样本
    RecordEditor.tsx          行内 / 弹窗共用的紧凑编辑器
    recordModel.ts            DNS 记录的表单模型与校验规则（整页表单与编辑器共用）
    pages/                    DnsRecords（交互式表格）/ RecordForm / Settings / AddSite / Misc
  showcase/                   展示壳：Stage（舞台 + 浮层）、DocsView、Panel
```

## 4. 路由与参数

| 路由 | 说明 |
| --- | --- |
| `#/` | 展示壳 · 设计稿 |
| `#/docs/<slug>` | 展示壳 · 文档（如 `#/docs/02-sidebar-spec`） |
| `#/dashboard/overview` | 概览 |
| `#/dashboard/dns` | DNS 记录列表（`?highlight=<id>` 高亮某行） |
| `#/dashboard/dns/new` · `#/dashboard/dns/edit/<id>` | 添加 / 编辑记录 |
| `#/dashboard/settings` | SSL/TLS 设置 |
| `#/dashboard/sites` · `#/dashboard/sites/new` | 域名列表 · 添加站点向导 |
| `#/dashboard/p/<slug>` | 其余导航项的占位页 |
| 查询参数 `embed=1` | 嵌入模式（由舞台设置，站内跳转自动保留） |
| 查询参数 `variant=legacy` | 传统方案 |
| 查询参数 `theme=light\|dark\|system` | 首次加载时的主题 |

可以直接用浏览器打开 `#/dashboard/dns/new`，脱离舞台验证真实窗口行为。

## 5. 父子页面消息协议

舞台（父）与设计稿（iframe）通过 `postMessage` 通信，类型定义见 `src/lib/bridge.ts`。双方都校验 `event.source`。

| 方向 | 类型 | 载荷 | 作用 |
| --- | --- | --- | --- |
| 父 → 子 | `nimbus:theme` | `value: system \| light \| dark` | 同步主题（不写入子页本地存储） |
| 父 → 子 | `nimbus:navigate` | `to: string` | 切换场景（hash 路由） |
| 父 → 子 | `nimbus:sidebar` | `action: pin-expanded \| pin-collapsed \| peek-on \| peek-off` | 驱动侧边栏演示 |
| 子 → 父 | `nimbus:ready` | — | 子页就绪，父页补发主题与路由（iframe 被移动后会重新加载） |
| 子 → 父 | `nimbus:state` | `path, layout, pinned, expanded, peek, drawer, width, variant` | 上报布局与侧边栏状态，用于浮层状态监视 |

## 6. 迁移到自己的项目

### 6.1 最小迁移：侧边栏

1. 复制 `src/index.css` 中的令牌（`:root` / `.dark`）与 `.sb-*`、`.btn`、`.badge`、`.kbd` 样式；
2. 复制 `src/dashboard/Sidebar.tsx`（`useSidebar`、`Sidebar`、`DrawerSidebar`）、`src/ui/Modal.tsx`、`src/lib/hooks.ts`；
3. 替换 `nav.ts` 为你的导航配置，替换 `Link` 为你的路由组件；
4. 在外壳中按 `useLayout()` 渲染 `Sidebar` 或 `DrawerSidebar`，并绑定 `[` 快捷键到 `sb.toggle`。

```tsx
const layout = useLayout();           // 'wide' | 'medium' | 'narrow'
const sb = useSidebar(layout);
return (
  <div className="app" data-layout={layout}>
    {layout !== "narrow" && <Sidebar api={sb} path={path} onSearch={openSearch} />}
    <div className="app-main">{/* Topbar + Page */}</div>
    {layout === "narrow" && <DrawerSidebar api={sb} path={path} onSearch={openSearch} />}
  </div>
);
```

### 6.2 最小迁移：表单

1. 复制 `Field` / `Select` / `Switch`（`src/ui/controls.tsx`）与 `.field`、`.input`、`.actionbar` 等样式；
2. 复制 `RecordForm.tsx` 中的校验流程：`touched` + `submitted` 决定何时显示错误，`ORDER` 决定首错聚焦顺序，`dirtyRef` + 导航守卫实现离开保护；
3. 将 `validate()` 替换为你的业务规则（或接入 zod 等库），保持「每个字段一条可行动的消息」。

### 6.3 新增一个场景

1. 在 `src/dashboard/pages/` 新增页面组件；
2. 在 `DashboardApp.tsx` 的路由分支中注册；
3. 在 `nav.ts` 增加导航项（可选）；
4. 在 `src/showcase/scenarios.ts` 增加场景条目（标题、路由、要点、尝试步骤）。

## 7. 已知限制

| 项 | 说明 |
| --- | --- |
| 浏览器后退键 | 离开保护只拦截站内链接与「取消」，不拦截浏览器后退（hash 路由限制）；刷新 / 关闭标签页由 `beforeunload` 保护 |
| iframe 嵌入 | 受托管环境策略影响，不可用时请使用「新标签页打开」 |
| 数据 | 所有数据为内存模拟，刷新后重置；固定状态与主题存于 `localStorage` |
| 国际化 | 设计稿界面为英文（与参考对象一致），展示壳与文档为中文 |
| 图标 | 仅使用 Lucide；Logo 为自绘云朵，非 Cloudflare 标识 |

## 8. 常见问题

**Q：为什么折叠态展开用「覆盖」而不是「推挤」？**
A：推挤会让内容区每次划过都重排；覆盖没有重排成本，视觉上也更稳定。固定展开才会推动内容，并且是用户显式选择。

**Q：为什么保存按钮不置灰？**
A：置灰无法告诉用户缺了什么。我们让按钮始终可点，点击后给出具体、可跳转的错误并聚焦第一个问题。

**Q：能把侧边栏悬停延迟改成别的值吗？**
A：可以，修改 `useSidebar` 中的 `120` 与 `250`；建议保持进入 100 – 150ms、离开 200 – 300ms。

**Q：为什么用 iframe 预览？**
A：媒体查询依赖真实视口。iframe 提供独立视口，才能如实演示 `@media` 与 `matchMedia` 的行为。

**Q：深色主题怎么扩展？**
A：在 `.dark` 中覆盖同名令牌即可；不要在组件内写死色值。
