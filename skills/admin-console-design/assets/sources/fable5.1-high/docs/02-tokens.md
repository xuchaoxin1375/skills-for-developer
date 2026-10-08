# 02 · 设计令牌与视觉

令牌（Design Tokens）是所有组件唯一允许引用的视觉值来源。实现见 `src/index.css`：原始值定义在 `:root` / `:root[data-theme="dark"]`，通过 Tailwind v4 的 `@theme inline` 暴露为工具类（`bg-surface`、`text-fg-2`、`border-line`、`shadow-2`…）。

## 1. 颜色

### 1.1 语义令牌

| 令牌 | 浅色 | 深色 | 用途 |
| --- | --- | --- | --- |
| `--c-bg` | `#f5f6f7` | `#0f1114` | 页面画布 |
| `--c-surface` | `#ffffff` | `#17191d` | 卡片、顶栏、侧边栏 |
| `--c-surface-2` | `#f6f7f8` | `#1e2126` | 表头、悬停、禁用输入底 |
| `--c-surface-3` | `#eceef0` | `#262a30` | 选中、按下、导航激活 |
| `--c-text` / `-2` / `-3` | `#1d1f23` / `#4a4f57` / `#7b8089` | `#e8eaed` / `#b4b9c1` / `#848a94` | 三级文字 |
| `--c-border` / `-strong` | `#dde0e4` / `#c3c7cd` | `#2c3037` / `#3d424a` | 分割线 / 控件边框 |
| `--c-primary` | `#0051c3` | `#6ea8ff` | 主按钮、链接、焦点 |
| `--c-orange` | `#f6821f` | 同 | 品牌点缀（Logo、Proxied 云朵、激活指示条） |
| `--c-success` / `warning` / `danger` | 绿 / 琥珀 / 红 | 提亮版本 | 状态 |

### 必须

- 组件 **只能** 引用语义令牌，不得出现裸色值。
- 正文与背景对比度 ≥ 4.5:1；大号文字 / 图标 ≥ 3:1。深色模式下主色改用更亮的 `#6ea8ff` 以维持对比度。
- 品牌橙色仅用于点缀（≤ 5% 面积），**不作为**按钮主色（与 Cloudflare 一致：primary 是蓝色）。

### 应该

- 状态色成对出现：实色（图标 / 文字）+ `-soft` 浅底（Badge、Alert 背景）。
- 悬停 = `surface-2`，激活/选中 = `surface-3`；不要用透明度叠加黑色。

### 避免

- 为了"好看"引入第四种灰阶文字。
- 深色模式简单反相；需单独调校阴影（更深）与主色（更亮）。

## 2. 主题切换

- 三种偏好：`light` / `dark` / `system`（默认）。实现见 `src/lib/theme.tsx`。
- 偏好持久化于 `localStorage("cfui.theme")`；`system` 监听 `prefers-color-scheme` 变化实时切换。
- 通过 `<html data-theme="light|dark">` 生效，同时设置 `color-scheme`，使原生控件（滚动条、`<select>` 下拉）随之变色。
- **必须**：切换主题无闪烁（令牌在 CSS 中，无需等待 JS 重绘整个树）。

## 3. 字体与排版

- 字体栈：`Inter, system-ui, -apple-system, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif`。等宽：`ui-monospace, Menlo, Consolas`。
- 字号 7 档（见 01 §3）。基准 14px。
- 技术值（IP、主机名、记录内容）**应该**使用等宽字体，便于逐字核对。
- 数字列 **应该**使用 `tabular-nums`。

## 4. 间距

只允许：`4 / 8 / 12 / 16 / 24 / 32 / 48`。

| 场景 | 值 |
| --- | --- |
| 图标与文字 | 8 |
| 字段标签与输入框 | 6（例外：Tailwind `gap-1.5`） |
| 字段之间（纵向） | 16 |
| 卡片内边距 | 16（移动）/ 20（桌面） |
| 卡片之间 | 16（移动）/ 24（桌面） |
| 页面标题与内容 | 24 |

## 5. 圆角（4 档）

`xs 4` 徽标、复选框 · `sm 6` 按钮、输入框 · `md 8` 卡片、弹出层 · `lg 12` 对话框。

## 6. 阴影（3 级）

| 级别 | 用途 |
| --- | --- |
| `shadow-1` | 卡片、按钮的"贴地"感 |
| `shadow-2` | Tooltip、缩放预览框 |
| `shadow-3` | Popover、Dialog、悬停展开的侧边栏 |

## 7. 图标

- 单一图标库 lucide-react；线宽 2；尺寸 16（内联 / 按钮）、18（导航）、20（Alert / Dialog）。
- 纯图标按钮 **必须** 提供 `aria-label`。
- 装饰性图标 **必须** `aria-hidden`。

## 8. 动效

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--dur-fast` | 120ms | 颜色、悬停 |
| `--dur-base` | 200ms | 透明度、折叠展开 |
| `--dur-slow` | 280ms | 侧边栏宽度、抽屉滑入 |
| `--ease-out` | `cubic-bezier(.2,0,0,1)` | 全部进入动画 |

- 只对 `transform / opacity / width(侧边栏) / grid-template-rows(折叠)` 做过渡。
- **必须** 响应 `prefers-reduced-motion: reduce`（全局将时长压到 0.01ms）。

## 9. 层级（z-index）

| 值 | 组件 |
| --- | --- |
| 20 | 侧边栏（常规） |
| 40 | 侧边栏（悬停展开态）、批量操作浮条 |
| 50 | 顶栏 |
| 60 | 移动端抽屉 |
| 70 | Popover / Menu |
| 80 | Tooltip |
| 90 | Dialog / 命令面板 |
| 100 | Toast |
