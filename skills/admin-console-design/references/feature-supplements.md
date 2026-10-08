# sonnet 与 gpt 的补充设计和交互

本页用于选择局部补强方案，不要求把三稿的功能全部合并。默认视觉仍以所选整体模板为准；补充逻辑要通过适配层接入，别连带换成另一套按钮、密度和页面结构。fable 主稿目录见[外壳](feature-shell.md)、[DNS](feature-dns.md)和[其他模式](feature-patterns.md)。

## sonnet：导航状态、列表操作与恢复

| 代号 | 源码入口 |
|---|---|
| N1 | [Sidebar](../assets/sources/sonnet5.5xhigh/src/dashboard/Sidebar.tsx) |
| N2 | [DnsRecords](../assets/sources/sonnet5.5xhigh/src/dashboard/pages/DnsRecords.tsx) |
| N3 | [columns](../assets/sources/sonnet5.5xhigh/src/ui/columns.tsx) |
| N4 | [RecordEditor](../assets/sources/sonnet5.5xhigh/src/dashboard/RecordEditor.tsx) / [recordModel](../assets/sources/sonnet5.5xhigh/src/dashboard/recordModel.ts) |
| N5 | [data](../assets/sources/sonnet5.5xhigh/src/dashboard/data.tsx) |
| N6 | [Stage](../assets/sources/sonnet5.5xhigh/src/showcase/Stage.tsx) / [Legacy](../assets/sources/sonnet5.5xhigh/src/dashboard/Legacy.tsx) |

| 功能 | 设计与交互细节 | 取用边界 / 入口 |
|---|---|---|
| 六类侧栏状态 | pinned 固定偏好、hover 指针意图、kbFocus 焦点意图、forced 显式临时展开、suppressed 收起抑制、drawer 移动入口；240/56/0 槽宽 | medium 强制 Rail，wide 才按 pinned 分配槽；peek 覆盖不推内容，别把规则直接写成 fable 已实现，N1 |
| hover / keyboard / forced | 进入 120ms、离开 250ms；touch 不触发 hover；`:focus-visible` 设 kbFocus；forced 点外部/Esc 清；离开面板清 kbFocus | forced 关闭不等于所有临时输入意图都清；Esc/混合输入仍需验证，N1 |
| 收起与分组 | 宽屏固定开关清 hover/kbFocus/forced，指针尚在时抑制到离开；Rail 分组点击强制展开并打开该组；导航清 forced/抽屉 | 分组动作不同于 fable 直接导航首子页；隐藏子项的实际可聚焦性需在目标核对，N1 |
| 列宽 | 局部拖拽预览、结束提交与存储；←/→8，Shift32，Home 最小、End 最大、Enter/双击默认 | Name 原值默认200、最小120、最大720；保留同一键位文案/aria/边界，不能配 fable 的 Home 默认值提示，N3 |
| 数据管线 | 搜索 useDeferredValue → AND 筛选 → 排序 → 分页；TTL/proxy/modified 用数值排序 | deferred 不是固定毫秒 debounce；搜索/筛选/pageSize 改变回第1页，N2 |
| 分页与回定位 | 5/10/25/50、上一页/下一页、范围计数；`highlight` 找目标页并滚到可见 row/card | 用真实 ID 定位，而非假设记录在当前页；不是后端分页实现，N2 |
| 页选择与 Shift | 表头当前页全选及 indeterminate；保留页外 Set；Shift 对当前页上次点击到本次项区间增删；另可选全部匹配 | selRows 为当前匹配结果中已选记录，不等于整个 Set；筛选后隐藏选择与批量范围需解释，N2 |
| 表/卡与滚动 | 容器低于700切卡；选择列和操作列 sticky；表滚动区可聚焦、有名称/边缘提示；Display 有 Modified 等列 | 与 fable 的 viewport640 不同，容器观察一起取用；字段/列与模型同步，N2 |
| 行内 / dialog / 全页 | editing Set 可开多行，原行下展开 RecordEditor；dialog 用同一编辑器；Open full form 链接 | 分页或过滤导致编辑器卸载仍可能丢局部输入，不能以有 nav guard 推断所有切换安全；容器转换要额外验证，N2/N4 |
| 编辑字段与保存 | 六类型 A/AAAA/CNAME/MX/TXT/NS；名称后缀 addon、TXT textarea、MX priority、proxy/TTL 联动、100字 comment；改 Type 清 Content；450ms 模拟保存后检查 conflicts | 紧凑编辑器无顶部错误摘要；namedItem 聚焦首错；服务错误保输入；实际是本地冲突检查，非 API，N4/N5 |
| dirty 与离开保护 | 编辑器上报 dirty；取消/Esc close 走 discard confirm；注册站内 nav guard 和 beforeunload；关闭/保存回可见 Edit；保存后高亮2600ms | 这是列表挂载端与表单一起完成的能力；不能只复制 RecordEditor 就宣称有保护，也不保证所有浏览器返回路径，N2/N4 |
| 批量代理 | Proxied/DNS only；只处理支持类型且状态需改的匹配已选记录，报告 changed/skipped；代理开启 TTL=0 | 旧值 snapshot 支持本地 Undo；代理关闭未必恢复原 TTL，目标需定义；不假冒服务器批量事务，N2/N5 |
| 删除与恢复 | 确认后删除，Toast Undo；删除保存 `{rec,index}`，按原索引恢复；批改按ID恢复旧快照 | 比 fable 前插更完整，仍有并发/后端恢复边界；记录是内存 useState，刷新不保留修改，N2/N5 |
| 导出 | 普通导出与选择导出传入不同 list；文本 zone 格式，Auto→300 | proxy/comment 不导出；不是无损格式，N2 |
| 导入 | 粘贴简化 `name type content` 文本；MX 支持 priority；显示行号解析错误并焦点回文本；有错误则整批不写 | 未完整验证 IP/名称/TTL/重复/CNAME 冲突；不能称与 gpt 相同的全面预检；Auto0、DNSonly，N2/N5 |
| 设计舞台 / Legacy | 新舞台用真实 iframe、场景/视口/主题 controls、底部 hover dock；Legacy 提供旧式后台对照 | 用户调整后的 Stage 已归档；hover 不压工作台。设计工具不是产品功能，旧对照不作为复用基底，N6 |

