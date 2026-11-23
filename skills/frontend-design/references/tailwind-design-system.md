## Tailwind v4 设计系统与前端可维护性

> 何时读：项目用 Tailwind v4（React、Vue 或 Svelte 均可），需要把设计令牌落到代码、控制工具类蔓延、让页面增长后仍可维护时。三层令牌的视觉规则见 [tokens.md](tokens.md)；状态归属与跨端契约见 [架构与契约](../../swe-gov/references/architecture-and-contracts.md)。本文只补 Tailwind 落地与组件组织。

### 令牌到 Tailwind v4

三层令牌不变，落地按层分工（组件层可选）：

| 层 | 放哪 | 作用 | 产品代码能否直接用 |
|---|---|---|---|
| 原始层 | `@theme` | 调色板、字号、间距、圆角等原始值；按需生成工具类 | 不直接用 |
| 语义层 | `:root`、`.dark`、`[data-theme]` | 角色：背景、文字、主色、边框、焦点、危险；主题切换只改这里 | 通过桥接层使用 |
| 桥接层 | `@theme inline` | 把语义变量注册成 `bg-background`、`text-foreground` 等工具类 | 只用它生成的语义工具类 |
| 组件层 | 组件令牌文件 | 只有组件确实需要偏离共享角色时才加 | 按需 |

示例：

```css
@import "tailwindcss";

@theme {
  --color-blue-500: oklch(0.62 0.19 250);
  --spacing-gutter: 1.5rem;
}

:root {
  --background: oklch(0.99 0 0);
  --foreground: oklch(0.2 0 0);
  --primary: var(--color-blue-500);
  --primary-foreground: oklch(0.99 0 0);
  --border: oklch(0.9 0 0);
}

.dark {
  --background: oklch(0.16 0 0);
  --foreground: oklch(0.95 0 0);
  --primary: oklch(0.75 0.15 250);
  --primary-foreground: oklch(0.16 0 0);
  --border: oklch(0.3 0 0);
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-border: var(--border);
}
```

- 组件只用语义工具类：`bg-background`、`text-foreground`、`border-border`、`text-primary`；不写 `bg-white dark:bg-zinc-900`，不写十六进制或 `oklch()` 字面量。
- 用类切换主题且需要 `dark:` 变体时，加 `@custom-variant dark (&:where(.dark, .dark *));`；只用语义工具类时不需要给每个组件写 `dark:`。
- 语义令牌引用其他变量时用 `@theme inline`；否则主题覆盖可能不生效。
- 重置默认色板：在 `@theme` 里写 `--color-*: initial;`，再声明项目色板；off-brand 类不再生成。不要只靠口头约定。
- 原始层是否暴露给产品代码按团队约定；默认不暴露，避免绕过语义层。
- 间距、圆角、字号同理：命名令牌放 `@theme`（如 `--spacing-gutter`、`--radius-control`），组件用 `p-gutter`、`rounded-control`；不在页面写 arbitrary values。

### 组件变体与类合并

- 变体是设计决策，不是调用点的条件类。重复控件（按钮、徽章、输入、提示）先建命名变体：`variant`（primary、secondary、ghost、danger）、`size`（sm、md、lg）、`state`（loading、disabled）。
- React 可用 `cva` 与 `tailwind-merge`；Vue 可用同一套变体思路或项目既有工具，同样配 `tailwind-merge` 的 `cn`。`tailwind-merge` 主版本要与 Tailwind 主版本匹配，升级时一起核对；不强制某个库，关键是变体有名字、有默认值、有组合规则。

```ts
import { cva } from "class-variance-authority";

const button = cva("inline-flex items-center rounded-control", {
  variants: {
    variant: {
      primary: "bg-primary text-primary-foreground",
      ghost: "bg-transparent text-foreground",
    },
    size: { sm: "h-8 px-3 text-sm", md: "h-10 px-4" },
  },
  defaultVariants: { variant: "primary", size: "md" },
});
```

调用方只传 `className` 做布局；视觉差异用 `variant` 与 `size`。
- 调用方 `className` 只用于布局（margin、width、grid 位置）；颜色、间距、圆角等视觉差异走 variant。需要覆盖时用 `cn` 合并冲突类，避免 `px-4` 与 `px-6` 依赖样式表顺序。
- 新变体先问是否已有语义角色可表达；不要为单页加一次性 variant。
- 原生控件或成熟无头库能满足时优先复用；自定义控件要有键盘、焦点、ARIA 等价。

### 工具类治理

