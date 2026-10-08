# 08 · 部署与使用说明

## 1. 技术栈

| 项 | 选择 | 说明 |
| --- | --- | --- |
| 框架 | React 19 + TypeScript | 函数组件 + Hooks |
| 构建 | Vite 7 + `vite-plugin-singlefile` | 产物为单个 `dist/index.html`，可直接静态托管或离线打开 |
| 样式 | Tailwind CSS v4 | 令牌通过 `@theme inline` 映射；组件只用语义工具类 |
| 图标 | lucide-react | 单一图标库 |
| 文档渲染 | react-markdown + remark-gfm | `docs/*.md` 以 `?raw` 方式打包进应用 |
| 路由 | 自研 hash 路由 | `#/dns/records?q=...`，适配单文件与 iframe 预览 |

无后端：DNS 记录、列可见性、主题、侧边栏状态持久化在 `localStorage`，可随时清空重置。

## 2. 目录结构

```
docs/                        设计文档（本目录）
src/
  index.css                  设计令牌、基础样式、文档排版
  lib/
    router.tsx               hash 路由 Provider / useRouter / Link
    theme.tsx                主题 Provider（light/dark/system）
    hooks.ts                 媒体查询、localStorage、点击外部、防抖…
  components/
    ui/primitives.tsx        Button Badge Field Input Select Textarea Toggle Checkbox RadioCards Segmented
    ui/overlays.tsx          Tooltip Popover Dialog Toast Menu
    ui/layout.tsx            Card* CollapsibleCard Alert PageHeader InfoTip EmptyState Stat Kbd
    ui/table.tsx             useColumnWidths（列宽状态/持久化）+ ColumnResizer（拖拽/键盘把手）
    shell/ShellContext.tsx   侧边栏状态机、快捷键
    shell/Sidebar.tsx        桌面侧边栏（pinned/rail/peek）+ 移动抽屉
    shell/TopBar.tsx         顶栏
    shell/CommandPalette.tsx 快速搜索
    shell/AppShell.tsx       外壳组合
  data/nav.ts                导航信息架构、最近访问
  data/records.ts            DNS 示例数据、类型、校验
  pages/
    OverviewPage.tsx         仪表盘 + 占位页
    dns/DnsRecordsPage.tsx   列表页综合案例
    dns/DnsRecordForm.tsx    内联表单
    forms/FormPatternsPage.tsx  长表单 + 向导
    SettingsPage.tsx         设置页
    ResponsiveLabPage.tsx    响应式模拟工具
    DocsPage.tsx             文档阅读器（左侧文档目录 + 右侧大纲）
  App.tsx                    Provider 组合与路由表
```

## 3. 本地运行与构建

```bash
npm install
npm run dev        # 开发服务器
npm run build      # 产出 dist/index.html（单文件）
npm run preview    # 本地预览构建产物
```

部署：将 `dist/index.html` 放到任意静态托管（Cloudflare Pages、Nginx、S3、GitHub Pages）。因为是 hash 路由，不需要服务端重写规则。

> Responsive Lab 通过 `iframe` 加载同一 HTML（附加 `?frame=1`），因此需要通过 HTTP(S) 访问；直接 `file://` 打开时部分浏览器会阻止 iframe 访问 `contentDocument`（主题同步失效，但预览本身仍可用）。

## 4. 在自己的项目中复用

1. **复制令牌**：把 `src/index.css` 的 `:root` / `[data-theme="dark"]` / `@theme inline` 段落拷到你的全局样式。只改原始值，不改语义名。
2. **复制外壳**：`components/shell/*` 与 `lib/hooks.ts`、`lib/router.tsx`（或替换为 react-router，只需把 `useRouter().path` 换成 `useLocation().pathname`）。
3. **配置导航**：编辑 `data/nav.ts` 的 `NAV` 数组；`group: "top" | "main" | "bottom"` 控制分区；带 `children` 的项自动成为手风琴。
4. **页面骨架**：每个页面以 `<PageHeader>` 开始，内容放在 `<Card>` 中；表单字段用 `<Field>` 包装。
5. **校验**：按 `validateRecord` 的方式写纯函数，返回 `{ field: message }`；组件层只负责"何时显示"。

## 5. 验收清单（完整）

### 布局
- [ ] 390 / 768 / 1440 三宽逐页检查；页面级无横向滚动。
- [ ] 320px：导航抽屉、表单、表格卡片列表全部可用；300px 不溢出。
- [ ] 间距仅使用 4/8/12/16/24/32/48；圆角 ≤ 4 档；阴影 ≤ 3 级；字号 ≤ 7 档。

### 外壳
- [ ] 侧边栏 pinned ↔ rail 切换平滑；rail 悬停 ≥110ms 展开、离开 ≥220ms 收起；内容不推挤。
- [ ] 点击"Collapse"后鼠标未离开不会立即再展开。
- [ ] 键盘 Tab 进入 rail 自动展开，Esc 收起。
- [ ] 移动抽屉：遮罩/Esc/导航关闭，body 滚动锁定。
- [ ] `Ctrl/⌘+K` 命令面板、`[` 切换侧边栏。

### 表单
- [ ] 可见标签；失焦校验 + 提交汇总；首错聚焦；保留已填；允许粘贴。
- [ ] 窄屏按钮堆叠，primary 在上；Cancel 在 Save 左。
- [ ] 删除在编辑态内，确认对话框主按钮为动词；高风险需输入名称。

### 表格
- [ ] 筛选草稿/应用分离；Enter 应用；chips 可移除；显示选项持久化。
- [ ] 排序 `aria-sort`；全选/半选；批量操作浮条；删除后 Undo。
- [ ] 列宽可拖拽（有 min/max），键盘可调，双击/一键还原，拖动结束才持久化。
- [ ] Edit 列 sticky 常驻；横向滚动时出现分隔阴影；悬停/选中态背景不透明一致。
- [ ] 展开行 / 弹窗两种编辑形式可切换，复用同一表单；关闭后焦点回到 Edit 按钮。
- [ ] < 640px 切换为卡片列表。

### 侧边栏 Rail
- [ ] 56px 带内图标水平居中；折叠态零文字泄露（含徽标、快捷键）。
- [ ] 隐藏文字不可聚焦、不被读屏朗读。

### 主题与无障碍
- [ ] 浅色 / 深色 / 跟随系统；系统切换实时生效；无闪烁。
- [ ] 焦点环可见；无 `outline:none` 无替代；无 `div onClick`。
- [ ] 对比度 ≥ 4.5:1；命中目标 ≥ 24px（触屏 44px）。
- [ ] `prefers-reduced-motion` 生效。

### 性能
- [ ] 搜索防抖；过滤排序 memo；列表 key 稳定。
- [ ] 浮层只在打开时挂载；Tooltip/Popover 使用 Portal，不触发父级重排。
- [ ] 构建产物单文件 ≤ 500KB gzip 前（文档内嵌）。

## 6. 已知限制

- 示例数据与"保存"均为本地模拟（350–600ms 延迟），刷新后保留在 `localStorage`。
- Responsive Lab 与主页面共享 `localStorage`，在预览中切换侧边栏固定状态会在下次加载时影响主页面。
- 命令面板的 "Ask AI" 仅为入口示意。
