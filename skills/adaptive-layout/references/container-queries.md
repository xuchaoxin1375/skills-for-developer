# 容器查询实现与文字约束

> 何时读：流程步骤 3。原则：**容器决定组件，视口只管页面**。阈值一律实测，不抄示例数字。

## 命名容器 + 双态

```css
.resource-card { container: resource-card / inline-size; }

/* 以单张卡片可用宽度决定是否显示完整动作文字。32.5rem 只是示例，必须实测。 */
@container resource-card (min-width: 32.5rem) {
  .resource-card__actions--labeled { display: flex; }
  .resource-card__actions--compact { display: none; }
}
```

- 同一张卡片会进全宽列表、双列网格、侧栏、弹窗：只看视口会误判，必须用容器查询。
- 视口媒体查询只调页级列数、外边距、导航（单列/双列/多列），不决定组件内部是文字还是菜单。
- 不支持容器查询的旧环境：回退到主操作+菜单或文字换行，动作不许消失。

## 按钮文字约束（按序执行）

1. 宽时展示完整标签。
2. 放不下则整颗按钮移到下一行；不收缩文字、不截断、不用省略号。
3. 必须控高则用整颗图标按钮 + 准确可访问名，悬停/聚焦可给提示。
4. 不适合图标化的进纵向菜单，保留完整标签。
5. 页面沿阅读方向纵向滚动；不用卡片内横向滚动或滑动手势露按钮。

## 防假适配 CSS

- 布局可用 `min-width: 0` 管 flex 收缩，但**不许**对按钮标签用
  `overflow: hidden` / `text-overflow: ellipsis` / `flex-shrink: 1` 假装适配。
- 长行（URL/命令/长标识）用 `overflow-wrap: anywhere` 断行不断窗。
- 页面级建议 `html, body { overflow-x: clip; }`（保 sticky），flex 直接子 `min-width: 0`。
- `[hidden] { display: none !important; }` 兜底，防止显式 display 覆盖隐藏语义。

## hover 只做增强

```css
@media (any-hover: hover) {
  .resource-card:hover .resource-card__actions { opacity: 1; visibility: visible; }
}
.resource-card:focus-within .resource-card__actions,
.resource-card[data-selected="true"] .resource-card__actions {
  opacity: 1; visibility: visible;
}
```

桌面悬停可预览，但点击与键盘焦点必须有等价路径；触控不依赖 hover/长按。

## React 结构示意（宽窄两态同数据）

```tsx
<div className="card-actions" role="group" aria-label={`${title}的操作`}>
  <div className="actions-wide">{actions.map(renderLabeledButton)}</div>
  <div className="actions-compact">
    {renderPrimary(actions[0])}
    {renderMoreMenu(actions.slice(1))}
  </div>
</div>
```

宽窄只是呈现切换：顺序、名称、行为一致；图标示例见 `interaction.md`。
