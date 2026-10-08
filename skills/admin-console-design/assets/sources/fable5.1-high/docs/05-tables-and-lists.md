# 05 · 表格与列表

参考页面：**DNS records**。该页面集中了控制台列表页的全部标准构件：页面标题、状态横幅、可折叠推荐、工具栏、筛选浮层、显示选项、排序表格、内联编辑、批量操作、空态与分页信息。

## 1. 页面骨架（自上而下）

1. `PageHeader`：标题、描述、右侧 meta Badge（`DNS Setup: Full`）与文档按钮。
2. `Alert(warning)`：域名 Pending 等页面级状态，可关闭。
3. `CollapsibleCard`：Recommendations，"All set"时默认收起。
4. **工具栏**：搜索框（左、伸缩、最大 520px）| Filters | Display options | Import | Export | **Add record**（primary，最右）。
5. 激活筛选 chips（可逐个移除）。
6. （条件）新增表单卡片。
7. 表格卡片：配额说明条 → 表格 → "Showing a–b of n"。
8. （条件）浮动批量操作条。

## 2. 工具栏

### 必须

- 搜索框带可见清除按钮；输入 **防抖 ≥ 150ms** 后再过滤，避免逐键重算。
- 所有按钮带图标 + 文字；primary 只有一个。
- < 1024px 时搜索框独占一行，按钮组换行并允许折行（`flex-wrap`），不得横向溢出。

### 应该

- 搜索支持从 URL 参数预填（`?q=`），便于分享与从命令面板跳转。
- Export 立即下载（Blob + `<a download>`），Import 使用 Dialog 粘贴文本并说明格式。

## 3. 筛选浮层（Filters Popover）

结构：标题 + 关闭 → 多行条件（字段 ▾ · 运算符 ▾ · 值 · 删除）→ 底部（+ Add filter | "Press Enter to apply" · Clear · **Apply**）。

### 必须

- **草稿与已应用分离**：浮层内的修改是草稿，`Apply`/Enter 才生效；关闭浮层不丢草稿。
- Apply 在没有任何有效值时禁用，并有文字提示（这是"禁用按钮"的允许例外：无输入即无意义）。
- 条件行在 < 640px 时重排为两行（字段+删除 / 运算符+值），保持可操作。
- 浮层 `role=dialog`，打开后焦点进入首个控件，`Esc` 关闭并把焦点还给触发按钮；点击外部关闭。
- 浮层宽度 `min(560px, 100vw − 16px)`，位置随滚动/缩放重新计算，永不越出视口。

### 应该

- 触发按钮上显示激活筛选数量徽标；页面上显示 chips，支持单独移除。

## 4. 显示选项（Display options）

- 列可见性复选框（Proxy / TTL / Comment / Details）与密度开关（Comfortable / Compact）。
- 持久化到 `localStorage`，刷新后保留。

## 5. 表格

### 必须

- 语义化：`<table>` + `<caption class="sr-only">` + `<th scope="col">`；排序按钮带 `aria-sort`。
- 表格置于卡片内 `overflow-x: auto`；设置 `min-width`（示例 760px）保证列不被压扁；**页面级不出现横向滚动**。
- 可能很长的单元格（Name、Content、Comment）设置 `max-width` + `truncate` + `title` 悬停显示全文。
- 行选择复选框使用 24px 命中区包裹 16px 视觉框；表头支持全选 / 半选（`indeterminate`）。
- 行操作 `Edit` 固定在最右列，并带 `aria-label="Edit A www.example.com"`。

### 应该

- 名称列区分子域与主域颜色（`www.` 深色 + `myexample.com` 浅色）。
- 技术内容列用等宽字体。
- 排序三态循环：升 → 降 → 无。
- 悬停行底色 `surface-2`；选中行 `primary-soft`。
- 警告图标列固定在最左侧，Tooltip 解释原因。

### 可以

- 行密度切换（Compact 行高 32px）。

## 5.1 列宽调节

### 必须

- 数据列可拖拽调节宽度：表头右缘 8px 热区（视觉 1px 分隔线，悬停/拖动变为 3px 主色），`cursor: col-resize`。
- 使用 `table-layout: fixed` + `<colgroup>` 设置宽度，拖动时**只重排本表**，不影响页面其它部分。
- 每列有 `min / max` 边界（示例：Name 140–520，Content 160–720），防止拖成 0 或无限宽。
- 固定功能列（复选框、警告、操作）不可调节，也不显示把手。
- 把手可键盘操作：`role="separator" aria-orientation="vertical" aria-valuenow`，`← →` 16px、`Shift` 64px、`Home` 还原；双击还原单列；Display options 中提供"Reset column widths"。
- 宽度持久化（`localStorage`）**只在拖动结束时写入**，拖动过程中仅更新内存状态。

