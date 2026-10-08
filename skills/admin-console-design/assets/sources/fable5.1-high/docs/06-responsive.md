# 06 · 响应式与自适应

## 1. 断点

| 名称 | 范围 | 外壳行为 | 内容行为 |
| --- | --- | --- | --- |
| xs | < 640 | 抽屉导航 | 单列；表格 → 卡片列表；按钮纵向堆叠；Dialog 底部抽屉 |
| sm | 640–767 | 抽屉导航 | 表格横向滚动（卡片内）；6 列表单栅格 |
| md | 768–1023 | **Rail 侧边栏 + 悬停展开** | 单列设置/表单；统计 2 列 |
| lg | 1024–1279 | 侧边栏默认固定 | 12 列表单栅格；长表单出现右侧大纲 |
| xl | 1280–1535 | 同上 | 统计 4 列；Overview 2+1 栅格 |
| 2xl | ≥ 1536 | 同上 | 内容区封顶 1440px 居中 |

验证基线：**390 / 768 / 1440** 三档必须逐页检查；**320** 必须可回流；**300** 应该不溢出（允许部分文字换行、按钮全宽）。

## 2. 布局策略（按优先级）

1. **让容器伸缩**：`flex-1 min-w-0`、`grid minmax(0, 1fr)`。`min-width: 0` 是防止 flex/grid 子项撑破父容器的关键。
2. **让内容折行**：工具栏 `flex-wrap`、页脚链接 `flex-wrap`、chips `flex-wrap`。
3. **截断**：只对"可通过其它方式获得全文"的内容截断（表格单元格有 `title`，名称有 Tooltip）。
4. **重排**：表格 → 卡片；并列按钮 → 堆叠；双栏 → 单栏。
5. **隐藏**：仅限次要/冗余元素（顶栏"Ask AI/Support"文字按钮、步骤条标签、快捷键提示）。永不隐藏主操作。
6. **卡片内滚动**：最后手段，仅用于宽表格，且必须限制在卡片内部。

### 必须

- 页面级（`body`）无横向滚动。检查方式：`document.documentElement.scrollWidth <= innerWidth`。
- 所有文本容器允许换行；长 URL / 哈希使用 `break-all` 或 `truncate`。
- 浮层（Popover/Tooltip/Dialog）计算位置时夹紧到视口内，宽度 `min(期望, 100vw − 16px)`。
- 触屏（`pointer: coarse`）下主要命中目标 ≥ 44px；桌面 ≥ 24px。

### 应该

- 使用逻辑尺寸优先级：先 `max-width`，再断点覆盖。
- 图像/预览使用 `transform: scale` 适配而不是裁切。
- 顶栏右侧的按钮使用 `square` 图标按钮在窄屏保持可达。

### 避免

- 为每个断点写一套独立样式；应是"单列基线 + 渐进增强"。
- 使用固定像素宽度的表单列（除短字段如 Port 140px，且外层仍需 `minmax(0,1fr)`）。
- `100vw` 用作宽度（含滚动条会溢出），改用 `100%`。

## 3. 外壳的响应式细节

- 侧边栏占位宽度只有 0 / 56 / 264 三种，过渡 280ms；内容区 `flex-1 min-w-0`。
- 从桌面缩到移动时自动关闭 peek 与抽屉；从移动放大时关闭抽屉。
- 顶栏资源名 `max-width: 60vw` + `truncate`。

## 4. Responsive Lab（模拟工具）使用说明

路径：侧边栏 **Responsive Lab**（`#/lab`）。

| 功能 | 说明 |
| --- | --- |
| 宽度滑条 | 280–1600px，实时改变预览 iframe 宽度；右侧数字框可精确输入 |
| 设备预设 | 320 / 390 / 768 / 1024 / 1440 一键切换 |
| Auto sweep | 自动在 280↔1600 之间往返扫描（0.5× / 1× / 2×），`Space` 暂停/继续 |
| 页面选择 | 预览 DNS 表格、长表单、向导、设置、仪表盘 |
| 高度 | 560 / 720 / 900 |
| Side by side | 同时展示 390 / 768 / 1440 三档 |
| 自动缩放 | 预览比窗口宽时按比例缩小，仍以真实 CSS 像素渲染 |
| 控制区停靠 | 控制卡片默认 sticky 于顶栏下方，可取消停靠 |

实现要点：预览是同一构建产物的 `iframe`（URL 加 `?frame=1`），因此媒体查询、侧边栏状态机、浮层定位均为真实行为；父页面通过 `contentDocument` 同步主题，通过 `location.hash` 切换页面避免整页重载；`frame` 模式下侧边栏隐藏 "Responsive Lab" 入口以避免递归。

## 5. 自检脚本（控制台可用）

```js
// 1) 页面是否横向溢出
console.log("overflow:", document.documentElement.scrollWidth > innerWidth);
// 2) 找到溢出元素
[...document.querySelectorAll("*")].filter(e => e.getBoundingClientRect().right > innerWidth + 1)
  .slice(0, 10).forEach(e => console.log(e));
// 3) 过小的命中目标
[...document.querySelectorAll("button,a,[role=button],input")]
  .filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.width < 24 || r.height < 24); })
  .forEach(e => console.warn("small target", e));
```
