# 数据表格（DNS 记录为范本）

为什么是这个骨架：用户进列表页只想“找到一条记录并改它”，所以 PageHeader 一句话 + 搜索左伸缩 +
主操作最右 + 批量悬底 + 行末 Edit 常驻，三工程骨架完全一致。

## 骨架 9 层

`PageHeader(h1唯一+desc≤2行+actions≤3) + Alert汇总 + Collapsible推荐 + 工具栏 + chips + 新增卡 + 表格卡(配额条+表+Showing) + 浮动批量条 + 分页`

- 工具栏：`flex-col lg:row，搜索 flex-1 max520（防抖150ms）+ Filters + Display + Import/Export(icon-only带名) + Add primary最右`。
  <1024 搜索独占一行 wrap；按钮图标+文字，窄屏文字可 `sr-only` 留图标但保可访问名。
- 导入导出（gpt `docs/02` §7）：JSON 导入先整体校验（必填 type/name/content、1MB 上限、总数上限如 200、重复检查），
  **任一失败整个导入拒绝、零部分写入**；导入生成本地新 ID（来源 ID 不可信）。
  导出未选中导全部、选中导所选，Blob 下载后释放 object URL。
- Filters：草稿/应用分离，Apply/Enter 才生效，无值禁用，<640 两行重排，`role=dialog + 首焦 + Esc还焦`，宽 `min(560,100vw-16)`。
- Display：列显隐 + 密度，localStorage；空态分零数据 vs 零匹配（后者给“清除搜索与筛选”）。

## 表结构

- `Card > div overflow-x:auto(可聚焦 region) > table fixed + colgroup + thead sticky + tbody`，页面永无横滚。
- 每列 min/max（如 Name140-520/Content160-720），固定列禁调，加填充列吸余（防 100% 拉伸失真）。
- 表头内按钮三态（升/降/无）+ `th aria-sort`，激活强调；数值列按数值排，其余 locale。
- 首列复选：24 命中包 16 视觉 + indeterminate + Shift 连选 + 头“本页全选” + “选全部匹配”（跨页 Set 解耦，翻页不丢）。
- 行：hover surface-2，选中 primary-soft + `aria-selected`；长格 `max+truncate+title`，技术值等宽+break-all，等宽内容 tabular。
- 末列操作 `sticky right0 + 背景 inherit 行实色 + scroll+RO>1 才显阴影 + 头 z2 体 z1`；Edit 文（主行操）+ Delete 图标，
  `aria-label="Edit A record www…"`，禁中列 Edit、禁整行点编、禁粘无背。

## 列宽拖拽

- 8px 热区 / 1px 线 / hover 3px 主色，`role=separator + aria-valuenow/min/max + ←→8 / Shift32 / Home还原 / 双击还原`
  （用 sonnet 口径 8/32；fable 为 16/64，同产品只用一组，见 SKILL 收敛口径）。
- 拖时只写 DOM（`<col>/table style`），松手才 setState+localStorage；隔条止冒泡防误排序；拖完 `body user-select:none` 还原。

## 行内展开 vs 弹窗（共用同一表单）

- 共用 RecordEditor + 同一 `validateRecord`，Display 选项记住（`nimbus.dns.edit inline/dialog`）。
- 展开：紧跟 `<tr><td colSpan全>` 内 `sticky left0 width var(--sw)`，--sw 由 scroll 维护，横滚停可视；
  内 `grid auto-fit minmax(min(260px,100%),1fr)`；窄卡内展；默认行内（上下文不丢，可多行独存）。
- 弹窗：离表专注一次一，原生 dialog + 陷阱 + Esc + `aria-haspopup=dialog`。
- 开焦首字段，关后回 Edit，`aria-expanded/controls`；保存进度防重，成功收起 + Toast + 高亮行。
- 行内/弹窗共用同一表单同一校验是交互逻辑，整体迁移；只有一种挂载点时只取该形态并声明，不算拼凑。例：单文件页无行内展开位，只做 dialog＋同一 validateRecord。

## 批量与分页

- 批量条 `fixed bottom16 宽calc-32 max520 深色 + 数量live + 选全部 + 动作 + 清除`，禁顶插（勾首表移连选错）。
- 删除确认 + 8s Undo（优于强确认），改直行 + Undo，不适用明示（如 `2 Proxied·3 skipped`）。
- Undo 快照实现（sonnet `data.tsx`）：**快照先行**——`bulkUpdate(ids, patch)` 先筛出 `prev` 再改并返回更新前记录，
  `restoreSnapshots(prev)` 按 id 回写；删除 `removeRecords` 返回 `{rec,index}`，`restoreRecords` 按 index 排序 splice 归位。
  没有快照返回值的"可撤销"都是假的。
- 分页左 `Showing 1–10 of N(filtered from M) live` 右 Rows+上下；搜筛量变回页 1；`?highlight` 翻到行央闪亮 2.4s。

## 窄屏（<640 容器切卡；sonnet 工程为 <700，统一用 <640）

- `thead` 保留语义但视觉隐藏，`tbody tr:grid 24px 48px 1fr 32px`：类型/名称/Edit + 内容跨列换行 + 代理/TTL；
  排序/全选移入 Display；焦点移交（表头→搜索框）；表卡只渲染其一。
