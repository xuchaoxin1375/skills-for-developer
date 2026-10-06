# 容器查询实现与文字约束

> 何时读：流程步骤 3。原则：**容器决定组件，视口只管页面**。阈值一律实测，不抄示例数字。

## 命名容器 + 双态（下例以资源模块命名，实际按组件改名：工具栏/表格行/弹窗底部同理）

```css
.resp-unit { container: resp-unit / inline-size; }

/* 以单个模块可用宽度决定是否显示完整动作文字。32.5rem 只是示例，必须实测。 */
@container resp-unit (min-width: 32.5rem) {
  .resp-unit__actions--labeled { display: flex; }
  .resp-unit__actions--compact { display: none; }
}
```

- 同一组件会进全宽列表、双列网格、侧栏、弹窗：只看视口会误判，必须用容器查询。
- 成对阈值必须**同值分侧**（`(width >= 26rem)` 与 `(width < 26rem)`）；别写 `430px`/`431px` 这种整数对，落在中间的容器两头都不命中，宽窄标签会同时出现。
- 视口媒体查询只调页级列数、外边距、导航（单列/双列/多列），不决定组件内部是文字还是菜单。
- 不支持容器查询的旧环境：回退到主操作+菜单或文字换行，动作不许消失。

## 字段与匹配规则

```css
container-type: normal | inline-size | size | scroll-state;
container-name: none | <ident>+;          /* 不能用 none/and/or/not 等保留字 */
@container [<name>] <condition> { ... }   /* 省略名 → 匹配最近的、类型符合的祖先容器 */
```

| 取值 | 要点 |
|---|---|
| `normal` | 默认，**不是尺寸容器**，但样式查询仍可命中它 |
| `inline-size` | 最常用；只查行内方向，同时对该方向做**尺寸隔离**（宽度不再由内容决定） |
| `size` | 宽高都查；两向隔离，**必须显式给高**否则塌陷为 0 |
| `scroll-state` | 滚动状态查询（仅 Chromium 133+） |

- 嵌套多层时查询命中错容器是常见 bug：**命名容器并带名查询**。
- 容器查询同样是“逻辑”的：`inline-size`/`cqi` 在竖排（writing-mode）下自动变为按高度算。

## 按钮文字约束（按序执行）

1. 宽时展示完整标签。
2. 放不下则整颗按钮移到下一行；不收缩文字、不截断、不用省略号。
3. 必须控高则用整颗图标按钮 + 准确可访问名，悬停/聚焦可给提示。
4. 不适合图标化的进纵向菜单，保留完整标签。
5. 页面沿阅读方向纵向滚动；不用模块内横向滚动或滑动手势露按钮。

## 防假适配 CSS

- 布局可用 `min-width: 0` 管 flex 收缩，但**不许**对按钮标签用
  `overflow: hidden` / `text-overflow: ellipsis` / `flex-shrink: 1` 假装适配。
- 长行（URL/命令/长标识）用 `overflow-wrap: anywhere` 断行不断窗。
- 页面级建议 `html, body { overflow-x: clip; }`（保 sticky），flex 直接子 `min-width: 0`。
  **别用 `overflow-x: hidden` 掩盖溢出**：真正的溢出元素被藏起来验收看不见，且会让 `position: sticky` 失效。
- `[hidden] { display: none !important; }` 兜底，防止显式 display 覆盖隐藏语义。

## hover 只做增强

```css
@media (any-hover: hover) {
  .resp-unit:hover .resp-unit__actions { opacity: 1; visibility: visible; }
}
.resp-unit:focus-within .resp-unit__actions,
.resp-unit[data-selected="true"] .resp-unit__actions {
  opacity: 1; visibility: visible;
}
```

桌面悬停可预览，但点击与键盘焦点必须有等价路径；触控不依赖 hover/长按。

## React 结构示意（宽窄两态同数据）

```tsx
<div className="actions-group" role="group" aria-label={`${label}的操作`}>
  <div className="actions-wide">{actions.map(renderLabeledButton)}</div>
  <div className="actions-compact">
    {renderPrimary(actions[0])}
    {renderMoreMenu(actions.slice(1))}
  </div>
</div>
```

