# DNS 列表与编辑表单功能

默认对象为 fable 当前归档源码；这里逐项记录设计、操作和实现边界。sonnet/gpt 的分页、离开保护和导入增强另见[补充功能](feature-supplements.md)，不能当作 fable 已有能力。目标应满足的规范见[表格](tables.md)、[表单](forms.md)。

视觉对照可看已归档的 [1440px DNS](builds/shots/fable-dns-1440-2026-10-08.webp) 与 [390px DNS](builds/shots/fable-dns-390-2026-10-08.webp)；编辑、错误和浮层等其他状态仍需实际打开预览。

## 源码定位

| 代号 | 入口 | 负责的功能 |
|---|---|---|
| D1 | [DnsRecordsPage](../assets/sources/fable5.1-high/src/pages/dns/DnsRecordsPage.tsx) | 页面、数据管线、列配置、选择、编辑容器、保存删除、导入导出 |
| D2 | [DnsRecordForm](../assets/sources/fable5.1-high/src/pages/dns/DnsRecordForm.tsx) | 字段布局、类型联动、校验、提交、dirty |
| D3 | [records](../assets/sources/fable5.1-high/src/data/records.ts) | 记录类型、初始数据、名称规范化、TTL 文案、字段校验 |
| D4 | [table](../assets/sources/fable5.1-high/src/components/ui/table.tsx) | 列宽状态、拖拽、键盘和持久化 |
| D5 | [primitives](../assets/sources/fable5.1-high/src/components/ui/primitives.tsx) / [overlays](../assets/sources/fable5.1-high/src/components/ui/overlays.tsx) | Field、输入控件、Dialog/Popover/Toast |

## 页面层次与查找

| 功能 | 设计细节 | 交互流程与结果 | 边界 / 入口 |
|---|---|---|---|
| 页标题与引导 | 资源标题、副标题、设置状态徽章、文档按钮；Pending 提示在任务区上方 | 提示可关闭；文档按钮跳说明；不抢占主编辑流程 | 提示关闭为本页状态；非后台检测结果，D1 |
| Recommendations | 可折叠卡片，状态概括在标题右侧 | 展开查看 All set / No recommendations 示例 | 静态内容，没有推荐规则引擎，D1 |
| 工具栏 | 搜索优先，Filters/Display/Import/Export/Add 分组；宽屏左右排列，窄屏堆叠/换行 | 各入口打开对应面板或执行；新建打开时主 Add 禁用 | 控件收纳也是模板，不能只复制列表，D1 |
| 文本搜索 | 前置放大镜、清除按钮；与条件 chips 区分 | name/type/content/comment 忽略大小写；150ms debounce；路由 `q` 初始化；清除后回输入焦点 | 不检索 proxy/TTL；不同于另外两稿 deferred value，D1 |
| 多条件筛选 | Popover 每行字段/操作符/值；新增/删除行，底部 Apply；生效条件显示 chips | name/type/content/comment；contains/equals/startsWith；有效行以 AND 组合；草稿关闭不应用；Enter 可提交 | 空值忽略、全空禁用 Apply、最后一行不可删；chip 移除只改 applied，草稿可能仍保留旧条件，D1 |
| 清除筛选 | 搜索清除、chip 单删、Filters 内 Clear、空态 Clear search & filters | Filters 内 Clear 重置 draft/applied；空态清搜索和 applied | 空态动作/chip 移除未同步草稿；重开面板需核对，不能把两套状态混为一个，D1 |
| 空结果 | 空态与查找工具保留 | 搜索/筛选变更后重新得到记录 | 区分无记录和无匹配，并验证目标空态动作；本地列表无真实加载/网络错误态，D1 |

## 桌面列表、卡片与列控制