### 应该

- 拖动期间给 `body` 设置 `user-select: none` 与统一的 `cursor`，避免选中文字和光标闪烁。
- 使用 Pointer Events + `setPointerCapture`，鼠标移出表格也能继续拖动。

## 5.2 常驻操作列（Sticky actions）

> 列很多时，用户最常用的 Edit 不能被"滚到右边才看得到"。

### 必须

- 最后一列（Edit / 行菜单）`position: sticky; right: 0`，始终可见。
- 粘性单元格背景必须**不透明**，且与行的悬停/选中态一致：行使用实色背景（`bg-surface` / `hover:bg-surface-2` / 选中 `bg-primary-soft`，**不用透明度**），单元格 `background: inherit`。
- 只有在内容实际可横向滚动且未滚到最右时，才显示左侧分隔线与内阴影（提示"右侧被遮住的部分在这里"）。实现：监听容器 `scroll` + `ResizeObserver`，`scrollWidth − clientWidth − scrollLeft > 1`。
- 表头同列同样 sticky，并与数据行 z-index 配合（表头 2，单元格 1）。

### 可以

- 需要时同样固定首列（复选框 + 名称），但同时固定两侧时要确保窄屏（≥640px 表格模式）中间仍有 ≥ 240px 可读区域。

## 6. 编辑形式：展开行 vs 弹窗

两种 Web 端典型形式都提供，并允许用户在 Display options 中切换：

| 形式 | 适用 | 特点 |
| --- | --- | --- |
| **展开行（默认）** | 字段 ≤ 8、需要参照相邻记录 | 该行替换为表单（`colSpan` 全宽、浅蓝底），表格上下文保留；同一时刻只允许一个编辑态 |
| **弹窗（Dialog）** | 字段多、需要全宽、或列表很长 | 同一个表单组件放入 `Dialog(size=lg)`；焦点陷阱、Esc 关闭、移动端底部抽屉 |

### 必须

- 两种形式复用**同一个表单组件与校验函数**，差异只在容器。
- 打开编辑前记录触发按钮，取消/保存/关闭后焦点**回到该 Edit 按钮**。
- Edit 按钮 `aria-expanded`（展开行模式）或 `aria-haspopup="dialog"`（弹窗模式）。
- 删除按钮只出现在编辑态内部（最左侧），并经确认框。

## 7. 批量操作

- 选中 ≥ 1 行时底部居中浮现深色操作条（`fixed; bottom: 16px`），内容：`n selected · Clear · Delete`。
- 浮条宽度 `calc(100% − 32px)`，最大 520px，不遮挡页脚链接之外的交互。
- 删除走统一确认框并列出受影响记录；完成后 toast + Undo。

## 8. 窄屏退化（< 640px）

表格切换为 **卡片列表**（`<ul>`）：

```
[☐] [A] www.myexample.com            ⚠   Edit
     199.168.103.236
     Proxied · TTL Auto
```

- 第一行：复选框、类型 Badge、名称（截断）、警告、Edit。
- 第二行：内容（等宽、允许断行 `break-all`）。
- 第三行：次要属性以 `·` 分隔，自动折行。
- 编辑态在卡片内展开为单列表单。

### 为什么不是横向滚动？

横向滚动的表格在手机上几乎不可用：用户看不到最右的操作列，且滚动与页面滚动冲突。640–1023px 之间保留横向滚动（表格仍可读）；更窄时必须重排。

## 9. 空态

| 场景 | 标题 | 描述 | 动作 |
| --- | --- | --- | --- |
| 无数据 | No DNS records yet | Add your first record… | primary `Add record` |
| 无匹配 | No records match | Try a different search… | `Clear search & filters` |
| 无推荐 | No recommendations | 说明何时会出现 | 无 |

## 10. 性能注意

- 过滤与排序使用 `useMemo`，依赖 `[records, debouncedQuery, appliedFilters, sort]`。
- 搜索防抖；筛选草稿不触发表格重算。
- 列表 key 使用稳定 id，避免编辑态切换时整表重挂载。
- 数据持久化到 `localStorage` 的写入在 `setState` 回调中一次完成。