宽窄只是呈现切换：顺序、名称、行为一致；图标示例见 `interaction.md`。

## 双层容器 + 滑块验证（demo3 做法）

- 判读对象分两层：卡片容器宽决定按钮文字是否显示（如 `<330px` 次要藏文字）；工作区/视口容器宽决定单双列与浮层图文形式
  （如 `<600px` 单列 + 浮层用图标）。`330/600` 只是示例内容值，国际化/换字号后重测，不沿用。
- 判据：`W >= sum(B_i)+(N-1)*G`（`W` 操作区可用宽，`B_i` 第 i 个按钮完整固有宽，`G` 间距如 8px）。不成立即换呈现策略，不给按钮分更小宽度。
- 验证用滑块连续拖 300–800px（或 320–1440px）+ 设备预设点检，调试信息显示容器实测宽、可见数、换行行数；预设值 ≠ 真机测试，
  窄宿主下只标“当前可用宽”，正式验收用真实窗口或设备模拟。1:1 渲染，不整体缩放压字号与目标尺寸。

## 容器单位与回退

- `cqi`（行内1%，推荐，竖排自动转）/`cqw/cqh`/`cqb`/`cqmin/cqmax`；标题流体如 `clamp(1rem,.85rem+2.2cqi,1.6rem)`。
- 找不到容器时回退小视口单位（`svw/svh`）；`@container` 里可放心写范围语法。

## 样式查询与滚动状态（渐进增强）

```css
.promo-zone { --variant: promo; }
@container style(--variant: promo) { .resp-unit { border-color: #f97316; } }
.header-wrap { position: sticky; top: 0; container-type: scroll-state; }
@container scroll-state(stuck: top) { .header-wrap > .header { box-shadow: 0 2px 8px rgb(0 0 0/.15); } }
```

- 样式查询目前只查自定义属性（Chrome 111/Safari 18，Firefox 待补 Interop 2026）；滚动状态（`stuck/snapped/scrollable`）仅 Chromium 133+，兜底 `IntersectionObserver`。

## 五种塌陷/循环陷阱

| 陷阱 | 解法 |
|---|---|
| 容器查自己（在 `.card` 上声明又改 `.card`） | 外面包一层当容器 |
| 尺寸隔离致宽塌陷（inline-block/浮动/内容定宽 Flex 子项变 0） | 给明确宽或 `flex:1 1 20rem`、`width:100%` |
| `size` 类型高塌陷为 0 | 显式高或改 `inline-size` |
| 嵌套容器匹配错位 | 命名容器并带名查询 |
| 在 `@container` 里改容器自身尺寸（循环依赖，规范禁止） | 只改后代；容器尺寸交给外层容器或视口决定 |

## 命中自证与验收装置（零 JS）

```css
/* 自报告：不用 DevTools 也能看出哪条规则命中（可交给非前端验收方看） */
.cq-state::after { content: "默认：纵向堆叠（容器 < 26rem）"; }
@container card-slot (width >= 26rem) {
  .cq-card { grid-template-columns: minmax(8rem, 38%) 1fr; }
  .cq-state::after { content: "命中 (width >= 26rem)：左图右文"; }
}
/* 原生拖拽手柄：客户自己拖宽看断点，resize 需与 overflow:auto 成对 */
.stage { min-width: 220px; resize: horizontal; overflow: auto; }
```

- 调试徽章/读数里的“容器宽”必须是**内容盒宽**：`clientWidth - padding`，再扣滚动条差值
  （`offsetWidth - clientWidth`），否则读数比 `@container` 实际判据大一圈（详见 `js-apis.md`）。

## 与媒体查询分工

媒体查视口/能力/偏好（骨架/导航/栏数/`prefers-*`），容器查祖先尺寸/样式/滚动（可复用组件内部）；配套单位分别为 `vw/dvh` 与 `cqi/cqw`；尺寸查询 Baseline 2023。