| 功能 | 设计细节 | 操作与结果 | 边界 / 入口 |
|---|---|---|---|
| 默认表格 | 选择、警告、Name、Type、Content、Proxy、TTL、Comment、Details、Actions；功能列固定 | colgroup + fixed layout；表最小宽度由当前可见列之和决定，局部横滚 | 保留真实 table 语义；不能为了塞进容器把全部列任意压扁，D1 |
| 记录阅读 | 名称及淡色域名后缀；等宽 Content 截断且有 title；橙云/文字代理状态；TTL/评论/优先级详情 | 警告图标有 Tooltip；编辑动作与长数据分离 | title 不是完整触屏长内容查看方案；代理不是只靠颜色，D1/D3 |
| 排序 | Name/Type/Content 表头按钮带当前方向图标 | 首次升序 → 降序 → 关闭；字符串 localeCompare | 非 TTL/Modified 数值排序；源码 aria-sort 放在 button，目标应放在列头，D1 |
| 固定操作列 | 右侧表头与单元格粘性、实色背景；还有右方内容时显示边缘阴影 | 横滚仍可点 Edit | 与父滚动层/背景一起复用；不要声称已冻住所有列，D1 |
| Display | proxy/ttl/comment/details 选择；compact/comfortable；inline/dialog | 偏好分别持久化；Reset widths 恢复全部列宽 | 改 editMode 会直接清 editingId，没有 dirty 确认；需补保护，D1 |
| 列宽拖拽 | 可调列边界有拖拽手柄；固定列无手柄 | pointer capture；拖动 React state 预览，松手存储；各列 min/max 限制 | pointercancel 清拖动但不回滚预览；读取持久值未按列边界夹取，D4 |
| 列宽键盘 | 手柄可聚焦、separator 信息 | ←/→ 16，Shift 64；Home 或双击回默认；Reset all | 没有 End；aria min/max 统一 60/720，可能不同于真实列边界，目标需修，D4 |
| 手机卡片 | 640px 以下由 table 切 card；内容换行，类型徽章、名称、代理/TTL/优先级、选择/Edit | 同一数据和回调驱动两种阅读形态 | 卡片没有全量桌面列；当前两分支 CSS 隐藏，行内表单可同时挂载、ID 独立但草稿各自一份；需避免隐藏编辑器重复状态，D1 |
| 底部统计 | 记录范围、总数、使用配额 | 数据变动后更新计数 | “Showing 1–N of N”不是分页；N/200 是展示，保存未强制容量，D1 |

列宽原值用于保留此稿的密度，不作为所有表格的要求：Name 默认 240、范围 140–520；Type 90/70–160；Content 300/160–720；Proxy 140/110–220；TTL 90/70–160；Comment 180/100–400；Details 120/90–240；Select/Warnings/Actions 固定 48/32/88。改字段或改单位时同步检查列和、横滚、粘性背景与窄屏形态。

## 选择、批量与编辑容器

| 功能 | 设计与状态 | 触发 → 结果 | 边界 / 入口 |
|---|---|---|---|
| 单选 / 全选 | 行复选框，表头部分选中态；Set 存记录 ID | 单选切换 ID；全选将 Set 替换为当前可见 ID，全取消清空 Set | 单选可保留被过滤的隐藏选择；全选却替换范围。批量计数是整个 Set，需要明确范围，D1 |
| 批量条 | 底部固定深色条，数量、Clear、Delete；出现不改正文流 | Clear 清选择；Delete 走同一危险确认 | 未见专门预留底部遮挡空间；无分页/Shift 连选/批量改代理，D1 |
| 新建 | 列表上方独立编辑卡；沿用同一表单 | Add 打开、清行编辑、主 Add 暂禁用；取消关闭 | 新建与编辑切换不能静默丢 dirty，需挂载端补保护，D1/D2 |
| 行内编辑 | 原记录行替换为整行 colspan 表单；单个 editingId | Edit 记住触发器；取消关闭并明确回焦 | 与 sonnet “原行下插入、可多行”不同；桌面/卡片双挂载缺口见上，D1 |
| 弹窗编辑 | lg Dialog；共享字段和校验；窄屏转底部 sheet | Edit 开 Dialog；取消/关闭调用共享 closeEdit | 所有浮层关闭与 dirty 的关系需补；不独立写一套校验，D1/D2/D5 |
| 保存 | 按钮 spinner/忙碌，表单输入保留 | 模拟 350ms；name→FQDN；新记录前插或按 ID 替换；Toast 成功；关闭编辑器 | 记录存 `cfui.dns.records`；新建明确回 Add，编辑保存未显式回原触发器；无真实 API，D1 |
| 删除确认 | 明列受影响记录及删除后果；取消/危险按钮 | 确认移除本地记录、清选择/编辑；Toast 有 Undo | 危险按钮 data-autofocus，不能认定默认焦点安全；Undo 前插记录，不恢复原顺序/服务端事务，D1/D5 |

## 表单字段与联动

表单初始编辑值将当前资源名称转换成 `@` 或相对名；默认聚焦 Type。宽屏用 12 列、sm 6 列、窄屏单列；Type/Name/Content 的扫描顺序稳定，评论占整行。控件、提示、错误和尾部动作都属于单元，不只复用字段名称。