- arbitrary values（如 `top-[117px]`、`bg-[#bada55]`）是逃生口，不是常规手段；出现时先查令牌，重复出现提升为令牌或 `@utility`。
- 新增项目级工具类用 `@utility`，按 API 变更审查；不在页面散写一次性 CSS。
- 同类样式重复三次以上，抽成组件 variant 或 pattern，不复制类串。
- lint 与 CI 拦截：组件内颜色字面量、off-brand 类、常规 arbitrary values、未使用令牌；具体规则按项目工具链配置。
- `dark:` 只用于真正需要不同结构的例外；主题差异放语义令牌，不把两套颜色写进每个组件。

### 组件分层与依赖方向

名字可随项目调整，依赖方向不变：

| 层 | 放什么 | 依赖 |
|---|---|---|
| `ui/` | 无业务 primitives：Button、Input、Dialog、Table 基础件 | 令牌、通用工具 |
| `patterns/` | 跨功能组合：PageHeader、DataTable、FormSection、EmptyState | `ui/` |
| `features/<domain>/` | 业务组件、hooks 或 composables、API 调用、领域局部状态 | `ui/`、`patterns/` |
| `pages/` | 路由级组装 | `features/`、`patterns/`、`ui/` |
| `app/` | 壳、路由、providers、主题、全局错误边界 | 下层 |
| `shared/` | 无业务工具、类型、常量 | 不依赖 features 与 pages |

- 依赖只能向下（`pages` → `features` → `patterns` → `ui`）；`ui` 不反向导入业务。
- 跨 feature 通过公开 API（`index`）或 `shared`，不深挖对方内部文件。
- 组件文件靠近使用方；只有真正跨功能复用才上移，不提前建大而全的 `components/` 垃圾场。
- 每个 feature 暴露最小公开 API；内部实现可改，调用方不依赖文件路径。
- 单文件组件超过约 200–300 行或承担多个任务时拆分；按职责拆，不按 HTML 标签拆。
- React 用 hooks、Vue 用 composables 承载可复用逻辑；不把业务规则塞进通用组件。
- 状态归属按架构与契约：服务端数据、URL 状态、全局客户端状态、组件本地状态分开；服务端数据用请求缓存层，不整包复制进全局 store。

### React 与 Vue 选择

两者都能支撑长期应用；按团队熟悉度、生态与招聘、现有代码与迁移成本、官方栈偏好选择，不在同一产品混用两套。

| 维度 | React | Vue 3 |
|---|---|---|
| 生态与招聘 | 更大，选择更多 | 官方栈更集中 |
| 默认规范 | 需团队自定路由、数据请求、状态与目录 | Vue Router、Pinia、Nuxt 减少决策 |
| 适合 | 已有 React 资产、需要自由组合、跨端或招聘要求 | 希望快速统一规范的小到中型团队、单文件组件协作 |
| 组件库 | shadcn/ui、Radix 等 | shadcn-vue、Reka UI 等 |
| 风险 | 自由度高，缺规范时容易分裂 | 生态相对小，升级与招聘面需评估 |

- 选择写入 ADR 或方案确认单；把版本、升级预算、组件库与测试栈一起记录，不只写框架名。
- 现有 `admin-console-design` 模板以 React、Vite、Tailwind v4 为主，另有 Vue 3 外壳候选；不为套模板强换栈。
- 框架选型属于 `swe-gov` 的技术选型；本文只补前端落地差异。

### 可维护性门禁

- TypeScript strict 或项目等价类型检查；组件 props 与事件有类型。
- eslint（React `jsx-a11y` 或 Vue 无障碍插件）、stylelint 或令牌 lint、Tailwind 类检查；CI 与本地同一入口。
- 组件测试覆盖关键交互与状态；关键用户链路有 E2E 或真实接口冒烟；视觉回归覆盖主题与窄屏关键页。
- 设计令牌变更走同一入口，组件不写死颜色与间距；新增令牌有用途、亮暗值、对比度证据。
- 代码评审检查：新组件是否重复、依赖方向是否反向、是否新增一次性模式、是否绕过令牌、状态是否多源。
- 页面增长时先补 [设计规格](design-spec.md) 与组件契约，再写实现；规格与实现不一致按缺陷处理。

### 验收清单

- [ ] 语义令牌是唯一来源；组件无颜色与间距字面量。
- [ ] 主题切换只改语义层；`dark:` 仅用于结构例外。
- [ ] 无 off-brand 类、无常规 arbitrary values。
- [ ] 重复控件有命名变体；`className` 只做布局。
- [ ] 依赖方向无反向导入；跨 feature 走公开 API。
- [ ] 服务端、URL、全局、本地状态归属清楚。
- [ ] lint、类型、组件测试、关键 E2E 或视觉回归通过。
- [ ] 新增页面或组件已映射到现有模式，或记录新增理由。