数据与偏好分开理解：N5 的 records/sites 是内存 `useState`，不是 localStorage 数据库；sidebar pinned、列宽、编辑模式等偏好有持久化。生产读写和撤销需要独立接线。

## gpt：草稿、错误恢复与导入预检

| 代号 | 源码入口 |
|---|---|
| G1 | [DnsConsole](../assets/sources/gpt6astra-max/src/components/DnsConsole.tsx) |
| G2 | [RecordForm](../assets/sources/gpt6astra-max/src/components/RecordForm.tsx) |
| G3 | [data](../assets/sources/gpt6astra-max/src/lib/data.ts) / [hooks](../assets/sources/gpt6astra-max/src/lib/hooks.ts) |
| G4 | [acceptance.spec](../assets/sources/gpt6astra-max/tests/acceptance.spec.ts) |

| 功能 | 设计与交互细节 | 取用边界 / 入口 |
|---|---|---|
| 两层导航 | 控制台外壳与站点导航分别存在，站点含 Overview/Analytics/DNS/Email/Security/Performance/Settings | 两层模型和各自断点不是 fable 必须增加的结构；Email 从同一数据筛 MX/TXT，非邮件服务，G1 |
| 容器回流 | ResizeObserver 在 DNS 容器≤640转 cards；导航/头部消失时转移焦点 | 真容器宽度决定形态；不只用 viewport media query；列宽调整未实现，G1 |
| 查找与分页 | useDeferredValue 搜索、draft/applied filters、排序、10/25/50；页码夹取合法范围 | query/rules/pageSize/section 变化清 selection 并回第1页；与 sonnet 保留 Set 的策略不同，G1 |
| 表单结构 | 编号 Basic/Resolution 两区、type/name/content/proxy/TTL/priority/comment；底部草稿状态和动作；comment200 | 五类型 A/AAAA/CNAME/MX/TXT；按其数据类型适配，不把字符串TTL直接写入 fable 模型，G2/G3 |
| 新建草稿 | `edgelab.draft` 保存新建值，恢复时验证结构；成功后清草稿；编辑不持久草稿 | 草稿键为演示；应按用户/资源隔离；有草稿不等于全部取消/SPA guard 完备，G2 |
| 保存失败恢复 | blur/touched 和修正错误；550ms 模拟延迟；saving 防重入；simulateFailure 抛错；错误面板聚焦、保输入、可重试；alive/timer 清理 | 不是实时 API；接线保留错误恢复契约，同时继承主稿视觉；inline成功回焦与dialog外层协作需验证，G2 |
| 记录持久化与配额 | `edgelab.records` 读取检查数组、记录结构、≤200、ID 唯一；保存检查容量、重复、代理TTL规范化 | localStorage 为演示数据；容量是本地限制而非真实套餐；重复键为 type/name/content，不是所有 DNS 冲突规则，G1/G3 |
| 导出 / 删除 | 有选择导出所选，否则全部；JSON；删除确认后写本地状态 | 不按当前页冒充全量；没有删除 Undo；JSON不是BIND格式，G1/G3 |
| 文档与验收 | 附分级说明、实现/验收边界和 Playwright 案例 | G4 可改造成目标测试；历史测试结果和源码检查不能算目标通过，不把已有接受测试全量执行当本目录事实 |

### JSON 导入的完整流程

G1 的 `ImportRecords` 在一个 Modal 中提供文件选择、粘贴文本、填入示例、错误面板、取消和“校验并导入”。文件读取中禁用提交；readVersion/alive 防止旧读取或卸载后的结果覆盖当前输入。

1. 文件和文本均限制 1MB；解析 JSON，要求非空数组，或含 records 的对象。对象若带 domain/version，分别要求当前演示域名和 version1。
2. 检查现有数量加本批不超过200；逐条检查对象、支持 type、string name/content；默认值补齐，trim，代理类型和TTL规范化，每条分配新ID。
3. 对每条运行 `validateRecord`；任一错误报告该条序号，不调用 onImport。合法结构仍需按字段规则校验。
4. 用 recordKey 检查与现有记录和批内重复；全部通过后才一次调用 onImport(next)。失败显示 alert 并 rAF 聚焦，保留输入供修改重试。

这是**本地状态写入前的整批预检**，不是服务端事务。默认值/规范化允许部分输入被转换，并非对所有未知字段实行严格 schema 拒绝；也没有因此覆盖全部 DNS 共存冲突。接真实导入 API 时仍需权限、资源匹配、服务器校验与原子性契约。

## 选择补充方案

需要分页/范围选择/批量恢复时，读 N2/N5；需要列宽精确键位时，读 N3；需要站内编辑保护时，连同 N2/N4/路由 guard 取用；需要新建草稿与失败重试时，读 G2；需要完整导入流程时，读 G1/G3。每次只采用当前任务需要的机制，记录与基底的必要差异，并在目标中验证。