| 字段 / 机制 | 设计 | 输入或状态改变后的行为 | 限制 / 入口 |
|---|---|---|---|
| Type | A、AAAA、CNAME、MX、TXT、NS、SRV、CAA 下拉 | 类型元数据切换 Content 标签/占位/帮助；TXT 用等宽 textarea，其他等宽 Input | SRV/CAA 为简化模型，不是完整协议编辑器，D2/D3 |
| Name | 必填，接受 `@`、相对名或完整名称；“resolves as” 提示 | `toFqdn` 规范化到固定 ZONE；编辑时转换显示形式 | 目标必须对接资源上下文，不能保留演示常量，D2/D3 |
| Content | 类型对应 IP、目标主机、文本等文案 | blur 后按类型显示错误；数据长时保持可编辑 | IPv6 正则是样例；SRV/CAA 语义验证不完整，D2/D3 |
| Priority | MX/SRV 才显示，和 Content 共同行布局 | 数值检查 0–65535 | 服务端仍需完整记录语义验证，D2/D3 |
| Proxy | A/AAAA/CNAME 才显示云图标、状态文字和开关 | 开启强制 Auto TTL；不支持类型关闭代理 | 不能把灰控件当唯一状态说明，D2/D3 |
| TTL | 常用时长下拉；代理开启时禁用并显示 Auto | Auto 用数值 1；否则可选 60…86400 等值 | 未显式全面校验 TTL，数据契约需补，D2/D3 |
| Comment | optional、100 字计数，超限变危险色 | 超限报错；不因无评论阻止保存 | gpt 是 200 字，不要混用文案和限制，D2/D3 |

## 校验、失败与未保存数据

| 阶段 | 源码实现 | 复用时要补或验证 |
|---|---|---|
| 输入与 blur | touched 控制何时显示字段错误；Field 的帮助/错误、图标和文本呈现；提交后显示错误数量 | 检查错误 ID/aria-describedby 有效；不要遗漏可见标签或把帮助当占位符，D2/D5 |
| 客户端校验 | 名称、IPv4、简化 IPv6、目标主机、TXT ≤2048、优先级、评论；CNAME 同名共存冲突和同 type/content 重复排除当前 ID | 完整 DNS 与服务端冲突/权限另实现，不把本地数组检索当后端校验，D2/D3 |
| 首错定位 | submit 标记已提交并尝试 query 首个无效字段 | 同步查询发生在 submitted 重渲染前，首次提交是否定位正确未证明；应在错误 DOM 更新后聚焦，D2 |
| 保存中 | `saving`、await onSave、finally 清忙碌；共享 Button 禁用提交 | Cancel/Delete 并非全部禁用；需要防重复写、取消竞态和卸载后状态更新，D2 |
| 保存失败 | 表单没有自己的 catch / 服务器错误面板 | 接真实 API 后捕获异常、保留输入、显示错误、允许重试；可以参考 gpt，但保留 fable 视觉，D2 |
| dirty 与离开 | JSON 对比初始值；dirty 时 beforeunload preventDefault | 没有持久草稿、SPA guard 或取消舍弃确认；浏览器关闭保护不能覆盖站内切页/切模式，D2/D1 |
| 窄屏尾部动作 | 源码使用 flex-col-reverse | 视觉顺序与 DOM/Tab 顺序可能不一致；目标按表单规范修正，不照搬缺陷，D2/D5 |

## 导入与导出

| 功能 | 设计与操作 | 实际范围与边界 |
|---|---|---|
| Import | Dialog 中粘贴 zone 风格文本；解析后给反馈，加入记录 | 简化 BIND 解析；跳过不支持/过短/注释行，接受可解析子集；Auto TTL=1、DNS only，忽略输入 TTL；缺全面校验/冲突/预览；不同于 gpt 全批预检，D1 |
| Export | 工具栏下载 zone 文本 | 导出所有记录，不按筛选或选择；Auto 转 300；proxy/comment 不序列化，SRV/CAA 不完整；Blob URL 释放。不能宣称导入导出无损往返，D1 |

## 此单元的复用检查

按“查找 → 选中 → 打开 → 类型联动 → 错误 → 保存/取消 → 回焦 → 删除/恢复”走完整路径；另外核对列宽持久化、横滚末端 Edit、卡片长内容、筛选后的隐藏选择、编辑中切模式/切页面、导入混合合法非法记录与导出范围。桌面表格看起来一致，不足以证明编辑表单与手机卡片已完整迁移。
